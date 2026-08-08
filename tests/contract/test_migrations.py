"""Migration manifest, renderer and released lock (ADR 0028).

Everything here is offline. Rendering is a pure function of a manifest, a
template and a rendered outputs document, so determinism, the placeholder
contract and every mutation case are provable in a checkout with no cluster.

The mutation cases carry the weight. A renderer that works on correct input
proves very little -- `render-config.py` worked on correct input in Session 2
and still produced a file Traefik silently discarded. What is asserted here is
what the machinery *refuses*: an edited applied migration, a removed one, a
duplicate version, an unknown placeholder, a placeholder whose name looks like
a credential, an identifier too long to survive PostgreSQL's truncation, and a
render that is not reproducible.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, config, migrations
from agentic_postgres.migrations import MigrationError

pytestmark = [pytest.mark.contract, pytest.mark.p0]

FIXTURE_OUTPUTS = REPO_ROOT / ".generated" / "fixture-alpha-dev" / "outputs.json"


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return migrations.load_manifest()


@pytest.fixture(scope="module")
def outputs() -> dict[str, Any]:
    if not FIXTURE_OUTPUTS.exists():
        pytest.skip("fixtures are not rendered in this working tree")
    return json.loads(FIXTURE_OUTPUTS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def lock() -> dict[str, Any]:
    return migrations.load_lock()


def write_manifest(tmp_path: Path, document: dict[str, Any]) -> Path:
    """A manifest beside a copy of the real templates.

    The templates are copied rather than stubbed so a mutation case fails for
    the reason it names, instead of because a hand-written template happened
    not to use the placeholder under test.
    """
    import shutil

    shutil.copytree(migrations.MIGRATIONS_ROOT / "templates", tmp_path / "templates")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# The committed set is coherent
# ---------------------------------------------------------------------------


def test_the_committed_manifest_loads(manifest: dict[str, Any]) -> None:
    """A count, not a number.

    This asserted `== 5` until Session 4 added a sixth migration, at which point
    it failed for a reason that had nothing to do with the manifest loading. The
    property worth having is that the manifest lists every template on disk and
    no more; a literal restates the answer and has to be edited by whoever adds
    a migration, which is the one person least likely to notice it is wrong.
    """
    assert manifest["schema_version"] == 1

    listed = {entry["template"] for entry in manifest["migrations"]}
    on_disk = {
        f"templates/{path.name}" for path in (REPO_ROOT / "migrations" / "templates").glob("*.sql")
    }
    assert listed == on_disk, "the manifest and templates/ disagree about what exists"


def test_versions_are_unique_and_ordered(manifest: dict[str, Any]) -> None:
    versions = [entry["version"] for entry in manifest["migrations"]]
    assert versions == sorted(versions)
    assert len(set(versions)) == len(versions)


def test_every_template_exists_and_is_referenced_once(manifest: dict[str, Any]) -> None:
    referenced = [entry["template"] for entry in manifest["migrations"]]
    assert len(set(referenced)) == len(referenced), "a template is used by two migrations"

    on_disk = sorted(
        str(path.relative_to(migrations.MIGRATIONS_ROOT))
        for path in (migrations.MIGRATIONS_ROOT / "templates").glob("*.sql")
    )
    assert sorted(referenced) == on_disk, "a template exists that no migration renders"


def test_every_migration_declares_both_dbmate_blocks(manifest: dict[str, Any]) -> None:
    for entry in manifest["migrations"]:
        text = (migrations.MIGRATIONS_ROOT / entry["template"]).read_text(encoding="utf-8")
        assert "-- migrate:up" in text, entry["version"]
        assert "-- migrate:down" in text, entry["version"]


def test_no_migration_permits_a_non_transactional_apply(manifest: dict[str, Any]) -> None:
    """Plan §4.3: `transaction:false` is not permitted in this set.

    A migration that opts out of the transaction can leave a schema half-built
    with a version already stamped, which is the one state the five-way
    preflight cannot untangle.
    """
    for entry in manifest["migrations"]:
        text = (migrations.MIGRATIONS_ROOT / entry["template"]).read_text(encoding="utf-8")
        assert "transaction:false" not in text.replace(" ", ""), entry["version"]


def test_every_down_block_refuses(manifest: dict[str, Any]) -> None:
    """Released platform migrations are fix-forward only (ADR 0028)."""
    for entry in manifest["migrations"]:
        text = (migrations.MIGRATIONS_ROOT / entry["template"]).read_text(encoding="utf-8")
        down = text.split("-- migrate:down", 1)[1]
        assert "AP900" in down, f"{entry['version']}: down block does not raise AP900"
        assert "DROP" not in down.upper(), f"{entry['version']}: down block drops something"


def test_every_up_block_assumes_and_returns_the_owner_role(manifest: dict[str, Any]) -> None:
    """ADR 0026: objects are owned by object_owner, versions stamped by migration_user.

    A migration that assumed the role and never returned it would leave the
    session as the owner for whatever dbmate did next.
    """
    for entry in manifest["migrations"]:
        text = (migrations.MIGRATIONS_ROOT / entry["template"]).read_text(encoding="utf-8")
        up = text.split("-- migrate:down", 1)[0]
        assert "SET LOCAL ROLE" in up, entry["version"]
        assert "RESET ROLE" in up, entry["version"]
        assert up.index("SET LOCAL ROLE") < up.index("RESET ROLE"), entry["version"]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_rendering_is_deterministic(manifest: dict[str, Any], outputs: dict[str, Any]) -> None:
    """DBX-MIG-002's offline half: two renders of one input agree byte for byte."""
    for entry in manifest["migrations"]:
        first = migrations.render_migration(entry, manifest, outputs)
        second = migrations.render_migration(entry, manifest, outputs)
        assert first == second, entry["version"]


