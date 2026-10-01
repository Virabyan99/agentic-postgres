"""Migration 0037: approval enforced in the database (ADR 0242, AGT-APPROVE-003).

`app.require_approval(p_tool)` under a real cluster with every released
migration applied as `migration_user` (D285). The cluster fixture and its small
helpers are COPIED from `test_connectivity_substrate.py`, not imported, for
D386's reason: a reader must be able to tell whose fixture broke.

**What rig 35a measured before 0037 was written** (Session 35 Run 1, D1892,
through the REAL loop, plane and PostgREST on one `apg dev up` stack): the
approved step token's `apg_approval {id, key, tool}` arrives in
`current_setting('request.jwt.claims')` exactly as `step_token` minted it, and
the plane's `Idempotency-Key` arrives in `request.headers` as
`idempotency-key`, equal to the claim's key; a prototype of this guard refused
the agent's own token `403 {"code":"PT403", ..., "message":"AP403:
approval_required"}` with nothing written while an ungated twin served it; a
malformed key met `PT412` from `agent_idempotency_key()` first; no login or
request role could execute the guard. **These proofs set exactly those GUCs**
-- `request.jwt.claims`, `request.headers`, `app.agent_id` and `app.user_id`,
transaction local with `set_config(..., true)` inside ONE transaction as the
request role -- which is what PostgREST and the pre-request hook do, so no
token is forged and no stack is needed.

**The guard is reached the way a project reaches it**: a scratch definer RPC
created as the object owner, `api.s35_gated`, calls the REAL
`app.require_approval('s35_gated')` first and then writes one row. Every
refusal is asserted by its SQLSTATE and message AND by the row count, because a
refusal that wrote is not a refusal.

**The foreign-agent arm is D1893's**: rig 35a could not exercise
`r.agent_id = acting_agent` (its UPDATE was refused by a constraint); here a
SECOND agent presents the first agent's claim and key, and nothing is forged.

**Every call to a released function is ONE string literal** (D464): the arity
guard walks a call as written.
"""

from __future__ import annotations

# ruff: noqa: S608
#
# Every interpolated value below is a role or database name read from a rendered
# outputs document this repository produced, or a uuid / key this module
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

SCOPES = ["notes:read", "notes:write"]

#: The tool the scratch RPC is gated as. Any name: the guard compares strings.
TOOL = "s35_gated"

#: Migration 0037's version, which the `applied` fixture requires.
GATE_VERSION = "20261001120037"

#: The one sentence every refusal is (ADR 0242).
REFUSAL = ("PT403", "AP403: approval_required")

#: The run statuses that are not `running`, every one an ended or not-yet-
#: started run whose decision must not authorise a write.
NOT_RUNNING = ("queued", "succeeded", "failed", "cancelled", "stopped", "compensating")

