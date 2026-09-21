"""Migration 0034: the durable step substrate, under a real cluster (WF-STATE-001).

**Applied as `migration_user`, never as a superuser**, for D285's reason. Every
offline rig that applies migrations as `postgres` bypasses the ownership check
that made the first Session 6 host deploy fail, and this module exists in the
class of proofs that refuses to do that. The cluster fixture is
`test_migrations_apply_as_the_migration_user.py:95-163`'s recipe -- a `docker
run -d` of the locked `POSTGRES_IMAGE`, two consecutive `pg_isready`, and the
PRODUCT's own `dev_environment` statements -- rather than `apg dev`, because
this module needs a cluster a script established.

**What the rigs measured before a line of this file was written** (Session 32
Run 1, ADR 0227):

* rig 32d: a no-grant `app_private` table behind a definer function granted to
  `auth_service` is readable by that function and by nothing else, and the SAME
  table under `FORCE ROW LEVEL SECURITY` with no policy returns **zero rows and
  exits 0** -- silently, in the reassuring direction. That control is why the
  four tables below carry no RLS (D1647).
* rig 32e: the LEASE PREDICATE is the correctness mechanism and `SKIP LOCKED` is
  throughput; a holder inside an open transaction is skipped, an unexpired lease
  is not taken, an expired one is reclaimed with the attempt incremented, and a
  late finish scoped to the old holder updates zero rows. The control without
  the predicate loses the row thirty seconds into a thirty-second lease.
* rig 32e also measured that `pg_catalog.now()` is the TRANSACTION START time,
  which is why the lease timings below sleep past a short lease rather than
  holding a transaction open.

**`has_*_privilege()::text` renders the WORDS `true`/`false` under `psql -qtA`,
never `t`/`f`** -- measured in rig 32d, after this module's first draft of those
assertions would have failed on first execution (section 7 question 2).
"""

from __future__ import annotations

# ruff: noqa: S608
#
# Every interpolated value below is a role or database name read from a rendered
# outputs document this repository produced, validated by the outputs schema.
# None of it is caller input, and a role name cannot be bound as a parameter.
import json
import secrets
import subprocess
import time
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

#: A hash the `agent_credentials` CHECK accepts. Not a credential: it is the
#: literal `test_storage_plane.py:193` uses, and no secret verifies against it.
STORED_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$aGFzaA"

#: A compiled definition body, shaped the way `workflow_definition.compile`
#: emits one. Written here rather than compiled, because this module is about
#: the SUBSTRATE: the compiler has its own module and its own proofs, and a
#: fixture that ran the compiler would make a failure here ambiguous between the
#: two.
BODY = {
    "timeout_seconds": 600,
    "steps": [
        {
            "name": "first",
            "tool": "create_note",
            "capability": "create_note",
            "capability_version": "1.0.0",
            "kind": "write",
            "arguments": {"p_title": "one"},
            "retry": {"max": 1, "backoff_seconds": 5},
            "timeout_seconds": 30,
        },
        {
            "name": "second",
            "tool": "query_resource",
            "capability": "query_notes",
            "capability_version": "1.0.0",
            "kind": "read",
            "arguments": {"resource": "notes", "limit": 5},
            "retry": {"max": 0, "backoff_seconds": 5},
            "timeout_seconds": 30,
        },
    ],
}

#: The run input, as one token so the enqueue call fits on ONE LINE.
#:
#: `test_every_call_to_a_released_function_uses_a_released_arity` walks the
#: parentheses of the CALL AS WRITTEN (D464: a text scan standing in for a
#: construct), and a call split across two Python string literals broke its walk
#: -- it read four arguments where five are passed. The repair is to write the
#: call so the guard can read it, never to except this module from the guard.
INPUT = '\'{"title": "canary"}\'::jsonb'

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64


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
    """A cluster on the locked image with every RELEASED migration applied.

    The two skips are `test_migrations_apply_as_the_migration_user.py`'s and
    mean the same things: no rendered fixture, and no Docker.
    """
    if not (FIXTURE / "outputs.json").is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    if _docker("version", "--format", "{{.Server.Version}}", timeout=30).returncode != 0:
        pytest.skip("docker is not available")

    document = json.loads((FIXTURE / "outputs.json").read_text(encoding="utf-8"))
    roles = document["database"]["roles"]
    database = document["database"]["name"]
    password = secrets.token_hex(24)
    name = f"apg-workflow-substrate-{secrets.token_hex(4)}"

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
    """One migration, over TCP as the migration user, in one transaction.

    Over TCP with a password rather than `-U role` on the socket, because the
    socket would use peer authentication as root and could connect as a role
    this test has not established a password for.
    """
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
    """Every released migration applied as `migration_user`, 0034 included.

    A FUNCTION-scoped assertion inside a module-scoped fixture would be reported
    as an ERROR rather than a FAILED, and a reader that cannot tell the two apart
    reports a broken fixture as a kill (D386). So the fixture raises with the
    migration's own stderr, and the first test below asserts the count.
    """
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
    return {"versions": applied_versions, **cluster}


