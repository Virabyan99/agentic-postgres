"""The compiler: what a workflow definition may name, and what it may not.

**The lock these proofs compile against is the real one** -- the release's
approved contract joined with the example project's through
`capability_manifest.compile_joint_contract`, which is the function
`bin/mcp-contract.py lock` itself calls (D1114). Nothing here re-implements the
join, and nothing here hand-writes a tool: a compiler proved against a fixture
tool list is a compiler proved against a belief about the lock.

The load-bearing tests are the REFUSALS. A compiler that accepted everything
would pass a test that only showed the two shipped definitions compiling, so
each refusal in D1660's list has its own case, and `test_the_example_projects_
definitions_compile` is the control that the refusals are not simply a compiler
that refuses everything.

Nothing here reaches a database, a network or a container.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, capability_compiler
from agentic_postgres import workflow_definition as wd
from app import mcp_lock

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

EXAMPLE = REPO_ROOT / "project.example.yaml"
SECOND = REPO_ROOT / "project.second.example.yaml"
PROJECT_ROOT = REPO_ROOT / "projects" / "example"


@pytest.fixture(scope="module")
def lock() -> wd.LockView:
    """The example project's joint lock, computed the way `validate` computes it."""
    return wd.lock_view_for_project(EXAMPLE)


def definition(steps: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
    """A definition whose only interesting part is its steps."""
    document = {
        "schema_version": 1,
        "name": "probe",
        "version": 1,
        "description": "a probe definition",
        "steps": steps,
    }
    document.update(overrides)
    return document


def compile_it(document: dict[str, Any], lock: wd.LockView) -> wd.Compiled:
    return wd.compile(document, lock, source_sha256="0" * 64)


# ---------------------------------------------------------------------------
# The lock this compiler reads
# ---------------------------------------------------------------------------


def test_the_lock_view_and_the_runtime_agree_about_every_reads_shape(
    lock: wd.LockView, tmp_path: Any
) -> None:
    """**The one rule this module duplicates across the src/service boundary.**

    `ToolView.read_shape` is `mcp_lock.Tool.read_shape` written a second time,
    because `src/agentic_postgres` may not import the service package (ADR
    0093). A duplicated RULE is a divergence waiting to happen, so it is
    guarded rather than commented: the same lock is parsed by both readers and
    every tool's answer must agree.

    The control is in the assertion: at least one `relation` and at least one
    `rpc` must be found, or the comparison is over a set of `None`s and would
    agree about nothing.
    """
    document = _lock_document(EXAMPLE)
    path = tmp_path / "mcp-lock.json"
    path.write_bytes(capability_compiler.canonical_bytes(document))
    runtime = mcp_lock.load_lock(path)

    ours = {tool.name: tool.read_shape for tool in lock.tools}
    theirs = {tool.name: tool.read_shape for tool in runtime.tools}
    assert ours == theirs, (
        "the compiler and the runtime disagree about which reads are relations; "
        "this is the rule that decides which arguments a read step may carry"
    )
    assert set(ours.values()) >= {"relation", "rpc"}, (
        f"only {sorted(set(ours.values()), key=str)} were found, so this comparison "
        "proves nothing about the distinction it exists to hold"
    )


def _lock_document(manifest_path: Any) -> dict[str, Any]:
    """The lock as a document, built by the product's own chain.

    Spelled out here rather than exported from `workflow_definition` because
    this is the only caller that needs the document rather than the view.
    """
    from agentic_postgres import capability_manifest, config, naming, scope_registry

    manifest = config.load_project_manifest(manifest_path)
    inputs = capability_manifest.project_inputs(manifest)
    capabilities = config.load_capabilities_manifest(wd.DEFAULT_CAPABILITIES)
    canonical = capability_manifest.compile_joint_contract(capabilities, inputs)
    return capability_compiler.compile_lock(
        canonical=canonical,
        project_key=naming.project_key(
            manifest["project"]["slug"], manifest["project"]["environment"]
        ),
        upstream=wd.UNDEPLOYED_UPSTREAM,
        sources={
            "capabilities_sha256": "0" * 64,
            "api_surface_sha256": "0" * 64,
            "canonical_openapi_sha256": "0" * 64,
            "project_manifest_sha256": "0" * 64,
        },
        profile=manifest["mcp"]["profile"],
        vocabulary=scope_registry.vocabulary_block(inputs.surface),
    )


def test_the_recorded_lock_digest_does_not_depend_on_the_placeholder_address() -> None:
    """**The property `UNDEPLOYED_UPSTREAM` rests on.**

    A checkout has no rendered document, so `lock_view_for_project` puts an
    impossible address in the field a deployment would fill. That is only
    honest if the digest a definition RECORDS is unaffected by it -- otherwise
    `validate` would compile against one `lock_tools_sha256` and step 6d would
    install another, and the difference would be invisible.
    """
    first = _lock_document(EXAMPLE)
    second = copy.deepcopy(first)
    assert first["upstream"] == wd.UNDEPLOYED_UPSTREAM

    from agentic_postgres import capability_manifest, config, naming, scope_registry

    manifest = config.load_project_manifest(EXAMPLE)
    inputs = capability_manifest.project_inputs(manifest)
    capabilities = config.load_capabilities_manifest(wd.DEFAULT_CAPABILITIES)
    canonical = capability_manifest.compile_joint_contract(capabilities, inputs)
    second = capability_compiler.compile_lock(
        canonical=canonical,
        project_key=naming.project_key(
            manifest["project"]["slug"], manifest["project"]["environment"]
        ),
        upstream="https://a-real-looking-address.example/rest/v1",
        sources={
            "capabilities_sha256": "0" * 64,
            "api_surface_sha256": "0" * 64,
            "canonical_openapi_sha256": "0" * 64,
            "project_manifest_sha256": "0" * 64,
        },
        profile=manifest["mcp"]["profile"],
        vocabulary=scope_registry.vocabulary_block(inputs.surface),
    )
    assert first["upstream"] != second["upstream"]
    assert first["tools_sha256"] == second["tools_sha256"]


def test_a_lock_the_compiler_did_not_sign_is_refused() -> None:
    """A definition records what it compiled against; an unsigned list is not
    something anyone can say that about (ADR 0200)."""
    with pytest.raises(wd.DefinitionError, match="tools_sha256"):
        wd.LockView.from_json('{"tools": []}')


# ---------------------------------------------------------------------------
# The refusals of D1660
# ---------------------------------------------------------------------------


def test_a_capability_the_lock_does_not_serve_is_refused(lock: wd.LockView) -> None:
    with pytest.raises(wd.DefinitionError) as refused:
        compile_it(definition([{"name": "a", "capability": "no_such_thing@1.0.0"}]), lock)
    assert refused.value.step_name == "a"
    assert "compiles no capability named" in refused.value.reason
    # It names what there IS. A refusal that does not is a refusal an author
    # answers by guessing.
    assert "create_note@1.0.0" in refused.value.reason


def test_a_version_the_lock_does_not_carry_is_a_different_refusal(lock: wd.LockView) -> None:
    """*No such capability* and *that capability at another version* are
    different mistakes with different fixes, and folding them into one sends an
    author looking for a typo when the lock simply moved."""
    with pytest.raises(wd.DefinitionError) as refused:
        compile_it(definition([{"name": "a", "capability": "create_note@2.0.0"}]), lock)
    assert "carries create_note at 1.0.0, not at 2.0.0" in refused.value.reason


def test_a_tool_name_is_not_a_capability_reference(lock: wd.LockView) -> None:
    """`query_resource` is a TOOL and is backed by three capabilities here; a
    step that named it would not have said which one it means."""
    with pytest.raises(wd.DefinitionError) as refused:
        compile_it(definition([{"name": "a", "capability": "query_resource@1.0.0"}]), lock)
    assert "compiles no capability named 'query_resource'" in refused.value.reason


def test_a_capability_whose_lifecycle_is_not_active_is_refused(lock: wd.LockView) -> None:
    """A definition is stored and outlives the session that wrote it.

    The lock is mutated rather than a deprecated capability being waited for:
    the tree's own contract has none, and a proof that waits for one is a proof
    that has never run.
    """
    retired = _view_with(lock, "create_note", lifecycle="deprecated")
    with pytest.raises(wd.DefinitionError) as refused:
        compile_it(definition([{"name": "a", "capability": "create_note@1.0.0"}]), retired)
    assert "is deprecated, not active" in refused.value.reason


def test_a_metadata_tools_capability_is_refused(lock: wd.LockView) -> None:
    with pytest.raises(wd.DefinitionError) as refused:
        compile_it(definition([{"name": "a", "capability": "list_resources@1.0.0"}]), lock)
    assert "a metadata tool" in refused.value.reason


def test_a_capability_that_requires_approval_is_refused(lock: wd.LockView) -> None:
    """**The example project ships one, and it is not a hypothetical.**
    `set_note_embedding@1.0.0` is `requires_approval: true` in
    `projects/example/capabilities.yaml`, so this refusal fires against the
    real lock rather than against a mutated one (D1657).
    """
    with pytest.raises(wd.DefinitionError) as refused:
        compile_it(definition([{"name": "a", "capability": "set_note_embedding@1.0.0"}]), lock)
    assert "requires approval" in refused.value.reason
    assert "Session 33" in refused.value.reason


def test_an_argument_a_write_does_not_declare_is_refused(lock: wd.LockView) -> None:
    with pytest.raises(wd.DefinitionError) as refused:
        compile_it(
            definition(
                [
                    {
                        "name": "a",
                        "capability": "create_note@1.0.0",
                        "arguments": {"p_title": "x", "p_smuggled": "y"},
                    }
                ]
            ),
            lock,
        )
    assert "does not take p_smuggled" in refused.value.reason
    assert "p_title, p_content" in refused.value.reason


def test_a_relation_read_takes_the_runtimes_four_and_not_resource(lock: wd.LockView) -> None:
    """**The lock declares an argument list for a WRITE and for nothing else.**

    A read's arguments are the ones the runtime registers its closure with, and
    `resource` is not among them here because the COMPILER derives it from the
    capability -- an author who named it would be naming something already
    decided (D1682).
    """
    compiled = compile_it(
        definition([{"name": "a", "capability": "query_notes@1.0.0", "arguments": {"limit": 5}}]),
        lock,
    )
    assert compiled.steps[0].resource == "notes"

    with pytest.raises(wd.DefinitionError) as refused:
        compile_it(
            definition(
                [
                    {
                        "name": "a",
                        "capability": "query_notes@1.0.0",
                        "arguments": {"resource": "tasks"},
                    }
                ]
            ),
            lock,
        )
    assert "does not take resource" in refused.value.reason


def test_an_rpc_read_takes_no_arguments_at_all(lock: wd.LockView) -> None:
    """`run_report`'s resource is reached by `post`, so its shape is `rpc` and
    the runtime registers a closure with no parameters."""
    assert compile_it(definition([{"name": "a", "capability": "run_report@1.0.0"}]), lock)
    with pytest.raises(wd.DefinitionError) as refused:
        compile_it(
            definition(
                [{"name": "a", "capability": "run_report@1.0.0", "arguments": {"limit": 1}}]
            ),
            lock,
        )
    assert "it takes none" in refused.value.reason


def test_a_reference_to_a_later_step_is_refused(lock: wd.LockView) -> None:
    with pytest.raises(wd.DefinitionError) as refused:
        compile_it(
            definition(
                [
                    {
                        "name": "first",
                        "capability": "create_note@1.0.0",
                        "arguments": {"p_title": "{{steps.second.row}}"},
                    },
                    {"name": "second", "capability": "create_note@1.0.0"},
                ]
            ),
            lock,
        )
    assert "names a step that runs later" in refused.value.reason


def test_a_reference_to_a_step_that_does_not_exist_is_a_different_refusal(
    lock: wd.LockView,
) -> None:
    with pytest.raises(wd.DefinitionError) as refused:
        compile_it(
            definition(
                [
                    {
                        "name": "first",
                        "capability": "create_note@1.0.0",
                        "arguments": {"p_title": "{{steps.ghost.row}}"},
                    }
                ]
            ),
            lock,
        )
    assert "is not a step of this definition" in refused.value.reason


def test_a_reference_to_an_earlier_step_compiles(lock: wd.LockView) -> None:
    """**The control for the two above.** Without it, a compiler that refused
    every reference would pass them both."""
    compiled = compile_it(
        definition(
            [
                {"name": "first", "capability": "create_note@1.0.0"},
                {
                    "name": "second",
                    "capability": "create_note@1.0.0",
                    "arguments": {
                        "p_title": "{{steps.first.row}}",
                        "p_content": "{{input.anything}}",
                    },
                },
            ]
        ),
        lock,
    )
    assert [step.name for step in compiled.steps] == ["first", "second"]


def test_a_brace_that_is_not_a_reference_is_a_typo_and_not_a_literal(lock: wd.LockView) -> None:
    """D1679's lesson, borrowed from the migration renderer: a marker the
    pattern did not match would otherwise reach the upstream as text."""
    for spelling in ("{{ input.x }}", "{{steps.first}}", "{{INPUT.x}}", "{{input}}"):
        with pytest.raises(wd.DefinitionError) as refused:
            compile_it(
                definition(
                    [
                        {
                            "name": "first",
                            "capability": "create_note@1.0.0",
                            "arguments": {"p_title": spelling},
                        }
                    ]
                ),
                lock,
            )
        assert "is a typo, not a literal" in refused.value.reason, spelling


def test_a_reference_inside_a_list_or_an_object_is_found_too(lock: wd.LockView) -> None:
    """`filters` is a list of small objects and its operands are exactly where
    a reference is useful, so the walk is not over top-level strings."""
    with pytest.raises(wd.DefinitionError) as refused:
        compile_it(
            definition(
                [
                    {
                        "name": "first",
                        "capability": "query_notes@1.0.0",
                        "arguments": {
                            "filters": [{"column": "title", "value": "{{steps.ghost.row}}"}]
                        },
                    }
                ]
            ),
            lock,
        )
    assert "is not a step of this definition" in refused.value.reason


def test_a_step_timeout_below_the_tools_own_floor_is_refused(lock: wd.LockView) -> None:
    with pytest.raises(wd.DefinitionError) as refused:
        compile_it(
            definition([{"name": "a", "capability": "create_note@1.0.0", "timeout_seconds": 2}]),
            lock,
        )
    assert "below create_note's own floor of 5s" in refused.value.reason


def test_a_step_with_no_timeout_is_given_one_above_the_tools_floor(lock: wd.LockView) -> None:
    """The enqueue casts `steps[].timeout_seconds` into a NOT NULL column, so
    the compiler always emits one."""
    compiled = compile_it(definition([{"name": "a", "capability": "create_note@1.0.0"}]), lock)
    assert compiled.steps[0].timeout_seconds == wd.DEFAULT_STEP_TIMEOUT_SECONDS
    assert compiled.steps[0].timeout_seconds * 1000 >= 5000


def test_the_retry_bounds_are_the_tables_own(lock: wd.LockView) -> None:
    for retry, marker in (
        ({"max": 6}, "retry.max 6 is outside 0..5"),
        ({"backoff_seconds": 301}, "backoff_seconds 301 is outside 1..300"),
        ({"backoff_seconds": 0}, "backoff_seconds 0 is outside 1..300"),
    ):
        with pytest.raises(wd.DefinitionError) as refused:
            compile_it(
                definition([{"name": "a", "capability": "create_note@1.0.0", "retry": retry}]),
                lock,
            )
        assert marker in refused.value.reason


def test_a_run_timeout_above_an_hour_is_refused(lock: wd.LockView) -> None:
    with pytest.raises(wd.DefinitionError) as refused:
        compile_it(
            definition([{"name": "a", "capability": "create_note@1.0.0"}], timeout_seconds=3601),
            lock,
        )
    assert refused.value.step_name is None
    assert "outside 1..3600" in refused.value.reason


def test_two_steps_may_not_share_a_name(lock: wd.LockView) -> None:
    """`workflow_step` is UNIQUE (run_id, name), and a reference names a step
    by name -- so a duplicate would make a reference ambiguous as well as
    making the insert fail."""
    with pytest.raises(wd.DefinitionError) as refused:
        compile_it(
            definition(
                [
                    {"name": "a", "capability": "create_note@1.0.0"},
                    {"name": "a", "capability": "create_note@1.0.0"},
                ]
            ),
            lock,
        )
    assert "already has" in refused.value.reason


# ---------------------------------------------------------------------------
# The shape, before the lock is consulted
# ---------------------------------------------------------------------------


def test_the_schema_refuses_what_the_table_would_refuse(tmp_path: Any) -> None:
    """A name the column's CHECK rejects is rejected in the checkout instead.

    The alternative is a deploy that compiles every definition, reaches step
    6d and fails on a constraint -- with the cluster already migrated.
    """
    path = tmp_path / "bad.yaml"
    path.write_text(
        "schema_version: 1\nname: Not_A_Name\nversion: 1\ndescription: x\n"
        "steps:\n  - name: a\n    capability: create_note@1.0.0\n",
        encoding="utf-8",
    )
    with pytest.raises(wd.DefinitionError, match=r"workflow\.schema\.json"):
        wd.load(path)


def test_a_step_name_may_not_carry_a_hyphen_although_the_table_allows_one(
    tmp_path: Any,
) -> None:
    """**Narrower than the table on purpose.** `workflow_step.name`'s CHECK
    admits a hyphen; a reference grammar that did could not tell
    `{{steps.a-b.c}}` from an expression."""
    path = tmp_path / "hyphen.yaml"
    path.write_text(
        "schema_version: 1\nname: fine\nversion: 1\ndescription: x\n"
        "steps:\n  - name: a-b\n    capability: create_note@1.0.0\n",
        encoding="utf-8",
    )
    with pytest.raises(wd.DefinitionError, match=r"workflow\.schema\.json"):
        wd.load(path)


def test_a_file_that_is_not_yaml_is_reported_rather_than_crashing(tmp_path: Any) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("steps: [\n", encoding="utf-8")
    with pytest.raises(wd.DefinitionError, match="is not YAML"):
        wd.load(path)


def test_definitions_of_a_project_with_no_workflows_directory_is_empty(tmp_path: Any) -> None:
    """Not an error and not a zero-length listing of a directory that exists:
    a project that declares no workflows is a different thing from one whose
    directory is empty, and only the caller can say which sentence to print."""
    assert wd.definitions_of(tmp_path) == []


# ---------------------------------------------------------------------------
# The control: the definitions this release ships
# ---------------------------------------------------------------------------


def test_the_example_projects_definitions_compile(lock: wd.LockView) -> None:
    """**The control for every refusal above.**

    Without it, a compiler that refused everything would pass this whole
    module. It is also the check that `bin/workflow.sh validate --project
    project.example.yaml` exits 0, asserted here over the same two files.
    """
    paths = wd.definitions_of(PROJECT_ROOT)
    assert [path.name for path in paths] == ["notes-retry.yaml", "notes-roundtrip.yaml"]

    compiled = {path.name: wd.compile_file(path, lock) for path in paths}

    roundtrip = compiled["notes-roundtrip.yaml"]
    assert [step.name for step in roundtrip.steps] == [
        "create_the_first_note",
        "read_the_notes_back",
        "create_the_second_note",
    ]
    assert [step.tool for step in roundtrip.steps] == [
        "create_note",
        "query_resource",
        "create_note",
    ]
    assert roundtrip.steps[1].resource == "notes"
    assert roundtrip.required_scopes == ("notes:read", "notes:write")

    retry = compiled["notes-retry.yaml"]
    assert retry.steps[0].retry == {"max": 1, "backoff_seconds": 45}
    assert retry.required_scopes == ("notes:write", "tasks:write")
    # The rehearsal's task id is a reference, not a committed uuid: a literal
    # would be right on no deployment at all (D1657).
    assert retry.steps[0].arguments["p_task_id"] == "{{input.task_id}}"


def test_every_compiled_body_carries_what_the_enqueue_reads(lock: wd.LockView) -> None:
    """`workflow_enqueue` reads `timeout_seconds` off the body and `name`,
    `retry.max`, `retry.backoff_seconds` and `timeout_seconds` off each step.
    A body missing one of them inserts a NULL into a NOT NULL column."""
    for path in wd.definitions_of(PROJECT_ROOT):
        body = wd.compile_file(path, lock).body()
        assert isinstance(body["timeout_seconds"], int)
        for step in body["steps"]:
            assert isinstance(step["name"], str)
            assert isinstance(step["retry"]["max"], int)
            assert isinstance(step["retry"]["backoff_seconds"], int)
            assert isinstance(step["timeout_seconds"], int)


def test_a_project_with_no_capabilities_of_its_own_still_gets_a_lock() -> None:
    """The other branch of `lock_view_for_project`: the release's contract
    alone. `project.second.example.yaml` declares no `mcp.capabilities`, which
    is the control that the branch exists."""
    view = wd.lock_view_for_project(SECOND)
    assert "create_note@1.0.0" in view.capability_names
    assert "query_note_embeddings@1.0.0" not in view.capability_names


def test_the_source_digest_is_over_the_bytes_and_not_the_document(tmp_path: Any) -> None:
    """Two files that parse to the same document and differ in a COMMENT are
    two different sources. The comments are where the reasoning lives, and a
    definition whose reasoning changed is one a reviewer should see again."""
    first = tmp_path / "a.yaml"
    second = tmp_path / "b.yaml"
    body = "schema_version: 1\nname: same\nversion: 1\ndescription: x\nsteps:\n  - name: a\n    capability: create_note@1.0.0\n"  # noqa: E501
    first.write_text(body, encoding="utf-8")
    second.write_text("# a comment\n" + body, encoding="utf-8")
    assert wd.load(first) == wd.load(second)
    assert wd.source_digest(first) != wd.source_digest(second)


def _view_with(lock: wd.LockView, tool_name: str, **changes: Any) -> wd.LockView:
    """The same lock with one capability's declaration changed."""
    import dataclasses

    tools = []
    for tool in lock.tools:
        capabilities = tuple(
            dataclasses.replace(capability, **changes)
            if tool.name == tool_name and capability.name == tool_name
            else capability
            for capability in tool.capabilities
        )
        tools.append(dataclasses.replace(tool, capabilities=capabilities))
    return dataclasses.replace(lock, tools=tuple(tools))
