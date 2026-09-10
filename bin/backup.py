#!/usr/bin/env python3
"""The backup operator surface: five verbs, and none of them names a credential.

**Every verb runs pgBackRest inside the database container** (ADR 0144). Not a
preference: `archive_command` is executed by the postmaster, so the binary lives
in the postgres image, the repository credential and the cipher pass are
materialized into that container's generation owned by uid 999, and the host has
no pgBackRest at all. A command that reached R2 from here would need the
credential here, and per-consumer materialization is what makes "the storage
service cannot reach the backup repository" a filesystem property rather than a
rule somebody keeps (ADR 0145).

**No verb takes a bucket, a prefix, a stanza or a retention count.** All four are
in the deployed document and in the rendered `pgbackrest.conf`, decided once
(ADR 0002). `retain_full` in particular reaches pgBackRest through the config and
through nothing else -- measured in rig 6, `expire` applies it with nothing on
the command line. A `--retention` flag here would be one value stated twice,
where the second statement wins and the first is the one people read (D495, D463).

**`info` never trusts an exit code.** Measured: `pgbackrest info` exits 0 for a
stanza that does not exist, for a stanza with no backups, and for a healthy one.
The state is in `status.code`, and `agentic_postgres.backup_report` is the one
place that reads it.

The verbs:

  stanza-create  Initialise the repository for this project's stanza. Idempotent
                 -- measured, twice in a row exits 0 -- which is why the deploy's
                 step 6c runs it unconditionally rather than probing first.
  check          Prove archiving and the repository BOTH work: forces a WAL
                 switch and confirms the segment arrived. This is the only thing
                 in this system that tests the archiver end to end, and a
                 failure here is a deploy failure rather than a warning.
  backup         Take one, `--type full` or `--type incr`. Retention is applied
                 by pgBackRest from the config afterwards.
  info           What the repository reports, as pgBackRest's own text or, with
                 `--json`, the summary the deployed document is built from.
  expire         Apply the retention policy now. The timers do not need it --
                 `backup` expires as it goes -- and it exists for an operator
                 reclaiming space after lowering `retain_full`.

Exit codes (runbook section 2 convention):
  0  the verb completed
  2  invalid operator input
  3  missing local prerequisite, or not root
  5  the deployment or the repository refused the operation
  6  the verb ran and its answer is "no" -- the repository is not healthy
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import (  # noqa: E402
    backup_report,
    backup_schedule,
    config,
    deployed_output,
    fleet,
    naming,
    runtime_override,
)

EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_STATE = 5
EXIT_REFUSED = 6

#: The database container is selected by `runtime_override`, not from here.
#:
#: This module declared `apg.project.key` and selected the cluster with it until
#: Session 10 Run 11 measured that **the postgres service does not carry that
#: label** -- it is on six edge-facing services and on none of `postgres`,
#: `pgbouncer` or `dbmate`. The selector returned 0 containers on a healthy
#: cluster, and nothing noticed because step 6c had never run (D587).

#: The uid pgBackRest must run as inside the database container.
#:
#: The same 999 the postmaster runs as, and the same 999 the three backup
#: secrets are materialized to (D515). Running as root inside the container
#: would read the credential files fine and then write repository state owned by
#: root, which the postmaster could not read afterwards -- a failure that
#: appears one archive-push later, somewhere else.
POSTGRES_UID = "999"

#: How long a backup may take before this command stops waiting.
#:
#: An hour, and still a bound rather than a measurement -- but no longer an
#: unmeasured one. A first full backup of a 31.7 MB database against R2 took
#: **15 minutes 36 seconds** on a bring-up in 2026-09 (4.1 MB in the
#: repository, ~87% compression), so an hour has headroom of roughly four
#: times at that size and says nothing about a larger one. `process-max` is 1
#: by decision (D593), so this scales with data rather than with the host.
BACKUP_TIMEOUT_SECONDS = 3600

#: How long a *quick* verb -- `info`, `check`, a mirror count -- may wait.
#:
#: Was 300, and 300 was wrong in the way a chosen number usually is: smaller
#: than the operation standing next to it (D1051). `backup --type full` returns
#: while pgBackRest is still running `expire`, so the very next verb in the
#: documented sequence met a repository that was not quiescent and died here
#: after five minutes -- immediately after a backup that had worked perfectly,
#: with nothing saying so.
#:
#: `info` is not itself slow: measured at 1 second inside the container and 2
#: through this wrapper. The stall was contention, so what this bound has to
#: cover is waiting for the repository, not the read.
QUICK_TIMEOUT_SECONDS = 900

#: How long a mirror copy may take. The one measured figure is Run 2's rig: a
#: 31 MB repository copied from R2 to Backblaze in under a minute, and the
#: nightly delta is smaller. An hour is the same bound the backup takes, and
#: the unit says the same.
MIRROR_TIMEOUT_SECONDS = 3600

#: Where the mirror verb finds the installed rendered output and writes its
#: copy record. `deployed_output` owns both roots; they are named here so a
#: proof can point the verb at a directory it controls.
RENDERED_ROOT = deployed_output.RENDERED_ROOT
STATE_ROOT = deployed_output.PROJECT_STATE_ROOT


class OperatorError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def require_root() -> None:
    if os.geteuid() != 0:
        raise OperatorError(
            EXIT_PREREQUISITE,
            "must run as root: the deployed document is root-owned and every verb here "
            "reaches the database container over the local socket.",
        )


def load_document(path: Path) -> dict:
    if not path.is_file():
        raise OperatorError(EXIT_INPUT, f"deployed document not found: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise OperatorError(EXIT_STATE, f"{path} is not readable as JSON: {error}") from error
    if "database" not in document:
        raise OperatorError(EXIT_INPUT, f"{path} is not a deployed document (no 'database')")
    return document


def project_key(document: dict) -> str:
    key = (document.get("project") or {}).get("key")
    if not key:
        raise OperatorError(EXIT_STATE, "the deployed document names no project key")
    return str(key)


def stanza_name(document: dict) -> str:
    """The stanza, read from the document and never re-derived (ADR 0002).

    `naming` derives it, `outputs.json` publishes it, and the rendered
    `pgbackrest.conf` and the `archive_command` both carry it. A fourth
    derivation here is the copy that disagrees, and the way it would disagree is
    a command operating on a stanza the archiver is not writing to -- which
    reports success at every step.
    """
    backup = document.get("backup") or {}
    stanza = backup.get("stanza")
    if not stanza:
        raise OperatorError(
            EXIT_INPUT,
            "this project's deployed document declares no backup stanza, which means "
            "backups are disabled for it. There is nothing here to operate.",
        )
    if not backup.get("enabled"):
        raise OperatorError(
            EXIT_INPUT,
            f"backups are disabled for {project_key(document)} in its manifest. Enable "
            "backup.enabled and redeploy; this command does not configure a project.",
        )
    return str(stanza)


def database_container(document: dict) -> str:
    """The running database container, found by label rather than predicted.

    `naming` predicts Compose's container name and the model deliberately does
    not pin it with `container_name:` (D55), so building the name here would
    depend on a convention this repository has chosen not to depend on.
    """
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
    arguments = ["docker", "ps"]
    for value in filters:
        arguments += ["--filter", value]
    arguments += ["--format", "{{.Names}}"]

    result = subprocess.run(arguments, capture_output=True, text=True, check=False, timeout=60)
    names = [line for line in result.stdout.split() if line]
    if len(names) != 1:
        # A selector that matches nothing and a container that is genuinely down
        # look identical from here. D293 is the record of reporting the second
        # while the first was true, so both are named.
        raise OperatorError(
            EXIT_STATE,
            f"expected exactly one running database container matching {filters}, found "
            f"{names or 'none'}. If the cluster is up, the selector is wrong; if it is "
            "down, no backup verb can run -- pgBackRest lives in that container.",
        )
    return names[0]


def pgbackrest(
    container: str,
    stanza: str,
    *arguments: str,
    timeout: int = QUICK_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess:
    """One pgBackRest command inside the database container, as uid 999.

    **Nothing secret is in the argument vector**, and nothing needs to be: the
    repository credential and the cipher pass are read by pgBackRest from files
    the runtime override mounts, and the config supplies everything else. argv is
    visible in `ps`, in `/proc/<pid>/cmdline` and in the daemon's own record of
    the exec, which is why that is a property worth stating rather than a
    coincidence (D105).
    """
    command = [
        "docker",
        "exec",
        "-u",
        POSTGRES_UID,
        container,
        "pgbackrest",
        f"--stanza={stanza}",
        *arguments,
    ]
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)


def _relay(result: subprocess.CompletedProcess) -> None:
    """pgBackRest's own words, on the stream it chose.

    Relayed rather than summarised: its messages carry an error number and a
    HINT, and Run 5 measured how much the difference matters -- `[027]: no
    database found` with `check indexed pg-path/pg-host configurations` is what
    a connection-limit refusal looks like, and a command that replaced that with
    "the backup failed" would delete the only clue (D543).
    """
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)


def read_archiver(container: str, document: dict) -> dict | None:
    """`pg_stat_archiver`, over the container's own socket.

    Through `psql` as the superuser rather than as `backup_user`: this is the
    operator's command, it already runs as root on the host and reaches the
    container over the local socket, and giving the backup identity a sixth
    privilege so that a diagnostic could use it would be a grant nothing
    measured needed (ADR 0148's necessity matrix).

    The SQL is a module constant in `backup_report` -- one place naming the
    columns, so this command and the deploy's observer cannot read the archiver
    two different ways.

    Returns None rather than raising: a repository report is still worth
    printing when the cluster will not answer a second question.
    """
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "psql",
            "-U",
            "postgres",
            "-d",
            (document.get("database") or {}).get("name", "postgres"),
            "-X",
            "-qtA",
            "-F",
            backup_report.ARCHIVER_SEPARATOR,
            "-c",
            backup_report.ARCHIVER_QUERY,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=QUICK_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return None
    return backup_report.parse_archiver(result.stdout)


def read_repository(container: str, stanza: str) -> dict:
    """The repository's own report, summarised. Never reads the exit code.

    `pgbackrest info` exits 0 in every state including a stanza that does not
    exist (rig 6), so the only thing checked here is that the process produced
    parseable JSON. What that JSON MEANS is `backup_report`'s, in one place, so
    this command and the deploy's observer cannot disagree.
    """
    result = pgbackrest(container, stanza, "info", "--output=json")
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
        return backup_report.summarise(document, stanza)
    except ValueError as error:
        raise OperatorError(EXIT_STATE, str(error)) from error


# ---------------------------------------------------------------------------
# The verbs
# ---------------------------------------------------------------------------


def verb_stanza_create(arguments: argparse.Namespace) -> int:
    document = load_document(arguments.outputs)
    stanza = stanza_name(document)
    container = database_container(document)

    result = pgbackrest(container, stanza, "stanza-create")
    _relay(result)
    if result.returncode != 0:
        raise OperatorError(
            EXIT_STATE,
            f"stanza-create failed (exit {result.returncode}). The repository credential, "
            "the endpoint and the cipher pass all reach pgBackRest from the container's "
            "mounted generation; none of them is on this command line.",
        )
    print(f"backup: stanza {stanza} exists")
    return 0


def verb_check(arguments: argparse.Namespace) -> int:
    document = load_document(arguments.outputs)
    stanza = stanza_name(document)
    container = database_container(document)

    result = pgbackrest(container, stanza, "check")
    _relay(result)
    if result.returncode != 0:
        # EXIT_REFUSED rather than EXIT_STATE: the command ran and its answer is
        # "no". The deploy maps this to a failed convergence, and an operator
        # running it by hand gets a code that says the repository is unhealthy
        # rather than that the tooling broke.
        raise OperatorError(
            EXIT_REFUSED,
            f"check failed (exit {result.returncode}). This is the one command that "
            "tests archiving end to end -- it forces a WAL switch and confirms the "
            "segment reached the repository -- so a failure here means WAL is not "
            "arriving, whatever the cluster's own health says.",
        )
    print(f"backup: archiving and repository both reachable for {stanza}")
    return 0


def verb_backup(arguments: argparse.Namespace) -> int:
    document = load_document(arguments.outputs)
    stanza = stanza_name(document)
    container = database_container(document)

    result = pgbackrest(
        container,
        stanza,
        f"--type={arguments.type}",
        "backup",
        timeout=BACKUP_TIMEOUT_SECONDS,
    )
    _relay(result)
    if result.returncode != 0:
        raise OperatorError(EXIT_STATE, f"backup failed (exit {result.returncode})")

    summary = read_repository(container, stanza)
    print(
        f"backup: {arguments.type} complete; repository holds "
        f"{summary['backup_count']} backup(s), newest full "
        f"{summary['last_full_backup_label'] or 'none'}"
    )
    # D1051. pgBackRest runs `expire` as part of a backup and this command
    # returns before it finishes, so the repository stays busy afterwards and
    # the next verb -- `info`, which any sane runbook calls for here to confirm
    # the backup exists -- can block on it. Nothing was broken when that
    # happened on a first bring-up, and nothing said so either.
    print(
        "  the repository stays busy while pgBackRest finishes expiring; "
        "`info` may block for a few minutes yet"
    )
    return 0


def verb_info(arguments: argparse.Namespace) -> int:
    document = load_document(arguments.outputs)
    stanza = stanza_name(document)
    container = database_container(document)

    # **Both sources, because they fail independently** (ADR 0150). A repository
    # full of good backups can sit behind an archiver that stopped an hour ago,
    # and `pgbackrest info` reports `ok` for exactly that cluster. The
    # repository says what was saved; `pg_stat_archiver` says whether anything
    # still is.
    summary = read_repository(container, stanza)
    archiver = read_archiver(container, document)
    state = backup_report.backup_state(summary, archiver)
    status = state["status"]

    if arguments.json:
        # The published block, not the raw report: this is exactly what the
        # deploy writes into `outputs.json`, so an operator can see the document
        # before it exists rather than diffing it afterwards.
        print(json.dumps(state, indent=2, sort_keys=True))
        return 0 if status != backup_report.STATUS_FAILING else EXIT_REFUSED

    result = pgbackrest(container, stanza, "info")
    _relay(result)
    print(f"backup: {stanza} is {status} (pgbackrest status.code {summary['status_code']})")
    if archiver is None:
        print("  archiver: not readable, so the WAL counters are unknown")
    else:
        print(
            f"  archiver: {archiver['archived_count']} archived, "
            f"{archiver['failed_count']} failed"
            + (
                ""
                if not backup_report.archiving_is_failing(archiver)
                else f" -- THE NEWEST ATTEMPT FAILED, at {archiver['last_failed_wal']}"
            )
        )
        # The counters are cumulative and never reset, so a non-zero
        # `failed_count` on a healthy cluster is normal and says so: every
        # project accrues failures in the window between the container starting
        # with archive_mode=on and step 6c creating the stanza (D553).
        if archiver["failed_count"] and not backup_report.archiving_is_failing(archiver):
            print(
                "  (a non-zero failed count on a healthy archiver is expected: the counter "
                "is cumulative and every project fails to archive until its stanza exists)"
            )
    return 0 if status != backup_report.STATUS_FAILING else EXIT_REFUSED


def verb_expire(arguments: argparse.Namespace) -> int:
    document = load_document(arguments.outputs)
    stanza = stanza_name(document)
    container = database_container(document)

    # No retention on the command line, and that is the decision rather than an
    # omission: `repo1-retention-full` is in the rendered config, resolved from
    # the manifest's `retain_full` (Run 4), and measured to apply from there.
    result = pgbackrest(container, stanza, "expire")
    _relay(result)
    if result.returncode != 0:
        raise OperatorError(EXIT_STATE, f"expire failed (exit {result.returncode})")

    summary = read_repository(container, stanza)
    print(f"backup: retention applied; repository holds {summary['backup_count']} backup(s)")
    return 0


# ---------------------------------------------------------------------------
# The schedule (Session 17 Run 5, FLEET-BACKUP-001)
# ---------------------------------------------------------------------------

#: `systemctl` answers in well under this; the bound is for a hung manager.
SYSTEMCTL_TIMEOUT_SECONDS = 60


def systemctl(*arguments: str) -> subprocess.CompletedProcess:
    """One `systemctl` call, bounded, stdin closed (D673)."""
    return subprocess.run(
        ["systemctl", *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=SYSTEMCTL_TIMEOUT_SECONDS,
        stdin=subprocess.DEVNULL,
    )


def timer_states(key: str, kinds: tuple[str, ...]) -> dict[str, str]:
    """Each timer's unit-file state, in `fleet`'s measured vocabulary (D962).
    ``kinds`` is `fleet.timer_kinds`' answer for the project: the mirror's
    timer is read only for a project that has a mirror (ADR 0188)."""
    states: dict[str, str] = {}
    for kind, unit in backup_schedule.units(key, kinds).items():
        try:
            result = systemctl("is-enabled", unit)
        except (OSError, subprocess.TimeoutExpired):
            states[kind] = fleet.UNKNOWN
            continue
        states[kind] = fleet.unit_state(result.returncode, result.stdout)
    return states


def verb_schedule(arguments: argparse.Namespace) -> int:
    """`status`, `enable`, `disable` -- the two backup timers of one project.

    `status` answers 0 when both timers are enabled and 6 otherwise: the verb
    ran and its answer is "no", which is the convention `check` and `info`
    follow. `enable` refuses while a unit file is absent (naming the
    provisioning command) or while the repository holds no full backup (naming
    the backup command), and re-reads the states afterwards rather than
    trusting `systemctl`'s exit code. `disable` is unconditional.
    """
    document = load_document(arguments.outputs)
    key = project_key(document)
    kinds = fleet.timer_kinds(document)
    states = timer_states(key, kinds)

    if arguments.action == "status":
        if arguments.json:
            print(backup_schedule.render_json(key, states))
        else:
            print(backup_schedule.render_status(key, states))
        return 0 if fleet.schedule(states) == fleet.SCHEDULED else EXIT_REFUSED

    if arguments.action == "disable":
        for kind, unit in backup_schedule.units(key, kinds).items():
            if states[kind] == fleet.ABSENT:
                print(f"backup: {unit} is not installed; nothing to disable")
                continue
            result = systemctl("disable", "--now", unit)
            if result.returncode != 0:
                raise OperatorError(
                    EXIT_STATE, f"could not disable {unit} (exit {result.returncode})"
                )
            print(f"backup: {unit} disabled")
        return 0

    # enable: the two refusals first, and the repository is read only after
    # the unit files are known to exist -- an absent unit is the cheaper answer
    # and names the repair for the other state anyway.
    absent = backup_schedule.enable_refusal(
        states, repository_status=backup_report.STATUS_READY, last_full_backup_at="pending"
    )
    if absent is not None:
        raise OperatorError(EXIT_PREREQUISITE, absent)
    stanza = stanza_name(document)
    container = database_container(document)
    summary = read_repository(container, stanza)
    state = backup_report.backup_state(summary, read_archiver(container, document))
    why = backup_schedule.enable_refusal(
        states,
        repository_status=state["status"],
        last_full_backup_at=state.get("last_full_backup_at"),
    )
    if why is not None:
        raise OperatorError(EXIT_REFUSED, why)

    for kind, unit in backup_schedule.units(key, kinds).items():
        if states[kind] == fleet.ENABLED:
            print(f"backup: {unit} already enabled")
            continue
        result = systemctl("enable", "--now", unit)
        if result.returncode != 0:
            raise OperatorError(EXIT_STATE, f"could not enable {unit} (exit {result.returncode})")
        print(f"backup: {unit} enabled")

    # Re-read rather than trust: a unit `systemctl enable` accepted and did not
    # activate is the state this verb exists to make visible.
    after = timer_states(key, kinds)
    print(backup_schedule.render_status(key, after))
    if fleet.schedule(after) != fleet.SCHEDULED:
        raise OperatorError(
            EXIT_STATE, "the timers were enabled and systemd does not report both enabled"
        )
    # Measured on the host at the first enable (D973): Persistent=true catches
    # up a slot missed while the timer was already installed and the host was
    # down, judged against the stamp file the timer writes on its first
    # trigger. A freshly enabled timer has no stamp, so nothing is owed and the
    # first runs are the next calendar slots. The earlier text here promised an
    # immediate run; it was stated, not measured, and it was wrong.
    print(
        "backup: Persistent=true catches up a slot missed while the host was down; "
        "a timer enabled for the first time owes nothing, so the first runs are the "
        "next calendar slots (systemctl list-timers 'agentic-postgres-backup-*')."
    )
    return 0


# ---------------------------------------------------------------------------
# The mirror (ADR 0188)
# ---------------------------------------------------------------------------


def compose_mirror(rendered: Path, action: str, *, timeout: int) -> subprocess.CompletedProcess:
    """One run of the `backup-mirror` container through `bin/compose.sh`.

    Through the wrapper and never `docker compose` directly, so the runtime
    overrides -- the router labels, the secret grants, the mount digests --
    are the ones the deploy installed, and the `run` refusals (no
    `--entrypoint`, no `-e`) apply here as they do everywhere. The container is
    the only thing that holds either credential; this process holds neither.
    """
    command = [
        str(REPO_ROOT / "bin" / "compose.sh"),
        str(rendered),
        "--runtime",
        "--profile",
        "mirror",
        "run",
        "--rm",
        "backup-mirror",
        action,
    ]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )


def write_mirror_record(path: Path, record: dict) -> None:
    """Root-owned, 0600, replaced atomically: a half-written record is a
    record the doctor cannot parse, which it reports as unknown, not as a copy."""
    staging = path.with_name(f".{path.name}.staging")
    descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(staging, path)


def verb_mirror(arguments: argparse.Namespace) -> int:
    """Copy the repository to the second provider, and record the copy.

    What the timer runs. The copy is `mc mirror --overwrite --remove` inside
    the `backup-mirror` container (measured, D1001: complete on a pass that
    exits 0; a pass that exits non-zero has left objects behind and the next
    pass completes it). The record is written ONLY after a pass that exits 0
    and a listing of the mirror bucket that parses, so a record always
    describes a complete copy and the count that was read after it -- never a
    count somebody assumed. A failed pass is this verb's non-zero exit, the
    unit's failure, and the doctor's stale-copy warning; it is not a status
    written anywhere.
    """
    document = load_document(arguments.outputs)
    key = project_key(document)
    stanza_name(document)  # refuses a project whose backups are disabled
    if not config.backup_mirror_enabled(document):
        raise OperatorError(
            EXIT_INPUT,
            f"{key} declares no backup mirror. Enable backup.mirror in the manifest and "
            "redeploy; this command does not configure a project.",
        )
    rendered = deployed_output.rendered_path(key, root=RENDERED_ROOT)
    if not (rendered / "compose.env").is_file():
        raise OperatorError(
            EXIT_STATE,
            f"no rendered output for {key} at {rendered}; the project was never deployed "
            "on this host.",
        )

    copy = compose_mirror(rendered, "copy", timeout=MIRROR_TIMEOUT_SECONDS)
    _relay(copy)
    if copy.returncode != 0:
        raise OperatorError(
            EXIT_STATE,
            f"the mirror copy exited {copy.returncode}; the copy record was not written and "
            "the next pass completes what this one left behind (D1001).",
        )

    listing = compose_mirror(rendered, "count", timeout=QUICK_TIMEOUT_SECONDS)
    objects = backup_report.count_listing(listing.stdout) if listing.returncode == 0 else None
    if objects is None:
        raise OperatorError(
            EXIT_STATE,
            "the copy completed and the mirror bucket could not be listed afterwards "
            f"(exit {listing.returncode}); the copy record was not written.",
        )

    record = backup_report.mirror_record(objects=objects, copied_at=datetime.now(UTC))
    write_mirror_record(deployed_output.mirror_record_path(key, root=STATE_ROOT), record)
    print(f"backup: mirror of {key} complete: {objects} object(s) at {record['last_copied_at']}")
    return 0


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backup",
        description=(
            "Operate a project's backup repository. No verb names a bucket, a stanza, "
            "a retention count or a credential -- all four come from the deployed "
            "document and the rendered config."
        ),
    )
    parser.add_argument(
        "--outputs",
        required=True,
        type=Path,
        help="the project's deployed outputs.json",
    )
    verbs = parser.add_subparsers(dest="verb", required=True)

    create = verbs.add_parser("stanza-create", help="initialise the repository (idempotent)")
    create.set_defaults(handler=verb_stanza_create)

    check = verbs.add_parser("check", help="prove archiving and the repository both work")
    check.set_defaults(handler=verb_check)

    take = verbs.add_parser("backup", help="take one backup")
    take.add_argument(
        "--type",
        choices=("full", "incr"),
        required=True,
        help="full starts a new chain; incr builds on the newest backup",
    )
    take.set_defaults(handler=verb_backup)

    show = verbs.add_parser("info", help="what the repository reports")
    show.add_argument(
        "--json",
        action="store_true",
        help="print the summary the deployed document is built from",
    )
    show.set_defaults(handler=verb_info)

    expire = verbs.add_parser("expire", help="apply the retention policy from the config")
    expire.set_defaults(handler=verb_expire)

    # Sub-verbs rather than a positional: the parser guard in
    # test_backup_repository_report reads every `add_argument` as a value this
    # command is being TOLD, and an action is not one.
    schedule = verbs.add_parser("schedule", help="the two backup timers: status, enable, disable")
    actions = schedule.add_subparsers(dest="action", required=True)
    status = actions.add_parser("status", help="both timers' unit-file state; 0 when both enabled")
    status.add_argument("--json", action="store_true", help="status as a document")
    status.set_defaults(handler=verb_schedule)
    enable = actions.add_parser("enable", help="enable both timers, after two refusals")
    enable.set_defaults(handler=verb_schedule, json=False)
    disable = actions.add_parser("disable", help="disable both timers, unconditionally")
    disable.set_defaults(handler=verb_schedule, json=False)

    mirror = verbs.add_parser(
        "mirror", help="copy the repository to the second provider and record the copy"
    )
    mirror.set_defaults(handler=verb_mirror)

    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        require_root()
        return int(arguments.handler(arguments))
    except OperatorError as error:
        print(f"backup: {error}", file=sys.stderr)
        return error.code
    except subprocess.TimeoutExpired as error:
        print(
            f"backup: pgBackRest did not answer within {error.timeout}s. That bound is "
            "chosen rather than derived -- the one measurement is a 31.7 MB database "
            "taking 15m36s for a full backup against R2, and `process-max` is 1 by "
            "decision (D593), so it scales with data and not with the host -- and "
            "work may still be running inside the container. A backup returns before "
            "pgBackRest finishes expiring, so a read that timed out here may simply "
            "have been waiting for the repository.",
            file=sys.stderr,
        )
        return EXIT_STATE


if __name__ == "__main__":
    raise SystemExit(main())
