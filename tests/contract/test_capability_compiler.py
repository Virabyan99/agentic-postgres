"""The capability compiler (ADR 0119, ADR 0120), and the rule it exists to keep.

**`AGT-DRIFT-001` is the load-bearing test here** and it is written the only way
that means anything: it *adds an operation* to both the reviewed surface and the
approved snapshot, recompiles, and asserts the tool set did not move. A test
asserting that the compiler "does not iterate OpenAPI" would be asserting the
absence of a loop, which any refactor could reintroduce while the test stayed
green — the shape D277 names, where an AST scan asking whether a function is
*mentioned* is satisfied by dead code.

Nothing here reaches a database or a network. The compiler is pure over its
arguments for that reason, and the capture is `bin/mcp-contract.py`'s business.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, api_surface, capability_compiler, config, openapi_normalize
from agentic_postgres.capability_compiler import CompilerError

pytestmark = [pytest.mark.contract, pytest.mark.p0]

CANONICAL = REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
SNAPSHOT = REPO_ROOT / "contracts" / "postgrest-openapi.canonical.json"
MANIFEST = REPO_ROOT / "capabilities.example.yaml"


@pytest.fixture(scope="module")
def capabilities() -> dict[str, Any]:
    return config.load_capabilities_manifest(MANIFEST)


@pytest.fixture(scope="module")
def surface() -> dict[str, Any]:
    return api_surface.load_surface()


@pytest.fixture(scope="module")
def published() -> set[str]:
    return openapi_normalize.declared_objects(json.loads(SNAPSHOT.read_text("utf-8")))


@pytest.fixture(scope="module")
def canonical(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> dict[str, Any]:
    return capability_compiler.compile_canonical(
        capabilities=capabilities, surface=surface, published_objects=published
    )


def compile_with(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> dict[str, Any]:
    return capability_compiler.compile_canonical(
        capabilities=copy.deepcopy(capabilities),
        surface=copy.deepcopy(surface),
        published_objects=set(published),
    )


# ---------------------------------------------------------------------------
# The derivation (ADR 0119)
# ---------------------------------------------------------------------------


def test_the_operation_id_is_derived_the_one_way() -> None:
    """One function, one spelling, both sides of every comparison.

    `/` becomes `.` because the schema's pattern permits neither `/` nor `:` --
    a constraint rather than a preference, and the reason the id is not the
    wire's spelling.
    """
    assert capability_compiler.derive_operation_id("notes", "GET") == "notes.get"
    assert capability_compiler.derive_operation_id("rpc/create_note", "post") == (
        "rpc.create_note.post"
    )
    with pytest.raises(CompilerError):
        capability_compiler.derive_operation_id("", "get")


def test_no_derived_id_could_have_been_copied_from_the_document() -> None:
    """**The measurement this ADR rests on, asserted against the artefact.**

    PostgREST publishes no `operationId` anywhere -- measured on the live locked
    image, Swagger 2.0, every operation without one. So a capability's
    `operation_id` cannot be a copy of anything the document carries, and this
    asserts the premise rather than leaving it in a comment where a reader could
    not tell it from a guess (D267).
    """
    document = json.loads(SNAPSHOT.read_text("utf-8"))
    carried = [
        f"{method} {path}"
        for path, operations in document["paths"].items()
        for method, operation in operations.items()
        if isinstance(operation, dict) and operation.get("operationId")
    ]
    assert not carried, (
        f"the approved snapshot carries operationIds {carried}. If the source publishes "
        "them, a derived id is a second authority for a name the document already has"
    )


def test_every_derived_id_resolves_against_the_reviewed_contract(
    surface: dict[str, Any],
) -> None:
    """The reviewed contract is the authority, not the served document (ADR 0050).

    Both `agent_rpcs` entries appear here and neither appears in the snapshot,
    which is the whole of ADR 0118 -- and it is why the contract, not the
    document, is what a capability resolves against.
    """
    operations = capability_compiler.surface_operations(surface)
    assert "notes.get" in operations
    assert "rpc.create_note.post" in operations
    assert "rpc.owner_activity_report.post" in operations
    assert "rpc.mcp_agent_context.get" in operations

    assert operations["notes.get"]["published"] is True
    assert operations["rpc.owner_activity_report.post"]["published"] is False


# ---------------------------------------------------------------------------
# Five capabilities, four tools (ADR 0120)
# ---------------------------------------------------------------------------


def test_the_compiled_tools_are_the_four_that_were_planned(canonical: dict[str, Any]) -> None:
    """`docs/capability-plan.md` named these in Session 1. This is where they meet.

    `PLANNED_TOOLS` is a constant rather than a derivation on purpose: the
    compiler derives the tool set from the manifest, so a test comparing the two
    derivations would be comparing a function against itself -- the shape Session
    7 Run 7's M8 records, where both constants held the same number.
    """
    names = tuple(tool["name"] for tool in canonical["tools"])
    assert names == capability_compiler.PLANNED_TOOLS
    assert names == tuple(sorted(names)), "the tools are not lexicographic"
    assert canonical["tool_count"] == 4
    assert canonical["capability_count"] == 5


def test_one_tool_carries_two_resources_with_a_scope_each(canonical: dict[str, Any]) -> None:
    """ADR 0120's substance: the "or" in "notes:read or tasks:read".

    Two capabilities, one tool, and each resource keeps its OWN requirement. A
    tool that pooled them would authorize `notes` on the strength of
    `tasks:read`, which is what a flattened scope list means.
    """
    query = next(tool for tool in canonical["tools"] if tool["name"] == "query_resource")
    resources = {resource["name"]: resource for resource in query["resources"]}
    assert set(resources) == {"notes", "tasks"}
    assert resources["notes"]["required_scopes"] == ["notes:read"]
    assert resources["tasks"]["required_scopes"] == ["tasks:read"]
    assert resources["notes"]["capability"] == "query_notes"
    assert resources["tasks"]["capability"] == "query_tasks"


def test_discovery_is_a_disjunction_of_conjunctions(canonical: dict[str, Any]) -> None:
    """**The distinction a flat scope list cannot carry.**

    `query_resource` is `notes:read` OR `tasks:read`; `run_report` is
    `notes:read` AND `tasks:read`. Flattened, both are the same two strings --
    and an agent holding only `notes:read` would be shown `run_report` and
    refused when it called it, which is a tool list that lies.

    Goes red if: the sets are collapsed into one union; or `run_report`'s
    conjunction is split into two sets, which would advertise it to an agent
    holding half of what it needs.
    """
    tools = {tool["name"]: tool for tool in canonical["tools"]}

    assert tools["query_resource"]["discovery_scope_sets"] == [["notes:read"], ["tasks:read"]]
    assert tools["run_report"]["discovery_scope_sets"] == [["notes:read", "tasks:read"]]
    assert tools["list_resources"]["discovery_scope_sets"] == [["meta:read"]]

    # And the two are genuinely different documents, not two spellings of one.
    flattened = {
        name: sorted({scope for scopes in tool["discovery_scope_sets"] for scope in scopes})
        for name, tool in tools.items()
    }
    assert flattened["query_resource"] == flattened["run_report"], (
        "the premise of this test is that these two FLATTEN to the same thing; if they no "
        "longer do, the distinction below is being carried by something else"
    )
    assert (
        tools["query_resource"]["discovery_scope_sets"]
        != tools["run_report"]["discovery_scope_sets"]
    )


def test_a_metadata_tool_reaches_no_backend(canonical: dict[str, Any]) -> None:
    """ADR 0120: `list_resources` and `describe_resource` answer from the lock.

    No `resources`, no `max_rows`, and `source: lock` -- which is not a service.
    The schema forbids the fields; this asserts the compiled artefact agrees,
    because a schema rule the compiler ignores is a rule about a file rather
    than about the thing the runtime obeys.
    """
    for name in ("list_resources", "describe_resource"):
        tool = next(tool for tool in canonical["tools"] if tool["name"] == name)
        assert tool["kind"] == "metadata"
        assert tool["source"] == "lock"
        assert tool["reads"] == "lock"
        assert "resources" not in tool
        assert "max_rows" not in tool


# ---------------------------------------------------------------------------
# AGT-DRIFT-001 -- the rule the compiler exists to keep
# ---------------------------------------------------------------------------


def test_a_new_api_operation_exposes_no_capability(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> None:
    """**AGT-DRIFT-001, and the reason it is written this way.**

    A new operation is added to BOTH the reviewed surface contract and the
    approved OpenAPI snapshot -- so it is reviewed, published and real, exactly
    as a genuinely added endpoint would be. The compiler is then run again, and
    the compiled contract must be **byte-identical**.

    This is deliberately not a test that the compiler "does not iterate OpenAPI".
    That would assert the absence of a loop, which a refactor can reintroduce
    while the assertion stays green -- D277's shape, where a scan asking whether
    a name is *mentioned* is satisfied by dead code. What is asserted here is
    what the compiler PRODUCES.

    Goes red if: the compiler ever enumerates the document or the contract to
    discover a capability. It cannot go red for any other reason, because the
    manifest is untouched.
    """
    before = capability_compiler.canonical_bytes(compile_with(capabilities, surface, published))

    widened = copy.deepcopy(surface)
    widened["relations"]["invoices"] = {
        "kind": "view",
        "methods": ["GET", "HEAD"],
        "columns": ["id", "owner_id", "total"],
    }
    widened["rpcs"]["settle_invoice"] = {"methods": ["POST"], "arguments": ["p_invoice_id"]}
    after = capability_compiler.canonical_bytes(
        compile_with(capabilities, widened, published | {"invoices", "rpc/settle_invoice"})
    )

    assert after == before, (
        "adding an operation to the reviewed surface and to the published document changed "
        "the compiled capability contract. The agent surface is decided by "
        "capabilities.yaml and by nothing else (AGT-DRIFT-001)"
    )


def test_the_manifest_is_what_moves_the_contract(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> None:
    """The control for the test above, and it is not optional.

    If the compiled contract were insensitive to *everything*, the drift test
    would pass against a compiler that returned a constant. Disabling one
    capability must change the output, and by exactly one tool.
    """
    before = compile_with(capabilities, surface, published)

    narrowed = copy.deepcopy(capabilities)
    for entry in narrowed["capabilities"]:
        if entry["name"] == "run_report":
            entry["enabled"] = False
    after = compile_with(narrowed, surface, published)

    assert after["tool_count"] == before["tool_count"] - 1
    assert "run_report" not in {tool["name"] for tool in after["tools"]}
    assert capability_compiler.canonical_bytes(after) != capability_compiler.canonical_bytes(before)


# ---------------------------------------------------------------------------
# What the compiler refuses
# ---------------------------------------------------------------------------


def test_an_operation_the_reviewed_contract_does_not_name_is_refused(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> None:
    """The contract is the authority (ADR 0050), so this is where a typo stops."""
    broken = copy.deepcopy(capabilities)
    for entry in broken["capabilities"]:
        if entry["name"] == "query_notes":
            entry["operation"]["operation_id"] = "notes.delete"

    with pytest.raises(CompilerError, match="reviewed surface contract does not permit"):
        compile_with(broken, surface, published)


def test_a_column_the_reviewed_relation_does_not_publish_is_refused(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> None:
    """A frozen allowlist that names an unreviewed column is one nobody reviewed."""
    broken = copy.deepcopy(capabilities)
    for entry in broken["capabilities"]:
        if entry["name"] == "query_notes":
            entry["columns"] = [*entry["columns"], "password_hash"]

    with pytest.raises(CompilerError, match="password_hash"):
        compile_with(broken, surface, published)


def test_a_filter_on_an_unreviewed_column_is_refused(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> None:
    """Filters are a second way to name a column, and were nearly a second gap."""
    broken = copy.deepcopy(capabilities)
    for entry in broken["capabilities"]:
        if entry["name"] == "query_tasks":
            entry["filters"] = [*entry["filters"], {"column": "secret", "operators": ["eq"]}]

    with pytest.raises(CompilerError, match="filtering on"):
        compile_with(broken, surface, published)


def test_an_agent_plane_operation_that_became_published_is_refused(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> None:
    """ADR 0118, checked from the compiler as well as from the contract tests.

    If `api_documentation` were granted EXECUTE and a capture approved, the
    agent-plane RPC would appear in the snapshot -- and the capability backed by
    it would be describing a published surface. The compiler refuses to compile
    a lock over that state rather than compiling one that is quietly wrong.
    """
    with pytest.raises(CompilerError, match="PUBLISHES"):
        compile_with(capabilities, surface, published | {"rpc/owner_activity_report"})


def test_a_published_operation_missing_from_the_snapshot_is_refused(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> None:
    """The other direction: reviewed and published, and the document has neither."""
    with pytest.raises(CompilerError, match="approved OpenAPI snapshot does not"):
        compile_with(capabilities, surface, published - {"notes"})


def test_capabilities_sharing_a_tool_must_share_a_kind(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> None:
    """One name with two authorization models is two tools wearing one label."""
    broken = copy.deepcopy(capabilities)
    for entry in broken["capabilities"]:
        if entry["name"] == "query_tasks":
            entry["kind"] = "write"
            entry["max_affected_rows"] = 1
            entry["idempotent"] = True

    with pytest.raises(CompilerError, match="two authorization models"):
        compile_with(broken, surface, published)


# ---------------------------------------------------------------------------
# The committed artefact
# ---------------------------------------------------------------------------


def test_the_committed_contract_is_what_the_manifest_compiles_to(
    canonical: dict[str, Any],
) -> None:
    """The offline half of `bin/mcp-contract.sh check`, run by the gate.

    Byte-for-byte, because a comparison of parsed documents is equal for two
    files whose formatting differs -- and the committed file is the one a human
    reviewed.
    """
    assert CANONICAL.is_file(), f"no approved contract at {CANONICAL}"
    assert capability_compiler.canonical_bytes(canonical) == CANONICAL.read_bytes(), (
        "the capability manifest no longer compiles to the committed contract. Either the "
        "manifest changed and the contract was not re-approved, or the reviewed API surface "
        "moved underneath it"
    )


def test_the_check_command_contains_no_writer() -> None:
    """ADR 0050's rule, applied to this compiler: a gate cannot approve its subject.

    Asserted on the source, like `api_surface.test_the_module_cannot_write_a_contract`:
    the `check` path may not contain a write call at all. A command that could
    write the file it compares against is one that can make its own comparison
    pass.
    """
    source = (REPO_ROOT / "bin" / "mcp-contract.py").read_text("utf-8")
    start = source.index("def command_check")
    body = source[start : source.index("\ndef ", start + 1)]
    for forbidden in ("write_text", "write_bytes", "open(", "unlink", "rename"):
        assert forbidden not in body, f"the check path calls {forbidden}"


def test_check_exits_zero_against_the_committed_tree() -> None:
    """The command itself, executed. Reading its source is not running it."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "bin" / "mcp-contract.py"), "check"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        timeout=120,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "4 tools" in result.stdout


