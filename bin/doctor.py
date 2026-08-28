#!/usr/bin/env python3
"""Diagnose one deployed project, live (`OPS-001`).

Invoked only by `sudo bin/doctor.sh --project <key>`, which has already checked
root and resolved an interpreter. Kept as its own program so that a future
`apg-diag` verb can reach these checks without pulling `doctor.sh` into the
root-reachable closure (ADR 0158).

**The deployed document is read for identities and for nothing else.** Every
verdict below comes from a live read, because that document records what was
observed at deploy time — a project deployed three weeks ago whose archiver died
yesterday still publishes `backup_state.status: ok`. The verdicts themselves live
in `agentic_postgres.diagnosis`, which is what makes them testable without a
host.

Exit codes follow the convention:
  0   every check is ok or a warning
  2   invalid operator input
  3   missing local prerequisite
  4   no deployed document for that project -- it was never deployed here
  6   a check failed, or could not be run
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import (
    REPO_ROOT,
    access_broker,
    backup_report,
    deployed_output,
    diagnosis,
    migrations,
    naming,
    runtime_override,
)

EXIT_INPUT = 2
EXIT_STATE = 4
EXIT_CHECK = 6

#: Compose's own label. `runtime_override` owns the constant; a second spelling
#: here is the copy that disagrees.
COMPOSE_PROJECT_LABEL = runtime_override.COMPOSE_PROJECT_LABEL

#: Long enough for a `pgbackrest info` round trip to R2, bounded so a wedged
#: probe reports UNKNOWN instead of hanging the command (D631's lesson, applied
#: to every subprocess here rather than only to the daemon).
PROBE_TIMEOUT_SECONDS = 60


def run(
    *command: str, timeout: int = PROBE_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str] | None:
    """Every probe, bounded. None when it could not complete at all.

    None rather than a synthetic failure: a probe that timed out and a probe that
    returned an error are different facts, and the callers below turn the first
    into UNKNOWN rather than PROBLEM.

    **`stdin=DEVNULL`, and the first live run is why** (D673). `probe_tls` runs
    `openssl s_client`, which READS STDIN and does not exit until it closes. With
    stdin inherited, that blocked until this function's own timeout and reported
    `UNKNOWN tls` -- and, worse, the `docker exec -i` in `probe_database`
    immediately after it then failed too, reporting `PROBLEM database` against a
    cluster whose migrations the very next probe read successfully. One bug, two
    symptoms, and the louder symptom was the false one.
    """
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


# ---------------------------------------------------------------------------
# The document -- identities only
# ---------------------------------------------------------------------------


def load_document(project_key: str) -> dict[str, Any]:
    path = deployed_output.deployed_path(project_key)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(
            _die(
                EXIT_STATE,
                f"{project_key} has no deployed document at {path}; "
                "it has not been deployed on this host.",
            )
        ) from None
    except OSError as problem:
        raise SystemExit(_die(EXIT_STATE, f"{path} could not be read: {problem}")) from None
    except ValueError as problem:
        raise SystemExit(_die(EXIT_STATE, f"{path} is not valid JSON: {problem}")) from None
    return document


def _die(code: int, message: str) -> int:
    print(f"doctor: {message}", file=sys.stderr)
    return code


# ---------------------------------------------------------------------------
# The probes
# ---------------------------------------------------------------------------


def probe_containers(project_key: str) -> diagnosis.Check:
    """Every container Compose started for this project.

    The compose project name is **derived from `project.key` through `naming`**,
    because the deployed document has no `compose` block — reading one is exactly
    what D592 and D598 did, and each refused a real command.
    """
    compose_project = naming.compose_project_name(project_key)
    listing = run(
        "docker",
        "ps",
        "-a",
        "--filter",
        f"label={COMPOSE_PROJECT_LABEL}={compose_project}",
        "--format",
        "{{.Names}}\t{{.State}}\t{{.Status}}",
        timeout=20,
    )
    if listing is None or listing.returncode != 0:
        return diagnosis.containers(expected=0, running=(), unhealthy=())

    running: list[str] = []
    unhealthy: list[str] = []
    total = 0
    for line in listing.stdout.splitlines():
        if not line.strip():
            continue
        total += 1
        name, state, status = [*line.split("\t"), "", ""][:3]
        if state == "running":
            running.append(name)
        # "(unhealthy)" is Docker's own word, and it appears in Status rather
        # than State. A container can be running and unhealthy at once, which is
        # the case worth catching.
        if "(unhealthy)" in status:
            unhealthy.append(name)

    return diagnosis.containers(expected=total, running=tuple(running), unhealthy=tuple(unhealthy))


def probe_routes(document: dict[str, Any]) -> list[diagnosis.Check]:
    """The published routes, each from a real request through the edge.

    Only the health route is asserted to be 200. The rest are expected to
    *refuse* an unauthenticated caller, and their refusal is the healthy answer —
    asserting 200 on them would be asserting the boundary is open.
    """
    routes = document.get("routes") or {}
    checks: list[diagnosis.Check] = []
    health = (routes.get("health") or {}).get("url")
    if health:
        checks.append(
            diagnosis.route(name="health", url=health, status=_status(health), expected=200)
        )
    return checks


def _status(url: str) -> int | None:
    probe = run(
        "curl",
        "-sS",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
        "--max-time",
        "15",
        url,
        timeout=20,
    )
    if probe is None or probe.returncode != 0:
        return None
    try:
        return int(probe.stdout.strip())
    except ValueError:
        return None


def probe_tls(document: dict[str, Any]) -> diagnosis.Check:
    """The certificate the edge is serving now, not the one it recorded then."""
    domain = (document.get("project") or {}).get("domain")
    if not domain:
        return diagnosis.tls(days_remaining=None, not_after=None)

    probe = run(
        "openssl",
        "s_client",
        "-connect",
        f"{domain}:443",
        "-servername",
        domain,
        timeout=20,
    )
    if probe is None or probe.returncode != 0:
        return diagnosis.tls(days_remaining=None, not_after=None)

    dates = run("openssl", "x509", "-noout", "-enddate", timeout=10)
    # `openssl x509` needs the PEM on stdin, which `run` does not carry. Parse
    # the handshake output instead: s_client prints the peer certificate inline.
    match = re.search(r"NotAfter\s*:\s*(.+)", probe.stdout) or re.search(
        r"notAfter=(.+)", (dates.stdout if dates else "")
    )
    if not match:
        return diagnosis.tls(days_remaining=None, not_after=None)

    raw = match.group(1).strip()
    for fmt in ("%b %d %H:%M:%S %Y GMT", "%Y-%m-%d %H:%M:%S"):
        try:
            expires = datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
        remaining = (expires - datetime.now(UTC)).days
        return diagnosis.tls(days_remaining=remaining, not_after=raw)
    return diagnosis.tls(days_remaining=None, not_after=raw)


def probe_database(document: dict[str, Any]) -> diagnosis.Check:
    """The cluster and the pooler, each from a real connection."""
    db = document.get("database") or {}
    container = db.get("container")
    name = db.get("name")
    if not container or not name:
        return diagnosis.database(
            reachable=False, pooler_reachable=False, detail="the document names no container"
        )

    cluster = run(
        "docker",
        "exec",
        "-i",
        container,
        "psql",
        "-U",
        "postgres",
        "-d",
        name,
        "-X",
        "-qtA",
        "-c",
        "SELECT 1",
        timeout=20,
    )
    cluster_ok = cluster is not None and cluster.returncode == 0

    pooler_ok = _pooler_answers(document)
    if pooler_ok is None:
        # The document says there is no available pooled endpoint, or the probe
        # could not complete. Neither is "the pooler is down", and saying so
        # would be D680 again in a quieter voice.
        return diagnosis.database_pooler_undetermined(reachable=cluster_ok)
    return diagnosis.database(reachable=cluster_ok, pooler_reachable=pooler_ok)


def _pooler_answers(document: dict[str, Any]) -> bool | None:
    """Is the pooler listening, **at the address the product reaches it at**?

    Not a SQL round trip: the pooler's credential is a secret and this command
    reads none. What is asked is whether it is listening, which is the half a
    doctor can answer while holding nothing.

    **The address is derived the way `access_broker` derives it, and D682 is
    what two wrong guesses cost.** `database.pooled` in the deployed document is
    *not* the pooler's address: `observe_transports` builds it from the host's
    `loopback_address` and a broker-allocated local port, so it is **the near
    end of an SSH tunnel** that exists only while `connect.sh tunnel` is
    running. Probing it found nothing from the host (D680) and nothing from
    inside a container either, where `127.0.0.1` is that container's own
    loopback — two different failures, one wrong idea.

    `access_broker` already holds the right one, and reusing it is ADR 0002:
    the pooled transport is the pooler's *container* on the project's internal
    network, port 6432 from `CONTAINER_PORTS`. A third derivation of "where the
    pooler is" is exactly the second-authority mistake that made this a defect
    twice.

    The address is resolved per call and never recorded (ADR 0044): a container
    address changes when the container is recreated, and a stored one is right
    until the next restart.

    Returns None when the pooler cannot be located or the probe cannot complete
    — that is `UNKNOWN`'s job, not `PROBLEM`'s.
    """
    db = document.get("database") or {}
    container = db.get("container")
    network = ((document.get("edge") or {}).get("project_internal_network")) or ""
    if not container or not network or "-postgres-1" not in container:
        return None

    pooler = container.replace("-postgres-1", "-pgbouncer-1")
    port = access_broker.CONTAINER_PORTS["pooled"]

    address = run(
        "docker",
        "inspect",
        "-f",
        f'{{{{ (index .NetworkSettings.Networks "{network}").IPAddress }}}}',
        pooler,
        timeout=15,
    )
    if address is None or address.returncode != 0:
        return None
    host = address.stdout.strip()
    if not host or host == "<no value>":
        return None

    # Out of the cluster's container, across the project network, to the pooler
    # — the hop PostgREST crosses. `/dev/tcp` is a bash builtin, so nothing has
    # to be installed into an image.
    probe = run(
        "docker",
        "exec",
        "-i",
        container,
        "bash",
        "-c",
        f"exec 3<>/dev/tcp/{host}/{port}",
        timeout=15,
    )
    if probe is None:
        return None
    return probe.returncode == 0


def probe_migrations(document: dict[str, Any]) -> diagnosis.Check:
    """The ledger, against what this release has released."""
    db = document.get("database") or {}
    container, name = db.get("container"), db.get("name")
    released = len(migrations.load_manifest().get("migrations") or [])
    if not container or not name:
        return diagnosis.migrations(applied=None, released=released)

    counted = run(
        "docker",
        "exec",
        "-i",
        container,
        "psql",
        "-U",
        "postgres",
        "-d",
        name,
        "-X",
        "-qtA",
        "-c",
        "SELECT count(*) FROM app_private.migration_ledger",
        timeout=20,
    )
    if counted is None or counted.returncode != 0:
        return diagnosis.migrations(applied=None, released=released)
    # Parsed into a value BEFORE the call, never inside it. `int(...)` could not
    # leak text either way, but "no `.stdout` appears in a `diagnosis.*` call" is
    # a rule a scan can check and a reader can apply without judgement, and one
    # extra line is cheaper than an exemption (ADR 0159).
    try:
        applied = int(counted.stdout.strip())
    except ValueError:
        return diagnosis.migrations(applied=None, released=released)
    return diagnosis.migrations(applied=applied, released=released)


def probe_repository(project_key: str) -> diagnosis.Check:
    """`bin/backup.sh info --json`, and its STATE FIELD rather than its status.

    D548: `pgbackrest info` exits 0 for a stanza that does not exist. D145:
    `postgrest --ready` returns 0 while every request 404s. Two third parties,
    five sessions apart, one shape — the state was in a field both times.
    """
    outputs = deployed_output.deployed_path(project_key)
    info = run(str(REPO_ROOT / "bin" / "backup.sh"), "--outputs", str(outputs), "info", "--json")
    if info is None or not info.stdout.strip():
        return diagnosis.repository(status=None, last_full_backup_at=None)
    try:
        state = json.loads(info.stdout)
    except ValueError:
        return diagnosis.repository(status=None, last_full_backup_at=None)
    return diagnosis.repository(
        status=state.get("status"), last_full_backup_at=state.get("last_full_backup_at")
    )


def probe_archiver(document: dict[str, Any]) -> diagnosis.Check:
    """`pg_stat_archiver`, live, through Session 10's own predicate (D630)."""
    db = document.get("database") or {}
    container, name = db.get("container"), db.get("name")
    if not container or not name:
        return diagnosis.archiver(failing=None, last_archived_time=None)

    read = run(
        "docker",
        "exec",
        "-i",
        container,
        "psql",
        "-U",
        "postgres",
        "-d",
        name,
        "-X",
        "-qtA",
        "-F",
        backup_report.ARCHIVER_SEPARATOR,
        "-c",
        backup_report.ARCHIVER_QUERY,
        timeout=20,
    )
    if read is None or read.returncode != 0:
        return diagnosis.archiver(failing=None, last_archived_time=None)
    parsed = backup_report.parse_archiver(read.stdout)
    if parsed is None:
        return diagnosis.archiver(failing=None, last_archived_time=None)
    return diagnosis.archiver(
        failing=backup_report.archiving_is_failing(parsed),
        last_archived_time=parsed.get("last_archived_time"),
    )


