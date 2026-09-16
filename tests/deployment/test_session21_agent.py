"""Session 21's live halves: the agent plane opened to a tenant's domain, on
the deployment (ADR 0200, ADR 0201).

**Five claims' live halves, written in Run 6 and executed first on Run 7's
trip** (D938 applied: every offline half was written in the run that built its
plane; these are the halves only a deployment can answer). Beta is the project
that declares a migration set AND a capability manifest of its own
(`projects/example`, both keys); alpha declares neither and is the control for
every reading here -- it serves exactly the six tools it served, its lock's
vocabulary derives no tenant relation, and the same grant that beta issues is
refused on it.

**What is here can only be proved on a deployment.** The lock the plane obeys
is the one the deploy compiled from the installed manifest and mounted into the
container; the issuer's ceiling is read from the lock the auth container
mounts; the audit rows are written by the deployed cluster's own functions; the
contract digest the deployed document publishes is read off a running
container (ADR 0065/0066).

**Everything here uses the deployment suite's own fixtures and shapes.** Agents
are created through `app_private.auth_create_agent` -- the function `POST
/admin/agents` calls -- and torn down after (D392); the one proof about the
ceiling at CREATION goes through the admin endpoint on alpha, because that is
the gate rig 21c measured. Beta's owner is a registered subject created on beta
through `auth_create_user`, the same way the suite creates alpha's.

**The tenant write is refused, on purpose, and that is the measurement.** The
example project's manifest is what the scaffold wrote (Run 5), and the scaffold
declares `requires_approval: true` at the conservative end of every bound (ADR
0201 §5); approval is a refusal (ADR 0182). So the write registered from beta's
lock is reached through the plane, refused pending approval, and AUDITED with
that reason -- which proves the tool is the lock's, the scope check runs, and
the audit order holds (ADR 0141) for a tool the runtime had never seen. A
proof that rewrote the manifest to make the write succeed would measure a
manifest the release does not ship.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import secrets
import subprocess
from collections.abc import Callable
from hashlib import sha256
from typing import Any

import pytest

from agentic_postgres import (
    REPO_ROOT,
    capability_manifest,
    deployed_output,
    dr_kit,
    output_migrations,
    runtime_override,
)
from agentic_postgres import evaluation_harness as harness

# ruff: noqa: S608 -- every literal here is this module's own constant, run by an
# operator's psql against probe projects. The same waiver every deployment
# module carries, for the same reason.
pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    # The administrator's password is not a roster variable: `admin_session`
    # skips by itself when APG_ADMIN_PASSWORD_FILE is absent, as Session 16's
    # module relies on, and the claim then reports not_run.
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"
    ),
]

MCP_ACCEPT = "application/json, text/event-stream"
SET_ROOT = "projects/example"
TENANT_RELATION = "note_embeddings"
TENANT_WRITE = "set_note_embedding"
TENANT_SCOPES = ("meta:read", "note_embeddings:read", "note_embeddings:write")
READER_SCOPES = ("meta:read", "note_embeddings:read", "notes:read")

OWNER_USERNAME = "apg-s21-tenant-owner"
OWNER_PASSWORD = "tenant-owner-probe-91c3e0a7f2b4"  # noqa: S105 -- a probe credential
WRITER_NAME = "apg-s21-tenant-writer"
READER_NAME = "apg-s21-tenant-reader"
ALPHA_NAME = "apg-s21-alpha-control"
AGENT_SECRET = "s21-tenant-secret-4d1e9b0c7a52"  # noqa: S105 -- a probe credential
NOTE_TITLE = "apg-s21-embedding-canary-3f7a"

RELEASE_CONTRACT = REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
RELEASE_REPORT = REPO_ROOT / "docs" / "evaluation-report.md"
EXAMPLE_ROOT = REPO_ROOT / SET_ROOT

#: Rig 21d's finding: PostgREST accepts a JSON STRING of 768 floats for a
#: `vector(768)` parameter (and refuses 767). A string rather than an array,
#: because that is the shape a caller has to send through the plane's
#: argument contract, which admits scalars.
EMBEDDING = "[" + ", ".join("0.001" for _ in range(768)) + "]"


def sse_result(body: str) -> dict[str, Any] | None:
    """The JSON-RPC message out of an SSE response (D458)."""
    payload = None
    for line in body.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
    return payload


def refused(result: dict[str, Any]) -> bool:
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
    return route["url"]


def deployed_lock_of(document: dict[str, Any]) -> dict[str, Any]:
    """The lock the deploy compiled and mounted into the container (ADR 0126)."""
    path = (
        deployed_output.rendered_path(document["project"]["key"])
        / runtime_override.MCP_LOCK_FILENAME
    )
    assert path.is_file(), f"no capability lock at {path}; the deploy did not compile one"
    return json.loads(path.read_text(encoding="utf-8"))


def create_agent(
    psql: Callable[..., tuple[int, str, str]],
    document: dict[str, Any],
    *,
    name: str,
    role_suffix: str,
    scopes: tuple[str, ...],
    owner_id: str,
) -> str:
    """Through the product's own function, the way every agent probe is made."""
    from agentic_postgres import service_source

    hashing = service_source.load("hashing")
    role_name = document["database"]["roles"][role_suffix]
    array = ", ".join(f"'{scope}'" for scope in sorted(scopes))
    psql(document, f"DELETE FROM app_private.agents WHERE name = '{name}';")
    code, agent_id, error = psql(
        document,
        "SELECT app_private.auth_create_agent("
        f"'{name}', 'Session 21 tenant probe', '{role_name}', "
        f"ARRAY[{array}]::text[], '{owner_id}', "
        f"'{hashing.Hasher().hash(AGENT_SECRET)}', NULL);",
    )
    assert code == 0 and agent_id, (
        f"could not create {name!r} on {document['project']['key']}: {error}"
    )
    return agent_id


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
    """A registered subject on BETA, the owner of every agent and row here.

    `auth_create_user`, the function `POST /admin/users` calls, at the
    service's own hash profile (ADR 0081); deleted first for the reason the
    suite's own subject fixture gives (a run that died mid-way leaves a row).
    The subject's rows go before it does, and the tenant table's rows before
    the notes they reference.
    """
    from agentic_postgres import service_source

    hashing = service_source.load("hashing")
    role_name = project_b["database"]["roles"]["authenticated"]
    stored = hashing.Hasher().hash(OWNER_PASSWORD)

    def sweep(user_id: str | None) -> None:
        for name in (WRITER_NAME, READER_NAME):
            psql(project_b, f"DELETE FROM app_private.agents WHERE name = '{name}';")
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
    sweep(existing or None)

    code, user_id, error = psql(
        project_b,
        "SELECT app_private.auth_create_user("
        f"'{OWNER_USERNAME}', 'Session 21 tenant owner', '{role_name}', "
        "ARRAY['note_embeddings:read', 'note_embeddings:write', 'notes:read', 'notes:write']"
        f"::text[], '{stored}');",
    )
    assert code == 0 and user_id, f"could not create the tenant owner on beta: {error}"
    try:
        yield user_id
    finally:
        sweep(user_id)
        _, remaining, _ = psql(
            project_b,
            f"SELECT count(*) FROM app_private.users WHERE username = '{OWNER_USERNAME}';",
        )
        assert remaining == "0", f"the tenant owner survived teardown ({remaining} rows)"


