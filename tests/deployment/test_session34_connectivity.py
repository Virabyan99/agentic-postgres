"""Session 34's live halves: connectors and events, on beta, alpha the control.

`CONN-IN-002`, `CONN-OUT-002`, `EVT-WAIT-002`, `CONN-SCHED-002` (ADR 0235-0239).
Written at the bump (Run 9) and gated on variables the Session 33 gate already
exports -- no new environment gate (§2).

**None of this has executed before the trip.** Every proof asserts against the
deployed records -- `connector_receipt`, `connector_event`, `workflow_run`,
`app.notes`, the sink's own log -- and never against what the loop says it did
(D1696's reason, carried).

**Every signature here is this module's OWN HMAC** over the bytes sent or
received, under a key the PRODUCT'S command wrote (`bin/connector.sh key`, as
root -- the sweep is root), so a proof cannot share a belief with the service
about the scheme (CLAUDE.md §7, question 6).

**The sink** is D1809's: a container on beta's `internal` network under the
alias `apg-s34-sink`, running the stdlib server rig 34d measured from beta's own
auth image, answering 200 on `/ok` and 500 on anything else and logging one
JSON line per request. Beta's installed manifest points `note-embedded` at
`/ok` and `notes-deadletter` at `/fail` (Run 10's sheet D3). It is started per
sweep and stopped in `finally`.

**What these proofs leave behind** (D1700): probe agents revoked, their owner,
and the connectors administrator when an `enabled_by` references it. Every
connector is DISABLED at teardown. A dead letter is left on purpose -- REC-EVT-001
(`tests/recovery/test_session34_delivery_restore.py`, collected after this
directory) reads it.
"""

from __future__ import annotations

import hashlib
import hmac
import itertools
import json
import os
import secrets
import subprocess
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, deployed_output, naming, runtime_override

# ruff: noqa: S608 -- every interpolated value is a uuid this module generated or
# read back from the cluster, a connector name from the committed set, or a role
# name from a deployed document the outputs schema validated.

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST",
        "APG_PROJECT_A_OUTPUTS",
        "APG_PROJECT_B_OUTPUTS",
    ),
]

#: The event owner's tenant scopes: notes to create, embeddings to write.
OWNER_SCOPES = ("note_embeddings:read", "note_embeddings:write", "notes:read", "notes:write")

#: A suffix unique to this sweep, in every name and title (D1700).
SWEEP = secrets.token_hex(4)

INBOX = "notes-inbox"
DIGEST = "notes-digest"
EMBEDDED = "note-embedded"
DEADLETTER = "notes-deadletter"
WAITER = "notes-await-embedding"

TERMINAL = frozenset({"succeeded", "failed", "cancelled", "stopped"})
RUN_SECONDS = 90
#: A scheduled connector fires at enable and then every 60 s; the loop polls
#: every 5 s. `every_seconds + 2 * POLL_SECONDS` is the plan's bound.
SCHEDULE_SECONDS = 70
#: Three attempts spaced by max(backoff, the idle poll) -- D1838 -- plus polls.
DEAD_LETTER_SECONDS = 90
#: How long a non-matching event must leave a wait parked.
UNMATCHED_SECONDS = 15

#: Rig 33b's measured literal: 768 zeros, which PostgREST accepts into a
#: `vector` parameter.
EMBEDDING = "[" + ",".join(["0"] * 768) + "]"

#: The sink, rig 34d's server with the arrival time added so the retry
#: spacing is read from the receiver's own clock.
SINK_SERVER = """
import http.server
import json
import time


class Sink(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        line = {
            "at": time.time(),
            "path": self.path,
            "delivery": self.headers.get("X-Apg-Delivery"),
            "event": self.headers.get("X-Apg-Event"),
            "signature": self.headers.get("X-Apg-Signature"),
            "body": body.decode("utf-8", "replace"),
        }
        print(json.dumps(line, sort_keys=True), flush=True)
        self.send_response(200 if self.path == "/ok" else 500)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *arguments):
        return


http.server.ThreadingHTTPServer(("0.0.0.0", 8080), Sink).serve_forever()
"""
SINK_ALIAS = "apg-s34-sink"


# ---------------------------------------------------------------------------
# Subjects and agents -- `test_session33_gates.py`'s helpers, copied
# ---------------------------------------------------------------------------


