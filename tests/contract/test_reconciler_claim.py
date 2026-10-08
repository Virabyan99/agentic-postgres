"""The reconciler's half of the control set, against a real cluster (D2151, D2152).

OPN-CLAIM-001 (ADR 0256). The functions the reconciler calls are SECURITY
INVOKER and granted to nobody (D2093): only the bootstrap superuser -- root,
over the container socket -- executes them. These proofs call them as the
superuser, the way the reconciler will, on `control_cluster`.

The claim's two properties are two proofs (D2191): two claimers whose
transactions overlap take DISTINCT rows (the row lock and the outer recheck),
and the second does not WAIT for the first (SKIP LOCKED). Each overlap is made
deterministic the way rig 38f made it: claimer A claims and holds its
transaction open 2 s; claimer B starts 0.3 s after A.
"""

# ruff: noqa: S608 -- every interpolated value is a uuid, a key or a word this
# module wrote, run against a throwaway cluster.

from __future__ import annotations

import json
import subprocess
import threading
import time
import uuid
from collections.abc import Iterator

import control_cluster as cc
import pytest

from app import operations

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

#: The reconciler's functions: executable by no role (D2093).
RECONCILER = {
    "control_claim_operation",
    "control_advance_operation",
    "control_finish_operation",
    "control_interrupted_operations",
    "control_record_slots",
    "control_mark_deleted",
    "control_adopt_project",
    "control_registry_rows",
}

#: How long claimer A holds its claim open, and when B starts (rig 38f).
HOLD_SECONDS = 2.0
B_STARTS_AFTER = 0.3
#: B, not waiting, returned in 0.13-0.17 s in rig 38f; waiting, 1.84-1.87 s.
NOT_WAITING_BOUND = 1.0
ROUNDS = 3


@pytest.fixture(scope="module")
def cluster() -> Iterator[cc.ControlCluster]:
    try:
        with cc.control_cluster() as started:
            yield started
    except RuntimeError as error:
        pytest.skip(str(error))


@pytest.fixture(scope="module")
def org(cluster: cc.ControlCluster) -> tuple[str, str]:
    """An account and its organisation, written as root writes them."""
    user = str(uuid.uuid4())
    cluster.query(
        "INSERT INTO app.control_accounts (user_id, username, display_name) "
        f"VALUES ('{user}', 'claim-{user[:8]}', 'Claim')"
    )
    organization = cluster.query(
        "INSERT INTO app.control_organizations (name, created_by) "
        f"VALUES ('claims', '{user}') RETURNING id"
    )[0]
    return user, organization


def _pending(cluster: cc.ControlCluster, org: tuple[str, str], count: int) -> None:
    """`count` pending rows, distinct creation times, after closing every open one."""
    user, organization = org
    cluster.query(
        "UPDATE app.control_operations SET status = 'cancelled', finished_at = now() "
        "WHERE status = 'pending'"
    )
    cluster.query(
        "UPDATE app.control_operations SET status = 'failed', error_code = 'interrupted', "
        "finished_at = now() WHERE status = 'running'"
    )
    cluster.query(
        "INSERT INTO app.control_operations "
        "(organization_id, type, requested_by, arguments, created_at) "
        f"SELECT '{organization}', 'project.sleep', '{user}', '{{}}'::jsonb, clock_timestamp() "
        f"FROM generate_series(1, {count})"
    )


