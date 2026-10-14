"""A branch's expiry, the reconciler's half, against a real cluster (ADR 0272,
rig 40d; BR-TTL-001).

`bin/reconciler.py` itself: its `record_branches` reads each `branch.json` under
a branch root this module owns and records it through `control_record_branches`;
its `request_expiries` names each READY branch past its recorded expiry to
`control_request_expiry`, which decides -- ONE `branch.delete`, `origin =
expiry`, on behalf of the member whose operation set the expiry, and nothing
while any operation for the project is open. Both functions are granted to
nobody; the reconciler calls them as the superuser, through the real
`container_exec.run`, as it does on the host. A project has no expiry: nothing
the loop writes is ever anything but a branch's deletion.

The route's bounds (15 minutes to 7 days) are `test_control_branches`'.
"""

# ruff: noqa: S608 -- every interpolated value is a uuid, a key or a name this
# module wrote, run against a throwaway cluster.

from __future__ import annotations

import importlib.util
import json
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import control_cluster as cc
import pytest

from agentic_postgres import REPO_ROOT, branch_record

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]


@pytest.fixture(scope="module")
def cluster() -> Iterator[cc.ControlCluster]:
    try:
        with cc.control_cluster() as started:
            yield started
    except RuntimeError as error:
        pytest.skip(str(error))


class Project:
    """One adopted project, its owner and the member who sets an expiry."""

    def __init__(self, cluster: cc.ControlCluster) -> None:
        tag = uuid.uuid4().hex[:8]
        self.owner, self.member = str(uuid.uuid4()), str(uuid.uuid4())
        for user, role in ((self.owner, "owner"), (self.member, "member")):
            cluster.query(
                "INSERT INTO app.control_accounts (user_id, username, display_name) "
                f"VALUES ('{user}', 'ttl-{role}-{tag}', 'Expiry')"
            )
        self.organization = cluster.query(
            "INSERT INTO app.control_organizations (name, created_by) "
            f"VALUES ('ttl-{tag}', '{self.owner}') RETURNING id"
        )[0]
        self.key = f"t{tag}-prod"
        cluster.query(
            f"SELECT app.control_adopt_project('{self.key}', '{self.organization}', "
            f"'t{tag}', 'prod', '{self.key}.test', '1.18.0', 'abc')"
        )


@pytest.fixture
def project(cluster: cc.ControlCluster) -> Project:
    return Project(cluster)