# ---------------------------------------------------------------------------
# the migration itself
# ---------------------------------------------------------------------------


def test_the_migration_applies_as_the_migration_user_and_its_down_refuses(
    applied: dict[str, Any],
) -> None:
    """0034 applies as the role a deploy connects with, and its down is AP900.

    The down block is applied on its own rather than being reasoned about: a
    refusal nobody has executed is a refusal nobody has measured.
    """
    assert "20260917120034" in applied["versions"], applied["versions"][-3:]
    assert len(applied["versions"]) == 34, len(applied["versions"])

    template = (REPO_ROOT / "migrations" / "templates" / "0034-workflow-substrate.sql").read_text(
        encoding="utf-8"
    )
    down = template.split("-- migrate:down", 1)[1]
    values = {
        "object_owner": applied["roles"]["object_owner"],
        "auth_service": applied["roles"]["auth_service"],
    }
    result = _apply_as_migration_user(applied, migrations.render(down, values))
    assert result.returncode != 0, "the down block did not refuse"
    assert "AP900" in result.stderr, result.stderr[:400]


def test_no_role_holds_a_privilege_on_the_four_tables(applied: dict[str, Any]) -> None:
    """The posture, and it is the whole of the access control (D1647, rig 32d).

    `app_private` tables are protected by *no request role holds any table
    privilege*, not by RLS. `anon` is the control the audit plane's own privilege
    proof uses: a role that should hold nothing anywhere.
    """
    offenders: list[str] = []
    for role_key in (
        "auth_service",
        "agent_writer",
        "agent_reader",
        "authenticated",
        "anon",
        "storage_service",
        "app_runtime",
    ):
        role = applied["roles"][role_key]
        for table in ("workflow_definition", "workflow_run", "workflow_step", "workflow_worker"):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                got = _scalar(
                    applied,
                    f"SELECT has_table_privilege('{role}', "
                    f"'app_private.{table}', '{privilege}')::text;",
                )
                if got != "false":
                    offenders.append(f"{role_key} holds {privilege} on {table}")
    assert not offenders, offenders


def test_the_four_tables_carry_no_row_level_security(applied: dict[str, Any]) -> None:
    """Refused deliberately, and the rig measured why (D1647).

    FORCE RLS applies to the OWNER, which is the role every definer function
    here runs as -- rig 32d measured a forced `app_private` table with no policy
    returning ZERO ROWS and exiting 0 to its own definer function. It fails
    silently, in the reassuring direction. This asserts the tree's actual
    posture rather than the stage plan's sentence.
    """
    reading = _scalar(
        applied,
        "SELECT string_agg(relname || ':' || relrowsecurity::text || ':' "
        "|| relforcerowsecurity::text, ' ' ORDER BY relname) "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'app_private' AND c.relkind = 'r' "
        "AND c.relname LIKE 'workflow%';",
    )
    assert reading == (
        "workflow_definition:false:false workflow_run:false:false "
        "workflow_step:false:false workflow_worker:false:false"
    ), reading


def test_the_eight_functions_are_executable_by_the_auth_service_role_and_nobody_else(
    applied: dict[str, Any],
) -> None:
    """The grant, and the four roles that must not have it.

    `anon` is the control (`test_agent_audit_plane.py:1355`'s): a role that holds
    nothing anywhere, so a `true` for it would mean the REVOKE never ran rather
    than that this grant is wrong.
    """
    signatures = {
        "workflow_enqueue": "uuid, text, integer, jsonb, boolean",
        "workflow_claim_step": "text, integer",
        "workflow_finish_step": "uuid, text, app_private.workflow_step_outcome, jsonb, text",
        "workflow_park": "uuid, text, text, timestamptz",
        "workflow_cancel": "uuid, uuid",
        "workflow_run_status": "uuid, uuid",
        "workflow_heartbeat": "text",
        "workflow_counts": "",
    }
    auth = applied["roles"]["auth_service"]
    for function, signature in signatures.items():
        granted = _scalar(
            applied,
            f"SELECT has_function_privilege('{auth}', "
            f"'app_private.{function}({signature})', 'EXECUTE')::text;",
        )
        assert granted == "true", f"auth_service cannot execute {function}: {granted!r}"

    for role_key in ("agent_writer", "agent_reader", "authenticated", "anon", "storage_service"):
        role = applied["roles"][role_key]
        for function, signature in signatures.items():
            granted = _scalar(
                applied,
                f"SELECT has_function_privilege('{role}', "
                f"'app_private.{function}({signature})', 'EXECUTE')::text;",
            )
            assert granted == "false", f"{role_key} can execute {function}"


