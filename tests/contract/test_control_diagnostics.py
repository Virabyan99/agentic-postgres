"""The support bundle: the doctor's verdicts, recorded by the reconciler, read by a member.

Session 46 (ADR 0292, D2874, D2897, D2898). The control plane holds no
credential to the node (ADR 0246), so it never runs a doctor: the reconciler
runs `bin/doctor.py --project KEY --json` as root every
`DIAGNOSTICS_RECORD_SECONDS`, reduces each check to `{name, verdict, detail}`
in `reconciler_dispatch.diagnostics_reading` -- **the doctor's `evidence` never
leaves that function**, and a host path or an opaque run inside a `detail` is
replaced there -- and records the result through
`app.control_record_diagnostics`, granted to nobody. A member reads the
readings with the project's operations through `GET
/v1/projects/{key}/diagnostics`; a reading older than 1,800 s is `stale`, a
sleeping project one `asleep` row, no reading at all *could not be determined*
(ADR 0195) -- never a page of twelve passes nobody took.

The reduction and the document are pure and proved without a cluster; the
control set and the route against a real one (`control_cluster`), the
superuser playing the reconciler's call the way `test_control_branches`
plays `control_record_backups`. The reconciler's own pass is
`test_reconciler_dispatch.py`'s; the CLI's file is `test_control_cli.py`'s.
"""

# ruff: noqa: S608 -- every interpolated value is a uuid, a key or JSON this
# module wrote, run against a throwaway cluster.

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import control_cluster as cc
import pytest

from agentic_postgres import reconciler_dispatch
from app import control_service

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

KEY = "slot3-prod"
#: `test_doctor_redaction`'s shape of a planted value: a canary a reading must
#: never carry, in a check's evidence and in its detail.
CANARY = f"APG-SECRET-CANARY-{uuid.uuid4().hex}"
HOST_PATH = "/var/lib/docker/volumes/apg-slot3-prod_postgres-data/_data"


def _answer(**changes: Any) -> dict[str, Any]:
    """A doctor `--json` answer as `diagnosis.document` builds it: twelve
    checks, each with evidence -- three of them carrying what IR4 named (a
    mount, a lock holder, a URL) and one a planted canary."""
    checks = [
        {"name": "containers", "verdict": "ok", "detail": "12/12 running, none unhealthy",
         "evidence": {"expected": "12", "running": "12", "unhealthy": ""}},
        {"name": "route health", "verdict": "ok",
         "detail": "https://slot3.agenticpostgresql.com/api/app/health answered 200",
         "evidence": {"url": "https://slot3.agenticpostgresql.com/api/app/health",
                      "status": "200", "expected": "200"}},
        {"name": "tls", "verdict": "ok", "detail": "61d remaining (2026-12-24T10:00:00Z)",
         "evidence": {"days_remaining": "61"}},
        {"name": "database", "verdict": "ok", "detail": "the cluster and the pooler answered",
         "evidence": {"cluster_answered": "True", "pooler_answered": "True"}},
        {"name": "migrations", "verdict": "ok", "detail": "all 39 released migrations applied",
         "evidence": {"applied": "39", "released": "39"}},
        {"name": "backup repository", "verdict": "ok",
         "detail": "last full backup 2026-10-24T02:00:00Z",
         "evidence": {"reported_status": "ok", "last_full_backup_at": CANARY}},
        {"name": "wal archiver", "verdict": "ok", "detail": "last archived 2026-10-24 11:50:01",
         "evidence": {"failing": "False"}},
        {"name": "backup mirror", "verdict": "ok", "detail": "last copied 2026-10-24T04:41:38Z",
         "evidence": {"enabled": "True"}},
        {"name": "disk headroom", "verdict": "ok",
         "detail": f"81920 MiB free at {HOST_PATH}, cluster is 42 MiB (1950.5x)",
         "evidence": {"mount": HOST_PATH, "available_kb": "83886080", "cluster_kb": "43008"}},
        {"name": "capability drift", "verdict": "ok", "detail": "the plane matches the lock",
         "evidence": {"matches": "True"}},
        {"name": "agent record", "verdict": "warn", "detail": f"token {CANARY} in the record",
         "evidence": {"audit_rows": "0"}},
        {"name": "workflow", "verdict": "ok", "detail": "0 definitions; runs ; steps ",
         "evidence": {"heartbeat_holder": "auth-7f3c9a"}},
    ]  # fmt: skip
    answer = {"project_key": KEY, "observed_at": "2026-10-24T11:53:57Z", "worst": "warn",
              "exit_code": 6, "checks": checks}  # fmt: skip
    answer.update(changes)
    return answer


