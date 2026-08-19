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

#: The MCP tool names this release registers, lexicographically. A constant
#: rather than a derivation, and that is deliberate: `compile_canonical` derives
#: the tool set from the manifest, so a test comparing the two would be comparing
#: a function against itself. This is the reviewed answer, and
#: `test_the_compiled_tools_are_the_four_that_were_planned` is where the two meet.
PLANNED_TOOLS = ("describe_resource", "list_resources", "query_resource", "run_report")

#: Sources a capability may name, and what each one means for compilation.
#:
#: `lock` is not a service. A capability naming it is answered from the deployed
#: lock itself, holds no credential and reaches no backend, so it has no
#: operation to resolve against the reviewed contract -- there is nothing there
#: to resolve.
BACKED_SOURCES = frozenset({"postgrest"})
UNBACKED_SOURCES = frozenset({"lock"})

CONTRACT_ID = "notes-tasks-agent-v1"
SCHEMA_VERSION = 1

__all__ = [
    "BACKED_SOURCES",
    "CONTRACT_ID",
    "PLANNED_TOOLS",
    "SCHEMA_VERSION",
    "UNBACKED_SOURCES",
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

    def add(section: str, name: str, obj: str, methods: list[str]) -> None:
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
            }

    for name, relation in surface["relations"].items():
        add("relations", name, name, relation["methods"])
    for name, rpc in surface["rpcs"].items():
        add("rpcs", name, f"rpc/{name}", rpc["methods"])
    for name, rpc in surface["agent_rpcs"].items():
        add("agent_rpcs", name, f"rpc/{name}", rpc["methods"])

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
    operations = surface_operations(surface)
    entries = [entry for entry in capabilities["capabilities"] if entry.get("enabled")]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for capability in entries:
        _check_columns(capability, surface)
        resolved = _resolve(capability, operations)
        _check_against_snapshot(capability, resolved["backend"], published_objects)
        grouped.setdefault(capability.get("tool") or capability["name"], []).append(
            {"capability": capability, "resolved": resolved}
        )

    tools = [_compile_tool(name, backing) for name, backing in sorted(grouped.items())]

    return {
        "schema_version": SCHEMA_VERSION,
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

    resources = [
        {
            "name": entry["capability"]["resource"],
            "capability": entry["capability"]["name"],
            "required_scopes": sorted(entry["capability"]["required_scopes"]),
            "columns": list(entry["capability"]["columns"]),
            "filters": [
                {"column": f["column"], "operators": sorted(f["operators"])}
                for f in sorted(entry["capability"].get("filters") or [], key=lambda f: f["column"])
            ],
            "order_by": [
                {"column": o["column"], "direction": o["direction"]}
                for o in entry["capability"].get("order_by") or []
            ],
            "max_rows": entry["capability"]["max_rows"],
            "operation": {
                "operation_id": entry["resolved"]["operation_id"],
                "method": entry["resolved"]["backend"]["method"],
                "path": entry["resolved"]["backend"]["path"],
            },
        }
        for entry in sorted(backing, key=lambda e: e["capability"]["name"])
        if kind != "metadata"
    ]

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
    }
    if kind == "metadata":
        compiled["reads"] = "lock"
        compiled["operation_ids"] = sorted(entry["resolved"]["operation_id"] for entry in backing)
    else:
        compiled["resources"] = resources
        compiled["max_rows"] = max(resource["max_rows"] for resource in resources)
    return compiled


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
        "schema_version": SCHEMA_VERSION,
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
