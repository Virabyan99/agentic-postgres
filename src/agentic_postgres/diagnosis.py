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

Nothing here reads a file, runs a process or touches the network.
"""

from __future__ import annotations

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
    "exit_code",
    "migrations",
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
    name: str
    verdict: str
    detail: str


def _check(name: str, verdict: str, detail: str) -> Check:
    return Check(name=name, verdict=verdict, detail=detail)


def containers(*, expected: int, running: tuple[str, ...], unhealthy: tuple[str, ...]) -> Check:
    """Are this project's containers up, and are any reporting unhealthy?

    ``expected`` is 0 when the caller could not determine it. A project whose
    container set cannot be established is UNKNOWN rather than PROBLEM: an empty
    `docker ps` result and a daemon that answered nothing look identical here,
    and only the caller can tell them apart.
    """
    if expected <= 0:
        return _check("containers", UNKNOWN, "could not establish this project's container set")
    if unhealthy:
        return _check(
            "containers",
            PROBLEM,
            f"{len(running)}/{expected} running, unhealthy: {', '.join(sorted(unhealthy))}",
        )
    if len(running) < expected:
        return _check("containers", PROBLEM, f"{len(running)}/{expected} running")
    return _check("containers", OK, f"{len(running)}/{expected} running, none unhealthy")


def route(*, name: str, url: str, status: int | None, expected: int) -> Check:
    """One published route, from a live request.

    ``status is None`` means the request did not complete, which is UNKNOWN — a
    route that could not be reached from here may be perfectly well from
    somewhere else, and this command runs on the host.
    """
    if status is None:
        return _check(f"route {name}", UNKNOWN, f"{url} did not answer")
    if status != expected:
        return _check(f"route {name}", PROBLEM, f"{url} answered {status}, expected {expected}")
    return _check(f"route {name}", OK, f"{url} answered {status}")


def tls(*, days_remaining: int | None, not_after: str | None) -> Check:
    """The certificate the edge is actually serving, not the one it recorded.

    Read live, because a document written at deploy time says what the
    certificate was then — and a certificate's whole failure mode is the passage
    of time (ADR 0158).
    """
    if days_remaining is None:
        return _check("tls", UNKNOWN, "no certificate could be read from the edge")
    if days_remaining < 0:
        return _check("tls", PROBLEM, f"expired {abs(days_remaining)}d ago ({not_after})")
    if days_remaining < TLS_WARN_DAYS:
        return _check("tls", WARN, f"{days_remaining}d remaining ({not_after})")
    return _check("tls", OK, f"{days_remaining}d remaining ({not_after})")


def database(*, reachable: bool, pooler_reachable: bool, detail: str = "") -> Check:
    """The cluster and the pooler, each from a real connection.

    Both, and reported together, because they fail independently: a pooler that
    cannot reach its cluster and a cluster nobody can reach look the same from a
    client and need different repairs.
    """
    if reachable and pooler_reachable:
        return _check("database", OK, "cluster and pooler both answered")
    if reachable and not pooler_reachable:
        return _check(
            "database", PROBLEM, f"the cluster answered; the pooler did not{_tail(detail)}"
        )
    if not reachable and pooler_reachable:
        return _check(
            "database", PROBLEM, f"the pooler answered; the cluster did not{_tail(detail)}"
        )
    return _check(
        "database", PROBLEM, f"neither the cluster nor the pooler answered{_tail(detail)}"
    )


def migrations(*, applied: int | None, released: int) -> Check:
    """Every released migration applied, from the ledger rather than from a lock.

    ``applied is None`` is UNKNOWN: the ledger could not be read, which is not
    the same as a ledger that is behind.
    """
    if applied is None:
        return _check("migrations", UNKNOWN, "the migration ledger could not be read")
    if applied < released:
        return _check("migrations", PROBLEM, f"{applied} of {released} released migrations applied")
    if applied > released:
        return _check(
            "migrations",
            WARN,
            f"the cluster reports {applied} applied and this release has {released}; "
            "it is ahead of this checkout",
        )
    return _check("migrations", OK, f"all {released} released migrations applied")


def repository(*, status: str | None, last_full_backup_at: str | None) -> Check:
    """What the backup repository reports about itself (ADR 0149).

    ``status`` is `bin/backup.sh info --json`'s **state field**, never its exit
    code: `pgbackrest info` exits 0 for a stanza that does not exist (D548), the
    same defect as `postgrest --ready` returning 0 while every request 404s
    (D145). Two third parties, five sessions apart, one shape.
    """
    if status is None:
        return _check("backup repository", UNKNOWN, "the repository could not be queried")
    if status == "ok":
        return _check("backup repository", OK, f"last full backup {last_full_backup_at}")
    if status == "awaiting_first_backup":
        return _check("backup repository", WARN, "the stanza exists and holds no full backup yet")
    return _check("backup repository", PROBLEM, f"the repository reports {status}")


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
    if failing is None:
        return _check("wal archiver", UNKNOWN, "pg_stat_archiver could not be read")
    if failing:
        return _check("wal archiver", PROBLEM, "the most recent archive attempt failed")
    return _check("wal archiver", OK, f"last archived {last_archived_time}")


def disk_headroom(*, cluster_kb: int | None, available_kb: int | None, mount: str) -> Check:
    """Is there room for the restore this deployment promises?

    **Derived, not typed** — a restore materialises a second copy of the cluster,
    so the threshold is copies of PGDATA rather than a percentage nobody can
    justify. And it is measured at ``mount``, never at `/`: the two coincide on a
    developer machine, so a check reading `/` passes there for a reason that does
    not generalise (D634).
    """
    if cluster_kb is None or available_kb is None:
        return _check("disk headroom", UNKNOWN, f"could not measure {mount}")
    if cluster_kb <= 0:
        return _check("disk headroom", UNKNOWN, f"{mount} reported a cluster size of {cluster_kb}")

    copies = available_kb / cluster_kb
    summary = (
        f"{available_kb // 1024} MiB free at {mount}, "
        f"cluster is {cluster_kb // 1024} MiB ({copies:.1f}x)"
    )
    if copies < DISK_PROBLEM_COPIES:
        return _check("disk headroom", PROBLEM, f"a restore cannot run: {summary}")
    if copies < DISK_WARN_COPIES:
        return _check("disk headroom", WARN, f"one restore would fit, barely: {summary}")
    return _check("disk headroom", OK, summary)


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


def report(checks: tuple[Check, ...], *, project_key: str) -> str:
    counts = {verdict: sum(1 for c in checks if c.verdict == verdict) for verdict in _SEVERITY}
    headline = (
        f"{project_key}: {counts[OK]} ok, {counts[WARN]} warning, "
        f"{counts[PROBLEM]} problem, {counts[UNKNOWN]} unknown"
    )
    label = {OK: "ok", WARN: "WARN", PROBLEM: "PROBLEM", UNKNOWN: "UNKNOWN"}
    lines = [headline, ""]
    lines.extend(f"  {label[c.verdict]:<8} {c.name} — {c.detail}" for c in checks)
    return "\n".join(lines)


def _tail(detail: str) -> str:
    return f" ({detail})" if detail else ""
