"""The intermediate representation a generated client is emitted from (ADR 0204).

**Four inputs, and nothing else**: the merged reviewed surface, the PostgREST
snapshot (the project's when it declares a set, the release's otherwise), the
application snapshot, and the project's compiled lock -- as a *document*, the
JSON, never the service's dataclasses, because `src/` may not import
`services/` (ADR 0084).

What this module is for is stated once here, because every rule below follows
from it. A generated client is *held by someone who did not generate it*, and it
goes stale in both directions: the surface can move under the client, and the
client can be regenerated from a contract the deployment has not caught up to.
That is D700's shape (`backup_state`) at the caller. So the IR carries, beside
the shapes an emitter needs, the **digests of the artefacts it was built from**,
and the emitted client refuses to call anything until it has compared the one
digest it can legitimately read at runtime -- the served REST document's, as the
caller -- against the one it was generated with.

Pure: files in, a frozen dataclass out. No subprocess, no network, no
environment, no import from `services/` or `bin/`. That is what makes every
proof of this module an offline one (ADR 0202), and it is asserted by AST in
`tests/contract/test_client_ir.py` rather than described here.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from agentic_postgres import REPO_ROOT, capability_compiler, compatibility, openapi_normalize
from agentic_postgres.config import ManifestError
from agentic_postgres.evaluation_harness import filter_operators

__all__ = [
    "CALLER_FACING_TOKENS",
    "FORMAT_TYPES",
    "IR",
    "PT_CODE_PATTERN",
    "READ_RELATION_ARGUMENTS",
    "RESERVED_WRITE_PARAMETERS",
    "Argument",
    "AuthOperation",
    "ClientIrError",
    "Column",
    "Digests",
    "Relation",
    "Rpc",
    "Tool",
    "ToolArgument",
    "build",
    "classify_changes",
    "from_document",
    "js_reproducible",
    "next_version",
    "to_document",
]


class ClientIrError(ManifestError):
    """An IR that cannot be built from the four inputs given.

    A `ManifestError` like every other refusal in this package, so a command
    that already handles one handles this.
    """


#: PostgREST's `format` for a column or an argument, mapped to the TypeScript
#: type a client may declare for it.
#:
#: **Exhaustive on purpose, and an unknown format refuses** (ADR 0204). The
#: tempting default is `any` -- or `unknown` -- for a format nobody listed, and
#: it is wrong in the direction that cannot be noticed: a client would compile,
#: the developer would get no type, and the first thing they learn about the
#: column is whatever the runtime hands them. A format this table does not name
#: is a format nobody decided about, which is `compatibility.required_level`'s
#: rule applied one layer down.
#:
#: `json`/`jsonb` map to `unknown` and that is not a default: it is the correct
#: type for a value whose shape the contract genuinely does not state, and
#: `unknown` (unlike `any`) forces the caller to narrow before use.
#:
#: **Every key below is a spelling measured against a running PostgREST**, by
#: rig 27b at Session 27 Run 2 (D1390) -- one column and one RPC argument of
#: every type in this table plus every array form, read out of the served
#: document. Before that measurement the table was written from the SQL type
#: names, and seventeen of its twenty-one entries had never matched a served
#: format in this repository's history: PostgREST serves an `integer` as
#: `int32` everywhere, and had never been asked for an array at all. The
#: measurement is committed beside the guard in
#: `tests/contract/test_client_ir.py` as `RIG_27B_SERVED`, so the next spelling
#: this table lacks fails a proof rather than an adopter's first generate.
#:
#: `tsvector` is deliberately absent and must stay absent: it is the control in
#: `test_an_unknown_column_format_is_refused_and_never_typed_any`, and the
#: property it holds -- that a format nobody decided about refuses rather than
#: becoming `any` -- is what this table may never be widened past.
FORMAT_TYPES: dict[str, str] = {
    # --- what PostgREST serves for a scalar column or argument -------------
    "uuid": "string",
    "text": "string",
    "character varying": "string",
    "character": "string",
    "name": "string",
    "timestamp with time zone": "string",
    "timestamp without time zone": "string",
    "date": "string",
    "time with time zone": "string",
    "time without time zone": "string",
    "interval": "string",
    "extensions.vector": "string",
    # `int32` and `int64` are what PostgREST actually serves for `integer`,
    # `smallint` and `bigint`, as a COLUMN and as an ARGUMENT alike (rig 27b).
    "int32": "number",
    "int64": "number",
    "real": "number",
    "double precision": "number",
    "numeric": "number",
    "boolean": "boolean",
    "json": "unknown",
    "jsonb": "unknown",
    # --- the SQL spellings, which PostgREST serves for NO scalar ------------
    # Kept because `_openapi_type` reduces the APPLICATION snapshot's JSON
    # Schema types into this same table: `integer` and `numeric` are reached
    # from there, `text`, `boolean` and `json` above are reached from both.
    # `smallint` and `bigint` are reached by neither document and are kept only
    # so that a hand-written surface spelling them resolves rather than refuses.
    "integer": "number",
    "bigint": "number",
    "smallint": "number",
    # --- arrays, which carry the SQL spelling and never `int32` -------------
    # Measured by rig 27b over every array form: an array is served as its base
    # type's SQL name with `[]`, with the modifier kept only for `vector`
    # (`extensions.vector(768)[]`), which `_FORMAT_MODIFIER` strips.
    "text[]": "string[]",
    "character varying[]": "string[]",
    "character[]": "string[]",
    "name[]": "string[]",
    "uuid[]": "string[]",
    "timestamp with time zone[]": "string[]",
    "timestamp without time zone[]": "string[]",
    "date[]": "string[]",
    "time with time zone[]": "string[]",
    "time without time zone[]": "string[]",
    "interval[]": "string[]",
    "extensions.vector[]": "string[]",
    "integer[]": "number[]",
    "bigint[]": "number[]",
    "smallint[]": "number[]",
    "real[]": "number[]",
    "double precision[]": "number[]",
    "numeric[]": "number[]",
    "boolean[]": "boolean[]",
    "json[]": "unknown[]",
    "jsonb[]": "unknown[]",
}

#: A parameterised format carries its modifier: a `vector` COLUMN is served as
#: `extensions.vector(768)` while the same type as an RPC ARGUMENT is served as
#: bare `extensions.vector`. Measured in the example project's snapshot, where
#: the two spellings of one type appear in one document (D1216). Stripped
#: before the table is consulted, so the table holds one entry per type rather
#: than one per modifier -- a table keyed on the modifier would refuse the first
#: column anybody declares at a different width.
#:
#: **The modifier can sit before a trailing `[]`, which is why this is not
#: anchored at the end of the string** (rig 27b, D1390): an array of vectors is
#: served as `extensions.vector(768)[]`. `character varying(64)` is NOT one of
#: these -- PostgREST drops that modifier itself, as a column and in an array
#: alike -- so `vector` is the one type this branch exists for, and it is the
#: one the release's own example domain uses.
_FORMAT_MODIFIER = re.compile(r"\(\s*[^()]*\)\s*(?=(?:\s*\[\s*\])*\s*$)")

#: Every `PT` SQLSTATE this product's migrations raise, matched in SQL text.
PT_CODE_PATTERN = re.compile(r"\bPT\d{3}\b")

#: The read tool's fixed signature, as the RUNTIME declares it
#: (`mcp_tools.register_relation_read`). Copied from that registration rather
#: than invented, because a client that sent a name the runtime does not declare
#: would be generating a call the product cannot receive. `resource` is the only
#: required one.
READ_RELATION_ARGUMENTS: tuple[tuple[str, str, bool], ...] = (
    ("resource", "string", True),
    ("columns", "string[]", False),
    ("filters", "AgentFilter[]", False),
    ("order_by", "number", False),
    ("limit", "number", False),
)

#: The two parameters every write tool takes beside the lock's own arguments,
#: and both are REQUIRED of a caller (`mcp_tools.register_write`: *"every one is
#: required"*). A second copy of `evaluation_harness.RESERVED_WRITE_PARAMETERS`,
#: compared against it by a test (D486).
RESERVED_WRITE_PARAMETERS: tuple[str, ...] = ("idempotency_key", "dry_run")

#: The seven tokens an agent may be told, and the only ones. A second copy of
#: `services/auth-api/app/mcp_errors.CALLER_FACING_TOKENS`, here because `src/`
#: may not import `services/` (ADR 0084) and a generated client's refusal union
#: must be exactly the runtime's vocabulary. Equality is asserted by
#: `test_the_caller_facing_tokens_match_the_runtimes`, which imports the service
#: module the way the service's own tests do -- D486's arrangement: two copies of
#: a fact with a test between them are one fact.
CALLER_FACING_TOKENS: tuple[str, ...] = (
    "approval_required",
    "budget_exceeded",
    "input_not_permitted",
    "resource_unknown",
    "row_not_found",
    "scope_not_held",
    "write_conflict",
)

#: The three application operations a client wraps, by path (D1209). The admin
#: and storage halves are deliberately absent: a client holds no administrative
#: credential, and wrapping `/admin/*` would generate calls whose refusal is the
#: point.
AUTH_PATHS: tuple[str, ...] = ("/auth/login", "/auth/refresh", "/auth/me")

#: JavaScript's `Number` is an IEEE double, so an integer past this loses
#: precision in a round trip and the canonical form stops reproducing (D1203).
_JS_SAFE_INTEGER = 2**53


# ---------------------------------------------------------------------------
# the representation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Column:
    name: str
    ts_type: str
    format: str
    nullable: bool


@dataclass(frozen=True)
class Relation:
    name: str
    columns: tuple[Column, ...]
    methods: tuple[str, ...]


@dataclass(frozen=True)
class Argument:
    name: str
    ts_type: str
    format: str
    required: bool


@dataclass(frozen=True)
class Rpc:
    name: str
    arguments: tuple[Argument, ...]
    path: str


@dataclass(frozen=True)
class AuthOperation:
    name: str
    method: str
    path: str
    request: tuple[Argument, ...]
    response_schema: str


@dataclass(frozen=True)
class ToolArgument:
    name: str
    ts_type: str
    required: bool


@dataclass(frozen=True)
class Tool:
    name: str
    kind: str
    arguments: tuple[ToolArgument, ...]
    discovery_scope_sets: tuple[tuple[str, ...], ...]
    resources: tuple[str, ...]
    supports_dry_run: bool | None
    requires_approval: bool | None
    descriptions: tuple[str, ...]


@dataclass(frozen=True)
class Digests:
    """The four artefacts a client is a claim about.

    **`merged_surface_sha256`, not `api_surface_sha256`** (D1217). That name is
    taken: `bin/mcp-contract.py` writes `sources.api_surface_sha256` and the
    deployed document publishes `api.api_surface_sha256`, and both mean *the
    digest of the release's reviewed file's bytes*. This field means the digest
    of the MERGED surface -- release joined with the project's -- which for a
    project that declares a set is a different value. Two fields with one name
    digesting two files is a defect this repository already carries one instance
    of (the two `capabilities_sha256`), and a third was not worth the symmetry.

    `app_openapi_sha256` is **provenance and is never checked at runtime**
    (D1209, ADR 0204): the application document is not served to a caller on a
    route a client holds, and its canonical form is not reproducible in
    JavaScript (D1203), so a client comparing it could never pass.
    """

    merged_surface_sha256: str
    rest_openapi_sha256: str
    app_openapi_sha256: str
    tools_sha256: str


@dataclass(frozen=True)
class IR:
    rest_contract_id: str
    agent_contract_id: str
    project_root: str | None
    relations: tuple[Relation, ...]
    rpcs: tuple[Rpc, ...]
    auth: tuple[AuthOperation, ...]
    tools: tuple[Tool, ...]
    enums: dict[str, tuple[str, ...]]
    filter_operators: tuple[str, ...]
    pt_codes: tuple[str, ...]
    caller_facing_tokens: tuple[str, ...]
    digests: Digests
    template_version: str


# ---------------------------------------------------------------------------
# typing a column or an argument
# ---------------------------------------------------------------------------


def _ts_type(
    *,
    format_name: str,
    exposed_schema: str,
    enums: dict[str, tuple[str, ...]],
    where: str,
) -> str:
    """The TypeScript type for one served format. Refuses an unknown one.

    **One type has up to three spellings in one document, and all three were
    measured** (D1216):

    * a COLUMN of an enum type carries the SCHEMA-QUALIFIED name
      (`tasks.status` → `api.task_status`);
    * the same type as an RPC ARGUMENT carries the BARE name
      (`update_task_status.p_expected_status` → `task_status`);
    * a parameterised type carries its modifier as a column and not as an
      argument (`note_embeddings.embedding` → `extensions.vector(768)`,
      `set_note_embedding.p_embedding` → `extensions.vector`).

    Resolution order matters and is deliberate: the qualified name first, then
    the built-in table, then the bare enum name. A bare format that is also a
    built-in type name therefore resolves to the built-in, and an enum that
    would shadow one is refused outright rather than silently typed as the
    built-in -- the qualified spelling would reach the enum while the bare one
    reached `string`, and the generated client would disagree with itself about
    one type.
    """
    bare = _FORMAT_MODIFIER.sub("", format_name).strip()
    prefix = f"{exposed_schema}."

    shadowed = sorted(set(enums) & set(FORMAT_TYPES))
    if shadowed:
        raise ClientIrError(
            f"the reviewed surface declares enum(s) {shadowed} whose name(s) are also "
            "PostgREST format names. A column of that type is served qualified and an "
            "argument of it bare, so the two spellings would resolve to different "
            "TypeScript types. Rename the type"
        )

    if bare.startswith(prefix):
        key = bare[len(prefix) :]
        if key not in enums:
            raise ClientIrError(
                f"{where} is served as {format_name!r}, which names a type in the exposed "
                f"schema, but the reviewed surface declares no enum {key!r}. Either the "
                "surface is missing the type or the snapshot predates it -- a client "
                "cannot name the members of a type nobody reviewed"
            )
        return _enum_union(enums[key])

    if bare in FORMAT_TYPES:
        return FORMAT_TYPES[bare]

    if bare in enums:
        return _enum_union(enums[bare])

    # `where` is "column <relation>.<column>" or "argument <rpc>.<argument>";
    # the noun is taken from it rather than assumed, because the sentence used
    # to say "column" to somebody looking at an argument (D1390).
    noun = where.split(" ", 1)[0]
    raise ClientIrError(
        f"{where} is served as format {format_name!r}, which this generator has no "
        f"TypeScript type for. Add it to client_ir.FORMAT_TYPES with the type it should "
        f"carry; it is not given `any`, because a {noun} whose type nobody decided is "
        f"not a {noun} a client should silently accept (ADR 0204)"
    )


def _enum_union(values: tuple[str, ...]) -> str:
    """A string-literal union, members in the REVIEWED order.

    The surface's list order, which is the order a reviewer wrote and the order
    `enumsortorder` produced when the type was captured. Not sorted: a union
    re-sorted here would diff against the contract for no reason.
    """
    return " | ".join(f'"{value}"' for value in values)


# ---------------------------------------------------------------------------
# the JavaScript canonical form's preconditions
# ---------------------------------------------------------------------------


def js_reproducible(document: Any) -> str | None:
    """The first JSON pointer whose value JavaScript would serialize differently.

    `None` when the whole document reproduces. Measured rather than reasoned
    (rig 23b, D1203): `JSON.stringify(sortKeysDeep(x), null, 2) + "\\n"` equals
    `openapi_normalize.canonical_bytes` for four of the five committed
    contracts, and differs for `app-openapi.canonical.json` on exactly two
    lines -- `1.0` and `0.0`, which JavaScript prints as `1` and `0` because it
    has one number type.

    Three causes, each checked:

    * a `float` -- JavaScript prints `1.0` as `1`, so the bytes differ;
    * an `int` past 2**53 -- outside the double's exact range, so a round trip
      loses digits (measured: `12345678901234567890` came back as
      `12345678901234567000`);
    * keys that Python's `sorted` and JavaScript's sort order differently.
      `Array.prototype.sort` compares UTF-16 code units and Python compares
      code points, and the two disagree above the BMP -- an astral character
      sorts below `\\uffff` in JavaScript and above it in Python.

    A `bool` is checked before `int` on purpose: `isinstance(True, int)` is true
    in Python, and reporting every boolean as a precision risk would make this
    function useless at exactly the moment somebody needed to trust it.
    """
    return _js_offender(document, "")


def _js_offender(node: Any, pointer: str) -> str | None:
    if isinstance(node, bool):
        return None
    if isinstance(node, float):
        return pointer or "/"
    if isinstance(node, int):
        return pointer or "/" if abs(node) > _JS_SAFE_INTEGER else None
    if isinstance(node, dict):
        keys = list(node)
        if sorted(keys) != sorted(keys, key=lambda key: key.encode("utf-16-be", "surrogatepass")):
            return pointer or "/"
        for key in keys:
            found = _js_offender(
                node[key], f"{pointer}/{key.replace('~', '~0').replace('/', '~1')}"
            )
            if found is not None:
                return found
        return None
    if isinstance(node, list):
        for index, value in enumerate(node):
            found = _js_offender(value, f"{pointer}/{index}")
            if found is not None:
                return found
    return None


# ---------------------------------------------------------------------------
# building
# ---------------------------------------------------------------------------


def build(
    *,
    surface: dict[str, Any],
    snapshot: dict[str, Any],
    app_snapshot: dict[str, Any],
    lock: dict[str, Any],
    project_root: str | None,
    pt_sources: tuple[Path, ...],
    app_snapshot_bytes: bytes,
    template_version: str,
) -> IR:
    """The IR for one project, from the four inputs and nothing else.

    `app_snapshot_bytes` is taken beside the parsed document because that
    digest is over the FILE (D1203): the application snapshot's canonical form
    is not reproducible in JavaScript, so a digest of a re-serialization would
    be a value no reader could recompute.
    """
    exposed = surface["exposed_schema"]
    enums = {name: tuple(entry["values"]) for name, entry in (surface.get("enums") or {}).items()}

    _refuse_object_disagreement(snapshot, surface)

    offender = js_reproducible(snapshot)
    if offender is not None:
        raise ClientIrError(
            f"the REST snapshot holds a value at {offender} that JavaScript serializes "
            "differently, so the generated client's canonical form could not reproduce this "
            "document's fingerprint and `init()` would refuse every correct deployment "
            "(D1203). Repair the capture, not the client"
        )

    relations = tuple(
        _relation(name=name, entry=entry, snapshot=snapshot, exposed=exposed, enums=enums)
        for name, entry in sorted((surface.get("relations") or {}).items())
    )
    rpcs = tuple(
        _rpc(name=name, entry=entry, snapshot=snapshot, exposed=exposed, enums=enums)
        for name, entry in sorted((surface.get("rpcs") or {}).items())
    )
    auth = tuple(_auth_operation(path=path, document=app_snapshot) for path in AUTH_PATHS)
    tools = tuple(_tool(entry) for entry in sorted(lock["tools"], key=lambda t: t["name"]))

    return IR(
        rest_contract_id=surface["contract_id"],
        agent_contract_id=lock["contract_id"],
        project_root=project_root,
        relations=relations,
        rpcs=rpcs,
        auth=auth,
        tools=tools,
        enums=enums,
        filter_operators=tuple(filter_operators()),
        pt_codes=_pt_codes(pt_sources),
        caller_facing_tokens=CALLER_FACING_TOKENS,
        digests=Digests(
            merged_surface_sha256=sha256(capability_compiler.canonical_bytes(surface)).hexdigest(),
            rest_openapi_sha256=openapi_normalize.fingerprint(snapshot),
            app_openapi_sha256=sha256(app_snapshot_bytes).hexdigest(),
            tools_sha256=_required_digest(lock),
        ),
        template_version=template_version,
    )


def _required_digest(lock: dict[str, Any]) -> str:
    """The lock's own `tools_sha256`, which a generated client compares live.

    Refused when absent rather than recomputed. The client's `listResources()`
    check is *"the plane reports the digest I was generated from"*, and a digest
    this generator computed itself would make that a comparison of the generator
    against itself -- the shape D1153 is about, one layer out.
    """
    digest = lock.get("tools_sha256")
    if not isinstance(digest, str) or not digest:
        raise ClientIrError(
            "the lock carries no `tools_sha256`, so a generated client could not check "
            "which roster the plane loaded (ADR 0204). Compile the lock at schema 4 or "
            "above -- `bin/mcp-contract.sh lock --project FILE`"
        )
    return digest


def _refuse_object_disagreement(snapshot: dict[str, Any], surface: dict[str, Any]) -> None:
    """The comparison `bin/api-contract.py::compare_snapshot_to_surface` makes.

    Made again here rather than imported, because `src/` may not import `bin/`
    -- and made the SAME way, over `openapi_normalize.declared_objects` and the
    surface's own names spelled as served paths, so the two cannot disagree
    about what a difference is. Both directions refuse: a published object the
    surface does not name is the case the contract exists for, and a reviewed
    object the snapshot does not publish means the snapshot predates the
    surface and the client would be generated against a stale capture.
    """
    published = openapi_normalize.declared_objects(snapshot)
    reviewed = set(surface.get("relations") or {}) | {
        f"rpc/{name}" for name in (surface.get("rpcs") or {})
    }

    unreviewed = sorted(published - reviewed)
    if unreviewed:
        raise ClientIrError(
            f"the snapshot publishes {unreviewed}, which the reviewed surface does not "
            "name. A client generated from this pair would declare calls nobody reviewed"
        )
    unpublished = sorted(reviewed - published)
    if unpublished:
        raise ClientIrError(
            f"the reviewed surface names {unpublished}, which the snapshot does not "
            "publish. Either the migration that creates it has not shipped, its grants "
            "keep it out of the document, or the snapshot predates this surface -- "
            "re-capture it with `bin/api-contract.sh --update` after the deploy that "
            "serves it, then generate"
        )


def _relation(
    *,
    name: str,
    entry: dict[str, Any],
    snapshot: dict[str, Any],
    exposed: str,
    enums: dict[str, tuple[str, ...]],
) -> Relation:
    """One relation, columns in the SURFACE's order and typed from the snapshot.

    The surface's order, not the snapshot's: the snapshot sorts its properties
    (the canonical form sorts every key), and the surface's order is the one a
    reviewer chose. A generated type whose field order came from a sort would
    reorder itself the first time a column was renamed.
    """
    definition = (snapshot.get("definitions") or {}).get(name)
    if not isinstance(definition, dict):
        raise ClientIrError(
            f"the snapshot publishes no definition for relation {name!r}, so its column "
            "types are unknown. A client cannot type a row it has no definition for"
        )
    properties = definition.get("properties") or {}

    columns = []
    for column in entry.get("columns") or ():
        spec = properties.get(column)
        if not isinstance(spec, dict) or "format" not in spec:
            raise ClientIrError(
                f"the reviewed surface names column {name}.{column!r}, which the "
                f"snapshot's definition does not publish with a format. The snapshot "
                "predates the surface, or the column is not granted to the role the "
                "capture read as"
            )
        format_name = spec["format"]
        columns.append(
            Column(
                name=column,
                ts_type=_ts_type(
                    format_name=format_name,
                    exposed_schema=exposed,
                    enums=enums,
                    where=f"column {name}.{column}",
                ),
                format=format_name,
                # **Every column is nullable in the generated type.** PostgREST's
                # document states `required` for a request body and says nothing
                # about a view's columns, so the honest answer for a read row is
                # that the contract does not state it -- and a client that
                # declared a column non-null on no evidence would be the
                # generated equivalent of D600's `null` that looks measured.
                nullable=True,
            )
        )
    return Relation(name=name, columns=tuple(columns), methods=tuple(entry.get("methods") or ()))


def _rpc(
    *,
    name: str,
    entry: dict[str, Any],
    snapshot: dict[str, Any],
    exposed: str,
    enums: dict[str, tuple[str, ...]],
) -> Rpc:
    """One reviewed RPC, arguments in the SURFACE's order, typed from the body.

    A name in one document and not the other refuses in both directions: an
    argument the surface reviewed and the snapshot does not publish means the
    function's signature moved, and one the snapshot publishes and the surface
    does not name is an argument nobody reviewed.
    """
    path = f"/rpc/{name}"
    operation = (snapshot.get("paths") or {}).get(path, {}).get("post")
    if not isinstance(operation, dict):
        raise ClientIrError(
            f"the snapshot publishes no POST at {path!r}, which the reviewed surface "
            f"names as an RPC. A client cannot call a function the document does not "
            "advertise"
        )
    body = next(
        (
            parameter
            for parameter in operation.get("parameters") or ()
            if isinstance(parameter, dict) and parameter.get("in") == "body"
        ),
        None,
    )
    schema = (body or {}).get("schema") or {}
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or ())

    reviewed = tuple(entry.get("arguments") or ())
    unreviewed = sorted(set(properties) - set(reviewed))
    if unreviewed:
        raise ClientIrError(
            f"the snapshot's body for {path!r} publishes {unreviewed}, which the reviewed "
            "surface does not name as arguments of that function"
        )
    missing = sorted(set(reviewed) - set(properties))
    if missing:
        raise ClientIrError(
            f"the reviewed surface names arguments {missing} of {path!r}, which the "
            "snapshot's body does not publish. The function's signature moved, or the "
            "snapshot predates it"
        )

    arguments = tuple(
        Argument(
            name=argument,
            ts_type=_ts_type(
                format_name=properties[argument]["format"],
                exposed_schema=exposed,
                enums=enums,
                where=f"argument {name}.{argument}",
            ),
            format=properties[argument]["format"],
            required=argument in required,
        )
        for argument in reviewed
    )
    return Rpc(name=name, arguments=arguments, path=path)


def _auth_operation(*, path: str, document: dict[str, Any]) -> AuthOperation:
    """One of the three authentication operations, read from the app snapshot."""
    entry = (document.get("paths") or {}).get(path)
    if not isinstance(entry, dict):
        raise ClientIrError(
            f"the application snapshot publishes no {path!r}. A client wraps exactly the "
            f"three operations {list(AUTH_PATHS)} (D1209); one of them is missing, so the "
            "snapshot is not this release's"
        )
    method = "post" if "post" in entry else "get"
    operation = entry.get(method)
    if not isinstance(operation, dict):
        raise ClientIrError(f"{path!r} publishes neither a POST nor a GET in the snapshot")

    request: tuple[Argument, ...] = ()
    body = ((operation.get("requestBody") or {}).get("content") or {}).get("application/json")
    schema = (body or {}).get("schema") or {}
    reference = schema.get("$ref") or ""
    resolved = _resolve(document, reference) if reference else schema
    properties = (resolved or {}).get("properties") or {}
    required = set((resolved or {}).get("required") or ())
    request = tuple(
        Argument(
            name=field,
            # The application document is OpenAPI 3 from FastAPI, whose schemas
            # carry `type` and not PostgREST's `format`. Typed from `type`
            # through the same table, so one mapping serves both documents.
            ts_type=FORMAT_TYPES.get(_openapi_type(spec), "unknown"),
            format=_openapi_type(spec),
            required=field in required,
        )
        for field, spec in sorted(properties.items())
    )

    responses = operation.get("responses") or {}
    success = responses.get("200") or responses.get("201") or {}
    response_body = ((success.get("content") or {}).get("application/json") or {}).get("schema", {})
    response_schema = (response_body.get("$ref") or "").rsplit("/", 1)[-1] or "unknown"

    return AuthOperation(
        name=path.rsplit("/", 1)[-1].replace("-", "_"),
        method=method.upper(),
        path=path,
        request=request,
        response_schema=response_schema,
    )


def _openapi_type(spec: dict[str, Any]) -> str:
    """An OpenAPI 3 schema's scalar type name, reduced to one of ours.

    `anyOf` is FastAPI's spelling of an optional field, and the interesting
    member is the one that is not `null`.
    """
    if "type" in spec:
        name = spec["type"]
        return {
            "string": "text",
            "integer": "integer",
            "number": "numeric",
            "boolean": "boolean",
        }.get(name, name)
    for member in spec.get("anyOf") or ():
        if isinstance(member, dict) and member.get("type") != "null":
            return _openapi_type(member)
    return "json"


def _resolve(document: dict[str, Any], reference: str) -> dict[str, Any]:
    """One local `$ref`. Nothing else: a remote reference is not resolvable
    offline, and a client generated from a document that needed one would be a
    client generated from something nobody committed."""
    if not reference.startswith("#/"):
        raise ClientIrError(f"the application snapshot carries a non-local $ref {reference!r}")
    node: Any = document
    for part in reference[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise ClientIrError(
                f"the application snapshot's $ref {reference!r} resolves to nothing"
            )
        node = node[part]
    return node if isinstance(node, dict) else {}


def _tool(entry: dict[str, Any]) -> Tool:
    """One tool from the lock document, with the arguments the RUNTIME declares.

    Copied from `mcp_tools.register_*` rather than derived from the lock's shape,
    because the runtime's registered signature is what a call must match: a
    client sending a name the runtime does not declare generates a request the
    product cannot receive (ADR 0127).
    """
    kind = entry["kind"]
    name = entry["name"]

    if kind == "read":
        # A relation read takes the query shape; an rpc read takes NOTHING
        # (`register_rpc_read`: *"one named RPC, chosen from the lock, no caller
        # input"*). At lock schema 4 the lock declares which it is; below that
        # it is derived from the methods its resources reach, the way
        # `mcp_lock._read_shape` derives it.
        shape = entry.get("reads") or _derived_read_shape(entry)
        if shape == "rpc":
            arguments: tuple[ToolArgument, ...] = ()
        else:
            arguments = tuple(
                ToolArgument(name=argument, ts_type=ts_type, required=required)
                for argument, ts_type, required in READ_RELATION_ARGUMENTS
            )
    elif kind == "write":
        # **The lock DOCUMENT's shape, which is flat.** `arguments`, `operation`
        # and `required_scopes` sit at the tool entry's top level; the nested
        # `write` member is `mcp_lock.WriteSpec`'s shape, which is the loaded
        # dataclass and not the JSON (D1218). Reading the dataclass's shape here
        # found every write tool argument-less and refused the release's own
        # lock -- `src/` may not import `services/` (ADR 0084), so the document
        # is the only shape this module may believe.
        declared = tuple(entry.get("arguments") or ())
        if not declared:
            raise ClientIrError(
                f"write tool {name!r} declares no arguments in the lock, so a client could "
                "not build a call for it"
            )
        arguments = (
            *(
                ToolArgument(name=argument, ts_type="string", required=True)
                for argument in declared
            ),
            ToolArgument(name="idempotency_key", ts_type="string", required=True),
            ToolArgument(name="dry_run", ts_type="boolean", required=True),
        )
    elif kind == "metadata":
        # `list_resources` takes nothing; `describe_resource` takes the pair it
        # needs to select one resource out of the lock.
        arguments = (
            (
                ToolArgument(name="tool", ts_type="string", required=True),
                ToolArgument(name="resource", ts_type="string", required=True),
            )
            if name == "describe_resource"
            else ()
        )
    else:
        raise ClientIrError(
            f"tool {name!r} is of kind {kind!r}, which this generator has no call shape "
            "for. A client may not guess how to call a tool"
        )

    return Tool(
        name=name,
        kind=kind,
        arguments=arguments,
        discovery_scope_sets=tuple(
            tuple(scopes) for scopes in entry.get("discovery_scope_sets") or ()
        ),
        resources=tuple(
            resource["name"] for resource in entry.get("resources") or () if "name" in resource
        ),
        supports_dry_run=entry.get("supports_dry_run"),
        requires_approval=entry.get("requires_approval"),
        descriptions=tuple(entry.get("descriptions") or ()),
    )


def _derived_read_shape(entry: dict[str, Any]) -> str:
    methods = {
        resource.get("operation", {}).get("method") for resource in entry.get("resources") or ()
    }
    return "rpc" if methods == {"post"} else "relation"


def _pt_codes(sources: tuple[Path, ...]) -> tuple[str, ...]:
    """Every `PT` SQLSTATE the given migration directories raise, sorted.

    The caller passes the release's templates AND each project set's, so a
    project raising a code of its own gets it in its own client's error union.
    A generator scanning only the release would emit a union missing exactly the
    codes a tenant's own functions raise -- the client would then report the
    tenant's refusals as unrecognised.
    """
    codes: set[str] = set()
    for directory in sources:
        if not directory.is_dir():
            raise ClientIrError(
                f"{directory} is not a directory, so the PT codes it raises cannot be read"
            )
        for path in sorted(directory.glob("*.sql")):
            codes.update(PT_CODE_PATTERN.findall(path.read_text(encoding="utf-8")))
    return tuple(sorted(codes))


# ---------------------------------------------------------------------------
# versioning
# ---------------------------------------------------------------------------


def classify_changes(previous: IR, current: IR) -> tuple[str, ...]:
    """ADR 0162's change classes over an IR diff. Never a second scheme.

    Every name returned is already in `compatibility.CHANGE_CLASSES`, which is
    also the set `bin/upgrade.py` lets an operator declare with `--also`
    (D1213). So the generator's vocabulary and the upgrade planner's agree by
    construction rather than by reconciliation, and `required_level` turns the
    result into a bump without this module deciding what a bump means.

    **Compared member by member, not by dataclass equality** (D1219). Equality
    between two `Relation`s or two `Tool`s cannot tell an addition from a
    retyping, and `api_operation_changed` is MAJOR -- so the equality reading
    classified the example project's purely additive tenant extension as a major
    bump, because `query_resource` gained `note_embeddings` in its resource set.
    Stage 3's whole premise is that adding a table is additive, so the grain has
    to be the member: something gained is `api_operation_added` or
    `capability_added`, something removed or RETYPED is major.
    """
    changes: set[str] = set()

    before = {relation.name: relation for relation in previous.relations}
    after = {relation.name: relation for relation in current.relations}
    before_rpcs = {rpc.name: rpc for rpc in previous.rpcs}
    after_rpcs = {rpc.name: rpc for rpc in current.rpcs}
    before_tools = {tool.name: tool for tool in previous.tools}
    after_tools = {tool.name: tool for tool in current.tools}

    if set(after) - set(before) or set(after_rpcs) - set(before_rpcs):
        changes.add("api_operation_added")
    if set(before) - set(after) or set(before_rpcs) - set(after_rpcs):
        changes.add("api_operation_removed")
    if set(after_tools) - set(before_tools):
        changes.add("capability_added")
    if set(before_tools) - set(after_tools):
        changes.add("api_operation_removed")

    for name in sorted(set(before) & set(after)):
        changes |= _relation_changes(before[name], after[name])
    for name in sorted(set(before_rpcs) & set(after_rpcs)):
        changes |= _argument_changes(
            tuple((a.name, a.ts_type, a.required) for a in before_rpcs[name].arguments),
            tuple((a.name, a.ts_type, a.required) for a in after_rpcs[name].arguments),
        )
    for name in sorted(set(before_tools) & set(after_tools)):
        changes |= _tool_changes(before_tools[name], after_tools[name])

    # An enum whose members GREW is additive for a caller writing values and
    # breaking for one exhaustively matching what it reads. The second reader is
    # the one a typed client creates, so a moved member set is major either way.
    if previous.enums != current.enums:
        changes.add("api_operation_changed")
    if previous.filter_operators != current.filter_operators:
        changes.add("api_operation_changed")
    if previous.auth != current.auth:
        changes.add("api_operation_changed")

    return tuple(sorted(changes))


def _relation_changes(previous: Relation, current: Relation) -> set[str]:
    """One relation's diff: a column gained is additive, retyped or lost is not."""
    changes: set[str] = set()
    before = {column.name: column.ts_type for column in previous.columns}
    after = {column.name: column.ts_type for column in current.columns}

    if set(after) - set(before):
        changes.add("api_operation_added")
    if set(before) - set(after):
        changes.add("api_operation_changed")
    if any(before[name] != after[name] for name in set(before) & set(after)):
        changes.add("api_operation_changed")
    if set(previous.methods) != set(current.methods):
        changes.add("api_operation_changed")
    return changes


