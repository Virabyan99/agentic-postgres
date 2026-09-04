"""The evaluation harness: cases derived from the compiled contract (ADR 0184).

**The one rule this module keeps**: every case it derives is generated from the
approved capability contract and never from the runtime. A positive case is a
request the contract permits; an adversarial case is a request the contract
does not permit, produced **per field** the contract freezes -- one case for
the scope set, one for the column allowlist, one for the filter allowlist, one
for the operator allowlist, and so on -- mechanically, so that nothing here
encodes what the implementation happens to do. D868 is why: *an adversarial
case whose expected denial was written from the implementation is a description
of the implementation.*

So a case carries an EXPECTATION and never a denial reason. Three expectations
exist and the third is the one a first draft would have got wrong:

- ``permitted``  the contract permits this; the runtime must serve it;
- ``refused``    the contract does not permit this; the runtime must refuse it,
                 and WHICH boundary refused is observed, never asserted here;
- ``bounded``    the contract permits this and bounds it -- a ``limit`` above
                 ``max_rows`` is clamped rather than refused (ADR 0127, D937),
                 and a listing held on fewer scopes is filtered rather than
                 refused (D421). A harness that only knew "permitted" and
                 "refused" would have called both of those defects.

**Hand-written cases are counted separately** and are bound to the capability
version they were written against: a capability whose version moves without
its cases moving fails the gate and CI, which is what gives `version` a reader
with consequences. Written cases live in ``tests/evaluation-cases.yaml``.

Nothing here imports the runtime. The evaluation -- running each case against
the agent plane's own request builders with a fake upstream -- is
``tests/contract/test_evaluation_harness.py``'s, because that is the one place
the service package is importable without a container. This module derives,
validates, counts and renders; it decides nothing about outcomes.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

from agentic_postgres import REPO_ROOT
from agentic_postgres.capability_compiler import canonical_bytes
from agentic_postgres.config import load_schema

#: The three verdicts a case may expect. `bounded` is the one that keeps the
#: harness honest about clamping (D937): a contract that bounds a value is not
#: a contract that refuses it.
EXPECTATIONS = ("permitted", "refused", "bounded")
KINDS = ("positive", "adversarial")
ORIGINS = ("derived", "written")

#: Where the hand-written cases live. Beside the acceptance registry rather than
#: under `contracts/`, because a case is a proof's input and not a reviewed
#: surface -- the contract is the authority, the cases are questions asked of it.
WRITTEN_CASES_PATH = REPO_ROOT / "tests" / "evaluation-cases.yaml"

#: The two write-tool parameters the runtime requires and the contract does not
#: carry (ADR 0181). A third copy, deliberately, of `mcp_tools.RESERVED_WRITE_
#: PARAMETERS` and `render-mcp-catalog`'s -- with a contract test between all
#: three (D486's arrangement). Cases are derived for both because a caller meets
#: them on every write, whether or not the contract names them.
RESERVED_WRITE_PARAMETERS = ("idempotency_key", "dry_run")

#: A well-formed idempotency key for derived cases: the shape migration 0029
#: enforces and `mcp_tools.IDEMPOTENCY_KEY_PATTERN` mirrors, 8 to 255 printable
#: ASCII characters. Constant so a derived case is reproducible byte for byte.
DERIVED_IDEMPOTENCY_KEY = "eval-harness-0000000001"

#: A key the pattern refuses, for the reserved-parameter case.
MALFORMED_IDEMPOTENCY_KEY = "x"

__all__ = [
    "DERIVED_IDEMPOTENCY_KEY",
    "EXPECTATIONS",
    "KINDS",
    "ORIGINS",
    "RESERVED_WRITE_PARAMETERS",
    "WRITTEN_CASES_PATH",
    "Case",
    "HarnessError",
    "capabilities_of",
    "contract_digest",
    "coverage",
    "derive_cases",
    "filter_operators",
    "load_written_cases",
    "render_report",
]


class HarnessError(ValueError):
    """A case set that cannot support the claim: a capability without cases,
    a written case bound to a version the contract no longer declares, or a
    case naming a capability the contract does not compile."""


@dataclass(frozen=True)
class Case:
    """One question asked of the contract.

    `field` names the contract member the case exercises; `probe` says whether
    the case shapes the REQUEST or the upstream RESPONSE (a budget is checked on
    the way out, so its adversarial case is a response the contract's bound
    forbids). `scopes` is what the caller holds. `call` is the tool invocation,
    keyed by the runtime's own parameter names. `upstream` describes the fake
    response the evaluation returns -- rows, or one row of a given size.
    """

    id: str
    capability: str
    tool: str
    kind: str
    origin: str
    field: str
    expects: str
    scopes: tuple[str, ...]
    call: dict[str, Any]
    probe: str = "request"
    upstream: dict[str, Any] = field(default_factory=dict)
    capability_version: str | None = None
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        document = asdict(self)
        document["scopes"] = list(self.scopes)
        return document


def contract_digest(contract: dict[str, Any]) -> str:
    """The digest the lock records as `canonical_sha256` and the deployed
    document publishes as `capability_contract_sha256` -- the same bytes, so
    the report and the deployment can be compared by one number."""
    return sha256(canonical_bytes(contract)).hexdigest()


def filter_operators() -> tuple[str, ...]:
    """The closed operator vocabulary, read from the schema that owns it.

    The capability schema is the sole authority for the operator enum (its own
    description says so); a copy here would be a second one. Read from the
    schema so a derived case can name an operator the contract does not permit
    on a column without this module knowing which operators exist.
    """
    schema = load_schema("capabilities.schema.json")
    filters = schema["$defs"]["capability"]["properties"]["filters"]
    return tuple(filters["items"]["properties"]["operators"]["items"]["enum"])


def capabilities_of(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every capability the contract compiled, with the tool it backs.

    Keyed by capability name. At contract version 2 or above the names come
    from each tool's `capabilities` list; at version 1 -- where a tool declares
    no such list -- a read's capability is named on its resource and a write's
    or metadata tool's capability is the tool itself. Each entry carries the
    tool, its kind, the resource it backs when it is a read, and the version
    the contract declares for it (None at version 1).
    """
    found: dict[str, dict[str, Any]] = {}
    for tool in contract["tools"]:
        declared = {entry["name"]: entry for entry in tool.get("capabilities", [])}
        if tool["kind"] == "read":
            for resource in tool["resources"]:
                name = resource["capability"]
                found[name] = {
                    "tool": tool,
                    "resource": resource,
                    "version": declared.get(name, {}).get("version"),
                    "lifecycle": declared.get(name, {}).get("lifecycle"),
                }
            continue
        names = list(declared) or [tool["name"]]
        for name in names:
            found[name] = {
                "tool": tool,
                "resource": None,
                "version": declared.get(name, {}).get("version"),
                "lifecycle": declared.get(name, {}).get("lifecycle"),
            }
    return found


