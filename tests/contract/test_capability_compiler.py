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
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import (
    REPO_ROOT,
    api_surface,
    capability_compiler,
    config,
    deployed_output,
    openapi_normalize,
)
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
# Seven capabilities, six tools (ADR 0120)
# ---------------------------------------------------------------------------


def test_the_compiled_tools_are_the_six_that_were_planned(canonical: dict[str, Any]) -> None:
    """`docs/capability-plan.md` named all six in Session 1. This is where they meet.

    Four since Session 8; Session 9 Run 3 added the two writes the plan's rows
    5 and 6 had reserved for it. The counts moved with them: seven capabilities
    behind six tools.

    `PLANNED_TOOLS` is a constant rather than a derivation on purpose: the
    compiler derives the tool set from the manifest, so a test comparing the two
    derivations would be comparing a function against itself -- the shape Session
    7 Run 7's M8 records, where both constants held the same number.
    """
    names = tuple(tool["name"] for tool in canonical["tools"])
    assert names == capability_compiler.PLANNED_TOOLS
    assert names == tuple(sorted(names)), "the tools are not lexicographic"
    assert canonical["tool_count"] == 6
    assert canonical["capability_count"] == 7


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
# The two writes (Session 9 Run 3): D470, D479, D487
# ---------------------------------------------------------------------------


def test_a_write_tool_is_an_operation_and_an_argument_contract(canonical: dict[str, Any]) -> None:
    """**D470's resolution, asserted on the artefact.**

    A write compiles to an operation, an argument contract and a side-effect
    bound -- and to no `columns`, `filters`, `order_by`, `max_rows` or
    `resources`, because a write projects nothing. The arguments are the
    reviewed contract's, **in PostgreSQL parameter order**: they are positional
    facts about a function, and sorting them would be a second spelling of a
    list one authority already owns.
    """
    expected = {
        "create_note": ("rpc.create_note.post", ["p_title", "p_content"]),
        "update_task_status": (
            "rpc.update_task_status.post",
            ["p_task_id", "p_expected_status", "p_new_status"],
        ),
    }
    for name, (operation_id, arguments) in expected.items():
        tool = next(tool for tool in canonical["tools"] if tool["name"] == name)
        assert tool["kind"] == "write"
        assert tool["source"] == "postgrest"
        assert tool["operation"]["operation_id"] == operation_id
        assert tool["operation"]["method"] == "post"
        assert tool["arguments"] == arguments, "the argument contract is not in parameter order"
        for field in ("resources", "columns", "filters", "order_by", "max_rows"):
            assert field not in tool, f"write tool {name!r} carries the read field {field!r}"


def test_the_write_bound_is_the_functions_own_shape(canonical: dict[str, Any]) -> None:
    """**D487.** `max_affected_rows` is 1 on both writes, and 1 is not a choice.

    Both RPCs are `RETURNS api.notes` / `RETURNS api.tasks` -- a single
    composite row, not `SETOF` -- so 1 is the function's actual shape. A bound
    larger than the operation can produce can never fire, which is a control
    measuring nothing.

    `idempotent` is stated honestly rather than defensively: `create_note`
    creates a row on every call; `update_task_status` is a compare-and-swap,
    so a repeat cannot advance the state twice.
    """
    tools = {tool["name"]: tool for tool in canonical["tools"]}
    assert tools["create_note"]["max_affected_rows"] == 1
    assert tools["update_task_status"]["max_affected_rows"] == 1
    assert tools["create_note"]["idempotent"] is False
    assert tools["update_task_status"]["idempotent"] is True


def test_audit_redaction_reaches_every_tool_and_one_list_is_non_empty(
    canonical: dict[str, Any],
) -> None:
    """**D479.** `audit.redact` was validated on the way in and emitted into nothing.

    Now every compiled tool carries its redaction list, and at least one is
    NON-empty -- `create_note` redacts `p_content`, the note's body -- because
    an empty redaction list on every capability is indistinguishable from a
    redaction mechanism that does not exist.
    """
    redactions = {tool["name"]: tool["audit_redact"] for tool in canonical["tools"]}
    assert set(redactions) == set(capability_compiler.PLANNED_TOOLS), (
        "a tool compiled without its redaction list; the runtime would have nothing to obey"
    )
    assert redactions["create_note"] == ["p_content"]
    assert any(redactions.values()), (
        "every redaction list is empty, which is D479's original state wearing new keys"
    )


