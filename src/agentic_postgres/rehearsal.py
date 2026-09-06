"""Bounded failure rehearsals: induce, observe, reverse (ADR 0190, ADR 0193).

`OPS-REHEARSE-001`..`008`. Each scenario is a plan of three phases over facts
the command read off the deployment up front -- the containers by label, the
registry path, the mirror's endpoint and the backup network's subnet, the lock
on disk -- and this module decides what each phase runs, what each observation
reads, and what a set of readings proves. `bin/rehearse.py` executes plans and
holds every subprocess; nothing here runs one.

**A rehearsal is of a reader.** The failure is bounded and reversible, and what
is proved is that the detection that exists names it: the restart count and
the doctor's containers and route checks for a killed service, the doctor's
`database` check and the agent route's boundary for a restarted cluster,
`check`'s exit for a wrong credential (the same reader a deploy's step 6c
uses), the mirror verb's exit for a blocked mirror path (the unit's failure)
with the archiver check as the control that the primary never felt it, every
`database-ports.sh` verb's refusal for a lost registry, `disk_headroom` with an
injected threshold, and the doctor's drift check against a foreign lock.

**Three things were measured before this was written** (rig 4, D1015):

* Docker does not restart a container after `docker kill`, under any restart
  policy -- the daemon records a manual stop and cancels the restart manager
  (exit 137, restart count 0). A SIGKILL to the container's main process from
  the host's PID namespace is an unexpected exit, and `on-failure:5` restarts
  it within two seconds. `kill -9 1` from inside the container's own
  namespace is ignored by the kernel. So service termination sends the signal
  to the process, and the plan says why.
* A REJECT rule in `DOCKER-USER` selected by the backup network's subnet and
  the mirror endpoint's address blocks that network and no other, and is
  removed by its comment; `iptables -S` lists it in the form `-D` accepts.
* The service whose route the doctor reads is `edge-probe`, which serves the
  reserved health route (ADR 0015); killing PostgREST would leave every doctor
  check green. The killed service is the one the reader covers.

**Two things a rehearsal does not do.** The disk is never filled: the threshold
is injected into the doctor and the reading says so. Archiving to the primary
is never blocked: the WAL scenario blocks the MIRROR's path, whose loss the
archiver does not feel (ADR 0188), and reads the archiver check as its control.

Nothing here reads a file, runs a process, resolves a name or reads a clock.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from agentic_postgres import naming

__all__ = [
    "BOUNDS",
    "COMMENT_PREFIX",
    "DEPLOYED_DOCTOR_CHECKS",
    "HEALTH_SERVICE",
    "PROVIDER_LOSS_RECORD",
    "SCENARIOS",
    "STATE_FILENAME",
    "Action",
    "Facts",
    "Observation",
    "Plan",
    "RehearsalError",
    "doctor_check",
    "doctor_worst",
    "foreign_lock",
    "inspect_state",
    "iptables_delete_arguments",
    "plan",
    "record",
    "render_plan",
    "rule_comment",
    "state_document",
    "throwaway_credential",
    "verdict",
]

SCENARIOS = (
    "service-termination",
    "database-restart",
    "backup-credential-failure",
    "wal-archiving-failure",
    "registry-loss",
    "disk-threshold",
    "capability-drift",
    "provider-loss",
)

#: The stateless service whose route the doctor reads (ADR 0015: `edge-probe`
#: serves the reserved health route). The one service a termination rehearsal
#: kills, because it is the one the reader covers (ADR 0193).
HEALTH_SERVICE = "edge-probe"
DATABASE_SERVICE = "postgres"

#: The doctor's check names this module reads. Spelled once, from
#: `diagnosis`'s own vocabulary; a misspelling here would read nothing and
#: report it, which is the failure `verdict` exists to refuse.
DEPLOYED_DOCTOR_CHECKS = {
    "containers": "containers",
    "health": "route health",
    "database": "database",
    "archiver": "wal archiver",
    "mirror": "backup mirror",
    "disk": "disk headroom",
    "drift": "capability drift",
}

#: Seconds a scenario waits for its reader, chosen and named so they can be
#: revised: a restarted edge-probe is back in seconds; a restarted cluster and
#: its dependents reconnect within a minute on the measured host; a mirror
#: copy against a rejected endpoint fails as fast as the client gives up.
BOUNDS = {
    "service-termination": 120,
    "database-restart": 300,
    "wal-archiving-failure": 900,
}

#: The one file that says a rehearsal is un-reversed. Beside the projects'
#: state directory, persisted rather than under `/run`, so a rehearsal a
#: reboot interrupted is still refused and still reversible.
STATE_FILENAME = "rehearsal-in-progress.json"
COMMENT_PREFIX = "apg-rehearsal-"

#: Provider loss is recorded, never induced (ADR 0190, D990): D976 measured
#: it on Session 17's trip, and a rehearsal of it would repeat a measurement.
PROVIDER_LOSS_RECORD = (
    "D976 (Session 17 Run 7, the production host): the first authenticated Infisical "
    "read after a login took 8.9 s on one project and answered 504 after 60 s on "
    "another. A deploy against a slow or absent provider fails at step 5 "
    "(materialize) and touches nothing running; the client retries idempotent calls "
    "three times. Nothing running depends on the provider between deploys."
)

#: The values the thresholds are injected at. Larger than any headroom a host
#: has, so the reading is the threshold's and not the disk's.
INJECTED_WARN_COPIES = 1.0e9
INJECTED_PROBLEM_COPIES = 1.0e9
INJECTED_WARN_ABOVE_PROBLEM = 2.0e9


class RehearsalError(Exception):
    """The plan cannot be built for these facts. The message names why."""


@dataclass(frozen=True)
class Facts:
    """What the command read before planning; every value the plan needs.

    Optional members are absent when the deployment has no such thing (no
    mirror, no lock), and the scenario that needs one refuses rather than
    planning around it.
    """

    project_key: str
    rehearsal_id: str
    outputs_path: str
    doctor_argv: tuple[str, ...]
    backup_sh: str
    database_ports_sh: str
    containers: dict[str, str] = field(default_factory=dict)
    container_pids: dict[str, int] = field(default_factory=dict)
    restart_counts: dict[str, int] = field(default_factory=dict)
    health_url: str | None = None
    mcp_url: str | None = None
    stanza: str | None = None
    bucket: str | None = None
    endpoint: str | None = None
    mirror_enabled: bool = False
    mirror_endpoint: str | None = None
    mirror_bucket: str | None = None
    mirror_addresses: tuple[str, ...] = ()
    backup_subnet: str | None = None
    registry_path: str | None = None
    registry_present: bool = False
    registry_sha256: str | None = None
    instance_uuid: str | None = None
    lock_path: str | None = None
    lock_present: bool = False
    lock_recorded: bool = False
    foreign_lock_path: str | None = None

    @property
    def compose_project(self) -> str:
        return naming.compose_project_name(self.project_key)

    @property
    def backup_network(self) -> str:
        return naming.backup_network_name(self.project_key)

    @property
    def registry_aside_path(self) -> str | None:
        if self.registry_path is None:
            return None
        return f"{self.registry_path}.{COMMENT_PREFIX}{self.rehearsal_id}"


@dataclass(frozen=True)
class Action:
    """One thing a phase does. `run` executes ``argv``; the file kinds move,
    write or remove one path; `none` is a statement the plan prints."""

    what: str
    kind: str = "none"
    argv: tuple[str, ...] = ()
    source: str | None = None
    target: str | None = None
    content: str | None = None
    #: A fallback runs only when the condition it names was not met.
    conditional: str | None = None

    def as_document(self) -> dict[str, Any]:
        return {
            "what": self.what,
            "kind": self.kind,
            "argv": list(self.argv),
            "source": self.source,
            "target": self.target,
            "conditional": self.conditional,
        }


@dataclass(frozen=True)
class Observation:
    """One reading: what runs, which reader it is, and what a healthy
    rehearsal expects it to say."""

    name: str
    what: str
    argv: tuple[str, ...] = ()
    expect: str = ""
    control: bool = False
    #: Polled until the condition named holds or the bound is reached.
    until: str | None = None


@dataclass(frozen=True)
class Plan:
    scenario: str
    reader: str
    induce: tuple[Action, ...]
    observe: tuple[Observation, ...]
    reverse: tuple[Action, ...]
    verify: tuple[str, ...]
    bound_seconds: int = 0
    induced: bool = True


def rule_comment(rehearsal_id: str) -> str:
    return f"{COMMENT_PREFIX}{rehearsal_id}"


def throwaway_credential(rehearsal_id: str) -> str:
    """A value that authenticates to nothing. Not a secret and named so: it
    exists in one exec's environment and nowhere else."""
    return f"{COMMENT_PREFIX}{rehearsal_id}-not-a-credential"


