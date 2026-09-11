"""The scope vocabulary's three classes, and the role ceiling (ADR 0079, ADR 0200).

The property that matters here is not "the registry is correct" -- it is that the
registry cannot become a *second vocabulary*. ADR 0006 makes
`schemas/capabilities.schema.json` the sole authority for what it enumerates and
says the code carries no second copy; since ADR 0200 the data class is DERIVED
from the reviewed surface by one function, and the role ceiling names classes
rather than scopes. These tests are what make both distinctions load-bearing
rather than stated.
"""

from __future__ import annotations

import json

import pytest

from agentic_postgres import REPO_ROOT, api_surface, config, naming, scope_registry
from agentic_postgres.config import ManifestError

pytestmark = [pytest.mark.contract, pytest.mark.p0]

RELEASE_DATA_CLASS = {"notes:read", "notes:write", "tasks:read", "tasks:write", "meta:read"}


def schema() -> dict:
    return config.load_schema("capabilities.schema.json")


def merged_example_surface() -> dict:
    """The release surface joined with the example project's (ADR 0198)."""
    project = api_surface.load_project_surface(
        api_surface.project_contract_path(REPO_ROOT / "projects" / "example")
    )
    return api_surface.merged_surface(api_surface.load_surface(), project)


# ---------------------------------------------------------------------------
# Three classes: one derived, two enumerated, in one authority each
# ---------------------------------------------------------------------------


def test_the_data_class_is_derived_from_the_reviewed_surface_and_the_classes_still_partition() -> (
    None
):
    """**Replaces `test_the_data_class_is_still_exactly_the_five_adr_0003_closes`**
    under ADR 0200, and it is stricter in both directions.

    The old test asserted the enum held five names. This asserts that the
    RELEASE surface derives exactly those five -- so nothing the change widened
    is visible to a deployment without a project set, and the enum a schema-3
    manifest may still name is exactly what the release derives -- AND that the
    merged example surface derives those five plus the example project's
    relation, which is the whole of what the change opens. An equality on both
    sides: a `<=` would admit an unreviewed relation silently.
    """
    assert scope_registry.agent_requestable_scopes() == RELEASE_DATA_CLASS
    assert scope_registry.enumerated_agent_scopes() == RELEASE_DATA_CLASS

    merged = scope_registry.agent_requestable_scopes(merged_example_surface())
    assert merged == RELEASE_DATA_CLASS | {"note_embeddings:read", "note_embeddings:write"}

    # The function is pure over its argument: a surface with no relations
    # derives introspection alone, and never reads a file to do it.
    assert scope_registry.vocabulary({"relations": {}}) == {"meta:read"}


def test_the_administrative_class_is_one_per_identity_resource_and_verb() -> None:
    """One per (platform identity resource, verb), closed by the auth surface.

    Enumerated in the schema, not derived (ADR 0100), and an equality over a
    closed list is what makes an unreviewed addition to the vocabulary fail
    here; a `<=` would have admitted `admin_audit:read` silently and admitted
    the next name silently too. Five members since Session 9 Run 7 (ADR 0142).
    """
    assert scope_registry.administrative_scopes() == {
        "admin_users:read",
        "admin_users:write",
        "admin_agents:read",
        "admin_agents:write",
        "admin_audit:read",
    }
    assert scope_registry.administrative_scopes() <= scope_registry.approved_scopes()

    # The asymmetry is a decision and not an oversight (ADR 0142), so it is
    # asserted rather than left to the equality above to imply.
    assert "admin_audit:write" not in scope_registry.approved_scopes()


def test_the_storage_class_is_one_per_object_verb() -> None:
    """ADR 0100. Two segments and a (resource, verb) pair, like every other scope."""
    assert scope_registry.storage_scopes() == {"objects:read", "objects:write"}
    assert scope_registry.storage_scopes() <= scope_registry.approved_scopes()


