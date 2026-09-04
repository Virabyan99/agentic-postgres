"""Session 16's live halves: capability governance against the deployment.

**Seven claims, seven live halves, all written in Run 9 and none executed
before Run 10's trip** (D938). Runs 2-8 built the planes and proved them in a
checkout -- against a fixture cluster that applied every migration through the
product's own render path -- and wrote no proof that reaches the deployment an
operator is running. `claim_mode` refuses a claim whose every proof is offline,
so these exist; D211-D214 say what a proof that has never executed is worth, so
the docstrings say what each one asserts and the trip is what finds out.

**What is here can only be proved on a deployment.** The lock the plane obeys
is the one mounted into its container, compiled by the deploy from the
installed manifest; the audit rows are written by the deployed cluster's own
functions; the contract digest the deployed document publishes is read off a
running container. ADR 0065/0066: a proof that reaches the right end state by a
route the product does not take proves the end state is reachable, not that the
product reaches it.

**Everything here uses the deployment suite's own fixtures**, and the agent is
created the way Session 9's writer is: through `app_private.auth_create_agent`,
owned by the ordinary probe subject, torn down after (D392).

**These require migrations 0027-0030.** Released, and until the trip applied on
no cluster: the taxonomy column, the quota table, the idempotency table and the
dry-run all arrive with them, and every proof here fails without them --
correctly and loudly.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from hashlib import sha256
from typing import Any

import pytest
import yaml

from agentic_postgres import (
    REPO_ROOT,
    capability_compiler,
    config,
    deployed_output,
    runtime_override,
)
from agentic_postgres import evaluation_harness as harness
from agentic_postgres.capability_compiler import RISK_ORDER

# ruff: noqa: S608 -- every literal here is this module's own constant, run by an
# operator's psql against a probe project. The same waiver every deployment
# module carries, for the same reason.

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]

MCP_ACCEPT = "application/json, text/event-stream"

#: A WRITE agent that can also read and discover, so one agent proves every
#: plane: the quota counts reads, the taxonomy records a read's denial, the
#: idempotency key and the dry run are a write's.
AGENT_SCOPES = ("meta:read", "notes:read", "notes:write", "tasks:read", "tasks:write")
AGENT_NAME = "apg-acceptance-mcp-governance"
AGENT_SECRET = "mcp-governance-secret-2c7e41a9d0b5"  # noqa: S105 -- a probe credential

#: Titles this module creates and nothing else does, so a row carrying one is
#: this module's rather than a coincidence.
IDEM_TITLE = "apg-run9-idempotency-canary-71c0"
IDEM_TITLE_OTHER_KEY = "apg-run9-idempotency-other-key-71c1"
DRY_RUN_TITLE = "apg-run9-dry-run-canary-71c2"
TITLES = (IDEM_TITLE, IDEM_TITLE_OTHER_KEY, DRY_RUN_TITLE)

CONTRACT = REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
REPORT = REPO_ROOT / "docs" / "evaluation-report.md"


def sse_result(body: str) -> dict[str, Any] | None:
    """The JSON-RPC message out of an SSE response (D458)."""
    payload = None
    for line in body.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
    return payload


def tool_text(result: dict[str, Any]) -> str:
    """The text a tool answered with, whether it served or refused.

    A served tool returns its JSON in `result.content[0].text`; a refused one
    returns the framework's error either as a JSON-RPC `error` or as
    `result.isError` with the message in the same content slot.
    """
    if "error" in result:
        return str(result["error"].get("message", result["error"]))
    content = result["result"]["content"]
    return str(content[0].get("text", "")) if content else ""


def refused(result: dict[str, Any]) -> bool:
    return "error" in result or bool(result.get("result", {}).get("isError"))


@pytest.fixture(scope="module")
def mcp_route(project_a: dict[str, Any]) -> str:
    route = (project_a.get("routes") or {}).get("mcp")
    if not isinstance(route, dict) or route.get("status") != "ready" or not route.get("url"):
        pytest.fail(
            f"routes.mcp is {route!r}. The agent plane is not being served, so every proof "
            "below would measure a closed port. D326's two-stage convergence means the "
            "FIRST deploy publishes 'unavailable' -- deploy twice before running this gate"
        )
    return route["url"]


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
def governance_agent(
    project_a: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
    app_probe_subject: Any,
) -> Any:
    """An `agent_writer` agent owned by the probe subject, and a token.

    Session 9's writer fixture, with this module's name and scopes. The quota
    it is later given is CLEARED in teardown before the agent is deleted, and
    every row this module writes is removed by title.
    """
    from agentic_postgres import service_source

    hashing = service_source.load("hashing")
    role_name = project_a["database"]["roles"]["agent_writer"]
    scopes = ", ".join(f"'{scope}'" for scope in sorted(AGENT_SCOPES))

    psql(project_a, f"DELETE FROM app_private.agents WHERE name = '{AGENT_NAME}';")
    code, agent_id, error = psql(
        project_a,
        "SELECT app_private.auth_create_agent("
        f"'{AGENT_NAME}', 'MCP governance acceptance probe', '{role_name}', "
        f"ARRAY[{scopes}]::text[], '{app_probe_subject.user_id}', "
        f"'{hashing.Hasher().hash(AGENT_SECRET)}', NULL);",
    )
    assert code == 0 and agent_id, f"could not create the governance probe agent: {error}"

    try:
        answer = api_call(
            f"{app_base(project_a)}/auth/agent-token",
            method="POST",
            body={"agent_id": agent_id, "secret": AGENT_SECRET},
        )
        assert answer.status == 200, (
            f"the probe agent could not obtain a token ({answer.status}: {answer.body[:200]})"
        )
        yield {
            "agent_id": agent_id,
            "owner_id": app_probe_subject.user_id,
            "token": json.loads(answer.body)["access_token"],
        }
    finally:
        for title in TITLES:
            psql(project_a, f"DELETE FROM app.notes WHERE title = '{title}';")
        psql(project_a, f"DELETE FROM app_private.agent_quota WHERE agent_id = '{agent_id}';")
        psql(project_a, f"DELETE FROM app_private.agents WHERE name = '{AGENT_NAME}';")


def _audit_rows(
    psql: Callable[..., tuple[int, str, str]], project_a: dict[str, Any], agent_id: str
) -> list[dict[str, Any]]:
    """Every audit row this agent produced, oldest first, with Session 16's
    three columns beside Session 9's."""
    code, out, error = psql(
        project_a,
        "SELECT coalesce(json_agg(row_to_json(r) ORDER BY r.started_at), '[]'::json) FROM ("
        "SELECT source::text, tool, outcome::text, denial_reason::text, capability_version, "
        "contract_hash, row_count, started_at "
        "FROM app_private.agent_audit "
        f"WHERE agent_id = '{agent_id}' ORDER BY started_at) r;",
    )
    assert code == 0, f"could not read the audit record: {error}"
    return json.loads(out)