def test_rendering_carries_no_deployment_metadata(
    manifest: dict[str, Any], outputs: dict[str, Any]
) -> None:
    """No timestamp, no commit, no hostname -- or determinism is accidental."""
    import socket

    for entry in manifest["migrations"]:
        rendered = migrations.render_migration(entry, manifest, outputs)
        assert socket.gethostname() not in rendered
        assert "20" + "26-08" not in rendered.replace(entry["version"], "")


def test_two_projects_render_different_payloads(manifest: dict[str, Any]) -> None:
    """The reason the rendered payload is the immutable unit, not the template.

    Same template, two projects, different bytes and therefore different
    digests. A lock that recorded the template digest would record one value
    for both and notice nothing when a naming rule changed underneath.
    """
    alpine = REPO_ROOT / ".generated" / "fixture-alpine-dev" / "outputs.json"
    alpha = REPO_ROOT / ".generated" / "fixture-alpha-dev" / "outputs.json"
    if not (alpine.exists() and alpha.exists()):
        pytest.skip("both fixtures are not rendered in this working tree")

    left = json.loads(alpha.read_text(encoding="utf-8"))
    right = json.loads(alpine.read_text(encoding="utf-8"))
    entry = manifest["migrations"][0]

    rendered_left = migrations.render_migration(entry, manifest, left)
    rendered_right = migrations.render_migration(entry, manifest, right)
    assert rendered_left != rendered_right
    assert migrations.digest(rendered_left) != migrations.digest(rendered_right)


def test_no_placeholder_survives_rendering(
    manifest: dict[str, Any], outputs: dict[str, Any]
) -> None:
    for entry in manifest["migrations"]:
        rendered = migrations.render_migration(entry, manifest, outputs)
        assert "{{" not in rendered and "}}" not in rendered, entry["version"]


