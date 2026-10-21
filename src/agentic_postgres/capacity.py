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
            "these windows are the caller's view of the restarts its after-read dated. "
            "D1941 read them as paid by every deploy; Session 36 corrected it (D2034): the same "
            "commit redeployed takes nothing away, a new commit recreates auth, mcp and "
            "storage, and rest and docs went here because 1.13.0 changed their own definitions "
            "(mem_limit). 0 x 429, 0 unexplained answers."
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
            "these windows are the caller's view of the restarts its after-read dated. "
            "D1941 read them as paid by every deploy; Session 36 corrected it (D2034): the same "
            "commit redeployed takes nothing away, a new commit recreates auth, mcp and "
            "storage, and rest and docs went here because 1.13.0 changed their own definitions "
            "(mem_limit). 0 x 429, 0 unexplained answers."
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
            "these windows are the caller's view of the restarts its after-read dated. "
            "D1941 read them as paid by every deploy; Session 36 corrected it (D2034): the same "
            "commit redeployed takes nothing away, a new commit recreates auth, mcp and "
            "storage, and rest and docs went here because 1.13.0 changed their own definitions "
            "(mem_limit). 0 x 429, 0 unexplained answers."
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
            "these windows are the caller's view of the restarts its after-read dated. "
            "D1941 read them as paid by every deploy; Session 36 corrected it (D2034): the same "
            "commit redeployed takes nothing away, a new commit recreates auth, mcp and "
            "storage, and rest and docs went here because 1.13.0 changed their own definitions "
            "(mem_limit). 0 x 429, 0 unexplained answers."
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
            "these windows are the caller's view of the restarts its after-read dated. "
            "D1941 read them as paid by every deploy; Session 36 corrected it (D2034): the same "
            "commit redeployed takes nothing away, a new commit recreates auth, mcp and "
            "storage, and rest and docs went here because 1.13.0 changed their own definitions "
            "(mem_limit). 0 x 429, 0 unexplained answers."
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
    # ---- Session 36: the sittings of 2026-10-04, on the host -----------------
    #
    # Session 36 Runs 9 and 10, both projects at 1.14.0. Each number below was read
    # from the trip's own files by ~/s36/run11/s36-envelope.py and pasted, never
    # retyped: the probe's gaps documents (R2a, R2b, R3, R5, X1-X3), the units
    # transcripts of the power-on and the reboot, the host readings and the D1581
    # instrument's diff. The server was NOT rescaled (D2032), so every MACHINE row
    # here ran on the same CX23 as Session 35's.
    Measurement(
        subject=(
            "A cold start on the host: the three units active after a power-on, and after a reboot"
        ),
        value=(
            "power-on: all three active 131 s after boot (the edge by 50 s, both projects by "
            "110 s); reboot: 124 s (the edge by 43 s, both projects by 104 s)"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 3,814 MB deployment host (Hetzner CX23, NOT rescaled -- D2032), no swap, "
                "2 vCPU Intel Xeon Processor (Skylake, IBRS, no TSX)"
            ),
            "kernel 7.0.0-34-generic on both boots (the power-on took it, D2031)",
            (
                "power-on 2026-10-04, boot 08:49:00Z, release 1.13.0 at f7fb96d; reboot "
                "2026-10-04, boot 10:26:50Z, release 1.14.0 at 2538ac0"
            ),
            (
                "s36-units.sh as op: `systemctl is-active` every 10 s on "
                "agentic-postgres-project@alpha-dev, @beta-dev and agentic-postgres-edge; done "
                "= all three active three readings in a row"
            ),
        ),
        note=(
            "Measured from the boot the kernel reports, so the BIOS and the console are not in "
            "it. The rescale sitting's whole outage was ~26 min per project (08:26:31Z "
            "poweroff -> ~08:52:30Z doctors), 22.5 of them powered off while a size was chosen "
            "at the console -- that is the operator's time, not the machine's, and it is not a "
            "rescale's cost (none was taken)."
        ),
    ),
    Measurement(
        subject="A deploy's downtime per class, through the edge, on the host: 1.13.0 -> 1.14.0",
        value=(
            "alpha-dev (R2a): auth 7.1 s (bound 9.6 s), mcp 12.5 s (bound 15.0 s), storage "
            "10.8 s (bound 13.3 s), rest 0 s, docs 0 s; beta-dev (R2b): auth 8.3 s (bound 10.8 "
            "s), mcp 12.5 s (bound 15.0 s), storage 8.3 s (bound 10.8 s), rest 0 s, docs 0 s; "
            "the neighbour 0 s on every class during each"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 3,814 MB deployment host (Hetzner CX23, NOT rescaled -- D2032), no swap, "
                "2 vCPU Intel Xeon Processor (Skylake, IBRS, no TSX)"
            ),
            (
                "release 1.14.0 at 7fa90c5 over 1.13.0, 2026-10-04 (alpha ended 08:59:01Z, "
                "beta 09:03:11Z)"
            ),
            (
                "s35-r10-probe.py from the host as op through the public edge: one "
                "unauthenticated GET per class and project every 1.25 s, 10 targets, 8 req/s "
                "in total, 2 s timeout"
            ),
            (
                "down = a transport error, a 502/503/504 or Traefik's 404; bound = observed + "
                "one interval either side"
            ),
            (
                "services/auth-api moved in this release; migrations 0038 and 0039 applied by "
                "each deploy"
            ),
        ),
        note=(
            "Only auth, mcp and storage were recreated (their containers created at the "
            "deploy; postgrest and docs kept the boot's) -- D2034. Session 35's rest and docs "
            "windows came from 1.13.0 changing those services' own definitions (mem_limit), "
            "not from every deploy."
        ),
    ),
    Measurement(
        subject="A deploy of a NEW commit that moves no product file, per class, on the host",
        value=(
            "alpha-dev: auth 8.3 s (bound 10.8 s), mcp 13.8 s (bound 16.2 s), storage 8.3 s "
            "(bound 10.8 s), rest 0 s, docs 0 s; beta-dev: auth 10.9 s (bound 13.4 s), mcp "
            "12.8 s (bound 15.4 s), storage 8.8 s (bound 11.2 s), rest 0 s, docs 0 s"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 3,814 MB deployment host (Hetzner CX23, NOT rescaled -- D2032), no swap, "
                "2 vCPU Intel Xeon Processor (Skylake, IBRS, no TSX)"
            ),
            (
                "7fa90c5 -> 2538ac0 (only bin/session-36-check.sh and two test modules moved), "
                "2026-10-04, alpha ended 09:32:27Z, beta 09:33:50Z, one after the other"
            ),
            (
                "s35-r10-probe.py from the host as op through the public edge: one "
                "unauthenticated GET per class and project every 1.25 s, 10 targets, 8 req/s "
                "in total, 2 s timeout"
            ),
            (
                "down = a transport error, a 502/503/504 or Traefik's 404; bound = observed + "
                "one interval either side"
            ),
        ),
        note="The agent predicted 0 s from R3 (the same commit) and was wrong -- D2034.",
    ),
    Measurement(
        subject=(
            "What a redeploy takes away (D1581, D1713): the same commit, a new commit, a "
            "changed definition"
        ),
        value=(
            "the SAME commit redeployed: nothing -- 10 of 10 containers UNTOUCHED (same id, "
            "StartedAt, 0 restarts), 0 down windows over 10 probe targets, the secret "
            "generation MOVED; a NEW commit: auth, mcp and storage recreated even when no "
            "product file moved; rest and docs only when their own definition changes"
        ),
        kind=CONFIGURATION,
        conditions=(
            (
                "deploy.sh step 5 brings a project up 'without auth,mcp,postgrest,storage' and "
                "6b starts them"
            ),
            (
                "s36-d1581.py as root: every project container's id, image, Created, "
                "StartedAt, RestartCount, before and after"
            ),
            (
                "R3 alpha-dev at 7fa90c5 twice (2026-10-04 09:06Z); R2 1.13.0 -> 1.14.0; R5 "
                "7fa90c5 -> 2538ac0"
            ),
        ),
        note=(
            "'up without' does not stop a running container: Compose leaves one whose "
            "definition did not change. What ties auth, mcp and storage to the COMMIT is not "
            "measured (the release directory is keyed by commit -- a hypothesis). The "
            "containers keep the generation they started with after a same-commit redeploy "
            "(D253's class: harmless while the values are identical)."
        ),
    ),
    Measurement(
        subject="A credential rotation's downtime on alpha, per class (X1 / X3; X2 took none)",
        value=(
            "X1 the authenticator / X3 the application credential: rest 97.2 / 85.3 s, auth "
            "96.8 / 85.5 s, mcp 94.7 / 84.1 s, storage 96.7 / 86.6 s, docs 56.3 / 46.2 s; X2 "
            "the documentation password, with no `down`: 0 s on every class; beta-dev 0 s "
            "throughout"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 3,814 MB deployment host (Hetzner CX23, NOT rescaled -- D2032), no swap, "
                "2 vCPU Intel Xeon Processor (Skylake, IBRS, no TSX)"
            ),
            (
                "release 1.14.0 at 2538ac0, 2026-10-04, X1 deploy ended 10:17:34Z, X2 "
                "10:21:13Z, X3 10:24:44Z"
            ),
            (
                "docs/api-operations.md's sequence: capture, the value replaced at Infisical "
                "by hand, project-runtime.sh down (X1, X3 only -- D2039), materialize, shape "
                "check, deploy"
            ),
            (
                "s35-r10-probe.py from the host as op through the public edge: one "
                "unauthenticated GET per class and project every 1.25 s, 10 targets, 8 req/s "
                "in total, 2 s timeout"
            ),
            (
                "down = a transport error, a 502/503/504 or Traefik's 404; bound = observed + "
                "one interval either side"
            ),
        ),
        note=(
            "The window runs from `down` to the deploy's 6b, so it includes the operator's "
            "pace between the lines (materialize and the shape check were typed by hand). A "
            "root-plane credential needs no `down` and costs nothing (ADR 0086)."
        ),
    ),
    # ---- Session 37: the sittings of 2026-10-06 and -07, on the host ---------
    #
    # Session 37 Runs 10 and 11: the control project brought up beside alpha and
    # beta, all three at 1.15.0. Each number below was read from the trips' own
    # files by ~/s37/run12/s37-envelope.py and pasted, never retyped: the s37-free
    # readings, C4's doctor capacity and C5's backup info (extracted verbatim from
    # the operator's pasted output), the deploy transcripts' script(1) times, the
    # probe's gaps documents and the units transcripts of Run 11's three reboots.
    # Still the CX23 (D2032).
    Measurement(
        subject="Three projects on the CX23: the memory the control project took, and what is left",
        value=(
            "available 2,145 MiB with alpha-dev and beta-dev (2026-10-06T12:14:37Z) -> 1,624 "
            "MiB with control-prod added (2026-10-06T20:24:42Z), used 1,669 -> 2,189 MiB; "
            "`doctor capacity`: 912 MiB committed of 1,600 claimable across 3 projects, 1,582 "
            "MiB available, ceilings 9,312 MiB of mem_limit across 4 compose projects"
        ),
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host (Hetzner CX23, NOT rescaled -- D2032), no swap, 2 vCPU",
            (
                "release 1.15.0; the before reading at 1.14.0 (Run 8's rehearsal), the after "
                "reading once C3's second control deploy ended"
            ),
            (
                "s37-free.sh as op (`free -m`; FITS at >= 1,024 MiB available, D2042); doctor "
                "capacity as root (Sheet C4)"
            ),
        ),
        note=(
            "Both readings FIT D2042's 1,024 MiB margin. 'committed' charges each project's "
            "declared budget (control-prod at the defaults: 912 of 1,600, D2042), never the "
            "caps (D767); the ceilings figure includes the edge's compose project and is a sum "
            "of caps, not a reservation."
        ),
    ),
    Measurement(
        subject="The control project's bring-up on the host: its deploys and its first full backup",
        value=(
            "the first deploy 183 s (C1b; the attempt before it stopped at step 6 after 55 s, "
            "exit 5, D2136), the ports render 5 s, the second deploy 172 s; the first full "
            "backup 5 min 32 s (32.7MB database, 4.2MB backup set); alpha-dev and beta-dev 0 "
            "down windows throughout"
        ),
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host (Hetzner CX23, NOT rescaled -- D2032), no swap, 2 vCPU",
            (
                "release 1.15.0, 2026-10-06 (C1 19:20Z, C1b 20:00Z, C3 20:18-20:22Z, backup "
                "20:25-20:31Z)"
            ),
            (
                "wall time from script(1)'s start and done lines; the backup from pgBackRest's "
                "own timestamps"
            ),
            (
                "s37-probe-start.sh from the host as op through the public edge (Session 35's "
                "s35-r10-probe.py): one unauthenticated GET per class and project every 1.25 "
                "s, 10 targets, 2 s timeout (alpha's and beta's five classes)"
            ),
        ),
        note=(
            "C1b includes the production certificate's issue on the one attempt (D2064) and "
            "the release's 39 migrations plus the control set's 3. A full backup prints "
            "nothing until it ends (Run 10's operator asked whether it hung at ~5 min)."
        ),
    ),
    Measurement(
        subject="A deploy's downtime per class, through the edge, on the host: 1.14.0 -> 1.15.0",
        value=(
            "beta-dev (R2b, 90 s): auth 17.1 s (bound 19.6 s), mcp 13.8 s (bound 16.2 s), "
            "storage 17.1 s (bound 19.6 s), rest 0 s, docs 0 s; alpha-dev 0 s on every class "
            "during it; alpha-dev's own deploy (R2a, 76 s) was not probed"
        ),
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host (Hetzner CX23, NOT rescaled -- D2032), no swap, 2 vCPU",
            (
                "release 1.15.0 at f58b471 over 1.14.0, 2026-10-06 (R2a 20:06-20:07Z, R2b "
                "20:08-20:10Z), three projects on the host"
            ),
            (
                "s37-probe-start.sh from the host as op through the public edge (Session 35's "
                "s35-r10-probe.py): one unauthenticated GET per class and project every 1.25 "
                "s, 10 targets, 2 s timeout"
            ),
            (
                "down = a transport error, a 502/503/504 or Traefik's 404; bound = observed + "
                "one interval either side"
            ),
        ),
        note=(
            "The same three services D2034 found tied to a new commit (auth, mcp, storage); "
            "rest and docs kept their containers. Alpha's window is unmeasured because R2a ran "
            "before the probe started (D2138); beta's stands for the release."
        ),
    ),
    Measurement(
        subject="A cold start with three projects: the four units after a reboot",
        value=(
            "before ADR 0255 (1.15.0 at f58b471): the edge active at boot+49 s, alpha-dev +109 "
            "s, control-prod +99 s, and beta-dev FAILED at +69 s (Infisical HTTP 429, D2139); "
            "after it (00a73f4, then c3eec1d): all four active three readings in a row 156 s "
            "and 156 s after boot, every unit started by the boot itself, NRestarts 0"
        ),
        kind=MACHINE,
        conditions=(
            "the 3,814 MB deployment host (Hetzner CX23, NOT rescaled -- D2032), no swap, 2 vCPU",
            "2026-10-07: boots 05:32:10Z (f58b471), 06:41:04Z (00a73f4), 08:40:02Z (c3eec1d)",
            (
                "s37-units.sh as op: `systemctl is-active` every 10 s on the three project "
                "units and the edge; done = all four active three readings in a row; 'started "
                "by the boot' = the unit left inactive before multi-user.target was reached "
                "(D2140)"
            ),
        ),
        note=(
            "Each unit materializes its secrets twice before Compose (~30 reads each), so a "
            "boot of three is ~180 provider reads in ~20 s against Infisical Cloud's free-plan "
            "120 a minute. Session 36's two-project boot took 124 s; three take ~156 s. "
            "Whether the client waited on a 429 in the later boots is not measured (its waits "
            "print nothing)."
        ),
    ),
    # ---- Session 38: the trip of 2026-10-09 and -10, on OVH (1.16.0) ----------
    Measurement(
        subject=(
            "Provisioning a managed project (project.create into the prepared slot, end to end)"
        ),
        value=(
            "1227 s from the reconciler's claim to succeeded (queued 1.9 s before it); the "
            "CLI's wait read 1234 s; steps: allocate 0.3, admit 0.7, deploy-1 71.6, admin 2.2, "
            "ports 1.8, deploy-2 46.5, unit 0.8, backup 1100.9, registry 0.2 s"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.16.0 at efaef09, 2026-10-10, operation 31d7eb2a, profile small",
            (
                "~/s38/run9/s38-lifecycle.py from the workstation as the probe owner, through "
                "the product's own CLI; each operation's created/started/finished read back "
                "through /v1, its steps from result.steps (D2171)"
            ),
        ),
        note=(
            "The first full backup is ~90% of it (pgBackRest process-max 1, D593, then the B2 "
            "mirror's first pass). Attempts 1-3 of the same day stopped at the mirror (D2311, "
            "D2315) and the sleep (D2314); their steps before the stop read within a few "
            "seconds of these."
        ),
    ),
    Measurement(
        subject="Deleting a managed project (project.delete, the slot consumed)",
        value=(
            "17.1 s from claim to succeeded (queued 1.5 s); steps: retire 16.0, tombstone 0.0, "
            "registry 0.2 s; the address answered the edge's 404 at once (4 of 4 samples)"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.16.0 at efaef09, 2026-10-10, operation abce2385",
            (
                "~/s38/run9/s38-lifecycle.py from the workstation as the probe owner, through "
                "the product's own CLI; each operation's created/started/finished read back "
                "through /v1, its steps from result.steps (D2171)"
            ),
        ),
        note=(
            "retire = project-retire.sh --permanent --destroy-data --defer-provider: the data "
            "and the volumes go, the provider's resources stay for slot.sh revoke (ADR 0257)."
        ),
    ),
    Measurement(
        subject="Sleep (project.sleep): the time to stop, and what a caller sees while asleep",
        value=(
            "16.5 s from claim to succeeded (queued 4.2 s); steps: schedule 3.2, unit 0.9, "
            "stop 11.4 s; asleep, 40 of 40 samples of the app route answered the edge's 404"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.16.0 at efaef09, 2026-10-10, operation a2123d67, profile small",
            (
                "~/s38/run9/s38-lifecycle.py from the workstation as the probe owner, through "
                "the product's own CLI; each operation's created/started/finished read back "
                "through /v1, its steps from result.steps (D2171)"
            ),
            (
                "the asleep samples: GET <routes.app>/auth/me from the workstation, 1 s apart, "
                "after succeeded"
            ),
        ),
        note=(
            "The time to the edge's FIRST 404 was not read (the instrument samples after the "
            "operation ends); the edge is detached before the stop, so it falls inside the "
            "'schedule' and 'stop' steps."
        ),
    ),
    Measurement(
        subject="Wake (project.wake): the cold start a caller sees",
        value=(
            "the first answer that was not the edge's 404 (401, /auth/me without a token) 19.3 "
            "s after the request; the operation 21.8 s from claim to succeeded (queued 2.0 s); "
            "steps: start 15.5, unit 0.8, schedule 4.6 s"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.16.0 at efaef09, 2026-10-10, operation b66b779e, profile small",
            (
                "~/s38/run9/s38-lifecycle.py from the workstation as the probe owner, through "
                "the product's own CLI; each operation's created/started/finished read back "
                "through /v1, its steps from result.steps (D2171)"
            ),
            (
                "the first answer: GET <routes.app>/auth/me from the workstation every 0.5 s "
                "from the request"
            ),
        ),
        note=(
            "ADR 0267's first proof of the same path on the rehearsal slot (profile large, the "
            "same day): sleep 21.6 s, wake 22.1 s, first answer 16.5 s."
        ),
    ),
    Measurement(
        subject="Resize: the restart a profile change causes (RESIZE_WINDOW_SECONDS, D2157)",
        value=(
            "84 s: small -> standard, the operation's deploy step 81.3 s (operation 3914872b, "
            "claim to succeeded 83.7 s); standard -> large 83.5 s (e9fb5c95, 86.0 s); admission "
            "read 304 and 840 MB requested against 4,620 MB safe available, both admitted"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            (
                "1.17.0 at 1c40860, 2026-10-12, slot2-prod (lifecycle attempt 3); 1c40860 is "
                "product-identical to the tagged b0249ce (D2415)"
            ),
            (
                "~/s39/run8/s39-lifecycle.py from the workstation as the probe owner, through "
                "the product's own CLI; each operation's created/started/finished read back "
                "through /v1, its steps and its admission reading from result (D2171, D2362)"
            ),
            (
                "the window is the resize's own deploy step (postgres and its dependents "
                "recreated with the new limits) -- an UPPER bound on the restart: the slot's "
                "routes were not probed (D2324)"
            ),
        ),
        note=(
            "Session 38 (1.16.0 at efaef09) read 70.5 s and 66.5 s and set the constant to 71; "
            "what the ~13-17 s more at 1.17.0 is spent on was not read. The constant follows "
            "the newest release's larger step, rounded up (Session 39's close)."
        ),
    ),
    Measurement(
        subject="Export (project.export): the archive and its time",
        value=(
            "39,900 bytes (the claimed, empty project's app and api schemas); 2.5 s from claim "
            "to succeeded (queued 2.3 s); steps: dump 0.3, upload 1.3 s; the one-time URL "
            "answered 200 at once and 403 after 930 s"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.16.0 at efaef09, 2026-10-10, operation f49b5f8e",
            (
                "~/s38/run9/s38-lifecycle.py from the workstation as the probe owner, through "
                "the product's own CLI; each operation's created/started/finished read back "
                "through /v1, its steps from result.steps (D2171)"
            ),
        ),
        note=(
            "An empty project: the time is the floor of the path, not a customer's; size and "
            "time scale with the customer's data, unmeasured. The rehearsal's CLI end to end "
            "(download and SHA-256 included) read 8.3 s."
        ),
    ),
    Measurement(
        subject="Memory with the customer slot (free -m `available`)",
        value=(
            "5,046 MiB available with the slot created (small, 2026-10-10T14:17:56Z); 5,634 "
            "MiB with it deleted (2026-10-10T17:37:23Z, after a reboot)"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "three projects (alpha-dev, beta-dev, control-prod) plus the slot, then without it",
            (
                "s38-free.sh as op (free -m only; docker stats is root's, D1375); FITS needs "
                ">= 1,024 MiB (D2145)"
            ),
        ),
        note=(
            "The difference (~590 MiB) is not the slot's cost: the two readings straddle a "
            "reboot and the page cache differs. Admission charges budgets, never this figure "
            "(D767)."
        ),
    ),
    Measurement(
        subject=(
            "A new commit's deploy on OVH: each class's window, per project (Run 12 R4, efaef09)"
        ),
        value=(
            "alpha-dev auth 9.6 s (bound 12.1 s), storage 14.5 s (bound 17.0 s), mcp 13.8 s "
            "(bound 16.2 s), rest 0 s, docs 0 s; beta-dev auth 9.5 s (bound 12.0 s), storage "
            "7.1 s (bound 9.6 s), mcp 13.7 s (bound 16.2 s), rest 0 s, docs 0 s; control-prod "
            "mcp 12.4 s (bound 13.6 s)"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            (
                "2026-10-10 ~12:39-12:45Z: alpha, beta, control-prod redeployed 7b2ff75 -> "
                "efaef09, one after the other, the reconciler stopped (D2178)"
            ),
            (
                "s38-probe-start.sh from the host as op through the public edge (Session 35's "
                "s35-r10-probe.py): one unauthenticated GET per class and project every 1.25 s "
                "(alpha, beta: 10 targets) and every 0.625 s (control-prod's mcp), 2 s timeout"
            ),
            (
                "down = a transport error, a 502/503/504 or Traefik's 404; bound = observed + "
                "one interval either side"
            ),
        ),
        note=(
            "The same three services D2034 found tied to a new commit (auth, mcp, storage); "
            "rest and docs kept their containers. The diff between the commits was compose.sh "
            "alone."
        ),
    ),
    Measurement(
        subject="The neighbours while a customer's project lives and dies beside them",
        value=(
            "no window on any of the 11 targets: 23,273 + 4,652 samples all up, through the "
            "creation, claim, sleep, wake, two resizes, export and deletion"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.16.0 at efaef09, 2026-10-10, 13:52-14:40Z (lifecycle attempt 4)",
            (
                "s38-probe-start.sh from the host as op through the public edge (Session 35's "
                "s35-r10-probe.py): one unauthenticated GET per class and project every 1.25 s "
                "(alpha, beta: 10 targets) and every 0.625 s (control-prod's mcp), 2 s timeout"
            ),
            (
                "down = a transport error, a 502/503/504 or Traefik's 404; bound = observed + "
                "one interval either side"
            ),
        ),
        note=(
            "Read from the neighbours' side only: no sample of theirs went down. What the "
            "slot's operations did to the shared edge was not read separately."
        ),
    ),
    Measurement(
        subject=(
            "A cold start with three projects on OVH: the five units after a reboot (ADR "
            "0265's proof)"
        ),
        value=(
            "all five active three readings in a row 100 s after boot, every unit started by "
            "the boot itself (left inactive before multi-user.target); NRestarts: edge 0, "
            "project@alpha-dev 0, project@beta-dev 0, project@control-prod 0, reconciler 1"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "booted 2026-10-10 14:42:21 UTC at efaef09 (Sheet B1, D2303)",
            (
                "s38-units.sh as op: `systemctl is-active` every 10 s on the three project "
                "units, the edge and the reconciler; 'started by the boot' as D2140 reads it"
            ),
        ),
        note=(
            "At 1.15.0 on this host every project unit FAILED at boot (D2291: the collector's "
            "healthcheck sized for a warm start); 1.16.0 carries ADR 0265. The reconciler "
            "restarted once during the boot (read, not repaired). On the CX23 a three-project "
            "cold start took 156 s."
        ),
    ),
    # ---- Session 39: the sittings of 2026-10-11 and -12, on OVH (1.17.0) ------
    Measurement(
        subject=(
            "Recreating the edge with the public Postgres entrypoint (Sheet E1): what every "
            "project loses"
        ),
        value=(
            "every class of alpha-dev, beta-dev and control-prod down 23.1 s (bound 25.8-26.4 "
            "s), alpha-dev's rest 24.4 s (bound 27.7 s), docs 13.75 s on both (bound 16.25 s); "
            "each window ended by up"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            (
                "2026-10-11, `bin/edge.sh --host host.yaml restart` adding the `postgres` "
                "entrypoint (:8432 published as 5432), before 1.17.0's first deploy (ADR 0268)"
            ),
            (
                "s39-probe-start.sh from the host as op through the public edge: one "
                "unauthenticated GET "
                "per class and project every 1.25 s (alpha, beta: 10 targets) and every 0.625 s "
                "(control-prod's mcp), 2 s timeout"
            ),
            (
                "down = a transport error, a 502/503/504 or Traefik's 404; bound = observed + "
                "one interval either side"
            ),
        ),
        note=(
            "The shared edge is one container: Session 35 read 24.4 s on the CX23. Every edge "
            "change pays this on every project at once."
        ),
    ),
    Measurement(
        subject="Provisioning a managed project at 1.17.0 (project.create, end to end), twice",
        value=(
            "slot2-prod 1210.7 s from the reconciler's claim to succeeded (queued 3.5 s), the "
            "CLI's wait 1217.4 s; steps allocate 0.8, admit 0.9, deploy-1 88.9, admin 2.1, ports "
            "2.2, deploy-2 59.9, unit 1.1, backup 1051.9, registry 0.3 s. slot3-prod 1156.3 s "
            "(queued 3.4 s), the CLI's 1164.8 s; backup 1006.7 s"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            (
                "1.17.0 at 1c40860, 2026-10-12, operations 85d48751 (slot2-prod, lifecycle "
                "attempt 3) and 4b936429 (slot3-prod, the kept project), profile small"
            ),
            (
                "~/s39/run8/s39-lifecycle.py from the workstation as the probe owner, through "
                "the product's own CLI; each operation's created/started/finished read back "
                "through /v1, its steps from result.steps (D2171)"
            ),
        ),
        note=(
            "The first full backup is ~87% of it, as at 1.16.0 (1,227 s, backup 1,100.9 s). "
            "Attempts 1 and 2 stopped before it succeeded (D2411, D2412)."
        ),
    ),
    Measurement(
        subject="A customer credential at 1.17.0 (credential.rotate, the CLI's credential)",
        value=(
            "a rotation 1.8-2.0 s from claim to succeeded (six operations; steps check 0.0-0.1, "
            "alter 0.2-0.3, sync 0.7 s; queued 0.2-4.9 s); both roles' credentials through the "
            "CLI (generate, verifier, wait) 17.3 s on slot2-prod and 22.7 s on slot3-prod; after "
            "the application role's rotation its old password was refused (exit 2) and the new "
            "one admitted"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.17.0 at 1c40860, 2026-10-12, slot2-prod and slot3-prod",
            (
                "~/s39/run8/s39-lifecycle.py from the workstation as the probe owner, through "
                "`bin/endpoint.sh credential --wait`; the operations' steps from result.steps"
            ),
        ),
        note=(
            "The password never leaves the workstation: the operation carries a SCRAM "
            "verifier (ADR 0269). 'sync' rewrites both customer poolers' lists."
        ),
    ),
    Measurement(
        subject="A TLS connection through each public name (pool.<domain>, direct.<domain>)",
        value=(
            "`bin/endpoint.sh connect` running one `select current_user`, process start to "
            "exit: slot2-prod pool 4.9 s, direct 3.4 s; slot3-prod pool 4.7 s, direct 3.3 s. "
            "psql alone, after each reboot: pool 2.7 s, direct 1.9 s (B1); 2.8 s, 2.0 s (B2)"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            (
                "1.17.0 at 1c40860 (2026-10-12 09:44Z, 10:45Z, and B1 11:01Z) and b0249ce (B2, "
                "12:49Z); sslmode=verify-full against the workstation's roots"
            ),
            "from the workstation, over the internet to Reston VA",
        ),
        note=(
            "Where the time goes (distance, TLS, SCRAM, the CLI's own start) was not split; "
            "the four drivers' own timings were not kept (13/13 passed)."
        ),
    ),
    Measurement(
        subject="Sleep and wake at 1.17.0 (project.sleep, project.wake) on slot2-prod",
        value=(
            "sleep 17.2 s from claim to succeeded (queued 3.8 s; schedule 3.8, unit 1.0, stop "
            "11.4 s); asleep, 40 of 40 app-route samples answered the edge's 404 and both "
            "public names refused (exit 2). Wake: the first answer that was not the edge's 404 "
            "(401) 23.1 s after the request; the operation 25.9 s (queued 1.8 s; start 18.6, "
            "unit 1.0, schedule 5.4 s)"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.17.0 at 1c40860, 2026-10-12, operations 2fa78e91 and bf22ca4b, profile small",
            (
                "~/s39/run8/s39-lifecycle.py from the workstation as the probe owner, through "
                "the product's own CLI; each operation's created/started/finished read back "
                "through /v1, its steps from result.steps (D2171)"
            ),
        ),
        note="Session 38 at 1.16.0: sleep 16.5 s, wake 21.8 s, first answer 19.3 s.",
    ),
    Measurement(
        subject="Export and deletion at 1.17.0 (project.export, project.delete) on slot2-prod",
        value=(
            "export 2.6 s and 2.7 s from claim to succeeded (dump 0.4, upload 1.5 s), 40,276 "
            "bytes holding api, app and public (no app_private); its URL answered 200 at once "
            "and 403 after 930 s. Delete 18.9 s (queued 1.5 s; retire 17.6, tombstone 0.0, "
            "registry 0.2 s); the address answered the edge's 404 at once (4 of 4)"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            (
                "1.17.0 at 1c40860, 2026-10-12, operations 85fd16f6, 527b104e and 7df91215; a "
                "near-empty project"
            ),
            (
                "~/s39/run8/s39-lifecycle.py from the workstation as the probe owner, through "
                "the product's own CLI; each operation's created/started/finished read back "
                "through /v1, its steps from result.steps (D2171)"
            ),
        ),
        note="An export of a project with data was not measured.",
    ),
    Measurement(
        subject="The neighbours while a customer's project lives and dies beside them (1.17.0)",
        value=(
            "no window on any of the 11 targets: 23,991 + 4,795 samples all up through the "
            "creation, three rotations, sleep, wake, two resizes, two exports and the deletion"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.17.0 at 1c40860, 2026-10-12, ~09:23-10:13Z (lifecycle attempt 3), 2,999 s",
            (
                "s39-probe-start.sh from the host as op through the public edge: one "
                "unauthenticated GET "
                "per class and project every 1.25 s (alpha, beta: 10 targets) and every 0.625 s "
                "(control-prod's mcp), 2 s timeout"
            ),
        ),
        note="Read from the neighbours' side only; the slot's own routes were not probed (D2324).",
    ),
    Measurement(
        subject="Memory available with four projects live (the customer's slot3-prod among them)",
        value=(
            "5,207 MiB available of 7,746 (used 2,538, buff/cache 3,254); with three projects "
            "(slot2-prod deleted, slot3-prod not yet created) 5,454 MiB"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            (
                "four projects: 2026-10-12 14:46Z, b0249ce, 2 h after the boot of 12:49Z; three: "
                "2026-10-12 10:25Z, 1c40860, before slot3-prod's creation"
            ),
            "`free -m` as op (docker stats is root's, D1375)",
        ),
        note=(
            "The ~250 MiB difference is not slot3-prod's cost: the readings straddle a reboot "
            "and the page cache differs. Admission charges budgets, never this figure (D767)."
        ),
    ),
    Measurement(
        subject="A cold start with four projects on OVH: six units after a reboot",
        value=(
            "the edge, four project units and the reconciler each active and started by the "
            "boot itself, NRestarts 0 on all six; all six first read active at boot+101 s (B1) "
            "and boot+102 s (B2), three readings in a row by boot+122 s; multi-user.target at "
            "boot+101 s and boot+96 s; 42 healthy containers after each"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "booted 2026-10-12 11:01:05Z at 1c40860 (B1) and 12:49:46Z at b0249ce (B2)",
            (
                "s39-after-reboot.sh as op, `systemctl is-active` every 10 s, read before the "
                "sweep ('started by the boot' as D2140 reads it)"
            ),
        ),
        note="Session 38's three-project cold start: 100 s, the reconciler restarted once.",
    ),
    # ---- Session 40: Sheet E0 and the sittings of 2026-10-14 to -16, on OVH (1.18.0) ----
    Measurement(
        subject="A drill on slot3-prod, the branch parent, before any branch (Sheet E0)",
        value=(
            "the repository 5,236,768 bytes, the cluster 145 MiB, 2,711 WAL archived / 0 "
            "failed, the last full 2026-10-12 10:39:26Z; a restore to a target time verified "
            "(achieved 08:08:14.473036, timeline 2): restore 288.5 s, recovery 217.9 s, RTO "
            "506.7 s; available 5,035 MiB before, 4,941 after; doctor 12 ok before and after"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.17.0 at b0249ce, 2026-10-14 08:18Z, four projects deployed",
            (
                "/home/op/s40-e0.sh as root (sha256 9ed449ac...): the readings, then one "
                "disposable drill (`--target-time '2026-10-14 08:08:15+00:00'`), nothing left"
            ),
        ),
        note=(
            "The baseline a branch of slot3-prod is read against (D2452): 506.7 s is under "
            "OPERATION_SECONDS less 300, so the bound was not raised."
        ),
    ),
    Measurement(
        subject="Provisioning a managed project at 1.18.0 (project.create, end to end)",
        value=(
            "slot4-prod 1,243.8 s from the operation's creation to succeeded; steps allocate "
            "0.8, admit 0.8, deploy-1 70.4, admin 1.5, ports 1.6, deploy-2 44.3, unit 0.8, "
            "backup 1,117.2, registry 0.2 s"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.18.0 at 8cc3440, 2026-10-15, operation 3bc297e3, profile small",
            (
                "~/s40/run7/s40-lifecycle.py from the workstation as the probe owner, through "
                "the product's own CLI; timed from the operation row (created_at..finished_at), "
                "because the instrument resumed inside the create after a transport blip (D2499)"
            ),
        ),
        note="The first full backup is ~90% of it (1.17.0: 1,217.4 s, backup 1,051.9 s).",
    ),
    Measurement(
        subject="The lifecycle's other operations at 1.18.0, on slot4-prod",
        value=(
            "credential.rotate x3 3.2-6.2 s (steps check 0.0, alter 0.1-0.2, sync 0.5-0.6 s; "
            "the old password refused, exit 2); sleep 38.9 s (stop 30.9 s); wake 21.6 s (start "
            "14.6 s), the first answer 18.1 s after it; resize small -> standard 67.2 s and "
            "standard -> large 70.2 s (deploy 60.7 / 63.9 s; admission read 304 and 840 MB "
            "against 4,428 MB safe available, both admitted); export 2.5 / 3.7 s (40,276 bytes; "
            "the URL 403 after its expiry); delete 19.3 s (retire 15.1 s); the second create "
            "refused no_slot with creations 8 -> 8"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.18.0 at 8cc3440, 2026-10-15 09:25-09:54Z",
            (
                "~/s40/run7/s40-lifecycle.py, each operation's created/finished and steps read "
                "back through /v1 (D2171), the admission reading from result (D2362)"
            ),
        ),
        note=(
            "RESIZE_WINDOW_SECONDS stays 84 (1.17.0's larger step, rounded up): 1.18.0's "
            "steps are under it, and the slot's pooled name was not read through them (D2500)."
        ),
    ),
    Measurement(
        subject=(
            "The resize and sleep windows as the slot's own app route saw them (D2444): "
            "the longest run of failed samples"
        ),
        value=(
            "resize small -> standard 10.0 s (9 of 61 samples failed), standard -> large "
            "10.0 s (5 of 63); sleep 89.7 s (39 of 41: the slot is asleep by design); wake "
            "16.0 s (12 of 40); every window covered; the four neighbours lost no sample"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.18.0 at 8cc3440, 2026-10-15, slot4-prod",
            (
                "s40-lifecycle.py's route probe from the workstation, holding no control-plane "
                "session: GET <app>/auth/me every 2 s, up only if answered within 5 s and not "
                "404/502/503/504; a window is the operation's started_at to finished_at plus "
                "60 s, the longest run measured start to start (one period of resolution)"
            ),
        ),
        note=(
            "The pooled name's probe died after 4 samples (D2500), so the database side of "
            "these windows stays UNMEASURED."
        ),
    ),
    Measurement(
        subject="A branch's operations on slot3-prod at 1.18.0 (ADR 0271, ADR 0272)",
        value=(
            "branch.create at the end (tmp) 635.1 s; restore.create at a point (dev, timeline "
            "2) 1,100.0 s; branch.reset 1,091.0 s, and 405.9 s after the reboot; branch.delete "
            "5.0 s (dev) and 7.9 s (tmp, requested by the reconciler 57.8 s after expires_at, "
            "origin expiry); each door answered on its first attempt, 4.5-6.4 s after ready"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            (
                "1.18.0 at 8cc3440, 2026-10-15 and -16, the parent slot3-prod (145 MiB, a "
                "quiet parent: E0's drill RTO 506.7 s)"
            ),
            (
                "~/s40/run7/s40-branches.py from the workstation as the probe owner, through "
                "the product's own CLI; each operation's created_at..finished_at read back "
                "through /v1"
            ),
        ),
        note=(
            "A create at a point and a reset sit within ~100 s of the reconciler's 1,200 s "
            "child budget (D2495). What the after-reboot reset saved was not read."
        ),
    ),
    Measurement(
        subject="A branch's memory, in the rig (rig 40c, D2431)",
        value=(
            "the branch's postgres at small 21.0 MiB idle, 24.2 MiB with 20 pooled clients "
            "(20/20 answered), 28.1 MiB after; each pooler 1.2-1.6 MiB of its 64; the 192 MiB "
            "charge is the budget, ~7x the resident reading"
        ),
        kind=MACHINE,
        conditions=(
            "the 8 GB development machine, WSL2, 2026-10-14 (Run 1), NOT the deployment host",
            (
                "~/s40/run1/rig40/rig40a.py: the project's own image built from versions.env "
                "at the small profile's limits, with two PgBouncers"
            ),
        ),
        note="The host's memory with a branch live was not read (UNMEASURED).",
    ),
    Measurement(
        subject="A cold start with four projects and a branch on OVH (B1)",
        value=(
            "the edge, four project units and the reconciler each active and started by the "
            "boot itself, NRestarts 0 on all six, active from boot+79-99 s, 42 healthy; the "
            "branch did NOT come back: the reconciler's start --all failed and its record "
            "read stopped (D2504)"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "booted 2026-10-15 21:55:26Z at 8cc3440, slot3-prod_dev ready before it",
            "read as op before the sweep ('started by the boot' as D2140 reads it)",
        ),
        note=(
            "branch.env pins the parent's image as an index id the boot's rebuild orphaned, "
            "so compose tried to pull it; one reset made the branch ready again."
        ),
    ),
    # ---- Session 41: the sittings of 2026-10-17, on OVH (1.19.0 at 601a0ea) ----------
    Measurement(
        subject="A new commit's deploy at 1.19.0, per project (R2a-R2d, twice)",
        value=(
            "each project's own auth, storage and mcp unanswered 5.6-11.3 s (control-prod's "
            "mcp 6.9-11.9 s), rest and docs never; the neighbours lost no sample; slot3-prod's "
            "door certificates byte-identical across slot.sh redeploy, both rounds"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "af694c6 then 601a0ea (the commit moved for D2556), 2026-10-17 09:05-10:29Z",
            (
                "/home/op/s35-r10-probe.py through the edge, 8 req/s, one label per sheet; the "
                "certificates read with openssl s_client from the workstation"
            ),
        ),
        note="The same shape as 1.17.0 and 1.18.0 (D2034): a new commit recreates the three.",
    ),
    Measurement(
        subject="Provisioning a managed project at 1.19.0 (project.create, end to end)",
        value=(
            "slot5-prod 1,715.2 s from the request to succeeded (the row 1,709.6 s); steps "
            "allocate 1.0, admit 0.7, deploy-1 69.8, admin 1.7, ports 1.6, deploy-2 44.0, unit "
            "0.9, backup 1,588.1 s; 4,459 MiB available with the slot (FITS)"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.19.0 at 601a0ea, 2026-10-17 11:42-12:10Z, operation 44e33232, profile small",
            (
                "~/s41/run8/s41-lifecycle.py from the workstation as the probe owner, in its "
                "own organisation lifecycle-s41, through the product's own CLI"
            ),
        ),
        note=(
            "The first full backup is 93% of it, and 471 s longer than 1.18.0's (1,117.2 s): "
            "read, not explained."
        ),
    ),
    Measurement(
        subject="The lifecycle's other operations at 1.19.0, on slot5-prod",
        value=(
            "credential.rotate x3 1.3-1.4 s (check 0.0, alter 0.2, sync 0.5 s); sleep 15.8 s "
            "(stop 11.0 s); wake 20.2 s (start 14.3 s), the first answer 16.8 s after it; resize "
            "small -> standard 66.5 s and standard -> large 65.4 s (deploy 64.7 / 63.7 s; "
            "admission read 304 and 840 MB against 4,428 MB safe available, both admitted); "
            "export 2.0 / 1.9 s (40,286 bytes; the URL 200 at once, 403 after its 900 s); delete "
            "16.2 s (retire 15.3 s); the second create refused no_slot, creations 1 -> 1"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.19.0 at 601a0ea, 2026-10-17 12:10-13:29Z",
            (
                "s41-lifecycle.py, each operation's created/finished and steps read back "
                "through /v1; the first export failed on a mis-entered credential and the run "
                "resumed at it (D2557)"
            ),
        ),
        note="RESIZE_WINDOW_SECONDS stays 84: both resizes' deploy steps are under it.",
    ),
    Measurement(
        subject="Idle sleep: from the setting to the sleep (ADR 0276)",
        value=(
            "set to 15 minutes at 13:07:12Z with the slot's probes paused; the reconciler's "
            "project.sleep (origin idle) requested 1,121.4 s later (18.7 min, within the "
            "1,620 s bound), asleep 21.1 s after that; both names refused while it slept"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.19.0 at 601a0ea, 2026-10-17, slot5-prod, the reconciler's 300 s sampler",
            "s41-lifecycle.py's idle step; the operation read back through /v1",
        ),
        note=(
            "15 minutes of quiet samples, then the next pass: the request lands between 15 "
            "and 25 minutes after the last activity by design."
        ),
    ),
    Measurement(
        subject="A branch's operations on slot3-prod at 1.19.0",
        value=(
            "branch.create at the end (tmp) 718.1 s (runtime 717.3); restore.create at a point "
            "(dev, timeline 2) 645.5 s; branch.reset 628.2 s; branch.delete 2.9 s (tmp, "
            "requested by the reconciler 22.3 s after expires_at, origin expiry) and 3.3 s "
            "(dev); each door answered its FIRST connect at ready (D2503)"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.19.0 at 601a0ea, 2026-10-17, the parent slot3-prod",
            (
                "~/s41/run8/s41-branches.py from the workstation as the probe owner, through "
                "the product's own CLI; created_at..finished_at read back through /v1"
            ),
        ),
        note="A create at a point and a reset are 455-472 s faster than 1.18.0's.",
    ),
    Measurement(
        subject="The host's memory with a branch live (Sheet M1, D2509)",
        value=(
            "4,884 MiB available (free -m; doctor capacity 4,875 of 7,745), the branch charged "
            "192 MiB of 1,296 committed; its three containers 24.3 MiB (postgres, of 512) + "
            "1.5 + 3.0 MiB (the poolers, of 64)"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "1.19.0 at 601a0ea, 2026-10-17 ~14:35Z, slot3-prod_dev ready, four projects",
            "the operator's free -m, doctor capacity and docker stats --no-stream",
        ),
        note="The charge is ~6.6x the resident reading (rig 40c: ~7x).",
    ),
    Measurement(
        subject="A cold start with four projects and a branch on OVH (B1, 1.19.0)",
        value=(
            "the edge, alpha-dev, control-prod, slot3-prod and the reconciler started by the "
            "boot itself, active by boot+79-89 s; beta-dev's unit FAILED at boot+89 s (its "
            "edge reconcile lost a race with control-prod's, D2558) and was started by the "
            "operator; the branch came back BY ITSELF and apg-diag listed it (D2504 repaired)"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 7,745 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 4 "
                "vCPU, no swap"
            ),
            "booted 2026-10-17 14:44:11Z at 601a0ea, slot3-prod_dev ready before it",
            "read as op before the sweep (s41-units.sh, D2140)",
        ),
        note="Session 40's boot did not lose the race; whether one does is timing.",
    ),
    # ---- Session 42: the upgrade of 2026-10-18, the sittings of 2026-10-19 (1.20.0 at 77303e4)
    Measurement(
        subject="The upgraded host's capacity (sitting U, D2628; Session 36's D1991 rescale)",
        value=(
            "11,671 MiB, 6 vCPU, 95 GiB declared (was 7,745 / 4 / 71); doctor capacity 9,457 MiB "
            "claimable (was 5,532), 9,222 available with four projects; after the telemetry "
            "plane: 4,656 MiB committed of which the plane 3,552, ceilings 15,872 MiB across 6; "
            "8,208 MiB available before the lifecycle, 7,603 with slot6-prod live"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 11,671 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 6 "
                "vCPU, no swap, upgraded 2026-10-18"
            ),
            "the model changed in the OVHcloud manager; OVH rebooted the host 2026-10-18 08:35:47Z",
            "doctor capacity (U3, T1) and s42-free.sh's free -m (2026-10-19)",
        ),
        note="The IPv4 and the SSH host key were kept; the upgrade was a reboot, not a move.",
    ),
    Measurement(
        subject="The telemetry plane under load on the host (Sheet E1, ADR 0277)",
        value=(
            "100 lines/s for 1,800 s: 179,997 of 180,000 rows, every row stamped with the "
            "sending project; memory.peak ClickHouse 250 MiB (182 pids), HyperDX 425 MiB (54), "
            "MongoDB 98 MiB (64), the gateway ~49 MiB (docker stats); a reader query 96-115 ms "
            "each minute; the host's lowest available 8,324 MiB; 911 KiB on disk"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 11,671 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 6 "
                "vCPU, no swap, upgraded 2026-10-18"
            ),
            "2026-10-18 08:52-09:23Z, the stack at ADR 0277's limits, no published port",
            (
                "s42-e1.sh as root, telemetrygen into a stand-in collector; E0's real rate "
                "~0.75 lines/s"
            ),
        ),
        note=(
            "HyperDX's limit moved to 1,728 MiB from this reading (4 x 425, D2626); the plane's "
            "charge is 3,552 MiB, its four limits."
        ),
    ),
    Measurement(
        subject="1.20.0's deploy, per project and class (R2a-R2d, pg_stat_statements loaded)",
        value=(
            "each database restarted once; unanswered: alpha-dev rest 3.2 s (503) and auth 7.6 s "
            "(404/502); beta-dev 4.2 and 8.5 s; control-prod auth 8.7 s (no rest route); "
            "slot3-prod (slot.sh redeploy) 2.1 and 8.4 s; every deploy exit 0"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 11,671 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 6 "
                "vCPU, no swap, upgraded 2026-10-18"
            ),
            "77303e4, 2026-10-19 05:14-05:25Z, one project at a time",
            (
                "~/s42/run8/s42-window.py from the workstation, one GET a second per class: rest "
                "= PostgREST's root, auth = routes.app/auth/me, each answer written as taken"
            ),
        ),
        note="The release restart costs seconds per project; the neighbours were not probed by it.",
    ),
    Measurement(
        subject="Provisioning a managed project at 1.20.0 (project.create, end to end)",
        value=(
            "slot6-prod 1,375.9 s from the request to succeeded (the instrument's 1,384.5 s); "
            "steps allocate 1.0, admit 0.8, deploy-1 63.8, admin 1.4, ports 1.4, deploy-2 41.2, "
            "unit 0.9, backup 1,259.1, registry 0.2 s; 7,603 MiB available with the slot (FITS)"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 11,671 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 6 "
                "vCPU, no swap, upgraded 2026-10-18"
            ),
            "1.20.0 at 77303e4, 2026-10-19 08:32-08:55Z, operation 453f9279, profile small",
            (
                "~/s42/run8/s42-lifecycle.py from the workstation as the probe owner, in its "
                "own organisation lifecycle-s42, through the product's own CLI"
            ),
        ),
        note=(
            "The first full backup is 92% of it, and 329 s shorter than 1.19.0's (1,588.1 s): "
            "read, not explained."
        ),
    ),
    Measurement(
        subject="The lifecycle's other operations at 1.20.0, on slot6-prod",
        value=(
            "credential.rotate x3 1.7, 5.1, 4.4 s (check 0.0, alter 0.1-0.2, sync 0.4-0.5 s: the "
            "rest is the wait to be claimed); sleep 19.6 s (stop 11.1 s); wake 20.1 s (start "
            "13.1 s), the first answer 15.1 s after it; resize small -> standard 59.4 s and "
            "standard -> large 58.8 s (deploy 57.5 / 56.3 s; 304 and 840 MiB against 4,801 MiB "
            "safe, both admitted); export 1.9 / 9.2 s (40,286 bytes; the URL 200 at once, 403 "
            "after its 900 s); delete 16.4 s (retire 14.8 s); the second create refused no_slot"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 11,671 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 6 "
                "vCPU, no swap, upgraded 2026-10-18"
            ),
            "1.20.0 at 77303e4, 2026-10-19 08:55-09:50Z",
            "s42-lifecycle.py, each operation's created/finished and steps read back through /v1",
        ),
        note="RESIZE_WINDOW_SECONDS stays 84: both resizes' deploy steps are under it.",
    ),
    Measurement(
        subject="The sleep, wake and resize windows as the slot's names see them (D2171, D2444)",
        value=(
            "longest unanswered run, the app route / the pooled name: sleep 71.5 / 71.8 s; wake "
            "12.0 / 16.8 s; resize to standard 8.6 / 16.8 s; resize to large 8.6 / 16.8 s; every "
            "window covered on both, 1,816 samples sealed"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 11,671 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 6 "
                "vCPU, no swap, upgraded 2026-10-18"
            ),
            "1.20.0 at 77303e4, 2026-10-19, slot6-prod, from the workstation",
            (
                "s42-lifecycle.py's probe threads every 2 s, each sample appended and fsynced as "
                "taken (D2581); a sample that could not be taken counts as failed"
            ),
        ),
        note="The first lifecycle to read the pooled name through every window (D2500, D2557).",
    ),
    Measurement(
        subject="Idle sleep: from the setting to the sleep (ADR 0276)",
        value=(
            "set to 15 minutes at 09:26:17Z with the slot's probes paused; the reconciler's "
            "project.sleep (origin idle) requested 1,200.4 s later (20.0 min, within the "
            "1,620 s bound), asleep 20.5 s after that; both names refused; woken in 22.9 s"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 11,671 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 6 "
                "vCPU, no swap, upgraded 2026-10-18"
            ),
            "1.20.0 at 77303e4, 2026-10-19, slot6-prod, the reconciler's 300 s sampler",
            "s42-lifecycle.py's idle step; the operation read back through /v1",
        ),
        note="Session 41 read 1,121.4 s: the request lands between 15 and 25 minutes by design.",
    ),
    Measurement(
        subject="Query Insights after a known workload (ADR 0278, INS-LIVE-001)",
        value=(
            "one call (4.2 s through the pooled door), a sample at 09:00:33Z, 200 calls in "
            "40.5 s, the next sample at 09:05:37Z (304 s later); insights show held the "
            "statement normalised with exactly 200 calls, as the slot's customer_app role, "
            "its literal nowhere"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 11,671 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 6 "
                "vCPU, no swap, upgraded 2026-10-18"
            ),
            "1.20.0 at 77303e4, 2026-10-19 08:56-09:06Z, slot6-prod awake",
            "s42-lifecycle.py through bin/endpoint.sh connect --role app and bin/insights.sh show",
        ),
        note="A statement's first sample counts nothing, so one call goes first (ADR 0278).",
    ),
    Measurement(
        subject="A branch's operations on slot3-prod at 1.20.0",
        value=(
            "branch.create at the end (tmp) 571.5 s (runtime 566.2); restore.create at a point "
            "(dev) 486.9 s; branch.reset 474.5 s; branch.delete 7.8 s (tmp, requested by the "
            "reconciler, finished 125.2 s after expires_at, origin expiry) and 4.5 s (dev); "
            "each door answered its FIRST connect at ready"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 11,671 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 6 "
                "vCPU, no swap, upgraded 2026-10-18"
            ),
            "1.20.0 at 77303e4, 2026-10-19 09:51-11:29Z, the parent slot3-prod",
            (
                "~/s42/run8/s42-branches.py from the workstation as the probe owner, through "
                "the product's own CLI; created_at..finished_at read back through /v1"
            ),
        ),
        note=(
            "Each of create, a point and reset is 147-159 s faster than 1.19.0's; tmp's expiry "
            "took 125.2 s against 1.19.0's 22.3 s -- read, not explained."
        ),
    ),
    Measurement(
        subject="A cold start with four projects, the plane and a branch on OVH (B1, 1.20.0)",
        value=(
            "all seven units -- the edge, the four projects, the reconciler and the telemetry "
            "plane -- started by the boot itself, NRestarts 0, active by boot+69 s (three "
            "readings by boot+89 s); the plane's four containers and the branch's three up; "
            "the branch ready by itself (D2558 repaired)"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 11,671 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 6 "
                "vCPU, no swap, upgraded 2026-10-18"
            ),
            "booted 2026-10-19 10:35:33Z at 77303e4, slot3-prod_dev ready before it",
            "read as op before the sweep (s42-units.sh, D2140)",
        ),
        note="Session 41's boot failed beta-dev's unit on the edge's attach race; this did not.",
    ),
    Measurement(
        subject="The host suite's duration at 1.20.0",
        value=(
            "V1 (writing nothing, no lifecycle or branch proofs): 405 passed in 37 min 04 s; "
            "the sweep's suite (every proof, after the reboot): 425 passed, 1 failed, in "
            "45 min 18 s; the whole sweep 10:38:59-11:27:52Z"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 11,671 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 6 "
                "vCPU, no swap, upgraded 2026-10-18"
            ),
            "77303e4, 2026-10-19, four projects and the plane up",
            "s42-v1.sh and s42-sweep.sh as root, stdin from /dev/null",
        ),
        note="Session 41's V1 took 44.5 min and its sweep 53.6 min on the 4 vCPU host.",
    ),
    # ---- Session 43: the console rig of 2026-10-20, the sitting of 2026-10-21 (1.21.0 at 012ac06)
    Measurement(
        subject="The console service's footprint (Run 4's rig, ADR 0280)",
        value=(
            "image 43,209,566 B; 28.6 MB at rest; 1,008 requests in 14.2 s -> memory.peak "
            "44.07 MiB, pids.peak 8, healthy throughout; limits set from it: 192 MiB, 64 pids, "
            "0.25 CPU (D2699)"
        ),
        kind=MACHINE,
        conditions=(
            "the operator's development machine (Windows 11, WSL 2, Docker Desktop)",
            "2026-10-20, the console image built from the tree, no other load",
            "~/s43/run4/measure.txt: cgroup memory.peak and pids.peak read after the burst",
        ),
        note=(
            "On the deployment host console_live_host read the container bounded at these "
            "limits and healthy; its own peak there was not read (op cannot reach the Docker "
            "socket, D1375)."
        ),
    ),
    Measurement(
        subject="1.21.0's deploy, per project and class (R2a-R2d, no database restart)",
        value=(
            "auth unanswered beta-dev 9.4 s, alpha-dev 9.3 s, slot3-prod (slot.sh redeploy) "
            "6.6 s, control-prod 7.0 s (404/502); rest never unanswered on any; the console "
            "first answered 200 41 s into control-prod's window and never failed after; every "
            "deploy exit 0"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 11,671 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 6 "
                "vCPU, no swap"
            ),
            "012ac06, 2026-10-21 05:51-06:03Z, one project at a time, the reconciler stopped",
            (
                "~/s43/run8/s43-window.py from the workstation, one GET a second per class, "
                "each answer written as taken"
            ),
        ),
        note="Session 42's release, which restarted each database, cost rest 2.1-4.2 s.",
    ),
    Measurement(
        subject="The console in a real browser: first paint and invitation to connection string",
        value=(
            "first contentful paint 1,140 / 1,008 / 1,060 ms (W0) and 1,024 / 900 / 1,028 ms "
            "(W1); DOMContentLoaded 1,158-1,442 ms; from opening the invitation link to the "
            "connection string with the rotated password on the Connect page 26.1 s, the "
            "account, the second factor and the sign-in included"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the operator's development machine (Windows 11, WSL 2), reaching "
                "control.agenticpostgresql.com on the deployment host over the public internet"
            ),
            "Chromium 153.0.8010.12 in the pinned Playwright 1.63.0 image, --network host",
            "1.21.0 at 012ac06, 2026-10-21 07:24Z (W0) and 07:29Z (W1)",
        ),
        note=(
            "Named as from the operator's workstation (D2675): the time is the driver's, typing "
            "at machine speed, not a person's."
        ),
    ),
    Measurement(
        subject="The fifth re-earning: slot7-prod's lifecycle at 1.21.0",
        value=(
            "create 1,378.0 s; wake's first answer 16.6 s; the slot's names unanswered during "
            "sleep 69.4 / 72.2 s, wake 14.0 / 17.9 s, the standard resize 8.0 / 17.9 s and the "
            "large 10.0 / 17.6 s (route / pool); the export link refused 930 s after it was "
            "read; 8,111 MiB available before, 7,510 with the slot live; the neighbours "
            "through 5,199 s: 0 unanswered"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 11,671 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 6 "
                "vCPU, no swap"
            ),
            "012ac06, 2026-10-21 08:01-09:27Z, organisation lifecycle-s43",
            (
                "s43-lifecycle.py from the workstation, its samples written as taken (D2581); "
                "the neighbours by s43-probe-start.sh on the host"
            ),
        ),
        note="Session 42's slot6-prod: create 1,384.5 s, wake 15.1 s.",
    ),
    Measurement(
        subject="A usage pass's duration (ADR 0275)",
        value="1.0 s for slot3-prod, the one awake slot",
        kind=MACHINE,
        conditions=(
            (
                "the 11,671 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 6 "
                "vCPU, no swap"
            ),
            "012ac06, 2026-10-21 08:00:19Z, the reconciler's first pass after RC1's restart",
            "the reconciler's own line 'usage pass for <key>: <s> s' (bin/reconciler.py)",
        ),
        note="One reading of one slot; Session 42 listed it UNMEASURED.",
    ),
    Measurement(
        subject="Branches at 1.21.0 (slot3-prod)",
        value=(
            "an expired branch deleted by the reconciler 52.3 s after expires_at (Session 42: "
            "125.2 s); the restore window's top passed a mark 505.7 s after it was written; "
            "every unit and the branch back by themselves after a reboot, all active by "
            "boot+79 s"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 11,671 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 6 "
                "vCPU, no swap"
            ),
            "012ac06, 2026-10-21 09:29-10:20Z, the reboot at 10:17:34Z",
            "s43-branches.py from the workstation; s43-after-reboot.sh",
        ),
        note="The expiry is a reconciler pass's spacing, not a promise.",
    ),
    Measurement(
        subject="The host suite's duration at 1.21.0",
        value=(
            "V1 (writing nothing, no lifecycle or branch proofs): 408 passed, 1 failed, in "
            "40 min 26 s; the sweep's suite (every proof, after the reboot): 428 passed, 1 "
            "failed, in 47 min 16 s; the external half 115 passed, 3 failed, in 11 min 04 s"
        ),
        kind=MACHINE,
        conditions=(
            (
                "the 11,671 MiB deployment host apg-ovh-01 (OVH VPS US-East, Reston VA), 6 "
                "vCPU, no swap; the external half from the operator's development machine"
            ),
            "012ac06, 2026-10-21, four projects and the plane up",
            "s43-v1.sh and s43-sweep.sh as root, stdin from /dev/null; s43-external.sh",
        ),
        note="Session 42's: V1 37 min 04 s, the sweep's suite 45 min 18 s.",
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
        subject="Whether a boot of three projects meets the provider's rate limit",
        reason=(
            "ADR 0255's client waits on a 429 silently; the two boots after it took ~30 s longer "
            "than the morning's, which a wait would explain and does not prove (D2139)."
        ),
        unblocked_by="a counted wait in the materializer's output, or the provider's log",
    ),
    Unmeasured(
        subject="The telemetry plane's footprint at rest on the host (ADR 0277)",
        reason=(
            "E1 read the plane under load and was torn down; after T1 installed it no sheet took "
            "its containers' docker stats at rest (op cannot reach the Docker socket, D1375), and "
            "a free -m difference across the day's other changes is not its footprint."
        ),
        unblocked_by="a root docker stats --no-stream of the four apg-telemetry containers, idle",
    ),
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