@pytest.fixture(scope="module")
def deployed_lock(project_a: dict[str, Any], as_root: None) -> dict[str, Any]:
    """The lock the deploy compiled and mounted into the container (ADR 0126).

    Read from the installed rendered directory, which is root-only -- host mode
    runs as root -- rather than from a checkout: a checkout's lock is the one
    somebody could have typed, and this is the one the plane reads.
    """
    path = (
        deployed_output.rendered_path(project_a["project"]["key"])
        / runtime_override.MCP_LOCK_FILENAME
    )
    assert path.is_file(), f"no capability lock at {path}; the deploy did not compile one"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def installed_manifest(project_a: dict[str, Any], as_root: None) -> tuple[dict[str, Any], bytes]:
    """The project manifest the deploy installed -- the one it hands to the
    bootstrap, the migrator and, since ADR 0183, the lock compiler."""
    path = deployed_output.PROJECT_STATE_ROOT / project_a["project"]["key"] / "manifest.yaml"
    assert path.is_file(), f"no installed manifest at {path}"
    raw = path.read_bytes()
    return yaml.safe_load(raw.decode("utf-8")), raw


# ---------------------------------------------------------------------------
# AGT-CAPVER-001 and AGT-RISK-001 -- the classification reaches the deployment
# ---------------------------------------------------------------------------


