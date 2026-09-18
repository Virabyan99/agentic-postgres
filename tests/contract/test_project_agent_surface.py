"""A project's own agent surface (ADR 0201, Session 21 Run 4, `AGT-TENANT-001`).

A project manifest at schema 6 may name `mcp.capabilities: projects/<slug>`,
a capability manifest of the project's own beside its migration set. This
module drives a HAND-BUILT one under `tmp_path` against the example project's
committed reviewed surface and snapshot -- the example project's own manifest
is Run 5's, emitted by the scaffold, and the tests that read it live there.

What is proved here:

* the project's manifest compiles against the MERGED surface and the
  project's snapshot into the project's own contract, and could not compile
  against the release's surface (the control);
* the JOINT contract is the release's capabilities less the disabled ones plus
  the project's, and a lock compiled from it loads through the runtime's own
  loader with the merged vocabulary;
* a disabled release capability leaves THIS project's lock and no other's;
* the shapes a project may not declare are each refused with their reason;
* the render records the block, the deployed schema couples it to a ready
  plane, and a project without capabilities renders the explicit null.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from agentic_postgres import (
    REPO_ROOT,
    api_surface,
    capability_compiler,
    capability_manifest,
    config,
    deployed_output,
    openapi_normalize,
    rendering,
    scope_registry,
)
from agentic_postgres.capability_compiler import CompilerError
from agentic_postgres.config import ManifestError
from app.mcp_lock import load_lock

pytestmark = [pytest.mark.contract, pytest.mark.p0]

EXAMPLE_SET = REPO_ROOT / "projects" / "example"
RELEASE_CAPABILITIES = REPO_ROOT / "capabilities.example.yaml"
SOURCES = {
    "capabilities_sha256": "a" * 64,
    "api_surface_sha256": "b" * 64,
    "canonical_openapi_sha256": "c" * 64,
}


def project_document() -> dict[str, Any]:
    """The hand-built capability manifest: one read grouped under the release's
    `query_resource`, one write of its own, and one release write disabled."""
    return {
        "schema_version": 4,
        "release": {"disabled": ["create_note"]},
        "capabilities": [
            {
                "name": "query_note_embeddings",
                "tool": "query_resource",
                "description": "Which of the caller's notes carry an embedding, and when.",
                "kind": "read",
                "version": "1.0.0",
                "lifecycle": "active",
                "risk": "low",
                "max_response_bytes": 262144,
                "max_concurrent_calls": 1,
                "enabled": True,
                "required_scopes": ["note_embeddings:read"],
                "operation": {"source": "postgrest", "operation_id": "note_embeddings.get"},
                "resource": "note_embeddings",
                "columns": ["note_id", "owner_id", "updated_at"],
                "filters": [{"column": "note_id", "operators": ["eq", "in"]}],
                "order_by": [{"column": "updated_at", "direction": "desc"}],
                "max_rows": 100,
                "timeout_ms": 5000,
                "audit": {"redact": []},
            },
            {
                "name": "set_note_embedding",
                "description": "Store one note's embedding, computed by the caller.",
                "kind": "write",
                "version": "1.0.0",
                "lifecycle": "active",
                "risk": "moderate",
                "max_response_bytes": 65536,
                "max_concurrent_calls": 1,
                "supports_dry_run": True,
                "requires_approval": True,
                "enabled": True,
                "required_scopes": ["note_embeddings:write"],
                "operation": {"source": "postgrest", "operation_id": "rpc.set_note_embedding.post"},
                "max_affected_rows": 1,
                "idempotent": False,
                "timeout_ms": 5000,
                "audit": {"redact": ["p_embedding"]},
            },
        ],
    }


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A checkout under tmp_path: the example set copied, plus the project's
    capability manifest beside it."""
    root = tmp_path / "checkout"
    shutil.copytree(EXAMPLE_SET, root / "projects" / "example")
    (root / "projects" / "example" / "capabilities.yaml").write_text(
        yaml.safe_dump(project_document(), sort_keys=False), encoding="utf-8"
    )
    return root