# ---------------------------------------------------------------------------
# The reduction (pure): verdicts in, evidence never out
# ---------------------------------------------------------------------------


def test_only_verdicts_are_recorded() -> None:
    """Each check becomes `{name, verdict, detail}` in the doctor's order and
    nothing else -- no `evidence` member at any depth, no `worst`, no
    `observed_at` (the control database stamps its own `read_at`)."""
    reading, why = reconciler_dispatch.diagnostics_reading(KEY, _answer())
    assert why is None and reading is not None, why
    assert set(reading) == {"project_key", "checks"} and reading["project_key"] == KEY
    assert [c["name"] for c in reading["checks"]] == [c["name"] for c in _answer()["checks"]]
    for check in reading["checks"]:
        assert set(check) == {"name", "verdict", "detail"}, check
    assert reading["checks"][10]["verdict"] == "warn"
    # A public route, a time and a count are kept as the doctor wrote them.
    assert reading["checks"][1]["detail"].startswith("https://slot3.agenticpostgresql.com/api/app")
    assert reading["checks"][2]["detail"] == "61d remaining (2026-12-24T10:00:00Z)"
    assert reading["checks"][0]["detail"] == "12/12 running, none unhealthy"


def test_a_planted_value_is_recorded_nowhere() -> None:
    """The canary in a check's evidence and in a detail, the mount in the disk
    check's detail and evidence, the lock holder: none in what is recorded.
    The disk check keeps its numbers -- the sentence is kept, the path is
    replaced inside it (D2897)."""
    reading, _ = reconciler_dispatch.diagnostics_reading(KEY, _answer())
    recorded = json.dumps(reading)
    for planted in (CANARY, HOST_PATH, "/var/lib/docker", "auth-7f3c9a", "83886080"):
        assert planted not in recorded, planted
    disk = reading["checks"][8]["detail"]
    assert disk == "81920 MiB free at [a host path], cluster is 42 MiB (1950.5x)", disk
    assert reading["checks"][10]["detail"] == "token [a value not shown] in the record"


def test_a_long_detail_is_bounded() -> None:
    long = _answer()
    long["checks"][3]["detail"] = "the cluster did not answer " + "x " * 400
    reading, _ = reconciler_dispatch.diagnostics_reading(KEY, long)
    assert len(reading["checks"][3]["detail"]) == reconciler_dispatch.DIAGNOSTIC_DETAIL_MAX


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"project_key": "slot9-prod"}, "another project"),
        ({"checks": []}, "no check"),
        ({"checks": "twelve"}, "shape"),
        ({"checks": [{"name": "tls", "verdict": "fine", "detail": "x"}]}, "verdict"),
        ({"checks": [{"name": "", "verdict": "ok", "detail": "x"}]}, "shape"),
        ({"checks": [{"name": "tls", "verdict": "ok", "detail": 3}]}, "shape"),
    ],
)
def test_an_answer_not_in_the_shape_asked_for_records_nothing(
    change: dict[str, Any], reason: str
) -> None:
    """ADR 0195: an answer that is not the doctor's document is no reading --
    `None` and the reason, never a partial set of checks. The control: the
    unchanged answer, in the same invocation, is a reading."""
    reading, why = reconciler_dispatch.diagnostics_reading(KEY, _answer(**change))
    assert reading is None and why is not None and reason in why, (reading, why)
    assert reconciler_dispatch.diagnostics_reading(KEY, _answer())[0] is not None
    assert reconciler_dispatch.diagnostics_reading(KEY, None)[0] is None


def test_a_sleeping_slot_is_one_reading_not_twelve() -> None:
    assert reconciler_dispatch.diagnostics_asleep(KEY) == {"project_key": KEY, "asleep": True}


