"""The scope vocabulary's two classes, and the role ceiling (ADR 0079).

The property that matters here is not "the registry is correct" -- it is that the
registry cannot become a *second vocabulary*. ADR 0006 makes
`schemas/capabilities.schema.json` the sole authority and says the code carries
no second copy; this module is a mapping onto that file, and these tests are
what make the distinction load-bearing rather than stated.
"""

from __future__ import annotations

import json

import pytest

from agentic_postgres import config, naming, scope_registry
from agentic_postgres.config import ManifestError

pytestmark = [pytest.mark.contract, pytest.mark.p0]


def schema() -> dict:
    return config.load_schema("capabilities.schema.json")


# ---------------------------------------------------------------------------
# Two closed classes, in one authority
# ---------------------------------------------------------------------------


def test_the_data_class_is_still_exactly_the_five_adr_0003_closes() -> None:
    """ADR 0079 adds a class; it does not touch the one ADR 0003 froze.

    Replaces the equality this file used to assert over `$defs/scope`, which is
    now the union. Stricter rather than weaker: that assertion could not have
    told an added *data* scope from an added administrative one, and this one
    can. The data class still grows only when ADR 0003 is superseded.
    """
    assert scope_registry.agent_requestable_scopes() == {
        "notes:read",
        "notes:write",
        "tasks:read",
        "tasks:write",
        "meta:read",
    }


def test_the_administrative_class_is_one_per_identity_resource_and_verb() -> None:
    """One per (platform identity resource, verb), closed by the auth surface.

    **Replaces `test_the_administrative_class_is_derived_not_listed`**, which
    asserted a property ADR 0100 removed: the class is listed in the schema now,
    not derived as the union less the data class. A test asserting that it is
    derived cannot be kept once it is not, and CLAUDE.md §5 admits replacement by
    a stricter test on an ADR's authority.

    Stricter in the way that matters. The old version's disjointness check
    covered one pair, because there were only two classes to compare; the
    partition test below covers every pair *and* the union -- which is what
    catches the failure the complement produced and this could not: an approved
    name belonging to no class at all.
    """
    assert scope_registry.administrative_scopes() == {
        "admin_users:read",
        "admin_users:write",
        "admin_agents:read",
        "admin_agents:write",
    }
    assert scope_registry.administrative_scopes() <= scope_registry.approved_scopes()


def test_the_storage_class_is_one_per_object_verb() -> None:
    """ADR 0100. Two segments and a (resource, verb) pair, like every other scope.

    `storage:*` was the runbook's spelling and names a *surface* rather than a
    resource -- the ground on which ADR 0049 refused `openapi:read`.
    """
    assert scope_registry.storage_scopes() == {"objects:read", "objects:write"}
    assert scope_registry.storage_scopes() <= scope_registry.approved_scopes()


def test_the_three_classes_partition_the_vocabulary() -> None:
    """The relation that replaced the complement (ADR 0100)."""
    scope_registry.assert_classes_partition_the_vocabulary()

    classes = (
        scope_registry.agent_requestable_scopes(),
        scope_registry.storage_scopes(),
        scope_registry.administrative_scopes(),
    )
    union: set[str] = set()
    for members in classes:
        assert not (union & members), "two classes name the same scope"
        union |= members
    assert union == scope_registry.approved_scopes()


