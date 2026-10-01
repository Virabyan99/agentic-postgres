"""A proposed change to a project's set, and who records its review (ADR 0243).

`GOV-LINT-001` (the destructive reading), `GOV-PROPOSE-001` (`bin/migrate.sh
propose`) and `GOV-APPROVE-001`'s record half (`bin/migrate.sh approve`).

**The commands are the product's** (D1114): `bin/migrate.py`'s own `main`, in
process, with two of its module names pointed elsewhere -- `PROJECTS_ROOT`, so
the records land under `tmp_path` and never in the tree's
`projects/example/proposals/`, and `DEV_SH`, so `apg dev` is a recording stub.

**The stub's text is rig 35b's MEASURED output** (Session 35 Run 1, D1895,
`~/s35r1/rig35/rig35.txt`): `bin/dev.sh status` with no environment printed
*dev: no development environment; `apg dev up` creates one* and exited 4;
while one was up it printed the `is running on` line and exited 0; `up` exited
0 printing `dev: 39 migrations applied as apg_fixture_alpha_dev_migration_user`
among its lines; `down` exited 0. So the fixture does not share the code's
belief about what `dev.sh` says (§7 question 6) -- it carries the measurement,
and `test_propose_applies_the_set_from_empty_through_dev_up` runs the REAL one.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import (
    REPO_ROOT,
    approval_gate,
    capability_manifest,
    config,
    migrations,
    proposal,
    template_version,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

EXAMPLE = REPO_ROOT / "projects" / "example"
MANIFEST = REPO_ROOT / "project.example.yaml"
FIXTURE = REPO_ROOT / ".generated" / "fixture-alpha-dev"
SECOND_FIXTURE = REPO_ROOT / ".generated" / "fixture-alpine-dev"

#: Rig 35b's lines, verbatim (the subject and port are the rig's own).
RIG_STATUS_ABSENT = "dev: no development environment; `apg dev up` creates one"
RIG_STATUS_UP = (
    "dev: apg-dev-fixture-alpha-dev is running on 127.0.0.1:32871, database "
    "fixture_alpha_dev, 39 migrations, subject 52e833b6-9d4d-40fb-a17a-2626ed015243"
)
RIG_UP = [
    "dev: apg-dev-fixture-alpha-dev started on docker.io/pgvector/pgvector:pg18",
    "dev: bootstrap applied, 2 roles activated",
    "dev: 39 migrations applied as apg_fixture_alpha_dev_migration_user",
    "",
    "  container   apg-dev-fixture-alpha-dev",
    "  database    fixture_alpha_dev  on 127.0.0.1:32871",
    "  migrations  39, ledger recorded",
    "  workflows   7 definition(s) installed",
    "  connectors  not enabled (the manifest's connectors.enabled is false)",
    "  subject     52e833b6-9d4d-40fb-a17a-2626ed015243  (7 scopes)",
]
RIG_DOWN = (
    "dev: removed container apg-dev-fixture-alpha-dev and its volume and "
    "/home/gmpar/projects/agentic-postgres/.generated/.dev/fixture-alpha-dev"
)


def _migrate_module():
    name = "_migrate_under_test"
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "bin" / "migrate.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _stub(directory: Path, *, up: bool = False) -> Path:
    """A `bin/dev.sh` that records each call and answers with rig 35b's lines."""
    directory.mkdir(parents=True, exist_ok=True)
    if up:
        (directory / "up").touch()
    lines = "\n".join(f"  printf '%s\\n' {json.dumps(line)}" for line in RIG_UP)
    script = directory / "dev.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        'here="$(dirname "$0")"\n'
        'printf \'%s\\n\' "$*" >> "$here/calls.log"\n'
        'case "$1" in\n'
        "  status)\n"
        f"    if [ -f \"$here/up\" ]; then printf '%s\\n' {json.dumps(RIG_STATUS_UP)}; exit 0; fi\n"
        f"    printf '%s\\n' {json.dumps(RIG_STATUS_ABSENT)}; exit 4 ;;\n"
        "  up)\n"
        f"{lines}\n"
        "    exit 0 ;;\n"
        f"  down) printf '%s\\n' {json.dumps(RIG_DOWN)}; exit 0 ;;\n"
        "esac\n"
        "exit 2\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def _calls(stub: Path) -> list[str]:
    log = stub.parent / "calls.log"
    if not log.is_file():
        return []
    return [line.split()[0] for line in log.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def migrate(monkeypatch, tmp_path: Path):
    """`bin/migrate.py`, records under `tmp_path/records`, `apg dev` stubbed."""
    module = _migrate_module()
    monkeypatch.setattr(module, "PROJECTS_ROOT", tmp_path / "records")
    monkeypatch.setattr(module, "DEV_SH", _stub(tmp_path / "stub"))
    return module


def _propose(module, by: str = "Ada Lovelace") -> int:
    return module.main(["--mode", "propose", "--project", str(MANIFEST), "--by", by])


def _approve(module, digest: str, by: str) -> int:
    return module.main(
        ["--mode", "approve", "--project", str(MANIFEST), "--by", by, "--proposal", digest]
    )


def _example_digest() -> str:
    return migrations.set_digest(
        migrations.MigrationSet(label="project", root=EXAMPLE / "migrations")
    )


def _records(module) -> Path:
    return module.PROJECTS_ROOT / "projects" / "example" / proposal.PROPOSALS_SUBDIR


# ---------------------------------------------------------------------------
# GOV-LINT-001 -- the destructive reading
# ---------------------------------------------------------------------------


def _set_with(tmp_path: Path, up: str, *, down: str = "") -> migrations.MigrationSet:
    """The example set copied, with ONE more migration whose up section is `up`."""
    root = tmp_path / "example"
    shutil.copytree(EXAMPLE, root)
    manifest_path = root / "migrations" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = copy.deepcopy(manifest["migrations"][-1])
    entry.update(version="20261001120099", name="scratch", template="templates/0099-scratch.sql")
    manifest["migrations"].append(entry)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (root / "migrations" / "templates" / "0099-scratch.sql").write_text(
        "-- migrate:up\nSET LOCAL ROLE {{object_owner}};\n"
        f"{up}\nRESET ROLE;\n-- migrate:down\n{down}\n"
        "DO $$ BEGIN RAISE EXCEPTION 'AP900: fix-forward only'; END $$;\n",
        encoding="utf-8",
    )
    return migrations.MigrationSet(label="project", root=root / "migrations")


def _scratch_findings(tmp_path: Path, up: str, **kwargs) -> list[tuple[str, str]]:
    found = migrations.destructive_findings(_set_with(tmp_path, up, **kwargs))
    assert all(finding.version == "20261001120099" for finding in found), found
    return [(finding.kind, finding.object) for finding in found]


#: One plain spelling per shape D1862 names.
PLAIN = [
    ("DROP TABLE app.notes_archive;", "drop_table", "app.notes_archive"),
    ("DROP VIEW api.note_digest;", "drop_view", "api.note_digest"),
    ("DROP MATERIALIZED VIEW app.note_stats;", "drop_materialized_view", "app.note_stats"),
    ("DROP FUNCTION api.set_note_digest(uuid);", "drop_function", "api.set_note_digest"),
    ("DROP PROCEDURE app.rebuild();", "drop_procedure", "app.rebuild"),
    ("DROP INDEX app.note_embeddings_owner_idx;", "drop_index", "app.note_embeddings_owner_idx"),
    ("DROP TYPE app.note_kind;", "drop_type", "app.note_kind"),
    ("DROP SEQUENCE app.note_seq;", "drop_sequence", "app.note_seq"),
    ("DROP TRIGGER note_touch ON app.notes_extra;", "drop_trigger", "note_touch"),
    ("DROP POLICY owner_only ON app.note_embeddings;", "drop_policy", "owner_only"),
    ("ALTER TABLE app.note_embeddings DROP COLUMN updated_at;", "drop_column",
     "app.note_embeddings.updated_at"),
    ("ALTER TABLE app.note_embeddings DROP CONSTRAINT note_fk;", "drop_constraint",
     "app.note_embeddings.note_fk"),
    ("ALTER TABLE app.note_embeddings ALTER COLUMN embedding TYPE extensions.vector(3);",
     "alter_column_type", "app.note_embeddings.embedding"),
    ("ALTER TABLE app.note_embeddings RENAME TO note_vectors;", "rename", "app.note_embeddings"),
    ("TRUNCATE app.note_embeddings;", "truncate", "app.note_embeddings"),
    ("DELETE FROM app.note_embeddings;", "delete_without_where", "app.note_embeddings"),
]  # fmt: skip

#: A second spelling per shape: IF EXISTS, ONLY, quoted, spaced, lowercase,
#: CASCADE, SET DATA TYPE, an unqualified name.
SPELLED = [
    ('DROP TABLE IF EXISTS "app"."Notes_Archive" CASCADE;', "drop_table", "app.notes_archive"),
    ("drop view if exists note_digest;", "drop_view", "note_digest"),
    ('DROP MATERIALIZED VIEW IF EXISTS "app" . "note_stats";', "drop_materialized_view",
     "app.note_stats"),
    ("DROP FUNCTION IF EXISTS api.set_note_digest;", "drop_function", "api.set_note_digest"),
    ("drop procedure if exists rebuild(integer);", "drop_procedure", "rebuild"),
    ("DROP INDEX CONCURRENTLY IF EXISTS note_embeddings_owner_idx;", "drop_index",
     "note_embeddings_owner_idx"),
    ('DROP TYPE IF EXISTS "note_kind" CASCADE;', "drop_type", "note_kind"),
    ("drop   sequence   if exists   app.note_seq;", "drop_sequence", "app.note_seq"),
    ('DROP TRIGGER IF EXISTS "note_touch" ON notes_extra;', "drop_trigger", "note_touch"),
    ('DROP POLICY IF EXISTS "owner_only" ON app.note_embeddings;', "drop_policy", "owner_only"),
    ('ALTER TABLE IF EXISTS ONLY "app"."note_embeddings" DROP updated_at;', "drop_column",
     "app.note_embeddings.updated_at"),
    ('alter table note_embeddings drop constraint if exists "note_fk" cascade;',
     "drop_constraint", "note_embeddings.note_fk"),
    ("ALTER TABLE app.note_embeddings ALTER embedding SET DATA TYPE text USING embedding::text;",
     "alter_column_type", "app.note_embeddings.embedding"),
    ("ALTER TABLE app.note_embeddings RENAME COLUMN embedding TO vector;", "rename",
     "app.note_embeddings"),
    ('TRUNCATE TABLE ONLY "app"."note_embeddings" CASCADE;', "truncate", "app.note_embeddings"),
    ('delete from only "app"."note_embeddings" ;', "delete_without_where",
     "app.note_embeddings"),
]  # fmt: skip


def test_the_shapes_are_every_kind_in_both_tables() -> None:
    """Both tables cover all sixteen kinds, so neither proof is short a shape."""
    assert [kind for _, kind, _ in PLAIN] == list(migrations.DESTRUCTIVE_KINDS)
    assert [kind for _, kind, _ in SPELLED] == list(migrations.DESTRUCTIVE_KINDS)


@pytest.mark.parametrize(("statement", "kind", "name"), PLAIN, ids=[kind for _, kind, _ in PLAIN])
def test_each_destructive_shape_is_named_with_its_object(
    tmp_path: Path, statement: str, kind: str, name: str
) -> None:
    """D1862: every shape is a finding naming its migration, its kind and its object."""
    assert _scratch_findings(tmp_path, statement) == [(kind, name)]


def test_every_accepted_spelling_is_read(tmp_path: Path) -> None:
    """D1818's lesson: every spelling PostgreSQL accepts for a name is read --
    IF EXISTS, ONLY, quoted, spaced, lowercase, CASCADE, `SET DATA TYPE`."""
    misses = []
    for statement, kind, name in SPELLED:
        found = _scratch_findings(tmp_path / kind, statement)
        if found != [(kind, name)]:
            misses.append(f"{statement!r} -> {found}")
    assert not misses, "\n".join(misses)

    several = _scratch_findings(
        tmp_path / "several",
        "ALTER TABLE app.note_embeddings DROP COLUMN a, DROP COLUMN IF EXISTS b,"
        " ALTER COLUMN c TYPE text;",
    )
    assert several == [
        ("drop_column", "app.note_embeddings.a"),
        ("drop_column", "app.note_embeddings.b"),
        ("alter_column_type", "app.note_embeddings.c"),
    ], several


#: The same words where they drop nothing.
NOT_FINDINGS = [
    ("line_comment", "-- DROP TABLE app.notes_archive;", ""),
    ("block_comment", "/* DROP TABLE app.notes_archive; */", ""),
    ("string_literal",
     "COMMENT ON TABLE app.note_embeddings IS 'DROP TABLE app.notes; TRUNCATE x';", ""),
    ("down_section", "SELECT 1;", "DROP TABLE app.note_embeddings;"),
    ("a_column_called_drop_date",
     "CREATE TABLE app.note_dates (id integer PRIMARY KEY, drop_date date);", ""),
    ("enable_row_security", "ALTER TABLE app.note_embeddings ENABLE ROW LEVEL SECURITY;", ""),
    ("force_row_security", "ALTER TABLE app.note_embeddings FORCE ROW LEVEL SECURITY;", ""),
    ("delete_with_where", "DELETE FROM app.note_embeddings WHERE owner_id IS NULL;", ""),
    ("drop_not_null", "ALTER TABLE app.note_embeddings ALTER COLUMN embedding DROP NOT NULL;", ""),
    ("add_a_column", "ALTER TABLE app.note_embeddings ADD COLUMN dropped boolean;", ""),
]  # fmt: skip


def test_a_commented_statement_or_a_down_section_is_not_a_finding(tmp_path: Path) -> None:
    """Ten statements carrying the words and dropping nothing; the control is
    the same set with one real DROP added, found."""
    wrong = {}
    for name, up, down in NOT_FINDINGS:
        found = _scratch_findings(tmp_path / name, up, down=down)
        if found:
            wrong[name] = found
    assert not wrong, wrong
    assert _scratch_findings(tmp_path / "control", "DROP TABLE app.notes_archive;") == [
        ("drop_table", "app.notes_archive")
    ]


def test_a_finding_never_refuses_the_lint(tmp_path: Path) -> None:
    """Named, never refused (D1862): a set that drops its own table passes the
    lint, and the reading names the drop."""
    candidate = _set_with(tmp_path, "DROP TABLE IF EXISTS app.note_scratch;")
    migrations.lint_project_set(candidate)
    assert migrations.destructive_findings(candidate) == (
        migrations.DestructiveFinding("20261001120099", "drop_table", "app.note_scratch"),
    )


def test_the_example_set_has_no_destructive_statement() -> None:
    """The control: four migrations, `ENABLE`/`FORCE ROW LEVEL SECURITY`
    among them, and nothing a reviewer must weigh."""
    example = migrations.MigrationSet(label="project", root=EXAMPLE / "migrations")
    assert len(example.load_manifest()["migrations"]) == 4
    assert migrations.destructive_findings(example) == ()


# ---------------------------------------------------------------------------
# GOV-PROPOSE-001 -- the proposal
# ---------------------------------------------------------------------------


def test_the_digest_is_the_renders_lock_sha256(tmp_path: Path) -> None:
    """D1857: one identity for a set -- the sha256 of its lock's BYTES, which
    the render records and a proposal is named by.

    Read on both example renders: alpha's set digest is the function's; alpine
    declares no set and records none. And the BYTES, not the content: the same
    lock re-indented is a different file and a different digest.
    """
    if not (FIXTURE / "outputs.json").is_file() or not (SECOND_FIXTURE / "outputs.json").is_file():
        pytest.skip("no rendered fixtures; run ./deploy.sh --render-only for both")
    example = migrations.MigrationSet(label="project", root=EXAMPLE / "migrations")
    digest = migrations.set_digest(example)
    assert digest == sha256(example.lock_path.read_bytes()).hexdigest()

    alpha = json.loads((FIXTURE / "outputs.json").read_text(encoding="utf-8"))
    alpine = json.loads((SECOND_FIXTURE / "outputs.json").read_text(encoding="utf-8"))
    assert alpha["migrations"]["project_set"]["lock_sha256"] == digest
    assert alpine["migrations"]["project_set"] is None
    rendered = json.loads(
        (FIXTURE / "migrations" / "rendered-manifest.json").read_text(encoding="utf-8")
    )
    assert rendered["project_set"]["lock_sha256"] == digest

    copied = tmp_path / "set"
    shutil.copytree(EXAMPLE / "migrations", copied)
    lock = json.loads((copied / "released.lock.json").read_text(encoding="utf-8"))
    (copied / "released.lock.json").write_text(json.dumps(lock, indent=4) + "\n", encoding="utf-8")
    assert migrations.set_digest(migrations.MigrationSet(label="project", root=copied)) != digest


def test_propose_records_every_reading_and_its_limits(migrate) -> None:
    """Every member of the record, each read from the source it names."""
    assert _propose(migrate) == 0
    digest = _example_digest()
    path = _records(migrate) / f"{digest}.json"
    data = path.read_bytes()
    assert data.endswith(b"\n") and data == proposal.record_bytes(json.loads(data))
    record = json.loads(data)

    assert set(record) == {
        "schema_version", "kind", "project_slug", "set_digest", "set", "release", "lint",
        "destructive", "dev_apply", "surface", "approval_gate", "harness",
        "capability_contract_sha256", "declared_by", "declared_at", "note",
    }  # fmt: skip
    assert record["kind"] == "migration_set_proposal" and record["schema_version"] == 1
    assert record["project_slug"] == "fixture-alpha"
    assert record["set_digest"] == digest
    example = migrations.MigrationSet(label="project", root=EXAMPLE / "migrations")
    assert record["set"] == {
        "root": "projects/example",
        "versions": [
            {"version": entry["version"], "name": entry["name"]}
            for entry in example.load_manifest()["migrations"]
        ],
        "follows_release_version": "20260912120031",
        "follows_release_version_source": "declared",
    }
    assert record["release"] == {
        "template_version": template_version(),
        "release_lock_sha256": sha256(migrations.LOCK_PATH.read_bytes()).hexdigest(),
    }
    assert record["lint"] == "passed"
    assert record["destructive"] == []
    assert record["dev_apply"] == {
        "exit": 0,
        "migrations_applied": 39,
        "seconds": record["dev_apply"]["seconds"],
        "from_empty": True,
        "applied_by": "psql as migration_user",
        "existing_rows": "none",
    }
    assert record["surface"] == {
        "functions": [{"name": "set_note_embedding", "reviewed": True}],
        "views": [{"name": "note_embeddings", "reviewed": True}],
    }
    assert record["approval_gate"] == []
    assert set(record["harness"]) == {"contract_sha256", "derived", "written", "capabilities",
                                      "note"}  # fmt: skip
    assert record["harness"]["derived"] > 0 and record["harness"]["written"] > 0
    contract_path = capability_manifest.project_contract_path(EXAMPLE)
    assert record["capability_contract_sha256"] == sha256(contract_path.read_bytes()).hexdigest()
    assert record["declared_by"] == "Ada Lovelace"
    assert record["note"] == proposal.NOTE

    assert _calls(migrate.DEV_SH) == ["status", "up", "down"]


def test_propose_refuses_while_a_dev_environment_is_up(migrate, tmp_path: Path) -> None:
    """D1861: an environment that exists is somebody's, and propose never downs
    it -- it refuses, exit 3, before `up`, and the stub records no `down`."""
    migrate.DEV_SH = _stub(tmp_path / "up-stub", up=True)
    assert _propose(migrate) == 3
    assert _calls(migrate.DEV_SH) == ["status"], "propose touched an environment that was up"
    assert not _records(migrate).exists() or not any(_records(migrate).iterdir())


def test_propose_refuses_an_unguarded_gated_function(migrate, monkeypatch, capsys) -> None:
    """ADR 0242: a gated RPC that does not call the guard first is refused,
    exit 5, before the dev environment is touched and with nothing written."""
    real = migrate.sql_surface.final_function_bodies

    def unguarded(manifest, root):
        bodies = real(manifest, root)
        return {name: body.replace("PERFORM app.require_approval", "-- ") for name, body in
                bodies.items()}  # fmt: skip

    monkeypatch.setattr(migrate.sql_surface, "final_function_bodies", unguarded)
    assert _propose(migrate) == 5
    printed = capsys.readouterr().err
    assert "approval gate: set_note_embedding does not call app.require_approval" in printed
    assert _calls(migrate.DEV_SH) == []
    assert not _records(migrate).exists()


def test_propose_refuses_an_existing_proposal(migrate) -> None:
    """A record is written once: the second propose of one set exits 5 and
    leaves the first file's bytes."""
    assert _propose(migrate) == 0
    path = _records(migrate) / f"{_example_digest()}.json"
    first = path.read_bytes()
    assert _propose(migrate, "Grace Hopper") == 5
    assert path.read_bytes() == first


def test_a_proposal_is_deterministic_but_for_its_times(migrate, monkeypatch, tmp_path) -> None:
    """Two proposals of one set, by one name, differ only in `declared_at` and
    `dev_apply.seconds`."""
    assert _propose(migrate) == 0
    first = json.loads((_records(migrate) / f"{_example_digest()}.json").read_text("utf-8"))
    monkeypatch.setattr(migrate, "PROJECTS_ROOT", tmp_path / "second")
    monkeypatch.setattr(migrate, "DEV_SH", _stub(tmp_path / "second-stub"))
    assert _propose(migrate) == 0
    second = json.loads((_records(migrate) / f"{_example_digest()}.json").read_text("utf-8"))
    for record in (first, second):
        record.pop("declared_at")
        record["dev_apply"].pop("seconds")
    assert first == second


def test_propose_applies_the_set_from_empty_through_dev_up(monkeypatch, tmp_path: Path) -> None:
    """The REAL `bin/dev.sh` (Docker): the release's migrations and the set's
    applied from empty, read from `up`'s own line, then removed.

    In this module rather than `test_dev_environment_cluster.py` (D1907): that
    module holds an environment up for its whole length, and propose refuses
    while one exists -- under a shuffled order this proof would meet it.
    """
    if not (FIXTURE / "outputs.json").is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    probe = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        capture_output=True, text=True, check=False, timeout=30,
    )  # fmt: skip
    if probe.returncode != 0:
        pytest.skip("docker is not available")
    module = _migrate_module()
    status = module._dev("status", str(MANIFEST))
    if status.returncode != 4:
        pytest.skip(f"an apg dev environment exists here: {status.stdout.strip()}")
    monkeypatch.setattr(module, "PROJECTS_ROOT", tmp_path / "records")

    assert _propose(module) == 0
    record = json.loads((_records(module) / f"{_example_digest()}.json").read_text("utf-8"))
    release = len(migrations.release_set().load_manifest()["migrations"])
    example = migrations.MigrationSet(label="project", root=EXAMPLE / "migrations")
    assert record["dev_apply"]["exit"] == 0
    assert record["dev_apply"]["migrations_applied"] == release + len(
        example.load_manifest()["migrations"]
    )
    assert module._dev("status", str(MANIFEST)).returncode == 4, "propose left an environment"


