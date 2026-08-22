# 0139 — A write refusal is translated from the product's own errcode, never relayed

Status: accepted
Date: 2026-08-22
Session: 9, Run 4
Affects: ADR 0097, ADR 0130, D433, D489, migration 0019,
`services/auth-api/app/mcp_errors.py`, `services/auth-api/app/mcp_upstream.py`

## Context

The two write tools make `update_task_status` a compare-and-swap, and a
compare-and-swap a caller cannot distinguish from a generic failure is not one:
the caller's next action after "the task was not in the expected status" is to
re-read and retry, and after "refused" it is to give up. So *some* upstream
write refusals must reach the caller — and ADR 0130's rule is that telling a
caller something is the act that requires a decision. This is that decision.

Two prior rules bound it. **D433**: an upstream *status code* is never relayed,
because three measured 401s (bad signature, stale identity, missing privilege)
are indistinguishable by status. **ADR 0097**: an upstream *message* is never
forwarded, because PostgREST's error documents name functions, schemas and
hints.

## What was measured (rig4, locked PostgREST v14.16, negative control first)

Twelve arms against functions mirroring 0019's shapes — `RETURNS <composite>`,
a defaulted argument, `RAISE … USING ERRCODE 'PTxxx'`:

- **PostgREST maps `ERRCODE PTxxx` to HTTP status xxx**, with the errcode in
  the body's `code` member: the CAS branch arrives as `409` /
  `{"code":"PT409","message":"AP409: …"}`; the missing-row branch as `404` /
  `PT404`.
- **Status alone cannot classify a write refusal.** A missing argument and an
  unknown extra argument are both `404 PGRST202` — the same status as the
  product's own "no such task". A 404 is *either* "the function you built a
  request for does not exist" *or* "the row you named does not exist", and only
  the body's `code` tells them apart. Relaying the status would be D433's guess
  dressed as a diagnosis, measured rather than assumed this time.
- A malformed enum value arrives as `400 22P02` whose message **names the
  schema's enum type** — the disclosure ADR 0097 exists to stop.
- A non-SETOF composite return is a **single JSON object** (a SETOF control is
  an array); `Prefer: return=minimal` changes nothing on an RPC POST and
  `Prefer: count=exact` only adds headers, so the header allowlist keeps its
  reason.
- A JSON number where the function takes `text` is coerced (`7` → `"7"`), so
  the adapter's type gate needs to refuse only structured values, not numbers.

## Decision

`mcp_errors` owns one enumerated map from **the product's own write-refusal
vocabulary** — the `PT` errcodes migration 0019's write RPCs raise — to caller
tokens and to sentences this runtime wrote:

- `PT404` → `row_not_found` — the row this write names does not exist (under
  the caller's own RLS, so the sentence discloses nothing about other owners).
- `PT409` → `write_conflict` — the row is not in the expected state; re-read
  and retry is the caller's move.
- `PT422` → `input_not_permitted` — the transition changes nothing.

Everything else stays masked, **including `PT401`**: a missing request identity
is the authentication plane's business, and a caller that reached a tool has
already been authenticated — a `PT401` there is a fault, not an instruction.

The write executor reads a refused response's body **for the `code` member and
nothing else**; the message, details and hint are discarded unread of content.
The sentence a caller sees is this repository's, reviewed here, not the wire's.
The read path keeps discarding bodies entirely — nothing about ADR 0097 or
D433 moves for reads.

## Alternatives rejected

- **Mask every write refusal.** Makes the compare-and-swap unusable as one and
  turns "the task moved underneath you" into "give up".
- **Relay the HTTP status.** Measured ambiguous: `404` is both `PGRST202` and
  `PT404`, opposite meanings.
- **Forward the upstream message for mapped codes.** The message is the
  product's today and an arbitrary string after the next migration; the map is
  enumerated precisely so a new sentence needs a new decision.

## Consequences

- A future migration adding a new `PT` code is **masked until this map moves**
  — silent by default, which is ADR 0130's default working as designed.
- The map is a second place 0019's refusal vocabulary lives, so a test compares
  the map's keys against the errcodes the migration template actually raises —
  a key the product never raises is dead vocabulary and fails the suite.
- `CALLER_FACING_TOKENS` grows by `write_conflict` and `row_not_found`, the
  closed-set constructor check unchanged.