# ---------------------------------------------------------------------------
# The document (pure): read, asleep, stale, nothing recorded
# ---------------------------------------------------------------------------

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
OPERATIONS = [
    {"project_key": KEY, "type": "project.create", "status": "succeeded", "error_code": None,
     "created_at": NOW - timedelta(days=2)},
    {"project_key": KEY, "type": "project.sleep", "status": "failed",
     "error_code": "operation_failed", "created_at": NOW - timedelta(hours=1)},
]  # fmt: skip


def _row(name: str, verdict: str, age: float, detail: str = "a sentence") -> dict[str, Any]:
    return {"check_name": name, "verdict": verdict, "detail": detail,
            "read_at": NOW - timedelta(seconds=age)}  # fmt: skip


def test_a_fresh_reading_is_read_with_its_ages_and_operations() -> None:
    rows = [_row("containers", "ok", 600), _row("tls", "warn", 600)]
    document = control_service.diagnostics_document(KEY, rows, OPERATIONS, NOW)
    assert document["status"] == "read" and document["project_key"] == KEY, document
    assert [c["name"] for c in document["checks"]] == ["containers", "tls"]
    assert all(c["stale"] is False and c["age_seconds"] == 600 for c in document["checks"])
    assert [o["type"] for o in document["operations"]] == ["project.create", "project.sleep"]
    assert document["operations"][1]["error_code"] == "operation_failed"
    assert set(document["operations"][0]) == {"type", "status", "error_code", "created_at"}


def test_an_old_reading_is_stale() -> None:
    """Older than 1,800 s (2 x 900): each old reading `stale: true`, its
    verdict unchanged, and the document says how old -- never `read`."""
    rows = [_row("containers", "ok", 1801), _row("tls", "ok", 1801)]
    document = control_service.diagnostics_document(KEY, rows, OPERATIONS, NOW)
    assert document["status"] == "stale", document
    assert all(c["stale"] is True and c["verdict"] == "ok" for c in document["checks"])
    assert "1801 seconds old" in document["reason"] and "1800" in document["reason"]
    # The control: 1,800 s exactly is not stale.
    fresh = control_service.diagnostics_document(KEY, [_row("tls", "ok", 1800)], [], NOW)
    assert fresh["status"] == "read" and fresh["checks"][0]["stale"] is False


def test_no_reading_is_said_never_an_empty_pass() -> None:
    document = control_service.diagnostics_document(KEY, [], OPERATIONS, NOW)
    assert document["status"] == "could_not_determine" and document["checks"] == []
    assert document["reason"] == "no reading has been recorded for this project yet"
    assert len(document["operations"]) == 2


def test_the_staleness_bound_is_two_of_the_reconcilers_intervals() -> None:
    """The API's `stale` bound is twice the interval the reconciler records at,
    read from both sides -- the reconciler's own constant, never a copy."""
    import importlib.util

    from agentic_postgres import REPO_ROOT
    from app import operations

    spec = importlib.util.spec_from_file_location(
        "apg_reconciler_s46", REPO_ROOT / "bin" / "reconciler.py"
    )
    assert spec is not None and spec.loader is not None
    reconciler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reconciler)
    assert reconciler.DIAGNOSTICS_RECORD_SECONDS == operations.DIAGNOSTICS_RECORD_SECONDS == 900
    assert control_service.DIAGNOSTICS_READING_MAX_AGE == timedelta(
        seconds=2 * reconciler.DIAGNOSTICS_RECORD_SECONDS
    )


def test_an_asleep_reading_is_named() -> None:
    rows = [
        _row("state", "asleep", 60, "the project sleeps; its checks run again once it is woken")
    ]
    document = control_service.diagnostics_document(KEY, rows, [], NOW)
    assert document["status"] == "asleep" and document["checks"][0]["verdict"] == "asleep"


# ---------------------------------------------------------------------------
# The control set and the route, against a real cluster
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def drive(tmp_path_factory: pytest.TempPathFactory) -> Any:
    try:
        with cc.control_cluster() as cluster:
            with cc.control_app(cluster, tmp_path_factory.mktemp("control-diagnostics")) as driver:
                yield driver
    except RuntimeError as exc:
        pytest.skip(str(exc))


