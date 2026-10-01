"""The host applies only a proposed set (`GOV-APPLY-001`, D1865, ADR 0243).

`bin/migrate.py`'s `up` asks `proposal.gate` BEFORE it writes anything: before
`reconcile_project_ledger` (which moves ledger rows, D1912) and before either
dbmate run. These proofs drive the product's own `run_every_set` -- and, where
the manifest or the relay matters, its own `main` -- over a temporary release
holding a COPY of the example set (so its lock, and therefore its digest, is the
real one), with the three things that reach a cluster recorded:

- `container_exec.run`, the gate's one READ-ONLY psql read of what is applied,
  answering with the versions a test says are applied;
- `reconcile_project_ledger`, the repair that writes;
- `run_dbmate`, which FAILS the test when it is reached for a refused set.

`status`'s proposal line is the same reading reported (ADR 0195: an applied set
it could not read is said, never folded); deploy step 6's relay is read out of
`bin/deploy-project.py`'s AST and evaluated over the stderr `main` printed.
The capability report (D1866) is `deploy-project.py`'s own `capability_report`.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, migrations, proposal, rendering

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

EXAMPLE = REPO_ROOT / "projects" / "example"
MANIFEST = REPO_ROOT / "project.example.yaml"
SECOND_MANIFEST = REPO_ROOT / "project.second.example.yaml"
DEPLOY = REPO_ROOT / "bin" / "deploy-project.py"
PROPOSER = "Ada Lovelace"
APPROVER = "Grace Hopper"


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Plane:
    """What reached a cluster, in order, and what the cluster says is applied."""

    def __init__(self) -> None:
        self.applied: tuple[str, ...] = ()
        self.read_fails = False
        self.reads: list[str] = []
        self.reached: list[str] = []

    def read(self, container: str, *argv: str, **options: Any) -> subprocess.CompletedProcess:
        self.reads.append(options["input"])
        if self.read_fails:
            return subprocess.CompletedProcess(argv, 2, "", "psql: connection refused\n")
        return subprocess.CompletedProcess(argv, 0, "".join(f"{v}\n" for v in self.applied), "")


@pytest.fixture
def release(tmp_path: Path) -> Path:
    """A release directory holding a copy of the example set, without proposals."""
    root = tmp_path / "release"
    shutil.copytree(EXAMPLE / "migrations", root / "projects" / "example" / "migrations")
    return root


@pytest.fixture
def project_set(release: Path) -> migrations.MigrationSet:
    return migrations.MigrationSet(
        label="project", root=release / "projects" / "example" / "migrations"
    )


@pytest.fixture
def versions(project_set: migrations.MigrationSet) -> tuple[str, ...]:
    return tuple(entry["version"] for entry in project_set.load_lock()["migrations"])


@pytest.fixture
def digest(project_set: migrations.MigrationSet) -> str:
    return migrations.set_digest(project_set)


@pytest.fixture
def rendered(tmp_path: Path, versions: tuple[str, ...]) -> Path:
    """A rendered directory whose manifest names the release's newest and the set."""
    directory = tmp_path / "rendered"
    (directory / "migrations").mkdir(parents=True)
    entries = [{"version": migrations.newest_release_version(), "set": "release"}]
    entries += [{"version": version, "set": "project"} for version in versions]
    (directory / "migrations" / rendering.MIGRATION_MANIFEST_NAME).write_text(
        json.dumps({"migrations": entries}), encoding="utf-8"
    )
    return directory


DOCUMENT = {
    "database": {
        "container": "apg-gate-postgres-1",
        "name": "gate",
        "roles": {"migration_user": "apg_gate_migration_user"},
    },
    "migrations": {"project_set": {"root": "projects/example"}},
}
RELEASE_ONLY = {key: value for key, value in DOCUMENT.items() if key != "migrations"}


@pytest.fixture
def plane() -> Plane:
    return Plane()


@pytest.fixture
def migrate(monkeypatch: pytest.MonkeyPatch, release: Path, plane: Plane) -> Any:
    module = _load(REPO_ROOT / "bin" / "migrate.py", "_apg_migrate_gate_under_test")
    monkeypatch.setattr(module, "REPO_ROOT", release)
    monkeypatch.setattr(module.container_exec, "run", plane.read)

    def reconcile(document: dict, rendered_dir: str) -> int:
        plane.reached.append("reconcile")
        return 0

    def dbmate(mode: str, document: dict, rendered_dir: str, service: str = "dbmate") -> int:
        plane.reached.append(f"dbmate {mode} {service}")
        return 0

    def ledger(document: dict, rendered_dir: str) -> int:
        plane.reached.append("ledger")
        return 0

    monkeypatch.setattr(module, "reconcile_project_ledger", reconcile)
    monkeypatch.setattr(module, "run_dbmate", dbmate)
    monkeypatch.setattr(module, "record_ledger", ledger)
    return module


