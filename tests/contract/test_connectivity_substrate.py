"""Migration 0036: the emitter, the outbox, connectors, receipts and the event wait.

`EVT-EMIT-001`, the substrate halves of `EVT-WAIT-001`, `CONN-SCHED-001`,
`CONN-IN-001` and `CONN-ADMIN-001`, under a real cluster with every released
migration applied as `migration_user` (D285). The cluster fixture and its small
helpers are COPIED from `test_workflow_gates.py`, not imported, for D386's
reason: a reader must be able to tell whose fixture broke.

**What the rigs measured before 0036 was written** (Session 34 Run 1):

* rig 34a: every request role and `auth_service` meets `42501 permission denied
  for schema app` calling the emitter, `has_function_privilege` is false for
  each, PostgREST answers `POST /rpc/emit_event` with `PGRST202`, and a
  rolled-back caller leaves nothing (ADR 0235, D1814);
* rig 34c: a tool call is served with the tool's own scope alone, so the
  binding rule's equality does not include `meta:read` (ADR 0236).

**The emitter is reached the way a project reaches it**: a scratch definer RPC
created as the object owner calls `app.emit_event`, and a request role calls
the RPC with the GUCs the pre-request hook would set. Nothing here grants the
emitter to anyone.

**The claims are global by design**, so every proof that claims a step or a
delivery begins from the `fresh` fixture, which closes what another proof left
open, and every proof names its own connectors and events.

**Every call to a released function is ONE string literal** (D464): the arity
guard walks a call as written.
"""

from __future__ import annotations

# ruff: noqa: S608
#
# Every interpolated value below is a role or database name read from a rendered
# outputs document this repository produced, or a uuid / name this module
# generated. None of it is caller input, and a role name cannot be bound.
import json
import re
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

TABLES = ("connector", "connector_event", "connector_delivery", "connector_receipt")

#: Every role but the object owner, which owns the tables and every function.
ROLES = (
    "auth_service",
    "agent_writer",
    "agent_reader",
    "authenticated",
    "anon",
    "storage_service",
    "app_runtime",
    "migration_user",
)

DIGEST = "c" * 64

#: One write step: a note. The definition a connector starts in these proofs.
ONE_NOTE = {
    "timeout_seconds": 600,
    "steps": [
        {
            "name": "note",
            "tool": "create_note",
            "capability": "create_note",
            "capability_version": "1.0.0",
            "resource": None,
            "kind": "write",
            "arguments": {"p_title": "{{input.title}}"},
            "retry": {"max": 0, "backoff_seconds": 5},
            "timeout_seconds": 30,
        }
    ],
}

#: A wait on an event, then a write.
WAITER = {
    "timeout_seconds": 600,
    "steps": [
        {
            "name": "hold",
            "kind": "wait",
            "event": "note_embedding.set@1",
            "match": {"note_id": "{{input.note_id}}"},
            "seconds": 60,
            "timeout_seconds": 5,
            "retry": {"max": 0, "backoff_seconds": 1},
        },
        ONE_NOTE["steps"][0],
    ],
}


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
    """`test_workflow_gates.py`'s cluster, copied: the locked image, the
    product's own role statements, and the same two skips."""
    if not (FIXTURE / "outputs.json").is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    if _docker("version", "--format", "{{.Server.Version}}", timeout=30).returncode != 0:
        pytest.skip("docker is not available")

    document = json.loads((FIXTURE / "outputs.json").read_text(encoding="utf-8"))
    roles = document["database"]["roles"]
    database = document["database"]["name"]
    password = secrets.token_hex(24)
    name = f"apg-connectivity-{secrets.token_hex(4)}"

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


def _scalar(cluster: dict[str, Any], sql: str) -> str:
    result = _superuser(cluster, sql)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""


def _session(
    cluster: dict[str, Any],
    role_key: str | None,
    sql: str,
    *,
    user: str | None = None,
    agent: str | None = None,
    end: str = "COMMIT",
) -> str:
    """One transaction as a named role, with the GUCs the pre-request hook sets.

    The GUCs are set inside a `DO` block so they print nothing, transaction
    local exactly as the hook sets them (0018). `role_key` None is the
    bootstrap superuser, which is how the deploy and the rehearsal call.
    """
    lines = ["BEGIN;"]
    if role_key is not None:
        lines.append(f'SET LOCAL ROLE "{cluster["roles"][role_key]}";')
    settings = []
    if user is not None:
        settings.append(f"PERFORM pg_catalog.set_config('app.user_id', '{user}', true);")
    if agent is not None:
        settings.append(f"PERFORM pg_catalog.set_config('app.agent_id', '{agent}', true);")
    if settings:
        lines.append("DO $gucs$ BEGIN " + " ".join(settings) + " END $gucs$;")
    lines.append(sql)
    lines.append(f"{end};")
    return "\n".join(lines)


def _value(cluster: dict[str, Any], role_key: str | None, sql: str, **gucs: Any) -> str:
    result = _superuser(cluster, _session(cluster, role_key, sql, **gucs))
    assert result.returncode == 0, result.stderr[:600]
    lines = result.stdout.strip().splitlines()
    return lines[-1] if lines else ""