def test_install_is_executable_by_nobody(applied: dict[str, Any]) -> None:
    """0033's pattern, and the absence IS the decision (ADR 0228).

    A grant to `auth_service` -- the role the HTTP routes run as -- would put a
    definition-writing authority behind an identity reachable over the network,
    which is 0020's reason for keeping a DELETE out of the audit reader.
    """
    for role_key in (
        "auth_service",
        "agent_writer",
        "agent_reader",
        "authenticated",
        "anon",
        "storage_service",
        "app_runtime",
        "project_admin",
    ):
        role = applied["roles"][role_key]
        granted = _scalar(
            applied,
            f"SELECT has_function_privilege('{role}', 'app_private."
            "workflow_install_definition(text, integer, jsonb, text, text, text[])', "
            "'EXECUTE')::text;",
        )
        assert granted == "false", f"{role_key} can install a definition"


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


def _install(applied: dict[str, Any], name: str, version: int, source: str = DIGEST_A):
    return _superuser(
        applied,
        "SELECT app_private.workflow_install_definition("
        f"'{name}', {version}, '{json.dumps(BODY)}'::jsonb, "
        f"'{source}', '{DIGEST_B}', ARRAY['notes:read','notes:write']);",
    )


def test_install_refuses_a_different_body_under_the_same_name_and_version(
    applied: dict[str, Any],
) -> None:
    """Immutable per (name, version), and idempotent for an identical source.

    Both halves matter: a deploy re-run must not be a conflict, and a changed
    definition under an unchanged version must be. That is D912's rule for a
    migration, applied to a definition.
    """
    first = _install(applied, "immutability", 1)
    assert first.returncode == 0, first.stderr
    identifier = first.stdout.strip().splitlines()[-1]

    again = _install(applied, "immutability", 1)
    assert again.returncode == 0, again.stderr
    assert again.stdout.strip().splitlines()[-1] == identifier, "a re-install minted a new id"

    changed = _install(applied, "immutability", 1, source=DIGEST_C)
    assert changed.returncode != 0, "a different source was accepted"
    assert "AP409" in changed.stderr, changed.stderr[:300]

    later = _install(applied, "immutability", 2)
    assert later.returncode == 0, "fixing forward under a new version was refused"


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def agents(applied: dict[str, Any]) -> dict[str, str]:
    """One agent holding both scopes and one holding only the read.

    Created through `app_private.auth_create_user` and `auth_create_agent` --
    the PRODUCT's own functions -- rather than by an INSERT written here: the
    owner column is a foreign key, and a subject this module invented would be
    an identity the deployment has never heard of (D313).
    """
    owner = _scalar(
        applied,
        "SELECT app_private.auth_create_user('wf-owner', 'wf-owner', 'authenticated', "
        f"ARRAY['notes:read','notes:write']::text[], '{STORED_HASH}');",
    )
    wide = _scalar(
        applied,
        "SELECT app_private.auth_create_agent('wf-wide', '', "
        f"'{applied['roles']['agent_writer']}', ARRAY['notes:read','notes:write'], "
        f"'{owner}', '{STORED_HASH}', NULL);",
    )
    narrow = _scalar(
        applied,
        "SELECT app_private.auth_create_agent('wf-narrow', '', "
        f"'{applied['roles']['agent_reader']}', ARRAY['notes:read'], "
        f"'{owner}', '{STORED_HASH}', NULL);",
    )
    return {"owner": owner, "wide": wide, "narrow": narrow}


def _enqueue(applied: dict[str, Any], agent: str, name: str, version: int = 1):
    sql = f"SELECT app_private.workflow_enqueue('{agent}', '{name}', {version}, {INPUT}, false);"
    return _as_role(applied, applied["roles"]["auth_service"], sql)


