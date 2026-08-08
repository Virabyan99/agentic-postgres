"""A restarted project comes back from its recorded release, with its data.

DEP-BOOT-001. Session 2 proved that what systemd runs is an immutable release
(``DEP-REL-001``); it could not prove that a restart preserves anything, because
until Session 3 a project held no state worth preserving. It does now, and the
restart path is the one place where a wrong answer is silent: a unit that comes
back healthy while having started the wrong set of services reports a clean
start either way.

Two properties, measured separately:

*The data is older than the process reading it.* ``bound_at`` in the identity
sentinel is compared against ``pg_postmaster_start_time()`` rather than against a
value this suite recorded a moment ago. A snapshot comparison shows the numbers
did not change; it does not show that the rows outlived the postmaster, which is
the actual claim and the one that fails if a restart silently reinitialised into
a fresh volume. Both are asserted, because a restart that changed the data would
pass the first and a restart that never happened would pass the second.

*The session came back from the document.* After ``systemctl restart`` the
cluster container must be running again. It is only running if the launcher read
``deployed_through_session`` from the deployed document (ADR 0032); the literal
``--session 2`` this launcher carried until Run 7 would restore the Session 2
profile, start no cluster, and leave ``systemctl status`` green. That is why the
assertion is on the container and not on the unit's exit status.

Nothing here is destructive. Each test restarts one project and asserts it came
back, so a failure to restore cannot pass silently -- the same discipline as
``test_removing_the_second_project_leaves_the_first_routed``, and the reason
destructive volume tests are not written here (D51, D69).
"""

from __future__ import annotations

import json
import ssl
import subprocess
import time
import urllib.request
from typing import Any

import pytest

from agentic_postgres.naming import HEALTH_ROUTE_PATH

pytestmark = [
    pytest.mark.p0,
    pytest.mark.deployment,
    pytest.mark.database,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"
    ),
]

#: A container restart is a postmaster start; a unit restart also re-materializes
#: secrets, re-renders the grant surface and rebuilds images. The second is
#: minutes on a cold layer cache, which is why the ceiling is generous rather
#: than tuned -- a timeout here reads as a failed restart, and reporting that
#: about a slow build would be worse than waiting.
CLUSTER_READY_TIMEOUT_SECONDS = 300


def psql(document: dict[str, Any], statement: str) -> subprocess.CompletedProcess[str]:
    """One statement over the Unix socket as the superuser.

    ``-i`` is not optional even with no stdin to send: ``docker exec`` without it
    discards a heredoc silently and exits 0, so a block that ran nothing looks
    exactly like one that worked.
    """
    return subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            document["database"]["container"],
            "psql",
            "-U",
            "postgres",
            "-d",
            document["database"]["name"],
            "-X",
            "-qtA",
            "-c",
            statement,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def query(document: dict[str, Any], statement: str) -> str:
    result = psql(document, statement)
    assert result.returncode == 0, f"{statement}\n{result.stderr.strip()}"
    return result.stdout.strip()


def await_cluster(document: dict[str, Any]) -> None:
    """Two consecutive successful queries, not one.

    ``pg_isready`` succeeds against the image's *temporary* initialisation
    server, and a single successful query can land on it too. The second query
    is what distinguishes a cluster that is up from one that is about to be
    shut down and restarted underneath the caller.
    """
    deadline = time.monotonic() + CLUSTER_READY_TIMEOUT_SECONDS
    consecutive = 0
    last = ""
    while time.monotonic() < deadline:
        result = psql(document, "SELECT 1;")
        if result.returncode == 0 and result.stdout.strip() == "1":
            consecutive += 1
            if consecutive == 2:
                return
        else:
            consecutive = 0
            last = result.stderr.strip()
        time.sleep(2)
    pytest.fail(
        f"{document['database']['container']} did not answer twice in "
        f"{CLUSTER_READY_TIMEOUT_SECONDS}s; last error: {last}"
    )


def state(document: dict[str, Any]) -> dict[str, str]:
    """What must be identical on the other side of a restart.

    Three separate reads rather than one digest over everything: the identity,
    the applied migrations, and ordinary table rows fail in different ways, and a
    combined hash would name none of them.
    """
    return {
        "identity": query(
            document,
            "SELECT project_key || '|' || instance_uuid || '|' "
            "|| extract(epoch from bound_at)::bigint "
            "FROM app_private.project_identity;",
        ),
        "ledger": query(
            document,
            "SELECT coalesce(md5(string_agg(version || rendered_sha256 || applied_at::text, "
            "',' ORDER BY version)), 'empty') FROM app_private.migration_ledger;",
        ),
        "notes": query(document, "SELECT count(*)::text FROM app.notes;"),
    }