def issue_token(
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
    document: dict[str, Any],
    agent_id: str,
) -> Any:
    return api_call(
        f"{app_base(document)}/auth/agent-token",
        method="POST",
        body={"agent_id": agent_id, "secret": AGENT_SECRET},
    )


def audit_rows(
    psql: Callable[..., tuple[int, str, str]], document: dict[str, Any], agent_id: str
) -> list[dict[str, Any]]:
    code, out, error = psql(
        document,
        "SELECT coalesce(json_agg(row_to_json(r) ORDER BY r.started_at), '[]'::json) FROM ("
        "SELECT tool, outcome::text, denial_reason::text, contract_hash, started_at "
        "FROM app_private.agent_audit "
        f"WHERE agent_id = '{agent_id}' ORDER BY started_at) r;",
    )
    assert code == 0, f"could not read the audit record: {error}"
    return json.loads(out)


# ---------------------------------------------------------------------------
# AGT-VOCAB-001 -- the ceiling is the deployed lock's, on both projects
# ---------------------------------------------------------------------------


def test_an_agent_on_beta_is_issued_a_tenant_scope_and_the_same_grant_on_alpha_is_refused(
    project_a: dict[str, Any],
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
    admin_session: Any,
    app_probe_subject: Any,
    beta_owner: str,
) -> None:
    """Two gates, both the deployed issuer's, read from the lock each auth
    container mounts (ADR 0200, D1126). On BETA an agent holding
    `note_embeddings:write` is issued a token: the merged surface derives the
    scope. On ALPHA the same stored grant is refused at issue -- and the same
    request is refused at CREATION through `POST /admin/agents`, the gate rig
    21c measured as the only vocabulary gate on the path -- while a release
    scope is accepted there, which is the half that says the ceiling did not
    simply close.
    """
    writer = create_agent(
        psql, project_b, name=WRITER_NAME, role_suffix="agent_writer",
        scopes=TENANT_SCOPES, owner_id=beta_owner,
    )  # fmt: skip
    issued = issue_token(api_call, app_base, project_b, writer)
    assert issued.status == 200, (
        f"beta refused to issue a token for {sorted(TENANT_SCOPES)} ({issued.status}: "
        f"{issued.body[:200]}); its lock's vocabulary should derive note_embeddings"
    )
    assert "access_token" in json.loads(issued.body)

    control = create_agent(
        psql, project_a, name=ALPHA_NAME, role_suffix="agent_writer",
        scopes=TENANT_SCOPES, owner_id=app_probe_subject.user_id,
    )  # fmt: skip
    try:
        refused_issue = issue_token(api_call, app_base, project_a, control)
        assert refused_issue.status != 200, (
            "alpha ISSUED a token carrying note_embeddings:* though its surface publishes "
            "no such relation; the issuer's ceiling is not the deployed lock's"
        )
    finally:
        psql(project_a, f"DELETE FROM app_private.agents WHERE name = '{ALPHA_NAME}';")

    def create(name: str, scopes: list[str]) -> Any:
        return api_call(
            f"{app_base(project_a)}/admin/agents",
            method="POST",
            token=admin_session.token,
            body={"name": name, "description": "", "role": "agent_writer", "scopes": scopes},
        )

    try:
        borrowed = create(f"{ALPHA_NAME}-endpoint", ["meta:read", "note_embeddings:write"])
        assert borrowed.status == 422, (
            f"alpha's admin endpoint answered {borrowed.status} to a tenant scope its lock "
            f"does not derive: {borrowed.body[:200]}"
        )
        accepted = create(f"{ALPHA_NAME}-release", ["meta:read", "notes:write"])
        assert accepted.status == 201, accepted.body[:200]
    finally:
        psql(
            project_a,
            f"DELETE FROM app_private.agents WHERE name LIKE '{ALPHA_NAME}-%';",
        )


