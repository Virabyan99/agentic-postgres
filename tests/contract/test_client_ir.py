"""`GEN-IR-001`, `GEN-VERSION-001` and one half of `GEN-TOOLCHAIN-001` (Session 23 Run 2).

The IR is what every generated client is emitted from (ADR 0204), so a defect
here reaches a developer's checkout rather than a log. Three things are proved:

* the IR is built from **exactly four inputs** and carries what each one says;
* it **refuses** a surface and a snapshot that disagree, in both directions;
* the version rule is `compatibility`'s classes over an IR diff and **never a
  second scheme** -- which is what stops a generated artefact's number from
  meaning something different from the template's.

The lock is compiled **in the test** the way `bin/mcp-contract.py::command_lock`
compiles it -- the same library calls in the same order -- rather than loaded
from a committed fixture. A fixture lock would freeze the compiler's output of
the day it was written, and the thing under test is whether the IR reads what
the compiler actually emits today. No `bin/` code was needed to do it, so
nothing moved into `src/`.
"""

from __future__ import annotations

import ast
import copy
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import (
    REPO_ROOT,
    api_surface,
    capability_compiler,
    capability_manifest,
    client_ir,
    compatibility,
    config,
    openapi_normalize,
    scope_registry,
    service_source,
)

# `GEN-IR-001` and `GEN-VERSION-001`: every proof here reads committed
# files and needs no daemon.
#
# **Marked, and the marks are load-bearing** (D1240). Without them no
# marker-selected sweep collects this module at all -- not the Session 1
# gate's `contract and not future`, not CI's `p0 and not future and not
# live_host and not external` -- so every proof here passes only when
# somebody names the file. The registry's node ids stayed COLLECTIBLE the
# whole time, which is exactly why `test_acceptance_registry` could not
# see it: collectible and collected are different questions.
pytestmark = [pytest.mark.contract, pytest.mark.p0]

APP_SNAPSHOT = REPO_ROOT / "contracts" / "app-openapi.canonical.json"
RELEASE_SNAPSHOT = REPO_ROOT / "contracts" / "postgrest-openapi.canonical.json"
CANONICAL_MCP = REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
PROJECT_MANIFEST = REPO_ROOT / "project.example.yaml"
TEMPLATE_VERSION = "1.4.0"


# ---------------------------------------------------------------------------
# the four inputs, assembled the way the product assembles them
# ---------------------------------------------------------------------------


def _compile_lock(project_manifest: Path | None) -> tuple[dict[str, Any], Any]:
    """The lock, by `command_lock`'s own sequence (ADR 0201, D1147)."""
    canonical = json.loads(CANONICAL_MCP.read_text(encoding="utf-8"))
    surface = None
    sources: dict[str, str] = {}
    inputs = None

    if project_manifest is not None:
        inputs = capability_manifest.project_inputs(config.load_project_manifest(project_manifest))
    if inputs is not None:
        capabilities = config.load_capabilities_manifest(REPO_ROOT / "capabilities.example.yaml")
        canonical = capability_manifest.compile_joint_contract(capabilities, inputs)
        surface = inputs.surface
        sources = {
            "project_capabilities_sha256": sha256(
                capability_manifest.project_capabilities_path(inputs.root).read_bytes()
            ).hexdigest(),
            "project_contract_sha256": sha256(
                capability_manifest.project_contract_path(inputs.root).read_bytes()
            ).hexdigest(),
        }

    lock = capability_compiler.compile_lock(
        canonical=canonical,
        project_key="fixture-alpha-dev",
        # Deliberately unreachable: the IR must carry no address it could call,
        # and a rig that pointed at a real host would make this suite's result
        # depend on one.
        upstream="https://example.invalid/api/rest",
        sources={
            "capabilities_sha256": "0" * 64,
            "api_surface_sha256": api_surface.contract_digest(),
            "canonical_openapi_sha256": "0" * 64,
            "project_manifest_sha256": "0" * 64,
            **sources,
        },
        profile=None,
        vocabulary=scope_registry.vocabulary_block(surface),
    )
    return lock, inputs


@pytest.fixture(scope="module")
def release_ir() -> client_ir.IR:
    """The client a project declaring NO set would be generated with."""
    lock, _ = _compile_lock(None)
    return client_ir.build(
        surface=api_surface.load_surface(),
        snapshot=json.loads(RELEASE_SNAPSHOT.read_text(encoding="utf-8")),
        app_snapshot=json.loads(APP_SNAPSHOT.read_text(encoding="utf-8")),
        lock=lock,
        project_root=None,
        pt_sources=client_ir.project_pt_sources(None),
        app_snapshot_bytes=APP_SNAPSHOT.read_bytes(),
        template_version=TEMPLATE_VERSION,
    )


@pytest.fixture(scope="module")
def project_ir() -> client_ir.IR:
    """The example project's client: a set, a tenant relation, a seventh tool."""
    lock, inputs = _compile_lock(PROJECT_MANIFEST)
    assert inputs is not None, "the example project declares capabilities; this fixture needs them"
    return client_ir.build(
        surface=inputs.surface,
        snapshot=json.loads(
            api_surface.project_snapshot_path(inputs.root).read_text(encoding="utf-8")
        ),
        app_snapshot=json.loads(APP_SNAPSHOT.read_text(encoding="utf-8")),
        lock=lock,
        project_root=str(inputs.root.relative_to(REPO_ROOT)),
        pt_sources=client_ir.project_pt_sources(inputs.root),
        app_snapshot_bytes=APP_SNAPSHOT.read_bytes(),
        template_version=TEMPLATE_VERSION,
    )