def test_identifiers_are_quoted_in_the_rendered_output(
    manifest: dict[str, Any], outputs: dict[str, Any]
) -> None:
    """Quoted, not interpolated bare. An identifier reaching SQL as raw text is
    one reserved word away from parsing as something else."""
    entry = manifest["migrations"][0]
    rendered = migrations.render_migration(entry, manifest, outputs)
    owner = outputs["database"]["roles"]["object_owner"]
    assert f'"{owner}"' in rendered


# ---------------------------------------------------------------------------
# Mutation cases -- what the machinery refuses
# ---------------------------------------------------------------------------


def test_an_edited_applied_migration_is_detected(
    manifest: dict[str, Any], lock: dict[str, Any], tmp_path: Path
) -> None:
    """The case ADR 0028 exists for. One byte, and the lock disagrees."""
    import shutil

    shutil.copytree(migrations.MIGRATIONS_ROOT / "templates", tmp_path / "templates")
    target = tmp_path / manifest["migrations"][0]["template"]
    target.write_text(target.read_text(encoding="utf-8") + "\n-- edited\n", encoding="utf-8")

    with pytest.raises(MigrationError, match="template_sha256 disagrees"):
        migrations.verify_lock(manifest, lock, root=tmp_path)


def test_a_removed_migration_is_detected(manifest: dict[str, Any], lock: dict[str, Any]) -> None:
    shortened = copy.deepcopy(manifest)
    shortened["migrations"] = shortened["migrations"][:-1]
    with pytest.raises(MigrationError, match="the lock records migrations the manifest"):
        migrations.verify_lock(shortened, lock)


def test_an_unlocked_migration_is_detected(manifest: dict[str, Any], lock: dict[str, Any]) -> None:
    """Nothing may be applied before its entry is committed."""
    partial = copy.deepcopy(lock)
    partial["migrations"] = partial["migrations"][:-1]
    with pytest.raises(MigrationError, match="absent from the released lock"):
        migrations.verify_lock(manifest, partial)


def test_a_duplicate_version_is_refused(manifest: dict[str, Any], tmp_path: Path) -> None:
    broken = copy.deepcopy(manifest)
    broken["migrations"][1]["version"] = broken["migrations"][0]["version"]
    path = write_manifest(tmp_path, broken)
    with pytest.raises(MigrationError, match="duplicate migration versions"):
        migrations.load_manifest(path)


def test_out_of_order_versions_are_refused(manifest: dict[str, Any], tmp_path: Path) -> None:
    broken = copy.deepcopy(manifest)
    broken["migrations"].reverse()
    path = write_manifest(tmp_path, broken)
    with pytest.raises(MigrationError, match="ascending version order"):
        migrations.load_manifest(path)


def test_an_undeclared_placeholder_is_refused(manifest: dict[str, Any], tmp_path: Path) -> None:
    broken = copy.deepcopy(manifest)
    broken["migrations"][0]["placeholders"].remove("object_owner")
    path = write_manifest(tmp_path, broken)
    with pytest.raises(MigrationError, match="placeholder list omits"):
        migrations.load_manifest(path)


def test_a_declared_but_unused_placeholder_is_refused(
    manifest: dict[str, Any], tmp_path: Path
) -> None:
    """A stale declaration reads as evidence that a value still reaches the SQL."""
    broken = copy.deepcopy(manifest)
    broken["migrations"][1]["placeholders"].append("agent_reader")
    path = write_manifest(tmp_path, broken)
    with pytest.raises(MigrationError, match="never uses"):
        migrations.load_manifest(path)


def test_an_unknown_placeholder_is_refused_at_render(
    manifest: dict[str, Any], outputs: dict[str, Any]
) -> None:
    with pytest.raises(MigrationError, match="no value supplied"):
        migrations.render("SELECT {{nobody_declared_this}};", {})