def test_the_deployed_lock_classifies_every_capability_and_the_write_records_its_version(
    deployed_lock: dict[str, Any],
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    governance_agent: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    project_a: dict[str, Any],
) -> None:
    """**AGT-CAPVER-001's live half.** The lock the plane obeys is at a version
    that declares a semver and a lifecycle for every capability, none is
    retired, and a write's audit row on the deployment carries that version and
    the lock's own contract hash -- the version reaches the record, on the
    deployment, through the product's own functions."""
    assert deployed_lock["schema_version"] >= 2, (
        f"the deployed lock is schema version {deployed_lock['schema_version']}: the "
        "deployment predates ADR 0177 and declares no version for anything"
    )
    for tool in deployed_lock["tools"]:
        backing = tool["capabilities"]
        assert backing, tool["name"]
        for entry in backing:
            assert re.fullmatch(r"\d+\.\d+\.\d+", entry["version"]), entry
            assert entry["lifecycle"] in ("active", "deprecated"), entry
            assert entry["lifecycle"] != "retired"

    create = next(t for t in deployed_lock["tools"] if t["name"] == "create_note")
    declared_version = create["capabilities"][0]["version"]
    answer = mcp_rpc(
        mcp_route,
        token=governance_agent["token"],
        method="tools/call",
        params={
            "name": "create_note",
            "arguments": {
                "p_title": IDEM_TITLE,
                "p_content": "governance canary body",
                "idempotency_key": "run9-capver-0000000001",
                "dry_run": False,
            },
        },
    )
    assert answer.status == 200, answer.body[:300]
    result = sse_result(answer.body)
    assert result is not None and not refused(result), tool_text(result)

    rows = [
        r
        for r in _audit_rows(psql, project_a, governance_agent["agent_id"])
        if r["tool"] == "create_note"
    ]
    assert rows, "the write left no audit row"
    plane = [r for r in rows if r["source"] == "agent_plane"]
    assert plane, rows
    assert plane[-1]["capability_version"] == declared_version, plane[-1]
    assert plane[-1]["contract_hash"] == deployed_lock["canonical_sha256"], plane[-1]


def test_the_deployed_locks_risk_is_the_worst_of_what_backs_each_tool(
    deployed_lock: dict[str, Any],
) -> None:
    """**AGT-RISK-001's live half**, and it claims exactly what the tree does
    (D934): the classification is carried, ordered, aggregated worst-case, and
    the lock the deployment serves is refused at start without it. It selects
    no runtime behaviour, and this proof does not pretend otherwise."""
    for tool in deployed_lock["tools"]:
        assert tool["risk"] in RISK_ORDER, tool
        worst = max((c["risk"] for c in tool["capabilities"]), key=RISK_ORDER.index)
        assert tool["risk"] == worst, (tool["name"], tool["risk"], worst)
        if tool["kind"] == "metadata":
            assert tool["risk"] == "low", tool["name"]
        if tool["kind"] == "write":
            assert tool["risk"] != "low", tool["name"]


# ---------------------------------------------------------------------------
# AGT-DENIAL-001 -- a denial on the deployment carries its reason
# ---------------------------------------------------------------------------


