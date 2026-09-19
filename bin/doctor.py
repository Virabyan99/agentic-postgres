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
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import (
    REPO_ROOT,
    access_broker,
    agent_plane,
    backup_report,
    capacity_reading,
    config,
    deployed_output,
    diagnosis,
    fleet,
    host_config,
    migrations,
    naming,
    runtime_override,
)

EXIT_INPUT = 2
EXIT_STATE = 4
EXIT_CHECK = 6

#: The reading's stand-in key for "the project root itself could not be read".
#: A slash cannot appear in a project key, so this can never be confused with
#: a real project whose document is missing.
PROJECT_ROOT_UNREADABLE = "<project state root>"

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


def load_document(
    project_key: str, root: Path = deployed_output.PROJECT_STATE_ROOT
) -> dict[str, Any]:
    path = deployed_output.deployed_path(project_key, root=root)
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


def read_deployed(root: Path, key: str) -> tuple[dict[str, Any] | None, str | None]:
    """One deployed document, or the REASON it could not be read.

    The non-fatal sibling of `load_document` above, and the difference between
    them is the whole point rather than an oversight. `load_document` answers
    *diagnose THIS project*, where a missing document means the command was
    asked about something that was never deployed and should stop. This one
    answers *what has this node already committed*, where a document that
    cannot be read is one project's claim among several -- and stopping would
    turn a partial answer into no answer, while returning nothing would turn it
    into a confident wrong one.

    So the reason is carried back and `capacity_reading.decide` refuses over
    it. **On this host that is the ordinary case, not the exceptional one**:
    `/etc/agentic-postgres/projects/<key>/` is `drwx------ root root`, so every
    document is unreadable to anyone but root (D1606).

    It deliberately does NOT reuse the operator inventory command's reader of
    the same shape. Nothing in the release may name that command -- it is the
    end of a chain, never a link in one (ADR 0185, FLEET-INV-002), and the
    scan that enforces it cannot tell a mention from a use, which is why this
    paragraph does not spell the path either. What the two readers share is
    the library underneath, `deployed_path` and `validate_deployed_document`.
    What they do not share is the failure policy, which is the part that
    actually differs.
    """
    path = deployed_output.deployed_path(key, root=root)
    try:
        deployed = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "no deployed document: the directory exists and outputs.json does not"
    except OSError:
        return None, "the deployed document could not be read"
    except ValueError:
        return None, "the deployed document is not valid JSON"
    try:
        deployed_output.validate_deployed_document(deployed)
    except config.ManifestError:
        return None, "the deployed document does not validate against the outputs schema"
    return deployed, None


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
    """The ledger, against every set this project applies.

    `migrations.load_manifest()` -- the release's alone -- is what this counted
    until ADR 0198, and it is one of the eleven callers D1088 names: it meant
    *every migration this project applies* and answered *the release's*. On a
    project with a set of its own that reads as a cluster AHEAD of the release,
    which `diagnosis.migrations` reports as a warning -- a green-adjacent line
    for the one project whose tenant tables the check exists to notice.

    `sets_for` reads the DOCUMENT, so a host whose checkout does not carry the
    project's directory still counts what the deployment declared.
    """
    db = document.get("database") or {}
    container, name = db.get("container"), db.get("name")
    released = sum(
        len(migration_set.load_manifest().get("migrations") or [])
        for migration_set in migrations.sets_for(document)
    )
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


def probe_repository(
    project_key: str, root: Path = deployed_output.PROJECT_STATE_ROOT
) -> diagnosis.Check:
    """`bin/backup.sh info --json`, and its STATE FIELD rather than its status.

    D548: `pgbackrest info` exits 0 for a stanza that does not exist. D145:
    `postgrest --ready` returns 0 while every request 404s. Two third parties,
    five sessions apart, one shape — the state was in a field both times.
    """
    outputs = deployed_output.deployed_path(project_key, root=root)
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


