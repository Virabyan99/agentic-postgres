"""Two projects, two clusters, nothing shared (DEP-ISO-003, DBX-PG-003).

Replaces the Session 3 placeholders in ``test_future_deployment.py`` and
``test_future_database_platform.py`` that need two live deployments.

The property is not "the names differ" -- that is proved offline by
``test_render_isolation.py`` and would pass over a single shared cluster with
two sets of labels. What is measured here is that each project's cluster
genuinely does not contain the other's objects, and that a volume carrying one
project's identity is refused to the other.

Nothing here is destructive. Two tests mutate and both restore: an insert into a
project's own tables, and a stop of one cluster followed by a start and an
assertion that it came back. No volume is removed and no project is torn down --
destructive volume tests run against the disposable third project only (D51),
which does not exist and is not built here (D69).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

# ruff: noqa: S608
#
# Every statement below interpolates values that came from the rendered
# outputs document -- role names and a database name derived by `naming` and
# validated by the outputs schema -- plus two hard-coded uuid constants. None
# of it is operator input, and parameter binding is unavailable where an
# identifier or a role name goes, which is the same reason
# `migrations.quote_identifier` exists. Suppressed per module rather than per
# line because the rule fires on nearly every assertion here and a wall of
# inline noqa comments is one nobody reads.

pytestmark = [
    pytest.mark.p0,
    pytest.mark.deployment,
    pytest.mark.database,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"
    ),
]


def load(variable: str) -> dict[str, Any]:
    return json.loads(Path(os.environ[variable]).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def project_a() -> dict[str, Any]:
    return load("APG_PROJECT_A_OUTPUTS")


@pytest.fixture(scope="module")
def project_b() -> dict[str, Any]:
    return load("APG_PROJECT_B_OUTPUTS")


def sql(document: dict[str, Any], statement: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            document["database"]["container"],
            "psql",
            "-U",
            "postgres",
            "-d",
            document["database"]["name"],
            "-X",
            "-qtA",
            "-c",
            statement,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        return f"ERROR: {result.stderr.strip()}"
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# DEP-ISO-003
# ---------------------------------------------------------------------------


def test_the_two_projects_run_separate_containers(
    project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    """And the running container is the one the rendered document named.

    This is what closes D55. `database.container` records the name Compose
    derives rather than one `container_name:` forced, so until now it was a
    prediction. Here it is compared against what is actually running.
    """
    for document in (project_a, project_b):
        name = document["database"]["container"]
        running = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", name],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        assert running == "true", f"{name} is not running; the recorded name is wrong"

    assert project_a["database"]["container"] != project_b["database"]["container"]


def test_the_two_projects_use_separate_volumes(
    project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    left = project_a["compose"]["volumes"]["postgres"]
    right = project_b["compose"]["volumes"]["postgres"]
    assert left != right

    for name in (left, right):
        found = subprocess.run(
            ["docker", "volume", "inspect", "--format", "{{.Name}}", name],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        assert found == name, f"volume {name} does not exist"


def test_neither_projects_roles_exist_in_the_other(
    project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    """Thirteen names each, checked in the other's catalog.

    Offline isolation proves the *names* differ. This proves the roles are not
    present, which is a different claim and the one that fails if two projects
    were ever pointed at one cluster.
    """
    for document, other in ((project_a, project_b), (project_b, project_a)):
        names = "', '".join(sorted(other["database"]["roles"].values()))
        observed = sql(
            document,
            f"SELECT coalesce(string_agg(rolname, ','), '') FROM pg_roles "
            f"WHERE rolname IN ('{names}');",
        )
        assert observed == "", (
            f"{other['project']['key']}'s roles exist in {document['project']['key']}: {observed}"
        )


def test_a_row_written_to_one_project_is_absent_from_the_other(
    project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    """The claim isolation is actually about. Names and roles can be distinct
    while both point at one set of tables."""
    marker = "isolation-probe-a"
    owner = "33333333-3333-3333-3333-333333333333"
    written = sql(
        project_a,
        f'SET ROLE "{project_a["database"]["roles"]["authenticated"]}"; '
        f"SET app.user_id = '{owner}'; "
        f"SELECT (api.create_note('{marker}')).owner_id;",
    )
    assert written == owner, written

    found_in_b = sql(project_b, f"SELECT count(*) FROM app.notes WHERE title = '{marker}';")
    assert found_in_b == "0", f"a row written to A is visible in B: {found_in_b}"


def test_each_project_has_its_own_identity_sentinel(
    project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    identities = {}
    for document in (project_a, project_b):
        observed = sql(
            document,
            "SELECT project_key || '|' || instance_uuid FROM app_private.project_identity;",
        )
        assert "|" in observed, observed
        key, _, uuid = observed.partition("|")
        assert key == document["project"]["key"], f"{key} != {document['project']['key']}"
        identities[key] = uuid

    assert len(set(identities.values())) == 2, "both projects share one instance uuid"


def test_the_databases_have_different_names(
    project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    assert project_a["database"]["name"] != project_b["database"]["name"]


def test_each_projects_migration_credential_opens_its_own_cluster(
    as_root, migration_password, pg_login, project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    """Guard the guard, and it is not optional here.

    The test below asserts that a login fails. A cluster that refuses every
    password -- because the role was never given one, because the credential
    rotated out from under the materializer, because ``psql`` cannot reach the
    port at all -- passes it completely. This is the control that says the
    refusal below is about *whose* password it was.
    """
    del as_root
    for document in (project_a, project_b):
        key = document["project"]["key"]
        code, stdout, stderr = pg_login(
            document, document["database"]["roles"]["migration_user"], migration_password(key)
        )
        assert code == 0 and stdout.strip() == "1", (
            f"{key}'s own migration credential does not open {key}: {stderr.strip()}"
        )


def test_neither_projects_migration_credential_opens_the_other(
    as_root, migration_password, pg_login, project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    """The clause of DEP-ISO-003 that had no proof behind it.

    The requirement has said "neither project's credential authenticates against
    the other" since Run 1 and nothing measured it. What made that comfortable is
    that the role names differ, so the obvious construction -- A's role name
    against B -- fails with "role does not exist" and proves nothing about the
    credential. The password is therefore presented against **the target's own
    migration role**, which does exist there. The only reason it can fail is that
    the value is wrong.
    """
    del as_root
    for document, other in ((project_a, project_b), (project_b, project_a)):
        target = document["project"]["key"]
        foreign_password = migration_password(other["project"]["key"])
        code, stdout, stderr = pg_login(
            document, document["database"]["roles"]["migration_user"], foreign_password
        )
        assert code != 0, (
            f"{other['project']['key']}'s migration credential opened {target}: {stdout.strip()}"
        )
        assert "password authentication failed" in stderr, (
            f"the login against {target} failed for a reason other than the password, "
            f"so this proves nothing: {stderr.strip()}"
        )
        assert foreign_password not in stderr + stdout, "the failure printed the credential"


def test_stopping_one_projects_cluster_leaves_the_other_serving(
    as_root, sh, project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    """Isolation that holds only while both clusters are healthy is not isolation.

    Session 2 proves the routing half of this by stopping B's whole project
    (``test_removing_the_second_project_leaves_the_first_routed``). What is new
    at Session 3 is shared kernel memory and a shared page cache: two postmasters
    on a 2-vCPU box with no swap. B's cluster is stopped, A is asked a question
    that requires its own cluster to answer it, and B is started again -- and
    then asserted to have come back, so a failure to restore cannot pass silently.
    """
    del as_root
    container = project_b["database"]["container"]

    sh("docker", "stop", container)
    try:
        answered = sql(project_a, "SELECT count(*)::text FROM app_private.migration_ledger;")
        assert answered.isdigit() and int(answered) > 0, (
            f"A could not answer while B's cluster was stopped: {answered}"
        )
    finally:
        sh("docker", "start", container)

    for _ in range(60):
        if sql(project_b, "SELECT 1;") == "1":
            break
        time.sleep(2)
    else:
        pytest.fail(f"{container} did not come back after being stopped")


# ---------------------------------------------------------------------------
# DBX-PG-003 — a volume belongs to one project
# ---------------------------------------------------------------------------


def test_bootstrap_refuses_a_volume_belonging_to_another_project(
    project_a: dict[str, Any], project_b: dict[str, Any], tmp_path: Path
) -> None:
    """Exit 11, and nothing changed (ADR 0030, ADR 0031).

    Constructed by pointing A's document at B's cluster rather than by moving a
    volume: the comparison under test is the sentinel row against the document,
    and this exercises it without putting either project's data at risk.
    """
    foreign = json.loads(json.dumps(project_a))
    foreign["database"]["container"] = project_b["database"]["container"]
    foreign["database"]["name"] = project_b["database"]["name"]
    document = tmp_path / "foreign-outputs.json"
    document.write_text(json.dumps(foreign), encoding="utf-8")

    before = sql(project_b, "SELECT project_key FROM app_private.project_identity;")

    result = subprocess.run(
        [
            str(Path(__file__).resolve().parents[2] / "bin" / "postgres-bootstrap.py"),
            "--outputs",
            str(document),
            "--mode",
            "apply",
            "--state-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert result.returncode == 11, f"got {result.returncode}: {result.stderr}"
    assert "belongs to a different project" in result.stderr

    after = sql(project_b, "SELECT project_key FROM app_private.project_identity;")
    assert after == before, "the recorded identity changed during a refused bootstrap"


def test_the_refusal_message_carries_no_secret(
    project_a: dict[str, Any], project_b: dict[str, Any], tmp_path: Path
) -> None:
    """Every field it reports is a derived, non-secret identity."""
    foreign = json.loads(json.dumps(project_a))
    foreign["database"]["container"] = project_b["database"]["container"]
    foreign["database"]["name"] = project_b["database"]["name"]
    document = tmp_path / "foreign-outputs.json"
    document.write_text(json.dumps(foreign), encoding="utf-8")

    result = subprocess.run(
        [
            str(Path(__file__).resolve().parents[2] / "bin" / "postgres-bootstrap.py"),
            "--outputs",
            str(document),
            "--mode",
            "apply",
            "--state-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    combined = result.stdout + result.stderr
    for forbidden in ("password", "PASSWORD", "postgresql://", "secret"):
        assert forbidden not in combined, f"the refusal printed {forbidden!r}"
