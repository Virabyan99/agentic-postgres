"""The release workflows: what triggers them, what they verify, what they may hold.

Session 43 (ADR 0284, D2667): `DX-PKG-002` -- `.github/workflows/publish-cli.yml`.
Run 7 adds the site's half (`site.yml`, ADR 0283). Read with `yaml.safe_load`
(where YAML 1.1 reads the key `on` as `True`), and the verify step's script is
EXECUTED against a fake `gh`, once per bucket -- what it decides, not what it
says.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

WORKFLOWS = REPO_ROOT / ".github" / "workflows"
PUBLISH = WORKFLOWS / "publish-cli.yml"
#: rig 43d: v1.14.2's commit.
PYPI_PUBLISH = "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33"


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _trigger(document: dict[str, Any]) -> Any:
    return document.get("on", document.get(True))


def _uses(document: dict[str, Any]) -> list[str]:
    return [
        step["uses"] for job in document["jobs"].values() for step in job["steps"] if "uses" in step
    ]


def test_publish_runs_only_on_a_release_tag() -> None:
    document = _load(PUBLISH)
    assert _trigger(document) == {"push": {"tags": ["[0-9]+.[0-9]+.[0-9]+"]}}
    assert document["concurrency"] == {"group": "publish-cli", "cancel-in-progress": False}
    assert document["jobs"]["publish"]["environment"] == "pypi"


def _verify_script() -> str:
    steps = _load(PUBLISH)["jobs"]["verify"]["steps"]
    (step,) = [step for step in steps if step.get("name") == "contract succeeded on this commit"]
    return step["run"]


def _run(name: str, number: int, status: str, conclusion: str | None) -> dict[str, Any]:
    return {"name": name, "run_number": number, "status": status, "conclusion": conclusion}


@pytest.mark.parametrize(
    ("runs", "passes"),
    [
        ([], False),  # nothing registered: not a verdict (D1057)
        ([_run("contract", 7, "completed", "success")], True),
        ([_run("contract", 7, "completed", "failure")], False),
        ([_run("contract", 7, "completed", "cancelled")], False),
        ([_run("contract", 7, "in_progress", None)], False),
        ([_run("site", 9, "completed", "success")], False),
        ([_run("contract", 7, "completed", "success"), _run("contract", 8, "completed", "failure")],
         False),
    ],
)  # fmt: skip
def test_publish_verifies_the_contract_run(tmp_path: Path, runs: list[dict], passes: bool) -> None:
    """The three buckets, executed: only the latest `contract` run's success passes."""
    jq = shutil.which("jq")
    if jq is None:
        pytest.skip("jq, which the step runs, is not on PATH")
    fake = tmp_path / "bin"
    fake.mkdir()
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps({"workflow_runs": runs}), encoding="utf-8")
    # `gh api URL --jq FILTER`: the fake applies the filter with the real jq.
    (fake / "gh").write_text(
        f'#!/bin/sh\necho "$2" > "{tmp_path}/url"\njq -c "$4" "{answer}"\n', encoding="utf-8"
    )
    (fake / "gh").chmod(0o755)
    done = subprocess.run(
        ["bash", "-c", _verify_script()],
        env={"PATH": f"{fake}:{Path(jq).parent}:/usr/bin:/bin",
             "GITHUB_REPOSITORY": "Virabyan99/agentic-postgres",
             "GITHUB_SHA": "0" * 40, "GH_TOKEN": "x"},
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert (done.returncode == 0) is passes, (runs, done.stdout, done.stderr)
    asked = (tmp_path / "url").read_text(encoding="utf-8")
    assert f"head_sha={'0' * 40}" in asked and "event=push" in asked and "branch=main" in asked


def test_the_tag_must_be_the_version() -> None:
    steps = _load(PUBLISH)["jobs"]["verify"]["steps"]
    (step,) = [step for step in steps if step.get("name") == "The tag equals VERSION"]
    assert '"${GITHUB_REF_NAME}" != "${version}"' in step["run"] and "cat VERSION" in step["run"]
    jobs = _load(PUBLISH)["jobs"]
    assert jobs["build"]["needs"] == "verify" and jobs["publish"]["needs"] == "build"


def test_only_the_publish_job_has_id_token() -> None:
    document = _load(PUBLISH)
    assert document["permissions"] == {}
    holders = [name for name, job in document["jobs"].items()
               if (job.get("permissions") or {}).get("id-token") == "write"]  # fmt: skip
    assert holders == ["publish"]
    assert document["jobs"]["publish"]["permissions"] == {"id-token": "write"}
    for name, job in document["jobs"].items():
        assert "permissions" in job, f"{name} inherits instead of declaring"
        assert "secrets." not in json.dumps(job), f"{name} reads a secret"


def test_publish_pins_the_action() -> None:
    uses = _uses(_load(PUBLISH))
    assert PYPI_PUBLISH in uses
    for action in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", action), (
            f"{action} is not pinned by SHA"
        )
