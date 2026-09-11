"""The derived scope vocabulary, from the schema to the issuer (ADR 0200, Session 21 Run 2).

`test_scope_registry` proves the registry; this module proves the readers the
change touched, each one where it reads:

* the capability schema at version 4 admits a data scope by SHAPE and the
  compiler approves it against the reviewed surface (F-025's two runs as arms);
* a relation named for an enumerated resource is refused at load and at merge;
* the compiler writes the vocabulary into a lock at schema version 4, the agent
  plane's loader requires it there and forbids it below, and the issuer's
  loader reads the same block;
* the issuer's ceiling is a function of the vocabulary (two vocabularies, one
  role);
* the auth service mounts the lock;
* no data-scope literal survives in `src/`, `bin/` or `services/`.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import (
    REPO_ROOT,
    api_surface,
    capability_compiler,
    config,
    openapi_normalize,
    runtime_override,
    scope_registry,
    service_source,
)
from agentic_postgres.config import ManifestError

pytestmark = [pytest.mark.contract, pytest.mark.p0]

EXAMPLE = REPO_ROOT / "capabilities.example.yaml"
EXAMPLE_PROJECT = REPO_ROOT / "projects" / "example"
RELEASE_RELATIONS = {"notes", "tasks"}
DATA_LITERALS = ("notes:read", "notes:write", "tasks:read", "tasks:write")


def _mcp_contract() -> Any:
    spec = importlib.util.spec_from_file_location(
        "apg_mcp_contract", REPO_ROOT / "bin" / "mcp-contract.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def inputs() -> tuple[dict[str, Any], dict[str, Any], set[str]]:
    """The example manifest, the release surface and the release snapshot's objects."""
    return _mcp_contract()._inputs(EXAMPLE)


@pytest.fixture(scope="module")
def merged() -> tuple[dict[str, Any], set[str]]:
    """The merged example surface and the example project's snapshot objects."""
    project = api_surface.load_project_surface(api_surface.project_contract_path(EXAMPLE_PROJECT))
    surface = api_surface.merged_surface(api_surface.load_surface(), project)
    snapshot = json.loads(
        api_surface.project_snapshot_path(EXAMPLE_PROJECT).read_text(encoding="utf-8")
    )
    return surface, openapi_normalize.declared_objects(snapshot)


def _with_scopes(manifest: dict[str, Any], name: str, scopes: list[str]) -> dict[str, Any]:
    document = copy.deepcopy(manifest)
    for entry in document["capabilities"]:
        if entry["name"] == name:
            entry["required_scopes"] = scopes
            return document
    raise AssertionError(name)


def _tenant_read() -> dict[str, Any]:
    """A read over the example project's relation, the shape `apg agent init` will emit."""
    return {
        "name": "query_note_embeddings",
        "tool": "query_resource",
        "description": "The caller's own note embeddings.",
        "kind": "read",
        "version": "1.0.0",
        "lifecycle": "active",
        "risk": "low",
        "max_response_bytes": 65536,
        "max_concurrent_calls": 1,
        "enabled": True,
        "required_scopes": ["note_embeddings:read"],
        "operation": {"source": "postgrest", "operation_id": "note_embeddings.get"},
        "resource": "note_embeddings",
        "columns": ["note_id", "owner_id", "updated_at"],
        "filters": [],
        "order_by": [],
        "max_rows": 100,
        "timeout_ms": 5000,
        "audit": {"redact": []},
    }


# ---------------------------------------------------------------------------
# The schema: a shape at 4, the enum at 3 and below
# ---------------------------------------------------------------------------


