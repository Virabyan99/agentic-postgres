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
    # ---- the developer's own machine (Session 22, D1066, D1168) -----------
    #
    # `apg dev` exists because the alternative to a local cluster is a restore,
    # and the Session 18 trip measured that at 247 s on the deployment host.
    # These two numbers are what the command actually costs, and they are
    # MACHINE numbers in the strictest sense: a developer reading them wants to
    # know what THEIR machine will do, and the only honest thing this document
    # can say is what one machine did under stated conditions.
    Measurement(
        subject="apg dev up: a disposable cluster, migrated, from nothing",
        value="10.98 s and 9.89 s (two samples)",
        kind=MACHINE,
        conditions=(
            "an 8 GB development machine, WSL2, kernel 6.6.87.2-microsoft-standard-WSL2",
            "Docker server 29.5.2, the locked postgres image ALREADY CACHED",
            "33 migrations: the 31 released, plus the example project's set of two "
            "(what the tree held WHEN THIS WAS SAMPLED; it now carries 33 released "
            "and 3 in the example set. The condition records the measurement, so it "
            "is not rewritten to today's numbers -- D1541, D1557)",
            "no container of this project running and no state directory present",
        ),
        note=(
            "The whole verb: `docker run` on the pinned image, the bootstrap "
            "statements as the superuser, 33 rendered migrations applied one "
            "transaction each as the migration user, both ledgers written, two "
            "roles activated and one subject registered. **The comparison "
            "worth making is against a restore**, which the Session 18 trip "
            "measured at 247 s -- on a different machine, so the ratio is not "
            "a number either, but the two are answers to the same question and "
            "one of them is a coffee break. The image being cached is a "
            "condition and not a detail: the uncached case is a first-run cost "
            "this machine cannot measure without evicting the image the whole "
            "suite shares, and it is listed as unmeasured below."
        ),
    ),
    Measurement(
        subject="apg dev reset: down, then up",
        value="10.07 s and 10.28 s (two samples)",
        kind=MACHINE,
        conditions=(
            "the same 8 GB development machine, WSL2, Docker server 29.5.2",
            "the locked postgres image already cached",
            "an environment that was running, with its 33 migrations applied",
            "the anonymous volume and the state directory removed, then 33 re-applied",
        ),
        note=(
            "`reset` is `down` then `up`, and the numbers say so: the teardown "
            "disappears into the sampling spread, which is the property worth "
            "publishing. A developer deciding whether to reset rather than "
            "debug a dirty database is choosing between ten seconds and an "
            "afternoon, and that is the decision this row is for."
        ),
    ),
    # ---- and the machine nobody prepared (Session 22, D1169) -------------
    #
    # Read from the log of CI run 34679195048, the push that added the
    # round-trip step, rather than copied from a plan. A fresh `ubuntu-latest`
    # runner has cached nothing, which is the first-run case the workstation
    # cannot measure without evicting the image the whole contract suite
    # shares -- so this is the only place in the envelope where the cold cost
    # of `apg dev up` appears at all.
    Measurement(
        subject="apg dev up on a CI runner: the first run, image pulled",
        value="14.46 s",
        kind=MACHINE,
        conditions=(
            "a GitHub-hosted CI runner, ubuntu-latest, runner 2.337.0",
            "the locked postgres image NOT CACHED -- pulled inside the measurement",
            "33 migrations, the same as the workstation rows",
            "one sample: the step runs once per push and is not repeated",
        ),
        note=(
            "**One sample, and it is said rather than hidden.** A number "
            "quoted from a single run of a shared machine carries whatever "
            "that machine was doing; what makes it worth publishing anyway is "
            "that it is the only measurement of the cold path. Set beside the "
            "`reset` row below -- 6.19 s on the SAME runner, in the same step, "
            "seconds later with the image now local -- the gap is dominated by "
            "the pull. That is the number a developer feels once and never "
            "again."
        ),
    ),
    # ---- what a regeneration costs (Session 23, D1079, GEN-ENV-001) ------
    #
    # `apg generate` is in the loop a developer runs after every capture, so
    # the number that matters is not whether it is fast but whether it is fast
    # enough to be unremarkable. Two contract sizes, because the only input
    # that could plausibly move it is how much surface there is to emit; and
    # the typecheck separately, because that is the part with a container in
    # it and it is what the developer actually waits for.
    Measurement(
        subject="apg generate: the release contract, 5 objects and 6 tools",
        value="0.28 s, 0.28 s and 0.29 s (three samples)",
        kind=MACHINE,
        conditions=(
            "an 8 GB development machine, WSL2, kernel 6.6.87.2-microsoft-standard-WSL2",
            "Python 3.12.13 in the checkout's venv; NO DOCKER DAEMON is needed or used",
            "project.second.example.yaml -- a manifest declaring no migration set,"
            " so the surface and the lock are the release's",
            "2 relations, 3 RPCs and 6 tools, emitting 29,157 bytes of TypeScript",
            "Python only: no typecheck and no container in this number",
        ),
        note=(
            "**The first `bin/apg.sh generate` in a fresh shell took 0.81 s** "
            "and every one after it 0.28 s, on the same inputs. The difference "
            "is the interpreter starting, not the generation, and it is stated "
            "here rather than averaged in: a developer's first regeneration of "
            "the day is the slow one and it is still under a second."
        ),
    ),
    Measurement(
        subject="apg generate: a project's contract, 7 objects and 7 tools",
        value="0.31 s, 0.32 s and 0.33 s (three samples)",
        kind=MACHINE,
        conditions=(
            "the same 8 GB development machine, WSL2, the same venv",
            "project.example.yaml -- a manifest declaring a migration set and its"
            " own capabilities, so the surface is merged and the lock is joint",
            "3 relations, 4 RPCs and 7 tools, emitting 31,097 bytes of TypeScript",
            "Python only: no typecheck and no container in this number",
        ),
        note=(
            "Forty milliseconds more than the release contract for two more "
            "objects, one more tool and 1,940 more bytes of output. **The "
            "point of publishing both is the slope, not either figure**: the "
            "cost is the process starting, and a tenant's surface growing does "
            "not change what this command feels like. A project ten times this "
            "size is unmeasured -- none exists -- and the two rows are what "
            "can honestly be said about scale."
        ),
    ),
    Measurement(
        subject="The generated client typechecks on the pinned toolchain",
        value="1.12-1.61 s (four samples: 1.12, 1.22, 1.57, 1.61)",
        kind=MACHINE,
        conditions=(
            "the same 8 GB development machine, WSL2, Docker server 29.5.2",
            "the toolchain image ALREADY BUILT AND CACHED; TypeScript 7.0.2",
            "`docker run --network none` over the committed example client"
            " mounted read-only -- container start included in the number",
            "9 emitted files, 31,097 bytes, `tsc --strict`",
        ),
        note=(
            "**This is the number a developer waits for**, because it is the "
            "one with a container in it: the generation is a third of a second "
            "and the check that the generation was right is four times that. "
            "The first run after the image is built took 2.72 s -- a warm-up "
            "the samples above do not repeat -- and building the image from "
            "scratch is a separate cost this row does not carry. Still: a "
            "capture, a regeneration and a full typecheck of the result is "
            "under two seconds, which is what makes `generate --check` "
            "affordable in a gate."
        ),
    ),
    # ---- what Studio costs (Session 24, STU-ENV-001) ---------------------
    #
    # Three rows because Studio has three costs a person feels and they are
    # different KINDS of cost: a launch that does everything once, a page that
    # does nothing, and a view that renders something already in memory. The
    # views that make an upstream call are deliberately absent -- those are a
    # deployment's numbers, and this envelope's rule is that a machine's number
    # describes that machine.
    Measurement(
        subject="apg studio: the command's own start",
        value="0.74 s, 0.66 s and 0.74 s (three samples)",
        kind=MACHINE,
        conditions=(
            "the same 8 GB development machine, WSL2, the checkout's venv",
            "process spawn to the printed `open http://...` line -- everything"
            " before a browser could connect",
            "a loopback deployment: `apg dev`, the auth application on uvicorn,"
            " the pinned PostgREST verifying its published JWKS and the pinned"
            " Traefik in front (rig 24e)",
            "project.example.yaml -- 3 relations, 4 RPCs, 7 tools and 1 enum,"
            " read back from the served `/__apg/schema` payload, not recalled",
            "an `authenticated` subject, so the surface answers `ok` (D1275)",
        ),
        note=(
            "**Everything is in this number**: the deployed document read, the "
            "IR built from four committed inputs, `POST /auth/login`, the "
            "session read that tells the launch which row is its own, the "
            "surface fetched as the human and compared, and the socket bound. "
            "Three quarters of a second, and `apg generate` measures 0.28 s for "
            "the same kind of work with no network in it -- so most of the "
            "difference is two round trips to a service on loopback."
        ),
    ),
    Measurement(
        subject="apg studio: the page, served from memory",
        value="1.3 ms, 3.1 ms and 2.4 ms (three samples, one per launch)",
        kind=MACHINE,
        conditions=(
            "the same 8 GB development machine, the same rig",
            "`curl -s -o /dev/null -w %{time_total}` carrying the launch cookie"
            " and `X-Apg-Studio`, so all five checks ran",
            "the three first-party assets -- index.html 4,217 bytes,"
            " studio.js 22,875 and studio.css 5,647 -- are read once at launch"
            " and served from memory; nothing is read from disk per request",
            "no surface size applies: this response is a static file and does"
            " not touch the IR, which is why it is published beside the view"
            " that does",
            "one sample per launch, because the launch is what varies",
        ),
        note=(
            "The spread across three launches is larger than any of the values, "
            "which is the honest thing to say about a number this small: it is "
            "scheduling noise, and a mean would imply a precision nobody has. "
            "**No upstream request happens here**, which is the point of the "
            "row and the contrast with the views that do make one."
        ),
    ),
    Measurement(
        subject="apg studio: the schema view",
        value="1.3 ms, 1.1 ms and 1.2 ms (three samples, one per launch)",
        kind=MACHINE,
        conditions=(
            "the same 8 GB development machine, the same rig, the same headers",
            "`GET /__apg/schema` -- 5,235 bytes of JSON over 3 relations,"
            " 4 RPCs, 7 tools and 1 enum",
            "the surface answered `ok`, so the view is served rather than 409",
            "one sample per launch",
        ),
        note=(
            "**The same cost as the static page, and that is the design.** This "
            "view is the IR rendered, and the IR was built once at launch from "
            "the checkout's own contracts -- so the request makes no upstream "
            "call and reaches no database. What it costs is JSON serialisation. "
            "The query, audit and roster views cost what the deployment costs "
            "and none of them is measured here."
        ),
    ),
    Measurement(
        subject="apg dev reset on a CI runner",
        value="6.19 s",
        kind=MACHINE,
        conditions=(
            "the same CI runner, ubuntu-latest, in the same step seconds later",
            "the locked postgres image cached by the `up` above it",
            "an environment that was running, seeded, with its 33 migrations applied",
            "one sample",
        ),
        note=(
            "Faster than the same verb on the development machine (10.07 s, "
            "10.28 s), which is what a `MACHINE` measurement is for: neither "
            "number is the product's, both are their machine's, and the "
            "envelope publishes them side by side rather than averaging them "
            "into a figure about nothing."
        ),
    ),
    # ---- the deployment's own numbers, taken ON the deployment ----------
    #
    # Session 31 Run 8, 2026-09-21, on the host, as root, after the trip's
    # sweep. Until this session the envelope carried an `Unmeasured` row here
    # saying every number in it was taken off-host and that **the
    # CONFIGURATION numbers transfer and the MACHINE numbers do not**. These
    # are the first figures in this document measured on the machine the
    # product actually runs on.
    Measurement(
        subject="doctor capacity: the whole-host reading, on the host",
        value="0.69 s wall (0.68 s for the single-project form)",
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host, no swap, 2 vCPU, eighteen containers",
            "two projects deployed at template 1.9.0, both healthy",
            "run as root; `time bin/doctor.sh capacity --host host.yaml`",
            "the Docker root read with df at the path the reading names, not /var/lib/docker",
            "**taken BEFORE Session 32 Run 2 repaired the ceilings grouping (D1636)**: "
            "the 2,944 MiB below is what the pre-repair reading produced, and the "
            "same command on the same host reports 4,480 MiB by compose project "
            "from template 1.10.0 onwards -- the wall time is unchanged, the "
            "figure is not",
        ),
        note=(
            "Sub-second, and that matters for what the reading is FOR: admission "
            "consults the same sum at a deploy's step 0, so the cost of deciding "
            "whether a project fits is noise beside the deploy it gates. Five "
            "groups ok -- declared 3,814 MiB and 37 GiB with 1,600 MiB claimable, "
            "2,067 MiB available, 22 GiB free, **608 MiB committed across two "
            "projects**, and a ceilings figure of 2,944 MiB that is WRONG BY "
            "DESIGN-FLAW and known (D1636): it excludes the database, the largest "
            "cap on the host, because `apg.project.key` is not applied to "
            "`postgres` or `pgbouncer` (D587). The real sum is 4,480 MiB against "
            "3,814 MB of RAM, which is D767's whole point -- and the number as "
            "reported under-states it in the REASSURING direction. **Repaired in "
            "Session 32 Run 2** (ADR 0221, D1636): the reading groups by "
            "`com.docker.compose.project`, which Compose applies to every "
            "container it creates, and a container carrying neither label is "
            "reported under `(unlabeled)` rather than dropped. The figure this "
            "row records is therefore the last reading of its kind."
        ),
    ),
    Measurement(
        subject="doctor usage: one project's eight figures, on the host",
        value="2.92 s wall, against 0.69 s for the capacity reading",
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host, run as root, immediately after a 1,030-proof sweep",
            "alpha-dev: the database sized, the pgBackRest repository sized, the "
            "agent record counted, and the project's own Prometheus queried",
            "beta-dev read in the same pass as the control",
        ),
        note=(
            "Four times the capacity reading, and the difference is where it goes: "
            "capacity reads manifests, a `df` and container labels, while usage "
            "reaches the database, the repository AND the store. Alpha returned "
            "`285 requests, 21 calls` -- **the sweep's own traffic, which is the "
            "first time this product has read its own telemetry back on "
            "production**. Beta returned `UNKNOWN: tool_calls_total could not be "
            "read; the store holds no such series yet` and the verb exited 6, "
            "because no agent tool call has ever been made there. That is the "
            "reading working: a Prometheus counter has no series until it is "
            "first incremented, and `exit_code` refuses to fold *no series* into "
            "*zero calls* (D1643, ADR 0195). **Session 32 Run 8 found that premise "
            "too narrow** (D1712): beta still read no series AFTER its first tool "
            "calls, with 100 audit rows on record, because each `mcp` process mints "
            "its own series set (D1609) and the sweep had recreated `mcp` after its "
            "last call. The reading is empty whenever the CURRENT agent-plane "
            "process has served no call -- not only when none was ever made."
        ),
    ),
    # ---- Session 32: the workflow loop, on the host ----------------------
    #
    # Session 32 Run 8, 2026-09-26, beta-dev's `auth` container read as root
    # through its cgroup on Sheets B1 and B4. Rig 32a measured the loop off-host
    # (ADR 0226: +8.1 MiB cgroup, +7.8 MiB RSS idle, against a 32 MiB flip
    # criterion); these are the same subject on the machine the product runs on.
    Measurement(
        subject="the auth container's memory with the workflow loop, on the host",
        value=(
            "53.56 MiB before (1.9.0, no loop) -> 54.91 MiB with the loop idle -> "
            "56.11 MiB after a worker restart, against a 384 MiB cap"
        ),
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host, no swap, beta-dev's `auth` container",
            "cgroup `memory.current`, read as root: 56,164,352 / 57,577,472 / 58,830,848 bytes",
            "BEFORE: the 1.9.0 container, five days old, no loop, read on Sheet B1",
            "WITH THE LOOP: the 1.10.0 container three minutes after its deploy, two "
            "definitions installed, no run ever made, heartbeat every poll",
            "AFTER RESTART: the same container ~30 s after `rehearse.sh worker-restart` "
            "SIGKILLed the process and the restart policy brought it back",
            "**NOT under a run** -- no figure was taken while a run executed (D1711); "
            "Session 35 read it: see the row below",
        ),
        note=(
            "+1.35 MiB with the loop and +2.54 MiB after the restart -- a fraction of "
            "rig 32a's +8.1 MiB and an order of magnitude inside ADR 0226's 32 MiB "
            "idle flip criterion. **The deltas are NOT the loop's cost alone**: the "
            "two sides are different processes of different ages, and "
            "`memory.current` counts page cache, which a five-day-old container "
            "has accumulated and a fresh one has not. What the figures DO establish "
            "is the absolute: 56 MiB against a 384 MiB cap, with the hash budget's "
            "four-concurrent 259 MiB the only other claimant on that headroom "
            "(`config.py:576-592`). The rig's delta stays the better estimate of "
            "the loop's own cost, because it held everything else still."
        ),
    ),
    # ---- Session 35: the act of changing a deployment, on the host --------
    #
    # Session 35 Run 10, 2026-10-02/03, both projects at 1.13.0 (f7fb96d). Each
    # number below was read from the trip's own files by
    # ~/s35r11/s35-r11-envelope.py and pasted, never retyped: the probe's gaps
    # documents (Sheets F2, F3, F4a, F7b), the neighbour sitting's four phase
    # documents (F7a) and the classifier's output over its sampler.
    Measurement(
        subject="A deploy's downtime for the rest class, through the edge, on the host",
        value=(
            "alpha-dev 10.2 s (bound 11.4 s), beta-dev 11.5 s (bound 12.7 s) unreachable "
            "through the edge during a 1.13.0 deploy"
        ),
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host, no swap, 2 vCPU",
            (
                "release 1.13.0 at f7fb96d, deployed 2026-10-02 (alpha 20:25:51-20:27:25Z, "
                "beta 20:30:21-20:31:55Z)"
            ),
            (
                "s35-r10-probe.py from the host as op: one unauthenticated GET per class every "
                "0.625 s, 8 req/s in total, 2 s timeout, through the public edge"
            ),
            (
                "down = a transport error, a 502/503/504 or Traefik's 404; the rest service "
                "was held back at step 5 and started at 6b, after the bootstrap (D1941)"
            ),
            "bound = observed + one probe interval either side; both projects idle otherwise",
        ),
        note=(
            "Measured, not predicted: the deploy prints no per-container line (D1941), and "
            "these windows are the caller's view of the restarts its after-read dated. Every "
            "deploy pays them -- step 5 brings a project up WITHOUT auth, mcp, postgrest and "
            "storage and step 6b starts them, whatever their image -- so a deploy is a 10-17 s "
            "outage of the API by design, not a defect. 0 x 429, 0 unexplained answers."
        ),
    ),
    Measurement(
        subject="A deploy's downtime for the auth class, through the edge, on the host",
        value=(
            "alpha-dev 16.4 s (bound 17.7 s), beta-dev 12.7 s (bound 13.9 s) unreachable "
            "through the edge during a 1.13.0 deploy"
        ),
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host, no swap, 2 vCPU",
            (
                "release 1.13.0 at f7fb96d, deployed 2026-10-02 (alpha 20:25:51-20:27:25Z, "
                "beta 20:30:21-20:31:55Z)"
            ),
            (
                "s35-r10-probe.py from the host as op: one unauthenticated GET per class every "
                "0.625 s, 8 req/s in total, 2 s timeout, through the public edge"
            ),
            (
                "down = a transport error, a 502/503/504 or Traefik's 404; the auth service "
                "was held back at step 5 and started at 6b, after the bootstrap (D1941)"
            ),
            "bound = observed + one probe interval either side; both projects idle otherwise",
        ),
        note=(
            "Measured, not predicted: the deploy prints no per-container line (D1941), and "
            "these windows are the caller's view of the restarts its after-read dated. Every "
            "deploy pays them -- step 5 brings a project up WITHOUT auth, mcp, postgrest and "
            "storage and step 6b starts them, whatever their image -- so a deploy is a 10-17 s "
            "outage of the API by design, not a defect. 0 x 429, 0 unexplained answers."
        ),
    ),
    Measurement(
        subject="A deploy's downtime for the storage class, through the edge, on the host",
        value=(
            "alpha-dev 16.4 s (bound 17.7 s), beta-dev 12.7 s (bound 14.0 s) unreachable "
            "through the edge during a 1.13.0 deploy"
        ),
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host, no swap, 2 vCPU",
            (
                "release 1.13.0 at f7fb96d, deployed 2026-10-02 (alpha 20:25:51-20:27:25Z, "
                "beta 20:30:21-20:31:55Z)"
            ),
            (
                "s35-r10-probe.py from the host as op: one unauthenticated GET per class every "
                "0.625 s, 8 req/s in total, 2 s timeout, through the public edge"
            ),
            (
                "down = a transport error, a 502/503/504 or Traefik's 404; the storage service "
                "was held back at step 5 and started at 6b, after the bootstrap (D1941)"
            ),
            "bound = observed + one probe interval either side; both projects idle otherwise",
        ),
        note=(
            "Measured, not predicted: the deploy prints no per-container line (D1941), and "
            "these windows are the caller's view of the restarts its after-read dated. Every "
            "deploy pays them -- step 5 brings a project up WITHOUT auth, mcp, postgrest and "
            "storage and step 6b starts them, whatever their image -- so a deploy is a 10-17 s "
            "outage of the API by design, not a defect. 0 x 429, 0 unexplained answers."
        ),
    ),
    Measurement(
        subject="A deploy's downtime for the mcp class, through the edge, on the host",
        value=(
            "alpha-dev 14.8 s (bound 16.1 s), beta-dev 14.2 s (bound 15.4 s) unreachable "
            "through the edge during a 1.13.0 deploy"
        ),
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host, no swap, 2 vCPU",
            (
                "release 1.13.0 at f7fb96d, deployed 2026-10-02 (alpha 20:25:51-20:27:25Z, "
                "beta 20:30:21-20:31:55Z)"
            ),
            (
                "s35-r10-probe.py from the host as op: one unauthenticated GET per class every "
                "0.625 s, 8 req/s in total, 2 s timeout, through the public edge"
            ),
            (
                "down = a transport error, a 502/503/504 or Traefik's 404; the mcp service was "
                "held back at step 5 and started at 6b, after the bootstrap (D1941)"
            ),
            "bound = observed + one probe interval either side; both projects idle otherwise",
        ),
        note=(
            "Measured, not predicted: the deploy prints no per-container line (D1941), and "
            "these windows are the caller's view of the restarts its after-read dated. Every "
            "deploy pays them -- step 5 brings a project up WITHOUT auth, mcp, postgrest and "
            "storage and step 6b starts them, whatever their image -- so a deploy is a 10-17 s "
            "outage of the API by design, not a defect. 0 x 429, 0 unexplained answers."
        ),
    ),
    Measurement(
        subject="A deploy's downtime for the docs class, through the edge, on the host",
        value=(
            "alpha-dev 12.5 s (bound 13.8 s), beta-dev 11.9 s (bound 13.1 s) unreachable "
            "through the edge during a 1.13.0 deploy"
        ),
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host, no swap, 2 vCPU",
            (
                "release 1.13.0 at f7fb96d, deployed 2026-10-02 (alpha 20:25:51-20:27:25Z, "
                "beta 20:30:21-20:31:55Z)"
            ),
            (
                "s35-r10-probe.py from the host as op: one unauthenticated GET per class every "
                "0.625 s, 8 req/s in total, 2 s timeout, through the public edge"
            ),
            (
                "down = a transport error, a 502/503/504 or Traefik's 404; the docs service "
                "was recreated at deploy step 5 (its mounted content moved, ADR 0155)"
            ),
            "bound = observed + one probe interval either side; both projects idle otherwise",
        ),
        note=(
            "Measured, not predicted: the deploy prints no per-container line (D1941), and "
            "these windows are the caller's view of the restarts its after-read dated. Every "
            "deploy pays them -- step 5 brings a project up WITHOUT auth, mcp, postgrest and "
            "storage and step 6b starts them, whatever their image -- so a deploy is a 10-17 s "
            "outage of the API by design, not a defect. 0 x 429, 0 unexplained answers."
        ),
    ),
    Measurement(
        subject="Recreating the edge: both projects unreachable, on the host",
        value="24.4 s observed on all four targets (bound 27.1 s), both projects at once",
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host, no swap, 2 vCPU",
            (
                "release 1.13.0 at f7fb96d, deployed 2026-10-02; `sudo bin/edge.sh --host "
                "host.yaml restart` 2026-10-02T20:33:50Z"
            ),
            (
                "traefik and docker-socket-proxy removed and recreated with their new limits "
                "(ADR 0244); the proxy healthy at 11.9 s, traefik at 21.7 s, then two networks "
                "reattached"
            ),
            "s35-r10-probe.py: rest and auth on each project, 4 targets every 0.625 s (6.4 req/s)",
        ),
        note=(
            "Every failed request was a refused connection: the shared ingress is ONE "
            "container, so its recreation is an outage of every project on the host for its "
            "whole start. This is the price of any change to the shared edge, and the reading "
            "a hosted design must beat."
        ),
    ),
    Measurement(
        subject="A database restart, induced by the rehearsal: what a caller sees, on the host",
        value=(
            "rest 3.1 s unreachable (bound 4.4 s, every answer a 503); auth, storage, mcp and "
            "docs no window; every dependent reconnected in 6.9 s"
        ),
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host, no swap, 2 vCPU",
            (
                "release 1.13.0 at f7fb96d, deployed 2026-10-02; `bin/rehearse.sh "
                "database-restart` on alpha-dev, 2026-10-03T05:30Z (evidence "
                "rehearsal-alpha-dev-database-restart-20261003053087a0)"
            ),
            (
                "INDUCED by the rehearsal (`docker restart -t 30` of the cluster), not a "
                "deploy and not an outage the product had"
            ),
            "s35-r10-probe.py: five classes on alpha every 0.625 s, 8 req/s",
        ),
        note=(
            "PostgREST answers 503 while its database is gone and recovers without a restart; "
            "the other classes' probe endpoints answer before any database, so their silence "
            "here says the route stayed, not that a database-backed call would have succeeded. "
            "No dependent restarted."
        ),
    ),
    Measurement(
        subject="The noisy neighbour, phase A: the other project's REST latency, on the host",
        value=(
            "alpha-dev p50/p95/p99 41.84/53.96/76.82 ms (n 481); beta-dev p50/p95/p99 "
            "41.18/53.0/77.46 ms (n 480), 0 errors, 0 x 429"
        ),
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host, no swap, 2 vCPU",
            (
                "release 1.13.0 at f7fb96d, deployed 2026-10-02; sitting c772ea89, "
                "2026-10-02T21:43-21:52Z, 120 s per phase"
            ),
            "both projects idle; delivery pass idle (no connector enabled, D1888)",
            (
                "the neighbour read by s35-r10-probe.py through the edge, GET <rest>/ at 8 "
                "req/s; the load from s35-r10-load.py inside the loaded project's own internal "
                "network (8 threads)"
            ),
        ),
        note="The baseline: both projects idle.",
    ),
    Measurement(
        subject="The noisy neighbour, phase B: the other project's REST latency, on the host",
        value=(
            "alpha-dev p50/p95/p99 41.15/55.36/74.23 ms (n 967), 0 errors, 0 x 429; 24 runs "
            "enqueued ({'201': 24}), statuses ['succeeded']"
        ),
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host, no swap, 2 vCPU",
            (
                "release 1.13.0 at f7fb96d, deployed 2026-10-02; sitting c772ea89, "
                "2026-10-02T21:43-21:52Z, 120 s per phase"
            ),
            (
                "beta-dev's step pass loaded by 24 runs of notes-roundtrip v1 enqueued at once "
                "by one probe agent; alpha-dev idle; delivery pass idle (D1888); the sampler "
                "ran from the window's start until every run had ended"
            ),
            (
                "the neighbour read by s35-r10-probe.py through the edge, GET <rest>/ at 8 "
                "req/s; the load from s35-r10-load.py inside the loaded project's own internal "
                "network (8 threads)"
            ),
        ),
        note="Workflow runs on one project do not move the other's latency at all.",
    ),
    Measurement(
        subject="The noisy neighbour, phase C: the other project's REST latency, on the host",
        value=(
            "beta-dev p50/p95/p99 49.58/107.78/156.62 ms (n 953), 0 errors, 0 x 429; the "
            "loaded side served 57,706 requests in 122.016 s = 472.94 req/s, all 200, "
            "p50/p95/p99 13.81/38.32/57.84 ms"
        ),
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host, no swap, 2 vCPU",
            (
                "release 1.13.0 at f7fb96d, deployed 2026-10-02; sitting c772ea89, "
                "2026-10-02T21:43-21:52Z, 120 s per phase"
            ),
            (
                "alpha-dev's REST loaded from inside its internal network (8 threads, GET "
                "/notes?limit=50 as a probe human); beta-dev idle; delivery pass idle (D1888)"
            ),
            (
                "the neighbour read by s35-r10-probe.py through the edge, GET <rest>/ at 8 "
                "req/s; the load from s35-r10-load.py inside the loaded project's own internal "
                "network (8 threads)"
            ),
        ),
        note=(
            "Saturating one project's REST moves its neighbour's p50 by ~8 ms and p95 by ~50 "
            "ms, with no error: the two share a CPU (2 vCPU), nothing else."
        ),
    ),
    Measurement(
        subject="The noisy neighbour, phase D: the other project's REST latency, on the host",
        value=(
            "alpha-dev p50/p95/p99 50.37/98.34/133.94 ms (n 957), 0 errors, 0 x 429; the "
            "loaded side served 59,888 requests in 122.008 s = 490.85 req/s, all 200, "
            "p50/p95/p99 13.76/35.27/50.49 ms"
        ),
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host, no swap, 2 vCPU",
            (
                "release 1.13.0 at f7fb96d, deployed 2026-10-02; sitting c772ea89, "
                "2026-10-02T21:43-21:52Z, 120 s per phase"
            ),
            (
                "beta-dev's REST loaded from inside its internal network (8 threads, GET "
                "/notes?limit=50 as a probe human); alpha-dev idle; delivery pass idle (D1888)"
            ),
            (
                "the neighbour read by s35-r10-probe.py through the edge, GET <rest>/ at 8 "
                "req/s; the load from s35-r10-load.py inside the loaded project's own internal "
                "network (8 threads)"
            ),
        ),
        note="The mirror of C, with the roles swapped; the same shape.",
    ),
    Measurement(
        subject="The auth container's memory WHILE workflow runs execute, on the host",
        value=(
            "median 63.13 MB, max 73.38 MB over 104 samples inside a run; outside 62.91 / "
            "73.61 MB (1108 samples) -- against ADR 0226's 96 MiB under-load criterion"
        ),
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host, no swap, 2 vCPU",
            (
                "release 1.13.0 at f7fb96d, deployed 2026-10-02; beta-dev's `auth`, neighbour "
                "sitting c772ea89 phase B, 2026-10-02T21:45Z"
            ),
            (
                "cgroup memory.current sampled every 0.1 s as op through /proc (D1739), the "
                "container resolved by its uvicorn cmdline and secrets mount (D1930)"
            ),
            (
                "24 runs of notes-roundtrip v1 enqueued at once by one probe agent, all "
                "succeeded, each 0.31-0.65 s; a sample is INSIDE when it falls between a run's "
                "started_at and finished_at (microseconds, D1876)"
            ),
            "the delivery pass idle (no connector enabled, D1888)",
        ),
        note=(
            "D1711 read at last, three trips after it was first owed: the step loop under 24 "
            "concurrent runs costs nothing measurable -- inside and outside differ by 0.2 MB "
            "at the median -- and the maximum stays under ADR 0226's 96 MiB criterion by more "
            "than 20 MB."
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
    Unmeasured(
        subject="apg dev up on this workstation with the image NOT cached",
        reason=(
            "The first `apg dev up` a developer ever runs pulls the locked postgres "
            "image, and that pull is most of what they will wait for. Measuring it "
            "here means `docker rmi` of the image **the whole contract suite shares** "
            "-- six cluster fixtures and the round trip -- so the measurement would "
            "cost every later test in the session a pull, and the number obtained "
            "would be this machine's link speed rather than anything about the "
            "product. CI measures the case instead: a fresh `ubuntu-latest` runner "
            "has cached nothing, and the round-trip step times the same two verbs "
            "there (D1168, D1169)."
        ),
        unblocked_by=(
            "nothing that should be run mid-session; the CI row is the measurement, "
            "and a developer wanting their own first-run number can time "
            "`docker pull` from versions.env"
        ),
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
