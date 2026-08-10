"""Two transports, four clients, and a pool that actually multiplexes.

Replaces the Session 4 placeholders in ``tests/integration/test_future_database_clients.py``
and the port-allocation placeholder in ``tests/contract/test_future_deployment.py``.

**Every test here is deselected in an offline gate**, and that is the risk this
module carries rather than a convenience. D70 is what it costs when it goes
unmanaged: ``DEP-ISO-003`` read as proved for two runs behind six node IDs, and
not one of them presented a credential to anything. So every test below states,
in its own docstring, **what would have to break for it to go red** — and where a
property could be satisfied by an absence, both halves are asserted.

The pool tests are the ones to read closely. "The pooler is configured for
transaction pooling" is a fact about a file; "the pooler multiplexes" is a fact
about server connections under load; and "a prepared statement survives a
backend change" is only a claim at all if the backend is *observed* to change.
Run 1 measured what the locked image can do. These measure what the deployed
pooler does.
"""

from __future__ import annotations

import json
import socket
import subprocess
from typing import Any

import pytest

# ruff: noqa: S608
#
# The two catalog queries below interpolate the disposable schema name, which is
# read back out of the project's own rendered compose.env and asserted not to be
# one of the protected schemas before it is used. It is not operator input, and
# `psql -c` offers no bind parameter -- the same reason
# `tests/deployment/test_session3_isolation.py` suppresses this rule per module.

pytestmark = [
    pytest.mark.p0,
    pytest.mark.deployment,
    pytest.mark.database,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]


def key(document: dict[str, Any]) -> str:
    return document["project"]["key"]


# ---------------------------------------------------------------------------
# The client compatibility fixtures (DBX-001..004)
#
# Each fixture is a program that exits non-zero on an unexpected count, so the
# assertion here is its exit status and the evidence is its output. Restating
# its checks would be a second, weaker copy of them.
# ---------------------------------------------------------------------------


def assert_fixture_passed(result: tuple[int, str, str], service: str) -> str:
    status, out, err = result
    assert status == 0, f"{service} exited {status}\nstdout:\n{out}\nstderr:\n{err}"
    assert "every check passed" in out, f"{service} exited 0 without reporting its checks:\n{out}"
    return out


def test_psql_works_through_both_transports(project_a, run_client_fixture) -> None:
    """DBX-003. The client with no framework between it and the boundary.

    Goes red if: either transport stops authenticating; the pooler drops
    ``application_name``; a row written under one claim becomes visible under
    another; a transaction with no claim starts returning rows; or ``app.notes``
    becomes readable through the runtime credential. The fixture runs the same
    six checks over each transport in turn, so a failure names which one.
    """
    output = assert_fixture_passed(run_client_fixture(key(project_a), "client-psql"), "client-psql")
    assert "both transports passed" in output
    assert "over the pooled transport" in output
    assert "over the direct transport" in output


@pytest.mark.parametrize("service", ["client-node-pg", "client-psycopg"])
def test_node_and_python_drivers_work_through_the_pooler(
    project_a, run_client_fixture, service: str
) -> None:
    """DBX-004. Two drivers that are not libpq's own client.

    Parametrized rather than looped so a failure names the driver: node-postgres
    reimplements the wire protocol and Psycopg 3 wraps libpq, and the failures
    that distinguish them are the interesting ones.

    Goes red if: either driver stops resolving its credential from
    ``PGPASSFILE`` (node-postgres does it through ``pgpass``, which is why that
    package is pinned in the committed lock); either stops sending parameters
    server-side; or the pooler's transaction mode breaks the explicit
    transactions the claims are set in.
    """
    output = assert_fixture_passed(run_client_fixture(key(project_a), service), service)
    assert "over the pooled transport" in output


def test_prisma_client_works_through_the_pooler(project_a, run_client_fixture) -> None:
    """DBX-002. Prisma Client through PgBouncer, with prepared statements ON.

    Goes red if: ``max_prepared_statements`` drops to zero, which makes the
    repeated named statement fail with "prepared statement already exists";
    Prisma's interactive ``$transaction`` stops holding one server connection
    across the ``SET LOCAL`` and the query it applies to; or row isolation
    stops holding through the ORM.

    It would NOT go red if somebody added ``?pgbouncer=true`` — it would go
    green against the fallback path. That is why the fixture refuses the flag
    rather than merely not setting it, and why
    ``tests/contract/test_client_fixtures.py`` asserts the refusal offline.
    """
    output = assert_fixture_passed(
        run_client_fixture(key(project_a), "client-prisma", "client"), "client-prisma client"
    )
    assert "a named prepared statement is reusable" in output


