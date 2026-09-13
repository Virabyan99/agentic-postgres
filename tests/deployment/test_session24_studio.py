"""Session 24's live halves: a revocation a plane honoured, and the boundary it recorded.

**Two claims, and neither can be answered in a checkout.**

`STU-REVOKE-001` (`studio_revocation`). Studio's revocation is
`PATCH /admin/agents/{id}` — the existing endpoint, never a second path — and
what the claim is about is not that the request is well formed. It is that after
it, **the agent's next request is refused**: `agent_claims_are_current` no longer
matches the claims its live token carries, so the pre-request hook raises before
anything reads a row. Offline that is proved against a cluster this repository
stands up; here it is proved against the plane that is actually serving, with the
agent's own exchanged token, through the deployed MCP route.

`AGT-AUDIT-002` (`audit_boundary_reported`). Migration 0032 makes
`auth_list_agent_audit` return `denial_reason` and `GET /admin/audit` serialise
it. Offline, rows are written through the definer functions with a boundary
chosen by the test. Here nobody chooses it: a real agent is refused by the
running plane, the plane records whatever boundary refused it, and the endpoint
is asked what it says. **A declared field with no reader is an unverified field**
(D816, D929, D1247) — and a field read only from rows the reader wrote is the
same defect one step in.

**The two proofs read the same refusal two ways.** Studio shows it through the
forwarder; `api_call` reads it through the endpoint directly. They must agree,
and the second is what says the first is not rendering something of its own.

**The credential is the proof's own subject's** (D298, ADR 0095). An
audit-capable administrator is created through `app_private.auth_create_user` —
the same function `POST /admin/users` calls — and then LOGS IN through
`POST /auth/login`. Studio is handed that subject's name and a `0600` file the
proof wrote; there is no flag that would take the password any other way.

**Gated on two declarations, not three.** The plan named
`APG_ADMIN_PASSWORD_FILE` beside the other two, and
`tests/conftest.py::ENVIRONMENT_VARIABLES` is a CLOSED tuple that does not carry
it — `requires_environment` raises `UsageError` on a name outside it, so that a
typo cannot produce a test that silently never runs (D687). The third variable is
read by `admin_password`, which fails with the file's name when it is unset, and
this module gates on the two that are declared (D1278).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, service_source, studio

# ruff: noqa: S608 -- every literal here is this module's own constant, run by an
# operator's psql against the alpha project. The same waiver every deployment
# module carries, for the same reason.

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]

MCP_ACCEPT = "application/json, text/event-stream"

#: This module's own names. Fixed and nobody's real account: the sweeps below
#: delete by these names, and a generated one that leaked between runs would
#: accumulate rows nothing removes.
AUDITOR_USERNAME = "apg-s24-studio-auditor"
AUDITOR_PASSWORD = "s24-studio-auditor-9c41e7b0d268"  # noqa: S105 -- a probe credential
AGENT_NAME = "apg-s24-studio-reader"
AGENT_SECRET = "s24-studio-reader-3f80a2c5e194"  # noqa: S105 -- a probe credential

#: What the auditor holds, and why each one.
#:
#: `admin_audit:read` to see the record, `admin_agents:read` to see the roster
#: Studio lists, `admin_agents:write` because a revocation is a write and the
#: whole point of this module is that Studio carries no authority the subject
#: does not. Nothing else administrative.
AUDITOR_SCOPES = ("admin_agents:read", "admin_agents:write", "admin_audit:read")

#: The scope the agent holds, chosen because `list_resources` needs it and
#: nothing else does: a refusal below must be the REVOCATION, not a scope.
#: The probe agent's scopes.
#:
#: **D1297.** `meta:read` alone was not enough, and the reason is a decision
#: rather than an oversight: `list_resources` and `describe_resource` answer
#: from the loaded lock and reach nothing, so they sit outside `AUDITED_KINDS`
#: -- and `meta:read` is the scope for exactly those two. An agent holding only
#: it cannot produce an audit row at all, which made `AGT-AUDIT-002` ask for a
#: row that could never exist while `STU-REVOKE-001` was proved against a call
#: that reaches nothing.
#:
#: `notes:read` admits `query_resource` over the release's own relation, which
#: is `KIND_READ` and therefore audited. Alpha's vocabulary carries it.
AGENT_SCOPES = ("meta:read", "notes:read")

#: The relation the audited probe reads. The release's own, so this works on a
#: project that declares no set of its own -- alpha, which is where the
#: revocation proofs run.
AUDITED_RELATION = "notes"

#: Where the alpha manifest lives on the host. Inside the checkout for alpha and
#: beta, outside it for a third project (D971: a third manifest inside the
#: checkout dirties the release and every deploy refuses).
ALPHA_MANIFEST = REPO_ROOT / "project.alpha.yaml"


# ---------------------------------------------------------------------------
# the subjects, made the way every probe here is made
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mcp_route(project_a: dict[str, Any]) -> str:
    route = (project_a.get("routes") or {}).get("mcp")
    if not isinstance(route, dict) or route.get("status") != "ready" or not route.get("url"):
        pytest.fail(
            f"routes.mcp is {route!r}. The agent plane is not being served, so a refusal "
            "below would be a closed port rather than a revocation. D326's two-stage "
            "convergence means the FIRST deploy publishes 'unavailable'"
        )
    return str(route["url"])


@pytest.fixture(scope="module")
def mcp_rpc(api_call: Callable[..., Any]) -> Callable[..., Any]:
    """One JSON-RPC exchange with the agent plane. Returns, never judges."""

    def call(url: str, *, token: str | None, method: str, params: dict[str, Any] | None = None):
        return api_call(
            url,
            method="POST",
            token=token,
            body={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            headers={"Accept": MCP_ACCEPT},
        )

    return call


def sse_result(body: str) -> dict[str, Any] | None:
    """The JSON-RPC message out of an SSE response (D458).

    Byte-for-byte the helper Sessions 16, 21, 22 and 23 each carry. The agent
    plane runs `stateless_http` and answers `text/event-stream`: every reply is
    SSE-framed even when it is one message.
    """
    payload = None
    for line in body.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
    return payload


def mcp_message(answer: Any) -> dict[str, Any]:
    """One MCP reply, decoded the way the plane actually frames it.

    **This module set `MCP_ACCEPT` and never decoded what it asked for.**
    `json.loads` fails on an SSE body, and the fallback reported the failure as
    `{"error": {"message": "HTTP 200: event: message..."}}` -- so `refused()`
    saw an `error` key and every proof below read a SUCCESSFUL `list_resources`
    as a refusal. A 200 relayed as an error is D433's shape, inside a proof
    rather than a product, and it survived because the module had never run:
    its claims are host claims and this was their first execution.

    SSE first, then plain JSON, and only then an error -- and the error names
    the status, so "it answered something I cannot read" stays distinguishable
    from "it refused" (ADR 0195).
    """
    for decode in (sse_result, json.loads):
        try:
            message = decode(answer.body)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if isinstance(message, dict):
            return message
    return {"error": {"message": f"HTTP {answer.status}: {answer.body[:200]}"}}


def refused(result: dict[str, Any]) -> bool:
    """Session 16's helper. Reads BOTH shapes.

    A transport error puts `error` at the top level; a tool refusal puts
    `isError` inside `result`. Session 9's live proofs check only the first and
    pass on a refused write; that is the defect this helper exists to not
    repeat.
    """
    return "error" in result or bool(result.get("result", {}).get("isError"))


@pytest.fixture(scope="module")
def auditor(
    project_a: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
    tmp_path_factory: pytest.TempPathFactory,
) -> Any:
    """An audit- and agent-capable `project_admin`, and a `0600` file for Studio.

    `audit_admin`'s shape with this module's own names, so the two can run in one
    sweep without either sweeping the other's rows. Created through
    `auth_create_user` rather than through `POST /admin/users`, for the reason
    every probe subject here gives: a fixture built on an endpoint makes every
    proof below conditional on that endpoint.

    The password file is written under a `tmp_path`, mode `0600`, and removed
    with the rest of the temporary tree. It is the only way Studio will take a
    password apart from a TTY, and there is no TTY in a sweep.
    """
    hashing = service_source.load("hashing")
    role_name = project_a["database"]["roles"]["project_admin"]
    scopes = ", ".join(f"'{scope}'" for scope in sorted(AUDITOR_SCOPES))

    psql(project_a, f"DELETE FROM app_private.users WHERE username = '{AUDITOR_USERNAME}';")
    code, user_id, error = psql(
        project_a,
        "SELECT app_private.auth_create_user("
        f"'{AUDITOR_USERNAME}', 'Session 24 studio auditor', '{role_name}', "
        f"ARRAY[{scopes}]::text[], "
        f"'{hashing.Hasher().hash(AUDITOR_PASSWORD)}');",
    )
    assert code == 0 and user_id.strip(), f"could not create the studio auditor: {error}"

    password_file = tmp_path_factory.mktemp("studio-auditor") / "password"
    password_file.write_text(AUDITOR_PASSWORD + "\n", encoding="utf-8")
    password_file.chmod(0o600)

    try:
        answer = api_call(
            f"{app_base(project_a)}/auth/login",
            method="POST",
            body={"username": AUDITOR_USERNAME, "password": AUDITOR_PASSWORD},
        )
        assert answer.status == 200, (
            f"the studio auditor could not log in ({answer.status}: {answer.body[:200]}). "
            "Every refusal below would then be a refusal of a missing credential"
        )
        yield {
            "user_id": user_id.strip(),
            "token": json.loads(answer.body)["access_token"],
            "password_file": password_file,
        }
    finally:
        psql(project_a, f"DELETE FROM app_private.users WHERE username = '{AUDITOR_USERNAME}';")


@pytest.fixture(scope="module")
def reader_agent(
    project_a: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
    auditor: dict[str, Any],
) -> Any:
    """An agent owned by the auditor, with a token it exchanged for itself.

    `create_reader`'s shape. Swept in `finally` whatever happens — the audit rows
    it leaves behind are NOT swept, because the table is append-only by design
    and deleting a proof's own denials would be deleting the record this session
    exists to make readable.
    """
    hashing = service_source.load("hashing")
    role_name = project_a["database"]["roles"]["agent_reader"]
    scopes = ", ".join(f"'{scope}'" for scope in sorted(AGENT_SCOPES))

    psql(project_a, f"DELETE FROM app_private.agents WHERE name = '{AGENT_NAME}';")
    code, agent_id, error = psql(
        project_a,
        "SELECT app_private.auth_create_agent("
        f"'{AGENT_NAME}', 'Session 24 studio revocation probe', '{role_name}', "
        f"ARRAY[{scopes}]::text[], '{auditor['user_id']}', "
        f"'{hashing.Hasher().hash(AGENT_SECRET)}', NULL);",
    )
    assert code == 0 and agent_id.strip(), f"could not create {AGENT_NAME!r} on alpha: {error}"
    identifier = agent_id.strip()

    try:
        answer = api_call(
            f"{app_base(project_a)}/auth/agent-token",
            method="POST",
            body={"agent_id": identifier, "secret": AGENT_SECRET},
        )
        assert answer.status == 200, (
            f"the probe agent could not exchange its secret ({answer.status}: "
            f"{answer.body[:200]}), so a refusal below would say nothing about revocation"
        )
        yield {"agent_id": identifier, "token": json.loads(answer.body)["access_token"]}
    finally:
        psql(project_a, f"DELETE FROM app_private.agents WHERE name = '{AGENT_NAME}';")


# ---------------------------------------------------------------------------
# Studio, launched on the host by this proof
# ---------------------------------------------------------------------------


class Launched:
    """A running `apg studio`, its bound address, its launch key and its output."""

    def __init__(self, process: subprocess.Popen[str], url: str, lines: list[str]) -> None:
        self.process = process
        self.url = url
        self.lines = lines
        self.port = int(url.split("/open/")[0].rsplit(":", 1)[1])
        self.key = url.rsplit("/open/", 1)[1]
        self.bound = f"127.0.0.1:{self.port}"

    def call(self, method: str, path: str, payload: Any = None) -> tuple[int, Any]:
        """One page call, made the way the page makes it: the cookie, the header.

        `http.client` rather than the product's own HTTP helper, because the
        page is a browser and this is what a browser sends. Everything else in
        this module goes through `api_call`.
        """
        import http.client

        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Host": self.bound,
            "Cookie": f"{studio.LAUNCH_COOKIE}={self.key}",
            studio.CUSTOM_HEADER: "1",
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
        finally:
            connection.close()
        try:
            return response.status, json.loads(raw)
        except json.JSONDecodeError:
            return response.status, raw


@pytest.fixture(scope="module")
def launched_studio(auditor: dict[str, Any]) -> Any:
    """`bin/studio.sh` against this deployment, as the auditor (D1114).

    The product's own wrapper, as a subprocess, pointed at the op-owned copy of
    the deployed document — `APG_PROJECT_A_OUTPUTS` is what the whole deployment
    suite reads, and Studio is a client of a deployed document by decision
    (ADR 0158).
    """
    outputs = os.environ.get("APG_PROJECT_A_OUTPUTS")
    assert outputs, "APG_PROJECT_A_OUTPUTS is unset; the environment gate should have skipped"
    if not ALPHA_MANIFEST.is_file():
        pytest.fail(
            f"{ALPHA_MANIFEST} is not in this checkout. It is a gitignored operator input and "
            "the sweep runs where it lives; without it Studio cannot build the IR it compares "
            "the served surface against"
        )

    process = subprocess.Popen(
        [
            str(REPO_ROOT / "bin" / "studio.sh"),
            "--project", str(ALPHA_MANIFEST),
            "--outputs", outputs,
            "--username", AUDITOR_USERNAME,
            "--password-file", str(auditor["password_file"]),
        ],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )  # fmt: skip

    url = ""
    lines: list[str] = []
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        line = process.stdout.readline() if process.stdout else ""
        if not line:
            if process.poll() is not None:
                break
            continue
        lines.append(line.rstrip("\n"))
        if "open http://" in line:
            url = line.split("open ", 1)[1].strip()
            break

    if not url:
        process.kill()
        stderr = process.stderr.read() if process.stderr else ""
        pytest.fail(
            f"`apg studio` printed no URL against this deployment. stdout={lines} "
            f"stderr={stderr[:1000]}"
        )

    started = Launched(process, url, lines)
    try:
        yield started
    finally:
        started.process.terminate()
        try:
            started.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            started.process.kill()
            started.process.wait(timeout=10)


@pytest.fixture(scope="module")
def revocation(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    reader_agent: dict[str, Any],
    launched_studio: Launched,
) -> dict[str, Any]:
    """Perform the sequence once and RECORD it; the tests below do the judging.

    A fixture that asserted would turn every failure into an ERROR, which says
    the rig broke rather than which step did (D386). So this one takes the four
    readings in order and hands them over:

    1. the agent's next request BEFORE anything — the control that it works;
    2. Studio's revocation with a WRONG confirmation, and the agent's next
       request after it — the control that a refused confirmation changes
       nothing, without which step 4 proves only that something happened;
    3. Studio's revocation with the right one;
    4. the agent's next request after that.
    """
    agent_token = reader_agent["token"]
    identifier = reader_agent["agent_id"]

    def resources() -> dict[str, Any]:
        answer = mcp_rpc(mcp_route, token=agent_token, method="tools/call",
                         params={"name": "list_resources", "arguments": {}})  # fmt: skip
        return mcp_message(answer)

    def audited_read() -> dict[str, Any]:
        """A call the plane AUDITS, which `list_resources` is not (D1297).

        `query_resource` is `KIND_READ`: it reaches the database through the
        caller's own role and the plane opens an audit record for it. That is
        what gives `AGT-AUDIT-002` a row to read -- both the served one before
        the revocation and the refused one after, which is the pair that makes
        `denial_reason` mean something rather than being a constant.
        """
        answer = mcp_rpc(
            mcp_route,
            token=agent_token,
            method="tools/call",
            params={
                "name": "query_resource",
                "arguments": {"resource": AUDITED_RELATION, "limit": 1},
            },
        )
        return mcp_message(answer)

    before = resources()
    # An audited read on each side of the revocation, so the audit view has a
    # served row and a refused one to show (D1297).
    served_read = audited_read()
    wrong_status, wrong_body = launched_studio.call(
        "POST", "/__apg/revoke", {"agent_id": identifier, "confirm": "yes"}
    )
    after_wrong = resources()
    right_status, right_body = launched_studio.call(
        "POST", "/__apg/revoke", {"agent_id": identifier, "confirm": identifier}
    )
    after_right = resources()
    refused_read = audited_read()

    audit_status, audit_body = launched_studio.call("GET", f"/__apg/audit?agent_id={identifier}")

    return {
        "agent_id": identifier,
        "before": before,
        "wrong": (wrong_status, wrong_body),
        "after_wrong": after_wrong,
        "right": (right_status, right_body),
        "after_right": after_right,
        "served_read": served_read,
        "refused_read": refused_read,
        "audit": (audit_status, audit_body),
    }


# ---------------------------------------------------------------------------
# STU-REVOKE-001 -- the live half
# ---------------------------------------------------------------------------


def test_revocation_through_studio_refuses_the_agents_next_request_on_alpha(
    revocation: dict[str, Any], launched_studio: Launched
) -> None:
    """**STU-REVOKE-001.** A click in a page, and a plane refuses the next request.

    Four readings in one order, and the middle pair is what makes the last one
    evidence: a WRONG confirmation must be refused with 422 **and the agent must
    still work afterwards**. Without that control, an agent refused at step 4
    could equally mean the revocation happened at step 2, or that the token
    expired, or that the plane stopped answering — three states that look
    identical from outside and none of which is the property being claimed.

    The refusal is read with Session 16's `refused()`, which checks `isError`
    inside `result` as well as a top-level `error`. Session 9's live proofs read
    only the second and pass on a refused write; that is the defect this helper
    exists not to repeat.

    Goes red if: a revocation stops being the existing endpoint; the
    confirmation stops being checked in the process; the plane stops re-reading
    the agent's claims per request, which is `agent_claims_are_current`'s whole
    job and the reason a revoked agent stops on the NEXT request rather than at
    its token's expiry.
    """
    assert not refused(revocation["before"]), (
        "the probe agent's request was refused before anything was revoked, so every "
        f"reading below is about something else: {revocation['before']}"
    )

    wrong_status, wrong_body = revocation["wrong"]
    assert wrong_status == 422, (wrong_status, wrong_body)
    assert wrong_body["status"] == "invalid", wrong_body
    assert revocation["agent_id"] in wrong_body["reason"], (
        f"the refusal does not name the agent it expected: {wrong_body}"
    )
    assert not refused(revocation["after_wrong"]), (
        "the control failed: the agent stopped working after a REFUSED confirmation, so the "
        f"revocation below proves nothing about the confirmation — {revocation['after_wrong']}"
    )

    right_status, right_body = revocation["right"]
    assert right_status == 200, (right_status, right_body)
    assert right_body["status"] == "ok", right_body

    assert refused(revocation["after_right"]), (
        "the agent's next request was still served after Studio revoked it. A revoked agent "
        "stops on the NEXT request, not at its token's expiry — "
        f"{revocation['after_right']}"
    )

    # And the launch printed nothing it should not have. The auditor is a
    # `project_admin`, so the surface answer here is `stale_contract` by
    # construction (D1275) and the audit view works anyway, which is the split
    # this session built.
    printed = "\n".join(launched_studio.lines)
    assert AUDITOR_PASSWORD not in printed, printed
    assert AGENT_SECRET not in printed, printed


# ---------------------------------------------------------------------------
# AGT-AUDIT-002 -- the live half
# ---------------------------------------------------------------------------


def test_the_deployed_audit_read_carries_the_boundary_of_a_real_refusal(
    revocation: dict[str, Any],
    auditor: dict[str, Any],
    project_a: dict[str, Any],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
) -> None:
    """**AGT-AUDIT-002.** The boundary a running plane recorded, read two ways.

    Nobody chose this denial reason. A real agent was refused by the plane that
    is actually serving, the plane wrote whatever boundary refused it, and both
    readers are asked what it says: Studio through its forwarder, and
    `GET /admin/audit` directly through `api_call`. **They must agree**, and the
    direct read is what says Studio is not rendering something of its own.

    The `served` rows are checked too, and they are the half that makes the
    field mean something: `denial_reason` non-null on a refused row is only
    informative if it is null on a row nothing refused. A column that always
    carried a value would be a constant with a column's name.

    Goes red if: migration 0032 is lost in a fix-forward; the endpoint stops
    serialising the member; the plane records a denial without its boundary; or
    Studio's audit view starts deciding what to show.
    """
    studio_status, studio_body = revocation["audit"]
    assert studio_status == 200, (studio_status, studio_body)
    assert studio_body["status"] == "ok", (
        f"Studio's audit view was not served to a subject holding admin_audit:read: {studio_body}"
    )
    studio_rows = studio_body["rows"]
    assert studio_rows, (
        "the plane recorded no audit row at all for the revoked agent. A denial that is not "
        "audited is the state ADR 0135 exists to prevent"
    )

    direct = api_call(
        f"{app_base(project_a)}/admin/audit?agent_id={revocation['agent_id']}",
        token=auditor["token"],
    )
    assert direct.status == 200, f"{direct.status}: {direct.body[:300]}"
    direct_rows = json.loads(direct.body)["audit"]

    # Keyed on `id`, which is what both readers call it: the endpoint
    # serialises `"id": str(row["id"])` and Studio relays `payload["audit"]`
    # unchanged -- which is itself half of what this proof checks. The table
    # has no `audit_id`; migration 0019 declares `id uuid PRIMARY KEY` (D1298).
    by_id = {row["id"]: row for row in direct_rows}
    assert by_id, "the endpoint returned no row for an agent Studio showed rows for"

    refusals = [row for row in direct_rows if row["outcome"] == "refused"]
    assert refusals, (
        f"the plane refused this agent's request and recorded no `refused` row: "
        f"{[row['outcome'] for row in direct_rows]}"
    )
    for row in refusals:
        assert row["denial_reason"], (
            "a refused row carries no boundary. That is exactly D1247: the column was "
            f"declared, the plane wrote it, and the reader did not return it — {row}"
        )

    for row in direct_rows:
        if row["outcome"] == "served":
            assert row["denial_reason"] is None, (
                "a served row carries a denial boundary, so the field is not the boundary "
                f"that refused — it is something else with that name: {row}"
            )

    # The two readers agree, row for row, on the field this claim is about.
    studio_by_id = {row["id"]: row for row in studio_rows}
    shared = set(studio_by_id) & set(by_id)
    assert shared, (
        f"Studio and the endpoint returned disjoint sets of rows for one agent: "
        f"{sorted(studio_by_id)[:3]} vs {sorted(by_id)[:3]}"
    )
    for audit_id in sorted(shared):
        assert studio_by_id[audit_id]["denial_reason"] == by_id[audit_id]["denial_reason"], (
            f"Studio and the endpoint disagree about row {audit_id}'s boundary: "
            f"{studio_by_id[audit_id]['denial_reason']!r} vs "
            f"{by_id[audit_id]['denial_reason']!r}"
        )