def test_enqueue_refuses_an_agent_missing_a_required_scope_and_admits_one_holding_them(
    applied: dict[str, Any], agents: dict[str, str]
) -> None:
    """The agent's STORED scopes authorise the run, not the token's (ADR 0229).

    The wide agent is the control: the same definition, the same call, admitted
    -- so the refusal is about the scopes and not about the definition or the
    role the call is made as.
    """
    assert _install(applied, "scope-check", 1).returncode == 0

    refused = _enqueue(applied, agents["narrow"], "scope-check")
    assert refused.returncode != 0, "an agent missing a scope was admitted"
    assert "scope_not_held" in refused.stderr, refused.stderr[:300]

    admitted = _enqueue(applied, agents["wide"], "scope-check")
    assert admitted.returncode == 0, admitted.stderr[:300]


def test_enqueue_refuses_an_unknown_definition_and_an_inactive_agent(
    applied: dict[str, Any], agents: dict[str, str]
) -> None:
    """`no such definition` is the message the route maps to a 404.

    A revoked agent and an unknown one are ONE refusal, for 0013's reason: an
    agent that has been revoked must not be distinguishable from one that never
    existed.
    """
    missing = _enqueue(applied, agents["wide"], "no-such-definition-here")
    assert missing.returncode != 0
    assert "no such definition" in missing.stderr, missing.stderr[:300]

    assert _install(applied, "revocation-check", 1).returncode == 0
    revoked = _scalar(
        applied,
        "SELECT app_private.auth_create_agent('wf-revoked', '', "
        f"'{applied['roles']['agent_writer']}', ARRAY['notes:read','notes:write'], "
        f"'{agents['owner']}', '{STORED_HASH}', NULL);",
    )
    _superuser(
        applied,
        f"SELECT app_private.auth_set_agent_status('{revoked}', 'revoked');",
    )
    stopped = _enqueue(applied, revoked, "revocation-check")
    assert stopped.returncode != 0, "a revoked agent enqueued a run"
    assert "AP403" in stopped.stderr, stopped.stderr[:300]

    unknown = _enqueue(applied, "00000000-0000-4000-8000-000000000000", "revocation-check")
    assert unknown.returncode != 0
    assert "AP403" in unknown.stderr, "an unknown agent is distinguishable from a revoked one"


def test_enqueue_derives_one_key_per_step_inside_the_pattern(
    applied: dict[str, Any], agents: dict[str, str]
) -> None:
    """One key per (run, step), never per attempt (D1646, ADR 0181).

    The keys are asserted to be DERIVED FROM THE RUN as well as the step: two
    runs of the same definition must not share a key, or the second run would
    replay the first's writes.
    """
    assert _install(applied, "key-shape", 1).returncode == 0
    first = _enqueue(applied, agents["wide"], "key-shape")
    second = _enqueue(applied, agents["wide"], "key-shape")
    assert first.returncode == 0 and second.returncode == 0
    first_run = first.stdout.strip().splitlines()[-1]
    second_run = second.stdout.strip().splitlines()[-1]

    keys = _scalar(
        applied,
        "SELECT string_agg(name || '=' || idempotency_key, ' ' ORDER BY position) "
        f"FROM app_private.workflow_step WHERE run_id = '{first_run}';",
    )
    assert keys == f"first=wf-{first_run}-first second=wf-{first_run}-second", keys

    other = _scalar(
        applied,
        "SELECT string_agg(idempotency_key, ' ' ORDER BY position) "
        f"FROM app_private.workflow_step WHERE run_id = '{second_run}';",
    )
    assert first_run not in other, "two runs of one definition share a key"

    # The shape 0029's header parser enforces, asserted by the DATABASE rather
    # than by a regex written here: a key the CHECK would reject cannot be in
    # the table at all, so this asserts the CHECK is the one 0029 uses.
    mismatched = _scalar(
        applied,
        "SELECT count(*)::text FROM app_private.workflow_step "
        "WHERE idempotency_key !~ '^[\\x21-\\x7e]{8,255}$';",
    )
    assert mismatched == "0", mismatched


# ---------------------------------------------------------------------------
# claim, finish, park
# ---------------------------------------------------------------------------


def _claim(applied: dict[str, Any], holder: str, lease: int = 60):
    return _as_role(
        applied,
        applied["roles"]["auth_service"],
        f"SELECT * FROM app_private.workflow_claim_step('{holder}', {lease});",
    )