def test_a_denied_read_on_the_deployment_records_a_taxonomy_reason(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    governance_agent: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    project_a: dict[str, Any],
    deployed_lock: dict[str, Any],
) -> None:
    """A filter on a column the lock lets the caller READ and not FILTER on is
    refused, and the deployed cluster records which boundary refused. The
    reason is a member of the cluster's own enum, never free text, and every
    non-refused row carries none."""
    notes = next(
        r
        for t in deployed_lock["tools"]
        if t["name"] == "query_resource"
        for r in t["resources"]
        if r["name"] == "notes"
    )
    filterable = {f["column"] for f in notes["filters"]}
    unfilterable = [c for c in notes["columns"] if c not in filterable]
    assert unfilterable, "every readable column is filterable; the case cannot be built"

    answer = mcp_rpc(
        mcp_route,
        token=governance_agent["token"],
        method="tools/call",
        params={
            "name": "query_resource",
            "arguments": {
                "resource": "notes",
                "filters": [{"column": unfilterable[0], "operator": "eq", "value": "x"}],
            },
        },
    )
    assert answer.status == 200, answer.body[:300]
    result = sse_result(answer.body)
    assert result is not None and refused(result), "the deployment served a filter the lock forbids"

    code, members, _ = psql(
        project_a, "SELECT array_to_json(enum_range(NULL::app_private.agent_denial_reason));"
    )
    assert code == 0
    taxonomy = set(json.loads(members))

    rows = _audit_rows(psql, project_a, governance_agent["agent_id"])
    denied = [r for r in rows if r["tool"] == "query_resource" and r["outcome"] == "refused"]
    assert denied, rows
    assert denied[-1]["denial_reason"] in taxonomy, denied[-1]
    for row in rows:
        assert (row["outcome"] == "refused") == (row["denial_reason"] is not None), row


# ---------------------------------------------------------------------------
# AGT-QUOTA-001 -- the fifth budget, on the deployment
# ---------------------------------------------------------------------------


def test_a_quota_bounds_the_agent_across_requests_and_its_refusal_is_audited(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    governance_agent: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    project_a: dict[str, Any],
) -> None:
    """Two calls in the window are served, the third is refused, the refusal is
    a `refused` row the database wrote for itself with `budget_exceeded`, and
    the counter lives in `agent_quota` -- durable state outside the process,
    which is what makes the bound survive a restart (ADR 0180)."""
    agent_id = governance_agent["agent_id"]
    before = len(_audit_rows(psql, project_a, agent_id))
    code, _, error = psql(
        project_a,
        f"UPDATE app_private.agents SET quota_calls = 2, quota_window_seconds = 3600 "
        f"WHERE id = '{agent_id}';",
    )
    assert code == 0, error
    psql(project_a, f"DELETE FROM app_private.agent_quota WHERE agent_id = '{agent_id}';")

    outcomes = []
    for _ in range(3):
        answer = mcp_rpc(
            mcp_route,
            token=governance_agent["token"],
            method="tools/call",
            params={"name": "query_resource", "arguments": {"resource": "notes", "limit": 1}},
        )
        assert answer.status == 200, answer.body[:300]
        result = sse_result(answer.body)
        assert result is not None
        outcomes.append("refused" if refused(result) else "served")
    try:
        assert outcomes == ["served", "served", "refused"], outcomes

        code, spent, _ = psql(
            project_a,
            f"SELECT calls FROM app_private.agent_quota WHERE agent_id = '{agent_id}';",
        )
        assert code == 0 and spent.strip(), "no quota row: the counter is not durable"

        rows = _audit_rows(psql, project_a, agent_id)[before:]
        quota_rows = [
            r for r in rows if r["outcome"] == "refused" and r["denial_reason"] == "budget_exceeded"
        ]
        assert len(quota_rows) == 1, rows
    finally:
        psql(
            project_a,
            f"UPDATE app_private.agents SET quota_calls = NULL, quota_window_seconds = NULL "
            f"WHERE id = '{agent_id}';",
        )
        psql(project_a, f"DELETE FROM app_private.agent_quota WHERE agent_id = '{agent_id}';")


# ---------------------------------------------------------------------------
# AGT-IDEM-001 -- a replay performs the work once
# ---------------------------------------------------------------------------