def _refusal(cluster: dict[str, Any], role_key: str | None, call: str, **gucs: Any) -> tuple:
    """`(sqlstate, message)` of the refusal `call` meets, or `("", "")` when served."""
    block = (
        "DO $refusal$ BEGIN "
        f"PERFORM {call}; "
        "RAISE NOTICE 'refusal=|'; "
        "EXCEPTION WHEN OTHERS THEN "
        "RAISE NOTICE 'refusal=%|%', SQLSTATE, SQLERRM; "
        "END $refusal$;"
    )
    result = _superuser(cluster, _session(cluster, role_key, block, **gucs))
    assert result.returncode == 0, result.stderr[:600]
    found = re.search(r"refusal=([^|\n]*)\|(.*)", result.stderr)
    assert found, result.stderr[:600]
    return found.group(1), found.group(2).strip()


@pytest.fixture(scope="module")
def applied(cluster: dict[str, Any]) -> dict[str, Any]:
    """Every released migration applied as `migration_user`, 0036 included."""
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
    assert "20260929120036" in applied_versions, applied_versions[-3:]
    return {"versions": applied_versions, **cluster}


@pytest.fixture(scope="module")
def people(applied: dict[str, Any]) -> dict[str, str]:
    """Two owners (two tenants), a writer agent of the first, the definitions,
    and a scratch definer RPC in the project's shape that calls the emitter."""
    scopes = ", ".join(f"'{scope}'" for scope in SCOPES)
    owner = _scalar(
        applied,
        "SELECT app_private.auth_create_user('conn-owner', 'conn-owner', 'authenticated', "
        f"ARRAY[{scopes}]::text[], '{STORED_HASH}');",
    )
    other = _scalar(
        applied,
        "SELECT app_private.auth_create_user('conn-other', 'conn-other', 'authenticated', "
        f"ARRAY[{scopes}]::text[], '{STORED_HASH}');",
    )
    writer = applied["roles"]["agent_writer"]
    agent = _scalar(
        applied,
        f"SELECT app_private.auth_create_agent('conn-agent', '', '{writer}', ARRAY[{scopes}], '{owner}', '{STORED_HASH}', NULL);",  # noqa: E501
    )
    for name, body, required in (
        ("one-note", ONE_NOTE, "ARRAY['notes:write']"),
        ("waiter", WAITER, "ARRAY['notes:write']"),
    ):
        installed = _superuser(
            applied,
            f"SELECT app_private.workflow_install_definition('{name}', 1, '{json.dumps(body)}'::jsonb, '{'a' * 64}', '{'b' * 64}', {required});",  # noqa: E501
        )
        assert installed.returncode == 0, installed.stderr

    roles = applied["roles"]
    made = _superuser(
        applied,
        f'SET ROLE "{roles["object_owner"]}";\n'
        "CREATE FUNCTION api.s34_emit(p_name text, p_version integer, p_payload jsonb)\n"
        "  RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp\n"
        "AS $fn$ BEGIN RETURN app.emit_event(p_name, p_version, p_payload); END $fn$;\n"
        "REVOKE ALL ON FUNCTION api.s34_emit(text, integer, jsonb) FROM PUBLIC;\n"
        "GRANT EXECUTE ON FUNCTION api.s34_emit(text, integer, jsonb) "
        f'TO "{roles["authenticated"]}", "{roles["agent_writer"]}";\n'
        "RESET ROLE;",
    )
    assert made.returncode == 0, made.stderr
    return {"owner": owner, "other": other, "agent": agent}


@pytest.fixture
def fresh(applied: dict[str, Any], people: dict[str, str]) -> dict[str, str]:
    """Every run and every pending delivery another proof left open is closed."""
    closed = _superuser(
        applied,
        "UPDATE app_private.workflow_run SET status = 'cancelled', finished_at = now() "
        "WHERE status::text IN ('queued', 'running', 'compensating');\n"
        "UPDATE app_private.connector_delivery SET status = 'delivered', delivered_at = now(), "
        "claimed_by = NULL, lease_until = NULL WHERE status = 'pending';",
    )
    assert closed.returncode == 0, closed.stderr
    return people


def _name(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(3)}"


def _event() -> str:
    """An event name no other proof subscribes to."""
    return f"s34.t{secrets.token_hex(3)}"


def _agent(applied: dict[str, Any], owner: str, scopes: list[str]) -> str:
    writer = applied["roles"]["agent_writer"]
    listed = ", ".join(f"'{scope}'" for scope in scopes)
    return _scalar(
        applied,
        f"SELECT app_private.auth_create_agent('{_name('conn')}', '', '{writer}', ARRAY[{listed}], '{owner}', '{STORED_HASH}', NULL);",  # noqa: E501
    )


def _outbound(
    applied: dict[str, Any], name: str, event: str, *, endpoint: str | None, retry: int = 2
) -> str:
    target = "NULL" if endpoint is None else f"'{endpoint}'"
    return _scalar(
        applied,
        f"SELECT app_private.connector_install('{name}', 1, 'outbound', '{{}}'::jsonb, '{DIGEST}', '{event}@1', {target}, NULL, NULL, '{{}}', NULL, {retry}, 5);",  # noqa: E501
    )


