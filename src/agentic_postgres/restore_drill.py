"""The disposable restore rehearsal: what it runs, and what it may report.

Pure logic, so that every property the drill exists to hold can be driven
without a cluster, a repository or a Docker daemon. That matters more here than
anywhere else in this repository, because the interesting cases are the ones a
correct drill never reaches -- a mount plan that names the live volume, a
`--delta` on the argument vector, a restore that exits 0 having landed nowhere.

**The two decisions this module implements are ADR 0151 and ADR 0152.**

ADR 0151, in one sentence: the drill's resources are derived with contexts of
their own, its configuration surface is *inherited from the container that runs
the archiver* rather than re-derived, and the check that the live volume cannot
appear runs on the argument vector -- in the product path, on every invocation --
because D523 says in advance that a source scan asking whether a name is
*mentioned* is satisfied by dead code (D277, D464).

ADR 0152, in one sentence: every field the evidence document carries is a
measurement with a named source, and for two of them the plausible wrong source
is more obvious than the right one and produces a well-formed value.

The measured facts this module depends on, all rig 8:

============================================  ==========================================
what                                          measured
============================================  ==========================================
restore into an empty volume                  exit 0
restore over a populated one, no ``--delta``  **exit 40** -- pgBackRest refuses
a target before the oldest backup set         **exit 75**, before anything is written
a target in the future                        restore **exits 0**; the instance never promotes
a successful restore at ``log-level-console=warn``  **zero bytes** on both streams
the same restore at ``info``                  names the backup set, on **stdout**
``pg_last_xact_replay_timestamp()`` on a restore  the achieved recovery point
the same function on a cluster that never recovered  **NULL** -- the free control
``pg_control_checkpoint().checkpoint_time``   the end-of-recovery checkpoint, 14s late
``system_identifier``                         **identical** on live and drill
``timeline_id``                               1 on live, **2** on a promoted restore
============================================  ==========================================
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agentic_postgres import config, naming, runtime_override

__all__ = [
    "FORBIDDEN_RESTORE_FLAGS",
    "PGBACKREST_ENVIRONMENT_PREFIX",
    "RESTORE_EXIT_NO_BACKUP_SET",
    "RESTORE_EXIT_POPULATED_DIRECTORY",
    "RESTORE_LOG_LEVEL",
    "DisposabilityError",
    "DrillError",
    "DrillPlan",
    "Mount",
    "archive_mode_is_off",
    "assert_disposable",
    "build_plan",
    "drill_verdict",
    "evidence_document",
    "inherited_environment",
    "inherited_mounts",
    "instance_command",
    "instant",
    "live_mount_sources",
    "parse_backup_set",
    "required_container_paths",
    "restore_arguments",
]


class DrillError(Exception):
    """The drill cannot proceed, or cannot honestly report what it did."""


class DisposabilityError(DrillError):
    """The plan could reach something that is not the drill's to touch.

    A separate type from :class:`DrillError` because it is the one failure that
    must never be caught and retried: every other error here is a drill that did
    not happen, and this one is a drill that was *about to happen to the wrong
    thing*.
    """


#: The environment namespace pgBackRest reads its own options from.
#:
#: Measured (rig 8, arm 0), with a control: `PGBACKREST_REPO1_CIPHER_PASS` in the
#: environment makes `repo-ls` exit 0 against an encrypted repository, and the
#: same command with the variable absent exits **37**, `[037]: repo-ls command
#: requires option: repo1-cipher-pass`. There is **no** `repo-cipher-pass-file`,
#: `repo-s3-key-file` or `repo-s3-key-secret-file` option -- the only `-file`
#: options pgBackRest 2.59.1 has are for TLS and SSH material -- so a credential
#: that lives in a file reaches pgBackRest through this namespace or through a
#: `config-include-path` file, and through nothing else.
#:
#: The drill carries the whole namespace forward from the database container
#: rather than naming the three variables, because **nothing populates them
#: today** (D558): the archiver's credential path does not exist yet, and when it
#: is built the drill must inherit it without being edited. A prefix over a
#: namespace a third party owns is an allowlist, not a subset check.
PGBACKREST_ENVIRONMENT_PREFIX = "PGBACKREST_"

#: What the drill passes for its own invocation, overriding the rendered config.
#:
#: `build_pgbackrest_conf` renders `log-level-console=warn`, at which a
#: **successful restore prints zero bytes on both streams** (measured). A command
#: that read the backup set out of the restore's output would therefore publish
#: an empty field on every drill that worked. This is the only place in this
#: repository where a rendered configuration value is overridden on a command
#: line, and it is done for that reason (ADR 0152).
RESTORE_LOG_LEVEL = "info"

#: Flags that must never reach `pgbackrest restore` from here (ADR 0151 §3).
#:
#: `--delta` is the flag that disarms pgBackRest's own refusal to restore over a
#: populated directory. Measured: an empty volume restores with exit 0, and the
#: same volume a second time exits **40**. That refusal is the outer guard --
#: the one that would still hold if every derivation in this module were wrong at
#: once -- and `--delta` is the single argument that removes it.
FORBIDDEN_RESTORE_FLAGS: tuple[str, ...] = ("--delta",)

#: pgBackRest's exit code for a populated `pg1-path` with no `--delta`.
RESTORE_EXIT_POPULATED_DIRECTORY = 40

#: pgBackRest's exit code for a target no backup set precedes.
#:
#: `[075]: unable to find backup set with stop time less than '<target>'`, and it
#: is raised before anything is written. Named so that the command can say what
#: happened in the operator's terms rather than relaying a number.
RESTORE_EXIT_NO_BACKUP_SET = 75

#: The line pgBackRest prints, at info level, naming the set it chose.
#:
#: Verbatim from rig 8:
#:
#:     P00   INFO: repo1: restore backup set 20260825-104447F, recovery will
#:     start at 2026-08-25 10:44:47
#:
#: Parsing a third party's log line is D374's shape, so it is bounded two ways
#: (ADR 0152 §3): a restore whose output does not match **fails the drill**
#: rather than publishing a null, and the label found here must also appear in
#: `pgbackrest info --output=json`, from which the backup's *type* is read. Two
#: independent reads that have to agree, rather than one read and a convention
#: about a trailing letter.
_BACKUP_SET_LINE = re.compile(r"restore backup set (?P<label>[0-9]{8}-[0-9]{6}[FDI])\b")


@dataclass(frozen=True)
class Mount:
    """One mount on a drill container.

    ``kind`` distinguishes a named volume from a bind, because the two are not
    interchangeable in the one place that matters: a missing *bind source* makes
    Docker create a directory (D463), and a missing *volume* makes Docker create
    an empty volume (rig 8, arm J). Both are silent, and neither is what a
    caller wanted.
    """

    source: str
    target: str
    readonly: bool
    kind: str

    def as_mount_argument(self) -> str:
        """The `--mount` value. Long syntax, deliberately.

        `-v a:b:ro` and `--mount type=...,readonly` are equivalent to Docker and
        are not equivalent to a reader: the short form's third field is a
        position, and a mount written with two fields is read-write with nothing
        marking it. The drill's mounts are asserted by a rig that reads this
        string, so the string says what it means.
        """
        parts = [f"type={self.kind}", f"source={self.source}", f"target={self.target}"]
        if self.readonly:
            parts.append("readonly")
        return ",".join(parts)


@dataclass(frozen=True)
class DrillPlan:
    """Everything the drill will run, decided before any process is started.

    Built once and asserted once, so that "what the drill would do" is a value a
    test can hold rather than a sequence a test has to observe.
    """

    image: str
    names: naming.RestoreDrillNames
    stanza: str
    database: str
    project_key: str
    live_container: str
    live_volume: str
    live_mount_sources: frozenset[str]
    inherited: tuple[Mount, ...]
    environment: dict[str, str] = field(default_factory=dict)
    network: str | None = None
    #: The project's derived role names, read from the deployed document.
    #:
    #: `REC-SMOKE-001`'s RLS read runs as `app_runtime`, not as the superuser:
    #: FORCE RLS still exempts a superuser, so the same SELECT run as `postgres`
    #: returns every row and passes for the wrong reason (ADR 0065/0066).
    roles: dict[str, str] = field(default_factory=dict)

    @property
    def data_mount(self) -> Mount:
        """The drill volume, at the path the image declares as its VOLUME.

        `POSTGRES_VOLUME_TARGET`, never PGDATA -- D53 measured that mounting at
        PGDATA works while silently leaving an anonymous volume on the parent,
        and two of the three candidates persist data, so "the row survived" does
        not distinguish them.

        The rendered `pgbackrest.conf` needs no edit for the drill because of
        this: `pg1-path` is PGDATA, PGDATA is inside this mount, and the drill
        container simply does not mount the live volume there. Which is also why
        the whole safety property lives in the mount argument and nowhere else.
        """
        return Mount(
            source=self.names.volume,
            target=runtime_override.POSTGRES_VOLUME_TARGET,
            readonly=False,
            kind="volume",
        )

    def mounts(self) -> tuple[Mount, ...]:
        """Every mount both drill containers get, data volume first."""
        return (self.data_mount, *self.inherited)


def required_container_paths(contract: dict[str, Any]) -> tuple[str, ...]:
    """The container paths the archiver reads, from the contract that grants them.

    The three backup secrets as the database container sees them, plus the
    rendered `pgbackrest.conf`. Read out of `secrets.required.yaml` rather than
    written here, because the target file names are that document's and a second
    spelling of them is the copy that is right until somebody renames one.

    An **allowlist of destinations**, not a denylist of the dangerous one. D300's
    rule: a denylist is correct only for the entries somebody thought of, and the
    entry nobody thinks of is the next mount the database service gains.

    **Not filtered by `introduced_in_session`**, and that is deliberate (D561).
    `active_secrets` answers "what would a deploy through session N materialize",
    which is a question about a *deploy*. This is a question about a *container
    that is already running*: whatever the drill is told to look for, the
    authority on whether it is there is :func:`inherited_mounts`, reading the
    container. Filtering here by `CURRENT_SESSION` -- which is 9 until the
    session that publishes -- would have made the drill look for nothing at all
    and then inherit nothing, silently.
    """
    from agentic_postgres.secrets_contract import container_secret_path

    declared = {secret["name"]: secret for secret in contract["secrets"]}
    missing = sorted(set(config.BACKUP_CREDENTIAL_NAMES) - set(declared))
    if missing:
        raise DrillError(f"the secret contract declares no {missing}")

    paths: list[str] = [runtime_override.PGBACKREST_CONF_CONTAINER_PATH]
    for name in config.BACKUP_CREDENTIAL_NAMES:
        for consumer in declared[name]["consumers"]:
            if consumer.get("service") == runtime_override.DATABASE_SERVICE:
                paths.append(container_secret_path(consumer))
    return tuple(sorted(set(paths)))


def _mounts_of(inspect: dict[str, Any]) -> list[dict[str, Any]]:
    return list(inspect.get("Mounts") or [])


def live_mount_sources(inspect: dict[str, Any]) -> frozenset[str]:
    """Every source the live container mounts, whatever kind it is.

    The set :func:`assert_disposable` checks the drill's target against. Not the
    data volume alone: a drill that wrote into any volume the live cluster holds
    is a drill that touched production, and the data volume is only the one whose
    name anybody would think to check.
    """
    return frozenset(
        str(mount.get("Name") or mount.get("Source") or "") for mount in _mounts_of(inspect)
    ) - {""}


def inherited_mounts(inspect: dict[str, Any], required: tuple[str, ...]) -> tuple[Mount, ...]:
    """The archiver's configuration surface, carried forward READ-ONLY.

    Selected by *destination* out of the running database container, because the
    host side is a path into the active secret generation and the active
    generation changes on every deploy: any path into it is derived, never typed
    (CLAUDE.md §7). Re-deriving it here would be a second authority that is right
    until the next `up`.

    Every required destination must be present. A database container missing one
    of them is a container that cannot be archiving, and a drill that quietly
    dropped the mount would fail later, inside pgBackRest, with an error about a
    credential rather than about a deployment.
    """
    by_destination = {str(mount.get("Destination")): mount for mount in _mounts_of(inspect)}
    carried: list[Mount] = []
    for destination in required:
        mount = by_destination.get(destination)
        if mount is None:
            raise DrillError(
                f"the database container does not mount {destination}. It cannot be "
                "archiving, so there is nothing for a drill to restore from -- and a "
                "drill that carried on would fail inside pgBackRest with a message "
                "about a credential rather than about this deployment."
            )
        kind = "volume" if mount.get("Type") == "volume" else "bind"
        source = str(mount.get("Name") if kind == "volume" else mount.get("Source"))
        # Read-only whatever the live container has it as. The drill reads this
        # material and has no reason to write any of it, and a config the drill
        # could rewrite is a config the next archive-push would read.
        carried.append(Mount(source=source, target=destination, readonly=True, kind=kind))
    return tuple(carried)


def inherited_environment(inspect: dict[str, Any]) -> dict[str, str]:
    """Every `PGBACKREST_*` variable the database container carries.

    See :data:`PGBACKREST_ENVIRONMENT_PREFIX`. Nothing else is inherited -- not
    `POSTGRES_PASSWORD_FILE`, which the drill instance does not need because its
    PGDATA is restored and the image's entrypoint skips initialisation, and not
    `POSTGRES_DB`, which is likewise already in the restored cluster.

    Returns the names and values as they stand. **No value is logged, printed or
    written to the evidence document**; it is passed to `docker run` through
    `--env NAME=VALUE`, which is the same argument-vector exposure the archiver
    already has inside its own container, and it is why D558's repair belongs at
    the database service rather than here.
    """
    environment: dict[str, str] = {}
    for entry in inspect.get("Config", {}).get("Env") or []:
        name, separator, value = str(entry).partition("=")
        if separator and name.startswith(PGBACKREST_ENVIRONMENT_PREFIX):
            environment[name] = value
    return environment


def build_plan(
    *,
    document: dict[str, Any],
    inspect: dict[str, Any],
    drill_id: str,
    contract: dict[str, Any],
) -> DrillPlan:
    """One plan, from the deployed document and the running database container.

    Nothing here is re-derived from a manifest. The stanza, the project key, the
    database name and the live volume are read out of `outputs.json` (ADR 0002);
    the image, the mounts and the environment are read off the container that is
    actually running, which is the authority on what the archiver is configured
    with right now.
    """
    backup = document.get("backup") or {}
    stanza = backup.get("stanza")
    if not stanza:
        raise DrillError(
            "this project's deployed document declares no backup stanza, which means "
            "backups are disabled for it. There is nothing here to restore."
        )
    if not backup.get("enabled"):
        raise DrillError(
            "backups are disabled for this project in its manifest. Enable "
            "backup.enabled and redeploy; this command does not configure a project."
        )

    key = (document.get("project") or {}).get("key")
    if not key:
        raise DrillError("the deployed document names no project key")

    live_volume = ((document.get("compose") or {}).get("volumes") or {}).get("postgres")
    if not live_volume:
        raise DrillError(
            "the deployed document names no postgres volume, so nothing here can say "
            "which volume the drill must not touch. Refusing rather than guessing."
        )

    image = str(inspect.get("Image") or "")
    if not image:
        raise DrillError("the database container reports no image id")

    return DrillPlan(
        image=image,
        names=naming.restore_drill_names(str(key), drill_id),
        stanza=str(stanza),
        database=str((document.get("database") or {}).get("name") or "postgres"),
        project_key=str(key),
        live_container=str(inspect.get("Name") or "").lstrip("/"),
        live_volume=str(live_volume),
        live_mount_sources=live_mount_sources(inspect),
        inherited=inherited_mounts(inspect, required_container_paths(contract)),
        environment=inherited_environment(inspect),
        network=(document.get("compose") or {}).get("networks", {}).get("backup"),
        roles=dict((document.get("database") or {}).get("roles") or {}),
    )


def assert_disposable(plan: DrillPlan, arguments: tuple[str, ...] | list[str]) -> None:
    """Refuse a plan that could reach anything that is not the drill's (ADR 0151 §5).

    **This runs in the product path, on every invocation, before any `docker`
    process is started**, and that is the whole design. D523 rules out the
    obvious proof in advance: an offline scan asserting the source never *names*
    the live volume is D277's shape, satisfied by dead code, and D464 is this
    repository's standing example of a text scan producing a false positive. What
    anybody actually fears is a *derivation* that produces the live name, and a
    derivation mentions nothing.

    So the check is on the argument vector, and the offline rig drives the
    command until it produces one -- with a **control arm** in which the
    derivation is deliberately wrong. An assertion that only ever sees correct
    input is D509's shape: *a control that cannot fail for the reason it is
    watching for is not a control.*
    """
    if plan.names.volume == plan.live_volume:
        raise DisposabilityError(
            f"the drill volume derived to {plan.names.volume!r}, which is the live "
            "data volume. Nothing is started."
        )
    if plan.names.volume in plan.live_mount_sources:
        raise DisposabilityError(
            f"the drill volume {plan.names.volume!r} is already mounted by the live "
            f"database container {plan.live_container!r}. Nothing is started."
        )
    if plan.names.container == plan.live_container:
        raise DisposabilityError(
            f"the drill container derived to {plan.names.container!r}, which is the "
            "running database container. Nothing is started."
        )

    for mount in plan.mounts():
        # The data mount is identified by its TARGET, never by object identity:
        # `data_mount` is a property that builds a fresh `Mount` on every read,
        # so `mount is not plan.data_mount` was true for the data mount itself
        # and refused every correct plan. Caught by the subject arm, which is
        # what a subject arm is for -- a guard that only ever fires is as broken
        # as one that never does.
        is_data_mount = mount.target == runtime_override.POSTGRES_VOLUME_TARGET
        if mount.source == plan.live_volume:
            raise DisposabilityError(
                f"a drill mount names the live data volume {plan.live_volume!r} "
                f"at {mount.target}. Nothing is started."
            )
        if is_data_mount and mount.source != plan.names.volume:
            raise DisposabilityError(
                f"the data mount names {mount.source!r} rather than the drill volume "
                f"{plan.names.volume!r}. Nothing is started."
            )
        if not is_data_mount and not mount.readonly:
            raise DisposabilityError(
                f"the inherited mount {mount.source!r} at {mount.target} is writable. "
                "Everything the drill inherits it reads. Nothing is started."
            )

    forbidden = sorted(set(arguments) & set(FORBIDDEN_RESTORE_FLAGS))
    if forbidden:
        raise DisposabilityError(
            f"{', '.join(forbidden)} is on the restore argument vector. pgBackRest "
            f"refuses a populated directory with exit {RESTORE_EXIT_POPULATED_DIRECTORY}, "
            "and that refusal is the outer guard this drill does not disarm. "
            "Nothing is started."
        )


def restore_arguments(plan: DrillPlan, target_time: str) -> tuple[str, ...]:
    """The pgBackRest argument vector for the restore. No secret is in it.

    `--log-level-console` overrides the rendered `warn` for this invocation only,
    because at `warn` a successful restore prints nothing at all and the backup
    set would be unreadable (ADR 0152 §3).

    `--target-action=promote` is what makes the restored instance *finish*: it
    leaves recovery and accepts writes, which is what "the command queried the
    restored instance" requires. Without it the instance pauses at the target and
    a smoke check would be reading a cluster in recovery.
    """
    return (
        f"--stanza={plan.stanza}",
        f"--log-level-console={RESTORE_LOG_LEVEL}",
        "restore",
        "--type=time",
        f"--target={target_time}",
        "--target-action=promote",
    )


def instance_command() -> tuple[str, ...]:
    """The drill instance's command line: archiving OFF, explicitly (ADR 0151 §6).

    A promoted restore is on **timeline 2** (measured: 2 on the drill, 1 on the
    live cluster). An instance with `archive_mode=on` and the project's
    `archive_command` would push its own divergent history into the project's
    stanza -- the live volume untouched, and the repository corrupted anyway.

    Stated rather than left to the restored configuration: this project sets
    `archive_mode` on the **command line** (ADR 0144), so the restored
    `postgresql.conf` says nothing about it, and relying on a default is relying
    on the absence of a setting somebody may later add.
    """
    return ("postgres", "-c", "archive_mode=off")


def archive_mode_is_off(command: tuple[str, ...] | list[str]) -> bool:
    """Does this command line turn archiving off? Used by the check and by tests."""
    return "archive_mode=off" in list(command)


def instant(value: str | None) -> datetime | None:
    """One timestamp, parsed, because the two this module compares are not one format.

    **The achieved recovery point and the published floor arrive in different
    spellings of the same instant**, and comparing them as strings is wrong in a
    way that looks right:

        pgbackrest info, via backup_report   2026-08-25T10:42:29Z
        PostgreSQL, via psql                 2026-08-25 10:45:00.109084+00

    Lexicographically the second sorts *before* the first whenever the dates
    agree, because a space is 0x20 and ``T`` is 0x54. So a drill that landed
    thirty seconds **after** the floor would have been reported as landing before
    it -- and `drill_verdict` would have failed every correct drill with a
    sentence about an inconsistency that was entirely its own.

    This is the defect this repository keeps producing (§6): a comparison that
    coincides with the right answer for as long as the two formats happen to
    agree, which here is never. Caught by the subject arm of the verdict tests.

    Raises rather than returning None for an unparseable value. A comparison that
    silently degrades to "unknown" is how the check comes back.
    """
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise DrillError(
            f"{text!r} is not a timestamp this drill can compare ({error}). The two "
            "sources are `pgbackrest info` through backup_report and PostgreSQL "
            "through psql; a third spelling means something changed upstream."
        ) from error


def parse_backup_set(output: str) -> str:
    """The backup set label pgBackRest says it restored (ADR 0152 §3).

    Raises rather than returning None. A drill that could not read the label
    publishes **no** backup set rather than an empty one, and an empty field in
    an evidence document is indistinguishable from a field nobody filled in.

    If pgBackRest changes this wording the drill goes red on a working restore.
    That is the failure direction this repository accepts: D374 is the record of
    a test checking a string its target could not contain, which passed for an
    unrelated reason -- and a silently-empty field is that defect with the
    evidence document as its reader.
    """
    match = _BACKUP_SET_LINE.search(output or "")
    if match is None:
        raise DrillError(
            "the restore did not name a backup set. Expected a line matching "
            f"{_BACKUP_SET_LINE.pattern!r} at --log-level-console={RESTORE_LOG_LEVEL}; "
            "a restore is completely silent at the rendered `warn` level, so an empty "
            "capture here means the log level did not take rather than that the "
            "restore did nothing."
        )
    return match.group("label")


def backup_set_type(summary_backups: list[dict[str, Any]], label: str) -> str:
    """The set's type, from `pgbackrest info` and NOT from the label's suffix.

    `20260825-104447F` ends in `F` and that does mean full -- and reading it that
    way would be this repository deriving a fact from a third party's naming
    convention when the third party publishes the fact itself. The cross-check is
    the point: a label the repository's own report does not contain is a label
    parsed out of the wrong line.
    """
    for backup in summary_backups:
        if backup.get("label") == label:
            return str(backup.get("type") or "")
    raise DrillError(
        f"pgbackrest info does not list a backup set named {label!r}, which the "
        "restore said it used. Two reads of one repository disagree; nothing here "
        "can say which is right."
    )


def evidence_document(
    *,
    plan: DrillPlan,
    drill_id: str,
    requested_target: str,
    observed: dict[str, Any],
    repository: dict[str, Any],
    backup_set: dict[str, str],
    timings: dict[str, float],
    smoke: dict[str, Any],
    release: str | None = None,
) -> dict[str, Any]:
    """The drill's record. Every field has a source and none of them is the clock.

    ``observed`` is what the *restored instance* answered, read once by
    `bin/restore-test.py`: `recovery_target_time`, `pg_last_xact_replay_timestamp`,
    `pg_last_wal_replay_lsn`, `timeline_id`, `schema_version`.

    **What this never carries** (plan §6, restated so that a future field has to
    argue against it): a credential, a cipher pass, a connection string, a bucket
    URL with a signature in it, or any row of restored user data. Identifiers,
    timestamps, an LSN, counts and verdicts -- nothing else.
    """
    achieved = observed.get("achieved_recovery_point")
    floor = repository.get("latest_recoverable_time")

    return {
        "kind": "restore_drill",
        "project_key": plan.project_key,
        "stanza": plan.stanza,
        "release": release,
        "drill": {
            "id": drill_id,
            "volume": plan.names.volume,
            "container": plan.names.container,
            "restore_container": plan.names.restore_container,
        },
        "backup_set": {
            "label": backup_set.get("label"),
            "type": backup_set.get("type"),
        },
        "recovery": {
            # Read BACK off the restored instance, never echoed from the command
            # line: a copy of an input cannot disagree with anything, and the
            # pair exists so that it can (ADR 0152 §2).
            "requested_target": observed.get("requested_target"),
            # And the operator's own words, recorded beside it so that a
            # mismatch between what was asked for and what pgBackRest parsed is
            # visible rather than absorbed.
            "requested_target_argument": requested_target,
            "achieved_recovery_point": achieved,
            "achieved_lsn": observed.get("achieved_lsn"),
            "timeline_id": observed.get("timeline_id"),
            # The FLOOR, from `pgbackrest info` (D550, ADR 0149). An achieved
            # point LATER than this is the floor being a floor. An achieved point
            # EARLIER than it is an inconsistency, and `drill_verdict` says so.
            "latest_recoverable_time": floor,
            "achieved_is_at_or_after_floor": (
                None
                if not (instant(achieved) and instant(floor))
                else instant(achieved) >= instant(floor)
            ),
        },
        "timing": {
            # Wall time this command measured, split because the two halves fail
            # for different reasons: restore scales with the cluster, recovery
            # scales with the distance from the backup set to the target.
            "restore_seconds": round(float(timings.get("restore_seconds", 0.0)), 3),
            "recovery_seconds": round(float(timings.get("recovery_seconds", 0.0)), 3),
            "rto_seconds": round(float(timings.get("rto_seconds", 0.0)), 3),
            # pgBackRest's own elapsed time, recorded BESIDE ours and never
            # instead of it: it excludes recovery entirely, so a document
            # carrying it alone understates an RTO by the part that scales.
            "pgbackrest_reported_ms": timings.get("pgbackrest_reported_ms"),
            "measured_by": "bin/restore-test.py, time.monotonic()",
        },
        "schema_version": observed.get("schema_version"),
        "smoke": smoke,
        "verdict": drill_verdict(observed=observed, repository=repository, smoke=smoke),
    }


def drill_verdict(
    *, observed: dict[str, Any], repository: dict[str, Any], smoke: dict[str, Any]
) -> dict[str, Any]:
    """Pass or fail, computed -- never written by hand (ADR 0045's rule, applied).

    Five conditions, and the first two are the ones a drill fails silently
    without:

    * `pg_last_xact_replay_timestamp()` is NULL on a cluster that **never
      recovered** (measured, live control). A null here means this drill read a
      cluster that is not a restore, so it is a failure and not a missing value.
    * the timeline must have advanced. A promoted restore is on timeline 2; a
      drill reading the live cluster would see 1.
    """
    reasons: list[str] = []
    achieved = observed.get("achieved_recovery_point")
    floor = repository.get("latest_recoverable_time")

    if not achieved:
        reasons.append(
            "the restored instance reported no achieved recovery point. "
            "pg_last_xact_replay_timestamp() is NULL on a cluster that never "
            "recovered, so this reads as a cluster that is not a restore."
        )
    if not observed.get("achieved_lsn"):
        reasons.append("the restored instance reported no replay LSN")
    timeline = observed.get("timeline_id")
    if timeline is None or int(timeline) < 2:
        reasons.append(
            f"the restored instance is on timeline {timeline!r}; a promoted "
            "point-in-time restore advances the timeline, and timeline 1 is what "
            "the live cluster is on"
        )
    # Parsed, never compared as strings: the two sources spell one instant two
    # ways and the string order is the reverse of the real one. See `instant`.
    achieved_at, floor_at = instant(achieved), instant(floor)
    if achieved_at and floor_at and achieved_at < floor_at:
        reasons.append(
            f"the achieved recovery point {achieved} is EARLIER than the repository's "
            f"published latest recoverable time {floor}, which the repository claims "
            "is reachable"
        )
    # `applicable` is read, and a check that did not run is neither a pass nor a
    # failure here -- it is `REC-SMOKE-001`'s business, which asserts both fields.
    # Defaulting to True keeps Run 8's three checks, which have no such field,
    # exactly as strict as they were.
    failed = sorted(
        name
        for name, result in (smoke or {}).items()
        if result.get("applicable", True) and not result.get("passed")
    )
    if failed:
        reasons.append(f"smoke checks failed: {', '.join(failed)}")

    return {"passed": not reasons, "reasons": reasons}