# ---------------------------------------------------------------------------
# GOV-APPROVE-001 -- the approval record
# ---------------------------------------------------------------------------


@pytest.fixture
def proposed(migrate) -> tuple[Any, str, Path]:
    assert _propose(migrate, "Ada") == 0
    digest = _example_digest()
    return migrate, digest, _records(migrate) / f"{digest}.json"


def test_approve_refuses_the_proposers_own_name(proposed) -> None:
    """A second NAME (D1864): `"ada"` is `"Ada"` folded, and is refused; the
    control, a different name, writes."""
    module, digest, _ = proposed
    assert _approve(module, digest, "ada") == 5
    assert not (_records(module) / f"{digest}.approval.json").exists()
    assert proposal.fold("Ada  Lovelace") == proposal.fold("ada lovelace")
    assert _approve(module, digest, "Grace") == 0


def test_approve_names_the_proposal_by_its_bytes(proposed) -> None:
    """The approval names the proposal FILE's sha256: one whitespace byte
    edited in the proposal -- the same JSON -- is a different file and a
    different approval."""
    module, digest, path = proposed
    assert _approve(module, digest, "Grace") == 0
    approval = json.loads((_records(module) / f"{digest}.approval.json").read_text("utf-8"))
    original = path.read_bytes()
    assert approval["proposal_sha256"] == sha256(original).hexdigest()
    assert approval["set_digest"] == digest

    edited = original.replace(b'\n  "kind"', b'\n   "kind"', 1)
    assert edited != original and json.loads(edited) == json.loads(original)
    rebuilt = proposal.build_approval(edited, "Grace", "2026-10-01T00:00:00Z")
    assert rebuilt["proposal_sha256"] == sha256(edited).hexdigest()
    assert rebuilt["proposal_sha256"] != approval["proposal_sha256"]


