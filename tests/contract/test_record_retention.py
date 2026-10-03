"""Migrations 0038 and 0039: retention for the Stage 4 record (OPS-RETAIN-001).

**Applied as `migration_user`, never as a superuser** (D285), on the locked
image, by `test_workflow_substrate.py`'s recipe. ADR 0248 extends ADR 0213 to the
ten Stage 4 tables: three prunes by AGGREGATE granted to nobody, a size reading
granted to nobody, and a withdrawal of ended runs' pending approvals granted to
`auth_service` alone.

**What the rigs measured before a line of this file was written** (Session 36
Run 1):

* rig 36a: a value added by `ALTER TYPE ... ADD VALUE` cannot be used in its own
  transaction on 18.4 (55P04), and one dbmate file adding and using it prints
  `Applied` and then fails -- so `withdrawn` is 0038's alone and 0039 uses it.
* rig 36b: the run prune's order (attempts, approvals, receipts, steps, runs) is
  load-bearing -- the control, runs first, raised `23503` on
  `workflow_step_run_id_fkey`; the bound counted roots; `LIMIT NULL` is none.
* rig 36d: the withdrawal finds nothing in ~1 ms, so an idle poll can afford it.

**Every scenario is one transaction that is ROLLED BACK**, so the proofs share a
cluster and no state. The identities are the product's own
(`auth_create_user`, `auth_create_agent`, D313); the RECORD rows are written
here, because the thing under test is what a prune does to runs ended ten days
ago in every status, and no product path makes those on demand. The fixture and
the functions do not share a belief about which rows are ended: the fixture
names statuses, the assertions name the survivors.
"""

from __future__ import annotations

# ruff: noqa: S608
#
# Every interpolated value below is a role or database name read from a rendered
# outputs document this repository produced, or a uuid the cluster returned.
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

#: A hash the `agent_credentials` CHECK accepts; `test_workflow_substrate.py`'s.
STORED_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$aGFzaA"

#: The four granted to nobody and the one granted to the worker's role.
NOBODY = (
    "workflow_run_prune(timestamptz, integer)",
    "connector_delivery_prune(timestamptz, integer)",
    "agent_prune(timestamptz, integer)",
    "record_size()",
)
WITHDRAWAL = "workflow_withdraw_ended_approvals()"

#: Every request-reachable role a deployment has, and `anon` as the control the
#: audit plane's own privilege proofs use.
REACHABLE = (
    "auth_service",
    "agent_writer",
    "agent_reader",
    "authenticated",
    "anon",
    "storage_service",
    "app_runtime",
)

#: What `record_size()` names, in its order (ADR 0248).
RELATIONS = [
    "agent_audit",
    "agent_idempotency",
    "workflow_run",
    "workflow_step",
    "workflow_attempt",
    "workflow_approval",
    "connector_event",
    "connector_delivery",
    "connector_receipt",
    "agents (revoked)",
    "workflow_approval (pending on an ended run)",
]

#: The ten-minute-old horizon every prune accepts (D1988's bound is 600 s).
HORIZON = "now() - interval '601 seconds'"


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
    """A cluster on the locked image; `test_workflow_substrate.py`'s recipe."""
    if not (FIXTURE / "outputs.json").is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    if _docker("version", "--format", "{{.Server.Version}}", timeout=30).returncode != 0:
        pytest.skip("docker is not available")

    document = json.loads((FIXTURE / "outputs.json").read_text(encoding="utf-8"))
    roles = document["database"]["roles"]
    database = document["database"]["name"]
    password = secrets.token_hex(24)
    name = f"apg-record-retention-{secrets.token_hex(4)}"

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


def _as_role(cluster: dict[str, Any], role_key: str, sql: str):
    return _superuser(cluster, f'SET ROLE "{cluster["roles"][role_key]}";\n{sql}')


def _scalar(cluster: dict[str, Any], sql: str) -> str:
    result = _superuser(cluster, sql)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""