def _org(drive: Any, label: str) -> dict[str, Any]:
    tag = f"{label}-{uuid.uuid4().hex[:6]}"
    people: dict[str, Any] = {"tokens": {}, "users": {}}
    owner = drive.account(f"{tag}-owner")
    people["users"]["owner"] = owner
    people["id"] = drive.organization(owner, tag)
    people["tokens"]["owner"] = drive.token(f"{tag}-owner", drive.enable_factor(owner))
    for role in ("member", "viewer"):
        user = drive.account(f"{tag}-{role}")
        drive.member(people["id"], user, role)
        people["users"][role] = user
        people["tokens"][role] = drive.token(f"{tag}-{role}")
    key = f"d{uuid.uuid4().hex[:8]}-prod"
    drive.cluster.query(
        f"SELECT app.control_adopt_project('{key}', '{people['id']}', '{key[:9]}', 'prod', "
        f"'{key}.test', '1.24.0', 'abc')"
    )
    people["project"] = key
    return people


def _record(drive: Any, readings: list[dict[str, Any]]) -> list[str]:
    """The reconciler's call, as the superuser makes it through `container_exec`."""
    text = json.dumps(readings).replace("'", "''")
    return drive.cluster.query(f"SELECT app.control_record_diagnostics('{text}'::jsonb)")


def _executable_by(cluster: cc.ControlCluster, role: str) -> set[str]:
    return set(
        cluster.query(
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'app' AND p.proname LIKE 'control\\_%diagnostic%' "
            f"AND has_function_privilege('{role}', p.oid, 'EXECUTE')"
        )
    )


def test_the_record_function_is_granted_to_nobody(drive: Any) -> None:
    """The writer is executable by no role but its owner -- not the identity
    service, not PUBLIC -- and the identity service executes exactly the
    member reader; neither table nor writer is reachable from a request role."""
    cluster = drive.cluster
    assert _executable_by(cluster, cluster.auth_role) == {"control_project_diagnostics"}
    for suffix, role in sorted(cluster.roles.items()):
        if suffix in {"auth_service", "object_owner"}:
            continue
        assert _executable_by(cluster, role) == set(), suffix
    assert "permission denied" in cluster.refused(
        "SELECT app.control_record_diagnostics('[]'::jsonb)", as_role=cluster.auth_role
    )
    assert "permission denied" in cluster.refused(
        "SELECT count(*) FROM app.control_diagnostic_readings", as_role=cluster.auth_role
    )


def test_the_writer_refuses_evidence_and_unknown_shapes(drive: Any) -> None:
    """The control set refuses what the reduction should never send: an
    `evidence` member, a verdict outside the vocabulary, a check with an extra
    key -- `AP422: invalid_readings`, nothing written. The control: the same
    project's well-formed reading is written."""
    key = _org(drive, "shape")["project"]
    good = {"name": "tls", "verdict": "ok", "detail": "61d remaining"}
    for bad in (
        [{"project_key": key, "checks": [{**good, "evidence": {"mount": HOST_PATH}}]}],
        [{"project_key": key, "checks": [{**good, "verdict": "fine"}]}],
        [{"project_key": key, "checks": [good], "worst": "ok"}],
        [{"project_key": key, "checks": []}],
    ):
        text = json.dumps(bad).replace("'", "''")
        # As the superuser, the reconciler's identity: the refusal is the
        # function's own, not a missing privilege.
        done = drive.cluster.run(f"SELECT app.control_record_diagnostics('{text}'::jsonb)")
        assert done.returncode != 0 and "AP422: invalid_readings" in done.stderr, (bad, done)
    assert drive.cluster.query(
        f"SELECT count(*) FROM app.control_diagnostic_readings WHERE project_key = '{key}'"
    ) == ["0"]
    assert _record(drive, [{"project_key": key, "checks": [good]}]) == ["1"]


