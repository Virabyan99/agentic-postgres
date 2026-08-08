"""The rendered migration set: the payload dbmate actually reads.

ADR 0028 makes the *rendered* text the immutable unit, not the template. Until
Run 7 nothing wrote it: `.generated/<key>/` held three files, `migrate.sh up`
printed a list and applied nothing, and the dbmate service had no `/migrations`
mount to read (D60). These tests are about the artifact, its modes, and the one
property that makes handing dbmate a *directory* safe -- that the files in it
are the payloads this release rendered and nothing else.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT, migrations, rendering

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.database]

ALPHA = REPO_ROOT / ".generated" / "fixture-alpha-dev"
MIGRATIONS = ALPHA / "migrations"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads((MIGRATIONS / rendering.MIGRATION_MANIFEST_NAME).read_text(encoding="utf-8"))


def test_the_rendered_set_exists_beside_the_document_that_produced_it() -> None:
    assert MIGRATIONS.is_dir(), "render wrote no migrations directory"
    assert sorted(path.name for path in MIGRATIONS.glob("*.sql"))


def test_one_file_per_declared_migration(manifest: dict) -> None:
    declared = migrations.load_manifest()["migrations"]
    assert len(manifest["migrations"]) == len(declared)
    assert {path.name for path in MIGRATIONS.glob("*.sql")} == {
        entry["file"] for entry in manifest["migrations"]
    }


def test_each_recorded_digest_is_the_digest_of_the_file(manifest: dict) -> None:
    """The manifest describes these bytes, not the template they came from."""
    for entry in manifest["migrations"]:
        payload = (MIGRATIONS / entry["file"]).read_text(encoding="utf-8")
        assert migrations.digest(payload) == entry["sha256"], entry["file"]


def test_the_filename_carries_the_version_dbmate_will_record(manifest: dict) -> None:
    """dbmate parses `<version>_<name>.sql` and keeps the version forever."""
    for entry in manifest["migrations"]:
        assert entry["file"] == f"{entry['version']}_{entry['name']}.sql"


def test_no_placeholder_survives_into_the_rendered_payload() -> None:
    """The residue check, asserted on the artifact rather than on the renderer.

    `render()` refuses leftover markers, but that is a property of a function;
    this is a property of the files a container will execute.
    """
    for path in MIGRATIONS.glob("*.sql"):
        text = path.read_text(encoding="utf-8")
        assert not migrations.RESIDUE.search(text), path.name


def test_the_rendered_sql_names_this_project_and_not_the_template(manifest: dict) -> None:
    """A rendered set that still said `{{object_owner}}` would be caught above;
    one rendered against the *wrong* project would not. Every file must carry
    this project's derived owner."""
    document = json.loads((ALPHA / "outputs.json").read_text(encoding="utf-8"))
    owner = document["database"]["roles"]["object_owner"]
    assert manifest["project_key"] == document["project"]["key"]
    assert any(
        owner in (MIGRATIONS / entry["file"]).read_text(encoding="utf-8")
        for entry in manifest["migrations"]
    )


def test_the_modes_are_the_ones_a_non_root_container_can_read() -> None:
    """0600 everywhere else, and deliberately not here.

    dbmate reads these as uid 65532 from inside a container. A 0600 file it
    cannot open fails as "permission denied" from the one service whose whole
    job is to touch the schema -- a long way from where the mode was set.
    """
    assert MIGRATIONS.stat().st_mode & 0o777 == rendering.MIGRATION_DIRECTORY_MODE
    for path in MIGRATIONS.iterdir():
        assert path.stat().st_mode & 0o777 == rendering.MIGRATION_FILE_MODE, path.name


def test_everything_else_in_the_rendered_directory_stays_owner_only() -> None:
    """The exemption is narrow, and this is what keeps it narrow."""
    for path in ALPHA.iterdir():
        if path.name == "migrations":
            continue
        assert path.stat().st_mode & 0o777 == rendering.FILE_MODE, path.name


def test_the_install_exemption_is_the_migrations_directory_and_nothing_deeper() -> None:
    """Source-level, because the installer needs root to run.

    `"migrations" in path.parts` would widen the mode of anything a future
    render put under a directory of that name at any depth. The predicate is
    written against one directory and its immediate children.
    """
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    assert "_is_migration_artifact" in source
    assert 'staging / "migrations"' in source
    assert "path.parent == migrations_dir" in source


def test_the_verifier_refuses_a_file_edited_after_rendering(tmp_path: Path) -> None:
    """The property that makes handing dbmate a directory safe.

    dbmate applies whatever is in the directory it is given; comparing each
    file against the manifest written beside it is what makes ADR 0028's
    immutable payload a fact about what runs.
    """
    import importlib.util

    specification = importlib.util.spec_from_file_location(
        "migrate_helper", REPO_ROOT / "bin" / "migrate.py"
    )
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)

    directory = tmp_path / "migrations"
    directory.mkdir()
    payload = "SELECT 1;\n"
    (directory / "0001_x.sql").write_text(payload, encoding="utf-8")
    (directory / rendering.MIGRATION_MANIFEST_NAME).write_text(
        json.dumps(
            {
                "project_key": "alpha-dev",
                "migrations_table": rendering.MIGRATIONS_TABLE,
                "migrations": [
                    {
                        "version": "0001",
                        "name": "x",
                        "file": "0001_x.sql",
                        "sha256": migrations.digest(payload),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    module.assert_rendered_files_match(str(tmp_path))

    (directory / "0001_x.sql").write_text("DROP TABLE notes;\n", encoding="utf-8")
    with pytest.raises(migrations.MigrationError, match="edited after rendering"):
        module.assert_rendered_files_match(str(tmp_path))

    (directory / "0001_x.sql").write_text(payload, encoding="utf-8")
    (directory / "0002_planted.sql").write_text("SELECT 2;\n", encoding="utf-8")
    with pytest.raises(migrations.MigrationError, match="does not match its manifest"):
        module.assert_rendered_files_match(str(tmp_path))