def _doctor(facts: Facts, *extra: str) -> tuple[str, ...]:
    return (*facts.doctor_argv, "--project", facts.project_key, "--json", *extra)


# ---------------------------------------------------------------------------
# The plans
# ---------------------------------------------------------------------------


def plan(scenario: str, facts: Facts) -> Plan:
    if scenario not in SCENARIOS:
        raise RehearsalError(f"unknown scenario {scenario!r}; one of {', '.join(SCENARIOS)}")
    return _PLANNERS[scenario](facts)


def _service_termination(facts: Facts) -> Plan:
    container = facts.containers.get(HEALTH_SERVICE)
    if not container:
        raise RehearsalError(
            f"{facts.project_key} has no running {HEALTH_SERVICE} container; the service "
            "whose route the doctor reads is not there to terminate"
        )
    pid = facts.container_pids.get(HEALTH_SERVICE)
    if not pid:
        raise RehearsalError(f"{container} has no main process id; it is not running")
    if not facts.health_url:
        raise RehearsalError("the deployed document publishes no health route to read")
    doctor = _doctor(facts)
    return Plan(
        scenario="service-termination",
        reader=(
            "the restart count and the health route, and the doctor's containers and "
            "route health checks at the moment after the kill"
        ),
        induce=(
            Action(
                what=(
                    f"SIGKILL to {container}'s main process (host pid {pid}) from the host's "
                    "PID namespace. Not `docker kill`: the daemon records that as a manual "
                    "stop and no restart policy restarts it (rig 4, D1015)"
                ),
                kind="run",
                argv=("kill", "-KILL", str(pid)),
            ),
        ),
        observe=(
            Observation(
                name="state_after_kill",
                what=f"{container}'s state and restart count immediately after",
                argv=("docker", "inspect", "-f", "{{.State.Running}} {{.RestartCount}}", container),
                expect="not running, or already restarted once",
            ),
            Observation(
                name="doctor_at_kill",
                what="the doctor's containers and route health checks immediately after",
                argv=doctor,
                expect="the gap, if the doctor ran before the restart policy closed it",
            ),
            Observation(
                name="restarted",
                what=f"{container} running with its restart count incremented",
                argv=("docker", "inspect", "-f", "{{.State.Running}} {{.RestartCount}}", container),
                expect="running, restart count incremented, within the bound",
                until="running-and-restarted",
            ),
            Observation(
                name="route_ready",
                what="the health route answering 200 again",
                argv=(
                    "curl",
                    "-ksS",
                    "-o",
                    "/dev/null",
                    "-w",
                    "%{http_code}",
                    "--max-time",
                    "10",
                    facts.health_url,
                ),
                expect="200 within the bound",
                until="http-200",
            ),
            Observation(
                name="doctor_after",
                what="the doctor's containers and route health checks after",
                argv=doctor,
                expect="both ok",
            ),
        ),
        reverse=(
            Action(what="the restart policy (on-failure:5) is the reversal; nothing to undo"),
            Action(
                what=f"docker start {container}, only if the policy did not bring it back",
                kind="run",
                argv=("docker", "start", container),
                conditional="restarted",
            ),
        ),
        verify=(f"{container} is running",),
        bound_seconds=BOUNDS["service-termination"],
    )