def probe_mirror(
    project_key: str, document: dict[str, Any], root: Path = deployed_output.PROJECT_STATE_ROOT
) -> diagnosis.Check:
    """The mirror's copy record, read off disk rather than the document (ADR 0188).

    The deployed document's `backup_state.mirror` is a deploy-time snapshot;
    the record beside it is written by every completed copy, so it is the live
    reading. An absent record on a mirrored project is `never`; a record that
    does not parse is unknown, never zero objects.
    """
    enabled = config.backup_mirror_enabled(document)
    if not enabled:
        return diagnosis.mirror(enabled=False, status=None, last_copied_at=None, age_days=None)
    path = deployed_output.mirror_record_path(project_key, root=root)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        reading = backup_report.mirror_reading(enabled=True, record=None)
    except OSError:
        return diagnosis.mirror(enabled=True, status=None, last_copied_at=None, age_days=None)
    else:
        record = backup_report.parse_mirror_record(text)
        if record is None:
            return diagnosis.mirror(enabled=True, status=None, last_copied_at=None, age_days=None)
        reading = backup_report.mirror_reading(enabled=True, record=record)
    return diagnosis.mirror(
        enabled=True,
        status=reading["status"],
        last_copied_at=reading["last_copied_at"],
        age_days=fleet.age_days(reading["last_copied_at"], datetime.now(UTC)),
    )


def probe_disk(
    document: dict[str, Any],
    *,
    warn_copies: float = diagnosis.DISK_WARN_COPIES,
    problem_copies: float = diagnosis.DISK_PROBLEM_COPIES,
) -> diagnosis.Check:
    """PGDATA's size against the space free on the filesystem holding it.

    **The mount point, never `/`** (D634). Measured in Run 1: the two coincide on
    a developer machine, so a check reading `/` is right there for a reason that
    does not generalise — and on a host that gives the database its own device it
    would be reading an unrelated filesystem while still printing a number.

    The thresholds are the deployment's unless a rehearsal injects them
    (`--disk-warn-copies`, `--disk-problem-copies`; ADR 0190): the reader is
    rehearsed by moving the threshold, never by filling the disk.
    """
    db = document.get("database") or {}
    container = db.get("container")
    mount = runtime_override.POSTGRES_PGDATA
    if not container:
        return diagnosis.disk_headroom(
            cluster_kb=None,
            available_kb=None,
            mount=mount,
            warn_copies=warn_copies,
            problem_copies=problem_copies,
        )

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
    return diagnosis.disk_headroom(
        cluster_kb=cluster_kb,
        available_kb=available_kb,
        mount=mount,
        warn_copies=warn_copies,
        problem_copies=problem_copies,
    )


def probe_capability_drift(
    document: dict[str, Any],
    *,
    lock_file: Path | None = None,
    plane_reader: Callable[[str, bytes], bool | None] | None = None,
) -> diagnosis.Check:
    """The capability lock on disk against the digest the deploy recorded.

    `AGT-DRIFT-001` on the running deployment (`OPS-REHEARSE-008`, ADR 0190).
    The lock's path is derived from the project key through
    `deployed_output.rendered_path` -- the path the deploy wrote it to and the
    runtime mounts it from -- unless a rehearsal points `--lock-file` at a lock
    with a foreign hash, which is how the reader is exercised without touching
    the deployed file.

    **The digests stay here.** The recorded one is in the `mcp` block, which the
    doctor never echoes, so `diagnosis.capability_drift` is handed booleans and
    the comparison's answer, never either digest (ADR 0159).

    Since D1153 it also asks the RUNNING plane which lock it loaded, through the
    one probe the deploy uses (`agent_plane.PROBE`). A file that agrees with the
    document says nothing about the process: a deploy whose only change is the
    lock recreates no container unless the container's mount digest moved (ADR
    0155), and on 2026-09-11 that cost eight minutes of a document describing a
    plane it did not match, with every check here green (D1152).
    """
    recorded = (document.get("mcp") or {}).get("capability_lock_sha256")
    key = str((document.get("project") or {}).get("key") or "")
    path = lock_file or (deployed_output.rendered_path(key) / runtime_override.MCP_LOCK_FILENAME)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return diagnosis.capability_drift(
            recorded=bool(recorded), present=False, matches=None, plane=None
        )
    except OSError:
        return diagnosis.capability_drift(
            recorded=bool(recorded), present=None, matches=None, plane=None
        )
    digest = hashlib.sha256(raw).hexdigest()
    matches = (digest == recorded) if recorded else None
    # Asked only where the answer can change the verdict. A project with no
    # recorded lock has no plane to ask about, and a file that already disagrees
    # with the document is a PROBLEM whatever the plane says -- so the probe is
    # not run to produce a fact nothing reads.
    reader = plane_reader or probe_plane_lock
    plane = reader(key, raw) if recorded and matches else None
    return diagnosis.capability_drift(
        recorded=bool(recorded), present=True, matches=matches, plane=plane
    )


