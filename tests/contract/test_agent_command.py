"""`bin/agent.sh init` -- the scaffold for a project's agent surface
(ADR 0201 §5, D1137, D1138; `AGT-INIT-001`).

One verb. It streams one capability entry derived from the merged reviewed
surface -- the same operations table the compiler resolves against -- and
writes no file. What is proved here:

* for EVERY object the example project's surface publishes, the entry it
  emits compiles under `mcp-contract.sh check --project` unchanged, placed in
  a copy of the manifest under `tmp_path`;
* an operation the merged surface does not name is refused with exit 2 and
  the names it does; so is a release-owned object, an agent-plane operation,
  a write without `--relation`, and a `--kind` that contradicts the object;
* the example project's committed `capabilities.yaml` is byte-identical to
  `init --head` plus the scaffold's two entries -- so the shipped example is
  what the product writes, not what somebody typed.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import (
    REPO_ROOT,
    api_surface,
    capability_compiler,
    capability_manifest,
    config,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0]

EXAMPLE_SET = REPO_ROOT / "projects" / "example"
EXAMPLE_MANIFEST = REPO_ROOT / "project.example.yaml"
SECOND_MANIFEST = REPO_ROOT / "project.second.example.yaml"


def agent(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(REPO_ROOT / "bin" / "agent.sh"), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )


def contract_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "bin" / "mcp-contract.py"), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )


@pytest.fixture(scope="module")
def project_surface() -> dict[str, Any]:
    return api_surface.load_project_surface(api_surface.project_contract_path(EXAMPLE_SET))


def scaffold_calls(surface: dict[str, Any]) -> list[tuple[str, ...]]:
    """One `init` invocation per object the project's surface publishes: a
    relation as itself, an RPC with the project's first relation as the one it
    writes -- what a reviewer would name for the example set."""
    relation = sorted(surface["relations"])[0]
    calls: list[tuple[str, ...]] = [("--operation", name) for name in sorted(surface["relations"])]
    calls += [("--operation", name, "--relation", relation) for name in sorted(surface["rpcs"])]
    return calls


# ---------------------------------------------------------------------------
# Every object of the example project scaffolds an entry that compiles
# ---------------------------------------------------------------------------


def test_init_emits_an_entry_that_compiles_for_every_object_of_the_example_project(
    tmp_path: Path, project_surface: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The entry is placed in a manifest of its own under a copy of the
    checkout and compiled through `capability_manifest.project_inputs` -- the
    same path `check --project` takes -- so "compiles" means what the product
    means by it: against the merged surface and the project's snapshot."""
    calls = scaffold_calls(project_surface)
    assert len(calls) >= 2, "the example project publishes a relation and an RPC"

    checkout = tmp_path / "checkout"
    shutil.copytree(EXAMPLE_SET, checkout / "projects" / "example")
    manifest = config.load_project_manifest(EXAMPLE_MANIFEST)
    head = agent("init", "--head")
    assert head.returncode == 0, head.stderr

    compiled_names: list[str] = []
    for call in calls:
        result = agent("init", "--project", str(EXAMPLE_MANIFEST), *call)
        assert result.returncode == 0, result.stderr
        assert result.stdout.startswith("  - name: "), result.stdout
        (checkout / "projects" / "example" / "capabilities.yaml").write_text(
            head.stdout + result.stdout, encoding="utf-8"
        )
        inputs = capability_manifest.project_inputs(manifest, repo_root=checkout)
        assert inputs is not None
        contract = capability_manifest.compile_project_contract(inputs)
        assert contract["capability_count"] == 1
        compiled_names.append(contract["tools"][0]["name"])
        entry = yaml.safe_load(result.stdout)[0]
        assert entry["kind"] == ("read" if call[1] in project_surface["relations"] else "write")
        if entry["kind"] == "write":
            assert entry["requires_approval"] is True and entry["supports_dry_run"] is True
            assert entry["audit"]["redact"] == project_surface["rpcs"][call[1]]["arguments"]
            assert entry["required_scopes"] == [f"{call[3]}:write"]
        else:
            assert entry["tool"] == "query_resource"
            assert entry["columns"] == project_surface["relations"][call[1]]["columns"]
            assert entry["filters"] == [] and entry["order_by"] == []
            assert entry["required_scopes"] == [f"{call[1]}:read"]
    assert compiled_names == ["query_resource", *sorted(project_surface["rpcs"])]