def _sample_value(operator: str) -> Any:
    """A value of the shape the operator takes. Nothing about it is meaningful."""
    if operator == "in":
        return ["harness-value"]
    if operator == "is_null":
        return None
    return "harness-value"


def _read_cases(name: str, tool: dict[str, Any], resource: dict[str, Any]) -> list[Case]:
    """A read capability's cases, one adversarial per frozen field."""
    tool_name = tool["name"]
    required = tuple(resource["required_scopes"])
    filters = resource["filters"]
    orderings = resource["order_by"]
    cases: list[Case] = []

    def case(**overrides: Any) -> Case:
        base: dict[str, Any] = {
            "capability": name,
            "tool": tool_name,
            "origin": "derived",
            "scopes": required,
            "probe": "request",
        }
        base.update(overrides)
        return Case(**base)

    # The base call: the first permitted filter, the first ordering, the ceiling.
    call: dict[str, Any] = {"tool": tool_name}
    if tool_name == "query_resource":
        call["resource"] = resource["name"]
        if filters:
            first = filters[0]
            operator = first["operators"][0]
            call["filters"] = [
                {"column": first["column"], "operator": operator, "value": _sample_value(operator)}
            ]
        if orderings:
            call["order_by"] = 0
        call["limit"] = resource["max_rows"]

    cases.append(
        case(
            id=f"derived:{name}:positive",
            kind="positive",
            field="operation",
            expects="permitted",
            call=call,
            upstream={"rows": 1},
        )
    )

    if required:
        cases.append(
            case(
                id=f"derived:{name}:required_scopes",
                kind="adversarial",
                field="required_scopes",
                expects="refused",
                scopes=required[:-1],
                call=call,
                upstream={"rows": 1},
            )
        )

    if tool_name == "query_resource":
        cases.append(
            case(
                id=f"derived:{name}:resources",
                kind="adversarial",
                field="resources",
                expects="refused",
                call={**call, "resource": f"{resource['name']}_no_such_resource"},
            )
        )
        cases.append(
            case(
                id=f"derived:{name}:columns",
                kind="adversarial",
                field="columns",
                expects="refused",
                call={**call, "columns": [f"{resource['name']}_no_such_column"]},
            )
        )
        # A column the caller may READ and may not FILTER on is the sharper
        # case; a made-up name is the fallback when every column is filterable.
        filterable = {entry["column"] for entry in filters}
        unfilterable = [column for column in resource["columns"] if column not in filterable]
        column = unfilterable[0] if unfilterable else f"{resource['name']}_no_such_column"
        cases.append(
            case(
                id=f"derived:{name}:filters.column",
                kind="adversarial",
                field="filters",
                expects="refused",
                call={
                    **call,
                    "filters": [{"column": column, "operator": "eq", "value": "harness-value"}],
                },
            )
        )
        if filters:
            first = filters[0]
            forbidden = [op for op in filter_operators() if op not in first["operators"]]
            if forbidden:
                cases.append(
                    case(
                        id=f"derived:{name}:filters.operators",
                        kind="adversarial",
                        field="filters",
                        expects="refused",
                        call={
                            **call,
                            "filters": [
                                {
                                    "column": first["column"],
                                    "operator": forbidden[0],
                                    "value": _sample_value(forbidden[0]),
                                }
                            ],
                        },
                    )
                )
        cases.append(
            case(
                id=f"derived:{name}:order_by",
                kind="adversarial",
                field="order_by",
                expects="refused",
                call={**call, "order_by": len(orderings)},
            )
        )
        # Above the ceiling is CLAMPED, not refused (ADR 0127): the contract
        # bounds the value, and the evaluation checks the bound was applied.
        cases.append(
            case(
                id=f"derived:{name}:max_rows",
                kind="adversarial",
                field="max_rows",
                expects="bounded",
                call={**call, "limit": resource["max_rows"] + 1},
                upstream={"rows": 1},
            )
        )

    # The response side of the row ceiling: an upstream that returns more than
    # the contract permits is refused rather than truncated.
    cases.append(
        case(
            id=f"derived:{name}:max_rows.response",
            kind="adversarial",
            field="max_rows",
            expects="refused",
            probe="response",
            call=call,
            upstream={"rows": resource["max_rows"] + 1},
        )
    )
    if "max_response_bytes" in tool:
        cases.append(
            case(
                id=f"derived:{name}:max_response_bytes",
                kind="adversarial",
                field="max_response_bytes",
                expects="refused",
                probe="response",
                call=call,
                upstream={"rows": 1, "bytes": tool["max_response_bytes"] + 1},
            )
        )
    return cases