@pytest.fixture(scope="module")
def applied(cluster: dict[str, Any]) -> dict[str, Any]:
    """Every released migration applied as `migration_user`, 0038 and 0039 last.

    Raises with the migration's own stderr rather than asserting, so a broken
    fixture is an ERROR and never reads as a kill (D386); the owner is created
    through the product's own function (D313).
    """
    document = cluster["document"]
    versions: list[str] = []
    for migration_set in migrations.sets_for(document):
        if migration_set.is_project:
            continue
        manifest = migration_set.load_manifest()
        for entry in manifest["migrations"]:
            rendered = migrations.render_migration(entry, manifest, document, migration_set.root)
            result = _apply_as_migration_user(cluster, rendered.split("-- migrate:down")[0])
            if result.returncode != 0:
                raise RuntimeError(
                    f"{entry['version']} {entry['name']} failed as migration_user: "
                    f"{result.stderr.strip()[:800]}"
                )
            versions.append(entry["version"])
    owner = _scalar(
        cluster,
        "SELECT app_private.auth_create_user('rr-owner', 'rr-owner', 'authenticated', "
        f"ARRAY['notes:read','notes:write']::text[], '{STORED_HASH}');",
    )
    return {"versions": versions, "owner": owner, **cluster}


#: The scenario every behavioural proof starts from, written once (rig 36b's).
#: `{owner}`, `{writer}` and `{hash}` are filled in; every stamp is relative to
#: the transaction's `now()`. `ids` maps a fixture name to the row it made.
SEED = """
BEGIN;
CREATE TEMP TABLE ids (k text PRIMARY KEY, id uuid NOT NULL DEFAULT gen_random_uuid())
  ON COMMIT DROP;
INSERT INTO ids (k) SELECT unnest(ARRAY['def',
  'r_queued', 'r_running', 'r_succeeded', 'r_failed', 'r_cancelled', 'r_stopped',
  'r_compensating', 'r_succeeded_new',
  'c_out', 'c_in', 'ev_old', 'ev_pending', 'ev_awaited', 'ev_new']);
INSERT INTO ids (k, id)
SELECT k,
  app_private.auth_create_agent(k, '', '{writer}', {scopes}, '{owner}', '{hash}', NULL)
  FROM unnest(ARRAY['ag_active', 'ag_rev_free', 'ag_rev_run', 'ag_rev_conn']) k;
UPDATE app_private.agents SET status = 'revoked'
 WHERE id IN (SELECT id FROM ids WHERE k LIKE 'ag_rev_%');
UPDATE app_private.agents SET updated_at = now() - interval '30 days'
 WHERE id IN (SELECT id FROM ids WHERE k LIKE 'ag_%');

INSERT INTO app_private.workflow_definition
  (id, name, version, body, source_sha256, lock_tools_sha256, required_scopes)
SELECT id, 'rr-def', 1, '{{}}', repeat('a', 64), repeat('b', 64), '{{}}'
  FROM ids WHERE k = 'def';

INSERT INTO app_private.workflow_run
  (id, definition_id, agent_id, owner_id, timeout_seconds, status, created_at, finished_at)
SELECT r.id, (SELECT id FROM ids WHERE k = 'def'),
       (SELECT id FROM ids
         WHERE k = CASE WHEN r.k = 'r_failed' THEN 'ag_rev_run' ELSE 'ag_active' END),
       '{owner}', 60,
       replace(replace(r.k, 'r_', ''), '_new', '')::app_private.workflow_run_status,
       now() - interval '11 days',
       CASE WHEN r.k IN ('r_queued', 'r_running', 'r_compensating') THEN NULL
            WHEN r.k = 'r_succeeded_new' THEN now() - interval '1 minute'
            WHEN r.k = 'r_succeeded' THEN now() - interval '13 days'
            WHEN r.k = 'r_failed' THEN now() - interval '12 days'
            ELSE now() - interval '10 days' END
  FROM ids r WHERE r.k LIKE 'r_%';

INSERT INTO app_private.workflow_step
  (run_id, position, name, retry_max, backoff_seconds, timeout_seconds, idempotency_key,
   status, await_event)
SELECT id, 1, 'step-one', 0, 1, 60, 'rr-key-' || k,
       CASE WHEN k = 'r_running' THEN 'parked' ELSE 'succeeded' END
         ::app_private.workflow_step_status,
       CASE WHEN k = 'r_running' THEN 'order.paid@1' END
  FROM ids WHERE k LIKE 'r_%';
INSERT INTO app_private.workflow_attempt (step_id, attempt, event)
SELECT s.id, n, 'finished'
  FROM app_private.workflow_step s CROSS JOIN generate_series(1, 2) n
 WHERE s.run_id IN (SELECT id FROM ids WHERE k LIKE 'r_%');

INSERT INTO app_private.workflow_approval
  (run_id, step_id, tool, capability, idempotency_key, expires_at, status, decided_by,
   decided_at)
SELECT s.run_id, s.id, 'create_note', 'notes_write@1.0.0', 'rr-appr-' || i.k,
       now() + interval '1 day',
       CASE WHEN i.k = 'r_succeeded' THEN 'approved' ELSE 'pending' END
         ::app_private.workflow_approval_status,
       CASE WHEN i.k = 'r_succeeded' THEN '{owner}'::uuid END,
       CASE WHEN i.k = 'r_succeeded' THEN now() - interval '13 days' END
  FROM app_private.workflow_step s JOIN ids i ON i.id = s.run_id
 WHERE i.k IN ('r_cancelled', 'r_running', 'r_succeeded', 'r_compensating');

INSERT INTO app_private.connector
  (id, name, version, kind, body, source_sha256, event, retry_max, backoff_seconds)
SELECT id, 'rr-out', 1, 'outbound', '{{}}', repeat('c', 64), 'order.paid@1', 2, 5
  FROM ids WHERE k = 'c_out';
INSERT INTO app_private.connector
  (id, name, version, kind, body, source_sha256, definition_name, definition_version,
   agent_id)
SELECT id, 'rr-in', 1, 'inbound', '{{}}', repeat('d', 64), 'rr-def', 1,
       (SELECT id FROM ids WHERE k = 'ag_rev_conn')
  FROM ids WHERE k = 'c_in';

INSERT INTO app_private.connector_receipt (connector_id, delivery_id, run_id, received_at)
SELECT (SELECT id FROM ids WHERE k = 'c_in'), gen_random_uuid(),
       (SELECT id FROM ids WHERE k = x), now() - interval '10 days'
  FROM unnest(ARRAY['r_stopped', 'r_running']) x;
INSERT INTO app_private.connector_receipt (connector_id, delivery_id, run_id, received_at)
SELECT id, gen_random_uuid(), NULL, now() - interval '10 days' FROM ids WHERE k = 'c_in';

INSERT INTO app_private.connector_event (id, name, version, owner_id, payload, emitted_at)
SELECT id, CASE WHEN k = 'ev_awaited' THEN 'order.paid' ELSE 'thing.done' END, 1,
       '{owner}', '{{}}',
       CASE WHEN k = 'ev_new' THEN now() - interval '1 minute'
            ELSE now() - interval '10 days' END
  FROM ids WHERE k LIKE 'ev_%';
INSERT INTO app_private.connector_delivery
  (event_id, connector_id, max_attempts, backoff_seconds, status, delivered_at, dead_at)
SELECT e.id, (SELECT id FROM ids WHERE k = 'c_out'), 3, 5, v.status::app_private.delivery_status,
       CASE WHEN v.status = 'delivered' THEN v.at END,
       CASE WHEN v.status = 'dead' THEN v.at END
  FROM (VALUES ('ev_old', 'delivered', now() - interval '10 days'),
               ('ev_old', 'dead', now() - interval '9 days'),
               ('ev_pending', 'delivered', now() - interval '10 days'),
               ('ev_pending', 'pending', NULL::timestamptz),
               ('ev_awaited', 'delivered', now() - interval '10 days'),
               ('ev_new', 'delivered', now() - interval '1 minute')) v(k, status, at)
  JOIN ids e ON e.k = v.k;
"""


