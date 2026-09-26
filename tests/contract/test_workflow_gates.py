"""Migration 0035: gates, compensation, the attempt history and provenance.

`WF-GATE-001`, `WF-COMP-001` and the substrate half of `WF-PROV-001`, under a
real cluster with every released migration applied as `migration_user` (D285).
The cluster fixture and the four small helpers are COPIED from
`test_workflow_substrate.py`, not imported: a module that imported another's
fixtures would fail as the other module's failure, and D386 is the reason a
reader must be able to tell whose fixture broke.

**What the rigs measured before 0035 was written** (Session 33 Run 1):

* rig 33e: `ALTER TYPE ... ADD VALUE 'compensating'` followed by a plpgsql
  definer function using it APPLIES under the pinned dbmate on 18.4, and the
  value named in a column DEFAULT in the same migration is `55P04` -- so the
  value appears only inside function bodies (ADR 0233);
* rig 33b: the plane refuses a gated write with `approval_required`, audited
  once, with the PLANE's own request id -- the id `workflow_request_approval`
  records and provenance joins on (D1696).

**The claim is global by design**, so every proof that claims begins from the
`fresh` fixture, which finishes every run another proof left open. A failure
therefore reports itself in the proof that caused it.

**Every call to a released function is ONE string literal**, because
`test_every_call_to_a_released_function_uses_a_released_arity` walks the
parentheses of the call as written (D464) and a call split across two literals
reads as the wrong arity.
"""

from __future__ import annotations

# ruff: noqa: S608
#
# Every interpolated value below is a role or database name read from a rendered
# outputs document this repository produced, or a uuid / holder this module
# generated. None of it is caller input, and a role name cannot be bound.
import json
import secrets
import subprocess
import time
import uuid
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, dev_environment, migrations

pytestmark = [
    pytest.mark.contract,
    pytest.mark.p0,
    pytest.mark.database,
    pytest.mark.security,
]

FIXTURE = REPO_ROOT / ".generated" / "fixture-alpha-dev"

#: A hash the `agent_credentials` CHECK accepts; `test_storage_plane.py:193`'s.
STORED_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$aGFzaA"

SCOPES = [
    "note_embeddings:read",
    "note_embeddings:write",
    "notes:read",
    "notes:write",
    "tasks:read",
    "tasks:write",
]


def _write_step(name: str, tool: str, capability: str, **extra: Any) -> dict[str, Any]:
    return {
        "name": name,
        "tool": tool,
        "capability": capability,
        "capability_version": "1.0.0",
        "resource": None,
        "kind": "write",
        "arguments": {"p_task_id": "{{input.task_id}}"},
        "retry": {"max": 1, "backoff_seconds": 5},
        "timeout_seconds": 30,
        **extra,
    }


def _undo(new_status: str) -> dict[str, Any]:
    """A compensation block, shaped as Run 4's compiler will emit one."""
    return {
        "kind": "write",
        "tool": "update_task_status",
        "capability": "update_task_status",
        "capability_version": "1.0.0",
        "arguments": {"p_task_id": "{{input.task_id}}", "p_new_status": new_status},
        "retry": {"max": 1, "backoff_seconds": 5},
        "timeout_seconds": 20,
    }


#: start (compensated) -> gate (approval) -> finish (compensated).
GATES = {
    "timeout_seconds": 1800,
    "steps": [
        _write_step(
            "start", "update_task_status", "update_task_status", compensation=_undo("pending")
        ),
        _write_step(
            "gate",
            "set_note_embedding",
            "set_note_embedding",
            approval={"expires_after_seconds": 900},
        ),
        _write_step(
            "finish", "update_task_status", "update_task_status", compensation=_undo("in_progress")
        ),
    ],
}

#: a, b compensated; c not; d is the one that fails.
REVERSE = {
    "timeout_seconds": 600,
    "steps": [
        _write_step("a", "update_task_status", "update_task_status", compensation=_undo("pending")),
        _write_step("b", "update_task_status", "update_task_status", compensation=_undo("pending")),
        _write_step("c", "create_note", "create_note"),
        _write_step("d", "update_task_status", "update_task_status"),
    ],
}

#: Nothing compensated anywhere.
PLAIN = {
    "timeout_seconds": 600,
    "steps": [
        _write_step("one", "create_note", "create_note"),
        _write_step("two", "create_note", "create_note"),
    ],
}

#: A wait, then a write.
WAITING = {
    "timeout_seconds": 600,
    "steps": [
        {
            "name": "pause",
            "kind": "wait",
            "seconds": 5,
            "timeout_seconds": 5,
            "retry": {"max": 0, "backoff_seconds": 1},
        },
        _write_step("after", "create_note", "create_note"),
    ],
}

#: The run input, one token so every enqueue call fits on ONE literal. It
#: carries a canary no provenance or listing read may ever return.
CANARY = "input-canary-7f3a"
INPUT = f'\'{{"task_id": "{uuid.uuid4()}", "secret": "{CANARY}"}}\'::jsonb'


def _lock() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() and not name.strip().startswith("#"):
            values[name.strip()] = value.strip()
    return values


def _docker(*args: str, stdin: str | None = None, timeout: int = 240):
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=False,
        input=stdin,
        timeout=timeout,
    )


