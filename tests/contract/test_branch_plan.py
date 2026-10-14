"""A branch's three phases, and the check that keeps it from its parent
(Session 40, ADR 0271, D2424, D2426, D2454).

The plan is built from a parent's deployed document and a `docker inspect` of
its running database container, as `bin/branch-runtime.py` builds it; nothing
here runs a process. Rig 40a measured the property on a real cluster: the
repository unchanged through a branch's restore, recovery and life, and the
control -- the persistent phase given the repository and archiving -- writing a
timeline-2 segment into it. These proofs hold that the plan the runtime executes
is the rig's, and that every way of building the control is refused.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Any

import pytest

from agentic_postgres import (
    REPO_ROOT,
    branch_plan,
    naming,
    restore_drill,
    runtime_override,
    secrets_contract,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0]

KEY = "slot3-prod"
STANZA = "slot3-prod"
DOMAIN = "slot3.agenticpostgresql.com"
GENERATION = "/var/lib/agentic-postgres/secrets/slot3-prod/20261012T102807Z-abcd"
PARENT_VOLUME = naming.postgres_volume_name(KEY)


def _contract() -> dict[str, Any]:
    return secrets_contract.load_secret_contract(REPO_ROOT / "secrets.required.yaml")


def _inspect() -> dict[str, Any]:
    """The parent's running database container as `docker inspect` reports it:
    its data volume, the archiver's configuration and credential binds out of
    the active generation, and its environment."""
    mounts: list[dict[str, Any]] = [
        {
            "Type": "volume",
            "Name": PARENT_VOLUME,
            "Destination": runtime_override.POSTGRES_VOLUME_TARGET,
            "RW": True,
        }
    ]
    for path in restore_drill.required_container_paths(_contract()):
        mounts.append(
            {
                "Type": "bind",
                "Source": f"{GENERATION}/postgres/{path.rsplit('/', 1)[-1]}",
                "Destination": path,
                "RW": False,
            }
        )
    return {
        "Name": "/apg-slot3-prod-postgres-1",
        "Image": "sha256:8ee5f141d0b840d37a47402f4901ec93efdd18d0c665655eefc3abe6cd2ad484",
        "Mounts": mounts,
        "Config": {"Env": ["PGBACKREST_LOG_LEVEL_FILE=info", "POSTGRES_PASSWORD_FILE=/run/x"]},
    }


def _document() -> dict[str, Any]:
    return {
        "project": {"key": KEY, "domain": DOMAIN},
        "backup": {"enabled": True, "stanza": STANZA},
        "database": {"name": "slot3_prod", "roles": naming.database_roles("slot3_prod")},
    }


def _plan(target: str | datetime | None = "2026-10-14T08:04:56.104356Z") -> branch_plan.BranchPlan:
    return branch_plan.build(
        document=_document(),
        inspect=_inspect(),
        contract=_contract(),
        branch="dev",
        target_time=target,
    )


def test_the_restore_phase_is_the_drills_argv() -> None:
    """The restore and the recovery ARE the drill's (ADR 0151): the same
    pgBackRest vector -- to a time in pgBackRest's one form (D2454), or with no
    point to the end of the archive -- the parent's repository configuration
    and credentials inherited read-only, the parent's backup network, archiving
    off in the recovery. The data mount is the branch's own volume.

    Goes red if: a phase stops inheriting the drill's argv or mounts, the
    target reaches pgBackRest in the `T` form, or the default form carries a
    `--target-action` pgBackRest refuses without a target (D1011)."""
    plan = _plan()
    assert plan.target == "2026-10-14 08:04:56.104356+00:00"
    assert plan.restore.argv == restore_drill.restore_argv(STANZA, plan.target)
    assert plan.restore.argv[-3:] == (
        "--type=time",
        "--target=2026-10-14 08:04:56.104356+00:00",
        "--target-action=promote",
    )
    assert plan.restore.entrypoint == "pgbackrest"
    assert (
        plan.recovery.argv
        == restore_drill.instance_command()
        == ("postgres", "-c", "archive_mode=off")
    )
    for phase in (plan.restore, plan.recovery):
        data, *inherited = phase.mounts
        assert (data.source, data.target, data.readonly) == (
            "apg-slot3-prod_dev-postgres",
            runtime_override.POSTGRES_VOLUME_TARGET,
            False,
        )
        assert inherited and all(mount.readonly for mount in inherited)
        assert {m.target for m in inherited} == set(
            restore_drill.required_container_paths(_contract())
        )
        assert phase.network == naming.backup_network_name(KEY)
        assert phase.environment == {"PGBACKREST_LOG_LEVEL_FILE": "info"}
    assert plan.restore.container == "apg-slot3-prod_dev-pgbackrest"
    assert plan.recovery.container == "apg-slot3-prod_dev-recovery"

    end = _plan(target=None)
    assert end.target is None
    assert end.restore.argv == (
        f"--stanza={STANZA}",
        "--log-level-console=info",
        "restore",
        "--type=default",
    )
    instant = _plan(target=datetime(2026, 10, 14, 8, 4, 56, tzinfo=UTC))
    assert instant.target == "2026-10-14 08:04:56.000000+00:00"
    branch_plan.assert_branch_safe(plan)
    branch_plan.assert_branch_safe(end)


def test_the_persistent_service_cannot_reach_the_repository() -> None:
    """The phase rig 40a ran for a branch's life: its own volume and nothing
    else, its own internal network, no `PGBACKREST_` variable, `archive_mode=off`
    and `archive_command=/bin/false`, and `small`'s database settings. A
    branch is charged `small`'s 192 MiB whatever its parent's profile (D2431).

    Goes red if: the persistent phase gains any mount, network or variable of
    the parent's repository, or archives."""
    persistent = _plan().persistent
    assert persistent.container == "apg-slot3-prod_dev-postgres-1"
    assert len(persistent.mounts) == 1
    assert persistent.mounts[0].source == "apg-slot3-prod_dev-postgres"
    assert persistent.network == "apg-slot3-prod_dev-internal"
    assert persistent.environment == {}
    assert persistent.entrypoint is None
    argv = persistent.argv
    assert argv[0] == "postgres"
    settings = {argv[i + 1] for i, part in enumerate(argv) if part == "-c"}
    assert {
        "archive_mode=off",
        "archive_command=/bin/false",
        "shared_buffers=64MB",
        "max_connections=48",
        "work_mem=4MB",
        "maintenance_work_mem=32MB",
        "listen_addresses=*",
    } == settings
    assert branch_plan.BRANCH_UNRECLAIMABLE_MB == 192
    assert _plan().hosts == (f"dev.pool.{DOMAIN}", f"dev.direct.{DOMAIN}")


