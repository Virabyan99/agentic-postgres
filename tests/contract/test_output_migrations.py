"""Output schema migration and document-kind rejection (ADR 0012, 0027, 0041, 0053).

All four fixtures are real renders, not hand-built objects: ``outputs-v1.json``
is a Session 1 render, ``outputs-v2.json`` a Session 2 one, ``outputs-v3.json``
a Session 3 one, and ``outputs-v4.json`` the Session 4 render every deployed
host is running at the time version 5 was written. A hand-built fixture drifts
away from what was actually shipped, and then the migrator is proved to handle a
document that never existed.

Two negative properties carry more weight here than the positive one:

* the migrator refuses to invent a ``deployed`` document, because every field
  that distinguishes one is an observation;
* a rendered document is refused where deployed state is required, and the
  refusal happens at the boundary rather than as a ``KeyError`` further in.
  The two files share a basename, so passing the wrong path is the realistic
  mistake.

The v3 step adds a third: it refuses to *derive* anything. `database.budget`
comes from a manifest and `database.container` from ``naming``, and this module
holds neither, so both are supplied by the caller and shape-checked.

The v4 step is the interesting one, because there it *could* derive. A profile's
transport is fixed by its name and its role is already in ``database.roles``, so
a migrator could fill both in and be right. It validates instead — a supplied
profile naming a role the document does not declare is refused rather than
corrected — because deriving would make this module a second authority on which
role serves which profile, and ADR 0002 allows one derivation path per name.

The v5 step is the opposite kind of interesting: it adds nothing at all, because
everything version 5 added is on the deployed branch. What is asserted about it
is therefore mostly what it still refuses — a deployed document, an incomplete
one, one carrying fields no v4 rendered document has — because a step that
changes one integer is exactly the one somebody would later be tempted to make a
shortcut past the checks.
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, config, naming, output_migrations
from agentic_postgres.output_migrations import MigrationError

pytestmark = [pytest.mark.contract, pytest.mark.p0]

FIXTURE_V1 = REPO_ROOT / "tests" / "fixtures" / "outputs-v1.json"
FIXTURE_V2 = REPO_ROOT / "tests" / "fixtures" / "outputs-v2.json"
FIXTURE_V3 = REPO_ROOT / "tests" / "fixtures" / "outputs-v3.json"
FIXTURE_V4 = REPO_ROOT / "tests" / "fixtures" / "outputs-v4.json"

CONTRACT_DIGEST = sha256((REPO_ROOT / "secrets.required.yaml").read_bytes()).hexdigest()

#: What a caller supplies for the v3 step. Taken from the real resolver rather
#: than written out, so a change to the budget's shape fails here rather than
#: producing a fixture that agrees only with itself.
BUDGET = config.database_budget({})
CONTAINER = "apg-fixture-alpha-dev-postgres-1"


def profiles_for(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """What a caller supplies for the v4 step (ADR 0041).

    Built from the document's *own* declared roles rather than written out as
    literals, for the same reason ``BUDGET`` comes from the real resolver: a
    literal role name here would agree only with itself, and would keep agreeing
    after ``naming`` changed.

    Every profile is ``unavailable`` with a null secret reference, which is the
    only thing a migration may produce. An archived document records no bound
    port and no provisioned credential, so a profile claiming otherwise would be
    a deployment invented by a migrator.
    """
    roles = document["database"]["roles"]
    return {
        name: {
            "status": "unavailable",
            "available_from_session": 4,
            "transport": transport,
            "role": roles["migration_user" if name == "migration_direct" else "app_runtime"],
            "password_secret_ref": None,
        }
        for name, transport in output_migrations.ACCESS_PROFILE_TRANSPORTS.items()
    }


@pytest.fixture
def v1() -> dict[str, Any]:
    return json.loads(FIXTURE_V1.read_text(encoding="utf-8"))


@pytest.fixture
def v2_fixture() -> dict[str, Any]:
    """The committed Session 2 render."""
    return json.loads(FIXTURE_V2.read_text(encoding="utf-8"))


@pytest.fixture
def v3_fixture() -> dict[str, Any]:
    """The committed Session 3 render."""
    return json.loads(FIXTURE_V3.read_text(encoding="utf-8"))


@pytest.fixture
def v2(v1: dict[str, Any]) -> dict[str, Any]:
    """The v1 fixture advanced one step."""
    return output_migrations.migrate_v1_to_v2(v1, secrets_contract_sha256=CONTRACT_DIGEST)


@pytest.fixture
def v3(v2: dict[str, Any]) -> dict[str, Any]:
    """The v1 fixture advanced two steps, stopping at 3."""
    return output_migrations.migrate_v2_to_v3(
        v2, database_budget=BUDGET, database_container=CONTAINER
    )


@pytest.fixture
def v4_fixture() -> dict[str, Any]:
    """The committed Session 4 render."""
    return json.loads(FIXTURE_V4.read_text(encoding="utf-8"))


@pytest.fixture
def v4(v3: dict[str, Any]) -> dict[str, Any]:
    """The v1 fixture advanced three steps, stopping at 4."""
    return output_migrations.migrate_v3_to_v4(v3, access_profiles=profiles_for(v3))


@pytest.fixture
def v5(v1: dict[str, Any]) -> dict[str, Any]:
    """The whole chain, v1 -> v2 -> v3 -> v4 -> v5, through the public entry point."""
    return output_migrations.migrate_rendered(
        v1,
        secrets_contract_sha256=CONTRACT_DIGEST,
        database_budget=BUDGET,
        database_container=CONTAINER,
        access_profiles=profiles_for(v1),
    )


# ---------------------------------------------------------------------------
# The fixtures are genuine documents of their stated versions
# ---------------------------------------------------------------------------


def test_v1_fixture_is_version_one_and_no_longer_validates(v1: dict[str, Any]) -> None:
    """A v1 document must fail the current schema, or the migration is decorative."""
    assert output_migrations.detect_version(v1) == 1
    assert "document_kind" not in v1
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(v1, "outputs.schema.json")


def test_v2_fixture_is_version_two_and_no_longer_validates(v2_fixture: dict[str, Any]) -> None:
    """The same claim for v2, which is the version deployed hosts are running.

    This is the test that makes the version bump mean something. If a v2
    document still validated, ``schema_version`` would be a label rather than a
    contract and an old reader would have no way to tell it was out of date.
    """
    assert output_migrations.detect_version(v2_fixture) == 2
    assert v2_fixture["document_kind"] == "rendered"
    assert "container" not in v2_fixture["database"]
    assert "budget" not in v2_fixture["database"]
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(v2_fixture, "outputs.schema.json")


# ---------------------------------------------------------------------------
# v1 -> v2
# ---------------------------------------------------------------------------


def test_v1_to_v2_sets_the_rendered_kind(v2: dict[str, Any]) -> None:
    assert v2["schema_version"] == 2
    assert v2["document_kind"] == "rendered"


def test_migration_preserves_the_secrets_namespace(v1: dict[str, Any], v2: dict[str, Any]) -> None:
    """ADR 0012: the runbook's fragment would have dropped this field.

    ``secrets.namespace`` is in ``test_render_isolation.MUST_DIFFER`` and in
    ``evidence.ISOLATED_FIELDS``, so losing it would silently remove a tested
    isolation field.
    """
    assert v2["secrets"]["namespace"] == v1["secrets"]["namespace"]
    assert v2["secrets"]["status"] == "planned"


def test_migration_derives_the_health_route(v1: dict[str, Any], v2: dict[str, Any]) -> None:
    """The health route is a pure function of the domain, so v1 determines it."""
    assert v2["routes"]["health"] == {
        "status": "planned",
        "url": f"https://{v1['project']['domain']}{naming.HEALTH_ROUTE_PATH}",
    }


def test_health_route_constant_agrees_with_naming() -> None:
    """The copy in output_migrations exists only to avoid an import cycle."""
    assert output_migrations.HEALTH_ROUTE_PATH == naming.HEALTH_ROUTE_PATH


def test_migration_does_not_invent_required_names(v2: dict[str, Any]) -> None:
    """A v1 document predates every declaration, so the honest answer is none.

    Copying today's contract in would assert that it applied retroactively.
    """
    assert v2["secrets"]["required_names"] == []


def test_v1_to_v2_preserves_every_other_field(v1: dict[str, Any], v2: dict[str, Any]) -> None:
    for key in ("project", "compose", "database", "jwt", "storage", "backup", "capabilities"):
        assert v2[key] == v1[key], key
    assert v2["template_version"] == v1["template_version"]


def test_migration_does_not_mutate_its_input(v1: dict[str, Any]) -> None:
    before = json.dumps(v1, sort_keys=True)
    output_migrations.migrate_rendered(
        v1,
        secrets_contract_sha256=CONTRACT_DIGEST,
        database_budget=BUDGET,
        database_container=CONTAINER,
        access_profiles=profiles_for(v1),
    )
    assert json.dumps(v1, sort_keys=True) == before


# ---------------------------------------------------------------------------
# v2 -> v3
# ---------------------------------------------------------------------------


def test_the_committed_v2_fixture_migrates_and_validates(v2_fixture: dict[str, Any]) -> None:
    """The v2 step alone no longer produces a valid document, and should not.

    Migrating v2 -> v3 lands on a version the schema stopped accepting when it
    moved to 4. That is the version bump working: what has to be true is that
    the *chain* reaches something valid, not that any single link does.
    """
    at_three = output_migrations.migrate_v2_to_v3(
        v2_fixture, database_budget=BUDGET, database_container=CONTAINER
    )
    assert at_three["schema_version"] == 3
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(at_three, "outputs.schema.json")

    at_four = output_migrations.migrate_v3_to_v4(at_three, access_profiles=profiles_for(at_three))
    assert at_four["schema_version"] == 4
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(at_four, "outputs.schema.json")

    migrated = output_migrations.migrate_v4_to_v5(at_four)
    assert migrated["schema_version"] == 5
    config.validate_against_schema(migrated, "outputs.schema.json")


def test_the_whole_chain_validates(v5: dict[str, Any]) -> None:
    """v1 -> v2 -> v3 -> v4 -> v5 end to end, not only the newest link (ADR 0027)."""
    assert v5["schema_version"] == 5
    assert v5["document_kind"] == "rendered"
    config.validate_against_schema(v5, "outputs.schema.json")


def test_v3_carries_the_supplied_budget_and_container(v3: dict[str, Any]) -> None:
    assert v3["database"]["budget"] == BUDGET
    assert v3["database"]["container"] == CONTAINER


def test_v3_adds_no_observed_block(v3: dict[str, Any]) -> None:
    """The rendered branch has no `observed`, and the migrator does not add one.

    A migrator that emitted `{"status": "not_observed", ...}` here would be
    producing a field that only the deployed branch has, which is how a
    migrated document starts looking like state somebody measured.
    """
    assert "observed" not in v3["database"]


def test_v3_preserves_every_other_database_member(
    v2_fixture: dict[str, Any],
) -> None:
    migrated = output_migrations.migrate_v2_to_v3(
        v2_fixture, database_budget=BUDGET, database_container=CONTAINER
    )
    for key in ("name", "roles", "pooled", "direct"):
        assert migrated["database"][key] == v2_fixture["database"][key], key


def test_v3_leaves_both_endpoints_unavailable(v3: dict[str, Any]) -> None:
    """D41: Session 3 offers no client endpoint, and a migration invents none."""
    for endpoint in ("pooled", "direct"):
        assert v3["database"][endpoint]["status"] == "unavailable"
        assert v3["database"][endpoint]["available_from_session"] == 4
        assert v3["database"][endpoint]["url"] is None


def test_budget_members_agree_with_config() -> None:
    """The copy in output_migrations exists to keep this module dependency-free."""
    assert output_migrations.BUDGET_MEMBERS == frozenset(config.database_budget({}))


def test_current_version_agrees_with_the_renderer() -> None:
    """One number, three places. This is the test that keeps them one number."""
    from agentic_postgres import deployed_output

    assert output_migrations.CURRENT_VERSION == deployed_output.SCHEMA_VERSION
    rendered = json.loads(
        (REPO_ROOT / ".generated" / "fixture-alpha-dev" / "outputs.json").read_text("utf-8")
    )
    assert rendered["schema_version"] == output_migrations.CURRENT_VERSION


# ---------------------------------------------------------------------------
# What the v3 step refuses to guess
# ---------------------------------------------------------------------------


def test_migration_requires_a_real_contract_digest(v1: dict[str, Any]) -> None:
    """The `inputs` block's whole value is that its digests are real."""
    with pytest.raises(MigrationError, match="64 lowercase hex"):
        output_migrations.migrate_rendered(
            v1,
            secrets_contract_sha256="<computed SHA-256>",
            database_budget=BUDGET,
            database_container=CONTAINER,
            access_profiles=profiles_for(v1),
        )


