# 0141 — A write fails closed on its audit record, and a read does not

Status: accepted
Date: 2026-08-22
Session: 9, Run 6
Affects: ADR 0125, ADR 0129, ADR 0130, ADR 0135, D473, D477, D478, D479, D483,
D489, D498, D499, D500, migration 0019,
`services/auth-api/app/mcp_audit.py`, `services/auth-api/app/mcp_tools.py`,
`services/auth-api/app/mcp_authorization.py`,
`services/auth-api/app/mcp_telemetry.py`, `services/auth-api/app/mcp_query.py`,
`AGT-AUDIT-001`, `AGT-AUDITFAIL-001`

## Context

The session summary says *"audit initialization fails closed"* and does not say
for what. D483 recorded that the silence is load-bearing rather than an omission
to tidy: `AGT-AUDITFAIL-001`'s own description is **"a write fails closed when
its audit record cannot be created"**, which is already narrower than the
reflex — and the reflex is what needs writing down.

Failing a read closed would couple every agent read's availability to the audit
table and add a mandatory round trip to a path ADR 0125 already pays one for.
Failing a write open would let a change happen that no record describes, which
is the one thing the record exists to prevent.

## What was measured (rig6, PostgREST v14.16 + the pinned pgvector image)

Eleven arms against functions mirroring 0019's shapes, with a negative control
that failed as designed. **The rig itself was wrong first**, and the way it was
wrong is worth keeping: it established the agent identity with
`ALTER ROLE rig_anon SET app.agent_id = …`, and every `begin` arm came back
`403 PT403`. **A role-level setting is applied at LOGIN**, and PostgREST logs in
as the authenticator and switches role per request — so a setting attached to
the switched-to role is never applied at all. The rig moved to a pre-request
hook, which is what production uses.

- **A non-SETOF SCALAR return renders as a bare JSON scalar.** `RETURNS uuid` is
  `"c8c13a67-…"`, a JSON **string**, not an object and not an array; the SETOF
  contrast is `["fa15e1b7-…"]`. **rig4's composite finding is not evidence for
  this** — that measured `RETURNS <composite>` and got one object. Three
  shapes, three renderings, and the audit parser depends on the third.
- `RETURNS boolean` renders as bare `true` / `false`. **Closing an
  already-closed record answers `200 false`, not an error** — the record is
  scoped to the calling agent's own started rows, so "matched nothing" and
  "belongs to somebody else" are one answer, deliberately (0019's comment).
- A defaulted `jsonb` argument may be **omitted entirely** or sent as an
  explicit JSON `null`; both are 200.
- `committed` is refused **422 / `PT422`**, and the missing-identity branch
  crosses as **403 / `PT403`** — both the errcode's own status, as rig4 found
  for `PT404`/`PT409`.
- **A custom request header reaches the database.** With `X-Request-Id` sent,
  `current_setting('request.headers')::jsonb` carries `"x-request-id"`
  (lowercased); without it, the key is absent. The pair is what makes this a
  measurement rather than an observation.
- **Three `started` rows survived across the run.** Each RPC call is its own
  transaction and commits before the next request runs — which is what lets an
  `agent_plane` record outlive the failed write it describes, and is D489
  arriving from the other side.

## Decision

**One vocabulary decides three things, and each is a named function of it.**
`bounded()` takes the lock's own `kind` — `metadata`, `read`, `write` — and
derives `reaches_upstream`, `is_audited` and `fails_closed_on_audit` from it,
each with its reason at the definition. This is deliberately *not* D495's
mistake repeated: there the two ideas were an **accident** of representation
(`resource is None`), agreeing only until the first tool separated them. Here
the classification is one the reviewed contract already makes, and each derived
property is written down rather than inferred.

1. **A write whose `agent_audit_begin` fails does not happen.** The refusal is
   structural and the caller is told nothing beyond the mask, because an
   unauditable write is this deployment's fault and not the caller's.
2. **A read whose begin fails still runs**, and the failure is emitted as
   telemetry. Availability of the read surface does not depend on the audit
   table.
3. **Metadata tools are not audited at all.** They answer from the lock in
   memory, reach no backend, and take no concurrency slot (ADR 0129). Auditing
   them would turn a dictionary lookup into two network round trips and make
   discovery depend on the audit table — undoing the reason they exist in that
   shape. Telemetry still records them.
4. **A denial is audited.** The scope check runs inside the audited work, after
   `begin`, so a refused call is a record whose `complete` says `refused`. That
   is how `AGT-AUDIT-001`'s "denied" arm is satisfied, and it is why the order
   is begin-then-check rather than check-then-begin.
5. **A failing `complete` never fails the call.** The work has already happened;
   a committed write cannot be un-committed by a bookkeeping failure, and
   reporting a failure that did not occur would make the record less true, not
   more. It is emitted as telemetry.
6. **The audit record carries what telemetry deliberately does not.** A filter
   operand and a note title are in the parameters document, redacted per the
   lock's `audit_redact`, and are *never* in a telemetry record. They are
   different artefacts with different readers: telemetry is shipped by the
   journal and read by operators; the record lives in `app_private`, is granted
   to nobody, and answers a record-keeper months later (ADR 0130, ADR 0135).

**The request id is minted by the agent plane**, once per HTTP request, in
`AgentContextMiddleware.on_request` — beside the context, carried on the same
held value, reset in the same `finally`. It is forwarded upstream on every
request the plane makes, including the context lookup, and passed to both audit
calls as an argument.

## Alternatives rejected

- **Fail every tool closed on its audit record.** Couples discovery and reads to
  the audit table, and adds a round trip to the metadata path that currently
  makes none. It would also make an audit-table outage a total outage.
- **Fail nothing closed and rely on the database-side row.** The `database` row
  is written by the write RPC in the write's own transaction, so it exists only
  for changes that COMMITTED (D489). A refused or failed write would then have
  no record anywhere.
- **Check scopes before `begin`.** Cheaper, and it loses the denial record that
  `AGT-AUDIT-001` names.
- **Read the request id from the forwarded header inside the database.**
  Measured available, and not used: it would be a second authority for a value
  the argument already carries, and 0019 is released.

## Consequences

- **Every audited tool call costs two extra upstream round trips**, on top of
  ADR 0125's context resolution. An MCP write is now **four** requests to
  PostgREST: context, begin, the write, complete. Stated here as a cost rather
  than discovered on a cluster — and still **unmeasured against the
  deployment**, which is the open item ADR 0125 already carried and this
  decision triples.
- **The `database`-source row carries no `request_id`** (D500). 0019 inserts
  `source, agent_id, owner_id, tool, outcome, row_count, completed_at` and no
  id, so the two records for one MCP write correlate by agent, tool and time
  rather than by request. The header measurement above makes the repair cheap
  for whoever takes it, and it needs a migration 0020 rather than an amendment
  to a released 0019.
- A new `PT` code from a future migration is **masked** on the audit path as it
  is on the write path (ADR 0139), so a new refusal is silent until somebody
  chooses otherwise.
- `RECORD_FIELDS` grows by `request_id`, and `as_dict` still raises if the
  dataclass and the tuple disagree. The canary's list is unchanged: a request id
  is this process's own mint, not a token, a URL or a caller value.
- `FORWARDED_HEADERS` grows to three, and `_dial`'s equality guard moves in the
  same commit (D477). It stays an equality: both of Session 8's allowlist
  failures were right to fail, and a subset check is D300's shape.
