# 0165 — A telemetry component carries an explicit memory limit, because its default is a share of somebody else's machine

- **Status:** accepted
- **Date:** 2026-09-01
- **Session:** 14, Run 2 (`CAP-ENV-001`, D770)
- **Related:** **D770** (measured: a store sizes its caches from the machine it
  finds), **D761** (no swap, so an OOM is a kill), **D767** (measured: the
  memory caps on this host already exceed its RAM, and the databases hold ~37 MB
  against 768 MB each), ADR 0131 (`MCP_MEMORY_LIMIT_MB`, and what it actually
  measured), ADR 0164 (the surface these components serve).

## Context

Session 14 adds the first components to this deployment whose memory
consumption is **a function of the machine rather than of the workload**.

Every service deployed before this one holds roughly what its work requires: the
two PostgreSQL containers hold about 37 MB each including shared memory, the MCP
runtimes 88–89 MB, PostgREST about 20 MB. Their `memory.max` values bound them
from above and are otherwise not consulted by the processes inside.

A time-series store does not behave that way. Measured against
`victoriametrics/victoria-metrics`, unbounded, on a 7,786 MB development
machine, it logs its own intention on startup:

```
limiting caches to 4898660352 bytes, leaving 3265773568 bytes to the OS
according to -memory.allowedPercent=60, system memory limit 8164433920 bytes
```

**4.9 GB of caches, decided by reading the machine.** The deployment host has
3,814 MB and **no swap**, so the same default resolves to roughly 2.3 GB of
caches on a machine where eighteen containers currently hold 573.8 MB in total
and an OOM kill is chosen by the kernel rather than by this repository.

The same image under a container limit reads the limit instead:

```
limiting caches to 120795955 bytes, leaving 80530637 bytes to the OS
according to -memory.allowedPercent=60, system memory limit 201326592 bytes
```

Its settled resident set moved from 63 MB and still climbing to 45.6 MB.

## Decision

**Every telemetry component this repository deploys carries an explicit
container memory limit, derived per project like every other value, and no
component is deployed without one.**

Three things follow, and the second and third are the ones that will be
forgotten first:

**1. The limit is the mechanism, not a comment.** These components read the
cgroup limit and size themselves from it, so the limit is not merely a ceiling
that stops a runaway — it is the input that decides how much memory the process
intends to use in normal operation. Setting it is configuring the component, and
omitting it is choosing whatever the host happens to have.

**2. `anon` is the figure a limit is chosen against, never `memory.current` and
never `docker stats`.** On a machine with no swap, an OOM kill is decided by
what cannot be reclaimed. Page cache can be. Measured twice in Run 1: reading
`memory.current` made Traefik's metrics surface look like it cost 71 MB when its
anonymous memory had not moved at all, and a collector under a 128 MB cap showed
`memory.current` pinned at exactly 128 MB while holding 31.1 MB of `anon` —
because reclaimable cache expands to fill whatever it is given. **A container
under a limit will eventually report `current ≈ limit` whatever it is doing**,
so sizing from that number would ratchet upward for ever.

**3. A number measured on a machine with more memory than the host is not
evidence about the host.** It is evidence about the machine it was taken on.
Any figure quoted in the capacity envelope states the memory of the machine it
was sampled on, and an unbounded off-host measurement is not quotable at all.

## Consequences

Makes easy:

- The failure mode this decision exists to prevent is not available: a telemetry
  component cannot expand into the memory a database container's cap has
  reserved-in-name-only (D767), because it was told a smaller number at startup.
- The limits are visible in one derivation rather than discovered by reading a
  vendor's defaults, so raising one is a reviewable diff.
- A component that outgrows its limit fails as itself, loudly, instead of
  causing the kernel to choose a victim elsewhere on a swapless host.

Makes hard:

- **A limit that is too small is now a way to break a working component**, and
  the symptom may be a store that silently keeps fewer series rather than one
  that dies. The limits are recorded with the measurement that chose them, and
  Run 6's load work is where they are re-checked under something other than an
  idle scrape.
- Every future telemetry component needs a number before it can be deployed,
  which means measuring it. That is the intended cost.

Residual:

- **This decision governs telemetry components only.** The existing services
  keep the limits they have, including `MCP_MEMORY_LIMIT_MB`, whose 384 was
  inherited from an interpreter measurement rather than derived (ADR 0131) and
  which Run 1 measured as bounding an 89 MB resident set. Whether that number
  should move is a separate question against a separate component, and folding
  it in here would be ADR 0021's mistake — applying a decision to a subject that
  did not ask for it.

## Alternatives considered

**Rely on the component's own percentage default.** Rejected on the
measurement: the default is a share of total system memory, so it produces a
different answer on the development machine, the deployment host, and any future
host — while looking identical in every configuration file.

**Set the component's own memory flag (`-memory.allowedBytes` and its
equivalents) instead of a container limit.** Rejected as the primary mechanism:
it is per-component spelling for one idea, it does not bound anything the
component does not account for, and the container limit was measured to be read
correctly by the component anyway. Where a component offers such a flag it may
be set *in addition*, never instead.

**Give the components no limit and rely on the host having room.** Rejected.
The host has room today — 2,110 MB available — and that is exactly the condition
under which an unbounded cache-sizing default does the most damage, because it
will take it.