def test_a_stopped_database_reads_asleep(drive: Any) -> None:
    """A sleeping slot is ONE row, `state` / `asleep`, its sentence the control
    set's -- and the next awake reading replaces the project's rows whole, so
    no old check lingers beside a new set (and the asleep row is gone)."""
    org = _org(drive, "asleep")
    key, member = org["project"], org["users"]["member"]
    _record(drive, [{"project_key": key, "checks": [
        {"name": "containers", "verdict": "ok", "detail": "12/12 running"},
        {"name": "tls", "verdict": "ok", "detail": "61d remaining"}]}])  # fmt: skip
    assert _record(drive, [{"project_key": key, "asleep": True}]) == ["1"]
    rows = drive.cluster.as_service(
        f"SELECT check_name, verdict FROM app.control_project_diagnostics('{member}', '{key}')"
    )
    assert rows == ["state|asleep"], rows
    _record(drive, [{"project_key": key, "checks": [
        {"name": "containers", "verdict": "problem", "detail": "11/12 running"}]}])  # fmt: skip
    rows = drive.cluster.as_service(
        f"SELECT check_name, verdict FROM app.control_project_diagnostics('{member}', '{key}')"
    )
    assert rows == ["containers|problem"], rows


def test_a_non_member_is_refused(drive: Any) -> None:
    """Member and above read; a viewer is `AP403`; a stranger and a missing
    project are the one `AP404` (D2053) -- in SQL, independent of the route."""
    org = _org(drive, "scope")
    key = org["project"]
    _record(drive, [{"project_key": key, "checks": [
        {"name": "tls", "verdict": "ok", "detail": "61d remaining"}]}])  # fmt: skip
    for role in ("owner", "member"):
        user = org["users"][role]
        assert drive.cluster.as_service(
            f"SELECT check_name FROM app.control_project_diagnostics('{user}', '{key}')"
        ) == ["tls"], role
    viewer = org["users"]["viewer"]
    assert "AP403" in drive.cluster.refused(
        f"SELECT * FROM app.control_project_diagnostics('{viewer}', '{key}')",
        as_role=drive.cluster.auth_role,
    )
    stranger = drive.account(f"stranger-{uuid.uuid4().hex[:6]}")
    for target in (key, "nothere-prod"):
        assert "AP404" in drive.cluster.refused(
            f"SELECT * FROM app.control_project_diagnostics('{stranger}', '{target}')",
            as_role=drive.cluster.auth_role,
        ), target


def test_the_route_serves_the_readings_and_the_operations(drive: Any) -> None:
    """`GET /v1/projects/{key}/diagnostics` through the app: no reading is
    `could_not_determine`; a recorded one is `read` with each check's age and
    the project's operations; a viewer is 403, a stranger's key 404, and a key
    -- even one holding `projects:read` -- is `human_session_required`."""
    org = _org(drive, "route")
    key, member = org["project"], org["tokens"]["member"]
    path = f"/v1/projects/{key}/diagnostics"
    none = drive.call("GET", path, token=member)
    assert none.status_code == 200, none.text
    assert none.json()["status"] == "could_not_determine" and none.json()["checks"] == []
    _record(drive, [{"project_key": key, "checks": [
        {"name": "containers", "verdict": "ok", "detail": "12/12 running"},
        {"name": "disk headroom", "verdict": "warn", "detail": "1 restore fits at [a host path]"},
    ]}])  # fmt: skip
    read = drive.call("GET", path, token=member).json()
    assert read["status"] == "read", read
    assert [(c["name"], c["verdict"]) for c in read["checks"]] == [
        ("containers", "ok"), ("disk headroom", "warn")]  # fmt: skip
    assert all(c["stale"] is False and c["age_seconds"] < 120 for c in read["checks"])
    assert isinstance(read["operations"], list)
    assert drive.call("GET", path, token=org["tokens"]["viewer"]).status_code == 403
    stranger = _org(drive, "stranger")
    assert drive.call("GET", path, token=stranger["tokens"]["member"]).status_code == 404
    minted = drive.call(
        "POST", f"/v1/organizations/{org['id']}/keys", token=member,
        body={"name": "automation", "scopes": ["projects:read"]},
    )  # fmt: skip
    assert minted.status_code == 201, minted.text
    keyed = drive.call("GET", path, token=minted.json()["key"])
    assert keyed.status_code == 403 and "human_session_required" in keyed.text, keyed.text
