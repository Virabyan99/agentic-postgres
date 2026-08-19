"""Capability manifest contract (runbook §5).

The point of this file is negative: the capability surface must not be able to
grow by accident. Every test that rejects something is protecting the property
that adding an API operation does not make it agent-reachable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, capability_compiler, config

pytestmark = [pytest.mark.contract, pytest.mark.p0]

EXAMPLE = REPO_ROOT / "capabilities.example.yaml"


def check(tmp_path: Path, document: dict[str, Any]) -> dict[str, Any]:
    path = tmp_path / "capabilities.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return config.load_capabilities_manifest(path)


def read_capability() -> dict[str, Any]:
    return {
        "name": "query_notes",
        "description": "Structured read over approved note columns.",
        "kind": "read",
        "enabled": False,
        "required_scopes": ["notes:read"],
        "operation": {"source": "postgrest", "operation_id": "notes_list"},
        "resource": "notes",
        "columns": ["id", "title", "created_at"],
        "max_rows": 100,
    }


def write_capability() -> dict[str, Any]:
    return {
        "name": "create_note",
        "kind": "write",
        "enabled": False,
        "required_scopes": ["notes:write"],
        "operation": {"source": "postgrest", "operation_id": "rpc_create_note"},
        "max_affected_rows": 1,
        "idempotent": False,
    }


# ---------------------------------------------------------------------------
# The shipped default
# ---------------------------------------------------------------------------


def test_the_example_manifest_is_the_reviewed_agent_surface() -> None:
    """**It asserted `== {"schema_version": 1, "capabilities": []}` until Run 3.**

    Empty was the correct answer through Session 7 and it was not an oversight:
    no live backing API contract existed to validate an entry against. Session 5
    shipped the reviewed surface and the approved snapshot, and Session 8 Run 3
    is what compiles against them.

    What replaces the equality is not a looser check. Five capabilities, four
    tools, every one enabled and every one resolved against the reviewed contract
    by `capability_compiler` -- a stronger statement than "the list is empty",
    and one that fails if a sixth appears without review.
    """
    document = config.load_capabilities_manifest(EXAMPLE)
    assert document["schema_version"] == 1
    assert {entry["name"] for entry in document["capabilities"]} == {
        "list_resources",
        "describe_resource",
        "query_notes",
        "query_tasks",
        "run_report",
    }
    assert all(entry["enabled"] for entry in document["capabilities"])


def test_the_two_query_authorizations_are_separate_entries() -> None:
    """ADR 0120, at the manifest rather than at the compiled contract.

    `query_notes` and `query_tasks` are two authorizations behind one tool, and
    the reason they are two is that `required_scopes` is a CONJUNCTION: one entry
    naming both scopes would refuse an agent holding either, which is the
    opposite of what "notes:read or tasks:read" means.
    """
    document = config.load_capabilities_manifest(EXAMPLE)
    entries = {entry["name"]: entry for entry in document["capabilities"]}

    assert entries["query_notes"]["tool"] == "query_resource"
    assert entries["query_tasks"]["tool"] == "query_resource"
    assert entries["query_notes"]["required_scopes"] == ["notes:read"]
    assert entries["query_tasks"]["required_scopes"] == ["tasks:read"]
    assert sorted(entries["run_report"]["required_scopes"]) == ["notes:read", "tasks:read"]
    for name in ("list_resources", "describe_resource", "run_report"):
        assert entries[name].get("tool", name) == name


# ---------------------------------------------------------------------------
# Enabling is validated by the compiler, not refused here
# ---------------------------------------------------------------------------


def test_a_metadata_capability_may_not_declare_a_backend(tmp_path: Path) -> None:
    """ADR 0120: the schema forbids the fields; the runtime does not merely ignore them.

    A metadata tool answers from the deployed lock. Given a `resource` and a
    `columns` list it would carry a description of a query nobody makes, and the
    next reader could not tell those values from the ones that are real -- D267's
    rule about a fabricated measurement in a comment, applied to a manifest.
    """
    metadata = {
        "name": "list_resources",
        "kind": "metadata",
        "enabled": True,
        "required_scopes": ["meta:read"],
        "operation": {"source": "lock", "operation_id": "lock.resources.list"},
    }
    assert check(tmp_path, {"schema_version": 1, "capabilities": [metadata]})

    for field, value in (("resource", "notes"), ("columns", ["id"]), ("max_rows", 10)):
        with pytest.raises(config.ManifestError):
            check(tmp_path, {"schema_version": 1, "capabilities": [metadata | {field: value}]})


def test_a_tool_name_may_not_collide_with_another_capability_name(tmp_path: Path) -> None:
    """One entry's grouping must not silently rename another (ADR 0120)."""
    first = read_capability() | {"name": "query_notes", "tool": "run_report", "enabled": True}
    second = read_capability() | {"name": "run_report", "enabled": True}
    with pytest.raises(config.ManifestError, match="another capability"):
        check(tmp_path, {"schema_version": 1, "capabilities": [first, second]})


def test_the_contract_error_is_still_distinguishable_from_bad_input() -> None:
    """It maps to exit 5 (contract failure), not exit 2 (invalid input).

    The blanket refusal of `enabled: true` is gone; this class is not. It is what
    `capability_compiler` raises for a capability the reviewed surface does not
    permit, and the distinction it carries was always the point of having it --
    the class outlives the check that first used it.
    """
    assert issubclass(config.CapabilityContractError, config.ManifestError)
    assert issubclass(capability_compiler.CompilerError, config.CapabilityContractError), (
        "the compiler's refusal is not a contract failure, so a manifest asserting an "
        "operation nothing serves would exit 2 (invalid input) rather than 5"
    )