def test_the_three_classes_partition_the_vocabulary() -> None:
    """The relation that replaced the complement (ADR 0100), kept under ADR 0200
    for the enumerated union and asserted again over the derived class."""
    scope_registry.assert_classes_partition_the_vocabulary()
    scope_registry.assert_classes_partition_the_vocabulary(merged_example_surface())

    for surface in (None, merged_example_surface()):
        classes = (
            scope_registry.agent_requestable_scopes(surface),
            scope_registry.storage_scopes(),
            scope_registry.administrative_scopes(),
        )
        union: set[str] = set()
        for members in classes:
            assert not (union & members), "two classes name the same scope"
            union |= members
        assert union == scope_registry.approved_scopes(surface)


def test_an_unclassified_scope_is_refused_rather_than_absorbed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The measured failure, turned into a guard.

    Before ADR 0100 the administrative class was `approved - agent_requestable`,
    so a name added to the union and to no class was *classified administrative
    by arithmetic*. Driven through the loader rather than by editing the schema
    on disk, because the property is about what the registry does with an
    enumerated union rather than about a file. The first line is the control.
    """
    scope_registry.assert_classes_partition_the_vocabulary()

    real = config.load_schema

    def widened(name: str) -> dict:
        document = real(name)
        if name == "capabilities.schema.json":
            document = json.loads(json.dumps(document))
            document["$defs"]["scope"]["enum"].append("telemetry:read")
        return document

    monkeypatch.setattr(config, "load_schema", widened)

    with pytest.raises(ManifestError, match="telemetry:read"):
        scope_registry.assert_classes_partition_the_vocabulary()

    # And it fails where the registry is READ, not only when asked directly --
    # which is what makes it reachable before any deployment could carry it.
    with pytest.raises(ManifestError, match="telemetry:read"):
        scope_registry.permitted_scopes("authenticated")


def test_a_scope_in_two_classes_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A name in two classes makes the classes depend on evaluation order."""
    scope_registry.assert_classes_partition_the_vocabulary()

    overlapping = scope_registry.storage_scopes() | {"notes:read"}
    monkeypatch.setattr(scope_registry, "storage_scopes", lambda: overlapping)
    with pytest.raises(ManifestError, match="notes:read"):
        scope_registry.assert_classes_partition_the_vocabulary()


def test_a_class_may_not_name_a_scope_the_union_does_not_admit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An enumerated class is a subset of the enumerated union, never an extension (ADR 0006)."""
    scope_registry.assert_classes_partition_the_vocabulary()

    extended = scope_registry.storage_scopes() | {"objects:delete"}
    monkeypatch.setattr(scope_registry, "storage_scopes", lambda: extended)
    with pytest.raises(ManifestError, match="objects:delete"):
        scope_registry.assert_classes_partition_the_vocabulary()


def test_the_derived_class_may_not_name_an_enumerated_resource() -> None:
    """ADR 0200's guarantee, asserted at the partition and not only at the loader.

    A surface whose relation is named `objects` or `admin_users` would derive a
    data scope indistinguishable from an enumerated one. `api_surface` refuses
    such a surface at load and at merge; this is the check behind that refusal,
    driven with a surface document the loader never saw.
    """
    scope_registry.assert_classes_partition_the_vocabulary({"relations": {"notes": {}}})
    for reserved in ("objects", "admin_users", "admin_audit"):
        with pytest.raises(ManifestError, match=reserved):
            scope_registry.assert_classes_partition_the_vocabulary({"relations": {reserved: {}}})


def test_the_release_surface_still_derives_everything_an_older_manifest_may_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The enum is the floor of every vocabulary (ADR 0200). A release surface
    that dropped `tasks` would leave every schema-3 manifest naming a scope no
    deployment derives, and that is refused where the registry is read."""
    scope_registry.assert_classes_partition_the_vocabulary()

    narrowed = {"relations": {"notes": {}}}
    monkeypatch.setattr(scope_registry, "_release_surface", lambda: narrowed)
    with pytest.raises(ManifestError, match="tasks:read"):
        scope_registry.assert_classes_partition_the_vocabulary()


