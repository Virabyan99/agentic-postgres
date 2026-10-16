"""Idle sleep is a trigger, decided in the control database (Session 41, ADR 0276, D2525, D2539).

`app.control_request_idle_sleep`, granted to nobody, inserts ONE `project.sleep`
with `origin = 'idle'` on behalf of the member who set the project's idle-sleep
minutes -- and only over a window of samples that are all present (contiguous
within 1.5 x the 300 s interval, the first near the window's start, the last
near now), awake, with both signals READ and quiet: the edge's sub-400 counter
unmoved, and no customer-role activity inside the window. **No customer backend
is quiet** (Sheet E0: at rest a customer role has none, D2539); a failed read is
unread, and an unread sample is not idle. A decision that fails closed.
"""

# ruff: noqa: S608 -- every interpolated value is a uuid, a key or a number this module made.

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import control_cluster as cc
import pytest

from app import operations

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

QUIET = (840, 540, 240, 10)  # seconds ago: a full 15-minute window at 300 s


@pytest.fixture(scope="module")
def drive(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    """One control cluster and the control mode over it (Run 5's routes)."""
    try:
        with cc.control_cluster() as started:
            with cc.control_app(started, tmp_path_factory.mktemp("control-idle")) as driver:
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


class Project:
    """An adopted project with idle sleep set to 15 by its member."""

    def __init__(self, cluster: cc.ControlCluster, minutes: int | None = 15) -> None:
        self.cluster = cluster
        tag = uuid.uuid4().hex[:8]
        self.owner, self.member = str(uuid.uuid4()), str(uuid.uuid4())
        for user, label in ((self.owner, "o"), (self.member, "m")):
            cluster.query(
                "INSERT INTO app.control_accounts (user_id, username, display_name) "
                f"VALUES ('{user}', 'idle-{label}-{tag}', 'Idle')"
            )
        self.org = cluster.query(
            "INSERT INTO app.control_organizations (name, created_by) "
            f"VALUES ('idle {tag}', '{self.owner}') RETURNING id"
        )[0]
        for user, role in ((self.owner, "owner"), (self.member, "member")):
            cluster.query(
                "INSERT INTO app.control_memberships (organization_id, user_id, role) "
                f"VALUES ('{self.org}', '{user}', '{role}')"
            )
        self.key = f"i{tag}-prod"
        cluster.query(
            f"SELECT app.control_adopt_project('{self.key}', '{self.org}', 'i{tag}', 'prod', "
            f"'{self.key}.test', '1.19.0', 'abc')"
        )
        # Adopted long ago: no operation of its own inside any window.
        cluster.query(
            f"UPDATE app.control_projects SET adopted_at = now() - interval '2 days' "
            f"WHERE key = '{self.key}'"
        )
        if minutes is not None:
            self.set(minutes, self.member)

    def set(self, minutes: int | None, user: str) -> list[str]:
        value = "NULL" if minutes is None else str(minutes)
        call = f"app.control_set_idle_sleep('{user}', '{self.key}', {value})"
        return self.cluster.as_service(f"SELECT coalesce({call}::text, 'NULL')")

    def sample(
        self,
        seconds_ago: int,
        *,
        counter: int | None = 4242,
        activity: str | None = None,  # an SQL expression, or None: no backend
        unread: tuple[str, ...] = (),
        state: str = "active",
    ) -> None:
        unread_sql = "ARRAY[" + ",".join(f"'{u}'" for u in unread) + "]::text[]"
        self.cluster.query(
            "INSERT INTO app.control_usage_samples (project_key, observed_at, state, "
            "requests_counter, last_customer_activity, unread) VALUES "
            f"('{self.key}', now() - interval '{seconds_ago} seconds', '{state}', "
            f"{'NULL' if counter is None else counter}, "
            f"{'NULL' if activity is None else activity}, {unread_sql})"
        )

    def quiet_window(self, skip: int | None = None, **sample: object) -> None:
        for seconds in QUIET:
            if seconds != skip:
                self.sample(seconds, **sample)  # type: ignore[arg-type]

    def request(self) -> str:
        (value,) = self.cluster.query(
            f"SELECT coalesce(app.control_request_idle_sleep('{self.key}')::text, 'NULL')"
        )
        return value

    def rows(self) -> list[str]:
        return self.cluster.query(
            "SELECT type || '|' || status || '|' || origin || '|' || requested_by "
            f"FROM app.control_operations WHERE project_key = '{self.key}' ORDER BY created_at"
        )


@pytest.fixture
def project(cluster: cc.ControlCluster) -> Project:
    return Project(cluster)


def test_a_quiet_window_requests_one_sleep(project: Project) -> None:
    """Rig 41d's case: four samples across 15 minutes, all awake, the counter
    unmoved, no customer backend -- ONE pending `project.sleep`, origin idle;
    asked again with it pending, nothing."""
    project.quiet_window()
    assert project.request() != "NULL"
    assert project.request() == "NULL"
    assert project.rows() == [f"project.sleep|pending|idle|{project.member}"]


def test_no_customer_backend_is_quiet(project: Project) -> None:
    """D2539 (Sheet E0: a customer role holds no backend at rest): a window whose
    samples READ no customer backend sleeps. Control: one sample with a customer
    backend's activity inside the window keeps the project awake."""
    project.quiet_window(activity=None)
    assert project.request() != "NULL"
    busy = Project(project.cluster)
    busy.quiet_window()
    busy.sample(120, activity="now() - interval '120 seconds'")
    assert busy.request() == "NULL" and busy.rows() == []


def test_a_missing_sample_is_not_idle(project: Project) -> None:
    """A gap of 600 s (the -540 s sample missing) exceeds 1.5 x the interval:
    not idle, nothing requested. Control: the same project with the gap filled
    sleeps."""
    project.quiet_window(skip=540)
    assert project.request() == "NULL" and project.rows() == []
    project.sample(540)
    assert project.request() != "NULL"


def test_an_unread_sample_is_not_idle(project: Project) -> None:
    """A sample that could not read the counter or the backends names it in
    `unread`; one such sample in the window means not idle -- the decision
    fails closed (ADR 0195)."""
    project.quiet_window()
    project.sample(120, counter=None, unread=("requests_counter",))
    assert project.request() == "NULL"
    other = Project(project.cluster)
    other.quiet_window()
    other.sample(120, unread=("last_customer_activity",))
    assert other.request() == "NULL"


def test_a_moved_counter_is_not_idle(project: Project) -> None:
    """A sub-400 request inside the window -- the counter moved -- keeps the
    project awake; so does a counter reset (a decrease is read as activity's
    possibility, never as quiet)."""
    for seconds, counter in zip(QUIET, (4242, 4242, 4243, 4243), strict=True):
        project.sample(seconds, counter=counter)
    assert project.request() == "NULL"


def test_a_recent_wake_restarts_the_window(project: Project) -> None:
    """A wake that finished 5 minutes ago starts the window again: not idle yet,
    however quiet the samples."""
    project.quiet_window()
    project.cluster.query(
        "INSERT INTO app.control_operations (organization_id, project_key, type, status, "
        "requested_by, arguments, started_at, finished_at, claimed_by, attempt, progress) VALUES "
        f"('{project.org}', '{project.key}', 'project.wake', 'succeeded', '{project.member}', "
        "'{}', now() - interval '6 minutes', now() - interval '5 minutes', 'rig', 1, 100)"
    )
    assert project.request() == "NULL"


def test_the_request_names_the_member_who_set_it(project: Project) -> None:
    """The row is attributed to whoever set the minutes last -- the owner here --
    and a setting of `never` stops it."""
    project.set(30, project.owner)
    for seconds in (1740, 1440, 1140, 840, 540, 240, 10):
        project.sample(seconds)
    assert project.request() != "NULL"
    assert project.rows() == [f"project.sleep|pending|idle|{project.owner}"]
    never = Project(project.cluster)
    never.set(None, never.member)
    never.quiet_window()
    assert never.request() == "NULL"


def test_idle_is_only_a_sleep(project: Project) -> None:
    """The widened CHECK: `idle` only on a `project.sleep`, `expiry` only on a
    `branch.delete`; the setting accepts 15, 30, 60 or never and nothing else,
    from a member and above."""
    refused = project.cluster.run(
        "INSERT INTO app.control_operations (organization_id, project_key, type, status, "
        f"requested_by, arguments, origin) VALUES ('{project.org}', '{project.key}', "
        f"'project.wake', 'pending', '{project.member}', '{{}}', 'idle')"
    )
    assert (
        refused.returncode != 0 and "control_operations_idle_sleeps_a_project" in refused.stderr
    ), refused
    assert "AP422" in project.cluster.refused(
        f"SELECT app.control_set_idle_sleep('{project.member}', '{project.key}', 5)"
    )
    viewer = str(uuid.uuid4())
    project.cluster.query(
        "INSERT INTO app.control_accounts (user_id, username, display_name) "
        f"VALUES ('{viewer}', 'idle-v-{viewer[:8]}', 'V')"
    )
    project.cluster.query(
        "INSERT INTO app.control_memberships (organization_id, user_id, role) "
        f"VALUES ('{project.org}', '{viewer}', 'viewer')"
    )
    assert "AP403" in project.cluster.refused(
        f"SELECT app.control_set_idle_sleep('{viewer}', '{project.key}', 15)"
    )
    stranger = Project(project.cluster, minutes=None)
    assert "AP404" in project.cluster.refused(
        f"SELECT app.control_set_idle_sleep('{stranger.member}', '{project.key}', 15)"
    )


def test_no_role_but_the_reconciler_requests_an_idle_sleep(cluster: cc.ControlCluster) -> None:
    """Granted to nobody: the identity service's role cannot execute the request."""
    (held,) = cluster.query(
        f"SELECT has_function_privilege('{cluster.auth_role}', "
        "'app.control_request_idle_sleep(text)', 'EXECUTE')"
    )
    assert held == "f"


# ---------------------------------------------------------------------------
# The route (Run 5)
# ---------------------------------------------------------------------------


@pytest.fixture
def accepting(monkeypatch: pytest.MonkeyPatch) -> None:
    """The sleep an idle request inserts accepted, for this proof only: the
    control mode runs in this process, so the module the route reads is the
    one patched (D2548)."""
    monkeypatch.setattr(
        operations, "ACCEPTED_TYPES", operations.ACCEPTED_TYPES | {operations.IDLE_SLEEP_TYPE}
    )


def test_the_setting_route_says_what_sleeping_does_to_backups(drive: Any, accepting: None) -> None:
    """`PUT /v1/projects/{key}/idle-sleep`: a member sets 15 and the answer says
    the backups stop while it sleeps (D2534); null turns it off; 5 minutes is
    refused; a viewer is refused; the setting names the member who set it."""
    people = _people(drive, "setting")
    path = f"/v1/projects/{people['project']}/idle-sleep"
    member = people["tokens"]["member"]
    set_ = drive.call("PUT", path, token=member, body={"minutes": 15})
    assert set_.status_code == 200, set_.text
    assert set_.json()["idle_sleep_minutes"] == 15
    assert "its backups stop" in set_.json()["note"]
    (row,) = drive.cluster.query(
        "SELECT idle_sleep_minutes || '|' || idle_sleep_set_by FROM app.control_projects "
        f"WHERE key = '{people['project']}'"
    )
    assert row == f"15|{people['users']['member']}", row
    assert drive.call("PUT", path, token=member, body={"minutes": 5}).status_code == 400
    assert drive.call("PUT", path, token=people["tokens"]["viewer"],
                      body={"minutes": 30}).status_code == 403  # fmt: skip
    off = drive.call("PUT", path, token=member, body={"minutes": None})
    assert (off.status_code, off.json()["idle_sleep_minutes"]) == (200, None)


def test_the_setting_is_not_offered_while_the_sleep_is_not_accepted(drive: Any) -> None:
    """D2548 (ADR 0247, ADR 0254): a setting is not an operation, so
    `require_accepted` never sees it -- and an idle project would otherwise be
    slept by a type the Ledger refuses a person. With the release's own
    `ACCEPTED_TYPES` the route answers `409 not_available` naming `idle_sleep`,
    for 15 minutes and for never alike, and nothing is stored. The control:
    the same member reads the project (`200`), so the refusal is the gate's."""
    assert operations.IDLE_SLEEP_TYPE not in operations.ACCEPTED_TYPES
    people = _people(drive, "offered")
    key, member = people["project"], people["tokens"]["member"]
    for minutes in (15, None):
        refused = drive.call("PUT", f"/v1/projects/{key}/idle-sleep", token=member,
                             body={"minutes": minutes})  # fmt: skip
        assert refused.status_code == 409, refused.text
        assert (refused.json()["error"], refused.json()["ledger_row"]) == (
            "not_available",
            operations.IDLE_SLEEP_ROW,
        ), refused.text
    assert drive.cluster.query(
        "SELECT coalesce(idle_sleep_minutes::text, 'never') FROM app.control_projects "
        f"WHERE key = '{key}'"
    ) == ["never"]
    assert drive.call("GET", f"/v1/projects/{key}", token=member).status_code == 200