@pytest.fixture
def run_id(applied: dict[str, Any], agents: dict[str, str]) -> str:
    """A fresh two-step run, and every OTHER run finished off first.

    The claim is global by design -- it takes the oldest claimable step on the
    node -- so a test that left a run behind would hand the next test somebody
    else's step. Finishing them here rather than in a teardown means a failure
    reports itself in the test that caused it.
    """
    _superuser(
        applied,
        "UPDATE app_private.workflow_run SET status = 'cancelled', "
        "finished_at = now() WHERE status IN ('queued', 'running');",
    )
    name = f"claim-{secrets.token_hex(3)}"
    assert _install(applied, name, 1).returncode == 0
    enqueued = _enqueue(applied, agents["wide"], name)
    assert enqueued.returncode == 0, enqueued.stderr[:300]
    return enqueued.stdout.strip().splitlines()[-1]


def test_claim_returns_the_lowest_unfinished_step_once_and_leases_it(
    applied: dict[str, Any], run_id: str
) -> None:
    """One claim, one step, and the second claimant gets nothing (rig 32e).

    The lease predicate is what makes the second claim empty -- not the row
    lock, which was released when the first claim committed. Rig 32e's control
    measured the difference: without the predicate the second claimant takes the
    row immediately.
    """
    first = _claim(applied, "A")
    assert first.returncode == 0, first.stderr
    columns = first.stdout.strip().splitlines()[-1].split("|")
    assert columns[2] == "1", f"claimed position {columns[2]}, not the first"
    assert columns[3] == "first", columns[3]
    assert columns[4] == "1", f"attempt is {columns[4]}, not 1"

    second = _claim(applied, "B")
    assert second.returncode == 0, second.stderr
    assert second.stdout.strip() == "", "a second holder claimed a leased step"

    state = _scalar(
        applied,
        "SELECT status || ' ' || claimed_by || ' ' || (lease_until > now())::text "
        f"FROM app_private.workflow_step WHERE run_id = '{run_id}' AND position = 1;",
    )
    assert state == "claimed A true", state

    run_state = _scalar(
        applied, f"SELECT status::text FROM app_private.workflow_run WHERE id = '{run_id}';"
    )
    assert run_state == "running", run_state


def test_an_expired_lease_is_reclaimed_with_the_attempt_incremented(
    applied: dict[str, Any], run_id: str
) -> None:
    """Rig 32e's third arm, as a proof: two seconds of lease, three of sleep.

    The sleep is real time and not a held transaction, because
    `pg_catalog.now()` is the TRANSACTION START time -- rig 32e's first pass
    held a transaction open and expired its own lease by doing so.
    """
    first = _claim(applied, "A", lease=2)
    assert first.stdout.strip(), first.stderr
    time.sleep(3)

    reclaimed = _claim(applied, "B", lease=60)
    assert reclaimed.stdout.strip(), "an expired lease was not reclaimed"
    columns = reclaimed.stdout.strip().splitlines()[-1].split("|")
    assert columns[4] == "2", f"attempt is {columns[4]}, not 2"

    holder = _scalar(
        applied,
        "SELECT claimed_by FROM app_private.workflow_step "
        f"WHERE run_id = '{run_id}' AND position = 1;",
    )
    assert holder == "B", holder


def test_finish_by_a_holder_that_lost_its_lease_is_refused(
    applied: dict[str, Any], run_id: str
) -> None:
    """`lease_lost` is a fact, not an error (0016's rule, one plane over).

    The work happened and a successor holds the row. Raising would report a
    failure that did not occur; returning `succeeded` would mark a step done
    that another worker is still doing.
    """
    claimed = _claim(applied, "A")
    step = claimed.stdout.strip().splitlines()[-1].split("|")[0]

    lost = _as_role(
        applied,
        applied["roles"]["auth_service"],
        f"SELECT app_private.workflow_finish_step('{step}', 'B', 'succeeded', NULL, NULL);",
    )
    assert lost.stdout.strip().splitlines()[-1] == "lease_lost", lost.stdout or lost.stderr

    unchanged = _scalar(
        applied,
        f"SELECT status::text FROM app_private.workflow_step WHERE id = '{step}';",
    )
    assert unchanged == "claimed", "a lost-lease finish moved the step anyway"

    kept = _as_role(
        applied,
        applied["roles"]["auth_service"],
        f"SELECT app_private.workflow_finish_step('{step}', 'A', 'succeeded', "
        "'{\"row\": 1}'::jsonb, NULL);",
    )
    assert kept.stdout.strip().splitlines()[-1] == "running", kept.stdout or kept.stderr