def _write_cases(name: str, tool: dict[str, Any]) -> list[Case]:
    """A write capability's cases: the argument contract, the two reserved
    parameters, the two declarations, and the two response-side bounds."""
    tool_name = tool["name"]
    required = tuple(tool["required_scopes"])
    arguments = {argument: f"<{argument}>" for argument in tool["arguments"]}
    cases: list[Case] = []

    def case(**overrides: Any) -> Case:
        base: dict[str, Any] = {
            "capability": name,
            "tool": tool_name,
            "origin": "derived",
            "scopes": required,
            "probe": "request",
            "upstream": {"rows": 1},
        }
        base.update(overrides)
        return Case(**base)

    call = {
        "tool": tool_name,
        "arguments": arguments,
        "idempotency_key": DERIVED_IDEMPOTENCY_KEY,
        "dry_run": False,
    }
    # A capability declaring approval refuses its own positive call (D870):
    # the derived positive becomes an adversarial case of `requires_approval`.
    if tool.get("requires_approval"):
        cases.append(
            case(
                id=f"derived:{name}:requires_approval",
                kind="adversarial",
                field="requires_approval",
                expects="refused",
                call=call,
            )
        )
    else:
        cases.append(
            case(
                id=f"derived:{name}:positive",
                kind="positive",
                field="operation",
                expects="permitted",
                call=call,
            )
        )
    if required:
        cases.append(
            case(
                id=f"derived:{name}:required_scopes",
                kind="adversarial",
                field="required_scopes",
                expects="refused",
                scopes=required[:-1],
                call=call,
            )
        )
    cases.append(
        case(
            id=f"derived:{name}:arguments.unknown",
            kind="adversarial",
            field="arguments",
            expects="refused",
            call={**call, "arguments": {**arguments, "not_an_argument": "harness-value"}},
        )
    )
    if arguments:
        cases.append(
            case(
                id=f"derived:{name}:arguments.missing",
                kind="adversarial",
                field="arguments",
                expects="refused",
                call={**call, "arguments": dict(list(arguments.items())[:-1])},
            )
        )
    cases.append(
        case(
            id=f"derived:{name}:idempotency_key",
            kind="adversarial",
            field="idempotency_key",
            expects="refused",
            call={**call, "idempotency_key": MALFORMED_IDEMPOTENCY_KEY},
        )
    )
    if "supports_dry_run" in tool and not tool.get("requires_approval"):
        # A permission, so the derived case's KIND follows the declaration: a
        # write that supports a rehearsal gets a second positive; one that does
        # not gets an adversarial case, because asking is an input the contract
        # does not permit.
        supported = bool(tool["supports_dry_run"])
        cases.append(
            case(
                id=f"derived:{name}:supports_dry_run",
                kind="positive" if supported else "adversarial",
                field="supports_dry_run",
                expects="permitted" if supported else "refused",
                call={**call, "dry_run": True},
            )
        )
    if not tool.get("requires_approval"):
        cases.append(
            case(
                id=f"derived:{name}:max_affected_rows",
                kind="adversarial",
                field="max_affected_rows",
                expects="refused",
                probe="response",
                call=call,
                upstream={"rows": tool["max_affected_rows"] + 1},
            )
        )
        if "max_response_bytes" in tool:
            cases.append(
                case(
                    id=f"derived:{name}:max_response_bytes",
                    kind="adversarial",
                    field="max_response_bytes",
                    expects="refused",
                    probe="response",
                    call=call,
                    upstream={"rows": 1, "bytes": tool["max_response_bytes"] + 1},
                )
            )
    return cases