def _argument_changes(
    previous: tuple[tuple[str, str, bool], ...], current: tuple[tuple[str, str, bool], ...]
) -> set[str]:
    """An argument list's diff.

    **Any difference at all is `api_operation_changed`, and that is not laziness
    -- an added argument really is breaking here.** PostgREST resolves a function
    by the set of argument names supplied, and a call missing one is a
    `404 PGRST202` (ADR 0139). So an argument added to an existing RPC breaks
    every existing caller, unlike a column added to a relation, which breaks
    none. The same goes for a write tool: `mcp_tools.register_write` makes every
    declared argument required.

    **Order is compared too**, not only the set: the lock declares a write's
    arguments in PostgreSQL parameter order and `mcp_lock` reads them *"in
    PARAMETER ORDER, never sorted"*, so a reordering is a different contract
    even with the same names. Tuple equality gives that for free, which is why
    this is one comparison rather than several.
    """
    return set() if previous == current else {"api_operation_changed"}


def _tool_changes(previous: Tool, current: Tool) -> set[str]:
    """One tool's diff: a resource gained is additive, everything else is not."""
    changes: set[str] = set()

    if set(current.resources) - set(previous.resources):
        changes.add("capability_added")
    if set(previous.resources) - set(current.resources):
        changes.add("api_operation_removed")
    changes |= _argument_changes(
        tuple((a.name, a.ts_type, a.required) for a in previous.arguments),
        tuple((a.name, a.ts_type, a.required) for a in current.arguments),
    )
    # **A discovery scope set is an ALTERNATIVE, so gaining one is additive**
    # (D1219). `discovery_scope_sets` is a disjunction -- a caller discovers the
    # tool if it holds every scope in ANY of the sets -- so adding
    # `('note_embeddings:read',)` beside `('notes:read',)` takes nothing from a
    # caller holding `notes:read`. That is exactly the example project's diff:
    # comparing the sets for inequality called the tenant extension breaking.
    # Losing a set is the breaking direction, because a caller who discovered
    # the tool through it no longer can.
    if set(current.discovery_scope_sets) - set(previous.discovery_scope_sets):
        changes.add("capability_added")
    if set(previous.discovery_scope_sets) - set(current.discovery_scope_sets):
        changes.add("api_operation_removed")
    if (previous.kind, previous.requires_approval, previous.supports_dry_run) != (
        current.kind,
        current.requires_approval,
        current.supports_dry_run,
    ):
        changes.add("api_operation_changed")
    return changes