def _scenario(applied: dict[str, Any], body: str) -> list[str]:
    """SEED, then `body`, then ROLLBACK -- one transaction, nothing kept.

    Returns `body`'s output lines. A failure anywhere raises with psql's stderr,
    so a broken seed is an ERROR of the proof that ran it (D386).
    """
    seed = SEED.format(
        owner=applied["owner"],
        writer=applied["roles"]["agent_writer"],
        hash=STORED_HASH,
        scopes="ARRAY['notes:read','notes:write']",
    )
    result = _superuser(applied, f"{seed}\n\\echo ---BODY---\n{body}\nROLLBACK;\n")
    if result.returncode != 0:
        raise RuntimeError(f"the scenario failed: {result.stderr.strip()[:800]}")
    return result.stdout.split("---BODY---", 1)[1].strip().splitlines()


def _grantees(applied: dict[str, Any], signature: str) -> str:
    name = signature.split("(", 1)[0]
    return _scalar(
        applied,
        "SELECT coalesce(string_agg(DISTINCT a.grantee::regrole::text, ','), '') "
        "FROM pg_proc p, aclexplode(p.proacl) a "
        f"WHERE p.pronamespace = 'app_private'::regnamespace AND p.proname = '{name}' "
        "  AND a.grantee <> p.proowner;",
    )