@pytest.fixture
def manifest() -> dict[str, Any]:
    """The alpha fixture at schema 6, naming the project's capabilities."""
    document = yaml.safe_load((REPO_ROOT / "project.example.yaml").read_text("utf-8"))
    document["schema_version"] = 6
    document["mcp"]["capabilities"] = "projects/example"
    return document


@pytest.fixture
def inputs(checkout: Path, manifest: dict[str, Any]) -> capability_manifest.ProjectInputs:
    found = capability_manifest.project_inputs(manifest, repo_root=checkout)
    assert found is not None
    return found


@pytest.fixture(scope="module")
def release() -> dict[str, Any]:
    return config.load_capabilities_manifest(RELEASE_CAPABILITIES)


@pytest.fixture(scope="module")
def release_canonical() -> dict[str, Any]:
    path = REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
    return json.loads(path.read_text("utf-8"))


def tool_names(contract: dict[str, Any]) -> list[str]:
    return [entry["name"] for entry in contract["tools"]]


def tool(contract: dict[str, Any], name: str) -> dict[str, Any]:
    return next(entry for entry in contract["tools"] if entry["name"] == name)


# ---------------------------------------------------------------------------
# The project's own contract
# ---------------------------------------------------------------------------


def test_a_projects_manifest_compiles_against_the_merged_surface_to_its_own_contract(
    inputs: capability_manifest.ProjectInputs,
) -> None:
    """The merged surface is what makes `note_embeddings` resolve, and the
    project's snapshot is what publishes it; the control compiles the same
    manifest against the RELEASE surface and fails on the project's relation
    (the battery's fourth mutation, inverted)."""
    contract = capability_manifest.compile_project_contract(inputs)
    assert contract["contract_id"] == "example-note-embeddings-agent-v1"
    assert tool_names(contract) == ["query_resource", "set_note_embedding"]
    assert contract["capability_count"] == 2

    read = tool(contract, "query_resource")
    assert [r["name"] for r in read["resources"]] == ["note_embeddings"]
    assert read["resources"][0]["required_scopes"] == ["note_embeddings:read"]
    assert read["discovery_scope_sets"] == [["note_embeddings:read"]]
    write = tool(contract, "set_note_embedding")
    assert write["arguments"] == ["p_note_id", "p_embedding"]
    assert write["required_scopes"] == ["note_embeddings:write"]

    with pytest.raises(CompilerError, match="note_embeddings"):
        capability_compiler.compile_canonical(
            capabilities=inputs.capabilities,
            surface=api_surface.load_surface(),
            published_objects=set(inputs.published_objects),
            contract_id=inputs.contract_id,
        )


def test_a_projects_contract_id_is_derived_from_its_surfaces() -> None:
    assert capability_compiler.project_contract_id("notes-tasks-v1") == "notes-tasks-agent-v1"
    assert (
        capability_compiler.project_contract_id("example-note-embeddings-v1")
        == "example-note-embeddings-agent-v1"
    )
    assert capability_compiler.CONTRACT_ID == capability_compiler.project_contract_id(
        api_surface.load_surface()["contract_id"]
    ), "the release's own id follows the rule it sets for a project's"
    assert (
        capability_compiler.joint_contract_id("a-agent-v1", "b-agent-v2") == "a-agent-v1+b-agent-v2"
    )
    with pytest.raises(CompilerError, match="-v<N>"):
        capability_compiler.project_contract_id("no-version")


# ---------------------------------------------------------------------------
# The joint contract and the lock
# ---------------------------------------------------------------------------


