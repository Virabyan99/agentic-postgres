"""The rendered migration set: the payload dbmate actually reads.

ADR 0028 makes the *rendered* text the immutable unit, not the template. Until
Run 7 nothing wrote it: `.generated/<key>/` held three files, `migrate.sh up`
printed a list and applied nothing, and the dbmate service had no `/migrations`
mount to read (D60). These tests are about the artifact, its modes, and the one
property that makes handing dbmate a *directory* safe -- that the files in it
are the payloads this release rendered and nothing else.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT, migrations, rendering, secrets_contract


def _calls(node: ast.Call, name: str) -> bool:
    """Whether this call is `name(...)` or `something.name(...)`."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == name
    return isinstance(func, ast.Name) and func.id == name


def _calls_chmod(node: ast.Call) -> bool:
    return _calls(node, "chmod")


def _calls_chown(node: ast.Call) -> bool:
    return _calls(node, "chown")


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


#: The three things in a rendered directory that are not `0600`, and why.
#:
#: Every entry a rendered project directory may contain, with the **exact** mode
#: it must carry — not a list of names to skip (ADR 0154).
#:
#: This replaced a `RENDERED_EXEMPTIONS` set when Session 10 added a third mode.
#: The set had a hole this mapping does not: an exempted name was `continue`d,
#: so nothing asserted its mode at all and `openapi.json` could have been `0666`
#: and stayed green. Here every entry states its mode, and a file the mapping
#: does not name is a failure rather than a silent pass.
#:
#: `migrations` is a directory the render widens so dbmate can read it.
#: `openapi.json` and `app-openapi.json` are the reviewed OpenAPI snapshots the
#: two documentation surfaces serve (D226): each is a **published document**
#: rather than a description of a deployment, each is a committed artefact a
#: human approved, and the container that reads them runs as 65532 rather than
#: as the owner of this directory (ADR 0069).
#: `pgbackrest.conf` is the archiver's configuration, read by a container
#: running as **999**. It was `0600` until a deploy proved it unreadable from
#: two places at once — step 6c and every `archive_command` after it (D588).
#:
#: A `0600` copy of any of the four would reach its mount unreadable. For the
#: snapshots `serve.py` reports 503; for the config pgBackRest reports
#: `[041] … Permission denied`. Both are correct, and both are permanent.
#:
#: **Every name and every mode here is a literal, and that is deliberate.**
#: The first draft wrote `rendering.PGBACKREST_CONF_MODE` and friends, and
#: battery Q1 -- D588 reintroduced, `PGBACKREST_CONF_MODE` set back to `0o600`
#: -- **survived it**: mutating the constant moved both sides of the assertion
#: at once. That is §6's *a test comparing two constants is not testing the
#: thing between them*, and it made the test tautological for exactly the drift
#: it exists to catch. `rendering.py` holds the reasoning for each mode; this
#: holds the contract, and the two have to be able to disagree.
#: `otelcol.yaml` is Session 14's metrics collector pipeline (ADR 0164), read by
#: a container running as a uid that does not own the rendered directory. It is
#: world-readable on the snapshots' terms rather than the archiver's: **it holds
#: no secret and structurally cannot.** The credential guarding the surface it
#: serves is a bcrypt hash in the edge's dynamic document (ADR 0086), and
#: `secrets.required.yaml` declares that password with a root-plane consumer
#: only -- so there is no path by which a value in this file could be one. A
#: `0600` copy would reach the mount unreadable and the collector would exit at
#: startup: loud, but it reads as a bad config rather than a bad mode.
RENDERED_FILE_MODES: dict[str, int] = {
    "migrations": 0o755,
    "compose.env": 0o600,
    "outputs.json": 0o600,
    "rendered-summary.txt": 0o600,
    "pgbackrest.conf": 0o444,
    "openapi.json": 0o444,
    "app-openapi.json": 0o444,
    "otelcol.yaml": 0o444,
    # Session 14 Run 5's store (ADR 0168), on exactly the terms
    # `otelcol.yaml` is on: the store runs as `nobody`, does not own
    # this directory, and neither file holds a secret. It scrapes one
    # target on the project's own network over plain HTTP, and the
    # credential that guards the metrics ROUTE is a Traefik concern
    # that nothing in the metrics plane holds (ADR 0164).
    #
    # Measured rather than reasoned about: mounting the rendered
    # DIRECTORY into the store fails with `permission denied` because
    # it is 0700, and the deployment bind-mounts each file instead --
    # which is why the file's own mode is what decides readability.
    "prometheus.yaml": 0o444,
    "alert-rules.yaml": 0o444,
}


def test_every_rendered_entry_has_a_stated_mode_and_carries_it() -> None:
    """Both directions, from the directory (ADR 0154).

    The mapping is closed *and* exact: an entry the render produces that nobody
    stated a mode for fails, and a stated entry whose mode drifted fails. The
    predecessor asserted only the second, and only for the names it did not skip.
    """
    present = {path.name for path in ALPHA.iterdir()}
    stated = set(RENDERED_FILE_MODES)

    assert present == stated, (
        f"the render produced {sorted(present - stated)} that no mode is stated for, and "
        f"states {sorted(stated - present)} that it did not produce. A new rendered "
        "artefact needs a row in RENDERED_FILE_MODES with the reason for its mode "
        "(ADR 0154) -- not an exemption."
    )

    for path in sorted(ALPHA.iterdir()):
        expected = RENDERED_FILE_MODES[path.name]
        assert path.stat().st_mode & 0o777 == expected, (
            f"{path.name} is {path.stat().st_mode & 0o777:04o}, stated {expected:04o}"
        )