def _database_restart(facts: Facts) -> Plan:
    container = facts.containers.get(DATABASE_SERVICE)
    if not container:
        raise RehearsalError(f"{facts.project_key} has no running database container")
    doctor = _doctor(facts)
    observe: list[Observation] = [
        Observation(
            name="doctor_recovered",
            what="the doctor's database, containers and route health checks",
            argv=doctor,
            expect="every check ok within the bound",
            until="doctor-ok",
        ),
        Observation(
            name="dependents_not_restarted",
            what="the restart count of every dependent container",
            argv=(
                "docker",
                "ps",
                "-a",
                "--filter",
                f"label=com.docker.compose.project={facts.compose_project}",
                "--format",
                "{{.Names}}",
            ),
            expect="unchanged: every dependent reconnected without a restart or a redeploy",
        ),
    ]
    if facts.mcp_url:
        observe.append(
            Observation(
                name="agent_route",
                what="an anonymous request to the agent route after the restart",
                argv=(
                    "curl",
                    "-ksS",
                    "-o",
                    "/dev/null",
                    "-w",
                    "%{http_code}",
                    "--max-time",
                    "10",
                    "-X",
                    "POST",
                    facts.mcp_url,
                ),
                expect="401: the plane answers at its boundary (ADR 0115)",
            )
        )
    return Plan(
        scenario="database-restart",
        reader="the doctor's database, containers and route checks; the agent route's boundary",
        induce=(
            Action(
                what=f"docker restart -t 30 {container}",
                kind="run",
                argv=("docker", "restart", "-t", "30", container),
            ),
        ),
        observe=tuple(observe),
        reverse=(Action(what="the restart is its own reversal; nothing to undo"),),
        verify=(f"{container} is running",),
        bound_seconds=BOUNDS["database-restart"],
    )


