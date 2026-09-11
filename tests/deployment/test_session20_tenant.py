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
import stat
import subprocess
from typing import Any

import pytest

from agentic_postgres import (
    REPO_ROOT,
    api_surface,
    config,
    deployed_output,
    migrations,
    rendering,
)

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
    """The half no offline proof can have, made by the product's own comparison.

    Offline, the merged comparison runs against a snapshot BUILT under
    `tmp_path`: a project's real snapshot comes from a deployment of that
    project, so before this trip there was nothing to compare. What that proved
    is that the comparison ACCEPTS a document naming the merged surface's
    objects. This is whether PostgREST produces one.

    **The first version hand-rolled a `curl` and measured the anonymous view.**
    `bin/dev-token.sh` puts the minted token in the child's ENVIRONMENT and in
    nothing else -- no argument, no file, no output, which is the whole of D105,
    and `bin/dev-token.py`'s own comment says `bin/api-contract.sh` reads
    exactly one of those variables. `curl` reads no bearer from the environment.
    So the request went out unauthenticated, PostgREST answered as `anon`, and
    beta "served" exactly `{'/'}` -- the proof failed for a reason with nothing
    to do with its subject, which is this repository's signature defect arriving
    inside a proof written to catch it.

    `bin/api-contract.sh --check --project FILE --project-outputs FILE` is the
    caller `TEN-SURF-001` actually names, and it was there the whole time: it
    reads `APG_DOCS_TOKEN` from the environment because it is the command
    `dev-token.sh` exists to run, and with a deployed document it compares
    THREE things -- the reviewed surface, the committed snapshot, and the
    document the deployment is serving right now -- exiting 6 and naming the
    objects when they disagree.

    **Alpha is the control, and the assertion with teeth.** It declares no set,
    so `--check` without `--project` compares the RELEASE's surface and
    snapshot against alpha's live document. If a set had reached a project that
    did not declare one, alpha's document would name an object the release's
    reviewed surface does not, and the command would exit 6 saying "served but
    not approved". The boundary is proved by a neighbour that does not cross
    it, and no offline proof has two deployments to compare.
    """
    # The manifest handed to --project must name the set beta ACTUALLY
    # deployed, not one this test picked. The deployed document records the
    # root at outputs v17 (ADR 0158: the document is the address book), and the
    # tracked example manifest declares it. Assert they agree before either is
    # used -- otherwise passing a manifest of this test's choosing would assume
    # exactly the thing under test.
    recorded = ((project_b.get("migrations") or {}).get("project_set") or {}).get("root")
    assert recorded == SET_ROOT, (
        f"beta's deployed document records project set {recorded!r}, not {SET_ROOT!r}. "
        "The comparison below would then be against a contract beta does not serve."
    )
    manifest = REPO_ROOT / "project.example.yaml"
    declared = config.project_migration_set(config.load_project_manifest(manifest, expiry=False))
    assert declared == SET_ROOT, (
        f"{manifest.name} declares migrations.set {declared!r}, not {SET_ROOT!r}"
    )

    beta_outputs = os.environ["APG_PROJECT_B_OUTPUTS"]
    alpha_outputs = os.environ["APG_PROJECT_A_OUTPUTS"]

    code, out, err = sh_status(
        str(REPO_ROOT / "bin" / "dev-token.sh"),
        "--project-outputs", beta_outputs,
        "--role", "docs", "--",
        str(REPO_ROOT / "bin" / "api-contract.sh"), "--check",
        "--project", str(manifest),
        "--project-outputs", beta_outputs,
    )  # fmt: skip
    assert code == 0, (
        "beta's live document, its own snapshot and the merged surface do not all "
        f"agree (exit {code}). Exit 6 names the objects; exit 5 means the snapshot "
        f"and the reviewed surface disagree before any fetch.\n{out}\n{err}"
    )

    # The control, and the boundary.
    code, out, err = sh_status(
        str(REPO_ROOT / "bin" / "dev-token.sh"),
        "--project-outputs", alpha_outputs,
        "--role", "docs", "--",
        str(REPO_ROOT / "bin" / "api-contract.sh"), "--check",
        "--project-outputs", alpha_outputs,
    )  # fmt: skip
    assert code == 0, (
        "alpha's live document does not match the RELEASE's surface and snapshot "
        f"(exit {code}). If it names one of the project's objects, a set reached a "
        f"project that did not declare one.\n{out}\n{err}"
    )

    # Anti-vacuity. Both commands above exit 0 against the release's surface if
    # beta's snapshot happens to be the release's -- the two comparisons would
    # then be the same comparison run twice, and the boundary would be unproved.
    # These assertions are what make them different: beta's own snapshot names
    # the project's objects, and the merged surface names both sets'.
    release = api_surface.load_surface()
    project = api_surface.load_project_surface(
        api_surface.project_contract_path(REPO_ROOT / SET_ROOT)
    )
    merged = api_surface.merged_surface(release, project)
    beta_snapshot = json.loads(
        api_surface.project_snapshot_path(REPO_ROOT / SET_ROOT).read_text(encoding="utf-8")
    )
    served = set(beta_snapshot.get("paths", {}))

    assert project["relations"] or project["rpcs"], (
        "the project contract names no objects, so every assertion below is vacuous"
    )
    for name in project["relations"]:
        assert f"/{name}" in served, (
            f"beta's own snapshot does not name /{name}, so the comparison that "
            "passed above was not the merged one"
        )
    for name in project["rpcs"]:
        assert f"/rpc/{name}" in served, f"beta's own snapshot does not name /rpc/{name}"
    for name in merged["relations"]:
        assert f"/{name}" in served, f"beta's snapshot does not name the merged relation /{name}"

    release_snapshot = json.loads(rendering.CANONICAL_OPENAPI.read_text(encoding="utf-8"))
    release_served = set(release_snapshot.get("paths", {}))
    for name in project["relations"]:
        assert f"/{name}" not in release_served, (
            f"the RELEASE's snapshot names /{name}, so alpha's comparison and beta's "
            "are the same comparison and the boundary above is unproved"
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
        # `evidence`, not `facts`. `diagnosis._check` takes an `evidence` tuple
        # of pairs and `bin/doctor.py` renders it with `dict(check.evidence)`.
        # This asserted a key name read from memory of the shape rather than
        # from the module, and died with KeyError on the host -- after the
        # verdict it actually cares about had already passed.
        counted = dict(check["evidence"])
        assert int(counted["released"]) == expected, (
            f"{key}'s doctor counts {counted['released']} released migrations and "
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


def test_render_as_the_checkout_owner_of_a_root_owned_directory_says_unreadable_not_absent(
    project_a: dict[str, Any],
) -> None:
    """D1060's live site, read the way D1121 says it has to be read.

    A privileged command can leave `.generated/<key>` root-owned. Before ADR
    0199 every reader answered *"the project was never deployed here"* -- false
    about a project deployed minutes earlier, and it sent an operator looking
    for a deploy that did happen.

    **The first version of this proof could never run** (D1121). Its docstring
    said *"run as the gate's own user, unprivileged"*, and the gate is invoked
    under `sudo`: `os.access` is unconditionally true for root, so it took its
    own skip branch on every host run, and past that branch a render as root
    would have exited 0 rather than 3. It also depended on a state a `sudo`
    deploy undoes (D1110: `_restore_checkout_ownership` hands the directory
    back), so the state had to be CONSTRUCTED on the trip to be read at all.

    So, both halves, because either alone still measures the wrong thing:

    * **The reading is made as the checkout's owner**, never as whoever invoked
      the gate. Under root, `sudo -u '#<uid>'` to `REPO_ROOT`'s owner -- the
      position `op` is in after a deploy. Unprivileged, the command runs as-is.
    * **The precondition is constructed and restored by the proof itself.**
      Under root the directory is made root-owned and mode 0700 for the
      duration, and put back to the recorded owner, group and mode in
      `finally`, with the restore asserted by `stat` -- a proof that changes
      the host puts the host back, or the next proof in the sweep inherits it.

    Unprivileged and the directory readable, there is nothing to observe and
    that is a SKIP rather than a pass: a reading of a state that is not there
    is not a reading.
    """
    key = _key(project_a)
    generated = REPO_ROOT / ".generated" / key
    if not generated.exists():
        pytest.skip(f"no {generated} on this host; the render was never published here")

    command = [
        str(REPO_ROOT / "bin" / "migrate.sh"),
        "--project",
        os.environ.get("APG_PROJECT_A_MANIFEST", "project.alpha.yaml"),
        "render",
    ]

    if os.geteuid() == 0:
        owner = REPO_ROOT.stat()
        if owner.st_uid == 0:
            pytest.skip(
                f"{REPO_ROOT} is root-owned, so there is no unprivileged checkout owner "
                "to make the reading as (D1121); chown the checkout to the operator first"
            )
        before = generated.stat()
        os.chown(generated, 0, 0)
        os.chmod(generated, 0o700)
        try:
            result = subprocess.run(
                ["sudo", "-u", f"#{owner.st_uid}", "-g", f"#{owner.st_gid}", *command],
                capture_output=True,
                text=True,
                check=False,
                cwd=REPO_ROOT,
            )
        finally:
            os.chown(generated, before.st_uid, before.st_gid)
            os.chmod(generated, stat.S_IMODE(before.st_mode))
        after = generated.stat()
        assert (after.st_uid, after.st_gid, stat.S_IMODE(after.st_mode)) == (
            before.st_uid,
            before.st_gid,
            stat.S_IMODE(before.st_mode),
        ), f"{generated} was not restored to its recorded owner, group and mode"
    else:
        readable = os.access(generated, os.R_OK | os.X_OK)
        if readable:
            pytest.skip(
                f"{generated} is readable by this user, so the root-owned state D1060 "
                "describes is not present; as root this proof constructs it"
            )
        result = subprocess.run(
            command,
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