def test_the_agent_class_is_not_widened_by_the_storage_class() -> None:
    """Session 7's human-only property, asserted where it is enforced."""
    assert not (scope_registry.agent_requestable_scopes() & scope_registry.storage_scopes())
    for role in ("agent_reader", "agent_writer"):
        assert not (scope_registry.permitted_scopes(role) & scope_registry.storage_scopes()), role


def test_a_human_may_hold_a_storage_scope_and_a_service_identity_may_not() -> None:
    """The other half of the same claim, with the holders enumerated."""
    storage = scope_registry.storage_scopes()
    holders = {
        role
        for role in scope_registry.ROLE_CLASSES
        if scope_registry.permitted_scopes(role) & storage
    }
    assert holders == {"authenticated", "project_admin"}


def test_a_capability_manifest_cannot_request_an_administrative_scope() -> None:
    """The reason the split exists, asserted through the validator itself at
    schema version 1, where the enum still binds."""
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


def test_required_scopes_binds_to_the_shape_and_the_older_gate_to_the_enum() -> None:
    """**Replaces `test_required_scopes_binds_to_the_agent_class`** under ADR 0200.

    Read from the file, because the binding is a one-word `$ref`. The base
    binds to the SHAPE; a gate at schema version 3 and below binds to the enum;
    and nothing anywhere binds `required_scopes` to `$defs/scope`, the union --
    which is the regression the old test guarded and this one still does.
    """
    document = schema()
    items = document["$defs"]["capability"]["properties"]["required_scopes"]["items"]
    assert items == {"$ref": "#/$defs/agent_scope_name"}

    gates = [
        gate
        for gate in document["allOf"]
        if gate["if"]["properties"]["schema_version"].get("maximum") == 3
    ]
    assert len(gates) == 1, "exactly one gate narrows the versions below 4"
    narrowed = gates[0]["then"]["properties"]["capabilities"]["items"]["properties"]
    assert narrowed["required_scopes"]["items"] == {"$ref": "#/$defs/agent_scope"}

    assert '"#/$defs/scope"' not in json.dumps(document["$defs"]["capability"]), (
        "required_scopes bound to the union would admit an administrative scope"
    )
    assert '"#/$defs/scope"' not in json.dumps(document["allOf"])


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
    unknown = set(scope_registry.ROLE_CLASSES) - set(naming.ROLE_SUFFIXES)
    assert not unknown, f"the registry names roles naming.py does not derive: {sorted(unknown)}"


def test_the_ceiling_names_classes_and_never_a_scope() -> None:
    """ADR 0200. The one declaration in the service names classes; every
    scope in a ceiling is computed from a vocabulary."""
    classes = {"data", "data_read", "introspection", "storage", "administrative"}
    for role, members in scope_registry.ROLE_CLASSES.items():
        assert members <= classes, f"{role} names something that is not a class: {members}"
        assert not any(":" in member for member in members), role


def test_every_granted_scope_is_one_the_vocabulary_admits() -> None:
    for surface in (None, merged_example_surface()):
        for role in scope_registry.ROLE_CLASSES:
            assert scope_registry.permitted_scopes(role, surface) <= scope_registry.approved_scopes(
                surface
            )


