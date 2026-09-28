"""Session 33's live halves: approval gates, compensation and provenance, on beta.

`WF-APPROVE-001`, `WF-COMP-002`, `WF-PROV-002`, `AGT-AUDIT-004` (ADR 0230-0234).
Written at the bump (Run 8) and gated on variables the Session 32 gate already
exports -- no new environment gate (§2).

**None of this has executed before the trip.** Every proof asserts against the
deployed plane's own records -- the audit table, the approval table, the tasks
and embeddings tables -- and never against what the loop says it did, for
Session 32's reason (D1696): the loop's rigs ran against a plane that believed
what the loop believed.

**Beta only, with alpha as the control** (D1733): alpha declares no project set
and installs no definition, so its approval listing is empty.

**The humans are person-SHAPED, not persons.** Each is a subject created in SQL
through `app_private.auth_create_user` with a random password, logged in over
HTTP -- `test_session32_workflows.py`'s `beta_admin` shape. The approver is a
SECOND user, never the owner of the agents whose runs it decides; the owner
rule is proved by an agent the approver DOES own.

**What these proofs leave behind, deliberately** (D1700). A run references its
agent, so the probe agents are REVOKED at teardown and left; their owner stays
because they reference it. An approval's `decided_by` references the approver,
so the approver is deleted if the database allows it and LEFT otherwise --
the D1700 shape for humans, which the retention story owes. Tasks, notes and
the two other administrators are deleted.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import time
import urllib.parse
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, deployed_output, runtime_override

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

#: The owner's tenant scopes: both definitions' union -- tasks for the forward
#: steps and their compensations, note embeddings for the approval step.
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

#: A suffix unique to this sweep, in every name and title (D1700: agents are
#: left, so a fixed name would collide with the previous sweep's).
SWEEP = secrets.token_hex(4)

APPROVAL = "tasks-approval"
COMPENSATE = "tasks-compensate"
APPROVAL_STEP = "set_the_embedding"

#: `compensating` is NOT terminal: a proof polls through it.
TERMINAL = frozenset({"succeeded", "failed", "cancelled", "stopped"})

#: A run reaches its approval park after one write and one refused call: two
#: poll intervals of 5 s and the calls between them.
PARKED_SECONDS = 60
RUN_SECONDS = 120

#: The text literal of 768 zeros -- rig 33b's measured shape, which PostgREST
#: accepts into a `vector` parameter. A whole-string reference keeps the
#: input's own type, so it reaches the plane as this string (`"type":
#: "string"` in the reviewed surface).
EMBEDDING = "[" + ",".join(["0"] * 768) + "]"


def refused(result: dict[str, Any]) -> bool:
    """A refusal, read both ways (D509, D1414, D1672)."""
    return "error" in result or bool(result.get("result", {}).get("isError"))


# ---------------------------------------------------------------------------
# Subjects and agents -- `test_session32_workflows.py`'s helpers, copied
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
        f"'{username}', 'Session 33 gate probe', "
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
    name = f"apg-s33-{label}-{SWEEP}"
    array = ", ".join(f"'{scope}'" for scope in sorted(AGENT_SCOPES))
    code, agent_id, error = psql(
        document,
        "SELECT app_private.auth_create_agent("
        f"'{name}', 'Session 33 gate probe', "
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


# ---------------------------------------------------------------------------
# The principals
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def beta_app(project_b: dict[str, Any], app_base: Callable[[dict[str, Any]], str]) -> str:
    return app_base(project_b)


@pytest.fixture(scope="module")
def gate_owner(
    project_b: dict[str, Any], psql: Callable[..., tuple[int, str, str]]
) -> Iterator[str]:
    """The human three of the probe agents belong to. Its password is random
    and never recorded; it is left at teardown because its agents are (D1700).

    **Beta's deployed lock is read first**: the owner's scopes include
    `note_embeddings:*`, and a lock that did not derive them is a deployment
    this module cannot prove anything about -- said by name, not discovered as
    a refused call ten proofs later.
    """
    path = (
        deployed_output.rendered_path(project_b["project"]["key"])
        / runtime_override.MCP_LOCK_FILENAME
    )
    assert path.is_file(), f"no capability lock at {path}; the deploy did not compile one"
    vocabulary = json.loads(path.read_text(encoding="utf-8"))["vocabulary"]["data"]
    missing = sorted(set(OWNER_SCOPES) - set(vocabulary))
    assert not missing, f"beta's deployed lock derives no {missing}; the gate proofs need them"

    owner = _create_subject(
        psql,
        project_b,
        username=f"apg-s33-owner-{SWEEP}",
        role="authenticated",
        scopes=OWNER_SCOPES,
        password=secrets.token_urlsafe(24),
    )
    yield owner


@pytest.fixture(scope="module")
def approver(
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    beta_app: str,
) -> Iterator[dict[str, str]]:
    """A SECOND user: `project_admin` holding `admin_audit:read` and
    `admin_workflows:approve`, logged in over HTTP. Deleted at teardown if the
    database allows it -- an approval's `decided_by` references it."""
    username = f"apg-s33-approver-{SWEEP}"
    password = secrets.token_urlsafe(24)
    user_id = _create_subject(
        psql,
        project_b,
        username=username,
        role="project_admin",
        scopes=("admin_audit:read", "admin_workflows:approve"),
        password=password,
    )
    try:
        yield {
            "user_id": user_id,
            "username": username,
            "token": _login(api_call, beta_app, username, password),
        }
    finally:
        code, _, error = psql(project_b, f"DELETE FROM app_private.users WHERE id = '{user_id}';")
        if code != 0:
            print(f"the approver {username} is LEFT (D1700's shape for humans): {error[:200]}")