def _backup_credential_failure(facts: Facts) -> Plan:
    container = facts.containers.get(DATABASE_SERVICE)
    if not container or not facts.stanza:
        raise RehearsalError(
            f"{facts.project_key} has no running database container or no backup stanza"
        )
    wrong = throwaway_credential(facts.rehearsal_id)
    check = ("pgbackrest", f"--stanza={facts.stanza}", "check")
    return Plan(
        scenario="backup-credential-failure",
        reader="`check`'s exit, the reader a deploy's step 6c fails on",
        induce=(
            Action(
                what=(
                    "nothing is changed: the wrong credential exists in one exec's "
                    "environment, where it overrides the mounted include (D1009), and nowhere "
                    "else"
                ),
            ),
        ),
        observe=(
            Observation(
                name="check_with_wrong_credential",
                what=(
                    f"pgbackrest check for {facts.stanza} with a credential that "
                    "authenticates to nothing"
                ),
                argv=(
                    "docker",
                    "exec",
                    "-u",
                    "999",
                    "-e",
                    f"PGBACKREST_REPO1_S3_KEY={wrong}",
                    "-e",
                    f"PGBACKREST_REPO1_S3_KEY_SECRET={wrong}",
                    container,
                    *check,
                ),
                expect=(
                    f"non-zero: the repository {facts.bucket} at {facts.endpoint} refused "
                    "the credential and the check failed closed"
                ),
            ),
            Observation(
                name="check_with_deployed_credential",
                what=f"pgbackrest check for {facts.stanza} with the deployed credential",
                argv=("docker", "exec", "-u", "999", container, *check),
                expect="0: the repository is healthy and the failure above was the credential's",
                control=True,
            ),
        ),
        reverse=(Action(what="nothing was changed; nothing to undo"),),
        verify=(),
    )