def _create_subject(
    psql: Callable[..., tuple[int, str, str]],
    document: dict[str, Any],
    *,
    username: str,
    role: str,
    scopes: tuple[str, ...],
    password: str,
) -> str:
    from agentic_postgres import service_source

    hashing = service_source.load("hashing")
    array = ", ".join(f"'{scope}'" for scope in sorted(scopes))
    code, user_id, error = psql(
        document,
        "SELECT app_private.auth_create_user("
        f"'{username}', 'Session 34 connectivity probe', "
        f"'{document['database']['roles'][role]}', ARRAY[{array}]::text[], "
        f"'{hashing.Hasher().hash(password)}');",
    )
    assert code == 0 and user_id, f"could not create {username}: {error}"
    return user_id.splitlines()[0]


def _login(api_call: Callable[..., Any], app: str, username: str, password: str) -> str:
    answer = api_call(
        f"{app}/auth/login", method="POST", body={"username": username, "password": password}
    )
    assert answer.status == 200, f"{username} could not log in: {answer.body[:200]}"
    return json.loads(answer.body)["access_token"]


class ProbeAgent:
    """An agent on one project and a way to get a fresh token."""

    def __init__(
        self, agent_id: str, secret: str, owner_id: str, api_call: Callable[..., Any], app: str
    ) -> None:
        self.agent_id = agent_id
        self.owner_id = owner_id
        self._secret = secret
        self._api_call = api_call
        self.app = app

    def token(self) -> str:
        answer = self._api_call(
            f"{self.app}/auth/agent-token",
            method="POST",
            body={"agent_id": self.agent_id, "secret": self._secret},
        )
        assert answer.status == 200, (
            f"agent {self.agent_id} could not obtain a token ({answer.status}: {answer.body[:200]})"
        )
        return json.loads(answer.body)["access_token"]


def _create_agent(
    psql: Callable[..., tuple[int, str, str]],
    document: dict[str, Any],
    owner_id: str,
    label: str,
    api_call: Callable[..., Any],
    app: str,
    *,
    role: str,
    scopes: tuple[str, ...],
) -> ProbeAgent:
    from agentic_postgres import service_source

    hashing = service_source.load("hashing")
    secret = secrets.token_urlsafe(24)
    name = f"apg-s34-{label}-{SWEEP}"
    array = ", ".join(f"'{scope}'" for scope in sorted(scopes))
    code, agent_id, error = psql(
        document,
        "SELECT app_private.auth_create_agent("
        f"'{name}', 'Session 34 connectivity probe', "
        f"'{document['database']['roles'][role]}', ARRAY[{array}]::text[], "
        f"'{owner_id}', '{hashing.Hasher().hash(secret)}', NULL);",
    )
    assert code == 0 and agent_id, f"could not create the probe agent {name}: {error}"
    return ProbeAgent(agent_id.splitlines()[0], secret, owner_id, api_call, app)


def _revoke(
    psql: Callable[..., tuple[int, str, str]], document: dict[str, Any], agent: str
) -> None:
    psql(
        document,
        "UPDATE app_private.agents SET status = 'revoked', "
        f"authz_version = authz_version + 1, updated_at = now() WHERE id = '{agent}';",
    )


def _until(
    read: Callable[[], Any], predicate: Callable[[Any], bool], seconds: float, what: str
) -> Any:
    deadline = time.monotonic() + seconds
    value = read()
    while not predicate(value):
        if time.monotonic() > deadline:
            pytest.fail(f"{what} not reached within {seconds:.0f}s; last read: {str(value)[:1500]}")
        time.sleep(2)
        value = read()
    return value


def _one(psql: Callable[..., tuple[int, str, str]], document: dict[str, Any], sql: str) -> str:
    code, out, error = psql(document, sql)
    assert code == 0, f"{sql[:120]} failed: {error}"
    return out.splitlines()[0] if out else ""


def _array(text: str) -> tuple[str, ...]:
    """A `text[]` as psql prints it, `{a,b}`, as a sorted tuple."""
    inner = text.strip().strip("{}")
    return tuple(sorted(item for item in inner.split(",") if item))


# ---------------------------------------------------------------------------
# The facility, the principals, the keys and the sink
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def beta_app(project_b: dict[str, Any], app_base: Callable[[dict[str, Any]], str]) -> str:
    return app_base(project_b)


@pytest.fixture(scope="module")
def facility_on(project_a: dict[str, Any], project_b: dict[str, Any]) -> None:
    """Beta's DEPLOYED document says the facility is on, alpha's that it is off
    -- Run 10's sheet D3 enables it on beta alone, as its own operation."""
    assert (project_b.get("connectors") or {}).get("enabled") is True, (
        "beta's deployed document does not enable the connectors facility; Run 10's "
        "facility operation (sheet D3) has not been deployed"
    )
    assert (project_a.get("connectors") or {}).get("enabled") is not True, (
        "alpha's deployed document enables the connectors facility; it is the control"
    )