def test_park_defers_a_step_until_its_resume_time(applied: dict[str, Any], run_id: str) -> None:
    """Park IS the backoff and a parked step IS the pause (ADR 0227).

    A parked step is invisible to a claim until its time, and the claim then
    takes it with the attempt already incremented -- which is what makes a retry
    cost nothing but a claim.
    """
    claimed = _claim(applied, "A")
    step = claimed.stdout.strip().splitlines()[-1].split("|")[0]

    parked = _as_role(
        applied,
        applied["roles"]["auth_service"],
        f"SELECT app_private.workflow_park('{step}', 'A', 'write_conflict', "
        "now() + interval '30 seconds');",
    )
    assert parked.stdout.strip().splitlines()[-1] == "parked", parked.stdout or parked.stderr

    blocked = _claim(applied, "B")
    assert blocked.stdout.strip() == "", "a parked step was claimed before its time"

    state = _scalar(
        applied,
        "SELECT status::text || ' ' || (claimed_by IS NULL)::text || ' ' || reason "
        f"FROM app_private.workflow_step WHERE id = '{step}';",
    )
    assert state == "parked true write_conflict", state

    _superuser(
        applied,
        f"UPDATE app_private.workflow_step SET resume_after = now() - interval '1 second' "
        f"WHERE id = '{step}';",
    )
    resumed = _claim(applied, "C")
    assert resumed.stdout.strip(), "a step past its resume time was not claimed"
    assert resumed.stdout.strip().splitlines()[-1].split("|")[4] == "2"


def test_the_last_step_succeeds_the_run_and_a_failure_fails_it(
    applied: dict[str, Any], run_id: str
) -> None:
    """The run's terminal status comes from the step that ends it.

    Asserted through the function's RETURN rather than by reading the run row,
    because the return value is what the worker acts on and a proof that read
    the row would not notice the two disagreeing.
    """
    for expected in ("running", "succeeded"):
        claimed = _claim(applied, "A")
        step = claimed.stdout.strip().splitlines()[-1].split("|")[0]
        finished = _as_role(
            applied,
            applied["roles"]["auth_service"],
            f"SELECT app_private.workflow_finish_step('{step}', 'A', 'succeeded', "
            "'{}'::jsonb, NULL);",
        )
        assert finished.stdout.strip().splitlines()[-1] == expected, finished.stdout

    assert _claim(applied, "A").stdout.strip() == "", "a succeeded run offered another step"


def test_a_failed_step_fails_the_run_and_a_token_refusal_stops_it(
    applied: dict[str, Any], agents: dict[str, str]
) -> None:
    """`failed` and `stopped` are different operator actions, so they are
    different statuses (ADR 0227).

    A failure means a step refused and the run is over; a stop means the agent
    stopped being able to act. Collapsing them would hide the one an operator
    fixes by reauthorising an agent.
    """
    for outcome, expected, reason in (
        ("failed", "failed", "write_conflict"),
        ("token_refused", "stopped", "agent_not_active"),
    ):
        _superuser(
            applied,
            "UPDATE app_private.workflow_run SET status = 'cancelled', "
            "finished_at = now() WHERE status IN ('queued', 'running');",
        )
        name = f"terminal-{secrets.token_hex(3)}"
        assert _install(applied, name, 1).returncode == 0
        enqueued = _enqueue(applied, agents["wide"], name)
        identifier = enqueued.stdout.strip().splitlines()[-1]

        claimed = _claim(applied, "A")
        step = claimed.stdout.strip().splitlines()[-1].split("|")[0]
        finished = _as_role(
            applied,
            applied["roles"]["auth_service"],
            f"SELECT app_private.workflow_finish_step('{step}', 'A', '{outcome}', "
            f"NULL, '{reason}');",
        )
        assert finished.stdout.strip().splitlines()[-1] == expected, finished.stdout

        stopped_reason = _scalar(
            applied,
            f"SELECT stopped_reason FROM app_private.workflow_run WHERE id = '{identifier}';",
        )
        assert stopped_reason == reason, stopped_reason