def test_migrated_inputs_carry_the_supplied_digest(v5: dict[str, Any]) -> None:
    assert v5["inputs"]["secrets_contract_sha256"] == CONTRACT_DIGEST
    assert len(v5["inputs"]) == 5


@pytest.mark.parametrize(
    "budget",
    [
        pytest.param({}, id="empty"),
        pytest.param({"shared_buffers_mb": 128}, id="partial"),
        pytest.param({**BUDGET, "extra_mb": 1}, id="extra-member"),
    ],
)
def test_an_incomplete_budget_is_refused(v2_fixture: dict[str, Any], budget: dict) -> None:
    with pytest.raises(MigrationError, match="database_budget must have exactly"):
        output_migrations.migrate_v2_to_v3(
            v2_fixture, database_budget=budget, database_container=CONTAINER
        )


@pytest.mark.parametrize("bad", [0, -1, "128", 12.5, True])
def test_a_non_positive_integer_budget_member_is_refused(
    v2_fixture: dict[str, Any], bad: Any
) -> None:
    """`True` is in this list on purpose: it is an int, and it is not a size."""
    with pytest.raises(MigrationError, match="positive integers"):
        output_migrations.migrate_v2_to_v3(
            v2_fixture,
            database_budget={**BUDGET, "shared_buffers_mb": bad},
            database_container=CONTAINER,
        )


