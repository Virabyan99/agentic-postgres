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

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The lock formats this runtime understands. A lock declaring anything else is
#: refused at startup rather than read optimistically -- a capability surface
#: from a schema this code does not know is a surface nobody reviewed against
#: this code.
#:
#: **2 was added before any v2 lock could reach a host** (ADR 0177), and that
#: ordering is the most breakable thing in Session 16 Run 2. The check is `!=`,
#: it runs at startup, and it fails the start. A release compiling a v2 lock
#: while this still said 1 would deploy a project whose MCP service refuses to
#: come up -- and `DEFERRED_SERVICES` starts it at step 6b, so the failure lands
#: in the middle of a convergence rather than at its edge.
SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2, 3, 4})

#: The lock version at which the compiler writes the deployment's scope
#: VOCABULARY into the lock (ADR 0200): the data class the reviewed surface
#: derives, and the two enumerated classes. Required at and above, forbidden
#: below (ADR 0177). The agent plane does not consult it -- its scope check
#: holds the caller's scopes against each tool's own `required_scopes` -- but
#: it parses it, so a lock the ISSUER would refuse is refused here first, at
#: the same startup, rather than by a second container minutes later.
VOCABULARY_FROM = 4

#: The lock version at which a tool carries `risk` and its backing
#: `capabilities`. Below it those keys must be ABSENT and above it required --
#: parsed as strictly as everything else here, because a lock parsed leniently
#: is a surface nobody bounded, and because a tool that is silently missing its
#: risk is indistinguishable from one classified as harmless.
VERSIONED_CAPABILITIES_FROM = 2

#: The lock version at which a tool carries its own budget bounds (ADR
#: 0179). Below it those keys must be ABSENT and at or above it a read or a
#: write carries both -- a metadata tool carries neither at any version,
#: because it bounds neither: `_within_byte_budget` never sees its result
#: and it takes no concurrency slot.
BUDGETS_FROM = 3

#: The two tools that answer from the lock itself. **The one roster this module
#: keeps** (ADR 0200): these two are the runtime's own -- `list_resources` and
#: `describe_resource` are implemented here, not compiled -- so every lock must
#: carry exactly this pair, and a metadata tool by any other name is a tool the
#: runtime cannot answer.
METADATA_TOOLS = ("describe_resource", "list_resources")

#: The three kinds a tool may be, and the two SHAPES a read may take. Since ADR
#: 0200 the runtime registers from the lock by kind and shape, never by name:
#: a `relation` read selects among frozen resources with the query shape, an
#: `rpc` read is one argument-free operation with no caller input, and a write
#: carries its own argument list. "Enumerated, not discovered" (ADR 0127) is
#: kept as "compiled, not edited": at lock schema version 4 the compiler signs
#: the tool list with `tools_sha256`, recomputed at load.
KINDS = ("metadata", "read", "write")
READ_SHAPES = ("relation", "rpc")

#: The lock version at which a read tool declares its `reads` shape and the
#: list carries the compiler's digest (ADR 0200). Required at and above,
#: forbidden below (ADR 0177).
TOOLS_DIGEST_FROM = 4


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
class CapabilityRef:
    """One authorization behind a tool, with what it declares about itself.

    A tool may be backed by several (ADR 0120), and they move independently, so
    there is no single version or lifecycle for a tool -- `query_resource` is
    `query_notes` and `query_tasks`, and either can be deprecated while the
    other is not. This is why the lock carries a list rather than three fields
    on the tool.
    """

    name: str
    version: str
    lifecycle: str
    risk: str


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
class WriteSpec:
    """The write half of a tool: one operation, an argument contract, a bound.

    `arguments` is the reviewed contract's list in PostgreSQL parameter order —
    the names a caller supplies values for, and the only names it may supply
    (D470). `max_affected_rows` is carried for the executor to check **against
    the response**, never to trust (D487).
    """

    operation: Operation
    arguments: tuple[str, ...]
    required_scopes: tuple[str, ...]
    max_affected_rows: int
    idempotent: bool


