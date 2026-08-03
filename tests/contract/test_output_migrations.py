"""Output schema v1 to v2 migration and document-kind rejection (ADR 0012).

The fixture at ``tests/fixtures/outputs-v1.json`` is a real Session 1 render,
not a hand-built object. A hand-built fixture drifts away from what was actually
shipped, and then the migrator is proved to handle a document that never
existed.

Two negative properties carry more weight here than the positive one:

* the migrator refuses to invent a ``deployed`` document, because every field
  that distinguishes one is an observation;
* a rendered document is refused where deployed state is required, and the
  refusal happens at the boundary rather than as a ``KeyError`` further in.
  The two files share a basename, so passing the wrong path is the realistic
  mistake.
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, config, naming, output_migrations
from agentic_postgres.output_migrations import MigrationError

pytestmark = [pytest.mark.contract, pytest.mark.p0]

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "outputs-v1.json"

CONTRACT_DIGEST = sha256((REPO_ROOT / "secrets.required.yaml").read_bytes()).hexdigest()


@pytest.fixture
def v1() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def v2(v1: dict[str, Any]) -> dict[str, Any]:
    return output_migrations.migrate_rendered(v1, secrets_contract_sha256=CONTRACT_DIGEST)


# ---------------------------------------------------------------------------
# The fixture is a genuine v1 document
# ---------------------------------------------------------------------------


def test_fixture_is_version_one_and_no_longer_validates(v1: dict[str, Any]) -> None:
    """A v1 document must fail the v2 schema, or the migration is decorative."""
    assert output_migrations.detect_version(v1) == 1
    assert "document_kind" not in v1
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(v1, "outputs.schema.json")


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def test_migrated_document_validates(v2: dict[str, Any]) -> None:
    config.validate_against_schema(v2, "outputs.schema.json")


def test_migration_sets_the_rendered_kind(v2: dict[str, Any]) -> None:
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


def test_migration_preserves_every_other_field(v1: dict[str, Any], v2: dict[str, Any]) -> None:
    for key in ("project", "compose", "database", "jwt", "storage", "backup", "capabilities"):
        assert v2[key] == v1[key], key
    assert v2["template_version"] == v1["template_version"]


def test_migration_does_not_mutate_its_input(v1: dict[str, Any]) -> None:
    before = json.dumps(v1, sort_keys=True)
    output_migrations.migrate_rendered(v1, secrets_contract_sha256=CONTRACT_DIGEST)
    assert json.dumps(v1, sort_keys=True) == before


# ---------------------------------------------------------------------------
# The digest it refuses to guess
# ---------------------------------------------------------------------------


def test_migration_requires_a_real_contract_digest(v1: dict[str, Any]) -> None:
    """The `inputs` block's whole value is that its digests are real."""
    with pytest.raises(MigrationError, match="64 lowercase hex"):
        output_migrations.migrate_rendered(v1, secrets_contract_sha256="<computed SHA-256>")


def test_migrated_inputs_carry_the_supplied_digest(v2: dict[str, Any]) -> None:
    assert v2["inputs"]["secrets_contract_sha256"] == CONTRACT_DIGEST
    assert len(v2["inputs"]) == 5


# ---------------------------------------------------------------------------
# What the migrator refuses
# ---------------------------------------------------------------------------


def test_a_v2_document_is_not_migrated_again(v2: dict[str, Any]) -> None:
    with pytest.raises(MigrationError, match="already version 2"):
        output_migrations.migrate_rendered(v2, secrets_contract_sha256=CONTRACT_DIGEST)


def test_an_incomplete_v1_document_is_refused(v1: dict[str, Any]) -> None:
    del v1["jwt"]
    with pytest.raises(MigrationError, match="missing"):
        output_migrations.migrate_rendered(v1, secrets_contract_sha256=CONTRACT_DIGEST)


def test_a_document_with_unexpected_fields_is_refused(v1: dict[str, Any]) -> None:
    """Something claiming to be v1 while carrying v2 fields is not v1."""
    v1["tls"] = {"status": "issued"}
    with pytest.raises(MigrationError, match="no version 1 document has"):
        output_migrations.migrate_rendered(v1, secrets_contract_sha256=CONTRACT_DIGEST)


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