@pytest.mark.parametrize("bad", ["", "Apg-Upper", "-leading", "has space", "sl/ash", 5, None])
def test_an_unusable_container_name_is_refused(v2_fixture: dict[str, Any], bad: Any) -> None:
    with pytest.raises(MigrationError, match="not a usable Compose name"):
        output_migrations.migrate_v2_to_v3(
            v2_fixture, database_budget=BUDGET, database_container=bad
        )


def test_the_migrator_never_derives_a_container_name() -> None:
    """ADR 0002: one derivation path per name, and it is not this module.

    Asserted on the import graph rather than on behaviour, because the failure
    this prevents is someone adding `from agentic_postgres import naming` and a
    one-line `f"apg-{key}-postgres-1"` that agrees with `naming` until it does
    not.
    """
    source = (REPO_ROOT / "src" / "agentic_postgres" / "output_migrations.py").read_text("utf-8")
    assert "import naming" not in source
    assert "postgres-1" not in source


# ---------------------------------------------------------------------------
# What the migrator refuses
# ---------------------------------------------------------------------------


def test_a_current_version_document_is_not_migrated_again(v5: dict[str, Any]) -> None:
    """Replaces the v2 form of this assertion, applied to the current version.

    ADR 0017's rule: a test may only be replaced by a stricter one. This is the
    same property -- migrating a document that is already current is a no-op and
    is refused -- now asserted through the chaining entry point as well as the
    single step, which the previous version did not cover.
    """
    with pytest.raises(MigrationError, match="already version 5"):
        output_migrations.migrate_rendered(
            v5,
            secrets_contract_sha256=CONTRACT_DIGEST,
            database_budget=BUDGET,
            database_container=CONTAINER,
            access_profiles=profiles_for(v5),
        )
    with pytest.raises(MigrationError, match="already version 5"):
        output_migrations.migrate_v4_to_v5(v5)


