"""`OPS-001` — the deployed diagnosis, and the honesty rules it runs under.

Behavioural, on `agentic_postgres.diagnosis`, for ADR 0157's reason: `bin/doctor.py`
needs root and a deployment, so the verdicts are put where they can be exercised
and mutated.

Two source-level tests sit at the bottom and are labelled as such. They guard
properties that are *about the command's shape* rather than its output — that the
document is read for identities only, and that the bare `python` cannot be
reached from the root-only path — and neither has a behavioural form that runs
off a host.
"""

from __future__ import annotations

import ast
import json

import pytest

from agentic_postgres import REPO_ROOT, backup_report, diagnosis

pytestmark = [pytest.mark.contract, pytest.mark.p0]


# ---------------------------------------------------------------------------
# UNKNOWN is not a pass, and it is not a failure either
# ---------------------------------------------------------------------------


def test_an_unknown_check_does_not_exit_zero() -> None:
    """The whole reason the verdict exists.

    A check that could not run is not a healthy check. A monitoring caller that
    read exit 0 from a doctor that measured nothing would be holding D600's
    value: one that looks measured and is not.
    """
    checks = (diagnosis.archiver(failing=None, last_archived_time=None),)
    assert diagnosis.worst(checks) == diagnosis.UNKNOWN
    assert diagnosis.exit_code(checks) == 6


def test_a_warning_exits_zero() -> None:
    """ADR 0157 predicted this tier would be needed and left it undecided;
    ADR 0158 decides it. A warning is advisory by construction."""
    checks = (diagnosis.tls(days_remaining=10, not_after="soon"),)
    assert diagnosis.worst(checks) == diagnosis.WARN
    assert diagnosis.exit_code(checks) == 0


def test_unknown_outranks_warn_when_both_are_present() -> None:
    """Nobody knows which of the other three an unknown would have been, so it
    cannot be ranked below a verdict that was actually measured."""
    checks = (
        diagnosis.tls(days_remaining=10, not_after="soon"),
        diagnosis.archiver(failing=None, last_archived_time=None),
    )
    assert diagnosis.worst(checks) == diagnosis.UNKNOWN


def test_a_problem_outranks_everything() -> None:
    checks = (
        diagnosis.tls(days_remaining=90, not_after="later"),
        diagnosis.archiver(failing=None, last_archived_time=None),
        diagnosis.archiver(failing=True, last_archived_time=None),
    )
    assert diagnosis.worst(checks) == diagnosis.PROBLEM
    assert diagnosis.exit_code(checks) == 6


def test_an_empty_run_is_not_silently_healthy() -> None:
    """A doctor that ran no checks reports ok — which is only safe because
    `diagnose()` always appends a fixed set. Asserted so that a future caller
    filtering checks to nothing sees this test rather than a green run."""
    assert diagnosis.worst(()) == diagnosis.OK


# ---------------------------------------------------------------------------
# Each family
# ---------------------------------------------------------------------------


def test_a_running_but_unhealthy_container_is_a_problem() -> None:
    """Docker puts `(unhealthy)` in Status, not State, so a container can be
    running and unhealthy at once. Counting only `running` would call that well."""
    check = diagnosis.containers(expected=3, running=("a", "b", "c"), unhealthy=("b",))
    assert check.verdict == diagnosis.PROBLEM
    assert "b" in check.detail


def test_an_undeterminable_container_set_is_unknown_not_a_problem() -> None:
    """An empty `docker ps` and a daemon that answered nothing look identical."""
    assert diagnosis.containers(expected=0, running=(), unhealthy=()).verdict == diagnosis.UNKNOWN


def test_an_expired_certificate_is_a_problem_and_a_near_one_is_a_warning() -> None:
    assert diagnosis.tls(days_remaining=-1, not_after="x").verdict == diagnosis.PROBLEM
    assert diagnosis.tls(days_remaining=5, not_after="x").verdict == diagnosis.WARN
    assert diagnosis.tls(days_remaining=60, not_after="x").verdict == diagnosis.OK


def test_the_tls_warning_fires_after_renewal_should_have_happened() -> None:
    """Let's Encrypt renews at 30 days. A threshold at or above that would warn
    on every healthy certificate for the fortnight before renewal."""
    assert diagnosis.TLS_WARN_DAYS < 30


def test_the_cluster_and_the_pooler_are_reported_separately() -> None:
    """They fail independently and need different repairs, so a single boolean
    would collapse two diagnoses into one."""
    assert "pooler" in diagnosis.database(reachable=True, pooler_reachable=False).detail
    assert "cluster" in diagnosis.database(reachable=False, pooler_reachable=True).detail
    assert diagnosis.database(reachable=True, pooler_reachable=True).verdict == diagnosis.OK


def test_a_ledger_behind_the_release_is_a_problem_and_ahead_is_a_warning() -> None:
    """Ahead is not a failure: it is a host running a newer release than this
    checkout, which is normal mid-trip and is worth saying rather than failing."""
    assert diagnosis.migrations(applied=20, released=21).verdict == diagnosis.PROBLEM
    assert diagnosis.migrations(applied=22, released=21).verdict == diagnosis.WARN
    assert diagnosis.migrations(applied=21, released=21).verdict == diagnosis.OK
    assert diagnosis.migrations(applied=None, released=21).verdict == diagnosis.UNKNOWN


