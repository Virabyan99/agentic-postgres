"""Reading the node's capacity off the machine (Session 31, ADR 0221).

The impure half of :mod:`agentic_postgres.capacity_reading`, which stays pure:
this module opens `/proc/meminfo`, stats a filesystem and shells out to
`docker`; that one parses, arranges and decides.

**Why this is in the library and not spelled three times in `bin/`.** Three
commands need the same reading -- `doctor capacity` reports it, `admit`
decides on it, and the deploy decides on it at step 0 -- and ADR 0093 bars a
`bin/` command from importing another, so the alternative was three copies of
the same six probes. Three copies is the shape question 5 of the handoff's §7
exists for: *when a decision is implemented, which of its callers got it?* A
repair to the ceiling parser that reached the doctor and not the deploy would
be invisible until a deploy admitted something the doctor had refused.

**What each command still owns is its `runner`**, and that is the part that
genuinely differs. Every command in `bin/` has a bounded `run()` with its own
timeout policy and its own rule about stdin, and those policies are not this
module's business -- so the runner arrives as an argument. A runner returns
``None`` when a command could not complete at all, which is how a timeout and
a non-zero exit stay different facts.

Nothing here decides anything. Every figure it cannot read comes back as a
:class:`~agentic_postgres.capacity_reading.Figure` carrying its reason, and
what to do about that is :func:`~agentic_postgres.capacity_reading.decide`'s
question (ADR 0195: a report may not fold the third outcome away; a decision
may fail closed).
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from agentic_postgres import capacity_reading, config, deployed_output, host_config
from agentic_postgres.capacity_reading import Figure, Reading

__all__ = ["PROJECT_ROOT_UNREADABLE", "Runner", "read", "read_deployed"]


#: The reading's stand-in key for *the project root itself could not be read*.
#: A slash cannot appear in a project key, so this can never be confused with a
#: real project whose document happens to be missing.
PROJECT_ROOT_UNREADABLE = "<project state root>"


class Runner(Protocol):
    """One bounded subprocess. ``None`` when it could not complete at all."""

    def __call__(self, *command: str, timeout: int = ...) -> Any | None: ...


def read_deployed(root: Path, key: str) -> tuple[dict[str, Any] | None, str | None]:
    """One deployed document, or the REASON it could not be read.

    Non-fatal by design, and that is the whole difference from the readers in
    `bin/` that raise. Those answer *diagnose THIS project*, where a missing
    document means the command was asked about something never deployed and
    should stop. This one answers *what has this node already committed*, where
    an unreadable document is one project's claim among several -- stopping
    would turn a partial answer into no answer, and returning nothing would
    turn it into a confident wrong one.

    **On the reference host this is the ordinary case, not the exceptional
    one**: `/etc/agentic-postgres/projects/<key>/` is `drwx------ root root`,
    so every document is unreadable to anyone but root (D1606). An
    unprivileged run therefore reports every project unreadable and `decide`
    refuses -- rather than summing zero and admitting everything.
    """
    import json

    path = deployed_output.deployed_path(key, root=root)
    try:
        deployed = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "no deployed document: the directory exists and outputs.json does not"
    except OSError:
        return None, "the deployed document could not be read"
    except ValueError:
        return None, "the deployed document is not valid JSON"
    try:
        deployed_output.validate_deployed_document(deployed)
    except config.ManifestError:
        return None, "the deployed document does not validate against the outputs schema"
    return deployed, None


def read_meminfo(path: Path = Path(capacity_reading.MEMINFO_PATH)) -> dict[str, int] | None:
    """The node's memory, read DIRECTLY and not through a container.

    A figure read inside a cgroup answers a different question: `mem_limit` is
    what that container may use, and this reading is about what the machine
    has. It is a file read rather than an exec into a container, which is why
    `container_exec` is not involved (D1593 draws that line).
    """
    try:
        return capacity_reading.parse_meminfo(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def read_docker_root(runner: Runner) -> str | None:
    """Where Docker keeps its data, asked rather than assumed.

    `/var/lib/docker` is the default and is not the contract. A host that had
    moved it would otherwise be measured at the wrong filesystem, and the
    number would look perfectly plausible.
    """
    answered = runner("docker", "info", "--format", "{{.DockerRootDir}}", timeout=20)
    if answered is None or answered.returncode != 0:
        return None
    return answered.stdout.strip() or None


def disk_usage_near(path: str) -> tuple[Any | None, str]:
    """The filesystem holding ``path``, measured from the deepest readable point.

    Returns ``(usage, measured_at)``; ``usage`` is ``None`` when nothing on the
    way up could be stat'd.

    **Why an ancestor is acceptable and a default would not be.** The question
    is *how much room is on the filesystem holding the Docker data root*, and
    `statvfs` answers it identically from any point on that filesystem. The
    Docker root itself is frequently unreadable for reasons that have nothing
    to do with capacity -- it does not exist at all under Docker Desktop, whose
    daemon reports a path inside its own VM, and it is 0710 root on a CI
    runner. A figure that was undeterminable in both of those places would
    refuse every admission, and a rule nothing can satisfy is not a rule.

    What is NOT done here is substitute a number. The path that was measured
    comes back with it and is printed, because if the Docker root were its own
    mount an ancestor would describe a different disk -- and then an operator
    should see the path rather than a plausible number. On the reference host
    `/var/lib/docker` and `/` are one `/dev/sda1` (rig 31b), and root can stat
    the exact path anyway.
    """
    candidate = Path(path)
    seen: list[Path] = []
    while True:
        seen.append(candidate)
        try:
            return shutil.disk_usage(candidate), str(candidate)
        except OSError:
            pass
        if candidate.parent == candidate:
            return None, ""
        candidate = candidate.parent


def read_ceilings(runner: Runner) -> tuple[dict[str, int], tuple[str, ...], str]:
    """Every Compose container's `mem_limit`, summed per COMPOSE PROJECT.

    Returns ``(by_compose_project, unbounded, reason)`` where ``reason`` is
    empty when the reading succeeded. The keys are compose project names;
    :func:`read` is what maps them back to project keys.

    The `docker ps` filter here has always been `com.docker.compose.project`.
    Until Session 32 the *grouping* in `ceilings_from_inspect` was
    `apg.project.key`, so this function selected the database and then threw it
    away (D1636). The two now agree, and agreeing is the repair.

    **These decide nothing**, which is why a failure here is a missing report
    line and not a refusal (ADR 0221). They are read at all because an operator
    staring at a refusal wants both numbers, and because the gap between them
    is this host's most misleading fact: the six caps sum to 2240 MiB per
    project against 3814 MiB of RAM, and that is survivable only because a cap
    is a ceiling and was never a reservation (D767).
    """
    from agentic_postgres import runtime_override

    label = runtime_override.COMPOSE_PROJECT_LABEL
    listing = runner("docker", "ps", "--filter", f"label={label}", "-q", timeout=20)
    if listing is None or listing.returncode != 0:
        return {}, (), "docker ps did not answer"
    ids = listing.stdout.split()
    if not ids:
        return {}, (), ""
    inspected = runner("docker", "inspect", *ids, timeout=30)
    if inspected is None or inspected.returncode != 0:
        return {}, (), "docker inspect did not answer"
    by_project, unbounded = capacity_reading.ceilings_from_inspect(inspected.stdout)
    return by_project, unbounded, ""


def _ceilings_by_project_key(by_compose_project: dict[str, int], keys: list[str]) -> dict[str, int]:
    """Compose project names translated back to project keys, where one is known.

    **Derived through `naming.compose_project_name`, not read from a document**
    (D1673), and that is not a second derivation under ADR 0002 -- that function
    IS the authority and says so (`naming.py:711-714`). The obvious alternative,
    matching a document's published `compose.project_name`, **cannot work
    here**: only the RENDERED document publishes a `compose` block, and this
    reader walks the DEPLOYED documents under
    `/etc/agentic-postgres/projects/<key>/` (`naming.py:704-708`,
    `postgres_volume_name`'s docstring, D592). A mapping written that way would
    have printed `apg-alpha-dev` on production and never fired.

    `keys` is what :func:`read` could actually list. A compose project this
    node runs but whose directory could not be read keeps its compose name --
    reported as what it is, rather than mapped to a key that was never
    established (ADR 0195).
    """
    from agentic_postgres import naming

    translated = {naming.compose_project_name(key): key for key in keys}
    return {translated.get(name, name): total for name, total in by_compose_project.items()}


def read(
    host_manifest: Path,
    root: Path,
    *,
    runner: Runner,
    exclude: str | None = None,
    declared_override: Callable[[host_config.Declared | None], host_config.Declared | None]
    | None = None,
) -> tuple[Reading, str]:
    """The whole reading. Returns ``(reading, ceilings_reason)``.

    `ceilings_reason` is carried separately because it is the one figure whose
    failure is a report line rather than an input to any rule -- keeping it out
    of `Reading.unreadable` is what stops a missing `docker inspect` from
    refusing a deploy that would otherwise be fine.

    `Reading.ceilings` is keyed by PROJECT KEY for every project whose
    directory this call could list, and by COMPOSE PROJECT NAME for anything
    else on the node (D1636, D1673).

    `declared_override` exists for a rehearsal (ADR 0190): a threshold is moved
    rather than a host filled. The caller is responsible for marking an
    injected figure as injected in what it prints, so that a rehearsal's
    reading can never be mistaken for the host's.
    """
    declared = host_config.declared_capacity(host_config.load_host_manifest(host_manifest))
    if declared_override is not None:
        declared = declared_override(declared)

    memory = read_meminfo()
    if memory is None:
        why = (
            "/proc/meminfo could not be read, or did not carry all three of "
            "MemTotal, MemAvailable and SwapTotal"
        )
        mem_total = Figure.unknown(why)
        mem_available = Figure.unknown(why)
        swap_total = Figure.unknown(why)
    else:
        mem_total = Figure.measured(memory["MemTotal"])
        mem_available = Figure.measured(memory["MemAvailable"])
        swap_total = Figure.measured(memory["SwapTotal"])

    docker_root = read_docker_root(runner)
    measured_at = ""
    if docker_root is None:
        why = "`docker info` did not report a data root"
        free_gb = Figure.unknown(why)
        total_gb = Figure.unknown(why)
    else:
        usage, measured_at = disk_usage_near(docker_root)
        if usage is None:
            why = (
                f"neither {docker_root} nor any ancestor of it could be stat'd, so the "
                "filesystem holding it could not be measured"
            )
            free_gb = Figure.unknown(why)
            total_gb = Figure.unknown(why)
        else:
            free_gb = Figure.measured(usage.free // (1024**3))
            total_gb = Figure.measured(usage.total // (1024**3))

    documents: dict[str, Any] = {}
    unreadable: dict[str, str] = {}
    try:
        keys = sorted(path.name for path in root.iterdir() if path.is_dir())
    except OSError as problem:
        # NOT an empty list. A root this command cannot list is a set of claims
        # it does not know, and reporting that as `0 MiB committed` would hand
        # `decide` the whole declared budget on the strength of a directory it
        # failed to open.
        unreadable[PROJECT_ROOT_UNREADABLE] = (
            f"the project state root could not be listed: {problem.strerror}"
        )
        keys = []

    for key in keys:
        deployed, why = read_deployed(root, key)
        if deployed is None:
            unreadable[key] = why or "the deployed document could not be read"
            continue
        documents[key] = deployed

    committed, missing_member = capacity_reading.committed_from_documents(
        documents, exclude=exclude
    )
    unreadable.update(missing_member)
    # The candidate's own document is never a reason to refuse the candidate.
    unreadable.pop(exclude, None)

    ceilings, unbounded, ceilings_reason = read_ceilings(runner)
    ceilings = _ceilings_by_project_key(ceilings, keys)

    reading = Reading(
        declared=declared,
        mem_total=mem_total,
        mem_available=mem_available,
        swap_total=swap_total,
        docker_root_free_gb=free_gb,
        docker_root_total_gb=total_gb,
        committed=committed,
        unreadable=unreadable,
        ceilings=ceilings,
        unbounded=unbounded,
        docker_root_measured_at=measured_at,
    )
    return reading, ceilings_reason