def test_a_v2_document_is_still_refused_by_the_v1_step(v2_fixture: dict[str, Any]) -> None:
    """The single step keeps its own narrow refusal."""
    with pytest.raises(MigrationError, match="already version 2"):
        output_migrations.migrate_v1_to_v2(v2_fixture, secrets_contract_sha256=CONTRACT_DIGEST)


def test_an_unknown_version_is_refused(v1: dict[str, Any]) -> None:
    v1["schema_version"] = 99
    with pytest.raises(MigrationError, match="only versions 1, 2, 3 and 4"):
        output_migrations.migrate_rendered(
            v1,
            secrets_contract_sha256=CONTRACT_DIGEST,
            database_budget=BUDGET,
            database_container=CONTAINER,
            access_profiles=profiles_for(v1),
        )


def test_an_incomplete_v1_document_is_refused(v1: dict[str, Any]) -> None:
    del v1["jwt"]
    with pytest.raises(MigrationError, match="missing"):
        output_migrations.migrate_rendered(
            v1,
            secrets_contract_sha256=CONTRACT_DIGEST,
            database_budget=BUDGET,
            database_container=CONTAINER,
            access_profiles=profiles_for(v1),
        )


def test_an_incomplete_v2_document_is_refused(v2_fixture: dict[str, Any]) -> None:
    del v2_fixture["jwt"]
    with pytest.raises(MigrationError, match="not a complete version 2"):
        output_migrations.migrate_v2_to_v3(
            v2_fixture, database_budget=BUDGET, database_container=CONTAINER
        )


