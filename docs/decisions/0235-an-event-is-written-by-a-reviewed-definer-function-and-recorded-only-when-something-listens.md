# 0235 — An event is written by a reviewed definer function in its caller's transaction, lives in `app`, and is recorded only when something listens

- **Status:** Accepted
- **Date:** 2026-09-29
- **Session:** 34, Run 1 (D1779, D1780, D1781, D1782, D1814, D1815; rig 34a)
- **Affects:** migration 0036 (`app.emit_event`, `app_private.connector_event`,
  `app_private.connector_delivery`), `src/agentic_postgres/migrations.py`
  (`lint_project_set`), `projects/example/migrations/templates/
  0003-note-embedding-events.sql`.
- **Related:** ADR 0050 (nothing in `api` the contract does not name), ADR 0135
  (the definer-function grant shape), ADR 0198/0206 (a project set and its
  lint), ADR 0213 (a record pruned by an operator who states a horizon), ADR
  0227 (four tables nobody may read), ADR 0239 (a wait on an event).

## Context

The stage plan asks for *"versioned domain events on a transactional outbox"*,
written *"in the caller's transaction by a reviewed function, never by a
trigger on a base table"*, and names the function `api.emit_event`, *"granted
to the request roles like the audit functions"*.

Two things in the tree refuse that shape. A function in `api` granted to the
request roles is addressable as `POST /rpc/emit_event` by every agent and every
signed-in human, so any caller could forge any event with any payload. A
function in `api` granted to NOBODY is refused by
`tests/contract/test_api_migrations.py` (*"exists in the exposed schema and no
role can call it"*) and moves five exact pins of the `api` contract. `app` is
already a forbidden PostgREST schema and already holds one release function,
`app.current_user_id()`. A project's RPC is `SECURITY DEFINER` running as the
object owner, the role that owns every release object.

**Rig 34a measured the prototype** on the `apg dev` cluster (PostgreSQL 18.4,
35 release + 2 project migrations): an `app.emit_event(text, integer, jsonb)
RETURNS uuid`, SECURITY DEFINER, created as the owner, `REVOKE ALL … FROM
PUBLIC`, and a project-shaped `api.rig_emit()` definer RPC calling it.

- Called directly as `authenticated`, `agent_writer`, `auth_service` and
  `anon`: **`42501 permission denied for schema app`** for all four, and
  `has_function_privilege(…, 'EXECUTE')` **false** for all four. The refusal a
  caller meets FIRST is the schema's; the function's grant to nobody is the
  second belt (D1814).
- Through the definer RPC as `authenticated` with `app.user_id` set: one row,
  carrying the GUC's owner. Through PostgREST with an AGENT token: one row
  carrying the agent's OWNER and the agent's id — the pre-request hook's GUCs,
  never a parameter.
- `POST /rpc/emit_event` to PostgREST with a human token and with an agent
  token: **404 `PGRST202`** (not in the schema cache). Control: `POST
  /rpc/create_note` **200**.
- A rolled-back caller (`BEGIN; … SELECT api.rig_emit(); ROLLBACK;`): the table
  held 3 rows before and 3 after.
- **The lint's hole, both halves** (D1780, D1815): `lint_project_set` PASSED a
  project template containing `CREATE OR REPLACE FUNCTION api.create_note(…)`,
  `CREATE OR REPLACE FUNCTION app.emit_event(…)`, `ALTER FUNCTION
  api.create_note(text, text) SECURITY INVOKER` and `CREATE OR REPLACE FUNCTION
  app.current_user_id()` — the function every row policy reads. Applied as the
  owner, `api.create_note`'s definition changed (md5 `c0cdcc57…` →
  `0d4f9729…`). Controls: a body naming `app_private` refused; `DROP FUNCTION
  api.create_note` refused (the existing rule); a project RPC calling
  `app.emit_event` passed.

## Decision

1. **`app.emit_event(p_name text, p_version integer, p_payload jsonb) RETURNS
   uuid`**, SECURITY DEFINER, `SET search_path = pg_catalog, pg_temp`, created
   as the object owner, `REVOKE ALL … FROM PUBLIC`, **granted to nobody**. Only
   a function already running as the owner can call it: the release's own
   definer functions and a project set's reviewed definer RPCs. Identity is
   read from `app.current_user_id()` and the GUC `app.agent_id`, never from a
   parameter; no owner identity refuses `PT401`.
2. **An event is recorded only when something listens.** Inside the caller's
   transaction the emitter serves every parked `wait` step of the same OWNER
   whose resolved match the payload contains (ADR 0239), and, if at least one
   ENABLED outbound connector subscribes to `name@version` and has an
   endpoint, inserts ONE `connector_event` row and ONE `connector_delivery` row
   per such connector. It returns the event's id, or `NULL` when no delivery
   was recorded. A caller that rolls back rolls the event back with it.
3. **Bounds**: name `^[a-z][a-z0-9_]{0,62}(\.[a-z][a-z0-9_]{0,62}){0,3}$`,
   version 1..999, payload a JSON object of at most 8,192 bytes
   (`octet_length(p_payload::text)`), else `PT422`. The bound keeps a delivery
   inside the 16 KiB the edge and the application accept.
4. **No trigger writes an event, anywhere.**
5. **The project lint gains one rule**: a project set may not `CREATE [OR
   REPLACE]`, `ALTER` or `DROP` a FUNCTION the release creates in `api` or
   `app`. The names are DERIVED from the release templates, never typed, and
   the existing DROP rule is folded into it. `app.current_user_id()` is one of
   them.
6. **The example set's `0003`** replaces `api.set_note_embedding` with its
   signature, grants and body unchanged plus one line after the upsert:
   `PERFORM app.emit_event('note_embedding.set', 1,
   pg_catalog.jsonb_build_object('note_id', p_note_id));`. The payload names
   the note and never carries the embedding.

## Consequences

- The `api` contract does not move; no request role and no PostgREST route can
  reach the emitter. An event can be forged only by SQL an operator reviewed
  into a release or a project set.
- The emitter is exactly as trustworthy as the rule that nobody but the release
  defines it. The rule's absence for `api.create_note` and
  `app.current_user_id()` is older than this session and is closed with it —
  a stricter lint, never a looser one.
- A subscriber enabled later sees only later events; nothing is replayed to it.
- The proof of the grant must assert `has_function_privilege` false for every
  role as well as the `42501`, because the `42501` alone is the schema's and
  would survive a function granted to PUBLIC (D1814).

## Alternatives rejected

- **`api.emit_event` granted to the request roles** — a forgeable `POST
  /rpc/emit_event` with any payload.
- **`api.emit_event` granted to nobody** — refused by
  `test_api_migrations.py`'s every-function-is-granted proof; five exact pins
  move for nothing.
- **A trigger on a base table** — refused by the stage plan: every write
  becomes an event nobody reviewed.
- **An event log that records everything** — retention with no reader (ADR
  0213's shape; D1700 and D1775 already owe one).