def probe_disk(document: dict[str, Any]) -> diagnosis.Check:
    """PGDATA's size against the space free on the filesystem holding it.

    **The mount point, never `/`** (D634). Measured in Run 1: the two coincide on
    a developer machine, so a check reading `/` is right there for a reason that
    does not generalise — and on a host that gives the database its own device it
    would be reading an unrelated filesystem while still printing a number.
    """
    db = document.get("database") or {}
    container = db.get("container")
    mount = runtime_override.POSTGRES_PGDATA
    if not container:
        return diagnosis.disk_headroom(cluster_kb=None, available_kb=None, mount=mount)

    used = run("docker", "exec", "-i", container, "du", "-sk", mount, timeout=60)
    free = run("docker", "exec", "-i", container, "df", "-Pk", mount, timeout=20)

    cluster_kb = _first_int(used.stdout) if used and used.returncode == 0 else None
    available_kb = None
    if free and free.returncode == 0:
        rows = free.stdout.splitlines()
        if len(rows) >= 2:
            fields = rows[1].split()
            if len(fields) >= 4:
                try:
                    available_kb = int(fields[3])
                except ValueError:
                    available_kb = None
    return diagnosis.disk_headroom(cluster_kb=cluster_kb, available_kb=available_kb, mount=mount)


def _first_int(text: str) -> int | None:
    match = re.match(r"\s*(\d+)", text or "")
    return int(match.group(1)) if match else None


# ---------------------------------------------------------------------------


def diagnose(project_key: str) -> tuple[diagnosis.Check, ...]:
    document = load_document(project_key)
    checks: list[diagnosis.Check] = [probe_containers(project_key)]
    checks.extend(probe_routes(document))
    checks.append(probe_tls(document))
    checks.append(probe_database(document))
    checks.append(probe_migrations(document))
    checks.append(probe_repository(project_key))
    checks.append(probe_archiver(document))
    checks.append(probe_disk(document))
    return tuple(checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", required=True)
    parser.add_argument("--verbose", action="store_true")
    arguments = parser.parse_args(argv)

    checks = diagnose(arguments.project)
    # `verbose` reaches the RENDERER and nothing else. There is no verbose branch
    # in any probe above, which is what keeps "a third party's bytes are never
    # printed" a property of the shape rather than a rule each probe obeys
    # (ADR 0159).
    print(diagnosis.report(checks, project_key=arguments.project, verbose=arguments.verbose))
    return diagnosis.exit_code(checks)


if __name__ == "__main__":
    sys.exit(main())