def _inbound(applied: dict[str, Any], name: str, definition: str = "one-note") -> str:
    body = json.dumps({"body": {"members": {"title": {"type": "string", "required": True}}}})
    return _scalar(
        applied,
        f"SELECT app_private.connector_install('{name}', 1, 'inbound', '{body}'::jsonb, '{DIGEST}', NULL, NULL, '{definition}', 1, ARRAY['notes:write'], NULL, NULL, NULL);",  # noqa: E501
    )


def _scheduled(applied: dict[str, Any], name: str) -> str:
    body = json.dumps({"input": {"title": "scheduled"}})
    return _scalar(
        applied,
        f"SELECT app_private.connector_install('{name}', 1, 'scheduled', '{body}'::jsonb, '{DIGEST}', NULL, NULL, 'one-note', 1, ARRAY['notes:write'], 60, NULL, NULL);",  # noqa: E501
    )


def _enable(applied: dict[str, Any], name: str, agent: str | None, user: str) -> str:
    target = "NULL" if agent is None else f"'{agent}'"
    return _value(
        applied,
        "auth_service",
        f"SELECT app_private.connector_enable('{name}', {target}, '{user}');",
    )


def _emit(applied: dict[str, Any], event: str, payload: dict[str, Any], **gucs: Any) -> str:
    return _value(
        applied,
        gucs.pop("role", "authenticated"),
        f"SELECT coalesce(api.s34_emit('{event}', 1, '{json.dumps(payload)}'::jsonb)::text, 'NULL');",  # noqa: E501
        **gucs,
    )


def _count(applied: dict[str, Any], sql: str) -> int:
    return int(_scalar(applied, sql))


# ---------------------------------------------------------------------------
# EVT-EMIT-001 -- who may write an event, and what one is
# ---------------------------------------------------------------------------


def test_the_four_tables_grant_nothing_to_any_role(applied: dict[str, Any]) -> None:
    """0034's posture for the four new tables (D1647): no role holds anything."""
    offenders: list[str] = []
    for role_key in ROLES:
        role = applied["roles"][role_key]
        for table in TABLES:
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                got = _scalar(
                    applied,
                    f"SELECT has_table_privilege('{role}', "
                    f"'app_private.{table}', '{privilege}')::text;",
                )
                if got != "false":
                    offenders.append(f"{role_key} holds {privilege} on {table}")
    assert not offenders, offenders


def test_emit_event_is_executable_by_no_role(applied: dict[str, Any], people) -> None:
    """Granted to nobody, measured on the FUNCTION and not only the schema (D1814).

    A call from a request role meets `42501` at the `app` schema first (rig
    34a), which would survive a function granted to PUBLIC -- so the proof reads
    the function's own privilege for every role as well, and its ACL.
    """
    signature = "app.emit_event(text,integer,jsonb)"
    for role_key in ROLES:
        role = applied["roles"][role_key]
        got = _scalar(
            applied, f"SELECT has_function_privilege('{role}', '{signature}', 'EXECUTE');"
        )
        assert got == "f", f"{role_key} may execute the emitter"
    grantees = _scalar(
        applied,
        "SELECT coalesce(string_agg(a.grantee::regrole::text, ','), '') FROM pg_proc p, "
        "aclexplode(p.proacl) a WHERE p.oid = 'app.emit_event(text,integer,jsonb)'::regprocedure "
        "AND a.privilege_type = 'EXECUTE';",
    )
    assert grantees == applied["roles"]["object_owner"], grantees

    for role_key in ("authenticated", "agent_writer", "auth_service", "anon"):
        sqlstate, message = _refusal(
            applied,
            role_key,
            "app.emit_event('note_embedding.set', 1, '{}'::jsonb)",
            user=people["owner"],
        )
        assert sqlstate == "42501", (role_key, sqlstate, message)


def test_a_definer_function_emits_inside_its_own_transaction(applied, fresh) -> None:
    """The project's shape: a definer RPC calls the emitter; the identity is the GUCs'."""
    event = _event()
    connector = _name("out")
    assert _outbound(applied, connector, event, endpoint="http://sink.test/ok") == "installed"
    assert _enable(applied, connector, None, fresh["owner"]) == "enabled"

    as_human = _emit(applied, event, {"note_id": "n1"}, user=fresh["owner"])
    assert as_human != "NULL"
    row = _scalar(
        applied,
        "SELECT owner_id || '|' || coalesce(agent_id::text, 'none') || '|' || payload::text "
        f"FROM app_private.connector_event WHERE id = '{as_human}';",
    )
    assert row == f'{fresh["owner"]}|none|{{"note_id": "n1"}}', row

    as_agent = _emit(
        applied,
        event,
        {"note_id": "n2"},
        role="agent_writer",
        user=fresh["owner"],
        agent=fresh["agent"],
    )
    row = _scalar(
        applied,
        "SELECT owner_id || '|' || agent_id FROM app_private.connector_event "
        f"WHERE id = '{as_agent}';",
    )
    assert row == f"{fresh['owner']}|{fresh['agent']}", row


