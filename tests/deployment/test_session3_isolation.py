"""Two projects, two clusters, nothing shared (DEP-ISO-003, DBX-PG-003).

Replaces the Session 3 placeholders in ``test_future_deployment.py`` and
``test_future_database_platform.py`` that need two live deployments.

The property is not "the names differ" -- that is proved offline by
``test_render_isolation.py`` and would pass over a single shared cluster with
two sets of labels. What is measured here is that each project's cluster
genuinely does not contain the other's objects, and that a volume carrying one
project's identity is refused to the other.

Nothing here is destructive. The one mutating action is an insert into each
project's own tables, and neither project's teardown is exercised: destructive
volume tests run against the disposable third project only (D51), which is
Run 8's work.
"""

from __future__ import annotations

import json
import os
import subprocess
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
