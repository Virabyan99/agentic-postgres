# 0220 — A mirror pass has three outcomes, and the verb reports three

- **Status:** Accepted
- **Date:** 2026-09-18
- **Session:** 30, Run 2 (D1546, D1549); **implemented after Run 6**, at the
  operator's instruction, with the host's next timed pass hours away. The plan
  named no run for it (D1566)
- **Affects:** `OPS-MIRROR-*` (Session 30 assigns), `bin/backup.py`'s
  `verb_mirror`, the copy record's document, `diagnosis.mirror`. No migration,
  no deployed-document field, no schema move at the project or host level.
- **Related:** ADR 0188 (the mirror at a second provider), ADR 0190/0193 (the
  rehearsals), ADR 0195 (a report may not substitute an answer for a failure to
  determine one), D1000, D1001, D1016.

## Context

ADR 0188's mirror copies the primary repository's bucket to a second provider
nightly, by a host timer, through `mc mirror --overwrite --remove` in a
container on the project's backup egress network.

**Three files state, as the design, that a pass may legitimately exit
non-zero.** `services/backup-mirror/mirror.sh:36-39`:

> A pass may exit non-zero with objects behind and the next pass completes it
> (D1001); the exit code is the whole of what the verb reads.

`systemd/agentic-postgres-backup-mirror@.service:28-31` says the same in other
words, and `verb_mirror`'s own docstring repeats it.

**And `bin/backup.py:688-695` treats exactly that case as a hard failure**:

```python
if copy.returncode != 0:
    raise OperatorError(EXIT_STATE, f"the mirror copy exited {copy.returncode}; ...")
```

### What that cost, measured on the production host on 2026-09-18

Both projects' mirror units had been `failed` since 04:38 and 04:50 (D1512).
Diagnosed with root (D1546): **the copy succeeded.** `mc` transferred the whole
pass — alpha 7.21 MiB in 18 s, beta 5.78 MiB — printed its summary table, and
exited **1**, because exactly one object per pass failed:

```
mc: <ERROR> Failed to copy `…/17551.gz`. Put "…": net/http: HTTP/1.x transport
connection broken: http: ContentLength=928 with Body length 0
```

One object out of ~3,700, always a small `.gz` (928, 1856, 272 bytes), on
09-14, 09-16 and 09-18. Alpha's journal alternates complete/failed across six
days. Copied by hand minutes later: exit 0, 3893 and 3446 objects.

The consequences of that one object, all of them operator-visible:

1. the verb exits 5;
2. the unit enters `failed`, with no `Restart=`, by design;
3. `systemctl is-system-running` reads `degraded`;
4. **`mirror-state.json` is not written**;
5. and from `MIRROR_STALE_AFTER_DAYS` (2), `diagnosis.mirror` reports `WARN …
   last copied 2026-09-17, 2 days ago; the nightly copy has missed` —

while the mirror bucket is materially current. An operator reading
`list-units --failed`, the doctor, or the fleet inventory cannot distinguish
*one object flaked and the next pass will take it* from *the mirror is
broken*. Only the journal's `mc` line separates them, and `apg-diag`'s log
allowlist does not cover this unit (D380's neighbourhood).

**A mirror pass has three outcomes — complete, partial, failed — and the verb
reports two.** `diagnosis.mirror` is already careful in its own right: it has
five outcomes and returns `UNKNOWN` when the record cannot be read. The fold is
upstream of it, in what the record is allowed to say.

### The flake itself is not in scope

The transport error is upstream — the body read from R2 comes back empty while
its `ContentLength` is advertised — and no change here removes it. Nobody has
asked Cloudflare or Backblaze which side truncates. This ADR decides what the
product *reports* about it.

## Decision

**A mirror pass that transferred what it could is completed by an immediate
second pass, and only then judged.**

1. `verb_mirror` runs the copy. On a non-zero exit it runs the copy **once
   more, in the same invocation**, before judging. D1001's *"the next pass
   completes it"* becomes immediate rather than a day later.
2. If the second pass exits 0, the pass is **complete**: the listing is taken,
   `mirror-state.json` is written exactly as it is today, and the verb exits 0.
   The retry is recorded in the copy record as `retried: true` so that a
   reader can see it happened.
3. If the second pass also exits non-zero, the pass is **failed**: the verb
   exits 5 with the message it prints today, no record is written, and the unit
   fails. Two consecutive failures are not a flake.
4. **`mirror-state.json` keeps its present meaning exactly** — a record
   describes a copy that completed and a count read after it. This is the
   property that made the record trustworthy and it is not traded away.
5. The retry is bounded: **one** extra pass, no backoff loop, no schedule
   change. `MIRROR_TIMEOUT_SECONDS` applies to each pass as it does now.

## Consequences

**Makes easy:** a failed unit means the mirror is actually behind, which is
what every reader downstream — `list-units --failed`, the doctor, the fleet
inventory, `is-system-running` — already assumes it means.

**Makes hard:** a persistent, low-rate flake is now invisible in the unit's
state, because it is corrected. That is deliberate and it is why the retry is
recorded in the record: the count is where a rising rate becomes visible, not
the exit code. If the rate rises, the reading is `mc`'s line in the unit's
journal, which stays uncovered by `apg-diag` (an open item).

**Costs:** a passing copy that flakes now takes roughly twice as long in the
worst case. The measured passes are 7–21 s, against a `TimeoutStartSec` of
3600.

**Enforced by:** an offline proof against a fake `compose_mirror` whose first
pass returns 1 and whose second returns 0 — the record is written, the verb
exits 0, `retried` is true — with the **control** being a fake whose passes
both return 1, where the verb still exits 5 and writes nothing. Neither proof
touches a network or a container.

## Alternatives considered

**Write a record that distinguishes a complete copy from an attempt with N
objects behind, and teach `diagnosis.mirror` to read both.** The most
informative option, and rejected for this session: it moves the record's
document, and the record's current guarantee — *a record always describes a
complete copy* — is load-bearing in `diagnosis.mirror`'s five outcomes and in
D1016. Widening it is a bigger change than the defect warrants, and it can be
built later on top of this one without undoing it.

**Declare the present behaviour correct and raise `MIRROR_STALE_AFTER_DAYS`.**
Rejected: it silences the doctor while leaving the failed unit and the
`degraded` host, which are the loudest of the five consequences. It also treats
a reporting defect as a threshold-tuning problem, which is how a fold becomes
permanent.

**Retry only the objects that failed.** `mc mirror` has no such interface at
this layer; re-running the whole pass is the mechanism it offers, and a pass
over an already-copied bucket is cheap because `--overwrite` compares first.

**Retry three times with backoff.** More retries convert a genuine outage into
a long silence before the unit fails. One extra pass distinguishes a flake from
a failure, which is the entire question being asked; a second extra pass
answers nothing new.

**Leave it and note it in the runbook.** D1501, D1504 and D1505 are this
project's record of what a noted-but-unrepaired exec defect costs. Documentation
is not a control.