# ---------------------------------------------------------------------------
# AGT-ROSTER-001 -- six on alpha, seven on beta, and ADR 0140 re-run
# ---------------------------------------------------------------------------


def test_alpha_serves_six_beta_seven_and_a_reader_can_neither_see_nor_call_the_tenant_write(
    project_a: dict[str, Any],
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
    mcp_rpc: Callable[..., Any],
    beta_owner: str,
) -> None:
    """The document says what each deployment SERVES, read from its lock; the
    roster is no longer a written six (ADR 0200). A reader on beta holding
    `note_embeddings:read` sees the grouped read and not the tenant write, and
    calling the write by name is refused and audited -- the boundary is the
    call-time scope check, not the hidden name (ADR 0140), re-run against a
    roster that is not six."""
    assert project_a["mcp"]["tool_count"] == 6, project_a["mcp"]
    assert project_b["mcp"]["tool_count"] == 7, project_b["mcp"]
    beta_lock = deployed_lock_of(project_b)
    assert sorted(t["name"] for t in beta_lock["tools"]) == sorted(
        [*(t["name"] for t in deployed_lock_of(project_a)["tools"]), TENANT_WRITE]
    )

    reader = create_agent(
        psql, project_b, name=READER_NAME, role_suffix="agent_reader",
        scopes=READER_SCOPES, owner_id=beta_owner,
    )  # fmt: skip
    issued = issue_token(api_call, app_base, project_b, reader)
    assert issued.status == 200, issued.body[:200]
    token = json.loads(issued.body)["access_token"]
    route = mcp_route_of(project_b)

    listing = mcp_rpc(route, token=token, method="tools/list")
    assert listing.status == 200, listing.body[:200]
    names = sorted(tool["name"] for tool in sse_result(listing.body)["result"]["tools"])
    assert "query_resource" in names, names
    assert TENANT_WRITE not in names, names

    call = mcp_rpc(
        route,
        token=token,
        method="tools/call",
        params={
            "name": TENANT_WRITE,
            "arguments": {
                "p_note_id": "00000000-0000-4000-8000-000000000001",
                "p_embedding": EMBEDDING,
                "idempotency_key": f"s21-reader-{secrets.token_hex(6)}",
                "dry_run": False,
            },
        },
    )
    assert call.status == 200, call.body[:300]
    result = sse_result(call.body)
    assert result is not None and refused(result), "a reader CALLED the tenant write"

    rows = [r for r in audit_rows(psql, project_b, reader) if r["tool"] == TENANT_WRITE]
    assert rows and rows[-1]["outcome"] == "refused", rows
    assert rows[-1]["denial_reason"] is not None, rows[-1]


