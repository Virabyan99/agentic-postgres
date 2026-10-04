#!/usr/bin/env python3
"""The migration plane's work. Invoked only by ``bin/migrate.sh``.

Split from the shell for the same reason ``bin/postgres-bootstrap.py`` is: the
script owns the operator surface and the privilege gate, and digest comparison
written in bash is a string comparison somebody eventually relaxes to a prefix.

``freeze-lock`` and ``verify-lock`` share one implementation of what the lock
should contain (``migrations.build_lock``). A gate that verified with different
code than the one that wrote the lock would be checking its own arithmetic.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_postgres import (
    api_surface,
    approval_gate,
    capability_compiler,
    capability_manifest,
    config,
    container_exec,
    evaluation_harness,
    migrations,
    proposal,
    rendering,
    runtime_override,
    sql_surface,
    template_version,
)

EXIT_CONTRACT = 5

REPO_ROOT = Path(__file__).resolve().parents[1]


def render_set(document: dict) -> list[tuple[str, str, str]]:
    """(version, name, rendered digest) for this project, in applied order.

    **Every set, release first** (ADR 0198). `sets_for` answers the release's
    alone for a project that declares none, so a project without a set renders
    exactly what it rendered before this existed.

    The order is the release's set and then the project's, which is also the
    version order dbmate will use, because a project's versions are required to
    sort after the release lock's newest at freeze. That requirement is not
    decoration: rig 20a measured `up --strict` exiting 2 and applying nothing
    when it is broken on a deployed cluster, while a fresh cluster applies the
    same pair of files silently -- one set, two schemas (D1098).
    """
    rendered = []
    for migration_set in migrations.sets_for(document, REPO_ROOT):
        manifest = migration_set.load_manifest()
        for entry in manifest["migrations"]:
            payload = migrations.render_migration(entry, manifest, document, migration_set.root)
            rendered.append((entry["version"], entry["name"], migrations.digest(payload)))
    return rendered


def assert_rendered_files_match(rendered_dir: str) -> None:
    """The files dbmate will read are the payloads this release rendered.

    **The body is `migrations.verify_rendered_directory`** since Session 22 Run
    3, and the name, the argument and the `None` return are unchanged (ADR
    0175). `apg dev` applies the same rendered payloads to a disposable cluster
    and has to verify them the same way; a second reading of one directory
    would be a second verification nobody compares (ADR 0203).

    What this keeps is the SHAPE: a checker that raises, called for its effect.
    What the library returns -- the manifest's entries, in order -- is what the
    other caller needs, and is dropped here because dbmate is handed the
    directory rather than a list.
    """
    migrations.verify_rendered_directory(Path(rendered_dir))


def assert_installed_render_is_current(
    rendered: list[tuple[str, str, str]], rendered_dir: str
) -> None:
    """The set this checkout declares is the set the installed render carries.

    D1053. `assert_rendered_files_match` above compares the rendered directory
    against the manifest written *beside it*, which makes it internally
    consistent and says nothing about whether it is current. `render_set` reads
    this checkout's manifest. Until this function existed the two were never
    compared, so `--runtime up` on a host whose last deploy predated a new
    migration listed 34 migrations, applied the installed 33, and exited 0.

    The only signal was a count in the summary line -- and D941 exists because
    that line is not to be trusted: *read the cluster, never the migrator's
    summary line*. A tool whose correct use requires ignoring its own output is
    not reporting, it is decorating.

    This is the third appearance of one defect. D60 was `up` printing the set
    and returning 0 having applied nothing; the comment in `main` still records
    the repair. D941 wrote down that the summary line lies. Neither reader
    compared the two sets, because neither of them was the reader that had both
    numbers -- which is question 5 of the defect pattern, answered wrong twice.
    """
    directory = Path(rendered_dir) / "migrations"
    recorded = json.loads(
        (directory / rendering.MIGRATION_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    installed = {
        (entry["version"], entry["name"]): entry["sha256"] for entry in recorded["migrations"]
    }
    declared = {(version, name): sha for version, name, sha in rendered}

    if declared == installed:
        return

    missing = sorted(declared.keys() - installed.keys())
    extra = sorted(installed.keys() - declared.keys())
    changed = sorted(
        key for key in declared.keys() & installed.keys() if declared[key] != installed[key]
    )

    detail = []
    if missing:
        detail.append(
            "not installed: " + ", ".join(f"{version}_{name}" for version, name in missing)
        )
    if extra:
        detail.append(
            "installed but not declared: "
            + ", ".join(f"{version}_{name}" for version, name in extra)
        )
    if changed:
        detail.append(
            "installed with different content: "
            + ", ".join(f"{version}_{name}" for version, name in changed)
        )

    raise migrations.MigrationError(
        f"this checkout declares {len(declared)} migrations and the installed render "
        f"at {rendered_dir} carries {len(installed)}; "
        + "; ".join(detail)
        + ". Applying the installed set would report success having applied "
        "something other than what this checkout declares. Run deploy.sh, which "
        "re-renders and then migrates."
    )


def run_dbmate(mode: str, document: dict, rendered_dir: str, service: str = "dbmate") -> int:
    """Run one dbmate subcommand through bin/compose.sh, as migration_user.

    Through the wrapper, never `docker` directly: the wrapper is what pins the
    env files, refuses a secret source outside this project's own tree, and
    resolves the model the release committed. A `docker compose run` here would
    be a second way to start a container in this repository, and it would be
    the one nothing audits.
    """
    command = [
        str(REPO_ROOT / "bin" / "compose.sh"),
        rendered_dir,
        "--runtime",
        "--profile",
        "migration",
        "run",
        "--rm",
        service,
        mode,
    ]
    if mode == "up":
        # Subcommand-only, and it exists on `up` but not on `status` -- measured
        # in tests/contract/test_image_contracts.py. Without it dbmate applies
        # what it can and exits 0 on a partially applied set.
        command.append("--strict")

    print(f"migrate: {mode} {service} as {document['database']['roles']['migration_user']}")
    # Through the discipline (ADR 0218): stdin closed and `-T` after `run`.
    # dbmate does not read stdin -- rig 30b2 measured that a non-reading child
    # completes in the shape D1505 recorded -- so this is not what D1505 hit,
    # and D1505's own cause is still not established (D1544). Closed anyway:
    # nothing reads it, and a child that cannot reach a terminal cannot stop.
    result = container_exec.compose_run(command[0], command[1], *command[3:], text=False)
    # **Relayed, not swallowed** (D1707). `compose_run` always captures, and
    # from 1.8.0 until Session 33 this returned the exit code alone -- so
    # `status` printed no ledger and exited 0, and a failed `up` reached the
    # deploy's step 6 with an empty stderr. dbmate's own lines are the
    # operator's to read; they are still not the verdict (D941: read the
    # ledger, never the migrator's line). Bytes, because `text=False`; a byte
    # that is not UTF-8 is replaced rather than allowed to fail the relay.
    sys.stdout.write((result.stdout or b"").decode("utf-8", errors="replace"))
    sys.stdout.flush()
    sys.stderr.write((result.stderr or b"").decode("utf-8", errors="replace"))
    sys.stderr.flush()
    return result.returncode


def applied_project_versions(document: dict, versions: tuple[str, ...]) -> frozenset[str]:
    """Which of the project set's ``versions`` the cluster has applied.

    One READ-ONLY psql script as the superuser over the container socket, the
    way `reconcile_project_ledger` reaches the same tables -- and through
    `container_exec.run` (the rule for new code, ADR 0218). It reads what the
    cluster will hold AFTER that repair, so it can be asked before it (D1865).
    A failure, or a line that is not one of the versions asked about, raises:
    the gate cannot decide on an applied set it could not read.
    """
    result = container_exec.run(
        document["database"]["container"],
        "psql",
        "-U",
        "postgres",
        "-d",
        document["database"]["name"],
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-qtA",
        "-f",
        "-",
        input=migrations.applied_project_versions_statement(versions),
    )
    if result.returncode != 0:
        raise migrations.MigrationError(
            "the project set's applied versions could not be read "
            f"(psql exited {result.returncode}): {result.stderr.strip()}"
        )
    applied = frozenset(line.strip() for line in result.stdout.splitlines() if line.strip())
    unexpected = sorted(applied - set(versions))
    if unexpected:
        raise migrations.MigrationError(
            f"the read of the project set's applied versions returned {unexpected}, which "
            "it did not ask about"
        )
    return applied


def pending_project_set(
    document: dict, rendered_dir: str
) -> tuple[migrations.MigrationSet, tuple[str, ...]] | None:
    """The project set and its versions the cluster lacks; None without a set.

    `pending` is the RENDERED set minus what is applied -- what dbmate's `up`
    would apply, which is the act the gate governs (D1865).
    """
    project_set = migrations.project_set_from(document, REPO_ROOT)
    if project_set is None:
        return None
    rendered = migrations.rendered_project_versions(Path(rendered_dir))
    if not rendered:
        return project_set, ()
    applied = applied_project_versions(document, rendered)
    return project_set, tuple(version for version in rendered if version not in applied)


def gate_project_set(document: dict, rendered_dir: str, approvals_required: int) -> None:
    """The host gate (D1865, ADR 0243), BEFORE anything in `up` writes.

    Before `reconcile_project_ledger` as well as before both dbmate runs: that
    repair moves ledger rows, and a refused deploy writes nothing (D1912). The
    release set is never gated -- its own lock reviews it -- and is not applied
    ahead of a refusal either.
    """
    found = pending_project_set(document, rendered_dir)
    if found is None:
        return
    project_set, pending = found
    if pending:
        print(f"migrate: {len(pending)} project version(s) pending: {', '.join(pending)}")
    proposal.gate(
        project_set.root.parent,
        migrations.set_digest(project_set),
        pending,
        approvals_required,
    )
    if pending:
        print(f"migrate: proposal {migrations.set_digest(project_set)[:16]} admits them")


def print_proposal_line(document: dict, rendered_dir: str, approvals_required: int) -> None:
    """`status`'s proposal line (D1865), after the ledger. A report: an applied
    set it cannot read is said, never folded into an answer (ADR 0195)."""
    project_set = migrations.project_set_from(document, REPO_ROOT)
    if project_set is None:
        print("migrate: proposal: not applicable (this project applies no set of its own)")
        return
    digest = migrations.set_digest(project_set)
    try:
        found = pending_project_set(document, rendered_dir)
    except migrations.MigrationError as error:
        line = proposal.status_line(
            project_set.root.parent, digest, None, approvals_required, unread=str(error)
        )
    else:
        assert found is not None
        line = proposal.status_line(project_set.root.parent, digest, found[1], approvals_required)
    print(f"migrate: {line}")


def run_every_set(mode: str, document: dict, rendered_dir: str, *, approvals_required: int) -> int:
    """One dbmate invocation per set, release first, then the ledger once.

    **Each set has its own directory and its own table** since ADR 0206, so each
    is ordered against its own applied set alone. While they shared a table they
    shared an ordering space, and `up --strict` refuses a pending version below
    `max(applied)` whichever set either came from -- which is how a release
    migration stamped below an applied PROJECT migration came to refuse a deploy
    on beta, having applied nothing (D1288).

    Release first is ADR 0198's order and is kept. It no longer decides anything
    about ordering -- that is what the split removed -- but a project's
    migrations are written against the schema the release's migrations create,
    so the dependency is real even though the constraint is gone.

    The ledger is written ONCE, after both, and is not split: it keys on the
    version across every set and is the one record of which bytes ran (D1096).
    It is also why a failure in the second set still leaves the first recorded
    only if the first succeeded -- the early return below stops before the
    ledger, so a partially applied pair records nothing and says so, rather than
    recording a set that half ran.

    **`up` asks the host gate first** (D1865): a refusal raises
    `MigrationError` before the ledger repair and before either dbmate run, so
    a refused deploy has applied and written nothing. ``approvals_required`` is
    the INSTALLED manifest's, keyword-only: a default would be the one way to
    call this without the project's own answer.
    """
    if mode == "up":
        gate_project_set(document, rendered_dir, approvals_required)
        status = reconcile_project_ledger(document, rendered_dir)
        if status != 0:
            return status

    for migration_set in migrations.sets_for(document, REPO_ROOT):
        service = (
            runtime_override.MIGRATION_PROJECT_SERVICE
            if migration_set.is_project
            else runtime_override.MIGRATION_SERVICE
        )
        status = run_dbmate(mode, document, rendered_dir, service)
        if status != 0:
            return status

    if mode != "up":
        print_proposal_line(document, rendered_dir, approvals_required)
        return 0
    return record_ledger(document, rendered_dir)


def reconcile_project_ledger(document: dict, rendered_dir: str) -> int:
    """Move a project set's applied versions into its own table (ADR 0206).

    Runs BEFORE either dbmate invocation and as the superuser, over the
    container socket, exactly as `record_ledger` does -- `migration_user` may
    write its own bookkeeping but must not rearrange it, and this moves rows
    between two tables it does not own the relationship between.

    **This is D1288's repair on a cluster that predates the split.** Such a
    cluster recorded both sets in `app_private.schema_migrations`, so the
    release's `max(applied)` includes project versions and `up --strict` refuses
    any release migration stamped below one of them -- which is precisely how
    beta refused Session 24's deploy, having applied nothing. Moving the rows
    restores the release's own ordering without re-applying anything.

    Re-runnable, and a no-op on a cluster that has already been moved or never
    had project migrations: the statement is `None` when this release renders
    none, the insert is `ON CONFLICT DO NOTHING`, and the delete names the same
    versions. Nothing here is conditional on "has this run before", because a
    repair that had to know would be a repair with state of its own.
    """
    statement = migrations.project_ledger_move_statement(Path(rendered_dir))
    if statement is None:
        return 0

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
            "-v",
            "ON_ERROR_STOP=1",
            "-qtA",
            "-f",
            "-",
        ],
        input=statement,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(
            "migrate: the project set's applied versions could not be moved into "
            f"{rendering.PROJECT_MIGRATIONS_TABLE}: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return EXIT_CONTRACT
    print(f"migrate: project versions recorded in {rendering.PROJECT_MIGRATIONS_TABLE} (ADR 0206)")
    return 0


def record_ledger(document: dict, rendered_dir: str) -> int:
    """Write what actually ran into app_private.migration_ledger.

    The table has existed since migration 0002 and nothing has ever written to
    it (D62). An empty ledger makes the convergence check the plan asks for --
    "identical ledger checksums" -- a comparison of two absences.

    Written by this program over the container socket as the superuser, *not*
    by the migration plane. dbmate's `schema_migrations` records that a version
    ran; this records which bytes ran, and a migration role that could write its
    own audit record could record bytes it did not execute. migration_user has
    no privilege on this table at all, which is the property that makes the row
    worth reading.

    **The statement is `migrations.ledger_insert_statement`** since Session 22
    Run 3; this function keeps its name, its two arguments and its exit code,
    and owns what it always owned -- issuing the statement over the container
    socket, and turning a failure into `EXIT_CONTRACT` with the message an
    operator reads. `apg dev` issues the same statement over its own socket
    (ADR 0203), so the bytes recorded on a dev cluster and on a deployment are
    built by one function.

    D1096 is why that function reads EVERY set's lock: it used to build its
    digests from the release lock alone and index them by every RENDERED
    version, so the first deploy that rendered a project migration raised
    `KeyError` **after dbmate had already applied it**. A cluster that has moved
    and a record that has not is the worst order a failure can arrive in.
    """
    statement = migrations.ledger_insert_statement(document, Path(rendered_dir), REPO_ROOT)
    recorded = statement.count("), (") + 1

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
            "-v",
            "ON_ERROR_STOP=1",
            "-qtA",
            "-f",
            "-",
        ],
        input=statement,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(
            f"migrate: the ledger could not be recorded: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return EXIT_CONTRACT

    print(f"migrate: ledger recorded for {recorded} migrations")
    return 0


def project_set_from_manifest(project_path: str) -> migrations.MigrationSet:
    """The set a project manifest names, read from the manifest itself.

    The manifest and NOT a deployed document, because `freeze-lock --project`
    runs on a workstation before anything is deployed -- which is the whole
    point of a freeze. `migrations.project_set_from` reads the document and is
    what the render and the ledger use; these two verbs are the one place the
    manifest is the only thing that exists.
    """
    from agentic_postgres import config

    document = config.load_project_manifest(Path(project_path))
    named = config.project_migration_set(document)
    if named is None:
        raise migrations.ProjectSetError(
            f"{project_path} declares no migrations.set, so it has no lock of its own. "
            "A project's set is declared at project manifest schema version 5 "
            "(ADR 0198); without one this project applies the release's migrations "
            "and nothing else."
        )
    return migrations.MigrationSet(label="project", root=REPO_ROOT / named / "migrations")


def _control_facility(project_path: str) -> bool:
    """Does the manifest naming this set enable the control-plane facility? (ADR 0251.)

    Read from the manifest for `project_set_from_manifest`'s reason: these verbs run
    on a workstation before anything is deployed, and the lint needs the facility
    to know whether the identity service's role may be granted anything.
    """
    from agentic_postgres import config

    return config.control_enabled(config.load_project_manifest(Path(project_path)))


def freeze_project_lock(project_path: str, declared_follows: str | None = None) -> int:
    """Freeze the project's own lock. The release's is never touched.

    `follows_release_version` is computed here, at the freeze, from the release
    manifest's newest version -- and recorded, rather than recomputed at verify
    time. The release gains migrations after a project freezes, and a check that
    compared against the release's CURRENT newest would invalidate every project
    lock the day a platform migration shipped. What the rule needs is that the
    freeze was done under it, and the recorded value is that evidence.

    **`--follows` declares the record instead (ADR 0210), and for a set frozen
    against an EARLIER release it is the only way to record the truth.** This
    freeze runs on the checkout in hand, and for such a set that checkout is a
    later release by construction -- so the computed value is wrong, the
    refusal fires, and re-freezing computes the same wrong value again (D1436).
    The declared value is checked against the release's own append-only
    manifest, and the lock records that it was DECLARED, because a record that
    is sometimes measured and sometimes asserted with no way to tell which is a
    `null` that looks measured (D600).
    """
    migration_set = project_set_from_manifest(project_path)
    manifest = migration_set.load_manifest()
    if declared_follows is None:
        follows = migrations.newest_release_version()
        source = migrations.FOLLOWS_COMPUTED
    else:
        # Before anything else this command does: an unusable declaration must
        # not be reported alongside a set the freeze then refuses for its own
        # reasons, because the operator would repair the wrong one.
        migrations.assert_declarable_release_version(declared_follows)
        follows = declared_follows
        source = migrations.FOLLOWS_DECLARED
    lock = migrations.build_lock(
        manifest,
        migration_set.root,
        follows_release_version=follows,
        follows_release_version_source=source,
    )

    # Refuse before writing. A freeze that wrote a lock recording a rule it
    # breaks would make `verify-lock` the first thing to notice, which is one
    # commit too late.
    migrations.verify_lock(manifest, lock, migration_set.root)
    migrations.lint_project_set(migration_set, control=_control_facility(project_path))

    migration_set.lock_path.write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"migrate: wrote {migration_set.lock_path} ({len(lock['migrations'])} migrations)")
    print(f"  follows_release_version {follows}, {source}; the release lock was not touched.")
    print("  Review and commit it before the gate runs.")
    return 0


def verify_project_lock(project_path: str) -> str:
    """Verify a project's own set, RETURNING the sentence rather than printing it.

    **D1403.** The caller used to print the release half's success before
    calling this, so when this refused -- which it does for every project that
    declares no set of its own -- the last line an operator saw was
    *"the released lock agrees with the manifest and templates"*, on exit 5.
    The sentence was true; its position was the defect. Both halves' sentences
    are now printed together, after both halves have agreed, so a refusal is
    the last thing on the terminal.
    """
    migration_set = project_set_from_manifest(project_path)
    manifest = migration_set.load_manifest()
    lock = migration_set.load_lock()
    migrations.verify_lock(manifest, lock, migration_set.root)
    migrations.lint_project_set(migration_set, control=_control_facility(project_path))

    # The record AND its provenance, because the sentence is what an operator
    # reads before a deploy and "which release was this reviewed against" has
    # two different answers depending on who wrote it (ADR 0210).
    record = migrations.follows_record(lock)
    recorded = (
        "no ordering record"
        if record is None
        else f"follows_release_version {record[0]}, {record[1]}"
    )
    return (
        f"migrate: {migration_set.root} agrees with its own lock, and the set is "
        f"within what a project may contain ({recorded})"
    )


# ---------------------------------------------------------------------------
# propose and approve (ADR 0243)
# ---------------------------------------------------------------------------

#: `apg dev`'s own command: `propose` applies the set with the product's own
#: environment (D1114, D1861), never a cluster of its own.
DEV_SH = REPO_ROOT / "bin" / "dev.sh"

#: Where `projects/<slug>/` is found for the records. The checkout, always; a
#: name rather than a literal so a proof can write its records under a
#: temporary root instead of the tree's own `projects/example/proposals/`.
PROJECTS_ROOT = REPO_ROOT

#: `bin/dev.sh up` is ~10-30 s (rig 35b: 22.5-29.4 s); six times that is a
#: hang, not a slow cluster.
DEV_UP_TIMEOUT = 180

#: The line `bin/dev.sh up` prints after its migrations, measured by rig 35b:
#: `dev: 39 migrations applied as <the project's migration_user role>`. The
#: count is the WHOLE cluster's -- the release's and the set's (D1895).
DEV_APPLIED = re.compile(r"^dev: (\d+) migrations applied as (\S+)$", re.MULTILINE)

#: The release's own capability manifest, the joint contract's other half --
#: what `bin/render-evaluation-report.py` and `bin/mcp-contract.sh` compile
#: against when no host manifest is named.
RELEASE_CAPABILITIES = REPO_ROOT / "capabilities.example.yaml"
RELEASE_CONTRACT = REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"


class Refusal(Exception):
    """`propose` or `approve` refuses, with the exit code the usage documents."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dev(verb: str, project_path: str, timeout: int = 120) -> subprocess.CompletedProcess:
    """One `bin/dev.sh` verb, stdin closed, output captured (ADR 0218)."""
    return subprocess.run(
        [str(DEV_SH), verb, "--project", project_path],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _write_exclusive(target: Path, data: bytes) -> None:
    """Create ``target`` with these bytes, or Refusal(5) if it exists."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        raise Refusal(
            EXIT_CONTRACT,
            f"{target} already exists. A record is written once; a changed set has a new "
            "digest and so a new proposal",
        ) from None
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def _project(project_path: str) -> tuple[dict, str, migrations.MigrationSet]:
    manifest = config.load_project_manifest(Path(project_path))
    named = config.project_migration_set(manifest)
    if named is None:
        raise Refusal(
            2,
            f"{project_path} declares no migrations.set, so it has no set to propose or "
            "approve. A proposal is a record of a project's OWN set (ADR 0243)",
        )
    return (
        manifest,
        named,
        migrations.MigrationSet(label="project", root=REPO_ROOT / named / "migrations"),
    )


def _deployed_contract(manifest: dict) -> tuple[dict, object | None]:
    """The contract this project deploys, narrowed by its profile, and its inputs.

    `bin/mcp-contract.sh check --project`'s reading: the joint contract for a
    project with capabilities of its own, the release's otherwise, then the
    profile applied -- so an approval a profile adds is visible (D1869).
    """
    inputs = capability_manifest.project_inputs(manifest)
    if inputs is None:
        contract = json.loads(RELEASE_CONTRACT.read_text(encoding="utf-8"))
    else:
        release = config.load_capabilities_manifest(RELEASE_CAPABILITIES)
        contract = capability_manifest.compile_joint_contract(release, inputs)
    if manifest["schema_version"] >= config.PROJECT_PROFILE_FROM:
        contract = capability_compiler.apply_profile(contract, manifest["mcp"]["profile"])
    return contract, inputs


def _harness(contract: dict, inputs) -> dict:
    """Cases ASKED, never results (D1860), or why there are none."""
    if inputs is None:
        return {"not_applicable": "the manifest declares no capabilities"}
    derived = evaluation_harness.derive_cases(contract)
    written: tuple = ()
    own = inputs.root / "evaluation-cases.yaml"
    for cases in (evaluation_harness.WRITTEN_CASES_PATH,) + ((own,) if own.is_file() else ()):
        written += evaluation_harness.load_written_cases(
            contract,
            cases,
            disabled=frozenset(
                capability_manifest.disabled_release_capabilities(inputs.capabilities)
            ),
        )
    return {
        "contract_sha256": evaluation_harness.contract_digest(contract),
        "derived": len(derived),
        "written": len(written),
        "capabilities": len(evaluation_harness.coverage(contract, derived, written)),
        "note": "cases asked of the contract, not results",
    }


def _dev_apply(project_path: str) -> dict:
    """`bin/dev.sh up` on an empty cluster, read and timed, then `down` (D1861).

    **Refuses before starting when an environment exists** -- up, stopped, or
    a state `status` could not read: `propose` never downs somebody's
    environment, and a status it cannot read is not one it may assume absent
    (ADR 0195). Only `status`'s *no environment* answer (exit 4) proceeds.
    """
    status = _dev("status", project_path)
    if status.returncode != 4:
        raise Refusal(
            3,
            f"an apg dev environment exists for this project (`bin/dev.sh status` exited "
            f"{status.returncode}: {status.stdout.strip() or status.stderr.strip()}). "
            f"propose applies the set to an EMPTY cluster and never removes yours: run "
            f"`bin/apg.sh dev down --project {project_path}` first",
        )
    started = time.monotonic()
    try:
        try:
            up = _dev("up", project_path, timeout=DEV_UP_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise Refusal(
                EXIT_CONTRACT,
                f"`bin/dev.sh up` did not finish in {DEV_UP_TIMEOUT} s; no proposal written",
            ) from None
        seconds = round(time.monotonic() - started, 1)
    finally:
        _dev("down", project_path)
    if up.returncode == 4:
        raise Refusal(3, f"the project is not rendered here: {up.stderr.strip()}")
    if up.returncode != 0:
        raise Refusal(
            EXIT_CONTRACT,
            f"the set did not apply on an empty cluster (`bin/dev.sh up` exited "
            f"{up.returncode}): {up.stderr.strip()[-600:]}. No proposal written",
        )
    applied = DEV_APPLIED.search(up.stdout)
    if applied is None:
        raise Refusal(
            EXIT_CONTRACT,
            "`bin/dev.sh up` exited 0 and printed no `dev: N migrations applied as ROLE` "
            "line, so how many migrations applied could not be read. No proposal written",
        )
    return {"exit": 0, "migrations_applied": int(applied.group(1)), "seconds": seconds}


def propose(project_path: str, by: str) -> int:
    """Write `projects/<slug>/proposals/<set_digest>.json` (ADR 0243, GOV-PROPOSE-001)."""
    try:
        proposal.require_name(by)
    except proposal.ProposalError as error:
        raise Refusal(2, str(error)) from None
    manifest, named, project_set = _project(project_path)
    set_manifest = project_set.load_manifest()
    lock = project_set.load_lock()
    migrations.verify_lock(set_manifest, lock, project_set.root)
    migrations.lint_project_set(project_set, control=config.control_enabled(manifest))

    digest = migrations.set_digest(project_set)
    project_root = PROJECTS_ROOT / named
    target = proposal.proposal_path(project_root, digest)
    if target.exists():
        raise Refusal(EXIT_CONTRACT, f"{target} already exists; this set is already proposed")

    contract, inputs = _deployed_contract(manifest)
    bodies = sql_surface.final_function_bodies(set_manifest, project_set.root)
    findings = approval_gate.unguarded(
        contract, bodies, migrations.release_functions(migrations.release_set())
    )
    refused = approval_gate.refused(findings)
    if refused:
        for finding in findings:
            print(f"migrate: {approval_gate.describe(finding)}", file=sys.stderr)
        raise Refusal(
            EXIT_CONTRACT,
            f"{len(refused)} gated tool(s) do not call {approval_gate.GUARD} first; no "
            "proposal written (ADR 0242)",
        )

    surface_path = api_surface.project_contract_path(REPO_ROOT / named)
    if not surface_path.is_file():
        raise Refusal(
            EXIT_CONTRACT,
            f"{surface_path.relative_to(REPO_ROOT)} does not exist, so the set's surface "
            "cannot be read against a reviewed one",
        )
    reviewed = api_surface.load_project_surface(surface_path)
    final = sql_surface.final_surface(set_manifest, project_set.root)
    surface = {
        "functions": [
            {"name": name, "reviewed": name in reviewed["rpcs"]}
            for name in sorted(final["functions"])
        ],
        "views": [
            {"name": name, "reviewed": name in reviewed["relations"]}
            for name in sorted(final["views"])
        ],
    }

    if inputs is None:
        capability_digest: str | dict = {"not_applicable": "the manifest declares no capabilities"}
    else:
        capability_digest = sha256(
            capability_manifest.project_contract_path(inputs.root).read_bytes()
        ).hexdigest()
    harness = _harness(contract, inputs)
    destructive = migrations.destructive_findings(project_set)
    record_follows = migrations.follows_record(lock)

    dev_apply = _dev_apply(project_path)

    record = proposal.build_proposal(
        project_slug=manifest["project"]["slug"],
        set_digest=digest,
        set_root=named,
        versions=[
            {"version": entry["version"], "name": entry["name"]}
            for entry in set_manifest["migrations"]
        ],
        follows_release_version=None if record_follows is None else record_follows[0],
        follows_release_version_source=None if record_follows is None else record_follows[1],
        template_version=template_version(),
        release_lock_sha256=migrations.set_digest(migrations.release_set()),
        destructive=[finding._asdict() for finding in destructive],
        dev_apply=dev_apply,
        surface=surface,
        approval_gate=[finding._asdict() for finding in findings],
        harness=harness,
        capability_contract_sha256=capability_digest,
        declared_by=by,
        declared_at=_now(),
    )
    _write_exclusive(target, proposal.record_bytes(record))
    print(
        f"proposal {digest[:16]} written: {named}/{proposal.PROPOSALS_SUBDIR}/{digest}.json "
        f"({len(destructive)} destructive finding(s))"
    )
    return 0


def approve(project_path: str, digest: str, by: str) -> int:
    """Write `<set_digest>.approval.json` naming the proposal file's bytes (ADR 0243)."""
    try:
        proposal.require_name(by)
        proposal.require_digest(digest)
    except proposal.ProposalError as error:
        raise Refusal(2, str(error)) from None
    _manifest, named, _project_set = _project(project_path)
    project_root = PROJECTS_ROOT / named
    source = proposal.proposal_path(project_root, digest)
    if not source.is_file():
        raise Refusal(
            EXIT_CONTRACT,
            f"no proposal at {named}/{proposal.PROPOSALS_SUBDIR}/{digest}.json; "
            "`bin/migrate.sh propose` writes it first",
        )
    data = source.read_bytes()
    try:
        record = proposal.build_approval(data, by, _now())
    except proposal.ProposalError as error:
        raise Refusal(EXIT_CONTRACT, str(error)) from None
    if record["set_digest"] != digest:
        raise Refusal(
            EXIT_CONTRACT,
            f"the proposal at {source.name} names set {record['set_digest'][:16]}, not "
            f"{digest[:16]}; its file name and its content disagree",
        )
    target = proposal.approval_path(project_root, digest)
    _write_exclusive(target, proposal.record_bytes(record))
    print(
        f"approval of proposal {digest[:16]} written: {named}/{proposal.PROPOSALS_SUBDIR}/"
        f"{digest}.approval.json (declared by {by})"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--outputs")
    parser.add_argument("--rendered-dir")
    parser.add_argument("--project")
    parser.add_argument("--follows")
    parser.add_argument("--by")
    parser.add_argument("--proposal")
    arguments = parser.parse_args(argv)

    # A declaration about a project set's ordering record, so it means nothing
    # without a set. Refused rather than ignored: a flag silently dropped is how
    # an operator comes to believe a record was written that was not.
    if arguments.follows and not (arguments.mode == "freeze-lock" and arguments.project):
        print(
            "migrate: --follows declares the release version a PROJECT set was frozen "
            "against, so it is only meaningful with `freeze-lock --project` (ADR 0210). "
            "The release's own lock has no such record.",
            file=sys.stderr,
        )
        return 2

    if arguments.follows:
        # Checked HERE as well as inside the freeze, and the two are not
        # redundant: the function refuses whoever calls it, and this maps the
        # refusal to exit 2 -- a value an operator typed is invalid operator
        # input, not the contract drift EXIT_CONTRACT means (rig 25m's reading
        # of what each code tells a reader).
        try:
            migrations.assert_declarable_release_version(arguments.follows)
        except migrations.ProjectSetError as error:
            print(f"migrate: {error}", file=sys.stderr)
            return 2

    # `--by` names the person a record is declared by and `--proposal` the
    # set an approval names; both belong to the two record verbs and nothing
    # else (ADR 0243). Refused rather than ignored, `--follows`' reason.
    if arguments.by is not None and arguments.mode not in ("propose", "approve"):
        print("migrate: --by belongs to propose and approve", file=sys.stderr)
        return 2
    if arguments.proposal is not None and arguments.mode != "approve":
        print("migrate: --proposal belongs to approve", file=sys.stderr)
        return 2

    try:
        if arguments.mode in ("propose", "approve"):
            if not arguments.project or arguments.by is None:
                print(f"migrate: {arguments.mode} requires --project and --by", file=sys.stderr)
                return 2
            if arguments.mode == "propose":
                return propose(arguments.project, arguments.by)
            if arguments.proposal is None:
                print("migrate: approve requires --proposal DIGEST", file=sys.stderr)
                return 2
            return approve(arguments.project, arguments.proposal, arguments.by)

        if arguments.mode == "freeze-lock":
            if arguments.project:
                return freeze_project_lock(arguments.project, arguments.follows)
            manifest = migrations.load_manifest()
            lock = migrations.build_lock(manifest)
            migrations.LOCK_PATH.write_text(
                json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(f"migrate: wrote {migrations.LOCK_PATH} ({len(lock['migrations'])} migrations)")
            print("  Review and commit it before the gate runs.")
            return 0

        if arguments.mode == "verify-lock":
            # The release's, always. `--project` adds the project's; it never
            # replaces it, because a project verb that could leave the release
            # lock unverified would be the one way to render an unlocked
            # platform migration.
            manifest = migrations.load_manifest()
            migrations.verify_lock(manifest, migrations.load_lock())
            released = "migrate: the released lock agrees with the manifest and templates"
            if arguments.project:
                # Computed first, printed last (D1403): `verify_project_lock`
                # raises for a project with no set of its own, and a sentence
                # already on the terminal cannot be taken back.
                project_line = verify_project_lock(arguments.project)
                print(released)
                print(project_line)
                return 0
            print(released)
            return 0

        document = json.loads(Path(arguments.outputs).read_text(encoding="utf-8"))

        # Every path that touches a project verifies the lock first. A render
        # or an apply against a manifest the lock does not cover is the state
        # ADR 0028 exists to prevent, and checking it here means no caller has
        # to remember to.
        manifest = migrations.load_manifest()
        migrations.verify_lock(manifest, migrations.load_lock())

        if arguments.mode == "render":
            for version, name, sha in render_set(document):
                print(f"{version}  {sha[:16]}  {name}")
            return 0

        if arguments.mode in ("status", "up"):
            # The rendered set, then the ledger. Both, in that order, and the
            # first is not a substitute for the second: until Run 7 this printed
            # the set and returned 0, so `migrate up` reported success having
            # applied nothing at all (D60). Printing what *should* be applied is
            # only useful next to what a cluster says is applied.
            rendered = render_set(document)
            print(f"migrate: the rendered set for this project ({len(rendered)}):")
            for version, name, sha in rendered:
                print(f"  {version}  {sha[:16]}  {name}")

            if not arguments.rendered_dir:
                print("migrate: --rendered-dir is required for status and up", file=sys.stderr)
                return 2
            # The INSTALLED manifest (`bin/migrate.sh` passes the one it was
            # handed -- deploy step 6's copy), because `approvals_required` is
            # the project's own answer and the gate reads it (D1865).
            if not arguments.project:
                print("migrate: --project is required for status and up", file=sys.stderr)
                return 2
            approvals_required = config.approvals_required(
                config.load_project_manifest(Path(arguments.project))
            )

            # Currency first, then integrity (D1053). A stale render is
            # internally consistent, so the integrity check below passes on it
            # and says nothing; asking "is this the set this checkout declares"
            # first means the answer names the right remedy.
            assert_installed_render_is_current(rendered, arguments.rendered_dir)
            assert_rendered_files_match(arguments.rendered_dir)
            return run_every_set(
                arguments.mode,
                document,
                arguments.rendered_dir,
                approvals_required=approvals_required,
            )

    except config.ManifestError as error:
        # An invalid project manifest, which is INVALID OPERATOR INPUT and not a
        # contract drift -- so exit 2, the code `deploy.sh --render-only`,
        # `render-mcp-catalog.py` and `render-evaluation-report.py` already give
        # for the same file (measured, rig 25m).
        #
        # Before this clause the exception escaped: `freeze-lock --project` on a
        # manifest naming a directory that does not exist printed a full Python
        # traceback and exited 1, and 1 is not a code the runbook's convention
        # defines at all. **This is D1340 exactly, one caller over** -- that row
        # repaired `bin/render-config.py`, which was the third caller of a
        # decision `bin/migrate.py` and `bin/dev.py` already had, and nobody
        # grepped for the fourth. Rig 25m grepped: of the twenty-five `bin/`
        # commands that load a manifest, this was the only one that raised.
        #
        # The second walk met it at step 9 of the guide, which is the first
        # command an adopter runs against a manifest they wrote themselves.
        print(f"migrate: {error}", file=sys.stderr)
        return 2

    except Refusal as refusal:
        print(f"migrate: {refusal}", file=sys.stderr)
        return refusal.code

    except migrations.MigrationError as error:
        print(f"migrate: {error}", file=sys.stderr)
        return EXIT_CONTRACT

    except (evaluation_harness.HarnessError, proposal.ProposalError) as error:
        print(f"migrate: {error}", file=sys.stderr)
        return EXIT_CONTRACT

    print(f"migrate: unknown mode {arguments.mode!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
