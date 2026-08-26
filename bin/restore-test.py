#!/usr/bin/env python3
"""The disposable restore rehearsal, and the evidence document it writes.

**A restore that cannot be verified is a failed restore.** That sentence has
been in this command's `--help` since Session 1, when the command was a stub that
did nothing, and it is the reason the drill does not end when pgBackRest exits 0.
Measured (rig 8): a restore to a target the archive cannot reach **exits 0** and
produces an instance that never promotes and never accepts a connection. That is
`postgrest --ready` returning 0 while every request 404s (D145), and
`pgbackrest info` exiting 0 for a stanza that does not exist (D548), a third
time. The verdict comes from querying the promoted instance.

What this command does, in order:

  1. Reads the deployed document for the stanza, the project key, the database
     name and **the live volume** -- the one name the whole drill is defined
     against. Nothing is re-derived (ADR 0002).
  2. Reads the running database container for its image, its pgBackRest mounts
     and its `PGBACKREST_*` environment. The active secret generation changes on
     every deploy, so any path into it is derived, never typed.
  3. Derives the drill's own volume and containers through `naming`, refuses the
     plan if anything in it could reach the live volume (ADR 0151 §5), and
     writes the state file the shell wrapper's `trap` tears down from.
  4. Restores into the drill volume, starts a cluster on it with archiving
     **off**, waits for promotion, and queries it.
  5. Writes `evidence/restore-drill-<key>-<id>.json` and removes everything it
     created, pass or fail.

Exit codes (runbook section 2 convention):
  0  the drill ran and the restore verified
  2  invalid operator input
  3  missing local prerequisite, or not root
  5  the deployment or the repository refused the operation
  6  the drill ran and its answer is "no" -- the restore did not verify
  7  the plan was refused as unsafe; nothing was started
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import (  # noqa: E402
    backup_report,
    naming,
    restore_drill,
    runtime_override,
)
from agentic_postgres.secrets_contract import load_secret_contract  # noqa: E402

EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_STATE = 5
EXIT_REFUSED = 6
EXIT_UNSAFE = 7

#: The database container is selected by , not from here.
#:
#: D566 recorded that  was spelled in five  commands and
#: left it alone. Run 11 measured that **the postgres service does not carry it**
#: -- so of those five spellings, the two that select a DATABASE container were
#: both wrong and both unexercised (D587). They now share one function; the three
#: that select an edge-facing service keep their own, because those services do
#: carry the label.

#: The uid pgBackRest and the postmaster both run as inside the image.
POSTGRES_UID = "999"

#: An identity the drill asserts in order to see NOTHING (`REC-SMOKE-001`).
#:
#: A fixed, obviously-synthetic UUID rather than a random one, so that a row it
#: ever matched would be a row somebody wrote deliberately. The RLS check needs
#: both halves -- the owner sees rows, and a second identity sees none -- because
#: the first half alone passes against a table whose policies were dropped.
SMOKE_FOREIGN_OWNER = "00000000-0000-4000-8000-0000000000ff"

#: How long the drill waits for a restored instance to leave recovery.
#:
#: A bound, not a measurement, and it is named so that it is a decision somebody
#: can revise. Rig 8 promoted in 3.4 seconds against a 30 MB cluster with two WAL
#: segments to replay; recovery time scales with the distance from the backup set
#: to the target, which is why the drill records it as a measurement of its own.
PROMOTION_TIMEOUT_SECONDS = 900
RESTORE_TIMEOUT_SECONDS = 7200
QUICK_TIMEOUT_SECONDS = 120

#: `pgbackrest restore` prints its own elapsed time on the last line at info
#: level. Recorded BESIDE our wall time and never instead of it: it excludes
#: recovery entirely (ADR 0152 §4).
_REPORTED_MS = re.compile(r"restore command end: completed successfully \((?P<ms>\d+)ms\)")


class OperatorError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def require_root() -> None:
    if os.geteuid() != 0:
        raise OperatorError(
            EXIT_PREREQUISITE,
            "must run as root: the deployed document is root-owned, and the drill "
            "creates a volume and two containers over the local Docker socket.",
        )


def docker(*arguments: str, timeout: int = QUICK_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *arguments], capture_output=True, text=True, check=False, timeout=timeout
    )


# ---------------------------------------------------------------------------
# Reading what exists
# ---------------------------------------------------------------------------


def load_document(project_dir: Path) -> dict[str, Any]:
    """The deployed document, from the rendered project directory.

    `--project-dir` rather than `--outputs` because this command's `--help` has
    said `--project-dir` since Session 1 and the flag is part of a contract
    paragraph that was already the right one (D524). The directory is what the
    render publishes; `outputs.json` is one file in it.
    """
    if not project_dir.is_dir():
        raise OperatorError(EXIT_INPUT, f"not a directory: {project_dir}")
    path = project_dir / "outputs.json"
    if not path.is_file():
        raise OperatorError(
            EXIT_INPUT,
            f"{path} does not exist. --project-dir takes a RENDERED project "
            "directory (the one `deploy.sh` publishes under .generated/), not a "
            "manifest and not a checkout.",
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise OperatorError(EXIT_STATE, f"{path} is not readable as JSON: {error}") from error
    if "database" not in document:
        raise OperatorError(EXIT_INPUT, f"{path} is not a deployed document (no 'database')")
    return document


def project_key(document: dict[str, Any]) -> str:
    """The project key, which BOTH document kinds carry.

    `bin/backup.py` has the same accessor for the same reason: the deployed
    document publishes no `compose` block, so the key is the one identity a
    caller can rely on being there (D592).
    """
    key = (document.get("project") or {}).get("key")
    if not key:
        raise OperatorError(EXIT_STATE, "the deployed document names no project key")
    return str(key)


def database_container(document: dict[str, Any]) -> str:
    """The running database container, found by label rather than predicted."""
    # Derived from the project key rather than read from `compose.project_name`
    # (D592). Only the RENDERED document publishes that field; the DEPLOYED
    # document -- which is what `--outputs /etc/agentic-postgres/projects/<key>/`
    # names, and what an operator actually passes -- does not carry a `compose`
    # block at all. `naming.compose_project_name` is the one authority and
    # `naming.derive` calls it too, so this is not a second derivation.
    filters = list(
        runtime_override.database_container_filters(
            naming.compose_project_name(project_key(document))
        )
    )
    arguments = ["ps"]
    for value in filters:
        arguments += ["--filter", value]
    arguments += ["--format", "{{.Names}}"]

    names = [line for line in docker(*arguments).stdout.split() if line]
    if len(names) != 1:
        raise OperatorError(
            EXIT_STATE,
            f"expected exactly one running database container matching {filters}, found "
            f"{names or 'none'}. A drill reads the archiver's own configuration off "
            "that container, so there is nothing here to read.",
        )
    return names[0]


def inspect_container(name: str) -> dict[str, Any]:
    result = docker("inspect", name)
    if result.returncode != 0:
        raise OperatorError(EXIT_STATE, f"docker inspect {name} failed: {result.stderr.strip()}")
    try:
        entries = json.loads(result.stdout)
    except ValueError as error:
        raise OperatorError(EXIT_STATE, f"docker inspect did not return JSON ({error})") from error
    if len(entries) != 1:
        raise OperatorError(EXIT_STATE, f"docker inspect {name} returned {len(entries)} entries")
    return entries[0]


def read_repository(container: str, stanza: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """`pgbackrest info`, summarised, and the raw backup list beside it.

    The summary is `backup_report`'s, in one place, so this command and the
    deploy's observer cannot disagree about what a repository's report means --
    and **nothing here reads an exit code**, because `pgbackrest info` exits 0 in
    every state including a stanza that does not exist (D548).

    The raw list comes back too, because the backup *set* the restore chose has
    to be looked up in it by label (ADR 0152 §3).
    """
    result = docker(
        "exec",
        "-u",
        POSTGRES_UID,
        container,
        "pgbackrest",
        f"--stanza={stanza}",
        "info",
        "--output=json",
    )
    if not result.stdout.strip():
        raise OperatorError(
            EXIT_STATE,
            f"pgbackrest info produced no output (exit {result.returncode}): "
            f"{result.stderr.strip()[:400]}",
        )
    try:
        document = json.loads(result.stdout)
    except ValueError as error:
        raise OperatorError(EXIT_STATE, f"pgbackrest info did not return JSON ({error})") from error
    try:
        summary = backup_report.summarise(document, stanza)
    except ValueError as error:
        raise OperatorError(EXIT_STATE, str(error)) from error

    entries = [entry for entry in document if entry.get("name") == stanza]
    return summary, list(entries[0].get("backup") or [])


# ---------------------------------------------------------------------------
# The drill's own resources
# ---------------------------------------------------------------------------


def new_drill_id() -> str:
    """A per-drill token: the UTC minute, then four random hex characters.

    The timestamp so that a leftover says when it was left, and the random half
    so that two drills started in the same minute cannot collide. It is
    validated by `naming.restore_drill_names`, which is where the shape of a
    derived name is decided rather than here.
    """
    return datetime.now(UTC).strftime("%Y%m%d%H%M") + secrets.token_hex(2)


def write_state_file(path: Path, plan: restore_drill.DrillPlan) -> None:
    """What the shell wrapper's `trap` tears down from.

    Written **after** the plan is asserted disposable and **before** anything is
    created, so that a drill killed between those two points leaves a file naming
    resources that do not exist yet -- which the teardown handles, because
    `docker rm` on an absent name exits 1 and the teardown reads that as "already
    gone" only for names it put there itself.

    `live_volume` is in the file so the wrapper's `trap` can **refuse** to remove
    it. The trap does not derive that name and could not; it compares.
    """
    path.write_text(
        "".join(
            f"{key}={value}\n"
            for key, value in (
                ("live_volume", plan.live_volume),
                ("live_container", plan.live_container),
                ("drill_volume", plan.names.volume),
                ("drill_container", plan.names.container),
                ("drill_restore_container", plan.names.restore_container),
            )
        ),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def refuse_a_leftover(plan: restore_drill.DrillPlan) -> None:
    """The drill's volume must not already exist.

    Measured (rig 8, arm J): `docker volume create` on a name that already exists
    **exits 0** and keeps the existing volume and its labels. So the exit code of
    a create says nothing about whose volume it is, and the pre-flight is an
    `inspect` -- which exits 1 for an absent volume and 0 for a present one.
    """
    for name in (plan.names.volume,):
        if docker("volume", "inspect", name).returncode == 0:
            raise OperatorError(
                EXIT_STATE,
                f"the drill volume {name} already exists. `docker volume create` "
                "would adopt it silently, so this refuses instead. Remove it by hand "
                "once you know what left it there.",
            )
    for name in (plan.names.container, plan.names.restore_container):
        if docker("inspect", name).returncode == 0:
            raise OperatorError(
                EXIT_STATE, f"the drill container {name} already exists; refusing to reuse it."
            )


def teardown(plan: restore_drill.DrillPlan) -> list[str]:
    """Remove exactly what the drill created, and report what could not be found.

    **Without `-f`**, deliberately. Measured: `docker rm -f` and
    `docker volume rm -f` exit 0 for a name that does not exist, so the forced
    form cannot tell "removed" from "was never there" -- and §4.5 of the plan
    requires that a teardown which cannot find its target exits non-zero rather
    than widening its search. Containers are stopped first, then removed.
    """
    problems: list[str] = []
    for name in (plan.names.container, plan.names.restore_container):
        if docker("inspect", name).returncode != 0:
            continue
        docker("stop", "-t", "10", name, timeout=QUICK_TIMEOUT_SECONDS)
        result = docker("rm", name)
        if result.returncode != 0:
            problems.append(f"container {name}: {result.stderr.strip()}")
    if docker("volume", "inspect", plan.names.volume).returncode == 0:
        result = docker("volume", "rm", plan.names.volume)
        if result.returncode != 0:
            problems.append(f"volume {plan.names.volume}: {result.stderr.strip()}")
    return problems


# ---------------------------------------------------------------------------
# The drill
# ---------------------------------------------------------------------------


def run_arguments(plan: restore_drill.DrillPlan, name: str, *, detached: bool) -> list[str]:
    """The common `docker run` prefix for both drill containers.

    Every mount goes through `Mount.as_mount_argument`, so the rig that drives
    this command with a stubbed `docker` reads exactly the strings the daemon
    would.
    """
    arguments = ["run", "--name", name, "-u", f"{POSTGRES_UID}:{POSTGRES_UID}"]
    arguments += ["-d"] if detached else ["--rm"]
    for mount in plan.mounts():
        arguments += ["--mount", mount.as_mount_argument()]
    for key, value in sorted(plan.environment.items()):
        arguments += ["--env", f"{key}={value}"]
    if plan.network:
        arguments += ["--network", plan.network]
    return arguments


def run_restore(
    plan: restore_drill.DrillPlan, arguments: tuple[str, ...]
) -> tuple[subprocess.CompletedProcess, float]:
    command = run_arguments(plan, plan.names.restore_container, detached=False)
    command += ["--entrypoint", "pgbackrest", plan.image, *arguments]
    started = time.monotonic()
    result = docker(*command, timeout=RESTORE_TIMEOUT_SECONDS)
    return result, time.monotonic() - started


def start_instance(plan: restore_drill.DrillPlan) -> None:
    command = run_arguments(plan, plan.names.container, detached=True)
    command += [plan.image, *restore_drill.instance_command()]
    result = docker(*command)
    if result.returncode != 0:
        raise OperatorError(
            EXIT_STATE, f"the drill instance did not start: {result.stderr.strip()[:400]}"
        )


def query(plan: restore_drill.DrillPlan, sql: str) -> tuple[int, str]:
    """One query against the drill instance, over the container's own socket.

    `docker exec -i`, and the `-i` is not optional: without it stdin is not
    attached, psql runs nothing, and the container exits 0 having done nothing --
    which D552 is the record of a rig discovering the hard way.
    """
    result = docker(
        "exec",
        "-i",
        plan.names.container,
        "psql",
        "-U",
        "postgres",
        "-d",
        plan.database,
        "-X",
        "-qtA",
        "-c",
        sql,
    )
    return result.returncode, result.stdout.strip()


def wait_for_promotion(plan: restore_drill.DrillPlan) -> float:
    """Wait until the restored instance has left recovery, or say which way it failed.

    Three states, never collapsed (ADR 0152 §6): **promoted**, **still
    recovering**, **dead**. A restore whose target the archive cannot reach exits
    0 and produces the third -- `FATAL: recovery ended before configured recovery
    target was reached` -- so "the container is not answering" and "the container
    has gone" are different findings and the second one carries its own log.
    """
    started = time.monotonic()
    deadline = started + PROMOTION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        running = docker("inspect", "-f", "{{.State.Running}}", plan.names.container)
        if running.stdout.strip() != "true":
            logs = docker("logs", "--tail", "40", plan.names.container)
            raise OperatorError(
                EXIT_REFUSED,
                "the restored instance exited before it promoted. pgBackRest reported "
                "success, so the restore wrote a data directory -- what failed is "
                "recovery. Its last words:\n" + (logs.stdout or "") + (logs.stderr or ""),
            )
        code, answer = query(plan, "SELECT pg_is_in_recovery()")
        if code == 0 and answer == "f":
            return time.monotonic() - started
        time.sleep(2)

    logs = docker("logs", "--tail", "40", plan.names.container)
    raise OperatorError(
        EXIT_REFUSED,
        f"the restored instance did not promote within {PROMOTION_TIMEOUT_SECONDS}s. "
        "That bound is chosen rather than measured; recovery time scales with the "
        "distance from the backup set to the target. Its last words:\n"
        + (logs.stdout or "")
        + (logs.stderr or ""),
    )


def observe_restored_instance(plan: restore_drill.DrillPlan) -> dict[str, Any]:
    """Everything the evidence document takes from the restored cluster.

    Read here, once, in one place, so the document cannot carry two answers from
    two moments. Each field's source and its plausible wrong source are in ADR
    0152 §1; the one worth repeating is that
    `pg_control_checkpoint().checkpoint_time` is **not** the recovery point -- it
    is when the end-of-recovery checkpoint was written, measured at fourteen
    seconds late, and it is the trap this function exists to walk past.
    """
    reads = {
        "requested_target": "SELECT current_setting('recovery_target_time', true)",
        "achieved_recovery_point": "SELECT pg_last_xact_replay_timestamp()",
        "achieved_lsn": "SELECT pg_last_wal_replay_lsn()",
        "timeline_id": "SELECT timeline_id FROM pg_control_checkpoint()",
        "schema_version": ("SELECT coalesce(max(version), '') FROM app_private.schema_migrations"),
        "schema_migration_count": "SELECT count(*) FROM app_private.schema_migrations",
    }
    observed: dict[str, Any] = {}
    for name, sql in reads.items():
        code, answer = query(plan, sql)
        observed[name] = None if code != 0 or answer == "" else answer
    for name in ("timeline_id", "schema_migration_count"):
        if observed[name] is not None:
            observed[name] = int(observed[name])
    return observed


def released_versions() -> list[str]:
    """The versions `migrations/released.lock.json` says this release carries.

    Read from the lock rather than counted from `migrations/templates/`: the lock
    is what `bin/migrate.sh freeze-lock` froze and what the renderer installs, so
    a template added and not frozen is a template this release does not have.
    """
    lock = json.loads((REPO_ROOT / "migrations" / "released.lock.json").read_text("utf-8"))
    return [str(entry["version"]) for entry in lock["migrations"]]


def smoke_checks(
    plan: restore_drill.DrillPlan, observed: dict[str, Any], owner_id: str | None
) -> dict[str, Any]:
    """What the drill proves about the restored instance (`REC-SMOKE-001`).

    Run 8 wrote three; Run 9 adds the three the requirement actually names -- the
    schema matches the release's set, an RLS-protected read returns one owner's
    rows and only those, and a write RPC succeeds.

    **Every check carries `applicable`**, and the two that need an owner id are
    `applicable: false` when none was supplied. A check that quietly reported
    `passed: true` because it had nothing to do is the shape this repository
    keeps producing, and `REC-SMOKE-001` asserts `applicable` as well as
    `passed` so a drill run without `--smoke-owner-id` cannot satisfy it.
    """
    code, answer = query(plan, "SELECT 1")
    released = released_versions()
    present = [
        line
        for line in query(
            plan, "SELECT version FROM app_private.schema_migrations ORDER BY version"
        )[1].splitlines()
        if line.strip()
    ]

    checks: dict[str, Any] = {
        "answers_a_query": {
            "applicable": True,
            "passed": code == 0 and answer == "1",
            "detail": f"SELECT 1 -> {answer!r} (exit {code})",
        },
        "left_recovery": {
            "applicable": True,
            "passed": query(plan, "SELECT pg_is_in_recovery()")[1] == "f",
            "detail": "pg_is_in_recovery() is false",
        },
        "carries_a_schema_version": {
            "applicable": True,
            "passed": bool(observed.get("schema_version"))
            and bool(observed.get("schema_migration_count")),
            "detail": (
                f"app_private.schema_migrations holds "
                f"{observed.get('schema_migration_count')} rows, newest "
                f"{observed.get('schema_version')!r}"
            ),
        },
        # **Set equality, not a count.** A restored cluster with the right NUMBER
        # of migrations and a different set is a cluster restored from another
        # release, and counting would report it healthy.
        "schema_matches_the_release": {
            "applicable": True,
            "passed": present == released,
            "detail": (
                f"restored {len(present)} versions, the release declares {len(released)}"
                + (
                    ""
                    if present == released
                    else f"; only in the restore {sorted(set(present) - set(released))}, "
                    f"only in the release {sorted(set(released) - set(present))}"
                )
            ),
        },
    }

    if not owner_id:
        for name in ("rls_read_is_owner_scoped", "write_rpc_succeeds"):
            checks[name] = {
                "applicable": False,
                "passed": None,
                "detail": (
                    "no --smoke-owner-id was supplied, so this check did not run. It is "
                    "recorded as not applicable rather than as passing: REC-SMOKE-001 "
                    "reads `applicable` too."
                ),
            }
        return checks

    runtime_role = (plan.roles or {}).get("app_runtime")
    if not runtime_role:
        checks["rls_read_is_owner_scoped"] = {
            "applicable": False,
            "passed": None,
            "detail": "the deployed document names no app_runtime role",
        }
        checks["write_rpc_succeeds"] = dict(checks["rls_read_is_owner_scoped"])
        return checks

    # **As `app_runtime`, not as the superuser.** ADR 0065/0066: a proof that
    # reaches the right end state by a route the product does not take proves the
    # end state is reachable. FORCE RLS still exempts a superuser, so the same
    # SELECT run as `postgres` returns every row and passes for the wrong reason.
    def as_owner(claim: str, statement: str) -> tuple[int, str]:
        return query(
            plan,
            f"SET LOCAL ROLE {runtime_role}; SET LOCAL app.user_id = '{claim}'; {statement}",
        )

    mine_code, mine = as_owner(owner_id, "SELECT count(*) FROM api.notes;")
    # A second, absent identity. The check is not "the owner sees rows" -- that
    # passes against a table with RLS disabled -- it is "and nobody else sees
    # them", which is the half that fails when a policy is dropped.
    other_code, other = as_owner(SMOKE_FOREIGN_OWNER, "SELECT count(*) FROM api.notes;")

    checks["rls_read_is_owner_scoped"] = {
        "applicable": True,
        "passed": (
            mine_code == 0 and other_code == 0 and mine.isdigit() and int(mine) > 0 and other == "0"
        ),
        "detail": (
            f"as {runtime_role}: the drill owner sees {mine!r} note(s) (exit {mine_code}), "
            f"an unrelated identity sees {other!r} (exit {other_code})"
        ),
    }

    write_code, written = as_owner(owner_id, "SELECT (api.create_note('restore drill', ''))::text;")
    checks["write_rpc_succeeds"] = {
        "applicable": True,
        "passed": write_code == 0 and bool(written.strip()),
        "detail": (
            f"api.create_note as {runtime_role} exited {write_code} and returned "
            f"{'a row' if written.strip() else 'nothing'}"
        ),
    }
    return checks


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="restore-test",
        description=(
            "Restore this project's backup to a point in time, into a disposable "
            "instance, and verify it. Nothing here can name the live volume."
        ),
    )
    parser.add_argument(
        "--project-dir",
        required=True,
        type=Path,
        help="the rendered project directory holding outputs.json",
    )
    parser.add_argument(
        "--target-time",
        required=True,
        help="the recovery target, as a timestamp PostgreSQL parses (ISO 8601 with an offset)",
    )
    parser.add_argument(
        "--smoke-owner-id",
        default=None,
        help=(
            "an owner id present in the restored data. Without it the RLS read and "
            "the write RPC are recorded as not applicable rather than as passing"
        ),
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=REPO_ROOT / "evidence",
        help="where the drill's evidence document is written",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,  # bin/restore-test.sh's trap reads this; not an operator flag.
    )
    return parser


def drill(arguments: argparse.Namespace) -> int:
    document = load_document(arguments.project_dir)
    contract = load_secret_contract(REPO_ROOT / "secrets.required.yaml")

    live = database_container(document)
    inspect = inspect_container(live)

    drill_id = new_drill_id()
    try:
        plan = restore_drill.build_plan(
            document=document,
            inspect=inspect,
            drill_id=drill_id,
            contract=contract,
        )
    except restore_drill.DrillError as error:
        raise OperatorError(EXIT_STATE, str(error)) from error

    restore_argv = restore_drill.restore_arguments(plan, arguments.target_time)

    # Before anything is created, and it raises rather than warns.
    try:
        restore_drill.assert_disposable(plan, restore_argv)
    except restore_drill.DisposabilityError as error:
        raise OperatorError(EXIT_UNSAFE, str(error)) from error

    print(f"restore-test: drill {drill_id} for {plan.project_key}")
    print(f"  live volume  {plan.live_volume}  (never mounted by this drill)")
    print(f"  drill volume {plan.names.volume}")
    print(f"  image        {plan.image}")

    refuse_a_leftover(plan)
    if arguments.state_file:
        write_state_file(arguments.state_file, plan)

    summary, backups = read_repository(live, plan.stanza)

    rto_started = time.monotonic()
    problems: list[str] = []
    try:
        result, restore_seconds = run_restore(plan, restore_argv)
        if result.returncode != 0:
            raise OperatorError(EXIT_REFUSED, _restore_failure(result))

        label = restore_drill.parse_backup_set(result.stdout + result.stderr)
        backup_type = restore_drill.backup_set_type(backups, label)
        reported = _REPORTED_MS.search(result.stdout + result.stderr)

        start_instance(plan)
        recovery_seconds = wait_for_promotion(plan)
        rto_seconds = time.monotonic() - rto_started

        observed = observe_restored_instance(plan)
        smoke = smoke_checks(plan, observed, arguments.smoke_owner_id)

        evidence = restore_drill.evidence_document(
            plan=plan,
            drill_id=drill_id,
            requested_target=arguments.target_time,
            observed=observed,
            repository=summary,
            backup_set={"label": label, "type": backup_type},
            timings={
                "restore_seconds": restore_seconds,
                "recovery_seconds": recovery_seconds,
                "rto_seconds": rto_seconds,
                "pgbackrest_reported_ms": int(reported.group("ms")) if reported else None,
            },
            smoke=smoke,
            # `source_commit`, not a `release` block: NO document kind has one
            # (D600). This read produced `null` in every drill document ever
            # written, including the first real one, and a null in an evidence
            # record is worse than an absent field because it looks measured.
            # `source_commit` is what `build_deployed_document` calls "the commit
            # that deployed it", and it is the same field the evidence merge
            # compares to decide both halves describe one release -- so this
            # makes the drill document join to the session document.
            release=document.get("source_commit"),
        )
    except restore_drill.DrillError as error:
        raise OperatorError(EXIT_STATE, str(error)) from error
    finally:
        problems = teardown(plan)
        if arguments.state_file:
            Path(arguments.state_file).unlink(missing_ok=True)

    path = _write_evidence(arguments.evidence_dir, plan, drill_id, evidence)
    print(f"restore-test: evidence written to {path}")

    if problems:
        # The drill's own answer is separate from the teardown's. A verified
        # restore that could not clean up is still a verified restore, and the
        # leftover is what needs saying loudest.
        for problem in problems:
            print(f"restore-test: TEARDOWN FAILED -- {problem}", file=sys.stderr)
        raise OperatorError(
            EXIT_STATE, "the drill finished and its own resources could not be removed."
        )

    verdict = evidence["verdict"]
    if not verdict["passed"]:
        for reason in verdict["reasons"]:
            print(f"restore-test: {reason}", file=sys.stderr)
        return EXIT_REFUSED

    print(
        f"restore-test: verified. Requested {evidence['recovery']['requested_target']}, "
        f"achieved {evidence['recovery']['achieved_recovery_point']} at LSN "
        f"{evidence['recovery']['achieved_lsn']}, RTO "
        f"{evidence['timing']['rto_seconds']}s."
    )
    return 0


def _restore_failure(result: subprocess.CompletedProcess) -> str:
    """pgBackRest's own words, plus what its two named exit codes mean."""
    detail = (result.stderr or result.stdout or "").strip()[:600]
    if result.returncode == restore_drill.RESTORE_EXIT_NO_BACKUP_SET:
        return (
            f"no backup set precedes the requested target (pgBackRest exit "
            f"{result.returncode}). Nothing was written. Choose a target later than "
            f"the newest backup's stop time.\n{detail}"
        )
    if result.returncode == restore_drill.RESTORE_EXIT_POPULATED_DIRECTORY:
        return (
            f"pgBackRest refused a populated data directory (exit {result.returncode}). "
            "The drill volume was not empty, which this command's own pre-flight "
            f"should have caught.\n{detail}"
        )
    return f"the restore failed (pgBackRest exit {result.returncode}).\n{detail}"


def _write_evidence(
    directory: Path, plan: restore_drill.DrillPlan, drill_id: str, evidence: dict[str, Any]
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"restore-drill-{plan.project_key}-{drill_id}.json"
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        require_root()
        return int(drill(arguments))
    except OperatorError as error:
        print(f"restore-test: {error}", file=sys.stderr)
        return error.code
    except subprocess.TimeoutExpired as error:
        print(
            f"restore-test: docker did not answer within {error.timeout}s. Drill "
            "resources may still exist; bin/restore-test.sh's trap removes what its "
            "state file names.",
            file=sys.stderr,
        )
        return EXIT_STATE


if __name__ == "__main__":
    raise SystemExit(main())
