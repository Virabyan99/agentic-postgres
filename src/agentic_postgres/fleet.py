"""The fleet inventory: every deployed project on one host, as rows (ADR 0185).

`FLEET-INV-001`, `FLEET-INV-002`. The composition lives here and the reading
lives in `bin/fleet.py`, which is `diagnosis`'s split and `preflight`'s: that
command needs root and a host, so nothing in it is testable behaviourally.

**What a row is made of, and where each part comes from:**

* identity and release -- the deployed document, which `naming` derived and
  the deploy published. Nothing here re-derives a name (ADR 0002).
* health -- `bin/doctor.py --json`'s document, composed rather than parsed
  (D947): its `worst`, its counts, and each check's verdict. **Never the
  deployed document's status blocks**, which record a moment that has passed
  (ADR 0158).
* backups -- the two timers' unit-file state on the host and the age of the
  last full backup **as the doctor's repository probe read it live**. Never
  `backup_state.status`, which said `ready` for a project whose newest full
  backup was a week old and whose timers had never been installed (D944).
* denials -- counts by `denial_reason` over a window, from the audit table.
  Counts and not a rate: the taxonomy (ADR 0178) is the operator's question,
  and the alert plane has already decided a refusal is not an alarm (D948).

**Every value is printed under its own project's key**, in both renderings,
because a fleet view is the first place two projects' values sit on one
screen, and a prefix over a key admits another project (Session 14's lesson).

**A project whose document cannot be read is a row saying so, not an
exception that hides the other rows.** An inventory that stopped at the first
broken project would report nothing about the ones that are fine.

Nothing here reads a file, runs a process, reads a clock or touches the network.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from agentic_postgres import diagnosis

__all__ = [
    "ABSENT",
    "DISABLED",
    "ENABLED",
    "SCHEDULED",
    "TIMER_KINDS",
    "UNKNOWN",
    "UNSCHEDULED",
    "Row",
    "age_days",
    "invalid_row",
    "last_full_backup_at",
    "render_json",
    "render_text",
    "row",
    "schedule",
    "timer_unit",
    "unit_state",
]

#: The two backup timers a project has, by the kind of backup each takes.
TIMER_KINDS = ("full", "incr")

#: A unit file's state as this module classifies `systemctl is-enabled`'s
#: answer. Measured on the host on 2026-09-04 (D962): an instance of a template
#: that is **not installed** answers `not-found` and exits 4; an instance of an
#: installed template that nobody enabled answers `disabled` and exits 1; an
#: enabled instance answers `enabled` and exits 0. `absent` is D944's state and
#: is kept apart from `disabled` because the repairs differ -- one is
#: `provision-host.sh --apply`, the other is `enable`.
ENABLED = "enabled"
DISABLED = "disabled"
ABSENT = "absent"
UNKNOWN = "unknown"

#: A project's schedule, from its two timers. `scheduled` needs both.
SCHEDULED = "scheduled"
UNSCHEDULED = "unscheduled"

#: The doctor check whose evidence carries the live last-full-backup time.
_REPOSITORY_CHECK = "backup repository"
_LAST_FULL = "last_full_backup_at"


def timer_unit(kind: str, key: str) -> str:
    """`agentic-postgres-backup-<kind>@<key>.timer` -- the instance name of the
    template unit `systemd/agentic-postgres-backup-<kind>@.timer`. Derived
    here once; `bin/backup.sh schedule` (Run 5) and the inventory both read it."""
    if kind not in TIMER_KINDS:
        raise ValueError(f"unknown timer kind {kind!r}; expected one of {TIMER_KINDS}")
    return f"agentic-postgres-backup-{kind}@{key}.timer"


def unit_state(returncode: int | None, stdout: str) -> str:
    """Classify one `systemctl is-enabled` answer (D962).

    ``returncode is None`` means the command could not run at all -- no
    `systemctl`, a timeout -- which is UNKNOWN and never a synonym for absent.
    """
    answer = (stdout or "").strip()
    if returncode is None:
        return UNKNOWN
    if answer == "not-found":
        return ABSENT
    if returncode == 0 and answer in {"enabled", "enabled-runtime", "static", "indirect"}:
        return ENABLED
    if answer == "disabled":
        return DISABLED
    return UNKNOWN


def schedule(states: dict[str, str]) -> str:
    """A project is `scheduled` only when both timers are enabled. An unknown
    timer makes the schedule unknown rather than unscheduled: not measured is
    not the same as measured absent (ADR 0158)."""
    values = [states.get(kind, UNKNOWN) for kind in TIMER_KINDS]
    if all(value == ENABLED for value in values):
        return SCHEDULED
    if any(value == UNKNOWN for value in values):
        return UNKNOWN
    return UNSCHEDULED


def last_full_backup_at(doctor: dict[str, object] | None) -> str | None:
    """The live reading, out of the doctor's repository check. None when the
    check is missing or the doctor could not query the repository -- and the
    module's own `"null"` rendering of an unmeasured value is None here too."""
    if not doctor:
        return None
    for check in doctor.get("checks") or []:  # type: ignore[union-attr]
        if isinstance(check, dict) and check.get("name") == _REPOSITORY_CHECK:
            value = (check.get("evidence") or {}).get(_LAST_FULL)
            if value in (None, "null", "None", ""):
                return None
            return str(value)
    return None