def _metadata_cases(name: str, tool: dict[str, Any], contract: dict[str, Any]) -> list[Case]:
    """A metadata capability's cases. Both answer from the lock, so the fields
    a case can exercise are the scope sets and the resource roster."""
    tool_name = tool["name"]
    held = tuple(tool["discovery_scope_sets"][0])
    reads = [
        (read_tool["name"], resource)
        for read_tool in contract["tools"]
        if read_tool["kind"] == "read"
        for resource in read_tool["resources"]
    ]
    cases: list[Case] = []

    def case(**overrides: Any) -> Case:
        base: dict[str, Any] = {
            "capability": name,
            "tool": tool_name,
            "origin": "derived",
            "scopes": held,
            "probe": "request",
        }
        base.update(overrides)
        return Case(**base)

    if tool_name == "list_resources":
        every = tuple(sorted({s for _, r in reads for s in r["required_scopes"]} | set(held)))
        cases.append(
            case(
                id=f"derived:{name}:positive",
                kind="positive",
                field="operation",
                expects="permitted",
                scopes=every,
                call={"tool": tool_name},
            )
        )
        # Held on the metadata scope alone, the listing is FILTERED to what the
        # caller could use -- nothing, here -- rather than refused (D421).
        cases.append(
            case(
                id=f"derived:{name}:required_scopes",
                kind="adversarial",
                field="required_scopes",
                expects="bounded",
                call={"tool": tool_name},
            )
        )
        return cases

    # describe_resource: one positive per read resource, one refusal for a
    # resource the lock does not carry, one for a scope the caller lacks.
    for read_tool, resource in reads:
        cases.append(
            case(
                id=f"derived:{name}:positive:{resource['name']}",
                kind="positive",
                field="operation",
                expects="permitted",
                scopes=tuple(sorted(set(held) | set(resource["required_scopes"]))),
                call={"tool": tool_name, "read_tool": read_tool, "resource": resource["name"]},
            )
        )
    if reads:
        read_tool, resource = reads[0]
        cases.append(
            case(
                id=f"derived:{name}:resources",
                kind="adversarial",
                field="resources",
                expects="refused",
                scopes=tuple(sorted(set(held) | set(resource["required_scopes"]))),
                call={"tool": tool_name, "read_tool": read_tool, "resource": "no_such_resource"},
            )
        )
        cases.append(
            case(
                id=f"derived:{name}:required_scopes",
                kind="adversarial",
                field="required_scopes",
                expects="refused",
                call={"tool": tool_name, "read_tool": read_tool, "resource": resource["name"]},
            )
        )
    return cases


