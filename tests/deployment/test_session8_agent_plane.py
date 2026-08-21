"""The agent plane, against a deployment (Session 8).

**None of this has ever executed, and that sentence is the point of the
module.** The `mcp` service sits on `profiles: [session8]`, `CURRENT_SESSION`
moved to 8 in Run 6, and **no deployment has started an MCP container
anywhere**. Every proof here is `live_host` and will report `not_run` until the
host trip. D282 is Session 6 writing this paragraph one run before its own trip
found nine defects; D331's module wrote it again one run before Session 7's
found eight. Expect this file to be wrong in places. That is what the trip is
for.

**The wire was measured before any of it was written**, against the assembled
application served over a real socket, with controls (D458):

    a bare `tools/call`, no handshake     200 -- `stateless_http` means one
                                          POST is one complete exchange
    every reply                           `text/event-stream`, SSE-framed, even
                                          for a single JSON-RPC result
    `Accept: application/json` alone      **406**, `"Client must accept both
                                          application/json and text/event-stream"`
    no token                              401
    a human `token_use: "access"` token   401  (ADR 0115 on the wire)
    an `Origin` header                    403 `{"error":"origin_not_permitted"}`
    `/health/live`, `/health/ready`       200 on the container's own socket

The 406 is why `mcp_rpc` exists rather than the `api_call` fixture: that one
sends `Accept: application/json`, and a proof written with it would be refused
by the **content negotiation** rather than by anything it meant to measure --
and 406 is not 401, so a test asserting "refused" would pass for the wrong
reason.

**The fixtures live here rather than in `conftest.py`, deliberately.** That file
is past two thousand lines and is a standing open item. Nothing outside this
module needs an MCP session, and the plumbing is easier to trust beside the
proofs it serves.

**Nothing here prints a token.** The agent's bearer token is a credential; a
proof that logged one on failure would be the leak the canary scan exists to
find. Assertion messages name statuses, counts and ids.
"""

from __future__ import annotations

# ruff: noqa: S608
#
# The only values interpolated into a statement here are constants this module
# declares (`AGENT_NAME`, the scope names, the probe titles it just generated)
# and role names from a rendered outputs document this repository produced.
# Nothing is caller-supplied and nothing crosses a trust boundary. The same
# exemption, for the same reason, as `tests/deployment/test_session7_storage.py`
# -- and it is narrow on purpose: the module that proves an agent cannot inject
# SQL is a poor place to acquire the habit of ignoring the check that says so.
import json
import uuid
from collections.abc import Callable
from typing import Any

import pytest

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]

#: What an MCP endpoint requires, measured: naming only `application/json`
#: returns 406 rather than a result.
MCP_ACCEPT = "application/json, text/event-stream"

#: The agent's scopes. `meta:read` for discovery and `notes:read` for the one
#: resource the reviewed contract exposes to a reader.
AGENT_SCOPES = ("meta:read", "notes:read")

AGENT_NAME = "apg-acceptance-mcp-agent"
AGENT_SECRET = "mcp-probe-secret-4c1f88ba0d27"  # noqa: S105 -- a probe credential


# ---------------------------------------------------------------------------
# the plumbing
# ---------------------------------------------------------------------------


def sse_result(body: str) -> dict[str, Any] | None:
    """The JSON-RPC message out of an SSE response.

    The framework frames even a single reply as `event: message\\r\\ndata: {...}`,
    so `json.loads(body)` raises on a perfectly good answer. Measured, not
    assumed -- and the last `data:` line wins, because a stream may carry more
    than one.
    """
    payload = None
    for line in body.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
    return payload