def test_a_replayed_write_on_the_deployment_performs_the_work_once(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    governance_agent: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    project_a: dict[str, Any],
) -> None:
    """The same key twice: one row, the second answer the same row, the second
    audit outcome `replayed`. A different key with the same body: a second row."""

    def create(title: str, key: str) -> dict[str, Any]:
        answer = mcp_rpc(
            mcp_route,
            token=governance_agent["token"],
            method="tools/call",
            params={
                "name": "create_note",
                "arguments": {
                    "p_title": title,
                    "p_content": "idempotency canary body",
                    "idempotency_key": key,
                    "dry_run": False,
                },
            },
        )
        assert answer.status == 200, answer.body[:300]
        result = sse_result(answer.body)
        assert result is not None and not refused(result), tool_text(result)
        return json.loads(tool_text(result))

    psql(
        project_a,
        f"DELETE FROM app.notes WHERE title IN ('{IDEM_TITLE}', '{IDEM_TITLE_OTHER_KEY}');",
    )
    first = create(IDEM_TITLE, "run9-idempotency-0000000001")
    second = create(IDEM_TITLE, "run9-idempotency-0000000001")
    assert first["row"]["id"] == second["row"]["id"], (first, second)

    code, count, _ = psql(
        project_a, f"SELECT count(*) FROM app.notes WHERE title = '{IDEM_TITLE}';"
    )
    assert code == 0 and count.strip() == "1", f"a replay wrote a second row: {count}"

    rows = [
        r
        for r in _audit_rows(psql, project_a, governance_agent["agent_id"])
        if r["tool"] == "create_note" and r["source"] == "database"
    ]
    assert rows[-1]["outcome"] == "replayed", rows[-2:]
    assert rows[-2]["outcome"] == "committed", rows[-2:]

    create(IDEM_TITLE_OTHER_KEY, "run9-idempotency-0000000002")
    code, count, _ = psql(
        project_a, "SELECT count(*) FROM app.notes WHERE title LIKE 'apg-run9-idempotency-%';"
    )
    assert code == 0 and count.strip() == "2", count


# ---------------------------------------------------------------------------
# AGT-DRYRUN-001 -- a rehearsal on the deployment changes nothing
# ---------------------------------------------------------------------------


def test_a_dry_run_on_the_deployment_writes_nothing_and_is_audited_as_a_rehearsal(
    mcp_route: str,
    mcp_rpc: Callable[..., Any],
    governance_agent: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    project_a: dict[str, Any],
    deployed_lock: dict[str, Any],
) -> None:
    """`dry_run: true` returns the row it would have written with `row_count`
    0 and `dry_run` true, leaves no row, is audited as `dry_run` and not as a
    write, and spends no key: the same key then performs the real write."""
    create = next(t for t in deployed_lock["tools"] if t["name"] == "create_note")
    assert create.get("supports_dry_run") is True, (
        "the deployed lock does not support a dry run on create_note; the manifest this "
        "deployment was rendered from predates Run 7's declaration"
    )
    psql(project_a, f"DELETE FROM app.notes WHERE title = '{DRY_RUN_TITLE}';")

    def call(dry_run: bool) -> dict[str, Any]:
        answer = mcp_rpc(
            mcp_route,
            token=governance_agent["token"],
            method="tools/call",
            params={
                "name": "create_note",
                "arguments": {
                    "p_title": DRY_RUN_TITLE,
                    "p_content": "dry-run canary body",
                    "idempotency_key": "run9-dry-run-00000000001",
                    "dry_run": dry_run,
                },
            },
        )
        assert answer.status == 200, answer.body[:300]
        result = sse_result(answer.body)
        assert result is not None and not refused(result), tool_text(result)
        return json.loads(tool_text(result))

    rehearsal = call(True)
    assert rehearsal["dry_run"] is True and rehearsal["row_count"] == 0, rehearsal
    assert rehearsal["row"]["id"] is None, (
        "a rehearsal handed back an id for a row that will never exist (D924)"
    )
    code, count, _ = psql(
        project_a, f"SELECT count(*) FROM app.notes WHERE title = '{DRY_RUN_TITLE}';"
    )
    assert code == 0 and count.strip() == "0", "a dry run wrote a row"

    rows = [
        r
        for r in _audit_rows(psql, project_a, governance_agent["agent_id"])
        if r["tool"] == "create_note" and r["source"] == "database"
    ]
    assert rows[-1]["outcome"] == "dry_run", rows[-1]

    real = call(False)
    assert real["dry_run"] is False and real["row_count"] == 1, real
    code, count, _ = psql(
        project_a, f"SELECT count(*) FROM app.notes WHERE title = '{DRY_RUN_TITLE}';"
    )
    assert code == 0 and count.strip() == "1", "the key the rehearsal did not spend was refused"