def test_nothing_is_recorded_when_nothing_listens(applied, fresh) -> None:
    """D1782: no enabled subscriber, no row, and the answer is NULL."""
    before = _count(applied, "SELECT count(*) FROM app_private.connector_event;")
    assert _emit(applied, _event(), {"note_id": "x"}, user=fresh["owner"]) == "NULL"
    assert _count(applied, "SELECT count(*) FROM app_private.connector_event;") == before

    # The control: the same call with a subscriber records one.
    event = _event()
    connector = _name("out")
    _outbound(applied, connector, event, endpoint="http://sink.test/ok")
    _enable(applied, connector, None, fresh["owner"])
    assert _emit(applied, event, {"note_id": "x"}, user=fresh["owner"]) != "NULL"
    assert _count(applied, "SELECT count(*) FROM app_private.connector_event;") == before + 1


def test_one_delivery_per_enabled_subscriber_with_an_endpoint(applied, fresh) -> None:
    """Two enabled subscribers with endpoints, one whose endpoint was removed."""
    event = _event()
    first, second, emptied = _name("out"), _name("out"), _name("out")
    for connector in (first, second, emptied):
        _outbound(applied, connector, event, endpoint="http://sink.test/ok", retry=3)
        _enable(applied, connector, None, fresh["owner"])
    assert _outbound(applied, emptied, event, endpoint=None, retry=3) == "endpoint_updated"

    recorded = _emit(applied, event, {"note_id": "x"}, user=fresh["owner"])
    rows = _scalar(
        applied,
        "SELECT string_agg(c.name || ':' || d.max_attempts || ':' || d.status, ',' "
        "ORDER BY c.name) FROM app_private.connector_delivery d "
        "JOIN app_private.connector c ON c.id = d.connector_id "
        f"WHERE d.event_id = '{recorded}';",
    )
    assert rows == ",".join(sorted(f"{name}:4:pending" for name in (first, second))), rows


def test_a_disabled_connector_receives_no_delivery(applied, fresh) -> None:
    event = _event()
    enabled, disabled = _name("out"), _name("out")
    for connector in (enabled, disabled):
        _outbound(applied, connector, event, endpoint="http://sink.test/ok")
        _enable(applied, connector, None, fresh["owner"])
    assert (
        _value(
            applied, "auth_service", f"SELECT app_private.connector_disable('{disabled}', NULL);"
        )
        == "disabled"
    )
    recorded = _emit(applied, event, {"note_id": "x"}, user=fresh["owner"])
    names = _scalar(
        applied,
        "SELECT string_agg(c.name, ',') FROM app_private.connector_delivery d "
        "JOIN app_private.connector c ON c.id = d.connector_id "
        f"WHERE d.event_id = '{recorded}';",
    )
    assert names == enabled, names


def _parked_wait(applied: dict[str, Any], people: dict[str, str], note_id: str) -> tuple:
    """A run of `waiter` whose `hold` step is parked on `note_embedding.set@1`."""
    run = _value(
        applied,
        "auth_service",
        f"SELECT app_private.workflow_enqueue('{people['agent']}', 'waiter', 1, '{json.dumps({'note_id': note_id})}'::jsonb, false);",  # noqa: E501
    )
    holder = _name("holder")
    step = _value(
        applied,
        "auth_service",
        f"SELECT step_id FROM app_private.workflow_claim_step('{holder}', 60);",
    )
    assert step, "no step was claimed"
    match = json.dumps({"note_id": note_id})
    parked = _value(
        applied,
        "auth_service",
        f"SELECT app_private.workflow_await_event('{step}', '{holder}', 'note_embedding.set@1', '{match}'::jsonb, now() + interval '60 seconds');",  # noqa: E501
    )
    assert parked == "parked", parked
    return run, step


def _served(applied: dict[str, Any], step: str) -> str:
    return _scalar(
        applied,
        "SELECT (await_served_at IS NOT NULL)::text || '|' || coalesce(await_payload::text, '') "
        f"FROM app_private.workflow_step WHERE id = '{step}';",
    )


def test_a_wait_is_served_only_for_the_same_owner_and_a_contained_match(applied, fresh) -> None:
    """ADR 0239: the owner is the correlation, the match the selection.

    Three emissions, in the order an attacker would try them: another tenant's
    event with the right payload, the right owner with the wrong note, and only
    then the owner's own matching event -- carrying an EXTRA member, because the
    rule is containment and not equality.
    """
    note_id = str(uuid.uuid4())
    _, step = _parked_wait(applied, fresh, note_id)

    _emit(applied, "note_embedding.set", {"note_id": note_id}, user=fresh["other"])
    assert _served(applied, step) == "false|", "another owner's event served the wait"

    _emit(applied, "note_embedding.set", {"note_id": str(uuid.uuid4())}, user=fresh["owner"])
    assert _served(applied, step) == "false|", "a non-matching payload served the wait"

    _emit(applied, "note_embedding.set", {"note_id": note_id, "extra": 1}, user=fresh["owner"])
    served, payload = _served(applied, step).split("|", 1)
    assert served == "true"
    assert json.loads(payload) == {"note_id": note_id, "extra": 1}
    assert (
        _scalar(
            applied,
            f"SELECT (resume_after <= now())::text FROM app_private.workflow_step WHERE id = '{step}';",  # noqa: E501
        )
        == "true"
    )


