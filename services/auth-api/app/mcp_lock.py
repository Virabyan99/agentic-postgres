"""The deployed capability lock, as the runtime reads it.

The lock is what `bin/mcp-contract.sh lock` compiles for one project: the
approved capability contract, plus the identity of the API surface it was
compiled against and the digests of everything that went into it. It is read
**once, at startup**, for the reason the key set is (ADR 0113): a file re-read
per request is a runtime input, and the deployment needs to know exactly what
each container is serving from at each moment.

**`upstream` is not a dial string** (ADR 0126). It carries the project's public
`routes.rest` — `https://<domain>/api/rest` — which names *which API surface
this contract describes*. The address the runtime actually calls is the internal
one Run 5 established, and a test asserts no request is ever built from
`upstream`, because both are correct-looking URLs and only one of them resolves
from the internal network.

Everything the tools serve comes from here. `list_resources` and
`describe_resource` reach no database and no OpenAPI document (ADR 0127): the
lock is the answer, so discovery describes what a human approved rather than
what a service happens to be exposing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The lock format this runtime understands. A lock declaring anything else is
#: refused at startup rather than read optimistically -- a capability surface
#: from a schema this code does not know is a surface nobody reviewed against
#: this code.
SUPPORTED_SCHEMA_VERSION = 1

#: The two tools that answer from the lock, and the two that reach PostgREST.
#: Named rather than inferred from `kind`, so that a lock which changed a tool's
#: kind cannot silently move it between the two paths.
METADATA_TOOLS = ("describe_resource", "list_resources")
READ_TOOLS = ("query_resource", "run_report")

#: Exactly four, and the names in lexicographic order (ADR 0127). Asserted at
#: load, so a lock with a fifth tool never reaches registration.
EXPECTED_TOOL_NAMES = tuple(sorted((*METADATA_TOOLS, *READ_TOOLS)))


class LockError(Exception):
    """The lock cannot be trusted, so the runtime does not start.

    A refusal at startup rather than per request, for D381's reason inverted: a
    container that starts holding a lock it could not parse would serve an agent
    surface nobody can describe, and it would look deployed.
    """


@dataclass(frozen=True, slots=True)
class Operation:
    """One upstream operation, named by the lock and never by a caller."""

    method: str
    path: str
    operation_id: str


@dataclass(frozen=True, slots=True)
class Resource:
    """One queryable resource, with every bound the lock froze for it.

    `columns`, `filters` and `order_by` are the whole of what a caller may ask
    for. They are tuples rather than lists because nothing may add to them at
    runtime -- the frozen surface is the point, and a mutable default is how a
    frozen surface stops being one.
    """

    name: str
    capability: str
    columns: tuple[str, ...]
    filters: dict[str, tuple[str, ...]]
    order_by: tuple[tuple[str, str], ...]
    max_rows: int
    required_scopes: tuple[str, ...]
    operation: Operation


@dataclass(frozen=True, slots=True)
class Tool:
    """One registered tool and the resources behind it (ADR 0120)."""

    name: str
    kind: str
    source: str
    timeout_ms: int
    discovery_scope_sets: tuple[tuple[str, ...], ...]
    descriptions: tuple[str, ...]
    resources: tuple[Resource, ...]

    def discoverable_by(self, scopes: frozenset[str]) -> bool:
        """Whether a caller holding `scopes` may see this tool at all.

        A **disjunction of conjunctions** (ADR 0120, D421): the caller must hold
        every scope in at least one set. A flat list could not tell `notes:read`
        OR `tasks:read` from `notes:read` AND `tasks:read`, and would advertise
        `run_report` to an agent holding half of what it needs -- a tool list
        that advertises what it will refuse.
        """
        return any(set(required) <= scopes for required in self.discovery_scope_sets)


@dataclass(frozen=True, slots=True)
class CapabilityLock:
    """The deployed lock: what this project's agent plane serves."""

    contract_id: str
    project_key: str
    #: The PUBLIC identity of the compiled-against surface. **Never dialled.**
    upstream: str
    canonical_sha256: str
    tool_count: int
    capability_count: int
    tools: tuple[Tool, ...]

    def tool(self, name: str) -> Tool:
        for candidate in self.tools:
            if candidate.name == name:
                return candidate
        raise LockError(f"no tool named {name!r} in this lock")

    def resource(self, tool_name: str, resource_name: str) -> Resource:
        """One resource of one tool, by name. The only way an operation is chosen.

        Both names are compared against the lock, so a caller cannot reach an
        operation by supplying a path, a method or an id (ADR 0127).
        """
        for resource in self.tool(tool_name).resources:
            if resource.name == resource_name:
                return resource
        raise LockError(f"{tool_name} has no resource named {resource_name!r}")


