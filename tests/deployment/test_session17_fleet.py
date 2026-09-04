"""Session 17's live halves: the fleet inventory against the deployment.

Written in the run that built the inventory (Run 2), not at the end of the
session -- D938's lesson. Nothing here has executed before the trip; each
docstring says what it asserts and the trip finds out.

**What can only be proved on a deployment**: that the inventory's rows are
the projects the host actually holds, that its health column is the doctor's
live verdict over real containers, that the timer states are systemd's
answers, that the denial counts come from a real audit table, that no live
credential reaches either rendering, and that running it changes nothing on
the host's disk.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from agentic_postgres import deployed_output, diagnosis, fleet

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"
    ),
]

#: Paths a run must leave untouched. The state root, the secret generations,
#: the rendered projects and the edge's dynamic configuration -- everything a
#: deploy writes and an inventory could be tempted to cache into.
WATCHED = (
    str(deployed_output.PROJECT_STATE_ROOT),
    "/var/lib/agentic-postgres",
)


def _inventory(sh_status, *arguments: str) -> tuple[int, str, str]:
    return sh_status("bin/fleet.sh", *arguments)


def test_the_inventory_sees_every_deployed_project_and_nothing_else(
    project_a: dict[str, Any], project_b: dict[str, Any], as_root, sh_status
) -> None:
    """`FLEET-INV-001`. The rows are the directories under the state root, no
    more and no fewer; the two projects this run knows are among them with
    the identity their documents carry; and each carries a health verdict the
    doctor produced live -- on a healthy deployment, not `unknown`."""
    del as_root
    code, out, err = _inventory(sh_status, "--json")
    assert code == 0, f"fleet.sh --json exited {code}\n{err}"
    parsed = json.loads(out)
    keys = {p["key"] for p in parsed["projects"]}

    listed_code, listed, _ = sh_status("ls", "-1", str(deployed_output.PROJECT_STATE_ROOT))
    assert listed_code == 0
    assert keys == set(listed.split()), "the inventory and the state root disagree"

    by_key = {p["key"]: p for p in parsed["projects"]}
    for document in (project_a, project_b):
        key = document["project"]["key"]
        row = by_key[key]
        assert row["domain"] == document["project"]["domain"]
        assert row["source_commit"] == document["source_commit"]
        assert row["deployed_through_session"] == document["deployed_through_session"]
        assert row["health"]["worst"] != diagnosis.UNKNOWN, (
            f"{key}: the doctor could not measure something on a healthy deployment: "
            f"{row['health']}"
        )
        assert "containers" in row["health"]["checks"]
        assert row["backups"]["state"] in {fleet.SCHEDULED, fleet.UNSCHEDULED}, (
            f"{key}: a timer state systemd did not answer: {row['backups']}"
        )
        assert isinstance(row["denials"]["total"], int), (
            f"{key}: the audit table was not read: {row['denials']}"
        )
        assert row["problems"] == []


def test_the_inventory_writes_nothing(as_root, sh_status) -> None:
    """`FLEET-INV-002`. Every file under the state root and the runtime state
    is where it was, by mtime and size, after both renderings ran."""
    del as_root

    def snapshot() -> str:
        code, out, err = sh_status("find", *WATCHED, "-type", "f", "-printf", "%p %T@ %s\\n")
        assert code == 0, err
        return out

    before = snapshot()
    assert before.strip(), "the snapshot saw nothing; it is not looking at the host"
    for arguments in ((), ("--json",)):
        code, _, err = _inventory(sh_status, *arguments)
        assert code == 0, err
    after = snapshot()
    changed = sorted(set(before.splitlines()) ^ set(after.splitlines()))
    assert not changed, f"the inventory changed these files: {changed}"


def test_the_inventory_prints_no_credential(
    project_a: dict[str, Any], as_root, sh_status, migration_password
) -> None:
    """A credential that genuinely exists in the active generation is absent
    from both renderings -- the doctor's own live proof, applied to the
    command that composes the doctor."""
    del as_root
    value = migration_password(project_a["project"]["key"]).strip()
    assert len(value) >= 16, f"the credential read back is {len(value)} bytes; vacuous scan"
    for arguments in ((), ("--json",)):
        _, out, err = _inventory(sh_status, *arguments)
        assert value not in out + err, f"fleet.sh {' '.join(arguments)} printed a credential"


def test_a_permanent_project_publishes_its_lifecycle_at_v15(
    project_a: dict[str, Any], project_b: dict[str, Any], as_root, sh_status
) -> None:
    """`FLEET-LIFE-001`'s live half (Run 3). Both host manifests are version 1
    and declare no lifecycle; the deployed document at version 15 says
    `permanent` for each, which is what they always were (ADR 0186), and the
    inventory reads it off the host and reports neither as expired."""
    del as_root
    for document in (project_a, project_b):
        key = document["project"]["key"]
        assert document["schema_version"] == deployed_output.SCHEMA_VERSION, (
            f"{key} is at outputs v{document['schema_version']}; this release deploys "
            f"v{deployed_output.SCHEMA_VERSION}"
        )
        assert document["project"]["lifecycle"] == {"kind": fleet.PERMANENT}, key

    code, out, err = _inventory(sh_status, "--json")
    assert code == 0, err
    by_key = {p["key"]: p for p in json.loads(out)["projects"]}
    for document in (project_a, project_b):
        row = by_key[document["project"]["key"]]
        assert row["lifecycle"] == {"kind": fleet.PERMANENT, "expires_at": None, "expired": False}


def test_the_text_rendering_names_every_project_on_every_line(as_root, sh_status) -> None:
    """Every non-blank line after the header starts with a project key: a
    value on one screen is always under the project it belongs to."""
    del as_root
    code, out, err = _inventory(sh_status)
    assert code == 0, err
    lines = out.splitlines()
    assert lines and lines[0].startswith("fleet: ")
    key = re.compile(r"^\s*[a-z][a-z0-9-]*\s")
    stray = [line for line in lines[1:] if line.strip() and not key.match(line)]
    assert not stray, f"lines carrying no project key: {stray}"


def test_every_permanent_project_is_scheduled(
    project_a: dict[str, Any], project_b: dict[str, Any], as_root, sh_status
) -> None:
    """`FLEET-BACKUP-001`'s live half (Run 5), and the proof that goes red on
    the deployment as it was on 2026-09-04: no backup timer was installed
    (D944). Both permanent projects' timers are enabled according to systemd,
    `schedule status` exits 0 for each, and the inventory agrees."""
    del as_root
    for document in (project_a, project_b):
        key = document["project"]["key"]
        if document["project"]["lifecycle"]["kind"] != fleet.PERMANENT:
            continue
        outputs = deployed_output.deployed_path(key)
        code, out, err = sh_status(
            "bin/backup.sh", "--outputs", str(outputs), "schedule", "status", "--json"
        )
        assert code == 0, f"{key}: schedule status exited {code} -- not scheduled\n{out}{err}"
        status = json.loads(out)
        assert status["schedule"] == fleet.SCHEDULED, status
        assert set(status["timers"].values()) == {fleet.ENABLED}, status

    code, out, err = _inventory(sh_status, "--json")
    assert code == 0, err
    for row in json.loads(out)["projects"]:
        if row["lifecycle"]["kind"] == fleet.PERMANENT:
            assert row["backups"]["state"] == fleet.SCHEDULED, row["backups"]