def next_version(previous: str | None, level: str) -> str:
    """The artefact's OWN next number, bumped by `level`.

    `None` is `1.0.0`: a first generated client is a released artefact, not a
    `0.x` one, because the contract it is generated from is already reviewed and
    frozen. The number is the CLIENT's and never the template's -- a client
    regenerated from an unchanged contract does not move, whatever the template
    did (ADR 0204, ADR 0162).
    """
    if previous is None:
        return "1.0.0"
    version = compatibility.parse(previous)
    if level == compatibility.MAJOR:
        return f"{version.major + 1}.0.0"
    if level == compatibility.MINOR:
        return f"{version.major}.{version.minor + 1}.0"
    if level == compatibility.PATCH:
        return f"{version.major}.{version.minor}.{version.patch + 1}"
    raise ClientIrError(
        f"{level!r} is not one of {list(compatibility.LEVELS)}. A version is bumped by a "
        "level `compatibility` names, never by a string this module invented"
    )


# ---------------------------------------------------------------------------
# the document form
# ---------------------------------------------------------------------------


def to_document(ir: IR) -> dict[str, Any]:
    """The IR as JSON-able data, for the emitter's manifest and for `--check`.

    Round-trips through :func:`from_document`, asserted by a test: an IR that
    did not would make `--check` compare a client against a different IR than
    the one that wrote it, which is the drift the check exists to catch.
    """
    return asdict(ir)