@pytest.fixture(scope="module")
def scopeless_admin(
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    beta_app: str,
) -> Iterator[str]:
    """A `project_admin` WITHOUT the approve scope: it may revoke an agent and
    may not decide a run. Deleted at teardown; it decides nothing."""
    username = f"apg-s33-admin-{SWEEP}"
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
        yield _login(api_call, beta_app, username, password)
    finally:
        psql(project_b, f"DELETE FROM app_private.users WHERE username = '{username}';")


@pytest.fixture(scope="module")
def gate_agents(
    project_b: dict[str, Any],
    gate_owner: str,
    approver: dict[str, str],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    beta_app: str,
) -> Iterator[dict[str, ProbeAgent]]:
    """Four agents, one per concern, so no proof reads another's audit rows.

    `approve`, `reject` and `revocable` belong to `gate_owner`;
    `owned_by_approver` belongs to the APPROVER, for the owner rule.
    """
    agents = {
        label: _create_agent(psql, project_b, gate_owner, label, api_call, beta_app)
        for label in ("approve", "reject", "revocable")
    }
    agents["owned_by_approver"] = _create_agent(
        psql, project_b, approver["user_id"], "owned-by-approver", api_call, beta_app
    )
    try:
        yield agents
    finally:
        for agent in agents.values():
            _revoke(psql, project_b, agent.agent_id)
        object_owner = project_b["database"]["roles"]["object_owner"]
        for owner in {agent.owner_id for agent in agents.values()}:
            for table in ("app.tasks", "app.notes"):
                psql(
                    project_b,
                    f"DELETE FROM {table} WHERE owner_id = '{owner}' AND title LIKE '%{SWEEP}%';",
                    role=object_owner,
                    claim=owner,
                )


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def _task_and_note(
    psql: Callable[..., tuple[int, str, str]], document: dict[str, Any], owner: str, label: str
) -> dict[str, str]:
    """A `pending` task and a note, owned by the run's agent's OWNER."""
    code, task_id, error = psql(
        document,
        f"INSERT INTO app.tasks (owner_id, title) VALUES ('{owner}', "
        f"'apg-s33-{label}-{SWEEP}') RETURNING id;",
    )
    assert code == 0 and task_id, f"could not create a task: {error}"
    code, note_id, error = psql(
        document,
        f"INSERT INTO app.notes (owner_id, title, content) VALUES ('{owner}', "
        f"'apg-s33-{label}-{SWEEP}', 'session 33 gate probe') RETURNING id;",
    )
    assert code == 0 and note_id, f"could not create a note: {error}"
    return {"task_id": task_id.splitlines()[0], "note_id": note_id.splitlines()[0]}


