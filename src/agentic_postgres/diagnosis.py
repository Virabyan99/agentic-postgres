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

__all__ = [
    "DISK_PROBLEM_COPIES",
    "DISK_WARN_COPIES",
    "OK",
    "PROBLEM",
    "TLS_WARN_DAYS",
    "UNKNOWN",
    "WARN",
    "Check",
    "archiver",
    "containers",
    "database",
    "disk_headroom",
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


def disk_headroom(*, cluster_kb: int | None, available_kb: int | None, mount: str) -> Check:
    """Is there room for the restore this deployment promises?

    **Derived, not typed** — a restore materialises a second copy of the cluster,
    so the threshold is copies of PGDATA rather than a percentage nobody can
    justify. And it is measured at ``mount``, never at `/`: the two coincide on a
    developer machine, so a check reading `/` passes there for a reason that does
    not generalise (D634).
    """
    facts = _pairs(
        mount=mount,
        cluster_kb=cluster_kb,
        available_kb=available_kb,
        problem_below_copies=DISK_PROBLEM_COPIES,
        warn_below_copies=DISK_WARN_COPIES,
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
    if copies < DISK_PROBLEM_COPIES:
        return _check("disk headroom", PROBLEM, f"a restore cannot run: {summary}", facts)
    if copies < DISK_WARN_COPIES:
        return _check("disk headroom", WARN, f"one restore would fit, barely: {summary}", facts)
    return _check("disk headroom", OK, summary, facts)


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


def _tail(detail: str) -> str:
    return f" ({detail})" if detail else ""