def test_the_lock_carries_the_digests_of_everything_it_was_compiled_from(
    canonical: dict[str, Any],
) -> None:
    """A lock whose inputs cannot be identified is a surface nobody can prove was reviewed.

    That is the failure `capabilities.yaml` exists to prevent, and the plan's §4
    names it as one of the four irreversible operations: *"a lock built from an
    unreviewed OpenAPI capture is a capability surface nobody approved."*
    """
    lock = capability_compiler.compile_lock(
        canonical=canonical,
        project_key="fixture-alpha-dev",
        upstream="https://fixture-alpha-dev.test/api/rest",
        sources={
            "capabilities_sha256": "a" * 64,
            "api_surface_sha256": "b" * 64,
            "canonical_openapi_sha256": "c" * 64,
        },
    )
    assert set(lock["compiled_from"]) == {
        "capabilities_sha256",
        "api_surface_sha256",
        "canonical_openapi_sha256",
    }
    assert (
        lock["canonical_sha256"]
        == __import__("hashlib").sha256(capability_compiler.canonical_bytes(canonical)).hexdigest()
    )
    assert lock["tools"] == canonical["tools"]

    with pytest.raises(CompilerError, match="api_surface_sha256"):
        capability_compiler.compile_lock(
            canonical=canonical,
            project_key="fixture-alpha-dev",
            upstream="https://fixture-alpha-dev.test/api/rest",
            sources={"capabilities_sha256": "a" * 64, "canonical_openapi_sha256": "c" * 64},
        )


def test_the_canonical_contract_names_no_project(canonical: dict[str, Any]) -> None:
    """Project-neutral by construction, because the domain is (ADR 0050).

    Two projects compile the same bytes, which is what lets one file be reviewed
    once. The lock is where a project's own address arrives, and nowhere else.
    """
    text = capability_compiler.canonical_bytes(canonical).decode("utf-8")
    import yaml

    for manifest in ("project.example.yaml", "project.second.example.yaml"):
        project = yaml.safe_load((REPO_ROOT / manifest).read_text("utf-8"))["project"]
        assert project["slug"] not in text, manifest
        assert project["domain"] not in text, manifest
    assert "https://" not in text, "the canonical contract carries a URL"
