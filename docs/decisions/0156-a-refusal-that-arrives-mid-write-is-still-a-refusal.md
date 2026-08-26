# 0156 — A refusal that arrives mid-write is still a refusal

- **Status:** accepted
- **Date:** 2026-08-26
- **Session:** 10, post-close (a Session 6 proof, repaired)
- **Related:** ADR 0065/0066, **D273** (`request.body()` reads before the bound
  applies), **D509** (a control that cannot fail is not a control), **D511**
  (this flake), D374 (a test that passes for an unrelated reason).

## Context

`test_the_published_route_applies_the_input_bounds_before_the_service_allocates`
is `API-AUTH-002`'s live half. It sends a body four times `MAX_BODY_BYTES` and
asserts the edge answers **413** — Traefik's buffering middleware refusing on
`Content-Length` — rather than **400**, which would mean the request reached the
service and was read in full first. Both are refusals; only one means the
middleware is attached.

Traefik refuses and closes the connection **while the client is still writing the
body**. `urllib` raises `BrokenPipeError` or `ConnectionResetError` and
**discards the response it had already received**, so the proof reports status
`0` and fails against a deployment behaving exactly as designed.

Measured across one host trip at a single release: `ECONNRESET`, then `EPIPE`,
then a pass. Three runs, three outcomes, nothing changed between them. It cost
two full 11-minute host-gate runs.

D511 recorded this and declined to repair it, for a good reason: **accepting the
broken pipe as success would make the proof green whenever the connection broke
— including for the very defect it detects.** A middleware that is not attached
means the service reads the whole body and no 413 is ever sent; a client that
treated a broken pipe as a refusal could not tell that apart.

## Decision

**A dedicated client for that one request** —
`tests/deployment/oversized_request.py` — which writes the body in chunks, stops
writing the moment the server has answered, and reads the response **whether or
not the write completed**. It never synthesises a status: a connection that
broke with nothing received returns `0`, and the assertion fails exactly as
before.

The other two requests in that proof stay on `api_call`. Their bodies are small,
no write is ever in progress when the answer arrives, and there is nothing to
lose.

## Consequences

- The proof becomes deterministic. It goes red for a missing middleware and
  green for a present one, which is what it was always supposed to do.
- **The guard against D509's shape is asserted, not asserted-about.** A server
  that closes without answering must yield `0`, and mutating the exception
  branch to return `413` **kills** that test.
- `api_call` is untouched, so no other deployment proof changes behaviour.

## What the battery established, including what it did not

Six mutation arms, and **the first three all survived** — which was the useful
part.

- **V2b (the exception branch reports a refusal it never received): KILLED.**
  The silent arm returns through the *exception* branch, because an RST makes
  `recv` raise rather than return empty. The first attempt mutated the
  empty-buffer branch instead — a line that arm never reaches — and survived for
  a reason that said nothing about the guard.
- **V4 (never read at all): KILLED.** The read is load-bearing.
- **V1 (drop the readability check) and V3 (make a write error fatal) survived
  SEPARATELY, and together they KILL.** There are two independent routes to
  recovering the refusal, and each alone is sufficient. That is a real property
  of the design rather than a gap, but it is only visible from the combined arm —
  a single-mutation battery would have reported two survivors and left the
  impression that neither mechanism mattered.

**And the rig itself had to be repaired first.** The original test file ran
servers that answered immediately and closed, and **every arm passed with the
old `urllib` client too**: 64 KiB fits entirely in loopback socket buffers, so
`sendall` returned before the server had said anything and there was no race to
lose. Six green tests measuring nothing — D374's shape, in the file written to
prove a repair. The condition needs a tiny `SO_RCVBUF` on the listener, set
before `listen` so the accepted socket inherits it, and a server that never
drains the body; only then does the client block mid-write, `urllib` lose the
response, and the repair have something to demonstrate. Two permanent arms now
assert that `urllib` **fails** against those servers, so the rig cannot silently
stop reproducing the defect.

## What this does not decide

Whether `api_call` should adopt the same behaviour for every request. It should
not, on present evidence: no other proof sends a body large enough to be writing
when a refusal arrives, and a change to the shared client would alter the failure
mode of every deployment test to fix one. If a second such proof appears, this is
the ADR to re-read.
