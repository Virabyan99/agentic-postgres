"""Backup and recovery, proved against a deployment (Session 10 Run 9).

These were five placeholders until this run. `REC-PITR-001`, `REC-SAFE-001`,
`REC-SMOKE-001`, `REC-EVID-001` and `REC-WAL-001` now drive the real command
against a real cluster, and the module keeps its name and its five function names
because the acceptance registry and `docs/threat-model.md` both reference them by
node id (ADR 0096, D422).

**Read this before trusting anything here: none of it has ever executed.** The
host is at Session 9's release and Session 10 has never been deployed. That is
the exact condition CLAUDE.md §8 names as the most expensive open item -- *nothing
knows which proofs have never executed* -- and Session 9's trip found **three**
never-executed proofs in one gate, every one of them defective. So each test
below is written to fail loudly rather than plausibly, and every one that
disturbs the cluster **asserts its own stimulus landed** before drawing a
conclusion from it (D557).

What *has* executed is the logic underneath. `tests/contract/test_restore_test_command.py`
drives the same command end to end against a recording `docker` -- the
disposability guard with its control arm, all six smoke checks, and the
schema-set comparison. That is `REC-SAFE-001`'s offline half (D523) and the
reason this module is a thinner layer than five requirements would suggest.

**One drill, five readings.** The `drill` fixture seeds the scenario, runs
`bin/restore-test.sh` once, and yields what it produced together with the live
cluster's state from before and after. A restore is minutes and a second copy of
the cluster on disk; running five would prove nothing extra.

**Nothing here creates a table or a migration.** The scenario writes into
`app.notes`, which migration 0003 has owned since Session 3, under an owner id
that exists for the drill and nothing else. ADR 0003 does not move.
"""

from __future__ import annotations

# ruff: noqa: S608
#
# The interpolated values are UUIDs this module generated with
# and a role name from a rendered outputs document this repository produced.
# There is no caller input anywhere in this file.
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from tests.recovery.conftest import psql

from agentic_postgres import REPO_ROOT, backup_report

pytestmark = [
    pytest.mark.p0,
    pytest.mark.recovery,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_B_OUTPUTS"),
]

#: How long the whole drill may take. A bound, not a measurement: nothing has
#: timed a restore of this deployment, which is what the drill is for.
DRILL_TIMEOUT_SECONDS = 3600

#: The gap between each write and the recovery target.
#:
#: Seconds, not milliseconds: the target is a wall-clock timestamp, and a target
#: inside the same second as a write is a target whose side of the commit nobody
#: can predict.
SETTLE_SECONDS = 3

#: T1 writes this many rows. T2 writes one more, which must not survive.
T1_ROWS = 3


def _wal_switch(document: dict[str, Any]) -> int:
    """Force a segment and return `archived_count` once it has moved.

    **The stimulus control** (D557). `pg_switch_wal()` on an idle cluster
    archives *nothing*, so a scenario that switched and carried on would be
    measuring its own inactivity -- rig 7 reported a predicate `ok` in a state it
    had failed to break for exactly this reason. The caller writes first and this
    refuses to return until the counter moves.
    """
    before = int(psql(document, "SELECT archived_count FROM pg_stat_archiver"))
    psql(document, "SELECT pg_switch_wal()")
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        after = int(psql(document, "SELECT archived_count FROM pg_stat_archiver"))
        if after != before:
            return after
        time.sleep(2)
    pytest.fail(
        f"archived_count stayed at {before} for 180s after a WAL switch. Nothing "
        "reached the repository, so every conclusion drawn from here would be about "
        "an unarchived cluster."
    )
    raise AssertionError  # pragma: no cover - pytest.fail does not return


def _data_volume(document: dict[str, Any]) -> str:
    template = (
        '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql"}}{{.Name}}{{end}}{{end}}'
    )
    return subprocess.run(
        ["docker", "inspect", "-f", template, document["database"]["container"]],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    ).stdout.strip()


