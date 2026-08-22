# 0135 — An audit record is written by a definer function, as the caller, and the hook cannot write one

Status: accepted
Date: 2026-08-22
Session: 9, Run 1
Affects: ADR 0052, ADR 0099, ADR 0117, ADR 0121, ADR 0125, ADR 0130, D407, D412,
D473, D474, D480, D489, `migrations/templates/0019-agent-write-and-audit-plane.sql`,
`services/auth-api/app/settings.py`

## Context

Session 9 must produce a durable audit record for agent tool calls. Session 8
deliberately produced telemetry instead and said why: telemetry answers "what
happened" for an operator watching a running deployment; an audit record answers
it for a record-keeper, months later, **with a contract about what happens when
it cannot be written** (ADR 0130, D412).

Three constraints were already fixed before this session began, and together
they leave far less freedom than the question suggests.

**The runtime holds no database credential and must not gain one.**
`settings.load_mcp` refuses to start if any of `FORBIDDEN_VARIABLES["mcp"]` is
set — the signing key, five `APG_DATABASE_*` variables and `APG_POOL_SIZE` — and
`McpSettings` has no `conninfo`, no passfile and no pool size for a later change
to fill in. Its zero share of the connection budget is not an omission but a
decision, asserted by a test that parses the arithmetic (D407).

**The pre-request hook cannot write.** This repository measured that twice and
wrote it into two migration headers. 0008 and 0013 both record it: PostgREST
runs `db-pre-request` inside the request transaction, which is **READ ONLY on a
GET**, and an early version of the hook that kept an audit row *"turned the
entire read surface into 405 'cannot execute INSERT in a read-only
transaction'."*

**`mcp_audit_service` has existed unactivated since Session 3.** It is in
`naming.ROLE_SUFFIXES` and in no migration, no manifest placeholder and no
grant. The handoff is explicit that Session 9 owns *deciding* its fate.

## What was measured

A throwaway cluster on the pinned `pgvector:pg18` image (PostgreSQL 18.4), every
request made the way PostgREST makes one — as the authenticator, `SET LOCAL
ROLE` into the request role (ADR 0065/0066), because a privilege result measured
as a superuser measures nothing. **Nine arms, nine as designed**, with the
negative control run first: one expectation inverted produced `DIVERGES` and
exit 1, so the rig can tell success from failure.

| Arm | Question | Observed |
|---|---|---|
| a1 | Is the hook's `app.agent_id` readable inside a **VOLATILE** `SECURITY DEFINER` function in the same transaction? | the value |
| a1c | What does an unset custom GUC read as, through the `missing_ok` form? | **empty string**, not NULL |
| a2 | Can that definer INSERT into a table the caller holds nothing on, in a schema the caller cannot even USE? | inserted |
| a2c | *Control.* The same caller, the same table, directly. | **denied** (42501), 0 rows |
| a3 | Is the stored identity the GUC's, from a function whose only argument is a tool name? | agent and owner both the GUC's |
| a4 | Does a write that commits keep its audit row? | 1 row |
| **a5** | **Does a write that `RAISE`s keep its audit row?** | **0 rows** |

`api.mcp_agent_context()` already depended on a1 for a `STABLE` read, and
`AGT-READ-001` is green on the deployment — so a1 confirms a live property
rather than discovering one. a1c is the reason 0018 spells it
`nullif(current_setting(...), '')`, and that spelling is now measured rather
than inherited.

**a5 is the arm that changed the design.** The `RAISE` aborts the transaction
and the audit row inserted before it goes with it. That is not a defect to work
around — it is PostgreSQL being correct — but it decides what an in-transaction
record is allowed to claim.

## The part that matters

**A record written inside the transaction it describes can only ever describe a
committed change.** There is no arrangement of `SECURITY DEFINER`, exception
blocks or subtransactions that keeps the row: an exception handler rolls back to
its own savepoint and discards it just as surely as the aborting transaction
does. Recording a *failed* write durably would need an autonomous transaction —
a second connection — which is precisely the credential this plane does not hold.

So the two records are not redundant and neither can be dropped:

* The **in-transaction row** is unforgeable and unbypassable, and answers *what
  actually changed*. It sees a write that never went near the agent plane.
* The **MCP begin/complete record** answers *what was attempted*, with the
  denial, the failure, the elapsed time and the redaction. It sees a call that
  never reached the database.

## Decision

**The audit record is written by two `SECURITY DEFINER` functions in `api`,
called over PostgREST with the caller's own token.** `api.agent_audit_begin`
returns an id; `api.agent_audit_complete` closes it.

**Identity comes from the `app.agent_id` and `app.user_id` GUCs the hook sets,
and is never a parameter.** Neither function takes a principal, an owner, a role
or a scope. This is what makes `SEC-PARAM-001` structural rather than validated:
there is no argument for a caller to lie in.

**The two write RPCs append their own row in the same transaction when
`app.agent_id` is set**, and that row records a committed change only (a5). A
human caller sets no `app.agent_id` and is unaffected.

**Nothing is written from the pre-request hook**, and the reason is in its
header twice already.

**`mcp_audit_service` stays unactivated, and this is the decision rather than
the deferral.** The definer route needs no service identity, so activating one
would put a login role in production to write records that something else
writes. No manifest placeholder is added for it, and the AST guard forbidding
its name in any `mcp_*.py` stays exactly as strict.

## Alternatives rejected

**Give the MCP runtime a credential.** Reverses D407, requires a term in ADR
0099's fully-allocated 56 connections, and deletes a refusal that
`settings.load_mcp` currently makes at startup — all inside a session about
writes. The budget is the smaller objection; the larger one is that "the agent
plane holds no database credential" is a sentence this project can currently
prove.

**Route the audit write through auth-api.** It already holds `auth_service`, so
it would hold two database roles and the audit authority would sit in the
service that signs tokens. It also gives the agent plane a second upstream to
dial, where ADR 0125 deliberately has one.

**Write the record only inside the write RPCs.** Cheapest, and it cannot record
a denial — a call refused for a missing scope never reaches the database at all.
`AGT-AUDIT-001` requires denied attempts to appear.

**Write the record only from MCP.** Cannot see a write that reaches PostgREST
directly, which an agent token can (D480). Attribution a caller can route around
is not attribution.

## Consequences

An audited agent write costs **three** upstream round trips — context
resolution, begin, complete — plus the operation itself. ADR 0125 already spends
one on asking the authority rather than trusting the token, and that round trip
has still never been timed against the deployment. This session makes that open
item three times more load-bearing, and §10 of the plan says so.

`app_private.agent_audit` grows without bound. Nothing prunes it, exactly as
nothing prunes secret generations. Retention is Session 10's inheritance and is
recorded in the Session 10 handoff.

A caller that can reach PostgREST directly can call `agent_audit_begin` with a
tool name of its choosing. It cannot forge an identity, cannot alter or delete
any row, and cannot suppress a real one — the table is append-only to every
request role. What it can add is noise under its own true identity, which is a
weaker property than forgery and is stated here rather than discovered later.
