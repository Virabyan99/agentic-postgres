# 0136 — An agent-plane function that writes takes arguments, and GET refuses it for the reason the hook cannot write

Status: accepted
Date: 2026-08-22
Session: 9, Run 1
Affects: ADR 0050, ADR 0057, ADR 0118, ADR 0135, D474, D490,
`schemas/api-surface.schema.json`, `src/agentic_postgres/api_surface.py`,
`contracts/postgrest-api-surface.yaml`

## Context

ADR 0050's invariant is that **nothing exists in `api` which the reviewed
contract does not name**. Migration 0019 creates two functions in `api` —
`agent_audit_begin` and `agent_audit_complete` — so both must be named there.

The contract has three sections and none of them fits.

* `relations` is for views.
* `rpcs` is the published human surface. A name here must be **present** in the
  approved OpenAPI snapshot, and these two are granted to the agent roles only,
  so they are absent from a document built as `api_documentation` (ADR 0118).
* `agent_rpcs` fits in every respect but one: `api_surface.py` refuses any entry
  that declares arguments, and the schema states it as `maxItems: 0`.

The audit functions cannot be argument-free. At least one of them must carry a
tool name, and `complete` must carry the id of the record it closes.

The rule's stated reason is precise, and worth quoting because the measurement
below is about exactly it: *"PostgREST serves a stable function over GET as well
as POST, so an argument here reaches the query string — and a caller-supplied
value makes the tool's operation a runtime choice."*

## What was measured

A live PostgREST **v14.16** on the pinned image, against a real cluster on the
pinned `pgvector:pg18`. Four arms, and the negative control inverted one
expectation so the rig had to report `DIVERGES`.

**Both of the predictions going in were wrong**, in opposite directions.

| Arm | Request | Observed |
|---|---|---|
| control | `GET /rpc/stable_noargs` | `200` |
| the rule's justification | `GET /rpc/stable_with_args?p_value=leaked` | `200`, body `"stable-args:leaked"` |
| the prediction | `GET /rpc/volatile_with_args?p_tool=leaked` | **`200`**, body `"volatile-args:leaked"` |
| the one that decides it | `GET /rpc/volatile_marks?p_tool=…` (the function INSERTs) | **`405`**, `25006 cannot execute INSERT in a read-only transaction`, **and no row was written** |
| the intended route | `POST /rpc/volatile_marks` | `200`, row written |

Two facts, and they pull in opposite directions:

**PostgREST does not refuse GET on a VOLATILE function.** The first prediction
was that it would answer 405 on volatility alone. It does not — it executes the
function and takes the argument from the query string. So "the function is
volatile" is *not* what keeps its arguments out of a URL.

**A function that actually writes is refused over GET**, by the same mechanism
that stops the pre-request hook keeping an audit row (D474, and 0008's and
0013's headers): PostgREST runs a GET in a **read-only transaction**. The
refusal is `25006` surfaced as `405`, and the write does not happen.

## The part that matters

**The 405 prevents the effect. It does not prevent the disclosure.**

By the time PostgreSQL raises `25006`, the request line has already been formed,
sent, and written to every log and cache between the caller and the database.
The argument leaked whether or not the call succeeded. So the objection behind
`agent_rpcs`' `maxItems: 0` **survives the measurement** and it would be wrong to
relax that rule — which is what a first draft of this migration did by putting
both functions under `agent_rpcs` and deleting the check.

What the measurement does establish is narrower and still useful: a function
that writes cannot be *made to do anything* over GET. So the residual exposure
for this category is disclosure of its arguments, and nothing else — no state
change, no side effect, no partial write.

That is a different risk from the one `agent_rpcs` is protecting against, and it
is bounded by what the arguments are allowed to contain rather than by whether
they exist.

## Decision

**A fourth section, `agent_write_rpcs`**, for agent-plane functions that write.

1. **`methods` is `["POST"]` and only that.** Not because a reviewer prefers it
   but because it is the served surface: GET reaches the function and the
   function's own write is refused by the read-only transaction. An entry
   naming GET would describe a route that cannot complete.
2. **`arguments` is non-empty**, and every argument is named. The list is the
   review surface: it is exactly what could appear in a URL if somebody GETs the
   endpoint, so a reviewer reads the disclosure rather than inferring it. This is
   the same discipline as the capability lock's frozen column allowlist.
3. **No argument may carry a secret, a token, a credential or another
   principal's identifier.** The two functions here carry a tool name, a request
   id, an outcome, two integers and a parameter document the runtime has already
   redacted per the lock's `audit.redact`. None is a credential.
4. **Every name is absent from the approved OpenAPI snapshot**, exactly as
   `agent_rpcs` requires, and shares no name with any other section.
5. **`agent_rpcs`' `maxItems: 0` does not move.** A read function that takes
   nothing keeps the stronger guarantee, and the new category does not become
   the place to put things that were merely inconvenient to make argument-free.

## Alternatives rejected

**Relax `agent_rpcs` to permit arguments.** The measurement says its reason is
intact for STABLE functions, which is what that section holds. Widening a rule
whose justification still applies, in order to fit two functions it was not
written for, is how a boundary stops meaning anything (D300's shape).

**Put them under `rpcs`.** They would then have to appear in the approved
snapshot, which requires granting `api_documentation` EXECUTE, which publishes
two agent-plane functions to every anonymous reader of the document. ADR 0118
exists to prevent exactly that.

**Make the functions argument-free.** `complete` must name the record it closes.
An argument-free design would have to infer it — "the most recent open record for
this agent" — which is wrong under concurrency and turns a precise reference into
a guess.

**Do it with one function instead of two.** Then there is no record before the
work, and "records an audit entry *before* forwarding" is the requirement.

## Consequences

`api_surface.py` gains one validation block and `declared_objects` gains one
source, so an unnamed object in `api` still fails the gate.

The category's safety property — *these functions really do write, so GET really
is ineffective* — is asserted offline only as a contract shape. **The property
itself is a live-host proof**: a GET against the deployed endpoint must answer
405, and that belongs with Run 7's proofs rather than being assumed here. Until
it runs, the 405 is measured on a rig and not on the deployment.

A future entry in this section that does *not* write would silently lose the
guarantee, because nothing offline can tell a writing function from a reading
one by looking at the contract. The live proof is what closes that, and it is
named here so the next author knows it is load-bearing rather than ceremonial.