#: Every status `backup_report` can emit, and the verdict this session gives it.
#: **The keys are the module's own constants, not typed strings** — see
#: `test_every_status_the_repository_can_emit_is_classified` for why that
#: distinction is the whole point of the table.
REPOSITORY_VERDICTS = {
    backup_report.STATUS_NOT_OBSERVED: diagnosis.UNKNOWN,
    backup_report.STATUS_UNCONFIGURED: diagnosis.PROBLEM,
    backup_report.STATUS_AWAITING_FIRST_BACKUP: diagnosis.WARN,
    backup_report.STATUS_READY: diagnosis.OK,
    backup_report.STATUS_FAILING: diagnosis.PROBLEM,
}


def test_a_stanza_with_no_backup_yet_is_a_warning_not_a_problem() -> None:
    """ADR 0149: `awaiting_first_backup` is the honest state of a freshly
    created stanza, and a deploy that just made one is not broken."""
    for status, expected in REPOSITORY_VERDICTS.items():
        last = "t" if status == backup_report.STATUS_READY else None
        assert diagnosis.repository(status=status, last_full_backup_at=last).verdict == expected, (
            f"{status} should be {expected}"
        )
    assert diagnosis.repository(status=None, last_full_backup_at=None).verdict == diagnosis.UNKNOWN


def test_every_status_the_repository_can_emit_is_classified() -> None:
    """D674 — question 5, answered wrong again.

    The version of this file that shipped in Run 3 asserted `status="ok"` was
    `OK`. **`backup_report` has never emitted `"ok"`.** Its five statuses are
    `not_observed`, `unconfigured`, `awaiting_first_backup`, `ready` and
    `failing`. So the assertion measured a string its target cannot produce
    (D374), passed for that reason, and the real healthy status fell through to
    the catch-all: the first live run reported `PROBLEM the repository reports
    ready` against a repository holding a full backup from the previous day.

    Two more literals would not have repaired the class. **This test derives the
    set from `backup_report` itself**, so a sixth status added later cannot
    reach the catch-all silently — it reddens here, offline, and its author has
    to decide what it means.
    """
    emitted = {
        value
        for name, value in vars(backup_report).items()
        if name.startswith("STATUS_") and isinstance(value, str)
    }
    assert emitted, "no STATUS_* constants found — this test has lost its subject"
    unclassified = emitted - set(REPOSITORY_VERDICTS)
    assert not unclassified, (
        f"backup_report can emit {sorted(unclassified)}, and diagnosis.repository would send "
        f"each to the catch-all PROBLEM branch without anyone deciding that is right"
    )
    stale = set(REPOSITORY_VERDICTS) - emitted
    assert not stale, (
        f"{sorted(stale)} is classified here but nothing emits it — that is the D374 shape "
        f"this test exists to prevent"
    )


def test_the_archiver_verdict_is_handed_in_not_recomputed() -> None:
    """D630. `backup_report.archiving_is_failing` already ships the predicate,
    measured with rig 7 arm G, and it compares timestamps rather than
    `failed_count` — which stood at 26 on a healthy cluster (D553). Deriving a
    second threshold here is the D57/D262 pattern."""
    assert diagnosis.archiver(failing=True, last_archived_time=None).verdict == diagnosis.PROBLEM
    assert diagnosis.archiver(failing=False, last_archived_time="t").verdict == diagnosis.OK
    assert diagnosis.archiver(failing=None, last_archived_time=None).verdict == diagnosis.UNKNOWN


# ---------------------------------------------------------------------------
# The disk threshold is derived from what a restore needs
# ---------------------------------------------------------------------------


def test_disk_headroom_is_measured_in_copies_of_the_cluster() -> None:
    """Not a percentage. A restore materialises a second copy of the cluster, so
    "80% full" says nothing without knowing how big the cluster is: 80% of a
    small disk can hold three copies and 80% of a large one none."""
    cluster = 1000

    assert (
        diagnosis.disk_headroom(cluster_kb=cluster, available_kb=500, mount="/pg").verdict
        == diagnosis.PROBLEM
    )
    assert (
        diagnosis.disk_headroom(cluster_kb=cluster, available_kb=1500, mount="/pg").verdict
        == diagnosis.WARN
    )
    assert (
        diagnosis.disk_headroom(cluster_kb=cluster, available_kb=5000, mount="/pg").verdict
        == diagnosis.OK
    )


def test_a_disk_problem_says_a_restore_cannot_run() -> None:
    """The consequence, not the number. An operator reading "82% used" has to
    know what this deployment promises; "a restore cannot run" is the promise."""
    check = diagnosis.disk_headroom(cluster_kb=1000, available_kb=100, mount="/pg")
    assert "restore cannot run" in check.detail


def test_an_unmeasurable_disk_is_unknown() -> None:
    assert (
        diagnosis.disk_headroom(cluster_kb=None, available_kb=500, mount="/pg").verdict
        == diagnosis.UNKNOWN
    )
    assert (
        diagnosis.disk_headroom(cluster_kb=0, available_kb=500, mount="/pg").verdict
        == diagnosis.UNKNOWN
    )