def probe_plane_lock(project_key: str, lock_bytes: bytes) -> bool | None:
    """Does the running agent plane serve the lock these bytes are?

    `True` it does, `False` it serves another, **`None` this could not be
    determined** -- no single container, `docker` unavailable or timed out, an
    unreadable answer, or a runtime from before D1153 that does not say which
    lock it loaded. Three outcomes, and the third is reported rather than folded
    into either of the first two (ADR 0195).

    The lock's signature is read from the file rather than recomputed here:
    `tools_sha256` is what the compiler signed over the tool list, and it is the
    value the plane reports. A digest of the whole file is a different question
    and one the plane cannot answer.

    **The local is `lock`, and the name is load-bearing.** In a `bin/` command
    the name `document` means the DEPLOYED document, and
    `test_container_selectors.py::test_no_operator_command_reads_a_key_the_deployed_document_does_not_have`
    reads every `document[...]` and `document.get(...)` in this file against the
    outputs schema -- by name, deliberately, because following assignments would
    trade a precise guard for a vague one. Calling this one `document` made that
    guard report `tools_sha256` as a member this command invents (D1184).
    """
    try:
        lock = json.loads(lock_bytes)
    except ValueError:
        return None
    signature = lock.get("tools_sha256") if isinstance(lock, dict) else None
    if not isinstance(signature, str) or not signature:
        return None

    listing = run(
        "docker",
        "ps",
        *agent_plane.container_filters(project_key, runtime_override.MCP_SERVICE),
        timeout=20,
    )
    if listing is None or listing.returncode != 0:
        return None
    container = agent_plane.sole_container(listing.stdout)
    if container is None:
        return None

    answered = run("docker", "exec", "-i", container, "python", "-c", agent_plane.PROBE)
    if answered is None or answered.returncode != 0:
        return None
    return agent_plane.serves_lock(agent_plane.parse_report(answered.stdout), signature)


def _first_int(text: str) -> int | None:
    match = re.match(r"\s*(\d+)", text or "")
    return int(match.group(1)) if match else None


# ---------------------------------------------------------------------------


#: The agent record's size, in one round trip. Pipe-separated rather than four
#: queries: the four numbers describe one moment, and four calls would describe
#: four.
AGENT_RECORD_QUERY = (
    "SELECT (SELECT count(*) FROM app_private.agent_audit)::text || '|' || "
    "coalesce((SELECT min(started_at) FROM app_private.agent_audit)::text, '') || '|' || "
    "(SELECT count(*) FROM app_private.agent_idempotency)::text || '|' || "
    "coalesce((SELECT min(created_at) FROM app_private.agent_idempotency)::text, '')"
)

#: What a timestamp read back from the cluster is allowed to look like before it
#: is repeated in a report. Deliberately narrow: `YYYY-MM-DD HH:MM:SS` and
#: whatever fraction and offset follow, every character from a fixed alphabet.
#: The cluster is not a third party in the sense ADR 0159 means, but it is not
#: this program either, and a value that does not look like what was asked for
#: is dropped rather than printed.
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[0-9.:+-]*$")


def _timestamp(text: str) -> str | None:
    candidate = text.strip()
    return candidate if _TIMESTAMP.match(candidate) else None


