"""Session 35's live halves: approval in the database, the proposed set, the bounded edge.

`AGT-APPROVE-004`, `GOV-APPLY-002`, `NODE-LIMIT-003` (ADR 0242-0245). Written at
the bump (Run 9) and gated on variables the Session 34 gate already exports --
no new environment gate (§2).

**None of this has executed before the trip.** Every proof reads the
deployment's own records -- the embeddings table as the superuser, the plane's
audit, the release directory's committed proposal, the project ledger, the
running containers' `HostConfig` -- and never what a command said it did
(D145: an exit code is not a state).

**Beta only for the approval and the set** (alpha applies no set of its own and
installs no definition); the edge is both projects' and is read once.

**AGT-APPROVE-004 is proved by the DATABASE refusing an agent** (ADR 0242): the
agent's own token reaches `api.set_note_embedding` through PostgREST, where no
plane sits, and the guard 0004 installed first refuses it `PT403` with nothing
written -- read as the superuser, not from the answer. The owner's direct call
passes the guard's human branch; the approved call passes its claim branch.
Session 33's and 34's live claims, which call the same function as the owner and
through an approval, passing again on 1.13.0 is the rest of this claim's
evidence (§7).

**GOV-APPLY-002 reads the deployment AFTER beta's deploy** (D1936): the set is
fully applied, so `migrate.sh --runtime status` prints *not needed (nothing
pending)* -- the line that named the proposal at the act is deploy step 6's
(*proposal <digest16> admits them*), read from Sheet F3's transcript. What a
deployment can show afterwards is that the set it applied is the set the
committed proposal names, and that the release it was applied from carries that
proposal and its approval.

**What these proofs leave behind, deliberately** (D1700): the probe agents,
REVOKED (their runs and audit rows reference them), and their owner; the
approver if an approval's `decided_by` holds it. Notes and tasks are deleted.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import subprocess
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import (
    REPO_ROOT,
    capacity_probe,
    deployed_output,
    host_config,
    rendering,
    runtime_override,
)

# ruff: noqa: S608 -- every interpolated value is a uuid this module generated or
# read back from the cluster, or a role name from a deployed document the
# outputs schema validated. The same waiver every deployment module carries.

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST",
        "APG_PROJECT_A_OUTPUTS",
        "APG_PROJECT_B_OUTPUTS",
    ),
]

#: The owner's tenant scopes: `tasks-approval`'s -- tasks for its forward steps
#: and compensation, note embeddings for the gated step (Session 33's set).
OWNER_SCOPES = (
    "note_embeddings:read",
    "note_embeddings:write",
    "notes:read",
    "notes:write",
    "tasks:read",
    "tasks:write",
)

#: Every probe agent holds the owner's six and `meta:read`.
AGENT_SCOPES = ("meta:read", *OWNER_SCOPES)

#: A suffix unique to this sweep, in every name, title and key (D1700).
SWEEP = secrets.token_hex(4)

GATED = "set_note_embedding"
APPROVAL = "tasks-approval"
APPROVAL_STEP = "set_the_embedding"
TERMINAL = frozenset({"succeeded", "failed", "cancelled", "stopped"})
PARKED_SECONDS = 60
RUN_SECONDS = 120

#: The guard's one refusal (0037, rig 35a): SQLSTATE `PT403`, PostgREST's 403.
REFUSAL = ("PT403", "AP403: approval_required")

#: The text literal of 768 zeros -- rig 33b's measured shape; the plane types
#: `p_embedding` as a string (D1894).
EMBEDDING = "[" + ",".join(["0"] * 768) + "]"

#: The edge's two services, each once (ADR 0244).
EDGE_SERVICES = ("traefik", "docker-socket-proxy")


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
        f"'{username}', 'Session 35 governance probe', "
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
    """An `agent_writer` on one project and a way to get a fresh token."""

    def __init__(
        self,
        agent_id: str,
        secret: str,
        owner_id: str,
        api_call: Callable[..., Any],
        app: str,
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
) -> ProbeAgent:
    from agentic_postgres import service_source

    hashing = service_source.load("hashing")
    secret = secrets.token_urlsafe(24)
    name = f"apg-s35-{label}-{SWEEP}"
    array = ", ".join(f"'{scope}'" for scope in sorted(AGENT_SCOPES))
    code, agent_id, error = psql(
        document,
        "SELECT app_private.auth_create_agent("
        f"'{name}', 'Session 35 governance probe', "
        f"'{document['database']['roles']['agent_writer']}', ARRAY[{array}]::text[], "
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
    read: Callable[[], dict[str, Any]],
    predicate: Callable[[dict[str, Any]], bool],
    seconds: float,
    what: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + seconds
    document = read()
    while not predicate(document):
        if time.monotonic() > deadline:
            pytest.fail(
                f"{what} not reached within {seconds:.0f}s; "
                f"last read: {json.dumps(document)[:1500]}"
            )
        time.sleep(2)
        document = read()
    return document


def _audit(
    psql: Callable[..., tuple[int, str, str]], document: dict[str, Any], where: str
) -> list[dict[str, Any]]:
    code, out, error = psql(
        document,
        "SELECT coalesce(json_agg(row_to_json(r) ORDER BY r.started_at), '[]'::json) FROM ("
        "SELECT source::text, agent_id::text, tool, request_id::text, outcome::text, "
        f"denial_reason::text, started_at FROM app_private.agent_audit WHERE {where}) r;",
    )
    assert code == 0, f"could not read the audit record: {error}"
    return json.loads(out)


def _embeddings(
    psql: Callable[..., tuple[int, str, str]], document: dict[str, Any], note_id: str
) -> int:
    """Counted as the SUPERUSER, never read from an answer."""
    code, out, error = psql(
        document, f"SELECT count(*) FROM app.note_embeddings WHERE note_id = '{note_id}';"
    )
    assert code == 0, error
    return int(out)


def _embed(
    api_call: Callable[..., Any],
    rest: str,
    token: str,
    note_id: str,
    headers: dict[str, str] | None = None,
) -> Any:
    """`test_session34_connectivity.py`'s direct write, returning the answer
    unjudged so a refusal can be read."""
    return api_call(
        f"{rest}/rpc/{GATED}",
        method="POST",
        token=token,
        body={"p_note_id": note_id, "p_embedding": EMBEDDING},
        headers=headers,
    )


# ---------------------------------------------------------------------------
# The principals
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def beta_app(project_b: dict[str, Any], app_base: Callable[[dict[str, Any]], str]) -> str:
    return app_base(project_b)


@pytest.fixture(scope="module")
def beta_rest(project_b: dict[str, Any], rest_base: Callable[[dict[str, Any]], str]) -> str:
    return rest_base(project_b)


@pytest.fixture(scope="module")
def gate_owner(
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    beta_app: str,
) -> Iterator[dict[str, str]]:
    """The human the probe agents belong to, logged in. **Beta's deployed lock
    is read first**: a lock that derives no `note_embeddings:*` is a deployment
    these proofs cannot speak about, said by name. Left at teardown because its
    agents are (D1700)."""
    path = (
        deployed_output.rendered_path(project_b["project"]["key"])
        / runtime_override.MCP_LOCK_FILENAME
    )
    assert path.is_file(), f"no capability lock at {path}; the deploy did not compile one"
    vocabulary = json.loads(path.read_text(encoding="utf-8"))["vocabulary"]["data"]
    missing = sorted(set(OWNER_SCOPES) - set(vocabulary))
    assert not missing, f"beta's deployed lock derives no {missing}; these proofs need them"

    username = f"apg-s35-owner-{SWEEP}"
    password = secrets.token_urlsafe(24)
    user_id = _create_subject(
        psql, project_b, username=username, role="authenticated", scopes=OWNER_SCOPES,
        password=password,
    )  # fmt: skip
    yield {"user_id": user_id, "token": _login(api_call, beta_app, username, password)}


@pytest.fixture(scope="module")
def approver(
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    beta_app: str,
) -> Iterator[dict[str, str]]:
    """A SECOND user holding `admin_workflows:approve`. Deleted at teardown if
    the database allows it -- an approval's `decided_by` references it."""
    username = f"apg-s35-approver-{SWEEP}"
    password = secrets.token_urlsafe(24)
    user_id = _create_subject(
        psql, project_b, username=username, role="project_admin",
        scopes=("admin_audit:read", "admin_workflows:approve"), password=password,
    )  # fmt: skip
    try:
        yield {"user_id": user_id, "token": _login(api_call, beta_app, username, password)}
    finally:
        code, _, error = psql(project_b, f"DELETE FROM app_private.users WHERE id = '{user_id}';")
        if code != 0:
            print(f"the approver {username} is LEFT (D1700's shape for humans): {error[:200]}")