# ---------------------------------------------------------------------------
# who may call what
# ---------------------------------------------------------------------------


def test_every_prune_is_executable_by_no_role(applied: dict[str, Any]) -> None:
    """The three prunes and the size reading are granted to NOBODY (ADR 0248).

    Two readings of one fact: the ACL names no grantee but the owner, and every
    request-reachable role that tries is refused with *permission denied*. The
    control is that the superuser -- the hand `bin/record.sh` is -- is served.
    """
    last_two = applied["versions"][-2:]
    assert last_two == ["20261003120038", "20261003120039"], applied["versions"][-3:]
    calls = {
        "workflow_run_prune(timestamptz, integer)": f"SELECT app_private.workflow_run_prune({HORIZON});",  # noqa: E501
        "connector_delivery_prune(timestamptz, integer)": f"SELECT app_private.connector_delivery_prune({HORIZON});",  # noqa: E501
        "agent_prune(timestamptz, integer)": f"SELECT app_private.agent_prune({HORIZON});",
        "record_size()": "SELECT count(*) FROM app_private.record_size();",
    }
    for signature in NOBODY:
        assert _grantees(applied, signature) == "", f"app_private.{signature} is granted"
        for role_key in REACHABLE:
            refused = _as_role(applied, role_key, calls[signature])
            assert refused.returncode != 0, f"{role_key} reached app_private.{signature}"
            assert "permission denied" in refused.stderr, refused.stderr[:300]
        served = _superuser(applied, calls[signature])
        assert served.returncode == 0, f"the superuser was refused {signature}: {served.stderr}"


def test_the_withdrawal_is_executable_by_the_auth_service_alone(applied: dict[str, Any]) -> None:
    """Granted to the role the worker loop runs as (0034), and to nothing else."""
    assert _grantees(applied, WITHDRAWAL) == applied["roles"]["auth_service"]
    served = _as_role(applied, "auth_service", f"SELECT app_private.{WITHDRAWAL};")
    assert served.returncode == 0, served.stderr
    assert served.stdout.strip().isdigit(), served.stdout
    for role_key in REACHABLE:
        if role_key == "auth_service":
            continue
        refused = _as_role(applied, role_key, f"SELECT app_private.{WITHDRAWAL};")
        assert refused.returncode != 0, f"{role_key} reached the withdrawal"
        assert "permission denied" in refused.stderr, refused.stderr[:300]


# ---------------------------------------------------------------------------
# the refusals
# ---------------------------------------------------------------------------