@pytest.fixture(scope="module")
def connectors_admin(
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    beta_app: str,
    facility_on: None,
) -> Iterator[dict[str, str]]:
    """`project_admin` with the two connector scopes and the agent roster's."""
    username = f"apg-s34-admin-{SWEEP}"
    password = secrets.token_urlsafe(24)
    user_id = _create_subject(
        psql,
        project_b,
        username=username,
        role="project_admin",
        scopes=(
            "admin_agents:read",
            "admin_agents:write",
            "admin_connectors:read",
            "admin_connectors:write",
        ),
        password=password,
    )
    try:
        yield {"user_id": user_id, "token": _login(api_call, beta_app, username, password)}
    finally:
        code, _, error = psql(project_b, f"DELETE FROM app_private.users WHERE id = '{user_id}';")
        if code != 0:
            print(f"the connectors administrator {username} is LEFT (D1700): {error[:200]}")


@pytest.fixture(scope="module")
def event_owner(
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    beta_app: str,
    facility_on: None,
) -> Iterator[dict[str, str]]:
    """The human every probe agent belongs to, and the writer of every event.

    **Beta's deployed lock is read first** (`gate_owner`'s rule): a lock that
    did not derive `note_embeddings:*` is a deployment these proofs cannot use.
    """
    path = (
        deployed_output.rendered_path(project_b["project"]["key"])
        / runtime_override.MCP_LOCK_FILENAME
    )
    assert path.is_file(), f"no capability lock at {path}"
    vocabulary = json.loads(path.read_text(encoding="utf-8"))["vocabulary"]["data"]
    missing = sorted(set(OWNER_SCOPES) - set(vocabulary))
    assert not missing, f"beta's deployed lock derives no {missing}"

    username = f"apg-s34-owner-{SWEEP}"
    password = secrets.token_urlsafe(24)
    user_id = _create_subject(
        psql, project_b, username=username, role="authenticated", scopes=OWNER_SCOPES,
        password=password,
    )  # fmt: skip
    try:
        yield {"user_id": user_id, "token": _login(api_call, beta_app, username, password)}
    finally:
        object_owner = project_b["database"]["roles"]["object_owner"]
        psql(
            project_b,
            f"DELETE FROM app.notes WHERE owner_id = '{user_id}' AND "
            f"(title LIKE '%{SWEEP}%' OR title = 'embedding arrived');",
            role=object_owner,
            claim=user_id,
        )


@pytest.fixture(scope="module")
def agents(
    project_b: dict[str, Any],
    event_owner: dict[str, str],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    beta_app: str,
) -> Iterator[dict[str, ProbeAgent]]:
    """Four agents owned by `event_owner`, each with scopes READ from the
    cluster, never typed: `inbox` and `digest` exactly their connector's
    `required_scopes` (the status document does not carry them, so the row is
    read), `waiter` exactly its definition's, `wide` the inbox's plus
    `tasks:write`."""
    owner = event_owner["user_id"]

    def connector_scopes(name: str) -> tuple[str, ...]:
        return _array(
            _one(
                psql,
                project_b,
                f"SELECT required_scopes FROM app_private.connector WHERE name = '{name}';",
            )
        )

    inbox_scopes = connector_scopes(INBOX)
    waiter_scopes = _array(
        _one(
            psql,
            project_b,
            "SELECT required_scopes FROM app_private.workflow_definition "
            f"WHERE name = '{WAITER}' AND version = 1;",
        )
    )
    assert inbox_scopes and waiter_scopes, "the connector or the definition is not installed"
    specs = {
        "inbox": ("agent_writer", inbox_scopes),
        "digest": ("agent_reader", connector_scopes(DIGEST)),
        "waiter": ("agent_writer", waiter_scopes),
        "wide": ("agent_writer", tuple(sorted({*inbox_scopes, "tasks:write"}))),
    }
    made = {
        label: _create_agent(
            psql, project_b, owner, label, api_call, beta_app, role=role, scopes=scopes
        )
        for label, (role, scopes) in specs.items()
    }
    try:
        yield made
    finally:
        for agent in made.values():
            _revoke(psql, project_b, agent.agent_id)