def test_the_joint_contract_is_the_release_less_the_disabled_plus_the_projects(
    inputs: capability_manifest.ProjectInputs,
    release: dict[str, Any],
    release_canonical: dict[str, Any],
) -> None:
    joint = capability_manifest.compile_joint_contract(release, inputs)
    assert joint["contract_id"] == "notes-tasks-agent-v1+example-note-embeddings-agent-v1"
    expected = (set(tool_names(release_canonical)) - {"create_note"}) | {"set_note_embedding"}
    assert set(tool_names(joint)) == expected
    assert tool_names(joint) == sorted(tool_names(joint))
    assert joint["capability_count"] == release_canonical["capability_count"] - 1 + 2

    # The grouped read carries the release's resources AND the project's; the
    # release's own resources are byte-identical to the approved contract's.
    resources = {r["name"]: r for r in tool(joint, "query_resource")["resources"]}
    assert set(resources) == {"notes", "tasks", "note_embeddings"}
    approved = {r["name"]: r for r in tool(release_canonical, "query_resource")["resources"]}
    assert resources["notes"] == approved["notes"]
    assert resources["tasks"] == approved["tasks"]


def test_a_lock_compiled_from_the_joint_contract_loads_with_the_merged_vocabulary(
    inputs: capability_manifest.ProjectInputs, release: dict[str, Any], tmp_path: Path
) -> None:
    """Through the runtime's own loader (question 6): the lock the plane obeys,
    not a hand-built one. The vocabulary is the MERGED surface's, which is
    where a tenant's scope becomes issuable on one deployment and no other
    (ADR 0200); the release's vocabulary, the control, lacks it."""
    joint = capability_manifest.compile_joint_contract(release, inputs)
    lock = capability_compiler.compile_lock(
        canonical=joint,
        project_key="fixture-alpha-dev",
        upstream="https://fixture-alpha-dev.test/api/rest",
        sources=SOURCES,
        vocabulary=scope_registry.vocabulary_block(inputs.surface),
    )
    path = tmp_path / "lock.json"
    path.write_bytes(capability_compiler.canonical_bytes(lock))
    loaded = load_lock(path)
    names = sorted(t.name for t in loaded.tools)
    assert names == tool_names(joint)
    assert "create_note" not in names
    assert "set_note_embedding" in names
    assert "note_embeddings:read" in lock["vocabulary"]["data"]
    assert "note_embeddings:write" in lock["vocabulary"]["data"]
    assert "note_embeddings:read" not in scope_registry.vocabulary_block()["data"]
    assert (
        lock["canonical_sha256"] == sha256(capability_compiler.canonical_bytes(joint)).hexdigest()
    )