def test_a_document_with_unexpected_fields_is_refused(v1: dict[str, Any]) -> None:
    """Something claiming to be v1 while carrying v2 fields is not v1."""
    v1["tls"] = {"status": "issued"}
    with pytest.raises(MigrationError, match="no version 1 document has"):
        output_migrations.migrate_rendered(
            v1,
            secrets_contract_sha256=CONTRACT_DIGEST,
            database_budget=BUDGET,
            database_container=CONTAINER,
            access_profiles=profiles_for(v1),
        )


def test_a_v2_document_carrying_deployed_fields_is_refused(v2_fixture: dict[str, Any]) -> None:
    v2_fixture["observed_at"] = "2026-08-07T00:00:00Z"
    with pytest.raises(MigrationError, match="no version 2 rendered document has"):
        output_migrations.migrate_v2_to_v3(
            v2_fixture, database_budget=BUDGET, database_container=CONTAINER
        )


def test_a_deployed_document_is_not_migrated(v2_fixture: dict[str, Any]) -> None:
    """A deployed document is an observation of a host, and migrating one would
    republish those observations under a version that never measured them."""
    v2_fixture["document_kind"] = "deployed"
    with pytest.raises(MigrationError, match="expected a 'rendered'"):
        output_migrations.migrate_v2_to_v3(
            v2_fixture, database_budget=BUDGET, database_container=CONTAINER
        )


def test_there_is_no_way_to_produce_a_deployed_document() -> None:
    """ADR 0012: every field that makes a document `deployed` is an observation.

    Asserted against the module's public surface rather than by inspecting the
    source, so a future function that emitted one would have to be added to
    ``__all__`` unnoticed to escape this.
    """
    exported = set(output_migrations.__all__)
    assert not any("deploy" in name.lower() for name in exported)
    assert "migrate_rendered" in exported


# ---------------------------------------------------------------------------
# Document-kind rejection at the boundary
# ---------------------------------------------------------------------------


def test_rendered_output_is_reported_as_rendered() -> None:
    document = json.loads(
        (REPO_ROOT / ".generated" / "fixture-alpha-dev" / "outputs.json").read_text("utf-8")
    )
    assert output_migrations.document_kind(document) == "rendered"
    output_migrations.require_kind(document, "rendered")


