"""Session 37's host proofs: the control project beside its two neighbours.

`CTL-REG-002`'s four node ids, run by the sweep as root (claim
`control_plane_live`). Nothing here writes a row: the registry is read through
the operator's own command, never adopted (adoption is an operator's act on
Sheet A1, and the sweep is not an operator), and the two refused routes are
requests the control app does not serve.

The control project's deployed document is `APG_CONTROL_OUTPUTS` -- the
op-readable copy Sheet S1 installs, which the sweep checks byte-equal to the
document under `/etc/agentic-postgres/projects/` before it runs anything.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, naming
from agentic_postgres.evidence import ISOLATED_FIELDS

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST",
        "APG_CONTROL_OUTPUTS",
        "APG_PROJECT_A_OUTPUTS",
        "APG_PROJECT_B_OUTPUTS",
    ),
]


@pytest.fixture(scope="module")
def control_project() -> dict[str, Any]:
    path = Path(os.environ["APG_CONTROL_OUTPUTS"])
    if not path.is_file():
        pytest.fail(f"APG_CONTROL_OUTPUTS points at {path}, which does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


def _run(*command: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(command), stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=timeout, check=False,
    )  # fmt: skip


def _field(document: dict[str, Any], pointer: tuple[str, ...]) -> Any:
    """The value at `pointer`, or None where a DEPLOYED document carries none
    (`compose` and `project.generated_directory` are a render's alone)."""
    value: Any = document
    for key in pointer:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def test_the_registry_agrees_with_every_deployed_document(
    as_root: None,
    control_project: dict[str, Any],
    project_a: dict[str, Any],
    project_b: dict[str, Any],
) -> None:
    """`bin/control.sh registry --json`, the operator's own command: one outcome
    per project, `agrees` for alpha, beta and the control project, exit 0 --
    and the control project it names is the one APG_CONTROL_OUTPUTS describes."""
    read = _run(str(REPO_ROOT / "bin" / "control.sh"), "registry", "--json")
    assert read.returncode == 0, (
        f"registry exited {read.returncode}: {read.stdout[-400:]} {read.stderr[-400:]}"
    )
    answer = json.loads(read.stdout)
    assert answer["control_project"] == control_project["project"]["key"], answer["control_project"]
    outcomes = {o["project"]: o for o in answer["projects"]}
    keys = {document["project"]["key"] for document in (project_a, project_b, control_project)}
    assert keys <= set(outcomes), (sorted(keys), sorted(outcomes))
    differing = {key: o for key, o in outcomes.items() if o["outcome"] != "agrees"}
    assert not differing, differing


def test_the_control_project_is_isolated_from_both(
    control_project: dict[str, Any], project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    """`evidence.ISOLATED_FIELDS` and every derived role, between the control
    project's deployed document and each neighbour's: no value both carry is
    equal. A field neither carries is not a shared resource (ADR 0016), but the
    comparison must have compared something -- at least the key, the domain,
    the database's name and container, the issuer and audience, and the
    backup's stanza, prefix and bucket."""
    compared: set[tuple[str, ...]] = set()
    collisions = []
    for neighbour in (project_a, project_b):
        for pointer in ISOLATED_FIELDS:
            mine, theirs = _field(control_project, pointer), _field(neighbour, pointer)
            if mine is None or theirs is None:
                continue
            compared.add(pointer)
            if mine == theirs:
                collisions.append((neighbour["project"]["key"], ".".join(pointer), mine))
        roles = control_project["database"]["roles"]
        for role, name in roles.items():
            if neighbour["database"]["roles"].get(role) == name:
                collisions.append((neighbour["project"]["key"], f"role {role}", name))
    assert not collisions, collisions
    required = {
        ("project", "key"), ("project", "domain"),
        ("database", "name"), ("database", "container"),
        ("jwt", "issuer"), ("jwt", "audience"),
        ("backup", "stanza"), ("backup", "repository_prefix"), ("backup", "bucket"),
    }  # fmt: skip
    assert required <= compared, sorted(required - compared)


def test_the_control_mode_serves_no_release_admin_route(
    control_project: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
) -> None:
    """The control project's `auth` container runs `APP_MODE=control` (ADR
    0251): through the edge, `POST {routes.app}/auth/login` and `GET
    {routes.app}/admin/users` are not served (404), while `GET
    {routes.control}/me` without a token answers 401 -- the control: the same
    container, reached, refusing for the reason a served route refuses."""
    route = (control_project.get("routes") or {}).get("control") or {}
    assert route.get("status") == "ready" and route.get("url"), route
    served = api_call(f"{route['url']}/me")
    assert served.status == 401, (served.status, served.body[:200], served.reason)
    base = app_base(control_project)
    login = api_call(f"{base}/auth/login", method="POST", body={"username": "x", "password": "y"})
    assert login.status == 404, (login.status, login.body[:200])
    admin = api_call(f"{base}/admin/users")
    assert admin.status == 404, (admin.status, admin.body[:200])


@pytest.mark.requires_environment(
    "APG_LIVE_HOST",
    "APG_CONTROL_OUTPUTS",
    "APG_PROJECT_A_OUTPUTS",
    "APG_PROJECT_B_OUTPUTS",
    "APG_AFTER_REBOOT",
)
def test_the_control_project_survives_a_reboot(
    as_root: None, control_project: dict[str, Any]
) -> None:
    """D2060: the control project's unit is ENABLED, and after the reboot the
    sweep declares (`--after-reboot`), every one of its compose containers is
    running and started after the kernel booted -- it came back by itself."""
    key = control_project["project"]["key"]
    enabled = _run("systemctl", "is-enabled", f"agentic-postgres-project@{key}.service")
    assert enabled.stdout.strip() == "enabled", (enabled.stdout, enabled.stderr)
    booted = datetime.now(UTC).timestamp() - float(Path("/proc/uptime").read_text().split()[0])
    project = naming.compose_project_name(key)
    listing = _run(
        "docker",
        "ps",
        "-a",
        "-q",
        "--no-trunc",
        "--filter",
        f"label=com.docker.compose.project={project}",
    )
    ids = listing.stdout.split()
    assert listing.returncode == 0 and ids, f"{project}: no containers ({listing.stderr[:200]})"
    late = []
    for container in ids:
        inspected = json.loads(_run("docker", "inspect", container).stdout)[0]
        state = inspected["State"]
        started = datetime.fromisoformat(state["StartedAt"][:26].rstrip("Z") + "+00:00").timestamp()
        service = inspected["Config"]["Labels"].get("com.docker.compose.service")
        # A `compose run` container, or one with no restart policy that has
        # exited, is a job that finished -- not a service that failed to return.
        policy = (inspected["HostConfig"].get("RestartPolicy") or {}).get("Name") or "no"
        oneshot = inspected["Config"]["Labels"].get("com.docker.compose.oneoff") == "True"
        if oneshot or (policy == "no" and not state["Running"]):
            continue
        if not state["Running"] or started <= booted:
            late.append((service, state["Status"], state["StartedAt"]))
    assert not late, f"booted {datetime.fromtimestamp(booted, UTC).isoformat()}: {late}"