def age_days(timestamp: str | None, now: datetime) -> int | None:
    """Whole days between an RFC 3339 timestamp and ``now``; None when there is
    no timestamp or it cannot be parsed. Never negative: a backup from the
    future is a clock problem, reported as age 0 rather than hidden."""
    if not timestamp:
        return None
    try:
        moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return max(0, (now.astimezone(UTC) - moment.astimezone(UTC)).days)


@dataclass(frozen=True)
class Row:
    """One project. `problems` is non-empty when something about the row could
    not be established; the other fields then say what could."""

    key: str
    domain: str | None
    environment: str | None
    source_commit: str | None
    deployed_through_session: int | None
    template_version: str | None
    health: dict[str, object]
    backups: dict[str, object]
    denials: dict[str, object]
    problems: tuple[str, ...] = field(default_factory=tuple)


def _health(doctor: dict[str, object] | None, problem: str | None) -> dict[str, object]:
    if doctor is None:
        return {
            "worst": diagnosis.UNKNOWN,
            "counts": {},
            "checks": {},
            "reason": problem or "the doctor did not run",
        }
    checks = [c for c in (doctor.get("checks") or []) if isinstance(c, dict)]  # type: ignore[union-attr]
    verdicts = {str(c.get("name")): str(c.get("verdict")) for c in checks}
    counts = {
        verdict: sum(1 for v in verdicts.values() if v == verdict)
        for verdict in (diagnosis.OK, diagnosis.WARN, diagnosis.PROBLEM, diagnosis.UNKNOWN)
    }
    return {"worst": str(doctor.get("worst")), "counts": counts, "checks": verdicts}


def row(
    key: str,
    document: dict[str, object],
    *,
    doctor: dict[str, object] | None,
    doctor_problem: str | None,
    timers: dict[str, str],
    denials: dict[str, int] | None,
    window_hours: int,
    now: datetime,
) -> Row:
    """Compose one row. ``document`` has already passed
    `deployed_output.validate_deployed_document`; ``doctor`` is the parsed
    `doctor.py --json` document or None with ``doctor_problem`` saying why;
    ``timers`` maps a kind to a unit state; ``denials`` maps a reason to a
    count over ``window_hours``, or None when the table could not be read."""
    project = document.get("project") or {}
    if not isinstance(project, dict):
        project = {}
    states = {kind: timers.get(kind, UNKNOWN) for kind in TIMER_KINDS}
    last_full = last_full_backup_at(doctor)
    problems: list[str] = []
    if doctor is None:
        problems.append(f"health not measured: {doctor_problem or 'the doctor did not run'}")
    if denials is None:
        problems.append("denials not measured: the audit table could not be read")
    return Row(
        key=key,
        domain=_text(project.get("domain")),
        environment=_text(project.get("environment")),
        source_commit=_text(document.get("source_commit")),
        deployed_through_session=_integer(document.get("deployed_through_session")),
        template_version=_text(document.get("template_version")),
        health=_health(doctor, doctor_problem),
        backups={
            "state": schedule(states),
            "timers": states,
            "last_full_backup_at": last_full,
            "age_days": age_days(last_full, now),
        },
        denials={
            "window_hours": window_hours,
            "total": None if denials is None else sum(denials.values()),
            "by_reason": {} if denials is None else dict(sorted(denials.items())),
        },
        problems=tuple(problems),
    )


