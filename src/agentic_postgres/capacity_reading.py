"""The node as a finite resource: what it has, what is claimed, what fits.

Session 31, ADR 0221. Pure: nothing here runs a subprocess, opens a socket or
touches the host. ``bin/doctor.py`` does the reading and hands the results in;
this module parses, arranges and decides.

**The two halves of ADR 0195 are the whole design of this module, and they
pull in opposite directions.**

*A report may not fold a third outcome away.* Every measured figure is a
:class:`Figure`, which is either a number or ``None`` **with a reason**. There
is no default, no zero, and no "assume it is fine". ``doctor capacity`` prints
what it read and names what it could not, and it has exactly two verdicts --
``OK`` with every figure, or ``UNKNOWN`` naming the one it missed. It never
returns ``WARN`` or ``PROBLEM``, because a threshold in the one command that
runs as root on production could fail a host that works (D1441, ADR 0213).

*A decision may fail closed.* :func:`decide` is not a report. When a figure it
needs is ``None`` it **refuses**, naming the figure. The asymmetry is the
point: the reading tells an operator the truth about what it knows, and the
decision declines to act on what it does not.

**What admission charges.** Not the sum of the services' ``mem_limit``s --
those are ceilings, sum to 2240 MiB per project against a 3814 MiB host, and
were never a reservation (D767); a rule built on them refuses the deployment
that is running today. It charges ``database.budget.unreclaimable_mb``, the
figure the schema computes and the document publishes as *what the host must
actually find*. The ceilings are still read and still printed -- labelled as
ceilings -- because an operator looking at a refusal wants both numbers.

**Disk is a floor, not a sum** (D1596). No per-project disk claim exists
anywhere, and a candidate's PGDATA is unknowable before it runs, so inventing
a number for it would be a value that looked measured and was not (D267). What
an operator *can* state is how much free space a new project may not eat into.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from agentic_postgres.host_config import Declared

__all__ = [
    "EXIT_ADMISSION_REFUSED",
    "MEMINFO_PATH",
    "SUGGESTED_ACTION_DISK",
    "SUGGESTED_ACTION_MEMORY",
    "USAGE_FIGURE_UNITS",
    "Decision",
    "Figure",
    "Reading",
    "UsageFigures",
    "ceilings_from_inspect",
    "committed_from_documents",
    "decide",
    "parse_meminfo",
    "render_decision",
]

#: Read directly rather than through a container: the question is about the
#: node, and a figure read inside a cgroup would answer a different one.
MEMINFO_PATH = "/proc/meminfo"

#: Admission refused -- the declared capacity cannot hold this project.
#:
#: Twelfth in the one convention table (`docs/session-02-operator-guide.md`).
#: It is deliberately neither 4 nor 6: a refusal is not a precondition the
#: operator can go and create (4), and it is not a check that failed (6). It is
#: a decision taken against a declaration, and an operator reading ``$?`` has
#: to be able to tell the three apart (D1585).
EXIT_ADMISSION_REFUSED = 12

#: The three manifest fields that move `unreclaimable_mb`, named in the order
#: they are worth trying. `work_mem_mb` is deliberately absent: it is per sort,
#: not per backend, and does not enter the figure.
SUGGESTED_ACTION_MEMORY = (
    "lower database.shared_buffers_mb, database.maintenance_work_mem_mb or "
    "database.max_connections in this project's manifest; or retire a project "
    "from this host; or raise capacity.memory_mb in host.yaml only after "
    "`apg doctor capacity` shows the host actually has it"
)

SUGGESTED_ACTION_DISK = (
    "free space at the Docker root, or lower capacity.reserve_disk_gb in "
    "host.yaml only after deciding how little headroom this node may run on"
)


@dataclasses.dataclass(frozen=True, slots=True)
class Figure:
    """One measured number, or the reason there isn't one.

    ``value is None`` and an empty ``reason`` is not constructible through
    :meth:`unknown` and would be a bug: a figure that is absent for no stated
    reason is exactly the ``null`` that looks measured (D600).
    """

    value: int | None
    reason: str = ""

    @classmethod
    def measured(cls, value: int) -> Figure:
        return cls(value=value, reason="")

    @classmethod
    def unknown(cls, reason: str) -> Figure:
        if not reason:
            raise ValueError("an unknown figure must carry a reason")
        return cls(value=None, reason=reason)

    @property
    def known(self) -> bool:
        return self.value is not None


@dataclasses.dataclass(frozen=True, slots=True)
class Reading:
    """Everything the capacity reading found, measured and declared.

    ``committed`` and ``unreadable`` are the two halves of the same question:
    which projects' claims could be summed, and which could not. A project in
    ``unreadable`` is **never** counted as zero -- that is the whole reason the
    two are separate members rather than one dict with missing keys.
    """

    declared: Declared | None
    mem_total: Figure
    mem_available: Figure
    swap_total: Figure
    docker_root_free_gb: Figure
    docker_root_total_gb: Figure
    committed: dict[str, int]
    unreadable: dict[str, str]
    ceilings: dict[str, int]
    unbounded: tuple[str, ...] = ()
    #: Which path the disk figures were actually read from.
    #:
    #: Normally the Docker data root itself. When that path cannot be stat'd
    #: -- it does not exist under Docker Desktop, and it is 0710 root on a CI
    #: runner -- the nearest ancestor that can be is measured instead, and
    #: this says so. The same filesystem in every case measured so far, and
    #: where it is not, an operator reads the path rather than a number that
    #: quietly describes a different disk.
    docker_root_measured_at: str = ""

    @property
    def committed_total_mb(self) -> int:
        return sum(self.committed.values())


@dataclasses.dataclass(frozen=True, slots=True)
class Decision:
    """Admitted or refused, with the lines an operator reads either way.

    ``lines`` is ordered and is the same shape in both outcomes, because an
    operator comparing a refusal with a later admission should be comparing
    two of the same thing rather than reading two different reports.
    """

    outcome: str
    lines: tuple[tuple[str, str], ...]
    reason: str

    @property
    def refused(self) -> bool:
        return self.outcome == "refused"

    @property
    def exit_code(self) -> int:
        return EXIT_ADMISSION_REFUSED if self.refused else 0


#: What each usage figure is counted in, for the renderer. A figure whose unit
#: lived only in its name would be a number an operator has to guess about.
USAGE_FIGURE_UNITS: dict[str, str] = {
    "database_bytes": "bytes",
    "pgdata_kb": "KiB",
    "wal_kb": "KiB",
    "repository_bytes": "bytes",
    "audit_rows": "rows",
    "idempotency_rows": "rows",
    "requests_total": "requests",
    "tool_calls_total": "calls",
}


@dataclasses.dataclass(frozen=True, slots=True)
class UsageFigures:
    """How much of this node one project is actually using.

    Eight figures, each a :class:`Figure` -- a number or the reason there is
    none. **Not `storage_objects`** (D1601): the object listing is reachable
    only through the credential the storage container alone holds, and a second
    holder of that credential is this stage's declared failure mode. A member
    reported `unknown` forever would be a field with no reader (D816), so it is
    absent rather than permanently unanswerable.

    **Nothing here is thresholded.** These are sizes and counts; nobody has
    measured a value at which this deployment is unwell, and `doctor` runs as
    root on production (D1441, ADR 0213). What the reading owes is the numbers,
    or the reason it could not read one.
    """

    database_bytes: Figure
    pgdata_kb: Figure
    wal_kb: Figure
    repository_bytes: Figure
    audit_rows: Figure
    idempotency_rows: Figure
    requests_total: Figure
    tool_calls_total: Figure

    def as_mapping(self) -> dict[str, Figure]:
        """Ordered, because the report prints them in this order."""
        return {name: getattr(self, name) for name in USAGE_FIGURE_UNITS}


def parse_meminfo(text: str) -> dict[str, int] | None:
    """MemTotal, MemAvailable and SwapTotal in MiB, or ``None``.

    ``None`` when **any** of the three is missing, and the caller turns that
    into three unknown figures with one reason. Returning a dict with a missing
    key filled in as zero is the mutation this module's battery kills: a host
    reporting zero available memory and a host whose ``/proc/meminfo`` this
    program failed to parse are opposite situations, and only one of them is an
    emergency.

    ``SwapTotal`` is here because on a no-swap box it is the fact that makes
    every other number final -- there is nothing below the reserve to give, and
    the OOM killer is the only backstop, and it does not choose politely.

    Values in ``/proc/meminfo`` are in kB (which the kernel means as KiB), and
    the conversion floors: a capacity figure that rounded up would claim memory
    the host does not have.
    """
    wanted = {"MemTotal", "MemAvailable", "SwapTotal"}
    found: dict[str, int] = {}
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        if name not in wanted:
            continue
        parts = rest.split()
        if len(parts) != 2 or parts[1] != "kB" or not parts[0].isdigit():
            continue
        found[name] = int(parts[0]) // 1024
    if wanted - set(found):
        return None
    return found


def committed_from_documents(
    documents: dict[str, dict[str, Any]], *, exclude: str | None
) -> tuple[dict[str, int], dict[str, str]]:
    """What every OTHER deployed project has already claimed, in MiB.

    Returns ``(committed, unreadable)``. A document that does not carry
    ``database.budget.unreclaimable_mb`` lands in ``unreadable`` with a reason
    and is **not** counted as zero -- a project whose claim this program cannot
    read is a project whose claim it does not know, and summing it as nothing
    would admit a candidate that does not fit (D600's shape in arithmetic).

    ``exclude`` is the candidate's own key, and excluding it is what makes a
    redeploy the same decision as a new project: the candidate's *new* claim is
    charged against the others, so raising ``shared_buffers_mb`` on an existing
    project is decided exactly the way adding a third one is (D1592). Charging
    it twice -- once from its old document and once as the request -- would
    refuse redeployments that fit.
    """
    committed: dict[str, int] = {}
    unreadable: dict[str, str] = {}
    for key, document in sorted(documents.items()):
        if key == exclude:
            continue
        budget = document.get("database", {}).get("budget")
        if not isinstance(budget, dict):
            unreadable[key] = "the deployed document carries no database.budget"
            continue
        claimed = budget.get("unreclaimable_mb")
        if not isinstance(claimed, int):
            unreadable[key] = "database.budget.unreclaimable_mb is absent or not an integer"
            continue
        committed[key] = claimed
    return committed, unreadable


def ceilings_from_inspect(payload: str) -> tuple[dict[str, int], tuple[str, ...]]:
    """Sum each project's container memory CEILINGS from `docker inspect`.

    Returns ``(by_project_mib, unbounded_container_names)``.

    These decide nothing. They are reported because an operator reading a
    refusal wants to see both numbers, and because the gap between them is the
    single most misleading thing about this host: the six caps sum to 2240 MiB
    per project against 3814 MiB of RAM, which is only survivable because a cap
    is a ceiling and not a reservation (D767).

    A container with ``HostConfig.Memory`` of 0 is **unbounded**, and is listed
    by name rather than added as zero -- adding it as zero would make an
    unbounded container look like a free one, which is the opposite of true.
    """
    try:
        containers = json.loads(payload)
    except ValueError:
        return {}, ()
    if not isinstance(containers, list):
        return {}, ()

    by_project: dict[str, int] = {}
    unbounded: list[str] = []
    for container in containers:
        if not isinstance(container, dict):
            continue
        labels = container.get("Config", {}).get("Labels") or {}
        key = labels.get("apg.project.key")
        if not key:
            continue
        limit = container.get("HostConfig", {}).get("Memory")
        name = str(container.get("Name", "")).lstrip("/")
        if not isinstance(limit, int) or limit <= 0:
            unbounded.append(name)
            continue
        by_project[key] = by_project.get(key, 0) + limit // (1024 * 1024)
    return by_project, tuple(sorted(unbounded))


def decide(
    reading: Reading,
    *,
    candidate_key: str,
    candidate_unreclaimable_mb: int,
    candidate_is_deployed: bool,
) -> Decision:
    """Does this project fit on this node?

    **This is a decision and it fails closed.** Every rule below that needs a
    figure it does not have refuses and names the figure. That is the half of
    ADR 0195 a decision is allowed -- and is the opposite of what the reading
    beside it does with the same missing figure.

    With nothing declared, a candidate that has **never been deployed here is
    refused** and a redeploy is **admitted** (D1584). That asymmetry is what
    lets this release ship as a minor: no operator has to edit `host.yaml`
    before upgrading, and nothing that runs today stops running. It is also
    honest -- with no declaration there is no basis on which to admit anything
    new, and a redeploy is already on the host whatever this function says.
    """
    lines: list[tuple[str, str]] = []

    if reading.declared is None:
        lines.append(("declared", "nothing; host.yaml is schema 2"))
        lines.append(("candidate", candidate_key))
        lines.append(
            ("deployed here", "yes" if candidate_is_deployed else "no (this would be the first)")
        )
        if candidate_is_deployed:
            return Decision(
                outcome="admitted",
                lines=tuple(lines),
                reason=(
                    "no capacity is declared, and this project is already deployed here: "
                    "a redeploy is admitted because refusing it would stop something that "
                    "is already running"
                ),
            )
        return Decision(
            outcome="refused",
            lines=tuple(lines),
            reason=(
                "no capacity is declared in host.yaml and this project has never been "
                "deployed here. Move host.yaml to schema_version 3 and declare capacity "
                "(see host.example.yaml), then run this again"
            ),
        )

    declared = reading.declared

    if reading.unreadable:
        named = ", ".join(f"{key} ({why})" for key, why in sorted(reading.unreadable.items()))
        lines.append(("committed", f"undetermined: {named}"))
        return Decision(
            outcome="refused",
            lines=tuple(lines),
            reason=(
                "what other projects have already claimed could not be determined, so "
                f"whether this one fits cannot be decided: {named}"
            ),
        )

    committed = reading.committed_total_mb
    safe_available = declared.memory_mb - declared.reserve_memory_mb - committed

    lines.extend(
        (
            ("declared memory", f"{declared.memory_mb} MiB"),
            ("reserved", f"{declared.reserve_memory_mb} MiB"),
            (
                "committed",
                f"{committed} MiB across {len(reading.committed)} project(s): "
                + (", ".join(f"{k} {v}" for k, v in sorted(reading.committed.items())) or "none"),
            ),
            ("requested", f"{candidate_unreclaimable_mb} MiB for {candidate_key}"),
            ("safe available", f"{safe_available} MiB"),
        )
    )

    if candidate_unreclaimable_mb > safe_available:
        lines.append(("suggested action", SUGGESTED_ACTION_MEMORY))
        return Decision(
            outcome="refused",
            lines=tuple(lines),
            reason=(
                f"{candidate_key} claims {candidate_unreclaimable_mb} MiB of unreclaimable "
                f"memory and only {safe_available} MiB is safely available on this node"
            ),
        )

    free = reading.docker_root_free_gb
    lines.append(("declared disk", f"{declared.disk_gb} GiB"))
    if reading.docker_root_measured_at:
        lines.append(("disk measured at", reading.docker_root_measured_at))
    lines.append(("reserved disk", f"{declared.reserve_disk_gb} GiB"))
    if not free.known:
        lines.append(("free disk", f"undetermined: {free.reason}"))
        lines.append(("suggested action", SUGGESTED_ACTION_DISK))
        return Decision(
            outcome="refused",
            lines=tuple(lines),
            reason=(
                "free space at the Docker root could not be determined, so whether this "
                f"project fits cannot be decided: {free.reason}"
            ),
        )

    assert free.value is not None
    disk_headroom = free.value - declared.reserve_disk_gb
    lines.append(("free disk", f"{free.value} GiB"))
    lines.append(
        (
            "requested disk",
            "n/a -- no per-project disk claim exists (D1596); the reserve is a floor",
        )
    )
    lines.append(("safe available disk", f"{disk_headroom} GiB above the reserve"))

    if disk_headroom < 0:
        lines.append(("suggested action", SUGGESTED_ACTION_DISK))
        return Decision(
            outcome="refused",
            lines=tuple(lines),
            reason=(
                f"the Docker root has {free.value} GiB free and the declared reserve is "
                f"{declared.reserve_disk_gb} GiB, so a new project would eat into it"
            ),
        )

    lines.append(("suggested action", "none; deploy"))
    return Decision(
        outcome="admitted",
        lines=tuple(lines),
        reason=(
            f"{candidate_key} claims {candidate_unreclaimable_mb} MiB against "
            f"{safe_available} MiB safely available, and the Docker root has "
            f"{disk_headroom} GiB above its reserve"
        ),
    )


def render_decision(decision: Decision) -> str:
    """The text `bin/admit.py` and the deploy both print.

    One renderer, because a refusal an operator sees during a deploy and the
    same refusal from `apg admit` being worded differently is how two commands
    come to disagree about what happened.
    """
    width = max((len(label) for label, _ in decision.lines), default=0)
    body = "\n".join(f"  {label.ljust(width)}  {value}" for label, value in decision.lines)
    return f"admission: {decision.outcome}\n{body}\n\n{decision.reason}\n"