def _started(
    api_call: Callable[..., Any], agent: ProbeAgent, name: str, run_input: dict[str, Any]
) -> str:
    answer = api_call(
        f"{agent.app}/workflows/runs",
        method="POST",
        token=agent.token(),
        body={"name": name, "version": 1, "input": run_input, "dry_run": False},
    )
    assert answer.status == 201, f"enqueueing {name} answered {answer.status}: {answer.body[:300]}"
    return json.loads(answer.body)["run_id"]


def _status(api_call: Callable[..., Any], agent: ProbeAgent, run_id: str) -> dict[str, Any]:
    answer = api_call(f"{agent.app}/workflows/runs/{run_id}", token=agent.token())
    assert answer.status == 200, f"reading run {run_id} answered {answer.status}: {answer.body}"
    return json.loads(answer.body)


def _substrate_status(
    psql: Callable[..., tuple[int, str, str]], document: dict[str, Any], run_id: str, agent: str
) -> dict[str, Any]:
    """The run read from the substrate directly -- for an agent that can no
    longer read its own run through the route (D1704)."""
    code, out, error = psql(
        document, f"SELECT app_private.workflow_run_status('{run_id}', '{agent}');"
    )
    assert code == 0, error
    return json.loads(out)


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


def _terminal(document: dict[str, Any]) -> bool:
    return document["status"] in TERMINAL


def _step(document: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in document["steps"] if s["name"] == name and s["phase"] == "forward")


def _parked_for_approval(document: dict[str, Any]) -> bool:
    if _terminal(document):
        return True
    step = _step(document, APPROVAL_STEP)
    return step["status"] == "parked" and (step.get("approval") or {}).get("status") == "pending"


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


def _approval_status(
    psql: Callable[..., tuple[int, str, str]], document: dict[str, Any], run_id: str
) -> str:
    code, out, error = psql(
        document,
        f"SELECT status::text FROM app_private.workflow_approval WHERE run_id = '{run_id}';",
    )
    assert code == 0 and out, f"no approval row for run {run_id}: {error}"
    return out.splitlines()[0]


def _decide(api_call: Callable[..., Any], app: str, run_id: str, decision: str, token: str) -> Any:
    return api_call(
        f"{app}/admin/workflows/runs/{run_id}/{decision}",
        method="POST",
        token=token,
        body={"step": APPROVAL_STEP},
    )


def _task_status(
    psql: Callable[..., tuple[int, str, str]], document: dict[str, Any], task_id: str
) -> str:
    code, out, error = psql(document, f"SELECT status FROM app.tasks WHERE id = '{task_id}';")
    assert code == 0 and out, error
    return out.splitlines()[0]


def _embeddings(
    psql: Callable[..., tuple[int, str, str]], document: dict[str, Any], note_id: str
) -> int:
    code, out, error = psql(
        document, f"SELECT count(*) FROM app.note_embeddings WHERE note_id = '{note_id}';"
    )
    assert code == 0, error
    return int(out)


@pytest.fixture(scope="module")
def approved_run(
    project_b: dict[str, Any],
    gate_agents: dict[str, ProbeAgent],
    approver: dict[str, str],
    scopeless_admin: str,
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    beta_app: str,
) -> dict[str, Any]:
    """`tasks-approval` for `approve`, decided three ways in order: by the
    requesting AGENT (401), by an administrator WITHOUT the scope (403, still
    pending), and by the approver (200) -- then run to its end."""
    agent = gate_agents["approve"]
    rows = _task_and_note(psql, project_b, agent.owner_id, "approved")
    run_id = _started(api_call, agent, APPROVAL, {**rows, "embedding": EMBEDDING})
    parked = _until(
        lambda: _status(api_call, agent, run_id), _parked_for_approval, PARKED_SECONDS,
        "the approval park",
    )  # fmt: skip
    audit_at_park = _audit(
        psql, project_b, f"agent_id = '{agent.agent_id}' AND tool = 'set_note_embedding'"
    )

    by_agent = _decide(api_call, beta_app, run_id, "approve", agent.token())
    by_scopeless = _decide(api_call, beta_app, run_id, "approve", scopeless_admin)
    still = _approval_status(psql, project_b, run_id)
    by_approver = _decide(api_call, beta_app, run_id, "approve", approver["token"])

    final = _until(
        lambda: _status(api_call, agent, run_id), _terminal, RUN_SECONDS, "the approved run's end"
    )
    return {
        "agent": agent,
        "run_id": run_id,
        "rows": rows,
        "parked": parked,
        "audit_at_park": audit_at_park,
        "by_agent": by_agent,
        "by_scopeless": by_scopeless,
        "pending_after_scopeless": still,
        "by_approver": by_approver,
        "final": final,
    }


