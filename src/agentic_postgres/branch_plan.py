"""A branch's restore, recovery and life, decided before anything starts (ADR 0271).

A branch is the restore drill made to live (ADR 0151, D2424). Its first two
phases ARE the drill's -- the same pgBackRest argument vector, the parent's
repository mounts inherited out of the parent's RUNNING database container and
forced read-only, the parent's backup network -- and its third is what the
drill never had: an instance that stays, with no way back to the repository.

    restore      a one-shot `pgbackrest restore` into the branch's own volume
    recovery     `postgres -c archive_mode=off` on that volume, with the same
                 read-only mounts, until it promotes; then removed
    persistent   the branch's `postgres`: the volume and nothing else mounted,
                 the branch's own `internal` network, `archive_mode=off`,
                 `archive_command=/bin/false`, `small`'s database settings

:func:`assert_branch_safe` refuses -- exit 7 at the runtime, before any
`docker` process -- a plan in which the branch could write the parent's volume
or its repository (D2426). Rig 40a's control is the reason the persistent
phase is checked member by member: the same promoted copy started with the
repository mounted and archiving on pushed a timeline-2 segment into the
parent's archive on its first WAL switch.

Pure: nothing here runs a process. The runtime (`bin/branch-runtime.py`, Run 3)
reads the inspect document and the deployed document and executes the plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agentic_postgres import compute_profiles, config, naming, restore_drill, runtime_override
from agentic_postgres.restore_drill import Mount

__all__ = [
    "BRANCH_PROFILE",
    "BRANCH_UNRECLAIMABLE_MB",
    "BranchPlan",
    "BranchPlanError",
    "BranchSafetyError",
    "Phase",
    "assert_branch_safe",
    "build",
    "compose_environment",
    "compose_override",
    "persistent_command",
]

#: Every branch runs this profile's database settings, whatever its parent's
#: (D2431): one charge admission can sum, and a copy that cannot grow past it.
BRANCH_PROFILE = "small"


def _database() -> dict[str, Any]:
    return dict(compute_profiles.PROFILES[BRANCH_PROFILE]["database"])


#: A branch's charge at admission: `small`'s unreclaimable budget (192 MiB at
#: Session 40). The budget it could grow to, not what rig 40c read resident
#: (~21-28 MiB): admission charges the claim, never the sample (D767).
BRANCH_UNRECLAIMABLE_MB = config.unreclaimable_mb(
    {
        member: int(_database()[member])
        for member in ("shared_buffers_mb", "maintenance_work_mem_mb", "max_connections")
    }
)


class BranchPlanError(restore_drill.DrillError):
    """A plan could not be built from what the parent is."""


class BranchSafetyError(restore_drill.DisposabilityError):
    """A plan was built and could reach the parent. Nothing is started (exit 7)."""


@dataclass(frozen=True)
class Phase:
    """One container a branch runs: what it mounts, where, and what it runs."""

    name: str
    container: str
    image: str
    mounts: tuple[Mount, ...]
    network: str | None
    argv: tuple[str, ...]
    entrypoint: str | None = None
    environment: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BranchPlan:
    project_key: str
    branch: str
    names: naming.BranchNames
    hosts: tuple[str, str]
    image: str
    stanza: str
    database: str
    roles: dict[str, str]
    parent_container: str
    parent_volume: str
    parent_mount_sources: frozenset[str]
    parent_backup_network: str
    inherited: tuple[Mount, ...]
    #: The target exactly as pgBackRest receives it, or None for the end of the
    #: archive (D2454: `YYYY-MM-DD HH:MM:SS.ffffff+00:00`, never the `T` form).
    target: str | None
    restore: Phase
    recovery: Phase
    persistent: Phase

    @property
    def phases(self) -> tuple[Phase, Phase, Phase]:
        return (self.restore, self.recovery, self.persistent)


def persistent_command() -> tuple[str, ...]:
    """The branch's own `postgres`: archiving off TWICE over, `small`'s budget.

    `archive_mode=off` stops the postmaster running any archive command; the
    command is `/bin/false` as well so that a later `archive_mode` change by
    anybody still archives nothing -- the disabled project's own pair
    (`rendering._archive_settings`). Both on the command line, where this
    project sets archiving (ADR 0144), so the restored configuration cannot
    supply either.
    """
    database = _database()
    settings = (
        "listen_addresses=*",
        "archive_mode=off",
        "archive_command=/bin/false",
        f"shared_buffers={database['shared_buffers_mb']}MB",
        f"max_connections={database['max_connections']}",
        f"work_mem={database['work_mem_mb']}MB",
        f"maintenance_work_mem={database['maintenance_work_mem_mb']}MB",
    )
    command: list[str] = ["postgres"]
    for setting in settings:
        command += ["-c", setting]
    return tuple(command)


def build(
    *,
    document: dict[str, Any],
    inspect: dict[str, Any],
    contract: dict[str, Any],
    branch: str,
    target_time: str | datetime | None,
) -> BranchPlan:
    """The plan for one branch of the project ``document`` describes.

    ``inspect`` is `docker inspect` of the parent's RUNNING database container:
    the authority on which secret generation the archiver reads right now (the
    drill's rule, ADR 0151). Everything else comes from the deployed document
    (ADR 0002); every name of the branch from :func:`naming.branch_names`.
    """
    backup = document.get("backup") or {}
    stanza = backup.get("stanza")
    if not stanza or not backup.get("enabled"):
        raise BranchPlanError(
            "this project's backups are disabled, so there is no repository to make a branch from"
        )
    project = document.get("project") or {}
    key = project.get("key")
    domain = project.get("domain")
    if not key or not domain:
        raise BranchPlanError("the deployed document names no project key or domain")
    image = str(inspect.get("Image") or "")
    if not image:
        raise BranchPlanError("the parent's database container reports no image id")
    try:
        names = naming.branch_names(str(key), branch)
        hosts = naming.branch_endpoint_hosts(str(domain), branch)
    except naming.NamingError as error:
        raise BranchPlanError(str(error)) from None
    target = None if target_time is None else restore_drill.pgbackrest_target(target_time)

    try:
        inherited = restore_drill.inherited_mounts(
            inspect, restore_drill.required_container_paths(contract)
        )
    except restore_drill.DrillError as error:
        raise BranchPlanError(str(error)) from None
    environment = restore_drill.inherited_environment(inspect)
    backup_network = naming.backup_network_name(str(key))
    data = Mount(
        source=names.volume,
        target=runtime_override.POSTGRES_VOLUME_TARGET,
        readonly=False,
        kind="volume",
    )
    restore = Phase(
        name="restore",
        container=names.restore_container,
        image=image,
        mounts=(data, *inherited),
        network=backup_network,
        entrypoint="pgbackrest",
        argv=restore_drill.restore_argv(str(stanza), target),
        environment=dict(environment),
    )
    recovery = Phase(
        name="recovery",
        container=names.recovery_container,
        image=image,
        mounts=(data, *inherited),
        network=backup_network,
        argv=restore_drill.instance_command(),
        environment=dict(environment),
    )
    persistent = Phase(
        name="persistent",
        container=names.postgres_container,
        image=image,
        mounts=(data,),
        network=names.internal_network,
        argv=persistent_command(),
    )
    return BranchPlan(
        project_key=str(key),
        branch=branch,
        names=names,
        hosts=hosts,
        image=image,
        stanza=str(stanza),
        database=str((document.get("database") or {}).get("name") or "postgres"),
        roles=dict((document.get("database") or {}).get("roles") or {}),
        parent_container=str(inspect.get("Name") or "").lstrip("/"),
        parent_volume=naming.postgres_volume_name(str(key)),
        parent_mount_sources=restore_drill.live_mount_sources(inspect),
        parent_backup_network=backup_network,
        inherited=inherited,
        target=target,
        restore=restore,
        recovery=recovery,
        persistent=persistent,
    )


def compose_environment(
    plan: BranchPlan, *, pgbouncer_image: str, acme_resolver_name: str
) -> dict[str, str]:
    """Every value `infra/branch/compose.yaml` interpolates, for this branch.

    Names from :func:`naming.branch_names`; the database's settings, bounds and
    doors from `small` (D2431) and the resource tables a project's services read
    (`config.SERVICE_RESOURCE_DEFAULTS`, `config.SERVICE_MEMORY_LIMITS_MB`); the
    images are the parent's RUNNING ones, by id. No secret: a branch holds none.
    """
    database = _database()
    resources = compute_profiles.PROFILES[BRANCH_PROFILE]["resources"]["postgres"]
    doors = compute_profiles.CUSTOMER_CONNECTIONS[BRANCH_PROFILE]
    pool = config.SERVICE_RESOURCE_DEFAULTS[naming.CUSTOMER_POOL_SERVICE]
    direct = config.SERVICE_RESOURCE_DEFAULTS[naming.CUSTOMER_DIRECT_SERVICE]
    names = plan.names
    memory = config.SERVICE_MEMORY_LIMITS_MB
    return {
        "COMPOSE_PROJECT_NAME": names.compose_project,
        "PROJECT_KEY": plan.project_key,
        "BRANCH_NAME": plan.branch,
        "BRANCH_POSTGRES_IMAGE": plan.image,
        "BRANCH_PGBOUNCER_IMAGE": pgbouncer_image,
        "BRANCH_POSTGRES_MEMORY_LIMIT": f"{database['memory_limit_mb']}m",
        "BRANCH_POSTGRES_SHM_SIZE": f"{database['shm_size_mb']}m",
        "BRANCH_POSTGRES_PIDS_LIMIT": str(
            config.SERVICE_RESOURCE_DEFAULTS["postgres"]["pids_limit"]
        ),
        "BRANCH_POSTGRES_CPUS": str(resources["cpus"]),
        "BRANCH_SHARED_BUFFERS": f"{database['shared_buffers_mb']}MB",
        "BRANCH_MAX_CONNECTIONS": str(database["max_connections"]),
        "BRANCH_WORK_MEM": f"{database['work_mem_mb']}MB",
        "BRANCH_MAINTENANCE_WORK_MEM": f"{database['maintenance_work_mem_mb']}MB",
        "POSTGRES_DATABASE_NAME": plan.database,
        "CUSTOMER_POOL_PIDS_LIMIT": str(pool["pids_limit"]),
        "CUSTOMER_POOL_CPUS": str(pool["cpus"]),
        "CUSTOMER_POOL_MEMORY_LIMIT": f"{memory[naming.CUSTOMER_POOL_SERVICE]}m",
        "CUSTOMER_POOL_CONNECTIONS": str(doors["pool"]),
        "CUSTOMER_DIRECT_PIDS_LIMIT": str(direct["pids_limit"]),
        "CUSTOMER_DIRECT_CPUS": str(direct["cpus"]),
        "CUSTOMER_DIRECT_MEMORY_LIMIT": f"{memory[naming.CUSTOMER_DIRECT_SERVICE]}m",
        "CUSTOMER_DIRECT_CONNECTIONS": str(doors["direct"]),
        "BRANCH_VOLUME_NAME": names.volume,
        "BRANCH_INTERNAL_NETWORK": names.internal_network,
        "BRANCH_EDGE_NETWORK": names.edge_network,
        "CUSTOMER_POOL_HOST": plan.hosts[0],
        "CUSTOMER_DIRECT_HOST": plan.hosts[1],
        "ACME_RESOLVER_NAME": acme_resolver_name,
    }


def compose_override(plan: BranchPlan, *, userlist_directory: str) -> dict[str, Any]:
    """The override the runtime writes beside the env file: the two TCP routers
    -- the project's own label builder with the branch's router names (D2462) --
    and the userlist bind from the branch's own directory."""
    return {
        "services": runtime_override.customer_pooler_services(
            pool_router_name=plan.names.pool_router,
            direct_router_name=plan.names.direct_router,
            userlist_directory=userlist_directory,
        )
    }


def _archive_settings(argv: tuple[str, ...]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {"archive_mode": [], "archive_command": []}
    for part in argv:
        name, separator, value = part.partition("=")
        if separator and name in found:
            found[name].append(value)
    return found


def assert_branch_safe(plan: BranchPlan) -> None:
    """Refuse a plan through which the branch could reach its parent (D2426).

    Run on every create and reset, before any `docker` process. Each refusal
    names what it found; none of them can be argued past by a flag.
    """
    names = plan.names
    if names.volume == plan.parent_volume or names.volume in plan.parent_mount_sources:
        raise BranchSafetyError(
            f"the branch volume {names.volume!r} is the parent's volume or mounted by the "
            f"parent's database container {plan.parent_container!r}. Nothing is started."
        )
    own_containers = {names.restore_container, names.recovery_container, names.postgres_container}
    if plan.parent_container in own_containers:
        raise BranchSafetyError(
            f"a branch container derived to the parent's {plan.parent_container!r}. "
            "Nothing is started."
        )

    for phase in (plan.restore, plan.recovery):
        data = [m for m in phase.mounts if m.target == runtime_override.POSTGRES_VOLUME_TARGET]
        if len(data) != 1 or data[0].source != names.volume or data[0].readonly:
            raise BranchSafetyError(
                f"the {phase.name} phase's data mount is not the branch volume "
                f"{names.volume!r}, read-write, alone. Nothing is started."
            )
        for mount in phase.mounts:
            if mount.source == plan.parent_volume:
                raise BranchSafetyError(
                    f"the {phase.name} phase mounts the parent's volume "
                    f"{plan.parent_volume!r}. Nothing is started."
                )
            if mount.target != runtime_override.POSTGRES_VOLUME_TARGET and not mount.readonly:
                raise BranchSafetyError(
                    f"the {phase.name} phase mounts {mount.source!r} at {mount.target} "
                    "writable; everything a branch inherits it reads. Nothing is started."
                )

    forbidden = sorted(set(plan.restore.argv) & set(restore_drill.FORBIDDEN_RESTORE_FLAGS))
    if forbidden:
        raise BranchSafetyError(
            f"{', '.join(forbidden)} is on the restore argument vector; pgBackRest's "
            "refusal of a populated directory is not disarmed. Nothing is started."
        )
    recovery_archive = _archive_settings(plan.recovery.argv)
    if recovery_archive["archive_mode"] != ["off"]:
        raise BranchSafetyError(
            "the recovery instance does not run with archive_mode=off alone; a promoted "
            "restore would push its new timeline into the parent's repository. "
            "Nothing is started."
        )

    persistent = plan.persistent
    inherited_sources = {mount.source for mount in plan.inherited}
    if len(persistent.mounts) != 1 or persistent.mounts[0].source != names.volume:
        raise BranchSafetyError(
            "the branch's persistent postgres mounts something other than its own volume. "
            "Nothing is started."
        )
    for mount in persistent.mounts:
        if mount.source in inherited_sources or mount.target.startswith("/etc/pgbackrest"):
            raise BranchSafetyError(
                f"the branch's persistent postgres mounts {mount.source!r} at "
                f"{mount.target}: the parent's repository configuration or credential. "
                "Nothing is started."
            )
    if persistent.network != names.internal_network:
        raise BranchSafetyError(
            f"the branch's persistent postgres joins {persistent.network!r}, not its own "
            f"internal network {names.internal_network!r}"
            + (
                " -- the parent's backup network"
                if persistent.network == plan.parent_backup_network
                else ""
            )
            + ". Nothing is started."
        )
    if any(
        name.startswith(restore_drill.PGBACKREST_ENVIRONMENT_PREFIX)
        for name in persistent.environment
    ):
        raise BranchSafetyError(
            "the branch's persistent postgres carries a PGBACKREST_ variable. Nothing is started."
        )
    archive = _archive_settings(persistent.argv)
    if archive != {"archive_mode": ["off"], "archive_command": ["/bin/false"]}:
        raise BranchSafetyError(
            "the branch's persistent postgres does not run with exactly archive_mode=off "
            f"and archive_command=/bin/false (found {archive}). Nothing is started."
        )