@dataclass(frozen=True, slots=True)
class Tool:
    """One registered tool and the resources or write behind it (ADR 0120).

    `audit_redact` is the lock's per-tool redaction list (D479): the parameter
    names replaced before an audit record's parameter document is written. Run
    6 is its consumer; it is parsed here because the lock is parsed here.
    """

    name: str
    kind: str
    source: str
    timeout_ms: int
    discovery_scope_sets: tuple[tuple[str, ...], ...]
    descriptions: tuple[str, ...]
    resources: tuple[Resource, ...]
    write: WriteSpec | None = None
    audit_redact: tuple[str, ...] = ()
    #: `None` at lock schema version 1, where the fields do not exist. Not a
    #: default of "low" and not an empty tuple: a deployment that does not
    #: classify its capabilities must be distinguishable from one that
    #: classified them as harmless (D600), and Run 3 writes this into the audit
    #: row where the difference becomes a record rather than a variable.
    risk: str | None = None
    capabilities: tuple[CapabilityRef, ...] = ()
    #: `None` below lock schema version 3, and on a metadata tool at every
    #: version -- it bounds neither (ADR 0179). The runtime takes
    #: `min(this, the global)`, so a lock that widened would be narrowed back
    #: here: the schema refuses a wider MANIFEST and this refuses a wider LOCK,
    #: which is a different input and one this module is required to distrust.
    max_response_bytes: int | None = None
    max_concurrent_calls: int | None = None
    #: Declared at v3 and behaving in Run 7 (D892). Parsed now so the field has
    #: a reader the moment it exists, rather than sitting in the lock unread.
    supports_dry_run: bool | None = None
    requires_approval: bool | None = None

    @property
    def read_shape(self) -> str | None:
        """`relation` or `rpc` for a read, from what its resources reach.

        Derived from the operations rather than trusted from a field, so a lock
        below version 4 -- which carries no `reads` -- registers by the same
        rule as one that does, and a lock at 4 whose declared word disagrees is
        refused at load (ADR 0200).
        """
        if self.kind != "read":
            return None
        methods = {resource.operation.method for resource in self.resources}
        return "relation" if methods == {"get"} else "rpc"

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
    #: The project's narrowing the lock was compiled under (ADR 0183), as the
    #: compiler recorded it: tool name to the fields and values it narrowed.
    #: `None` when the project manifest predates profiles (version 1), which is
    #: distinguishable from an empty profile on a version 2 manifest (D600).
    #: Verified against the tools at load and never consulted afterwards -- the
    #: tools are what the runtime obeys, and this is the record of why they
    #: differ from the reviewed contract.
    profile: dict[str, dict[str, Any]] | None = None
    #: The deployment's scope classes (ADR 0200), present at lock schema
    #: version 4 and above and `None` below, where the field does not exist.
    vocabulary: dict[str, tuple[str, ...]] | None = None

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
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise LockError(
            f"the lock declares schema_version {version}; this runtime serves "
            f"{sorted(SUPPORTED_SCHEMA_VERSIONS)} and will not guess at the difference"
        )

    raw_tools = _require(document, "tools", list, "the lock")
    tools = tuple(_tool(entry, version) for entry in raw_tools)
    names = [tool.name for tool in tools]
    if len(set(names)) != len(names):
        raise LockError(f"the lock names a tool twice: {sorted(names)}")

    # **The one roster kept** (ADR 0200): the metadata pair is the runtime's
    # own and must be present -- a lock without `list_resources` is a surface
    # no caller can discover -- and nothing else is required by name. What a
    # lock may serve beyond the pair is decided by the compiler's digest below
    # and by each tool's shape in `_tool`, never by a list written here.
    metadata = {tool.name for tool in tools if tool.kind == "metadata"}
    if metadata != set(METADATA_TOOLS):
        raise LockError(
            f"the lock carries the metadata tools {sorted(metadata)}; the runtime answers "
            f"exactly {list(METADATA_TOOLS)} itself, and a lock must carry both"
        )

    declared = _require(document, "tool_count", int, "the lock")
    if declared != len(tools):
        raise LockError(f"the lock says {declared} tools and carries {len(tools)}")

    # **Compiled, not edited.** At version 4 the compiler signs the tool list
    # it wrote, after the profile; a tool added, removed or edited by hand is a
    # digest the compiler did not write. Below 4 there is no signature, which
    # is the state ADR 0127's fixed roster covered, and the field is forbidden
    # there so the version number is not decorative (ADR 0177).
    if version >= TOOLS_DIGEST_FROM:
        digest = _require(document, "tools_sha256", str, "the lock")
        actual = hashlib.sha256(canonical_bytes(raw_tools)).hexdigest()
        if digest != actual:
            raise LockError(
                "the lock's tools_sha256 does not match its tool list; this list was not "
                "written by the compiler that signed it (ADR 0200)"
            )
    elif "tools_sha256" in document:
        raise LockError(
            f"the lock carries tools_sha256 at schema_version {version}; the signature "
            f"arrives at {TOOLS_DIGEST_FROM} (ADR 0177)"
        )

    ordered = tuple(sorted(tools, key=lambda tool: tool.name))
    return CapabilityLock(
        contract_id=_require(document, "contract_id", str, "the lock"),
        project_key=_require(document, "project_key", str, "the lock"),
        upstream=_require(document, "upstream", str, "the lock"),
        canonical_sha256=_require(document, "canonical_sha256", str, "the lock"),
        tool_count=declared,
        capability_count=_require(document, "capability_count", int, "the lock"),
        tools=ordered,
        profile=_profile(document, ordered),
        vocabulary=_vocabulary(document, version),
    )