# ---------------------------------------------------------------------------
# WF-APPROVE-001 -- a person releases one parked write
# ---------------------------------------------------------------------------


def test_an_approval_step_parks_with_one_refusal_in_the_audit(
    approved_run: dict[str, Any],
) -> None:
    """The run parks at the approval step on the PLANE's own refusal, which is
    audited exactly once -- one `refused`/`approval_required` row -- and the
    first step, which needs nobody, has already succeeded."""
    parked = approved_run["parked"]
    assert parked["status"] == "running", json.dumps(parked)[:1500]
    assert _step(parked, "start_the_task")["status"] == "succeeded", parked["steps"]
    step = _step(parked, APPROVAL_STEP)
    assert step["status"] == "parked" and step["approval"]["status"] == "pending", step

    refusals = [
        row
        for row in approved_run["audit_at_park"]
        if row["source"] == "agent_plane" and row["outcome"] == "refused"
    ]
    assert len(refusals) == 1, approved_run["audit_at_park"]
    assert refusals[0]["denial_reason"] == "approval_required", refusals[0]
    assert not [r for r in approved_run["audit_at_park"] if r["outcome"] == "committed"], (
        f"the embedding was written before anybody approved it: {approved_run['audit_at_park']}"
    )


def test_the_requesting_agent_cannot_approve(approved_run: dict[str, Any]) -> None:
    """ADR 0232's first control, on the deployment: the agent's own token is
    refused by the approve route before any scope is read."""
    answer = approved_run["by_agent"]
    assert answer.status == 401, f"{answer.status}: {answer.body[:300]}"
    assert json.loads(answer.body) == {"error": "authentication_failed"}


def test_an_administrator_without_the_scope_cannot_approve(approved_run: dict[str, Any]) -> None:
    """A `project_admin` who may REVOKE the agent may not decide its run, and
    the refusal changes nothing: the approval is still `pending` after it,
    read from the table."""
    answer = approved_run["by_scopeless"]
    assert answer.status == 403, f"{answer.status}: {answer.body[:300]}"
    assert json.loads(answer.body) == {"error": "authorization_failed"}
    assert approved_run["pending_after_scopeless"] == "pending"


def test_a_second_user_approves_and_the_run_completes_once(
    approved_run: dict[str, Any],
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
) -> None:
    """The approver's decision releases ONE write: the run succeeds, the note
    has one embedding, and the database committed the step's write once."""
    answer = approved_run["by_approver"]
    assert answer.status == 200, f"{answer.status}: {answer.body[:300]}"
    assert json.loads(answer.body) == {
        "run_id": approved_run["run_id"],
        "step": APPROVAL_STEP,
        "approval": "approved",
    }

    final = approved_run["final"]
    assert final["status"] == "succeeded", json.dumps(final)[:2000]
    assert _step(final, APPROVAL_STEP)["approval"]["status"] == "approved"
    assert _embeddings(psql, project_b, approved_run["rows"]["note_id"]) == 1
    assert _task_status(psql, project_b, approved_run["rows"]["task_id"]) == "completed"

    agent = approved_run["agent"].agent_id
    rows = _audit(psql, project_b, f"agent_id = '{agent}' AND tool = 'set_note_embedding'")
    committed = [r for r in rows if r["source"] == "database" and r["outcome"] == "committed"]
    assert len(committed) == 1, f"the approved write committed {len(committed)} times: {rows}"