def test_a_horizon_is_required_past_and_bounded(applied: dict[str, Any]) -> None:
    """0033's three refusals on each prune, PT422, and the control accepted.

    Without the control a function that refused everything would pass (D499).
    """
    for function in ("workflow_run_prune", "connector_delivery_prune", "agent_prune"):
        for label, arguments in (
            ("a missing horizon", "NULL"),
            ("a future horizon", "now() + interval '1 hour'"),
            ("a bound below one", f"{HORIZON}, 0"),
        ):
            refused = _superuser(applied, f"SELECT app_private.{function}({arguments});")
            assert refused.returncode != 0, f"{function} accepted {label}"
            assert "AP422" in refused.stderr, f"{function}, {label}: {refused.stderr[:300]}"
        accepted = _superuser(applied, f"SELECT app_private.{function}({HORIZON}, 1);")
        assert accepted.returncode == 0, f"{function} refused the control: {accepted.stderr}"


def test_a_run_horizon_inside_the_replay_window_is_refused(applied: dict[str, Any]) -> None:
    """D1988: no receipt younger than twice the signature window goes with its run.

    The run prune refuses `now() - 300 s`; the same horizon is accepted by the
    other two prunes (the window is the run prune's alone), and `now() - 601 s`
    by the run prune -- the two controls.
    """
    inside = "now() - interval '300 seconds'"
    refused = _superuser(applied, f"SELECT app_private.workflow_run_prune({inside});")
    assert refused.returncode != 0, "a horizon inside the replay window was accepted"
    assert "inside the inbound replay window" in refused.stderr, refused.stderr[:300]
    for function in ("connector_delivery_prune", "agent_prune"):
        accepted = _superuser(applied, f"SELECT app_private.{function}({inside});")
        assert accepted.returncode == 0, f"{function} refused {inside}: {accepted.stderr}"
    accepted = _superuser(applied, f"SELECT app_private.workflow_run_prune({HORIZON});")
    assert accepted.returncode == 0, accepted.stderr


# ---------------------------------------------------------------------------
# what each prune removes, and what it never removes
# ---------------------------------------------------------------------------

#: Read after a prune: each surviving run's fixture name, and its children.
SURVIVORS = """
SELECT 'run:' || i.k FROM app_private.workflow_run r JOIN ids i ON i.id = r.id;
SELECT 'steps:' || count(*) FROM app_private.workflow_step WHERE run_id IN (SELECT id FROM ids);
SELECT 'attempts:' || count(*)
  FROM app_private.workflow_attempt a JOIN app_private.workflow_step s ON s.id = a.step_id
 WHERE s.run_id IN (SELECT id FROM ids);
SELECT 'approval:' || i.k FROM app_private.workflow_approval a JOIN ids i ON i.id = a.run_id;
SELECT 'receipt:' || coalesce(i.k, '-')
  FROM app_private.connector_receipt c LEFT JOIN ids i ON i.id = c.run_id
 WHERE c.connector_id = (SELECT id FROM ids WHERE k = 'c_in');
"""


def test_a_run_prune_removes_ended_runs_and_exactly_their_children(applied: dict[str, Any]) -> None:
    """Four runs ended before the horizon go, with every row that names them.

    Both halves asserted: what went (the count it returned, and none of the four
    is left) and what stayed (four runs, each with its step, two attempts, and
    the approvals and receipts that name a survivor).
    """
    lines = _scenario(
        applied,
        f"SELECT 'removed:' || app_private.workflow_run_prune({HORIZON});\n{SURVIVORS}",
    )
    assert "removed:4" in lines, lines
    assert sorted(line for line in lines if line.startswith("run:")) == [
        "run:r_compensating",
        "run:r_queued",
        "run:r_running",
        "run:r_succeeded_new",
    ]
    assert "steps:4" in lines and "attempts:8" in lines, lines
    assert sorted(line for line in lines if line.startswith("approval:")) == [
        "approval:r_compensating",
        "approval:r_running",
    ]
    assert sorted(line for line in lines if line.startswith("receipt:")) == [
        "receipt:-",
        "receipt:r_running",
    ]