# ---------------------------------------------------------------------------
# AGT-APPROVE-001 -- the declaration and the reason exist on the deployment
# ---------------------------------------------------------------------------


def test_the_deployment_declares_approval_on_every_write_and_names_the_refusal(
    deployed_lock: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    project_a: dict[str, Any],
    service_container: Callable[[str, str], str],
    sh: Callable[..., str],
) -> None:
    """**The refusal is the guarantee** (D870), and its behaviour is proved
    offline against a lock that declares it. What the deployment can honestly
    show is that the declaration reaches its lock on both writes, that the
    cluster's own enum carries `approval_required`, and that the runtime the
    container serves from names it as a caller-facing token -- all three read
    off the deployment, none inferred from the checkout."""
    for name in ("create_note", "update_task_status"):
        tool = next(t for t in deployed_lock["tools"] if t["name"] == name)
        assert isinstance(tool.get("requires_approval"), bool), (
            name,
            tool.get("requires_approval"),
        )

    code, members, _ = psql(
        project_a, "SELECT array_to_json(enum_range(NULL::app_private.agent_denial_reason));"
    )
    assert code == 0 and "approval_required" in json.loads(members)

    container = service_container(project_a["project"]["key"], runtime_override.MCP_SERVICE)
    reported = sh(
        "docker", "exec", container, "python", "-c",
        "import json, app.mcp_errors as m; "
        "print(json.dumps([m.APPROVAL_REQUIRED in m.CALLER_FACING_TOKENS, "
        "m.APPROVAL_REQUIRED_REASON in m.DENIAL_REASONS]))",
    )  # fmt: skip
    assert json.loads(reported) == [True, True], reported


# ---------------------------------------------------------------------------
# AGT-PROFILE-001 -- the deployed lock is the profile the manifest produced
# ---------------------------------------------------------------------------


def test_the_deployed_lock_is_the_one_the_installed_manifests_profile_produced(
    deployed_lock: dict[str, Any],
    installed_manifest: tuple[dict[str, Any], bytes],
) -> None:
    """Both branches are measurements. A version 1 manifest declares no
    profile, and the lock must then carry none and serve the approved contract's
    tools unchanged; a version 2 manifest's profile must be the lock's, applied
    by the same compiler to the same approved contract. Either way the lock
    records the digest of the manifest that produced it."""
    manifest, raw = installed_manifest
    approved = json.loads(CONTRACT.read_text("utf-8"))
    assert deployed_lock["canonical_sha256"] == harness.contract_digest(approved), (
        "the deployed lock was compiled from a contract this checkout does not hold"
    )
    assert deployed_lock["compiled_from"]["project_manifest_sha256"] == sha256(raw).hexdigest()

    if manifest["schema_version"] < config.PROJECT_PROFILE_FROM:
        assert "profile" not in deployed_lock
        assert deployed_lock["tools"] == approved["tools"]
        return

    profile = manifest["mcp"]["profile"]
    assert deployed_lock.get("profile") == profile
    narrowed = capability_compiler.apply_profile(approved, profile)
    assert deployed_lock["tools"] == narrowed["tools"]


# ---------------------------------------------------------------------------
# EVAL-HARNESS-001 -- the deployment serves the contract the harness evaluated
# ---------------------------------------------------------------------------


def test_the_deployed_contract_digest_is_the_one_the_harness_evaluated(
    project_a: dict[str, Any], deployed_lock: dict[str, Any]
) -> None:
    """One number, three places: the report the cases were derived for, the
    lock the plane obeys, and the deployed document's `mcp` block, read off
    the running container by the deploy (ADR 0184)."""
    match = re.search(r"digest `([0-9a-f]{64})`", REPORT.read_text("utf-8"))
    assert match, "the evaluation report names no contract digest"
    evaluated = match.group(1)

    published = (project_a.get("mcp") or {}).get("capability_contract_sha256")
    assert published, f"the deployed document publishes no contract digest: {project_a.get('mcp')}"
    assert published == evaluated, (
        f"the deployment serves contract {published} and the harness evaluated {evaluated}"
    )
    assert deployed_lock["canonical_sha256"] == evaluated