@pytest.fixture(scope="module")
def cluster() -> Any:
    """`test_workflow_substrate.py`'s cluster, copied: the locked image, the
    product's own role statements, and the same two skips."""
    if not (FIXTURE / "outputs.json").is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    if _docker("version", "--format", "{{.Server.Version}}", timeout=30).returncode != 0:
        pytest.skip("docker is not available")

    document = json.loads((FIXTURE / "outputs.json").read_text(encoding="utf-8"))
    roles = document["database"]["roles"]
    database = document["database"]["name"]
    password = secrets.token_hex(24)
    name = f"apg-workflow-gates-{secrets.token_hex(4)}"

    started = _docker(
        "run", "-d", "--name", name,
        "-e", f"POSTGRES_PASSWORD={secrets.token_hex(24)}",
        _lock()["POSTGRES_IMAGE"],
    )  # fmt: skip
    if started.returncode != 0:
        pytest.skip(f"cannot start the locked cluster: {started.stderr.strip()[:200]}")

    try:
        rounds = 0
        for _ in range(120):
            probe = _docker("exec", name, "pg_isready", "-U", "postgres", timeout=30)
            rounds = rounds + 1 if probe.returncode == 0 else 0
            if rounds >= 2:
                break
            time.sleep(1)
        assert rounds >= 2, "the cluster never became ready"

        setup = dev_environment.role_statements(document)
        setup += dev_environment.activation_statements(document, password, password)
        setup += dev_environment.owner_grant_statements(document)
        setup += [f'CREATE DATABASE "{database}" OWNER "{roles["object_owner"]}";']
        result = _docker(
            "exec", "-i", name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1", "-U", "postgres",
            stdin="\n".join(setup),
        )  # fmt: skip
        assert result.returncode == 0, result.stderr

        result = _docker(
            "exec", "-i", name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
            "-U", "postgres", "-d", database,
            "-c", dev_environment.extensions_schema_statement(document),
        )  # fmt: skip
        assert result.returncode == 0, result.stderr

        yield {
            "name": name,
            "database": database,
            "document": document,
            "roles": roles,
            "password": password,
        }
    finally:
        _docker("rm", "-f", name, timeout=60)


def _apply_as_migration_user(cluster: dict[str, Any], body: str):
    return _docker(
        "exec", "-i", "-e", f"PGPASSWORD={cluster['password']}", cluster["name"],
        "psql", "-U", cluster["roles"]["migration_user"], "-h", "127.0.0.1",
        "-d", cluster["database"], "-qtA", "-v", "ON_ERROR_STOP=1", "-1", "-f", "-",
        stdin=body,
    )  # fmt: skip


def _superuser(cluster: dict[str, Any], sql: str):
    return _docker(
        "exec", "-i", cluster["name"], "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-d", cluster["database"], "-f", "-",
        stdin=sql,
    )  # fmt: skip


def _as_role(cluster: dict[str, Any], role: str, sql: str):
    return _superuser(cluster, f'SET ROLE "{role}";\n{sql}')


def _scalar(cluster: dict[str, Any], sql: str) -> str:
    result = _superuser(cluster, sql)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""


@pytest.fixture(scope="module")
def applied(cluster: dict[str, Any]) -> dict[str, Any]:
    """Every released migration applied as `migration_user`, 0035 included."""
    document = cluster["document"]
    applied_versions: list[str] = []
    for migration_set in migrations.sets_for(document):
        if migration_set.is_project:
            continue
        manifest = migration_set.load_manifest()
        for entry in manifest["migrations"]:
            rendered = migrations.render_migration(entry, manifest, document, migration_set.root)
            up = rendered.split("-- migrate:down")[0]
            result = _apply_as_migration_user(cluster, up)
            assert result.returncode == 0, (
                f"{entry['version']} {entry['name']} failed as migration_user: "
                f"{result.stderr.strip()[:800]}"
            )
            applied_versions.append(entry["version"])
    assert "20260917120035" in applied_versions, applied_versions[-3:]
    return {"versions": applied_versions, **cluster}


# ---------------------------------------------------------------------------
# subjects, definitions and the driving helpers
# ---------------------------------------------------------------------------


def _auth(applied: dict[str, Any]) -> str:
    return applied["roles"]["auth_service"]


@pytest.fixture(scope="module")
def people(applied: dict[str, Any]) -> dict[str, str]:
    """An owner, a second human who decides, and two agents of the owner's.

    Through the product's own `auth_create_user` / `auth_create_agent`, for the
    substrate module's reason (D313).
    """
    scopes = ", ".join(f"'{scope}'" for scope in SCOPES)
    owner = _scalar(
        applied,
        "SELECT app_private.auth_create_user('gate-owner', 'gate-owner', 'authenticated', "
        f"ARRAY[{scopes}]::text[], '{STORED_HASH}');",
    )
    approver = _scalar(
        applied,
        "SELECT app_private.auth_create_user('gate-approver', 'gate-approver', 'authenticated', "
        f"ARRAY['notes:read']::text[], '{STORED_HASH}');",
    )
    writer = applied["roles"]["agent_writer"]
    agent = _scalar(
        applied,
        f"SELECT app_private.auth_create_agent('gate-agent', '', '{writer}', ARRAY[{scopes}], '{owner}', '{STORED_HASH}', NULL);",  # noqa: E501
    )
    other = _scalar(
        applied,
        f"SELECT app_private.auth_create_agent('gate-other', '', '{writer}', ARRAY[{scopes}], '{owner}', '{STORED_HASH}', NULL);",  # noqa: E501
    )
    for body_name, body in (
        ("gates", GATES),
        ("reverse", REVERSE),
        ("plain", PLAIN),
        ("waiting", WAITING),
    ):
        required = "ARRAY['notes:write','tasks:write','note_embeddings:write']"
        installed = _superuser(
            applied,
            f"SELECT app_private.workflow_install_definition('{body_name}', 1, '{json.dumps(body)}'::jsonb, '{'a' * 64}', '{'b' * 64}', {required});",  # noqa: E501
        )
        assert installed.returncode == 0, installed.stderr
    return {"owner": owner, "approver": approver, "agent": agent, "other": other}


@pytest.fixture
def fresh(applied: dict[str, Any], people: dict[str, str]) -> dict[str, str]:
    """Every run another proof left open is finished before this one starts."""
    closed = _superuser(
        applied,
        "UPDATE app_private.workflow_run SET status = 'cancelled', finished_at = now() "
        "WHERE status::text IN ('queued', 'running', 'compensating');",
    )
    assert closed.returncode == 0, closed.stderr
    return people


def _enqueue(applied: dict[str, Any], agent: str, name: str) -> str:
    result = _as_role(
        applied,
        _auth(applied),
        f"SELECT app_private.workflow_enqueue('{agent}', '{name}', 1, {INPUT}, false);",
    )
    assert result.returncode == 0, result.stderr[:400]
    return result.stdout.strip().splitlines()[-1]