def test_at_schema_4_a_scope_is_a_shape_and_at_3_it_is_the_enum(tmp_path: Path) -> None:
    """ADR 0177's gate, running the other way: version 4 widens what may be
    NAMED, and the versions below keep the vocabulary they were written against."""
    manifest = config.load_capabilities_manifest(EXAMPLE)
    assert manifest["schema_version"] == 4

    honest = _with_scopes(manifest, "query_notes", ["snippets:read"])
    path = tmp_path / "honest.yaml"
    path.write_text(yaml.safe_dump(honest, sort_keys=False), encoding="utf-8")
    loaded = config.load_capabilities_manifest(path)
    query_notes = next(e for e in loaded["capabilities"] if e["name"] == "query_notes")
    assert query_notes["required_scopes"] == ["snippets:read"], (
        "at version 4 the schema admits the shape; approval is the compiler's"
    )

    for malformed in ("admin:everything", "notes:delete", "*", "Snippets:read", "snippets:read:x"):
        bad = _with_scopes(manifest, "query_notes", [malformed])
        path.write_text(yaml.safe_dump(bad, sort_keys=False), encoding="utf-8")
        with pytest.raises(ManifestError):
            config.load_capabilities_manifest(path)

    older = copy.deepcopy(honest)
    older["schema_version"] = 3
    for entry in older["capabilities"]:
        entry.pop("nothing", None)
    path.write_text(yaml.safe_dump(older, sort_keys=False), encoding="utf-8")
    with pytest.raises(ManifestError, match="snippets:read"):
        config.load_capabilities_manifest(path)


# ---------------------------------------------------------------------------
# The compiler approves a name against the surface (F-025)
# ---------------------------------------------------------------------------


def test_a_scope_the_merged_surface_derives_is_accepted_and_one_it_does_not_is_refused(
    inputs: tuple[dict[str, Any], dict[str, Any], set[str]],
    merged: tuple[dict[str, Any], set[str]],
) -> None:
    """F-025's two runs, as the two arms.

    The adopter's honest scope over a relation the release does not publish was
    refused at schema validation; the borrowed release scope over their own
    table compiled to a contract the approved one did not match. At version 4
    the honest scope over a relation the MERGED surface publishes compiles, the
    same name over the release surface alone is refused by the compiler with
    the relations it does derive, and an administrative name is refused the
    same way -- the schema no longer enumerates, so the compiler is the gate.
    """
    manifest, release, release_objects = inputs
    merged_surface, merged_objects = merged

    tenant = copy.deepcopy(manifest)
    tenant["capabilities"].append(_tenant_read())
    canonical = capability_compiler.compile_canonical(
        capabilities=tenant, surface=merged_surface, published_objects=merged_objects
    )
    query = next(tool for tool in canonical["tools"] if tool["name"] == "query_resource")
    assert {resource["name"] for resource in query["resources"]} == {
        "notes",
        "tasks",
        "note_embeddings",
    }
    assert ["note_embeddings:read"] in query["discovery_scope_sets"]

    with pytest.raises(capability_compiler.CompilerError, match="does not derive") as refused:
        capability_compiler.compile_canonical(
            capabilities=tenant, surface=release, published_objects=release_objects
        )
    assert "note_embeddings:read" in str(refused.value)
    assert str(sorted(RELEASE_RELATIONS)) in str(refused.value)

    borrowed = _with_scopes(manifest, "query_notes", ["snippets:read"])
    with pytest.raises(capability_compiler.CompilerError, match="snippets:read"):
        capability_compiler.compile_canonical(
            capabilities=borrowed, surface=merged_surface, published_objects=merged_objects
        )

    administrative = _with_scopes(manifest, "query_notes", ["admin_users:read"])
    with pytest.raises(capability_compiler.CompilerError, match="admin_users:read"):
        capability_compiler.compile_canonical(
            capabilities=administrative, surface=release, published_objects=release_objects
        )

    # The control: the example manifest still compiles to the committed contract.
    committed = json.loads(_mcp_contract().CANONICAL_PATH.read_text(encoding="utf-8"))
    assert (
        capability_compiler.compile_canonical(
            capabilities=manifest, surface=release, published_objects=release_objects
        )
        == committed
    )


# ---------------------------------------------------------------------------
# A relation named for an enumerated resource is refused at load and at merge
# ---------------------------------------------------------------------------


def _project_surface(relation: str) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "contract_id": "rig-v1",
        "exposed_schema": "api",
        "relations": {relation: {"kind": "view", "methods": ["GET"], "columns": ["id"]}},
        "rpcs": {},
        "enums": {},
    }


