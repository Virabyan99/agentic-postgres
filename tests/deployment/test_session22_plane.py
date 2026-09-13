"""Session 22's live halves: the count the plane confirms, and the grant it needs.

**Two claims, and neither can be answered anywhere but on a deployment.**

`OPS-PLANE-001` (`plane_confirmed_count`). D1152: on 2026-09-11 beta served six
tools and refused a tenant's scope for eight minutes while the deployed document
said seven. A deploy whose only change is the capability lock recreates no
container unless the container's mount digest moved (ADR 0155), so the file the
document reads and the process answering requests are two different facts. Every
offline proof of the repair works against a recorded probe; this one asks the
running container what it loaded and compares that to what the document
published. There is no offline form, because the disagreement it exists to catch
is between a file and a process (ADR 0065/0066).

`AGT-TENANT-002` (`agent_tenant_read`). Session 21 proved the tenant surface by
DISCOVERY and by a REFUSAL: beta's lock carries the tool, alpha's does not, and
alpha refuses the scope at issue and at creation. What neither proved is the
door -- a capability compiler reads a reviewed surface and a project's snapshot
is captured as `api_documentation`, so neither can see a `GRANT`, and until the
tenant's own set issues one an agent holding `note_embeddings:read` is served
the tool and refused by the database (D1156). Migration `20260914120002` is the
tenant's half; this reads rows back through the tool.

**Measured at Session 24's trip, not Session 22's close.** Session 22 has no
host trip (D1163, ADR 0202): it closes on its offline half alone, and these two
claims are registered now with their live proofs gated on the roster variables
so that the next trip runs them rather than rediscovering that they are owed.
Session 24's plan owes a deploy `--through-session >= 22` first, so the example
set's second migration applies on beta.

The subject, the agent and the row are made through the deployed cluster's own
functions and swept afterwards (D392), the same way Session 21's module makes
them -- and the row is planted as the agent's OWN caller, because
`api.note_embeddings` is a `security_invoker` view over a FORCE row-level-
security table: a grant widens who may ask and never whose rows come back, so a
proof that read somebody else's rows would be measuring the absence of the
policy rather than the presence of the grant.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from agentic_postgres import agent_plane, deployed_output, runtime_override

# ruff: noqa: S608 -- every literal here is this module's own constant, run by an
# operator's psql against probe projects. The same waiver every deployment
# module carries, for the same reason.
pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"
    ),
]

MCP_ACCEPT = "application/json, text/event-stream"
TENANT_RELATION = "note_embeddings"
OWNER_USERNAME = "apg-s22-tenant-owner"
OWNER_PASSWORD = "tenant-owner-probe-2f81a4c7e0b9"  # noqa: S105 -- a probe credential
READER_NAME = "apg-s22-tenant-reader"
AGENT_SECRET = "s22-tenant-secret-7b2f4c1e9d03"  # noqa: S105 -- a probe credential
READER_SCOPES = ("meta:read", "note_embeddings:read")
GRANT_VERSION = "20260914120002"
EMBEDDING = "[" + ", ".join("0.002" for _ in range(768)) + "]"


def sse_result(body: str) -> dict[str, Any] | None:
    """The JSON-RPC message out of an SSE response (D458)."""
    payload = None
    for line in body.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
    return payload


def refused(result: dict[str, Any]) -> bool:
    """Both shapes. A refusal arrives as `result.isError`, not only as `error`."""
    return "error" in result or bool(result.get("result", {}).get("isError"))


def tool_text(result: dict[str, Any]) -> str:
    if "error" in result:
        return str(result["error"].get("message", result["error"]))
    content = result["result"]["content"]
    return str(content[0].get("text", "")) if content else ""


def mcp_route_of(document: dict[str, Any]) -> str:
    route = (document.get("routes") or {}).get("mcp")
    if not isinstance(route, dict) or route.get("status") != "ready" or not route.get("url"):
        pytest.fail(
            f"{document['project']['key']}: routes.mcp is {route!r}. The agent plane is not "
            "being served; D326's two-stage convergence means the FIRST deploy publishes "
            "'unavailable' -- deploy twice before running this gate"
        )
    return str(route["url"])


def plane_report(
    document: dict[str, Any], sh_status: Callable[..., tuple[int, str, str]]
) -> agent_plane.Report:
    """What the RUNNING agent plane says about itself, through the product's own
    probe.

    `agent_plane.PROBE` and not a probe written here: three of the four defects
    Session 20's trip found were found by making a proof call the product's own
    command instead of hand-rolling the request that command makes (D1114,
    D1117), and a second copy of this question is a second thing to keep in step
    (D486).
    """
    key = document["project"]["key"]
    code, out, err = sh_status(
        "docker",
        "ps",
        *agent_plane.container_filters(key, runtime_override.MCP_SERVICE),
    )
    assert code == 0, f"{key}: docker ps exited {code}: {err.strip()[:300]}"
    container = agent_plane.sole_container(out)
    assert container, (
        f"{key}: {out.strip()!r} is not one agent-plane container, so the probe cannot be "
        "asked and the document's tool_count is unconfirmable"
    )

    code, out, err = sh_status("docker", "exec", "-i", container, "python", "-c", agent_plane.PROBE)
    assert code == 0, f"{key}: the plane did not answer the probe: {err.strip()[:300]}"
    report = agent_plane.parse_report(out)
    assert report is not None, f"{key}: the plane's report is unreadable: {out.strip()[:200]!r}"
    return report


@pytest.fixture(scope="module")
def mcp_rpc(api_call: Callable[..., Any]) -> Callable[..., Any]:
    def call(
        url: str, *, token: str | None, method: str, params: dict[str, Any] | None = None
    ) -> Any:
        return api_call(
            url,
            method="POST",
            token=token,
            body={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            headers={"Accept": MCP_ACCEPT},
        )

    return call


@pytest.fixture(scope="module")
def beta_owner(project_b: dict[str, Any], psql: Callable[..., tuple[int, str, str]]) -> Any:
    """A registered subject on BETA, the owner of the agent and the row here.

    Session 21's fixture, with this module's own names so the two can run in one
    sweep without either sweeping the other's rows. Deleted first for the reason
    the suite's own subject fixture gives (a run that died mid-way leaves a
    row), and the tenant table's rows go before the notes they reference.
    """
    from agentic_postgres import service_source

    hashing = service_source.load("hashing")
    role_name = project_b["database"]["roles"]["authenticated"]
    stored = hashing.Hasher().hash(OWNER_PASSWORD)

    def sweep(user_id: str | None) -> None:
        psql(project_b, f"DELETE FROM app_private.agents WHERE name = '{READER_NAME}';")
        if user_id:
            psql(
                project_b,
                f"DELETE FROM app.{TENANT_RELATION} WHERE owner_id = '{user_id}'; "
                f"DELETE FROM app.notes WHERE owner_id = '{user_id}';",
            )
        psql(project_b, f"DELETE FROM app_private.users WHERE username = '{OWNER_USERNAME}';")

    _, existing, _ = psql(
        project_b, f"SELECT id FROM app_private.users WHERE username = '{OWNER_USERNAME}';"
    )
    sweep(existing.strip() or None)

    code, user_id, error = psql(
        project_b,
        "SELECT app_private.auth_create_user("
        f"'{OWNER_USERNAME}', 'Session 22 tenant owner', '{role_name}', "
        "ARRAY['note_embeddings:read', 'note_embeddings:write', 'notes:read', 'notes:write']"
        f"::text[], '{stored}');",
    )
    assert code == 0 and user_id.strip(), f"could not create the tenant owner on beta: {error}"
    owner = user_id.strip()
    try:
        yield owner
    finally:
        sweep(owner)


def create_reader(
    psql: Callable[..., tuple[int, str, str]], document: dict[str, Any], owner_id: str
) -> str:
    """Through the product's own function, the way every agent probe is made."""
    from agentic_postgres import service_source

    hashing = service_source.load("hashing")
    role_name = document["database"]["roles"]["agent_reader"]
    array = ", ".join(f"'{scope}'" for scope in sorted(READER_SCOPES))
    psql(document, f"DELETE FROM app_private.agents WHERE name = '{READER_NAME}';")
    code, agent_id, error = psql(
        document,
        "SELECT app_private.auth_create_agent("
        f"'{READER_NAME}', 'Session 22 tenant read probe', '{role_name}', "
        f"ARRAY[{array}]::text[], '{owner_id}', "
        f"'{hashing.Hasher().hash(AGENT_SECRET)}', NULL);",
    )
    assert code == 0 and agent_id.strip(), (
        f"could not create {READER_NAME!r} on {document['project']['key']}: {error}"
    )
    return agent_id.strip()