@pytest.fixture(scope="module")
def key_file(tmp_path_factory: pytest.TempPathFactory, project_b: dict[str, Any]) -> Iterator[Any]:
    """A connector's key, written by THE PRODUCT'S command as root (D1114,
    D1804), read, and the file deleted. Beta's installed manifest is the host
    checkout's `project.beta.yaml`; its project key is checked against the
    deployed document's before anything is derived."""
    import yaml

    manifest = REPO_ROOT / "project.beta.yaml"
    assert manifest.is_file(), f"{manifest} is not on this host; `key` derives from it"
    declared = yaml.safe_load(manifest.read_text(encoding="utf-8"))["project"]
    key = naming.project_key(declared["slug"], declared["environment"])
    assert key == project_b["project"]["key"], f"{manifest} is {key}, not beta"
    directory = tmp_path_factory.mktemp("connector-keys")
    written: list[Path] = []

    def read(name: str) -> str:
        output = directory / f"{name}.key"
        if not output.exists():
            result = subprocess.run(
                [
                    str(REPO_ROOT / "bin" / "connector.sh"), "key", "--project", str(manifest),
                    "--name", name, "--output", str(output),
                ],
                capture_output=True, text=True, check=False, timeout=60,
                stdin=subprocess.DEVNULL,
            )  # fmt: skip
            assert result.returncode == 0, f"key {name} exited {result.returncode}: {result.stderr}"
            written.append(output)
            value = output.read_text(encoding="ascii").strip()
            assert value not in result.stdout + result.stderr, "key printed the key"
        return output.read_text(encoding="ascii").strip()

    try:
        yield read
    finally:
        for path in written:
            path.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def sink(
    project_b: dict[str, Any], sh: Callable[..., str], sh_status: Callable[..., Any]
) -> Iterator[Callable[[], list[dict[str, Any]]]]:
    """D1809's receiver on beta's internal network, from beta's own auth image;
    yields a reader of its log, one parsed line per request."""
    compose_project = naming.compose_project_name(project_b["project"]["key"])
    auth = sh(
        "docker", "ps", "--filter", f"label=com.docker.compose.project={compose_project}",
        "--filter", "label=com.docker.compose.service=auth", "--format", "{{.Names}}",
    ).split()  # fmt: skip
    assert len(auth) == 1, f"beta runs {auth} as its auth container"
    image = sh("docker", "inspect", "-f", "{{.Config.Image}}", auth[0]).strip()
    # The DEPLOYED document carries no `compose` (a rendered-only member); it
    # names the project's internal network here. The first sweep's KeyError
    # (D1853) -- measured equal to the render's compose.networks.internal.
    network = project_b["edge"]["project_internal_network"]
    name = f"apg-s34-sink-{SWEEP}"
    sh(
        "docker", "run", "-d", "--rm", "--name", name, "--network", network,
        "--network-alias", SINK_ALIAS, "--entrypoint", "python3", image, "-c", SINK_SERVER,
    )  # fmt: skip

    def lines() -> list[dict[str, Any]]:
        code, out, _ = sh_status("docker", "logs", name)
        assert code == 0, f"the sink {name} is gone"
        return [json.loads(line) for line in out.splitlines() if line.startswith("{")]

    try:
        yield lines
    finally:
        sh_status("docker", "stop", name)


@contextmanager
def enabled(
    admin: dict[str, str], name: str, agent: ProbeAgent | None = None
) -> Iterator[subprocess.CompletedProcess[str]]:
    """Enable through `bin/connector.sh` -- the product's command -- and
    disable in `finally`, whatever the proof did in between."""
    result = connector_command(admin, "enable", name, agent=agent)
    assert result.returncode == 0, f"enable {name} exited {result.returncode}: {result.stderr}"
    try:
        yield result
    finally:
        connector_command(admin, "disable", name)


def connector_command(
    admin: dict[str, str], verb: str, name: str | None = None, agent: ProbeAgent | None = None
) -> subprocess.CompletedProcess[str]:
    arguments = [str(REPO_ROOT / "bin" / "connector.sh"), verb]
    if name is not None:
        arguments += ["--name", name, "--confirm", name]
    if agent is not None:
        arguments += ["--agent", agent.agent_id]
    arguments += ["--project-outputs", os.environ["APG_PROJECT_B_OUTPUTS"]]
    return subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env={**os.environ, "APG_API_TOKEN": admin["token"]},
        stdin=subprocess.DEVNULL,
    )


# ---------------------------------------------------------------------------
# Requests, notes, runs
# ---------------------------------------------------------------------------


