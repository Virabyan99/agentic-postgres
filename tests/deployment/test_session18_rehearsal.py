"""Session 18's live halves for the failure rehearsals (`OPS-REHEARSE-001`..`008`).

Written at the bump (Run 5; D1020) and never executed before the trip. A
rehearsal is run by the operator, one at a time, never during a backup, with
`sudo bin/rehearse.sh SCENARIO --outputs FILE`; each writes
`evidence/rehearsal-<key>-<scenario>-<id>.json` (ADR 0190, ADR 0193). These
proofs read those records -- every reading a value the command produced --
and read the host afterwards for anything a rehearsal could have left behind.

The records are declared through `APG_REHEARSAL_EVIDENCE_DIR`, the directory
the operator ran the rehearsals into (the checkout's `evidence/` by default).
A scenario with no record is a failure, not a skip: the gate exports the
variable only when the operator gave the directory, and a directory without
the eight records is a trip that did not run them.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, deployed_output, diagnosis, port_allocations, rehearsal

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_REHEARSAL_EVIDENCE_DIR"
    ),
]


def _records() -> list[dict[str, Any]]:
    directory = Path(os.environ["APG_REHEARSAL_EVIDENCE_DIR"])
    if not directory.is_dir():
        pytest.fail(f"APG_REHEARSAL_EVIDENCE_DIR points at {directory}, which is not a directory")
    records = []
    for path in sorted(directory.glob("rehearsal-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("document_kind") == "rehearsal":
            records.append(record)
    return records


def _latest(scenario: str, keys: set[str]) -> dict[str, Any]:
    """The newest record of one scenario for a project this run knows."""
    matching = [
        r for r in _records() if r.get("scenario") == scenario and r.get("project_key") in keys
    ]
    if not matching:
        pytest.fail(
            f"no rehearsal record for {scenario} in {os.environ['APG_REHEARSAL_EVIDENCE_DIR']}; "
            f"run `sudo bin/rehearse.sh {scenario} --outputs <outputs.json>` on this host"
        )
    return max(matching, key=lambda r: str(r.get("finished_at")))


def _read(record: dict[str, Any]) -> dict[str, Any]:
    assert record.get("reversed") is True, (
        f"{record['scenario']} was not reversed: {record.get('verification')}"
    )
    assert record.get("verdict") in {"read", "recorded"}, (
        f"{record['scenario']} read nothing: {record.get('why')}"
    )
    return record["readings"]


def _keys(project_a: dict[str, Any]) -> set[str]:
    keys = {str(project_a["project"]["key"])}
    other = os.environ.get("APG_PROJECT_B_OUTPUTS")
    if other and Path(other).is_file():
        keys.add(str(json.loads(Path(other).read_text(encoding="utf-8"))["project"]["key"]))
    return keys


def _doctor(sh_status, key: str) -> dict[str, dict[str, Any]]:
    code, out, err = sh_status(str(REPO_ROOT / "bin" / "doctor.py"), "--project", key, "--json")
    assert code in (0, 6), f"doctor --json exited {code}\n{err}"
    return {check["name"]: check for check in json.loads(out)["checks"]}


# ---------------------------------------------------------------------------


def test_every_rehearsal_reversed_and_nothing_of_its_own_is_left_behind(
    project_a: dict[str, Any], as_root, sh_status
) -> None:
    """`OPS-REHEARSE-001`. Every record in the directory says reversed; the
    in-progress file is absent; nothing tagged by a rehearsal remains on the
    host -- no moved-aside registry, no foreign lock beside a deployed
    document, no rule in DOCKER-USER carrying the rehearsal comment -- and
    `--plan` changes nothing under the state root."""
    del as_root
    records = _records()
    assert records, "the directory holds no rehearsal record"
    unreversed = [r["scenario"] for r in records if not r.get("reversed")]
    assert not unreversed, f"un-reversed rehearsals on record: {unreversed}"

    state_root = deployed_output.PROJECT_STATE_ROOT
    progress = state_root.parent / rehearsal.STATE_FILENAME
    assert not progress.exists(), f"{progress} names an un-reversed rehearsal"
    registry = Path(port_allocations.REGISTRY_PATH)
    assert registry.is_file(), "the port registry is absent after the rehearsals"
    aside = list(registry.parent.glob(f"{registry.name}.{rehearsal.COMMENT_PREFIX}*"))
    assert not aside, f"a moved-aside registry remains: {aside}"
    foreign = list(state_root.glob(f"*/{rehearsal.COMMENT_PREFIX}*"))
    assert not foreign, f"a rehearsal's file remains beside a deployed document: {foreign}"
    code, out, _ = sh_status("iptables", "-S", "DOCKER-USER")
    assert code == 0, "DOCKER-USER could not be listed"
    assert rehearsal.COMMENT_PREFIX not in out, "a rehearsal's rule remains in DOCKER-USER"

    before = {p: p.stat().st_mtime_ns for p in state_root.rglob("*")}
    code, out, err = sh_status(
        str(REPO_ROOT / "bin" / "rehearse.sh"),
        "disk-threshold",
        "--outputs",
        os.environ["APG_PROJECT_A_OUTPUTS"],
        "--plan",
    )
    assert code == 0, f"rehearse.sh --plan exited {code}\n{err}"
    assert "nothing was run" in out
    after = {p: p.stat().st_mtime_ns for p in state_root.rglob("*")}
    assert before == after, "--plan changed something under the state root"


def test_service_termination_was_read_on_this_host(project_a: dict[str, Any]) -> None:
    """`OPS-REHEARSE-002`. The record: the service came back by the restart
    policy (restart count incremented, no fallback), its route answered 200
    within the bound, and the doctor's containers and route checks read ok
    after. Whether the doctor saw the gap at T+0 is recorded either way."""
    record = _latest("service-termination", _keys(project_a))
    readings = _read(record)
    assert readings["restarted"] is True
    assert readings["restart_count_after"] == readings["restart_count_before"] + 1
    assert readings["route_status_after"] == 200
    assert float(readings["seconds_to_ready"]) <= record["bound_seconds"]
    assert all(v == diagnosis.OK for v in readings["doctor_after"].values()), readings[
        "doctor_after"
    ]
    assert isinstance(readings["gap_reported"], bool)


def test_database_restart_was_read_on_this_host(project_a: dict[str, Any]) -> None:
    """`OPS-REHEARSE-003`. Every dependent reconnected without a restart of its
    own, the doctor's database, containers and route checks read ok within
    the bound, and the agent route answered its boundary (401) after."""
    readings = _read(_latest("database-restart", _keys(project_a)))
    assert all(v == diagnosis.OK for v in readings["doctor_after"].values()), readings[
        "doctor_after"
    ]
    assert readings["dependents_restarted"] == [], readings["dependents_restarted"]
    assert readings.get("agent_route_status") == 401, readings.get("agent_route_status")


def test_backup_credential_failure_was_read_on_this_host(project_a: dict[str, Any]) -> None:
    """`OPS-REHEARSE-004`. `check` with a credential that authenticates to
    nothing failed closed, the same check with the deployed credential passed
    (the control), and the reading names this project's stanza."""
    record = _latest("backup-credential-failure", _keys(project_a))
    readings = _read(record)
    assert readings["wrong_credential_exit"] not in (0, "timeout"), readings
    assert readings["deployed_credential_exit"] == 0, readings
    assert readings["repository"]["stanza"], "the reading names no stanza"
    assert "6c" in readings["a_deploy_would"]


