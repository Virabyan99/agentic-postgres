"""The roster is compiled, not enumerated (ADR 0200, Session 21 Run 3).

`test_mcp_tools` proves the loader and the registrar over hand-built fixtures;
this module proves the same properties through the REAL compiler, the real
loader and the real server, on the example manifest and on a tenant's:

* a five-tool lock loads and serves five (D933 inverted), and a seven-tool
  lock compiled from a manifest that declares a tenant write loads and serves
  seven -- through the server's own pipeline, not a registry stub;
* a tool the compiler did not sign is refused by its digest, and the same
  tool compiled from a manifest that declares it is not;
* a tenant write registered from the lock opens its audit record before its
  scope is checked (ADR 0141), exactly as the release's writes do;
* the runtime's copy of the canonical serialization equals the compiler's;
* a read over an RPC with arguments has no shape and is refused (D1129), and a
  metadata capability outside the pair is refused.
"""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import (
    REPO_ROOT,
    api_surface,
    capability_compiler,
    openapi_normalize,
    scope_registry,
    service_source,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0]

EXAMPLE = REPO_ROOT / "capabilities.example.yaml"
EXAMPLE_PROJECT = REPO_ROOT / "projects" / "example"
SOURCES = {
    "capabilities_sha256": "0" * 64,
    "api_surface_sha256": "0" * 64,
    "canonical_openapi_sha256": "0" * 64,
}
IDEMPOTENCY_KEY = "k" * 16