def test_emit_refuses_without_an_identity(applied, fresh) -> None:
    sqlstate, message = _refusal(
        applied, "authenticated", "api.s34_emit('note_embedding.set', 1, '{}'::jsonb)"
    )
    assert (sqlstate, message) == ("PT401", "AP401: an event needs a request identity")


@pytest.mark.parametrize(
    "name,version,payload,token",
    [
        pytest.param("Bad", "1", "'{}'::jsonb", "event_name_invalid", id="uppercase_name"),
        pytest.param("a..b", "1", "'{}'::jsonb", "event_name_invalid", id="empty_segment"),
        pytest.param("ok.name", "0", "'{}'::jsonb", "event_version_invalid", id="version_zero"),
        pytest.param("ok.name", "1000", "'{}'::jsonb", "event_version_invalid", id="version_big"),
        pytest.param("ok.name", "1", "'[1]'::jsonb", "event_payload_invalid", id="array"),
        pytest.param("ok.name", "1", "NULL::jsonb", "event_payload_invalid", id="null"),
    ],
)
def test_emit_refuses_a_bad_name_version_or_payload(
    applied, fresh, name: str, version: str, payload: str, token: str
) -> None:
    sqlstate, message = _refusal(
        applied,
        "authenticated",
        f"api.s34_emit('{name}', {version}, {payload})",
        user=fresh["owner"],
    )
    assert (sqlstate, message) == ("PT422", f"AP422: {token}")


