"""What survives a restart, a reboot, and a credential rotation.

``DBX-PORT-001`` says host-loopback allocations are stable across redeploy,
restart and reboot. Run 8 proved the first; this module proves the other two, and
adds the two facts that make an allocation worth anything after a restart —
**both transports answer again, and nothing new is listening publicly.**

``SEC-DBX-004`` is the rotation: the credential a rotation replaced no longer
opens either transport, and the one that replaced it opens both.

**Three properties per restart, not one.** A unit that comes back healthy while
having started the wrong set of services reports a clean start either way, which
is why Session 3's convergence module asserts the container rather than the
unit's exit status. Session 4 adds two more things that can be quietly wrong: the
allocation can move — breaking every developer's saved tunnel and every
documented command, with nothing failing — and a restart is exactly when a
publication would be reintroduced.

**The restarts are run against project A, and project B is asserted undisturbed.**
Restarting both would double the slowest tests in the suite to prove the same
property twice. Reading B's allocation and transports after A restarts proves
something the second restart would not: that a project's recovery is its own.

**Nothing here is destructive.** Each test restarts one thing and asserts it came
back, so a failure to restore cannot pass silently — the same discipline as
Session 3's convergence module, and the reason destructive volume tests are not
written here (D51, D69).

Two procedural lessons from Session 3's reboot, both of which cost a run:

*A post-reboot check must wait for the units to reach* ``active``. A check run at
``up 0 min`` reported ten failures that all meant "still booting". The reboot test
below refuses to run rather than reporting that, which is the same information
without the ten red lines.

*A value the suite writes may not be compared for equality across a reboot.* The
isolation suite inserts a row on every run, so ``app.notes`` counts differ.
Identity and the migration ledger are compared for equality; rows are compared
for **never lost**. And the "before" a reboot is compared against is not a value
this suite recorded — it is the deployed document, written by the deploy that
predates the boot.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres.listeners import parse_listeners

pytestmark = [
    pytest.mark.p0,
    pytest.mark.deployment,
    pytest.mark.database,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"
    ),
]

#: Host-global port allocation state (ADR 0042). Re-read on every call rather
#: than through the session-scoped fixture: the question here is whether the file
#: changed, and a cached copy cannot answer it.
PORT_REGISTRY = Path("/etc/agentic-postgres/database-port-allocations.json")

#: The pooler's port on the project network, not a published host port. There is
#: no published host port (ADR 0044).
INTERNAL_POOL_PORT = 6432
INTERNAL_DIRECT_PORT = 5432

#: How long a transport may take to answer again after the thing under it
#: restarted. Generous: a unit restart re-materializes secrets, re-renders the
#: grant surface and rebuilds images, which is minutes on a cold layer cache. A
#: timeout here reads as a transport that never came back, and reporting that
#: about a slow build would be worse than waiting.
TRANSPORT_RETURN_TIMEOUT_SECONDS = 300

#: What is allowed to listen on a public address. The deployment host's own
#: baseline test owns this set; it is restated rather than imported because the
#: question here is different — not "is the baseline intact" but "did a restart
#: add something" — and because a restart is when a publication would appear.
#: UDP/68 is the DHCP client, which genuinely binds the public interface.
ALLOWED_PUBLIC = {("tcp", 22), ("tcp", 80), ("tcp", 443), ("udp", 68)}


def key(document: dict[str, Any]) -> str:
    return document["project"]["key"]


def allocation_now(project_key: str) -> dict[str, Any]:
    """This project's live allocation, read from disk at this moment.

    Refusing ambiguity the way the broker does: two live records for one key is a
    failure, because a first match would be a port reaching the wrong cluster and
    every assertion downstream would still pass.
    """
    assert PORT_REGISTRY.is_file(), f"no port allocation registry at {PORT_REGISTRY}"
    registry = json.loads(PORT_REGISTRY.read_text(encoding="utf-8"))
    live = [
        allocation
        for allocation in registry["allocations"]
        if allocation["project_key"] == project_key
        and allocation["state"] in ("reserved", "active")
    ]
    assert len(live) == 1, f"{project_key} holds {len(live)} live allocations"
    return live[0]


def public_listeners(sh) -> list[str]:
    """Public listeners that nothing accounts for, as printable strings.

    Parsed by ``agentic_postgres.listeners``, the same code
    ``bin/provision-host.sh --check`` uses. A second parser for one question is
    two chances to disagree about what "public" means, and in Session 2 they did.
    """
    return [
        f"{item.protocol}/{item.port} on {item.address}"
        for item in parse_listeners(sh("ss", "-H", "-lntup"))
        if not item.is_loopback and (item.protocol, item.port) not in ALLOWED_PUBLIC
    ]


def the_instrument_can_see(sh) -> None:
    """443 is listening publicly, in the same output the negative comes from.

    Without this the whole "no public listener" family passes on a host where
    ``ss`` returned nothing, a parser that matched nothing, or a command that
    silently produced no rows — a negative result from an instrument that cannot
    see anything. D114 is what that costs when it goes unstated: a request read
    as a measurement, in the document whose purpose was catching exactly that.
    """
    seen = {(item.protocol, item.port) for item in parse_listeners(sh("ss", "-H", "-lntup"))}
    assert ("tcp", 443) in seen, (
        "the edge is not listening on 443, so this scan is reporting an empty "
        "world rather than a closed one; every negative below would be vacuous"
    )


def container_is_running(name: str) -> bool:
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", name],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() == "true"


def pooler_of(document: dict[str, Any]) -> str:
    return document["database"]["container"].replace("-postgres-1", "-pgbouncer-1")


# ---------------------------------------------------------------------------
# The three facts asserted after every restart
# ---------------------------------------------------------------------------


def await_transports(document, transport_login, password) -> None:
    """Both transports accept the runtime credential again.

    Polled rather than asked once, and both are required: the pooled one is what
    a restart most plausibly breaks, and the direct one is the control that says
    a pooled failure is the pooler's rather than the cluster's.

    A real connection with a real credential, from a container on the project's
    own network. ``docker inspect`` reporting a healthy container is a statement
    about a health check; this is a statement about the transport.
    """
    network = document["edge"]["project_internal_network"]
    role = document["database"]["access_profiles"]["runtime_pooled"]["role"]
    deadline = time.monotonic() + TRANSPORT_RETURN_TIMEOUT_SECONDS
    pending = {"pooled": INTERNAL_POOL_PORT, "direct": INTERNAL_DIRECT_PORT}
    last: dict[str, str] = {}

    while pending and time.monotonic() < deadline:
        for name, port in list(pending.items()):
            host = "pgbouncer" if name == "pooled" else "postgres"
            code, stdout, stderr = transport_login(
                document, network, role, password, host=host, port=port
            )
            if code == 0 and stdout.strip() == "1":
                del pending[name]
            else:
                last[name] = stderr.strip() or stdout.strip()
        if pending:
            time.sleep(3)

    assert not pending, (
        f"{sorted(pending)} did not accept the runtime credential within "
        f"{TRANSPORT_RETURN_TIMEOUT_SECONDS}s: "
        + "; ".join(f"{name}: {message}" for name, message in last.items())
    )


def assert_converged(document, before, transport_login, password, sh) -> None:
    """The allocation is unchanged, both transports answer, nothing new listens."""
    await_transports(document, transport_login, password)

    after = allocation_now(key(document))
    assert after == before, (
        f"{key(document)}'s allocation changed across the restart:\n"
        f"  before {before}\n  after  {after}"
    )

    the_instrument_can_see(sh)
    assert not public_listeners(sh), "a restart introduced public listeners:\n" + "\n".join(
        public_listeners(sh)
    )


@pytest.fixture
def runtime_password(materialized_secret):
    """The pooler's copy of the application credential, from the active generation.

    The pooler's rather than a client fixture's: it is the copy the transport
    under test authenticates against, and reading a different consumer's file
    would prove a credential works for a service that was never given it.
    """

    def read(document: dict[str, Any]) -> str:
        return materialized_secret(key(document), "pgbouncer", "app_runtime_password")

    return read


# ---------------------------------------------------------------------------
# DBX-PORT-001 — the restart matrix
# ---------------------------------------------------------------------------


def test_restarting_the_pooler_keeps_the_allocation_and_both_transports(
    as_root, sh, project_a, project_b, transport_login, runtime_password
) -> None:
    """The pooler alone, with the cluster untouched underneath it.

    The cheapest of the four and the one most likely to be run by an operator by
    hand — ``docker restart`` on a pooler that has wedged. What it proves is that
    the pooler's configuration and its credential come back from state on disk
    rather than from anything a deploy left in memory.

    Goes red if: the rendered INI or the auth file is not readable at uid 70 on a
    second start; the allocation is rewritten by anything that observes a
    container change; or the pooled transport comes back without its user list,
    which authenticates nobody while the container reports healthy.
    """
    del as_root
    before = allocation_now(key(project_a))
    before_b = allocation_now(key(project_b))

    sh("docker", "restart", pooler_of(project_a))

    assert_converged(project_a, before, transport_login, runtime_password(project_a), sh)
    assert allocation_now(key(project_b)) == before_b, (
        "restarting one project's pooler moved the other project's allocation"
    )


def test_restarting_the_cluster_leaves_the_pooler_serving(
    as_root, sh, project_a, project_b, transport_login, runtime_password
) -> None:
    """Every server connection the pooler held dies at once.

    This is the restart with a real failure mode behind it: PgBouncer holds open
    server connections across clients, and a cluster restart invalidates all of
    them simultaneously. A pooler that did not reconnect would answer new clients
    with a stale backend error while its own container stayed healthy and its
    admin console kept working.

    Goes red if: the pooler does not re-establish server connections; the cluster
    comes back with a different identity, which would move the allocation; or the
    direct transport recovers while the pooled one does not — which is precisely
    why both are polled rather than only the one that was restarted.
    """
    del as_root
    before = allocation_now(key(project_a))
    before_b = allocation_now(key(project_b))

    sh("docker", "restart", project_a["database"]["container"])

    assert_converged(project_a, before, transport_login, runtime_password(project_a), sh)
    assert allocation_now(key(project_b)) == before_b
    assert container_is_running(pooler_of(project_a)), (
        "the pooler did not survive the cluster restarting underneath it"
    )


def test_restarting_the_project_unit_restores_both_transports(
    as_root, sh, sh_status, await_health, project_a, project_b, transport_login, runtime_password
) -> None:
    """The whole stack, through systemd and the installed launcher.

    The launcher reads ``deployed_through_session`` from the deployed document
    (ADR 0032); a launcher with a literal session frozen into it would restore an
    earlier profile, start no pooler, and leave ``systemctl status`` green. Every
    signal above the transport is green in that case, so the transport is what is
    asserted.

    Goes red if: the unit restores a session earlier than the document records;
    the re-materialized secret generation is not the one the pooler is started
    with; or the edge route does not come back, which is asserted last because it
    is the slowest and the least specific.
    """
    del as_root
    project_key = key(project_a)
    unit = f"agentic-postgres-project@{project_key}.service"
    recorded = project_a["deployed_through_session"]
    assert recorded >= 4, (
        f"{project_key} was deployed through session {recorded}; there is no pooler"
    )

    before = allocation_now(project_key)
    before_b = allocation_now(key(project_b))

    sh("systemctl", "restart", unit)

    code, stdout, _ = sh_status("systemctl", "is-active", unit)
    assert code == 0 and stdout.strip() == "active", f"{unit} did not come back: {stdout}"
    assert container_is_running(pooler_of(project_a)), (
        f"{unit} is active and no pooler is running: the launcher restored a session "
        f"other than the {recorded} the deployed document records"
    )

    assert_converged(project_a, before, transport_login, runtime_password(project_a), sh)
    assert allocation_now(key(project_b)) == before_b

    # Polled, not asked once: `systemctl start` returns when the containers are
    # healthy and the edge is attached, and Traefik discovers the backend a
    # moment after that (D75).
    await_health(project_a["project"]["domain"], project_key)


# ---------------------------------------------------------------------------
# DBX-PORT-001 — the reboot
# ---------------------------------------------------------------------------


def boot_time() -> int:
    """The host's boot, as an epoch second, from ``/proc/stat``.

    ``btime`` rather than ``uptime -s``: the latter prints a local-time string
    with no offset, and a comparison against a database timestamp would be an
    hour wrong twice a year without ever failing.
    """
    for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines():
        if line.startswith("btime "):
            return int(line.split()[1])
    pytest.fail("/proc/stat carries no btime")


@pytest.fixture(params=["a", "b"])
def either_project(request, project_a, project_b) -> dict[str, Any]:
    return project_a if request.param == "a" else project_b


@pytest.mark.requires_environment(
    "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS", "APG_AFTER_REBOOT"
)
def test_the_reboot_restored_the_projects_from_their_documents(
    as_root, sh, sh_status, either_project, transport_login, runtime_password
) -> None:
    """The one restart nothing in this suite can perform on itself.

    A test that rebooted the host would kill the process asserting the result, so
    the reboot is an operator step and ``--after-reboot`` is how the operator
    declares it happened. That makes the flag a claim, and the assertions below
    are what stop it being taken on trust: **the data predates the boot and every
    process reading it postdates the boot.** Both halves are needed. A cluster
    that reinitialised into a fresh volume passes the second; a host that was
    never rebooted passes the first.

    The "before" is the deployed document — written by a deploy that predates the
    boot, and not a value this suite recorded (Session 3's lesson: the isolation
    suite inserts a row on every run, so ``app.notes`` counts are compared for
    never-lost rather than for equality).

    Goes red if: a unit did not come back, and says to wait rather than reporting
    the ten failures a check at ``up 0 min`` produces; the allocation moved across
    the boot, which would break every saved tunnel; the identity row is younger
    than the postmaster; or a transport does not answer.
    """
    del as_root
    project_key = key(either_project)
    unit = f"agentic-postgres-project@{project_key}.service"

    code, stdout, _ = sh_status("systemctl", "is-active", unit)
    assert code == 0 and stdout.strip() == "active", (
        f"{unit} is {stdout.strip() or 'not active'}. Wait for the units to reach active "
        "before running the post-reboot check; at `up 0 min` every failure here means "
        "'still booting' and none of them means what it says."
    )

    booted = boot_time()
    container = either_project["database"]["container"]

    def query(statement: str) -> str:
        result = subprocess.run(
            ["docker", "exec", "-i", container, "psql", "-U", "postgres",
             "-d", either_project["database"]["name"], "-X", "-qtA", "-c", statement],
            capture_output=True, text=True, check=False, timeout=120,
        )  # fmt: skip
        assert result.returncode == 0, f"{statement}\n{result.stderr.strip()}"
        return result.stdout.strip()

    # The process postdates the boot, and the data predates it. `::text` rather
    # than psql's printed `t`/`f`, which is a different thing and is what three
    # Run 6 tests asserted against (D63).
    #
    # S608: `booted` is the result of `int(...)` over a field of /proc/stat, so
    # the interpolated text is a decimal integer or the read failed. psql has no
    # bind path through `-c`, and the alternative -- `-v` -- is the same
    # interpolation with a longer name.
    since_boot = f"to_timestamp({booted})"
    assert query(f"SELECT (pg_postmaster_start_time() > {since_boot})::text") == "true", (
        "the postmaster is older than the last boot, so this host has not rebooted "
        "and --after-reboot is asserting something that did not happen"
    )
    identity_predates = f"SELECT (bound_at < {since_boot})::text FROM app_private.project_identity"  # noqa: S608
    assert query(identity_predates) == "true", (
        "the identity row is younger than the last boot: this cluster did not come "
        "back onto the data it had, it created new data"
    )

    # Never lost, not unchanged.
    assert int(query("SELECT count(*) FROM app_private.migration_ledger")) > 0
    assert int(query("SELECT count(*) FROM app.notes")) > 0

    # The allocation against the deployed document, which the deploy wrote before
    # the boot. The registry and the document are two records of one decision, and
    # a reboot is where they would drift apart.
    allocation = allocation_now(project_key)
    assert allocation["state"] == "active"
    assert allocation["pooled_port"] == either_project["database"]["pooled"]["port"]
    assert allocation["direct_port"] == either_project["database"]["direct"]["port"]

    await_transports(either_project, transport_login, runtime_password(either_project))
    the_instrument_can_see(sh)
    assert not public_listeners(sh), "the reboot brought up public listeners:\n" + "\n".join(
        public_listeners(sh)
    )


# ---------------------------------------------------------------------------
# SEC-DBX-004 — the rotation
# ---------------------------------------------------------------------------


@pytest.mark.security
@pytest.mark.requires_environment(
    "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS", "APG_ROTATED_FROM_FILE"
)
def test_a_rotated_credential_is_replaced_in_both_planes(
    as_root, project_a, transport_login, runtime_password
) -> None:
    """The split-brain §4.3 exists to prevent, measured from both sides.

    Zero-downtime rotation is out of scope, so the state to plan for is
    PostgreSQL holding one password while the pooler holds another. That state
    passes a test of the direct transport and a test of the pooled one taken
    separately — with the *right* credential on one side and the *wrong* one on
    the other, whichever way round it went. So all four combinations are asserted
    in one run: the new credential opens both, and the old one opens neither.

    ``--rotated-from-file`` is supplied only in the maintenance window that
    rotated the credential, and its absence skips this rather than passing it. A
    skip is honest here: no rotation happened in this run.

    Goes red if: bootstrap set the new verifier and the pooler was not restarted
    onto the new generation, or the reverse; or the rotation replaced a value
    that was never in force, which the first assertion catches before any of the
    refusals can be misread as success.
    """
    del as_root
    old = Path(os.environ["APG_ROTATED_FROM_FILE"]).read_text(encoding="utf-8").rstrip("\n")
    assert old, "APG_ROTATED_FROM_FILE is empty"
    new = runtime_password(project_a)
    assert old != new, (
        "the credential supplied as the pre-rotation value is the one that is "
        "active; nothing was rotated, and every refusal below would be a failure "
        "of the control rather than a proof"
    )

    network = project_a["edge"]["project_internal_network"]
    role = project_a["database"]["access_profiles"]["runtime_pooled"]["role"]
    endpoints = {
        "pooled": ("pgbouncer", INTERNAL_POOL_PORT),
        "direct": ("postgres", INTERNAL_DIRECT_PORT),
    }

    # The positive control first, and on both transports. A cluster refusing
    # every login would satisfy both refusals below.
    for name, (host, port) in endpoints.items():
        code, stdout, stderr = transport_login(project_a, network, role, new, host=host, port=port)
        assert code == 0 and stdout.strip() == "1", (
            f"the active credential does not open the {name} transport: {stderr.strip()}"
        )

    for name, (host, port) in endpoints.items():
        code, _, stderr = transport_login(project_a, network, role, old, host=host, port=port)
        assert code != 0, (
            f"the pre-rotation credential still opens the {name} transport; that plane "
            "is holding a password the rotation replaced"
        )
        assert "authentication" in stderr.lower() or "password" in stderr.lower(), (
            f"the {name} transport refused the old credential for some reason other than "
            f"the credential: {stderr.strip()}"
        )
