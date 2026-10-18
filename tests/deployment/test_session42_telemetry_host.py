"""Session 42's host proofs: the telemetry plane on the machine; `pg_stat_statements` everywhere.

`INS-HOST-001` (claim `telemetry_live`) and `INS-HOST-002` (claim `pgss_live`),
run by the sweep as root after Sheet T1 installed the plane and every project
moved to 1.20.0 (ADR 0277, ADR 0278, D2586). The plane: its four containers
running at the limits the release's compose file declares, its charge in the
state file equal to their sum and read into the node's committed figure, no
public listener added, HyperDX's session secret nowhere in its environment, and
a line sent to a project's collector CLAIMING another project stored as the
collector's own. The databases: every project's loads the extension with the
release's five settings, holds it in `extensions`, and refuses it to every role
but the platform's. Reads only, except ONE log line sent through beta's own
collector (a marker no customer value). **None of these proofs has ever
executed.**
"""

# ruff: noqa: S608 -- every interpolated value is a uuid marker, a role or a name this module read.

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import bootstrap_statements, capacity_probe, telemetry_plane
from agentic_postgres.listeners import parse_listeners, unexpected_public_ports

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST",
        "APG_PROJECT_A_OUTPUTS",
        "APG_PROJECT_B_OUTPUTS",
        "APG_CONTROL_OUTPUTS",
        "APG_LIVE_SLOT_OUTPUTS",
        "APG_HOST_MANIFEST",
    ),
]

#: ADR 0268: the edge's three public ports and SSH; the plane publishes none.
PUBLIC_PORTS = (22, 80, 443, 5432)
PROJECTS_ROOT = Path("/etc/agentic-postgres/projects")
DOCUMENTS = ("APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS", "APG_CONTROL_OUTPUTS",
             "APG_LIVE_SLOT_OUTPUTS")  # fmt: skip


def _run(
    *command: str, timeout: int = 120, stdin: str | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(command), input=stdin, stdin=None if stdin is not None else subprocess.DEVNULL,
        capture_output=True, text=True, timeout=timeout, check=False,
    )  # fmt: skip