# ---------------------------------------------------------------------------
# AGT-TENANT-001 -- the tenant write is the lock's, reached and audited
# ---------------------------------------------------------------------------


def test_betas_lock_carries_the_tenant_write_the_plane_refuses_it_pending_approval_and_audits_it(
    project_b: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
    mcp_rpc: Callable[..., Any],
    beta_owner: str,
    as_root: None,
) -> None:
    """The lock names the write with the reviewed argument list; the holder of
    `note_embeddings:write` SEES it; the call reaches the plane over a note the
    owner holds, carrying rig 21d's 768-float string; the plane refuses it
    pending approval (the scaffold's declaration, ADR 0182) and AUDITS the
    refusal with that reason, after `begin` (ADR 0141); and the row is
    untouched. A tool the runtime had never seen, registered from the lock."""
    del as_root
    lock = deployed_lock_of(project_b)
    tool = next(t for t in lock["tools"] if t["name"] == TENANT_WRITE)
    assert tool["kind"] == "write" and tool["arguments"] == ["p_note_id", "p_embedding"]
    assert tool["requires_approval"] is True, "the shipped manifest declares approval"
    assert lock["contract_id"] == "notes-tasks-agent-v1+example-note-embeddings-agent-v1"
    assert "note_embeddings:write" in lock["vocabulary"]["data"]

    code, note_id, error = psql(
        project_b,
        f"INSERT INTO app.notes (owner_id, title, content) VALUES ('{beta_owner}', "
        f"'{NOTE_TITLE}', 'session 21 trip') RETURNING id;",
    )
    assert code == 0 and note_id, f"could not seed a note on beta: {error}"

    writer = create_agent(
        psql, project_b, name=WRITER_NAME, role_suffix="agent_writer",
        scopes=TENANT_SCOPES, owner_id=beta_owner,
    )  # fmt: skip
    token = json.loads(issue_token(api_call, app_base, project_b, writer).body)["access_token"]
    route = mcp_route_of(project_b)

    listing = mcp_rpc(route, token=token, method="tools/list")
    names = sorted(t["name"] for t in sse_result(listing.body)["result"]["tools"])
    assert TENANT_WRITE in names, names

    call = mcp_rpc(
        route,
        token=token,
        method="tools/call",
        params={
            "name": TENANT_WRITE,
            "arguments": {
                "p_note_id": note_id,
                "p_embedding": EMBEDDING,
                "idempotency_key": f"s21-writer-{secrets.token_hex(6)}",
                "dry_run": False,
            },
        },
    )
    assert call.status == 200, call.body[:300]
    result = sse_result(call.body)
    assert result is not None and refused(result), (
        "the plane SERVED a write the lock declares as requiring approval"
    )
    assert "approval" in tool_text(result).lower(), tool_text(result)

    rows = [r for r in audit_rows(psql, project_b, writer) if r["tool"] == TENANT_WRITE]
    assert rows and rows[-1]["outcome"] == "refused", rows
    assert rows[-1]["denial_reason"] is not None, rows[-1]
    assert rows[-1]["contract_hash"] == lock["canonical_sha256"], rows[-1]

    code, count, _ = psql(
        project_b, f"SELECT count(*) FROM app.{TENANT_RELATION} WHERE note_id = '{note_id}';"
    )
    assert code == 0 and count == "0", "a refused write reached the tenant table"


# ---------------------------------------------------------------------------
# AGT-INIT-001 -- the deployed lock records the scaffold's contract
# ---------------------------------------------------------------------------


def test_betas_deployed_lock_records_the_project_contract_the_scaffold_produced(
    project_a: dict[str, Any], project_b: dict[str, Any], as_root: None
) -> None:
    """Two digests of two committed files, in the lock and in the document:
    the manifest the scaffold wrote and the contract compiled from it. Alpha's
    document records the explicit null, at the same outputs version."""
    del as_root
    lock = deployed_lock_of(project_b)
    manifest = capability_manifest.project_capabilities_path(EXAMPLE_ROOT).read_bytes()
    contract = capability_manifest.project_contract_path(EXAMPLE_ROOT).read_bytes()
    assert lock["compiled_from"]["project_capabilities_sha256"] == sha256(manifest).hexdigest()
    assert lock["compiled_from"]["project_contract_sha256"] == sha256(contract).hexdigest()

    for document in (project_a, project_b):
        assert document["schema_version"] == output_migrations.CURRENT_VERSION, document[
            "schema_version"
        ]
    block = project_b["mcp"]["project_capabilities"]
    assert block is not None, "beta's document records no project capabilities"
    assert block["root"] == SET_ROOT
    assert block["contract_sha256"] == sha256(contract).hexdigest()
    assert block["tool_count"] == json.loads(contract)["tool_count"]
    assert project_a["mcp"]["project_capabilities"] is None, project_a["mcp"]
    assert "project_capabilities" in project_a["mcp"], "the member is required at v18"