def _vocabulary(document: dict[str, Any], version: int) -> dict[str, tuple[str, ...]] | None:
    """The three classes at lock version 4 and above; absent below (ADR 0177).

    The same shape `scopes.load_vocabulary` requires of the issuer's copy --
    three sorted, deduplicated string lists under the three class names -- so
    a lock either container would refuse is refused by both.
    """
    if version < VOCABULARY_FROM:
        if "vocabulary" in document:
            raise LockError(
                f"the lock carries a vocabulary at schema_version {version}; the block "
                f"arrives at {VOCABULARY_FROM} (ADR 0177)"
            )
        return None
    block = _require(document, "vocabulary", dict, "the lock")
    expected = ("administrative", "data", "storage")
    if tuple(sorted(block)) != expected:
        raise LockError(f"the lock's vocabulary names {sorted(block)}, not {list(expected)}")
    classes: dict[str, tuple[str, ...]] = {}
    for name in expected:
        members = _strings(block[name], f"the lock's vocabulary.{name}")
        if list(members) != sorted(set(members)):
            raise LockError(f"the lock's vocabulary.{name} is not sorted and deduplicated")
        classes[name] = members
    return classes


#: The seven fields a profile may narrow, and where each lives on a parsed tool
#: (ADR 0183). `max_rows` is on every resource of a read rather than on the
#: tool, so it is read from each. A second copy of the compiler's
#: `PROFILE_FIELDS` roster, deliberately: the runtime imports nothing from
#: `agentic_postgres`, and a contract test keeps the two rosters equal (D486's
#: arrangement, the one `RESERVED_WRITE_PARAMETERS` already uses).
PROFILE_FIELDS = (
    "timeout_ms",
    "max_response_bytes",
    "max_concurrent_calls",
    "max_rows",
    "max_affected_rows",
    "supports_dry_run",
    "requires_approval",
)


