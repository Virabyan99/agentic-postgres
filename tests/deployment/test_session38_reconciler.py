"""Session 38's host proofs: the reconciler, the slot it consumed, the registry.

`OPN-LIVE-001`'s five node ids, run by the sweep as root (claim
`reconciler_live`) AFTER the lifecycle (Run 12, D2175) -- so the slot these
proofs read is one the customer created, slept, woke, resized, exported and
deleted through `/v1`, and none of them changes anything: the registry is read
through the operator's own command, the slot through `bin/slot.sh status`, the
unit through `systemctl` and the listeners through `ss`.

The deleted slot's deployed document is `APG_SLOT_OUTPUTS` -- the op-readable
copy Sheet K2 made BEFORE the deletion (the deletion removes the original); the
control project's is `APG_CONTROL_OUTPUTS`, and A's and B's are the sweep's
usual two. **None of these five proofs has ever executed.**
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, deployed_output, naming, slot
from agentic_postgres.evidence import ISOLATED_FIELDS

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST",
        "APG_CONTROL_OUTPUTS",
        "APG_SLOT_OUTPUTS",
        "APG_PROJECT_A_OUTPUTS",
        "APG_PROJECT_B_OUTPUTS",
        "APG_HOST_MANIFEST",
    ),
]

UNIT = "agentic-postgres-reconciler.service"


def _document(variable: str) -> dict[str, Any]:
    path = Path(os.environ[variable])
    if not path.is_file():
        pytest.fail(f"{variable} points at {path}, which does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def control_project() -> dict[str, Any]:
    return _document("APG_CONTROL_OUTPUTS")


@pytest.fixture(scope="module")
def slot_project() -> dict[str, Any]:
    document = _document("APG_SLOT_OUTPUTS")
    key = document["project"]["key"]
    assert slot.SLOT_KEY.match(key), f"APG_SLOT_OUTPUTS names {key}, which is not a slot's key"
    return document


def _run(*command: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(command), stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=timeout, check=False,
    )  # fmt: skip


def _field(document: dict[str, Any], pointer: tuple[str, ...]) -> Any:
    value: Any = document
    for key in pointer:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def test_the_reconciler_is_enabled_and_listens_nowhere(as_root: None) -> None:
    """ADR 0256, D2151: the unit is enabled and active, `reconciler.sh status`
    reads `idle` -- the lifecycle is over and the sweep is not an operation --
    and no process in the unit's control group holds a listening socket. The
    control: `ss` read some listener on this host (sshd's at least), so an
    empty answer would have been a reader that read nothing."""
    enabled = _run("systemctl", "is-enabled", UNIT)
    assert enabled.stdout.strip() == "enabled", (enabled.stdout, enabled.stderr)
    active = _run("systemctl", "is-active", UNIT)
    assert active.stdout.strip() == "active", (active.stdout, active.stderr)
    status = _run(str(REPO_ROOT / "bin" / "reconciler.sh"), "status")
    assert (status.returncode, status.stdout.strip()) == (0, "idle"), (
        status.returncode, status.stdout[-300:], status.stderr[-300:],
    )  # fmt: skip

    group = _run("systemctl", "show", "-p", "ControlGroup", "--value", UNIT).stdout.strip()
    assert group, f"{UNIT} names no control group"
    procs = Path("/sys/fs/cgroup") / group.lstrip("/") / "cgroup.procs"
    pids = {line.strip() for line in procs.read_text(encoding="utf-8").splitlines() if line.strip()}
    assert pids, f"{UNIT} is active with no process in {procs}"

    listening = _run("ss", "-Hlntup")
    assert listening.returncode == 0, listening.stderr
    owners = set(re.findall(r"pid=(\d+)", listening.stdout))
    assert owners, "ss read no listener at all on this host -- the reader read nothing"
    assert not (owners & pids), f"the reconciler holds a listener: {sorted(owners & pids)}"


def test_the_slot_was_consumed_and_its_volumes_removed(
    as_root: None, slot_project: dict[str, Any], project_a: dict[str, Any]
) -> None:
    """D2158, ADR 0187: the deleted slot reads `consumed` through the
    operator's own command, its tombstone is where `slot.py` keeps it, and no
    volume of its compose project remains -- the data went with the deletion.
    The control: the same volume listing for alpha's compose project is not
    empty, so the filter reads what it should."""
    key = slot_project["project"]["key"]
    status = _run(
        str(REPO_ROOT / "bin" / "slot.sh"),
        "status",
        "--host",
        os.environ["APG_HOST_MANIFEST"],
        "--json",
    )
    assert status.returncode in (0, 6), (status.returncode, status.stderr[-300:])
    rows = {row["key"]: row for row in json.loads(status.stdout)["slots"]}
    assert rows.get(key, {}).get("state") == "consumed", rows.get(key)
    assert (slot.SLOT_ROOT / key / slot.CONSUMED).is_file(), f"{key} has no tombstone"

    def volumes(document: dict[str, Any]) -> list[str]:
        project = naming.compose_project_name(document["project"]["key"])
        listed = _run(
            "docker",
            "volume",
            "ls",
            "-q",
            "--filter",
            f"label=com.docker.compose.project={project}",
        )
        assert listed.returncode == 0, listed.stderr
        return listed.stdout.split()

    assert volumes(slot_project) == [], volumes(slot_project)
    assert volumes(project_a), "alpha has no volume by its compose label: the filter reads nothing"


def test_the_registry_agrees_including_the_deletion(
    as_root: None,
    control_project: dict[str, Any],
    slot_project: dict[str, Any],
    project_a: dict[str, Any],
    project_b: dict[str, Any],
) -> None:
    """D2167: `bin/control.sh registry --json`, exit 0 -- `agrees` for alpha,
    beta and the control project, and the deleted slot's row `deleted`
    (printed `agrees (deleted)`): no document deployed under its key AND its
    tombstone present."""
    read = _run(str(REPO_ROOT / "bin" / "control.sh"), "registry", "--json")
    assert read.returncode == 0, (read.returncode, read.stdout[-400:], read.stderr[-400:])
    answer = json.loads(read.stdout)
    assert answer["control_project"] == control_project["project"]["key"]
    outcomes = {o["project"]: o["outcome"] for o in answer["projects"]}
    for document in (project_a, project_b, control_project):
        assert outcomes.get(document["project"]["key"]) == "agrees", outcomes
    assert outcomes.get(slot_project["project"]["key"]) == "deleted", outcomes
    assert all(o in ("agrees", "deleted") for o in outcomes.values()), outcomes


def test_the_slot_was_isolated_from_every_project(
    slot_project: dict[str, Any],
    control_project: dict[str, Any],
    project_a: dict[str, Any],
    project_b: dict[str, Any],
) -> None:
    """The isolation matrix extended to the reconciler's project (stage plan
    §7 item 3): no `ISOLATED_FIELDS` value and no derived role of the slot's
    document equals A's, B's or the control project's, and the comparison
    compared at least the key, the domain, the database, the issuer and
    audience and the backup's stanza, prefix and bucket. And `region` is
    MUST_MATCH (D2162): one host, one region, named by all four."""
    compared: set[tuple[str, ...]] = set()
    collisions = []
    for neighbour in (project_a, project_b, control_project):
        for pointer in ISOLATED_FIELDS:
            mine, theirs = _field(slot_project, pointer), _field(neighbour, pointer)
            if mine is None or theirs is None:
                continue
            compared.add(pointer)
            if mine == theirs:
                collisions.append((neighbour["project"]["key"], ".".join(pointer), mine))
        for role, name in slot_project["database"]["roles"].items():
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
    regions = {d["project"]["key"]: d.get("region") for d in
               (slot_project, control_project, project_a, project_b)}  # fmt: skip
    assert None not in regions.values(), regions
    assert len({json.dumps(r, sort_keys=True) for r in regions.values()}) == 1, regions


def test_the_control_projects_rest_route_is_withheld(
    control_project: dict[str, Any], api_call: Callable[..., Any]
) -> None:
    """D2137/D2144, LIFE-REST-001's live half: the control project's manifest
    withholds REST, so its deployed document records the REST route not
    `ready` and the API block `API_NOT_PUBLISHED`, and the edge answers the
    route's address 404 -- no router. The control: the same project's control
    route is served (401 without a token), so the 404 is the missing router's."""
    route = (control_project.get("routes") or {}).get("rest") or {}
    assert route.get("status") != "ready", route
    assert control_project["api"] == deployed_output.API_NOT_PUBLISHED, control_project["api"]
    assert route.get("url"), f"the REST route records no address to ask: {route}"
    withheld = api_call(f"{str(route['url']).rstrip('/')}/")
    assert withheld.status == 404, (withheld.status, withheld.body[:200])
    served = api_call(f"{control_project['routes']['control']['url'].rstrip('/')}/me")
    assert served.status == 401, (served.status, served.body[:200])