def test_rendered_output_is_refused_where_deployed_state_is_required() -> None:
    """The two files share a basename, so this is the realistic mistake."""
    document = json.loads(
        (REPO_ROOT / ".generated" / "fixture-alpha-dev" / "outputs.json").read_text("utf-8")
    )
    with pytest.raises(MigrationError, match="expected a 'deployed'"):
        output_migrations.require_kind(document, "deployed")


def test_a_v1_document_is_reported_as_rendered(v1: dict[str, Any]) -> None:
    """v1 predates the discriminator, and everything it could be was rendered."""
    assert output_migrations.document_kind(v1) == "rendered"


def test_an_unknown_document_kind_is_refused() -> None:
    with pytest.raises(MigrationError, match="document_kind is missing or unknown"):
        output_migrations.document_kind({"schema_version": 2, "document_kind": "observed"})


def test_a_missing_schema_version_is_refused() -> None:
    with pytest.raises(MigrationError, match="schema_version"):
        output_migrations.detect_version({"document_kind": "rendered"})


# ---------------------------------------------------------------------------
# v3 -> v4 (ADR 0041)
# ---------------------------------------------------------------------------


def test_v3_fixture_is_version_three_and_no_longer_validates(v3_fixture: dict[str, Any]) -> None:
    """The committed Session 3 render, and the claim that makes v4 a real bump.

    This is the version every deployed host is running right now, so a v3
    document that still validated would mean the bump had changed a label and
    nothing else.
    """
    assert output_migrations.detect_version(v3_fixture) == 3
    assert v3_fixture["document_kind"] == "rendered"
    assert "access_profiles" not in v3_fixture["database"]
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(v3_fixture, "outputs.schema.json")


def test_the_committed_v3_fixture_migrates_and_validates(v3_fixture: dict[str, Any]) -> None:
    at_four = output_migrations.migrate_v3_to_v4(
        v3_fixture, access_profiles=profiles_for(v3_fixture)
    )
    assert at_four["schema_version"] == 4
    migrated = output_migrations.migrate_v4_to_v5(at_four)
    assert migrated["schema_version"] == 5
    config.validate_against_schema(migrated, "outputs.schema.json")


def test_v4_carries_three_profiles_over_two_transports(v4: dict[str, Any]) -> None:
    profiles = v4["database"]["access_profiles"]
    assert set(profiles) == {"runtime_pooled", "runtime_direct", "migration_direct"}
    assert {profile["transport"] for profile in profiles.values()} == {"pooled", "direct"}
    assert profiles["runtime_pooled"]["role"] == profiles["runtime_direct"]["role"]
    assert profiles["migration_direct"]["role"] != profiles["runtime_direct"]["role"]


def test_v4_leaves_every_profile_unprovisioned(v4: dict[str, Any]) -> None:
    """A migration of an archived document cannot produce a deployment."""
    for name, profile in v4["database"]["access_profiles"].items():
        assert profile["status"] == "unavailable", name
        assert profile["password_secret_ref"] is None, name
        assert profile["available_from_session"] == 4, name


def test_v4_preserves_every_other_database_member(v3_fixture: dict[str, Any]) -> None:
    migrated = output_migrations.migrate_v3_to_v4(
        v3_fixture, access_profiles=profiles_for(v3_fixture)
    )
    for key in ("name", "container", "roles", "budget", "pooled", "direct"):
        assert migrated["database"][key] == v3_fixture["database"][key], key


def test_v4_adds_no_observed_block(v4: dict[str, Any]) -> None:
    assert "observed" not in v4["database"]


def test_profile_transports_agree_with_the_schema() -> None:
    """The migrator's copy of the pairing, checked against the authority.

    The schema fixes each profile's transport with a `const`; this module keeps
    its own mapping so that it depends on nothing. Two copies of a fact need a
    test between them, or they are two facts.
    """
    schema = config.load_schema("outputs.schema.json")
    profiles = schema["$defs"]["accessProfiles"]["properties"]
    from_schema = {
        name: definition["allOf"][1]["properties"]["transport"]["const"]
        for name, definition in profiles.items()
    }
    assert from_schema == output_migrations.ACCESS_PROFILE_TRANSPORTS