def test_approve_refuses_a_missing_proposal_or_an_existing_approval(migrate) -> None:
    digest = _example_digest()
    assert _approve(migrate, digest, "Grace") == 5, "approved a proposal that does not exist"
    assert _propose(migrate) == 0
    assert _approve(migrate, digest, "Grace") == 0
    path = _records(migrate) / f"{digest}.approval.json"
    first = path.read_bytes()
    assert _approve(migrate, digest, "Linus") == 5
    assert path.read_bytes() == first
    assert _approve(migrate, "not-a-digest", "Grace") == 2


def test_the_records_say_their_names_are_declared(proposed) -> None:
    """D1864: `declared_by`, never `approved_by` or `author`, and the sentence
    in both records; a name outside the rule is invalid input."""
    module, digest, path = proposed
    assert _approve(module, digest, "Grace") == 0
    for record in (
        json.loads(path.read_text("utf-8")),
        json.loads((_records(module) / f"{digest}.approval.json").read_text("utf-8")),
    ):
        assert (
            record["note"] == "The names in this record are declared, not authenticated (ADR 0243)."
        )
        assert "declared_by" in record
        assert not {"approved_by", "author", "approver"} & set(record)
    for bad in ("", "1ada", "a", "x" * 65, "ada\n"):
        assert _propose(module, bad) == 2, bad