def _wal_archiving_failure(facts: Facts) -> Plan:
    if not facts.mirror_enabled or not facts.mirror_endpoint:
        raise RehearsalError(
            f"{facts.project_key} declares no backup mirror; there is no mirror path to "
            "block, and the primary's path is never blocked (ADR 0188, ADR 0190)"
        )
    if not facts.mirror_addresses:
        raise RehearsalError(f"{facts.mirror_endpoint} resolved to no IPv4 address")
    if not facts.backup_subnet:
        raise RehearsalError(
            f"the backup network {facts.backup_network} has no subnet to select on"
        )
    comment = rule_comment(facts.rehearsal_id)
    doctor = _doctor(facts)
    mirror = (facts.backup_sh, "--outputs", facts.outputs_path, "mirror")
    induce = tuple(
        Action(
            what=f"REJECT {facts.backup_subnet} -> {address}:443 in DOCKER-USER, tagged {comment}",
            kind="run",
            argv=(
                "iptables",
                "-I",
                "DOCKER-USER",
                "-s",
                facts.backup_subnet,
                "-d",
                address,
                "-p",
                "tcp",
                "--dport",
                "443",
                "-j",
                "REJECT",
                "--reject-with",
                "tcp-reset",
                "-m",
                "comment",
                "--comment",
                comment,
            ),
        )
        for address in facts.mirror_addresses
    )
    return Plan(
        scenario="wal-archiving-failure",
        reader=(
            "the mirror verb's exit (the unit's failure) and the doctor's mirror check; the "
            "doctor's archiver check is the control that the primary never felt it"
        ),
        induce=induce,
        observe=(
            Observation(
                name="doctor_before",
                what="the doctor's archiver and mirror checks under the block, before a copy",
                argv=doctor,
                expect="archiver ok: the primary's path is untouched",
                control=True,
            ),
            Observation(
                name="mirror_copy_blocked",
                what=f"the mirror copy of {facts.project_key} to {facts.mirror_bucket}",
                argv=mirror,
                expect="non-zero: the copy cannot reach the mirror endpoint",
            ),
            Observation(
                name="doctor_under_block",
                what="the doctor's archiver and mirror checks after the failed copy",
                argv=doctor,
                expect=(
                    "archiver ok; the mirror check reports the last completed copy's record, "
                    "which a failed copy does not write (D1016)"
                ),
                control=True,
            ),
        ),
        reverse=(
            Action(
                what=f"every DOCKER-USER rule tagged {comment} deleted",
                kind="run",
                argv=("iptables", "-S", "DOCKER-USER"),
            ),
            Action(
                what="the next copy, which completes what the blocked pass left behind (D1001)",
                kind="run",
                argv=mirror,
            ),
            Action(what="the doctor's mirror check after the copy", kind="run", argv=doctor),
        ),
        verify=(
            f"no DOCKER-USER rule tagged {comment} remains",
            "the copy after the reversal exited 0",
        ),
        bound_seconds=BOUNDS["wal-archiving-failure"],
    )


def _registry_loss(facts: Facts) -> Plan:
    if not facts.registry_path or not facts.registry_present:
        raise RehearsalError(
            f"no port registry at {facts.registry_path}; there is nothing to lose. An absent "
            "registry is a loss already, or a host provisioning never finished: "
            "provision-host.sh --apply creates it, and nothing else may (ADR 0190)"
        )
    if not facts.instance_uuid:
        raise RehearsalError(
            "the deployed document records no instance_uuid to ask the verbs about"
        )
    aside = facts.registry_aside_path
    assert aside is not None
    ports = facts.database_ports_sh
    return Plan(
        scenario="registry-loss",
        reader="every database-ports.sh verb's refusal (exit 4), and the registry left absent",
        induce=(
            Action(
                what=f"{facts.registry_path} renamed to {aside} (same directory, atomic)",
                kind="rename",
                source=facts.registry_path,
                target=aside,
            ),
        ),
        observe=(
            Observation(
                name="show_refused",
                what="database-ports.sh show",
                argv=(ports, "show", "--registry", facts.registry_path),
                expect="exit 4 naming the absent registry; nothing recreated",
            ),
            Observation(
                name="release_refused",
                what="database-ports.sh release --plan for this project's identity",
                argv=(
                    ports,
                    "release",
                    "--registry",
                    facts.registry_path,
                    "--project-key",
                    facts.project_key,
                    "--instance-uuid",
                    facts.instance_uuid,
                    "--plan",
                ),
                expect="exit 4 naming the absent registry; nothing recreated",
            ),
        ),
        reverse=(
            Action(
                what=f"{aside} renamed back to {facts.registry_path}",
                kind="rename",
                source=aside,
                target=facts.registry_path,
            ),
            Action(
                what="database-ports.sh show reads it again",
                kind="run",
                argv=(ports, "show", "--registry", facts.registry_path),
            ),
        ),
        verify=(
            f"{facts.registry_path} present with sha256 {facts.registry_sha256}",
            "database-ports.sh show exits 0",
        ),
    )


