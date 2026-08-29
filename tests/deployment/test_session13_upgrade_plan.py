"""`REL-*` live halves — the upgrade surface against a real deployment.

**The deployed document is read for the project key and for nothing else**, which
is ADR 0158's rule and `doctor.py`'s. Every verdict below comes from running the
command against the host, because a plan that was computed in a checkout proves
the planner works, not that this deployment can be planned for.

**The comparison the commands make is `rendered(installed)` against
`rendered(candidate)`**, both of the same document kind (D732, D733). The
installed one is at `deployed_output.rendered_path(key)/outputs.json`, root-owned,
which is why these need `as_root`.

**Every proof here also asserts the deployment did not change.** That is the
guarantee — *a plan before any mutation* — and asserting only that a plan came
back would leave the half that matters unmeasured. `.generated/` is not the
deployment: it is the checkout's staging area, and rendering a candidate there is
what an operator does before asking for a plan.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, deployed_output, template_version

pytestmark = [pytest.mark.p0, pytest.mark.deployment]

UPGRADE = REPO_ROOT / "bin" / "upgrade.sh"
APG = REPO_ROOT / "bin" / "apg.sh"


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(arguments[0]), *arguments[1:]],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def deployment_state(key: str) -> str:
    """Everything an upgrade would change, digested.

    The deployed document, the installed rendered document, and the container
    set. Not `.generated/`: that is the checkout's staging area and a render into
    it is the operator's own step, not a change to the deployment.
    """
    parts: list[str] = []
    for path in (
        deployed_output.deployed_path(key),
        deployed_output.rendered_path(key) / "outputs.json",
    ):
        try:
            stat = path.stat()
            parts.append(f"{path}:{stat.st_size}:{stat.st_mtime_ns}")
        except OSError as error:
            parts.append(f"{path}:unreadable:{error.errno}")

    containers = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}} {{.Status}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    parts.append(containers.stdout)
    return "\n".join(parts)


@pytest.fixture
def project_key(project_a: dict[str, Any]) -> str:
    """From the deployed document, which is the address book (ADR 0158)."""
    key = project_a.get("project", {}).get("key")
    assert key, "the deployed document names no project key"
    return str(key)


# ---------------------------------------------------------------------------
# REL-VER-001 — the installed version is machine-readable
# ---------------------------------------------------------------------------


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_the_installed_version_is_machine_readable(as_root: None, project_key: str) -> None:
    before = deployment_state(project_key)
    result = run(str(UPGRADE), "check", "--project", project_key, "--json")
    assert result.returncode == 0, result.stdout + result.stderr

    payload = json.loads(result.stdout)
    assert payload["project"] == project_key
    assert payload["verdict"] == "ok"
    assert payload["installed_version"], "the installed document carries no template_version"
    assert payload["release_version"] == template_version()
    assert payload["installed_kind"] == "rendered", (
        "the left-hand side must be a rendered document; a deployed one carries no `inputs`"
    )

    assert deployment_state(project_key) == before, "`check` changed the deployment"


# ---------------------------------------------------------------------------
# REL-PLAN-001 — a plan, and the deployment unchanged
# ---------------------------------------------------------------------------


@pytest.fixture
def candidate(project_key: str) -> Path:
    """What this checkout would render for the deployed project.

    Rendered from the manifest the deployment records rather than from an
    example: a plan computed against a different project's manifest would be a
    plan about nothing.
    """
    manifest = deployed_output.PROJECT_STATE_ROOT / project_key / "manifest.yaml"
    if not manifest.is_file():
        pytest.fail(f"no installed manifest at {manifest}")

    result = subprocess.run(
        [
            "./deploy.sh",
            "--project",
            str(manifest),
            "--capabilities",
            "capabilities.example.yaml",
            "--render-only",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    rendered = REPO_ROOT / ".generated" / project_key / "outputs.json"
    assert rendered.is_file(), f"the render produced no {rendered}"
    return rendered


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_a_plan_is_produced_without_changing_the_deployment(
    as_root: None, project_key: str, candidate: Path
) -> None:
    """The session's headline guarantee, asserted in both halves."""
    before = deployment_state(project_key)

    result = run(
        str(UPGRADE),
        "plan",
        "--project",
        project_key,
        "--candidate",
        str(candidate),
        "--json",
    )
    # 0 or 6: a plan that may proceed, or one that may not. Both are plans.
    assert result.returncode in {0, 6}, result.stdout + result.stderr

    payload = json.loads(result.stdout)
    assert payload["project"] == project_key
    assert payload["verdict"] in {"ok", "blocked"}, payload
    assert payload["installed_version"], payload
    assert payload["candidate_version"] == template_version()
    if payload["verdict"] == "blocked":
        assert payload["reasons"], "a blocked plan that names no reason sends a reader to source"

    assert deployment_state(project_key) == before, (
        "`plan` changed the deployment. It must produce a plan and mutate nothing."
    )


# ---------------------------------------------------------------------------
# REL-COMPAT-001 — the refusal, live
# ---------------------------------------------------------------------------


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_an_incompatible_candidate_is_refused_before_anything_changes(
    as_root: None, project_key: str, candidate: Path, tmp_path: Path
) -> None:
    """An operator input that moved is refused, on the deployment, before a write.

    The offline half proves the validator refuses. This proves the validator the
    **host** runs is that one — which is the narrower thing the offline half
    cannot say (D478).
    """
    document = json.loads(candidate.read_text(encoding="utf-8"))
    document["inputs"]["project_sha256"] = "9" * 64
    hostile = tmp_path / "hostile.json"
    hostile.write_text(json.dumps(document), encoding="utf-8")

    before = deployment_state(project_key)
    result = run(
        str(UPGRADE), "plan", "--project", project_key, "--candidate", str(hostile), "--json"
    )

    assert result.returncode == 6, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "blocked"
    assert "project_sha256" in payload["operator_digests_moved"]
    assert deployment_state(project_key) == before, "a refused plan changed the deployment"


# ---------------------------------------------------------------------------
# REL-CLI-001 — the front door reaches the verb on the host
# ---------------------------------------------------------------------------


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_the_front_door_reaches_the_verb_and_adds_nothing(as_root: None, project_key: str) -> None:
    """`apg upgrade check` is `bin/upgrade.sh check`, on the machine that matters.

    Compared output-for-output rather than merely both-exit-zero: a dispatcher
    that summarised, reformatted or re-ordered would pass the weaker check.
    """
    through = run(str(APG), "upgrade", "check", "--project", project_key, "--json")
    direct = run(str(UPGRADE), "check", "--project", project_key, "--json")

    assert through.returncode == direct.returncode, through.stderr + direct.stderr
    assert through.stdout == direct.stdout
    assert json.loads(through.stdout)["project"] == project_key