def test_a_disabled_release_capability_leaves_this_projects_lock_and_the_second_fixtures_keeps_it(
    inputs: capability_manifest.ProjectInputs,
    release: dict[str, Any],
    release_canonical: dict[str, Any],
) -> None:
    """D933's first thing, closed per project: `create_note` is compiled OUT of
    the lock of the project that disabled it -- absent, never flagged -- and
    the second fixture, which declares no capabilities of its own, keeps it."""
    joint = capability_manifest.compile_joint_contract(release, inputs)
    mine = capability_compiler.compile_lock(
        canonical=joint,
        project_key="fixture-alpha-dev",
        upstream="https://fixture-alpha-dev.test/api/rest",
        sources=SOURCES,
        vocabulary=scope_registry.vocabulary_block(inputs.surface),
    )
    second = capability_compiler.compile_lock(
        canonical=release_canonical,
        project_key="fixture-alpine-dev",
        upstream="https://fixture-alpine-dev.test/api/rest",
        sources=SOURCES,
        vocabulary=scope_registry.vocabulary_block(),
    )
    assert "create_note" not in [t["name"] for t in mine["tools"]]
    assert "create_note" in [t["name"] for t in second["tools"]]
    assert "create_note" not in json.dumps(mine), "compiled out, not carried with a flag"

    # The two refusals on the list itself, each naming its reason.
    unknown = copy.deepcopy(inputs.capabilities)
    unknown["release"]["disabled"] = ["create_everything"]
    with pytest.raises(ManifestError, match="does not declare"):
        capability_manifest.joined_capabilities(release, unknown)
    metadata = copy.deepcopy(inputs.capabilities)
    metadata["release"]["disabled"] = ["list_resources"]
    (inputs.root / "capabilities.yaml").write_text(
        yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(ManifestError, match="metadata tools"):
        capability_manifest.load_project_capabilities(inputs.root)


# ---------------------------------------------------------------------------
# What a project may not declare
# ---------------------------------------------------------------------------


def test_a_project_tool_named_for_a_release_tool_is_refused(
    inputs: capability_manifest.ProjectInputs, release: dict[str, Any]
) -> None:
    """A NEW tool under a release tool's name is two tools with one name; a
    read GROUPED under the release tool with `tool:` is the control and the
    point of the exercise (ADR 0120)."""
    stolen = copy.deepcopy(inputs.capabilities)
    stolen["capabilities"][0]["name"] = "query_resource"
    del stolen["capabilities"][0]["tool"]
    with pytest.raises(ManifestError, match="already serves tools"):
        capability_manifest.joined_capabilities(release, stolen)

    same_name = copy.deepcopy(inputs.capabilities)
    same_name["capabilities"][0]["name"] = "query_notes"
    with pytest.raises(ManifestError, match="already declares"):
        capability_manifest.joined_capabilities(release, same_name)

    grouped = capability_manifest.joined_capabilities(release, inputs.capabilities)
    assert "query_note_embeddings" in [c["name"] for c in grouped["capabilities"]]
    assert "release" not in grouped


@pytest.mark.parametrize(
    ("shape", "mutate", "message"),
    [
        (
            "a metadata capability",
            lambda d: d["capabilities"][0].update(
                {"name": "list_resources", "kind": "metadata", "tool": None}
            ),
            "metadata",
        ),
        (
            "an agent_rpcs operation",
            lambda d: d["capabilities"][1]["operation"].update(
                {"operation_id": "rpc.mcp_agent_context.post"}
            ),
            "agent-plane operations",
        ),
        (
            "a read over an RPC with arguments",
            lambda d: d["capabilities"][0].update(
                {
                    "tool": "read_set_note_embedding",
                    "name": "read_set_note_embedding",
                    "operation": {
                        "source": "postgrest",
                        "operation_id": "rpc.set_note_embedding.post",
                    },
                    "resource": "set_note_embedding",
                    "filters": [],
                    "order_by": [],
                }
            ),
            "RPC with arguments",
        ),
    ],
    ids=["metadata", "agent_rpcs", "rpc-read-with-arguments"],
)
def test_the_three_shapes_a_project_may_not_declare_are_refused(
    checkout: Path, manifest: dict[str, Any], shape: str, mutate: Any, message: str
) -> None:
    document = project_document()
    mutate(document)
    for entry in document["capabilities"]:
        if entry.get("tool") is None:
            entry.pop("tool", None)
    root = checkout / "projects" / "example"
    (root / "capabilities.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises((ManifestError, CompilerError), match=message):
        inputs = capability_manifest.project_inputs(manifest, repo_root=checkout)
        assert inputs is not None
        capability_manifest.compile_project_contract(inputs)


def test_a_manifest_below_four_and_a_project_without_a_set_are_refused(
    checkout: Path, manifest: dict[str, Any]
) -> None:
    root = checkout / "projects" / "example"
    three = project_document()
    three["schema_version"] = 3
    three.pop("release")
    for entry in three["capabilities"]:
        entry["required_scopes"] = ["notes:read"] if entry["kind"] == "read" else ["notes:write"]
    (root / "capabilities.yaml").write_text(yaml.safe_dump(three, sort_keys=False), "utf-8")
    with pytest.raises(ManifestError, match="version 4 or later"):
        capability_manifest.load_project_capabilities(root)

    without_set = copy.deepcopy(manifest)
    del without_set["migrations"]
    with pytest.raises(ManifestError, match=r"declares no migrations.set"):
        capability_manifest.project_inputs(without_set, repo_root=checkout)

    second = yaml.safe_load((REPO_ROOT / "project.second.example.yaml").read_text("utf-8"))
    assert capability_manifest.project_inputs(second, repo_root=checkout) is None


# ---------------------------------------------------------------------------
# The documents: rendered, deployed, and the observer's rule
# ---------------------------------------------------------------------------


def test_the_render_records_the_committed_contract_and_null_for_a_project_without_one(
    checkout: Path,
    manifest: dict[str, Any],
    inputs: capability_manifest.ProjectInputs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`capabilities.project` digests the COMMITTED contract -- the bytes
    `check --project` compares -- and refuses to render a project whose
    contract was never compiled, naming the command that writes it: null
    there would say "no capabilities of its own" about a project that
    declared some (ADR 0195)."""
    monkeypatch.setattr(rendering, "REPO_ROOT", checkout)
    contract_path = capability_manifest.project_contract_path(inputs.root)
    # The copy carries the example's committed contract (Run 5); the refusal
    # is for a project whose contract was never compiled, so remove it first.
    contract_path.unlink()
    with pytest.raises(ManifestError, match="compile --project"):
        rendering._project_capabilities_block(manifest)

    contract = capability_manifest.compile_project_contract(inputs)
    contract_path.write_bytes(capability_compiler.canonical_bytes(contract))
    block = rendering._project_capabilities_block(manifest)
    assert block == {
        "root": "projects/example",
        "contract_sha256": sha256(contract_path.read_bytes()).hexdigest(),
        "tool_count": 2,
        "capability_count": 2,
    }
    validator = Draft202012Validator(config.load_schema("outputs.schema.json"))
    sub = {"$ref": "#/$defs/projectCapabilities", "$defs": validator.schema["$defs"]}
    assert not list(Draft202012Validator(sub).iter_errors(block))
    assert not list(Draft202012Validator(sub).iter_errors(None))
    assert list(Draft202012Validator(sub).iter_errors({})), "an empty object is not the null"

    second = yaml.safe_load((REPO_ROOT / "project.second.example.yaml").read_text("utf-8"))
    assert rendering._project_capabilities_block(second) is None


def test_the_deployed_schema_couples_the_block_to_a_ready_plane() -> None:
    """`mcp.project_capabilities` is null beside `status: unavailable` like
    every other member, and null OR the object beside `ready` -- a ready plane
    on a project without capabilities of its own records the explicit null,
    which is the control (D600)."""
    schema = config.load_schema("outputs.schema.json")
    validator = Draft202012Validator({"$ref": "#/$defs/deployedMcp", "$defs": schema["$defs"]})
    block = {
        "root": "projects/example",
        "contract_sha256": "f" * 64,
        "tool_count": 2,
        "capability_count": 2,
    }
    unpublished = dict(deployed_output.MCP_NOT_PUBLISHED)
    assert not list(validator.iter_errors(unpublished))
    assert list(validator.iter_errors({**unpublished, "project_capabilities": block}))

    ready = {
        "status": "ready",
        "protocol_revision": "2025-06-18",
        "authorization_spec_conformant": False,
        "accepted_token_use": "agent",
        "capability_contract_sha256": "a" * 64,
        "capability_lock_sha256": "b" * 64,
        "tool_count": 6,
        "project_capabilities": None,
    }
    assert not list(validator.iter_errors(ready))
    assert not list(validator.iter_errors({**ready, "project_capabilities": block}))
    assert list(validator.iter_errors({**ready, "project_capabilities": {}}))
    del ready["project_capabilities"]
    assert list(validator.iter_errors(ready)), "the member is required at version 18"


def test_the_observer_carries_the_rendered_block_and_only_on_a_ready_plane() -> None:
    """Read from the deploy's source: the observer takes the rendered block by
    keyword, writes it into the READY block, and the unavailable one is the
    constant -- so a plane that never answered records nothing of the
    project's either."""
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    assert "project_capabilities: dict[str, Any] | None," in source
    assert 'project_capabilities=rendered["capabilities"]["project"],' in source
    observer = source[source.index("def observe_mcp(") :]
    ready = observer[observer.index('"status": "ready",') :]
    assert '"project_capabilities": (' in ready[: ready.index("return")]


# ---------------------------------------------------------------------------
# The command, on the shipped fixtures (the positive arms are Run 5's)
# ---------------------------------------------------------------------------


def contract_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "bin" / "mcp-contract.py"), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )


def test_the_command_refuses_a_project_contract_for_a_manifest_that_names_none() -> None:
    """Exit 2, the operator-input code: the second fixture declares no
    capabilities of its own, so `compile --project` has nothing to stream and
    says so rather than streaming the release's."""
    result = contract_cli("compile", "--project", "project.second.example.yaml")
    assert result.returncode == 2, result.stderr
    assert "declares no mcp.capabilities" in result.stderr
    assert result.stdout == ""

    # And the paths a manifest without the key took before, it still takes;
    # the example's, which names one since Run 5, reports the joint as well.
    checked = contract_cli("check", "--project", "project.second.example.yaml")
    assert checked.returncode == 0, checked.stderr
    assert "narrows the approved contract" in checked.stdout
    assert "joint contract" not in checked.stdout
    example = contract_cli("check", "--project", "project.example.yaml")
    assert example.returncode == 0, example.stderr
    assert "joint contract" in example.stdout


def test_the_shipped_fixtures_are_at_six_and_only_the_example_names_capabilities() -> None:
    """Version 6 on both; the example names its manifest (Run 5, written by
    the scaffold) and the second does not, so every proof above about a
    manifest that names one has a shipped control at the same version."""
    example = config.load_project_manifest(REPO_ROOT / "project.example.yaml")
    second = config.load_project_manifest(REPO_ROOT / "project.second.example.yaml")
    assert example["schema_version"] == second["schema_version"] == 6
    assert config.project_capabilities(example) == "projects/example"
    assert config.project_capabilities(second) is None
    assert capability_manifest.PROJECT_SCHEMA_FROM == capability_compiler.VOCABULARY_FROM


def test_published_objects_come_from_the_projects_snapshot(
    inputs: capability_manifest.ProjectInputs,
) -> None:
    snapshot = json.loads(api_surface.project_snapshot_path(EXAMPLE_SET).read_text("utf-8"))
    assert inputs.published_objects == frozenset(openapi_normalize.declared_objects(snapshot))
    assert "note_embeddings" in inputs.published_objects
    assert "rpc/set_note_embedding" in inputs.published_objects


# ---------------------------------------------------------------------------
# an artefact the project has not captured yet (D1360)
# ---------------------------------------------------------------------------


def test_an_artefact_the_project_has_not_captured_is_a_contract_failure_not_operator_input(
    checkout: Path, manifest: dict[str, Any]
) -> None:
    """`CapabilityContractError` exists for exactly this, and two sites missed it.

    Its docstring draws the line: *"the CLI maps it to exit 5 (contract
    failure) rather than exit 2 (invalid operator input): the manifest is well
    formed, it just asserts something untrue."* A project manifest naming a
    snapshot that has not been captured yet **is** well formed -- the capture
    needs a running deployment (ADR 0198, D1211) -- but both sites raised a
    plain `ManifestError`, so `render-evaluation-report.py` exited 2 while
    `mcp-contract compile`, `check` and `apg generate` all exited 5 on the very
    same sentence (D1360, the second walk's eighth finding).

    The control is the one that matters: a manifest that is genuinely invalid
    must still be a plain `ManifestError`, or the repair has simply moved every
    manifest error to 5 and lost the distinction the other way.
    """
    surface = capability_manifest.CONTRACTS_DIRECTORY, "postgrest-api-surface.yaml"
    snapshot = capability_manifest.CONTRACTS_DIRECTORY, "postgrest-openapi.canonical.json"
    project = checkout / "projects" / "example"

    for directory, name in (snapshot, surface):
        path = project / directory / name
        assert path.is_file(), f"the fixture never had {name}, so its absence proves nothing"
        kept = path.read_bytes()
        path.unlink()
        try:
            with pytest.raises(config.CapabilityContractError) as raised:
                capability_manifest.project_inputs(manifest, repo_root=checkout)
        finally:
            path.write_bytes(kept)
        assert name in str(raised.value), (
            f"the refusal does not name the artefact that is missing: {raised.value}"
        )
        assert isinstance(raised.value, ManifestError), (
            "CapabilityContractError must stay a ManifestError, or every existing "
            "`except config.ManifestError` stops catching it"
        )

    # The control: a well-formed file is what makes it a contract failure. A
    # manifest that is NOT well formed is still operator input.
    broken = dict(manifest)
    broken["mcp"] = dict(manifest["mcp"], capabilities="projects/does-not-exist")
    with pytest.raises(ManifestError) as raised:
        capability_manifest.project_inputs(broken, repo_root=checkout)
    assert not isinstance(raised.value, config.CapabilityContractError), (
        "a manifest naming a directory that does not exist is invalid operator input "
        "and must not be priced as a contract failure"
    )


def test_the_commands_that_read_project_inputs_price_a_missing_artefact_alike() -> None:
    """One condition, one number -- across every command that meets it.

    Each command's `main` is called with `project_inputs` raising what the real
    raise sites raise, so this measures the MAPPING each command applies rather
    than a fixture's guess at it. The second call of each pair is the control:
    a plain `ManifestError` -- a manifest the operator really did get wrong --
    must still be 2 wherever it was 2 before.

    Only `render-evaluation-report.py` has a 2 AND a 5 to tell apart, so it is
    the one carrying the control. `generate.py` and `mcp-contract.py` map every
    `ManifestError` to 5 already; what they prove is that a subclass did not
    change what they did. `studio` maps a contract failure to 2 on purpose (5
    is `EXIT_NO_ROUTE` there, an answer about a deployment), and
    `render-mcp-catalog.py` never reads `project_inputs` -- its own mapping is
    proved in `test_mcp_catalog.py`, where a contract is the subject.
    """
    import importlib.util

    def command(name: str):
        path = REPO_ROOT / "bin" / name
        spec = importlib.util.spec_from_file_location(f"_d1360_{name.replace('.', '_')}", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def exit_code(module, error: Exception, argv: list[str]) -> int:
        import contextlib
        import io

        def raise_it(*_args: Any, **_kwargs: Any):
            raise error

        original = capability_manifest.project_inputs
        module_inputs = getattr(module, "capability_manifest", None)
        assert module_inputs is not None, f"{module} does not read capability_manifest"
        module_inputs.project_inputs = raise_it
        try:
            with (
                contextlib.redirect_stderr(io.StringIO()),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                saved, sys.argv = sys.argv, argv
                try:
                    return module.main()
                except SystemExit as exit_info:
                    return int(exit_info.code or 0)
                finally:
                    sys.argv = saved
        finally:
            module_inputs.project_inputs = original

    sentence = "has no approved snapshot at contracts/postgrest-openapi.canonical.json"
    manifest_argument = str(REPO_ROOT / "project.example.yaml")

    for name, argv in (
        ("render-evaluation-report.py", ["x", "--write", "--project", manifest_argument]),
        ("generate.py", ["x", "--project", manifest_argument]),
        ("mcp-contract.py", ["x", "check", "--project", manifest_argument]),
    ):
        module = command(name)
        contract_failure = exit_code(module, config.CapabilityContractError(sentence), list(argv))
        assert contract_failure == 5, (
            f"bin/{name} prices an uncaptured artefact {contract_failure}, not 5; "
            "compile, check and generate all say 5 on this sentence"
        )

    # The control, on the one command that has both codes to tell apart: a
    # manifest the operator really did get wrong is still invalid input.
    report = command("render-evaluation-report.py")
    operator_input = exit_code(
        report,
        ManifestError("slug: expected a string"),
        ["x", "--write", "--project", manifest_argument],
    )
    assert operator_input == 2, (
        f"a genuinely invalid manifest is now priced {operator_input}; the subclass was "
        "meant to narrow the 5, not widen it"
    )