def derive_cases(contract: dict[str, Any]) -> tuple[Case, ...]:
    """Every case the contract implies, in a stable order.

    Pure over the contract. Two projects compiling the same contract derive the
    same cases; a contract that gains a filter gains a case; a contract that
    loses one loses one -- and `test_the_derivation_follows_the_contract` is
    the control that keeps this from quietly becoming a hand-kept list.
    """
    cases: list[Case] = []
    for name, entry in sorted(capabilities_of(contract).items()):
        tool = entry["tool"]
        if tool["kind"] == "read":
            derived = _read_cases(name, tool, entry["resource"])
        elif tool["kind"] == "write":
            derived = _write_cases(name, tool)
        else:
            derived = _metadata_cases(name, tool, contract)
        version = entry["version"]
        cases.extend(
            Case(**{**case.as_dict(), "scopes": case.scopes, "capability_version": version})
            for case in derived
        )
    identifiers = [case.id for case in cases]
    duplicates = sorted({i for i in identifiers if identifiers.count(i) > 1})
    if duplicates:  # pragma: no cover -- a derivation defect, not an input one
        raise HarnessError(f"derived case ids collide: {duplicates}")
    return tuple(cases)


def load_written_cases(
    contract: dict[str, Any], path: Path = WRITTEN_CASES_PATH
) -> tuple[Case, ...]:
    """The hand-written cases, validated against the contract they were written for.

    Every entry must name a capability the contract compiles and must carry the
    `capability_version` it was written against; **a version the contract no
    longer declares is refused**, which is how a capability changed without
    its cases fails the gate. At contract version 1 no capability declares a
    version, and a written case then carries `null` and is accepted as such
    (D600: absent, not defaulted).
    """
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(document, list):
        raise HarnessError(f"{path} must be a list of cases")
    known = capabilities_of(contract)
    cases: list[Case] = []
    seen: set[str] = set()
    for index, entry in enumerate(document):
        where = f"{path.name}[{index}]"
        if not isinstance(entry, dict):
            raise HarnessError(f"{where} is not a mapping")
        required = {
            "id",
            "capability",
            "capability_version",
            "kind",
            "field",
            "expects",
            "scopes",
            "call",
        }
        missing = sorted(required - set(entry))
        if missing:
            raise HarnessError(f"{where} lacks {missing}")
        unknown = sorted(set(entry) - required - {"upstream", "probe", "note"})
        if unknown:
            raise HarnessError(f"{where} carries {unknown}, which a case does not have")
        if entry["id"] in seen:
            raise HarnessError(f"{where}: id {entry['id']!r} is used twice")
        seen.add(entry["id"])
        if entry["capability"] not in known:
            raise HarnessError(
                f"{where} names capability {entry['capability']!r}, which the contract does "
                f"not compile. Known: {sorted(known)}"
            )
        declared = known[entry["capability"]]["version"]
        if entry["capability_version"] != declared:
            raise HarnessError(
                f"{where}: {entry['capability']} is at version {declared!r} and the case was "
                f"written against {entry['capability_version']!r}. A capability that changed "
                "must have its cases re-read and re-approved; update the case or the version"
            )
        if entry["kind"] not in KINDS or entry["expects"] not in EXPECTATIONS:
            raise HarnessError(f"{where}: kind {entry['kind']!r} / expects {entry['expects']!r}")
        if entry.get("probe", "request") not in ("request", "response"):
            raise HarnessError(f"{where}: probe {entry['probe']!r}")
        if not isinstance(entry["call"], dict) or "tool" not in entry["call"]:
            raise HarnessError(f"{where}: call must be a mapping naming a tool")
        tool = known[entry["capability"]]["tool"]["name"]
        if entry["call"]["tool"] != tool:
            raise HarnessError(
                f"{where}: {entry['capability']} is served by {tool!r}, not "
                f"{entry['call']['tool']!r}"
            )
        cases.append(
            Case(
                id=entry["id"],
                capability=entry["capability"],
                tool=tool,
                kind=entry["kind"],
                origin="written",
                field=str(entry["field"]),
                expects=entry["expects"],
                scopes=tuple(entry["scopes"]),
                call=dict(entry["call"]),
                probe=entry.get("probe", "request"),
                upstream=dict(entry.get("upstream") or {}),
                capability_version=entry["capability_version"],
                note=str(entry.get("note") or ""),
            )
        )
    return tuple(cases)