# ---------------------------------------------------------------------------
# OPS-PLANE-001 -- the document publishes what the plane confirmed
# ---------------------------------------------------------------------------


def test_the_documents_tool_count_is_the_one_the_plane_serves_on_both_projects(
    project_a: dict[str, Any],
    project_b: dict[str, Any],
    sh_status: Callable[..., tuple[int, str, str]],
) -> None:
    """The document publishes a count only when the plane confirmed the lock,
    and on a converged deployment it publishes one.

    Two readings per project, and the second is the repair: the `mcp.tool_count`
    the document published, and the count the RUNNING process reports for the
    lock it loaded. Before D1153 the document's count came from the file and the
    process was never asked -- so this test would have passed through D1152's
    eight minutes, and the assertion that catches that is the equality below.

    Goes red if: the deploy publishes a count it did not confirm; a plane serves
    a lock the deploy did not mount; or the probe stops reporting which lock it
    loaded, in which case the count is withheld and this says so rather than
    accepting the silence.
    """
    for document in (project_a, project_b):
        key = document["project"]["key"]
        block = document.get("mcp") or {}
        assert block.get("status") == "ready", (
            f"{key}: the agent plane is not ready ({block.get('status')!r}); deploy twice, "
            "D326's two-stage convergence"
        )

        report = plane_report(document, sh_status)
        assert report.tools_sha256, (
            f"{key}: the running plane does not say which lock it loaded. Either the "
            "deployed release predates D1153, or its lock carries no compiler signature "
            "-- and the document's tool_count is then unconfirmable by construction"
        )

        published = block.get("tool_count")
        assert published is not None, (
            f"{key}: the document withheld mcp.tool_count while the plane is answering. "
            "The deploy could not confirm the lock; its own line names both digests"
        )
        assert published == report.tool_count, (
            f"{key}: the document publishes {published} tools and the plane serves "
            f"{report.tool_count}. That is D1152 exactly, and the document is the half "
            "that is wrong"
        )

    # The control, in the same test: the two projects still differ, which is
    # what says these numbers are read per deployment rather than being one
    # constant this release carries.
    assert project_a["mcp"]["tool_count"] != project_b["mcp"]["tool_count"], (
        "both projects serve the same number of tools, so a document that published one "
        "constant for every deployment would satisfy every assertion above"
    )