def _disk_threshold(facts: Facts) -> Plan:
    return Plan(
        scenario="disk-threshold",
        reader="the doctor's disk headroom check, with the threshold injected",
        induce=(
            Action(
                what=(
                    "nothing is changed and no disk is filled (ADR 0190): the thresholds "
                    "are injected into the doctor with --disk-warn-copies and "
                    "--disk-problem-copies"
                ),
            ),
        ),
        observe=(
            Observation(
                name="disk_default",
                what="disk headroom at the deployed thresholds",
                argv=_doctor(facts),
                expect="the host's own reading, whatever it is",
                control=True,
            ),
            Observation(
                name="disk_warn",
                what=f"disk headroom with warn injected at {INJECTED_WARN_COPIES:g} copies",
                argv=_doctor(facts, "--disk-warn-copies", f"{INJECTED_WARN_COPIES:g}"),
                expect="warn",
            ),
            Observation(
                name="disk_problem",
                what=f"disk headroom with problem injected at {INJECTED_PROBLEM_COPIES:g} copies",
                argv=_doctor(
                    facts,
                    "--disk-warn-copies",
                    f"{INJECTED_WARN_ABOVE_PROBLEM:g}",
                    "--disk-problem-copies",
                    f"{INJECTED_PROBLEM_COPIES:g}",
                ),
                expect="problem",
            ),
        ),
        reverse=(Action(what="nothing was changed; nothing to undo"),),
        verify=(),
    )


def _capability_drift(facts: Facts) -> Plan:
    if not facts.lock_recorded or not facts.lock_path or not facts.lock_present:
        raise RehearsalError(
            f"{facts.project_key} records no capability lock, or none is on disk at "
            f"{facts.lock_path}; there is no deployed lock to drift from"
        )
    foreign = facts.foreign_lock_path
    assert foreign is not None
    return Plan(
        scenario="capability-drift",
        reader="the doctor's capability drift check against a lock with a foreign hash",
        induce=(
            Action(
                what=(
                    f"a lock with a foreign hash written beside the deployed document at "
                    f"{foreign}; the deployed lock at {facts.lock_path} is not touched"
                ),
                kind="write",
                target=foreign,
            ),
        ),
        observe=(
            Observation(
                name="drift_foreign",
                what="the doctor's drift check reading the foreign lock",
                argv=_doctor(facts, "--lock-file", foreign),
                expect="problem: the lock's hash is not the one the deployed document recorded",
            ),
            Observation(
                name="drift_deployed",
                what="the doctor's drift check reading the deployed lock",
                argv=_doctor(facts),
                expect="ok",
                control=True,
            ),
        ),
        reverse=(Action(what=f"{foreign} removed", kind="remove", target=foreign),),
        verify=(f"{foreign} absent", f"{facts.lock_path} unchanged"),
    )


def _provider_loss(facts: Facts) -> Plan:
    return Plan(
        scenario="provider-loss",
        reader="recorded, not induced: the deploy's step 5 against a slow provider (D976)",
        induce=(Action(what="nothing: provider loss is recorded, never induced (ADR 0190, D990)"),),
        observe=(
            Observation(
                name="record",
                what="the measurement on file",
                expect=PROVIDER_LOSS_RECORD,
            ),
        ),
        reverse=(Action(what="nothing was changed; nothing to undo"),),
        verify=(),
        induced=False,
    )


_PLANNERS = {
    "service-termination": _service_termination,
    "database-restart": _database_restart,
    "backup-credential-failure": _backup_credential_failure,
    "wal-archiving-failure": _wal_archiving_failure,
    "registry-loss": _registry_loss,
    "disk-threshold": _disk_threshold,
    "capability-drift": _capability_drift,
    "provider-loss": _provider_loss,
}


# ---------------------------------------------------------------------------
# Rendering and the readings
# ---------------------------------------------------------------------------


def render_plan(plan: Plan, facts: Facts) -> str:
    """The three phases as `--plan` prints them. Every argv is the one the
    rehearsal would run; a value here is one the command read or derived."""
    lines = [
        f"rehearsal {facts.rehearsal_id}: {plan.scenario} on {facts.project_key}",
        f"  reader   {plan.reader}",
    ]
    if plan.bound_seconds:
        lines.append(f"  bound    {plan.bound_seconds}s")
    lines.append("  induce")
    lines.extend(_render_action(action) for action in plan.induce)
    lines.append("  observe")
    for observation in plan.observe:
        label = "control" if observation.control else "reading"
        lines.append(f"    {label:<8} {observation.what}")
        if observation.argv:
            lines.append(f"             $ {' '.join(observation.argv)}")
        lines.append(f"             expects: {observation.expect}")
    lines.append("  reverse")
    lines.extend(_render_action(action) for action in plan.reverse)
    if plan.verify:
        lines.append("  verify")
        lines.extend(f"    {item}" for item in plan.verify)
    if not plan.induced:
        lines.append("  (recorded, not induced: running this scenario changes nothing)")
    return "\n".join(lines)