def _claim(cluster: cc.ControlCluster, worker: str, *, hold: float = 0.0) -> tuple[str, float]:
    """One claim in its own transaction, held `hold` seconds; (id or '', seconds)."""
    held = f"SELECT pg_sleep({hold}); " if hold else ""
    started = time.monotonic()
    done = subprocess.run(
        ["docker", "exec", "-i", cluster.name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
         "-U", "postgres", "-d", cluster.database],
        input=f"BEGIN; SELECT id FROM app.control_claim_operation('{worker}'); {held}COMMIT;",
        capture_output=True, text=True, timeout=60, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    return (lines[0] if lines else ""), time.monotonic() - started


def _overlapping(cluster: cc.ControlCluster) -> tuple[tuple[str, float], tuple[str, float]]:
    """A claims and holds; B claims 0.3 s later. ((A's id, s), (B's id, s))."""
    results: dict[str, tuple[str, float]] = {}

    def first() -> None:
        results["A"] = _claim(cluster, "worker-a", hold=HOLD_SECONDS)

    thread = threading.Thread(target=first)
    thread.start()
    time.sleep(B_STARTS_AFTER)
    results["B"] = _claim(cluster, "worker-b")
    thread.join()
    return results["A"], results["B"]


def test_the_claim_functions_are_executable_by_no_role(cluster: cc.ControlCluster) -> None:
    """Not the identity service, not a request role, not PUBLIC (D2093)."""
    names = ", ".join(f"'{name}'" for name in sorted(RECONCILER))
    for suffix, role in sorted(cluster.roles.items()):
        if suffix == "object_owner":
            continue
        executable = cluster.query(
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            f"WHERE n.nspname = 'app' AND p.proname IN ({names}) "
            f"AND has_function_privilege('{role}', p.oid, 'EXECUTE')"
        )
        assert executable == [], (suffix, executable)
    found = cluster.query(
        "SELECT DISTINCT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        f"WHERE n.nspname = 'app' AND p.proname IN ({names}) AND p.prosecdef = false"
    )
    assert set(found) == RECONCILER, "every reconciler function exists and is SECURITY INVOKER"
    # And the identity service is refused one when it tries.
    assert "permission denied" in cluster.refused("SELECT * FROM app.control_claim_operation('x')")


def test_two_claimers_get_distinct_rows(cluster: cc.ControlCluster, org: tuple[str, str]) -> None:
    """Overlapping claims take different rows, each claimed once (D2191)."""
    _pending(cluster, org, 2 * ROUNDS + 2)
    seen: list[str] = []
    for _ in range(ROUNDS):
        (a, _), (b, _) = _overlapping(cluster)
        assert a and b, (a, b)
        assert a != b, f"two claimers took the same row {a}"
        seen += [a, b]
    assert len(set(seen)) == len(seen)
    attempts = cluster.query(
        "SELECT attempt FROM app.control_operations WHERE status = 'running' ORDER BY 1"
    )
    assert set(attempts) == {"1"}, attempts


def test_a_claimer_does_not_wait_for_an_open_claim(
    cluster: cc.ControlCluster, org: tuple[str, str]
) -> None:
    """While A holds its claim open 2 s, B returns at once with another row."""
    _pending(cluster, org, 2 * ROUNDS + 2)
    for _ in range(ROUNDS):
        (a, held), (b, waited) = _overlapping(cluster)
        assert a and b and a != b, (a, b)
        assert held >= HOLD_SECONDS, held
        assert waited < NOT_WAITING_BOUND, f"B waited {waited:.2f} s for A's open claim"


def test_nothing_is_claimed_when_nothing_is_pending(
    cluster: cc.ControlCluster, org: tuple[str, str]
) -> None:
    _pending(cluster, org, 0)
    assert _claim(cluster, "idle")[0] == ""
    # Control: one pending row is claimed, once.
    _pending(cluster, org, 1)
    assert _claim(cluster, "busy")[0]
    assert _claim(cluster, "busy")[0] == ""


def test_an_interrupted_operation_is_finished_once_and_never_rewritten(
    cluster: cc.ControlCluster, org: tuple[str, str]
) -> None:
    """D2152: a row left `running` is listed as interrupted and finished
    `failed interrupted` naming its step; a finished row refuses a second
    finish, and so does a row nobody claimed."""
    _pending(cluster, org, 2)
    claimed, _ = _claim(cluster, "crashed")
    cluster.query(f"SELECT app.control_advance_operation('{claimed}', 'deploy-1', 10)")
    interrupted = cluster.query(
        "SELECT id, step, attempt FROM app.control_interrupted_operations()"
    )
    assert interrupted == [f"{claimed}|deploy-1|1"], interrupted

    cluster.query(
        f"SELECT app.control_finish_operation('{claimed}', 'failed', 'interrupted', "
        '\'{"step": "deploy-1"}\'::jsonb)'
    )
    assert cluster.query(
        "SELECT status, error_code, result::text FROM app.control_operations "
        f"WHERE id = '{claimed}'"
    ) == ['failed|interrupted|{"step": "deploy-1"}']
    assert cluster.query("SELECT count(*) FROM app.control_interrupted_operations()") == ["0"]

    again = cluster.run(
        f"SELECT app.control_finish_operation('{claimed}', 'succeeded', NULL, NULL)"
    )
    assert again.returncode != 0 and "AP409: not_running" in again.stderr
    pending = cluster.query("SELECT id FROM app.control_operations WHERE status = 'pending'")[0]
    unclaimed = cluster.run(
        f"SELECT app.control_finish_operation('{pending}', 'succeeded', NULL, NULL)"
    )
    assert unclaimed.returncode != 0 and "AP409: not_running" in unclaimed.stderr
    # A failure must name its code, and a success must not.
    claimed, _ = _claim(cluster, "honest")
    for status, code in (("failed", "NULL"), ("succeeded", "'operation_failed'")):
        refused = cluster.run(
            f"SELECT app.control_finish_operation('{claimed}', '{status}', {code}, NULL)"
        )
        assert refused.returncode != 0 and "AP422: invalid_outcome" in refused.stderr, status
    # Control: the honest finish of the same row is accepted.
    cluster.query(f"SELECT app.control_finish_operation('{claimed}', 'succeeded', NULL, NULL)")


def test_a_result_member_the_type_does_not_declare_is_refused(
    cluster: cc.ControlCluster, org: tuple[str, str]
) -> None:
    """D2151: the set's members equal `operations.RESULT_MEMBERS`, and a finish
    naming any other is refused; only a succeeded export carries a secret."""
    for kind, members in sorted(operations.RESULT_MEMBERS.items()):
        declared = cluster.query(f"SELECT unnest(app.control_result_members('{kind}')) ORDER BY 1")
        assert declared == sorted(members), kind

    _pending(cluster, org, 1)
    claimed, _ = _claim(cluster, "members")
    refused = cluster.run(
        f"SELECT app.control_finish_operation('{claimed}', 'succeeded', NULL, "
        '\'{"steps": [], "download_url": "https://x.invalid/"}\'::jsonb)'
    )
    assert refused.returncode != 0 and "AP422: undeclared_result" in refused.stderr
    secret = cluster.run(
        f"SELECT app.control_finish_operation('{claimed}', 'succeeded', NULL, NULL, "
        "'https://x.invalid/')"
    )
    assert secret.returncode != 0 and "control_operations_secret_only_on_export" in secret.stderr
    # Control: the declared members alone are accepted.
    cluster.query(
        f"SELECT app.control_finish_operation('{claimed}', 'succeeded', NULL, "
        '\'{"steps": [{"step": "stop", "seconds": 3}]}\'::jsonb)'
    )


def test_the_slot_reading_is_replaced_whole(cluster: cc.ControlCluster) -> None:
    """D2160: what the reconciler last observed, written whole; an element
    carrying anything but key, state and region is refused, writing nothing."""
    first = [
        {"key": "slot1-prod", "state": "ready", "region_id": "eu-hel-1"},
        {"key": "slot2-prod", "state": "consumed", "region_id": "eu-hel-1"},
    ]
    assert cluster.query(f"SELECT app.control_record_slots('{json.dumps(first)}'::jsonb)") == ["2"]
    second = [{"key": "slot2-prod", "state": "consumed", "region_id": "eu-hel-1"}]
    cluster.query(f"SELECT app.control_record_slots('{json.dumps(second)}'::jsonb)")
    assert cluster.query("SELECT key, state FROM app.control_slots") == ["slot2-prod|consumed"]

    for bad in (
        [{"key": "slot1-prod", "state": "ready", "path": "/etc"}],
        [{"key": "slot1-prod", "state": "free"}],
        {"key": "slot1-prod"},
    ):
        refused = cluster.run(f"SELECT app.control_record_slots('{json.dumps(bad)}'::jsonb)")
        assert refused.returncode != 0, bad
    assert cluster.query("SELECT key, state FROM app.control_slots") == ["slot2-prod|consumed"]