ONE_STEP = {
    "timeout_seconds": 600,
    "steps": [
        {
            "name": "gated",
            "tool": TOOL,
            "capability": TOOL,
            "capability_version": "1.0.0",
            "resource": None,
            "kind": "write",
            "arguments": {"p_note": "{{input.note}}"},
            "retry": {"max": 0, "backoff_seconds": 5},
            "timeout_seconds": 30,
        }
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
    """`test_connectivity_substrate.py`'s cluster, copied: the locked image, the
    product's own role statements, and the same two skips."""
    if not (FIXTURE / "outputs.json").is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    if _docker("version", "--format", "{{.Server.Version}}", timeout=30).returncode != 0:
        pytest.skip("docker is not available")

    document = json.loads((FIXTURE / "outputs.json").read_text(encoding="utf-8"))
    roles = document["database"]["roles"]
    database = document["database"]["name"]
    password = secrets.token_hex(24)
    name = f"apg-approval-gate-{secrets.token_hex(4)}"

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


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _session(
    cluster: dict[str, Any],
    role_key: str,
    sql: str,
    *,
    user: str | None = None,
    agent: str | None = None,
    claim: Any = None,
    key: str | None = None,
) -> str:
    """One transaction as a request role, with the GUCs rig 35a read arriving.

    `app.user_id` and `app.agent_id` are what the pre-request hook sets;
    `request.jwt.claims` and `request.headers` are what PostgREST sets from the
    token and the request (0029 reads the header from the latter). All four are
    transaction local, set inside a `DO` block so they print nothing.
    """
    settings = []
    if user is not None:
        settings.append(f"PERFORM pg_catalog.set_config('app.user_id', '{user}', true);")
    if agent is not None:
        settings.append(f"PERFORM pg_catalog.set_config('app.agent_id', '{agent}', true);")
    claims: dict[str, Any] = {"role": cluster["roles"][role_key]}
    if claim is not None:
        claims["apg_approval"] = claim
    settings.append(
        "PERFORM pg_catalog.set_config('request.jwt.claims', "
        f"{_literal(json.dumps(claims))}, true);"
    )
    headers = {} if key is None else {"idempotency-key": key}
    settings.append(
        f"PERFORM pg_catalog.set_config('request.headers', {_literal(json.dumps(headers))}, true);"
    )
    return "\n".join(
        [
            "BEGIN;",
            f'SET LOCAL ROLE "{cluster["roles"][role_key]}";',
            "DO $gucs$ BEGIN " + " ".join(settings) + " END $gucs$;",
            sql,
            "COMMIT;",
        ]
    )


def _call(cluster: dict[str, Any], role_key: str, note: str, **gucs: Any) -> tuple[str, str]:
    """`(sqlstate, message)` of the refusal the gated RPC meets, `("", "")` when served."""
    block = (
        "DO $refusal$ BEGIN "
        f"PERFORM api.s35_gated({_literal(note)}); "
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


def _written(cluster: dict[str, Any], note: str) -> int:
    return int(_scalar(cluster, f"SELECT count(*) FROM app.s35_gated_rows WHERE note = '{note}';"))


@pytest.fixture(scope="module")
def applied(cluster: dict[str, Any]) -> dict[str, Any]:
    """Every released migration applied as `migration_user`, 0037 included."""
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
    assert GATE_VERSION in applied_versions, applied_versions[-3:]
    return {"versions": applied_versions, **cluster}


@pytest.fixture(scope="module")
def people(applied: dict[str, Any]) -> dict[str, str]:
    """An owner, a second person who decides, two writer agents of the owner,
    the definition, and the scratch gated RPC in a project's shape."""
    scopes = ", ".join(f"'{scope}'" for scope in SCOPES)
    owner = _scalar(
        applied,
        "SELECT app_private.auth_create_user('gate-owner', 'gate-owner', 'authenticated', "
        f"ARRAY[{scopes}]::text[], '{STORED_HASH}');",
    )
    decider = _scalar(
        applied,
        "SELECT app_private.auth_create_user('gate-decider', 'gate-decider', 'authenticated', "
        f"ARRAY[{scopes}]::text[], '{STORED_HASH}');",
    )
    writer = applied["roles"]["agent_writer"]
    agent = _scalar(
        applied,
        f"SELECT app_private.auth_create_agent('gate-agent', '', '{writer}', ARRAY[{scopes}], '{owner}', '{STORED_HASH}', NULL);",  # noqa: E501
    )
    stranger = _scalar(
        applied,
        f"SELECT app_private.auth_create_agent('gate-stranger', '', '{writer}', ARRAY[{scopes}], '{owner}', '{STORED_HASH}', NULL);",  # noqa: E501
    )
    installed = _superuser(
        applied,
        f"SELECT app_private.workflow_install_definition('gated', 1, '{json.dumps(ONE_STEP)}'::jsonb, '{'a' * 64}', '{'b' * 64}', ARRAY['notes:write']);",  # noqa: E501
    )
    assert installed.returncode == 0, installed.stderr

    roles = applied["roles"]
    made = _superuser(
        applied,
        f'SET ROLE "{roles["object_owner"]}";\n'
        "CREATE TABLE app.s35_gated_rows (id bigserial PRIMARY KEY, note text NOT NULL);\n"
        "CREATE FUNCTION api.s35_gated(p_note text)\n"
        "  RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp\n"
        "AS $fn$\n"
        "DECLARE written bigint;\n"
        "BEGIN\n"
        f"  PERFORM app.require_approval('{TOOL}');\n"
        "  INSERT INTO app.s35_gated_rows (note) VALUES (p_note) RETURNING id INTO written;\n"
        "  RETURN written;\n"
        "END $fn$;\n"
        "REVOKE ALL ON FUNCTION api.s35_gated(text) FROM PUBLIC;\n"
        "GRANT EXECUTE ON FUNCTION api.s35_gated(text) "
        f'TO "{roles["authenticated"]}", "{roles["agent_writer"]}";\n'
        "RESET ROLE;",
    )
    assert made.returncode == 0, made.stderr
    return {"owner": owner, "decider": decider, "agent": agent, "stranger": stranger}


def _decision(
    applied: dict[str, Any],
    people: dict[str, str],
    *,
    tool: str = TOOL,
    status: str = "approved",
    run_status: str = "running",
) -> dict[str, Any]:
    """A run of `people["agent"]` with one parked step and its decision.

    Written as the superuser, because the decision's own functions are the
    workflow proofs' subject and this module's is the guard. Returns the claim
    `step_token` would mint for it and the key the plane would send.
    """
    key = f"s35-{secrets.token_hex(8)}"
    decided = status in ("approved", "rejected")
    approval = _scalar(
        applied,
        "WITH run AS (\n"
        "  INSERT INTO app_private.workflow_run (definition_id, agent_id, owner_id, status,"
        " timeout_seconds, started_at)\n"
        "  SELECT d.id, '{agent}', '{owner}', '{run_status}', 600, now()\n"
        "    FROM app_private.workflow_definition d WHERE d.name = 'gated' AND d.version = 1\n"
        "  RETURNING id\n"
        "), step AS (\n"
        "  INSERT INTO app_private.workflow_step (run_id, position, name, status, retry_max,"
        " backoff_seconds, timeout_seconds, idempotency_key)\n"
        "  SELECT id, 1, 'gated', 'parked', 0, 5, 30, '{key}' FROM run\n"
        "  RETURNING id, run_id\n"
        ")\n"
        "INSERT INTO app_private.workflow_approval (run_id, step_id, tool, capability,"
        " idempotency_key, expires_at, status, decided_by, decided_at)\n"
        "SELECT run_id, id, '{tool}', '{tool}@1.0.0', '{key}', now() + interval '1 hour',"
        " '{status}', {decided_by}, {decided_at} FROM step\n"
        "RETURNING id;".format(
            agent=people["agent"],
            owner=people["owner"],
            run_status=run_status,
            key=key,
            tool=tool,
            status=status,
            decided_by=f"'{people['decider']}'" if decided else "NULL",
            decided_at="now()" if decided else "NULL",
        ),
    )
    uuid.UUID(approval)
    return {"claim": {"id": approval, "tool": TOOL, "key": key}, "key": key, "id": approval}


def _note() -> str:
    return f"note-{secrets.token_hex(4)}"


def _agent_call(applied, people, note: str, *, agent: str | None = None, **gucs) -> tuple:
    return _call(
        applied,
        "agent_writer",
        note,
        user=people["owner"],
        agent=agent or people["agent"],
        **gucs,
    )


# ---------------------------------------------------------------------------
# Who may call the guard
# ---------------------------------------------------------------------------


def test_require_approval_is_executable_by_no_role(applied: dict[str, Any], people) -> None:
    """Granted to nobody, measured on the FUNCTION and not only the schema (D1814).

    A request role calling it meets `42501` at the `app` schema first (rig
    35a), which would survive a function granted to PUBLIC or to a role -- so
    the proof reads the function's own privilege for every role in the
    document but its owner, and its ACL.
    """
    signature = "app.require_approval(text)"
    roles = applied["roles"]
    checked = 0
    for role_key, role in sorted(roles.items()):
        if role_key == "object_owner":
            continue
        got = _scalar(
            applied, f"SELECT has_function_privilege('{role}', '{signature}', 'EXECUTE');"
        )
        assert got == "f", f"{role_key} may execute the guard"
        checked += 1
    assert checked >= 12, f"only {checked} role(s) were read"
    grantees = _scalar(
        applied,
        "SELECT coalesce(string_agg(a.grantee::regrole::text, ','), '') FROM pg_proc p, "
        f"aclexplode(p.proacl) a WHERE p.oid = '{signature}'::regprocedure "
        "AND a.privilege_type = 'EXECUTE';",
    )
    assert grantees == roles["object_owner"], grantees
    assert (
        _scalar(applied, f"SELECT prosecdef FROM pg_proc WHERE oid = '{signature}'::regprocedure;")
        == "t"
    ), "the guard is not SECURITY DEFINER, so it cannot read app_private as the caller"

    for role_key in ("authenticated", "agent_writer", "auth_service", "anon"):
        block = (
            "DO $direct$ BEGIN "
            f"PERFORM app.require_approval('{TOOL}'); "
            "RAISE NOTICE 'direct=|'; "
            "EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'direct=%|%', SQLSTATE, SQLERRM; "
            "END $direct$;"
        )
        result = _superuser(applied, _session(applied, role_key, block, user=people["owner"]))
        assert result.returncode == 0, result.stderr[:600]
        found = re.search(r"direct=([^|\n]*)\|", result.stderr)
        assert found and found.group(1) == "42501", (role_key, result.stderr[:300])


def test_a_caller_with_no_agent_identity_passes(applied, people) -> None:
    """A PERSON's own write passes: no `app.agent_id`, no claim, no key (ADR 0242).

    The control for every refusal below: the same RPC, the same role family,
    served and writing one row.
    """
    note = _note()
    assert _call(applied, "authenticated", note, user=people["owner"]) == ("", "")
    assert _written(applied, note) == 1


# ---------------------------------------------------------------------------
# What an agent needs
# ---------------------------------------------------------------------------


def test_an_agent_without_a_claim_is_refused_and_nothing_is_written(applied, people) -> None:
    """The agent's OWN token: no `apg_approval`, with and without a key (D1721)."""
    for key in (None, f"s35-{secrets.token_hex(8)}"):
        note = _note()
        assert _agent_call(applied, people, note, key=key) == REFUSAL, key
        assert _written(applied, note) == 0, key

    # A claim that is not an object is no claim.
    note = _note()
    key = f"s35-{secrets.token_hex(8)}"
    assert _agent_call(applied, people, note, claim="approved", key=key) == REFUSAL
    assert _written(applied, note) == 0


def test_a_claim_for_another_tool_is_refused(applied, people) -> None:
    """The claim names another tool; and -- the arm M4 needs -- the claim names
    THIS tool while the decision row names another."""
    decision = _decision(applied, people)
    claim = {**decision["claim"], "tool": "another_tool"}
    note = _note()
    assert _agent_call(applied, people, note, claim=claim, key=decision["key"]) == REFUSAL
    assert _written(applied, note) == 0

    elsewhere = _decision(applied, people, tool="another_tool")
    note = _note()
    assert (
        _agent_call(applied, people, note, claim=elsewhere["claim"], key=elsewhere["key"])
        == REFUSAL
    ), "a decision for another tool authorised this one"
    assert _written(applied, note) == 0


def test_a_key_that_differs_from_the_header_is_refused(applied, people) -> None:
    """The claim's key against the request's header (ADR 0231 binds one write).

    Three arms: no header; a header that differs from the claim and the row;
    and the informative one -- the claim says K1 while the header AND the
    decision row say K2, which only the claim-to-header comparison refuses.
    A malformed header is `agent_idempotency_key()`'s own `PT412`, before the
    guard decides (rig 35a).
    """
    decision = _decision(applied, people)

    note = _note()
    assert _agent_call(applied, people, note, claim=decision["claim"]) == REFUSAL
    assert _written(applied, note) == 0

    note = _note()
    other = f"s35-{secrets.token_hex(8)}"
    assert _agent_call(applied, people, note, claim=decision["claim"], key=other) == REFUSAL
    assert _written(applied, note) == 0

    row_key = _decision(applied, people)
    claim = {**row_key["claim"], "key": f"s35-{secrets.token_hex(8)}"}
    note = _note()
    assert _agent_call(applied, people, note, claim=claim, key=row_key["key"]) == REFUSAL, (
        "a claim whose key differs from the header was honoured because the row's matched"
    )
    assert _written(applied, note) == 0

    note = _note()
    sqlstate, _ = _agent_call(applied, people, note, claim=decision["claim"], key="short")
    assert sqlstate == "PT412", sqlstate
    assert _written(applied, note) == 0


def test_a_pending_rejected_expired_or_foreign_decision_is_refused(applied, people) -> None:
    """Only an `approved` decision, and only for the run's OWN agent (D1893).

    The foreign arm: a SECOND agent of the same owner presents the first
    agent's claim and key, exactly as minted. Rig 35a could not reach this
    member; here nothing is forged and nothing else differs.
    """
    for status in ("pending", "rejected", "expired"):
        decision = _decision(applied, people, status=status)
        note = _note()
        assert (
            _agent_call(applied, people, note, claim=decision["claim"], key=decision["key"])
            == REFUSAL
        ), status
        assert _written(applied, note) == 0, status

    decision = _decision(applied, people)
    note = _note()
    assert (
        _agent_call(
            applied,
            people,
            note,
            agent=people["stranger"],
            claim=decision["claim"],
            key=decision["key"],
        )
        == REFUSAL
    ), "another agent's approved decision authorised this agent"
    assert _written(applied, note) == 0

    # The same decision, presented by its own agent, is served: the arm above
    # differed in the agent alone.
    note = _note()
    assert _agent_call(applied, people, note, claim=decision["claim"], key=decision["key"]) == (
        "",
        "",
    )
    assert _written(applied, note) == 1


def test_a_decision_on_an_ended_run_is_refused(applied, people) -> None:
    """An approved decision authorises a write only while its run is `running`."""
    for run_status in NOT_RUNNING:
        decision = _decision(applied, people, run_status=run_status)
        note = _note()
        assert (
            _agent_call(applied, people, note, claim=decision["claim"], key=decision["key"])
            == REFUSAL
        ), run_status
        assert _written(applied, note) == 0, run_status


def test_an_approved_claim_on_a_running_run_passes(applied, people) -> None:
    """The approved path: the claim, its key in the header, the agent's own run.

    And D1871, stated rather than discovered: the guard does not consume the
    decision, so the same claim and key are served twice and the scratch RPC,
    which has no idempotency of its own, writes twice.
    """
    decision = _decision(applied, people)
    note = _note()
    for expected in (1, 2):
        assert _agent_call(applied, people, note, claim=decision["claim"], key=decision["key"]) == (
            "",
            "",
        )
        assert _written(applied, note) == expected


def test_every_refusal_is_one_sentence(applied, people) -> None:
    """Six causes, one answer: `PT403`, `AP403: approval_required`, nothing else.

    The message never says which member failed, so a caller probing the guard
    learns nothing from the answer it gets (ADR 0242).
    """
    approved = _decision(applied, people)
    rejected = _decision(applied, people, status="rejected")
    ended = _decision(applied, people, run_status="succeeded")
    causes = {
        "no_claim": {"key": approved["key"]},
        "another_tool": {"claim": {**approved["claim"], "tool": "x"}, "key": approved["key"]},
        "another_key": {"claim": approved["claim"], "key": f"s35-{secrets.token_hex(8)}"},
        "no_key": {"claim": approved["claim"]},
        "not_approved": {"claim": rejected["claim"], "key": rejected["key"]},
        "ended_run": {"claim": ended["claim"], "key": ended["key"]},
    }
    answers = {}
    for cause, gucs in causes.items():
        note = _note()
        answers[cause] = _agent_call(applied, people, note, **gucs)
        assert _written(applied, note) == 0, cause
    assert answers == dict.fromkeys(causes, REFUSAL), answers