def signed_headers(key_hex: str, body: bytes, *, delivery: str, t: int | None = None) -> dict:
    """This module's own HMAC over `<t>.<delivery>.<body>` (ADR 0237)."""
    t = int(time.time()) if t is None else t
    digest = hmac.new(
        bytes.fromhex(key_hex), f"{t}.{delivery}.".encode("ascii") + body, hashlib.sha256
    ).hexdigest()
    return {"X-Apg-Delivery": delivery, "X-Apg-Signature": f"t={t},v1={digest}"}


def inbound(
    api_call: Callable[..., Any], app: str, key_hex: str, body: dict[str, Any], **signing: Any
) -> tuple[Any, str]:
    """`(answer, delivery id)`: the response is frozen, so the id travels beside it."""
    raw = json.dumps(body).encode("utf-8")
    delivery = signing.pop("delivery", None) or str(uuid.uuid4())
    headers = signed_headers(key_hex, raw, delivery=delivery, **signing)
    answer = api_call(f"{app}/connectors/{INBOX}", method="POST", raw=raw, headers=headers)
    return answer, delivery


def _note(
    psql: Callable[..., tuple[int, str, str]], document: dict[str, Any], owner: str, label: str
) -> str:
    code, note_id, error = psql(
        document,
        f"INSERT INTO app.notes (owner_id, title, content) VALUES ('{owner}', "
        f"'apg-s34-{label}-{SWEEP}', 'session 34 connectivity probe') RETURNING id;",
    )
    assert code == 0 and note_id, f"could not create a note: {error}"
    return note_id.splitlines()[0]


def _embed(
    api_call: Callable[..., Any],
    rest: str,
    owner: dict[str, str],
    note_id: str,
) -> None:
    """The OWNER's direct write through PostgREST (D1721's path): the definer
    function emits `note_embedding.set@1` inside its own transaction."""
    answer = api_call(
        f"{rest}/rpc/set_note_embedding",
        method="POST",
        token=owner["token"],
        body={"p_note_id": note_id, "p_embedding": EMBEDDING},
    )
    assert answer.status == 200, f"set_note_embedding answered {answer.status}: {answer.body[:300]}"


def _run(api_call: Callable[..., Any], agent: ProbeAgent, run_id: str) -> dict[str, Any]:
    answer = api_call(f"{agent.app}/workflows/runs/{run_id}", token=agent.token())
    assert answer.status == 200, f"reading run {run_id} answered {answer.status}: {answer.body}"
    return json.loads(answer.body)


def _step(document: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in document["steps"] if s["name"] == name and s["phase"] == "forward")


def _runs_of(
    psql: Callable[..., tuple[int, str, str]], document: dict[str, Any], agent: ProbeAgent
) -> int:
    return int(
        _one(
            psql,
            document,
            f"SELECT count(*) FROM app_private.workflow_run WHERE agent_id = '{agent.agent_id}';",
        )
    )


def _receipts(
    psql: Callable[..., tuple[int, str, str]], document: dict[str, Any], delivery: str
) -> int:
    return int(
        _one(
            psql,
            document,
            f"SELECT count(*) FROM app_private.connector_receipt WHERE delivery_id = '{delivery}';",
        )
    )


def _verified(key_hex: str, line: dict[str, Any]) -> bool:
    """The sink's received request, verified by this module's own HMAC."""
    header = line.get("signature") or ""
    parts = dict(part.split("=", 1) for part in header.split(",") if "=" in part)
    expected = hmac.new(
        bytes.fromhex(key_hex),
        f"{parts.get('t')}.{line.get('delivery')}.".encode("ascii") + line["body"].encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, parts.get("v1", ""))


def _for_note(lines: list[dict[str, Any]], path: str, note_id: str) -> list[dict[str, Any]]:
    found = []
    for line in lines:
        if line.get("path") != path:
            continue
        try:
            body = json.loads(line["body"])
        except ValueError:
            continue
        if (body.get("payload") or {}).get("note_id") == note_id:
            found.append(line)
    return found


# ---------------------------------------------------------------------------
# CONN-IN-002 -- a signed request starts one run as the bound agent
# ---------------------------------------------------------------------------