def test_an_abandoned_step_returns_to_queued_with_its_attempt_spent(
    applied: dict[str, Any], run_id: str
) -> None:
    """The worker ran out of lease before it started the call, so nothing happened.

    The step goes back to `queued` -- not `failed` -- and the next claim takes
    it. The attempt is NOT rewound: a worker that keeps abandoning is a worker
    whose lease is too short for its step, and the attempt count is what says so.
    """
    claimed = _claim(applied, "A")
    step = claimed.stdout.strip().splitlines()[-1].split("|")[0]

    abandoned = _as_role(
        applied,
        applied["roles"]["auth_service"],
        f"SELECT app_private.workflow_finish_step('{step}', 'A', 'abandoned', "
        "NULL, 'out of lease');",
    )
    assert abandoned.returncode == 0, abandoned.stderr

    state = _scalar(
        applied,
        "SELECT status::text || ' ' || attempt::text || ' ' "
        "|| (outcome IS NULL)::text || ' ' || (finished_at IS NULL)::text "
        f"FROM app_private.workflow_step WHERE id = '{step}';",
    )
    assert state == "queued 1 true true", state

    again = _claim(applied, "A")
    assert again.stdout.strip().splitlines()[-1].split("|")[4] == "2"


# ---------------------------------------------------------------------------
# cancel and timeout
# ---------------------------------------------------------------------------


def test_cancel_marks_a_queued_run_cancelled_and_a_running_one_requested(
    applied: dict[str, Any], agents: dict[str, str], run_id: str
) -> None:
    """A cancel cannot recall a call already upstream, so a running run records
    an intent the next claim honours rather than a status (ADR 0227).

    Another agent's run is the same `PT404` a missing run gets, so neither leaks
    the other's existence (ADR 0229).
    """
    queued = _scalar(
        applied,
        f"SELECT app_private.workflow_cancel('{run_id}', '{agents['wide']}');",
    )
    assert queued == "cancelled", queued

    name = f"cancel-{secrets.token_hex(3)}"
    assert _install(applied, name, 1).returncode == 0
    identifier = _enqueue(applied, agents["wide"], name).stdout.strip().splitlines()[-1]
    _claim(applied, "A")

    running = _scalar(
        applied,
        f"SELECT app_private.workflow_cancel('{identifier}', '{agents['wide']}');",
    )
    assert running == "running", running
    requested = _scalar(
        applied,
        "SELECT (cancel_requested_at IS NOT NULL)::text FROM app_private.workflow_run "
        f"WHERE id = '{identifier}';",
    )
    assert requested == "true", requested

    stranger = _superuser(
        applied,
        f"SELECT app_private.workflow_cancel('{identifier}', '{agents['narrow']}');",
    )
    assert stranger.returncode != 0, "another agent cancelled a run"
    assert "AP404" in stranger.stderr, stranger.stderr[:300]


def test_a_claim_after_a_cancel_request_cancels_the_run_and_claims_nothing(
    applied: dict[str, Any], agents: dict[str, str]
) -> None:
    """The intent is honoured at the boundary the worker actually reaches.

    The run whose step is claimed under an UNEXPIRED lease is deliberately left
    alone: the call is upstream, and cancelling it would report the run stopped
    while it was still happening.
    """
    _superuser(
        applied,
        "UPDATE app_private.workflow_run SET status = 'cancelled', "
        "finished_at = now() WHERE status IN ('queued', 'running');",
    )
    name = f"cancel-claim-{secrets.token_hex(3)}"
    assert _install(applied, name, 1).returncode == 0
    identifier = _enqueue(applied, agents["wide"], name).stdout.strip().splitlines()[-1]

    _superuser(
        applied,
        "UPDATE app_private.workflow_run SET cancel_requested_at = now() "
        f"WHERE id = '{identifier}';",
    )
    claimed = _claim(applied, "A")
    assert claimed.stdout.strip() == "", "a cancelled run offered a step"

    status = _scalar(
        applied, f"SELECT status::text FROM app_private.workflow_run WHERE id = '{identifier}';"
    )
    assert status == "cancelled", status


