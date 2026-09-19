"""What a deployed project's health is, from what was read off it live.

`OPS-001`. The verdicts live here and the probing lives in `bin/doctor.py`,
which is `database_observation`'s split and `preflight`'s: that command needs
root and a deployment, so nothing in it is testable behaviourally.

**The deployed document is the address book, not the diagnosis** (ADR 0158).
Nothing here takes a `status` field off `outputs.json` and calls it a verdict.
That document records what was observed *at deploy time*: a project deployed
three weeks ago whose archiver died yesterday still publishes
`backup_state.status: ok`. The schema makes the point structurally —
`backupState` carries `wal_archived_count` and `wal_failed_count` and **not** the
timestamps, so the only archiver signal it holds is the cumulative counter D553
measured at **26 on a healthy, fully-caught-up cluster**.

**Four verdicts**, which is ADR 0157's three plus an advisory tier that ADR
predicted this requirement would need:

* ``OK``       — measured, and well.
* ``WARN``     — measured, and worth knowing. Exits 0.
* ``PROBLEM``  — measured, and wrong.
* ``UNKNOWN``  — **not measured.** Never a synonym for OK, and never for PROBLEM.

**`--verbose` adds resolution, never a third party's bytes** (ADR 0159). Every
value it prints is one this program produced: a parsed integer, a boolean, a
timestamp it read out of a catalog view. No subprocess stdout, no stderr, no
environment, no path under the secret root.

That is stricter than filtering, and the reason is already written down in this
repository — `storage_client.redact`: *"Half-redacting is worse than not logging:
a URL missing only `X-Amz-Signature` still names the bucket, the key and the
account."* A filter over `pgbackrest`'s stderr would be a denylist against a
third party's future output, and a test of it would be a test of the denylist
(D622). Not printing it is a property; filtering it is a hope.

**Two renderings of one set of checks, since Session 17** (`FLEET-INV-001`):
`report` is the operator's table and `render_json` is the same verdicts as a
document, for the fleet inventory to compose rather than to parse. The JSON
carries every check's evidence unconditionally -- it is a machine's reading,
and the values are the ones this program produced, so the redaction rule above
holds for it exactly as it holds for `--verbose`. What it never carries is
anything `report` would not: no subprocess bytes, no document block the doctor
does not read.

Nothing here reads a file, runs a process, reads a clock or touches the network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

__all__ = [
    "DISK_PROBLEM_COPIES",
    "DISK_WARN_COPIES",
    "OK",
    "PROBLEM",
    "TLS_WARN_DAYS",
    "UNKNOWN",
    "WARN",
    "Check",
    "agent_record",
    "archiver",
    "capability_drift",
    "containers",
    "database",
    "disk_headroom",
    "disk_thresholds",
    "document",
    "exit_code",
    "migrations",
    "render_json",
    "report",
    "repository",
    "route",
    "tls",
    "worst",
]

OK = "ok"
WARN = "warn"
PROBLEM = "problem"
UNKNOWN = "unknown"

#: Worst-to-best, for `worst()`. `UNKNOWN` outranks `WARN` deliberately: a check
#: that could not run is a worse answer than one that ran and found something
#: mildly wrong, because nobody knows which of the other three it would have been.
_SEVERITY = {OK: 0, WARN: 1, UNKNOWN: 2, PROBLEM: 3}

#: A restore materialises a second copy of the cluster, so the number that
#: matters is not a percentage — it is how many copies of PGDATA would fit in
#: what is free. Below one, a restore cannot run at all.
DISK_PROBLEM_COPIES = 1.0
DISK_WARN_COPIES = 2.0

#: Days of certificate life below which an operator should be told. Let's
#: Encrypt renews at 30 days remaining, so 21 means "renewal should already have
#: happened and did not" rather than "renewal is due".
TLS_WARN_DAYS = 21


@dataclass(frozen=True)
class Check:
    """One verdict, and the values `--verbose` is allowed to show behind it.

    ``evidence`` holds **only values this program produced** — parsed numbers,
    booleans and its own enum-ish strings. Never a byte a third party emitted.
    See the module docstring: half-redacting a subprocess's stderr is worse than
    omitting it.
    """

    name: str
    verdict: str
    detail: str
    evidence: tuple[tuple[str, str], ...] = ()


def _check(
    name: str, verdict: str, detail: str, evidence: tuple[tuple[str, str], ...] = ()
) -> Check:
    return Check(name=name, verdict=verdict, detail=detail, evidence=evidence)


def _pairs(**values: object) -> tuple[tuple[str, str], ...]:
    """Evidence from named values, rendered here rather than by the caller.

    The rendering is deliberately in this module: a caller that formatted its own
    strings could format anything, including something it had been handed. Taking
    values and doing the `str()` here is what makes "only what this program
    produced" a property of the construction rather than a rule to remember.
    """
    return tuple((name, "null" if value is None else str(value)) for name, value in values.items())


def containers(*, expected: int, running: tuple[str, ...], unhealthy: tuple[str, ...]) -> Check:
    """Are this project's containers up, and are any reporting unhealthy?

    ``expected`` is 0 when the caller could not determine it. A project whose
    container set cannot be established is UNKNOWN rather than PROBLEM: an empty
    `docker ps` result and a daemon that answered nothing look identical here,
    and only the caller can tell them apart.
    """
    facts = _pairs(expected=expected, running=len(running), unhealthy=len(unhealthy))
    if expected <= 0:
        return _check(
            "containers", UNKNOWN, "could not establish this project's container set", facts
        )
    if unhealthy:
        return _check(
            "containers",
            PROBLEM,
            f"{len(running)}/{expected} running, unhealthy: {', '.join(sorted(unhealthy))}",
            facts,
        )
    if len(running) < expected:
        return _check("containers", PROBLEM, f"{len(running)}/{expected} running", facts)
    return _check("containers", OK, f"{len(running)}/{expected} running, none unhealthy", facts)


def route(*, name: str, url: str, status: int | None, expected: int) -> Check:
    """One published route, from a live request.

    ``status is None`` means the request did not complete, which is UNKNOWN — a
    route that could not be reached from here may be perfectly well from
    somewhere else, and this command runs on the host.
    """
    facts = _pairs(url=url, status=status, expected=expected)
    if status is None:
        return _check(f"route {name}", UNKNOWN, f"{url} did not answer", facts)
    if status != expected:
        return _check(
            f"route {name}", PROBLEM, f"{url} answered {status}, expected {expected}", facts
        )
    return _check(f"route {name}", OK, f"{url} answered {status}", facts)


def tls(*, days_remaining: int | None, not_after: str | None) -> Check:
    """The certificate the edge is actually serving, not the one it recorded.

    Read live, because a document written at deploy time says what the
    certificate was then — and a certificate's whole failure mode is the passage
    of time (ADR 0158).
    """
    facts = _pairs(days_remaining=days_remaining, not_after=not_after, warn_below=TLS_WARN_DAYS)
    if days_remaining is None:
        return _check("tls", UNKNOWN, "no certificate could be read from the edge", facts)
    if days_remaining < 0:
        return _check("tls", PROBLEM, f"expired {abs(days_remaining)}d ago ({not_after})", facts)
    if days_remaining < TLS_WARN_DAYS:
        return _check("tls", WARN, f"{days_remaining}d remaining ({not_after})", facts)
    return _check("tls", OK, f"{days_remaining}d remaining ({not_after})", facts)


def database(*, reachable: bool, pooler_reachable: bool, detail: str = "") -> Check:
    """The cluster and the pooler, each from a real connection.

    Both, and reported together, because they fail independently: a pooler that
    cannot reach its cluster and a cluster nobody can reach look the same from a
    client and need different repairs.
    """
    facts = _pairs(cluster_answered=reachable, pooler_answered=pooler_reachable)
    if reachable and pooler_reachable:
        return _check("database", OK, "cluster and pooler both answered", facts)
    if reachable and not pooler_reachable:
        return _check(
            "database", PROBLEM, f"the cluster answered; the pooler did not{_tail(detail)}", facts
        )
    if not reachable and pooler_reachable:
        return _check(
            "database", PROBLEM, f"the pooler answered; the cluster did not{_tail(detail)}", facts
        )
    return _check(
        "database", PROBLEM, f"neither the cluster nor the pooler answered{_tail(detail)}", facts
    )


def database_pooler_undetermined(*, reachable: bool) -> Check:
    """The cluster answered; the pooler could not be asked (D680).

    A distinct verdict rather than a `PROBLEM`, and the distinction is the
    lesson: an endpoint the document does not publish, and a probe that could
    not complete, are both *"this was not measured"*. Reporting either as a
    failing pooler is the false alarm this check just produced on a live host.

    `UNKNOWN` even when the cluster answered, because a `Check` carries one
    verdict and the unmeasured half is the one an operator must not read as
    healthy. ADR 0158: `unknown` is not a pass and not a failure.
    """
    facts = _pairs(cluster_answered=reachable, pooler_answered=None)
    if not reachable:
        return _check(
            "database",
            PROBLEM,
            "the cluster did not answer, and the pooler could not be asked",
            facts,
        )
    return _check("database", UNKNOWN, "the cluster answered; the pooler could not be asked", facts)


def migrations(*, applied: int | None, released: int) -> Check:
    """Every released migration applied, from the ledger rather than from a lock.

    ``applied is None`` is UNKNOWN: the ledger could not be read, which is not
    the same as a ledger that is behind.
    """
    facts = _pairs(applied=applied, released=released)
    if applied is None:
        return _check("migrations", UNKNOWN, "the migration ledger could not be read", facts)
    if applied < released:
        return _check(
            "migrations", PROBLEM, f"{applied} of {released} released migrations applied", facts
        )
    if applied > released:
        return _check(
            "migrations",
            WARN,
            f"the cluster reports {applied} applied and this release has {released}; "
            "it is ahead of this checkout",
            facts,
        )
    return _check("migrations", OK, f"all {released} released migrations applied", facts)


def repository(*, status: str | None, last_full_backup_at: str | None) -> Check:
    """What the backup repository reports about itself (ADR 0149).

    ``status`` is `bin/backup.sh info --json`'s **state field**, never its exit
    code: `pgbackrest info` exits 0 for a stanza that does not exist (D548), the
    same defect as `postgrest --ready` returning 0 while every request 404s
    (D145). Two third parties, five sessions apart, one shape.

    **The vocabulary is imported, not retyped** (D674). Run 3 wrote `"ok"` and
    `"awaiting_first_backup"` from memory; `backup_report` emits
    `not_observed`, `unconfigured`, `awaiting_first_backup`, **`ready`** and
    `failing`, and **there is no `ok` at all**. So the healthy repository on the
    live host -- with a full backup from the previous day -- was reported
    `PROBLEM the repository reports ready` on the first run of this check.

    A guessed enum is the same defect as a guessed column name, and D596 is the
    standing example: five recovery proofs died on a column renamed six sessions
    earlier and findable by one grep. This was findable by one grep too.
    """
    from agentic_postgres import backup_report

    facts = _pairs(reported_status=status, last_full_backup_at=last_full_backup_at)
    if status is None or status == backup_report.STATUS_NOT_OBSERVED:
        return _check("backup repository", UNKNOWN, "the repository could not be queried", facts)
    if status == backup_report.STATUS_READY:
        return _check("backup repository", OK, f"last full backup {last_full_backup_at}", facts)
    if status == backup_report.STATUS_AWAITING_FIRST_BACKUP:
        return _check(
            "backup repository",
            WARN,
            "the stanza exists and holds no full backup yet",
            facts,
        )
    # `failing` and `unconfigured`, plus anything a later session adds. An
    # unknown status is a PROBLEM rather than an OK: a repository this command
    # cannot classify is not one it may call healthy.
    return _check("backup repository", PROBLEM, f"the repository reports {status}", facts)


def archiver(*, failing: bool | None, last_archived_time: str | None) -> Check:
    """Is WAL still arriving? (ADR 0150)

    ``failing`` is `backup_report.archiving_is_failing`'s answer and is not
    recomputed here (D630) — Session 10 shipped that predicate with rig 7 arm G's
    measurements in its docstring, and a second threshold would be the D57/D262
    pattern. It compares timestamps and never `failed_count`, which stood at 26
    on a healthy cluster (D553).

    The repository and the archiver fail independently, which is why this is a
    check of its own: a repository full of good backups can sit behind an
    archiver that stopped an hour ago.
    """
    facts = _pairs(failing=failing, last_archived_time=last_archived_time)
    if failing is None:
        return _check("wal archiver", UNKNOWN, "pg_stat_archiver could not be read", facts)
    if failing:
        return _check("wal archiver", PROBLEM, "the most recent archive attempt failed", facts)
    return _check("wal archiver", OK, f"last archived {last_archived_time}", facts)


#: A mirror copy older than this is a copy the nightly timer has missed. Two
#: days, not one: the timer fires at 04:30 with up to twenty minutes of jitter,
#: and a doctor run at 04:00 the next day sees a copy just under a day old
#: that is exactly on schedule (the same reasoning as the incremental's own
#: cadence). Chosen, and named so it can be revised.
MIRROR_STALE_AFTER_DAYS = 2


def mirror(
    *, enabled: bool, status: str | None, last_copied_at: str | None, age_days: int | None
) -> Check:
    """Has the repository's copy at the second provider kept up? (ADR 0188)

    ``status`` is `backup_report`'s mirror vocabulary as the doctor read the
    copy record: `disabled`, `never`, `copied`, or None when the record could
    not be read. ``age_days`` is the caller's arithmetic over the clock this
    module does not have, and a copy with no age is reported by its timestamp
    alone rather than assumed fresh.

    A project without a mirror is OK and says so: the check exists for every
    project so that a fleet reading has the same rows for each, and "no mirror"
    is a manifest decision, not a defect. A mirror that has never copied is a
    warning rather than a problem for the reason the first full backup is: the
    timer's first slot has not come, or the copy has been failing, and the unit's
    own failure state says which.
    """
    from agentic_postgres import backup_report

    facts = _pairs(
        enabled=enabled, reported_status=status, last_copied_at=last_copied_at, age_days=age_days
    )
    if not enabled:
        return _check("backup mirror", OK, "no mirror is configured for this project", facts)
    if status is None or status == backup_report.MIRROR_NOT_OBSERVED["status"]:
        return _check("backup mirror", UNKNOWN, "the copy record could not be read", facts)
    if status == backup_report.MIRROR_STATUS_NEVER:
        return _check(
            "backup mirror", WARN, "the mirror is configured and has never completed a copy", facts
        )
    if status != backup_report.MIRROR_STATUS_COPIED:
        return _check("backup mirror", PROBLEM, f"the copy record reports {status}", facts)
    if age_days is not None and age_days >= MIRROR_STALE_AFTER_DAYS:
        return _check(
            "backup mirror",
            WARN,
            f"last copied {last_copied_at}, {age_days} days ago; the nightly copy has missed",
            facts,
        )
    return _check("backup mirror", OK, f"last copied {last_copied_at}", facts)


def disk_thresholds(*, warn_copies: float, problem_copies: float) -> tuple[float, float]:
    """The one rule a pair of thresholds must satisfy, spelled once: the
    problem is above zero and the warning fires before it. `disk_headroom`
    applies it and `bin/doctor.py` refuses an injected pair before reading
    anything, so the same sentence names both refusals."""
    if problem_copies <= 0 or warn_copies <= problem_copies:
        raise ValueError(
            f"disk thresholds must satisfy 0 < problem ({problem_copies}) < warn "
            f"({warn_copies}); a warning that fires after the problem is not advisory"
        )
    return warn_copies, problem_copies


def disk_headroom(
    *,
    cluster_kb: int | None,
    available_kb: int | None,
    mount: str,
    warn_copies: float = DISK_WARN_COPIES,
    problem_copies: float = DISK_PROBLEM_COPIES,
) -> Check:
    """Is there room for the restore this deployment promises?

    **Derived, not typed** — a restore materialises a second copy of the cluster,
    so the threshold is copies of PGDATA rather than a percentage nobody can
    justify. And it is measured at ``mount``, never at `/`: the two coincide on a
    developer machine, so a check reading `/` passes there for a reason that does
    not generalise (D634).

    ``warn_copies`` and ``problem_copies`` are the deployment's thresholds by
    default and a rehearsal's when injected (`OPS-REHEARSE-007`, ADR 0190): the
    reader is rehearsed by moving the threshold, never by filling the disk, and
    the evidence carries the thresholds the verdict was computed at so an
    injected reading cannot be mistaken for the host's.
    """
    disk_thresholds(warn_copies=warn_copies, problem_copies=problem_copies)
    facts = _pairs(
        mount=mount,
        cluster_kb=cluster_kb,
        available_kb=available_kb,
        problem_below_copies=problem_copies,
        warn_below_copies=warn_copies,
    )
    if cluster_kb is None or available_kb is None:
        return _check("disk headroom", UNKNOWN, f"could not measure {mount}", facts)
    if cluster_kb <= 0:
        return _check(
            "disk headroom", UNKNOWN, f"{mount} reported a cluster size of {cluster_kb}", facts
        )

    copies = available_kb / cluster_kb
    summary = (
        f"{available_kb // 1024} MiB free at {mount}, "
        f"cluster is {cluster_kb // 1024} MiB ({copies:.1f}x)"
    )
    if copies < problem_copies:
        return _check("disk headroom", PROBLEM, f"a restore cannot run: {summary}", facts)
    if copies < warn_copies:
        return _check("disk headroom", WARN, f"one restore would fit, barely: {summary}", facts)
    return _check("disk headroom", OK, summary, facts)


def capability_drift(
    *, recorded: bool, present: bool | None, matches: bool | None, plane: bool | None
) -> Check:
    """Is the lock on disk the one the document recorded -- and the one the
    running plane loaded?

    `AGT-DRIFT-001` extended to the running deployment (`OPS-REHEARSE-008`,
    ADR 0190): the deploy compiles the lock and records its digest in the
    document's `mcp` block; the runtime mounts the file. A lock rewritten after
    the deploy -- by a hand-run `mcp-contract.sh lock`, a partial deploy, an
    edit -- is a lock the document did not describe, and a restarted runtime
    would serve it.

    ``recorded`` says whether the document records a digest at all; ``present``
    whether a lock is on disk (None when it could not be read); ``matches``
    whether the on-disk digest equals the recorded one; ``plane`` whether the
    RUNNING agent plane reports serving the lock on disk, and **None when that
    could not be determined** -- no container, a plane that did not answer, or
    one running a release that does not say. **No digest is a parameter**: the
    `mcp` block is one the doctor never echoes (ADR 0159), so every comparison
    happens in the caller and only its answer arrives here.

    ``plane`` is a third reading rather than a refinement of ``matches``, and
    D1152 is why. A deploy whose only change is the lock recreates no container
    unless the container's mount digest moved (ADR 0155), so a file that agrees
    with the document says nothing about the process serving requests: on
    2026-09-11 beta served six tools for eight minutes against a document and a
    file that both said seven, and every check here was green. A plane that
    cannot be asked is `UNKNOWN` and not `OK` -- this module's own rule, stated
    at `exit_code`: a check that could not run is not a healthy check.

    A project with no agent plane records no lock and has none, and is OK; a
    lock on disk that no document recorded is a warning, because nothing
    deployed it. Neither of those asks the plane anything.
    """
    facts = _pairs(recorded=recorded, present=present, matches=matches, plane=plane)
    if not recorded:
        if present:
            return _check(
                "capability drift",
                WARN,
                "a capability lock is on disk that the deployed document does not record",
                facts,
            )
        return _check(
            "capability drift", OK, "no capability lock is recorded for this project", facts
        )
    if present is None:
        return _check("capability drift", UNKNOWN, "the capability lock could not be read", facts)
    if not present:
        return _check(
            "capability drift",
            PROBLEM,
            "the deployed document records a capability lock and none is on disk",
            facts,
        )
    if not matches:
        return _check(
            "capability drift",
            PROBLEM,
            "the lock on disk is not the one the deployed document recorded; a restarted "
            "runtime would serve a lock this deploy did not compile",
            facts,
        )
    # The file agrees with the document. That leaves the process (D1152).
    if plane is None:
        return _check(
            "capability drift",
            UNKNOWN,
            "the lock on disk is the one the document recorded, and the running agent "
            "plane could not be asked which lock it loaded",
            facts,
        )
    if not plane:
        return _check(
            "capability drift",
            PROBLEM,
            "the running agent plane is serving a lock that is not the one on disk; the "
            "deployment is answering from a document this deploy did not compile",
            facts,
        )
    return _check(
        "capability drift",
        OK,
        "the lock on disk is the one the deployed document recorded, and the one the "
        "running agent plane loaded",
        facts,
    )


def agent_record(
    *,
    audit_rows: int | None,
    audit_oldest: str | None,
    idempotency_rows: int | None,
    idempotency_oldest: str | None,
    detail: str = "",
) -> Check:
    """How much agent record this deployment carries, and how far back it goes.

    **A reading with no threshold, and the absence is the decision** (ADR 0213).
    `app_private.agent_audit` and `app_private.agent_idempotency` grow without
    bound and nothing prunes either unless an operator asks; what this check
    adds is that the growth is a number an operator SEES rather than a sentence
    in a migration comment they will never open.

    There is no `WARN` at some row count because **nobody has measured a row
    count at which this deployment is unwell**, and a threshold invented in the
    one command that runs as root on production could fail a host that works --
    D1441, found in Run 3 of the same session that built this check. What is
    asked here is ADR 0195's question: the numbers, or *I could not read them*.

    The probe reads the two TABLES and not migration 0033's functions, so this
    check answers unchanged against a deployment that has not applied the
    retention migration yet -- which every deployment is until Session 29.

    `None` for either count means the reading did not come back. The two
    `*_oldest` values are `None` on an empty table, which is a fact rather than
    a failure: a deployment whose agent plane has never been called carries no
    record, and saying `0 audit rows` with no date is the truthful rendering.
    """
    facts = _pairs(
        audit_rows=audit_rows,
        audit_oldest=audit_oldest,
        idempotency_rows=idempotency_rows,
        idempotency_oldest=idempotency_oldest,
    )
    if audit_rows is None or idempotency_rows is None:
        return _check(
            "agent record",
            UNKNOWN,
            f"the agent record could not be read{_tail(detail)}",
            facts,
        )
    since = f" since {audit_oldest}" if audit_oldest else ""
    return _check(
        "agent record",
        OK,
        f"{audit_rows} audit rows{since}, {idempotency_rows} idempotency claims; "
        "nothing prunes either unless an operator asks (ADR 0213)",
        facts,
    )


def worst(checks: tuple[Check, ...]) -> str:
    """The most severe verdict present, OK when there is nothing to report."""
    return max((c.verdict for c in checks), key=lambda v: _SEVERITY[v], default=OK)


def exit_code(checks: tuple[Check, ...]) -> int:
    """0 for ok and warn, 6 for problem and unknown.

    **`UNKNOWN` is not a pass.** A check that could not run is not a healthy
    check, and a caller that treated it as one would be back at D600 — a value
    that looks measured and is not. `WARN` is advisory by construction and exits
    0, which is the tier ADR 0157 anticipated this requirement would need.
    """
    return 0 if _SEVERITY[worst(checks)] <= _SEVERITY[WARN] else 6


def report(checks: tuple[Check, ...], *, project_key: str, verbose: bool = False) -> str:
    """The table, and under `--verbose` the values behind each verdict.

    Verbose prints `Check.evidence` and **nothing else** — no subprocess output,
    no environment, no path under the secret root. What it adds is resolution:
    the numbers a verdict was computed from, so an operator can see *why* rather
    than being told to trust it (ADR 0159).
    """
    counts = {verdict: sum(1 for c in checks if c.verdict == verdict) for verdict in _SEVERITY}
    headline = (
        f"{project_key}: {counts[OK]} ok, {counts[WARN]} warning, "
        f"{counts[PROBLEM]} problem, {counts[UNKNOWN]} unknown"
    )
    label = {OK: "ok", WARN: "WARN", PROBLEM: "PROBLEM", UNKNOWN: "UNKNOWN"}
    lines = [headline, ""]
    for check in checks:
        lines.append(f"  {label[check.verdict]:<8} {check.name} — {check.detail}")
        if verbose:
            lines.extend(f"  {'':<8}   {key} = {value}" for key, value in check.evidence)
    return "\n".join(lines)


def document(checks: tuple[Check, ...], *, project_key: str, observed_at: str) -> dict[str, object]:
    """The same verdicts as a document (Session 17, `FLEET-INV-001`).

    Built from the checks and nothing else: the verdict vocabulary is this
    module's, `worst` and `exit_code` are the functions the text report uses,
    and the evidence is `Check.evidence` -- values this program produced. A
    consumer that reads `exit_code` here reads the number the command exited
    with, so a fleet inventory composing several of these cannot arrive at a
    verdict the per-project command would not have given.

    ``observed_at`` is passed in rather than read: this module reads no clock,
    so the caller decides what moment the document describes and a test can
    fix it.
    """
    return {
        "project_key": project_key,
        "observed_at": observed_at,
        "worst": worst(checks),
        "exit_code": exit_code(checks),
        "checks": [
            {
                "name": check.name,
                "verdict": check.verdict,
                "detail": check.detail,
                "evidence": dict(check.evidence),
            }
            for check in checks
        ],
    }


def render_json(checks: tuple[Check, ...], *, project_key: str, observed_at: str) -> str:
    """`document`, serialised deterministically -- sorted keys, so two runs over
    the same checks produce identical bytes and a diff between runs is a diff
    between deployments."""
    return json.dumps(
        document(checks, project_key=project_key, observed_at=observed_at),
        indent=2,
        sort_keys=True,
    )


def capacity_report(reading: Any) -> tuple[Check, ...]:
    """What this node has, what is declared, and what is already claimed.

    **Two verdicts, never four** (ADR 0221, ADR 0213's shape). Every check
    below is `OK` with its numbers or `UNKNOWN` naming the figure it could not
    read. There is deliberately no `WARN` at some percentage of memory used and
    no `PROBLEM` at some disk threshold, for `agent_record`'s reason: nobody has
    measured a utilisation at which this node is unwell, `doctor` runs as root
    on production, and a threshold invented here could fail a host that works
    (D1441). `decide` in `capacity_reading` is where a rule lives, and it is a
    decision rather than a report -- it is allowed to fail closed, and this is
    not.

    The declaration and the measurement are separate checks on purpose. An
    operator who declared 3814 MiB on a host that reports 2048 should see two
    numbers that disagree, not one number that has quietly picked a winner.

    `reading` is a `capacity_reading.Reading`; it is typed loosely here for the
    reason every other function in this module is -- `diagnosis` is pure and
    imports nothing from the probe side, so the shape arrives rather than being
    reached for.
    """
    checks: list[Check] = []

    if reading.declared is None:
        checks.append(
            _check(
                "declared",
                UNKNOWN,
                "host.yaml declares no capacity (schema 2); see host.example.yaml",
                _pairs(schema="2", capacity="absent"),
            )
        )
    else:
        declared = reading.declared
        checks.append(
            _check(
                "declared",
                OK,
                f"{declared.memory_mb} MiB RAM and {declared.disk_gb} GiB disk declared, "
                f"{declared.claimable_memory_mb} MiB claimable by projects",
                _pairs(
                    memory_mb=declared.memory_mb,
                    reserve_memory_mb=declared.reserve_memory_mb,
                    claimable_memory_mb=declared.claimable_memory_mb,
                    disk_gb=declared.disk_gb,
                    reserve_disk_gb=declared.reserve_disk_gb,
                ),
            )
        )

    memory_figures = {
        "mem_total_mb": reading.mem_total,
        "mem_available_mb": reading.mem_available,
        "swap_total_mb": reading.swap_total,
    }
    missing = sorted(name for name, figure in memory_figures.items() if not figure.known)
    facts = _pairs(**{name: figure.value for name, figure in memory_figures.items()})
    if missing:
        reason = memory_figures[missing[0]].reason
        checks.append(
            _check("memory", UNKNOWN, f"{', '.join(missing)} could not be read: {reason}", facts)
        )
    else:
        swap = reading.swap_total.value
        swap_note = "no swap" if swap == 0 else f"{swap} MiB swap"
        checks.append(
            _check(
                "memory",
                OK,
                f"{reading.mem_available.value} MiB available of "
                f"{reading.mem_total.value} MiB, {swap_note}",
                facts,
            )
        )

    disk_figures = {
        "docker_root_free_gb": reading.docker_root_free_gb,
        "docker_root_total_gb": reading.docker_root_total_gb,
    }
    disk_missing = sorted(name for name, figure in disk_figures.items() if not figure.known)
    disk_facts = _pairs(**{name: figure.value for name, figure in disk_figures.items()})
    # **Where these two numbers came from.** The probe walks up from the Docker
    # data root to the nearest point it can stat (D1611), because that root
    # does not exist at all under Docker Desktop and is 0710 root on a CI
    # runner -- and an ancestor can be a different mount from the one the
    # daemon actually writes to. `decide` prints this beside its disk line for
    # exactly that reason; the READING was reporting the same two figures and
    # saying nothing about their subject, which is a number an operator cannot
    # check (ADR 0195). Empty when nothing on the way up could be stat'd, in
    # which case the figures are unknown anyway and say so.
    if reading.docker_root_measured_at:
        disk_facts = disk_facts + _pairs(measured_at=reading.docker_root_measured_at)
    if disk_missing:
        reason = disk_figures[disk_missing[0]].reason
        checks.append(
            _check(
                "disk",
                UNKNOWN,
                f"{', '.join(disk_missing)} could not be read: {reason}",
                disk_facts,
            )
        )
    else:
        checks.append(
            _check(
                "disk",
                OK,
                f"{reading.docker_root_free_gb.value} GiB free of "
                f"{reading.docker_root_total_gb.value} GiB at the Docker root",
                disk_facts,
            )
        )

    if reading.unreadable:
        named = ", ".join(sorted(reading.unreadable))
        checks.append(
            _check(
                "committed",
                UNKNOWN,
                f"the claim of {named} could not be read, so the committed total is not a total",
                _pairs(readable=len(reading.committed), unreadable=len(reading.unreadable)),
            )
        )
    else:
        checks.append(
            _check(
                "committed",
                OK,
                f"{reading.committed_total_mb} MiB claimed across "
                f"{len(reading.committed)} project(s)",
                _pairs(**dict(sorted(reading.committed.items()))),
            )
        )

    # Ceilings decide nothing and cannot be UNKNOWN in a way that matters: an
    # empty inspect is reported as an empty sum, and the detail says so. They
    # are here because an operator reading a refusal wants both numbers, and
    # because the gap between the two is this host's most misleading fact
    # (D767: the caps in aggregate already exceed the machine's RAM).
    ceiling_total = sum(reading.ceilings.values())
    unbounded = f", {len(reading.unbounded)} unbounded" if reading.unbounded else ""
    checks.append(
        _check(
            "ceilings",
            OK,
            f"{ceiling_total} MiB of mem_limit across "
            f"{len(reading.ceilings)} project(s){unbounded} -- ceilings, not "
            "reservations (D767)",
            _pairs(**dict(sorted(reading.ceilings.items()))),
        )
    )

    return tuple(checks)


def usage_report(figures: Any, *, units: dict[str, str]) -> tuple[Check, ...]:
    """How much this project is using, in one check per group.

    **Two verdicts, never four**, for `capacity_report`'s reason and
    `agent_record`'s before it: no size or count here has a measured value at
    which this deployment is unwell, and a threshold invented inside the one
    command that runs as root on production could fail a host that works
    (D1441, ADR 0213, ADR 0221).

    Grouped rather than one check per figure, because the groups are what an
    operator actually asks about -- how big is the database, how big is the
    backup, how much agent record is there, how busy has it been -- and eight
    one-line checks would be a list to scan rather than an answer.

    A group is `UNKNOWN` when ANY of its figures is, and names the ones it
    could not read. Half a group reported as a healthy number is the fold ADR
    0195 forbids: two of three sizes is not a size.
    """
    mapping = figures.as_mapping()

    groups = (
        ("database", ("database_bytes", "pgdata_kb", "wal_kb")),
        ("repository", ("repository_bytes",)),
        ("agent record", ("audit_rows", "idempotency_rows")),
        ("traffic", ("requests_total", "tool_calls_total")),
    )

    checks: list[Check] = []
    for name, members in groups:
        selected = {member: mapping[member] for member in members}
        facts = _pairs(**{member: figure.value for member, figure in selected.items()})
        missing = sorted(member for member, figure in selected.items() if not figure.known)
        if missing:
            reason = selected[missing[0]].reason
            checks.append(
                _check(name, UNKNOWN, f"{', '.join(missing)} could not be read: {reason}", facts)
            )
            continue
        detail = ", ".join(f"{figure.value} {units[member]}" for member, figure in selected.items())
        checks.append(_check(name, OK, detail, facts))

    return tuple(checks)


def _tail(detail: str) -> str:
    return f" ({detail})" if detail else ""