def test_a_rolled_back_caller_leaves_no_event(applied, fresh) -> None:
    event = _event()
    connector = _name("out")
    _outbound(applied, connector, event, endpoint="http://sink.test/ok")
    _enable(applied, connector, None, fresh["owner"])
    before = _count(applied, "SELECT count(*) FROM app_private.connector_delivery;")
    result = _superuser(
        applied,
        _session(
            applied,
            "authenticated",
            f"SELECT api.s34_emit('{event}', 1, '{{}}'::jsonb);",
            user=fresh["owner"],
            end="ROLLBACK",
        ),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "the emitter returned nothing inside the transaction"
    assert _count(applied, "SELECT count(*) FROM app_private.connector_delivery;") == before
    assert (
        _count(
            applied,
            f"SELECT count(*) FROM app_private.connector_event WHERE name = '{event}';",
        )
        == 0
    )


def test_the_payload_bound_is_eight_kilobytes(applied, fresh) -> None:
    """8,192 bytes of `payload::text` is accepted and 8,193 refused (D1782)."""
    event = _event()
    connector = _name("out")
    _outbound(applied, connector, event, endpoint="http://sink.test/ok")
    _enable(applied, connector, None, fresh["owner"])
    # `{"k": "<n x>"}` renders as n + 9 bytes.
    for filler, expected in ((8183, 8192), (8184, 8193)):
        rendered = _scalar(
            applied, f"SELECT octet_length(jsonb_build_object('k', repeat('x', {filler}))::text);"
        )
        assert int(rendered) == expected
    accepted = _value(
        applied,
        "authenticated",
        f"SELECT api.s34_emit('{event}', 1, jsonb_build_object('k', repeat('x', 8183)));",
        user=fresh["owner"],
    )
    assert accepted
    sqlstate, message = _refusal(
        applied,
        "authenticated",
        f"api.s34_emit('{event}', 1, jsonb_build_object('k', repeat('x', 8184)))",
        user=fresh["owner"],
    )
    assert (sqlstate, message) == ("PT422", "AP422: event_payload_invalid")


# ---------------------------------------------------------------------------
# EVT-WAIT-001 -- the gate read reports the event
# ---------------------------------------------------------------------------


def test_gate_state_reports_the_event(applied, fresh) -> None:
    """Served, then reclaimed: the one gate read carries `served` and the payload."""
    note_id = str(uuid.uuid4())
    _, step = _parked_wait(applied, fresh, note_id)
    _emit(applied, "note_embedding.set", {"note_id": note_id}, user=fresh["owner"])

    holder = _name("holder")
    reclaimed = _value(
        applied,
        "auth_service",
        f"SELECT step_id FROM app_private.workflow_claim_step('{holder}', 60);",
    )
    assert reclaimed == step
    state = json.loads(
        _value(
            applied,
            "auth_service",
            f"SELECT app_private.workflow_gate_state('{step}', '{holder}');",
        )
    )
    assert state["event"] == {"served": True, "payload": {"note_id": note_id}}, state
    assert state["approval"] is None and state["waited"] is False, state


# ---------------------------------------------------------------------------
# CONN-SCHED-001 -- the interval table is the connector row
# ---------------------------------------------------------------------------


def _runs_of(applied: dict[str, Any], agent: str) -> int:
    return _count(
        applied, f"SELECT count(*) FROM app_private.workflow_run WHERE agent_id = '{agent}';"
    )


def _fire(applied: dict[str, Any]) -> int:
    return int(_value(applied, "auth_service", "SELECT app_private.connector_fire_due();"))


def test_a_due_schedule_fires_once_and_advances(applied, fresh) -> None:
    connector = _name("sched")
    agent = _agent(applied, fresh["owner"], ["notes:write"])
    assert _scheduled(applied, connector) == "installed"
    assert _enable(applied, connector, agent, fresh["owner"]) == "enabled"

    assert _fire(applied) == 1
    assert _runs_of(applied, agent) == 1
    ahead = int(
        _scalar(
            applied,
            "SELECT extract(epoch FROM next_fire_at - now())::integer "
            f"FROM app_private.connector WHERE name = '{connector}';",
        )
    )
    assert 55 <= ahead <= 60, ahead
    assert _fire(applied) == 0
    assert _runs_of(applied, agent) == 1


def test_missed_fires_coalesce_to_one(applied, fresh) -> None:
    connector = _name("sched")
    agent = _agent(applied, fresh["owner"], ["notes:write"])
    _scheduled(applied, connector)
    _enable(applied, connector, agent, fresh["owner"])
    _scalar(
        applied,
        "UPDATE app_private.connector SET next_fire_at = now() - interval '600 seconds' "
        f"WHERE name = '{connector}' RETURNING name;",
    )
    assert _fire(applied) == 1
    assert _fire(applied) == 0
    assert _runs_of(applied, agent) == 1


def test_a_disabled_or_unbound_schedule_fires_nothing(applied, fresh) -> None:
    """Disabled fires nothing; a widened agent fires nothing and still advances."""
    disabled = _name("sched")
    agent = _agent(applied, fresh["owner"], ["notes:write"])
    _scheduled(applied, disabled)
    _enable(applied, disabled, agent, fresh["owner"])
    _value(applied, "auth_service", f"SELECT app_private.connector_disable('{disabled}', NULL);")
    assert _fire(applied) == 0
    assert _runs_of(applied, agent) == 0

    widened = _name("sched")
    other_agent = _agent(applied, fresh["owner"], ["notes:write"])
    _scheduled(applied, widened)
    _enable(applied, widened, other_agent, fresh["owner"])
    _scalar(
        applied,
        "UPDATE app_private.agents SET scopes = ARRAY['notes:write', 'tasks:write'] "
        f"WHERE id = '{other_agent}' RETURNING id;",
    )
    assert _fire(applied) == 0
    assert _runs_of(applied, other_agent) == 0
    assert (
        _scalar(
            applied,
            "SELECT (next_fire_at > now())::text FROM app_private.connector "
            f"WHERE name = '{widened}';",
        )
        == "true"
    )
    status = json.loads(_value(applied, "auth_service", "SELECT app_private.connector_status(20);"))
    binding = {c["name"]: c["binding"] for c in status["connectors"]}
    assert binding[widened] == "agent_scopes_differ"
    assert binding[disabled] == "unbound"


# ---------------------------------------------------------------------------
# CONN-IN-001 (substrate) -- accept, exactly once, in one transaction
# ---------------------------------------------------------------------------


def _accept(applied: dict[str, Any], name: str, delivery: str, body: str = '{"title": "t"}'):
    return _refusal(
        applied,
        "auth_service",
        f"app_private.connector_accept('{name}', '{delivery}', '{body}'::jsonb)",
    )


def test_accept_refuses_each_case_by_its_token(applied, fresh) -> None:
    assert _accept(applied, "no-such-connector", str(uuid.uuid4())) == (
        "PT404",
        "AP404: no_such_connector",
    )

    connector = _name("in")
    _inbound(applied, connector)
    assert _accept(applied, connector, str(uuid.uuid4())) == ("PT409", "AP409: connector_disabled")

    agent = _agent(applied, fresh["owner"], ["notes:write"])
    _enable(applied, connector, agent, fresh["owner"])
    delivery = str(uuid.uuid4())
    assert _accept(applied, connector, delivery) == ("", "")
    assert _accept(applied, connector, delivery) == ("PT409", "AP409: delivery_replayed")
    assert _runs_of(applied, agent) == 1

    _scalar(
        applied,
        "UPDATE app_private.agents SET scopes = ARRAY['notes:read', 'notes:write'] "
        f"WHERE id = '{agent}' RETURNING id;",
    )
    assert _accept(applied, connector, str(uuid.uuid4())) == ("PT409", "AP409: agent_scopes_differ")
    assert _runs_of(applied, agent) == 1


def test_a_refused_enqueue_leaves_no_receipt(applied, fresh) -> None:
    """One transaction: a definition that is not installed refuses, and the
    receipt goes with it, so the sender may retry the SAME delivery id."""
    connector = _name("in")
    _inbound(applied, connector, definition="ghost")
    agent = _agent(applied, fresh["owner"], ["notes:write"])
    _enable(applied, connector, agent, fresh["owner"])
    delivery = str(uuid.uuid4())
    assert _accept(applied, connector, delivery) == ("PT404", "AP404: no such definition")
    receipts = _count(
        applied,
        "SELECT count(*) FROM app_private.connector_receipt r JOIN app_private.connector c "
        f"ON c.id = r.connector_id WHERE c.name = '{connector}';",
    )
    assert receipts == 0


def test_accept_starts_a_run_as_the_bound_agent(applied, fresh) -> None:
    connector = _name("in")
    _inbound(applied, connector)
    agent = _agent(applied, fresh["owner"], ["notes:write"])
    _enable(applied, connector, agent, fresh["owner"])
    delivery = str(uuid.uuid4())
    run = _value(
        applied,
        "auth_service",
        f"SELECT app_private.connector_accept('{connector}', '{delivery}', '{{\"title\": \"from a sender\"}}'::jsonb);",  # noqa: E501
    )
    row = _scalar(
        applied,
        "SELECT r.agent_id || '|' || r.owner_id || '|' || r.input::text || '|' || rc.run_id "
        "FROM app_private.workflow_run r JOIN app_private.connector_receipt rc ON rc.run_id = r.id "
        f"WHERE r.id = '{run}' AND rc.delivery_id = '{delivery}';",
    )
    assert row == f'{agent}|{fresh["owner"]}|{{"title": "from a sender"}}|{run}', row


# ---------------------------------------------------------------------------
# CONN-ADMIN-001 (substrate) -- binding, and what status may say
# ---------------------------------------------------------------------------


def _enable_refusal(applied: dict[str, Any], name: str, agent: str | None, user: str) -> tuple:
    target = "NULL" if agent is None else f"'{agent}'"
    return _refusal(
        applied, "auth_service", f"app_private.connector_enable('{name}', {target}, '{user}')"
    )


def test_enable_refuses_each_case_by_its_token(applied, fresh) -> None:
    owner = fresh["owner"]
    assert _enable_refusal(applied, "no-such-connector", None, owner) == (
        "PT404",
        "AP404: no_such_connector",
    )

    inbound = _name("in")
    _inbound(applied, inbound)
    revoked = _agent(applied, owner, ["notes:write"])
    _scalar(
        applied,
        f"UPDATE app_private.agents SET status = 'revoked' WHERE id = '{revoked}' RETURNING id;",
    )
    assert _enable_refusal(applied, inbound, revoked, owner) == ("PT409", "AP409: agent_not_active")

    wider = _agent(applied, owner, ["notes:read", "notes:write"])
    assert _enable_refusal(applied, inbound, wider, owner) == (
        "PT409",
        "AP409: agent_scopes_differ",
    )

    bound = _agent(applied, owner, ["notes:write"])
    first = _name("in")
    _inbound(applied, first)
    _enable(applied, first, bound, owner)
    assert _enable_refusal(applied, inbound, bound, owner) == (
        "PT409",
        "AP409: agent_already_bound",
    )

    outbound = _name("out")
    _outbound(applied, outbound, _event(), endpoint=None)
    assert _enable_refusal(applied, outbound, None, owner) == ("PT409", "AP409: no_endpoint")
    assert _enable_refusal(applied, outbound, bound, owner) == ("PT422", "AP422: agent_not_needed")

    exact = _agent(applied, owner, ["notes:write"])
    assert _enable(applied, inbound, exact, owner) == "enabled"
    recorded = _scalar(
        applied,
        "SELECT enabled_by || '|' || agent_id FROM app_private.connector "
        f"WHERE name = '{inbound}';",
    )
    assert recorded == f"{owner}|{exact}"


def test_the_scope_difference_is_named(applied, fresh) -> None:
    """The DETAIL names what is missing and what is extra, never a value."""
    inbound = _name("in")
    _inbound(applied, inbound)
    agent = _agent(applied, fresh["owner"], ["notes:read", "tasks:write"])
    result = _superuser(
        applied,
        _session(
            applied,
            "auth_service",
            "\\set VERBOSITY verbose\n"
            f"SELECT app_private.connector_enable('{inbound}', '{agent}', '{fresh['owner']}');",
        ),
    )
    assert result.returncode != 0
    assert "missing {notes:write}; extra {notes:read,tasks:write}" in result.stderr, result.stderr


def test_disable_clears_the_schedule_and_records_who(applied, fresh) -> None:
    connector = _name("sched")
    agent = _agent(applied, fresh["owner"], ["notes:write"])
    _scheduled(applied, connector)
    _enable(applied, connector, agent, fresh["owner"])
    assert (
        _value(
            applied,
            "auth_service",
            f"SELECT app_private.connector_disable('{connector}', '{fresh['owner']}');",
        )
        == "disabled"
    )
    row = _scalar(
        applied,
        "SELECT enabled::text || '|' || coalesce(agent_id::text, 'none') || '|' || "
        "coalesce(next_fire_at::text, 'none') || '|' || disabled_by "
        f"FROM app_private.connector WHERE name = '{connector}';",
    )
    assert row == f"false|none|none|{fresh['owner']}", row


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for item in value for k in _keys(item)}
    return set()