def _replace_phase(
    plan: branch_plan.BranchPlan, phase: str, **changes: Any
) -> branch_plan.BranchPlan:
    return dataclasses.replace(
        plan, **{phase: dataclasses.replace(getattr(plan, phase), **changes)}
    )


def _unsafe(name: str) -> branch_plan.BranchPlan:
    plan = _plan()
    inherited = plan.inherited
    data = plan.persistent.mounts[0]
    if name == "persistent on the backup network":
        return _replace_phase(plan, "persistent", network=plan.parent_backup_network)
    if name == "persistent with the repository configuration":
        return _replace_phase(plan, "persistent", mounts=(data, *inherited))
    if name == "persistent with an /etc/pgbackrest mount":
        extra = restore_drill.Mount("/srv/other", "/etc/pgbackrest/conf.d/x.conf", True, "bind")
        return _replace_phase(plan, "persistent", mounts=(data, extra))
    if name == "persistent archiving":
        argv = tuple(
            "archive_mode=on" if p == "archive_mode=off" else p for p in plan.persistent.argv
        )
        return _replace_phase(plan, "persistent", argv=argv)
    if name == "persistent archiving through a second setting":
        return _replace_phase(
            plan, "persistent", argv=(*plan.persistent.argv, "-c", "archive_mode=always")
        )
    if name == "persistent with a real archive command":
        argv = tuple(
            f"archive_command=pgbackrest --stanza={STANZA} archive-push %p"
            if p == "archive_command=/bin/false"
            else p
            for p in plan.persistent.argv
        )
        return _replace_phase(plan, "persistent", argv=argv)
    if name == "persistent with a PGBACKREST variable":
        return _replace_phase(plan, "persistent", environment={"PGBACKREST_REPO1_CIPHER_PASS": "x"})
    if name == "recovery archiving":
        return _replace_phase(plan, "recovery", argv=("postgres",))
    if name == "restore with --delta":
        return _replace_phase(plan, "restore", argv=(*plan.restore.argv, "--delta"))
    if name == "a writable inherited mount":
        writable = (dataclasses.replace(inherited[0], readonly=False), *inherited[1:])
        return _replace_phase(plan, "restore", mounts=(plan.restore.mounts[0], *writable))
    if name == "the branch volume is the parent's":
        names = dataclasses.replace(plan.names, volume=PARENT_VOLUME)
        return dataclasses.replace(plan, names=names)
    if name == "a phase mounting the parent's volume":
        parent = restore_drill.Mount(PARENT_VOLUME, "/mnt/parent", True, "volume")
        return _replace_phase(plan, "recovery", mounts=(*plan.recovery.mounts, parent))
    raise AssertionError(name)


UNSAFE = (
    "persistent on the backup network",
    "persistent with the repository configuration",
    "persistent with an /etc/pgbackrest mount",
    "persistent archiving",
    "persistent archiving through a second setting",
    "persistent with a real archive command",
    "persistent with a PGBACKREST variable",
    "recovery archiving",
    "restore with --delta",
    "a writable inherited mount",
    "the branch volume is the parent's",
    "a phase mounting the parent's volume",
)


@pytest.mark.parametrize("name", UNSAFE)
def test_a_plan_that_could_write_the_parent_is_refused(name: str) -> None:
    """Each way of building rig 40a's control -- or of touching the parent's
    volume -- is refused by `assert_branch_safe` before anything starts (exit 7
    at the runtime). The correct plan is accepted in the same test (the control
    the mutation cannot reach): the guard refuses for the reason named, not
    for every plan.

    Goes red if: any one check is removed from `assert_branch_safe`."""
    branch_plan.assert_branch_safe(_plan())
    with pytest.raises(branch_plan.BranchSafetyError, match="Nothing is started"):
        branch_plan.assert_branch_safe(_unsafe(name))


def test_a_parent_without_backups_or_a_bad_branch_has_no_plan() -> None:
    """No repository, no branch; a name the rule refuses, no plan; a target
    without an offset is refused rather than read as the server's local time."""
    document = _document()
    document["backup"] = {"enabled": False, "stanza": STANZA}
    with pytest.raises(branch_plan.BranchPlanError, match="disabled"):
        branch_plan.build(
            document=document, inspect=_inspect(), contract=_contract(), branch="dev",
            target_time=None,
        )  # fmt: skip
    with pytest.raises(branch_plan.BranchPlanError):
        branch_plan.build(
            document=_document(), inspect=_inspect(), contract=_contract(), branch="main",
            target_time=None,
        )  # fmt: skip
    with pytest.raises(restore_drill.DrillError, match="no timezone"):
        _plan(target="2026-10-14 08:04:56")