def test_an_unclassified_scope_is_refused_rather_than_absorbed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The measured failure, turned into a guard.

    Before ADR 0100 the administrative class was `approved - agent_requestable`,
    so a name added to the union and to no class was *classified administrative
    by arithmetic*. Run 1 measured it: adding `objects:read` and `objects:write`
    to `$defs/scope` alone turned the administrative-class tests red for a reason
    nobody would have connected to the cause -- and both of those tests look
    exactly like tests somebody would update when adding a scope, so the
    misclassification would have survived its own guard.

    Driven through the loader rather than by editing the schema on disk, because
    the property is about what the registry does with a vocabulary rather than
    about a file. The first line is the control: the real vocabulary partitions,
    so a failure below is the injected name and not a broken check.
    """
    scope_registry.assert_classes_partition_the_vocabulary()

    widened = scope_registry.approved_scopes() | {"telemetry:read"}
    monkeypatch.setattr(scope_registry, "approved_scopes", lambda: widened)

    with pytest.raises(ManifestError, match="telemetry:read"):
        scope_registry.assert_classes_partition_the_vocabulary()

    # And it fails where the registry is READ, not only when asked directly --
    # which is what makes it reachable before any deployment could carry it.
    with pytest.raises(ManifestError, match="telemetry:read"):
        scope_registry.permitted_scopes("authenticated")


def test_a_scope_in_two_classes_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A name in two classes makes the classes depend on evaluation order.

    A failure the complement could never have had: with one class derived by
    subtraction an overlap was unrepresentable. Listing all three makes it
    possible, so it is checked.
    """
    scope_registry.assert_classes_partition_the_vocabulary()

    overlapping = scope_registry.storage_scopes() | {"notes:read"}
    monkeypatch.setattr(scope_registry, "storage_scopes", lambda: overlapping)
    with pytest.raises(ManifestError, match="notes:read"):
        scope_registry.assert_classes_partition_the_vocabulary()


def test_a_class_may_not_name_a_scope_the_union_does_not_admit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A class is a subset of the vocabulary, never an extension of it (ADR 0006)."""
    scope_registry.assert_classes_partition_the_vocabulary()

    extended = scope_registry.storage_scopes() | {"objects:delete"}
    monkeypatch.setattr(scope_registry, "storage_scopes", lambda: extended)
    with pytest.raises(ManifestError, match="objects:delete"):
        scope_registry.assert_classes_partition_the_vocabulary()


def test_the_agent_class_is_not_widened_by_the_storage_class() -> None:
    """Session 7's human-only property, asserted where it is enforced.

    §8 of the Session 7 plan: an agent token cannot use storage. What makes that
    true is `required_scopes`' $ref to `$defs/agent_scope`, so the assertion is
    set membership rather than a prefix -- ADR 0006's argument about names
    applies here exactly as it does to `admin_`.
    """
    assert not (scope_registry.agent_requestable_scopes() & scope_registry.storage_scopes())
    for role in ("agent_reader", "agent_writer"):
        assert not (scope_registry.permitted_scopes(role) & scope_registry.storage_scopes()), role


def test_a_human_may_hold_a_storage_scope_and_a_service_identity_may_not() -> None:
    """The other half of the same claim, with the holders enumerated."""
    storage = scope_registry.storage_scopes()
    holders = {
        role
        for role in scope_registry.ROLE_SCOPES
        if scope_registry.permitted_scopes(role) & storage
    }
    assert holders == {"authenticated", "project_admin"}


def test_a_capability_manifest_cannot_request_an_administrative_scope() -> None:
    """The reason the split exists, asserted through the validator itself.

    ADR 0006 rejected pattern-validated scopes because they would accept
    `admin:everything`. One enum serving both the vocabulary and the capability
    surface reintroduces that: adding an administrative name to the vocabulary
    would silently make it requestable by a tool manifest.
    """
    capability = {
        "name": "query_notes",
        "description": "Structured read over approved note columns.",
        "kind": "read",
        "enabled": False,
        "required_scopes": ["admin_users:read"],
        "operation": {"source": "postgrest", "operation_id": "notes_list"},
        "resource": "notes",
        "columns": ["id", "title", "created_at"],
        "max_rows": 100,
    }
    with pytest.raises(ManifestError):
        config.validate_against_schema(
            {"schema_version": 1, "capabilities": [capability]}, "capabilities.schema.json"
        )

    # The control: the same manifest with a data scope validates, so the refusal
    # above is about the scope and not about the rest of the document.
    capability["required_scopes"] = ["notes:read"]
    config.validate_against_schema(
        {"schema_version": 1, "capabilities": [capability]}, "capabilities.schema.json"
    )


def test_required_scopes_binds_to_the_agent_class(tmp_path) -> None:
    """Read from the file, because the binding is a one-word `$ref`.

    A `$ref` pointed back at `#/$defs/scope` would restore the old behaviour and
    every other test here would still pass -- the vocabulary would be right, the
    classes would be right, and the capability surface would be wrong.
    """
    del tmp_path
    document = schema()
    reference = document["$defs"]["capability"]["properties"]["required_scopes"]["items"]
    assert reference == {"$ref": "#/$defs/agent_scope"}, (
        "required_scopes must bind to the agent class; bound to the union it would admit "
        "an administrative scope into a tool manifest"
    )


def test_the_code_still_carries_no_second_copy() -> None:
    """ADR 0006's own words, and the registry does not get an exemption."""
    assert not hasattr(config, "APPROVED_SCOPES")
    source = (config.REPO_ROOT / "src" / "agentic_postgres" / "scope_registry.py").read_text(
        encoding="utf-8"
    )
    enum = json.dumps(schema()["$defs"]["scope"]["enum"])
    assert enum not in source, "the registry embeds the schema's enum verbatim"


