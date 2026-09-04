"""Session 17's live halves for the retirement verb, against the deployment.

Written in the run that built the verb (Run 4), not at the end of the session
(D938). Neither has executed before the trip. What can only be proved on a
deployment: that a plan run as root against a real deployed document names
real resources and changes nothing on the host, and that the refusals arrive
before anything is read that could be acted on. The removal itself is
`DEP-REMOVE-001`'s proof, on the trip's third project.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, deployed_output, naming

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"
    ),
]

WATCHED = (str(deployed_output.PROJECT_STATE_ROOT), "/var/lib/agentic-postgres")


def _host_manifest() -> Path:
    path = REPO_ROOT / "host.yaml"
    if not path.is_file():
        pytest.fail(
            f"{path} is not here; the operator runs this suite from the checkout that deployed"
        )
    return path


def test_a_retirement_plan_mutates_nothing(
    project_a: dict[str, Any], project_b: dict[str, Any], as_root, sh_status, tmp_path: Path
) -> None:
    """`FLEET-RETIRE-001`'s plan half on a real project: every file under the
    state root and the runtime state is where it was, no record is written,
    the plan names the project's real volume, unit and instance uuid, and it
    names nothing of the other project's."""
    del as_root
    key = project_b["project"]["key"]
    record = tmp_path / "record.json"

    def snapshot() -> str:
        code, out, err = sh_status("find", *WATCHED, "-type", "f", "-printf", "%p %T@ %s\\n")
        assert code == 0, err
        return out

    before = snapshot()
    assert before.strip()
    code, out, err = sh_status(
        "bin/project-retire.sh",
        "--host",
        str(_host_manifest()),
        "--project",
        key,
        "--confirm",
        key,
        "--record",
        str(record),
        "--plan",
        "--permanent",
        "--destroy-data",
    )
    assert code == 0, f"the plan exited {code}\n{err}"
    assert snapshot() == before, "the plan changed a file on the host"
    assert not record.exists()
    for expected in (
        naming.postgres_volume_name(key),
        f"agentic-postgres-project@{key}.service",
        project_b["database"]["observed"]["instance_uuid"],
        "plan only, nothing changes",
    ):
        assert expected in out, f"the plan does not name {expected!r}"
    assert project_a["project"]["key"] not in out, "the plan names the other project"


def test_a_retirement_refuses_the_wrong_confirmation(
    project_b: dict[str, Any], as_root, sh_status, tmp_path: Path
) -> None:
    del as_root
    key = project_b["project"]["key"]
    record = tmp_path / "record.json"
    for arguments, expected in (
        (("--confirm", "not-this-one"), "Nothing was changed"),
        ((), "--confirm"),
        (("--confirm", key), "--permanent"),
    ):
        code, _, err = sh_status(
            "bin/project-retire.sh",
            "--host",
            str(_host_manifest()),
            "--project",
            key,
            "--record",
            str(record),
            "--plan",
            *arguments,
        )
        assert code == 2, f"{arguments}: exited {code}\n{err}"
        assert expected in err
    assert not record.exists()