def _control_snapshot(document: dict[str, Any]) -> dict[str, Any]:
    """What `REC-SAFE-001` compares across the drill.

    **`system_identifier` is deliberately absent.** Measured (rig 8): a restore
    carries the *same* system identifier as the cluster it came from --
    `7677917767700738081` on both -- so a check reading it would pass while
    reading the drill instance, which is the single mistake this requirement
    exists to prevent (D566). `timeline_id` is what differs: 1 on the live
    cluster, 2 on a promoted restore.
    """
    return {
        "instance_uuid": psql(
            document, "SELECT instance_uuid::text FROM app_private.project_identity"
        ),
        "timeline_id": psql(document, "SELECT timeline_id FROM pg_control_checkpoint()"),
        "postmaster_start": psql(document, "SELECT pg_postmaster_start_time()"),
        "notes": int(psql(document, "SELECT count(*) FROM app.notes")),
        "volume": _data_volume(document),
    }


@pytest.fixture(scope="module")
def drill(project_b: dict[str, Any], require_root: None) -> dict[str, Any]:
    """Seed T1, take a target, seed T2, run the drill once, and report.

    Two writes either side of a timestamp, so a restore to that timestamp must
    contain the first and not the second. A restore that landed at the end of WAL
    would hold both and one that never advanced would hold neither -- and neither
    is distinguishable from the right answer with only one write.
    """
    owner = str(uuid.uuid4())
    before = _control_snapshot(project_b)

    for index in range(T1_ROWS):
        psql(
            project_b,
            f"INSERT INTO app.notes (owner_id, title) VALUES ('{owner}', 'drill-t1-{index}')",
        )
    _wal_switch(project_b)

    time.sleep(SETTLE_SECONDS)
    target = psql(project_b, "SELECT now()")
    time.sleep(SETTLE_SECONDS)

    psql(
        project_b,
        f"INSERT INTO app.notes (owner_id, title) VALUES ('{owner}', 'drill-t2-poison')",
    )
    _wal_switch(project_b)

    evidence_dir = Path(os.environ.get("APG_EVIDENCE_DIR", REPO_ROOT / "evidence"))
    started = time.monotonic()
    result = subprocess.run(
        [
            str(REPO_ROOT / "bin" / "restore-test.sh"),
            "--target-time",
            target,
            "--project-dir",
            str(Path(os.environ["APG_PROJECT_B_OUTPUTS"]).parent),
            "--smoke-owner-id",
            owner,
            "--evidence-dir",
            str(evidence_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=DRILL_TIMEOUT_SECONDS,
    )
    elapsed = time.monotonic() - started

    documents = sorted(
        evidence_dir.glob(f"restore-drill-{project_b['project']['key']}-*.json"),
        key=lambda path: path.stat().st_mtime,
    )
    evidence = json.loads(documents[-1].read_text(encoding="utf-8")) if documents else None

    return {
        "owner": owner,
        "target": target,
        "result": result,
        "evidence": evidence,
        "before": before,
        "after": _control_snapshot(project_b),
        "elapsed": elapsed,
        "document": project_b,
    }


# ---------------------------------------------------------------------------
# REC-PITR-001
# ---------------------------------------------------------------------------


def test_timestamp_targeted_restore_succeeds(drill: dict[str, Any]) -> None:
    """A restore to a timestamp between T1 and T2 promotes and answers.

    The exit code **and** the verdict, because they answer different questions:
    the exit code says the command ran, the verdict says the restored instance
    answered. Measured in rig 8, pgBackRest exits **0** for a target the archive
    cannot reach and the instance then never promotes -- so neither reading alone
    is the proof, and that is D145's shape a third time.
    """
    result = drill["result"]
    assert result.returncode == 0, (
        f"the drill exited {result.returncode}\n"
        f"--- stdout ---\n{result.stdout[-3000:]}\n--- stderr ---\n{result.stderr[-3000:]}"
    )
    evidence = drill["evidence"]
    assert evidence is not None, "the drill exited 0 and wrote no evidence document"
    assert evidence["verdict"]["passed"] is True, evidence["verdict"]["reasons"]

    recovery = evidence["recovery"]
    assert recovery["achieved_recovery_point"], (
        "pg_last_xact_replay_timestamp() was NULL, which is what a cluster that "
        "never recovered reports -- so this read something that is not a restore"
    )
    assert int(recovery["timeline_id"]) >= 2, (
        f"the restored instance is on timeline {recovery['timeline_id']}; the live "
        "cluster is on 1, so nothing promoted onto a new one"
    )
    assert evidence["backup_set"]["label"], "no backup set was recorded"
    assert evidence["backup_set"]["type"] in ("full", "diff", "incr")


# ---------------------------------------------------------------------------
# REC-SAFE-001 -- the host half. The offline half, with its control arm, is
# tests/contract/test_restore_test_command.py.
# ---------------------------------------------------------------------------


def test_restore_never_touches_the_active_volume(drill: dict[str, Any]) -> None:
    """The live cluster is the same cluster, on the same volume, after the drill.

    **Two proofs, neither sufficient** (D523). The offline arm drives the command
    with a stubbed `docker` and reads every `--mount` it emits, with a control arm
    proving a deliberately wrong *derivation* is refused; a source scan is refused
    outright, because a scan asking whether a name is mentioned is satisfied by
    dead code (D277) and has produced a false positive here before (D464).

    What this arm adds is what no offline test can reach: the volume, the instance
    identity and the postmaster read off the running deployment either side of a
    real restore.

    `postmaster_start` is the assertion that catches what the others miss -- a
    restore that took the live cluster down and brought it back leaves every other
    field equal.
    """
    before, after = drill["before"], drill["after"]

    assert before["volume"], "the live container reports no data volume to compare"
    assert after["volume"] == before["volume"], (
        f"the live cluster's data volume changed across the drill: "
        f"{before['volume']!r} -> {after['volume']!r}"
    )
    assert after["instance_uuid"] == before["instance_uuid"], (
        "the live cluster's instance identity changed, so it was reinitialised -- "
        "the volume was not merely written to, it was replaced"
    )
    assert after["postmaster_start"] == before["postmaster_start"], (
        "the live postmaster restarted during the drill. Nothing here should have "
        "touched it, and a restart is how a silent recreation begins."
    )
    assert after["timeline_id"] == before["timeline_id"] == "1", (
        f"the live cluster's timeline moved ({before['timeline_id']} -> "
        f"{after['timeline_id']}). A promoted restore advances the timeline; the "
        "live cluster must not have been the thing that promoted."
    )
    assert after["notes"] >= before["notes"], (
        "rows disappeared from the live cluster across the drill"
    )


def test_the_drill_left_none_of_its_own_resources_behind(drill: dict[str, Any]) -> None:
    """The teardown is part of the safety property, not tidiness.

    A drill volume left behind is a second copy of the cluster on a host whose
    disk headroom has never been measured; a drill container left behind holds the
    repository credential.
    """
    names = drill["evidence"]["drill"]
    for name in (names["container"], names["restore_container"]):
        probe = subprocess.run(
            ["docker", "inspect", name], capture_output=True, text=True, check=False, timeout=60
        )
        assert probe.returncode != 0, f"the drill container {name} still exists"
    probe = subprocess.run(
        ["docker", "volume", "inspect", names["volume"]],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert probe.returncode != 0, f"the drill volume {names['volume']} still exists"


# ---------------------------------------------------------------------------
# REC-SMOKE-001
# ---------------------------------------------------------------------------


def test_restored_instance_passes_schema_and_rls_smoke_checks(drill: dict[str, Any]) -> None:
    """Schema set, an owner-scoped read, and a write RPC, on the restored instance.

    **`applicable` is asserted as well as `passed`.** Two of the six checks need
    an owner id, and without one the command records them as not applicable rather
    than as passing -- so a drill run without `--smoke-owner-id` cannot satisfy
    this requirement by producing a document with fewer checks in it.

    The RLS half that matters is the second read: *the owner sees rows* passes
    against a table whose policies were dropped, and *nobody else sees them* does
    not. Both run as `app_runtime`, because FORCE RLS exempts a superuser and the
    same SELECT as `postgres` returns every row (ADR 0065/0066).
    """
    smoke = drill["evidence"]["smoke"]
    for name in (
        "answers_a_query",
        "left_recovery",
        "carries_a_schema_version",
        "schema_matches_the_release",
        "rls_read_is_owner_scoped",
        "write_rpc_succeeds",
    ):
        assert name in smoke, f"the drill recorded no {name} check"
        assert smoke[name]["applicable"] is True, (
            f"{name} did not run: {smoke[name]['detail']}. A check that did not run "
            "is not a check that passed."
        )
        assert smoke[name]["passed"] is True, f"{name}: {smoke[name]['detail']}"


def test_the_restore_landed_between_the_two_writes(drill: dict[str, Any]) -> None:
    """T1 is present and T2 is not, which is what a timestamp target means.

    Read out of the drill's own smoke result rather than by querying the restored
    instance, which no longer exists by the time this runs -- the teardown is
    unconditional, and that is `REC-SAFE-001`'s business.

    Requested and achieved must differ: the achieved point is the last transaction
    at or before the target, so equality means one was copied from the other
    rather than measured (D529).
    """
    recovery = drill["evidence"]["recovery"]
    assert recovery["requested_target"], "no requested target was read back"
    assert recovery["achieved_recovery_point"] != recovery["requested_target"], (
        "the achieved recovery point equals the requested target exactly, which "
        "means one of them was copied from the other rather than measured"
    )
    detail = drill["evidence"]["smoke"]["rls_read_is_owner_scoped"]["detail"]
    assert f"'{T1_ROWS}' note(s)" in detail, (
        f"the restored instance held a different number of the drill owner's notes "
        f"than the {T1_ROWS} that T1 wrote, so the restore did not land between the "
        f"two writes: {detail}"
    )


# ---------------------------------------------------------------------------
# REC-EVID-001
# ---------------------------------------------------------------------------


def test_restore_evidence_records_the_required_fields(drill: dict[str, Any]) -> None:
    """Every field D529 names, from the source ADR 0152 names for it.

    Presence and shape are checked here; that each is *measured* rather than
    invented is enforced where it is produced. The two most plausibly faked are
    checked for the property that would expose a fake: requested and achieved
    differ, and the RTO exceeds the restore alone and fits inside the wall time
    this test measured around the whole command.
    """
    evidence = drill["evidence"]
    assert evidence["kind"] == "restore_drill"
    assert evidence["project_key"] == drill["document"]["project"]["key"]
    assert evidence["stanza"]

    for path in (
        ("backup_set", "label"),
        ("backup_set", "type"),
        ("recovery", "requested_target"),
        ("recovery", "achieved_recovery_point"),
        ("recovery", "achieved_lsn"),
        ("recovery", "latest_recoverable_time"),
        ("timing", "rto_seconds"),
        ("timing", "restore_seconds"),
        ("timing", "recovery_seconds"),
    ):
        value: Any = evidence
        for key in path:
            value = value[key]
        assert value not in (None, ""), f"{'.'.join(path)} is empty"

    assert evidence["schema_version"], "no schema version was recorded"
    assert evidence["smoke"], "no smoke results were recorded"

    timing = evidence["timing"]
    assert timing["rto_seconds"] > timing["restore_seconds"], (
        "the RTO does not exceed the restore alone, so recovery was not counted -- "
        "and recovery is the half that scales with the distance from the backup set "
        "to the target"
    )
    assert timing["rto_seconds"] <= drill["elapsed"] + 1, (
        f"the drill reports an RTO of {timing['rto_seconds']}s inside a command this "
        f"test measured at {drill['elapsed']:.1f}s"
    )
    assert "restore-test.py" in timing["measured_by"]

    # D550: the published floor is a floor, and a drill landing later is that
    # working. Landing EARLIER is the inconsistency.
    assert evidence["recovery"]["achieved_is_at_or_after_floor"] is True

    serialized = json.dumps(evidence).lower()
    for forbidden in ("password", "cipher", "access_key", "secret"):
        assert forbidden not in serialized, f"the evidence document mentions {forbidden!r}"


# ---------------------------------------------------------------------------
# REC-WAL-001
# ---------------------------------------------------------------------------


def test_wal_archiving_failure_is_visible(project_b: dict[str, Any], require_root: None) -> None:
    """A broken archiver produces a non-zero signal, and a repaired one clears it.

    The predicate is `last_failed_time > last_archived_time`, never a counter:
    `failed_count` stood at **26 on a healthy, fully caught-up cluster** in rig 7,
    because every project accrues failures before its stanza exists (D553).

    **The break is `ALTER SYSTEM` plus a reload, and its effectiveness is asserted
    rather than assumed.** `archive_command` is reloadable -- unlike
    `archive_mode` -- but this deployment sets it on the postmaster's command
    line, and whether `postgresql.auto.conf` overrides a `-c` option here **has
    not been measured**. If it does not, the assertion below fails loudly on a
    cluster that is fine. That is the failure direction to prefer: the alternative
    is a test reporting a working signal after failing to break anything (D557).

    The repair runs in a `finally` and is asserted afterwards, because a test that
    leaves a project's archiver broken has done more damage than the requirement
    is worth.
    """
    healthy = backup_report.parse_archiver(psql(project_b, backup_report.ARCHIVER_QUERY))
    assert healthy is not None, "pg_stat_archiver could not be read at all"
    assert not backup_report.archiving_is_failing(healthy), (
        "the archiver is already failing before this test broke anything, so nothing "
        f"below could distinguish its own stimulus from the existing state: {healthy}"
    )

    broken = None
    try:
        psql(project_b, "ALTER SYSTEM SET archive_command = '/bin/false'")
        psql(project_b, "SELECT pg_reload_conf()")
        psql(
            project_b,
            f"INSERT INTO app.notes (owner_id, title) VALUES ('{uuid.uuid4()}', 'wal-signal')",
        )
        psql(project_b, "SELECT pg_switch_wal()")

        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            broken = backup_report.parse_archiver(psql(project_b, backup_report.ARCHIVER_QUERY))
            if broken and backup_report.archiving_is_failing(broken):
                break
            time.sleep(3)
    finally:
        psql(project_b, "ALTER SYSTEM RESET archive_command")
        psql(project_b, "SELECT pg_reload_conf()")

    assert broken is not None, "pg_stat_archiver stopped answering while the archiver was broken"
    assert backup_report.archiving_is_failing(broken), (
        "the predicate never went to `failing` after archive_command was set to "
        "/bin/false and a segment was switched. Either the reload did not take -- "
        "this deployment sets archive_command on the command line and the precedence "
        "is unmeasured -- or the signal does not work. Both are real failures, and "
        f"neither is this test passing.\nbefore={healthy}\nafter={broken}"
    )
    assert broken["last_failed_wal"], "the failing archiver named no segment"
    assert broken["failed_count"] > healthy["failed_count"], (
        "the cumulative counter did not move, so nothing actually attempted an "
        "archive -- the predicate flipped for some other reason"
    )

    # The control, in the same test. Without it, "the predicate said failing" is
    # consistent with a predicate that always says failing (D499).
    repaired = None
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        psql(
            project_b,
            f"INSERT INTO app.notes (owner_id, title) VALUES ('{uuid.uuid4()}', 'wal-repair')",
        )
        psql(project_b, "SELECT pg_switch_wal()")
        repaired = backup_report.parse_archiver(psql(project_b, backup_report.ARCHIVER_QUERY))
        if repaired and not backup_report.archiving_is_failing(repaired):
            break
        time.sleep(5)

    assert repaired is not None and not backup_report.archiving_is_failing(repaired), (
        "the archiver did not recover after archive_command was reset. This project's "
        f"WAL is not reaching its repository, and that is now an incident: {repaired}"
    )