def test_the_runs_owner_cannot_approve(
    project_b: dict[str, Any],
    gate_agents: dict[str, ProbeAgent],
    approver: dict[str, str],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    beta_app: str,
) -> None:
    """Holding the scope is not enough (ADR 0232): the approver OWNS this
    agent, so its decision is `approver_is_owner` and changes nothing. The
    agent then cancels its own run, and the first step is compensated."""
    agent = gate_agents["owned_by_approver"]
    rows = _task_and_note(psql, project_b, agent.owner_id, "owner-rule")
    run_id = _started(api_call, agent, APPROVAL, {**rows, "embedding": EMBEDDING})
    _until(
        lambda: _status(api_call, agent, run_id), _parked_for_approval, PARKED_SECONDS,
        "the approval park",
    )  # fmt: skip

    answer = _decide(api_call, beta_app, run_id, "approve", approver["token"])
    assert answer.status == 403, f"{answer.status}: {answer.body[:300]}"
    assert json.loads(answer.body) == {"error": "approver_is_owner"}
    assert _approval_status(psql, project_b, run_id) == "pending"

    cancelled = api_call(
        f"{agent.app}/workflows/runs/{run_id}/cancel", method="POST", token=agent.token()
    )
    assert cancelled.status == 200, cancelled.body[:300]
    final = _until(
        lambda: _status(api_call, agent, run_id), _terminal, RUN_SECONDS, "the cancelled run"
    )
    assert final["status"] == "cancelled", json.dumps(final)[:2000]
    assert final["compensation_outcome"] == "complete", final
    assert _task_status(psql, project_b, rows["task_id"]) == "pending"


def test_the_project_without_a_set_lists_no_approvals(
    project_a: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
) -> None:
    """Alpha installs no definition (D1733), so a person holding the scope
    there reads an EMPTY listing -- 200, not a refusal: the route is served
    and nothing waits. The control is beta, where the approver's listing is
    what the runs above decided from."""
    username = f"apg-s33-alpha-approver-{SWEEP}"
    password = secrets.token_urlsafe(24)
    user_id = _create_subject(
        psql,
        project_a,
        username=username,
        role="project_admin",
        scopes=("admin_workflows:approve",),
        password=password,
    )
    try:
        app = app_base(project_a)
        token = _login(api_call, app, username, password)
        answer = api_call(f"{app}/admin/workflows/approvals", token=token)
        assert answer.status == 200, f"{answer.status}: {answer.body[:300]}"
        assert json.loads(answer.body) == {"approvals": [], "limit": 50}
    finally:
        psql(project_a, f"DELETE FROM app_private.users WHERE id = '{user_id}';")


# ---------------------------------------------------------------------------
# WF-COMP-002 -- a rejection and a failure, each undone
# ---------------------------------------------------------------------------


def test_a_rejection_cancels_the_run_and_compensates(
    project_b: dict[str, Any],
    gate_agents: dict[str, ProbeAgent],
    approver: dict[str, str],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    beta_app: str,
) -> None:
    """A rejection is a cancel (ADR 0230): the run passes through
    `compensating` to `cancelled` with outcome `complete`, the task is back in
    `pending`, and the note has no embedding -- the parked write never ran."""
    agent = gate_agents["reject"]
    rows = _task_and_note(psql, project_b, agent.owner_id, "rejected")
    run_id = _started(api_call, agent, APPROVAL, {**rows, "embedding": EMBEDDING})
    _until(
        lambda: _status(api_call, agent, run_id), _parked_for_approval, PARKED_SECONDS,
        "the approval park",
    )  # fmt: skip
    assert _task_status(psql, project_b, rows["task_id"]) == "in_progress"

    answer = _decide(api_call, beta_app, run_id, "reject", approver["token"])
    assert answer.status == 200, f"{answer.status}: {answer.body[:300]}"
    assert json.loads(answer.body)["approval"] == "rejected"

    final = _until(
        lambda: _status(api_call, agent, run_id), _terminal, RUN_SECONDS, "the rejected run"
    )
    assert final["status"] == "cancelled", json.dumps(final)[:2000]
    assert final["compensation_cause"] == "cancelled"
    assert final["compensation_outcome"] == "complete", final
    undos = [s for s in final["steps"] if s["phase"] == "compensation"]
    assert [u["status"] for u in undos] == ["succeeded"], undos
    assert _task_status(psql, project_b, rows["task_id"]) == "pending"
    assert _embeddings(psql, project_b, rows["note_id"]) == 0