def test_a_relation_named_for_an_enumerated_class_is_refused_at_load_and_at_merge(
    tmp_path: Path,
) -> None:
    assert api_surface.reserved_resource_names() == {
        "objects",
        "admin_users",
        "admin_agents",
        "admin_audit",
    }
    release = api_surface.load_surface()

    api_surface.validate_project_surface(_project_surface("widgets"))
    api_surface.merged_surface(release, _project_surface("widgets"))

    for reserved in sorted(api_surface.reserved_resource_names()):
        with pytest.raises(api_surface.SurfaceError, match=reserved):
            api_surface.validate_project_surface(_project_surface(reserved))
        with pytest.raises(api_surface.SurfaceError, match=reserved):
            api_surface.merged_surface(release, _project_surface(reserved))

    path = tmp_path / "postgrest-api-surface.yaml"
    path.write_text(yaml.safe_dump(_project_surface("objects")), encoding="utf-8")
    with pytest.raises(api_surface.SurfaceError, match="objects"):
        api_surface.load_project_surface(path)


# ---------------------------------------------------------------------------
# The lock carries the vocabulary at 4; both loaders read it
# ---------------------------------------------------------------------------


def _lock(canonical: dict[str, Any], vocabulary: dict[str, list[str]] | None) -> dict[str, Any]:
    return capability_compiler.compile_lock(
        canonical=canonical,
        project_key="fixture-alpha-dev",
        upstream="https://alpha.example.test/api/rest",
        sources={
            "capabilities_sha256": "0" * 64,
            "api_surface_sha256": "0" * 64,
            "canonical_openapi_sha256": "0" * 64,
        },
        vocabulary=vocabulary,
    )


def test_a_lock_at_schema_4_carries_the_vocabulary_and_one_below_may_not(
    inputs: tuple[dict[str, Any], dict[str, Any], set[str]], tmp_path: Path
) -> None:
    manifest, release, release_objects = inputs
    mcp_lock = service_source.load("mcp_lock")
    scopes = service_source.load("scopes")

    canonical = capability_compiler.compile_canonical(
        capabilities=manifest, surface=release, published_objects=release_objects
    )
    assert canonical["schema_version"] == 4
    block = scope_registry.vocabulary_block()

    with pytest.raises(capability_compiler.CompilerError, match="none was given"):
        _lock(canonical, None)

    lock = _lock(canonical, block)
    assert lock["vocabulary"] == block
    path = tmp_path / "v4.json"
    path.write_text(json.dumps(lock), encoding="utf-8")
    loaded = mcp_lock.load_lock(path)
    assert loaded.vocabulary["data"] == tuple(block["data"])
    issuer = scopes.load_vocabulary(path)
    assert issuer["data"] == frozenset(block["data"])
    assert issuer["administrative"] == scope_registry.administrative_scopes()

    stripped = dict(lock)
    del stripped["vocabulary"]
    path.write_text(json.dumps(stripped), encoding="utf-8")
    with pytest.raises(mcp_lock.LockError, match="vocabulary"):
        mcp_lock.load_lock(path)
    with pytest.raises(scopes.VocabularyError, match="no vocabulary"):
        scopes.load_vocabulary(path)

    older_manifest = copy.deepcopy(manifest)
    older_manifest["schema_version"] = 3
    older = capability_compiler.compile_canonical(
        capabilities=older_manifest, surface=release, published_objects=release_objects
    )
    assert older["schema_version"] == 3
    with pytest.raises(capability_compiler.CompilerError, match="ADR 0177"):
        _lock(older, block)
    v3 = _lock(older, None)
    assert "vocabulary" not in v3
    v3["vocabulary"] = block
    path.write_text(json.dumps(v3), encoding="utf-8")
    with pytest.raises(mcp_lock.LockError, match="ADR 0177"):
        mcp_lock.load_lock(path)