def _claim(applied: dict[str, Any], holder: str, margin: int = 60) -> dict[str, Any] | None:
    result = _as_role(
        applied,
        _auth(applied),
        "SELECT step_id || '|' || step_position || '|' || step_name || '|' || attempt "
        f"|| '|' || step::text FROM app_private.workflow_claim_step('{holder}', {margin});",
    )
    assert result.returncode == 0, result.stderr[:400]
    line = result.stdout.strip()
    if not line:
        return None
    step_id, position, name, attempt, step = line.splitlines()[-1].split("|", 4)
    return {
        "step_id": step_id,
        "position": int(position),
        "name": name,
        "attempt": int(attempt),
        "step": json.loads(step),
    }


def _finish(
    applied: dict[str, Any],
    step: str,
    holder: str,
    outcome: str,
    *,
    reason: str = "",
    request_id: str | None = None,
    result: str = "null",
):
    request = f"'{request_id}'" if request_id else "NULL"
    return _as_role(
        applied,
        _auth(applied),
        f"SELECT app_private.workflow_finish_step('{step}', '{holder}', '{outcome}', '{result}'::jsonb, '{reason}', {request});",  # noqa: E501
    )


def _finished(applied: dict[str, Any], step: str, holder: str, outcome: str, **kwargs: Any) -> str:
    done = _finish(applied, step, holder, outcome, **kwargs)
    assert done.returncode == 0, done.stderr[:400]
    return done.stdout.strip().splitlines()[-1]


def _run(applied: dict[str, Any], run: str, column: str) -> str:
    return _scalar(
        applied,
        f"SELECT coalesce({column}::text, 'NULL') FROM app_private.workflow_run WHERE id = '{run}';",  # noqa: E501
    )


def _request_approval(applied: dict[str, Any], step: str, holder: str, request_id: str) -> Any:
    return _as_role(
        applied,
        _auth(applied),
        f"SELECT app_private.workflow_request_approval('{step}', '{holder}', '{request_id}', 900);",
    )


def _decide(applied: dict[str, Any], run: str, step_name: str, user: str, decision: str):
    return _as_role(
        applied,
        _auth(applied),
        f"SELECT app_private.workflow_decide_approval('{run}', '{step_name}', '{user}', '{decision}');",  # noqa: E501
    )


def _gate_state(applied: dict[str, Any], step: str, holder: str) -> dict[str, Any]:
    result = _as_role(
        applied,
        _auth(applied),
        f"SELECT app_private.workflow_gate_state('{step}', '{holder}');",
    )
    assert result.returncode == 0, result.stderr[:400]
    return json.loads(result.stdout.strip().splitlines()[-1])


def _approval_row(applied: dict[str, Any], run: str) -> str:
    return _scalar(
        applied,
        "SELECT status::text || '|' || coalesce(decided_by::text, 'NULL') || '|' || "
        "coalesce(decided_at::text, 'NULL') || '|' || expires_at::text "
        f"FROM app_private.workflow_approval WHERE run_id = '{run}';",
    )


def _at_gate(applied: dict[str, Any], people: dict[str, str], holder: str = "H") -> dict[str, Any]:
    """A `gates` run whose first step succeeded and whose second is parked on a
    pending approval, as the loop leaves one after the plane's refusal."""
    run = _enqueue(applied, people["agent"], "gates")
    first = _claim(applied, holder)
    assert first is not None and first["name"] == "start", first
    assert (
        _finished(applied, first["step_id"], holder, "succeeded", request_id=str(uuid.uuid4()))
        == "running"
    )
    gate = _claim(applied, holder)
    assert gate is not None and gate["name"] == "gate", gate
    refused_call = str(uuid.uuid4())
    requested = _request_approval(applied, gate["step_id"], holder, refused_call)
    assert requested.returncode == 0, requested.stderr[:400]
    assert requested.stdout.strip().splitlines()[-1] == "parked"
    return {"run": run, "first": first, "gate": gate, "refused_call": refused_call}


# ---------------------------------------------------------------------------
# WF-GATE-001: the posture
# ---------------------------------------------------------------------------


NEW_FUNCTIONS = {
    "workflow_request_approval": "uuid, text, uuid, integer",
    "workflow_gate_state": "uuid, text",
    "workflow_expire_approval": "uuid, text",
    "workflow_decide_approval": "uuid, text, uuid, text",
    "workflow_pending_approvals": "integer",
    "workflow_approval_for_token": "uuid, uuid",
    "workflow_provenance": "uuid",
    "auth_count_agent_audit": "uuid, uuid, timestamptz, timestamptz",
}

REQUEST_ROLES = ("agent_writer", "agent_reader", "authenticated", "anon", "storage_service")


def test_the_two_tables_grant_nothing_to_any_role(applied: dict[str, Any]) -> None:
    """0034's posture for the two new tables (D1647): no table privilege at all.

    `anon` is the control a role that holds nothing anywhere gives; `auth_service`
    is the one that matters, because it is the role the routes run as.
    """
    offenders: list[str] = []
    for role_key in ("auth_service", *REQUEST_ROLES, "app_runtime", "project_admin"):
        role = applied["roles"][role_key]
        for table in ("workflow_approval", "workflow_attempt"):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                got = _scalar(
                    applied,
                    f"SELECT has_table_privilege('{role}', 'app_private.{table}', '{privilege}')::text;",  # noqa: E501
                )
                if got != "false":
                    offenders.append(f"{role_key} holds {privilege} on {table}")
    assert not offenders, offenders


