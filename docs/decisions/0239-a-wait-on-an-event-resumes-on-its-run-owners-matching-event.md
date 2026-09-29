# 0239 — A wait on an event resumes on its run owner's matching event, and the Session 34 refusal is replaced

- **Status:** Accepted
- **Date:** 2026-09-29
- **Session:** 34, Run 1 (D1793)
- **Affects:** `schemas/workflow.schema.json` (`wait.event`, `wait.match`),
  `src/agentic_postgres/workflow_definition.py` (`_compile_wait`), migration
  0036 (four `workflow_step` columns, `workflow_await_event`, the replaced
  `workflow_gate_state`), `services/auth-api/app/workflow_worker.py` (`_wait`),
  `tests/contract/test_workflow_definition.py`.
- **Related:** ADR 0233 (a wait is a park with a time), ADR 0235 (the emitter
  serves the wait), ADR 0227 (the substrate).

## Context

Session 33 admitted `wait: {event}` in the schema only so that the compiler
could refuse it — *"a wait on an event arrives in Session 34 with the events
that resume it"* — and a proof pins the refusal
(`test_a_wait_on_an_event_is_refused_naming_session_thirty_four`, WF-DEF-002).
`workflow_gate_state` is the one gate read. Nothing says WHICH event resumes
WHICH run: an event carries no run id, and two owners' runs may wait on one
name.

## Decision

1. **The definition shape**: `wait: {event: "<name>@<version>", match:
   {<member>: <literal or whole reference>}, seconds: N}`. `seconds` is the
   maximum wait (the existing bound, below the run's timeout); `match` holds at
   most 8 members whose values are literals or WHOLE `{{input.<k>}}` /
   `{{steps.<earlier>.<field>}}` references; the version is required.
2. **Resolved once, at park.** The worker resolves `match` and parks with
   `workflow_await_event(…)` (reason `awaiting_event`, `resume_after = now +
   seconds`), minting no token.
3. **The emitter serves the wait in the caller's transaction** (ADR 0235): a
   parked step awaiting `name@version` is served only when the run's agent's
   OWNER is the emitter's owner and the payload contains (`@>`) the resolved
   match.
4. **`workflow_gate_state` gains `"event": null | {"served": bool}`**, same
   signature, same return type. On reclaim a served wait finishes `succeeded`
   / `event_received` with result `{"event": "<name>@<v>", "payload": {…}}`; an
   unserved one finishes `failed` / `event_timeout`, and compensation runs by
   the existing path.
5. **This ADR authorises replacing
   `test_a_wait_on_an_event_is_refused_naming_session_thirty_four`** with the
   EVT-WAIT-001 proofs of the feature and of every refusal it now makes (no
   version, a non-whole reference, a reference to a later step). CLAUDE.md §6:
   a passing test may be replaced by a stricter one when an ADR authorises it;
   the refusal it pinned was a promise this session keeps.

## Consequences

- The owner is the only correlation the tree already enforces everywhere (row
  security); a match on payload members is the least a definition needs to say
  *this note*.
- A wait never resumes on another tenant's event.

## Alternatives rejected

- **A run id in the event** — the emitter's caller knows no run.
- **First come across owners** — a cross-tenant resume.
- **A separate event table the worker polls** — a second reader of one fact,
  and a delay the emitter need not add.
