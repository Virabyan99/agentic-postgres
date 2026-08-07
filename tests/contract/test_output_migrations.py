"""Output schema migration and document-kind rejection (ADR 0012, ADR 0027).

Both fixtures are real renders, not hand-built objects: ``outputs-v1.json`` is a
Session 1 render and ``outputs-v2.json`` is a Session 2 one. A hand-built
fixture drifts away from what was actually shipped, and then the migrator is
proved to handle a document that never existed.

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

CONTRACT_DIGEST = sha256((REPO_ROOT / "secrets.required.yaml").read_bytes()).hexdigest()

#: What a caller supplies for the v3 step. Taken from the real resolver rather
#: than written out, so a change to the budget's shape fails here rather than
#: producing a fixture that agrees only with itself.
BUDGET = config.database_budget({})
CONTAINER = "apg-fixture-alpha-dev-postgres-1"


@pytest.fixture
def v1() -> dict[str, Any]:
    return json.loads(FIXTURE_V1.read_text(encoding="utf-8"))


@pytest.fixture
def v2_fixture() -> dict[str, Any]:
    """The committed Session 2 render."""
    return json.loads(FIXTURE_V2.read_text(encoding="utf-8"))


@pytest.fixture
def v2(v1: dict[str, Any]) -> dict[str, Any]:
    """The v1 fixture advanced one step."""
    return output_migrations.migrate_v1_to_v2(v1, secrets_contract_sha256=CONTRACT_DIGEST)


@pytest.fixture
def v3(v1: dict[str, Any]) -> dict[str, Any]:
    """The whole chain, v1 -> v2 -> v3, through the public entry point."""
    return output_migrations.migrate_rendered(
        v1,
        secrets_contract_sha256=CONTRACT_DIGEST,
        database_budget=BUDGET,
        database_container=CONTAINER,
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
    )
    assert json.dumps(v1, sort_keys=True) == before


# ---------------------------------------------------------------------------
# v2 -> v3
# ---------------------------------------------------------------------------


def test_the_committed_v2_fixture_migrates_and_validates(v2_fixture: dict[str, Any]) -> None:
    migrated = output_migrations.migrate_v2_to_v3(
        v2_fixture, database_budget=BUDGET, database_container=CONTAINER
    )
    assert migrated["schema_version"] == 3
    config.validate_against_schema(migrated, "outputs.schema.json")


def test_the_whole_chain_validates(v3: dict[str, Any]) -> None:
    """v1 -> v2 -> v3 end to end, not only the newest link (ADR 0027)."""
    assert v3["schema_version"] == 3
    assert v3["document_kind"] == "rendered"
    config.validate_against_schema(v3, "outputs.schema.json")


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
        )


def test_migrated_inputs_carry_the_supplied_digest(v3: dict[str, Any]) -> None:
    assert v3["inputs"]["secrets_contract_sha256"] == CONTRACT_DIGEST
    assert len(v3["inputs"]) == 5


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


def test_a_current_version_document_is_not_migrated_again(v3: dict[str, Any]) -> None:
    """Replaces the v2 form of this assertion, applied to the current version.

    ADR 0017's rule: a test may only be replaced by a stricter one. This is the
    same property -- migrating a document that is already current is a no-op and
    is refused -- now asserted through the chaining entry point as well as the
    single step, which the previous version did not cover.
    """
    with pytest.raises(MigrationError, match="already version 3"):
        output_migrations.migrate_rendered(
            v3,
            secrets_contract_sha256=CONTRACT_DIGEST,
            database_budget=BUDGET,
            database_container=CONTAINER,
        )
    with pytest.raises(MigrationError, match="already version 3"):
        output_migrations.migrate_v2_to_v3(v3, database_budget=BUDGET, database_container=CONTAINER)


def test_a_v2_document_is_still_refused_by_the_v1_step(v2_fixture: dict[str, Any]) -> None:
    """The single step keeps its own narrow refusal."""
    with pytest.raises(MigrationError, match="already version 2"):
        output_migrations.migrate_v1_to_v2(v2_fixture, secrets_contract_sha256=CONTRACT_DIGEST)


def test_an_unknown_version_is_refused(v1: dict[str, Any]) -> None:
    v1["schema_version"] = 99
    with pytest.raises(MigrationError, match="only versions 1 and 2"):
        output_migrations.migrate_rendered(
            v1,
            secrets_contract_sha256=CONTRACT_DIGEST,
            database_budget=BUDGET,
            database_container=CONTAINER,
        )


def test_an_incomplete_v1_document_is_refused(v1: dict[str, Any]) -> None:
    del v1["jwt"]
    with pytest.raises(MigrationError, match="missing"):
        output_migrations.migrate_rendered(
            v1,
            secrets_contract_sha256=CONTRACT_DIGEST,
            database_budget=BUDGET,
            database_container=CONTAINER,
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