def _proposal_record(digest: str, by: str = PROPOSER, capability: str = "0" * 64) -> dict:
    return {
        "schema_version": proposal.RECORD_SCHEMA_VERSION,
        "kind": proposal.PROPOSAL_KIND,
        "set_digest": digest,
        "capability_contract_sha256": capability,
        "declared_by": by,
        "note": proposal.NOTE,
    }


def _write_proposal(release: Path, file_digest: str, record: dict) -> bytes:
    path = proposal.proposal_path(release / "projects" / "example", file_digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = proposal.record_bytes(record)
    path.write_bytes(data)
    return data


def _write_approval(release: Path, digest: str, record: dict) -> None:
    path = proposal.approval_path(release / "projects" / "example", digest)
    path.write_bytes(proposal.record_bytes(record))


def _up(migrate: Any, rendered: Path, approvals_required: int, document: dict = DOCUMENT) -> int:
    return migrate.run_every_set(
        "up", document, str(rendered), approvals_required=approvals_required
    )


def _refused(migrate: Any, rendered: Path, plane: Plane, approvals_required: int) -> str:
    with pytest.raises(migrations.MigrationError) as raised:
        _up(migrate, rendered, approvals_required)
    assert plane.reached == [], f"a refused set reached {plane.reached}"
    return str(raised.value)


ALL_REACHED = [
    "reconcile",
    "dbmate up dbmate",
    "dbmate up dbmate-project",
    "ledger",
]


def test_a_pending_set_without_a_proposal_is_refused(
    migrate: Any, rendered: Path, plane: Plane, digest: str, versions: tuple[str, ...]
) -> None:
    """The newest version is not applied and there is no proposal: refused with
    the first sentence, before the repair and before EITHER dbmate run -- the
    release set is not applied ahead of a refusal."""
    plane.applied = versions[:-1]
    message = _refused(migrate, rendered, plane, approvals_required=0)
    assert message == proposal.GATE_NO_PROPOSAL.format(digest16=digest[:16])
    assert len(plane.reads) == 1
    read = plane.reads[0]
    for verb in ("INSERT", "DELETE", "UPDATE", "BEGIN", "CREATE", "DROP"):
        assert verb not in read.upper(), f"the gate's read carries {verb}"


def test_a_proposal_for_another_set_is_refused(
    migrate: Any, rendered: Path, plane: Plane, release: Path, digest: str
) -> None:
    """A proposal at this set's path naming a digest that shares this one's
    first sixteen characters is another set: compared WHOLE, never a prefix."""
    other = digest[:16] + ("0" if digest[16] != "0" else "1") + digest[17:]
    assert other != digest and other[:16] == digest[:16]
    _write_proposal(release, digest, _proposal_record(other))
    assert _refused(migrate, rendered, plane, 0) == proposal.GATE_OTHER_SET

    _write_proposal(release, digest, _proposal_record(digest.upper()))
    assert proposal.GATE_OTHER_SET in _refused(migrate, rendered, plane, 0)


def test_an_unapproved_proposal_is_refused_when_approvals_are_required(
    migrate: Any, rendered: Path, plane: Plane, release: Path, digest: str
) -> None:
    """Under approvals_required: 1 a proposal alone is refused; at 0 the same
    proposal admits the set and both sets apply, release first."""
    _write_proposal(release, digest, _proposal_record(digest))
    assert _refused(migrate, rendered, plane, 1) == proposal.GATE_NO_APPROVAL

    assert _up(migrate, rendered, 0) == 0
    assert plane.reached == ALL_REACHED


def test_an_approval_by_the_proposer_or_for_other_bytes_is_refused(
    migrate: Any, rendered: Path, plane: Plane, release: Path, digest: str
) -> None:
    """An approval under the proposer's folded name, or naming other bytes than
    the proposal file's, is refused with the fourth sentence; a second name over
    these bytes admits the set."""
    data = _write_proposal(release, digest, _proposal_record(digest))
    by_proposer = {
        "schema_version": proposal.RECORD_SCHEMA_VERSION,
        "kind": proposal.APPROVAL_KIND,
        "proposal_sha256": sha256(data).hexdigest(),
        "set_digest": digest,
        "declared_by": "ada   LOVELACE",
        "note": proposal.NOTE,
    }
    _write_approval(release, digest, by_proposer)
    assert _refused(migrate, rendered, plane, 1) == proposal.GATE_BAD_APPROVAL

    approval = proposal.build_approval(data, APPROVER, "2026-10-01T00:00:00Z")
    _write_approval(release, digest, approval)
    edited = _proposal_record(digest)
    edited["note"] = proposal.NOTE + " "
    _write_proposal(release, digest, edited)
    assert _refused(migrate, rendered, plane, 1) == proposal.GATE_BAD_APPROVAL

    _write_proposal(release, digest, _proposal_record(digest))
    assert _up(migrate, rendered, 1) == 0
    assert plane.reached == ALL_REACHED


def test_a_set_with_nothing_pending_needs_no_proposal(
    migrate: Any, rendered: Path, plane: Plane, versions: tuple[str, ...]
) -> None:
    """Every version applied (beta's `36 + 3` today, before 0004): no proposal
    exists and both sets run -- the gate refuses an act, never a state."""
    plane.applied = versions
    assert _up(migrate, rendered, 1) == 0
    assert plane.reached == ALL_REACHED
    assert len(plane.reads) == 1


def test_the_release_set_is_never_gated(migrate: Any, rendered: Path, plane: Plane) -> None:
    """A project with no set of its own: nothing is read, the release set
    applies with no proposal anywhere, under approvals_required 1."""
    assert _up(migrate, rendered, 1, RELEASE_ONLY) == 0
    assert plane.reads == []
    assert plane.reached == ["reconcile", "dbmate up dbmate", "ledger"]


def test_status_prints_the_proposal_line(
    migrate: Any,
    rendered: Path,
    plane: Plane,
    release: Path,
    digest: str,
    versions: tuple[str, ...],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """After the ledger: not needed, absent, approved by a name, and an applied
    set it could not read SAID -- a report, so `status` still exits 0."""
    head = f"migrate: proposal {digest[:16]}: "

    def status(approvals_required: int = 1) -> str:
        plane.reached.clear()
        assert (
            migrate.run_every_set(
                "status", DOCUMENT, str(rendered), approvals_required=approvals_required
            )
            == 0
        )
        assert plane.reached == ["dbmate status dbmate", "dbmate status dbmate-project"]
        lines = capsys.readouterr().out.splitlines()
        assert lines[-1].startswith(head), lines
        return lines[-1][len(head) :]

    plane.applied = versions
    assert status() == "not needed (nothing pending)"
    plane.applied = versions[:-1]
    assert status() == "absent (1 pending; up refuses)"
    data = _write_proposal(release, digest, _proposal_record(digest))
    assert status() == f"present; up refuses: {proposal.GATE_NO_APPROVAL}"
    assert status(0) == "present (approvals_required is 0)"
    _write_approval(release, digest, proposal.build_approval(data, APPROVER, "t"))
    assert status() == f"present, approved by {APPROVER}"
    plane.read_fails = True
    line = status()
    assert line.startswith("whether anything is pending could not be read ("), line
    assert "connection refused" in line

    plane.reached.clear()
    migrate.run_every_set("status", RELEASE_ONLY, str(rendered), approvals_required=1)
    assert capsys.readouterr().out.splitlines()[-1] == (
        "migrate: proposal: not applicable (this project applies no set of its own)"
    )


def _main(
    migrate: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    rendered: Path,
    manifest: Path,
) -> int:
    """`bin/migrate.py --mode up` itself, the render's own checks stubbed: what
    is under proof is the dispatch from the manifest to the gate."""
    monkeypatch.setattr(migrate, "render_set", lambda document: [])
    monkeypatch.setattr(migrate, "assert_installed_render_is_current", lambda *a: None)
    monkeypatch.setattr(migrate, "assert_rendered_files_match", lambda *a: None)
    outputs = tmp_path / "outputs.json"
    outputs.write_text(json.dumps(DOCUMENT), encoding="utf-8")
    return migrate.main(
        [
            "--mode",
            "up",
            "--outputs",
            str(outputs),
            "--rendered-dir",
            str(rendered),
            "--project",
            str(manifest),
        ]
    )


def _installed_manifest(tmp_path: Path, approvals_required: int) -> Path:
    document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    document["migrations"]["approvals_required"] = approvals_required
    path = tmp_path / f"installed-{approvals_required}.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def test_approvals_required_is_read_from_the_installed_manifest(
    migrate: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    rendered: Path,
    plane: Plane,
    release: Path,
    digest: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The manifest `bin/migrate.sh` was handed decides, never the tree's
    example (which says 1): installed at 0 a lone proposal admits the set,
    installed at 1 the same set is refused."""
    assert yaml.safe_load(MANIFEST.read_text())["migrations"]["approvals_required"] == 1
    _write_proposal(release, digest, _proposal_record(digest))

    assert _main(migrate, monkeypatch, tmp_path, rendered, _installed_manifest(tmp_path, 0)) == 0
    assert plane.reached == ALL_REACHED

    plane.reached.clear()
    assert _main(migrate, monkeypatch, tmp_path, rendered, _installed_manifest(tmp_path, 1)) == 5
    assert plane.reached == []
    assert capsys.readouterr().err.strip().endswith(proposal.GATE_NO_APPROVAL)


def _relay_message(deploy_source: str) -> ast.expr:
    """The message expression of step 6's `fail(...)` under
    `if migrated.returncode != 0`, out of the deploy's own source."""
    for node in ast.walk(ast.parse(deploy_source)):
        if (
            isinstance(node, ast.If)
            and ast.unparse(node.test) == "migrated.returncode != 0"
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Call)
            and ast.unparse(node.body[0].value.func) == "fail"
        ):
            return node.body[0].value.args[1]
    raise AssertionError("step 6's migrate relay was not found in bin/deploy-project.py")


def test_deploy_relays_the_gates_sentence(
    migrate: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    rendered: Path,
    plane: Plane,
    digest: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`migrate.py up` refuses at exit 5 with the sentence on stderr, and step
    6's own `fail` -- its message expression evaluated over that stderr --
    exits 5 with the sentence intact."""
    assert _main(migrate, monkeypatch, tmp_path, rendered, _installed_manifest(tmp_path, 1)) == 5
    stderr = capsys.readouterr().err
    sentence = proposal.GATE_NO_PROPOSAL.format(digest16=digest[:16])
    assert sentence in stderr

    deploy = _load(DEPLOY, "_apg_deploy_relay_under_test")
    expression = _relay_message(DEPLOY.read_text(encoding="utf-8"))
    migrated = subprocess.CompletedProcess([], 5, "", stderr)
    message = eval(  # noqa: S307 - the deploy's own expression, over a fixed local
        compile(ast.Expression(expression), str(DEPLOY), "eval"), {}, {"migrated": migrated}
    )
    with pytest.raises(SystemExit) as raised:
        deploy.fail(deploy.EXIT_VALIDATION, message)
    assert raised.value.code == 5
    relayed = capsys.readouterr().err
    assert relayed.startswith("deploy: migrations did not apply:")
    assert sentence in relayed


def test_the_capability_report_names_a_proposal_or_says_none(tmp_path: Path) -> None:
    """D1866: one line. The release's committed proposal names the example's
    capability contract; a release copy with no proposal says none; an
    unreadable proposal is SAID; a manifest with no capabilities says so."""
    deploy = _load(DEPLOY, "_apg_deploy_report_under_test")
    contract = sha256(
        (EXAMPLE / "contracts" / "mcp-capabilities.canonical.json").read_bytes()
    ).hexdigest()
    head = f"capability contract {contract[:16]}: "

    named = deploy.capability_report(REPO_ROOT, MANIFEST)
    assert named.startswith(head + "named by proposal "), named

    copy = tmp_path / "release"
    shutil.copytree(EXAMPLE, copy / "projects" / "example")
    shutil.rmtree(copy / "projects" / "example" / proposal.PROPOSALS_SUBDIR, ignore_errors=True)
    assert deploy.capability_report(copy, MANIFEST) == head + "named by no proposal of this project"

    broken = copy / "projects" / "example" / proposal.PROPOSALS_SUBDIR / ("a" * 64 + ".json")
    broken.parent.mkdir()
    broken.write_text("not json", encoding="utf-8")
    unread = deploy.capability_report(copy, MANIFEST)
    assert unread.startswith(head + "the project's proposals could not be read ("), unread

    assert deploy.capability_report(REPO_ROOT, SECOND_MANIFEST) == (
        "no capability contract (the manifest declares none)"
    )