def test_a_live_run_is_never_pruned(applied: dict[str, Any]) -> None:
    """The status filter is the guard, and this proof leaves it the ONLY one.

    Every live run is given a `finished_at` ten days old -- a value the product
    never writes on one -- so a prune that read the timestamp alone would take
    them. A `queued`, `running` or `compensating` run survives anyway.
    """
    lines = _scenario(
        applied,
        "UPDATE app_private.workflow_run SET finished_at = now() - interval '20 days' "
        "WHERE id IN (SELECT id FROM ids WHERE k IN ('r_queued','r_running','r_compensating'));\n"
        f"SELECT 'removed:' || app_private.workflow_run_prune({HORIZON});\n{SURVIVORS}",
    )
    assert "removed:4" in lines, lines
    live = {"run:r_queued", "run:r_running", "run:r_compensating"}
    assert live <= set(lines), f"a live run was pruned: {sorted(live - set(lines))}"


def test_a_delivery_prune_keeps_pending_deliveries_and_awaited_events(
    applied: dict[str, Any],
) -> None:
    """Delivered and dead deliveries before the horizon go; the events left with
    no delivery go after them; a pending delivery, a recent one, and an event a
    live run's parked step awaits (`order.paid@1`, D2008's `name@version`) stay.

    **The control**: the same scenario with the awaiting run ENDED -- then the
    awaited event goes too, so the guard is about live waits and nothing else.
    """
    read = (
        f"SELECT 'removed:' || app_private.connector_delivery_prune({HORIZON});\n"
        "SELECT 'event:' || i.k FROM app_private.connector_event e JOIN ids i ON i.id = e.id;\n"
        "SELECT 'delivery:' || i.k || ':' || d.status FROM app_private.connector_delivery d "
        "JOIN ids i ON i.id = d.event_id;\n"
    )
    lines = _scenario(applied, read)
    assert "removed:4" in lines, lines
    assert sorted(line for line in lines if line.startswith("event:")) == [
        "event:ev_awaited",
        "event:ev_new",
        "event:ev_pending",
    ]
    assert sorted(line for line in lines if line.startswith("delivery:")) == [
        "delivery:ev_new:delivered",
        "delivery:ev_pending:pending",
    ]

    ended = _scenario(
        applied,
        "UPDATE app_private.workflow_run SET status = 'stopped', finished_at = now() "
        "WHERE id = (SELECT id FROM ids WHERE k = 'r_running');\n" + read,
    )
    assert "event:ev_awaited" not in ended, "the guard kept an event no live run awaits"


def test_an_agent_prune_keeps_active_and_referenced_agents(applied: dict[str, Any]) -> None:
    """Only a revoked agent no run and no connector names is removed, with its
    credentials and quota by their CASCADE. The active one, the one a run names
    and the one a connector is bound to stay."""
    lines = _scenario(
        applied,
        "INSERT INTO app_private.agent_quota (agent_id, window_start, calls) "
        "SELECT id, now(), 1 FROM ids WHERE k LIKE 'ag_%' ON CONFLICT DO NOTHING;\n"
        "SELECT 'quota-before:' || count(*) FROM app_private.agent_quota "
        "WHERE agent_id = (SELECT id FROM ids WHERE k = 'ag_rev_free');\n"
        f"SELECT 'removed:' || app_private.agent_prune({HORIZON});\n"
        "SELECT 'agent:' || i.k FROM app_private.agents a JOIN ids i ON i.id = a.id;\n"
        "SELECT 'credentials:' || count(*) FROM app_private.agent_credentials "
        "WHERE agent_id = (SELECT id FROM ids WHERE k = 'ag_rev_free');\n"
        "SELECT 'quota:' || count(*) FROM app_private.agent_quota "
        "WHERE agent_id = (SELECT id FROM ids WHERE k = 'ag_rev_free');\n",
    )
    assert "removed:1" in lines, lines
    assert sorted(line for line in lines if line.startswith("agent:")) == [
        "agent:ag_active",
        "agent:ag_rev_conn",
        "agent:ag_rev_run",
    ]
    # The CASCADE is observed, not assumed: the row existed before the prune.
    assert "quota-before:1" in lines, lines
    assert "credentials:0" in lines and "quota:0" in lines, lines