def _profile(document: Any, tools: tuple[Tool, ...]) -> dict[str, dict[str, Any]] | None:
    """The lock's own account of how it was narrowed, checked against its tools.

    **This is the reader** (D816): a field declared with no reader is an
    unverified field, and a lock that says it was narrowed and was not came
    from something other than this repository's compiler. The compiler sets
    every profiled field EQUAL to the profile's value -- a profile may only
    narrow, and the narrowed value is the profile's -- so the check is equality,
    per tool and per field, with `max_rows` read from every resource.

    Absent is a version 1 project manifest and is accepted. Present is parsed
    as strictly as everything else here, in both directions: an entry naming a
    tool the lock does not serve, a field the roster does not know, or a value
    the tool does not carry is a lock disagreeing with itself.
    """
    if "profile" not in document:
        return None
    declared = document["profile"]
    if not isinstance(declared, dict):
        raise LockError("the lock.profile is not an object")
    by_name = {tool.name: tool for tool in tools}

    profile: dict[str, dict[str, Any]] = {}
    for tool_name, entries in declared.items():
        tool = by_name.get(tool_name)
        if tool is None:
            raise LockError(
                f"the lock.profile narrows {tool_name!r}, which the lock does not serve"
            )
        if not isinstance(entries, dict) or not entries:
            raise LockError(f"the lock.profile entry for {tool_name} narrows nothing")
        for field, value in entries.items():
            if field not in PROFILE_FIELDS:
                raise LockError(
                    f"the lock.profile narrows {tool_name}.{field}, which is not a bound this "
                    f"runtime reads; it knows {list(PROFILE_FIELDS)}"
                )
            carried = (
                sorted({resource.max_rows for resource in tool.resources})
                if field == "max_rows"
                else [getattr(tool, field) if field != "max_affected_rows" else _affected(tool)]
            )
            if carried != [value]:
                raise LockError(
                    f"the lock.profile says {tool_name}.{field} was narrowed to {value!r} and "
                    f"the tool carries {carried}. A lock disagreeing with its own profile was "
                    "not compiled by this repository's compiler"
                )
        profile[tool_name] = dict(entries)
    return profile


def _affected(tool: Tool) -> int | None:
    return tool.write.max_affected_rows if tool.write is not None else None


def _tool(entry: Any, version: int) -> Tool:
    name = _require(entry, "name", str, "a tool")
    kind = _require(entry, "kind", str, f"tool {name}")
    source = _require(entry, "source", str, f"tool {name}")

    scope_sets = entry.get("discovery_scope_sets")
    if not isinstance(scope_sets, list) or not scope_sets:
        raise LockError(f"tool {name} declares no discovery_scope_sets")
    discovery = tuple(_strings(item, f"tool {name} scope set") for item in scope_sets)

    # **By kind and shape, never by name** (ADR 0200). The one name-bound rule
    # is the metadata pair, which the runtime implements itself: a metadata
    # tool must be one of the two, and one of the two must be metadata -- a
    # reviewed name with a different kind is a different tool wearing it.
    if kind not in KINDS:
        raise LockError(f"tool {name} declares kind {kind!r}; the kinds are {list(KINDS)}")
    if (name in METADATA_TOOLS) != (kind == "metadata"):
        raise LockError(
            f"tool {name} declares kind {kind!r}; the metadata tools are exactly "
            f"{list(METADATA_TOOLS)} and they are the only metadata tools the runtime answers"
        )

    resources = tuple(_resource(item, name) for item in entry.get("resources", []) if True)
    if kind == "read" and not resources:
        raise LockError(f"tool {name} reads a backend and names no resource")
    if kind == "metadata" and resources:
        raise LockError(f"tool {name} answers from the lock and must name no resource")
    # The third arm (D486): a write is one-to-one with its operation, so it
    # selects among no resources and must carry the write shape instead.
    if kind == "write" and resources:
        raise LockError(f"tool {name} writes one operation and must name no resource")
    write = _write(entry, name) if kind == "write" else None
    if kind != "write" and any(key in entry for key in ("arguments", "max_affected_rows")):
        raise LockError(f"tool {name} is a {kind} and carries a write's shape")
    _read_shape(entry, name, kind, resources, version)
    risk, capabilities = _classification(entry, name, version)
    budgets = _budgets(entry, name, kind, version)

    return Tool(
        name=name,
        kind=kind,
        source=source,
        timeout_ms=_require(entry, "timeout_ms", int, f"tool {name}"),
        discovery_scope_sets=discovery,
        descriptions=_strings(entry.get("descriptions", []), f"tool {name} descriptions"),
        resources=resources,
        write=write,
        audit_redact=_strings(entry.get("audit_redact", []), f"tool {name} audit_redact"),
        risk=risk,
        capabilities=capabilities,
        **budgets,
    )