def test_the_plane_serves_the_lock_the_deploy_mounted(
    project_b: dict[str, Any],
    sh_status: Callable[..., tuple[int, str, str]],
    as_root: None,
) -> None:
    """The doctor's tenth check, read against the same deployment it reads.

    The check was `ok` through D1152's eight minutes because it compared the
    file against the document and never asked the process. This reads the file's
    signature and the plane's and asserts they are one -- the same comparison
    the doctor now makes, so a doctor that stopped asking would be green here
    and this would be red.
    """
    key = project_b["project"]["key"]
    recorded = (project_b.get("mcp") or {}).get("capability_lock_sha256")
    assert recorded, f"{key}: the document records no capability lock digest"

    path = deployed_output.rendered_path(key) / runtime_override.MCP_LOCK_FILENAME
    on_disk = json.loads(path.read_text(encoding="utf-8"))

    report = plane_report(project_b, sh_status)
    assert report.tools_sha256 == on_disk.get("tools_sha256"), (
        f"{key}: the running plane serves a lock that is not the one on disk. A restart "
        "would change what this deployment answers, and the deployed document describes "
        "the file rather than the process (D1152)"
    )
    assert report.tool_count == on_disk.get("tool_count"), (
        f"{key}: the plane and the file agree on the signature and not on the count, "
        "which the loader should have refused at start"
    )


# ---------------------------------------------------------------------------
# AGT-TENANT-002 -- the door, proved by a read
# ---------------------------------------------------------------------------