def test_a_profile_naming_the_wrong_transport_is_refused(v3_fixture: dict[str, Any]) -> None:
    profiles = profiles_for(v3_fixture)
    profiles["runtime_pooled"]["transport"] = "direct"
    with pytest.raises(MigrationError, match="that profile is the 'pooled' transport"):
        output_migrations.migrate_v3_to_v4(v3_fixture, access_profiles=profiles)


def test_a_profile_naming_an_undeclared_role_is_refused(v3_fixture: dict[str, Any]) -> None:
    """The reason this module validates rather than derives.

    A caller that invents a role name gets a refusal naming the document's own
    declaration, not a document that quietly carries a role nothing created.
    """
    profiles = profiles_for(v3_fixture)
    profiles["migration_direct"]["role"] = "apg_some_other_project_migration_user"
    with pytest.raises(MigrationError, match=r"does not declare in database.roles"):
        output_migrations.migrate_v3_to_v4(v3_fixture, access_profiles=profiles)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("status", "available", id="status"),
        pytest.param("password_secret_ref", "app_runtime_password", id="secret-ref"),
    ],
)
def test_a_provisioned_profile_is_refused(
    v3_fixture: dict[str, Any], field: str, value: str
) -> None:
    """Either half alone is enough to refuse, which is why both are parametrized.

    A v3 document records no bound port and no credential. A migrator that
    accepted `available` would be publishing a deployment nobody performed, and
    one that accepted a secret reference would be naming a secret that may never
    have been declared.
    """
    profiles = profiles_for(v3_fixture)
    profiles["runtime_direct"][field] = value
    with pytest.raises(MigrationError, match="claims to be provisioned"):
        output_migrations.migrate_v3_to_v4(v3_fixture, access_profiles=profiles)


@pytest.mark.parametrize(
    "profiles",
    [
        pytest.param({}, id="empty"),
        pytest.param({"runtime_pooled": {}}, id="partial"),
        pytest.param(
            {
                "runtime_pooled": {},
                "runtime_direct": {},
                "migration_direct": {},
                "runtime_extra": {},
            },
            id="extra-profile",
        ),
    ],
)
def test_an_incomplete_profile_set_is_refused(v3_fixture: dict[str, Any], profiles: dict) -> None:
    with pytest.raises(MigrationError, match="access_profiles must have exactly"):
        output_migrations.migrate_v3_to_v4(v3_fixture, access_profiles=profiles)


def test_a_profile_missing_a_member_is_refused(v3_fixture: dict[str, Any]) -> None:
    profiles = profiles_for(v3_fixture)
    del profiles["runtime_direct"]["role"]
    with pytest.raises(MigrationError, match="must have exactly"):
        output_migrations.migrate_v3_to_v4(v3_fixture, access_profiles=profiles)


def test_a_v3_document_is_still_refused_by_the_v2_step(v3_fixture: dict[str, Any]) -> None:
    """Each single step keeps its own narrow refusal as the chain grows."""
    with pytest.raises(MigrationError, match="already version 3"):
        output_migrations.migrate_v2_to_v3(
            v3_fixture, database_budget=BUDGET, database_container=CONTAINER
        )


# ---------------------------------------------------------------------------
# v4 -> v5 (ADR 0053)
# ---------------------------------------------------------------------------


def test_v4_fixture_is_version_four_and_no_longer_validates(v4_fixture: dict[str, Any]) -> None:
    """The committed Session 4 render -- the version every host is running now.

    A v4 document that still validated would mean version 5 had changed a label
    and nothing else, which is a real risk here precisely because the rendered
    branch gained no field. The bump is real because the *schema* moved: the
    rendered branch's `schema_version` enum accepts one value, and it is 5.
    """
    assert output_migrations.detect_version(v4_fixture) == 4
    assert v4_fixture["document_kind"] == "rendered"
    assert "access_profiles" in v4_fixture["database"]
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(v4_fixture, "outputs.schema.json")


