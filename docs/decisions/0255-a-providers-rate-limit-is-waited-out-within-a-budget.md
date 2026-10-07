# 0255 — A provider's rate limit is waited out, within a budget

- **Status:** Accepted
- **Date:** 2026-10-07
- **Session:** 37, Run 11 (D2139, D2140)
- **Affects:** `src/agentic_postgres/infisical_client.py` (`_request`,
  `_rate_limit_wait`, the `RATE_LIMIT_*` constants),
  `tests/contract/test_infisical_client.py`. No contract, schema or document
  moves.
- **Related:** D976 (the transient retries this extends), ADR 0037 (the unit
  that materializes at boot), the plan's Sheet B1.

## Context

Run 11's reboot (Sheet B1, 2026-10-07 05:32Z) was the first with THREE
projects on the host. Alpha, control-prod and the edge came back by
themselves; beta's unit failed at boot+60 s, exit 8:

```
materialize-secrets: could not read mirror_s3_secret_access_key:
  GET /api/v3/secrets/raw/APG_MIRROR_S3_SECRET_ACCESS_KEY failed with HTTP 429
```

Each unit materializes its secrets TWICE before Compose starts (the unit's own
`materialize` step, then `project-runtime.sh up` again, by design: the grant
surface is rendered against the generation `up` has just written). Three
projects × two runs × ~30 secrets is ~180 reads in ~20 s; Infisical Cloud's
free plan publishes 120 secret operations a minute. Two projects stayed under
it through every earlier reboot. The client retried a timeout and a 502/503/504
three times (D976) and raised a 429 on the first answer, so one refused read
failed the boot. A sample of the provider's ordinary answers (one request,
2026-10-07) carries no rate-limit header at all, so nothing in a normal
response says how near the limit a host is.

## Decision

1. **A 429 on an idempotent call is waited out and repeated.** A 429 is a
   request refused, not performed, so repeating a read or a login is safe;
   the rule stays opt-in per call site (`idempotent=True`), so a
   non-idempotent call is still attempted once.
2. **The wait is `Retry-After` in delta-seconds, bounded to 1–60 s;** absent,
   an HTTP-date, negative, non-finite or unparseable, it is 20 s — long
   enough for a one-minute window to move, never zero (a zero wait repeats
   into the burst that was refused).
3. **Bounded twice.** At most 6 attempts per call, and at most 180 s of 429
   sleeping per client over its whole life: the unit's start has
   `TimeoutStartSec=600` and runs the materializer twice before `up --wait`,
   so two budgets and a cold start fit inside it. A limit that does not lift
   within either bound is an `InfisicalError` with `status` 429 — never
   `None`, never 404, so the materializer still fails the run rather than
   reading a secret absent.
4. **Counted apart from the transient attempts**, so a 429 never spends a
   timeout's retry and D976's behaviour is unchanged.

## Alternatives considered

- **Stagger the units** (an `ExecStartPre` sleep, or ordering beta after
  alpha). Spreads one boot's load, but hard-codes a guess at the provider's
  window into unit files and still fails the fourth project; a deploy and a
  rotation meet the same limit with no unit involved.
- **Materialize once per boot** (drop the second run in `up`). Halves the
  reads, but the second run is what keeps the grant surface on the generation
  Compose mounts (D591); changing that order is a launcher redesign, not a
  repair, and three projects × 30 reads is still 90 against a 120 window
  shared with every other caller.
- **A paid plan.** Raises the number, not the property: a client that fails a
  boot on the first refusal fails at any limit.
- **Retry 429 with the D976 backoff (1 s, 3 s).** Four seconds does not move
  a one-minute window; measured, the boot's burst lasted ~20 s.

## Consequences

- A boot of three projects converges more slowly when the provider limits it
  (by up to the budget, per materializer run) instead of failing.
- Run 11 redeploys all three projects on the repair and reboots again; the
  evidence that every unit came back BY ITSELF is read after that reboot and
  before the sweep (D2140), because the sweep's own restart proofs restart
  alpha's and beta's units before its reboot proof runs.
- `doctor secrets` (ADR 0250) reads through the same client and inherits the
  wait.
