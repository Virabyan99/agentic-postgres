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

**The Python half** (Run 6): `bin/reconciler.py` itself against the cluster --
its `Control` reaching the database through the real `container_exec.run`, its
`bin/` commands replaced by a recorder (`test_reconciler_dispatch.py`'s). A
creation killed mid-step leaves its row `running`; the next start finishes it
`failed interrupted` naming the step, quarantines its slot, and runs nothing for
it again (D2152).
"""

# ruff: noqa: S608 -- every interpolated value is a uuid, a key or a word this
# module wrote, run against a throwaway cluster.

from __future__ import annotations

import importlib.util
import json
import subprocess
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import control_cluster as cc
import pytest
import yaml

from agentic_postgres import REPO_ROOT, host_config, slot
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


# ---------------------------------------------------------------------------
# The Python half: bin/reconciler.py against the cluster (Run 6)
# ---------------------------------------------------------------------------

HOST = REPO_ROOT / "host.example.yaml"
SLOT = "slot1-dev"
CREATE_ARGUMENTS = {
    "name": "Interrupted",
    "profile": "small",
    "admin_username": "ada.admin",
    "handoff_sha256": "0" * 64,
}


class Killed(BaseException):
    """What a SIGKILL looks like from inside: nothing after it runs."""


#: The real one: `docker exec` -- the reconciler's path to this cluster through
#: `container_exec.run` -- passes through the stand-in below untouched.
_RUN = subprocess.run


class Commands:
    """`subprocess.run`'s stand-in for the `bin/` commands: records each one;
    raises `Killed` at `kill_at` (a command's file name), exit 0 otherwise."""

    def __init__(self, kill_at: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.kill_at = kill_at

    def __call__(self, argv: list[str], **kwargs: Any) -> Any:
        if argv[0] == "docker":
            return _RUN(argv, **kwargs)
        self.calls.append(list(argv))
        if Path(argv[0]).name == self.kill_at:
            raise Killed(argv[0])
        out = "{}" if kwargs.get("capture_output") else None
        return subprocess.CompletedProcess(argv, 0, out, "" if out is not None else None)


@pytest.fixture
def reconciler(cluster: cc.ControlCluster, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """`bin/reconciler.py` pointed at this cluster and at a prepared slot the
    proof owns; its commands replaced (`reconciler.commands`)."""
    spec = importlib.util.spec_from_file_location(
        "apg_reconciler_claim", REPO_ROOT / "bin" / "reconciler.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("STATE_ROOT", "SLOT_ROOT", "SECRET_ROOT", "LOG_ROOT", "RUN_ROOT"):
        monkeypatch.setattr(module, name, tmp_path / name.lower())
    monkeypatch.setattr(module, "HOST_MANIFEST", HOST)
    monkeypatch.setattr(module, "require_root", lambda: None)
    monkeypatch.setattr(module, "checkout_owner", lambda checkout=None: (1000, 1000))
    monkeypatch.setattr(module, "checkout_reading", lambda owner, checkout=None: ("a" * 40, ""))
    monkeypatch.setattr(module, "dns_reading", lambda domain, expected: (True, "recorded"))
    monkeypatch.setattr(
        module, "control_target", lambda: module.Control(cluster.name, cluster.database)
    )

    host = host_config.load_host_manifest(HOST)
    (entry,) = [e for e in host_config.declared_slots(host) if e.key == SLOT]
    directory = module.SLOT_ROOT / SLOT
    directory.mkdir(mode=0o700, parents=True)
    (directory / slot.MANIFEST).write_text(
        yaml.safe_dump(slot.slot_manifest(host, entry), sort_keys=False), "utf-8"
    )
    state = module.STATE_ROOT / SLOT
    state.mkdir(parents=True)
    (state / "bootstrap-state.json").write_text("{}", "utf-8")
    generation = module.SECRET_ROOT / SLOT / "generations" / "g1"
    generation.mkdir(parents=True)
    (generation / "manifest.json").write_text("{}", "utf-8")
    (module.SECRET_ROOT / SLOT / "active-secret-generation.json").write_text(
        '{"generation_id": "g1"}', "utf-8"
    )

    def commands(recorder: Commands) -> Commands:
        monkeypatch.setattr(module.subprocess, "run", recorder)
        return recorder

    module.commands = commands
    return module


def _create(cluster: cc.ControlCluster, org: tuple[str, str]) -> str:
    """One pending `project.create`, after closing every open row."""
    _pending(cluster, org, 0)
    user, organization = org
    return cluster.query(
        "INSERT INTO app.control_operations (organization_id, type, requested_by, arguments) "
        f"VALUES ('{organization}', 'project.create', '{user}', "
        f"'{json.dumps(CREATE_ARGUMENTS)}'::jsonb) RETURNING id"
    )[0]


def test_an_interrupted_creation_fails_and_quarantines_its_slot_never_resumed(
    cluster: cc.ControlCluster, org: tuple[str, str], reconciler: Any
) -> None:
    """D2152 against the real functions: killed in its first deploy, the
    creation's row stays `running` at `deploy-1` with its slot's key; the next
    start finishes it `failed interrupted {"step": "deploy-1"}`, attempt 1,
    quarantines the slot by the id its allocation marker carries, records the
    slot `quarantined` -- and runs nothing for it again."""
    created = _create(cluster, org)
    killed = reconciler.commands(Commands(kill_at="deploy.sh"))
    with pytest.raises(Killed):
        reconciler.main(["once"])
    assert [Path(argv[0]).name for argv in killed.calls] == ["admit.sh", "deploy.sh"]
    assert cluster.query(
        "SELECT status, step, project_key, attempt FROM app.control_operations "
        f"WHERE id = '{created}'"
    ) == [f"running|deploy-1|{SLOT}|1"]
    marker = reconciler.SLOT_ROOT / SLOT / slot.ALLOCATED
    assert marker.read_text("utf-8").strip() == created

    restarted = reconciler.commands(Commands())
    assert reconciler.main(["once"]) == 0
    assert restarted.calls == [], "nothing was run again for the interrupted creation"
    assert cluster.query(
        "SELECT status, error_code, result::text, attempt FROM app.control_operations "
        f"WHERE id = '{created}'"
    ) == ['failed|interrupted|{"step": "deploy-1"}|1']
    quarantined = reconciler.SLOT_ROOT / SLOT / slot.QUARANTINED
    assert quarantined.read_text("utf-8").strip() == created
    assert cluster.query(f"SELECT state FROM app.control_slots WHERE key = '{SLOT}'") == [
        "quarantined"
    ]


def test_a_result_reaches_the_control_database_unaltered(
    cluster: cc.ControlCluster, org: tuple[str, str], reconciler: Any
) -> None:
    """Every value the reconciler sends is set on psql's stdin (D2154); a
    quote, a backslash, a colon and a newline arrive as they were sent."""
    _pending(cluster, org, 1)
    reconciler.commands(Commands())
    control = reconciler.Control(cluster.name, cluster.database)
    owner = reconciler.Reconciler(control, {}, (1000, 1000), ("a" * 40, ""))
    claimed = owner.claim()
    assert claimed is not None and claimed["type"] == "project.sleep"
    reason = "it's a \\ back:slash :'quoted' and\na second line"
    owner.finish(claimed["id"], "failed", "operation_failed", {"reason": reason})
    assert cluster.query(
        "SELECT status, error_code, result ->> 'reason' = $r$" + reason + "$r$ "
        f"FROM app.control_operations WHERE id = '{claimed['id']}'"
    ) == ["failed|operation_failed|t"]
    assert owner.claim() is None