def _render_action(action: Action) -> str:
    text = f"    - {action.what}"
    if action.conditional:
        text += f"  [only if not {action.conditional}]"
    if action.kind == "run":
        text += f"\n      $ {' '.join(action.argv)}"
    elif action.kind == "rename":
        text += f"\n      mv {action.source} {action.target}"
    elif action.kind == "write":
        text += f"\n      write {action.target}"
    elif action.kind == "remove":
        text += f"\n      rm {action.target}"
    return text


def doctor_check(document_text: str, check: str) -> str | None:
    """One check's verdict out of `doctor --json`'s output, or None when the
    document does not carry it -- which `verdict` counts as unread."""
    try:
        report = json.loads(document_text)
    except ValueError:
        return None
    for entry in report.get("checks") or []:
        if entry.get("name") == check:
            return str(entry.get("verdict"))
    return None


def doctor_worst(document_text: str) -> str | None:
    try:
        report = json.loads(document_text)
    except ValueError:
        return None
    worst = report.get("worst")
    return str(worst) if worst is not None else None


def inspect_state(text: str) -> tuple[bool | None, int | None]:
    """`docker inspect -f '{{.State.Running}} {{.RestartCount}}'`, parsed."""
    parts = text.split()
    if len(parts) != 2:
        return None, None
    running = {"true": True, "false": False}.get(parts[0].lower())
    try:
        count = int(parts[1])
    except ValueError:
        return running, None
    return running, count


def iptables_delete_arguments(listing: str, comment: str) -> tuple[tuple[str, ...], ...]:
    """The `-D` argument vectors for every rule `iptables -S DOCKER-USER`
    lists with ``comment``, in the form the listing itself uses (measured:
    `-S` prints `-A CHAIN <spec>` and `-D CHAIN <spec>` deletes it)."""
    rules = []
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[0] != "-A" or parts[1] != "DOCKER-USER":
            continue
        try:
            marker = parts.index("--comment")
        except ValueError:
            continue
        if marker + 1 < len(parts) and parts[marker + 1] == comment:
            rules.append(("iptables", "-D", *parts[1:]))
    return tuple(rules)


def foreign_lock(lock_text: str, rehearsal_id: str) -> str:
    """The deployed lock's document with one member added, so its bytes hash
    differently and it is still lock-shaped. Never written over the deployed
    lock; the caller writes it beside the deployed document."""
    lock = json.loads(lock_text)
    if not isinstance(lock, dict):
        raise RehearsalError("the deployed lock is not a JSON object")
    lock = {**lock, "rehearsal": rehearsal_id}
    return json.dumps(lock, indent=2, sort_keys=True) + "\n"


def _doctor_ok(checks: Any) -> bool:
    """Every named check the observer recorded read `ok`; an empty or absent
    reading is not ok, because nothing was read."""
    return isinstance(checks, dict) and bool(checks) and all(v == "ok" for v in checks.values())