def test_a_run_past_its_timeout_is_failed_at_the_next_claim(
    applied: dict[str, Any], agents: dict[str, str]
) -> None:
    """Before the claim, so a run that has overrun cannot take one more step."""
    _superuser(
        applied,
        "UPDATE app_private.workflow_run SET status = 'cancelled', "
        "finished_at = now() WHERE status IN ('queued', 'running');",
    )
    name = f"timeout-{secrets.token_hex(3)}"
    assert _install(applied, name, 1).returncode == 0
    identifier = _enqueue(applied, agents["wide"], name).stdout.strip().splitlines()[-1]

    claimed = _claim(applied, "A", lease=1)
    step = claimed.stdout.strip().splitlines()[-1].split("|")[0]
    _as_role(
        applied,
        applied["roles"]["auth_service"],
        f"SELECT app_private.workflow_park('{step}', 'A', 'x', now() - interval '1 second');",
    )
    _superuser(
        applied,
        "UPDATE app_private.workflow_run SET started_at = now() - interval '2 hours' "
        f"WHERE id = '{identifier}';",
    )

    after = _claim(applied, "A")
    assert after.stdout.strip() == "", "an overrun run offered a step"
    state = _scalar(
        applied,
        "SELECT status::text || ' ' || stopped_reason FROM app_private.workflow_run "
        f"WHERE id = '{identifier}';",
    )
    assert state == "failed timed_out", state


# ---------------------------------------------------------------------------
# the heartbeat and the reading
# ---------------------------------------------------------------------------


def test_heartbeat_upserts_the_single_row(applied: dict[str, Any]) -> None:
    """One row, and `started_at` moves only when the HOLDER changes.

    That is what makes a restart observable to the `worker-restart` rehearsal: a
    holder that never changed is a loop that never stopped.
    """
    auth = applied["roles"]["auth_service"]
    _as_role(applied, auth, "SELECT app_private.workflow_heartbeat('host:1:100');")
    first = _scalar(applied, "SELECT started_at::text FROM app_private.workflow_worker;")

    time.sleep(1)
    _as_role(applied, auth, "SELECT app_private.workflow_heartbeat('host:1:100');")
    assert _scalar(applied, "SELECT count(*)::text FROM app_private.workflow_worker;") == "1"
    assert _scalar(applied, "SELECT started_at::text FROM app_private.workflow_worker;") == first
    assert (
        _scalar(applied, "SELECT (seen_at > started_at)::text FROM app_private.workflow_worker;")
        == "true"
    )

    _as_role(applied, auth, "SELECT app_private.workflow_heartbeat('host:2:200');")
    moved = _scalar(
        applied,
        "SELECT holder || ' ' || (started_at > '" + first + "'::timestamptz)::text "
        "FROM app_private.workflow_worker;",
    )
    assert moved == "host:2:200 true", moved


def test_counts_reports_numbers_and_no_verdict(applied: dict[str, Any]) -> None:
    """`agent_record_size`'s shape and its reason (D1441).

    Nobody has measured a run count at which a deployment is unwell, so this
    function reports and decides nothing. It also carries no URL, key, token or
    caller value: the assertion below is over the KEY SET, so a field added
    later has to be looked at.
    """
    counts = json.loads(
        _scalar(
            applied,
            f'SET ROLE "{applied["roles"]["auth_service"]}"; SELECT app_private.workflow_counts();',
        )
    )
    assert set(counts) == {
        "definitions",
        "runs",
        "steps",
        "oldest_claimed_lease_age_seconds",
        "heartbeat_age_seconds",
        "heartbeat_holder",
    }, sorted(counts)
    assert isinstance(counts["definitions"], int)
    assert isinstance(counts["runs"], dict)
    assert isinstance(counts["steps"], dict)
    assert "verdict" not in counts and "status" not in counts


def test_run_status_is_the_agents_own_and_another_agents_run_is_the_same_404(
    applied: dict[str, Any], agents: dict[str, str], run_id: str
) -> None:
    """One message for a missing run and for somebody else's (ADR 0229).

    A different refusal for the two would tell a caller that a run it may not
    read exists, which is the existence leak the single message exists to
    prevent.
    """
    document = json.loads(
        _scalar(
            applied,
            f"SELECT app_private.workflow_run_status('{run_id}', '{agents['wide']}');",
        )
    )
    assert document["run_id"] == run_id
    assert document["lock_tools_sha256"] == DIGEST_B
    assert [step["name"] for step in document["steps"]] == ["first", "second"]

    stranger = _superuser(
        applied,
        f"SELECT app_private.workflow_run_status('{run_id}', '{agents['narrow']}');",
    )
    missing = _superuser(
        applied,
        "SELECT app_private.workflow_run_status("
        f"'00000000-0000-4000-8000-000000000000', '{agents['wide']}');",
    )
    assert stranger.returncode != 0 and missing.returncode != 0
    assert "AP404: no such run" in stranger.stderr, stranger.stderr[:300]
    assert "AP404: no such run" in missing.stderr, missing.stderr[:300]
