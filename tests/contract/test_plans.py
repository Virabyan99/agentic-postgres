"""Plans and entitlements in the control set (Session 41, ADR 0274, D2519-D2522, D2538).

`services/auth-api/app/plans.py` is the release table; `app.control_plan_limits`,
seeded by the control set's `0008`, is its SQL twin for the two entitlements SQL
enforces. `app.control_request_operation` locks the organisation's row, counts,
and refuses `AP409: plan_limit_reached` / `AP409: branch_limit_reached` before any
row exists. **Rig 41d measured why the lock has a policy of its own**: without an
UPDATE policy a definer's `SELECT ... FOR UPDATE` under FORCE row security
returned no row, so the count would have run unlocked -- the function raises when
it locked nothing.

**The concurrency proof reads the CODE as well as the rows.** D2166's unique
index already holds an organisation to one open creation, so without the lock a
second concurrent request still leaves one row -- answered `conflict` with the
first's id. With the lock it waits for the first and is refused by the plan.
"""

# ruff: noqa: S608 -- every interpolated value is a uuid or a key this module made.

from __future__ import annotations

import subprocess
import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any

import control_cluster as cc
import pytest

from app import plans

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]


@pytest.fixture(scope="module")
def cluster() -> Iterator[cc.ControlCluster]:
    try:
        with cc.control_cluster() as started:
            yield started
    except RuntimeError as error:
        pytest.skip(str(error))


def _organization(cluster: cc.ControlCluster, role: str = "owner") -> tuple[str, str]:
    """`(user, organisation)`: an account holding `role` in a new organisation."""
    tag = uuid.uuid4().hex[:8]
    user = str(uuid.uuid4())
    cluster.query(
        "INSERT INTO app.control_accounts (user_id, username, display_name) "
        f"VALUES ('{user}', 'plan-{tag}', 'Plan')"
    )
    org = cluster.query(
        f"INSERT INTO app.control_organizations (name, created_by) VALUES ('plan {tag}', '{user}') "
        "RETURNING id"
    )[0]
    cluster.query(
        "INSERT INTO app.control_memberships (organization_id, user_id, role) "
        f"VALUES ('{org}', '{user}', '{role}')"
    )
    return user, org


def _adopt(cluster: cc.ControlCluster, org: str) -> str:
    tag = uuid.uuid4().hex[:8]
    key = f"p{tag}-prod"
    cluster.query(
        f"SELECT app.control_adopt_project('{key}', '{org}', 'p{tag}', 'prod', '{key}.test', "
        "'1.19.0', 'abc')"
    )
    return key


def _request(user: str, org: str, project: str | None, kind: str, arguments: str = "{}") -> str:
    target = "NULL" if project is None else f"'{project}'"
    return (
        "SELECT r.operation_id, r.created FROM app.control_request_operation("
        f"'{user}', '{org}', {target}, '{kind}', '{arguments}'::jsonb) r;"
    )


def _rows(cluster: cc.ControlCluster, org: str, kind: str = "project.create") -> int:
    return int(cluster.query(
        f"SELECT count(*) FROM app.control_operations WHERE organization_id = '{org}' "
        f"AND type = '{kind}'"
    )[0])  # fmt: skip


def test_the_sql_limits_are_the_release_table(cluster: cc.ControlCluster) -> None:
    """The twin (D2533): every enforced-in-SQL entitlement of every plan, value
    for value, and nothing else. A plan read through `control_list_plans` --
    the route's reader -- not the table."""
    user, _ = _organization(cluster)
    rows = cluster.as_service(
        f"SELECT plan, entitlement, value FROM app.control_list_plans('{user}')"
    )
    seeded = {(p, e): int(v) for p, e, v in (row.split("|") for row in rows)}
    expected = {
        (name, entitlement): plans.PLANS[name].entitlements[entitlement].value
        for name in plans.PLAN_NAMES
        for entitlement in plans.ENFORCED_IN_SQL
    }
    assert seeded == expected, (seeded, expected)
    for name in plans.PLAN_NAMES:
        for entitlement in plans.ENFORCED_IN_SQL:
            assert plans.PLANS[name].entitlements[entitlement].enforced
    assert plans.PLANS["free"].status == "active"
    assert plans.PLANS["premium"].status == "unavailable_during_beta"


def test_a_project_beyond_the_plan_is_refused_before_a_row(cluster: cc.ControlCluster) -> None:
    """Free allows one project: with one adopted, a creation is refused
    `plan_limit_reached` and no row exists; a deleted project does not count
    (the control), a sleeping one would (it holds its slot)."""
    user, org = _organization(cluster)
    key = _adopt(cluster, org)
    refused = cluster.refused(_request(user, org, None, "project.create"))
    assert "AP409: plan_limit_reached" in refused, refused
    assert _rows(cluster, org) == 0
    cluster.query(f"UPDATE app.control_projects SET deleted_at = now() WHERE key = '{key}'")
    (created,) = cluster.as_service(_request(user, org, None, "project.create"))
    assert created.endswith("|t"), created
    # On Free a second creation asked while the first is open is the plan's refusal.
    assert "AP409: plan_limit_reached" in cluster.refused(
        _request(user, org, None, "project.create")
    )
    assert _rows(cluster, org) == 1