def test_disabled_capability_entry_is_allowed(tmp_path: Path) -> None:
    document = check(tmp_path, {"schema_version": 1, "capabilities": [read_capability()]})
    assert document["capabilities"][0]["enabled"] is False


# ---------------------------------------------------------------------------
# Structural refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    ["sql", "query", "raw_query", "path", "select", "where", "postgrest_query"],
)
def test_sql_and_raw_query_fields_are_rejected(tmp_path: Path, field: str) -> None:
    capability = read_capability() | {field: "select * from notes"}
    with pytest.raises(config.ManifestError):
        check(tmp_path, {"schema_version": 1, "capabilities": [capability]})


def test_duplicate_capability_names_are_rejected(tmp_path: Path) -> None:
    document = {"schema_version": 1, "capabilities": [read_capability(), read_capability()]}
    with pytest.raises(config.ManifestError, match="duplicate capability names"):
        check(tmp_path, document)


@pytest.mark.parametrize("name", ["Bad-Name", "ab", "has-hyphen", "1leading", "x" * 49])
def test_invalid_capability_name_is_rejected(tmp_path: Path, name: str) -> None:
    capability = read_capability() | {"name": name}
    with pytest.raises(config.ManifestError):
        check(tmp_path, {"schema_version": 1, "capabilities": [capability]})


@pytest.mark.parametrize("scope", ["notes:delete", "admin", "*", "notes:*", ""])
def test_scope_outside_the_approved_vocabulary_is_rejected(tmp_path: Path, scope: str) -> None:
    capability = read_capability() | {"required_scopes": [scope]}
    with pytest.raises(config.ManifestError):
        check(tmp_path, {"schema_version": 1, "capabilities": [capability]})


def test_approved_scopes_are_accepted(tmp_path: Path) -> None:
    capability = read_capability() | {"required_scopes": ["notes:read", "meta:read"]}
    document = check(tmp_path, {"schema_version": 1, "capabilities": [capability]})
    assert document["capabilities"][0]["required_scopes"] == ["notes:read", "meta:read"]


def test_empty_scope_list_is_rejected(tmp_path: Path) -> None:
    capability = read_capability() | {"required_scopes": []}
    with pytest.raises(config.ManifestError):
        check(tmp_path, {"schema_version": 1, "capabilities": [capability]})


def test_read_capability_requires_frozen_allowlists(tmp_path: Path) -> None:
    capability = read_capability()
    del capability["columns"]
    with pytest.raises(config.ManifestError, match="columns"):
        check(tmp_path, {"schema_version": 1, "capabilities": [capability]})


def test_write_capability_requires_a_side_effect_bound(tmp_path: Path) -> None:
    capability = write_capability()
    del capability["max_affected_rows"]
    with pytest.raises(config.ManifestError, match="max_affected_rows"):
        check(tmp_path, {"schema_version": 1, "capabilities": [capability]})


def test_operation_reference_is_required(tmp_path: Path) -> None:
    capability = read_capability()
    del capability["operation"]
    with pytest.raises(config.ManifestError, match="operation"):
        check(tmp_path, {"schema_version": 1, "capabilities": [capability]})


def test_operation_source_is_constrained(tmp_path: Path) -> None:
    capability = read_capability()
    capability["operation"] = {"source": "arbitrary", "operation_id": "x"}
    with pytest.raises(config.ManifestError):
        check(tmp_path, {"schema_version": 1, "capabilities": [capability]})


@pytest.mark.parametrize("operator", ["like", "regex", "raw", "sql"])
def test_filter_operators_come_from_a_closed_enum(tmp_path: Path, operator: str) -> None:
    capability = read_capability() | {"filters": [{"column": "title", "operators": [operator]}]}
    with pytest.raises(config.ManifestError):
        check(tmp_path, {"schema_version": 1, "capabilities": [capability]})


def test_structured_filter_operators_are_accepted(tmp_path: Path) -> None:
    capability = read_capability() | {"filters": [{"column": "title", "operators": ["eq", "in"]}]}
    assert check(tmp_path, {"schema_version": 1, "capabilities": [capability]})


def test_row_ceiling_cannot_be_exceeded(tmp_path: Path) -> None:
    capability = read_capability() | {"max_rows": 1001}
    with pytest.raises(config.ManifestError):
        check(tmp_path, {"schema_version": 1, "capabilities": [capability]})


def test_unknown_top_level_key_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(config.ManifestError):
        check(tmp_path, {"schema_version": 1, "capabilities": [], "extra": True})


def test_scope_vocabulary_lives_only_in_the_schema() -> None:
    """Plan decision C: the schema is the sole authority; code holds no copy.

    **Replaced by a stricter assertion, authorised by ADR 0079.** This pinned
    `$defs/scope` to five names. That enum is now the *union* of two closed
    classes -- the data class ADR 0003 freezes, and the administrative class the
    auth service's own surface closes -- so the equality is asserted over the
    class that ADR 0003 governs, in `tests/contract/test_scope_registry.py`.

    Stricter rather than weaker: the old assertion could not tell an added data
    scope from an added administrative one, and the new pair can. What stays
    here is the authority property, which is what this test is named for.
    """
    schema = config.load_schema("capabilities.schema.json")
    vocabulary = set(schema["$defs"]["scope"]["enum"])
    agent_requestable = set(schema["$defs"]["agent_scope"]["enum"])

    assert agent_requestable == {
        "notes:read",
        "notes:write",
        "tasks:read",
        "tasks:write",
        "meta:read",
    }
    assert agent_requestable < vocabulary, (
        "the agent-requestable class must be a proper subset of the vocabulary; equal, "
        "the split has been undone and an administrative scope is requestable again"
    )
    assert not hasattr(config, "APPROVED_SCOPES")