def test_no_world_readable_rendered_file_carries_credential_material() -> None:
    """The closed list, and then the property the list is standing in for.

    Written from the directory rather than from the mapping, so a fourth
    world-readable artefact goes red here even if somebody remembered to give it
    a row above -- that is the direction that matters.

    And a name on the list is no longer sufficient (ADR 0154). Each
    world-readable file is *read*, and asserted to contain none of the pgBackRest
    options the credential files set. Those option names come from the secrets
    contract rather than from a list written here, so a fourth credential added
    to `secrets.required.yaml` is covered on the day it is added. The predecessor
    checked names only, and a correctly-listed file that began carrying a secret
    would have passed it.
    """
    readable = sorted(
        path.name for path in ALPHA.iterdir() if path.is_file() and path.stat().st_mode & 0o004
    )
    # Literals, for the reason RENDERED_FILE_MODES states: a name read from the
    # renderer moves with the renderer, and the list would agree with itself
    # through a rename nobody reviewed.
    assert readable == sorted(
        [
            "openapi.json",
            "app-openapi.json",
            "pgbackrest.conf",
            "otelcol.yaml",
            # Widened in Run 5 to the measured set, with the reason (ADR
            # 0168) -- and still an exact equality rather than a
            # containment check, because loosening this to `issubset`
            # is the move the non-negotiables forbid.
            "prometheus.yaml",
            "alert-rules.yaml",
        ]
    ), (
        f"{readable} are world-readable in the rendered directory. Only the two published "
        "snapshots, the archiver's config and the two telemetry configurations may be: the "
        "snapshots because they are served to whoever holds the documentation credential, "
        "the archiver's config because it runs as 999 (ADR 0154), and the collector's and "
        "the store's because each runs as a uid that does not own this directory and "
        "neither file holds a secret (ADR 0164, ADR 0168)"
    )

    contract = secrets_contract.load_secret_contract(REPO_ROOT / "secrets.required.yaml")
    credential_options = {
        consumer["option"]
        for secret in contract["secrets"]
        for consumer in secret.get("consumers", [])
        if consumer.get("format") == "pgbackrest"
    }
    assert credential_options, (
        "the secrets contract declares no pgbackrest-format consumer, so this test is "
        "asserting nothing. It reads `option` off every consumer whose format is "
        "`pgbackrest`; if that format was renamed, rename it here too"
    )

    for name in readable:
        payload = (ALPHA / name).read_text(encoding="utf-8", errors="replace")
        for option in sorted(credential_options):
            assert option not in payload, (
                f"{name} is world-readable and names {option!r}, which is an option a "
                "per-consumer secret file sets under /etc/pgbackrest/conf.d. Either the "
                "value is in the render -- which is a leak -- or the option is being set "
                "twice and the last file wins (ADR 0154)"
            )


def test_the_published_snapshot_is_the_reviewed_one() -> None:
    """Copied verbatim, not generated.

    A render that produced its own document would be a second authority on what
    the API looks like, and the whole point of the reviewed snapshot is that a
    human approved these exact bytes.
    """
    served = (ALPHA / rendering.SNAPSHOT_FILENAME).read_bytes()
    assert served == rendering.CANONICAL_OPENAPI.read_bytes()


def test_the_install_imposes_no_mode_of_its_own() -> None:
    """What the code produces, parsed -- not a string that stands for it.

    This replaced a scan asserting that `_is_migration_artifact` *appeared* in
    `bin/deploy-project.py`. It was D464's shape (two strings standing in for a
    construct) and it failed for the best possible reason: the correct repair
    DELETED the function. `install_rendered` used to re-impose `0600` on
    everything it copied except the migration set, which made it a second
    authority over a decision `rendering.py` had already taken three times --
    and this one won, so the archiver's config was rendered `0444` and installed
    `0600` (D588, D589).

    The property is now the one D589 established, and it is a property of the
    function rather than of the file's text: `install_rendered` calls no `chmod`
    at all. `shutil.copytree` uses `copy2`, which preserves modes, so what the
    render decided is what arrives; the install decides ownership only.

    A rename cannot defeat this and a mention cannot satisfy it (ADR 0154).
    """
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    function = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "install_rendered"
        ),
        None,
    )
    assert function is not None, (
        "bin/deploy-project.py defines no `install_rendered`. If it was renamed, this "
        "test needs the new name -- an absent function is not a passing assertion"
    )

    # The premise: chmod is spelled somewhere in this module, so a walk that
    # finds none inside `install_rendered` is finding a real absence rather than
    # matching nothing. Without this the test would pass if `chmod` were called
    # something else everywhere (D509: a control that cannot fail for the reason
    # it is watching for is not a control).
    module_chmods = [
        node for node in ast.walk(tree) if isinstance(node, ast.Call) and _calls_chmod(node)
    ]
    assert module_chmods, (
        "no chmod call anywhere in bin/deploy-project.py, so this test cannot tell "
        "`install_rendered` imposes no mode from its own detector being broken"
    )

    offenders = [
        ast.unparse(node.func)
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and _calls_chmod(node)
    ]
    assert not offenders, (
        f"install_rendered calls {offenders}. The render decides a rendered file's mode "
        "and the install decides its owner (ADR 0154). Re-imposing one here makes this a "
        "second authority, which is how a 0444 config reached the archiver as 0600 (D589)"
    )

    # And the positive half: it does change ownership, or it is not doing its job.
    chowns = [
        node for node in ast.walk(function) if isinstance(node, ast.Call) and _calls_chown(node)
    ]
    assert chowns, "install_rendered changes no ownership; the destination is root-owned state"


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
