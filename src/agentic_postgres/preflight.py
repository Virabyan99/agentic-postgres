"""What a deploy checks before it changes anything, and how it says it did not look.

`DEP-PRE-001` asks for two things that sound like one: a deploy must stop *before
it changes anything*, and it must list *every* absent item. The first is a
question of where the check runs; the second is a question of what a check is
allowed to return.

**Three verdicts, not two** (ADR 0157). The four things worth checking are not
independent — the edge check is a question you ask the Docker daemon — so a list
of booleans has no way to distinguish *"the edge plane is not running"* from
*"nobody could ask"*. It would print the first when it meant the second, which is
D600's family: a value that looks measured and is not. `UNDETERMINED` is the
verdict that makes the distinction expressible, and it blocks a deploy exactly as
an absence does, because a prerequisite nobody verified is not one to proceed on.

**The parsing lives here and the subprocesses live in `bin/deploy-project.py`**,
which is `database_observation`'s split and for its reason: that file needs root,
so every existing test of it is a source-level text scan. A pure module is
testable behaviourally, and its mutants can be killed.

Nothing here reads a file, runs a process or touches the network. Every function
takes what was observed and returns what to say about it.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ABSENT",
    "DAEMON_TIMEOUT_SECONDS",
    "KIND_PRECONDITION",
    "KIND_PREREQUISITE",
    "PRESENT",
    "UNDETERMINED",
    "Prerequisite",
    "blocking",
    "docker_daemon",
    "edge_plane",
    "exit_kind",
    "provider_bootstrap",
    "report",
    "secret_generation",
]

PRESENT = "present"
ABSENT = "absent"
UNDETERMINED = "undetermined"

#: A tool or daemon this machine needs (deploy.sh exit 3).
KIND_PREREQUISITE = "prerequisite"
#: A command that must have been run first (deploy.sh exit 4).
KIND_PRECONDITION = "precondition"

#: Seconds to wait for the Docker daemon before giving up on it (D631).
#:
#: `deploy-project.run()` passes no `timeout=`, and refusal is not the failure
#: mode that matters: measured in Run 1, a missing socket, a closed port and an
#: unroutable address all fail in **≤0.03s**, while a listener that ACCEPTS the
#: connection and never answers left `docker ps` running past **20s**. A healthy
#: daemon answered in 0.12s, so ten seconds is two orders of magnitude of slack
#: over the only timing ever observed, and still bounded.
DAEMON_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class Prerequisite:
    """One checked thing, what was seen, and what supplies it.

    ``remedy`` is None for an `UNDETERMINED` item on purpose: the fix is whatever
    it depended on, and printing a command beside a check that never ran would
    invite an operator to act on a diagnosis nobody made.
    """

    name: str
    kind: str
    verdict: str
    detail: str
    remedy: str | None = None

    @property
    def blocks(self) -> bool:
        return self.verdict != PRESENT


def docker_daemon(*, reachable: bool, timed_out: bool, error: str = "") -> Prerequisite:
    """The daemon, from one `docker ps`.

    A timeout is `UNDETERMINED` and a refusal is `ABSENT`, and the difference is
    not cosmetic: a daemon that accepted the connection is very likely running,
    and telling its operator to start it is the wrong instruction. One is "it
    isn't there", the other is "it isn't answering".
    """
    if timed_out:
        return Prerequisite(
            name="docker daemon",
            kind=KIND_PREREQUISITE,
            verdict=UNDETERMINED,
            detail=(
                f"accepted a connection but did not answer within "
                f"{DAEMON_TIMEOUT_SECONDS}s; it may be running and wedged"
            ),
            remedy=None,
        )
    if not reachable:
        return Prerequisite(
            name="docker daemon",
            kind=KIND_PREREQUISITE,
            verdict=ABSENT,
            detail=_one_line(error) or "could not be reached",
            remedy="systemctl start docker",
        )
    return Prerequisite(
        name="docker daemon",
        kind=KIND_PREREQUISITE,
        verdict=PRESENT,
        detail="reachable",
    )


def edge_plane(
    *,
    daemon: Prerequisite,
    running_names: tuple[str, ...],
    stack_name: str,
    host_manifest: str,
) -> Prerequisite:
    """The edge plane, from the container names the daemon reported.

    **Undetermined whenever the daemon is not present**, and that is the whole
    reason this module has three verdicts. `running_names` would be empty in that
    case for a reason that has nothing to do with the edge, and reporting an
    absence from it would be asserting something nobody measured.
    """
    if daemon.verdict != PRESENT:
        return Prerequisite(
            name="edge plane",
            kind=KIND_PRECONDITION,
            verdict=UNDETERMINED,
            detail=f"not checked: the Docker daemon is {daemon.verdict}",
            remedy=None,
        )
    if not any(name.startswith(stack_name) for name in running_names):
        return Prerequisite(
            name="edge plane",
            kind=KIND_PRECONDITION,
            verdict=ABSENT,
            detail=f"no running container is named {stack_name}*",
            remedy=f"sudo bin/edge.sh --host {host_manifest} up",
        )
    return Prerequisite(
        name="edge plane",
        kind=KIND_PRECONDITION,
        verdict=PRESENT,
        detail=f"{stack_name}* is running",
    )


def provider_bootstrap(
    *,
    error: str,
    state_path: str,
    host_manifest: str,
    project_manifest: str,
    readable: bool = True,
) -> Prerequisite:
    """The provider bootstrap, from an attempt to load and validate its state.

    ``error`` is empty when the load succeeded. A filesystem read needs nothing
    from the daemon, so it is determinable even when the daemon is down — which
    is exactly why it is worth reporting then.

    ``readable=False`` is the other case, and it is **not** an absence (D636).
    `Path.exists()` swallows `ENOENT` and **raises** `EACCES`, so a state file
    under a directory this process cannot traverse is a file nobody looked at.
    Reporting "run the bootstrap" for one that exists and is merely unreadable
    would send an operator to re-provision a provider identity that is already
    there.
    """
    if not readable:
        return Prerequisite(
            name="provider bootstrap",
            kind=KIND_PRECONDITION,
            verdict=UNDETERMINED,
            detail=f"not checked: {_one_line(error)}",
            remedy=None,
        )
    if error:
        return Prerequisite(
            name="provider bootstrap",
            kind=KIND_PRECONDITION,
            verdict=ABSENT,
            detail=_one_line(error),
            remedy=(
                f"sudo bin/bootstrap-providers.sh --host {host_manifest} "
                f"--project {project_manifest} --apply"
            ),
        )
    return Prerequisite(
        name="provider bootstrap",
        kind=KIND_PRECONDITION,
        verdict=PRESENT,
        detail=state_path,
    )


def secret_generation(
    *,
    error: str,
    generation_id: str,
    project_manifest: str,
    session: int,
    readable: bool = True,
) -> Prerequisite:
    """The active secret generation and the manifest that describes it.

    Both, or neither — `require_secret_generation`'s rule, restated here rather
    than re-derived: a pointer naming a generation whose manifest is missing
    describes a directory nothing can account for. The caller decides which of
    the two failed and hands the sentence in.

    ``readable=False`` carries D636's case, exactly as `provider_bootstrap` does:
    the secret root is `0700 root`, so an unprivileged caller gets `EACCES` and
    not `ENOENT`, and the honest verdict is that nobody looked.
    """
    if not readable:
        return Prerequisite(
            name="secret generation",
            kind=KIND_PRECONDITION,
            verdict=UNDETERMINED,
            detail=f"not checked: {_one_line(error)}",
            remedy=None,
        )
    if error:
        return Prerequisite(
            name="secret generation",
            kind=KIND_PRECONDITION,
            verdict=ABSENT,
            detail=_one_line(error),
            remedy=(
                f"sudo bin/materialize-secrets.sh --project {project_manifest} --session {session}"
            ),
        )
    return Prerequisite(
        name="secret generation",
        kind=KIND_PRECONDITION,
        verdict=PRESENT,
        detail=f"generation {generation_id}",
    )


def blocking(items: tuple[Prerequisite, ...]) -> tuple[Prerequisite, ...]:
    """Everything that is not `PRESENT`, in the order it was checked."""
    return tuple(item for item in items if item.blocks)


def exit_kind(items: tuple[Prerequisite, ...]) -> str | None:
    """The kind of the FIRST blocking item, or None if nothing blocks.

    The caller maps this to its own exit constant. Deliberately the first rather
    than the most severe: the items are ordered as the deploy needs them, so the
    first blocker is the one whose absence explains the rest — and mapping it
    reproduces the exit code each cause produces today, which is what lets this
    aggregate be added without moving any caller's contract (ADR 0157).
    """
    first = blocking(items)
    return first[0].kind if first else None


def report(items: tuple[Prerequisite, ...]) -> str:
    """The whole table, printed on refusal and on success alike.

    Printed on success too, so that a deploy log records what was true when it
    began rather than only when it failed.
    """
    stopped = blocking(items)
    if stopped:
        headline = (
            f"{len(stopped)} of {len(items)} prerequisites are not satisfied. "
            "Nothing has been changed."
        )
    else:
        headline = f"all {len(items)} prerequisites are satisfied."

    lines = [headline, ""]
    for item in items:
        label = {PRESENT: "ok", ABSENT: "MISSING", UNDETERMINED: "UNKNOWN"}[item.verdict]
        lines.append(f"  {label:<9} {item.name} — {item.detail}")
        if item.remedy:
            lines.append(f"  {'':<9} supply it with: {item.remedy}")
    return "\n".join(lines)


def _one_line(text: str) -> str:
    """Collapse a message to one line and bound it.

    A daemon's stderr and a validation error both arrive multi-line, and a report
    whose rows wrap is one an operator stops reading.
    """
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= 200 else collapsed[:197] + "..."
