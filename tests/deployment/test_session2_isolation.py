"""Two projects on one host share no route, no network, and no secret.

DEP-ISO-002. This is the Session 2 half of isolation: the parts that are true
because of how the edge and the secret store are built. ``DEP-ISO-001`` at
Session 12 keeps the broader claim about state and authority, and its
placeholder in ``tests/contract/test_future_deployment.py`` is untouched.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres.host_config import EDGE_STACK_NAME
from agentic_postgres.naming import HEALTH_ROUTE_PATH

pytestmark = [
    pytest.mark.p0,
    pytest.mark.deployment,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"
    ),
]


def health(hostname: str) -> dict[str, Any]:
    context = ssl.create_default_context()
    with urllib.request.urlopen(
        f"https://{hostname}{HEALTH_ROUTE_PATH}", timeout=20, context=context
    ) as response:
        return json.loads(response.read())


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_each_hostname_reaches_its_own_project(
    project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    assert health(project_a["project"]["domain"])["project_key"] == project_a["project"]["key"]
    assert health(project_b["project"]["domain"])["project_key"] == project_b["project"]["key"]


def test_the_two_projects_are_actually_distinct(
    project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    """Guard the guard: two names for one project would pass everything below."""
    assert project_a["project"]["key"] != project_b["project"]["key"]
    assert project_a["project"]["domain"] != project_b["project"]["domain"]


def test_neither_hostname_serves_the_other_project(
    project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    """Host-header routing must not fall through to the other project.

    A default router, or a rule matching on path alone, would make either
    hostname serve whichever project Traefik loaded first — an isolation
    failure that both projects' own health checks would report as success.
    """
    for own, other in ((project_a, project_b), (project_b, project_a)):
        payload = health(own["project"]["domain"])
        assert payload["project_key"] != other["project"]["key"], (
            f"{own['project']['domain']} served {other['project']['key']}"
        )


def test_an_unknown_hostname_is_not_served(project_a: dict[str, Any]) -> None:
    """No catch-all: an unmatched Host must not land on a real project."""
    request = urllib.request.Request(f"https://{project_a['project']['domain']}{HEALTH_ROUTE_PATH}")
    request.add_header("Host", "unclaimed.invalid")

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        # S310: literal https scheme; the host comes from the deployed document.
        with urllib.request.urlopen(request, timeout=20, context=context) as response:  # noqa: S310
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code

    assert status == 404, f"an unclaimed hostname was served with {status}"


# ---------------------------------------------------------------------------
# Networks
# ---------------------------------------------------------------------------


def test_the_recorded_networks_are_project_scoped(
    project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    """Guard the guard, for ADR 0023.

    Every network assertion below names a network out of the deployed document.
    If those fields ever went back to holding one host-wide value -- which is
    what ``egress_network`` holds, and what they were read from before -- the
    assertions would all keep passing while measuring nothing. This is the test
    that notices.
    """
    for field in ("project_edge_network", "project_internal_network"):
        assert project_a["edge"][field] != project_b["edge"][field], (
            f"both projects record the same {field}; it is not project-scoped"
        )
        for project in (project_a, project_b):
            assert project["edge"][field] != project["edge"]["egress_network"], (
                f"{field} holds the shared edge plane's network, not the project's"
            )


def test_traefik_joins_both_edge_networks_and_neither_internal_one(
    as_root, sh, project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    del as_root
    container = f"{EDGE_STACK_NAME}-traefik-1"
    networks = set(
        json.loads(
            sh("docker", "inspect", "--format", "{{json .NetworkSettings.Networks}}", container)
        )
    )

    for project in (project_a, project_b):
        edge = project["edge"]["project_edge_network"]
        assert edge in networks, f"Traefik is not attached to {edge}; that project has no ingress"

    # By name, not by prefix. The previous version matched networks against the
    # project *key* (`alpha-dev`), while every network name begins `apg-`, so
    # the comprehension was always empty and the assertion could not fail.
    internal = sorted(
        project["edge"]["project_internal_network"]
        for project in (project_a, project_b)
        if project["edge"]["project_internal_network"] in networks
    )
    assert not internal, f"Traefik is attached to project-internal networks: {internal}"


def test_neither_project_joins_the_others_network(
    as_root, sh, project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    del as_root
    for own, other in ((project_a, project_b), (project_b, project_a)):
        names = [
            line
            for line in sh(
                "docker",
                "ps",
                "--filter",
                f"label=apg.project.key={own['project']['key']}",
                "--format",
                "{{.Names}}",
            ).splitlines()
            if line.strip()
        ]
        assert names, f"no container carries the project label for {own['project']['key']}"

        for name in names:
            networks = set(
                json.loads(
                    sh("docker", "inspect", "--format", "{{json .NetworkSettings.Networks}}", name)
                )
            )
            # Both directions. Absent from the other project's networks is the
            # claim; present on its own is what makes the absence mean
            # something, rather than describing a container attached to nothing.
            assert own["edge"]["project_edge_network"] in networks, (
                f"{name} is not on its own edge network {own['edge']['project_edge_network']}"
            )
            for field in ("project_edge_network", "project_internal_network"):
                assert other["edge"][field] not in networks, (
                    f"{name} is attached to {other['project']['key']}'s {field}"
                )


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


def test_each_project_holds_only_its_own_secret_generation(
    as_root, project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    """Proved by the mount path, not by comparing digests.

    A digest comparison would show the two projects hold different bytes. It
    would not show that neither could read the other's file, which is the actual
    claim.
    """
    del as_root
    roots = {}
    for project in (project_a, project_b):
        key = project["project"]["key"]
        root = Path(f"/var/lib/agentic-postgres/secrets/{key}")
        assert root.is_dir(), f"{root} does not exist"
        roots[key] = root.resolve()

    (first, second) = roots.values()
    assert first != second
    assert not str(first).startswith(f"{second}/")
    assert not str(second).startswith(f"{first}/")


def test_removing_the_second_project_leaves_the_first_routed(
    as_root, sh, sh_status, await_health, project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    """The one deliberately mutating test, and it restores what it stopped.

    Isolation that only holds while both projects are healthy is not isolation.
    Proving otherwise requires stopping one, so this stops B, checks A, and
    starts B again — then asserts B came back, so a failure to restore cannot
    pass silently.

    A's check is immediate and stays immediate: that is the claim, and a retry
    there would let a route that came back *because B came back* pass. B's is
    polled, because `systemctl start` returns when the containers are healthy and
    the edge is attached, while Traefik discovers its backends a moment after
    that. Session 2 never lost the race; a Session 3 project's stack is large
    enough to reach the window (D75).
    """
    del as_root
    unit = f"agentic-postgres-project@{project_b['project']['key']}.service"

    sh("systemctl", "stop", unit)
    try:
        payload = health(project_a["project"]["domain"])
        assert payload["project_key"] == project_a["project"]["key"]
    finally:
        sh("systemctl", "start", unit)

    code, stdout, _ = sh_status("systemctl", "is-active", unit)
    assert code == 0 and stdout.strip() == "active", f"{unit} was not restored: {stdout}"
    await_health(project_b["project"]["domain"], project_b["project"]["key"])
