"""Session 20's live halves: the tenant extension point, the task domain, two honest readers.

`TEN-SET-001`, `TEN-SURF-001`, `TEN-DOC-001`, `API-TASK-001`, `OPS-READ-001`,
`OPS-READ-002`. Written at the bump (Run 6) and gated on the roster variables
the trip already exports -- **no new gate variable**, which is what lets
`pytest --setup-plan` answer *will these run* before the day rather than during
it (D671, D676).

None of this has executed before the trip. Each docstring says what it asserts
and Run 7 finds out. That sentence is not a disclaimer: eleven never-executed
proofs have failed on a trip across two sessions (D1023-D1027, D1029-D1031), and
the honest thing is to say which these are while they still cost nothing.

**What only a deployment can prove**, and why the offline halves are not enough:

* that dbmate applied a project's set to a real cluster and the ledger holds its
  row -- offline, `sets_for` says which sets a document names, and nothing says
  a cluster ran them;
* that PostgREST SERVES a project's objects. Offline, `TEN-SURF-001`'s merged
  comparison runs against a document BUILT under `tmp_path` from the captured
  control, because a project's real snapshot can only come from a deployment of
  that project (D1039's shape, second instance). This is the half that says
  PostgREST produces such a document;
* that alpha, which declares NO set, serves none of beta's objects. The
  strongest evidence for a boundary is a neighbour that does not cross it, and
  no offline proof has two deployments to compare;
* that `api.create_task` makes a row `api.update_task_status` then moves --
  ADR 0003's compare-and-swap, against real data, for the first time;
* that `migrate.sh render` as `op` after a ROOT deploy says *unreadable* rather
  than *never deployed here*. That is D1060 exactly: measured on this host on
  2026-09-10, and the offline arm reproduces it with `chmod 000` rather than
  with a root-owned directory, which is a different cause of the same errno.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, api_surface, deployed_output, migrations

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"
    ),
]

#: The project the trip gives a migration set. Alpha stays at manifest schema 1
#: deliberately -- a version 1 manifest deploying under a schema 5 release is
#: the control that the version gate did not break every existing project
#: (D930), and it is also what makes "beta serves these and alpha does not" a
#: comparison rather than an assertion.
SET_ROOT = "projects/example"


def _key(document: dict[str, Any]) -> str:
    return str(document["project"]["key"])


def _doctor_check(sh_status, key: str, name: str) -> tuple[str | None, dict[str, Any]]:
    code, out, err = sh_status(str(REPO_ROOT / "bin" / "doctor.py"), "--project", key, "--json")
    assert code in (0, 6), f"doctor --json exited {code} for {key}\n{err}"
    parsed = json.loads(out)
    for check in parsed["checks"]:
        if check["name"] == name:
            return check["verdict"], check
    return None, {}


# ---------------------------------------------------------------------------
# TEN-SET-001 -- a project's set, applied
# ---------------------------------------------------------------------------


def test_the_project_set_beta_declares_is_applied_ledgered_and_published(
    project_b: dict[str, Any], as_root, sh_status
) -> None:
    """Beta's own migration reached the cluster, and the ledger says so.

    Three readings, because each answers a question the others cannot:

    * the DOCUMENT says which set the deploy applied -- what was intended;
    * the LEDGER says which bytes ran, written by the deploy as the superuser
      rather than by the migration plane, so a migration role could not have
      recorded a migration it did not execute;
    * the CATALOG says the table is there.

    D941's rule is why all three: read the cluster, never the migrator's summary
    line. A deploy that reported success having applied nothing is D60, and a
    `--runtime status` reading `Applied: 18, Pending: 0` over a stale render is
    D506; both printed a green line.
    """
    key = _key(project_b)
    block = project_b["migrations"]
    assert block["project_set"] is not None, (
        f"{key}'s deployed document names no project set, so the manifest was not at "
        "schema 5 with `migrations.set` when it was deployed"
    )
    assert block["project_set"]["root"] == SET_ROOT
    declared = block["project_set"]["count"]
    assert declared >= 1

    container = project_b["database"]["container"]
    database = project_b["database"]["name"]

    code, out, err = sh_status(
        "docker", "exec", "-i", container, "psql", "-U", "postgres", "-d", database,
        "-X", "-qtA", "-v", "ON_ERROR_STOP=1", "-c",
        "SELECT version FROM app_private.migration_ledger ORDER BY version",
    )  # fmt: skip
    assert code == 0, f"the ledger could not be read for {key}\n{err}"
    ledgered = {line.strip() for line in out.splitlines() if line.strip()}

    project_versions = {
        entry["version"]
        for entry in migrations.MigrationSet(
            label="project", root=REPO_ROOT / SET_ROOT / "migrations"
        ).load_manifest()["migrations"]
    }
    assert project_versions <= ledgered, (
        f"{key}'s ledger is missing the project set's migrations: "
        f"{sorted(project_versions - ledgered)}. dbmate applied something; the ledger "
        "records which bytes ran, and a version in one and not the other is a cluster "
        "that moved without a record"
    )

    # And the object itself, in the catalog. The ledger is a record of what ran;
    # this is the thing that ran.
    code, out, err = sh_status(
        "docker", "exec", "-i", container, "psql", "-U", "postgres", "-d", database,
        "-X", "-qtA", "-v", "ON_ERROR_STOP=1", "-c",
        "SELECT to_regclass('app.note_embeddings') IS NOT NULL",
    )  # fmt: skip
    assert code == 0, err
    assert out.strip() == "t", f"{key} has no app.note_embeddings; the set did not apply"


def test_alpha_declares_no_set_and_holds_none_of_betas_objects(
    project_a: dict[str, Any], as_root, sh_status
) -> None:
    """The control, and the strongest thing this trip can say about the boundary.

    Alpha's manifest stays at schema 1 -- a version 1 manifest deploying under a
    schema 5 release, which is D930's property held rather than assumed. If
    alpha's cluster held `app.note_embeddings`, the "project set" would be a
    release migration with extra steps.
    """
    key = _key(project_a)
    assert project_a["migrations"]["project_set"] is None, (
        f"{key} declares a project set; it is meant to be the no-set control"
    )

    code, out, err = sh_status(
        "docker", "exec", "-i", project_a["database"]["container"], "psql",
        "-U", "postgres", "-d", project_a["database"]["name"],
        "-X", "-qtA", "-v", "ON_ERROR_STOP=1", "-c",
        "SELECT to_regclass('app.note_embeddings') IS NOT NULL",
    )  # fmt: skip
    assert code == 0, err
    assert out.strip() == "f", (
        f"{key} holds app.note_embeddings and declares no project set. A project's "
        "migrations reached a project that did not ask for them"
    )


# ---------------------------------------------------------------------------
# TEN-SURF-001 -- what each deployment SERVES
# ---------------------------------------------------------------------------


def test_betas_served_document_names_the_release_and_project_surfaces_and_nothing_else(
    project_a: dict[str, Any], project_b: dict[str, Any], as_root, sh_status
) -> None:
    """The half no offline proof can have.

    Offline, the merged comparison runs against a snapshot BUILT under
    `tmp_path`: a project's real snapshot comes from a deployment of that
    project, so before this trip there was nothing to compare. What that proved
    is that the comparison ACCEPTS a document naming the merged surface's
    objects. This is whether PostgREST produces one.

    Alpha is the control in the same test, and it is the assertion with teeth:
    the release's objects appear in both documents, so "beta serves the merged
    surface" would hold for a beta serving only the release's. Alpha must serve
    the release's and NOT beta's.
    """
    release = api_surface.load_surface()
    project = api_surface.load_project_surface(
        api_surface.project_contract_path(REPO_ROOT / SET_ROOT)
    )
    merged = api_surface.merged_surface(release, project)

    def served(document: dict[str, Any]) -> set[str]:
        url = document["routes"]["rest"]["url"]
        assert document["routes"]["rest"]["status"] == "ready", (
            f"{_key(document)} publishes no ready REST route, so nothing can be captured"
        )
        code, out, err = sh_status(
            str(REPO_ROOT / "bin" / "dev-token.sh"),
            "--project-outputs", os.environ["APG_PROJECT_B_OUTPUTS"],
            "--role", "docs", "--",
            "curl", "-ksS", "--max-time", "20", url.rstrip("/") + "/",
        )  # fmt: skip
        assert code == 0, f"the served document could not be fetched from {url}\n{err}"
        return set(json.loads(out).get("paths", {}))

    beta_paths = served(project_b)
    assert beta_paths, "beta served a document naming no paths at all"

    for name in project["relations"]:
        assert f"/{name}" in beta_paths, (
            f"beta does not serve /{name}, which its own contract names. Either the "
            "migration did not apply, or the grant to api_documentation is missing -- "
            "openapi-mode = follow-privileges reads the document as that role (F-007)"
        )
    for name in project["rpcs"]:
        assert f"/rpc/{name}" in beta_paths, f"beta does not serve /rpc/{name}"

    for name in merged["relations"]:
        assert f"/{name}" in beta_paths, f"beta does not serve the merged relation /{name}"

    # The control. Alpha declares no set, so it must serve the release's surface
    # and none of beta's.
    alpha_url = project_a["routes"]["rest"]["url"]
    code, out, err = sh_status(
        str(REPO_ROOT / "bin" / "dev-token.sh"),
        "--project-outputs", os.environ["APG_PROJECT_A_OUTPUTS"],
        "--role", "docs", "--",
        "curl", "-ksS", "--max-time", "20", alpha_url.rstrip("/") + "/",
    )  # fmt: skip
    assert code == 0, f"alpha's document could not be fetched\n{err}"
    alpha_paths = set(json.loads(out).get("paths", {}))

    for name in project["relations"]:
        assert f"/{name}" not in alpha_paths, (
            f"alpha serves /{name}, which belongs to a project set it does not declare"
        )
    for name in project["rpcs"]:
        assert f"/rpc/{name}" not in alpha_paths, f"alpha serves /rpc/{name}"

    assert "/rpc/create_note" in alpha_paths, (
        "alpha serves none of the release's own RPCs either, so the comparison above "
        "is between two empty sets"
    )


# ---------------------------------------------------------------------------
# TEN-DOC-001 -- the deployed documents, and the doctor
# ---------------------------------------------------------------------------


def test_both_deployed_documents_are_v17_and_the_doctor_reads_the_sets(
    project_a: dict[str, Any], project_b: dict[str, Any], as_root, sh_status
) -> None:
    """Version 17 on both branches, and a doctor that counts what was applied.

    The doctor counted the RELEASE's manifest until ADR 0198 -- one of D1088's
    eleven callers of a default. On a project with a set that reads as a cluster
    AHEAD of the release, which `diagnosis.migrations` reports as a WARNING: a
    green-adjacent line for the one project whose tenant tables the check exists
    to notice.
    """
    for document in (project_a, project_b):
        key = _key(document)
        assert document["schema_version"] == deployed_output.SCHEMA_VERSION, (
            f"{key} publishes schema_version {document['schema_version']}, not "
            f"{deployed_output.SCHEMA_VERSION}"
        )
        assert document["migrations"]["release_lock_sha256"], (
            f"{key} records no release lock digest"
        )

    assert (
        project_a["migrations"]["release_lock_sha256"]
        == project_b["migrations"]["release_lock_sha256"]
    ), "two projects on one host disagree about the release lock, so two releases are installed"

    for document in (project_a, project_b):
        key = _key(document)
        verdict, check = _doctor_check(sh_status, key, "migrations")
        assert verdict == "ok", f"{key}'s migration check is {verdict}: {check.get('detail')}"

        block = document["migrations"]["project_set"]
        expected = len(migrations.release_set().load_manifest()["migrations"])
        if block is not None:
            expected += block["count"]
        assert int(check["facts"]["released"]) == expected, (
            f"{key}'s doctor counts {check['facts']['released']} released migrations and "
            f"this release plus that project's set declares {expected}"
        )


# ---------------------------------------------------------------------------
# API-TASK-001 -- the compare-and-swap, against a real row
# ---------------------------------------------------------------------------


def test_a_task_created_through_the_enumerated_operation_is_the_row_update_task_status_moves(
    project_a: dict[str, Any], owner_session, as_root
) -> None:
    """ADR 0003's operation 4, against real data, for the first time.

    `update_task_status` was argued for in ADR 0003, activated in ADR 0116, and
    has never run against a row outside a fixture -- because until migration
    0031 no role any service connects as could create a task (rig 19). Two of
    the agent plane's six tools addressed a permanently empty table.

    **`owner_session`, not `dev-token.sh`** (D298, D675). A minted token carries
    NO SUBJECT (ADR 0095) and migration 0013's `auth_claims_are_current` is an
    EXISTS over five equalities no minted token satisfies -- so
    `app.current_user_id()` would be NULL and `create_task` would answer
    `PT401`, saying nothing about what this proof names. Ten proofs returned
    AP401 the first time a host gate ran after 0013 and were all moved to this
    fixture; the Session 20 plan's own text said to use a minted token, which is
    that defect restated as an instruction.

    `bin/api.sh` is still the caller, because F-023's point is the product's own
    ENUMERATED door rather than a hand-written `curl`. It reads its bearer from
    `APG_API_TOKEN`, so the owner's token goes there.

    The stale-expectation arm is the compare-and-swap itself: one success and
    one refusal, rather than a last-writer-wins overwrite.
    """
    outputs = os.environ["APG_PROJECT_A_OUTPUTS"]
    environment = {**os.environ, "APG_API_TOKEN": owner_session.token}

    def api(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(REPO_ROOT / "bin" / "api.sh"), "--project-outputs", outputs, *arguments],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
            cwd=REPO_ROOT,
        )

    made = api("create-task", "--title", "session 20 trip")
    assert made.returncode == 0, f"create-task failed\n{made.stdout}\n{made.stderr}"
    created = json.loads(made.stdout)
    if isinstance(created, list):
        created = created[0]

    task_id = created["id"]
    assert created["status"] == "pending", created
    assert created["owner_id"] == owner_session.user_id, (
        "the task is owned by somebody other than the caller. There is no owner "
        "parameter; the owner comes from the request identity, and if these differ "
        "the derivation is not the one ADR 0196 specifies"
    )

    moved = api(
        "update-task-status", "--task-id", task_id,
        "--expected-status", "pending", "--new-status", "in_progress",
    )  # fmt: skip
    assert moved.returncode == 0, (
        f"update-task-status failed on the row create-task made\n{moved.stdout}\n{moved.stderr}"
    )
    updated = json.loads(moved.stdout)
    if isinstance(updated, list):
        updated = updated[0]
    assert updated["id"] == task_id
    assert updated["status"] == "in_progress"

    # The compare-and-swap, with the expectation now stale. One success and one
    # refusal is the whole argument for `p_expected_status`: without it the
    # second caller silently overwrites the first, and nothing says so.
    stale = api(
        "update-task-status", "--task-id", task_id,
        "--expected-status", "pending", "--new-status", "completed",
    )  # fmt: skip
    assert stale.returncode != 0, (
        "a second transition from a stale expected status SUCCEEDED, so the "
        "compare-and-swap is last-writer-wins and ADR 0116 is not activated"
    )
    combined = stale.stdout + stale.stderr
    assert "PT409" in combined or "409" in combined, combined


# ---------------------------------------------------------------------------
# OPS-READ-001 / 002 -- the two honest readers, on the host
# ---------------------------------------------------------------------------


def test_render_as_the_operator_after_a_root_deploy_says_unreadable_not_never_deployed(
    project_a: dict[str, Any],
) -> None:
    """D1060's live site, and the reading Session 19 could not make.

    A root deploy leaves `.generated/<key>` root-owned. Before ADR 0199 every
    reader answered *"the project was never deployed here"* -- false about a
    project deployed minutes earlier, and it sent an operator looking for a
    deploy that did happen.

    Run as the GATE'S OWN USER against the checkout, unprivileged, which is
    exactly the position `op` is in after the deploy. If the directory is
    op-owned when this runs -- because somebody already ran the `chown` the
    runbook now prints -- there is nothing to observe, and that is a SKIP rather
    than a pass: a reading of a state that is not there is not a reading.
    """
    key = _key(project_a)
    generated = REPO_ROOT / ".generated" / key
    if not generated.exists():
        pytest.skip(f"no {generated} on this host; the render was never published here")

    readable = os.access(generated, os.R_OK | os.X_OK)
    if readable:
        pytest.skip(
            f"{generated} is readable by this user, so the root-owned state D1060 "
            "describes is not present -- run this before `sudo chown -R op:op .generated`"
        )

    result = subprocess.run(
        [
            str(REPO_ROOT / "bin" / "migrate.sh"),
            "--project",
            os.environ.get("APG_PROJECT_A_MANIFEST", "project.alpha.yaml"),
            "render",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    message = result.stdout + result.stderr

    assert result.returncode == 3, (
        f"migrate.sh render exited {result.returncode} against a directory this user "
        f"cannot read; 3 is unreadable and 4 is absent\n{message}"
    )
    assert "cannot read" in message, message
    assert "never deployed here" not in message, (
        "the operator was told a deployed project had never been deployed, which is "
        "D1060 unrepaired"
    )
    assert "chown" in message, "the remedy is not named, so the operator has only the problem"


def test_no_route_on_either_project_reads_unobserved_after_a_redeploy(
    project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    """A settled deployment observed every route it publishes.

    `unobserved` is honest and it is not a resting state: it means the deploy
    did not look. On a project that has just been deployed and whose services
    are up, every route is either observed serving or determinately not
    published. One appearing here is a signal, and the message says which route.

    Read from the documents rather than by probing, deliberately: what is under
    test is what the DEPLOY recorded, and a second probe would answer a
    different question -- the one `probe_routes` already asks.
    """
    for document in (project_a, project_b):
        key = _key(document)
        unobserved = sorted(
            name
            for name, route in document["routes"].items()
            if isinstance(route, dict)
            and route.get("status") == deployed_output.ROUTE_UNOBSERVED["status"]
        )
        assert not unobserved, (
            f"{key} records {unobserved} as unobserved after its deploy. That is not a "
            "failure of the route -- it means the deploy did not obtain an answer, so "
            "redeploy and read the deploy's own lines for those routes"
        )

        # Anti-vacuity: a document whose routes are all bare strings would pass
        # the loop above by having nothing to check.
        assert any(isinstance(route, dict) for route in document["routes"].values()), (
            f"{key}'s routes carry no status blocks at all, so the assertion above compared nothing"
        )