def _require(document: Any, key: str, kind: type, where: str) -> Any:
    if not isinstance(document, dict) or key not in document:
        raise LockError(f"{where} is missing {key!r}")
    value = document[key]
    if not isinstance(value, kind) or (isinstance(value, bool) and kind is int):
        raise LockError(f"{where}.{key} is not {kind.__name__}")
    return value


def _strings(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise LockError(f"{where} is not an array of strings")
    return tuple(value)


def load_lock(path: Path | str) -> CapabilityLock:
    """Read and validate the deployed lock, or refuse to start.

    Strict, and every check is a security boundary rather than a formality: this
    document decides which columns a caller may name, which operators may be
    applied to them, how many rows come back, and which upstream operation is
    reached. A lock parsed leniently is a surface nobody bounded.
    """
    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise LockError(f"the capability lock cannot be read: {error}") from error

    try:
        document = json.loads(raw)
    except ValueError as error:
        raise LockError(f"the capability lock is not JSON: {error}") from error

    version = _require(document, "schema_version", int, "the lock")
    if version != SUPPORTED_SCHEMA_VERSION:
        raise LockError(
            f"the lock declares schema_version {version}; this runtime serves "
            f"{SUPPORTED_SCHEMA_VERSION} and will not guess at the difference"
        )

    tools = tuple(_tool(entry) for entry in _require(document, "tools", list, "the lock"))
    names = tuple(sorted(tool.name for tool in tools))
    if names != EXPECTED_TOOL_NAMES:
        raise LockError(f"the lock serves {list(names)}, not {list(EXPECTED_TOOL_NAMES)}")

    declared = _require(document, "tool_count", int, "the lock")
    if declared != len(tools):
        raise LockError(f"the lock says {declared} tools and carries {len(tools)}")

    return CapabilityLock(
        contract_id=_require(document, "contract_id", str, "the lock"),
        project_key=_require(document, "project_key", str, "the lock"),
        upstream=_require(document, "upstream", str, "the lock"),
        canonical_sha256=_require(document, "canonical_sha256", str, "the lock"),
        tool_count=declared,
        capability_count=_require(document, "capability_count", int, "the lock"),
        tools=tuple(sorted(tools, key=lambda tool: tool.name)),
    )


def _tool(entry: Any) -> Tool:
    name = _require(entry, "name", str, "a tool")
    kind = _require(entry, "kind", str, f"tool {name}")
    source = _require(entry, "source", str, f"tool {name}")

    scope_sets = entry.get("discovery_scope_sets")
    if not isinstance(scope_sets, list) or not scope_sets:
        raise LockError(f"tool {name} declares no discovery_scope_sets")
    discovery = tuple(_strings(item, f"tool {name} scope set") for item in scope_sets)

    resources = tuple(_resource(item, name) for item in entry.get("resources", []) if True)
    if name in READ_TOOLS and not resources:
        raise LockError(f"tool {name} reads a backend and names no resource")
    if name in METADATA_TOOLS and resources:
        raise LockError(f"tool {name} answers from the lock and must name no resource")

    return Tool(
        name=name,
        kind=kind,
        source=source,
        timeout_ms=_require(entry, "timeout_ms", int, f"tool {name}"),
        discovery_scope_sets=discovery,
        descriptions=_strings(entry.get("descriptions", []), f"tool {name} descriptions"),
        resources=resources,
    )


def _resource(entry: Any, tool_name: str) -> Resource:
    name = _require(entry, "name", str, f"a resource of {tool_name}")
    where = f"{tool_name}.{name}"

    filters: dict[str, tuple[str, ...]] = {}
    for item in _require(entry, "filters", list, where):
        column = _require(item, "column", str, f"{where} filter")
        filters[column] = _strings(item.get("operators"), f"{where} filter {column}")

    order_by: list[tuple[str, str]] = []
    for item in _require(entry, "order_by", list, where):
        order_by.append(
            (
                _require(item, "column", str, f"{where} order_by"),
                _require(item, "direction", str, f"{where} order_by"),
            )
        )

    operation = _require(entry, "operation", dict, where)
    max_rows = _require(entry, "max_rows", int, where)
    if max_rows < 1:
        raise LockError(f"{where}.max_rows is {max_rows}; a page of no rows is not a page")

    return Resource(
        name=name,
        capability=_require(entry, "capability", str, where),
        columns=_strings(entry.get("columns"), f"{where}.columns"),
        filters=filters,
        order_by=tuple(order_by),
        max_rows=max_rows,
        required_scopes=_strings(entry.get("required_scopes"), f"{where}.required_scopes"),
        operation=Operation(
            method=_require(operation, "method", str, f"{where}.operation").lower(),
            path=_require(operation, "path", str, f"{where}.operation"),
            operation_id=_require(operation, "operation_id", str, f"{where}.operation"),
        ),
    )
