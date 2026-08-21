# 0130 — A refusal reaches the caller only through ToolError

Status: accepted
Date: 2026-08-20
Session: 8, Run 8
Affects: ADR 0097, ADR 0121, ADR 0125, ADR 0127, D274, D412, D433, D448, D449,
`services/auth-api/app/errors.py`, `services/auth-api/app/mcp_errors.py`,
`services/auth-api/app/mcp_telemetry.py`, `services/auth-api/app/mcp_tools.py`

## Context

ADR 0097 split refusals in two: a **structural** refusal tells an
unauthenticated or unauthorised caller nothing, because anything it said would be
a claim about state to somebody who has not established they may ask; an
**authenticated** caller may be told a state it can act on. `errors.py` is that
split made concrete for the application API — six fixed bodies, no prose, and
`OBJECT_UNAVAILABLE` collapsing four causes into one answer.

Run 6 wrote `ToolRefusal` messages in the same spirit: *"`secret` is not a
filterable column of `notes`"*, *"this resource requires ['notes:read',
'tasks:read']"* — messages that name the **input** and never the schema. Run 4
set `mask_error_details=True` on the server, for ADR 0097's reason.

Nobody checked whether the two interact.

## What was measured

Three ways of refusing, on the pinned framework, with a masked server and an
unmasked control:

| how the tool refuses | masked — what this deployment runs | CONTROL — masking off |
|---|---|---|
| a plain `Exception("column 'secret' is not queryable")` | **`"Error calling tool 'raises_plain'"`** — the message is gone | `"Error calling tool 'raises_plain': column 'secret' is not queryable"` |
| `ToolError("column 'secret' is not queryable")` | **`"column 'secret' is not queryable"`** | the same |
| a returned `{"error": …, "detail": …}` | passes through, `isError=False` | the same |

**`ToolError` is the framework's designated caller-facing channel, and it
bypasses the mask.** That is ADR 0097's split already expressed in the
framework's own vocabulary: silence by default, and one explicit type for what a
caller may be told.

**And Run 6's messages reach nobody.** `ToolRefusal` is a plain exception, so
every carefully-worded input refusal it raises is replaced by
`"Error calling tool 'query_resource'"` before it leaves the process. The
messages exist, are tested, and are invisible — **D274's shape**: a claim that
lives only where nobody reads it.

**A third thing was visible in the same output and is not about callers.** The
masked path logs a `rich` traceback panel with source lines, so the log is a sink
the canary has to cover.

**How far that goes was measured rather than assumed, and the first guess was
wrong.** The worry was that a traceback through `mcp_query` would render frame
locals — where a caller's filter operand lives. It does not: `show_locals` is
never set anywhere in the framework's logging setup, so `RichHandler`'s default
of `False` applies and the panel carries **source lines from this repository's
own code and no caller data**. The property is real and it rests on a default
this repository does not pin, which is what makes it worth writing down: a
framework bump that changed that default would turn every logged traceback into
a leak, silently.

## Decision

**A refusal reaches the caller if and only if it is raised as `ToolError`.
Everything else is masked, and the mask stays on.**

1. **Two vocabularies, in `errors.py`'s shape.** `mcp_errors.py` declares fixed
   bodies with stable machine tokens, split by who may read them:

   * **Caller-facing** (`ToolError`), for what an authenticated agent can act
     on: an input the lock does not permit, a scope it does not hold, a budget it
     exceeded. These name the **input** and never the schema, the upstream status
     or a row it did not receive.
   * **Masked** (plain exception), for everything structural: an upstream
     refusal, an unreachable upstream, a missing context. The caller gets the
     framework's opaque string, which is the right amount (D433 — the three
     measured 401s are indistinguishable, so relaying one would be a guess).

2. **`mask_error_details=True` stays**, and a test asserts it. It is what makes
   the first rule a boundary rather than a convention: a new plain exception is
   silent by default, and telling a caller something is the act that requires a
   decision.

3. **Telemetry is structured, per read, and durable nowhere** (D412). One record
   per tool call: the tool, the resource, the outcome, the row count, the elapsed
   milliseconds, and the **agent and owner ids**. It is written to the log and to
   nothing else; `mcp_audit_service` stays unactivated, because an audit identity
   in production before the record it writes has been designed is Session 9's
   decision to make with its own fail-closed contract.

4. **What a record may never carry**, and this is the canary's list: a **token**
   or any fingerprint of one, a **URL**, an **object key**, and **any caller
   value** — filter operands, column projections, or a row. The ids are
   deliberate and the values are deliberately absent: an owner id identifies a
   principal the deployment already knows about, where a note title is content.

5. **A logged traceback carries no caller data, and that is measured rather than
   configured.** `show_locals` is unset in the framework's logging setup, so the
   default `False` applies and a panel shows this repository's own source lines
   and nothing of the request. **It is a default, not a pin** — recorded here so
   a framework bump has to re-check it, and listed in the open items rather than
   claimed as a control this runtime enforces.

   What the runtime *does* enforce is narrower and is its own: an unclassified
   failure is logged with the exception's **type** and never its message, because
   a message is where a caller's value would be if one ever reached one.

## Alternatives rejected

**Return a structured refusal object instead of raising.** Measured to work, and
it is worse: `isError=False`, so a client that checks the protocol's own error
flag treats a refusal as a result. Making every caller parse a body to discover
failure is the mistake `errors.py` avoided by using status codes.

**Turn masking off and rely on message discipline.** It makes every future
exception caller-visible by default, including one raised by a library. The
current setting fails closed; that one fails open, and the failure is silent.

**A `ToolError` for structural refusals too, with a vague message.** A vague
message that is *reliably* vague is a fixed string, and a fixed string is what
the mask already produces — with the advantage that nobody has to keep it vague.

**Log the filter values for debuggability.** They are the caller's own data about
their own rows, so it feels safe, and it is not: a note title is content, the log
is read by operators and shipped by the journal, and D412 draws the line at
telemetry rather than audit precisely so this question has one answer.

## Consequences

- **Run 6's refusal messages become visible**, which is what they were written
  for, and the set of them is now a reviewed list rather than whatever a raise
  site happened to say.
- **A new refusal is silent unless somebody chooses otherwise.** The default is
  the safe one, so the review question is "may the caller be told this?" rather
  than "did anyone remember to hide it?".
- The canary scan gains a third subject. Session 7 looked for a URL and an object
  key; the agent plane adds the **token**, and the offline half asserts that no
  sink-writing call in the runtime is reachable from one.
- **No durable audit exists**, and `AGT-AUDIT-001` stays Session 9's placeholder.
  This ADR is the reason it can: telemetry answers "what happened" for an
  operator, and the audit record answers "what happened" for a record-keeper, and
  they are not the same artefact.