@pytest.fixture(scope="module")
def project_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """The example project's surface, snapshot and lock, for the refusal arms."""
    lock, inputs = _compile_lock(PROJECT_MANIFEST)
    snapshot = json.loads(
        api_surface.project_snapshot_path(inputs.root).read_text(encoding="utf-8")
    )
    return inputs.surface, snapshot, lock


def _build(surface: dict[str, Any], snapshot: dict[str, Any], lock: dict[str, Any]) -> client_ir.IR:
    return client_ir.build(
        surface=surface,
        snapshot=snapshot,
        app_snapshot=json.loads(APP_SNAPSHOT.read_text(encoding="utf-8")),
        lock=lock,
        project_root="projects/example",
        pt_sources=client_ir.project_pt_sources(REPO_ROOT / "projects" / "example"),
        app_snapshot_bytes=APP_SNAPSHOT.read_bytes(),
        template_version=TEMPLATE_VERSION,
    )


# ---------------------------------------------------------------------------
# GEN-IR-001
# ---------------------------------------------------------------------------


def test_the_ir_is_built_from_the_four_inputs_and_nothing_else() -> None:
    """**GEN-IR-001.** The module is pure, and it is proved by AST, not by hope.

    Three properties, each of which has been a defect somewhere in this tree:
    no import of a service or a command (`src/` may not import either -- ADR
    0084, ADR 0093), no subprocess or network, and no path literal reaching
    outside the artefacts the four inputs name. A generator that quietly read
    the deployed document would be the stage plan's own stop condition, and it
    would look exactly like a generator that did not.
    """
    source = (REPO_ROOT / "src" / "agentic_postgres" / "client_ir.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert "app" not in imported, "the IR may not import the service's modules (ADR 0084)"
    for forbidden in ("subprocess", "socket", "urllib", "http", "requests", "os"):
        assert forbidden not in imported, (
            f"client_ir imports {forbidden!r}; the IR is pure -- files in, a dataclass out -- "
            "and every proof of it is an offline one (ADR 0202)"
        )

    # No literal naming an artefact outside the four inputs. `outputs.json` is
    # the one that matters: reading the deployed document is ADR 0158's refusal
    # and this session's named stop condition.
    for literal in ("outputs.json", "/etc/agentic-postgres", ".generated", "host.yaml"):
        assert literal not in source, f"client_ir names {literal!r}, which is not one of its inputs"


def test_relations_carry_the_surfaces_columns_and_the_snapshots_types(
    project_ir: client_ir.IR,
) -> None:
    """**GEN-IR-001.** Columns in the REVIEWED order, types from the capture.

    The surface's order and not the snapshot's, because the canonical form
    sorts every key: a generated interface whose field order came from a sort
    would reorder itself the first time a column was renamed, and the diff a
    reviewer reads would be noise.
    """
    surface = api_surface.merged_surface(
        api_surface.load_surface(),
        api_surface.load_project_surface(
            api_surface.project_contract_path(REPO_ROOT / "projects" / "example")
        ),
    )
    relations = {relation.name: relation for relation in project_ir.relations}
    assert set(relations) == set(surface["relations"])

    for name, entry in surface["relations"].items():
        assert [column.name for column in relations[name].columns] == list(entry["columns"]), (
            f"{name}'s columns are not the surface's, in the surface's order"
        )

    # The types come from the snapshot, and the three interesting ones are the
    # three spellings D1216 found in one document.
    notes = {column.name: column for column in relations["notes"].columns}
    assert notes["id"].format == "uuid" and notes["id"].ts_type == "string"
    assert notes["created_at"].format == "timestamp with time zone"
    assert notes["created_at"].ts_type == "string"

    status = {column.name: column for column in relations["tasks"].columns}["status"]
    assert status.format == "api.task_status", "an enum COLUMN is served schema-qualified"
    assert status.ts_type == '"pending" | "in_progress" | "completed" | "cancelled"', (
        "an enum column is a string-literal union in the surface's reviewed order, not `string`"
    )

    embedding = {column.name: column for column in relations["note_embeddings"].columns}[
        "embedding"
    ]
    assert embedding.format == "extensions.vector(768)", "a vector COLUMN carries its dimension"
    assert embedding.ts_type == "string", "the modifier is stripped before the table is consulted"


def test_rpcs_carry_the_snapshots_argument_schema_in_parameter_order(
    project_ir: client_ir.IR,
) -> None:
    """**GEN-IR-001.** Arguments in the reviewed order, typed and marked required.

    PostgREST resolves a function by the argument names supplied and a missing
    one is a `404 PGRST202` (ADR 0139), so both the names and their required-ness
    are part of the call and neither may be guessed.
    """
    rpcs = {rpc.name: rpc for rpc in project_ir.rpcs}
    assert set(rpcs) >= {"create_note", "create_task", "update_task_status", "set_note_embedding"}

    create = rpcs["create_note"]
    assert create.path == "/rpc/create_note"
    assert [argument.name for argument in create.arguments] == ["p_title", "p_content"]
    assert [argument.required for argument in create.arguments] == [True, False], (
        "the snapshot's body marks p_title required and p_content not; a client that "
        "required both would refuse a call the product accepts"
    )

    update = rpcs["update_task_status"]
    expected = {argument.name: argument for argument in update.arguments}["p_expected_status"]
    assert expected.format == "task_status", "an enum ARGUMENT is served BARE (D1216)"
    assert expected.ts_type == '"pending" | "in_progress" | "completed" | "cancelled"', (
        "the bare spelling must resolve to the same union the qualified one does, or the "
        "generated client disagrees with itself about one type"
    )

    embed = {argument.name: argument for argument in rpcs["set_note_embedding"].arguments}
    assert embed["p_embedding"].format == "extensions.vector", (
        "the same type is served WITHOUT its modifier as an argument"
    )
    assert embed["p_embedding"].ts_type == "string"


def test_the_lock_tools_carry_arguments_scopes_and_the_reserved_write_parameters(
    project_ir: client_ir.IR,
) -> None:
    """**GEN-IR-001.** Each tool's call shape is the RUNTIME's, per kind.

    Copied from `mcp_tools.register_*` rather than derived from the lock's
    shape: a client sending a parameter name the runtime does not declare
    generates a request the product cannot receive (ADR 0127).
    """
    tools = {tool.name: tool for tool in project_ir.tools}
    assert set(tools) == {
        "create_note",
        "describe_resource",
        "list_resources",
        "query_resource",
        "run_report",
        "set_note_embedding",
        "update_task_status",
    }, "the example project's joint lock serves seven tools (ADR 0201)"

    write = tools["create_note"]
    assert [argument.name for argument in write.arguments] == [
        "p_title",
        "p_content",
        "idempotency_key",
        "dry_run",
    ], "a write's parameters are the lock's arguments plus the two reserved ones, in order"
    assert all(argument.required for argument in write.arguments), (
        "`register_write` makes every one required -- PostgREST resolves by the names sent"
    )
    assert client_ir.RESERVED_WRITE_PARAMETERS == ("idempotency_key", "dry_run")

    relation_read = tools["query_resource"]
    assert [argument.name for argument in relation_read.arguments] == [
        "resource",
        "columns",
        "filters",
        "order_by",
        "limit",
    ]
    assert [argument.required for argument in relation_read.arguments] == [
        True,
        False,
        False,
        False,
        False,
    ], "only `resource` is required of a relation read"
    assert set(relation_read.resources) == {"notes", "tasks", "note_embeddings"}

    assert tools["run_report"].arguments == (), (
        "an rpc read takes NO caller input (`register_rpc_read`)"
    )
    assert tools["list_resources"].arguments == ()
    assert [argument.name for argument in tools["describe_resource"].arguments] == [
        "tool",
        "resource",
    ]

    # The scopes travel, because discovery is filtered by them and a client that
    # did not know which it needed could not tell a refusal from a bug.
    assert ("notes:write",) in tools["create_note"].discovery_scope_sets
    assert ("note_embeddings:read",) in relation_read.discovery_scope_sets


def test_the_three_authentication_operations_are_read_from_the_app_snapshot(
    release_ir: client_ir.IR,
) -> None:
    """**GEN-IR-001.** Three, and only three (D1209).

    The admin and storage halves are not wrapped: a client holds no
    administrative credential, so generating `/admin/*` calls would generate
    calls whose refusal is the point.
    """
    auth = {operation.name: operation for operation in release_ir.auth}
    assert sorted(auth) == ["login", "me", "refresh"]
    assert auth["login"].method == "POST" and auth["login"].path == "/auth/login"
    assert {argument.name for argument in auth["login"].request} == {"username", "password"}
    assert auth["me"].method == "GET" and auth["me"].request == ()
    assert auth["refresh"].request[0].name == "refresh_token"

    emitted = json.dumps(client_ir.to_document(release_ir))
    for forbidden in ("/admin/", "/storage/"):
        assert forbidden not in emitted, (
            f"the IR carries {forbidden!r}; a client wraps three auth operations and no "
            "administrative or storage path (D1209)"
        )


def test_a_snapshot_object_the_surface_does_not_name_is_refused_and_vice_versa(
    project_inputs: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    """**GEN-IR-001.** Both directions, and the control is the unmodified pair.

    The comparison `bin/api-contract.py::compare_snapshot_to_surface` makes,
    made again over the same two functions because `src/` may not import
    `bin/`. A generator that skipped it would emit calls nobody reviewed, or
    emit against a capture that predates the surface.
    """
    surface, snapshot, lock = project_inputs

    # The control: as committed, the pair agrees and the IR builds.
    assert _build(surface, snapshot, lock).relations, "the unmodified pair must build"

    published = copy.deepcopy(snapshot)
    published["paths"]["/rpc/unreviewed_probe"] = copy.deepcopy(
        snapshot["paths"]["/rpc/create_note"]
    )
    with pytest.raises(client_ir.ClientIrError, match="rpc/unreviewed_probe"):
        _build(surface, published, lock)

    reviewed = copy.deepcopy(surface)
    reviewed["rpcs"]["unpublished_probe"] = {"methods": ["POST"], "arguments": ["p_x"]}
    with pytest.raises(client_ir.ClientIrError, match="unpublished_probe"):
        _build(reviewed, snapshot, lock)


def test_an_unknown_column_format_is_refused_and_never_typed_any(
    project_inputs: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    """**GEN-IR-001.** A format nobody decided about is not silently `any`.

    The failure this prevents cannot be noticed downstream: the client compiles,
    the developer gets no type, and the first thing they learn about the column
    is whatever the runtime hands them. `required_level`'s rule -- an
    unclassified change raises rather than defaulting to the permissive answer
    -- one layer down.
    """
    surface, snapshot, lock = project_inputs

    mutated = copy.deepcopy(snapshot)
    mutated["definitions"]["notes"]["properties"]["title"]["format"] = "tsvector"
    with pytest.raises(client_ir.ClientIrError, match="tsvector"):
        _build(surface, mutated, lock)

    # The control: the same column at a format the table DOES name builds.
    allowed = copy.deepcopy(snapshot)
    allowed["definitions"]["notes"]["properties"]["title"]["format"] = "character varying(80)"
    built = _build(surface, allowed, lock)
    title = {
        column.name: column
        for relation in built.relations
        if relation.name == "notes"
        for column in relation.columns
    }["title"]
    assert title.ts_type == "string", "a parameterised format resolves through its base type"


def test_the_pt_codes_are_scanned_from_the_release_and_the_set(
    release_ir: client_ir.IR, project_ir: client_ir.IR, tmp_path: Path
) -> None:
    """**GEN-IR-001.** A project's own codes reach its own client's error union.

    A generator scanning only the release would emit a union missing exactly the
    codes a tenant's functions raise, and the client would report the tenant's
    refusals as unrecognised -- the worst direction, because the caller reads it
    as a client bug.

    **The synthetic second directory is the whole proof** (D1221). The example
    project's own migrations raise no code the release does not, so asserting
    over the committed tree alone cannot tell a generator that scans both
    sources from one that scans only the first -- the battery's `sources[:1]`
    mutation SURVIVED against exactly that assertion. A directory carrying a
    code the release never raises is the only arm that can fail.
    """
    expected = {"PT401", "PT403", "PT404", "PT409", "PT412", "PT422"}
    assert set(release_ir.pt_codes) == expected
    assert set(project_ir.pt_codes) >= expected

    # Scanned, not listed: a code added to a template appears without this
    # module being edited.
    grep = set()
    for path in (REPO_ROOT / "migrations" / "templates").glob("*.sql"):
        grep.update(client_ir.PT_CODE_PATTERN.findall(path.read_text(encoding="utf-8")))
    assert set(release_ir.pt_codes) == grep

    # The arm that can fail: a SECOND source raising a code the release does not.
    tenant = tmp_path / "migrations"
    tenant.mkdir()
    (tenant / "20260101000001_tenant.sql").write_text(
        "-- migrate:up\nRAISE EXCEPTION 'tenant refusal' USING ERRCODE = 'PT499';\n",
        encoding="utf-8",
    )
    both = client_ir._pt_codes((REPO_ROOT / "migrations" / "templates", tenant))
    assert "PT499" in both, (
        "a code raised only by the project's own set did not reach the union, so a "
        "generator scanning the release alone would be indistinguishable from this one"
    )
    assert set(both) == expected | {"PT499"}
    assert "PT499" not in release_ir.pt_codes, "the release must not already raise the probe code"

    with pytest.raises(client_ir.ClientIrError, match="not a directory"):
        client_ir._pt_codes((REPO_ROOT / "migrations" / "there-is-no-such-directory",))


def test_every_format_the_committed_snapshots_serve_has_a_typescript_type() -> None:
    """**GEN-IR-001.** The format table covers the tree, asserted directly.

    **Separate from the relation proof, and built without the module fixtures,
    for a measured reason** (D1221). Removing `uuid` from `FORMAT_TYPES` makes
    `build` raise inside a module-scoped fixture, so every test in the module
    reports ERROR -- and an ERROR never reached an assertion, which makes it a
    broken fixture rather than a kill (D386). A reader that counted it as a kill
    would be reporting a false one. This test touches the table and the
    committed documents only, so the same mutation fails HERE, as an assertion.
    """
    served: dict[str, str] = {}
    for path in (
        RELEASE_SNAPSHOT,
        REPO_ROOT / "projects" / "example" / "contracts" / "postgrest-openapi.canonical.json",
    ):
        document = json.loads(path.read_text(encoding="utf-8"))
        for relation, definition in (document.get("definitions") or {}).items():
            for column, spec in (definition.get("properties") or {}).items():
                if "format" in spec:
                    served[spec["format"]] = f"{relation}.{column}"
        for route, entry in (document.get("paths") or {}).items():
            body = next(
                (
                    parameter
                    for parameter in (entry.get("post") or {}).get("parameters", [])
                    if isinstance(parameter, dict) and parameter.get("in") == "body"
                ),
                None,
            )
            for argument, spec in ((body or {}).get("schema") or {}).get("properties", {}).items():
                if "format" in spec:
                    served[spec["format"]] = f"{route}.{argument}"

    assert served, "no formats were read; this proof would pass over an empty tree"

    enums = set(api_surface.load_surface()["enums"])
    unmapped = []
    for format_name, where in sorted(served.items()):
        bare = client_ir._FORMAT_MODIFIER.sub("", format_name).strip()
        if bare in client_ir.FORMAT_TYPES:
            continue
        if bare in enums or bare.split(".")[-1] in enums:
            continue
        unmapped.append(f"{format_name} ({where})")
    assert not unmapped, (
        f"the committed snapshots serve formats with no TypeScript type: {unmapped}. "
        "Every one must be in client_ir.FORMAT_TYPES or a reviewed enum"
    )

    # The four the example domain actually depends on, named so that deleting
    # any ONE of them fails here rather than erroring in a fixture.
    for required in ("uuid", "text", "timestamp with time zone", "extensions.vector"):
        assert required in client_ir.FORMAT_TYPES, f"{required} is served by this tree"


#: What PostgREST serves as the `format` of a type, as a COLUMN and as an RPC
#: ARGUMENT: `(declared SQL type, column spelling, argument spelling)`.
#:
#: **Measured, not reasoned** (rig 27b, Session 27 Run 2, D1390). The rig reused
#: `test_generated_client_runtime`'s `served` fixture whole -- a dev cluster
#: built from the render and the release, PostgREST configured from
#: `compose.yaml`'s own environment -- and added one superuser statement: a
#: table with a column of every type below and a function taking an argument of
#: each. Its control was D1216's, that a `vector` column comes back
#: `extensions.vector(768)` and the same type as an argument comes back bare.
#:
#: The rig itself is not committed, for `test_generated_client_runtime`'s own
#: reason: it needs Docker, a cluster and ~40 seconds, and this table is the
#: part of it worth keeping. What the rig answered once, this table asserts on
#: every run.
RIG_27B_SERVED: tuple[tuple[str, str, str], ...] = (
    ("uuid", "uuid", "uuid"),
    ("text", "text", "text"),
    ("character varying(64)", "character varying", "character varying"),
    ("character(4)", "character", "character"),
    ("name", "name", "name"),
    ("timestamp with time zone", "timestamp with time zone", "timestamp with time zone"),
    (
        "timestamp without time zone",
        "timestamp without time zone",
        "timestamp without time zone",
    ),
    ("date", "date", "date"),
    ("time with time zone", "time with time zone", "time with time zone"),
    ("time without time zone", "time without time zone", "time without time zone"),
    ("interval", "interval", "interval"),
    ("extensions.vector(768)", "extensions.vector(768)", "extensions.vector"),
    ("integer", "int32", "int32"),
    ("bigint", "int64", "int64"),
    ("smallint", "int32", "int32"),
    ("real", "real", "real"),
    ("double precision", "double precision", "double precision"),
    ("numeric", "numeric", "numeric"),
    ("boolean", "boolean", "boolean"),
    ("json", "json", "json"),
    ("jsonb", "jsonb", "jsonb"),
    ("text[]", "text[]", "text[]"),
    ("integer[]", "integer[]", "integer[]"),
    ("uuid[]", "uuid[]", "uuid[]"),
    ("double precision[]", "double precision[]", "double precision[]"),
    ("boolean[]", "boolean[]", "boolean[]"),
    ("jsonb[]", "jsonb[]", "jsonb[]"),
    ("numeric[]", "numeric[]", "numeric[]"),
    ("tsvector", "tsvector", "tsvector"),
    ("character varying(64)[]", "character varying[]", "character varying[]"),
    ("character(4)[]", "character[]", "character[]"),
    ("name[]", "name[]", "name[]"),
    ("timestamp with time zone[]", "timestamp with time zone[]", "timestamp with time zone[]"),
    (
        "timestamp without time zone[]",
        "timestamp without time zone[]",
        "timestamp without time zone[]",
    ),
    ("date[]", "date[]", "date[]"),
    ("time with time zone[]", "time with time zone[]", "time with time zone[]"),
    ("time without time zone[]", "time without time zone[]", "time without time zone[]"),
    ("interval[]", "interval[]", "interval[]"),
    ("extensions.vector(768)[]", "extensions.vector(768)[]", "extensions.vector[]"),
    ("bigint[]", "bigint[]", "bigint[]"),
    ("smallint[]", "smallint[]", "smallint[]"),
    ("real[]", "real[]", "real[]"),
    ("json[]", "json[]", "json[]"),
    ("tsvector[]", "tsvector[]", "tsvector[]"),
)

#: The two spellings the table must NOT carry. `tsvector` is the control in
#: `test_an_unknown_column_format_is_refused_and_never_typed_any`: if widening
#: the table for D1390 had reached it, that proof would still pass -- against a
#: format the generator now types -- and the property ADR 0204 exists for would
#: be gone with nothing red. Named here so the widening cannot swallow it.
UNSERVED_ON_PURPOSE: frozenset[str] = frozenset({"tsvector", "tsvector[]"})


def test_every_spelling_postgrest_serves_has_a_typescript_type() -> None:
    """**GEN-IR-001**, and the half the committed snapshots cannot reach.

    `test_every_format_the_committed_snapshots_serve_has_a_typescript_type`
    asks whether the table covers the tree. It passed for three sessions while
    the table could not type an `integer`, because the tree's two snapshots
    between them serve five formats and an enum -- seventeen of the table's
    twenty-one entries had never matched a served format in this repository's
    history (D1390). This asks the other question: whether the table covers
    what PostgREST SERVES, measured over every type at once.

    Three assertions, and the third is the one D1390 is about: a type's column
    spelling and its argument spelling must reach the SAME TypeScript type. The
    old table typed an `integer` column and an `integer` argument differently
    -- one resolved and one refused -- which is a client disagreeing with
    itself about one type.
    """
    assert RIG_27B_SERVED, "the measurement is empty; this proof would pass over nothing"

    def resolved(spelling: str) -> str | None:
        bare = client_ir._FORMAT_MODIFIER.sub("", spelling).strip()
        return client_ir.FORMAT_TYPES.get(bare)

    unmapped: list[str] = []
    disagreeing: list[str] = []
    for declared, column, argument in RIG_27B_SERVED:
        if declared in UNSERVED_ON_PURPOSE:
            continue
        for role, spelling in (("column", column), ("argument", argument)):
            if resolved(spelling) is None:
                unmapped.append(f"{declared} as a {role} is served {spelling!r}")
        if resolved(column) is not None and resolved(column) != resolved(argument):
            disagreeing.append(
                f"{declared}: column {column!r} -> {resolved(column)}, "
                f"argument {argument!r} -> {resolved(argument)}"
            )

    assert not unmapped, (
        "PostgREST serves spellings client_ir.FORMAT_TYPES has no entry for, so "
        f"`apg generate` and `apg studio` both refuse a surface using them: {unmapped}"
    )
    assert not disagreeing, (
        "a type's two spellings reach different TypeScript types, so a generated "
        f"client disagrees with itself about one column: {disagreeing}"
    )

    #: The control, stated rather than implied: the widening did not reach the
    #: format the refusal proof relies on being unknown.
    for control in sorted(UNSERVED_ON_PURPOSE):
        bare = client_ir._FORMAT_MODIFIER.sub("", control).strip()
        assert bare not in client_ir.FORMAT_TYPES, (
            f"{control} is the control in the refusal proof and must have no "
            "TypeScript type; adding one makes that proof pass over a format "
            "this generator now accepts, which is ADR 0204's property with "
            "nothing left holding it"
        )

    #: And the three the old table carried that PostgREST serves for nothing,
    #: kept deliberately: `integer` and `numeric` are reached from the
    #: APPLICATION snapshot through `_openapi_type`, `smallint` and `bigint` by
    #: neither document. Asserted so that a later tidy-up that deletes them
    #: reads this sentence first.
    assert client_ir._openapi_type({"type": "integer"}) == "integer"
    assert client_ir._openapi_type({"type": "number"}) == "numeric"
    for sql_only in ("integer", "numeric", "smallint", "bigint"):
        assert sql_only in client_ir.FORMAT_TYPES


def test_the_caller_facing_tokens_match_the_runtimes() -> None:
    """**GEN-IR-001**, and D486's arrangement.

    Two copies of a fact with a test between them are one fact. `src/` may not
    import `services/` (ADR 0084), so the seven tokens are written twice -- and
    a client whose refusal union drifted from the runtime's vocabulary would
    report a real refusal as an unknown one.
    """
    mcp_errors = service_source.load("mcp_errors")
    assert client_ir.CALLER_FACING_TOKENS == tuple(mcp_errors.CALLER_FACING_TOKENS), (
        "the IR's token list and the runtime's have drifted; they are the same fact"
    )
    assert len(client_ir.CALLER_FACING_TOKENS) == 7


def test_the_reserved_write_parameters_match_the_harnesss() -> None:
    """D486 again, for the two parameters every write tool adds."""
    from agentic_postgres import evaluation_harness

    assert client_ir.RESERVED_WRITE_PARAMETERS == evaluation_harness.RESERVED_WRITE_PARAMETERS


def test_two_builds_are_equal(project_inputs: Any) -> None:
    """**GEN-IR-001.** Deterministic, and the document round-trips.

    Determinism is what lets `--check` mean anything: a generator whose output
    depended on dict ordering would report drift on every run, and the check
    would be turned off within a week.
    """
    surface, snapshot, lock = project_inputs
    first = _build(surface, snapshot, lock)
    second = _build(surface, snapshot, lock)

    assert first == second
    assert client_ir.to_document(first) == client_ir.to_document(second)
    assert client_ir.from_document(client_ir.to_document(first)) == first

    with pytest.raises(client_ir.ClientIrError):
        client_ir.from_document({"rest_contract_id": "x"})


def test_the_ir_carries_four_digests_and_the_rest_one_is_the_snapshots_fingerprint(
    project_ir: client_ir.IR, project_inputs: Any
) -> None:
    """**GEN-IR-001.** The digest `init()` compares is the capture's fingerprint.

    This is the join between the generator and rig 23a: the value embedded here
    is what an `authenticated` caller's own read of `GET /` normalizes to, which
    is why strict equality is the right relation at runtime.

    `merged_surface_sha256` is deliberately NOT the name the deployed document
    uses for a surface digest (D1217): that one means the release file's bytes,
    and this one covers the merged document.
    """
    surface, snapshot, lock = project_inputs

    assert project_ir.digests.rest_openapi_sha256 == openapi_normalize.fingerprint(snapshot)
    assert project_ir.digests.rest_openapi_sha256 == (
        "808ac715c09aeebc382dd5afc886c1680fe2ea9870e729b9d34a623dee8d18de"
    ), "the value rig 23a measured the authenticated role being served"
    assert project_ir.digests.tools_sha256 == lock["tools_sha256"]
    assert project_ir.digests.app_openapi_sha256 == sha256(APP_SNAPSHOT.read_bytes()).hexdigest()
    assert project_ir.digests.merged_surface_sha256 != api_surface.contract_digest(), (
        "the merged surface's digest is not the release file's, and the two names differ "
        "so that nobody reads one for the other"
    )

    # A lock with no signature cannot produce a client, because the client's
    # live check against the plane would have nothing to compare.
    unsigned = copy.deepcopy(lock)
    del unsigned["tools_sha256"]
    with pytest.raises(client_ir.ClientIrError, match="tools_sha256"):
        _build(surface, snapshot, unsigned)


# ---------------------------------------------------------------------------
# GEN-VERSION-001
# ---------------------------------------------------------------------------


def test_classify_changes_returns_only_compatibilitys_own_classes(
    release_ir: client_ir.IR, project_ir: client_ir.IR
) -> None:
    """**GEN-VERSION-001.** ADR 0162's vocabulary, never a second scheme.

    Every name returned is one `compatibility.CHANGE_CLASSES` defines, and one
    the upgrade planner can actually REACH -- which is a union of two sets and
    not one (D1220). `bin/upgrade.py::DECLARABLE` carries eight classes, the
    ones *"no pair of rendered documents can establish"*; `capability_added` is
    deliberately **not** among them because `upgrade_plan.classify_document_changes`
    computes it itself, from a `capabilities.*` addition in the rendered
    document. Asserting against `DECLARABLE` alone therefore failed on the
    generator's most ordinary output, and the repair is to assert the union --
    the honest statement of the agreement.
    """
    upgrade_source = (REPO_ROOT / "bin" / "upgrade.py").read_text(encoding="utf-8")
    upgrade = ast.parse(upgrade_source)
    declarable: set[str] = set()
    for node in ast.walk(upgrade):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "DECLARABLE" for target in node.targets
        ):
            declarable = {
                element.value
                for element in ast.walk(node.value)
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }
    assert declarable, "bin/upgrade.py no longer assigns DECLARABLE; this proof reads it by name"

    planner = ast.parse(
        (REPO_ROOT / "src" / "agentic_postgres" / "upgrade_plan.py").read_text(encoding="utf-8")
    )
    computed = {
        node.value
        for node in ast.walk(planner)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value in compatibility.CHANGE_CLASSES
    }
    reachable = declarable | computed
    assert "capability_added" in computed, (
        "the planner used to compute capability_added from the rendered documents; if it "
        "no longer does, the generator's class has no reader and D1220 needs re-reading"
    )

    for previous, current in (
        (release_ir, project_ir),
        (project_ir, release_ir),
        (release_ir, release_ir),
    ):
        for name in client_ir.classify_changes(previous, current):
            assert name in compatibility.CHANGE_CLASSES, f"{name} is not a change class"
            assert name in reachable, (
                f"{name} is a class the upgrade planner can neither be told (--also) nor "
                "compute, so the generator would report a class nothing acts on"
            )


def test_an_added_relation_or_tool_is_minor_and_a_removed_one_is_major(
    release_ir: client_ir.IR, project_ir: client_ir.IR
) -> None:
    """**GEN-VERSION-001.** The direction decides, and the tenant case is MINOR.

    Stage 3's premise is that a project adding a table is additive. Comparing
    `Relation` and `Tool` by dataclass equality made exactly that case MAJOR
    (D1219), because `query_resource` gained a resource and an alternative
    discovery scope set -- neither of which takes anything from an existing
    caller. The reverse direction is the control: removing them is major.
    """
    forward = client_ir.classify_changes(release_ir, project_ir)
    assert set(forward) == {"api_operation_added", "capability_added"}
    assert compatibility.required_level(list(forward)) == compatibility.MINOR, (
        "adding a tenant relation and its tool is a MINOR move, or Stage 3's extension "
        "point costs a major on every table"
    )

    backward = client_ir.classify_changes(project_ir, release_ir)
    assert "api_operation_removed" in backward
    assert compatibility.required_level(list(backward)) == compatibility.MAJOR

    assert client_ir.classify_changes(release_ir, release_ir) == ()
    assert compatibility.required_level([]) == compatibility.PATCH


def test_a_retyped_column_or_a_moved_argument_list_is_major(project_inputs: Any) -> None:
    """**GEN-VERSION-001.** A change that is not an addition is `..._changed`.

    Rig 23d's planted pair in miniature, built here rather than read from
    `/tmp` so the proof survives the machine it was measured on.
    """
    surface, snapshot, lock = project_inputs
    base = _build(surface, snapshot, lock)

    retyped = copy.deepcopy(snapshot)
    retyped["definitions"]["notes"]["properties"]["title"]["format"] = "integer"
    assert "api_operation_changed" in client_ir.classify_changes(
        base, _build(surface, retyped, lock)
    )

    # A planted RPC: the addition arm, over the same pair (rig 23d's fixture).
    planted_snapshot = copy.deepcopy(snapshot)
    probe = copy.deepcopy(snapshot["paths"]["/rpc/create_note"])
    probe["post"]["parameters"] = [
        parameter for parameter in probe["post"]["parameters"] if parameter.get("in") != "body"
    ] + [
        {
            "in": "body",
            "name": "args",
            "required": False,
            "schema": {
                "properties": {"p_x": {"format": "text", "type": "string"}},
                "type": "object",
            },
        }
    ]
    planted_snapshot["paths"]["/rpc/rpc_probe"] = probe
    planted_surface = copy.deepcopy(surface)
    planted_surface["rpcs"]["rpc_probe"] = {"methods": ["POST"], "arguments": ["p_x"]}

    planted = _build(planted_surface, planted_snapshot, lock)
    assert openapi_normalize.fingerprint(planted_snapshot) != openapi_normalize.fingerprint(
        snapshot
    ), "the planted snapshot must actually differ, or this proves nothing"
    changes = client_ir.classify_changes(base, planted)
    assert "api_operation_added" in changes
    assert compatibility.required_level(list(changes)) == compatibility.MINOR


def test_next_version_bumps_the_artefacts_own_number() -> None:
    """**GEN-VERSION-001.** `1.0.0` first, and the lower components reset."""
    assert client_ir.next_version(None, compatibility.MINOR) == "1.0.0"
    assert client_ir.next_version("1.0.0", compatibility.PATCH) == "1.0.1"
    assert client_ir.next_version("1.2.3", compatibility.MINOR) == "1.3.0"
    assert client_ir.next_version("1.2.3", compatibility.MAJOR) == "2.0.0"

    with pytest.raises(client_ir.ClientIrError, match="not one of"):
        client_ir.next_version("1.0.0", "enormous")
    with pytest.raises(compatibility.CompatibilityError):
        client_ir.next_version("not-a-version", compatibility.PATCH)


# ---------------------------------------------------------------------------
# GEN-TOOLCHAIN-001 -- the half that needs no image
# ---------------------------------------------------------------------------


def test_js_reproducible_refuses_a_float_and_a_big_integer_and_accepts_every_rest_snapshot() -> (
    None
):
    """**GEN-TOOLCHAIN-001.** The precondition for a second canonical form.

    Rig 23b measured it by comparing bytes: `JSON.stringify(sortKeysDeep, null,
    2)` reproduces `canonical_bytes` for four of the five committed contracts
    and differs for `app-openapi.canonical.json` on exactly two lines -- `1.0`
    and `0.0`, printed by JavaScript as `1` and `0`.

    This function is the Python side of that fact, and the assertion below is
    the join: it must find the app document's offender and clear every REST and
    MCP snapshot. Finding the SAME value the byte comparison found is what makes
    it a check rather than a restatement.
    """
    for path in (
        RELEASE_SNAPSHOT,
        REPO_ROOT / "projects" / "example" / "contracts" / "postgrest-openapi.canonical.json",
        CANONICAL_MCP,
        REPO_ROOT / "projects" / "example" / "contracts" / "mcp-capabilities.canonical.json",
    ):
        if not path.is_file():
            pytest.fail(f"{path} is missing; the comparison needs every committed contract")
        assert client_ir.js_reproducible(json.loads(path.read_text(encoding="utf-8"))) is None, (
            f"{path.name} holds a value JavaScript would serialize differently, so a "
            "generated client could not reproduce its fingerprint"
        )

    app = json.loads(APP_SNAPSHOT.read_text(encoding="utf-8"))
    offender = client_ir.js_reproducible(app)
    assert offender is not None, (
        "app-openapi carries two Pydantic floats (rig 23b, D1203); a walker that cleared "
        "it would be a walker that cannot fail"
    )
    assert "secret_ttl_seconds" in offender, (
        f"the offender moved: {offender}. Re-read rig 23b before trusting this boundary"
    )

    assert client_ir.js_reproducible({"a": 1.0}) == "/a"
    assert client_ir.js_reproducible({"a": 2**53 + 1}) == "/a"
    assert client_ir.js_reproducible({"a": True}) is None, (
        "isinstance(True, int) is true in Python; reporting every boolean would make this "
        "function useless at the moment somebody needed to trust it"
    )
    assert client_ir.js_reproducible({"a": 1, "b": "x", "c": [1, 2]}) is None
    assert client_ir.js_reproducible({"nested": {"deep": [{"x": 0.5}]}}) == "/nested/deep/0/x"


def test_the_build_refuses_a_snapshot_javascript_cannot_reproduce(project_inputs: Any) -> None:
    """**GEN-TOOLCHAIN-001.** The refusal, not merely the detector.

    A client generated from a document whose fingerprint its own canonical form
    cannot reproduce would refuse every correct deployment at `init()` -- and it
    would look like a stale contract, which is the one diagnosis that would send
    the operator to re-capture a snapshot that was already right.
    """
    surface, snapshot, lock = project_inputs
    mutated = copy.deepcopy(snapshot)
    mutated["definitions"]["notes"]["properties"]["title"]["maxLength"] = 80.0

    with pytest.raises(client_ir.ClientIrError, match="JavaScript serializes differently"):
        _build(surface, mutated, lock)

    # The control: the same document with the same value as an INT builds.
    allowed = copy.deepcopy(snapshot)
    allowed["definitions"]["notes"]["properties"]["title"]["maxLength"] = 80
    assert _build(surface, allowed, lock).relations