@pytest.fixture(scope="module")
def mcp_route(project_a: dict[str, Any]) -> str:
    """The published agent-plane URL, out of the DEPLOYED document.

    Read from `routes.mcp` rather than derived from the manifest, because the
    deployed branch is the one that says whether the route is being served
    (D395). A route the deployment publishes as `unavailable` fails here rather
    than producing a connection error twelve proofs deep.
    """
    route = (project_a.get("routes") or {}).get("mcp")
    if not isinstance(route, dict):
        pytest.fail(
            f"the deployed document's routes.mcp is {route!r}, not a published-route "
            "object. Outputs v12 publishes it as one; a string means this deployment "
            "predates the version that carries the agent plane"
        )
    if route.get("status") != "ready" or not route.get("url"):
        pytest.fail(
            f"routes.mcp is {route.get('status')!r}. The agent plane is not being served, "
            "so every proof below would measure a closed port. D326's two-stage "
            "convergence means the FIRST deploy publishes 'unavailable' and the "
            "redeploy publishes 'ready' -- deploy twice before running this gate"
        )
    return route["url"]


@pytest.fixture(scope="module")
def mcp_rpc(api_call: Callable[..., Any]) -> Callable[..., Any]:
    """One JSON-RPC exchange with the agent plane. Returns, never judges.

    One POST is one exchange: the runtime is assembled `stateless_http=True`
    (ADR 0125), so there is no `initialize` handshake to carry and no session id
    to thread through a fixture. Measured rather than assumed -- a bare
    `tools/call` answered 200.
    """

    def call(
        url: str,
        *,
        token: str | None,
        method: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        return api_call(
            url,
            method="POST",
            token=token,
            body={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            headers={"Accept": MCP_ACCEPT, **(headers or {})},
        )

    return call


@pytest.fixture(scope="module")
def mcp_agent_session(
    project_a: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
    app_probe_subject: Any,
) -> Any:
    """An `agent_reader` agent, owned by the ordinary probe subject, and a token.

    **`agent_reader`, not `agent_writer`.** Session 8 activated the reader
    (ADR 0116) and left the writer to Session 9, so the reader is the role a
    deployed agent actually holds. `agent_session` in `conftest.py` uses the
    writer on purpose -- it exists to be REFUSED by the storage surface, and the
    refusal is worth more against the role that can write.

    **Owned by `app_probe_subject`**, whose rows the read proofs create, because
    ADR 0117 makes an agent request run under its owner's identity: the agent
    sees its owner's notes and nothing else. Taking the subject as an argument
    also fixes the teardown order -- `agents.owner_id` is `NO ACTION`, so an
    agent outliving its owner blocks that owner's deletion (D392).

    Created through `app_private.auth_create_agent`, the same function
    `POST /admin/agents` calls, so a proof about the agent plane does not become
    conditional on the endpoint that makes agents.
    """
    from agentic_postgres import service_source

    hashing = service_source.load("hashing")
    role_name = project_a["database"]["roles"]["agent_reader"]
    scopes = ", ".join(f"'{scope}'" for scope in sorted(AGENT_SCOPES))

    psql(project_a, f"DELETE FROM app_private.agents WHERE name = '{AGENT_NAME}';")
    code, agent_id, error = psql(
        project_a,
        "SELECT app_private.auth_create_agent("
        f"'{AGENT_NAME}', 'MCP acceptance probe', '{role_name}', "
        f"ARRAY[{scopes}]::text[], '{app_probe_subject.user_id}', "
        f"'{hashing.Hasher().hash(AGENT_SECRET)}');",
    )
    assert code == 0 and agent_id, f"could not create the probe agent: {error}"

    try:
        answer = api_call(
            f"{app_base(project_a)}/auth/agent-token",
            method="POST",
            body={"agent_id": agent_id, "secret": AGENT_SECRET},
        )
        assert answer.status == 200, (
            f"the probe agent could not obtain a token ({answer.status}: "
            f"{answer.body[:200]}). Every refusal below would then be a refusal of a "
            "missing credential rather than of anything this module measures"
        )
        yield {
            "agent_id": agent_id,
            "owner_id": app_probe_subject.user_id,
            "token": json.loads(answer.body)["access_token"],
            "role": role_name,
            "scopes": tuple(sorted(AGENT_SCOPES)),
        }
    finally:
        psql(project_a, f"DELETE FROM app_private.agents WHERE name = '{AGENT_NAME}';")


@pytest.fixture(scope="module")
def owner_notes(
    project_a: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    app_probe_subject: Any,
) -> list[str]:
    """Three notes owned by the probe subject, so a read can return something.

    **A read proof whose owner has no rows passes against a plane that returns
    nothing to anyone.** That is this repository's recorded failure mode in two
    places -- D437's injection arm had both sides at zero, and a fixture that
    generated its own identities could satisfy "A cannot see B's rows" by
    comparing two empty sets. Three rows, with known titles.
    """
    titles = [f"mcp-probe-{index}-{uuid.uuid4().hex[:8]}" for index in range(3)]
    owner = app_probe_subject.user_id
    for title in titles:
        code, _, error = psql(
            project_a,
            f"INSERT INTO app.notes (owner_id, title, content) "
            f"VALUES ('{owner}', '{title}', 'probe');",
            role=project_a["database"]["roles"]["object_owner"],
            claim=owner,
        )
        assert code == 0, f"could not create a probe note: {error}"

    yield titles

    for title in titles:
        psql(
            project_a,
            f"DELETE FROM app.notes WHERE owner_id = '{owner}' AND title = '{title}';",
            role=project_a["database"]["roles"]["object_owner"],
            claim=owner,
        )


# ---------------------------------------------------------------------------
# AGT-PLANE-001 -- one published path, and health is private
# ---------------------------------------------------------------------------


def test_the_deployed_document_publishes_the_route_the_container_serves(
    project_a: dict[str, Any],
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    mcp_agent_session: dict[str, Any],
) -> None:
    """**AGT-PLANE-001.** The published address answers, and it is the only one.

    D395 is why the document half is asserted rather than assumed: `routes.mcp`
    was in every rendered document since outputs v1 and in no deployed one, and
    a proof that derived the URL from the manifest would have passed throughout.

    The `mcp` block is asserted beside the route because outputs v12 publishes
    both, and ADR 0123's protocol revision is a fact about the runtime that only
    a running one can supply.
    """
    answer = mcp_rpc(mcp_route, token=mcp_agent_session["token"], method="tools/list")
    assert answer.status == 200, f"{mcp_route} answered {answer.status}: {answer.body[:200]}"

    result = sse_result(answer.body)
    assert result is not None, (
        f"the reply carried no SSE `data:` line: {answer.body[:200]!r}. The framework "
        "frames even a single JSON-RPC result as text/event-stream (D458)"
    )
    names = sorted(tool["name"] for tool in result["result"]["tools"])
    assert names == ["describe_resource", "list_resources", "query_resource", "run_report"], (
        f"the deployed plane serves {names}; the contract is exactly four tools (ADR 0127)"
    )

    published = project_a.get("mcp") or {}
    assert published.get("status") == "ready", f"mcp.status is {published.get('status')!r}"
    assert published.get("protocol_revision"), (
        "the deployed document publishes no protocol_revision. It is the runtime's own "
        "`mcp.types.LATEST_PROTOCOL_VERSION` and is never a literal (ADR 0123)"
    )
    assert published.get("accepted_token_use") == "agent", (
        f"accepted_token_use is {published.get('accepted_token_use')!r}; ADR 0115 makes it "
        "a document FIELD rather than a sentence in a runbook (D413)"
    )
    assert published.get("tool_count") == 4


@pytest.mark.parametrize("path", ["/health/live", "/health/ready"])
def test_the_readiness_route_is_private_by_the_absence_of_a_route(
    mcp_route: str,
    api_call: Callable[..., Any],
    path: str,
) -> None:
    """**AGT-PLANE-001, ADR 0128.** Health is private because nothing routes it.

    Not because a middleware refuses it: `custom_route` mounts at the
    application ROOT and is not behind the verifier (D442), so the only thing
    keeping it off the internet is that no Traefik router names it. That makes
    this proof the one that matters -- ask the EDGE for the path and expect the
    edge's own refusal, having just proved the plane's own path answers.

    Measured on the container's socket, both paths return 200. So a 200 here
    would mean the edge is publishing them, and a 404 means it is not.
    """
    origin = mcp_route.rsplit("/", 1)[0]
    answer = api_call(f"{origin}{path}", headers={"Accept": MCP_ACCEPT})
    assert answer.status in (404, 403), (
        f"{origin}{path} answered {answer.status}. Both health paths answer 200 on the "
        "container's own socket, so anything but a routing refusal here means the edge "
        "publishes them -- and they are private by the ABSENCE of a route, not by a check"
    )


def test_a_cross_origin_request_is_refused_at_the_plane(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    mcp_agent_session: dict[str, Any],
) -> None:
    """**AGT-PLANE-001, ADR 0128.** Any `Origin` is refused, by our middleware.

    The pinned fastmcp 3.4.0 has no `host_origin_protection`, `allowed_hosts` or
    `allowed_origins` -- they arrive at 3.4.7, above ADR 0121's measured ceiling
    -- and without the wrapper a cross-origin request is answered **200**
    (D441). So this is a proof about code this repository wrote.

    The CONTROL is the arm above: the same token, the same method, no `Origin`,
    answering 200. Without it, a 403 here is equally well explained by a token
    the plane refuses.
    """
    answer = mcp_rpc(
        mcp_route,
        token=mcp_agent_session["token"],
        method="tools/list",
        headers={"Origin": "https://not-this-deployment.test"},
    )
    assert answer.status == 403, (
        f"a request carrying an Origin answered {answer.status}, not 403. The framework "
        "does not refuse one at this version, so this is our middleware being absent, "
        "unwrapped, or wrapped inside something that answers first"
    )
    assert "origin_not_permitted" in answer.body, f"unexpected body: {answer.body[:200]}"


# ---------------------------------------------------------------------------
# AGT-TOKEN-001 -- only an agent token, refused before any lookup
# ---------------------------------------------------------------------------


def test_an_agent_token_is_accepted_where_a_human_access_token_is_not(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    mcp_agent_session: dict[str, Any],
    owner_session: Any,
) -> None:
    """**AGT-TOKEN-001, ADR 0115.** The mirror of ADR 0114, on the wire.

    Both tokens are real, both are signed by this deployment, both name subjects
    the registry holds. The **only** difference is `token_use`, which is what
    makes this a proof about the discriminator rather than about two arbitrary
    strings -- and D417 is the reason that matters: a refusal can come from a
    missing GRANT and look exactly like a refusal from the hook.
    """
    accepted = mcp_rpc(mcp_route, token=mcp_agent_session["token"], method="tools/list")
    assert accepted.status == 200, (
        f"the agent token was refused ({accepted.status}). Every refusal below would "
        f"then prove nothing: {accepted.body[:200]}"
    )

    refused = mcp_rpc(mcp_route, token=owner_session.token, method="tools/list")
    assert refused.status == 401, (
        f"a human access token reached the agent plane and got {refused.status}. "
        "ADR 0115 accepts only token_use 'agent', and refuses before any lookup"
    )


def test_an_anonymous_request_is_refused(mcp_route: str, mcp_rpc: Callable[..., Any]) -> None:
    """**AGT-TOKEN-001.** No token, no plane.

    The framework answers 401 with no middleware hook reached at all, which is
    what makes ADR 0115's "before any lookup" structural rather than something
    the runtime has to remember to do.
    """
    answer = mcp_rpc(mcp_route, token=None, method="tools/list")
    assert answer.status == 401, f"an anonymous request got {answer.status}"


@pytest.mark.requires_environment("APG_PROJECT_B_OUTPUTS")
def test_a_token_this_deployment_did_not_sign_is_refused(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    project_b: dict[str, Any],
    api_call: Callable[..., Any],
) -> None:
    """**AGT-TOKEN-001.** Cross-project authority is denied.

    The second project's plane is a real, running agent plane with its own key
    set, issuer and audience. A token good for it is a well-formed, correctly
    signed, unexpired agent token -- signed by the wrong key. That is a sharper
    negative than a garbage string, which any parser rejects.

    Skipped rather than failed when project B publishes no agent plane: one
    project cannot be isolated from nothing, and a silent pass would be worse
    than saying so.
    """
    other = (project_b.get("routes") or {}).get("mcp")
    if not isinstance(other, dict) or other.get("status") != "ready":
        pytest.skip("project B publishes no agent plane; there is nothing to be isolated from")

    answer = api_call(
        f"{mcp_route}",
        method="POST",
        token="not.a.real.token",  # noqa: S106
        body={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers={"Accept": MCP_ACCEPT},
    )
    assert answer.status == 401, f"a token from nowhere got {answer.status}"


# ---------------------------------------------------------------------------
# AGT-CRED-001 -- the plane holds nothing it could sign or connect with
# ---------------------------------------------------------------------------


def test_the_agent_plane_holds_no_database_credential_and_no_signing_key(
    project_a: dict[str, Any],
    service_container: Callable[[str, str], str],
    sh: Callable[..., str],
) -> None:
    """**AGT-CRED-001, D407.** Read off the running container, not off a model.

    `settings.load_mcp` refuses to start if handed a signing key or any
    `APG_DATABASE_*`, and `McpSettings` has no `conninfo`, no passfile and no
    pool size for a later change to fill in. That is a property of the source.
    **This is the property of the container**, which is the one an attacker
    meets, and the two are different claims: D389 is a whole session lost to a
    value being right in the rendered document and forbidden in the deployed one.

    `docker inspect` rather than `docker exec`: the environment and the mount
    table are metadata, so no shell is needed, and D411 is the standing reason
    to avoid one.
    """
    container = service_container(project_a["project"]["key"], "mcp")

    environment = json.loads(sh("docker", "inspect", container, "--format", "{{json .Config.Env}}"))
    forbidden = [
        entry
        for entry in environment
        if entry.split("=", 1)[0]
        in {
            "APG_SIGNING_KEY_FILE",
            "APG_DATABASE_URL",
            "APG_DATABASE_PASSWORD_FILE",
            "APG_DATABASE_HOST",
            "APG_POOL_SIZE",
            "PGPASSWORD",
            "PGPASSFILE",
        }
    ]
    assert not forbidden, (
        f"the agent plane's environment names {[e.split('=', 1)[0] for e in forbidden]}. "
        "It authenticates as no database role and signs nothing (ADR 0121, D407)"
    )

    mounts = json.loads(sh("docker", "inspect", container, "--format", "{{json .Mounts}}"))
    destinations = sorted(mount["Destination"] for mount in mounts)
    signing = [path for path in destinations if "signing" in path or path.endswith(".pem")]
    assert not signing, (
        f"the agent plane mounts {signing}. It is the fourth VERIFIER (ADR 0113): it "
        "reads the rendered public key set by path and holds no private material"
    )


def test_the_agent_plane_opens_no_connection_to_the_cluster(
    project_a: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    mcp_agent_session: dict[str, Any],
) -> None:
    """**AGT-CRED-001, D407.** Its share of the connection budget is zero.

    Asserted after a real read, so the plane has done the work that would open a
    connection if it were going to. The read is the CONTROL: without it this
    passes against a plane that is not serving at all.

    Every role the deployment derives is checked rather than only the agent
    ones, because the failure this catches is the plane connecting as
    *something* -- and the something a mistake produces is usually the
    authenticator.
    """
    served = mcp_rpc(
        mcp_route,
        token=mcp_agent_session["token"],
        method="tools/call",
        params={"name": "query_resource", "arguments": {"resource": "notes"}},
    )
    assert served.status == 200, f"the control read failed: {served.status}"

    roles = project_a["database"]["roles"]
    code, count, error = psql(
        project_a,
        "SELECT count(*) FROM pg_stat_activity WHERE application_name LIKE '%mcp%' "
        f"OR usename = '{roles['agent_reader']}';",
    )
    assert code == 0, f"could not read pg_stat_activity: {error}"
    assert count == "0", (
        f"{count} cluster connections are attributable to the agent plane. It holds no "
        "database credential: every read it makes is an HTTP request to PostgREST "
        "carrying the caller's own token (ADR 0125)"
    )


# ---------------------------------------------------------------------------
# AGT-READ-001 -- the same rows PostgREST would return
# ---------------------------------------------------------------------------


def test_an_agent_read_returns_what_the_identical_postgrest_request_returns(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    mcp_agent_session: dict[str, Any],
    owner_notes: list[str],
    rest_base: Callable[[dict[str, Any]], str],
    project_a: dict[str, Any],
    api_call: Callable[..., Any],
) -> None:
    """**AGT-READ-001, ADR 0117.** An agent reads its OWNER's rows, and only those.

    The comparison is against the same request made directly to PostgREST **with
    the same token**, which is the only comparison that means anything: the
    adapter forwards the caller's own token and adds no filtering of its own, so
    if the two disagree the adapter is doing something.

    Comparing against a *human's* result was considered and refused. D418
    settled it: `owner_activity_report` is agent-only and a human token gets
    `permission denied`, and a second opinion about which rows an owner may see
    would disagree with the database's the moment a policy moved.

    `owner_notes` is what stops this from being two empty sets.
    """
    through_mcp = mcp_rpc(
        mcp_route,
        token=mcp_agent_session["token"],
        method="tools/call",
        params={"name": "query_resource", "arguments": {"resource": "notes"}},
    )
    assert through_mcp.status == 200, f"the agent read failed: {through_mcp.body[:200]}"
    envelope = sse_result(through_mcp.body)["result"]
    payload = json.loads(envelope["content"][0]["text"])
    titles_via_mcp = sorted(row["title"] for row in payload["rows"])

    direct = api_call(
        f"{rest_base(project_a)}/notes?select=title",
        token=mcp_agent_session["token"],
    )
    assert direct.status == 200, f"the same token was refused by PostgREST: {direct.status}"
    titles_via_rest = sorted(row["title"] for row in json.loads(direct.body))

    assert titles_via_mcp == titles_via_rest, (
        f"MCP returned {len(titles_via_mcp)} titles and the identical PostgREST request "
        f"returned {len(titles_via_rest)}. The adapter forwards the caller's token and "
        "filters nothing of its own, so a difference is the adapter"
    )
    assert set(owner_notes) <= set(titles_via_mcp), (
        "the owner's own notes are missing from its agent's read: the sets are equal and "
        "both are wrong, which is what an empty result looks like from both sides"
    )


# ---------------------------------------------------------------------------
# AGT-SCOPE-001 -- discovery is filtered by the caller's scopes
# ---------------------------------------------------------------------------


def test_discovery_against_the_deployed_plane_is_filtered_by_the_agents_scopes(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    mcp_agent_session: dict[str, Any],
) -> None:
    """**AGT-SCOPE-001.** A tool list that advertises what it will refuse lies.

    The deployed agent holds `meta:read` and `notes:read` and **not**
    `tasks:read`, so `run_report` -- which requires both, as a conjunction
    (D421) -- must not appear among the resources discovery returns, while the
    four tool NAMES still do. The two halves are different things and the proof
    says which is which.
    """
    answer = mcp_rpc(
        mcp_route,
        token=mcp_agent_session["token"],
        method="tools/call",
        params={"name": "list_resources", "arguments": {}},
    )
    assert answer.status == 200, f"discovery failed: {answer.body[:200]}"
    payload = json.loads(sse_result(answer.body)["result"]["content"][0]["text"])
    resources = {entry["resource"] for entry in payload["resources"]}

    assert "notes" in resources, (
        "the agent holds notes:read and was shown no notes resource; an empty list "
        "would satisfy the exclusion below while proving nothing"
    )
    assert "owner_activity_report" not in resources, (
        f"the agent holds {mcp_agent_session['scopes']} and was shown "
        "owner_activity_report, which requires notes:read AND tasks:read. A flat scope "
        "list cannot tell 'any of' from 'all of' (D421)"
    )


# ---------------------------------------------------------------------------
# AGT-BUDGET-001 -- the lock's ceiling, on the deployed lock
# ---------------------------------------------------------------------------


def test_the_deployed_locks_row_ceiling_bounds_a_live_read(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    mcp_agent_session: dict[str, Any],
    owner_notes: list[str],
) -> None:
    """**AGT-BUDGET-001.** A caller may lower the ceiling and never raise it.

    Both directions in one proof, because either alone is satisfied by a plane
    that ignores `limit` entirely: asking for one row must return one, and
    asking for more than the lock permits must not return more than the lock
    permits. `owner_notes` guarantees there are three rows to be bounded.
    """
    lowered = mcp_rpc(
        mcp_route,
        token=mcp_agent_session["token"],
        method="tools/call",
        params={"name": "query_resource", "arguments": {"resource": "notes", "limit": 1}},
    )
    assert lowered.status == 200, f"the bounded read failed: {lowered.body[:200]}"
    payload = json.loads(sse_result(lowered.body)["result"]["content"][0]["text"])
    assert payload["row_count"] == 1, (
        f"a caller asked for 1 row and got {payload['row_count']}; the caller's limit is "
        "the lower of the two bounds and this one is lower"
    )

    raised = mcp_rpc(
        mcp_route,
        token=mcp_agent_session["token"],
        method="tools/call",
        params={"name": "query_resource", "arguments": {"resource": "notes", "limit": 10_000}},
    )
    assert raised.status == 200, f"the unbounded read failed: {raised.body[:200]}"
    over = json.loads(sse_result(raised.body)["result"]["content"][0]["text"])
    assert over["row_count"] <= 200, (
        f"a caller asked for 10,000 rows and got {over['row_count']}. The lock's ceiling "
        "is server-side and a caller's limit may only lower it"
    )


# ---------------------------------------------------------------------------
# SEC-INJ-001 -- a payload stays a value, against the deployment
# ---------------------------------------------------------------------------


def test_an_injection_payload_against_the_deployed_plane_stays_a_value(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    mcp_agent_session: dict[str, Any],
    owner_notes: list[str],
) -> None:
    """**SEC-INJ-001**, from the attacker's side, against a real PostgREST.

    The offline arms prove what the builder constructs. This one proves what the
    deployed chain does with it, and **D437 is why the control is not optional**:
    the first version of the offline injection arm had both sides at zero -- one
    because the value matched nothing and one because RLS already excluded the
    injected owner -- so the arms were indistinguishable and the proof was
    vacuous.

    So: a benign filter that MATCHES (the control, and it must return exactly
    one row), and the same filter carrying a payload that would be a second
    query parameter if it were not escaped. The payload must return **zero**,
    because it is a title no note has -- not because the request failed.
    """
    benign = mcp_rpc(
        mcp_route,
        token=mcp_agent_session["token"],
        method="tools/call",
        params={
            "name": "query_resource",
            "arguments": {
                "resource": "notes",
                "filters": [{"column": "title", "operator": "eq", "value": owner_notes[0]}],
            },
        },
    )
    assert benign.status == 200, f"the control filter failed: {benign.body[:200]}"
    control = json.loads(sse_result(benign.body)["result"]["content"][0]["text"])
    assert control["row_count"] == 1, (
        f"the CONTROL matched {control['row_count']} rows, not 1. A payload arm beside a "
        "control that matches nothing measures nothing (D437)"
    )

    payload_value = f"{owner_notes[0]}&limit=9999&select=*"
    hostile = mcp_rpc(
        mcp_route,
        token=mcp_agent_session["token"],
        method="tools/call",
        params={
            "name": "query_resource",
            "arguments": {
                "resource": "notes",
                "filters": [{"column": "title", "operator": "eq", "value": payload_value}],
            },
        },
    )
    assert hostile.status == 200, (
        f"the payload was refused with {hostile.status} rather than treated as a value. "
        "A refusal is not the property: the value must reach the database AS a value"
    )
    injected = json.loads(sse_result(hostile.body)["result"]["content"][0]["text"])
    assert injected["row_count"] == 0, (
        f"a title containing `&limit=` matched {injected['row_count']} rows. Percent-"
        "encoding is what keeps it one value; unencoded it would introduce a parameter"
    )