def test_the_ceilings_over_the_release_surface_are_what_they_were() -> None:
    """The change is invisible to a deployment without a project set: every
    ceiling over the release surface is byte for byte the set Session 9 Run 7
    left. Asserted as equalities, because that is the claim."""
    assert scope_registry.permitted_scopes("anon") == frozenset()
    assert scope_registry.permitted_scopes("authenticated") == {
        "notes:read",
        "notes:write",
        "tasks:read",
        "tasks:write",
        "objects:read",
        "objects:write",
    }
    assert scope_registry.permitted_scopes("api_documentation") == {"meta:read"}
    assert scope_registry.permitted_scopes("agent_reader") == {
        "notes:read",
        "tasks:read",
        "meta:read",
    }
    assert scope_registry.permitted_scopes("agent_writer") == {
        "notes:read",
        "notes:write",
        "tasks:read",
        "tasks:write",
        "meta:read",
    }
    assert scope_registry.permitted_scopes("project_admin") == {
        "notes:read",
        "notes:write",
        "tasks:read",
        "tasks:write",
        "objects:read",
        "objects:write",
        "admin_users:read",
        "admin_users:write",
        "admin_agents:read",
        "admin_agents:write",
        "admin_audit:read",
    }


def test_the_ceilings_over_a_merged_surface_gain_exactly_the_projects_relation() -> None:
    """What ADR 0200 opens, and no more: a tenant's relation reaches the human,
    the writer and (its read half) the reader; not the documentation role, and
    the storage and administrative classes are untouched."""
    merged = merged_example_surface()
    gained = {"note_embeddings:read", "note_embeddings:write"}
    for role in ("authenticated", "agent_writer", "project_admin"):
        assert scope_registry.permitted_scopes(role, merged) == (
            scope_registry.permitted_scopes(role) | gained
        ), role
    assert scope_registry.permitted_scopes("agent_reader", merged) == (
        scope_registry.permitted_scopes("agent_reader") | {"note_embeddings:read"}
    )
    for role in ("anon", "api_documentation"):
        assert scope_registry.permitted_scopes(role, merged) == scope_registry.permitted_scopes(
            role
        ), role


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
        for role in scope_registry.ROLE_CLASSES
        if scope_registry.permitted_scopes(role) & administrative
    }
    assert holders == {"project_admin"}


def test_a_reader_agent_cannot_reach_a_write_scope() -> None:
    """AGT-SCOPE-001's shape: the ceiling is what makes it enumerable."""
    for surface in (None, merged_example_surface()):
        reader = scope_registry.permitted_scopes("agent_reader", surface)
        assert not {scope for scope in reader if scope.endswith(":write")}


def test_both_agent_ceilings_admit_introspection() -> None:
    """ADR 0138: an agent may be issued introspection, or it cannot ask which
    rows it may change."""
    for role in ("agent_reader", "agent_writer"):
        assert "meta:read" in scope_registry.permitted_scopes(role), (
            f"{role} cannot be issued meta:read, so no token naming it can call "
            "list_resources or describe_resource (ADR 0138)"
        )


def test_no_human_ceiling_admits_introspection() -> None:
    """The other half of ADR 0138, now that the data list carries `meta:read`:
    introspection is the documentation role's and the agents', never a user's."""
    for role in ("authenticated", "project_admin"):
        assert "meta:read" not in scope_registry.permitted_scopes(role), role


def test_an_agent_may_not_hold_a_storage_scope() -> None:
    """The half ADR 0138 explicitly does not move (ADR 0100)."""
    storage = scope_registry.storage_scopes()
    assert storage, "the storage class is empty; the refusal below would be vacuous"
    for role in ("agent_reader", "agent_writer"):
        assert not (scope_registry.permitted_scopes(role) & storage), (
            f"{role}'s ceiling admits a storage scope; object storage is human-only"
        )


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


def test_a_tenant_scope_is_permitted_only_over_the_surface_that_derives_it() -> None:
    """ADR 0200 at the issuer's check: the same request, two surfaces."""
    with pytest.raises(ManifestError, match="note_embeddings:write"):
        scope_registry.assert_scopes_permitted("agent_writer", ["note_embeddings:write"])
    assert scope_registry.assert_scopes_permitted(
        "agent_writer", ["note_embeddings:write"], merged_example_surface()
    ) == {"note_embeddings:write"}


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