def test_the_committed_v4_fixture_migrates_and_validates(v4_fixture: dict[str, Any]) -> None:
    migrated = output_migrations.migrate_v4_to_v5(v4_fixture)
    assert migrated["schema_version"] == 5
    config.validate_against_schema(migrated, "outputs.schema.json")


def test_v5_changes_exactly_one_field(v4_fixture: dict[str, Any]) -> None:
    """The whole content of the step, asserted as a difference rather than described.

    Version 5's additions are all on the deployed branch, so a rendered document
    gains nothing. If a later change makes this step add a member, this fails --
    which is the point: a rendered document that grew a status or a checksum
    would be carrying an observation, and that is the boundary ADR 0012 draws.
    """
    migrated = output_migrations.migrate_v4_to_v5(v4_fixture)
    assert migrated == {**v4_fixture, "schema_version": 5}


def test_v5_adds_no_deployed_member(v4_fixture: dict[str, Any]) -> None:
    """Named individually, because each one is a thing a migrator could invent."""
    migrated = output_migrations.migrate_v4_to_v5(v4_fixture)
    assert "api" not in migrated
    assert "observed" not in migrated["database"]
    assert isinstance(migrated["routes"]["rest"], str)
    assert isinstance(migrated["routes"]["docs"], str)
    assert set(migrated["jwt"]) == {"issuer", "audience"}


def test_the_v5_step_still_refuses_a_deployed_document(v4_fixture: dict[str, Any]) -> None:
    """The cheap step is not a way past the checks the expensive ones make."""
    v4_fixture["document_kind"] = "deployed"
    with pytest.raises(MigrationError, match="expected a 'rendered'"):
        output_migrations.migrate_v4_to_v5(v4_fixture)


def test_the_v5_step_refuses_an_incomplete_document(v4_fixture: dict[str, Any]) -> None:
    del v4_fixture["jwt"]
    with pytest.raises(MigrationError, match="not a complete version 4"):
        output_migrations.migrate_v4_to_v5(v4_fixture)


def test_the_v5_step_refuses_a_document_carrying_deployed_fields(
    v4_fixture: dict[str, Any],
) -> None:
    v4_fixture["observed_at"] = "2026-08-11T00:00:00Z"
    with pytest.raises(MigrationError, match="no version 4 rendered document has"):
        output_migrations.migrate_v4_to_v5(v4_fixture)


def test_a_v3_document_is_refused_by_the_v5_step(v3_fixture: dict[str, Any]) -> None:
    """A v3 document has every top-level key a v4 one has, and is not one.

    This is why the step looks inside `database` as well as at the top level:
    version 4's addition was a member, so the outer shape alone cannot tell the
    two apart, and a step that skipped v3 -> v4 would silently produce a v5
    document with no `access_profiles` in it.
    """
    with pytest.raises(MigrationError, match="only version 4 can be migrated to 5"):
        output_migrations.migrate_v4_to_v5(v3_fixture)

    mislabelled = {**v3_fixture, "schema_version": 4}
    with pytest.raises(MigrationError, match="access_profiles is missing"):
        output_migrations.migrate_v4_to_v5(mislabelled)


def test_the_v5_step_does_not_mutate_its_input(v4_fixture: dict[str, Any]) -> None:
    before = json.dumps(v4_fixture, sort_keys=True)
    output_migrations.migrate_v4_to_v5(v4_fixture)
    assert json.dumps(v4_fixture, sort_keys=True) == before


def test_a_v4_document_is_still_refused_by_the_v3_step(v4_fixture: dict[str, Any]) -> None:
    """Each single step keeps its own narrow refusal as the chain grows."""
    with pytest.raises(MigrationError, match="already version 4"):
        output_migrations.migrate_v3_to_v4(v4_fixture, access_profiles=profiles_for(v4_fixture))