def test_status_carries_no_endpoint_payload_or_body(applied, fresh) -> None:
    """A recursive key walk, and the three canaries searched for in the text."""
    event = _event()
    outbound = _name("out")
    _outbound(applied, outbound, event, endpoint="http://endpoint-canary.test/hook")
    _enable(applied, outbound, None, fresh["owner"])
    recorded = _emit(applied, event, {"note_id": "payload-canary"}, user=fresh["owner"])
    _scalar(
        applied,
        "UPDATE app_private.connector_delivery SET status = 'dead', dead_at = now(), attempts = 3, "
        f"last_error = 'http_500' WHERE event_id = '{recorded}' RETURNING id;",
    )
    inbound = _name("in")
    _inbound(applied, inbound)

    text = _value(applied, "auth_service", "SELECT app_private.connector_status(20);")
    document = json.loads(text)
    assert not _keys(document) & {"endpoint", "payload", "body"}, _keys(document)
    for canary in ("endpoint-canary", "payload-canary", "members"):
        assert canary not in text, canary

    mine = next(c for c in document["connectors"] if c["name"] == outbound)
    assert mine["deliveries"]["dead"] == 1
    assert mine["last_error"] == "http_500"
    assert mine["endpoint_declared"] is True
    assert [letter["event"] for letter in mine["dead_letters"]] == [f"{event}@1"]