def _probe(*command: str, timeout: int = 60) -> subprocess.CompletedProcess | None:
    """`capacity_probe`'s runner shape (`bin/doctor.py`'s `run`): bounded, None
    when the command could not complete at all."""
    try:
        return _run(*command, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None


def _inspect(name: str) -> dict[str, Any]:
    done = _run("docker", "inspect", name)
    assert done.returncode == 0, f"{name} does not exist"
    return json.loads(done.stdout)[0]


def _container(service: str) -> str:
    return f"{telemetry_plane.COMPOSE_PROJECT}-{service}-1"


def _sql(container: str, database: str, sql: str) -> subprocess.CompletedProcess:
    return _run("docker", "exec", container, "psql", "-X", "-qtA", "-U", "postgres", "-d",
                database, "-c", sql)  # fmt: skip


def _clickhouse(query: str) -> str:
    done = _run("docker", "exec", _container("clickhouse"), "clickhouse-client", "--query", query)
    assert done.returncode == 0, done.stderr.strip()[-300:]
    return done.stdout.strip()


@pytest.fixture(scope="module")
def documents() -> list[dict[str, Any]]:
    """The four deployed documents the sweep declares, each read whole."""
    found = []
    for variable in DOCUMENTS:
        path = Path(os.environ.get(variable, ""))
        if not path.is_file():
            pytest.fail(f"{variable} points at {path}, which does not exist")
        found.append(json.loads(path.read_text(encoding="utf-8")))
    return found


@pytest.fixture(scope="module")
def model() -> dict[str, Any]:
    return yaml.safe_load(telemetry_plane.COMPOSE_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# INS-HOST-001
# ---------------------------------------------------------------------------


def test_the_plane_is_bounded_and_charged(as_root: None, model: dict[str, Any]) -> None:
    """ADR 0277 items 5-6: each of the four services runs -- healthy where it
    has a healthcheck -- with exactly the memory, process and CPU limits the
    release's compose file declares; the state file's charge is their sum; and
    the node's reading carries it as the platform's committed figure."""
    del as_root
    for service, definition in model["services"].items():
        found = _inspect(_container(service))
        assert found["State"]["Running"] is True, (service, found["State"]["Status"])
        health = (found["State"].get("Health") or {}).get("Status")
        assert health in (None, "healthy"), (service, health)
        limits = found["HostConfig"]
        assert limits["Memory"] == telemetry_plane.memory_mb(definition["mem_limit"]) * 1024 * 1024
        assert limits["PidsLimit"] == definition["pids_limit"], (service, limits["PidsLimit"])
        assert limits["NanoCpus"] == int(float(definition["cpus"]) * 1e9), (
            service,
            limits["NanoCpus"],
        )
    charge, problem = telemetry_plane.read_charge(telemetry_plane.STATE_DIRECTORY)
    assert problem is None and charge == telemetry_plane.charge_mb(model), (charge, problem)
    reading, _ = capacity_probe.read(
        Path(os.environ.get("APG_HOST_MANIFEST", "")), PROJECTS_ROOT, runner=_probe
    )
    assert reading.platform == {telemetry_plane.CHARGE_KEY: charge}, reading.platform


def test_the_listeners_did_not_change(as_root: None) -> None:
    """D2586: with the plane running, the host listens publicly on 22, 80, 443
    and 5432 and nothing else -- the plane publishes no port. The control that
    the reading sees at all: the edge's 443 is in the same output."""
    del as_root
    done = _run("ss", "-H", "-lnt")
    assert done.returncode == 0, done.stderr
    seen = {item.port for item in parse_listeners(done.stdout) if not item.is_loopback}
    assert 443 in seen, "the edge is not listening on 443: the scan read an empty world"
    assert unexpected_public_ports(done.stdout, PUBLIC_PORTS) == (), sorted(seen)
    for service in telemetry_plane.SERVICES:
        ports = _inspect(_container(service))["NetworkSettings"]["Ports"] or {}
        assert not any(ports.values()), (service, ports)


def test_the_ui_holds_no_secret_in_its_environment(as_root: None) -> None:
    """D2578, D2600: HyperDX's session secret is made once on the host and read
    from a file by its entrypoint -- its value is in none of the container's
    `Env`, its argv or its labels. Counted, never printed. The control: the
    secret file exists and is not empty, so the scan looks for something."""
    del as_root
    secret = (
        (telemetry_plane.STATE_DIRECTORY / telemetry_plane.SESSION_SECRET_FILE)
        .read_text(encoding="utf-8")
        .strip()
    )
    assert len(secret) >= 32, "the session secret file is empty or short"
    found = _inspect(_container("hyperdx"))
    config = found["Config"]
    places = [*(config.get("Env") or []), *(config.get("Cmd") or []),
              *(config.get("Entrypoint") or []), *(found.get("Args") or []),
              json.dumps(config.get("Labels") or {})]  # fmt: skip
    holding = sum(1 for place in places if secret in place)
    assert holding == 0, f"{holding} place(s) in the container's configuration hold the secret"


def test_a_forged_project_is_stamped_over(as_root: None, documents: list[dict[str, Any]]) -> None:
    """ADR 0277 item 2: a line sent to BETA's own collector whose resource
    claims `project = alpha-dev` is stored in `otel.otel_logs` as beta-dev's --
    the collector's upsert, from its render, over whatever the payload said.
    Sent from beta's own `auth` container to `metrics:4318`, the path its lines
    take; one marker line, found by its marker within 90 s."""
    del as_root
    beta = documents[1]
    key = beta["project"]["key"]
    marker = f"apg.s42.forged {uuid.uuid4()}"
    payload = {"resourceLogs": [{
        "resource": {"attributes": [
            {"key": "service.name", "value": {"stringValue": "s42-forged"}},
            {"key": "project", "value": {"stringValue": "alpha-dev"}},
        ]},
        "scopeLogs": [{"logRecords": [{"timeUnixNano": str(time.time_ns()),
                                       "body": {"stringValue": marker}}]}],
    }]}  # fmt: skip
    sender = (
        "import sys, urllib.request\n"
        "r = urllib.request.Request('http://metrics:4318/v1/logs', data=sys.stdin.buffer.read(),"
        " method='POST', headers={'Content-Type': 'application/json'})\n"
        "print(urllib.request.urlopen(r, timeout=10).status)\n"
    )
    auth = f"{beta['database']['container'].rsplit('-postgres-1', 1)[0]}-auth-1"
    done = _run("docker", "exec", "-i", auth, "python", "-c", sender, stdin=json.dumps(payload))
    assert done.returncode == 0 and done.stdout.strip() == "200", done.stderr.strip()[-300:]
    stored = ""
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline and not stored:
        stored = _clickhouse(
            "SELECT ResourceAttributes['project'] FROM otel.otel_logs "
            f"WHERE Body = '{marker}' FORMAT TSV"
        )
        if not stored:
            time.sleep(5)
    assert stored.splitlines() == [key], (stored, key)


# ---------------------------------------------------------------------------
# INS-HOST-002
# ---------------------------------------------------------------------------


def test_every_database_loads_the_extension(as_root: None, documents: list[dict[str, Any]]) -> None:
    """ADR 0278: every project's running database reads the release's five
    settings back -- the library preloaded, at most 1,000 statements, `top`
    only, utility statements and planning not tracked -- and holds the
    extension in `extensions`."""
    del as_root
    for document in documents:
        container, database = document["database"]["container"], document["database"]["name"]
        for setting in bootstrap_statements.PG_STAT_STATEMENTS_SETTINGS:
            name, value = setting.split("=", 1)
            read = _sql(container, database, f"SHOW {name}")
            assert read.returncode == 0, (container, name, read.stderr.strip())
            assert value in read.stdout.strip().split(","), (container, name, read.stdout.strip())
        schema = _sql(container, database, "SELECT extnamespace::regnamespace FROM pg_extension "
                      "WHERE extname = 'pg_stat_statements'")  # fmt: skip
        assert schema.stdout.strip() == "extensions", (container, schema.stdout.strip())


def test_the_customer_role_cannot_read_it(as_root: None, documents: list[dict[str, Any]]) -> None:
    """ADR 0278, THR-INS-LEAK: the views and functions are revoked from
    `PUBLIC`, so on every database the request roles cannot read them, and on
    the kept slot neither can the customer's own two roles; the platform's
    superuser can (the control: the view answers at all)."""
    del as_root
    for document in documents:
        container, database = document["database"]["container"], document["database"]["name"]
        roles = document["database"]["roles"]
        wanted = [
            roles[r]
            for r in ("anon", "authenticated", "customer_app", "customer_admin")
            if r in roles
        ]
        assert roles.get("anon") and roles.get("authenticated"), (container, sorted(roles))
        control = _sql(
            container, database, "SELECT count(*) >= 0 FROM extensions.pg_stat_statements"
        )
        assert control.stdout.strip() == "t", (container, control.stderr.strip())
        for role in wanted:
            for table in bootstrap_statements.PG_STAT_STATEMENTS_TABLES:
                held = _sql(
                    container,
                    database,
                    f"SELECT has_table_privilege('{role}', '{table}', 'SELECT')",
                )
                assert held.stdout.strip() == "f", (container, role, table)
            for function in bootstrap_statements.PG_STAT_STATEMENTS_FUNCTIONS:
                held = _sql(container, database,
                            f"SELECT has_function_privilege('{role}', '{function}', "
                            "'EXECUTE')")  # fmt: skip
                assert held.stdout.strip() == "f", (container, role, function)
    slot = documents[3]["database"]["roles"]
    assert "customer_app" in slot and "customer_admin" in slot, sorted(slot)
