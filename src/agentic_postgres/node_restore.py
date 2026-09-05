"""A restore into a project's OWN volume, on a replacement host (ADR 0189, ADR 0192).

`REC-NODE-001`. The drill (`restore_drill`) restores into a disposable volume
beside a running cluster and inherits the archiver's configuration off that
container. A node restore has neither: the host is a replacement, the cluster
has never started here, and the whole point is that the project's data volume
ends up holding the restored cluster BEFORE the first `up` -- because a first
`up` on an empty volume runs `initdb`, and step 6c's `stanza-create` would
then meet a repository written by a cluster with a different system
identifier (D1008). So the order is: adopt, materialize, **restore**, deploy.

What this module decides, from the kit's deployed document and manifest, the
contract and the active secret generation on this host -- never from a
running container:

* **the volume**: `naming.postgres_volume_name(key)`, the project's own, and
  the one name every mount is checked against (`assert_own_volume`);
* **the repository**: `--from primary` reads the primary bucket with the
  archiver's own three include files; `--from mirror` reads the mirror bucket
  (ADR 0188) with the mirror's key pair, which reaches pgBackRest through the
  restore container's OWN environment -- measured (D1009): an option in the
  environment overrides the same option in a configuration file, so the
  primary's key includes are simply not mounted;
* **the configuration**: `rendering.build_pgbackrest_conf` over the document,
  with the mirror's endpoint and region substituted -- one renderer, and a
  file that names no credential;
* **the argument vector**: a plain `restore` for `--latest` (measured, D1011:
  `--target-action` is refused without a `--type`), or `--type=time` with
  `--target-action=promote` for a target time; never `--delta` (D997 is the
  outer guard, `[040]`, and this module does not disarm it);
* **the refusals** a caller applies before anything starts: a volume holding
  `PG_VERSION` (D1012), a container mounting the volume, a manifest naming
  another key or stanza, a mirror asked of a document that has none.

Nothing here runs a process.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_postgres import config, naming, rendering, runtime_override
from agentic_postgres.restore_drill import (
    FORBIDDEN_RESTORE_FLAGS,
    RESTORE_LOG_LEVEL,
    Mount,
    instant,
)
from agentic_postgres.secrets_contract import (
    active_secrets,
    container_secret_path,
    enabled_facilities,
    secret_source_path,
)

__all__ = [
    "CONFIG_CONTAINER_PATH",
    "INCLUDE_CONTAINER_DIR",
    "MIRROR_KEY_FILES",
    "SOURCES",
    "RestoreError",
    "RestorePlan",
    "RestoreRefusal",
    "assert_own_volume",
    "build_plan",
    "evidence_document",
    "instance_arguments",
    "pg_version_relative_path",
    "restore_arguments",
    "restore_verdict",
    "wrapper_script",
]

SOURCES = ("primary", "mirror")
#: Where the rendered restore configuration is mounted inside the container.
#: NOT `pgbackrest.conf`: that path is the archiver's, and a restore that could
#: be mistaken for the archiver's configuration is one somebody later starts a
#: postmaster against.
CONFIG_CONTAINER_PATH = "/etc/pgbackrest/restore.conf"
#: pgBackRest's include directory, the same one the archiver's consumers land
#: in (ADR 0153); passed on the command line because pgBackRest honours
#: `config-include-path` only there (Run 1's rig, D1010).
INCLUDE_CONTAINER_DIR = "/etc/pgbackrest/conf.d"
#: The mirror pair as the postgres consumer sees it (raw files, ADR 0192), in
#: the order the wrapper exports them: key id, then secret.
MIRROR_KEY_FILES = ("mirror-s3-access-key-id", "mirror-s3-secret-access-key")
_MIRROR_ENV = ("PGBACKREST_REPO1_S3_KEY", "PGBACKREST_REPO1_S3_KEY_SECRET")
_MIRROR_SECRET_NAMES = ("mirror_s3_access_key_id", "mirror_s3_secret_access_key")


class RestoreError(Exception):
    """The plan cannot be built. The message names why."""


class RestoreRefusal(RestoreError):
    """The plan could be built and must not run. Nothing is started."""


@dataclass(frozen=True)
class RestorePlan:
    project_key: str
    stanza: str
    database: str
    source: str
    #: The project's own data volume -- the one name every mount is checked against.
    volume: str
    image: str
    generation_id: str
    #: The rendered restore configuration, no credential in it.
    configuration: str
    #: Everything mounted beside the data volume, all read-only.
    inherited: tuple[Mount, ...]
    restore_container: str
    instance_container: str
    network: str | None
    expected_instance_uuid: str | None
    release: str | None

    @property
    def data_mount(self) -> Mount:
        return Mount(
            source=self.volume,
            target=runtime_override.POSTGRES_VOLUME_TARGET,
            readonly=False,
            kind="volume",
        )

    def mounts(self) -> tuple[Mount, ...]:
        return (self.data_mount, *self.inherited)


def pg_version_relative_path() -> str:
    """`PG_VERSION`'s path relative to the volume's mount point: what a caller
    tests for to decide whether the volume holds a cluster (D1012). Derived
    from the two constants the runtime override owns, never typed."""
    pgdata = Path(runtime_override.POSTGRES_PGDATA)
    return str(pgdata.relative_to(runtime_override.POSTGRES_VOLUME_TARGET) / "PG_VERSION")


def build_plan(
    *,
    document: dict[str, Any],
    manifest: dict[str, Any],
    contract: dict[str, Any],
    session: int,
    generation_id: str,
    configuration_host_path: Path,
    source: str,
    image: str,
    restore_id: str,
) -> RestorePlan:
    """One plan from the kit's two documents, the contract and this host's generation.

    ``document`` is the deployed document the kit carries (the stanza, the
    buckets, the identity); ``manifest`` is the project manifest deployed on
    this host (the primary endpoint's account, and the key it must agree on);
    ``generation_id`` is this host's active secret generation for the key,
    read by the caller from the pointer the materializer wrote.
    """
    if source not in SOURCES:
        raise RestoreError(f"--from must be one of {SOURCES}, not {source!r}")
    backup = document.get("backup") or {}
    key = str((document.get("project") or {}).get("key") or "")
    if not key:
        raise RestoreError("the deployed document names no project key")
    if not backup.get("enabled") or not backup.get("stanza"):
        raise RestoreError(
            f"{key}'s deployed document declares no backup stanza; there is nothing to restore"
        )
    stanza = str(backup["stanza"])

    project = manifest.get("project") or {}
    manifest_key = naming.project_key(str(project.get("slug")), str(project.get("environment")))
    if manifest_key != key:
        raise RestoreRefusal(
            f"the manifest derives project {manifest_key!r} and the deployed document names "
            f"{key!r}; a restore under one project's key from another's document is refused"
        )
    manifest_backup = manifest.get("backup") or {}
    manifest_stanza = str(manifest_backup.get("stanza") or key)
    if manifest_stanza != stanza:
        raise RestoreRefusal(
            f"the manifest names stanza {manifest_stanza!r} and the deployed document "
            f"{stanza!r}; they must agree (ADR 0002)"
        )

    mirror = backup.get("mirror") or {}
    if source == "mirror":
        if not mirror.get("enabled") or not mirror.get("bucket") or not mirror.get("endpoint"):
            raise RestoreRefusal(
                f"{key} has no mirror in its deployed document; --from mirror has nothing to read"
            )
        bucket, endpoint, region = (
            str(mirror["bucket"]),
            str(mirror["endpoint"]),
            str(mirror.get("region") or "auto"),
        )
    else:
        account = manifest_backup.get("account_id")
        if not account:
            raise RestoreError("the manifest's backup block names no account_id")
        bucket = str(backup["bucket"])
        endpoint = naming.storage_endpoint_url(
            str(account), str(manifest_backup.get("jurisdiction") or "default")
        ).removeprefix("https://")
        region = "auto"

    # One renderer for every pgBackRest configuration this repository writes:
    # the document's own block with the source's coordinates substituted.
    configuration = rendering.build_pgbackrest_conf(
        None,
        {
            "backup": {
                "enabled": True,
                "stanza": stanza,
                "bucket": bucket,
                "repository_prefix": str(backup["repository_prefix"]),
                "retain_full": int(backup.get("retain_full") or 1),
            }
        },
        endpoint,
        region=region,
    ).decode("utf-8")

    inherited = [
        Mount(
            source=str(configuration_host_path),
            target=CONFIG_CONTAINER_PATH,
            readonly=True,
            kind="bind",
        )
    ]
    # The include files: the cipher pass always (the objects were written under
    # it whichever bucket they sit in, ADR 0188); the primary's key pair only
    # when the primary is the source. A mirror restore never mounts them, so
    # the primary account's credential is absent from the argument vector
    # rather than merely overridden (D1009 makes either sufficient).
    wanted = {"pgbackrest_repo_cipher_pass"}
    if source == "primary":
        wanted |= {"backup_r2_access_key_id", "backup_r2_secret_access_key"}
    else:
        wanted |= set(_MIRROR_SECRET_NAMES)
    found: set[str] = set()
    for secret in active_secrets(contract, session, facilities=enabled_facilities(document)):
        if secret["name"] not in wanted:
            continue
        for consumer in secret["consumers"]:
            if consumer.get("service") != "postgres":
                continue
            found.add(secret["name"])
            inherited.append(
                Mount(
                    source=secret_source_path(key, generation_id, consumer),
                    target=container_secret_path(consumer),
                    readonly=True,
                    kind="bind",
                )
            )
    missing = sorted(wanted - found)
    if missing:
        raise RestoreError(
            f"the contract grants the postgres service no file for {missing}; a restore "
            f"--from {source} cannot reach the repository. For a mirror, the manifest "
            "must enable backup.mirror so the pair is materialized (ADR 0192)."
        )

    names = naming.restore_drill_names(key, restore_id)
    return RestorePlan(
        project_key=key,
        stanza=stanza,
        database=str((document.get("database") or {}).get("name") or "postgres"),
        source=source,
        volume=naming.postgres_volume_name(key),
        image=image,
        generation_id=generation_id,
        configuration=configuration,
        inherited=tuple(inherited),
        restore_container=names.restore_container,
        instance_container=names.container,
        network=naming.backup_network_name(key),
        expected_instance_uuid=(
            ((document.get("database") or {}).get("observed") or {}).get("instance_uuid")
        ),
        release=document.get("source_commit"),
    )


def assert_own_volume(plan: RestorePlan, arguments: tuple[str, ...] | list[str]) -> None:
    """Refuse a plan whose mounts name any volume but the project's own, or
    whose argument vector carries `--delta` (`REC-NODE-001`).

    The check is on the mounts and the argument vector, as the drill's is: a
    derivation that produced another project's volume would mention nothing.
    """
    for mount in plan.mounts():
        is_data = mount.target == runtime_override.POSTGRES_VOLUME_TARGET
        if mount.kind == "volume" and mount.source != plan.volume:
            raise RestoreRefusal(
                f"a mount names the volume {mount.source!r}, which is not this project's "
                f"{plan.volume!r}. Nothing is started."
            )
        if is_data and mount.source != plan.volume:
            raise RestoreRefusal(
                f"the data mount names {mount.source!r} rather than {plan.volume!r}. "
                "Nothing is started."
            )
        if not is_data and not mount.readonly:
            raise RestoreRefusal(
                f"the inherited mount {mount.source!r} at {mount.target} is writable. "
                "Nothing is started."
            )
    forbidden = sorted(set(arguments) & set(FORBIDDEN_RESTORE_FLAGS))
    if forbidden:
        raise RestoreRefusal(
            f"{', '.join(forbidden)} is on the restore argument vector; pgBackRest's own "
            "refusal of a populated directory is the guard this command does not disarm "
            "(D997). Nothing is started."
        )


def restore_arguments(plan: RestorePlan, target_time: str | None) -> tuple[str, ...]:
    """pgBackRest's argument vector. `--latest` is a plain restore: recovery
    replays every archived segment and ends with a promotion on a new timeline;
    `--target-action` is refused without a `--type` (D1011)."""
    common = (
        f"--config={CONFIG_CONTAINER_PATH}",
        f"--config-include-path={INCLUDE_CONTAINER_DIR}",
        f"--stanza={plan.stanza}",
        f"--log-level-console={RESTORE_LOG_LEVEL}",
        "restore",
    )
    if target_time is None:
        return common
    return (*common, "--type=time", f"--target={target_time}", "--target-action=promote")


def instance_arguments() -> tuple[str, ...]:
    """The restored instance's command: archiving OFF, as the drill's (ADR 0151
    §6). The instance exists to finish recovery and promote; the deploy that
    follows starts the cluster by the route production uses."""
    return ("postgres", "-c", "archive_mode=off")


def wrapper_script() -> str:
    """The shell that puts the mirror's key pair into pgBackRest's environment
    from the two mounted files, then execs whatever it was given.

    Inside the container only: the values exist in the process environment of
    the restore and of the recovering instance (whose `archive-get` inherits
    it), never in an argument vector on the host and never printed. The same
    shape `services/backup-mirror/mirror.sh` uses for its client.
    """
    reads = " ".join(
        f'{name}="$(cat /run/secrets/{file})"'
        for name, file in zip(_MIRROR_ENV, MIRROR_KEY_FILES, strict=True)
    )
    exports = " ".join(_MIRROR_ENV)
    return f'set -eu; {reads}; export {exports}; exec "$@"'


def restore_verdict(
    *, observed: dict[str, Any], expected_instance_uuid: str | None
) -> dict[str, Any]:
    """Pass or fail, computed (ADR 0045). Four conditions:

    * a replay LSN, which is NULL on a cluster that never recovered;
    * a timeline of 2 or more: every archive recovery ends on a new timeline;
    * the restored cluster's `instance_uuid` equals the kit's document's,
      when the kit recorded one -- the identity `REC-NODE-002` names;
    * a migration ledger with at least one row: a restored empty cluster is
      not this project.

    `pg_last_xact_replay_timestamp()` is deliberately NOT required: a restore
    to the latest point right after a full backup can replay no committed
    transaction and still be complete, which the drill's stricter rule (a
    target later than the newest set) never meets.
    """
    reasons: list[str] = []
    if not observed.get("achieved_lsn"):
        reasons.append("the restored instance reported no replay LSN; it did not recover")
    timeline = observed.get("timeline_id")
    if timeline is None or int(timeline) < 2:
        reasons.append(
            f"the restored instance is on timeline {timeline!r}; a promoted restore "
            "advances the timeline"
        )
    seen = observed.get("instance_uuid")
    if expected_instance_uuid and seen != expected_instance_uuid:
        reasons.append(
            f"the restored cluster's instance_uuid {seen!r} is not the kit's "
            f"{expected_instance_uuid!r}; this is not the project the kit describes"
        )
    if not (observed.get("schema_migration_count") or 0):
        reasons.append("the restored cluster holds no migration ledger; it is not this project")
    return {"passed": not reasons, "reasons": reasons}


def evidence_document(
    *,
    plan: RestorePlan,
    restore_id: str,
    requested_target: str | None,
    observed: dict[str, Any],
    repository: dict[str, Any],
    backup_set: dict[str, str | None],
    timings: dict[str, float | int | None],
) -> dict[str, Any]:
    """The restore's record, in the drill's shape (ADR 0152) with three
    differences a reader can see: `kind`, `source`, and `identity`. Identifiers,
    timestamps, an LSN, counts and verdicts -- never a value."""
    achieved = observed.get("achieved_recovery_point")
    floor = repository.get("latest_recoverable_time")
    return {
        "kind": "node_restore",
        "project_key": plan.project_key,
        "stanza": plan.stanza,
        "source": plan.source,
        "release": plan.release,
        "restore": {
            "id": restore_id,
            "volume": plan.volume,
            "container": plan.instance_container,
            "restore_container": plan.restore_container,
            "generation_id": plan.generation_id,
        },
        "backup_set": {"label": backup_set.get("label"), "type": backup_set.get("type")},
        "recovery": {
            "requested_target": observed.get("requested_target"),
            "requested_target_argument": requested_target,
            "achieved_recovery_point": achieved,
            "achieved_lsn": observed.get("achieved_lsn"),
            "timeline_id": observed.get("timeline_id"),
            "latest_recoverable_time": floor,
            "achieved_is_at_or_after_floor": (
                None
                if not (instant(achieved) and instant(floor))
                else instant(achieved) >= instant(floor)
            ),
        },
        "identity": {
            "expected_instance_uuid": plan.expected_instance_uuid,
            "observed_instance_uuid": observed.get("instance_uuid"),
        },
        "timing": {
            "restore_seconds": round(float(timings.get("restore_seconds") or 0.0), 3),
            "recovery_seconds": round(float(timings.get("recovery_seconds") or 0.0), 3),
            "rto_seconds": round(float(timings.get("rto_seconds") or 0.0), 3),
            "pgbackrest_reported_ms": timings.get("pgbackrest_reported_ms"),
            "measured_by": "bin/restore.py, time.monotonic()",
        },
        "schema_version": observed.get("schema_version"),
        "verdict": restore_verdict(
            observed=observed, expected_instance_uuid=plan.expected_instance_uuid
        ),
    }


def config_summary(document: dict[str, Any]) -> dict[str, Any]:
    """What `--plan` prints about the repositories: identifiers only."""
    backup = document.get("backup") or {}
    mirror = backup.get("mirror") or {}
    return {
        "stanza": backup.get("stanza"),
        "primary_bucket": backup.get("bucket"),
        "mirror_enabled": bool(mirror.get("enabled")),
        "mirror_bucket": mirror.get("bucket"),
        "mirror_endpoint": mirror.get("endpoint"),
    }


# `config` is imported for its loaders' benefit in the command; it is also the
# owner of the manifest rules `build_plan` relies on being enforced upstream.
_ = config