def test_an_agent_reads_rows_through_a_tenant_tool_on_beta(
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
    mcp_rpc: Callable[..., Any],
    beta_owner: str,
) -> None:
    """`AGT-TENANT-002`. The grant migration arrived, and the tool answers.

    Session 21 proved the tenant surface by discovery and by a refusal. Neither
    could see a `GRANT`: an agent holding `note_embeddings:read` was served the
    tool and refused upstream, because the release's own grants reach
    `api.notes` and `api.tasks` and a project's objects are the project's to
    grant (D1156). Migration 20260914120002 is the tenant's half.

    Goes red if: the second migration is not applied on this deployment; the
    grant names the wrong role; or the tool is served and the database still
    refuses -- which is the exact state D1156 recorded, and the message says so.
    """
    key = project_b["project"]["key"]

    # BOTH tables, since ADR 0206 gave a project set its own (D1288's repair).
    # This version belongs to the example project's set, so on a cluster the
    # deploy has moved it is in `project_schema_migrations`; on one that predates
    # the move it is still in `schema_migrations`. The question here is "did this
    # migration run", which neither table alone can answer any more.
    code, out, error = psql(
        project_b,
        "SELECT (count(*) FILTER (WHERE source = 'release') "
        "     + count(*) FILTER (WHERE source = 'project'))::text FROM ("
        "  SELECT 'release' AS source, version FROM app_private.schema_migrations"
        "  UNION ALL"
        "  SELECT 'project' AS source, version FROM app_private.project_schema_migrations"
        f") AS every_set WHERE version = '{GRANT_VERSION}';",
    )
    assert code == 0, f"{key}: {error.strip()[:300]}"
    assert out.strip() == "1", (
        f"{key}: migration {GRANT_VERSION} is not applied here. Deploy "
        "--through-session >= 22 first: the example set's second migration is what "
        "grants this project's view to the agent roles"
    )

    # One row, owned by the subject the agent acts for. Planted through the
    # product's own write path so the row is what a caller's write produces.
    code, note_id, error = psql(
        project_b,
        f"SELECT set_config('app.user_id', '{beta_owner}', true); "
        f'SET LOCAL ROLE "{project_b["database"]["roles"]["object_owner"]}"; '
        "SELECT (api.create_note('apg-s22-grant-canary', 'body')).id;",
    )
    assert code == 0, f"{key}: the canary note could not be written: {error.strip()[:300]}"
    planted = note_id.strip().splitlines()[-1]
    code, _, error = psql(
        project_b,
        f"SELECT set_config('app.user_id', '{beta_owner}', true); "
        f'SET LOCAL ROLE "{project_b["database"]["roles"]["object_owner"]}"; '
        f"SELECT api.set_note_embedding('{planted}'::uuid, "
        f"'{EMBEDDING}'::extensions.vector);",
    )
    assert code == 0, f"{key}: the canary embedding could not be written: {error.strip()[:300]}"

    reader = create_reader(psql, project_b, beta_owner)
    issued = api_call(
        f"{app_base(project_b)}/auth/agent-token",
        method="POST",
        body={"agent_id": reader, "secret": AGENT_SECRET},
    )
    assert issued.status == 200, issued.body[:300]
    token = json.loads(issued.body)["access_token"]
    route = mcp_route_of(project_b)

    # The relation read is registered into the GROUPED read (ADR 0200): the
    # tenant's relation is a `resource` of `query_resource`, not a tool of its
    # own. A call naming a tool that does not exist would be refused for a
    # reason that has nothing to do with the grant.
    listing = mcp_rpc(route, token=token, method="tools/list")
    assert listing.status == 200, listing.body[:300]
    names = sorted(tool["name"] for tool in sse_result(listing.body)["result"]["tools"])
    assert "query_resource" in names, names

    call = mcp_rpc(
        route,
        token=token,
        method="tools/call",
        params={"name": "query_resource", "arguments": {"resource": TENANT_RELATION, "limit": 5}},
    )
    assert call.status == 200, call.body[:300]
    result = sse_result(call.body)
    assert result is not None, call.body[:300]
    assert not refused(result), (
        f"{key}: the tenant read was refused: {tool_text(result)[:400]}. If the message "
        f"names a privilege on api.{TENANT_RELATION}, the grant migration did not reach "
        "this deployment -- which is D1156, and the tool being served is not the question"
    )
    assert planted in tool_text(result), (
        f"{key}: the tool answered without the row this test planted. The grant lets the "
        "agent ASK; the policy decides whose rows come back, and the agent acts for the "
        f"subject that owns this one.\n{tool_text(result)[:400]}"
    )