def _read_shape(
    entry: Any, tool_name: str, kind: str, resources: tuple[Resource, ...], version: int
) -> None:
    """A read is a `relation` read or an `rpc` read, and never both (ADR 0200).

    The shape is what the runtime registers by: a relation read takes the
    query shape, an rpc read takes no caller input at all. Derived from the
    resources' operations; at lock version 4 the compiler also DECLARES it, and
    the two must agree -- and below 4 the field is forbidden (ADR 0177).
    """
    if kind == "read":
        methods = {resource.operation.method for resource in resources}
        if methods not in ({"get"}, {"post"}):
            raise LockError(
                f"tool {tool_name} reads through {sorted(methods)}; a read selects among "
                "relations (GET) or runs one RPC (POST), never both"
            )
    if version < TOOLS_DIGEST_FROM:
        if kind == "read" and "reads" in entry:
            raise LockError(
                f"tool {tool_name} declares reads at lock schema_version {version}; the "
                f"field arrives at {TOOLS_DIGEST_FROM} (ADR 0177)"
            )
        return
    if kind != "read":
        return
    declared = _require(entry, "reads", str, f"tool {tool_name}")
    derived = "relation" if methods == {"get"} else "rpc"
    if declared not in READ_SHAPES or declared != derived:
        raise LockError(
            f"tool {tool_name} declares reads {declared!r} and its resources reach "
            f"{sorted(methods)}, which is {derived!r}"
        )


def canonical_bytes(document: Any) -> bytes:
    """The compiler's serialization, reproduced with the standard library.

    `capability_compiler.canonical_bytes`'s shape exactly -- two-space indent,
    sorted keys, UTF-8, a trailing newline -- because `tools_sha256` is a digest
    over these bytes and this runtime imports nothing from `agentic_postgres`
    (ADR 0084). A contract test keeps the two equal (D486's arrangement).
    """
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    )


def _classification(
    entry: Any, tool_name: str, version: int
) -> tuple[str | None, tuple[CapabilityRef, ...]]:
    """`risk` and the backing capabilities, required from lock version 2 (ADR 0177).

    **Both directions are refused**, and the second is the one worth having: a
    v1 lock carrying these keys came from a compiler that disagrees with its own
    declared version, and reading them anyway would make the version number
    decorative. The first is the ordinary strictness of this module -- a tool
    silently missing its risk is indistinguishable from one classified as
    harmless.
    """
    where = f"tool {tool_name}"
    present = "risk" in entry or "capabilities" in entry

    if version < VERSIONED_CAPABILITIES_FROM:
        if present:
            raise LockError(
                f"{where} carries risk or capabilities at lock schema_version {version}, "
                f"which does not define them; they arrive at "
                f"{VERSIONED_CAPABILITIES_FROM}"
            )
        return None, ()

    risk = _require(entry, "risk", str, where)
    if risk not in ("low", "moderate", "high"):
        raise LockError(f"{where}.risk is {risk!r}, which is not a classification")

    declared = _require(entry, "capabilities", list, where)
    if not declared:
        raise LockError(f"{where} names no backing capability")

    refs = []
    for item in declared:
        capability = _require(item, "name", str, f"{where}.capabilities")
        lifecycle = _require(item, "lifecycle", str, f"{where}.capabilities.{capability}")
        if lifecycle == "retired":
            raise LockError(
                f"{where} is backed by retired capability {capability!r}. A retired "
                "capability leaves the lock; one that reached it was compiled wrong"
            )
        refs.append(
            CapabilityRef(
                name=capability,
                version=_require(item, "version", str, f"{where}.capabilities.{capability}"),
                lifecycle=lifecycle,
                risk=_require(item, "risk", str, f"{where}.capabilities.{capability}"),
            )
        )
    return risk, tuple(refs)