@pytest.fixture(scope="module")
def gate_agents(
    project_b: dict[str, Any],
    gate_owner: dict[str, str],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    beta_app: str,
) -> Iterator[dict[str, ProbeAgent]]:
    """Two agents, one per concern, so no proof reads another's audit rows:
    `direct` calls the gated RPC itself; `approve` runs `tasks-approval`."""
    agents = {
        label: _create_agent(psql, project_b, gate_owner["user_id"], label, api_call, beta_app)
        for label in ("direct", "approve")
    }
    try:
        yield agents
    finally:
        for agent in agents.values():
            _revoke(psql, project_b, agent.agent_id)
        object_owner = project_b["database"]["roles"]["object_owner"]
        owner = gate_owner["user_id"]
        for table in ("app.tasks", "app.notes"):
            psql(
                project_b,
                f"DELETE FROM {table} WHERE owner_id = '{owner}' AND title LIKE '%{SWEEP}%';",
                role=object_owner,
                claim=owner,
            )


# ---------------------------------------------------------------------------
# AGT-APPROVE-004 -- the database refuses an agent's direct call
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def direct_calls(
    project_b: dict[str, Any],
    gate_owner: dict[str, str],
    gate_agents: dict[str, ProbeAgent],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    beta_rest: str,
) -> dict[str, Any]:
    """In order, on ONE note the owner created through the product's own RPC:
    the agent's own token calls the gated RPC (with a well-formed key, so the
    guard and not the key's shape decides), the embeddings are counted, then
    the owner calls it and they are counted again."""
    created = api_call(
        f"{beta_rest}/rpc/create_note",
        method="POST",
        token=gate_owner["token"],
        body={"p_title": f"apg-s35-direct-{SWEEP}", "p_content": "session 35 governance probe"},
    )
    assert created.status == 200, f"the owner could not create a note: {created.body[:300]}"
    note_id = json.loads(created.body)["id"]
    by_agent = _embed(
        api_call, beta_rest, gate_agents["direct"].token(), note_id,
        headers={"Idempotency-Key": f"apg-s35-direct-{SWEEP}"},
    )  # fmt: skip
    after_agent = _embeddings(psql, project_b, note_id)
    by_owner = _embed(api_call, beta_rest, gate_owner["token"], note_id)
    after_owner = _embeddings(psql, project_b, note_id)
    return {
        "note_id": note_id,
        "by_agent": by_agent,
        "after_agent": after_agent,
        "by_owner": by_owner,
        "after_owner": after_owner,
    }