@pytest.fixture
def reconciler(cluster: cc.ControlCluster, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """`bin/reconciler.py`'s `Reconciler`, its branch root this proof's own."""
    spec = importlib.util.spec_from_file_location(
        "apg_reconciler_expiry", REPO_ROOT / "bin" / "reconciler.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "BRANCH_ROOT", tmp_path / "branches")
    control = module.Control(cluster.name, cluster.database)
    owner = module.Reconciler(control, {}, (1000, 1000), ("a" * 40, ""))
    owner.root = tmp_path / "branches"
    return owner


def _stamp(delta: timedelta) -> str:
    return (datetime.now(UTC) + delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def _branch(
    reconciler: Any,
    project: Project,
    *,
    name: str = "dev",
    state: str = "ready",
    expires: timedelta | None = timedelta(minutes=-1),
) -> None:
    """What `branch-runtime.sh` leaves: one `branch.json`, then the loop's reading."""
    now = _stamp(timedelta(0))
    record = branch_record.Record(
        project_key=project.key,
        branch=name,
        state=state,
        operation=str(uuid.uuid4()),
        requested_point=None,
        reached_point=now,
        timeline=2,
        parent_commit="a" * 40,
        pool_host=f"pool.{name}.{project.key}.test",
        direct_host=f"direct.{name}.{project.key}.test",
        expires_at=None if expires is None else _stamp(expires),
        expires_for=None if expires is None else project.member,
        unreclaimable_mb=640,
        created_at=now,
        updated_at=now,
    )
    branch_record.write(branch_record.record_path(project.key, name, root=reconciler.root), record)
    reconciler.record_branches()


def _requests(cluster: cc.ControlCluster, project: Project) -> list[str]:
    return cluster.query(
        "SELECT type || '|' || origin || '|' || status || '|' || requested_by || '|' "
        "|| arguments::text FROM app.control_operations "
        f"WHERE project_key = '{project.key}' ORDER BY created_at"
    )


def test_an_expired_branch_is_deleted_by_one_request(
    cluster: cc.ControlCluster, project: Project, reconciler: Any
) -> None:
    """Rig 40d: a ready branch past its expiry is ONE pending `branch.delete`
    naming it; the loop's next pass, with that deletion open, requests nothing."""
    _branch(reconciler, project)
    assert cluster.query(
        f"SELECT state FROM app.control_branches WHERE project_key = '{project.key}'"
    ) == ["ready"]
    reconciler.request_expiries()
    reconciler.request_expiries()
    (request,) = _requests(cluster, project)
    kind, origin, status, _, arguments = request.split("|")
    assert (kind, origin, status) == ("branch.delete", "expiry", "pending"), request
    assert json.loads(arguments) == {"branch": "dev"}


def test_the_request_names_the_member_who_set_the_expiry(
    cluster: cc.ControlCluster, project: Project, reconciler: Any
) -> None:
    """ADR 0272: the deletion is requested on behalf of the member recorded in
    the branch's `expires_for` -- never the organisation's owner, never a
    member the reconciler names: its statement carries the key and the branch
    and nothing else."""
    from agentic_postgres import reconciler_dispatch as dispatch

    assert re.findall(r":'([a-z_]+)'", dispatch.REQUEST_EXPIRY_SQL) == ["key", "branch"]
    _branch(reconciler, project)
    reconciler.request_expiries()
    (request,) = _requests(cluster, project)
    assert request.split("|")[3] == project.member != project.owner


def test_an_open_operation_defers_the_expiry(
    cluster: cc.ControlCluster, project: Project, reconciler: Any
) -> None:
    """Rig 40d: while any operation for the project is pending or running the
    expiry writes nothing; the first pass after it finishes requests the one
    deletion."""
    opened = cluster.query(
        "INSERT INTO app.control_operations (organization_id, project_key, type, "
        f"requested_by, arguments) VALUES ('{project.organization}', '{project.key}', "
        f"'project.sleep', '{project.owner}', '{{}}'::jsonb) RETURNING id"
    )[0]
    _branch(reconciler, project)
    for status in ("pending", "running"):
        cluster.query(
            f"UPDATE app.control_operations SET status = '{status}' WHERE id = '{opened}'"
        )
        reconciler.request_expiries()
        assert len(_requests(cluster, project)) == 1, status
    cluster.query(
        "UPDATE app.control_operations SET status = 'succeeded', finished_at = now() "
        f"WHERE id = '{opened}'"
    )
    reconciler.request_expiries()
    assert [r.split("|")[:2] for r in _requests(cluster, project)] == [
        ["project.sleep", "member"],
        ["branch.delete", "expiry"],
    ]


def test_a_project_expiry_is_still_never_a_trigger(
    cluster: cc.ControlCluster, project: Project, reconciler: Any
) -> None:
    """ADR 0272: only a READY branch PAST its expiry is ever requested -- not
    one with no expiry, not one whose expiry is ahead, not a stopped one --
    and `origin = expiry` on any type but `branch.delete` is refused by the
    table, so nothing the loop writes can retire a project."""
    _branch(reconciler, project, name="noexpiry", expires=None)
    _branch(reconciler, project, name="ahead", expires=timedelta(hours=2))
    _branch(reconciler, project, name="stopped", state="stopped")
    reconciler.request_expiries()
    assert _requests(cluster, project) == []
    forged = cluster.run(
        "INSERT INTO app.control_operations (organization_id, project_key, type, status, "
        f"requested_by, arguments, origin) VALUES ('{project.organization}', '{project.key}', "
        f"'project.delete', 'pending', '{project.member}', '{{}}', 'expiry')"
    )
    assert forged.returncode != 0
    assert "control_operations_expiry_deletes_a_branch" in forged.stderr
