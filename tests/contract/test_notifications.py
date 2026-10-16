"""In-app notifications, written where an operation ends (Session 41, ADR 0275, D2526).

`app.control_finish_operation` -- the one place every operation ends -- writes
ONE notification in its own transaction, from a fixed template of the type, the
project key, the origin and the error code. It never interpolates the result,
the result secret (an export's download URL, ADR 0259) or any caller value. Its
body is 0004's byte for byte plus one block between `-- 0008:` markers, which
`test_the_finish_body_is_unchanged_but_for_the_insert` holds. A limit notice is
written by the sampler at most once per entitlement, organisation and UTC day.
A foreign organisation and a missing one read the same refusal.
"""

# ruff: noqa: S608 -- every interpolated value is a uuid or a key this module made.

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterator
from typing import Any

import control_cluster as cc
import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

TEMPLATES = REPO_ROOT / "projects" / "control" / "migrations" / "templates"
SECRET_URL = "https://exports.example.test/slot-x/dump.sql.gz?X-Amz-Signature=deadbeef" + "0" * 40


@pytest.fixture(scope="module")
def drive(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    """One control cluster and the control mode over it (Run 5's routes)."""
    try:
        with cc.control_cluster() as started:
            with cc.control_app(
                started, tmp_path_factory.mktemp("control-notifications")
            ) as driver:
                yield driver
    except RuntimeError as error:
        pytest.skip(str(error))


@pytest.fixture(scope="module")
def cluster(drive: Any) -> cc.ControlCluster:
    return drive.cluster


def _people(drive: Any, label: str) -> dict[str, Any]:
    """A route caller's organisation: an owner, a member, a viewer, their tokens,
    and one adopted project."""
    tag = f"{label}-{uuid.uuid4().hex[:6]}"
    people: dict[str, Any] = {"tokens": {}, "users": {}}
    owner = drive.account(f"{tag}-owner")
    people["id"] = drive.organization(owner, tag)
    people["tokens"]["owner"] = drive.token(f"{tag}-owner", drive.enable_factor(owner))
    for role in ("member", "viewer"):
        user = drive.account(f"{tag}-{role}")
        drive.member(people["id"], user, role)
        people["users"][role] = user
        people["tokens"][role] = drive.token(f"{tag}-{role}")
    key = f"r{uuid.uuid4().hex[:8]}-prod"
    drive.cluster.query(
        f"SELECT app.control_adopt_project('{key}', '{people['id']}', '{key[:9]}', 'prod', "
        f"'{key}.test', '1.19.0', 'abc')"
    )
    people["project"] = key
    return people


class Org:
    def __init__(self, cluster: cc.ControlCluster) -> None:
        self.cluster = cluster
        tag = uuid.uuid4().hex[:8]
        self.user = str(uuid.uuid4())
        cluster.query(
            "INSERT INTO app.control_accounts (user_id, username, display_name) "
            f"VALUES ('{self.user}', 'n-{tag}', 'N')"
        )
        self.id = cluster.query(
            f"INSERT INTO app.control_organizations (name, created_by) VALUES ('n {tag}', "
            f"'{self.user}') RETURNING id"
        )[0]
        cluster.query(
            "INSERT INTO app.control_memberships (organization_id, user_id, role) "
            f"VALUES ('{self.id}', '{self.user}', 'owner')"
        )
        self.key = f"n{tag}-prod"
        cluster.query(
            f"SELECT app.control_adopt_project('{self.key}', '{self.id}', 'n{tag}', 'prod', "
            f"'{self.key}.test', '1.19.0', 'abc')"
        )

    def running(self, kind: str, origin: str = "member", arguments: str = "{}") -> str:
        return self.cluster.query(
            "INSERT INTO app.control_operations (organization_id, project_key, type, status, "
            "requested_by, arguments, started_at, claimed_by, attempt, origin) VALUES "
            f"('{self.id}', '{self.key}', '{kind}', 'running', '{self.user}', '{arguments}', "
            f"now(), 'proof', 1, '{origin}') RETURNING id"
        )[0]

    def notifications(self) -> list[str]:
        return self.cluster.as_service(
            "SELECT kind || '|' || coalesce(project_key, '-') || '|' || text FROM "
            f"app.control_list_notifications('{self.user}', '{self.id}', 200)"
        )


def _finish(cluster: cc.ControlCluster, op: str, status: str, code: str | None = None,
            result: dict[str, Any] | None = None, secret: str | None = None) -> None:  # fmt: skip
    code_sql = "NULL" if code is None else f"'{code}'"
    result_sql = "NULL" if result is None else f"'{json.dumps(result)}'::jsonb"
    secret_sql = "NULL" if secret is None else f"'{secret}'"
    cluster.query(
        f"SELECT app.control_finish_operation('{op}', '{status}', {code_sql}, {result_sql}, "
        f"{secret_sql})"
    )


def test_a_finished_operation_writes_one_notification(cluster: cc.ControlCluster) -> None:
    """Each end of an operation writes exactly one row, its kind read from the
    outcome and the origin; a finish that is rolled back writes none."""
    org = Org(cluster)
    _finish(cluster, org.running("project.sleep"), "succeeded")
    _finish(cluster, org.running("project.wake"), "failed", "operation_failed")
    cluster.query(
        "UPDATE app.control_projects SET idle_sleep_minutes = 15, "
        f"idle_sleep_set_by = '{org.user}' WHERE key = '{org.key}'"
    )
    _finish(cluster, org.running("project.sleep", origin="idle"), "succeeded")
    _finish(cluster, org.running("branch.delete", "expiry", '{"branch": "dev"}'), "succeeded")
    listed = org.notifications()
    assert sorted(listed) == sorted([
        f"operation_succeeded|{org.key}|project.sleep on {org.key} succeeded",
        f"operation_failed|{org.key}|project.wake on {org.key} failed (operation_failed)",
        f"idle_sleep|{org.key}|project.sleep on {org.key} succeeded (requested because it was "
        "idle for 15 minutes; while it sleeps its backups stop; wake it with apg project wake)",
        f"branch_expired|{org.key}|branch.delete on {org.key} succeeded (requested because the "
        "branch expired)",
    ]), listed  # fmt: skip
    op = org.running("project.sleep")
    rolled = cc.docker(
        "exec", "-i", cluster.name, "psql", "-qtA", "-v", "ON_ERROR_STOP=1", "-U", "postgres",
        "-d", cluster.database,
        stdin=f"BEGIN;\nSELECT app.control_finish_operation('{op}', 'succeeded', NULL, NULL);\n"
              "ROLLBACK;\n",
    )  # fmt: skip
    assert rolled.returncode == 0, rolled.stderr
    assert len(org.notifications()) == 4


def test_no_template_carries_a_result_member(cluster: cc.ControlCluster) -> None:
    """An export finishes with its result members and its secret URL: the
    notification names neither (ADR 0259, D2526). And statically: the block the
    finish gained names no parameter but the status and the error code."""
    org = Org(cluster)
    result = {"sha256": "a" * 64, "size_bytes": 987654321, "expires_at": "2026-10-16T12:00:00Z"}
    _finish(cluster, org.running("project.export"), "succeeded", result=result, secret=SECRET_URL)
    (text,) = org.notifications()
    for value in (*map(str, result.values()), SECRET_URL, "exports.example.test", "X-Amz"):
        assert value not in text, (value, text)
    assert text == f"operation_succeeded|{org.key}|project.export on {org.key} succeeded"
    block = _marked_blocks(_function(TEMPLATES / "0008-control-plans-usage.sql", replace=True))
    assert block, "the finish's notification block was not found"
    for forbidden in ("p_result", "p_result_secret", "result", "arguments", "current_setting"):
        assert not re.search(rf"\b{forbidden}\b", _code(block)), forbidden


def _function(path: Any, *, replace: bool) -> str:
    text = path.read_text(encoding="utf-8")
    head = "CREATE OR REPLACE FUNCTION" if replace else "CREATE FUNCTION"
    start = text.index(f"{head} app.control_finish_operation(")
    end = text.index("$$;", start) + 3
    return text[start:end]


def _marked_blocks(text: str) -> str:
    marked = r"-- 0008: the notification \(ADR 0275\) --\n(.*?)-- 0008: end --\n"
    return "\n".join(re.findall(marked, text, flags=re.DOTALL))


def _code(text: str) -> str:
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def test_the_finish_body_is_unchanged_but_for_the_insert() -> None:
    """0008's finish is 0004's, byte for byte, once its two marked blocks are
    removed: the notification is the only thing the function gained."""
    before = _function(TEMPLATES / "0004-control-operations.sql", replace=False)
    after = _function(TEMPLATES / "0008-control-plans-usage.sql", replace=True)
    stripped = re.sub(
        r"  -- 0008: the notification \(ADR 0275\) --\n.*?  -- 0008: end --\n", "", after,
        flags=re.DOTALL,
    )  # fmt: skip
    assert after.count("-- 0008: end --") == 2, "both blocks are marked"
    assert stripped.replace("CREATE OR REPLACE FUNCTION", "CREATE FUNCTION", 1) == before


def test_a_limit_notice_is_daily(cluster: cc.ControlCluster) -> None:
    """At most one `limit_approaching` per entitlement, organisation and UTC day;
    another entitlement is its own notice; an unknown entitlement is refused;
    the identity service cannot write one."""
    org = Org(cluster)
    first = cluster.query(f"SELECT app.control_record_limit_notice('{org.key}', 'storage_gb')")
    again = cluster.query(
        f"SELECT coalesce(app.control_record_limit_notice('{org.key}', 'storage_gb')::text, 'NULL')"
    )
    other = cluster.query(
        f"SELECT app.control_record_limit_notice('{org.key}', 'agent_calls_per_day')"
    )
    assert first != ["NULL"] and again == ["NULL"] and other != ["NULL"]
    kinds = [row.split("|")[0] for row in org.notifications()]
    assert kinds == ["limit_approaching", "limit_approaching"], kinds
    assert (
        "AP422"
        in cluster.run(
            f"SELECT app.control_record_limit_notice('{org.key}', 'projects_active')"
        ).stderr
    )
    (held,) = cluster.query(
        f"SELECT has_function_privilege('{cluster.auth_role}', "
        "'app.control_record_limit_notice(text, text)', 'EXECUTE')"
    )
    assert held == "f"


def test_a_foreign_organization_reads_nothing(cluster: cc.ControlCluster) -> None:
    """A member of one organisation listing another's notifications, and anyone
    listing a missing organisation's, read the one `not_found`."""
    mine, theirs = Org(cluster), Org(cluster)
    _finish(cluster, theirs.running("project.sleep"), "succeeded")
    foreign = cluster.refused(
        f"SELECT * FROM app.control_list_notifications('{mine.user}', '{theirs.id}', 10)"
    )
    missing = cluster.refused(
        f"SELECT * FROM app.control_list_notifications('{mine.user}', '{uuid.uuid4()}', 10)"
    )
    assert "AP404: not_found" in foreign and "AP404: not_found" in missing, (foreign, missing)
    assert mine.notifications() == []


# ---------------------------------------------------------------------------
# The route (Run 5)
# ---------------------------------------------------------------------------


def test_the_notifications_route_lists_its_own_organizations(drive: Any) -> None:
    """`GET /v1/organizations/{organization}/notifications`: a viewer reads the
    organisation's newest first; a foreign organisation is `not_found`; the
    limit is bounded."""
    people, stranger = _people(drive, "notified"), _people(drive, "stranger")
    for kind in ("project.sleep", "project.wake"):
        op = drive.cluster.query(
            "INSERT INTO app.control_operations (organization_id, project_key, type, status, "
            "requested_by, arguments, started_at, claimed_by, attempt) VALUES "
            f"('{people['id']}', '{people['project']}', '{kind}', 'running', "
            f"'{people['users']['member']}', '{{}}', now(), 'proof', 1) RETURNING id"
        )[0]
        drive.cluster.query(f"SELECT app.control_finish_operation('{op}', 'succeeded', NULL, NULL)")
    path = f"/v1/organizations/{people['id']}/notifications"
    listed = drive.call("GET", path + "?limit=10", token=people["tokens"]["viewer"])
    assert listed.status_code == 200, listed.text
    texts = [n["text"] for n in listed.json()["notifications"]]
    assert texts == [f"project.wake on {people['project']} succeeded",
                     f"project.sleep on {people['project']} succeeded"], texts  # fmt: skip
    foreign = drive.call("GET", path, token=stranger["tokens"]["viewer"])
    assert (foreign.status_code, foreign.json()["error"]) == (404, "not_found")
    assert (
        drive.call("GET", path + "?limit=201", token=people["tokens"]["viewer"]).status_code == 422
    )