def _mcp_contract() -> Any:
    spec = importlib.util.spec_from_file_location(
        "apg_mcp_contract", REPO_ROOT / "bin" / "mcp-contract.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def release() -> tuple[dict[str, Any], dict[str, Any], set[str]]:
    return _mcp_contract()._inputs(EXAMPLE)


@pytest.fixture(scope="module")
def merged() -> tuple[dict[str, Any], set[str]]:
    project = api_surface.load_project_surface(api_surface.project_contract_path(EXAMPLE_PROJECT))
    surface = api_surface.merged_surface(api_surface.load_surface(), project)
    snapshot = json.loads(
        api_surface.project_snapshot_path(EXAMPLE_PROJECT).read_text(encoding="utf-8")
    )
    return surface, openapi_normalize.declared_objects(snapshot)


def _tenant_write() -> dict[str, Any]:
    """The example project's write, the shape `apg agent init` will emit."""
    return {
        "name": "set_note_embedding",
        "description": "Store the caller's own embedding for one of the caller's notes.",
        "kind": "write",
        "version": "1.0.0",
        "lifecycle": "active",
        "risk": "moderate",
        "max_response_bytes": 65536,
        "max_concurrent_calls": 1,
        "supports_dry_run": True,
        "requires_approval": False,
        "enabled": True,
        "required_scopes": ["note_embeddings:write"],
        "operation": {"source": "postgrest", "operation_id": "rpc.set_note_embedding.post"},
        "max_affected_rows": 1,
        "idempotent": False,
        "timeout_ms": 5000,
        "audit": {"redact": ["p_embedding"]},
    }


def _lock_document(canonical: dict[str, Any], vocabulary: dict[str, list[str]]) -> dict[str, Any]:
    return capability_compiler.compile_lock(
        canonical=canonical,
        project_key="fixture-alpha-dev",
        upstream="https://alpha.example.test/api/rest",
        sources=SOURCES,
        vocabulary=vocabulary,
    )


def _write_lock(tmp_path: Path, document: dict[str, Any], name: str = "lock.json") -> Path:
    path = tmp_path / name
    path.write_bytes(capability_compiler.canonical_bytes(document))
    return path


class _Registry:
    """The least a `register()` call needs; `test_mcp_tools` has the same stub."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, *, name: str, timeout: float | None = None) -> Any:
        def keep(function: Any) -> Any:
            self.tools[name] = function
            return function

        return keep


# ---------------------------------------------------------------------------
# Five loads and serves five; seven loads and serves seven
# ---------------------------------------------------------------------------


def test_a_five_tool_lock_loads_and_serves_five(
    release: tuple[dict[str, Any], dict[str, Any], set[str]], tmp_path: Path
) -> None:
    """D933 inverted, through the real compiler and loader. Rig 21b measured the
    refusal at `5a43f12`: *"the lock serves [five], not [six]"*. The six-tool
    lock is the control, compiled the same way in the same test."""
    manifest, surface, published = release
    mcp_lock = service_source.load("mcp_lock")
    mcp_tools = service_source.load("mcp_tools")

    six = capability_compiler.compile_canonical(
        capabilities=manifest, surface=surface, published_objects=published
    )
    loaded = mcp_lock.load_lock(
        _write_lock(tmp_path, _lock_document(six, scope_registry.vocabulary_block()), "six.json")
    )
    assert [tool.name for tool in loaded.tools] == [
        "create_note",
        "describe_resource",
        "list_resources",
        "query_resource",
        "run_report",
        "update_task_status",
    ]

    without = copy.deepcopy(manifest)
    for entry in without["capabilities"]:
        if entry["name"] == "create_note":
            entry["enabled"] = False
    five = capability_compiler.compile_canonical(
        capabilities=without, surface=surface, published_objects=published
    )
    loaded = mcp_lock.load_lock(
        _write_lock(tmp_path, _lock_document(five, scope_registry.vocabulary_block()), "five.json")
    )
    names = [tool.name for tool in loaded.tools]
    assert names == [
        "describe_resource",
        "list_resources",
        "query_resource",
        "run_report",
        "update_task_status",
    ]

    registry = _Registry()
    assert mcp_tools.register(registry, loaded, base_url="https://postgrest.test") == tuple(names)
    assert "create_note" not in registry.tools


def test_a_tenant_write_compiled_from_a_manifest_loads_and_is_served_through_the_pipeline(
    merged: tuple[dict[str, Any], set[str]],
    release: tuple[dict[str, Any], dict[str, Any], set[str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A seventh tool, from a manifest that declares it, over the merged surface.

    Through the assembled server's own `list_tools`, which runs the middleware
    pipeline (ADR 0140 M4): the roster a WRITER holding the tenant scope sees
    carries `set_note_embedding`, and the roster a READER sees does not -- the
    hidden-name half of ADR 0140, re-run against a roster that is not six.
    """
    manifest = copy.deepcopy(release[0])
    manifest["capabilities"].append(_tenant_write())
    surface, published = merged
    seven = capability_compiler.compile_canonical(
        capabilities=manifest, surface=surface, published_objects=published
    )
    assert seven["tool_count"] == 7
    tool = next(t for t in seven["tools"] if t["name"] == "set_note_embedding")
    assert tool["arguments"] == ["p_note_id", "p_embedding"]

    mcp_lock = service_source.load("mcp_lock")
    path = _write_lock(tmp_path, _lock_document(seven, scope_registry.vocabulary_block(surface)))
    lock = mcp_lock.load_lock(path)
    assert lock.tool("set_note_embedding").write.arguments == ("p_note_id", "p_embedding")

    import fastmcp.server.dependencies as dependencies
    from cryptography.hazmat.primitives.asymmetric import rsa

    from agentic_postgres import jwt_keys

    mcp_authorization = service_source.load("mcp_authorization")
    mcp_runtime = service_source.load("mcp_runtime")
    tokens = service_source.load("tokens")
    mcp_upstream = service_source.load("mcp_upstream")

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()
    jwks = tmp_path / "jwks.json"
    jwks.write_bytes(
        json.dumps(
            jwt_keys.build_jwks(
                [jwt_keys.public_jwk(modulus_hex=format(numbers.n, "X"), exponent=numbers.e)]
            )
        ).encode("utf-8")
    )

    class _Token:
        token = "the.callers.token"  # noqa: S105 -- a fixed placeholder

    monkeypatch.setattr(dependencies, "get_access_token", lambda: _Token())

    def roster(*scopes: str) -> list[str]:
        monkeypatch.setattr(
            mcp_authorization,
            "resolve_agent_context",
            lambda base_url, token, request_id: mcp_upstream.AgentContext(
                agent_id="agent-1",
                role_name="r",
                scopes=tuple(scopes),
                authz_version=1,
                owner_id="owner-1",
            ),
        )
        server = mcp_runtime.build_server(
            mcp_runtime.AgentTokenVerifier(
                tokens.LocalKeySet.from_path(jwks), issuer="https://i.test", audience="urn:a"
            ),
            project_key="fixture-alpha-dev",
            postgrest_url="http://postgrest:3000",
            lock=lock,
            max_concurrent_reads=2,
        )
        return sorted(tool.name for tool in asyncio.run(server.list_tools()))

    writer = roster("meta:read", "notes:read", "note_embeddings:write")
    assert writer == ["describe_resource", "list_resources", "query_resource", "set_note_embedding"]
    reader = roster("meta:read", "notes:read")
    assert "set_note_embedding" not in reader
    assert reader == ["describe_resource", "list_resources", "query_resource"]


# ---------------------------------------------------------------------------
# Compiled, not edited: the digest
# ---------------------------------------------------------------------------


def test_a_tool_the_compiler_did_not_digest_is_refused(
    release: tuple[dict[str, Any], dict[str, Any], set[str]],
    merged: tuple[dict[str, Any], set[str]],
    tmp_path: Path,
) -> None:
    """**Replaces `test_a_lock_with_a_seventh_tool_is_refused`** under ADR 0200.

    The old refusal was by count; this one is by signature. The seventh tool
    appended BY HAND to a compiled lock is refused because `tools_sha256` does
    not cover it; the SAME seventh tool compiled from a manifest that declares
    it loads (the previous test). A tool edited in place is refused the same
    way, and so is a tool removed -- and a lock below schema version 4 may not
    carry the signature at all (ADR 0177).
    """
    manifest, surface, published = release
    mcp_lock = service_source.load("mcp_lock")
    six = capability_compiler.compile_canonical(
        capabilities=manifest, surface=surface, published_objects=published
    )
    signed = _lock_document(six, scope_registry.vocabulary_block())
    assert "tools_sha256" in signed
    mcp_lock.load_lock(_write_lock(tmp_path, signed, "signed.json"))

    tenant_manifest = copy.deepcopy(manifest)
    tenant_manifest["capabilities"].append(_tenant_write())
    seven = capability_compiler.compile_canonical(
        capabilities=tenant_manifest, surface=merged[0], published_objects=merged[1]
    )
    stranger = next(t for t in seven["tools"] if t["name"] == "set_note_embedding")

    appended = json.loads(json.dumps(signed))
    appended["tools"].append(stranger)
    appended["tool_count"] = 7
    with pytest.raises(mcp_lock.LockError, match="tools_sha256"):
        mcp_lock.load_lock(_write_lock(tmp_path, appended, "appended.json"))

    edited = json.loads(json.dumps(signed))
    create = next(t for t in edited["tools"] if t["name"] == "create_note")
    create["max_affected_rows"] = 50
    with pytest.raises(mcp_lock.LockError, match="tools_sha256"):
        mcp_lock.load_lock(_write_lock(tmp_path, edited, "edited.json"))

    removed = json.loads(json.dumps(signed))
    removed["tools"] = [t for t in removed["tools"] if t["name"] != "create_note"]
    removed["tool_count"] = 5
    with pytest.raises(mcp_lock.LockError, match="tools_sha256"):
        mcp_lock.load_lock(_write_lock(tmp_path, removed, "removed.json"))

    older_manifest = copy.deepcopy(manifest)
    older_manifest["schema_version"] = 3
    three = capability_compiler.compile_canonical(
        capabilities=older_manifest, surface=surface, published_objects=published
    )
    unsigned = _lock_document(three, None)
    assert "tools_sha256" not in unsigned
    unsigned["tools_sha256"] = signed["tools_sha256"]
    with pytest.raises(mcp_lock.LockError, match="ADR 0177"):
        mcp_lock.load_lock(_write_lock(tmp_path, unsigned, "unsigned.json"))


def test_the_runtime_digests_a_tool_list_exactly_as_the_compiler_does(
    release: tuple[dict[str, Any], dict[str, Any], set[str]],
) -> None:
    """Two copies of one serialization rule, and the test between them (D486).

    The runtime imports nothing from `agentic_postgres` (ADR 0084), so it
    carries its own `canonical_bytes`. If the two ever differed, every lock
    would be refused at startup with a message about a signature nobody forged.
    """
    manifest, surface, published = release
    mcp_lock = service_source.load("mcp_lock")
    canonical = capability_compiler.compile_canonical(
        capabilities=manifest, surface=surface, published_objects=published
    )
    for document in (canonical, canonical["tools"], {"z": 1, "a": [1, "é", {"k": None}]}):
        assert mcp_lock.canonical_bytes(document) == capability_compiler.canonical_bytes(document)


# ---------------------------------------------------------------------------
# A tenant write registered from the lock keeps the audit order (ADR 0141)
# ---------------------------------------------------------------------------


def test_a_tenant_write_registered_from_the_lock_is_audited_before_its_scope_is_checked(
    release: tuple[dict[str, Any], dict[str, Any], set[str]],
    merged: tuple[dict[str, Any], set[str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Begin, then the scope refusal, then complete as `refused` -- for a tool the
    runtime had never seen (ADR 0141's order, on a closure built from data).

    The control is the same call by a caller HOLDING the scope, which reaches
    the work; without it a registrar that refused every tenant write would
    satisfy the first half.
    """
    manifest = copy.deepcopy(release[0])
    manifest["capabilities"].append(_tenant_write())
    surface, published = merged
    seven = capability_compiler.compile_canonical(
        capabilities=manifest, surface=surface, published_objects=published
    )
    mcp_lock = service_source.load("mcp_lock")
    mcp_tools = service_source.load("mcp_tools")
    mcp_authorization = service_source.load("mcp_authorization")
    mcp_upstream = service_source.load("mcp_upstream")
    lock = mcp_lock.load_lock(
        _write_lock(tmp_path, _lock_document(seven, scope_registry.vocabulary_block(surface)))
    )

    order: list[str] = []
    recorded: list[dict[str, Any]] = []

    def context(*scopes: str) -> None:
        resolved = mcp_upstream.AgentContext(
            agent_id="agent-1",
            role_name="r",
            scopes=tuple(scopes),
            authz_version=1,
            owner_id="owner-1",
        )
        # `mcp_tools` imports the name directly, so its own binding is the one
        # `_scopes()` and `bounded` read; the authorization module's is what
        # `register` binds at call time.
        monkeypatch.setattr(mcp_tools, "current_agent_context", lambda: resolved)
        monkeypatch.setattr(mcp_authorization, "current_agent_context", lambda: resolved)

    monkeypatch.setattr(mcp_authorization, "current_token", lambda: "t")
    monkeypatch.setattr(mcp_authorization, "current_request_id", lambda: "r" * 32)

    def began(*_: Any, **kwargs: Any) -> str:
        order.append("begin")
        recorded.append({"phase": "begin", **kwargs})
        return "audit-1"

    def completed(*_: Any, **kwargs: Any) -> bool:
        order.append("complete")
        recorded.append({"phase": "complete", **kwargs})
        return True

    def executed(*_: Any, **__: Any) -> list[dict[str, Any]]:
        order.append("work")
        return [{"note_id": "n1"}]

    monkeypatch.setattr(mcp_tools, "audit_begin", began)
    monkeypatch.setattr(mcp_tools, "audit_complete", completed)
    monkeypatch.setattr(mcp_tools, "execute_write", executed)

    registry = _Registry()
    mcp_tools.register(registry, lock, base_url="https://postgrest.test")
    call = registry.tools["set_note_embedding"]

    context("meta:read", "notes:read")
    with pytest.raises(Exception, match="requires"):
        asyncio.run(
            call(
                p_note_id="n1", p_embedding="[0.1]", idempotency_key=IDEMPOTENCY_KEY, dry_run=False
            )
        )
    assert order == ["begin", "complete"], "the refusal was not audited, or was audited late"
    closing = next(entry for entry in recorded if entry["phase"] == "complete")
    assert closing["outcome"] == "refused"
    opening = next(entry for entry in recorded if entry["phase"] == "begin")
    assert opening["tool"] == "set_note_embedding"
    assert set(opening["parameters"]) == {"p_note_id", "p_embedding"}
    assert opening["parameters"]["p_embedding"] != "[0.1]", "the lock's redaction was not applied"

    order.clear()
    recorded.clear()
    context("meta:read", "note_embeddings:write")
    result = asyncio.run(
        call(p_note_id="n1", p_embedding="[0.1]", idempotency_key=IDEMPOTENCY_KEY, dry_run=False)
    )
    assert order == ["begin", "work", "complete"]
    assert result["row_count"] == 1


# ---------------------------------------------------------------------------
# The shapes a compiler refuses
# ---------------------------------------------------------------------------


def test_a_read_over_an_rpc_with_arguments_and_a_metadata_capability_outside_the_pair_are_refused(
    release: tuple[dict[str, Any], dict[str, Any], set[str]],
) -> None:
    """D1129 and the one roster kept, at compile time, with the example manifest
    as the control that compiles unchanged."""
    manifest, surface, published = release
    capability_compiler.compile_canonical(
        capabilities=manifest, surface=surface, published_objects=published
    )

    with_arguments = copy.deepcopy(manifest)
    report = next(e for e in with_arguments["capabilities"] if e["name"] == "run_report")
    report["operation"]["operation_id"] = "rpc.create_task.post"
    report["resource"] = "create_task"
    report["columns"] = ["id"]
    with pytest.raises(capability_compiler.CompilerError, match="RPC with arguments"):
        capability_compiler.compile_canonical(
            capabilities=with_arguments, surface=surface, published_objects=published
        )

    stranger = copy.deepcopy(manifest)
    listing = next(e for e in stranger["capabilities"] if e["name"] == "list_resources")
    listing["name"] = "list_everything"
    with pytest.raises(capability_compiler.CompilerError, match="list_everything"):
        capability_compiler.compile_canonical(
            capabilities=stranger, surface=surface, published_objects=published
        )


# ---------------------------------------------------------------------------
# The lock this process loaded, readable from outside it (D1152, D1153)
# ---------------------------------------------------------------------------


def test_the_loaded_lock_keeps_the_signature_the_file_carried(
    release: tuple[dict[str, Any], dict[str, Any], set[str]], tmp_path: Path
) -> None:
    """`CapabilityLock.tools_sha256` is the file's value, not a recomputation.

    The distinction matters because `load_lock` already recomputes the digest to
    VERIFY it; keeping the recomputed value would make the field agree with the
    tools by construction and say nothing about which document was read. What is
    wanted is the value the compiler signed, so that two processes reporting the
    same string are serving the same reviewed list.

    Goes red if the field is dropped, recomputed, or filled in at a schema
    version that carries no signature.
    """
    manifest, surface, published = release
    mcp_lock = service_source.load("mcp_lock")

    canonical = capability_compiler.compile_canonical(
        capabilities=manifest, surface=surface, published_objects=published
    )
    document = _lock_document(canonical, scope_registry.vocabulary_block())
    path = _write_lock(tmp_path, document, "signed.json")
    loaded = mcp_lock.load_lock(path)

    assert loaded.tools_sha256 == document["tools_sha256"]
    assert (
        loaded.tools_sha256
        == mcp_lock.hashlib.sha256(
            mcp_lock.canonical_bytes(json.loads(path.read_text(encoding="utf-8"))["tools"])
        ).hexdigest()
    ), "the kept signature is not over the tool list the file carries"

    # The control: the count is equal for lists that are not, which is why the
    # deploy compares the signature and not the count (D1153).
    assert loaded.tool_count == document["tool_count"]


def test_the_runtime_records_the_lock_it_loaded_at_module_level(
    release: tuple[dict[str, Any], dict[str, Any], set[str]], tmp_path: Path, monkeypatch
) -> None:
    """`create_mcp_app` publishes the lock it built the server from.

    D1152: a deploy whose only change was the lock recreated no container, and
    the deployed document read the FILE and spoke of the plane. The repair is
    that the plane can be asked, and this is the value it answers with -- set
    once, at the line the server is built from, so the two cannot disagree.

    Goes red if the assignment is removed, if it is made before `load_lock`
    accepts the document, or if it records something other than the object the
    server was built with.
    """
    manifest, surface, published = release
    mcp_runtime = service_source.load("mcp_runtime")
    mcp_lock = service_source.load("mcp_lock")

    canonical = capability_compiler.compile_canonical(
        capabilities=manifest, surface=surface, published_objects=published
    )
    document = _lock_document(canonical, scope_registry.vocabulary_block())
    path = _write_lock(tmp_path, document, "loaded.json")

    assert mcp_runtime.LOADED_LOCK is None, (
        "a module that has not built an app already reports a lock, so the value "
        "below would not be evidence that building one recorded it"
    )

    built: dict[str, Any] = {}

    def fake_build_server(verifier, **keywords):
        built["lock"] = keywords["lock"]
        return object()

    class _Settings:
        jwks_file = tmp_path / "jwks.json"
        capability_lock_file = path
        issuer = "https://issuer.test"
        audience = "https://audience.test"
        project_key = "probe-dev"
        postgrest_url = "https://postgrest.test"
        max_concurrent_reads = 4
        # `None`, which is the arm where no collector is configured: this test
        # is about the lock the runtime recorded, and an exporter reaching for
        # a real endpoint is not its subject. It has to be declared, though --
        # a hand-rolled stub answers only the attributes it was written with,
        # so every setting `create_mcp_app` reads has to be here or the call
        # raises `AttributeError` somewhere down the function and the failure
        # surfaces as whatever the next assertion happens to be.
        otlp_endpoint = None

    record = tmp_path / "apg-loaded-lock.json"
    monkeypatch.setattr(mcp_runtime, "LOADED_LOCK_RECORD", str(record))
    monkeypatch.setattr(mcp_runtime, "build_server", fake_build_server)
    monkeypatch.setattr(mcp_runtime.settings_module, "load_mcp", lambda: _Settings())
    monkeypatch.setattr(mcp_runtime.LocalKeySet, "from_path", staticmethod(lambda _p: object()))
    # Everything after `build_server` is Starlette's, and the line under test is
    # the one before it. The stub returns an object with no routes, so whatever
    # the framework does with it next is not the subject -- and is not silenced
    # either: the reason is printed, and the assertions below fail if the lock
    # was never recorded, whatever went wrong afterwards.
    try:
        mcp_runtime.create_mcp_app()
    except Exception as stopped:
        print(f"create_mcp_app stopped after build_server: {stopped!r}")

    assert mcp_runtime.LOADED_LOCK is not None, (
        "the runtime built a server from a lock and recorded none, so nothing "
        "outside the process can say which lock it serves"
    )
    assert mcp_runtime.LOADED_LOCK is built["lock"], (
        "the module-level lock is not the object the server was built with -- two "
        "assignments that have to agree rather than one value"
    )
    assert mcp_runtime.LOADED_LOCK.tools_sha256 == document["tools_sha256"]
    assert mcp_runtime.LOADED_LOCK.tool_count == document["tool_count"]

    # D1286: and written where a SECOND process can read it. The global above is
    # invisible to `docker exec python -c`, which is how the deploy asks -- so
    # asserting only the global is asserting the half that was never in doubt.
    written = json.loads(record.read_text(encoding="utf-8"))
    assert written == {
        "tools_sha256": document["tools_sha256"],
        "tool_count": document["tool_count"],
    }, f"the record does not describe the lock the server was built with: {written}"

    # And the loader is still the gate: a lock this runtime refuses records
    # nothing, because the assignment sits after `load_lock` returns.
    monkeypatch.setattr(mcp_runtime, "LOADED_LOCK", None)
    broken = dict(document)
    broken["tools_sha256"] = "0" * 64
    _write_lock(tmp_path, broken, "broken.json")
    _Settings.capability_lock_file = tmp_path / "broken.json"
    with pytest.raises(mcp_lock.LockError):
        mcp_runtime.create_mcp_app()
    assert mcp_runtime.LOADED_LOCK is None, (
        "a lock the loader refused was recorded anyway, so the plane would report "
        "serving a document it rejected"
    )