def test_an_agents_direct_call_to_a_gated_rpc_is_refused_by_the_database(
    direct_calls: dict[str, Any],
) -> None:
    """D1721 closed on the deployment: an agent holding `note_embeddings:write`
    reaches `api.set_note_embedding` through PostgREST -- no plane on the path
    -- and the GUARD refuses it, 403 with 0037's one sentence, and the cluster
    holds no embedding for the note afterwards."""
    answer = direct_calls["by_agent"]
    assert answer.status == 403, f"{answer.status}: {answer.body[:400]}"
    body = json.loads(answer.body)
    assert (body.get("code"), body.get("message")) == REFUSAL, body
    assert direct_calls["after_agent"] == 0, (
        f"the refused call wrote {direct_calls['after_agent']} embedding(s) for "
        f"{direct_calls['note_id']}: the guard ran after the write, or not at all"
    )


def test_the_owners_direct_call_is_served(direct_calls: dict[str, Any]) -> None:
    """The guard's human branch: the note's owner calls the same function on
    the same note and is served, and exactly one embedding now exists -- so
    the refusal above was the guard's decision about an AGENT, not a broken
    function."""
    answer = direct_calls["by_owner"]
    assert answer.status == 200, f"{answer.status}: {answer.body[:400]}"
    assert direct_calls["after_owner"] == 1, direct_calls