# ---------------------------------------------------------------------------
# The role ceiling
# ---------------------------------------------------------------------------


def test_every_registry_role_is_a_real_role_suffix() -> None:
    """A ceiling for a role that does not exist is a ceiling on nothing."""
    unknown = set(scope_registry.ROLE_SCOPES) - set(naming.ROLE_SUFFIXES)
    assert not unknown, f"the registry names roles naming.py does not derive: {sorted(unknown)}"


def test_every_granted_scope_is_one_the_schema_admits() -> None:
    for role in scope_registry.ROLE_SCOPES:
        assert scope_registry.permitted_scopes(role) <= scope_registry.approved_scopes()


def test_a_service_identity_may_not_be_named_by_a_token() -> None:
    """`postgrest_authenticator`, `object_owner` and friends are absent by design."""
    for role in ("postgrest_authenticator", "object_owner", "migration_user", "auth_service"):
        assert role in naming.ROLE_SUFFIXES
        with pytest.raises(ManifestError, match="no token may name"):
            scope_registry.permitted_scopes(role)


def test_the_documentation_role_carries_exactly_introspection() -> None:
    """ADR 0049, unchanged: the shape of the API and none of its data."""
    assert scope_registry.permitted_scopes("api_documentation") == {"meta:read"}


def test_an_administrative_scope_is_reachable_only_by_the_admin_role() -> None:
    administrative = scope_registry.administrative_scopes()
    holders = {
        role
        for role in scope_registry.ROLE_SCOPES
        if scope_registry.permitted_scopes(role) & administrative
    }
    assert holders == {"project_admin"}


def test_a_reader_agent_cannot_reach_a_write_scope() -> None:
    """AGT-SCOPE-001's shape: the ceiling is what makes it enumerable."""
    reader = scope_registry.permitted_scopes("agent_reader")
    assert not {scope for scope in reader if scope.endswith(":write")}


# ---------------------------------------------------------------------------
# The issuer's check
# ---------------------------------------------------------------------------


def test_a_permitted_subset_is_accepted() -> None:
    assert scope_registry.assert_scopes_permitted("authenticated", ["notes:read"]) == {"notes:read"}


def test_a_scope_above_the_ceiling_is_refused() -> None:
    with pytest.raises(ManifestError, match="may not carry"):
        scope_registry.assert_scopes_permitted("authenticated", ["admin_users:write"])
    with pytest.raises(ManifestError, match="may not carry"):
        scope_registry.assert_scopes_permitted("api_documentation", ["notes:read"])


def test_an_empty_scope_list_is_refused_for_a_role_that_has_a_ceiling() -> None:
    """A token whose authority nothing describes is not a safe default."""
    with pytest.raises(ManifestError, match="at least one scope"):
        scope_registry.assert_scopes_permitted("authenticated", [])


def test_anon_may_carry_no_scopes_and_only_no_scopes() -> None:
    assert scope_registry.assert_scopes_permitted("anon", []) == frozenset()
    with pytest.raises(ManifestError, match="may carry no scopes"):
        scope_registry.assert_scopes_permitted("anon", ["notes:read"])


def test_a_repeated_scope_is_refused() -> None:
    with pytest.raises(ManifestError, match="repeat"):
        scope_registry.assert_scopes_permitted("authenticated", ["notes:read", "notes:read"])