def test_init_writes_no_file_and_prints_the_manifests_head_on_request() -> None:
    before = sorted(p.name for p in EXAMPLE_SET.iterdir())
    result = agent("init", "--project", str(EXAMPLE_MANIFEST), "--operation", "note_embeddings")
    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in EXAMPLE_SET.iterdir()) == before

    head = agent("init", "--head")
    assert head.returncode == 0
    lines = head.stdout.splitlines()
    assert lines[0] == "# yaml-language-server: $schema=../../schemas/capabilities.schema.json"
    assert lines[-2:] == ["schema_version: 4", "capabilities:"]
    assert (REPO_ROOT / "schemas" / "capabilities.schema.json").is_file()
    # And the head with no entries is a manifest the loader accepts as empty.
    assert yaml.safe_load(head.stdout) == {"schema_version": 4, "capabilities": None}


# ---------------------------------------------------------------------------
# What it refuses
# ---------------------------------------------------------------------------


def test_init_refuses_an_operation_the_merged_surface_does_not_name() -> None:
    result = agent("init", "--project", str(EXAMPLE_MANIFEST), "--operation", "snippets")
    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert "names no operation 'snippets'" in result.stderr
    for name in ("note_embeddings", "set_note_embedding", "notes", "create_note"):
        assert name in result.stderr, f"the refusal does not name {name}"
    assert "mcp_agent_context" not in result.stderr, "an agent-plane operation is not offered"


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("--operation", "notes"), "release's own object"),
        (("--operation", "mcp_agent_context", "--relation", "notes"), "agent-plane operation"),
        (("--operation", "set_note_embedding"), "name the relation it writes"),
        (("--operation", "set_note_embedding", "--relation", "snippets"), "not a relation"),
        (("--operation", "note_embeddings", "--kind", "write"), "--kind write does not apply"),
        (("--operation", "note_embeddings", "--relation", "notes"), "--relation does not apply"),
    ],
    ids=[
        "release-object",
        "agent-rpc",
        "write-without-relation",
        "bad-relation",
        "kind",
        "relation-on-a-read",
    ],
)
def test_init_refuses_the_shapes_the_compiler_or_the_join_would(
    arguments: tuple[str, ...], message: str
) -> None:
    result = agent("init", "--project", str(EXAMPLE_MANIFEST), *arguments)
    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert message in result.stderr


def test_init_needs_a_set_to_scaffold_from() -> None:
    """Exit 3, the prerequisite code: the second fixture has no migration set,
    so there is no merged surface and nothing of its own to open."""
    result = agent("init", "--project", str(SECOND_MANIFEST), "--operation", "notes")
    assert result.returncode == 3, result.stderr
    assert "declares no migrations.set" in result.stderr
    bare = agent()
    assert bare.returncode == 2


# ---------------------------------------------------------------------------
# The shipped example is what the scaffold writes
# ---------------------------------------------------------------------------


def test_the_example_manifest_is_what_the_scaffold_emits() -> None:
    """Byte for byte: `init --head`, the read, the write. A shipped example
    that drifted from the scaffold would document a shape the product does
    not write; the battery's first mutation (approval withdrawn in the
    scaffold) is what this test exists to catch."""
    head = agent("init", "--head")
    read = agent("init", "--project", str(EXAMPLE_MANIFEST), "--operation", "note_embeddings")
    write = agent(
        "init",
        "--project",
        str(EXAMPLE_MANIFEST),
        "--operation",
        "set_note_embedding",
        "--relation",
        "note_embeddings",
    )
    for result in (head, read, write):
        assert result.returncode == 0, result.stderr
    committed = (EXAMPLE_SET / "capabilities.yaml").read_bytes()
    assert committed == (head.stdout + read.stdout + write.stdout).encode("utf-8")

    # And the committed contract is what that manifest compiles to: the
    # product's own check, exit 0, naming the joint contract.
    result = contract_cli("check", "--project", str(EXAMPLE_MANIFEST))
    assert result.returncode == 0, result.stderr
    assert "compiles to its approved contract" in result.stdout
    assert "notes-tasks-agent-v1+example-note-embeddings-agent-v1" in result.stdout


def test_the_example_projects_manifest_compiles_to_its_committed_contract() -> None:
    """`AGT-TENANT-001`'s first node id, on the shipped example rather than a
    hand-built manifest: the committed contract's bytes are what the project's
    manifest compiles to, and its id derives from the project's surface."""
    manifest = config.load_project_manifest(EXAMPLE_MANIFEST)
    inputs = capability_manifest.project_inputs(manifest)
    assert inputs is not None
    contract = capability_manifest.compile_project_contract(inputs)
    path = capability_manifest.project_contract_path(inputs.root)
    assert path.read_bytes() == capability_compiler.canonical_bytes(contract)
    assert contract["contract_id"] == "example-note-embeddings-agent-v1"
    assert [t["name"] for t in contract["tools"]] == ["query_resource", "set_note_embedding"]

    streamed = contract_cli("compile", "--project", str(EXAMPLE_MANIFEST))
    assert streamed.returncode == 0, streamed.stderr
    assert streamed.stdout.encode("utf-8") == path.read_bytes()