def _budgets(entry: Any, tool_name: str, kind: str, version: int) -> dict[str, Any]:
    """The per-capability bounds a read or a write carries from lock version 3.

    **Both directions, as everywhere else in this module.** A tool carrying them
    below v3 came from a compiler that disagrees with its own declared version;
    a metadata tool carrying them at any version is describing a bound it has --
    `_within_byte_budget` never sees its result and it takes no concurrency slot
    (ADR 0179).

    The values are checked rather than trusted. A lock is an input, not a
    teammate: the schema refuses a manifest that widens, and this refuses a lock
    that does, because they are two different documents and only one of them was
    produced by this repository's compiler.
    """
    where = f"tool {tool_name}"
    keys = ("max_response_bytes", "max_concurrent_calls", "supports_dry_run", "requires_approval")
    present = [key for key in keys if key in entry]

    if version < BUDGETS_FROM or kind == "metadata":
        if present:
            raise LockError(
                f"{where} carries {present} at lock schema_version {version} with kind "
                f"{kind!r}, which bounds none of them; they arrive at {BUDGETS_FROM} for "
                "a read or a write"
            )
        return {}

    budgets: dict[str, Any] = {
        "max_response_bytes": _require(entry, "max_response_bytes", int, where),
        "max_concurrent_calls": _require(entry, "max_concurrent_calls", int, where),
    }
    if budgets["max_response_bytes"] < 1:
        raise LockError(f"{where}.max_response_bytes is not a positive number of bytes")
    if budgets["max_concurrent_calls"] < 1:
        raise LockError(
            f"{where}.max_concurrent_calls is {budgets['max_concurrent_calls']}; "
            "a tool bounded to nothing"
        )

    if kind == "write":
        budgets["supports_dry_run"] = _require(entry, "supports_dry_run", bool, where)
        budgets["requires_approval"] = _require(entry, "requires_approval", bool, where)
    elif "supports_dry_run" in entry or "requires_approval" in entry:
        raise LockError(
            f"{where} is a {kind} and declares a dry run or an approval; a call that "
            "changes nothing has neither"
        )
    return budgets


def _write(entry: Any, tool_name: str) -> WriteSpec:
    """The write shape, required in full or refused (D470).

    The same strictness `_resource` applies to a read: every member here
    decides what a caller can do, so a lenient default would be a bound nobody
    reviewed. `max_affected_rows` below 1 is a write that may change nothing it
    can report, and an operation whose method is not `post` is a write wearing
    a read's verb -- the compiler refuses both upstream, and the lock is
    validated as if the compiler had not (a lock is an input, not a teammate).
    """
    where = f"tool {tool_name}"
    operation = _require(entry, "operation", dict, where)
    method = _require(operation, "method", str, f"{where}.operation").lower()
    if method != "post":
        raise LockError(f"{where} writes over {method.upper()}; a write is a POST")

    bound = _require(entry, "max_affected_rows", int, where)
    if bound < 1:
        raise LockError(f"{where}.max_affected_rows is {bound}; a write bounded to nothing")

    idempotent = entry.get("idempotent")
    if not isinstance(idempotent, bool):
        raise LockError(f"{where}.idempotent is not a boolean")

    arguments = _strings(entry.get("arguments"), f"{where}.arguments")
    if not arguments:
        raise LockError(f"{where} declares no arguments; 0019's writes all take some")

    return WriteSpec(
        operation=Operation(
            method=method,
            path=_require(operation, "path", str, f"{where}.operation"),
            operation_id=_require(operation, "operation_id", str, f"{where}.operation"),
        ),
        arguments=arguments,
        required_scopes=_strings(entry.get("required_scopes"), f"{where}.required_scopes"),
        max_affected_rows=bound,
        idempotent=idempotent,
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
