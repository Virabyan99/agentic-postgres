"""`bin/migrate.py record_ledger`, over every set this project applies.

**Nothing tested this function before Session 20**, which is how D1096 survived:
`record_ledger` built its template digests from the RELEASE lock alone and then
indexed that dictionary by every RENDERED entry's version. A project migration's
version is absent from the release lock, so the first deploy that rendered one
raised `KeyError` -- **after dbmate had already applied it**, from an unhandled
exception that never reached the `the ledger could not be recorded` path. A
cluster that has moved and a record that has not is the worst order a failure
can arrive in on this plane.

Found by reading the reader before changing the writer (D979). Written here
against a RECORDED `psql` rather than a live one: the question is which rows the
function composes, and a cluster would answer that question only after adding a
container, a role and a schema to it. What a cluster is needed for --  that the
statement applies at all -- is `test_migrations_apply_as_the_migration_user`'s,
and that module now applies both sets.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, migrations, rendering

pytestmark = [pytest.mark.contract, pytest.mark.p0]

FIXTURE = REPO_ROOT / ".generated" / "fixture-alpha-dev"
SECOND_FIXTURE = REPO_ROOT / ".generated" / "fixture-alpine-dev"


@pytest.fixture(scope="module")
def migrate_module() -> Any:
    specification = importlib.util.spec_from_file_location(
        "apg_migrate", REPO_ROOT / "bin" / "migrate.py"
    )
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def document_for(directory: Path) -> dict[str, Any]:
    if not (directory / "outputs.json").is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    return json.loads((directory / "outputs.json").read_text(encoding="utf-8"))


class Recorder:
    """A stand-in for `subprocess.run` that keeps what it was asked to run.

    Returns success, because what is under test is the statement the function
    composes; a stub that failed would exercise the error path and leave the
    rows unexamined, which is the half that was broken.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, command, **kwargs):
        self.calls.append({"command": command, "input": kwargs.get("input")})
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch, migrate_module: Any) -> Recorder:
    recorder = Recorder()
    monkeypatch.setattr(migrate_module.subprocess, "run", recorder)
    return recorder


def rows_of(statement: str) -> list[str]:
    """The VALUES tuples of the composed INSERT, as written."""
    body = statement.split(" VALUES ", 1)[1].rsplit(" ON CONFLICT", 1)[0]
    return [tuple_.strip() for tuple_ in body.split("), (")]


def test_the_ledger_records_a_row_for_every_rendered_migration_of_every_set(
    migrate_module: Any, recorded: Recorder
) -> None:
    """D1096. The project's migration reaches the ledger, and does not KeyError.

    The count is asserted against the RENDERED manifest rather than against a
    number, because the rendered manifest is what dbmate actually applied -- and
    the whole defect was a function that read one authority for what ran and a
    different one for what to record.
    """
    document = document_for(FIXTURE)
    rendered = json.loads(
        (FIXTURE / "migrations" / rendering.MIGRATION_MANIFEST_NAME).read_text(encoding="utf-8")
    )

    assert any(entry["set"] == "project" for entry in rendered["migrations"]), (
        "the fixture rendered no project migration, so this measures only the "
        "release's set and D1096 could not reproduce here"
    )

    exit_code = migrate_module.record_ledger(document, str(FIXTURE))
    assert exit_code == 0

    assert len(recorded.calls) == 1
    statement = recorded.calls[0]["input"]
    rows = rows_of(statement)
    assert len(rows) == len(rendered["migrations"])

    for entry in rendered["migrations"]:
        assert f"'{entry['version']}'" in statement, (
            f"{entry['version']} ({entry['set']}) was applied and is not in the ledger write"
        )
        assert f"'{entry['sha256']}'" in statement, (
            f"the rendered digest of {entry['name']} is not recorded"
        )


