"""Compile a capability manifest into the contract an MCP runtime obeys.

**The one rule this module exists to keep**: it may *read* the OpenAPI document
and may never *infer* a capability from it. Nothing here iterates the document's
paths looking for things to expose. It iterates the **declared** capabilities and
asks two questions about each one — does the reviewed contract name this
operation, and does the served document agree about whether it is published.
That asymmetry is `AGT-DRIFT-001`: adding an API operation must expose nothing,
and the only way to be sure is for the enumeration to start somewhere else.

**Two artefacts, and the difference is the point.**

`compile_canonical` produces the **project-neutral** contract — the tools, their
input shapes, their scopes and their frozen bounds. Two projects serving the same
domain compile the same bytes, so it can be committed and reviewed once. It names
no host, no project key and no URL.

`compile_lock` produces the **deployed** lock, which is the canonical contract
plus the one thing a runtime cannot compile: where to send a request. It is
per-project by construction, and it is what the runtime obeys.

**Nothing here reads a catalog, a database or a network.** Both functions are
pure over their arguments, for the reason `api_surface` gives: a compiler that
could only run where a service exists is a compiler no offline test can check.
The capture is `bin/mcp-contract.py`'s business.
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from agentic_postgres.config import CapabilityContractError

#: The MCP tool names the reviewed manifest compiles to, lexicographically. A
#: constant rather than a derivation, and that is deliberate: `compile_canonical`
#: derives the tool set from the manifest, so a test comparing the two would be
#: comparing a function against itself. This is the reviewed answer, and
#: `test_the_compiled_tools_are_the_six_that_were_planned` is where the two meet.
#: Session 9 Run 3 added the two writes from docs/capability-plan.md; the
#: runtime's own roster (`mcp_lock.EXPECTED_TOOL_NAMES`) catches up in Run 4.
PLANNED_TOOLS = (
    "create_note",
    "describe_resource",
    "list_resources",
    "query_resource",
    "run_report",
    "update_task_status",
)

#: Sources a capability may name, and what each one means for compilation.
#:
#: `lock` is not a service. A capability naming it is answered from the deployed
#: lock itself, holds no credential and reaches no backend, so it has no
#: operation to resolve against the reviewed contract -- there is nothing there
#: to resolve.
BACKED_SOURCES = frozenset({"postgrest"})
UNBACKED_SOURCES = frozenset({"lock"})

CONTRACT_ID = "notes-tasks-agent-v1"

#: **The compiled contract's version is the manifest's, not a constant** (ADR
#: 0177). It was `SCHEMA_VERSION = 1`, and a constant was right while there was
#: one manifest shape. There are two now, and the compiled tool's shape is a
#: function of which one it came from: a v2 manifest produces tools carrying
#: `capabilities`, `risk` and their versions, a v1 manifest produces the tools it
#: always did. A fixed number on a document whose shape varies is a version that
#: describes nothing -- and a v1 manifest still has to render, because
#: `capabilities.yaml` lives only on the host.
COMPILED_SCHEMA_VERSIONS = frozenset({1, 2, 3})

#: Ordered, so a tool backed by several capabilities can take the riskiest.
#: Ascending; `_riskiest` compares by index and nothing else compares risks.
RISK_ORDER = ("low", "moderate", "high")

#: The three fields schema version 2 adds, carried verbatim into every tool.
VERSIONED_FIELDS = ("version", "lifecycle", "risk")

#: The two bounds schema version 3 adds to a read and a write, and the two
#: declarations it adds to a write (ADR 0179). Kept apart from
#: `VERSIONED_FIELDS` because they arrive per KIND rather than for every
#: capability -- a metadata capability declares none of them, and a read
#: declares two of the four.
BUDGET_FIELDS = ("max_response_bytes", "max_concurrent_calls")
WRITE_DECLARATIONS = ("supports_dry_run", "requires_approval")

__all__ = [
    "BACKED_SOURCES",
    "COMPILED_SCHEMA_VERSIONS",
    "CONTRACT_ID",
    "PLANNED_TOOLS",
    "RISK_ORDER",
    "UNBACKED_SOURCES",
    "VERSIONED_FIELDS",
    "CompilerError",
    "canonical_bytes",
    "compile_canonical",
    "compile_lock",
    "derive_operation_id",
    "surface_operations",
]


class CompilerError(CapabilityContractError):
    """A capability cannot be compiled against the reviewed surface.

    A `CapabilityContractError` and not a plain `ManifestError`, because that
    class was written for exactly this: *"the manifest is well formed, it just
    asserts something untrue"*, and the CLI maps it to exit 5 rather than exit 2.
    Until Session 8 its only raiser was the blanket refusal of `enabled: true`;
    the refusal moved to this module and the distinction moved with it.
    """


def derive_operation_id(obj: str, method: str) -> str:
    """The single authority for how an operation is spelled (ADR 0119).

    ``notes`` + ``get`` -> ``notes.get``; ``rpc/create_note`` + ``post`` ->
    ``rpc.create_note.post``.

    Derived rather than copied, because **the live PostgREST publishes no
    ``operationId`` anywhere** — measured on the locked image against a running
    service, Swagger 2.0, every operation without one. The capability plan asks
    for a reference "by ID" and the source provides none, so the id is
    manufactured here, once, by this function.

    ``/`` becomes ``.`` because the schema's pattern permits neither ``/`` nor
    ``:``. That is a constraint rather than a preference, and it is why the
    spelling is not the wire's.
    """
    if not obj or not method:
        raise CompilerError(f"an operation id needs an object and a method, got {obj!r}/{method!r}")
    return f"{obj.replace('/', '.')}.{method.lower()}"


def surface_operations(surface: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every operation the reviewed contract permits, keyed by derived id.

    The reviewed contract is the authority, not the served document (ADR 0050):
    it is hand-written, it can disagree with the catalog, and disagreeing is what
    it is for. The document is an observation and is cross-checked afterwards.

    Each entry carries where it came from, because the three sections mean
    different things downstream: a `relation` and an `rpc` must appear in the
    approved snapshot, and an `agent_rpc` must be absent from it (ADR 0118).
    """
    schema = surface["exposed_schema"]
    operations: dict[str, dict[str, Any]] = {}

    def add(section: str, name: str, obj: str, methods: list[str], arguments: list[str]) -> None:
        for method in methods:
            identifier = derive_operation_id(obj, method)
            if identifier in operations:
                raise CompilerError(
                    f"the reviewed surface yields {identifier!r} twice. Two operations "
                    "sharing a derived id would make a capability ambiguous about which "
                    "one it names"
                )
            operations[identifier] = {
                "section": section,
                "name": name,
                "object": obj,
                "method": method.lower(),
                "path": f"/{obj}",
                "qualified": f"{schema}.{name}",
                "published": section in {"relations", "rpcs"},
                # The reviewed contract records an RPC's arguments in PostgreSQL
                # parameter order, and that list IS a write tool's argument
                # contract (D470). A relation takes none: its inputs are the
                # frozen filters, which are a capability's business, not an
                # operation's.
                "arguments": list(arguments),
            }

    for name, relation in surface["relations"].items():
        add("relations", name, name, relation["methods"], [])
    for name, rpc in surface["rpcs"].items():
        add("rpcs", name, f"rpc/{name}", rpc["methods"], rpc["arguments"])
    for name, rpc in surface["agent_rpcs"].items():
        add("agent_rpcs", name, f"rpc/{name}", rpc["methods"], rpc["arguments"])

    return operations