def identity_predates_the_postmaster(document: dict[str, Any]) -> str:
    """``'true'`` when the sentinel row is older than the running postmaster.

    ``boolean || text`` and ``boolean::text`` both yield the words ``true`` and
    ``false``; ``t`` and ``f`` are what psql *prints* for a boolean column, which
    is a different thing and is what three Run 6 tests asserted against (D63).
    """
    return query(
        document,
        "SELECT (bound_at < pg_postmaster_start_time())::text FROM app_private.project_identity;",
    )


def health(hostname: str) -> dict[str, Any]:
    context = ssl.create_default_context()
    with urllib.request.urlopen(
        f"https://{hostname}{HEALTH_ROUTE_PATH}", timeout=30, context=context
    ) as response:
        return json.loads(response.read())


def container_is_running(name: str) -> bool:
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", name],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() == "true"


@pytest.fixture(params=["a", "b"])
def project(
    request: pytest.FixtureRequest, project_a: dict[str, Any], project_b: dict[str, Any]
) -> dict[str, Any]:
    return project_a if request.param == "a" else project_b


# ---------------------------------------------------------------------------
# DEP-BOOT-001
# ---------------------------------------------------------------------------


def test_restarting_the_container_preserves_the_cluster(project: dict[str, Any]) -> None:
    """Restart the postmaster; the volume is what carries the data across."""
    before = state(project)
    assert before["ledger"] != "empty", (
        "no migration has been applied; there is nothing here to preserve"
    )

    subprocess.run(
        ["docker", "restart", project["database"]["container"]],
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )
    await_cluster(project)

    assert state(project) == before, "the cluster changed across a restart"
    assert identity_predates_the_postmaster(project) == "true", (
        "the identity row is younger than the postmaster: this cluster did not "
        "restart onto the data it had, it created new data"
    )


def test_restarting_the_project_unit_brings_back_the_recorded_session(
    as_root, sh, sh_status, project: dict[str, Any]
) -> None:
    """The launcher reads the session; it does not repeat one (ADR 0032).

    A launcher with ``--session 2`` frozen into it restores the Session 2
    profile: the unit goes active, the edge attaches, the health route answers,
    and no cluster starts. Every signal above the container is green in that
    case, so the container is what is asserted.
    """
    del as_root
    key = project["project"]["key"]
    unit = f"agentic-postgres-project@{key}.service"
    recorded = project["deployed_through_session"]
    assert recorded >= 3, (
        f"{key} was deployed through session {recorded}; there is no cluster to lose"
    )

    before = state(project)

    sh("systemctl", "restart", unit)

    code, stdout, _ = sh_status("systemctl", "is-active", unit)
    assert code == 0 and stdout.strip() == "active", f"{unit} did not come back: {stdout}"

    container = project["database"]["container"]
    assert container_is_running(container), (
        f"{unit} is active but {container} is not running: the launcher restored a "
        f"session other than the {recorded} the deployed document records"
    )

    await_cluster(project)
    assert state(project) == before, "the cluster changed across a unit restart"
    assert identity_predates_the_postmaster(project) == "true"

    assert health(project["project"]["domain"])["project_key"] == key, (
        "the project came back without its ingress"
    )


def test_the_active_secret_generation_opens_the_cluster(
    as_root, rendered_document, migration_password, pg_login, project: dict[str, Any]
) -> None:
    """A valid secret is one that opens the cluster, not one whose file exists.

    Every start writes a *new* secret generation and repoints the project at it,
    so what a restart risks is not a missing file but a delivered value the
    cluster does not accept: the migration credential is set on the role by
    bootstrap, which a bare restart does not run, and the initialisation password
    is read by the image only when the data directory is empty (D66). A test that
    stopped at "the file is present" would be green over exactly that.

    What is measured is the generation the project points at *now*. The unit
    restart above wrote it; this holds after a deploy too, which is why it does
    not restart anything of its own to make the claim true.
    """
    del as_root
    key = project["project"]["key"]
    code, stdout, stderr = pg_login(
        project,
        rendered_document(key)["compose"]["networks"]["internal"],
        project["database"]["roles"]["migration_user"],
        migration_password(key),
    )
    assert code == 0 and stdout.strip() == "1", (
        f"the active secret generation does not open {key}: {stderr.strip()}"
    )