def _concurrently(
    cluster: cc.ControlCluster, first: tuple[str, str], second: tuple[str, str]
) -> list[Any]:
    """Two creations from two connections; the first holds its transaction 4 s."""
    auth = cluster.auth_role
    results: list[Any] = [None, None]

    def go(index: int, who: tuple[str, str], hold: float, delay: float) -> None:
        time.sleep(delay)
        sql = (
            f'BEGIN;\nSET ROLE "{auth}";\n'
            + _request(who[0], who[1], None, "project.create")
            + f"\nSELECT pg_sleep({hold});\nCOMMIT;\n"
        )
        started = time.monotonic()
        done = cc.docker(
            "exec", "-i", cluster.name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
            "-U", "postgres", "-d", cluster.database, stdin=sql,
        )  # fmt: skip
        results[index] = (time.monotonic() - started, done)

    threads = [
        threading.Thread(target=go, args=(0, first, 4, 0)),
        threading.Thread(target=go, args=(1, second, 0, 1)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def test_two_concurrent_creates_leave_one_row(cluster: cc.ControlCluster) -> None:
    """Rig 41d's case (D2521, D2538): the second creation for ONE organisation
    waits on its row lock, then is refused `plan_limit_reached` -- one row.
    Control: two organisations, two rows, and the second does not wait."""
    one = _organization(cluster)
    (waited, first), (blocked, second) = _concurrently(cluster, one, one)
    assert first.returncode == 0 and first.stdout.strip().splitlines()[0].endswith("|t"), first
    assert second.returncode != 0 and "AP409: plan_limit_reached" in second.stderr, second
    assert blocked > 2.0, (
        f"the second request did not wait on the organisation's row: {blocked:.1f} s"
    )
    assert _rows(cluster, one[1]) == 1
    a, b = _organization(cluster), _organization(cluster)
    (_, first), (quick, second) = _concurrently(cluster, a, b)
    assert first.returncode == 0 and second.returncode == 0, (first.stderr, second.stderr)
    assert quick < 2.0, f"a second organisation waited on the first's lock: {quick:.1f} s"
    assert _rows(cluster, a[1]) == 1 and _rows(cluster, b[1]) == 1
    del waited


def test_a_lock_that_locks_nothing_is_refused(cluster: cc.ControlCluster) -> None:
    """D2538: the lock is a policy whose UPDATE can change nothing (WITH CHECK
    false), and a request that cannot lock the row is refused, never counted
    unlocked."""
    user, org = _organization(cluster)
    owner = cluster.roles["object_owner"]
    # As a definer would hold it: the caller set, the organisation scoped --
    # the row visible and lockable, and still not writable.
    update = cluster.run(
        f"SELECT set_config('app.user_id', '{user}', true);\n"
        f"SELECT set_config('app.control_org', '{org}', true);\n"
        f"UPDATE app.control_organizations SET name = 'renamed' WHERE id = '{org}';",
        as_role=owner,
    )
    assert update.returncode != 0 and "row-level security" in update.stderr, update
    cluster.query("DROP POLICY control_organizations_lock ON app.control_organizations")
    try:
        refused = cluster.refused(_request(user, org, None, "project.create"))
        assert "the organisation row could not be locked" in refused, refused
    finally:
        cluster.query(
            "CREATE POLICY control_organizations_lock ON app.control_organizations "
            f'FOR UPDATE TO "{owner}" '
            "USING (id::text = current_setting('app.control_org', true)) WITH CHECK (false)"
        )
    assert _rows(cluster, org) == 0


def _branch_row(cluster: cc.ControlCluster, key: str, name: str) -> None:
    cluster.query(
        "INSERT INTO app.control_branches (project_key, name, state) "
        f"VALUES ('{key}', '{name}', 'ready')"
    )


def test_the_branch_limit_reads_the_plan(cluster: cc.ControlCluster) -> None:
    """`branches_total` from `control_plan_limits` (D2519): Free's 1 refuses a
    second branch `branch_limit_reached`; with the organisation on Premium (3)
    the same request is admitted -- the number is the plan's, not a constant."""
    user, org = _organization(cluster)
    key = _adopt(cluster, org)
    _branch_row(cluster, key, "dev")
    arguments = '{"branch": "qa"}'
    refused = cluster.refused(_request(user, org, key, "branch.create", arguments))
    assert "AP409: branch_limit_reached" in refused, refused
    assert _rows(cluster, org, "branch.create") == 0
    cluster.query(f"UPDATE app.control_organizations SET plan = 'premium' WHERE id = '{org}'")
    (created,) = cluster.as_service(_request(user, org, key, "branch.create", arguments))
    assert created.endswith("|t"), created


def test_premium_is_unavailable_and_interest_is_one_row(cluster: cc.ControlCluster) -> None:
    """*Notify me* (D2522): asked twice by two members, ONE row; only for the plan
    unavailable during the beta; a viewer cannot ask; the organisation's plan
    reader names the interest and counts the projects as the limit does."""
    owner, org = _organization(cluster)
    member = str(uuid.uuid4())
    cluster.query(
        "INSERT INTO app.control_accounts (user_id, username, display_name) "
        f"VALUES ('{member}', 'm-{member[:8]}', 'M')"
    )
    cluster.query(
        "INSERT INTO app.control_memberships (organization_id, user_id, role) "
        f"VALUES ('{org}', '{member}', 'member')"
    )
    first = cluster.as_service(
        f"SELECT app.control_register_interest('{owner}', '{org}', 'premium')"
    )
    again = cluster.as_service(
        f"SELECT app.control_register_interest('{member}', '{org}', 'premium')"
    )
    assert (first, again) == (["t"], ["f"]), (first, again)
    assert "AP422" in cluster.refused(
        f"SELECT app.control_register_interest('{owner}', '{org}', 'free')"
    )
    viewer = str(uuid.uuid4())
    cluster.query(
        "INSERT INTO app.control_accounts (user_id, username, display_name) "
        f"VALUES ('{viewer}', 'v-{viewer[:8]}', 'V')"
    )
    cluster.query(
        "INSERT INTO app.control_memberships (organization_id, user_id, role) "
        f"VALUES ('{org}', '{viewer}', 'viewer')"
    )
    assert "AP403" in cluster.refused(
        f"SELECT app.control_register_interest('{viewer}', '{org}', 'premium')"
    )
    assert cluster.query(
        f"SELECT count(*) FROM app.control_plan_interest WHERE organization_id = '{org}'"
    ) == ["1"]
    _adopt(cluster, org)
    (row,) = cluster.as_service(f"SELECT * FROM app.control_get_org_plan('{viewer}', '{org}')")
    assert row == "free|1|{premium}", row


def test_no_role_but_the_owner_writes_a_plan_or_a_limit(cluster: cc.ControlCluster) -> None:
    """No route writes a plan or a limit (D2533): the identity service's role
    holds no privilege on either table, and nothing it may execute writes them."""
    for table in (
        "app.control_plan_limits",
        "app.control_organizations",
        "app.control_plan_interest",
    ):
        for privilege in ("INSERT", "UPDATE", "DELETE"):
            (held,) = cluster.query(
                f"SELECT has_table_privilege('{cluster.auth_role}', '{table}', '{privilege}')"
            )
            assert held == "f", (table, privilege)
    granted = cluster.query(
        "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        f"WHERE n.nspname = 'app' AND p.prokind = 'f' "
        f"AND has_function_privilege('{cluster.auth_role}', p.oid, 'EXECUTE') "
        "AND pg_get_functiondef(p.oid) ~* "
        "'((insert into|update|delete from) app\\.control_plan_limits"
        "|update app\\.control_organizations)' "
        "ORDER BY 1"
    )
    assert granted == [], granted


def test_the_lock_is_held_across_the_count_by_one_transaction(cluster: cc.ControlCluster) -> None:
    """While one creation's transaction holds the row, a third connection's
    `FOR NO KEY UPDATE NOWAIT` on it is refused -- the lock is real, not a SELECT.

    NO KEY UPDATE, not UPDATE: the operation row's foreign key takes FOR KEY SHARE
    on the organisation, which a FOR UPDATE probe also meets -- that probe passed
    with the request's lock removed (Run 4's battery, mutation (a)). NO KEY UPDATE
    conflicts with the request's FOR UPDATE and not with a foreign key's share."""
    user, org = _organization(cluster)
    sql = (
        f'BEGIN;\nSET ROLE "{cluster.auth_role}";\n'
        + _request(user, org, None, "project.create")
        + "\nSELECT pg_sleep(4);\nROLLBACK;\n"
    )
    holder = subprocess.Popen(
        ["docker", "exec", "-i", cluster.name, "psql", "-qtA", "-U", "postgres",
         "-d", cluster.database],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )  # fmt: skip
    assert holder.stdin is not None
    holder.stdin.write(sql)
    holder.stdin.close()
    time.sleep(1.5)
    probe = cluster.run(
        f"SELECT 1 FROM app.control_organizations WHERE id = '{org}' FOR NO KEY UPDATE NOWAIT"
    )
    holder.wait(timeout=30)
    assert probe.returncode != 0 and "could not obtain lock" in probe.stderr, probe