def test_the_bound_counts_roots(applied: dict[str, Any]) -> None:
    """`p_limit` bounds RUNS, oldest first, and *call it again until it returns
    zero* is the procedure: 2, then 2, then 0, with every child of each removed
    run gone with it."""
    lines = _scenario(
        applied,
        f"SELECT 'first:' || app_private.workflow_run_prune({HORIZON}, 2);\n"
        "SELECT 'after-first:' || i.k FROM app_private.workflow_run r JOIN ids i ON i.id = r.id "
        "WHERE i.k IN ('r_succeeded','r_failed','r_cancelled','r_stopped');\n"
        "SELECT 'orphans:' || count(*) FROM app_private.workflow_step s "
        "WHERE NOT EXISTS (SELECT 1 FROM app_private.workflow_run r WHERE r.id = s.run_id);\n"
        f"SELECT 'second:' || app_private.workflow_run_prune({HORIZON}, 2);\n"
        f"SELECT 'third:' || app_private.workflow_run_prune({HORIZON}, 2);\n",
    )
    assert ["first:2", "second:2", "third:0"] == [
        line for line in lines if line.split(":")[0] in ("first", "second", "third")
    ], lines
    # The two OLDEST ended first: r_succeeded (13 days) and r_failed (12 days).
    assert sorted(line for line in lines if line.startswith("after-first:")) == [
        "after-first:r_cancelled",
        "after-first:r_stopped",
    ]
    assert "orphans:0" in lines, lines


# ---------------------------------------------------------------------------
# the withdrawal, and the reading
# ---------------------------------------------------------------------------


def test_the_withdrawal_moves_only_pending_approvals_of_ended_runs(
    applied: dict[str, Any],
) -> None:
    """D1775: the pending approval on the cancelled run becomes `withdrawn`; the
    running run's and the compensating run's stay `pending`; the decided one
    stays `approved`, its decider untouched. A second call finds nothing."""
    lines = _scenario(
        applied,
        f"SELECT 'moved:' || app_private.{WITHDRAWAL};\n"
        "SELECT 'approval:' || i.k || ':' || a.status || ':' || (a.decided_by IS NOT NULL) "
        "FROM app_private.workflow_approval a JOIN ids i ON i.id = a.run_id;\n"
        f"SELECT 'again:' || app_private.{WITHDRAWAL};\n",
    )
    assert "moved:1" in lines and "again:0" in lines, lines
    assert sorted(line for line in lines if line.startswith("approval:")) == [
        "approval:r_cancelled:withdrawn:false",
        "approval:r_compensating:pending:false",
        "approval:r_running:pending:false",
        "approval:r_succeeded:approved:true",
    ]


def test_the_size_reading_names_every_prunable_relation(applied: dict[str, Any]) -> None:
    """Eleven rows, in order, each agreeing with a direct count read in the same
    transaction; the pending-on-an-ended-run row is 1 before the withdrawal and
    0 after it -- the number the worker exists to keep at zero."""
    lines = _scenario(
        applied,
        "SELECT 'size:' || relation || ':' || row_count FROM app_private.record_size();\n"
        "SELECT 'direct:workflow_run:' || count(*) FROM app_private.workflow_run;\n"
        "SELECT 'direct:workflow_attempt:' || count(*) FROM app_private.workflow_attempt;\n"
        "SELECT 'direct:connector_delivery:' || count(*) FROM app_private.connector_delivery;\n"
        "SELECT 'direct:agents (revoked):' || count(*) FROM app_private.agents "
        "WHERE status = 'revoked';\n"
        f"SELECT 'moved:' || app_private.{WITHDRAWAL};\n"
        "SELECT 'after:' || row_count FROM app_private.record_size() "
        "WHERE relation = 'workflow_approval (pending on an ended run)';\n",
    )
    sizes = [line.split(":", 2) for line in lines if line.startswith("size:")]
    assert [relation for _, relation, _ in sizes] == RELATIONS, sizes
    counted = {relation: count for _, relation, count in sizes}
    for line in lines:
        if line.startswith("direct:"):
            _, relation, count = line.split(":", 2)
            assert counted[relation] == count, (
                f"{relation}: size {counted[relation]}, direct {count}"
            )
    assert counted["workflow_approval (pending on an ended run)"] == "1", counted
    assert "moved:1" in lines and "after:0" in lines, lines