@pytest.fixture(scope="module")
def approved_run(
    project_b: dict[str, Any],
    gate_agents: dict[str, ProbeAgent],
    approver: dict[str, str],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    beta_app: str,
) -> dict[str, Any]:
    """Session 33's `approved_run`, reduced to its one path: `tasks-approval`
    parks on the plane's refusal, a second user approves, the run ends."""
    agent = gate_agents["approve"]
    code, task_id, error = psql(
        project_b,
        f"INSERT INTO app.tasks (owner_id, title) VALUES ('{agent.owner_id}', "
        f"'apg-s35-approved-{SWEEP}') RETURNING id;",
    )
    assert code == 0 and task_id, f"could not create a task: {error}"
    code, note_id, error = psql(
        project_b,
        f"INSERT INTO app.notes (owner_id, title, content) VALUES ('{agent.owner_id}', "
        f"'apg-s35-approved-{SWEEP}', 'session 35 governance probe') RETURNING id;",
    )
    assert code == 0 and note_id, f"could not create a note: {error}"
    rows = {"task_id": task_id.splitlines()[0], "note_id": note_id.splitlines()[0]}
    started = api_call(
        f"{agent.app}/workflows/runs",
        method="POST",
        token=agent.token(),
        body={"name": APPROVAL, "version": 1, "input": {**rows, "embedding": EMBEDDING},
              "dry_run": False},
    )  # fmt: skip
    assert started.status == 201, f"enqueueing {APPROVAL} answered {started.status}: {started.body}"
    run_id = json.loads(started.body)["run_id"]

    def status() -> dict[str, Any]:
        answer = api_call(f"{agent.app}/workflows/runs/{run_id}", token=agent.token())
        assert answer.status == 200, f"reading run {run_id} answered {answer.status}"
        return json.loads(answer.body)

    def step(document: dict[str, Any]) -> dict[str, Any]:
        return next(
            s for s in document["steps"] if s["name"] == APPROVAL_STEP and s["phase"] == "forward"
        )

    def parked(document: dict[str, Any]) -> bool:
        if document["status"] in TERMINAL:
            return True
        current = step(document)
        return (
            current["status"] == "parked"
            and (current.get("approval") or {}).get("status") == "pending"
        )

    at_park = _until(status, parked, PARKED_SECONDS, "the approval park")
    decided = api_call(
        f"{beta_app}/admin/workflows/runs/{run_id}/approve",
        method="POST",
        token=approver["token"],
        body={"step": APPROVAL_STEP},
    )
    final = _until(status, lambda d: d["status"] in TERMINAL, RUN_SECONDS, "the approved run's end")
    return {"agent": agent, "rows": rows, "at_park": at_park, "decided": decided, "final": final}


def test_the_approved_call_through_the_plane_is_served_once(
    approved_run: dict[str, Any],
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
) -> None:
    """The guard's claim branch: the step token's `apg_approval` names the tool
    and the plane's `Idempotency-Key` equals its key, so the released call
    passes the database too -- the run succeeds, ONE embedding exists, and the
    plane's audit holds its refusal and then one `served` row."""
    assert approved_run["at_park"]["status"] == "running", json.dumps(approved_run["at_park"])[
        :1500
    ]
    decided = approved_run["decided"]
    assert decided.status == 200, f"{decided.status}: {decided.body[:300]}"
    final = approved_run["final"]
    assert final["status"] == "succeeded", json.dumps(final)[:2000]
    assert _embeddings(psql, project_b, approved_run["rows"]["note_id"]) == 1
    agent = approved_run["agent"].agent_id
    rows = _audit(psql, project_b, f"agent_id = '{agent}' AND tool = '{GATED}'")
    assert [(r["source"], r["outcome"]) for r in rows] == [
        ("agent_plane", "refused"),
        ("agent_plane", "served"),
    ], f"the approved write was not served exactly once after its refusal: {rows}"


# ---------------------------------------------------------------------------
# GOV-APPLY-002 -- the applied set is the proposed one
# ---------------------------------------------------------------------------