def test_a_terminal_failure_after_a_wait_compensates_in_reverse(
    project_b: dict[str, Any],
    gate_agents: dict[str, ProbeAgent],
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
) -> None:
    """`tasks-compensate`: the wait is served (`waited`), the third step fails
    terminally on a task that does not exist (`row_not_found`), and the first
    step is undone -- the run `failed` with outcome `complete`, the task back
    in `pending`."""
    agent = gate_agents["approve"]
    rows = _task_and_note(psql, project_b, agent.owner_id, "compensated")
    run_input = {"task_id": rows["task_id"], "missing_task_id": str(uuid.uuid4())}
    run_id = _started(api_call, agent, COMPENSATE, run_input)
    final = _until(
        lambda: _status(api_call, agent, run_id), _terminal, RUN_SECONDS, "the compensated run"
    )
    assert final["status"] == "failed", json.dumps(final)[:2000]
    assert final["compensation_outcome"] == "complete", final
    pause = _step(final, "pause")
    assert pause["status"] == "succeeded" and pause["reason"] == "waited", pause
    failing = _step(final, "touch_a_missing_task")
    assert failing["status"] == "failed" and failing["reason"] == "row_not_found", failing
    assert _task_status(psql, project_b, rows["task_id"]) == "pending"


# ---------------------------------------------------------------------------
# WF-PROV-002 -- provenance read back through the product's own command
# ---------------------------------------------------------------------------