def test_a_write_carrying_a_reads_shape_is_refused(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> None:
    """**D470's other half.** The schema does not forbid a write these fields --
    forbidding them there would be a version bump renaming nothing (D403) -- so
    the compiler must, or a `columns` list on a write validates, compiles into
    nothing, and reads exactly like a real projection (D274's shape).
    """
    for field, value in (
        ("resource", "notes"),
        ("columns", ["id"]),
        ("filters", [{"column": "id", "operators": ["eq"]}]),
        ("order_by", [{"column": "id", "direction": "asc"}]),
        ("max_rows", 10),
    ):
        broken = copy.deepcopy(capabilities)
        for entry in broken["capabilities"]:
            if entry["name"] == "create_note":
                entry[field] = value
        with pytest.raises(CompilerError, match="describe a read"):
            compile_with(broken, surface, published)


def test_a_write_backed_by_a_read_operation_is_refused(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> None:
    """A write whose backing is a GET is a tool whose kind lies about its effect.

    `notes.get` is a reviewed, published operation, so nothing upstream of the
    write branch refuses it -- which is exactly why the branch must.
    """
    broken = copy.deepcopy(capabilities)
    for entry in broken["capabilities"]:
        if entry["name"] == "create_note":
            entry["operation"]["operation_id"] = "notes.get"

    with pytest.raises(CompilerError, match="lies about its effect"):
        compile_with(broken, surface, published)


def test_an_unbacked_write_is_refused(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> None:
    """A write that reaches no backend is a side effect nobody can locate.

    `source: lock` is legitimate for a metadata capability and the schema does
    not couple sources to kinds, so the refusal is the compiler's.
    """
    broken = copy.deepcopy(capabilities)
    for entry in broken["capabilities"]:
        if entry["name"] == "create_note":
            entry["operation"] = {"source": "lock", "operation_id": "lock.resources.list"}

    with pytest.raises(CompilerError, match="unbacked source"):
        compile_with(broken, surface, published)


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
    """One name with two authorization models is two tools wearing one label.

    The turned capability is stripped of its read shape as well as re-kinded,
    because Session 9's write-shape refusal (D470) would otherwise fire first
    and this test would be re-measuring that check under this one's name.
    """
    broken = copy.deepcopy(capabilities)
    for entry in broken["capabilities"]:
        if entry["name"] == "query_tasks":
            entry["kind"] = "write"
            entry["max_affected_rows"] = 1
            entry["idempotent"] = True
            for field in ("resource", "columns", "filters", "order_by", "max_rows"):
                entry.pop(field, None)
            entry["operation"]["operation_id"] = "rpc.update_task_status.post"

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
    assert "6 tools" in result.stdout


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


# ---------------------------------------------------------------------------
# D465 -- the lock is compiled from the RENDERED branch, and the other is refused
# ---------------------------------------------------------------------------


def test_the_lock_is_compiled_from_the_rendered_document_not_the_deployed_one() -> None:
    """**D465.** Two errors lived in one comment, and both reached a host.

    It said *"the document THIS deploy is about to write … rather than from the
    previous deploy's"* and passed `deployed_path`. That document is the previous
    deploy's — step 7 writes the new one long afterwards — **and** the two
    branches carry `routes.rest` in different shapes: a string when rendered, a
    published-route object when deployed.

    So the compiler read an object where it wanted a URL, wrote a lock whose
    `upstream` was a dict, and the agent plane refused it at container start.
    **D389's shape**: one field, two branches, a consumer reading the wrong one.
    """
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    lock_call = source[source.index('"mcp-contract.sh"') :]
    lock_call = lock_call[: lock_call.index("lock_path.write_text")]

    assert 'rendered_path(key) / "outputs.json"' in lock_call, (
        "the lock is not compiled from the rendered document"
    )
    assert "deployed_path" not in lock_call, (
        "the lock is compiled from the DEPLOYED document, whose routes.rest is a "
        "published-route object rather than the URL the compiler wants (D465)"
    )


def test_the_two_branches_really_do_carry_routes_rest_differently() -> None:
    """The premise of the test above, asserted rather than assumed.

    If the two shapes ever converge, the test above becomes a rule with no
    reason behind it — and this is the arm that would say so. Read off the
    document builders rather than off a fixture, so it is a statement about the
    code and not about one render.
    """
    assert "published_route" in (
        REPO_ROOT / "src" / "agentic_postgres" / "deployed_output.py"
    ).read_text(encoding="utf-8")

    rendered = deployed_output.ROUTE_NOT_PUBLISHED
    assert set(rendered) == {"status", "url"}, (
        "the deployed branch no longer wraps a route in an object; D465's premise "
        "has changed and the rule above needs re-reading"
    )


def test_the_compiler_refuses_a_deployed_shaped_document_by_name(tmp_path: Path) -> None:
    """**The guard, and it is the half that matters next time.**

    The ordering fix stops *this* mistake. It does not stop the next caller from
    passing the wrong branch — and the failure mode was not an error, it was a
    **lock**: a published artefact whose defect surfaced four steps later inside
    a container. A wrong input that produces an artefact is worse than one that
    produces an error.

    Three arms, and the third is the CONTROL: the rendered shape must still
    compile, or the guard refuses everything and is worth nothing.
    """
    import json

    def document(rest: object) -> Path:
        path = tmp_path / f"outputs-{abs(hash(json.dumps(rest, sort_keys=True)))}.json"
        path.write_text(
            json.dumps({"project": {"key": "probe-dev"}, "routes": {"rest": rest}}),
            encoding="utf-8",
        )
        return path

    def compile_from(path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "bin" / "mcp-contract.py"),
                # `--capabilities` is a GLOBAL option and precedes the
                # subcommand. After it, argparse reports "unrecognized
                # arguments" and exits **2** -- which a test asserting merely
                # "non-zero" would have accepted as the refusal it was looking
                # for. That is why both refusal arms below check the MESSAGE.
                "--capabilities",
                str(REPO_ROOT / "capabilities.example.yaml"),
                "lock",
                "--outputs",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=REPO_ROOT,
        )

    deployed = compile_from(document({"status": "ready", "url": "https://x.test/api/rest"}))
    assert deployed.returncode != 0, "a deployed-shaped document compiled a lock"
    assert "DEPLOYED document" in deployed.stderr, deployed.stderr

    absent = compile_from(document(None))
    assert absent.returncode != 0
    assert "routes.rest is NoneType" in absent.stderr, absent.stderr

    # THE CONTROL. Without it, both arms are satisfied by a guard that refuses
    # every document it is given.
    ok = compile_from(document("https://x.test/api/rest"))
    assert ok.returncode == 0, f"the rendered shape no longer compiles: {ok.stderr}"
    assert '"upstream"' in ok.stdout


# ---------------------------------------------------------------------------
# Schema version 2: a version, a lifecycle and a risk (ADR 0177)
# ---------------------------------------------------------------------------


def v1_manifest(capabilities: dict[str, Any]) -> dict[str, Any]:
    """The same manifest as schema version 1: the three fields removed.

    A v1 manifest still has to compile, because `capabilities.yaml` is a
    gitignored operator input that exists only on the host and no commit can
    edit it. This is what that claim is checked against.
    """
    document = copy.deepcopy(capabilities)
    document["schema_version"] = 1
    for entry in document["capabilities"]:
        for field in capability_compiler.VERSIONED_FIELDS:
            entry.pop(field, None)
    return document


def test_the_compiled_version_is_the_manifests_not_a_constant(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> None:
    """D882. `SCHEMA_VERSION = 1` was right while there was one manifest shape.

    There are two now, and the compiled tool's shape is a function of which one
    it came from -- a v2 manifest produces tools carrying `capabilities` and
    `risk`, a v1 manifest produces the tools it always did. A fixed number on a
    document whose shape varies is a version that describes nothing.
    """
    at_two = compile_with(capabilities, surface, published)
    assert at_two["schema_version"] == 2

    at_one = compile_with(v1_manifest(capabilities), surface, published)
    assert at_one["schema_version"] == 1

    # The control: the two really are different documents, so the version is
    # tracking something. Equal shapes would make the assertion above vacuous.
    assert at_one["tools"] != at_two["tools"]


def test_a_v1_manifest_compiles_without_the_fields_rather_than_with_nulls(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> None:
    """D600's rule at the contract's edge.

    A `risk: null` on every tool would say this deployment classifies its
    capabilities and declined to, which is the reverse of the truth. The keys
    are absent, and a runtime can therefore tell the two states apart -- which
    is exactly what `mcp_lock` refuses a v1 lock carrying them for.
    """
    compiled = compile_with(v1_manifest(capabilities), surface, published)

    assert compiled["tools"], "the control: a v1 manifest compiled to nothing"
    for tool in compiled["tools"]:
        assert "risk" not in tool, f"{tool['name']} carries risk at schema version 1"
        assert "capabilities" not in tool, f"{tool['name']} carries capabilities at v1"


def test_every_tool_carries_its_backing_capabilities_and_the_riskiest_of_them(
    canonical: dict[str, Any],
) -> None:
    """A tool has no single version, and `query_resource` is why (ADR 0120).

    Two authorizations behind one name, able to move independently, so the list
    is the authority. `risk` is the one aggregate, because it is the only one of
    the three with an ordering and a defensible worst case: a tool is as
    dangerous as the most dangerous thing behind it.
    """
    by_name = {tool["name"]: tool for tool in canonical["tools"]}

    grouped = by_name["query_resource"]
    assert [entry["name"] for entry in grouped["capabilities"]] == [
        "query_notes",
        "query_tasks",
    ], "the grouped tool no longer names both authorizations"

    for tool in canonical["tools"]:
        declared = tool["capabilities"]
        assert declared, f"{tool['name']} names no backing capability"
        for entry in declared:
            assert set(entry) == {"name", *capability_compiler.VERSIONED_FIELDS}
        expected = max(
            (entry["risk"] for entry in declared), key=capability_compiler.RISK_ORDER.index
        )
        assert tool["risk"] == expected, (
            f"{tool['name']} declares risk {tool['risk']!r} over backing risks "
            f"{[entry['risk'] for entry in declared]}"
        )


def test_the_tool_takes_the_riskiest_of_its_capabilities_not_the_first(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> None:
    """D884. The shipped manifest cannot tell `max` from `[0]`, so this builds a case that can.

    Every capability in `capabilities.example.yaml` shares its tool's risk --
    `query_notes` and `query_tasks` are both `low` -- so a compiler taking the
    FIRST backing risk produces an identical contract, and a mutation replacing
    `max(...)` with `declared[0]` **survived** the test above. An uninformative
    mutation pointing at a real gap (D493): the aggregate is the only derivation
    this run adds, and nothing reached it with inputs that disagree.

    A read may be any risk, so raising one half of the grouped tool is a legal
    manifest rather than a contrivance. Both orderings are compiled, because
    taking the first would be right by accident in one of them.
    """
    for raised in ("query_notes", "query_tasks"):
        document = copy.deepcopy(capabilities)
        for entry in document["capabilities"]:
            if entry["name"] == raised:
                entry["risk"] = "high"

        compiled = compile_with(document, surface, published)
        grouped = next(tool for tool in compiled["tools"] if tool["name"] == "query_resource")
        backing = {entry["name"]: entry["risk"] for entry in grouped["capabilities"]}

        assert backing[raised] == "high"
        assert set(backing.values()) == {"low", "high"}, (
            f"the two capabilities agree ({backing}), so this case cannot tell the "
            "riskiest from the first"
        )
        assert grouped["risk"] == "high", (
            f"{raised} is high and the tool reports {grouped['risk']!r}; a tool is as "
            "dangerous as the most dangerous thing behind it"
        )


def test_a_retired_capability_may_not_be_enabled(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> None:
    """ADR 0177, and it is an existing decision reached by a declaration.

    `compile_canonical` already drops disabled capabilities entirely -- "a
    runtime that received them would have to be trusted to ignore them, and the
    lock is meant to be the thing that cannot be argued with". Retirement is
    that rule, so the enforcement is the lock's ABSENCE rather than a runtime
    check somebody could forget to apply.
    """
    retired = copy.deepcopy(capabilities)
    retired["capabilities"][0]["lifecycle"] = "retired"
    name = retired["capabilities"][0]["name"]

    with pytest.raises(CompilerError, match="retired"):
        compile_with(retired, surface, published)

    # Retired AND disabled is the state the refusal exists to allow. Checked
    # before the `enabled` filter for exactly this reason: afterwards the two
    # are indistinguishable, and a compiler that refused both would make
    # retirement unreachable.
    retired["capabilities"][0]["enabled"] = False
    compiled = compile_with(retired, surface, published)
    assert all(
        name not in [entry["name"] for entry in tool["capabilities"]] for tool in compiled["tools"]
    ), f"{name} is retired and disabled and still reached the contract"


def test_a_deprecated_capability_still_compiles_and_says_so(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> None:
    """The second state has to be reachable or the first one is the only one.

    A lifecycle that refused a deprecated call would make the word mean
    `retired`, and then one of the two would name nothing. Deprecation is
    visible -- it travels into the lock and the catalog -- and callable.
    """
    document = copy.deepcopy(capabilities)
    document["capabilities"][0]["lifecycle"] = "deprecated"
    name = document["capabilities"][0]["name"]

    compiled = compile_with(document, surface, published)
    states = {
        entry["name"]: entry["lifecycle"]
        for tool in compiled["tools"]
        for entry in tool["capabilities"]
    }
    assert states[name] == "deprecated", "a deprecated capability lost its state on the way in"
    assert set(states.values()) == {"active", "deprecated"}, (
        f"the control: every capability reads {set(states.values())}, so this proves nothing"
    )


def test_the_compiler_refuses_a_manifest_version_it_does_not_produce_a_contract_for(
    capabilities: dict[str, Any], surface: dict[str, Any], published: set[str]
) -> None:
    """The version is read, not merely copied through into the output."""
    beyond = copy.deepcopy(capabilities)
    beyond["schema_version"] = max(capability_compiler.COMPILED_SCHEMA_VERSIONS) + 1

    with pytest.raises(CompilerError, match="schema_version"):
        compile_with(beyond, surface, published)


def test_each_schema_version_constant_matches_its_schemas_enum() -> None:
    """D881. One frozenset governed two documents, and they had to diverge.

    `validate_project_semantics` and `load_capabilities_manifest` both read
    `SUPPORTED_SCHEMA_VERSIONS`, so adding 2 for the capability manifest would
    have made the project check accept a project manifest declaring 2 -- which
    `project.schema.json` then refuses. Two authorities disagreeing about one
    document, and invisibly, because the schema runs first and wins.
    """
    pairs = (
        ("project.schema.json", config.SUPPORTED_PROJECT_SCHEMA_VERSIONS),
        ("capabilities.schema.json", config.SUPPORTED_CAPABILITIES_SCHEMA_VERSIONS),
    )
    for filename, constant in pairs:
        schema = json.loads((REPO_ROOT / "schemas" / filename).read_text("utf-8"))
        enum = schema["properties"]["schema_version"]["enum"]
        assert set(enum) == set(constant), (
            f"{filename} accepts {sorted(enum)} and the constant says {sorted(constant)}"
        )

    # The control: the two are not the same set, so a test comparing each
    # against the other's schema would fail. Without this, one constant serving
    # both would still pass.
    assert (
        config.SUPPORTED_PROJECT_SCHEMA_VERSIONS != config.SUPPORTED_CAPABILITIES_SCHEMA_VERSIONS
    ), "the two constants are equal again, which is the state D881 was about"