def coverage(
    contract: dict[str, Any], derived: tuple[Case, ...], written: tuple[Case, ...]
) -> dict[str, dict[str, Any]]:
    """Per capability: how many cases of each kind and origin, and the fields
    the derived adversarial cases reach. Refuses a capability with no positive
    or no adversarial case of either origin -- that is the gate's and CI's
    enforcement, and `render_report` calls it before writing a line."""
    report: dict[str, dict[str, Any]] = {}
    for name, entry in sorted(capabilities_of(contract).items()):
        mine = [case for case in (*derived, *written) if case.capability == name]
        counts = {
            f"{origin}_{kind}": sum(1 for c in mine if c.origin == origin and c.kind == kind)
            for origin in ORIGINS
            for kind in KINDS
        }
        fields = sorted(
            {c.field for c in mine if c.origin == "derived" and c.kind == "adversarial"}
        )
        report[name] = {
            "tool": entry["tool"]["name"],
            "kind": entry["tool"]["kind"],
            "version": entry["version"],
            "lifecycle": entry["lifecycle"],
            **counts,
            "fields": fields,
        }
        short = [
            f"{origin} {kind}"
            for origin in ORIGINS
            for kind in KINDS
            if counts[f"{origin}_{kind}"] == 0
        ]
        if short:
            raise HarnessError(
                f"capability {name!r} has no {', no '.join(short)} case. Every enabled "
                "capability needs a positive and an adversarial case of each origin "
                "(EVAL-HARNESS-001); the derived ones follow the contract, the written "
                f"ones live in {WRITTEN_CASES_PATH.name}"
            )
    return report


def render_report(
    contract: dict[str, Any], derived: tuple[Case, ...], written: tuple[Case, ...]
) -> str:
    """The generated block of docs/evaluation-report.md.

    Counts and cases only, never outcomes: an outcome is what the evaluation
    observes on the day, and a document asserting one would be a proof result
    committed as prose. What can be committed is what was ASKED -- and the
    digest of the contract it was asked of, which is the number the deployed
    document publishes and the live half compares.
    """
    table = coverage(contract, derived, written)
    lines = [
        f"Contract `{contract['contract_id']}` at schema version {contract['schema_version']}, "
        f"digest `{contract_digest(contract)}`.",
        "",
        f"**{len(derived)} derived cases and {len(written)} written cases** over "
        f"{len(table)} capabilities. Derived cases are generated from the contract, one "
        "adversarial case per frozen field; written cases are hand-authored and bound to "
        "the capability version they were written against (ADR 0184).",
        "",
        "| Capability | Tool | Version | Derived positive | Derived adversarial | "
        "Written positive | Written adversarial | Fields the derived adversarial cases reach |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for name, row in table.items():
        lines.append(
            f"| `{name}` | `{row['tool']}` | {row['version'] or '—'} | "
            f"{row['derived_positive']} | {row['derived_adversarial']} | "
            f"{row['written_positive']} | {row['written_adversarial']} | "
            + ", ".join(f"`{f}`" for f in row["fields"])
            + " |"
        )
    lines += [
        "",
        "### Every case",
        "",
        "| Case | Capability | Kind | Origin | Field | Probe | Expects |",
        "|---|---|---|---|---|---|---|",
    ]
    for case in (*derived, *written):
        lines.append(
            f"| `{case.id}` | `{case.capability}` | {case.kind} | {case.origin} | "
            f"`{case.field}` | {case.probe} | {case.expects} |"
        )
    return "\n".join(lines)


def cases_document(derived: tuple[Case, ...], written: tuple[Case, ...]) -> str:
    """Every case as one JSON document, for a reader that wants the requests."""
    return json.dumps([case.as_dict() for case in (*derived, *written)], indent=2, sort_keys=True)