def _inspect(run_id: str, token: str) -> dict[str, Any]:
    """`bin/workflow.sh inspect`, the product's own command (D1114)."""
    result = subprocess.run(
        [
            str(REPO_ROOT / "bin" / "workflow.sh"),
            "inspect",
            "--run",
            run_id,
            "--project-outputs",
            os.environ["APG_PROJECT_B_OUTPUTS"],
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        stdin=subprocess.DEVNULL,
        env={**os.environ, "APG_API_TOKEN": token},
    )
    assert result.returncode == 0, f"inspect exited {result.returncode}: {result.stderr[:500]}"
    return json.loads(result.stdout)


def test_inspect_reads_back_the_approved_run_complete(
    approved_run: dict[str, Any], approver: dict[str, str]
) -> None:
    """The approval step's two attempts, each joined to its audit rows by the
    plane's request id: the refused call and the committed one -- and the
    approver named. `profile` is absent WITH its reason (ADR 0195)."""
    document = _inspect(approved_run["run_id"], approver["token"])
    assert document["run"]["status"] == "succeeded", json.dumps(document["run"])
    assert sorted(document["run"]["input_keys"]) == ["embedding", "note_id", "task_id"]
    assert EMBEDDING not in json.dumps(document), "provenance carried an input VALUE"

    step = next(s for s in document["steps"] if s["name"] == APPROVAL_STEP)
    requested = [a for a in step["attempts"] if a["event"] == "approval_requested"]
    finished = [a for a in step["attempts"] if a["event"] == "finished"]
    assert len(requested) == 1 and len(finished) == 1, step["attempts"]
    refusal = [a for a in requested[0]["audit"] if a["source"] == "agent_plane"]
    assert len(refusal) == 1 and refusal[0]["outcome"] == "refused", requested[0]
    assert refusal[0]["denial_reason"] == "approval_required", refusal[0]
    assert "committed" in {a["outcome"] for a in finished[0]["audit"]}, finished[0]
    assert finished[0]["attempt"] > requested[0]["attempt"], step["attempts"]

    assert len(document["approvals"]) == 1, document["approvals"]
    decided = document["approvals"][0]
    assert decided["status"] == "approved"
    assert decided["decided_by_username"] == approver["username"], decided
    assert document["profile"]["value"] is None and document["profile"]["reason"]


def test_an_auditor_reads_a_revoked_agents_stopped_run(
    project_b: dict[str, Any],
    gate_agents: dict[str, ProbeAgent],
    approver: dict[str, str],
    scopeless_admin: str,
    api_call: Callable[..., Any],
    psql: Callable[..., tuple[int, str, str]],
    beta_app: str,
) -> None:
    """D1704 answered. The agent is revoked while its run waits at the gate,
    then the run is approved -- the decision does not consult the agent -- so
    the next claim's mint is refused and the run stops. **Deterministic, unlike
    Session 32's revocation race**: the run cannot pass the gate until the
    approval, and the revocation lands first. The agent can no longer read its
    run; the auditor reads it whole with `inspect`."""
    agent = gate_agents["revocable"]
    rows = _task_and_note(psql, project_b, agent.owner_id, "revoked")
    run_id = _started(api_call, agent, APPROVAL, {**rows, "embedding": EMBEDDING})
    _until(
        lambda: _status(api_call, agent, run_id), _parked_for_approval, PARKED_SECONDS,
        "the approval park",
    )  # fmt: skip
    token = agent.token()

    revoked = api_call(
        f"{beta_app}/admin/agents/{agent.agent_id}",
        method="PATCH",
        token=scopeless_admin,
        body={"status": "revoked"},
    )
    assert revoked.status == 200, f"the revocation failed: {revoked.body[:300]}"
    decided = _decide(api_call, beta_app, run_id, "approve", approver["token"])
    assert decided.status == 200, f"{decided.status}: {decided.body[:300]}"

    final = _until(
        lambda: _substrate_status(psql, project_b, run_id, agent.agent_id), _terminal,
        RUN_SECONDS, "the revoked run's stop",
    )  # fmt: skip
    assert final["status"] == "stopped", json.dumps(final)[:2000]
    assert final["stopped_reason"] == "agent_not_active", final["stopped_reason"]

    own = api_call(f"{beta_app}/workflows/runs/{run_id}", token=token)
    assert own.status == 401, f"the revoked agent read its own run: {own.status}"

    document = _inspect(run_id, approver["token"])
    assert document["run"]["status"] == "stopped", document["run"]
    assert document["run"]["agent_id"] == agent.agent_id


# ---------------------------------------------------------------------------
# AGT-AUDIT-004 -- the filters on a real audit record
# ---------------------------------------------------------------------------


def _audit_page(api_call: Callable[..., Any], app: str, token: str, query: dict[str, str]) -> Any:
    answer = api_call(f"{app}/admin/audit?{urllib.parse.urlencode(query)}", token=token)
    assert answer.status == 200, f"{answer.status}: {answer.body[:300]}"
    return json.loads(answer.body)


def test_a_cursor_pages_the_deployments_audit_once_each(
    approver: dict[str, str], api_call: Callable[..., Any], beta_app: str
) -> None:
    """Beta's WHOLE audit record up to a fixed `until`, 500 rows a page: every
    id exactly once, and as many as the window's own count says there are.
    The fixed edge is what makes the two numbers comparable while the sweep
    keeps writing rows."""
    until = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    query = {"until": until, "limit": "500"}
    first = _audit_page(api_call, beta_app, approver["token"], query)
    total = first["window_counts"]["total"]
    seen = [row["id"] for row in first["audit"]]
    cursor = first["next_cursor"]
    pages = 1
    while cursor is not None:
        page = _audit_page(api_call, beta_app, approver["token"], {**query, "cursor": cursor})
        assert page["window_counts"]["total"] == total, "the window moved under a fixed until"
        seen.extend(row["id"] for row in page["audit"])
        cursor = page["next_cursor"]
        pages += 1
        assert pages < 10_000, "the cursor never ended"
    assert len(seen) == len(set(seen)), "a row was visited twice"
    assert len(seen) == total, f"the walk visited {len(seen)} rows; the window counts {total}"
    print(f"beta's audit to {until}: {total} rows in {pages} pages")


def test_a_filtered_page_reports_the_refusals_it_did_not_show(
    approved_run: dict[str, Any],
    approver: dict[str, str],
    api_call: Callable[..., Any],
    beta_app: str,
) -> None:
    """D1248's objection, answered on production: a page filtered to
    `committed` shows no refusal, and its `window_counts` still count the
    `approval_required` refusal the approved run was parked by."""
    agent = approved_run["agent"].agent_id
    page = _audit_page(
        api_call, beta_app, approver["token"], {"agent_id": agent, "outcome": "committed"}
    )
    assert page["audit"], "no committed row for the approved run's agent"
    assert {row["outcome"] for row in page["audit"]} == {"committed"}
    counts = page["window_counts"]
    assert counts["by_outcome"].get("refused", 0) >= 1, counts
    assert counts["by_denial_reason"].get("approval_required", 0) >= 1, counts