def test_a_signed_request_creates_one_note_as_the_bound_agent(
    project_b: dict[str, Any],
    connectors_admin: dict[str, str],
    event_owner: dict[str, str],
    agents: dict[str, ProbeAgent],
    key_file: Any,
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    beta_app: str,
) -> None:
    title = f"apg-s34-inbox-{SWEEP}"
    with enabled(connectors_admin, INBOX, agents["inbox"]):
        answer, _ = inbound(
            api_call, beta_app, key_file(INBOX), {"title": title, "content": "signed and sent"}
        )
        assert answer.status == 202, f"{answer.status}: {answer.body[:300]}"
        run_id = json.loads(answer.body)["run_id"]
        final = _until(
            lambda: _run(api_call, agents["inbox"], run_id),
            lambda document: document["status"] in TERMINAL,
            RUN_SECONDS,
            "the inbound run's end",
        )
    assert final["status"] == "succeeded", json.dumps(final)[:1500]
    agent_of_run = _one(
        psql, project_b, f"SELECT agent_id FROM app_private.workflow_run WHERE id = '{run_id}';"
    )
    assert agent_of_run == agents["inbox"].agent_id
    notes = _one(
        psql,
        project_b,
        f"SELECT count(*) FROM app.notes WHERE owner_id = '{event_owner['user_id']}' "
        f"AND title = '{title}';",
    )
    assert notes == "1", f"{notes} notes carry the signed title"


def test_a_wrongly_signed_request_leaves_no_receipt_and_no_run(
    project_b: dict[str, Any],
    connectors_admin: dict[str, str],
    agents: dict[str, ProbeAgent],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    beta_app: str,
) -> None:
    wrong = secrets.token_hex(32)
    with enabled(connectors_admin, INBOX, agents["inbox"]):
        before = _runs_of(psql, project_b, agents["inbox"])
        answer, delivery = inbound(
            api_call, beta_app, wrong, {"title": f"apg-s34-forged-{SWEEP}", "content": "x"}
        )
        assert answer.status == 401, f"{answer.status}: {answer.body[:300]}"
        assert json.loads(answer.body) == {"error": "signature_invalid"}
        assert _receipts(psql, project_b, delivery) == 0
        assert _runs_of(psql, project_b, agents["inbox"]) == before


def test_a_replayed_delivery_is_refused_once(
    project_b: dict[str, Any],
    connectors_admin: dict[str, str],
    agents: dict[str, ProbeAgent],
    key_file: Any,
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    beta_app: str,
) -> None:
    body = {"title": f"apg-s34-replayed-{SWEEP}", "content": "once"}
    delivery = str(uuid.uuid4())
    with enabled(connectors_admin, INBOX, agents["inbox"]):
        before = _runs_of(psql, project_b, agents["inbox"])
        first, _ = inbound(api_call, beta_app, key_file(INBOX), body, delivery=delivery)
        assert first.status == 202, f"{first.status}: {first.body[:300]}"
        again, _ = inbound(api_call, beta_app, key_file(INBOX), body, delivery=delivery)
        assert again.status == 409, f"{again.status}: {again.body[:300]}"
        assert json.loads(again.body) == {"error": "delivery_replayed"}
        assert _receipts(psql, project_b, delivery) == 1
        assert _runs_of(psql, project_b, agents["inbox"]) == before + 1


def test_a_stale_timestamp_is_refused(
    connectors_admin: dict[str, str],
    agents: dict[str, ProbeAgent],
    key_file: Any,
    api_call: Callable[..., Any],
    beta_app: str,
) -> None:
    body = {"title": f"apg-s34-stale-{SWEEP}", "content": "x"}
    with enabled(connectors_admin, INBOX, agents["inbox"]):
        answer, _ = inbound(api_call, beta_app, key_file(INBOX), body, t=int(time.time()) - 600)
    assert answer.status == 401, f"{answer.status}: {answer.body[:300]}"
    assert json.loads(answer.body) == {"error": "signature_invalid"}


def test_a_disabled_connector_refuses_after_the_signature(
    project_b: dict[str, Any],
    connectors_admin: dict[str, str],
    key_file: Any,
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    beta_app: str,
) -> None:
    """Disabled is answered only to a SIGNED request; an unsigned one is the 401."""
    connector_command(connectors_admin, "disable", INBOX)
    body = {"title": f"apg-s34-disabled-{SWEEP}", "content": "x"}
    signed, delivery = inbound(api_call, beta_app, key_file(INBOX), body)
    assert signed.status == 409, f"{signed.status}: {signed.body[:300]}"
    assert json.loads(signed.body) == {"error": "connector_disabled"}
    assert _receipts(psql, project_b, delivery) == 0
    unsigned, _ = inbound(api_call, beta_app, secrets.token_hex(32), body)
    assert unsigned.status == 401


