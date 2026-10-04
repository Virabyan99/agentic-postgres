"""Session 36's live proofs: the request line, the withdrawal, the record's size,
the secret ages.

Three host claims' node ids, run by the sweep as root (OPS-LOG-003,
OPS-RETAIN-003, OPS-ROTATE-002). Nothing here writes a row: the request is a public GET of the
key set, and the record is read, never pruned (a prune is an operator's act,
ADR 0213 / 0248, and the sweep is not an operator).

**The request id is the PLANE's, read from the response** (D2007): rig 36c
measured that the service mints its own and never reads a caller's, so the
proof plants a caller id as the control that the minting holds and looks for
the id it was HANDED.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, naming

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST",
        "APG_PROJECT_A_OUTPUTS",
        "APG_PROJECT_B_OUTPUTS",
    ),
]

CALLER_ID = "00000000-0000-4000-8000-0000000036aa"

#: `record_size()`'s relations and the direct count each must agree with.
DIRECT = {
    "agent_audit": "SELECT count(*) FROM app_private.agent_audit",
    "agent_idempotency": "SELECT count(*) FROM app_private.agent_idempotency",
    "workflow_run": "SELECT count(*) FROM app_private.workflow_run",
    "workflow_step": "SELECT count(*) FROM app_private.workflow_step",
    "workflow_attempt": "SELECT count(*) FROM app_private.workflow_attempt",
    "workflow_approval": "SELECT count(*) FROM app_private.workflow_approval",
    "connector_event": "SELECT count(*) FROM app_private.connector_event",
    "connector_delivery": "SELECT count(*) FROM app_private.connector_delivery",
    "connector_receipt": "SELECT count(*) FROM app_private.connector_receipt",
    "agents (revoked)": "SELECT count(*) FROM app_private.agents WHERE status = 'revoked'",
    "workflow_approval (pending on an ended run)": (
        "SELECT count(*) FROM app_private.workflow_approval a "
        "JOIN app_private.workflow_run r ON r.id = a.run_id "
        "WHERE a.status = 'pending' "
        "AND r.status IN ('succeeded', 'failed', 'cancelled', 'stopped')"
    ),
}

PENDING_ON_ENDED = "workflow_approval (pending on an ended run)"


def _run(*command: str, stdin: str | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(command),
        input=stdin,
        stdin=None if stdin is not None else subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _service_container(document: dict[str, Any], service: str) -> str:
    """The one running container of `service` in this project's compose project.

    The Compose project is DERIVED from the key (ADR 0002), as Sessions 32 and 34
    do: `compose.project_name` exists only in a RENDERED document, and the
    fixtures here are deployed ones -- the first version raised `KeyError:
    'compose'` on its first host run (D2036), the class Session 5's
    `service_container` had already recorded."""
    project = naming.compose_project_name(document["project"]["key"])
    listing = _run(
        "docker", "ps", "-q", "--no-trunc",
        "--filter", f"label=com.docker.compose.project={project}",
        "--filter", f"label=com.docker.compose.service={service}",
    )  # fmt: skip
    ids = listing.stdout.split()
    assert listing.returncode == 0 and len(ids) == 1, (
        f"{project} has {len(ids)} running {service} containers: {listing.stderr[:200]}"
    )
    return ids[0]


def _header(headers: dict[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def test_a_request_line_reaches_the_auth_containers_log(
    as_root: None,
    project_a: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
) -> None:
    """OPS-LOG-003 (ADR 0249): one GET of alpha's key set through the edge, and
    `docker logs` of alpha's `auth` container holds exactly ONE `apg.http.request`
    line naming the request id the RESPONSE carried, with the route template.
    The planted caller id appears in no line (the plane mints its own, D2007),
    and no line carries a bearer token."""
    container = _service_container(project_a, "auth")
    since = str(int(time.time()) - 2)
    answered = api_call(
        f"{app_base(project_a)}/auth/jwks.json", headers={"X-Request-Id": CALLER_ID}
    )
    assert answered.status == 200, (answered.status, answered.reason)
    minted = _header(answered.headers, "X-Request-Id")
    assert minted and minted != CALLER_ID, f"the response's request id is {minted!r}"

    lines: list[str] = []
    for _ in range(10):
        logs = _run("docker", "logs", "--since", since, container)
        assert logs.returncode == 0, logs.stderr[:300]
        lines = (logs.stdout + logs.stderr).splitlines()
        if any(minted in line for line in lines):
            break
        time.sleep(1)
    naming = [line for line in lines if minted in line]
    assert len(naming) == 1, f"{len(naming)} lines name {minted}: {naming[:3]}"
    assert naming[0].startswith("apg.http.request "), naming[0][:200]
    record = json.loads(naming[0].split(" ", 1)[1])
    assert record["route"] == "/auth/jwks.json" and record["status"] == 200, record
    assert not [line for line in lines if CALLER_ID in line], "the caller's id reached the log"
    assert not [line for line in lines if "Bearer " in line], "a bearer token reached the log"


def _record_size(document: dict[str, Any]) -> dict[str, int]:
    key = document["project"]["key"]
    read = _run(str(REPO_ROOT / "bin" / "record.sh"), "size", "--project", key, "--json")
    assert read.returncode == 0, f"record.sh size exited {read.returncode}: {read.stderr[:300]}"
    return {row["relation"]: row["rows"] for row in json.loads(read.stdout)["relations"]}


def test_no_pending_approval_outlives_its_run(as_root: None, project_b: dict[str, Any]) -> None:
    """OPS-RETAIN-003's first half (D1775): on beta, through the operator's own
    command, no approval is left `pending` on a run that has ended -- read up to
    three times 5 s apart, two worker polls and a margin, so a run that ended a
    moment ago is given the poll the worker is owed."""
    sizes: dict[str, int] = {}
    for attempt in range(3):
        sizes = _record_size(project_b)
        if sizes.get(PENDING_ON_ENDED) == 0:
            break
        if attempt < 2:
            time.sleep(5)
    assert PENDING_ON_ENDED in sizes, sorted(sizes)
    assert sizes[PENDING_ON_ENDED] == 0, sizes


def test_the_record_size_reading_matches_the_tables(
    as_root: None, project_b: dict[str, Any]
) -> None:
    """OPS-RETAIN-003's second half: every relation `record_size()` names agrees
    with a direct count, both read inside ONE `REPEATABLE READ` transaction so
    the worker's writes cannot land between them."""
    database = project_b["database"]
    script = "BEGIN ISOLATION LEVEL REPEATABLE READ;\n"
    script += "SELECT 'size|' || relation || '|' || row_count FROM app_private.record_size();\n"
    for relation, query in DIRECT.items():
        script += f"SELECT 'direct|{relation}|' || ({query});\n"
    script += "COMMIT;\n"
    read = _run(
        "docker", "exec", "-i", database["container"],
        "psql", "-U", "postgres", "-d", database["name"], "-X", "-qtA",
        "-v", "ON_ERROR_STOP=1", "-f", "-",
        stdin=script,
    )  # fmt: skip
    assert read.returncode == 0, read.stderr[:400]
    size: dict[str, str] = {}
    direct: dict[str, str] = {}
    for line in read.stdout.splitlines():
        kind, _, rest = line.partition("|")
        if kind in ("size", "direct"):
            relation, _, count = rest.rpartition("|")
            (size if kind == "size" else direct)[relation] = count
    assert set(size) == set(DIRECT), sorted(set(size) ^ set(DIRECT))
    assert size == direct, {k: (size[k], direct.get(k)) for k in size if size[k] != direct.get(k)}


#: The secrets that declare `max_age_days` (ADR 0250), read on alpha.
DECLARING = {"postgrest_authenticator_password", "docs_basic_auth_password", "app_runtime_password"}


def test_every_declared_secret_age_is_read(as_root: None, project_a: dict[str, Any]) -> None:
    """OPS-ROTATE-002 (ADR 0250): `doctor secrets` on alpha reads the provider's
    update time for every secret that declares an age -- one check each, none
    `unknown`. `overdue` is a reading, not a failure, so `ok` and `warn` both
    pass; the proof is that the age was READ, through the operator's command."""
    key = project_a["project"]["key"]
    read = _run(
        str(REPO_ROOT / "bin" / "doctor.sh"), "secrets", "--project", key, "--json", timeout=180
    )
    assert read.returncode == 0, f"doctor secrets exited {read.returncode}: {read.stderr[:300]}"
    checks = {check["name"]: check for check in json.loads(read.stdout)["checks"]}
    assert set(checks) == {f"secret {name}" for name in DECLARING}, sorted(checks)
    unread = {name: c["detail"] for name, c in checks.items() if c["verdict"] == "unknown"}
    assert not unread, unread
    assert {c["verdict"] for c in checks.values()} <= {"ok", "warn"}, checks