def test_each_rows_template_digest_comes_from_its_own_sets_lock(
    migrate_module: Any, recorded: Recorder
) -> None:
    """The half a count cannot catch.

    A repair that built the digest dictionary from every set but looked each
    version up in the wrong one would produce the right NUMBER of rows with a
    template digest describing somebody else's SQL -- and the ledger's whole
    purpose is to record which bytes ran.
    """
    document = document_for(FIXTURE)
    migrate_module.record_ledger(document, str(FIXTURE))
    statement = recorded.calls[0]["input"]

    for migration_set in migrations.sets_for(document):
        manifest = migration_set.load_manifest()
        follows = migration_set.load_lock().get("follows_release_version")
        built = migrations.build_lock(manifest, migration_set.root, follows_release_version=follows)
        assert built["migrations"], f"{migration_set.label} lock is empty"
        for entry in built["migrations"]:
            assert f"'{entry['template_sha256']}'" in statement, (
                f"{entry['version']} is recorded with a template digest that is not "
                f"the one its own set's lock holds ({migration_set.label})"
            )


def test_a_project_without_a_set_records_exactly_the_releases_migrations(
    migrate_module: Any, recorded: Recorder
) -> None:
    """The control. Without it, "every set" and "the release's set" would be one
    measurement on a tree where only one fixture exists."""
    document = document_for(SECOND_FIXTURE)
    rendered = json.loads(
        (SECOND_FIXTURE / "migrations" / rendering.MIGRATION_MANIFEST_NAME).read_text(
            encoding="utf-8"
        )
    )
    assert all(entry["set"] == "release" for entry in rendered["migrations"])

    assert migrate_module.record_ledger(document, str(SECOND_FIXTURE)) == 0
    rows = rows_of(recorded.calls[0]["input"])
    assert len(rows) == len(migrations.release_set().load_manifest()["migrations"])


def test_the_write_is_idempotent_and_names_the_platform_table(
    migrate_module: Any, recorded: Recorder
) -> None:
    """Two properties the composed statement carries, asserted rather than read.

    `ON CONFLICT DO NOTHING` is what makes the second `up` of a convergence
    check produce an identical ledger rather than fresh timestamps. And the
    write goes to `app_private.migration_ledger` as the SUPERUSER over the
    container socket, never through the migration plane -- a migration role that
    could write its own audit record could record bytes it did not execute,
    which is the property that makes the row worth reading at all.
    """
    document = document_for(FIXTURE)
    migrate_module.record_ledger(document, str(FIXTURE))
    call = recorded.calls[0]

    assert "ON CONFLICT (version) DO NOTHING" in call["input"]
    assert "app_private.migration_ledger" in call["input"]
    assert "-U" in call["command"]
    assert call["command"][call["command"].index("-U") + 1] == "postgres"
    assert document["database"]["container"] in call["command"]


def test_no_secret_or_placeholder_reaches_the_ledger_write(
    migrate_module: Any, recorded: Recorder
) -> None:
    """The rendered payload is committed to a lock and recorded here, so a
    template that carried a credential would put it in a table anything able to
    read the database can read. Digests and names only."""
    document = document_for(FIXTURE)
    migrate_module.record_ledger(document, str(FIXTURE))
    statement = recorded.calls[0]["input"]

    assert "{{" not in statement and "}}" not in statement

    # Stated as an allowlist rather than as a list of forbidden words, and the
    # difference is the whole point. A scan for "password" passes any template
    # that spells its credential differently -- it forbids the words somebody
    # thought of. This says what a row MAY contain: four literals, each one a
    # value already present in the rendered manifest or in a set's own lock.
    #
    # So a template that put anything else into this statement -- a fragment of
    # its own SQL, a value read from the document -- fails here whatever it is
    # called.
    permitted: set[str] = set()
    for migration_set in migrations.sets_for(document):
        manifest = migration_set.load_manifest()
        follows = migration_set.load_lock().get("follows_release_version")
        for entry in migrations.build_lock(
            manifest, migration_set.root, follows_release_version=follows
        )["migrations"]:
            permitted.add(entry["template_sha256"])
    for entry in json.loads(
        (FIXTURE / "migrations" / rendering.MIGRATION_MANIFEST_NAME).read_text(encoding="utf-8")
    )["migrations"]:
        permitted.update({entry["version"], entry["name"], entry["sha256"]})

    quoted = re.findall(r"'([^']*)'", statement)
    assert quoted, "the statement carries no literals at all"
    unexpected = sorted(set(quoted) - permitted)
    assert not unexpected, (
        f"the ledger write carries literals that are not a version, a name or a "
        f"digest: {unexpected}"
    )