def test_the_issuers_ceiling_is_a_function_of_the_vocabulary(
    merged: tuple[dict[str, Any], set[str]],
) -> None:
    """Two vocabularies, one role, in the service's own module (stdlib, ADR
    0084): the tenant's write scope is in the writer's ceiling under the merged
    block and not under the release's, and everything else is identical."""
    scopes = service_source.load("scopes")
    release_block = {k: frozenset(v) for k, v in scope_registry.vocabulary_block().items()}
    merged_block = {k: frozenset(v) for k, v in scope_registry.vocabulary_block(merged[0]).items()}

    for role in scopes.ROLE_CLASSES:
        release_ceiling = scopes.ceiling(role, release_block)
        merged_ceiling = scopes.ceiling(role, merged_block)
        assert release_ceiling == scope_registry.permitted_scopes(role), role
        assert merged_ceiling == scope_registry.permitted_scopes(role, merged[0]), role

    assert "note_embeddings:write" not in scopes.ceiling("agent_writer", release_block)
    assert "note_embeddings:write" in scopes.ceiling("agent_writer", merged_block)
    assert scopes.ceiling("postgrest_authenticator", merged_block) is None


# ---------------------------------------------------------------------------
# The auth service mounts the lock
# ---------------------------------------------------------------------------


def test_the_auth_service_mounts_the_same_lock_the_agent_plane_does() -> None:
    names = {
        "router_name": "r",
        "https_entrypoint": "websecure",
        "rendered_directory": "/var/lib/agentic-postgres/rendered/x",
        "rest_router_name": "rest",
        "buffering_middleware_name": "b",
        "stripprefix_middleware_name": "s",
        "docs_router_name": "d",
        "docs_auth_middleware_name": "da",
        "docs_stripprefix_middleware_name": "ds",
        "app_router_name": "a",
        "app_buffering_middleware_name": "ab",
        "app_stripprefix_middleware_name": "as",
        "app_docs_router_name": "ad",
        "storage_router_name": "st",
        "storage_buffering_middleware_name": "sb",
        "storage_stripprefix_middleware_name": "ss",
        "storage_cors_middleware_name": "sc",
        "mcp_router_name": "m",
        "metrics_router_name": "me",
        "metrics_auth_middleware_name": "ma",
    }
    document = runtime_override.build_override(**names)
    payload = yaml.safe_dump(document).encode("utf-8")
    source = f"{names['rendered_directory']}/{runtime_override.MCP_LOCK_FILENAME}"

    assert source in runtime_override.mount_sources(payload, [runtime_override.AUTH_SERVICE])
    assert source in runtime_override.mount_sources(payload, [runtime_override.MCP_SERVICE])
    auth = document["services"][runtime_override.AUTH_SERVICE]["volumes"]
    assert auth == [f"{source}:{runtime_override.AUTH_LOCK_CONTAINER_PATH}:ro"]
    assert runtime_override.AUTH_LOCK_CONTAINER_PATH != runtime_override.MCP_LOCK_CONTAINER_PATH

    compose = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert f"APG_MCP_LOCK_FILE: {runtime_override.AUTH_LOCK_CONTAINER_PATH}" in compose


# ---------------------------------------------------------------------------
# No data-scope literal outside the schema and the example manifest
# ---------------------------------------------------------------------------


def _string_constants(source: str) -> list[str]:
    """Every string constant in a module that is not a docstring."""
    tree = ast.parse(source)
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_no_data_scope_literal_survives_outside_the_schema_and_the_example_manifest() -> None:
    """**Replaces `test_scope_vocabulary_lives_only_in_the_schema`** under ADR
    0200, and is stricter: ADR 0006 forbade a second COPY of the vocabulary,
    and this forbids the four relation-derived names appearing as a string
    constant in any module of the product at all. `meta:read` is the one
    structural name and is allowed. Docstrings and comments are prose."""
    offenders: list[str] = []
    for directory in ("src", "bin", "services"):
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            if "__pycache__" in path.parts or ".venv" in path.parts:
                continue
            for constant in _string_constants(path.read_text(encoding="utf-8")):
                if any(literal in constant for literal in DATA_LITERALS):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {constant[:60]!r}")
        for path in sorted((REPO_ROOT / directory).rglob("*.sh")):
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if any(literal in stripped for literal in DATA_LITERALS):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {stripped[:60]!r}")
    assert not offenders, "\n".join(offenders)

    # The control: the two files that MAY name them still do, so the scan above
    # is looking for something that exists.
    assert "notes:read" in EXAMPLE.read_text(encoding="utf-8")
    assert "notes:read" in (REPO_ROOT / "schemas" / "capabilities.schema.json").read_text(
        encoding="utf-8"
    )