def test_the_report_names_the_mount_it_measured() -> None:
    """D634: `/` and the volume coincide on a developer machine. A report that
    did not say which filesystem it read could not be checked against the one
    that actually fills up."""
    check = diagnosis.disk_headroom(
        cluster_kb=10, available_kb=100, mount="/var/lib/postgresql/18/docker"
    )
    assert "/var/lib/postgresql/18/docker" in check.detail


# ---------------------------------------------------------------------------
# Source-level, and labelled as such
# ---------------------------------------------------------------------------


def _document_reads(source: str) -> set[str]:
    """Every literal key read off a name spelled `document`, as in D600's guard."""
    keys: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "document"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            keys.add(node.args[0].value)
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "document"
            and isinstance(node.slice, ast.Constant)
        ):
            keys.add(node.slice.value)
    return keys


def test_the_doctor_reads_no_status_block_off_the_deployed_document() -> None:
    """ADR 0158's central rule, asserted rather than intended.

    The document carries `backup_state.status`, `tls.status`, `mcp.status` and
    `database.observed` — every one of them recorded at deploy time. Echoing any
    of them would produce a well-formed diagnosis of a moment that has passed,
    which is precisely the defect class this project keeps producing.

    `backup_state` is the sharpest case and the reason this is a class rule:
    the schema gives it `wal_archived_count` and `wal_failed_count` and **no
    timestamps**, so a doctor reading it for archiver health would be forced onto
    the cumulative counter D553 measured at 26 on a healthy cluster.
    """
    source = (REPO_ROOT / "bin" / "doctor.py").read_text(encoding="utf-8")
    observed_blocks = {"backup_state", "mcp", "tls", "api", "jwt", "secrets", "bootstrap"}
    read = _document_reads(source)

    # Premise: the scan finds the reads it is supposed to find. Without this the
    # assertion below passes on an empty set.
    assert {"project", "database", "routes"} <= read, (
        f"the scan found {sorted(read)}; it is not reading doctor.py's document access"
    )

    echoed = sorted(read & observed_blocks)
    assert not echoed, (
        f"bin/doctor.py reads {echoed} off the deployed document. Those blocks record "
        "what was observed at DEPLOY time; a verdict built from one describes a moment "
        "that has passed (ADR 0158). Read it live."
    )


def test_the_deployed_mode_cannot_reach_the_bare_python() -> None:
    """ADR 0158's stricter replacement for a premise that stopped being true.

    `test_root_script_policy` asserts nothing privileged *invokes* `doctor.sh`,
    and that still holds — an operator typing `sudo` is not a script. What
    changed is the comment's premise: `doctor.sh` now has a root mode. Under
    `sudo`, `secure_path` hides an activated venv, so the workstation mode's
    deliberate bare `python` would report a false failure on every host.

    The property that keeps that impossible is the ordering: `--project`
    delegates and `exec`s before any workstation check runs.
    """
    source = (REPO_ROOT / "bin" / "doctor.sh").read_text(encoding="utf-8")

    body = source.split("deployed_mode() {")[1].split("\n}")[0]
    assert "exec " in body, (
        "deployed_mode must exec, so it can never return into the workstation checks"
    )
    assert "python_bin" in body, "deployed mode must resolve an interpreter, not trust the name"
    assert "command -v python\n" not in body and "python -c" not in body, (
        "deployed mode reaches a bare python; under sudo secure_path hides the venv"
    )

    main_body = source.split("main() {")[1]
    assert main_body.index("--project") < main_body.index("check_command"), (
        "a workstation check runs before --project is dispatched; the two modes must not mix"
    )


def test_the_doctor_is_registered_with_the_deployed_document_class_guard() -> None:
    """D637. That guard's reader list is hand-maintained, so a new reader is
    covered only if someone remembers. This fails if anyone forgets for doctor."""
    guard = (REPO_ROOT / "tests" / "contract" / "test_container_selectors.py").read_text(
        encoding="utf-8"
    )
    assert '"bin/doctor.py"' in guard.split("DEPLOYED_DOCUMENT_READERS")[1].split(")")[0]


def test_the_schema_still_gives_the_backup_state_no_timestamps() -> None:
    """The premise ADR 0158 rests on, asserted so that adding them re-opens it.

    If `backupState` ever gains `last_archived_time`, the argument that the
    document *cannot* answer archiver health stops holding — and somebody should
    re-read the ADR before deciding to echo it anyway.
    """
    schema = json.loads((REPO_ROOT / "schemas" / "outputs.schema.json").read_text("utf-8"))
    members = set(schema["$defs"]["backupState"].get("properties") or {})
    assert "wal_failed_count" in members, "reading the wrong definition"
    assert not (members & {"last_archived_time", "last_failed_time"}), (
        "backupState now carries archiver timestamps. ADR 0158 argues the deployed "
        "document cannot answer archiver health because it has only the cumulative "
        "counters; re-read it before anything starts trusting this block."
    )