def probe_agent_record(document: dict[str, Any]) -> diagnosis.Check:
    """The two agent tables' counts, read from the cluster (ADR 0213).

    One `psql` round trip over the container socket, as the superuser, the way
    `probe_database` reaches it. **The query names the TABLES and not migration
    0033's `agent_record_size()`**, so it answers on a deployment that has not
    applied the retention migration.

    Anything else -- no container in the document, a cluster that did not
    answer, a deployment so old that the tables do not exist -- is the third
    outcome, reported rather than folded into a healthy-looking zero (ADR 0195,
    D600).
    """
    db = document.get("database") or {}
    container = db.get("container")
    name = db.get("name")
    if not container or not name:
        return diagnosis.agent_record(
            audit_rows=None,
            audit_oldest=None,
            idempotency_rows=None,
            idempotency_oldest=None,
            detail="the document names no container",
        )

    read = run(
        "docker", "exec", "-i", container, "psql", "-U", "postgres", "-d", name,
        "-X", "-qtA", "-c", AGENT_RECORD_QUERY,
        timeout=30,
    )  # fmt: skip
    if read is None or read.returncode != 0:
        return diagnosis.agent_record(
            audit_rows=None,
            audit_oldest=None,
            idempotency_rows=None,
            idempotency_oldest=None,
            detail="the cluster did not answer",
        )

    fields = (read.stdout.strip().splitlines() or [""])[0].split("|")
    if len(fields) != 4:
        return diagnosis.agent_record(
            audit_rows=None,
            audit_oldest=None,
            idempotency_rows=None,
            idempotency_oldest=None,
            detail="the reading did not arrive in the shape it was asked for",
        )
    return diagnosis.agent_record(
        audit_rows=_first_int(fields[0]),
        audit_oldest=_timestamp(fields[1]),
        idempotency_rows=_first_int(fields[2]),
        idempotency_oldest=_timestamp(fields[3]),
        detail="the reading did not arrive in the shape it was asked for",
    )


# ---------------------------------------------------------------------------
# The node -- capacity (Session 31, ADR 0221)
# ---------------------------------------------------------------------------


