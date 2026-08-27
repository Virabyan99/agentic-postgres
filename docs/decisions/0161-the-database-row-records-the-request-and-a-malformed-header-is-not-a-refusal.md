# 0161 — The `database` row records the request, and a malformed header is not a refusal

- **Status:** accepted
- **Date:** 2026-08-27
- **Session:** 11, Run 6 (`OPS-LOG-001`)
- **Related:** **D500** (the gap), **D633** (an unguarded cast destroys the
  write), **D632** (how the header reads inside a definer function), **D642** /
  ADR 0160 (the id is the runtime's own mint), ADR 0141 (a write fails closed on
  *its own* audit record), ADR 0139 (a refusal is translated, never relayed),
  ADR 0135 (an agent can add noise to its own record), ADR 0091 (fix forward).

## Context

**D500 has been open since Session 9.** One MCP write produces two audit rows —
an `agent_plane` row the runtime writes, and a `database` row the RPC writes
inside the transaction it describes — and only the first carries a `request_id`.
The two correlate by agent, tool and time.

Migration 0020's own comment set the terms for closing it:

> Closing D500 means replacing both write RPCs, which is a change to what the
> product WRITES; this migration only adds a way to READ what is already
> written. Bundling them would make one migration two decisions, and **the
> deployment test that asserts the `database` row's `request_id` IS NULL stays
> green and stays the thing that will fail on the day the repair lands.**

This is that day. The test is flipped here, authorised by this ADR, and replaced
by a stricter one.

**Two measurements decide the shape, and both were made before this run.**

D632 (Run 1) settled the read: through PostgREST, through a role switch, behind a
`db-pre-request` hook, inside `SECURITY DEFINER` with
`SET search_path = pg_catalog, pg_temp`, the header reads back under the
**lowercase** key only. An absent key is SQL `NULL`, not the empty string — so
the repository's `nullif(current_setting(…), '')` idiom does **not** belong here;
it guards a different case. From `psql`, with no request at all, the GUC itself is
`NULL`, so the **two-argument** `current_setting` is required.

D633 (Run 1) settled the guard, and it is the sharper finding. A function that
inserts a row and *then* casts a malformed caller-supplied `X-Request-Id`:

    X-Request-Id: not-a-uuid   →  22P02  →  HTTP 400  →  **zero rows in the table**

The note is destroyed by a header. The well-formed control committed both rows in
the same rig; a *missing* header is harmless, because `NULL::uuid` is `NULL`.
Only the malformed path is dangerous — and it is reachable by any caller.

## Decision

**One helper, `app_private.agent_request_id()`, and both RPCs call it.**

It reads `current_setting('request.headers', true)`, takes the lowercase
`x-request-id`, **tests the shape before casting**, and returns `NULL` for
anything that is absent, unreadable or not a uuid. It never raises.

A shared function rather than the expression twice, and that is Question 5
answered in advance: a third write RPC added in a later session gets the rule by
calling it, instead of getting whichever version its author copied. It is
`STABLE`, `SECURITY INVOKER`, and `REVOKE ALL … FROM PUBLIC` — it needs no
privilege of its own, and running inside a `SECURITY DEFINER` caller it executes
as that function's owner.

**A malformed header records `NULL` and the write proceeds.** Two existing
decisions require this rather than one new one:

- **ADR 0141** makes a write fail closed on *its own* audit record. A caller's
  malformed header is not this deployment's audit record failing; it is caller
  input. The correlation field's convenience must never be able to destroy the
  operation it annotates.
- **ADR 0139** requires a write refusal to be *translated* from the product's own
  `PT` errcode, never a relayed status. A raw `22P02` surfacing as `400` is
  precisely the relayed status that ADR exists to forbid — and the agent plane
  could not classify it, because it is not a `PT` code.

**A shape test, not an exception block.** `BEGIN … EXCEPTION` opens a
subtransaction on every agent write; a regex is a comparison. The choice is
recorded because the alternative is the one a reader reaches for first.

## Consequences

- The two rows for one MCP write now join on `request_id`, and that value is the
  same one Traefik logged as `downstream_X-Request-Id` (ADR 0160). Four legs, one
  value: ingress, the runtime's log, the `agent_plane` row, the `database` row.
- **D500 closes. `OPS-LOG-001`'s audit leg is whole.**
- `test_the_request_id_is_recorded_and_is_this_planes_own_mint` is **replaced by
  a stricter assertion**: the `database` rows carry ids, and each matches an
  `agent_plane` row's id. Asserting a `NULL` was a statement about an absence;
  asserting the join is a statement about the correlation the requirement asks
  for. §6 permits the replacement because this ADR authorises it and the new
  test's docstring says so.
- Migration **0022**, not an edit to 0019 (ADR 0091). 0019 is released and applied
  on both clusters, and its `down` block raises AP900 like every other.

### The residual, stated rather than discovered

**A caller reaching PostgREST directly chooses the `request_id` on its own
`database` row.** It cannot forge `agent_id` or `owner_id` — those come from GUCs
the pre-request hook set, which is the whole of `SEC-PARAM-001` — but the
correlation field is caller-influenced on that path.

This is narrower than D642's refusal and is consistent with it. D642 refused
letting a caller's id become **the runtime's own** id, because the `agent_plane`
row is this deployment's authoritative record of what it did. Here the caller is
choosing a correlation hint on a row that already names them. It is ADR 0135's
conceded case — *"an agent can add noise to its own audit record"* — and the
noise is visible: a row whose `request_id` matches another agent's request still
carries its own `agent_id`, so an operator joining by request id sees the
mismatch rather than being fooled by it.

**An operator correlating by `request_id` should check `agent_id` beside it.**
That sentence belongs in the operator guide, and it is why this residual is
written here rather than left implicit.

## What this does not decide

**Whether a caller's own id should be recorded separately.** ADR 0160 left this
open and it stays open: a second column, explicitly named caller-supplied and
never joined to anything, would serve a client correlating its own logs. Nobody
has asked for it, and adding a caller-writable field to an audit table is not
something to do speculatively.

**Whether `agent_audit` should be pruned.** Still nobody's decision (ADR 0135),
still growing without bound, and this migration adds a column's worth of nothing
to that.