def test_the_applied_set_is_the_proposed_one(
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    as_root: None,
) -> None:
    """Four readings, each from a different authority (D1936):

    * the DEPLOYED document's `migrations.project_set.lock_sha256` equals the
      `set_digest` of the proposal committed in the RELEASE directory the
      document names (`runtime.release_path`, which ends in `source_commit`);
    * that release carries the approval beside it, naming the proposal file's
      own sha256 under a second declared name;
    * the project LEDGER's newest version is the proposal's newest;
    * `bin/migrate.sh --runtime status` over the installed manifest -- the
      product's own command, as root -- prints the set's proposal line, which
      on a fully applied set says nothing is pending.
    """
    block = project_b["migrations"]["project_set"]
    assert block is not None, f"{project_b['project']['key']} records no project set"
    digest = block["lock_sha256"]
    release = Path(project_b["runtime"]["release_path"])
    assert release.name == project_b["source_commit"], (release, project_b["source_commit"])
    proposals = release / block["root"] / "proposals"
    source = proposals / f"{digest}.json"
    assert source.is_file(), (
        f"the release {release.name[:12]} carries no proposal for the applied set {digest[:16]} "
        f"({sorted(p.name for p in proposals.glob('*'))})"
    )
    data = source.read_bytes()
    record = json.loads(data)
    assert record["set_digest"] == digest, (record["set_digest"], digest)

    approval = json.loads((proposals / f"{digest}.approval.json").read_text(encoding="utf-8"))
    assert approval["proposal_sha256"] == hashlib.sha256(data).hexdigest(), approval
    fold = " ".join(approval["declared_by"].split()).casefold()
    assert fold != " ".join(record["declared_by"].split()).casefold(), approval

    newest = max(entry["version"] for entry in record["set"]["versions"])
    code, out, error = psql(
        project_b, f"SELECT max(version)::text FROM {rendering.PROJECT_MIGRATIONS_TABLE};"
    )
    assert code == 0, error
    assert out.strip() == newest, f"the ledger's newest is {out.strip()!r}, the proposal's {newest}"

    manifest = deployed_output.PROJECT_STATE_ROOT / project_b["project"]["key"] / "manifest.yaml"
    assert manifest.is_file(), f"no installed manifest at {manifest}"
    status = subprocess.run(
        [str(REPO_ROOT / "bin" / "migrate.sh"), "--project", str(manifest), "--runtime", "status"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
        timeout=300,
    )
    assert status.returncode == 0, status.stdout[-2000:] + status.stderr[-2000:]
    line = f"migrate: proposal {digest[:16]}: not needed (nothing pending)"
    assert line in status.stdout.splitlines(), (
        f"status printed no {line!r}:\n{status.stdout[-2000:]}"
    )


# ---------------------------------------------------------------------------
# NODE-LIMIT-003 -- the bounded edge, and nothing unbounded, on the host
# ---------------------------------------------------------------------------


def _committed_edge_limits() -> dict[str, tuple[int, int, int]]:
    """`(Memory bytes, PidsLimit, NanoCpus)` per edge service, from the
    committed `infra/edge/compose.yaml` -- the values ADR 0244 records."""
    compose = yaml.safe_load((REPO_ROOT / "infra" / "edge" / "compose.yaml").read_text())
    limits = {}
    for name in EDGE_SERVICES:
        service = compose["services"][name]
        memory = str(service["mem_limit"])
        assert memory.endswith("m"), f"{name}'s mem_limit {memory!r} is not in MiB"
        limits[name] = (
            int(memory[:-1]) * 1024 * 1024,
            int(service["pids_limit"]),
            round(float(service["cpus"]) * 1_000_000_000),
        )
    return limits


def _run(*command: str, timeout: int = 30) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            list(command), capture_output=True, text=True, check=False,
            stdin=subprocess.DEVNULL, timeout=timeout,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return None


def test_the_edge_containers_are_bounded_on_the_host(as_root: None) -> None:
    """Each edge container RUNNING carries exactly the committed limits -- read
    from its `HostConfig`, so an edge never recreated after the release (Sheet
    F4a) reads 0 and fails here, which is the point."""
    expected = _committed_edge_limits()
    label = runtime_override.COMPOSE_PROJECT_LABEL
    for name in EDGE_SERVICES:
        listing = _run(
            "docker", "ps", "-q", "--filter", f"label={label}={host_config.EDGE_STACK_NAME}",
            "--filter", f"label=com.docker.compose.service={name}",
        )  # fmt: skip
        assert listing is not None and listing.returncode == 0, "docker ps did not answer"
        ids = listing.stdout.split()
        assert len(ids) == 1, (
            f"{len(ids)} running {name} container(s) in {host_config.EDGE_STACK_NAME}"
        )
        inspected = _run("docker", "inspect", "--format", "{{json .HostConfig}}", ids[0])
        assert inspected is not None and inspected.returncode == 0, f"docker inspect {name} failed"
        config = json.loads(inspected.stdout)
        observed = (config.get("Memory"), config.get("PidsLimit"), config.get("NanoCpus"))
        assert observed == expected[name], (
            f"{name} runs with Memory/PidsLimit/NanoCpus {observed}, the committed file says "
            f"{expected[name]}: the edge was not recreated after the release (Sheet F4a)"
        )


def test_no_running_compose_container_is_unbounded(as_root: None) -> None:
    """`doctor capacity`'s own reader (`capacity_probe.read_ceilings`) finds no
    running Compose container without a memory ceiling -- the threat model's
    *every long-running service* held on the host, both projects and the edge
    (D1878, D1900)."""
    _, unbounded, reason = capacity_probe.read_ceilings(_run)
    assert reason == "", f"the ceilings could not be read: {reason}"
    assert unbounded == (), f"running Compose containers with no memory ceiling: {list(unbounded)}"