# ---------------------------------------------------------------------------
# The delivery lease (the substrate half of CONN-OUT-001, ADR 0238)
# ---------------------------------------------------------------------------


def _claim_delivery(applied: dict[str, Any], holder: str) -> dict[str, Any] | None:
    line = _value(
        applied,
        "auth_service",
        "SELECT json_build_object('id', delivery_id, 'endpoint', endpoint, "
        "'rehearsal', rehearsal, 'attempt', attempt) "
        f"FROM app_private.connector_claim_delivery('{holder}', 30);",
    )
    return json.loads(line) if line else None


def _finish_delivery(applied: dict[str, Any], delivery: str, holder: str, error: str) -> str:
    return _value(
        applied,
        "auth_service",
        f"SELECT app_private.connector_finish_delivery('{delivery}', '{holder}', false, 500, '{error}');",  # noqa: E501
    )


def test_a_delivery_is_retried_to_max_then_dead(applied, fresh) -> None:
    event = _event()
    connector = _name("out")
    _outbound(applied, connector, event, endpoint="http://sink.test/fail", retry=1)
    _enable(applied, connector, None, fresh["owner"])
    _emit(applied, event, {"note_id": "x"}, user=fresh["owner"])

    holder = _name("holder")
    first = _claim_delivery(applied, holder)
    assert first is not None and first["attempt"] == 1
    assert first["endpoint"] == "http://sink.test/fail"
    assert _finish_delivery(applied, first["id"], "someone-else", "http_500") == "lease_lost"
    assert _finish_delivery(applied, first["id"], holder, "http_500") == "pending"
    assert _claim_delivery(applied, holder) is None, "claimed before its backoff"

    _scalar(
        applied,
        "UPDATE app_private.connector_delivery SET next_attempt_at = now() "
        f"WHERE id = '{first['id']}' RETURNING id;",
    )
    second = _claim_delivery(applied, holder)
    assert second is not None and second["id"] == first["id"] and second["attempt"] == 2
    assert _finish_delivery(applied, first["id"], holder, "http_500") == "dead"
    assert _claim_delivery(applied, holder) is None
    assert _refusal(
        applied,
        "auth_service",
        f"app_private.connector_finish_delivery('{first['id']}', '{holder}', false, 500, 'Internal Server Error')",  # noqa: E501
    ) == ("", "")  # the lease is gone, so the token is never read


def test_an_error_must_be_a_fixed_token(applied, fresh) -> None:
    event = _event()
    connector = _name("out")
    _outbound(applied, connector, event, endpoint="http://sink.test/fail")
    _enable(applied, connector, None, fresh["owner"])
    _emit(applied, event, {"note_id": "x"}, user=fresh["owner"])
    holder = _name("holder")
    claimed = _claim_delivery(applied, holder)
    assert claimed is not None
    assert _refusal(
        applied,
        "auth_service",
        f"app_private.connector_finish_delivery('{claimed['id']}', '{holder}', false, 500, 'Internal Server Error')",  # noqa: E501
    ) == ("PT422", "AP422: error_token_invalid")


def test_a_rehearsal_claim_never_returns_the_endpoint(applied, fresh) -> None:
    """Claimable while the connector is disabled, and addressed to nobody."""
    connector = _name("out")
    _outbound(applied, connector, _event(), endpoint="http://endpoint-canary.test/hook")
    made = _scalar(applied, f"SELECT app_private.connector_rehearse_delivery('{connector}');")
    claimed = _claim_delivery(applied, _name("holder"))
    assert claimed is not None and claimed["id"] == made
    assert claimed["rehearsal"] is True and claimed["endpoint"] is None