def test_the_new_functions_are_executable_by_the_auth_service_and_nobody_else(
    applied: dict[str, Any],
) -> None:
    """Every new definer granted to the auth service, and to no request role."""
    auth = applied["roles"]["auth_service"]
    for function, signature in NEW_FUNCTIONS.items():
        granted = _scalar(
            applied,
            f"SELECT has_function_privilege('{auth}', 'app_private.{function}({signature})', 'EXECUTE')::text;",  # noqa: E501
        )
        assert granted == "true", f"auth_service cannot execute {function}: {granted!r}"
        for role_key in REQUEST_ROLES:
            role = applied["roles"][role_key]
            denied = _scalar(
                applied,
                f"SELECT has_function_privilege('{role}', 'app_private.{function}({signature})', 'EXECUTE')::text;",  # noqa: E501
            )
            assert denied == "false", f"{role_key} can execute {function}"


def test_begin_compensation_is_executable_by_nobody(applied: dict[str, Any]) -> None:
    """Granted to NOBODY, and the absence is the decision (ADR 0233).

    Called only from the definer functions of 0035, which run as its owner. A
    grant to `auth_service` would let the role the HTTP routes run as start an
    undo of an agent's work on its own say.
    """
    target = "app_private.workflow_begin_compensation(uuid, app_private.workflow_run_status)"
    for role_key in ("auth_service", *REQUEST_ROLES, "app_runtime", "project_admin"):
        role = applied["roles"][role_key]
        granted = _scalar(
            applied,
            f"SELECT has_function_privilege('{role}', '{target}', 'EXECUTE')::text;",
        )
        assert granted == "false", f"{role_key} can begin a compensation"


def test_the_replaced_substrate_functions_keep_their_signatures(applied: dict[str, Any]) -> None:
    """0034's five, replaced in place: one declaration each, same types, same grant.

    A `CREATE OR REPLACE` with a different signature would have created an
    OVERLOAD beside 0034's function rather than replacing it, and every caller
    would keep reaching the old body -- which is why the count of declarations
    is asserted, not only the text of one.
    """
    expected = {
        "workflow_claim_step": (
            "p_holder text, p_lease_margin_seconds integer",
            "TABLE(step_id uuid, run_id uuid, step_position integer, step_name text, "
            "attempt integer, agent_id uuid, dry_run boolean, step jsonb, input jsonb, "
            "prior jsonb, timeout_seconds integer, idempotency_key text)",
        ),
        "workflow_finish_step": (
            "p_step uuid, p_holder text, p_outcome app_private.workflow_step_outcome, "
            "p_result jsonb, p_reason text, p_request_id uuid",
            "text",
        ),
        "workflow_park": (
            "p_step uuid, p_holder text, p_reason text, p_resume_after timestamp with time zone, "
            "p_request_id uuid",
            "text",
        ),
        "workflow_run_status": ("p_run uuid, p_agent uuid", "jsonb"),
        "workflow_counts": ("", "jsonb"),
    }
    auth = applied["roles"]["auth_service"]
    for function, (arguments, result) in expected.items():
        read = _scalar(
            applied,
            "SELECT count(*) || '#' || string_agg(pg_get_function_identity_arguments(p.oid), '') "
            "|| '#' || string_agg(pg_get_function_result(p.oid), '') || '#' || "
            f"bool_and(has_function_privilege('{auth}', p.oid, 'EXECUTE'))::text "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            f"WHERE n.nspname = 'app_private' AND p.proname = '{function}';",
        )
        count, got_arguments, got_result, granted = read.split("#")
        assert count == "1", f"{function} has {count} declarations; the replacement overloaded it"
        assert got_arguments == arguments, f"{function}: {got_arguments}"
        assert got_result == result, f"{function}: {got_result}"
        assert granted == "true", f"{function} lost 0034's grant to auth_service"


# ---------------------------------------------------------------------------
# WF-GATE-001: requesting, reading and deciding
# ---------------------------------------------------------------------------