def test_wal_archiving_failure_was_read_on_this_host(project_a: dict[str, Any]) -> None:
    """`OPS-REHEARSE-005`. With the mirror endpoint rejected on the backup
    network the copy failed, the archiver check read ok before and under the
    block (the primary's path untouched), no tagged rule remained after the
    reversal, and the copy after it completed."""
    readings = _read(_latest("wal-archiving-failure", _keys(project_a)))
    assert readings["blocked_copy_exit"] not in (0, "timeout"), readings["blocked_copy_exit"]
    assert readings["archiver_before"] == diagnosis.OK
    assert readings["archiver_under_block"] == diagnosis.OK
    assert readings["rules_remaining"] == 0
    assert readings["copy_after_reversal_exit"] == 0
    assert readings["blocked_addresses"], "no address was blocked"


def test_registry_loss_was_read_on_this_host(project_a: dict[str, Any], as_root, sh_status) -> None:
    """`OPS-REHEARSE-006`. Both verbs refused with exit 4 while the registry
    was absent and neither recreated it; the registry came back with its
    original bytes; and it reads today."""
    del as_root
    record = _latest("registry-loss", _keys(project_a))
    readings = _read(record)
    assert readings["show_exit"] == 4 and readings["release_exit"] == 4, readings
    assert readings["registry_present_after_show"] is False
    assert readings["registry_present_after_release"] is False
    assert record["verification"]["registry present with its original bytes"] is True
    code, _, err = sh_status(str(REPO_ROOT / "bin" / "database-ports.sh"), "show")
    assert code == 0, f"database-ports.sh show exits {code} today\n{err}"


def test_disk_threshold_was_read_on_this_host(
    project_a: dict[str, Any], as_root, sh_status
) -> None:
    """`OPS-REHEARSE-007`. Injected thresholds read `warn` and `problem`; the
    deployed threshold is what the doctor reports today, carried in its
    evidence, so an injected reading cannot be mistaken for the host's."""
    del as_root
    readings = _read(_latest("disk-threshold", _keys(project_a)))
    assert readings["disk_warn"] == diagnosis.WARN
    assert readings["disk_problem"] == diagnosis.PROBLEM
    assert readings["disk_default"] in {diagnosis.OK, diagnosis.WARN, diagnosis.PROBLEM}
    check = _doctor(sh_status, str(project_a["project"]["key"]))["disk headroom"]
    assert check["evidence"]["warn_below_copies"] == str(diagnosis.DISK_WARN_COPIES)
    assert check["evidence"]["problem_below_copies"] == str(diagnosis.DISK_PROBLEM_COPIES)


def test_capability_drift_was_read_on_this_host(
    project_a: dict[str, Any], as_root, sh_status
) -> None:
    """`OPS-REHEARSE-008`. A lock with a foreign hash read `problem`, the
    deployed lock read `ok` (the control), and the doctor reads the deployed
    lock as the one the document recorded today."""
    del as_root
    readings = _read(_latest("capability-drift", _keys(project_a)))
    assert readings["drift_foreign"] == diagnosis.PROBLEM
    assert readings["drift_deployed"] == diagnosis.OK
    check = _doctor(sh_status, str(project_a["project"]["key"]))["capability drift"]
    assert check["verdict"] == diagnosis.OK, check
    assert re.fullmatch(r"True", check["evidence"]["matches"]), check["evidence"]