def test_prisma_migrate_runs_through_the_direct_transport(
    project_a, run_client_fixture, sh, as_root
) -> None:
    """DBX-001. Prisma Migrate through ``directUrl``, into a disposable schema.

    The schema is created and dropped through the container-local privileged
    socket (plan §4.4), never through a TCP endpoint: ``migration_user`` holds
    no database ``CREATE``, which is exactly the property that makes the
    privileged half necessary. The drop targets the recorded name and nothing
    else, and it runs whether the migration passed or failed — a cleanup failure
    is a gate failure, not a warning.

    Goes red if: ``directUrl`` stops being honoured and the migration arrives
    through the pooler, where DDL and advisory locks do not behave; the
    migration credential stops authenticating on the direct transport; or the
    migration applies and leaves no ``fixture_rows`` table in the schema it
    claimed to create in.
    """
    del as_root
    document = project_a
    project_key = key(document)
    container = document["database"]["container"]
    schema = _disposable_schema(project_key, sh)
    migration_role = document["database"]["roles"]["migration_user"]
    assert schema not in ("api", "app", "app_private", "extensions", "public"), (
        f"the fixture schema resolves to the protected schema {schema}"
    )

    _psql_local(sh, container, document, f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    _psql_local(sh, container, document, f'CREATE SCHEMA "{schema}"')
    _psql_local(
        sh,
        container,
        document,
        f'GRANT USAGE, CREATE ON SCHEMA "{schema}" TO "{migration_role}"',
    )
    try:
        assert_fixture_passed(
            run_client_fixture(project_key, "client-prisma", "migrate"), "client-prisma migrate"
        )
        landed = _psql_local(
            sh,
            container,
            document,
            "SELECT count(*) FROM pg_tables "
            f"WHERE schemaname = '{schema}' AND tablename = 'fixture_rows'",
        )
        assert landed.strip() == "1", (
            f"Prisma Migrate reported success and created no fixture_rows in {schema}"
        )
    finally:
        _psql_local(sh, container, document, f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')

    remaining = _psql_local(
        sh, container, document, f"SELECT count(*) FROM pg_namespace WHERE nspname = '{schema}'"
    )
    assert remaining.strip() == "0", f"the disposable schema {schema} survived the run"


def _disposable_schema(project_key: str, sh) -> str:
    """The name recorded in the project's rendered environment.

    Read back rather than restated. D109: the name is a derived constant because
    a per-run value cannot reach a required Compose interpolation, and what §4.4
    actually buys is kept only if the drop targets *the recorded name* rather
    than one this test also knows how to spell.
    """
    for line in sh("cat", f"/var/lib/agentic-postgres/rendered/{project_key}/compose.env").split(
        "\n"
    ):
        name, _, value = line.partition("=")
        if name.strip() == "APG_DISPOSABLE_SCHEMA":
            return value.strip()
    pytest.fail(f"{project_key}'s compose.env records no APG_DISPOSABLE_SCHEMA")


def _psql_local(sh, container: str, document: dict[str, Any], statement: str) -> str:
    """A privileged statement over the container-local Unix socket.

    The socket, not 127.0.0.1: both are trusted by the image's ``pg_hba.conf``
    (D74), and naming the socket says which authority is being used rather than
    relying on a trust line that a later session may narrow.
    """
    return sh(
        "docker",
        "exec",
        container,
        "psql",
        "-U",
        "postgres",
        "-d",
        document["database"]["name"],
        "-v",
        "ON_ERROR_STOP=1",
        "-X",
        "-qtA",
        "-c",
        statement,
    )


# ---------------------------------------------------------------------------
# Pool behaviour (DBX-POOL-001..003)
# ---------------------------------------------------------------------------


def test_the_pooler_runs_transaction_mode_with_bounded_limits(project_a, pool_setting) -> None:
    """DBX-POOL-001. Read out of the running daemon, not out of the rendered ini.

    A rendered file nobody loaded is the defect this project keeps producing.
    ``SHOW CONFIG`` is answered by the process that is serving traffic.

    Goes red if: the pool mode is changed to ``session`` — which is how a
    failing client test gets "fixed" and which the plan forbids in so many
    words; ``max_prepared_statements`` drops to zero, taking DBX-POOL-003 and
    Prisma with it; or any of the three bounds becomes unbounded, which turns a
    saturated pool from a queue into a connection storm against the cluster.
    """
    project_key = key(project_a)
    assert pool_setting(project_key, "pool_mode") == "transaction"

    for setting in ("default_pool_size", "max_client_conn", "max_prepared_statements"):
        value = int(pool_setting(project_key, setting))
        assert value > 0, f"{setting} is {value}; an unbounded pool is not a pool"

    # A queue with no timeout is a client that waits forever and a symptom that
    # looks like the database being down.
    assert int(pool_setting(project_key, "query_wait_timeout")) > 0

    # More clients than servers, or there is nothing to multiplex.
    assert int(pool_setting(project_key, "max_client_conn")) > int(
        pool_setting(project_key, "default_pool_size")
    )


def test_more_clients_than_the_pool_stay_inside_the_server_budget(
    project_a, pool_setting, materialized_secret, client_image
) -> None:
    """DBX-POOL-002. Multiplexing observed, not assumed.

    Runs ``default_pool_size + 4`` concurrent clients, each doing a short
    transaction, and reads the server-side connection count for the application
    role *while they are running*. Without pooling that count equals the client
    count; with transaction pooling it stays at or below the pool size.

    Goes red if: the pooler stops multiplexing (each client gets its own server
    connection, so the count exceeds the pool size); or the clients stop
    completing, which is the other way a "pool" can hold the count down.
    **Both are asserted** — a test that only checked the ceiling would pass with
    every client hung.
    """
    document = project_a
    project_key = key(document)
    pool_size = int(pool_setting(project_key, "default_pool_size"))
    clients = pool_size + 4

    password = materialized_secret(project_key, "pgbouncer", "app_runtime_password")
    result = _run_python_probe(
        document,
        client_image(project_key, "client-psycopg"),
        _CONCURRENCY_PROBE,
        password,
        {"APG_CLIENTS": str(clients), "APG_POOL_SIZE": str(pool_size)},
    )
    assert result["completed"] == clients, (
        f"{result['completed']} of {clients} clients completed; a pool that holds the "
        "server count down by hanging its clients is not multiplexing"
    )
    assert result["peak_server_connections"] <= pool_size, (
        f"{result['peak_server_connections']} server connections for {clients} clients, "
        f"with default_pool_size {pool_size}: the pooler is not multiplexing"
    )


def test_a_named_prepared_statement_survives_an_observed_backend_change(
    project_a, pool_setting, materialized_secret, client_image
) -> None:
    """DBX-POOL-003. The backend change is measured, not assumed.

    One client session prepares a named statement, then executes it in a loop of
    separate transactions while other clients occupy the pool, until
    ``pg_backend_pid()`` comes back *different*. Only then is the statement
    executed again, and the assertion is that it still works.

    Goes red if: ``max_prepared_statements`` is zero, in which case the execute
    after the change fails with "prepared statement does not exist"; or the
    backend never changes within the bound, which is reported as a failure
    rather than passed as a success — a run where the client happened to keep
    one server proves nothing, and calling it green is exactly the defect this
    docstring exists to prevent.
    """
    document = project_a
    project_key = key(document)
    assert int(pool_setting(project_key, "max_prepared_statements")) > 0

    password = materialized_secret(project_key, "pgbouncer", "app_runtime_password")
    result = _run_python_probe(
        document,
        client_image(project_key, "client-psycopg"),
        _PREPARED_STATEMENT_PROBE,
        password,
        {"APG_POOL_SIZE": pool_setting(project_key, "default_pool_size")},
    )
    assert result["backend_changed"], (
        "the backend never changed within the bound, so nothing was proved about a "
        f"statement surviving one (first pid {result['first_pid']}, "
        f"{result['attempts']} attempts)"
    )
    assert result["reused_after_change"], (
        "the named statement was unusable after the backend changed, which is what "
        "max_prepared_statements = 0 looks like"
    )


# ---------------------------------------------------------------------------
# Port allocation (DBX-PORT-001)
# ---------------------------------------------------------------------------


def test_the_allocation_is_active_and_keyed_by_the_volumes_identity(
    project_a, allocation_for, sh
) -> None:
    """DBX-PORT-001. The key is the data's identity, not the configuration's.

    ``app_private.project_identity.instance_uuid`` is generated once on the first
    bootstrap of an empty volume and recovered on every bootstrap since, so a
    restored volume brings its ports with it. This reads the UUID out of the
    running cluster and asserts the registry recorded that one.

    Goes red if: the allocation is keyed by anything a redeploy regenerates, in
    which case the UUID in the registry stops matching the cluster's; or the
    allocation is still ``reserved``, which means the endpoint checks never
    passed and nothing adopted the ports — a deploy that crashed after
    publishing looks identical from the outside.
    """
    document = project_a
    allocation = allocation_for(key(document))

    assert allocation["state"] == "active", (
        f"the allocation is {allocation['state']}; a reservation nothing serves is what a "
        "crashed first deploy leaves behind"
    )
    assert allocation["pooled_port"] != allocation["direct_port"], "one port for two listeners"

    live = _psql_local(
        sh,
        document["database"]["container"],
        document,
        "SELECT instance_uuid::text FROM app_private.project_identity",
    ).strip()
    assert live, "the cluster records no instance_uuid"
    assert allocation["instance_uuid"] == live, (
        f"the registry records {allocation['instance_uuid']} and the volume carries {live}; "
        "the allocation is keyed by something other than the data's identity"
    )


def test_the_published_ports_are_the_ones_the_registry_allocated(
    project_a, allocation_for, sh
) -> None:
    """DBX-PORT-001, the other half: the registry, the host and the world agree.

    **Not measured with `ss`, and that is the point** (D114). `daemon.json` sets
    ``userland-proxy: false``, so Docker implements a publication as an iptables
    DNAT rule and **no host process listens on the published port**. The first
    version of this test asserted a listening socket, which this host's Docker
    configuration never creates — a check that could not pass, which is ADR
    0035's defect with its sign flipped. It would have reported a correct
    publication as broken on every run.

    So the two things that are actually true of a publication are asserted
    instead: Docker binds the container port to the allocated host port **on a
    loopback address**, and a TCP connect to that address completes.

    Goes red if: a publication is written for a port the registry does not hold;
    the registry holds a port nothing answers on; or — the one that matters —
    ``HostIp`` is anything but loopback, which is the difference between a
    developer's tunnel and a database on the internet.
    """
    document = project_a
    allocation = allocation_for(key(document))
    pooled_container = document["database"]["container"].replace("-postgres-1", "-pgbouncer-1")

    for transport, container, container_port, port in (
        ("pooled", pooled_container, INTERNAL_POOL_PORT, allocation["pooled_port"]),
        ("direct", document["database"]["container"], 5432, allocation["direct_port"]),
    ):
        bindings = json.loads(
            sh("docker", "inspect", "-f", "{{json .HostConfig.PortBindings}}", container)
        )
        published = bindings.get(f"{container_port}/tcp")
        assert published, (
            f"{container} publishes nothing on {container_port}; the registry allocates "
            f"{port} for the {transport} transport"
        )
        assert len(published) == 1, f"{transport} is published {len(published)} times: {published}"
        assert published[0]["HostPort"] == str(port), (
            f"{transport} is published on {published[0]['HostPort']}, and the registry "
            f"allocates {port}. A saved tunnel then reaches something other than it names"
        )
        assert _is_loopback(published[0]["HostIp"]), (
            f"{transport} is published on {published[0]['HostIp']}:{port}, which is not a "
            "loopback address (ADR 0040)"
        )

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(5.0)
            assert probe.connect_ex(("127.0.0.1", port)) == 0, (
                f"nothing answers on 127.0.0.1:{port}, which the registry allocates for "
                f"the {transport} transport"
            )


def _is_loopback(address: str) -> bool:
    """A real address comparison. `1270.0.0.1` starts with `127.` and is not."""
    from ipaddress import ip_address

    try:
        return ip_address(address).is_loopback
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Probes run inside a container on the project's own network
# ---------------------------------------------------------------------------

#: Both probes below take the credential on **stdin** and read it into a
#: variable inside the container. It is never an argument to ``docker``, never in
#: the container's declared environment, and therefore appears in no process
#: listing, no ``docker inspect`` and no log -- the rule ``pg_login`` follows.
_CONCURRENCY_PROBE = r"""
import json, os, sys, threading
import psycopg

password = sys.stdin.read().rstrip("\n")
clients = int(os.environ["APG_CLIENTS"])
conninfo = (
    f"host={os.environ['APG_POOL_HOST']} port={os.environ['APG_POOL_PORT']} "
    f"user={os.environ['APG_ROLE']} dbname={os.environ['APG_DATABASE']} "
    "sslmode=disable application_name=apg-pool-concurrency"
)

start = threading.Barrier(clients + 1)
done = threading.Event()
completed = []
peak = [0]

def client(index):
    with psycopg.connect(conninfo, password=password) as connection:
        start.wait()
        while not done.is_set():
            with connection.transaction():
                connection.execute("SELECT pg_sleep(0.05)")
        completed.append(index)

workers = [threading.Thread(target=client, args=(i,), daemon=True) for i in range(clients)]
for worker in workers:
    worker.start()
start.wait()

# Counted from the SERVER side, as the cluster sees it. The pooler's own SHOW
# POOLS would be the pooler reporting on itself.
with psycopg.connect(conninfo, password=password) as observer:
    for _ in range(40):
        count = observer.execute(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE usename = %s AND application_name = 'apg-pool-concurrency'",
            (os.environ["APG_ROLE"],),
        ).fetchone()[0]
        peak[0] = max(peak[0], count)

done.set()
for worker in workers:
    worker.join(timeout=30)

print(json.dumps({"completed": len(completed), "peak_server_connections": peak[0]}))
"""

_PREPARED_STATEMENT_PROBE = r"""
import json, os, sys, threading, time
import psycopg

password = sys.stdin.read().rstrip("\n")
pool_size = int(os.environ["APG_POOL_SIZE"])
conninfo = (
    f"host={os.environ['APG_POOL_HOST']} port={os.environ['APG_POOL_PORT']} "
    f"user={os.environ['APG_ROLE']} dbname={os.environ['APG_DATABASE']} "
    "sslmode=disable application_name=apg-prepared-probe"
)

# Occupy the pool so that releasing a server at COMMIT gives it to somebody
# else, which is what makes the next transaction land on a different backend.
done = threading.Event()

def occupier():
    with psycopg.connect(conninfo, password=password) as connection:
        while not done.is_set():
            with connection.transaction():
                connection.execute("SELECT pg_sleep(0.05)")

threads = [threading.Thread(target=occupier, daemon=True) for _ in range(pool_size)]
for thread in threads:
    thread.start()
time.sleep(1)

result = {"backend_changed": False, "reused_after_change": False, "attempts": 0}
with psycopg.connect(conninfo, password=password, autocommit=False) as session:
    with session.transaction():
        session.execute("PREPARE apg_probe AS SELECT pg_backend_pid()")
        first = session.execute("EXECUTE apg_probe").fetchone()[0]
    result["first_pid"] = first

    for attempt in range(1, 201):
        result["attempts"] = attempt
        with session.transaction():
            current = session.execute("EXECUTE apg_probe").fetchone()[0]
        if current != first:
            result["backend_changed"] = True
            result["changed_pid"] = current
            with session.transaction():
                again = session.execute("EXECUTE apg_probe").fetchone()[0]
            result["reused_after_change"] = isinstance(again, int)
            break

done.set()
for thread in threads:
    thread.join(timeout=30)

print(json.dumps(result))
"""


#: The pooler's port on the project network, which is NOT its published host
#: port. ADR 0042 allocates the host port from a host-wide range, so the two
#: numbers differ by construction — and both are "the pooled port" in
#: conversation. A probe on the internal network that used the host number would
#: simply fail to connect, which is a confusing way to learn this.
INTERNAL_POOL_PORT = 6432


def _run_python_probe(
    document: dict[str, Any],
    image: str,
    script: str,
    password: str,
    environment: dict[str, str],
) -> dict[str, Any]:
    """Run a Psycopg probe against the pooler from the project's own network.

    The image is the ``client-psycopg`` fixture's own, so the driver under the
    probe is the one its committed hash-locked ``requirements.txt`` pins rather
    than whatever the index has today. The script arrives as an argument and the
    credential on **stdin**: the script is not secret, the password is, and only
    one of them may appear in a process listing.
    """
    arguments = [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--network",
        document["edge"]["project_internal_network"],
        "--env",
        "APG_POOL_HOST=pgbouncer",
        "--env",
        f"APG_POOL_PORT={INTERNAL_POOL_PORT}",
        "--env",
        f"APG_ROLE={document['database']['access_profiles']['runtime_pooled']['role']}",
        "--env",
        f"APG_DATABASE={document['database']['name']}",
    ]
    for name, value in sorted(environment.items()):
        arguments += ["--env", f"{name}={value}"]
    arguments += ["--entrypoint", "python", image, "-c", script]

    result = subprocess.run(
        arguments, input=password, capture_output=True, text=True, check=False, timeout=600
    )
    assert result.returncode == 0, (
        f"the probe exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return json.loads(result.stdout.splitlines()[-1])
