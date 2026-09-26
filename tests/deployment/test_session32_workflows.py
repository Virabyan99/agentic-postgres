"""Session 32's live halves: the durable step substrate, on a deployment.

`NODE-READ-003`, `WF-RUN-001`, `WF-RESUME-001`, `WF-REVOKE-001`. Written at the
bump (Run 7) and gated on variables the Session 31 gate already exports -- no
new environment gate (§2), so `bin/session-32-check.sh --mode host` accepts
exactly the flags Session 31's did.

**None of this has executed before the trip, and one proof here already found
a defect by being written** (D1696): the correlation join could not have
returned a row, because the plane mints its own request id and ignores the
one the loop sent (ADR 0160). The loop's first end-to-end rig ran against a
FAKE plane that believed what the loop believed. That is the reason every
proof below asserts against the deployed plane's own records -- the audit
table, the idempotency table, the notes table -- and never against what the
loop says it did.

**What only a deployment can prove:**

* that a run started through the published route is executed by the loop in
  the `auth` container, as the agent, against the `mcp` container, and every
  step lands in the plane's audit under the id the step row records;
* that a step replayed after a crash writes ONE row, proved by the
  idempotency table's `replay_count` and by the notes table -- not by any
  status (§7 item 1: a claim about a worker is a claim about at-least-once
  plus an idempotent upstream);
* that a run parked on a retry survives the death of the process holding the
  loop (`worker-restart`, ADR 0193) and resumes at attempt 2;
* that a revoked agent's run stops at its next step boundary and makes no
  call there.

**Beta only, with alpha as the control** (D1657): alpha declares no project
set and therefore installs no definition, so the same request there is
`no_such_workflow`.

**What these proofs leave behind, deliberately** (D1700). A run references
its agent (`workflow_run.agent_id`, no `ON DELETE`), so an agent with runs
cannot be deleted -- and the runs are the substrate's record, which
`REC-WF-001`'s drill then reads. So the probe agents are REVOKED at teardown
and left, under names unique to the sweep; their owner is a subject whose
password was random and never written down, and it stays because the agents
reference it. The notes and tasks the runs wrote are deleted, and so is the
administrator this module creates to revoke with.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, deployed_output, naming

# ruff: noqa: S608 -- every interpolated value is a uuid this module generated or
# read back from the cluster, or a role name from a deployed document the
# outputs schema validated. The same waiver every deployment module carries.

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST",
        "APG_HOST_MANIFEST",
        "APG_PROJECT_A_OUTPUTS",
        "APG_PROJECT_B_OUTPUTS",
        "APG_REHEARSAL_EVIDENCE_DIR",
    ),
]

#: What an MCP endpoint requires, measured (Session 8, rig 32b).
MCP_ACCEPT = "application/json, text/event-stream"

#: The scopes every probe agent here holds: both definitions' union, and
#: `meta:read`/`tasks:read` so the set matches the Session 9 writer's exactly
#: -- a scope set nobody has deployed before is a second variable.
AGENT_SCOPES = ("meta:read", "notes:read", "notes:write", "tasks:read", "tasks:write")

#: A suffix unique to this sweep. The agents are LEFT (D1700), so a fixed name
#: would collide with the previous sweep's under `agents_name_normalised_key`.
SWEEP = secrets.token_hex(4)

ROUNDTRIP = "notes-roundtrip"
RETRY = "notes-retry"
TERMINAL = frozenset({"succeeded", "failed", "cancelled", "stopped"})

#: How long a run may take to reach a terminal status. The loop polls every 5
#: s and three steps run back to back, so a healthy run finishes in about ten;
#: the ceiling is for a loop that is busy with another run's step.
RUN_SECONDS = 120

#: The parked run's ceiling: the rehearsal's own bound (120 s), the step's 45 s
#: backoff, and one poll interval either side.
PARKED_SECONDS = 240


def _definition(name: str) -> dict[str, Any]:
    """One of the example project's definitions, read from the checkout.

    Read rather than restated, because the crash-state proof must present
    EXACTLY the arguments the loop will: the fingerprint is over them, and a
    proof that retyped a title would be proving `PT412` instead of a replay.
    """
    path = REPO_ROOT / "projects" / "example" / "workflows" / f"{name}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _step(definition: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in definition["steps"] if step["name"] == name)


def _header(headers: dict[str, str], name: str) -> str | None:
    """A response header, case-insensitively: uvicorn sends them lowercased."""
    wanted = name.lower()
    return next((value for key, value in headers.items() if key.lower() == wanted), None)


def sse_result(body: str) -> dict[str, Any] | None:
    """The JSON-RPC message out of an SSE response; the last `data:` wins (D458)."""
    payload = None
    for line in body.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
    return payload


def refused(result: dict[str, Any]) -> bool:
    """A refusal, read both ways (D509, D1414, D1672)."""
    return "error" in result or bool(result.get("result", {}).get("isError"))


# ---------------------------------------------------------------------------
# Subjects and agents
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
        f"'{username}', 'Session 32 workflow probe', "
        f"'{document['database']['roles'][role]}', ARRAY[{array}]::text[], "
        f"'{hashing.Hasher().hash(password)}');",
    )
    assert code == 0 and user_id, f"could not create {username}: {error}"
    return user_id


class ProbeAgent:
    """An `agent_writer` on one project and a way to get a fresh token.

    A token is minted per use rather than held: the module outlives the
    930-second TTL when the rehearsal arm runs, and a proof that failed on an
    expired token would be reporting its own duration.
    """

    def __init__(
        self,
        document: dict[str, Any],
        agent_id: str,
        secret: str,
        owner_id: str,
        api_call: Callable[..., Any],
        app: str,
    ) -> None:
        self.document = document
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
    name = f"apg-s32-{label}-{SWEEP}"
    array = ", ".join(f"'{scope}'" for scope in sorted(AGENT_SCOPES))
    code, agent_id, error = psql(
        document,
        "SELECT app_private.auth_create_agent("
        f"'{name}', 'Session 32 workflow probe', "
        f"'{document['database']['roles']['agent_writer']}', ARRAY[{array}]::text[], "
        f"'{owner_id}', '{hashing.Hasher().hash(secret)}', NULL);",
    )
    assert code == 0 and agent_id, f"could not create the probe agent {name}: {error}"
    return ProbeAgent(document, agent_id, secret, owner_id, api_call, app)


@pytest.fixture(scope="module")
def beta_owner(
    project_b: dict[str, Any], psql: Callable[..., tuple[int, str, str]]
) -> Iterator[str]:
    """The human the beta probe agents belong to (ADR 0117: an agent acts as
    its OWNER). Its password is random and never recorded, so the subject left
    behind by D1700 is one nobody can log in as."""
    owner = _create_subject(
        psql,
        project_b,
        username=f"apg-s32-owner-{SWEEP}",
        role="authenticated",
        scopes=("notes:read", "notes:write", "tasks:read", "tasks:write"),
        password=secrets.token_urlsafe(24),
    )
    try:
        yield owner
    finally:
        object_owner = project_b["database"]["roles"]["object_owner"]
        for table in ("app.tasks", "app.notes"):
            psql(
                project_b,
                f"DELETE FROM {table} WHERE owner_id = '{owner}';",
                role=object_owner,
                claim=owner,
            )


@pytest.fixture(scope="module")
def beta_agents(
    project_b: dict[str, Any],
    beta_owner: str,
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
) -> Iterator[dict[str, ProbeAgent]]:
    """Four agents, one per concern, so no proof reads another's audit rows.

    `notes` runs the round trip, the dry run and the constructed crash;
    `retry` is parked under the rehearsal; `revocable` is revoked mid-run;
    `control` is `revocable`'s twin and is not.
    """
    app = app_base(project_b)
    agents = {
        label: _create_agent(psql, project_b, beta_owner, label, api_call, app)
        for label in ("notes", "retry", "revocable", "control")
    }
    try:
        yield agents
    finally:
        # REVOKED, not deleted (D1700): their runs reference them.
        for agent in agents.values():
            psql(
                project_b,
                "UPDATE app_private.agents SET status = 'revoked', "
                "authz_version = authz_version + 1, updated_at = now() "
                f"WHERE id = '{agent.agent_id}';",
            )


@pytest.fixture(scope="module")
def beta_admin(
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
) -> Iterator[str]:
    """A `project_admin` holding `admin_agents:write` on beta -- what revokes.

    Through the product's own route (`PATCH /admin/agents/{id}`), the Session 9
    revocation proof's shape: a proof reaching the revoked state by an UPDATE
    would prove the state is reachable, not that the product reaches it.
    Deleted at teardown; it owns nothing.
    """
    username = f"apg-s32-admin-{SWEEP}"
    password = secrets.token_urlsafe(24)
    _create_subject(
        psql,
        project_b,
        username=username,
        role="project_admin",
        scopes=("admin_agents:read", "admin_agents:write"),
        password=password,
    )
    try:
        answer = api_call(
            f"{app_base(project_b)}/auth/login",
            method="POST",
            body={"username": username, "password": password},
        )
        assert answer.status == 200, f"the admin probe could not log in: {answer.body[:200]}"
        yield json.loads(answer.body)["access_token"]
    finally:
        psql(project_b, f"DELETE FROM app_private.users WHERE username = '{username}';")


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def _enqueue(
    api_call: Callable[..., Any],
    agent: ProbeAgent,
    name: str,
    *,
    run_input: dict[str, Any] | None = None,
    dry_run: bool = False,
    token: str | None = None,
) -> Any:
    return api_call(
        f"{agent.app}/workflows/runs",
        method="POST",
        token=token or agent.token(),
        body={"name": name, "version": 1, "input": run_input or {}, "dry_run": dry_run},
    )


def _started(api_call: Callable[..., Any], agent: ProbeAgent, name: str, **kwargs: Any) -> str:
    answer = _enqueue(api_call, agent, name, **kwargs)
    assert answer.status == 201, f"enqueueing {name} answered {answer.status}: {answer.body[:300]}"
    started = json.loads(answer.body)
    assert started["status"] == "queued", started
    return started["run_id"]


def _status(api_call: Callable[..., Any], agent: ProbeAgent, run_id: str) -> dict[str, Any]:
    answer = api_call(f"{agent.app}/workflows/runs/{run_id}", token=agent.token())
    assert answer.status == 200, f"reading run {run_id} answered {answer.status}: {answer.body}"
    return json.loads(answer.body)


def _until(
    api_call: Callable[..., Any],
    agent: ProbeAgent,
    run_id: str,
    predicate: Callable[[dict[str, Any]], bool],
    seconds: float,
    *,
    every: float = 2.0,
    between: Callable[[], None] | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + seconds
    document = _status(api_call, agent, run_id)
    while not predicate(document):
        if time.monotonic() > deadline:
            pytest.fail(
                f"run {run_id} did not reach the expected state within {seconds:.0f}s; "
                f"last read: {json.dumps(document)[:1500]}"
            )
        if between is not None:
            between()
        time.sleep(every)
        document = _status(api_call, agent, run_id)
    return document


def _terminal(document: dict[str, Any]) -> bool:
    return document["status"] in TERMINAL


def _audit(
    psql: Callable[..., tuple[int, str, str]], document: dict[str, Any], where: str
) -> list[dict[str, Any]]:
    code, out, error = psql(
        document,
        "SELECT coalesce(json_agg(row_to_json(r) ORDER BY r.started_at), '[]'::json) FROM ("
        "SELECT source::text, agent_id::text, tool, request_id::text, outcome::text, "
        f"started_at FROM app_private.agent_audit WHERE {where}) r;",
    )
    assert code == 0, f"could not read the audit record: {error}"
    return json.loads(out)


def _backends(psql: Callable[..., tuple[int, str, str]], document: dict[str, Any]) -> int:
    role = document["database"]["roles"]["auth_service"]
    code, out, error = psql(
        document, f"SELECT count(*) FROM pg_stat_activity WHERE usename = '{role}';"
    )
    assert code == 0, f"could not read pg_stat_activity: {error}"
    return int(out)


@pytest.fixture(scope="module")
def roundtrip(
    project_b: dict[str, Any],
    beta_agents: dict[str, ProbeAgent],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
) -> dict[str, Any]:
    """One three-step run as `notes`, with the auth role's backends SAMPLED
    throughout -- every ~200 ms on a thread, so the ceiling is read during the
    run rather than on either side of it."""
    agent = beta_agents["notes"]
    samples: list[int] = []
    stop = threading.Event()

    def sample() -> None:
        while not stop.is_set():
            samples.append(_backends(psql, project_b))
            stop.wait(0.2)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    try:
        run_id = _started(api_call, agent, ROUNDTRIP)
        document = _until(api_call, agent, run_id, _terminal, RUN_SECONDS)
    finally:
        stop.set()
        sampler.join(timeout=30)
    return {"run_id": run_id, "document": document, "samples": samples, "agent": agent}


# ---------------------------------------------------------------------------
# NODE-READ-003 -- the ceilings count the database, on this host
# ---------------------------------------------------------------------------


def test_the_ceilings_on_this_host_count_the_database(as_root: None) -> None:
    """**D1636 closed on production.**

    Session 31's reading printed 2,944 MiB because it grouped by
    `apg.project.key`, which `postgres` and `pgbouncer` do not carry, and
    dropped them -- under-reporting by the largest cap on the host, in the
    reassuring direction. Run 2 groups by Compose's own project label.

    **The expectation is measured here, not written down** (D1701): the plan's
    `2240` per key and `4480` in total are this host's numbers today, and a
    proof pinning them would fail the day a cap moves for a reason unrelated to
    the grouping. What is asserted instead is the grouping itself: for each
    deployed project, the reading equals the sum of `HostConfig.Memory` over
    every running container carrying that project's compose label, read
    independently -- and the DATABASE's cap is one of the summands, which is
    the whole of D1636.
    """
    completed = subprocess.run(
        [
            str(REPO_ROOT / "bin" / "doctor.sh"),
            "capacity",
            "--host",
            os.environ["APG_HOST_MANIFEST"],
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert completed.returncode in (0, 6), completed.stdout[-2000:] + completed.stderr[-2000:]
    reading = json.loads(completed.stdout)
    ceilings = next(check for check in reading["checks"] if check["name"] == "ceilings")
    assert "by compose project" in ceilings["detail"], ceilings

    for variable in ("APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"):
        document = json.loads(Path(os.environ[variable]).read_text(encoding="utf-8"))
        key = document["project"]["key"]
        compose = naming.compose_project_name(key)
        listing = subprocess.run(
            ["docker", "ps", "-q", "--filter", f"label=com.docker.compose.project={compose}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        assert listing, f"{key} ({compose}) is running no container"
        inspected = json.loads(
            subprocess.run(
                ["docker", "inspect", *listing], capture_output=True, text=True, check=True
            ).stdout
        )
        caps = {
            entry["Name"].lstrip("/"): int(entry["HostConfig"]["Memory"]) for entry in inspected
        }
        database = document["database"]["container"]
        assert caps.get(database, 0) > 0, (
            f"{key}'s database container {database} is not among the containers "
            f"carrying {compose}, or carries no cap: {sorted(caps)}"
        )
        expected = sum(caps.values()) // (1024 * 1024)
        reported = ceilings["evidence"].get(key)
        assert reported is not None, (
            f"the ceilings name no {key!r} -- the compose name was not mapped back to "
            f"its key (D1673): {ceilings['evidence']}"
        )
        assert int(reported) == expected, (
            f"{key}: the reading says {reported} MiB and the running containers' caps "
            f"sum to {expected} MiB, the database's {caps[database] // 1048576} among them"
        )
        print(f"ceilings {key}: {reported} MiB across {len(caps)} containers")

    # **The unbounded count is the HOST's, not the two projects'** (D1710). The
    # reading selects every container carrying ANY compose project label, and
    # the shared edge is a compose project of its own (`infra/edge/compose.yaml`)
    # whose two services set no `mem_limit`. The first sweep counted only the
    # two projects' containers, found 8 against the reading's 10, and failed a
    # reading that was right. So it is counted here over the reading's own
    # population, read independently -- and asserted both ways, because the
    # detail names no unbounded count at all when there are none.
    everything = subprocess.run(
        ["docker", "ps", "-q", "--filter", "label=com.docker.compose.project"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    unbounded = sorted(
        entry["Name"].lstrip("/")
        for entry in json.loads(
            subprocess.run(
                ["docker", "inspect", *everything], capture_output=True, text=True, check=True
            ).stdout
        )
        if int(entry["HostConfig"]["Memory"]) == 0
    )
    if unbounded:
        assert f", {len(unbounded)} unbounded," in ceilings["detail"], (ceilings, unbounded)
    else:
        assert "unbounded" not in ceilings["detail"], ceilings
    print(f"ceilings: {ceilings['detail']}; unbounded: {', '.join(unbounded) or 'none'}")


# ---------------------------------------------------------------------------
# WF-RUN-001 -- a run, as the agent, correlated to the plane's own record
# ---------------------------------------------------------------------------


def test_a_three_step_run_completes_as_the_invoking_agent(
    roundtrip: dict[str, Any],
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
) -> None:
    """The worker's first run anywhere that is not a rig.

    Three steps over two of beta's capabilities -- a write, a read, a write --
    each `succeeded` at attempt 1. The notes are asserted in the TABLE, owned
    by the agent's owner: a run whose steps all said `succeeded` while nothing
    landed would be the loop trusting its own reading of the plane (D1671).
    """
    document = roundtrip["document"]
    assert document["status"] == "succeeded", json.dumps(document)[:2000]
    assert document["definition"] == ROUNDTRIP and document["dry_run"] is False
    steps = document["steps"]
    assert [step["name"] for step in steps] == [
        step["name"] for step in _definition(ROUNDTRIP)["steps"]
    ]
    for step in steps:
        assert step["status"] == "succeeded" and step["outcome"] == "succeeded", step
        assert step["attempt"] == 1, step

    titles = [
        step["arguments"]["p_title"]
        for step in _definition(ROUNDTRIP)["steps"]
        if "p_title" in step.get("arguments", {})
    ]
    owner = roundtrip["agent"].owner_id
    for title in titles:
        code, out, error = psql(
            project_b,
            f"SELECT count(*) FROM app.notes WHERE owner_id = '{owner}' AND title = '{title}' "
            f"AND created_at >= '{document['started_at']}';",
        )
        assert code == 0, error
        assert int(out) >= 1, f"no note titled {title!r} was written for the agent's owner"


def test_every_step_is_correlated_to_one_audit_row_by_request_id(
    roundtrip: dict[str, Any],
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
) -> None:
    """**D1667's correlation, which D1696 repaired before it was ever run.**

    Each step's `request_id` is the one the PLANE minted and returned. For
    each, exactly one `agent_plane` audit row carries it, naming THIS run's
    agent and the step's tool; a write also has its `database` row under the
    same id. **The plan's `count(*) = 3` is not the number** (D1702): a write
    has two audit rows and a read one, so the join is five rows for three
    steps; what is asserted is one plane row PER step, which is the property.
    """
    agent_id = roundtrip["agent"].agent_id
    compiled = {step["name"]: step for step in _definition(ROUNDTRIP)["steps"]}
    for step in roundtrip["document"]["steps"]:
        request_id = step["request_id"]
        assert request_id, f"step {step['name']} records no request id: {step}"
        rows = _audit(psql, project_b, f"request_id = '{request_id}'")
        plane = [row for row in rows if row["source"] == "agent_plane"]
        assert len(plane) == 1, (
            f"step {step['name']}'s request id {request_id} is on {len(plane)} agent-plane "
            f"audit rows, not one: {rows}. Zero is D1696's defect: the id on the step is not "
            "the id the plane audited under"
        )
        assert plane[0]["agent_id"] == agent_id, plane[0]
        is_write = compiled[step["name"]]["capability"].startswith("create_")
        if is_write:
            database = [row for row in rows if row["source"] == "database"]
            assert len(database) == 1 and database[0]["outcome"] == "committed", rows


def test_the_auth_role_never_exceeded_its_pool_and_reserve(
    roundtrip: dict[str, Any], project_b: dict[str, Any]
) -> None:
    """**D1653: the seventh claimant is a user of the sixth's pool.**

    The loop takes its database connections from the auth service's pool, so
    the auth role's backends during a run must stay inside
    `database.auth_connection_budget` -- the figure the bootstrap plane already
    sums against `max_connections`. Sampled on a thread every ~200 ms while the
    run executed. The control is the floor: a pool of `min_size == max_size`
    holds its connections open, so a reading of zero would mean the sampler
    read the wrong role rather than an idle service.
    """
    samples = roundtrip["samples"]
    budget = int(project_b["database"]["auth_connection_budget"])
    assert len(samples) >= 3, f"only {len(samples)} samples were taken during the run"
    assert min(samples) >= 1, f"the auth role held no connection at some sample: {samples}"
    assert max(samples) <= budget, (
        f"the auth role held {max(samples)} connections during a run; its budget is {budget}"
    )
    print(f"auth backends during the run: min {min(samples)} max {max(samples)} of {budget}")


def test_a_dry_run_lands_no_row_and_records_dry_run_on_both_writes(
    project_b: dict[str, Any],
    beta_agents: dict[str, ProbeAgent],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
) -> None:
    """ADR 0182 through the loop: every write step rolled back, the read run.

    The count of the owner's notes is taken before and after; a dry run that
    wrote would move it. The steps' outcomes are the loop's reading and the
    audit's `dry_run` is the plane's, and both are asserted.
    """
    agent = beta_agents["notes"]

    def notes() -> int:
        code, out, error = psql(
            project_b, f"SELECT count(*) FROM app.notes WHERE owner_id = '{agent.owner_id}';"
        )
        assert code == 0, error
        return int(out)

    before = notes()
    run_id = _started(api_call, agent, ROUNDTRIP, dry_run=True)
    document = _until(api_call, agent, run_id, _terminal, RUN_SECONDS)
    assert document["status"] == "succeeded" and document["dry_run"] is True, document

    compiled = {step["name"]: step for step in _definition(ROUNDTRIP)["steps"]}
    writes = [
        s for s in document["steps"] if compiled[s["name"]]["capability"].startswith("create_")
    ]
    assert len(writes) == 2, document["steps"]
    for step in writes:
        assert step["outcome"] == "dry_run", step
        rows = _audit(psql, project_b, f"request_id = '{step['request_id']}'")
        outcomes = {row["outcome"] for row in rows}
        assert "dry_run" in outcomes and "committed" not in outcomes, rows
    assert notes() == before, "a dry run wrote a note"


def test_the_project_without_a_set_refuses_by_name(
    project_a: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
) -> None:
    """Alpha declares no project set, so it installs no definition: the same
    request beta accepts is `no_such_workflow` here -- the route's one 404
    word, which the plan called *no such definition* (D1698). The control is
    the round trip on beta, where the identical body is a 201."""
    owner = _create_subject(
        psql,
        project_a,
        username=f"apg-s32-alpha-owner-{SWEEP}",
        role="authenticated",
        scopes=("notes:read", "notes:write"),
        password=secrets.token_urlsafe(24),
    )
    agent = _create_agent(psql, project_a, owner, "alpha", api_call, app_base(project_a))
    try:
        answer = _enqueue(api_call, agent, ROUNDTRIP)
        assert answer.status == 404, f"alpha answered {answer.status}: {answer.body[:300]}"
        assert json.loads(answer.body) == {"error": "no_such_workflow"}, answer.body
    finally:
        # Alpha's agent enqueued nothing, so it CAN be deleted, and so can its
        # owner -- unlike beta's (D1700).
        psql(project_a, f"DELETE FROM app_private.agents WHERE id = '{agent.agent_id}';")
        psql(project_a, f"DELETE FROM app_private.users WHERE id = '{owner}';")


# ---------------------------------------------------------------------------
# WF-RESUME-001 -- exactly once after a crash, and a run that survives one
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def crash_state(
    project_b: dict[str, Any],
    beta_agents: dict[str, ProbeAgent],
    api_call: Callable[..., Any],
) -> dict[str, Any]:
    """**D1652 (a): the post-crash state, constructed rather than timed.**

    A worker that died after step 3's upstream committed and before it
    recorded the finish leaves the row written under the step's derived key
    and the step still to do. This builds that state: enqueue, then perform
    step 3's write AS THE AGENT, with the step's own key and the definition's
    own arguments. The loop may reach step 3 before or after this call -- the
    loop polls every 5 s -- and either order is the same property: between
    them, one `committed` and one `replayed`, and one row.

    The definition takes no input (D1697), so the key's arguments are read
    from the YAML and the row is found by the id the idempotency record holds
    rather than by a canary title.
    """
    agent = beta_agents["notes"]
    definition = _definition(ROUNDTRIP)
    last = definition["steps"][-1]
    run_id = _started(api_call, agent, ROUNDTRIP)
    key = f"wf-{run_id}-{last['name']}"
    answer = api_call(
        project_b["routes"]["mcp"]["url"],
        method="POST",
        token=agent.token(),
        body={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "create_note",
                "arguments": {**last["arguments"], "idempotency_key": key, "dry_run": False},
            },
        },
        headers={"Accept": MCP_ACCEPT},
    )
    document = _until(api_call, agent, run_id, _terminal, RUN_SECONDS)
    return {
        "run_id": run_id,
        "key": key,
        "answer": answer,
        "request_id": _header(answer.headers, "X-Request-Id"),
        "document": document,
        "agent": agent,
        "last": last,
    }


def test_a_run_whose_worker_died_after_the_upstream_committed_resumes_exactly_once(
    crash_state: dict[str, Any],
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
) -> None:
    """**§7 item 1: at-least-once plus an idempotent upstream is exactly once.**

    Proved by the TABLES, never by a status: the idempotency record for the
    step's key shows one replay, the notes table holds exactly one row for the
    id that record names, and the two database audit rows under the two
    request ids are one `committed` and one `replayed`.
    """
    answer = crash_state["answer"]
    assert answer.status == 200, f"the constructed write failed: {answer.body[:300]}"
    result = sse_result(answer.body)
    assert result is not None and not refused(result), (
        f"the constructed write was refused: {result}"
    )

    document = crash_state["document"]
    assert document["status"] == "succeeded", json.dumps(document)[:2000]
    last = document["steps"][-1]
    assert last["name"] == crash_state["last"]["name"] and last["status"] == "succeeded", last

    agent_id = crash_state["agent"].agent_id
    code, out, error = psql(
        project_b,
        "SELECT replay_count::text || ' ' || row_id::text FROM app_private.agent_idempotency "
        f"WHERE agent_id = '{agent_id}' AND idempotency_key = '{crash_state['key']}';",
    )
    assert code == 0 and out, f"no idempotency record for {crash_state['key']}: {error}"
    replays, row_id = out.split()
    assert replays == "1", f"the key was replayed {replays} times, not once"

    code, out, error = psql(project_b, f"SELECT count(*) FROM app.notes WHERE id = '{row_id}';")
    assert code == 0 and out == "1", f"the note the key names is there {out} times: {error}"

    ids = [value for value in (last["request_id"], crash_state["request_id"]) if value]
    assert len(ids) == 2, (
        f"one of the two calls carries no plane request id (step {last['request_id']!r}, "
        f"proof {crash_state['request_id']!r})"
    )
    rows = _audit(
        psql,
        project_b,
        "source = 'database' AND request_id IN (" + ", ".join(f"'{i}'" for i in ids) + ")",
    )
    assert sorted(row["outcome"] for row in rows) == ["committed", "replayed"], rows


def test_a_reused_key_with_other_arguments_is_refused(
    crash_state: dict[str, Any],
    project_b: dict[str, Any],
    api_call: Callable[..., Any],
) -> None:
    """**The control, and `PT412` is only the control** (D1646). The same key
    with a different body is refused `input_not_permitted` -- which proves the
    fingerprint is checked, so the replay above was a replay of the SAME call
    rather than a key that matches anything."""
    arguments = {
        **crash_state["last"]["arguments"],
        "p_content": f"a different body {SWEEP}",
        "idempotency_key": crash_state["key"],
        "dry_run": False,
    }
    answer = api_call(
        project_b["routes"]["mcp"]["url"],
        method="POST",
        token=crash_state["agent"].token(),
        body={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "create_note", "arguments": arguments},
        },
        headers={"Accept": MCP_ACCEPT},
    )
    assert answer.status == 200, answer.body[:300]
    result = sse_result(answer.body)
    assert result is not None and refused(result), (
        f"a reused key with another body was served: {result}"
    )
    text = result["result"]["content"][0]["text"]
    assert text.startswith("input_not_permitted"), text


@pytest.fixture(scope="module")
def parked_rehearsal(
    project_b: dict[str, Any],
    beta_agents: dict[str, ProbeAgent],
    beta_owner: str,
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    as_root: None,
) -> dict[str, Any]:
    """**D1652 (b): a run PARKED on a retry, and the process under it killed.**

    `notes-retry`'s first step asks for a transition the task is not in, which
    the plane names `write_conflict` -- retryable -- so the step parks for 45 s.
    While it is parked, `rehearse.sh worker-restart` SIGKILLs the auth process
    (ADR 0193, never `docker kill`), the restart policy brings it back, and the
    record lands in `APG_REHEARSAL_EVIDENCE_DIR`. The loop that comes back
    claims the step at its resume time; `retry.max` is 1, so attempt 2 is the
    last and the run FAILS naming the token -- which is the resumption this
    proves: a step nobody lost, executed once more, by a different holder.
    """
    agent = beta_agents["retry"]
    code, task_id, error = psql(
        project_b,
        f"INSERT INTO app.tasks (owner_id, title) VALUES ('{beta_owner}', "
        f"'apg-s32-retry-{SWEEP}') RETURNING id;",
    )
    assert code == 0 and task_id, f"could not create the rehearsal's task: {error}"
    run_id = _started(api_call, agent, RETRY, run_input={"task_id": task_id.splitlines()[0]})

    def first_parked(document: dict[str, Any]) -> bool:
        return _terminal(document) or document["steps"][0]["status"] == "parked"

    parked = _until(api_call, agent, run_id, first_parked, 30)
    evidence = Path(os.environ["APG_REHEARSAL_EVIDENCE_DIR"])
    key = project_b["project"]["key"]
    rehearsal = subprocess.run(
        [
            str(REPO_ROOT / "bin" / "rehearse.sh"),
            "worker-restart",
            "--outputs",
            str(deployed_output.deployed_path(key)),
            "--evidence-dir",
            str(evidence),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        timeout=600,
    )
    final = _until(api_call, agent, run_id, _terminal, PARKED_SECONDS, every=5.0)
    records = sorted(
        evidence.glob(f"rehearsal-{key}-worker-restart-*.json"), key=lambda p: p.stat().st_mtime
    )
    return {
        "run_id": run_id,
        "parked": parked,
        "rehearsal": rehearsal,
        "final": final,
        "record": json.loads(records[-1].read_text(encoding="utf-8")) if records else None,
    }


def test_a_parked_run_survives_the_worker_restart_rehearsal(
    parked_rehearsal: dict[str, Any],
) -> None:
    """The step was parked when the process died, and the run finished anyway
    -- at attempt 2, failing on the same `write_conflict`, because that is
    what the definition says a second failure is."""
    parked = parked_rehearsal["parked"]
    assert parked["steps"][0]["status"] == "parked", (
        f"the first step never parked, so nothing was rehearsed under it: {parked['steps'][0]}"
    )
    rehearsal = parked_rehearsal["rehearsal"]
    assert rehearsal.returncode == 0, (
        f"rehearse.sh worker-restart exited {rehearsal.returncode}\n"
        f"{rehearsal.stdout[-2500:]}\n{rehearsal.stderr[-2500:]}"
    )
    final = parked_rehearsal["final"]
    first = final["steps"][0]
    assert final["status"] == "failed", json.dumps(final)[:2000]
    assert final["stopped_reason"] == "write_conflict", final["stopped_reason"]
    assert first["attempt"] == 2 and first["status"] == "failed", first
    assert first["request_id"], "the resumed attempt reached the plane and records no id"
    assert final["steps"][1]["status"] == "queued", (
        "the second step ran, so the first step's failure did not stop the run"
    )


def test_the_rehearsal_recorded_a_new_holder_and_no_lost_step(
    parked_rehearsal: dict[str, Any],
) -> None:
    """The record `worker-restart` wrote: the reading is the heartbeat's HOLDER
    (D1695), and no claimed step was left past its lease."""
    record = parked_rehearsal["record"]
    assert record is not None, "worker-restart wrote no record"
    assert record["scenario"] == "worker-restart" and record["verdict"] == "read", record
    assert record["reversed"] is True, record
    readings = record["readings"]
    before, after = readings["heartbeat_holder_before"], readings["heartbeat_holder_after"]
    assert before and after and before != after, (
        f"the holder did not move ({before!r} -> {after!r}): the loop never stopped, "
        "or the check never read it"
    )
    assert readings["oldest_claimed_lease_age_seconds"] is None, readings


# ---------------------------------------------------------------------------
# WF-REVOKE-001 -- a revoked agent's run stops, and its twin's completes
# ---------------------------------------------------------------------------


def test_a_revoked_agents_run_stops_at_the_boundary_with_no_call(
    project_b: dict[str, Any],
    beta_agents: dict[str, ProbeAgent],
    beta_admin: str,
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
) -> None:
    """**A race, and this says so** (§10). The run is enqueued and the agent
    revoked through `PATCH /admin/agents/{id}` in the same second; the loop
    polls every 5 s, so it almost always finds the run after the revocation
    and the mint for step 1 is refused. If it claimed step 1 first, the run
    stops at a later boundary. Either way: `stopped`, `agent_not_active`, the
    boundary step `token_refused` with NO request id -- no call was made
    (D1696) -- and no audit row for this agent after the revocation.

    The offline proof `test_a_refused_mint_stops_the_run_and_makes_no_call`
    pins the boundary exactly; this proves the deployment does what it says.
    """
    agent = beta_agents["revocable"]
    token = agent.token()
    run_id = _started(api_call, agent, ROUNDTRIP, token=token)
    revoked = api_call(
        f"{agent.app}/admin/agents/{agent.agent_id}",
        method="PATCH",
        token=beta_admin,
        body={"status": "revoked"},
    )
    assert revoked.status == 200, f"the revocation failed: {revoked.body[:300]}"
    code, revoked_at, error = psql(
        project_b, f"SELECT updated_at FROM app_private.agents WHERE id = '{agent.agent_id}';"
    )
    assert code == 0 and revoked_at, error

    # The status route authenticates the AGENT, and a revoked agent is refused
    # there too (ADR 0229), so the run is read from the substrate directly.
    deadline = time.monotonic() + RUN_SECONDS
    while True:
        code, out, error = psql(
            project_b,
            f"SELECT app_private.workflow_run_status('{run_id}', '{agent.agent_id}');",
        )
        assert code == 0, error
        document = json.loads(out)
        if _terminal(document):
            break
        assert time.monotonic() < deadline, f"the revoked run never ended: {document}"
        time.sleep(2)

    assert document["status"] == "stopped", json.dumps(document)[:2000]
    assert document["stopped_reason"] == "agent_not_active", document["stopped_reason"]
    boundary = next(step for step in document["steps"] if step["outcome"] == "token_refused")
    assert boundary["request_id"] is None, (
        f"the refused step carries a request id, so a call was made: {boundary}"
    )
    later = _audit(
        psql, project_b, f"agent_id = '{agent.agent_id}' AND started_at > '{revoked_at}'"
    )
    assert later == [], f"the revoked agent reached the audit after its revocation: {later}"
    print(f"the revoked run stopped at step {boundary['position']} ({boundary['name']})")


def test_an_unrevoked_agents_identical_run_completes(
    beta_agents: dict[str, ProbeAgent], api_call: Callable[..., Any]
) -> None:
    """The control: the same definition, the same scopes, an agent nobody
    revoked -- it completes, so the stop above was the revocation's."""
    agent = beta_agents["control"]
    run_id = _started(api_call, agent, ROUNDTRIP)
    document = _until(api_call, agent, run_id, _terminal, RUN_SECONDS)
    assert document["status"] == "succeeded", json.dumps(document)[:2000]