def verdict(scenario: str, readings: dict[str, Any]) -> tuple[str, str]:
    """What the readings prove: ``read`` when the reader named the failure
    and the reversal restored the reading, ``unread`` otherwise, with why.

    A reader that read nothing is not a passed rehearsal (ADR 0190); it is a
    finding, and the reason is the sentence a divergence row starts from.
    """
    if scenario == "provider-loss":
        return "recorded", "provider loss is recorded, not induced (D976)"
    if scenario == "service-termination":
        if not readings.get("restarted"):
            return "unread", "the service did not come back within the bound"
        if readings.get("route_status_after") != 200:
            return "unread", "the health route did not answer 200 within the bound"
        if not _doctor_ok(readings.get("doctor_after")):
            return "unread", "the doctor did not report ok after the restart"
        return "read", (
            f"restarted in {readings.get('seconds_to_ready')}s; the doctor "
            f"{'reported' if readings.get('gap_reported') else 'did not see'} the gap at T+0"
        )
    if scenario == "database-restart":
        if not _doctor_ok(readings.get("doctor_after")):
            return "unread", "the doctor did not report ok within the bound"
        if readings.get("dependents_restarted"):
            return "unread", f"dependents restarted: {readings['dependents_restarted']}"
        if "agent_route_status" in readings and readings["agent_route_status"] != 401:
            return "unread", f"the agent route answered {readings['agent_route_status']}, not 401"
        return "read", f"every dependent reconnected in {readings.get('seconds_to_ok')}s"
    if scenario == "backup-credential-failure":
        if readings.get("wrong_credential_exit") == 0:
            return "unread", "check passed with a credential that authenticates to nothing"
        if readings.get("deployed_credential_exit") != 0:
            return "unread", "the control failed: check does not pass with the deployed credential"
        return "read", (
            f"check failed closed (exit {readings.get('wrong_credential_exit')}) and passed "
            "with the deployed credential"
        )
    if scenario == "wal-archiving-failure":
        if readings.get("blocked_copy_exit") == 0:
            return "unread", "the mirror copy succeeded under the block"
        if readings.get("archiver_before") != "ok" or readings.get("archiver_under_block") != "ok":
            return "unread", "the control failed: the archiver check was not ok throughout"
        if readings.get("copy_after_reversal_exit") != 0:
            return "unread", "the copy after the reversal did not complete"
        return "read", (
            f"the blocked copy exited {readings.get('blocked_copy_exit')}; the archiver stayed "
            f"ok; the mirror check read {readings.get('mirror_under_block')} under the block "
            f"and {readings.get('mirror_after')} after the copy"
        )
    if scenario == "registry-loss":
        for name in ("show", "release"):
            if readings.get(f"{name}_exit") != 4:
                return "unread", f"{name} exited {readings.get(f'{name}_exit')}, not 4"
            if readings.get(f"registry_present_after_{name}"):
                return "unread", f"{name} recreated the registry"
        return "read", "both verbs refused with exit 4 and neither recreated the registry"
    if scenario == "disk-threshold":
        if readings.get("disk_warn") != "warn":
            return "unread", f"warn injected, doctor read {readings.get('disk_warn')}"
        if readings.get("disk_problem") != "problem":
            return "unread", f"problem injected, doctor read {readings.get('disk_problem')}"
        return (
            "read",
            "warn and problem at the injected thresholds; deployed reading "
            f"{readings.get('disk_default')}",
        )
    if scenario == "capability-drift":
        if readings.get("drift_foreign") != "problem":
            return "unread", f"a foreign lock read {readings.get('drift_foreign')}, not problem"
        if readings.get("drift_deployed") != "ok":
            return (
                "unread",
                f"the control failed: the deployed lock read {readings.get('drift_deployed')}",
            )
        return "read", "the foreign lock is a problem and the deployed lock is ok"
    raise RehearsalError(f"no verdict for {scenario!r}")


def state_document(plan: Plan, facts: Facts, *, started_at: str) -> dict[str, Any]:
    """What the in-progress file holds: enough for `reverse` to replay the
    reversal after a crash, and for a second scenario to be refused by name."""
    return {
        "scenario": plan.scenario,
        "project_key": facts.project_key,
        "rehearsal_id": facts.rehearsal_id,
        "started_at": started_at,
        "outputs_path": facts.outputs_path,
        "reverse": [action.as_document() for action in plan.reverse],
        "registry_sha256": facts.registry_sha256,
    }


def record(
    plan: Plan,
    facts: Facts,
    *,
    started_at: str,
    finished_at: str,
    readings: dict[str, Any],
    reversed_: bool,
    verification: dict[str, Any],
) -> dict[str, Any]:
    """The evidence document: the plan as printed, every reading, whether the
    reversal verified, and what the readings prove."""
    outcome, why = verdict(plan.scenario, readings)
    return {
        "document_kind": "rehearsal",
        "scenario": plan.scenario,
        "project_key": facts.project_key,
        "rehearsal_id": facts.rehearsal_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "induced": plan.induced,
        "reader": plan.reader,
        "bound_seconds": plan.bound_seconds,
        "plan": render_plan(plan, facts),
        "readings": readings,
        "reversed": reversed_,
        "verification": verification,
        "verdict": outcome,
        "why": why,
    }
