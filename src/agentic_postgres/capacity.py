"""The capacity envelope: what this deployment does at its limits, and where it does not.

`CAP-ENV-001`, and §7 of the Session 14 plan names it *"the claim most at risk of
being reported dishonestly. An envelope is a document, and a claim over a
document can go green because the document exists."*

Three rules answer that, and each is enforced by a test rather than remembered.

**1. A number carries the conditions it was sampled under, or it is not a
number.** D593 and D603 are the standing instance: `process-max` is 1, so a
restore is ~1,330 serialised S3 round trips and any RTO figure is *a sample from
a band*. A latency quoted without its concurrency, its transaction duration and
the machine it ran on is a number about nothing.

**2. A measurement declares whether it TRANSFERS.** This is the distinction the
envelope turns on, and it is the one an envelope usually gets wrong:

  * ``CONFIGURATION`` -- follows from `pool_size`, `max_client_conn`,
    `query_wait_timeout` and their kin. *Which* error a caller gets, and at what
    client count. These hold wherever the deployment runs.
  * ``MACHINE`` -- throughput and milliseconds. These are about the machine the
    rig ran on. Quoting one for the deployment is D770's mistake in a new place:
    a store's memory measured on a 7.8 GB rig described that rig, not the host.

**3. What was NOT measured is listed, with the reason.** An envelope that
silently omits the scenarios nobody could run reads as an envelope of the whole
system. `UNMEASURED` is that list, and a test asserts it is non-empty for as long
as anything is outstanding — because the day it is empty is a claim in itself.

**The envelope is pinned to the images it was measured against**, and that is
the guard §7 asks for. `stale_against` compares the digests recorded here with
`versions.env`; a moved digest makes the envelope stale and says which image
moved. **This is not hypothetical** — `traefik:v3.7` moved twice inside Session
14 (D787), three days apart. A document that floats free of the release it
describes is D700's stale `backup_state` in a new place: it published `failing`
for every project and survived two sessions because it failed safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentic_postgres import REPO_ROOT

__all__ = [
    "CONFIGURATION",
    "ENVELOPE",
    "MACHINE",
    "MEASURED_AGAINST",
    "UNMEASURED",
    "Measurement",
    "Unmeasured",
    "locked_digests",
    "stale_against",
]

#: A number that follows from the deployment's configuration. It holds wherever
#: the deployment runs, because what produced it is a setting rather than a CPU.
CONFIGURATION = "configuration"

#: A number that describes the machine the rig ran on. It does NOT transfer to
#: the deployment host, and the envelope says so beside every one of them.
MACHINE = "machine"

#: The images whose behaviour these numbers describe. Only these three: an
#: envelope pinned to every image in the lock would go stale when an unrelated
#: one moved, and an envelope pinned to none would never go stale at all.
MEASURED_AGAINST: tuple[str, ...] = (
    "POSTGRES_IMAGE",
    "PGBOUNCER_IMAGE",
    "POSTGREST_IMAGE",
)


@dataclass(frozen=True, slots=True)
class Measurement:
    """One number, and everything needed to read it correctly."""

    subject: str
    value: str
    kind: str
    conditions: tuple[str, ...]
    note: str = ""

    def __post_init__(self) -> None:
        if self.kind not in (CONFIGURATION, MACHINE):
            raise ValueError(f"{self.subject}: {self.kind!r} is not a declared measurement kind")
        if not self.conditions:
            # The rule this module exists for, enforced at construction so a
            # conditionless number cannot be written at all.
            raise ValueError(
                f"{self.subject}: a measurement with no stated conditions is a number "
                "about nothing (D593, D603)"
            )


@dataclass(frozen=True, slots=True)
class Unmeasured:
    """A scenario the plan asked for that this run could not run, and why."""

    subject: str
    reason: str
    unblocked_by: str


#: What the pooled path and the REST path do at their limits.
#:
#: Measured in Session 14 Run 5's successor, against the images pinned in
#: `versions.env` and configured from the RENDERED settings rather than from
#: values retyped here -- a rig at a different `pool_size` measures a different
#: pooler (ADR 0065/0066).
ENVELOPE: tuple[Measurement, ...] = (
    # ---- the pooled path -------------------------------------------------
    Measurement(
        subject="Pooled clients: the pooler queues rather than refusing",
        value="80 concurrent clients against 20 server slots all completed, none refused",
        kind=CONFIGURATION,
        conditions=(
            "pgbouncer in transaction mode, default_pool_size 20, max_client_conn 100",
            "each client one transaction holding a server slot for 200 ms",
            "query_wait_timeout 20 s, never reached at this holding time",
        ),
        note=(
            "Four times the pool with no error at all. The pooler's response to "
            "excess concurrency is latency, not refusal -- which is why the "
            "refusal threshold below is expressed in holding TIME rather than in "
            "client count."
        ),
    ),
    Measurement(
        subject="Pooled clients: latency against concurrency",
        value="1 client 207 ms; 20 clients 240 ms; 40 clients 324 ms; 80 clients 476 ms (p50)",
        kind=MACHINE,
        conditions=(
            "200 ms transactions, pgbouncer default_pool_size 20",
            "an 8 GB development machine, NOT the 3,814 MB deployment host",
            "single project, no other load on the cluster",
        ),
        note=(
            "The shape transfers and the milliseconds do not. Latency tracks "
            "queue depth times service time: at 80 clients against 20 slots, "
            "four waves of a 200 ms transaction is 800 ms and the observed "
            "maximum was 733 ms. **A deployment's own numbers must be taken on "
            "the deployment.**"
        ),
    ),
    Measurement(
        subject="Pooled clients: what a caller sees when the queue times out",
        value="ProtocolViolation: query_wait_timeout",
        kind=CONFIGURATION,
        conditions=(
            "30 clients each holding a slot for 25 s against query_wait_timeout 20 s",
            "exactly 20 completed and 10 were refused, matching default_pool_size",
        ),
        note=(
            "**The error class names the wrong cause.** A capacity condition is "
            "reported as a PROTOCOL violation, so a client catching "
            "`OperationalError` -- the usual 'connection trouble, retry' -- does "
            "not catch it. This is D145's family: the state is real and the "
            "signal describes something else. Compare the REST path below, which "
            "gets the same failure right."
        ),
    ),
    Measurement(
        subject="Pooled clients: the client-connection ceiling",
        value="the 101st connection is refused with FATAL: no more connections allowed "
        "(max_client_conn)",
        kind=CONFIGURATION,
        conditions=(
            "max_client_conn 100; 105 connections opened in sequence",
            "exactly 100 were accepted before the refusal",
        ),
        note=(
            "This one names its cause correctly, and it arrives as an "
            "`OperationalError`. **So the same component reports one limit "
            "honestly and the other as a protocol violation**, which is worth "
            "knowing before writing a retry."
        ),
    ),
    # ---- the REST path ---------------------------------------------------
    Measurement(
        subject="REST callers: the served plateau",
        value="about 110 concurrent 500 ms requests are served; the rest are refused",
        kind=CONFIGURATION,
        conditions=(
            "PGRST_DB_POOL 10, PGRST_DB_POOL_ACQUISITION_TIMEOUT 5 s",
            "each request holds its connection for 500 ms",
            "measured at 100, 120, 160 and 240 concurrent",
        ),
        note=(
            "The plateau is stable: 110 served at 160 concurrent and 110 at 240. "
            "Offered load above the plateau does not reduce what is served, "
            "which is the property that makes this a limit rather than a "
            "collapse. **PostgREST connects directly to the cluster, not through "
            "the pooler**, so this limit and the pooled one are independent."
        ),
    ),
    Measurement(
        subject="REST callers: what a caller sees when the pool is exhausted",
        value='HTTP 504 with {"code":"PGRST003","message":"Timed out acquiring '
        'connection from connection pool."}',
        kind=CONFIGURATION,
        conditions=(
            "PGRST_DB_POOL 10, acquisition timeout 5 s, 500 ms requests",
            "first observed at 120 concurrent; 14 of 120 refused",
        ),
        note=(
            "**This is the honest one.** A machine-readable code, a message "
            "naming the actual cause, and a status a caller already classifies "
            "as a gateway timeout. Set beside the pooler's "
            "`ProtocolViolation`, it is the same failure reported two ways, and "
            "only one of them can be acted on without knowing this document."
        ),
    ),
    Measurement(
        subject="REST callers: the limit is connection-seconds, not requests",
        value="240 concurrent fast requests were all served; none was refused",
        kind=CONFIGURATION,
        conditions=(
            "the same 240 concurrency that refused 130 of the 500 ms requests",
            "a request doing no work beyond a constant select",
        ),
        note=(
            "The separating control, and it decides how the limit should be "
            "read. Neither the HTTP layer nor the caller count is the "
            "constraint -- what saturates is callers HOLDING a connection. "
            "**Capacity here is connection-seconds**, so halving a query's "
            "duration is worth as much as doubling the pool. (Those requests "
            "returned in single-digit milliseconds, but that figure is the "
            "rig machine's and is not quoted as this deployment's -- the "
            "transferring claim is that none of them was refused.)"
        ),
    ),
    Measurement(
        subject="REST callers: the service is undamaged by saturation",
        value="a request after 240-concurrent saturation returned 200 in 2 ms",
        kind=CONFIGURATION,
        conditions=("immediately after the 240-concurrent arm returned 130 refusals",),
        note=(
            "Checked because a limit that leaves wreckage is a different "
            "property from a limit that sheds load. This one sheds."
        ),
    ),
)


#: What the plan asked for and this run did not measure, each with its reason.
#:
#: **Listed rather than omitted.** An envelope silently missing the scenarios
#: nobody could run reads as an envelope of the whole system, and that is the
#: dishonest reporting §7 warns about — arriving as a document that looks
#: complete rather than as a claim that is false.
UNMEASURED: tuple[Unmeasured, ...] = (
    Unmeasured(
        subject="The deployment's own numbers, on the deployment",
        reason=(
            "Every measurement here was taken off-host, against the pinned images at "
            "the rendered settings. The host is a 3,814 MB machine with no swap and "
            "eighteen containers; this rig was an 8 GB development machine running "
            "two. **The CONFIGURATION numbers transfer and the MACHINE numbers do "
            "not**, and no arithmetic converts one into the other."
        ),
        unblocked_by="the Run 8 host trip, which is the first deploy in three sessions",
    ),
    Unmeasured(
        subject="MCP reads and writes",
        reason=(
            "A write is four upstream requests and a read is three (ADR 0129), and "
            "**nothing has ever timed any of it against the deployment** — a standing "
            "open item since Session 8. Timing it needs the whole agent plane: the "
            "auth service, a signed token, the capability contract and a live audit "
            "table. That is a deployment, not a rig."
        ),
        unblocked_by="the Run 8 host trip",
    ),
    Unmeasured(
        subject="Backup behaviour under load",
        reason=(
            "It needs the pgBackRest repository, which is an R2 bucket reached with a "
            "credential this machine does not hold and must not be given. "
            "`process-max` is 1, so a 31 MB backup is six minutes of serialised round "
            "trips (D593) — the interaction worth measuring is what that does to "
            "query latency, and it cannot be simulated without the real repository."
        ),
        unblocked_by="the Run 8 host trip, on a project carrying no data anybody needs",
    ),
    Unmeasured(
        subject="Timeout and pool tuning",
        reason=(
            "The plan asks for tuning after the load scenarios. **Nothing is tuned "
            "here, deliberately**: every number above was measured off-host, and "
            "changing `pool_size` or `query_wait_timeout` on the strength of a "
            "development machine's latency would be tuning the deployment to a "
            "measurement that is not about it. `ALERT_ERROR_RATIO` (Run 5) is "
            "waiting on the same evidence."
        ),
        unblocked_by="the Run 8 host trip, and a second envelope taken there",
    ),
)


def locked_digests(lock: Path | None = None) -> dict[str, str]:
    """The digest of every image this envelope's numbers describe."""
    text = (lock or (REPO_ROOT / "versions.env")).read_text(encoding="utf-8")
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            if key.strip() in MEASURED_AGAINST:
                values[key.strip()] = value.strip()
    return values


def stale_against(recorded: dict[str, str], lock: Path | None = None) -> tuple[str, ...]:
    """Which of the measured-against images have moved since `recorded`.

    Empty means the envelope still describes the release. Non-empty names the
    images that moved, because *"the envelope is stale"* sends a reader looking
    and *"POSTGREST_IMAGE moved"* sends them to the measurement that is now a
    claim about a previous version.

    Pinned to three images rather than to the whole lock: an envelope that went
    stale when `traefik` moved would cry wolf — and `traefik:v3.7` moved twice
    inside Session 14 alone (D787).
    """
    current = locked_digests(lock)
    missing = tuple(sorted(set(MEASURED_AGAINST) - set(recorded)))
    moved = tuple(
        sorted(key for key, digest in current.items() if recorded.get(key) not in (None, digest))
    )
    return tuple(sorted({*missing, *moved}))