def from_document(document: dict[str, Any]) -> IR:
    """The inverse of :func:`to_document`."""
    try:
        return IR(
            rest_contract_id=document["rest_contract_id"],
            agent_contract_id=document["agent_contract_id"],
            project_root=document["project_root"],
            relations=tuple(
                Relation(
                    name=relation["name"],
                    columns=tuple(Column(**column) for column in relation["columns"]),
                    methods=tuple(relation["methods"]),
                )
                for relation in document["relations"]
            ),
            rpcs=tuple(
                Rpc(
                    name=rpc["name"],
                    arguments=tuple(Argument(**argument) for argument in rpc["arguments"]),
                    path=rpc["path"],
                )
                for rpc in document["rpcs"]
            ),
            auth=tuple(
                AuthOperation(
                    name=operation["name"],
                    method=operation["method"],
                    path=operation["path"],
                    request=tuple(Argument(**argument) for argument in operation["request"]),
                    response_schema=operation["response_schema"],
                )
                for operation in document["auth"]
            ),
            tools=tuple(
                Tool(
                    name=tool["name"],
                    kind=tool["kind"],
                    arguments=tuple(ToolArgument(**argument) for argument in tool["arguments"]),
                    discovery_scope_sets=tuple(
                        tuple(scopes) for scopes in tool["discovery_scope_sets"]
                    ),
                    resources=tuple(tool["resources"]),
                    supports_dry_run=tool["supports_dry_run"],
                    requires_approval=tool["requires_approval"],
                    descriptions=tuple(tool["descriptions"]),
                )
                for tool in document["tools"]
            ),
            enums={name: tuple(values) for name, values in document["enums"].items()},
            filter_operators=tuple(document["filter_operators"]),
            pt_codes=tuple(document["pt_codes"]),
            caller_facing_tokens=tuple(document["caller_facing_tokens"]),
            digests=Digests(**document["digests"]),
            template_version=document["template_version"],
        )
    except (KeyError, TypeError) as exc:
        raise ClientIrError(
            f"the IR document is missing or misshapes {exc}. A `--check` against a "
            "malformed manifest would report drift it cannot actually see"
        ) from exc


def project_pt_sources(project_root: Path | None) -> tuple[Path, ...]:
    """The migration directories whose PT codes belong in one client's union.

    The release's templates always, and the project's own set when it has one.
    """
    sources = [REPO_ROOT / "migrations" / "templates"]
    if project_root is not None:
        candidate = project_root / "migrations"
        if candidate.is_dir():
            sources.append(candidate)
    return tuple(sources)