def probe_meminfo(path: Path = Path(capacity_reading.MEMINFO_PATH)) -> dict[str, int] | None:
    """The node's memory, read DIRECTLY and not through a container.

    A figure read inside a cgroup answers a different question: `mem_limit` is
    what that container may use, and this reading is about what the machine
    has. Nothing is exec'd, so `container_exec` is not involved (D1593 draws
    the line at execs INTO a container, and this is a file read).
    """
    try:
        return capacity_reading.parse_meminfo(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def probe_docker_root() -> str | None:
    """Where Docker keeps its data, asked rather than assumed.

    `/var/lib/docker` is the default and is not the contract; a host that moved
    it would otherwise be measured at the wrong filesystem, and the number
    would look perfectly plausible. `docker info` is not an exec into a
    container, so it goes through this module's own bounded `run` (D1593).
    """
    answered = run("docker", "info", "--format", "{{.DockerRootDir}}", timeout=20)
    if answered is None or answered.returncode != 0:
        return None
    root = answered.stdout.strip()
    return root or None


def probe_ceilings() -> tuple[dict[str, int], tuple[str, ...]]:
    """Every labelled container's `mem_limit`, summed per project.

    Reports and decides nothing (ADR 0221). `docker ps` and `docker inspect`
    are not execs into a container.
    """
    listing = run("docker", "ps", "--filter", f"label={COMPOSE_PROJECT_LABEL}", "-q", timeout=20)
    if listing is None or listing.returncode != 0:
        return {}, ()
    ids = listing.stdout.split()
    if not ids:
        return {}, ()
    inspected = run("docker", "inspect", *ids, timeout=30)
    if inspected is None or inspected.returncode != 0:
        return {}, ()
    return capacity_reading.ceilings_from_inspect(inspected.stdout)


def probe_capacity(
    host_manifest: Path,
    root: Path = deployed_output.PROJECT_STATE_ROOT,
    *,
    exclude: str | None = None,
) -> capacity_reading.Reading:
    """What this node has, what was declared, and what is already claimed.

    **Every figure is a `Figure`, and every failure to read one carries its
    reason** (ADR 0195). Nothing here substitutes a zero, a default or a guess:
    the reading reports what it could not determine and `capacity_reading.
    decide` is the thing allowed to refuse over it.

    **The deployed documents are root-readable only.** `/etc/agentic-postgres/
    projects/<key>/` is `drwx------ root root` (D1606, measured on both
    projects), so an unprivileged run lands every project in `unreadable` with
    its reason -- and `decide` then refuses rather than summing zero, which is
    the whole reason that dict exists.

    The loop variable is `deployed`, never `document`: in a `bin/` command the
    name `document` means the deployed document, and
    `test_container_selectors.py` reads every `document[...]` in this file
    against the outputs schema (D1184).
    """
    declared = host_config.declared_capacity(host_config.load_host_manifest(host_manifest))

    memory = probe_meminfo()
    if memory is None:
        why = "/proc/meminfo could not be read, or did not carry all three of "
        why += "MemTotal, MemAvailable and SwapTotal"
        mem_total = capacity_reading.Figure.unknown(why)
        mem_available = capacity_reading.Figure.unknown(why)
        swap_total = capacity_reading.Figure.unknown(why)
    else:
        mem_total = capacity_reading.Figure.measured(memory["MemTotal"])
        mem_available = capacity_reading.Figure.measured(memory["MemAvailable"])
        swap_total = capacity_reading.Figure.measured(memory["SwapTotal"])

    docker_root = probe_docker_root()
    if docker_root is None:
        why = "`docker info` did not report a data root"
        free_gb = capacity_reading.Figure.unknown(why)
        total_gb = capacity_reading.Figure.unknown(why)
    else:
        try:
            usage = shutil.disk_usage(docker_root)
        except OSError:
            why = f"the Docker data root could not be stat'd ({len(docker_root)} chars)"
            free_gb = capacity_reading.Figure.unknown(why)
            total_gb = capacity_reading.Figure.unknown(why)
        else:
            free_gb = capacity_reading.Figure.measured(usage.free // (1024**3))
            total_gb = capacity_reading.Figure.measured(usage.total // (1024**3))

    documents: dict[str, Any] = {}
    unreadable: dict[str, str] = {}
    try:
        keys = sorted(path.name for path in root.iterdir() if path.is_dir())
    except OSError as problem:
        # NOT an empty list. A root this command cannot list is a set of
        # claims it does not know, and reporting that as `0 MiB committed`
        # would hand `decide` the whole declared budget as safely available
        # and admit a candidate on the strength of a directory it could not
        # open. The reserved key is a project name no manifest can hold
        # (`/` is refused by the key pattern), so it cannot collide with one.
        unreadable[PROJECT_ROOT_UNREADABLE] = (
            f"the project state root could not be listed: {problem.strerror}"
        )
        keys = []
    for key in keys:
        deployed, why = read_deployed(root, key)
        if deployed is None:
            unreadable[key] = why or "the deployed document could not be read"
            continue
        documents[key] = deployed

    committed, missing_member = capacity_reading.committed_from_documents(
        documents, exclude=exclude
    )
    unreadable.update(missing_member)
    unreadable.pop(exclude, None)

    ceilings, unbounded = probe_ceilings()

    return capacity_reading.Reading(
        declared=declared,
        mem_total=mem_total,
        mem_available=mem_available,
        swap_total=swap_total,
        docker_root_free_gb=free_gb,
        docker_root_total_gb=total_gb,
        committed=committed,
        unreadable=unreadable,
        ceilings=ceilings,
        unbounded=unbounded,
    )


def diagnose(
    project_key: str,
    root: Path = deployed_output.PROJECT_STATE_ROOT,
    *,
    warn_copies: float = diagnosis.DISK_WARN_COPIES,
    problem_copies: float = diagnosis.DISK_PROBLEM_COPIES,
    lock_file: Path | None = None,
) -> tuple[diagnosis.Check, ...]:
    document = load_document(project_key, root)
    checks: list[diagnosis.Check] = [probe_containers(project_key)]
    checks.extend(probe_routes(document))
    checks.append(probe_tls(document))
    checks.append(probe_database(document))
    checks.append(probe_migrations(document))
    checks.append(probe_repository(project_key, root))
    checks.append(probe_archiver(document))
    checks.append(probe_mirror(project_key, document, root))
    checks.append(probe_disk(document, warn_copies=warn_copies, problem_copies=problem_copies))
    checks.append(probe_capability_drift(document, lock_file=lock_file))
    checks.append(probe_agent_record(document))
    return tuple(checks)


def _render(
    checks: tuple[diagnosis.Check, ...], arguments: argparse.Namespace, *, project_key: str
) -> None:
    """The rendering flags reach the RENDERER and nothing else.

    There is no verbose or json branch in any probe, which is what keeps "a
    third party's bytes are never printed" a property of the shape rather than
    a rule each probe obeys (ADR 0159). Lifted out of `main` in Session 31 so
    that the two readings and the eleven checks print through one function
    rather than three copies of it.
    """
    if arguments.json:
        observed_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        print(diagnosis.render_json(checks, project_key=project_key, observed_at=observed_at))
    else:
        print(diagnosis.report(checks, project_key=project_key, verbose=arguments.verbose))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    # Not required any more, and only because `capacity` asks about the NODE.
    # Every other invocation still has to name a project, which `main` enforces
    # below rather than argparse -- argparse can express "required" but not
    # "required unless the reading is this one", and a flag whose requirement
    # is conditional is worth stating in one place a reader can find.
    parser.add_argument("--project", default=None)
    # Session 31: the two readings, selected by a verb that `bin/doctor.sh`
    # maps to this flag. Absent, the eleven checks run exactly as before --
    # which is what keeps `bin/fleet.py` and `rehearsal._doctor`, both of which
    # invoke `--project KEY --json`, working untouched.
    parser.add_argument("--reading", choices=("capacity", "usage"), default=None)
    parser.add_argument("--host", type=Path, default=None)
    # Where the deployed documents live. The host's root by default; a fleet
    # inventory or a proof may point it elsewhere. It changes where the
    # DOCUMENT is read from and nothing about what is probed.
    parser.add_argument("--root", type=Path, default=deployed_output.PROJECT_STATE_ROOT)
    # Two renderings, never both: `--json` carries every check's evidence by
    # construction, so a `--verbose` beside it would be a flag that changes
    # nothing, which is D374's shape at the command line.
    rendering = parser.add_mutually_exclusive_group()
    rendering.add_argument("--verbose", action="store_true")
    rendering.add_argument("--json", action="store_true")
    # A rehearsal's injections (ADR 0190): the disk thresholds, and a lock file
    # to read instead of the deployed one. They change what a reader is asked
    # about, never what it prints; the evidence carries the values used.
    parser.add_argument("--disk-warn-copies", type=float, default=diagnosis.DISK_WARN_COPIES)
    parser.add_argument("--disk-problem-copies", type=float, default=diagnosis.DISK_PROBLEM_COPIES)
    parser.add_argument("--lock-file", type=Path, default=None)
    arguments = parser.parse_args(argv)

    if arguments.reading == "capacity":
        if arguments.host is None:
            return _die(EXIT_INPUT, "--host is required with the capacity reading")
        try:
            reading = probe_capacity(arguments.host, arguments.root, exclude=arguments.project)
        except config.ManifestError as problem:
            return _die(EXIT_INPUT, str(problem))
        except OSError as problem:
            return _die(EXIT_INPUT, f"the host manifest could not be read: {problem.strerror}")
        checks = diagnosis.capacity_report(reading)
        _render(checks, arguments, project_key=arguments.project or "(node)")
        return diagnosis.exit_code(checks)

    if arguments.reading == "usage":
        # Run 4 builds this. Until then the verb is refused rather than
        # answered with a report that reads nothing -- a reading that returns
        # OK having measured nothing is the defect this session exists to stop.
        return _die(EXIT_INPUT, "the usage reading is not available in this release")

    if arguments.host is not None:
        return _die(EXIT_INPUT, "--host belongs to the capacity reading; see `doctor.sh capacity`")
    if arguments.project is None:
        return _die(EXIT_INPUT, "--project is required")

    try:
        diagnosis.disk_thresholds(
            warn_copies=arguments.disk_warn_copies, problem_copies=arguments.disk_problem_copies
        )
    except ValueError as problem:
        return _die(EXIT_INPUT, str(problem))

    checks = diagnose(
        arguments.project,
        arguments.root,
        warn_copies=arguments.disk_warn_copies,
        problem_copies=arguments.disk_problem_copies,
        lock_file=arguments.lock_file,
    )
    _render(checks, arguments, project_key=arguments.project)
    return diagnosis.exit_code(checks)


if __name__ == "__main__":
    sys.exit(main())