# ---------------------------------------------------------------------------
# EVAL-HARNESS-002 -- one number, three places, per project
# ---------------------------------------------------------------------------


def test_betas_deployed_contract_digest_is_the_one_its_own_report_carries(
    project_a: dict[str, Any], project_b: dict[str, Any], as_root: None
) -> None:
    """Beta's report is rendered from the JOINT contract and carries its
    digest; the deployed lock and the deployed document publish the same one.
    Alpha's is the release's, which is the control that the two reports are
    two numbers."""
    del as_root
    beta_report = capability_manifest.project_report_path(EXAMPLE_ROOT).read_text("utf-8")
    match = re.search(r"digest `([0-9a-f]{64})`", beta_report)
    assert match, "the example project's report names no contract digest"
    evaluated = match.group(1)
    assert project_b["mcp"]["capability_contract_sha256"] == evaluated
    assert deployed_lock_of(project_b)["canonical_sha256"] == evaluated

    release = re.search(r"digest `([0-9a-f]{64})`", RELEASE_REPORT.read_text("utf-8"))
    assert release and release.group(1) != evaluated
    assert project_a["mcp"]["capability_contract_sha256"] == release.group(1)
    assert release.group(1) == harness.contract_digest(
        json.loads(RELEASE_CONTRACT.read_text("utf-8"))
    )


# ---------------------------------------------------------------------------
# REC-KIT-003 -- a kit exported before this release verifies at it
# ---------------------------------------------------------------------------


@pytest.mark.requires_environment("APG_KIT_DIR")
def test_the_kit_exported_before_this_release_verifies_at_it(as_root: None) -> None:
    """The kit the operator exported from this host BEFORE the deploy through
    this session -- its deployed documents at the previous outputs version --
    verifies at this release: `dr-kit.sh verify` exits 0 and reports no
    problem, reading each stored document version-aware (D1141). This is the
    situation a kit exists for, and the one D1122 found it could not survive.
    A kit re-exported after the deploy is at the current version and proves
    nothing here, so the premise is asserted rather than assumed."""
    del as_root
    kit = pathlib.Path(os.environ["APG_KIT_DIR"])
    assert kit.is_dir(), f"APG_KIT_DIR is not a directory: {kit}"

    versions: dict[str, int] = {}
    for path in sorted((kit / "projects").glob("*/*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(document, dict) and document.get("document_kind") == "deployed":
            versions[path.parent.name] = int(document["schema_version"])
    assert versions, f"{kit} holds no deployed document under projects/"
    older = {k: v for k, v in versions.items() if v < output_migrations.CURRENT_VERSION}
    if not older:
        # **Names what it found, not only what it wanted** (D1282, D1452). The
        # ledger has called this trap *quiet* -- "aiming --kit-dir at the newest
        # kit destroys the proof without failing" -- and that is not what
        # happens: this refuses, loudly, and has since Session 21. What it did
        # not do was say WHICH kit it was given or what was in it, so an
        # operator holding three kits had to work out which one it meant. That
        # is also why the older kits are kept rather than pruned: this claim's
        # premise IS the version gap, so the deployment needs at least one kit
        # exported before the current outputs version.
        pytest.fail(
            f"every stored document in {kit} is already at outputs v"
            f"{output_migrations.CURRENT_VERSION}, so this proof would compare a kit "
            f"against its own release and pass having measured nothing.\n"
            f"  found: {versions}\n"
            f"  wanted: at least one document below v{output_migrations.CURRENT_VERSION}\n"
            "Point --kit-dir at a kit exported BEFORE the deploy through this session. "
            "That is the premise of REC-KIT-003 and the reason earlier kits are kept."
        )
    assert min(older.values()) >= dr_kit.KIT_FIRST_OUTPUTS_VERSION, older

    assert dr_kit.verify_kit(kit) == [], "the kit verifier reports problems at this release"
    result = subprocess.run(
        [str(REPO_ROOT / "bin" / "dr-kit.sh"), "verify", str(kit)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, f"dr-kit.sh verify exited {result.returncode}\n{result.stderr}"