def invalid_row(key: str, reason: str) -> Row:
    """A project directory whose document could not be read or validated.
    Everything unknown, and the reason is this module's sentence about it --
    never the validator's message verbatim, which can quote the document."""
    return Row(
        key=key,
        domain=None,
        environment=None,
        source_commit=None,
        deployed_through_session=None,
        template_version=None,
        health={"worst": diagnosis.UNKNOWN, "counts": {}, "checks": {}, "reason": reason},
        backups={
            "state": UNKNOWN,
            "timers": {kind: UNKNOWN for kind in TIMER_KINDS},
            "last_full_backup_at": None,
            "age_days": None,
        },
        denials={"window_hours": 0, "total": None, "by_reason": {}},
        problems=(reason,),
    )


def render_json(rows: tuple[Row, ...], *, observed_at: str, window_hours: int) -> str:
    """Sorted by key, sorted keys within, so a diff between two inventories is
    a diff between two states of the host."""
    return json.dumps(
        {
            "observed_at": observed_at,
            "window_hours": window_hours,
            "projects": [asdict(r) for r in sorted(rows, key=lambda r: r.key)],
        },
        indent=2,
        sort_keys=True,
    )


def render_text(rows: tuple[Row, ...], *, observed_at: str, window_hours: int) -> str:
    """The operator's table: one block per project, every line under its key."""
    ordered = sorted(rows, key=lambda r: r.key)
    lines = [f"fleet: {len(ordered)} project(s) at {observed_at}, denial window {window_hours}h"]
    for r in ordered:
        lines.append("")
        if r.domain is None and r.problems:
            lines.append(f"{r.key}  ({r.problems[0]})")
            continue
        commit = (r.source_commit or "?")[:7]
        lines.append(
            f"{r.key}  {r.domain}  {r.environment}  release {commit} "
            f"s{r.deployed_through_session} v{r.template_version}"
        )
        counts = r.health.get("counts") or {}
        if counts:
            summary = ", ".join(
                f"{counts.get(v, 0)} {v}"
                for v in (diagnosis.OK, diagnosis.WARN, diagnosis.PROBLEM, diagnosis.UNKNOWN)
            )
        else:
            summary = str(r.health.get("reason", ""))
        lines.append(f"  {r.key}  health   {r.health.get('worst'):<12} {summary}")
        timers = r.backups.get("timers") or {}
        last = r.backups.get("last_full_backup_at") or "none"
        age = r.backups.get("age_days")
        age_text = f" ({age}d)" if age is not None else ""
        timer_text = " ".join(f"{k}={timers.get(k)}" for k in TIMER_KINDS)  # type: ignore[union-attr]
        lines.append(
            f"  {r.key}  backups  {r.backups.get('state'):<12} {timer_text}  "
            f"last full {last}{age_text}"
        )
        total = r.denials.get("total")
        if total is None:
            lines.append(f"  {r.key}  denials  not measured")
        else:
            by_reason = r.denials.get("by_reason") or {}
            detail = " ".join(f"{k}={v}" for k, v in by_reason.items()) or "none"  # type: ignore[union-attr]
            lines.append(f"  {r.key}  denials  {total} in {window_hours}h  {detail}")
        for problem in r.problems:
            lines.append(f"  {r.key}  !        {problem}")
    return "\n".join(lines)


def _text(value: object) -> str | None:
    return None if value is None else str(value)


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