def test_the_approval_gate_sentences_are_the_four_the_host_will_raise() -> None:
    """D1865's four sentences, fixed now so Run 4's gate raises these exactly."""
    assert proposal.GATE_NO_PROPOSAL.format(digest16="0123456789abcdef") == (
        "no proposal for this set 0123456789abcdef"
    )
    assert proposal.GATE_OTHER_SET == "the proposal names another set"
    assert proposal.GATE_NO_APPROVAL == "approvals_required is 1 and the proposal has no approval"
    assert proposal.GATE_BAD_APPROVAL == (
        "the approval does not name this proposal, or names its proposer"
    )
    assert approval_gate.GUARD == "app.require_approval"
    assert config.approvals_required(config.load_project_manifest(MANIFEST)) == 1


def test_the_example_sets_committed_proposal_names_its_lock() -> None:
    """The proposal `bin/migrate.sh propose` wrote and Run 4 committed names
    the example set as it is: its `set_digest` is the lock's, its versions the
    lock's, nothing destructive, no unguarded gated tool, applied from empty.
    A later change to the set moves the digest, and this proof -- like the
    host gate -- refuses until the set is proposed again. That is the point."""
    project_set = migrations.MigrationSet(label="project", root=EXAMPLE / "migrations")
    digest = migrations.set_digest(project_set)
    path = proposal.proposal_path(EXAMPLE, digest)
    assert path.is_file(), f"no committed proposal for the example set {digest[:16]}"
    record = proposal.read_proposal(path.read_bytes())
    assert record["set_digest"] == digest
    assert record["set"]["versions"] == [
        {"version": entry["version"], "name": entry["name"]}
        for entry in project_set.load_lock()["migrations"]
    ]
    assert record["destructive"] == []
    assert record["approval_gate"] == []
    assert record["dev_apply"]["exit"] == 0
    assert (
        record["capability_contract_sha256"]
        == sha256(capability_manifest.project_contract_path(EXAMPLE).read_bytes()).hexdigest()
    )
    assert path.read_bytes() == proposal.record_bytes(record)