def _resolve(capability: dict[str, Any], operations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """One capability's operation, or a refusal that names what was wrong."""
    source = capability["operation"]["source"]
    identifier = capability["operation"]["operation_id"]

    if source in UNBACKED_SOURCES:
        return {"source": source, "operation_id": identifier, "backend": None}
    if source not in BACKED_SOURCES:
        raise CompilerError(
            f"capability {capability['name']!r} names source {source!r}, which this release "
            f"cannot compile. Backed sources are {sorted(BACKED_SOURCES)} and unbacked ones "
            f"are {sorted(UNBACKED_SOURCES)}"
        )

    resolved = operations.get(identifier)
    if resolved is None:
        raise CompilerError(
            f"capability {capability['name']!r} names operation {identifier!r}, which the "
            "reviewed surface contract does not permit. The contract is the authority "
            "(ADR 0050); an operation the catalog serves and the contract does not name is "
            f"the case it exists for. Permitted: {sorted(operations)}"
        )
    return {"source": source, "operation_id": identifier, "backend": resolved}


def _check_columns(capability: dict[str, Any], surface: dict[str, Any]) -> None:
    """A frozen column allowlist may only name reviewed columns.

    Checked against `relations` where the backing is a view, and skipped where it
    is an RPC -- the reviewed contract records an RPC's *arguments*, not the
    shape of what it returns, so there is nothing here to compare a report's
    output columns against. Saying so is better than comparing them against
    something that happens to be the right length.
    """
    resource = capability.get("resource")
    if resource is None:
        return
    relation = surface["relations"].get(resource)
    if relation is None:
        return

    reviewed = set(relation["columns"])
    declared = set(capability.get("columns") or [])
    unknown = sorted(declared - reviewed)
    if unknown:
        raise CompilerError(
            f"capability {capability['name']!r} freezes columns {unknown} which the reviewed "
            f"relation {resource!r} does not publish. A column allowlist that names a column "
            "the contract does not is an allowlist nobody reviewed"
        )

    for entry in capability.get("filters") or []:
        if entry["column"] not in reviewed:
            raise CompilerError(
                f"capability {capability['name']!r} permits filtering on {entry['column']!r}, "
                f"which the reviewed relation {resource!r} does not publish"
            )
    for entry in capability.get("order_by") or []:
        if entry["column"] not in reviewed:
            raise CompilerError(
                f"capability {capability['name']!r} permits ordering by {entry['column']!r}, "
                f"which the reviewed relation {resource!r} does not publish"
            )


#: The fields that describe a read's projection, and only a read's. The schema
#: requires `max_affected_rows` and `idempotent` of a write and deliberately
#: does NOT forbid it these -- forbidding them there would be a schema change
#: for a shape nothing had ever carried, D403's version bump that renames
#: nothing. So the refusal lives in the compiler, beside the branch it protects.
_READ_SHAPE_FIELDS = ("resource", "columns", "filters", "order_by", "max_rows")


def _check_write_shape(capability: dict[str, Any]) -> None:
    """A write capability may not carry a read's shape (D470).

    Without this, a `columns` list on a write would validate against the schema
    and compile into nothing -- a field that reads exactly like a real
    projection and reaches nothing, which is D274's shape: a claim that lives
    only in a document nobody dereferences.
    """
    if capability["kind"] != "write":
        return
    carried = [field for field in _READ_SHAPE_FIELDS if field in capability]
    if carried:
        raise CompilerError(
            f"write capability {capability['name']!r} carries {carried}, which describe a "
            "read. A write is one-to-one with its operation and projects nothing; a field "
            "that validates and compiles into nothing is a claim nobody can dereference"
        )


def _check_against_snapshot(
    capability: dict[str, Any], backend: dict[str, Any] | None, published: set[str]
) -> None:
    """The cross-check, in both directions (ADR 0118, ADR 0119).

    **This is the only place OpenAPI is read, and it is read about a capability
    that already exists.** Nothing iterates `published` to discover anything;
    every question here starts from a declared capability. That asymmetry is
    AGT-DRIFT-001.
    """
    if backend is None:
        return
    name, obj = capability["name"], backend["object"]
    if backend["published"] and obj not in published:
        raise CompilerError(
            f"capability {name!r} is backed by {obj!r}, which the reviewed contract publishes "
            "and the approved OpenAPI snapshot does not. Either the migration that creates it "
            "has not shipped, or its grants keep it out of the document"
        )
    if not backend["published"] and obj in published:
        raise CompilerError(
            f"capability {name!r} is backed by the agent-plane operation {obj!r}, which the "
            "approved snapshot PUBLISHES. Either a grant to the documentation role was added "
            "and a capture approved, or the reviewed contract moved a name (ADR 0118)"
        )


def compile_canonical(
    *,
    capabilities: dict[str, Any],
    surface: dict[str, Any],
    published_objects: set[str],
) -> dict[str, Any]:
    """The project-neutral capability contract.

    `published_objects` is `openapi_normalize.declared_objects` over the approved
    snapshot -- passed in rather than read here, so this module keeps the
    property `api_surface` has: it opens no file it was not handed.

    Disabled capabilities are compiled out entirely rather than emitted with a
    flag. A runtime that received them would have to be trusted to ignore them,
    and the lock is meant to be the thing that cannot be argued with.
    """
    manifest_version = capabilities.get("schema_version")
    if manifest_version not in COMPILED_SCHEMA_VERSIONS:
        raise CompilerError(
            f"manifest schema_version {manifest_version!r} is not one this compiler "
            f"produces a contract for; supported: {sorted(COMPILED_SCHEMA_VERSIONS)}"
        )

    # **A retired capability may not be enabled** (ADR 0177). Raised here rather
    # than checked in the runtime, because the paragraph above is the reason: a
    # disabled capability is compiled out entirely, so retirement enforced this
    # way is the lock's ABSENCE rather than a runtime rule somebody could forget
    # to apply. Checked before the `enabled` filter, or a retired-and-disabled
    # entry and a retired-and-enabled one would be indistinguishable by then.
    retired = sorted(
        entry["name"]
        for entry in capabilities["capabilities"]
        if entry.get("lifecycle") == "retired" and entry.get("enabled")
    )
    if retired:
        raise CompilerError(
            f"retired capabilities are enabled: {retired}. A retired capability leaves the "
            "lock; disable it, or move it back to deprecated if it is still callable"
        )

    operations = surface_operations(surface)
    entries = [entry for entry in capabilities["capabilities"] if entry.get("enabled")]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for capability in entries:
        _check_columns(capability, surface)
        _check_write_shape(capability)
        resolved = _resolve(capability, operations)
        _check_against_snapshot(capability, resolved["backend"], published_objects)
        grouped.setdefault(capability.get("tool") or capability["name"], []).append(
            {"capability": capability, "resolved": resolved}
        )

    tools = [_compile_tool(name, backing) for name, backing in sorted(grouped.items())]

    return {
        "schema_version": manifest_version,
        "contract_id": CONTRACT_ID,
        "tool_count": len(tools),
        "capability_count": len(entries),
        "tools": tools,
    }


def _compile_tool(name: str, backing: list[dict[str, Any]]) -> dict[str, Any]:
    """One tool, from the one or more capabilities behind it (ADR 0120)."""
    kinds = {entry["capability"]["kind"] for entry in backing}
    sources = {entry["resolved"]["source"] for entry in backing}
    if len(kinds) != 1 or len(sources) != 1:
        raise CompilerError(
            f"tool {name!r} is backed by capabilities of kinds {sorted(kinds)} and sources "
            f"{sorted(sources)}. One name with two authorization models is two tools wearing "
            "one label"
        )
    kind = kinds.pop()

    if len(backing) > 1 and kind != "read":
        raise CompilerError(
            f"tool {name!r} groups {len(backing)} capabilities of kind {kind!r}. Only a read "
            "selects among frozen resources; a write is one-to-one with its operation"
        )

    # **Discovery is a disjunction of conjunctions, and a flat union will not do.**
    #
    # A tool is discoverable when the caller can use at least one capability
    # behind it, and a capability is usable when the caller holds ALL of its
    # scopes. Those two quantifiers are different and a single list cannot carry
    # both: `query_resource` is `notes:read` OR `tasks:read`, while `run_report`
    # is `notes:read` AND `tasks:read` -- and flattened, both read as the same
    # two strings. An agent holding only `notes:read` would then be shown
    # `run_report` and refused when it called, which is a tool list that lies.
    #
    # So each set is one capability's requirement, and the rule is: hold every
    # scope in any one set. One capability gives one set, which is the ordinary
    # case and is why the shape is not obviously necessary until it is.
    discovery = sorted(
        (sorted(entry["capability"]["required_scopes"]) for entry in backing),
        key=lambda scopes: (len(scopes), scopes),
    )

    compiled: dict[str, Any] = {
        "name": name,
        "kind": kind,
        "source": sources.pop(),
        "discovery_scope_sets": discovery,
        "timeout_ms": max(entry["capability"].get("timeout_ms") or 0 for entry in backing),
        "descriptions": [
            entry["capability"].get("description", "").strip()
            for entry in sorted(backing, key=lambda e: e["capability"]["name"])
        ],
        # **Every tool carries its redaction list** (D479). The union across the
        # backing capabilities, because redaction is conservative: a parameter
        # any one of them redacts is redacted for the tool. Until Session 9
        # every list was `[]` and nothing read any of them, which made the
        # mechanism indistinguishable from one that does not exist -- the lock
        # carrying the list is what gives the runtime something to obey.
        "audit_redact": sorted(
            {
                parameter
                for entry in backing
                for parameter in (entry["capability"].get("audit") or {}).get("redact", [])
            }
        ),
    }
    # **Per capability, and a derived worst case beside it** (ADR 0177).
    #
    # A tool may be backed by several capabilities, so there is no single
    # version or lifecycle for it -- `query_resource` is two authorizations, and
    # they can be at different versions and on different tracks. The list is
    # therefore the authority and the tool-level `risk` is the only aggregate,
    # because risk is the one of the three that has an ordering and a defensible
    # worst case: a tool is as dangerous as the most dangerous thing behind it.
    #
    # Absent entirely at manifest version 1, rather than present and null. A null
    # that looks measured is worse than an absent field (D600), and a runtime
    # reading a v1 lock must be able to tell "this deployment does not declare
    # risk" from "this deployment declares it and the value is nothing".
    declared = [
        entry["capability"] for entry in sorted(backing, key=lambda e: e["capability"]["name"])
    ]
    if all(field in capability for capability in declared for field in VERSIONED_FIELDS):
        compiled["capabilities"] = [
            {
                "name": capability["name"],
                **{f: capability[f] for f in VERSIONED_FIELDS},
                **{
                    f: capability[f]
                    for f in (*BUDGET_FIELDS, *WRITE_DECLARATIONS)
                    if f in capability
                },
            }
            for capability in declared
        ]
        compiled["risk"] = max(
            (capability["risk"] for capability in declared), key=RISK_ORDER.index
        )

    # **The NARROWEST wins** (ADR 0179). A tool may be backed by several
    # capabilities and each declares its own bound, so the tool's effective bound
    # is the smallest -- the opposite aggregation from `risk`, and for the same
    # reason: risk takes the worst case because a tool is as dangerous as the
    # most dangerous thing behind it, and a bound takes the tightest because a
    # tool may do no more than the most restricted thing behind it permits.
    #
    # Emitted only when EVERY backing capability declares them, so a v2 manifest
    # produces the tools it always did and the keys are absent rather than
    # defaulted (D600).
    if all(field in capability for capability in declared for field in BUDGET_FIELDS):
        for field in BUDGET_FIELDS:
            compiled[field] = min(capability[field] for capability in declared)
    if all(field in capability for capability in declared for field in WRITE_DECLARATIONS):
        for field in WRITE_DECLARATIONS:
            # A write is one-to-one with its operation (D486), so there is one
            # capability here and `any` is an identity. Written as a fold rather
            # than as `declared[0][field]` so that grouping a write later -- which
            # the compiler refuses today -- would not silently take the first.
            compiled[field] = any(capability[field] for capability in declared)

    if kind == "metadata":
        compiled["reads"] = "lock"
        compiled["operation_ids"] = sorted(entry["resolved"]["operation_id"] for entry in backing)
    elif kind == "write":
        compiled.update(_compile_write(name, backing[0]))
    else:
        compiled["resources"] = [_compile_resource(entry) for entry in backing]
        compiled["max_rows"] = max(resource["max_rows"] for resource in compiled["resources"])
    return compiled


def _compile_resource(entry: dict[str, Any]) -> dict[str, Any]:
    """One frozen resource behind a read tool, exactly as before Session 9."""
    capability = entry["capability"]
    return {
        "name": capability["resource"],
        "capability": capability["name"],
        "required_scopes": sorted(capability["required_scopes"]),
        "columns": list(capability["columns"]),
        "filters": [
            {"column": f["column"], "operators": sorted(f["operators"])}
            for f in sorted(capability.get("filters") or [], key=lambda f: f["column"])
        ],
        "order_by": [
            {"column": o["column"], "direction": o["direction"]}
            for o in capability.get("order_by") or []
        ],
        "max_rows": capability["max_rows"],
        "operation": {
            "operation_id": entry["resolved"]["operation_id"],
            "method": entry["resolved"]["backend"]["method"],
            "path": entry["resolved"]["backend"]["path"],
        },
    }


def _compile_write(name: str, entry: dict[str, Any]) -> dict[str, Any]:
    """A write tool's half of the contract: an operation, an argument contract,
    and a side-effect bound -- and no `columns`, `filters`, `order_by` or
    `max_rows`, because a write projects nothing (D470).

    `arguments` is the reviewed contract's list, in PostgreSQL parameter order.
    A caller supplies values for exactly these names and may never supply a
    name of its own -- the same rule `mcp_query` keeps for filter columns
    (ADR 0127), applied to the other verb.

    `max_affected_rows` is carried for the runtime to check **against the
    response**, never to trust (D487): both current writes bound it at 1
    because that is the function's own shape -- `RETURNS api.notes` /
    `RETURNS api.tasks`, a single composite row, not `SETOF`.
    """
    capability, resolved = entry["capability"], entry["resolved"]
    backend = resolved["backend"]
    if backend is None:
        raise CompilerError(
            f"write tool {name!r} names the unbacked source {resolved['source']!r}. A write "
            "changes rows, so it must reach a backend; an unbacked write is a side effect "
            "nobody can locate"
        )
    if backend["method"] != "post":
        raise CompilerError(
            f"write tool {name!r} is backed by {resolved['operation_id']!r}, whose method is "
            f"{backend['method'].upper()}. A write is a POST to a reviewed RPC; backing one "
            "with a read operation is a tool whose kind lies about its effect"
        )
    return {
        "required_scopes": sorted(capability["required_scopes"]),
        "operation": {
            "operation_id": resolved["operation_id"],
            "method": backend["method"],
            "path": backend["path"],
        },
        "arguments": list(backend["arguments"]),
        "max_affected_rows": capability["max_affected_rows"],
        "idempotent": capability["idempotent"],
    }


def compile_lock(
    *,
    canonical: dict[str, Any],
    project_key: str,
    upstream: str,
    sources: dict[str, str],
) -> dict[str, Any]:
    """The deployed lock: the canonical contract plus where to send a request.

    `upstream` is the ONE address the runtime may call -- Run 6's fixed upstream.
    It is carried here rather than derived by the runtime for ADR 0002's reason:
    the document is the one thing every plane reads, and a service resolving its
    own upstream would be a second authority for an address `naming` owns.

    `sources` are the digests of everything this lock was compiled from. A lock
    whose inputs cannot be identified is a capability surface nobody can prove
    was reviewed, which is the failure `capabilities.yaml` exists to prevent.
    """
    for required in ("capabilities_sha256", "api_surface_sha256", "canonical_openapi_sha256"):
        if required not in sources:
            raise CompilerError(f"the lock needs {required} and was not given one")

    return {
        "schema_version": canonical["schema_version"],
        "contract_id": canonical["contract_id"],
        "project_key": project_key,
        "upstream": upstream,
        "canonical_sha256": sha256(canonical_bytes(canonical)).hexdigest(),
        "compiled_from": dict(sorted(sources.items())),
        "tool_count": canonical["tool_count"],
        "capability_count": canonical["capability_count"],
        "tools": canonical["tools"],
    }


def canonical_bytes(document: dict[str, Any]) -> bytes:
    """The committed form: one document, one byte string, always.

    `openapi_normalize.canonical_bytes`'s shape, and for its reason: a digest
    over a re-serialized document is only stable if the serialization is.
    """
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    )
