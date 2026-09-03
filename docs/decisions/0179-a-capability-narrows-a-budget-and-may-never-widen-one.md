# 0179 — A capability narrows a budget and may never widen one

- **Status:** accepted
- **Date:** 2026-09-03
- **Session:** 16, Run 4 (`AGT-BUDGET-002`, D892, D893, D898–D901)
- **Related:** **ADR 0129** (four budgets, independent by decision; concurrency
  is a share of PostgREST's pool), **ADR 0177** (a capability field is required
  at the version that introduces it), **D892** (Run 7's fields land here, or the
  manifest moves three times in one session), **D893** (the metadata `not/anyOf`
  does not extend itself), ADR 0120 (a metadata capability reaches nothing),
  ADR 0070 (a division rather than a set of independent grants), ADR 0002.

## Context

ADR 0129 bounds four things independently — rows, serialized bytes, elapsed
time, concurrency. **Two of the four are already per capability** and two are
not:

| budget | bound by | per capability before this run |
|---|---|---|
| rows | `min(caller limit, resource.max_rows)` | **yes**, from the lock |
| elapsed time | `@server.tool(timeout=…)` | **yes**, the lock's `timeout_ms` |
| serialized bytes | `MAX_SERIALIZED_BYTES` | no — a runtime constant a caller cannot express |
| concurrency | a semaphore rendered from `api.rest.pool_size` at half | no — process-wide |

So this run finishes the per-capability half of that table rather than adding a
fifth budget beside it. **The fifth budget is Run 5's**, and the distinction is
the one the stage plan's *Must not* insists on.

### What a response actually costs

§9 records that `MAX_SERIALIZED_BYTES` is *"1 MiB, chosen and not measured"*, and
a per-capability limit read against an unmeasured global is a bound on a guess.
Measured, with the two kinds of number kept apart because they are not equally
strong — the metadata responses are computed exactly by calling the product's own
functions, and a read's size is the caller's data, so what is measured there is
the envelope and the per-row cost:

| capability | cost | share of 1 MiB |
|---|---|---|
| `list_resources` | **354 B** exact | 0.03% |
| `describe_resource` | **288–683 B** exact | 0.03–0.07% |
| `create_note` / `update_task_status` | 8–12 KB at 4 KiB content | ~1% |
| `query_resource/notes` | 79 B + ~6 B per content byte, per row | ceiling at **42 rows** at 4 KiB content |

**The two budgets cross over inside a realistic range**, which is ADR 0129's
independence claim turning numeric. At 0 and 256 bytes of content the row budget
binds first; at 4 KiB the byte budget does, at 42 rows against a `max_rows` of
200. For `notes` the crossover is around **860 bytes per column**. So 1 MiB is
not obviously wrong — it is roughly "two hundred rows of five kilobytes" — and
this run does not tune it.

## Decision

**Four new capability fields at `schema_version` 3, each narrowing something
that already exists, and none of them able to widen it.**

```
max_response_bytes    read, write   ≤ MAX_SERIALIZED_BYTES
max_concurrent_calls  read, write   the effective bound is min(this, process-wide)
supports_dry_run      write         Run 7's behaviour, declared here
requires_approval     write         Run 7's refusal, declared here
```

### Why all four arrive in one bump

ADR 0177 requires a field at the version that introduces it. D866 split seven
fields across Runs 2, 4 and 7, and honouring both would move the manifest format
three times in one session — which ADR 0177 argues against in as many words. So
Run 7's two fields are **declared here and behave there** (D892). Two formats for
the session, which is the minimum the run split allows.

### Why narrowing is enforced two different ways

**Bytes are bounded by the schema.** `maximum: 1048576` is the same number as
`MAX_SERIALIZED_BYTES`, so a manifest that tried to widen is refused before a
deployment exists. The number appears in two files and a contract test compares
them — the same arrangement as `DENIAL_REASONS` against migration 0027, and for
the same reason: JSON Schema cannot import a Python constant, so the choice is
between two authorities that are checked and one that is trusted.

**Concurrency is bounded by the runtime**, because it cannot be bounded by the
schema: the process-wide semaphore is rendered from `api.rest.pool_size`, which a
capability manifest never sees. So the effective bound is `min(declared,
process-wide)`, taken at the acquisition, and the schema's `maximum` is a
sanity cap rather than the real ceiling. **Stated because the asymmetry is
otherwise invisible**: a reader seeing two `maximum`s would reasonably assume
both are the enforcement.

### Metadata capabilities are forbidden all four

`allOf[2]`'s `not/anyOf` lists six fields today and **does not extend itself**
(D893), so without this each new field would be *permitted* on a metadata
capability. Each would bound nothing:

- `_within_byte_budget` is applied at `mcp_tools` 380 and 499 — the read result
  and the write result — and never to a metadata result, which is why
  `list_resources` costs 354 bytes and passes through no check;
- a metadata call takes no concurrency slot, because `read_slots` wraps only
  `UPSTREAM_KINDS`;
- a call that changes nothing has no dry run and needs no approval.

A value that bounds nothing is exactly what ADR 0120 forbids these capabilities
for the six fields it already lists.

## Alternatives rejected

**Let a capability widen a budget, with a ceiling.** It reads as flexibility and
is a second authority: the process-wide semaphore is a *share of PostgREST's
pool* (ADR 0129), and a capability that could raise its own share would be
deciding how much of a human-facing resource an agent may take — ADR 0070's rule
inverted.

**Make the byte limit a fifth budget rather than a narrowing.** It is the same
quantity, checked at the same point, against a smaller number. Two authorities
over one bound is D264's cost.

**Default the two limits instead of requiring them.** ADR 0177's rule, and the
same reasoning: a default is a value nobody chose, and the whole point of a
per-capability bound is that somebody chose it for that capability.

**Wait for Run 7 to declare its own fields.** That is the three-format outcome
D892 rejects, and it would have been discovered in Run 7 rather than decided in
Run 4.

## Consequences

- `capabilities.example.yaml` moves to v3, and a v1 or v2 manifest still loads —
  `capabilities.yaml` lives only on the host and no commit can edit it.
- The compiled contract's `schema_version` follows the manifest's (ADR 0177), so
  a v3 manifest produces a v3 lock, and `mcp_lock` must accept it before one can
  reach a host — the ordering D882 is about, now on its second instance.
- `MAX_SERIALIZED_BYTES` remains 1 MiB and remains unmeasured *as a choice*. What
  is no longer unmeasured is what it costs to reach it, which is the half §9's
  entry was actually missing.
- A fifth budget in Run 5 now has a clear contrast to describe itself against:
  every bound here is per request and decided from the lock; a windowed quota is
  per agent and outlives the request.