@pytest.mark.parametrize(
    "name",
    [
        "postgres_password",
        "migration_secret",
        "api_token",
        "signing_key",
        "database_url",
        "service_credentials",
    ],
)
def test_a_credential_shaped_placeholder_name_is_refused(
    manifest: dict[str, Any], tmp_path: Path, name: str
) -> None:
    """A migration is committed to a lock, a ledger and every reader of the
    database. A placeholder that could carry a credential has no business
    existing, and the refusal is by terminal token, the same rule as ADR 0008."""
    broken = copy.deepcopy(manifest)
    broken["placeholders"][name] = {
        "type": "literal",
        "source": "database.name",
        "description": "should never be accepted",
    }
    path = write_manifest(tmp_path, broken)
    with pytest.raises(config.ManifestError):
        migrations.load_manifest(path)


def test_an_over_length_identifier_is_refused() -> None:
    """PostgreSQL truncates at 63 bytes silently, which turns two distinct role
    names into one object."""
    with pytest.raises(MigrationError, match="exceeds 63 bytes"):
        migrations.quote_identifier("a" * 64)


@pytest.mark.parametrize(
    "value", ["Mixed_Case", "has space", "has-dash", "1leading", "", 'quote"inside']
)
def test_a_non_identifier_is_refused(value: str) -> None:
    with pytest.raises(MigrationError, match="not a bare lowercase SQL identifier"):
        migrations.quote_identifier(value)


def test_a_literal_is_escaped_not_interpolated() -> None:
    assert migrations.quote_literal("it's") == "'it''s'"


def test_residue_after_substitution_is_refused() -> None:
    """`{{ name }}` with spaces does not match the substitution pattern.

    Without the residue check it would reach the database as literal text
    inside otherwise valid SQL, which is a syntax error at apply time on a host
    rather than a failure in a checkout.
    """
    with pytest.raises(MigrationError, match="unresolved placeholder syntax"):
        migrations.render("SELECT {{ spaced }};", {})


def test_a_source_the_document_lacks_is_refused(manifest: dict[str, Any]) -> None:
    with pytest.raises(MigrationError, match="which the rendered document does not have"):
        migrations.resolve_placeholders(manifest, {"database": {}}, ["object_owner"])


# ---------------------------------------------------------------------------
# The lock
# ---------------------------------------------------------------------------


def test_the_committed_lock_verifies(manifest: dict[str, Any], lock: dict[str, Any]) -> None:
    """The gate verifies the lock and never writes it."""
    migrations.verify_lock(manifest, lock)


def test_the_lock_covers_every_migration(manifest: dict[str, Any], lock: dict[str, Any]) -> None:
    assert [entry["version"] for entry in lock["migrations"]] == [
        entry["version"] for entry in manifest["migrations"]
    ]


def test_the_lock_carries_no_project_identity(lock: dict[str, Any]) -> None:
    """It is committed, and the projects it covers are gitignored manifests.

    A per-project rendered digest here would be either wrong for every real
    deployment or a fixture identity in deployable source, which
    test_repository_contract.py forbids. The per-project digest lives in the
    database ledger; this file holds the canonical one.
    """
    text = json.dumps(lock)
    for marker in ("fixture-alpha", "fixture-alpine", "alpha-dev", "beta-dev", "apg_"):
        assert marker not in text, f"the released lock names {marker}"


def test_a_changed_renderer_moves_the_canonical_digest(manifest: dict[str, Any]) -> None:
    """What `canonical_render_sha256` is actually for.

    The template digest catches an edited template and the placeholder list
    catches a changed substitution surface. Neither notices the renderer itself
    changing -- different quoting, say -- under templates nobody touched.
    """
    built = migrations.build_lock(manifest)
    canonical = migrations.canonical_outputs(manifest)
    entry = manifest["migrations"][0]
    values = migrations.resolve_placeholders(manifest, canonical, entry["placeholders"])

    template = (migrations.MIGRATIONS_ROOT / entry["template"]).read_text(encoding="utf-8")
    unquoted = {name: value.strip('"') for name, value in values.items()}
    assert migrations.digest(migrations.render(template, unquoted)) != next(
        item["canonical_render_sha256"]
        for item in built["migrations"]
        if item["version"] == entry["version"]
    )