def test_an_over_scoped_agent_cannot_be_bound(
    project_b: dict[str, Any],
    connectors_admin: dict[str, str],
    agents: dict[str, ProbeAgent],
    psql: Callable[..., tuple[int, str, str]],
) -> None:
    result = connector_command(connectors_admin, "enable", INBOX, agent=agents["wide"])
    assert result.returncode == 5, (result.returncode, result.stdout, result.stderr)
    assert "agent_scopes_differ" in result.stderr
    enabled_now = _one(
        psql, project_b, f"SELECT enabled FROM app_private.connector WHERE name = '{INBOX}';"
    )
    assert enabled_now == "f"


def test_the_project_without_the_facility_has_no_connector(
    project_a: dict[str, Any],
    facility_on: None,
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
) -> None:
    raw = json.dumps({"title": "x", "content": "x"}).encode("utf-8")
    headers = signed_headers(secrets.token_hex(32), raw, delivery=str(uuid.uuid4()))
    answer = api_call(
        f"{app_base(project_a)}/connectors/{INBOX}", method="POST", raw=raw, headers=headers
    )
    assert answer.status == 404, f"{answer.status}: {answer.body[:300]}"
    assert json.loads(answer.body) == {"error": "no_such_connector"}


# ---------------------------------------------------------------------------
# CONN-OUT-002 -- an owner's write, delivered once and signed; a dead letter
# ---------------------------------------------------------------------------


def test_an_owners_write_is_delivered_once_and_signed(
    project_b: dict[str, Any],
    connectors_admin: dict[str, str],
    event_owner: dict[str, str],
    key_file: Any,
    sink: Callable[[], list[dict[str, Any]]],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    rest_base: Callable[[dict[str, Any]], str],
) -> None:
    note = _note(psql, project_b, event_owner["user_id"], "delivered")
    with enabled(connectors_admin, EMBEDDED):
        _embed(api_call, rest_base(project_b), event_owner, note)
        received = _until(
            lambda: _for_note(sink(), "/ok", note), bool, RUN_SECONDS, "the delivery to /ok"
        )
        time.sleep(12)  # two more polls: a second delivery would have arrived
        received = _for_note(sink(), "/ok", note)
    assert len(received) == 1, f"{len(received)} deliveries of one event: {received}"
    (line,) = received
    assert line["event"] == "note_embedding.set@1"
    assert _verified(key_file(EMBEDDED), line), "the delivery's signature does not verify"
    assert json.loads(line["body"])["payload"] == {"note_id": note}


def test_a_failing_endpoint_is_retried_to_max_then_dead_lettered(
    project_b: dict[str, Any],
    connectors_admin: dict[str, str],
    event_owner: dict[str, str],
    sink: Callable[[], list[dict[str, Any]]],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    rest_base: Callable[[dict[str, Any]], str],
) -> None:
    note = _note(psql, project_b, event_owner["user_id"], "deadletter")
    with enabled(connectors_admin, DEADLETTER):
        _embed(api_call, rest_base(project_b), event_owner, note)
        attempts = _until(
            lambda: _for_note(sink(), "/fail", note),
            lambda found: len(found) >= 3,
            DEAD_LETTER_SECONDS,
            "three attempts at /fail",
        )
        time.sleep(12)
        attempts = _for_note(sink(), "/fail", note)
        status = _until(
            lambda: connector_command(connectors_admin, "status"),
            lambda result: result.returncode == 0 and '"http_500"' in result.stdout,
            30,
            "the dead letter in the status",
        )
    assert len(attempts) == 3, f"{len(attempts)} attempts: {attempts}"
    assert len({line["delivery"] for line in attempts}) == 1, "one delivery, three attempts"
    times = sorted(line["at"] for line in attempts)
    spacing = [later - earlier for earlier, later in itertools.pairwise(times)]
    assert all(gap >= 2 for gap in spacing), f"attempts {spacing}s apart, under the backoff"
    document = json.loads(status.stdout)
    (entry,) = [c for c in document["connectors"] if c["name"] == DEADLETTER]
    dead = [d for d in entry["dead_letters"] if d["delivery_id"] == attempts[0]["delivery"]]
    assert dead and dead[0]["last_error"] == "http_500" and dead[0]["attempts"] == 3, entry
    assert SINK_ALIAS not in status.stdout and note not in status.stdout


def test_nothing_is_recorded_when_nothing_listens_on_the_deployment(
    project_b: dict[str, Any],
    connectors_admin: dict[str, str],
    event_owner: dict[str, str],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    rest_base: Callable[[dict[str, Any]], str],
) -> None:
    for name in (EMBEDDED, DEADLETTER):
        connector_command(connectors_admin, "disable", name)
    note = _note(psql, project_b, event_owner["user_id"], "unheard")
    _embed(api_call, rest_base(project_b), event_owner, note)
    events = _one(
        psql,
        project_b,
        f"SELECT count(*) FROM app_private.connector_event WHERE payload ->> 'note_id' = '{note}';",
    )
    assert events == "0", f"{events} events recorded with nothing listening"


