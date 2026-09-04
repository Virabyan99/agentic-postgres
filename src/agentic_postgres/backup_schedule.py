"""What `backup.sh schedule` may say and may do (`FLEET-BACKUP-001`, D944).

The decisions live here and the systemd calls live in `bin/backup.py`, which is
`diagnosis`'s split: the command needs root and a host, so what can be
reasoned about is put where it can be exercised.

**Two timers per project, and a project is scheduled only when both are
enabled.** The vocabulary is `fleet`'s, measured on the host (D962): a unit
file that was never installed answers `not-found` and is `absent`; one nobody
enabled is `disabled`; and the repairs differ -- `absent` needs
`provision-host.sh --apply`, which is the only thing that installs unit files,
and `disabled` needs `enable`.

**`enable` refuses twice before it enables.** It refuses while either unit
file is absent, naming the provisioning command, because `systemctl enable`
on an instance of an uninstalled template fails with a message about the
template rather than about the deployment. And it refuses while the
repository holds no full backup, because the first full backup of a project
is an operator's command by decision (`bin/backup.sh`'s own header): it is the
first operation that writes a meaningful amount to a repository nobody has
paid for yet, and a timer that took it would take it at 02:00 on Sunday with
nobody watching.

Nothing here reads a file, runs a process, reads a clock or touches the network.
"""

from __future__ import annotations

import json

from agentic_postgres import backup_report, fleet

__all__ = [
    "PROVISION_HINT",
    "enable_refusal",
    "render_status",
    "status_document",
    "units",
]

#: What repairs an absent unit file. Named in the refusal so the operator is
#: sent to the command that installs units rather than to `systemctl`.
PROVISION_HINT = "sudo bin/provision-host.sh --host host.yaml --apply"


def units(key: str) -> dict[str, str]:
    """The two timer instances for one project, by kind, derived once."""
    return {kind: fleet.timer_unit(kind, key) for kind in fleet.TIMER_KINDS}


def enable_refusal(
    states: dict[str, str], *, repository_status: str | None, last_full_backup_at: str | None
) -> str | None:
    """Why the timers may not be enabled yet, or None.

    ``states`` maps a kind to a `fleet` unit state; ``repository_status`` is
    `backup_report`'s vocabulary and ``last_full_backup_at`` its timestamp, both
    from `info`'s summary. Absent units are refused before the repository is
    consulted: the first refusal names the repair for the second state anyway.
    """
    absent = sorted(kind for kind in fleet.TIMER_KINDS if states.get(kind) == fleet.ABSENT)
    if absent:
        return (
            f"the {' and '.join(absent)} timer unit file(s) are not installed on this host; "
            f"install the units first: {PROVISION_HINT}"
        )
    unknown = sorted(
        kind for kind in fleet.TIMER_KINDS if states.get(kind, fleet.UNKNOWN) == fleet.UNKNOWN
    )
    if unknown:
        return (
            f"systemd did not answer for the {' and '.join(unknown)} timer(s); nothing was enabled"
        )
    if repository_status != backup_report.STATUS_READY or not last_full_backup_at:
        return (
            f"the repository reports {repository_status or 'nothing'} and holds no full backup; "
            "take the first one by hand first: sudo bin/backup.sh --outputs <outputs.json> "
            "backup --type full"
        )
    return None


def status_document(key: str, states: dict[str, str]) -> dict[str, object]:
    """The status as a document: the key, each timer's state, and the fold."""
    return {
        "project_key": key,
        "timers": {kind: states.get(kind, fleet.UNKNOWN) for kind in fleet.TIMER_KINDS},
        "units": units(key),
        "schedule": fleet.schedule(states),
    }


def render_status(key: str, states: dict[str, str]) -> str:
    document = status_document(key, states)
    lines = [f"backup: {key} is {document['schedule']}"]
    for kind in fleet.TIMER_KINDS:
        lines.append(f"  {kind:<5} {document['timers'][kind]:<9} {document['units'][kind]}")
    if document["schedule"] == fleet.UNSCHEDULED:
        if fleet.ABSENT in document["timers"].values():
            lines.append(f"  the unit files are not installed: {PROVISION_HINT}")
        else:
            lines.append(
                "  enable with: sudo bin/backup.sh --outputs <outputs.json> schedule enable"
            )
    return "\n".join(lines)


def render_json(key: str, states: dict[str, str]) -> str:
    return json.dumps(status_document(key, states), indent=2, sort_keys=True)