def test_request_approval_records_pending_and_parks_until_expiry(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    """The plane's refused call id is recorded; the expiry IS the park's time."""
    gated = _at_gate(applied, fresh)
    row = _scalar(
        applied,
        "SELECT a.status::text || '|' || a.tool || '|' || a.capability || '|' || "
        "(a.requested_request_id)::text || '|' || (a.idempotency_key = s.idempotency_key)::text "
        "|| '|' || (s.resume_after = a.expires_at)::text || '|' || s.status::text || '|' || "
        "s.reason || '|' || (s.request_id)::text || '|' || "
        "(a.expires_at - a.requested_at = interval '900 seconds')::text "
        "FROM app_private.workflow_approval a JOIN app_private.workflow_step s ON s.id = a.step_id "
        f"WHERE a.run_id = '{gated['run']}';",
    )
    assert row == (
        f"pending|set_note_embedding|set_note_embedding@1.0.0|{gated['refused_call']}|true|true"
        f"|parked|approval_required|{gated['refused_call']}|true"
    ), row

    again = _request_approval(applied, gated["gate"]["step_id"], "H", str(uuid.uuid4()))
    assert again.stdout.strip().splitlines()[-1] == "lease_lost", "a parked step was re-requested"


def test_a_step_that_declares_no_approval_cannot_open_a_gate(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    """The database refuses a gate the reviewed definition did not ask for."""
    _enqueue(applied, fresh["agent"], "plain")
    step = _claim(applied, "H")
    assert step is not None
    refused = _request_approval(applied, step["step_id"], "H", str(uuid.uuid4()))
    assert refused.returncode != 0, "a gate opened on a step with no approval declared"
    assert "declares no approval" in refused.stderr, refused.stderr[:300]


def test_an_approval_park_holds_no_lease(applied: dict[str, Any], fresh: dict[str, str]) -> None:
    """Nothing in flight while a human decides, so a restart loses nothing (D1735)."""
    gated = _at_gate(applied, fresh)
    lease = _scalar(
        applied,
        "SELECT coalesce(claimed_by, 'NULL') || '|' || coalesce(lease_until::text, 'NULL') "
        f"FROM app_private.workflow_step WHERE id = '{gated['gate']['step_id']}';",
    )
    assert lease == "NULL|NULL", lease
    assert _claim(applied, "SOMEONE-ELSE") is None, "a pending approval's step was claimable"


def test_approve_makes_the_step_claimable_at_once(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    gated = _at_gate(applied, fresh)
    decided = _decide(applied, gated["run"], "gate", fresh["approver"], "approve")
    assert decided.returncode == 0, decided.stderr[:300]
    assert decided.stdout.strip().splitlines()[-1] == "approved"

    again = _claim(applied, "H2")
    assert again is not None and again["name"] == "gate", again
    assert again["attempt"] == 2, again
    state = _gate_state(applied, again["step_id"], "H2")
    assert state["approval"]["status"] == "approved", state
    assert _approval_row(applied, gated["run"]).split("|")[1] == fresh["approver"]


def test_reject_requests_the_runs_cancel(applied: dict[str, Any], fresh: dict[str, str]) -> None:
    """A rejection is a cancel, applied by the next claim, and the undo follows."""
    gated = _at_gate(applied, fresh)
    decided = _decide(applied, gated["run"], "gate", fresh["approver"], "reject")
    assert decided.stdout.strip().splitlines()[-1] == "rejected", decided.stderr[:300]
    assert _run(applied, gated["run"], "cancel_requested_at") != "NULL"

    undo = _claim(applied, "H")
    assert undo is not None and undo["name"] == "undo-1", undo
    assert _run(applied, gated["run"], "status") == "compensating"
    assert _run(applied, gated["run"], "compensation_cause") == "cancelled"
    parked = _scalar(
        applied,
        f"SELECT status::text FROM app_private.workflow_step WHERE id = '{gated['gate']['step_id']}';",  # noqa: E501
    )
    assert parked == "parked", "the rejected step moved"


def test_the_runs_owner_cannot_decide(applied: dict[str, Any], fresh: dict[str, str]) -> None:
    """`approver_is_owner`, and nothing changes (ADR 0232)."""
    gated = _at_gate(applied, fresh)
    before = _approval_row(applied, gated["run"])
    for decision in ("approve", "reject"):
        refused = _decide(applied, gated["run"], "gate", fresh["owner"], decision)
        assert refused.returncode != 0, f"the owner's {decision} was accepted"
        assert "approver_is_owner" in refused.stderr, refused.stderr[:300]
    assert _approval_row(applied, gated["run"]) == before
    assert _run(applied, gated["run"], "cancel_requested_at") == "NULL"


def test_a_second_decision_is_refused_and_changes_nothing(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    gated = _at_gate(applied, fresh)
    assert _decide(applied, gated["run"], "gate", fresh["approver"], "approve").returncode == 0
    decided = _approval_row(applied, gated["run"])
    for decision in ("approve", "reject"):
        refused = _decide(applied, gated["run"], "gate", fresh["approver"], decision)
        assert refused.returncode != 0, f"a second {decision} was accepted"
        assert "approval_already_decided" in refused.stderr, refused.stderr[:300]
    assert _approval_row(applied, gated["run"]) == decided
    assert _run(applied, gated["run"], "cancel_requested_at") == "NULL", (
        "a refused reject still requested the cancel"
    )


def test_an_expired_approval_cannot_be_decided(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    gated = _at_gate(applied, fresh)
    _superuser(
        applied,
        "UPDATE app_private.workflow_approval SET expires_at = now() - interval '1 second' "
        f"WHERE run_id = '{gated['run']}';",
    )
    before = _approval_row(applied, gated["run"])
    refused = _decide(applied, gated["run"], "gate", fresh["approver"], "approve")
    assert refused.returncode != 0, "an expired approval was decided"
    assert "approval_expired" in refused.stderr, refused.stderr[:300]
    assert _approval_row(applied, gated["run"]) == before


def test_a_decision_on_an_unknown_step_or_run_is_the_one_refusal(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    gated = _at_gate(applied, fresh)
    for run, step in ((gated["run"], "no-such-step"), (str(uuid.uuid4()), "gate")):
        refused = _decide(applied, run, step, fresh["approver"], "approve")
        assert refused.returncode != 0
        assert "no such run" in refused.stderr, refused.stderr[:300]
    wrong = _decide(applied, gated["run"], "gate", fresh["approver"], "maybe")
    assert "AP422" in wrong.stderr, wrong.stderr[:300]


def test_the_token_lookup_answers_only_an_approved_approval_of_that_agents_running_run(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    """What the signer reads before it adds `apg_approval` (ADR 0231).

    Pending: nothing. Approved, this agent: the tool and the key. Another
    agent: nothing. The run cancelled: nothing. And -- D1745 -- an APPROVED
    approval past its decision window still answers, because the window bounds
    the human, and a retry after a conflict must be able to mint again.
    """
    gated = _at_gate(applied, fresh)
    approval = _scalar(
        applied, f"SELECT id FROM app_private.workflow_approval WHERE run_id = '{gated['run']}';"
    )

    def lookup(agent: str) -> str:
        result = _as_role(
            applied,
            _auth(applied),
            f"SELECT tool || '|' || idempotency_key FROM app_private.workflow_approval_for_token('{approval}', '{agent}');",  # noqa: E501
        )
        assert result.returncode == 0, result.stderr[:300]
        return result.stdout.strip()

    assert lookup(fresh["agent"]) == "", "a PENDING approval answered the signer"
    assert _decide(applied, gated["run"], "gate", fresh["approver"], "approve").returncode == 0
    key = _scalar(
        applied,
        f"SELECT idempotency_key FROM app_private.workflow_step WHERE id = '{gated['gate']['step_id']}';",  # noqa: E501
    )
    assert lookup(fresh["agent"]) == f"set_note_embedding|{key}"
    assert lookup(fresh["other"]) == "", "another agent's token could carry this approval"

    _superuser(
        applied,
        "UPDATE app_private.workflow_approval SET expires_at = now() - interval '1 second' "
        f"WHERE id = '{approval}';",
    )
    assert lookup(fresh["agent"]) == f"set_note_embedding|{key}", "D1745: a decided window closed"

    _superuser(
        applied,
        f"UPDATE app_private.workflow_run SET status = 'cancelled' WHERE id = '{gated['run']}';",
    )
    assert lookup(fresh["agent"]) == "", "an approval on a finished run still answered"


def test_expire_marks_only_a_pending_approval_past_its_expiry(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    gated = _at_gate(applied, fresh)
    _superuser(
        applied,
        "UPDATE app_private.workflow_approval SET expires_at = now() - interval '1 second' "
        f"WHERE run_id = '{gated['run']}'; UPDATE app_private.workflow_step SET "
        f"resume_after = now() - interval '1 second' WHERE id = '{gated['gate']['step_id']}';",
    )
    held = _claim(applied, "H")
    assert held is not None and held["name"] == "gate", held
    assert _gate_state(applied, held["step_id"], "H")["approval"]["status"] == "expired"

    expired = _as_role(
        applied,
        _auth(applied),
        f"SELECT app_private.workflow_expire_approval('{held['step_id']}', 'H');",
    )
    assert expired.stdout.strip().splitlines()[-1] == "expired", expired.stderr[:300]
    assert _approval_row(applied, gated["run"]).startswith("expired|NULL|NULL|")

    second = _at_gate(applied, fresh, holder="J")
    assert _decide(applied, second["run"], "gate", fresh["approver"], "approve").returncode == 0
    approved = _claim(applied, "J")
    assert approved is not None and approved["name"] == "gate"
    _superuser(
        applied,
        "UPDATE app_private.workflow_approval SET expires_at = now() - interval '1 second' "
        f"WHERE run_id = '{second['run']}';",
    )
    untouched = _as_role(
        applied,
        _auth(applied),
        f"SELECT app_private.workflow_expire_approval('{approved['step_id']}', 'J');",
    )
    assert untouched.stdout.strip().splitlines()[-1] == "not_expired"
    assert _approval_row(applied, second["run"]).startswith("approved|")


def test_gate_state_reports_a_served_wait(applied: dict[str, Any], fresh: dict[str, str]) -> None:
    """A wait parks ONCE; the second claim finds it served (ADR 0233)."""
    _enqueue(applied, fresh["agent"], "waiting")
    pause = _claim(applied, "H")
    assert pause is not None and pause["name"] == "pause"
    assert _gate_state(applied, pause["step_id"], "H") == {"approval": None, "waited": False}

    parked = _as_role(
        applied,
        _auth(applied),
        f"SELECT app_private.workflow_park('{pause['step_id']}', 'H', 'waiting', now() - interval '1 second', NULL);",  # noqa: E501
    )
    assert parked.stdout.strip().splitlines()[-1] == "parked", parked.stderr[:300]
    again = _claim(applied, "H")
    assert again is not None and again["name"] == "pause" and again["attempt"] == 2
    assert _gate_state(applied, again["step_id"], "H") == {"approval": None, "waited": True}

    not_held = _as_role(
        applied,
        _auth(applied),
        f"SELECT app_private.workflow_gate_state('{again['step_id']}', 'SOMEONE-ELSE');",
    )
    assert not_held.returncode != 0 and "no such step" in not_held.stderr


def test_pending_approvals_list_no_argument_value_oldest_first(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    """Who, what capability, which run, until when -- and nothing else (D1720)."""
    first = _at_gate(applied, fresh, holder="A")
    second = _at_gate(applied, fresh, holder="B")
    listed = _as_role(applied, _auth(applied), "SELECT app_private.workflow_pending_approvals(10);")
    assert listed.returncode == 0, listed.stderr[:300]
    raw = listed.stdout.strip().splitlines()[-1]
    page = json.loads(raw)
    assert [item["run_id"] for item in page] == [first["run"], second["run"]]
    assert set(page[0]) == {
        "run_id",
        "definition",
        "definition_version",
        "step",
        "position",
        "capability",
        "tool",
        "agent_id",
        "owner_id",
        "requested_at",
        "expires_at",
    }, sorted(page[0])
    assert page[0]["capability"] == "set_note_embedding@1.0.0"
    assert CANARY not in raw, "the approvals listing carried a value from the run's input"

    for bad in (0, 101):
        refused = _as_role(
            applied, _auth(applied), f"SELECT app_private.workflow_pending_approvals({bad});"
        )
        assert refused.returncode != 0 and "AP422" in refused.stderr

    counts = json.loads(
        _scalar(
            applied,
            f'SET ROLE "{_auth(applied)}"; SELECT app_private.workflow_counts();',
        )
    )
    assert counts["approvals_pending"] == 2, counts
    assert isinstance(counts["oldest_pending_approval_age_seconds"], int), counts


def test_every_finish_and_park_appends_an_attempt(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    """Every attempt is a row, with the plane's id for that attempt (ADR 0234).

    The lease-lost finish is the control: it took no effect, so it appends
    nothing -- the attempt number belongs to whoever holds the row now.
    """
    run = _enqueue(applied, fresh["agent"], "plain")
    first = _claim(applied, "H")
    assert first is not None
    parked_call, finished_call = str(uuid.uuid4()), str(uuid.uuid4())
    parked = _as_role(
        applied,
        _auth(applied),
        f"SELECT app_private.workflow_park('{first['step_id']}', 'H', 'write_conflict', now() - interval '1 second', '{parked_call}');",  # noqa: E501
    )
    assert parked.stdout.strip().splitlines()[-1] == "parked"
    again = _claim(applied, "H")
    assert again is not None and again["attempt"] == 2
    lost = _finish(applied, again["step_id"], "NOT-THE-HOLDER", "succeeded")
    assert lost.stdout.strip().splitlines()[-1] == "lease_lost"
    assert (
        _finished(applied, again["step_id"], "H", "succeeded", request_id=finished_call)
        == "running"
    )

    rows = _scalar(
        applied,
        "SELECT string_agg(attempt || ':' || event || ':' || coalesce(outcome::text, '-') || ':' "
        "|| coalesce(request_id::text, '-'), ' ' ORDER BY attempt, recorded_at) "
        f"FROM app_private.workflow_attempt WHERE step_id = '{first['step_id']}';",
    )
    assert rows == f"1:parked:-:{parked_call} 2:finished:succeeded:{finished_call}", rows
    assert run


# ---------------------------------------------------------------------------
# WF-COMP-001: compensation
# ---------------------------------------------------------------------------


def _fail_at_d(applied: dict[str, Any], people: dict[str, str], holder: str = "H") -> str:
    """A `reverse` run: a, b, c succeed; d fails terminally."""
    run = _enqueue(applied, people["agent"], "reverse")
    for expected in ("a", "b", "c"):
        step = _claim(applied, holder)
        assert step is not None and step["name"] == expected, step
        assert _finished(applied, step["step_id"], holder, "succeeded") == "running"
    last = _claim(applied, holder)
    assert last is not None and last["name"] == "d"
    status = _finished(applied, last["step_id"], holder, "refused", reason="row_not_found")
    assert status == "compensating", status
    return run


def test_a_failure_with_compensable_steps_becomes_compensating_in_reverse(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    """One undo per succeeded forward step that declares one, newest first.

    `c` succeeded and declares no compensation, so it has no undo row -- the
    rows are a record of what WILL be compensated, not of every step.
    """
    run = _fail_at_d(applied, fresh)
    rows = _scalar(
        applied,
        "SELECT string_agg(position || ':' || name || ':' || compensates || ':' || status::text, "
        "' ' ORDER BY position) FROM app_private.workflow_step "
        f"WHERE run_id = '{run}' AND phase = 'compensation';",
    )
    assert rows == "1001:undo-2:2:queued 1002:undo-1:1:queued", rows
    assert _run(applied, run, "compensation_cause") == "failed"
    assert _run(applied, run, "stopped_reason") == "row_not_found"
    assert _run(applied, run, "finished_at") == "NULL", "a compensating run reads as over"


def test_the_compensation_key_is_derived_from_the_run_and_the_forward_position(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    run = _fail_at_d(applied, fresh)
    keys = _scalar(
        applied,
        "SELECT string_agg(idempotency_key, ' ' ORDER BY position) FROM app_private.workflow_step "
        f"WHERE run_id = '{run}' AND phase = 'compensation';",
    )
    assert keys == f"wf-{run}-undo-2 wf-{run}-undo-1", keys
    forward = _scalar(
        applied,
        "SELECT string_agg(idempotency_key, ' ') FROM app_private.workflow_step "
        f"WHERE run_id = '{run}' AND phase = 'forward';",
    )
    assert not set(keys.split()) & set(forward.split()), "an undo reuses a forward key"


def test_a_compensation_row_waits_for_the_one_before_it(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    run = _fail_at_d(applied, fresh)
    first = _claim(applied, "H")
    assert first is not None and first["name"] == "undo-2", first
    assert first["step"]["tool"] == "update_task_status" and first["step"]["name"] == "undo-2"
    assert _claim(applied, "OTHER") is None, "undo-1 was claimable before undo-2 finished"
    assert _finished(applied, first["step_id"], "H", "succeeded") == "compensating"
    second = _claim(applied, "H")
    assert second is not None and second["name"] == "undo-1", second
    assert run


def test_a_failed_compensation_does_not_stop_the_rest_and_ends_incomplete(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    run = _fail_at_d(applied, fresh)
    first = _claim(applied, "H")
    assert first is not None
    assert (
        _finished(applied, first["step_id"], "H", "refused", reason="write_conflict")
        == "compensating"
    )
    second = _claim(applied, "H")
    assert second is not None and second["name"] == "undo-1", "a failed undo stopped the rest"
    assert _finished(applied, second["step_id"], "H", "succeeded") == "failed"
    assert _run(applied, run, "compensation_outcome") == "incomplete"
    assert _run(applied, run, "finished_at") != "NULL"


def test_all_compensations_succeeding_ends_complete_at_the_cause(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    run = _fail_at_d(applied, fresh)
    for _ in range(2):
        step = _claim(applied, "H")
        assert step is not None
        last = _finished(applied, step["step_id"], "H", "succeeded")
    assert last == "failed"
    assert _run(applied, run, "status") == "failed"
    assert _run(applied, run, "compensation_outcome") == "complete"


def test_a_cancel_with_nothing_to_compensate_is_cancelled_directly(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    run = _enqueue(applied, fresh["agent"], "plain")
    step = _claim(applied, "H")
    assert step is not None
    assert _finished(applied, step["step_id"], "H", "succeeded") == "running"
    cancelled = _as_role(
        applied,
        _auth(applied),
        f"SELECT app_private.workflow_cancel('{run}', '{fresh['agent']}');",
    )
    assert cancelled.returncode == 0, cancelled.stderr[:300]
    assert _claim(applied, "H") is None
    assert _run(applied, run, "status") == "cancelled"
    assert _run(applied, run, "compensation_cause") == "NULL"


def test_a_compensating_run_is_not_timed_out(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    run = _fail_at_d(applied, fresh)
    _superuser(
        applied,
        "UPDATE app_private.workflow_run SET started_at = now() - interval '2 hours' "
        f"WHERE id = '{run}';",
    )
    undo = _claim(applied, "H")
    assert undo is not None and undo["name"] == "undo-2", "a compensating run was timed out"
    assert _run(applied, run, "status") == "compensating"


def test_a_refused_mint_during_compensation_stops_the_run_incomplete(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    run = _fail_at_d(applied, fresh)
    undo = _claim(applied, "H")
    assert undo is not None
    assert _finished(applied, undo["step_id"], "H", "token_refused") == "stopped"
    assert _run(applied, run, "stopped_reason") == "agent_not_active"
    assert _run(applied, run, "compensation_outcome") == "incomplete"


def test_a_timed_out_run_with_a_call_in_flight_waits_for_the_call(
    applied: dict[str, Any], fresh: dict[str, str]
) -> None:
    """D1744: the timeout is applied only when nothing is upstream.

    The cancel phase's own rule, extended to the timeout: failing the run under a
    live lease would begin the undo while a forward write was still in flight,
    and that write, landing after the undo rows were appended, would be undone
    by nothing.
    """
    run = _enqueue(applied, fresh["agent"], "plain")
    step = _claim(applied, "H", margin=60)
    assert step is not None
    _superuser(
        applied,
        "UPDATE app_private.workflow_run SET started_at = now() - interval '2 hours' "
        f"WHERE id = '{run}';",
    )
    assert _claim(applied, "OTHER") is None
    assert _run(applied, run, "status") == "running", "the run was failed under a live lease"
    assert _finished(applied, step["step_id"], "H", "succeeded") == "running"
    assert _claim(applied, "H") is None
    assert _run(applied, run, "status") + " " + _run(applied, run, "stopped_reason") == (
        "failed timed_out"
    )


# ---------------------------------------------------------------------------
# WF-PROV-001: provenance, the substrate half
# ---------------------------------------------------------------------------


def _audit_row(
    applied: dict[str, Any],
    people: dict[str, str],
    request_id: str,
    *,
    source: str,
    outcome: str,
    reason: str = "NULL",
    tool: str = "set_note_embedding",
) -> None:
    written = _superuser(
        applied,
        "INSERT INTO app_private.agent_audit (source, agent_id, owner_id, tool, request_id, "
        "parameters, outcome, row_count, elapsed_ms, completed_at, capability_version, "
        "contract_hash, denial_reason) VALUES "
        f"('{source}', '{people['agent']}', '{people['owner']}', '{tool}', '{request_id}', "
        '\'{"p_note_id": "parameter-canary-9c1d"}\'::jsonb, '
        f"'{outcome}', 1, 7, now(), '1.0.0', '{'c' * 64}', {reason});",
    )
    assert written.returncode == 0, written.stderr[:400]


@pytest.fixture
def provenance(applied: dict[str, Any], fresh: dict[str, str]) -> dict[str, Any]:
    """An approved `gates` run carried to success, its audit rows written by the
    superuser with chosen request ids -- the join is the subject here, and the
    plane that writes those rows has its own proofs."""
    gated = _at_gate(applied, fresh)
    _audit_row(
        applied, fresh, gated["refused_call"], source="agent_plane", outcome="refused",
        reason="'approval_required'",
    )  # fmt: skip
    assert _decide(applied, gated["run"], "gate", fresh["approver"], "approve").returncode == 0
    held = _claim(applied, "H")
    assert held is not None and held["name"] == "gate"
    served = str(uuid.uuid4())
    _audit_row(applied, fresh, served, source="agent_plane", outcome="committed")
    _audit_row(applied, fresh, served, source="database", outcome="committed")
    result = '{"row": {"note_id": "result-canary-4e2b"}}'
    assert (
        _finished(applied, held["step_id"], "H", "succeeded", request_id=served, result=result)
        == "running"
    )
    last = _claim(applied, "H")
    assert last is not None and last["name"] == "finish"
    assert _finished(applied, last["step_id"], "H", "succeeded") == "succeeded"

    read = _as_role(
        applied, _auth(applied), f"SELECT app_private.workflow_provenance('{gated['run']}');"
    )
    assert read.returncode == 0, read.stderr[:400]
    raw = read.stdout.strip().splitlines()[-1]
    return {"raw": raw, "document": json.loads(raw), "served": served, **gated}


def test_provenance_joins_every_attempt_to_its_audit_rows(provenance: dict[str, Any]) -> None:
    document = provenance["document"]
    gate = next(step for step in document["steps"] if step["name"] == "gate")
    assert gate["capability"] == "set_note_embedding@1.0.0" and gate["tool"] == "set_note_embedding"
    assert [(a["attempt"], a["event"]) for a in gate["attempts"]] == [
        (1, "approval_requested"),
        (2, "finished"),
    ], gate["attempts"]
    requested, finished = gate["attempts"]
    assert requested["request_id"] == provenance["refused_call"]
    assert [
        (row["source"], row["outcome"], row["denial_reason"]) for row in requested["audit"]
    ] == [("agent_plane", "refused", "approval_required")]
    assert finished["request_id"] == provenance["served"]
    assert sorted((row["source"], row["outcome"]) for row in finished["audit"]) == [
        ("agent_plane", "committed"),
        ("database", "committed"),
    ]
    assert finished["audit"][0]["contract_hash"] == "c" * 64
    assert document["run"]["status"] == "succeeded"
    assert document["definition"]["lock_tools_sha256"] == "b" * 64


def test_provenance_names_the_approvals_decider(
    provenance: dict[str, Any], people: dict[str, str]
) -> None:
    (approval,) = provenance["document"]["approvals"]
    assert approval["status"] == "approved"
    assert approval["decided_by"] == people["approver"]
    assert approval["decided_by_username"] == "gate-approver"
    assert approval["requested_request_id"] == provenance["refused_call"]


def test_provenance_reports_the_profile_absent_with_a_reason(provenance: dict[str, Any]) -> None:
    """ADR 0195: not filled, not omitted -- absent, and why."""
    assert provenance["document"]["profile"] == {
        "value": None,
        "reason": "no per-call record names a profile",
    }


def test_provenance_carries_no_parameters_result_or_input_value(
    provenance: dict[str, Any],
) -> None:
    """D1746: provenance must not put back what the audit left out.

    The audit rows were written with a `parameters` canary, the step with a
    `result` canary, and the run's input with a third. None may appear; the
    input's KEYS do.
    """
    raw = provenance["raw"]
    for canary in ("parameter-canary-9c1d", "result-canary-4e2b", CANARY):
        assert canary not in raw, f"provenance carried {canary}"
    assert provenance["document"]["run"]["input_keys"] == ["secret", "task_id"]
    assert "parameters" not in raw and '"result"' not in raw


def test_provenance_refuses_a_missing_run(applied: dict[str, Any]) -> None:
    missing = _as_role(
        applied, _auth(applied), f"SELECT app_private.workflow_provenance('{uuid.uuid4()}');"
    )
    assert missing.returncode != 0 and "no such run" in missing.stderr