# ---------------------------------------------------------------------------
# EVT-WAIT-002 -- a run waits for its owner's matching event
# ---------------------------------------------------------------------------


def _await_run(
    api_call: Callable[..., Any], agent: ProbeAgent, note: str
) -> tuple[str, dict[str, Any]]:
    answer = api_call(
        f"{agent.app}/workflows/runs",
        method="POST",
        token=agent.token(),
        body={"name": WAITER, "version": 1, "input": {"note_id": note}, "dry_run": False},
    )
    assert answer.status == 201, f"enqueueing {WAITER} answered {answer.status}: {answer.body}"
    run_id = json.loads(answer.body)["run_id"]
    parked = _until(
        lambda: _run(api_call, agent, run_id),
        lambda document: (
            _step(document, "embedded")["status"] == "parked" or document["status"] in TERMINAL
        ),
        RUN_SECONDS,
        "the event wait's park",
    )
    assert _step(parked, "embedded")["status"] == "parked", json.dumps(parked)[:1500]
    return run_id, parked


def test_a_waiting_run_resumes_on_its_owners_matching_write(
    project_b: dict[str, Any],
    event_owner: dict[str, str],
    agents: dict[str, ProbeAgent],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    rest_base: Callable[[dict[str, Any]], str],
) -> None:
    note = _note(psql, project_b, event_owner["user_id"], "awaited")
    run_id, _ = _await_run(api_call, agents["waiter"], note)
    _embed(api_call, rest_base(project_b), event_owner, note)
    final = _until(
        lambda: _run(api_call, agents["waiter"], run_id),
        lambda document: document["status"] in TERMINAL,
        RUN_SECONDS,
        "the resumed run's end",
    )
    assert final["status"] == "succeeded", json.dumps(final)[:1500]
    step = _step(final, "embedded")
    assert step["outcome"] == "succeeded", step
    assert step["reason"] == "event_received", step
    assert (step.get("result") or {}).get("payload", {}).get("note_id") == note, step


def test_an_event_that_does_not_match_leaves_the_run_parked(
    project_b: dict[str, Any],
    event_owner: dict[str, str],
    agents: dict[str, ProbeAgent],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    rest_base: Callable[[dict[str, Any]], str],
) -> None:
    awaited = _note(psql, project_b, event_owner["user_id"], "awaited-other")
    other = _note(psql, project_b, event_owner["user_id"], "other")
    run_id, _ = _await_run(api_call, agents["waiter"], awaited)
    try:
        _embed(api_call, rest_base(project_b), event_owner, other)
        time.sleep(UNMATCHED_SECONDS)
        still = _run(api_call, agents["waiter"], run_id)
        assert _step(still, "embedded")["status"] == "parked", json.dumps(still)[:1500]
        assert still["status"] not in TERMINAL
    finally:
        api_call(
            f"{agents['waiter'].app}/workflows/runs/{run_id}/cancel",
            method="POST",
            token=agents["waiter"].token(),
        )


# ---------------------------------------------------------------------------
# CONN-SCHED-002 -- a schedule starts runs as its agent; disabling stops it
# ---------------------------------------------------------------------------


def test_an_enabled_schedule_starts_a_run_and_disable_stops_it(
    project_b: dict[str, Any],
    connectors_admin: dict[str, str],
    agents: dict[str, ProbeAgent],
    psql: Callable[..., tuple[int, str, str]],
) -> None:
    digest = agents["digest"]

    def succeeded() -> int:
        return int(
            _one(
                psql,
                project_b,
                "SELECT count(*) FROM app_private.workflow_run r "
                "JOIN app_private.workflow_definition d ON d.id = r.definition_id "
                f"WHERE r.agent_id = '{digest.agent_id}' AND d.name = '{DIGEST}' "
                "AND r.status = 'succeeded';",
            )
        )

    with enabled(connectors_admin, DIGEST, digest):
        _until(succeeded, lambda count: count >= 1, SCHEDULE_SECONDS, "a scheduled run")
    next_fire = _one(
        psql,
        project_b,
        f"SELECT coalesce(next_fire_at::text, 'null') FROM app_private.connector "
        f"WHERE name = '{DIGEST}';",
    )
    assert next_fire == "null", f"a disabled schedule still fires at {next_fire}"
