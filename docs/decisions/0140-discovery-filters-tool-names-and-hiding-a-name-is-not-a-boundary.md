# 0140 — Discovery filters tool names, and hiding a name is not a boundary

Status: accepted
Date: 2026-08-22
Session: 9, Run 5
Affects: ADR 0120, ADR 0125, ADR 0127, ADR 0129, D421, D476, D495, D496,
`services/auth-api/app/mcp_authorization.py`,
`services/auth-api/app/mcp_tools.py`, `services/auth-api/app/mcp_runtime.py`,
`AGT-WRITE-001`, `AGT-SCOPE-001`

## Context

`Tool.discoverable_by()` — the disjunction of conjunctions ADR 0120 and D421
exist for — was compiled into the lock, asserted by two contract tests, and
**called by nothing in production** (D476). Session 8's discovery filtering was
one level down, inside the `list_resources` payload, and its deployment proof
said so in as many words: *"`run_report` must not appear among the resources
discovery returns, while the four tool NAMES still do."*

Four read tool names leaking to a reader who would be refused was untidy. A
**write** tool name leaking to a read-only agent fails `AGT-WRITE-001` on its
own words, so Run 5 is where `discoverable_by` gets its caller.

The decision that needs writing down is not *whether* to filter — the
requirement settles that — but **what filtering buys**, because the intuitive
answer is wrong and the measurement says so.

## What was measured (rig5, FastMCP 3.4.0, four arms, each with a control)

- **M1 — a filtered `on_list_tools` removes the name.** Returning a subset of
  `call_next`'s sequence is enough; `tools/list` shows only what was returned.
  CONTROL: the same server with the hook returning `call_next`'s answer
  unchanged shows both names, so the arms differ.
- **M2 — a hidden tool is still callable, by name, and it runs.** Hiding
  `secret_write` from the roster and then calling it returned the tool's result.
  **This is the load-bearing measurement**: filtering discovery is disclosure
  control, not access control. The client re-listed the roster when asked for a
  name it had not seen, the hook fired again, and the call proceeded anyway.
- **M3 — the context resolved in `on_request` is visible inside
  `on_list_tools`.** Measured over a real HTTP transport, not the in-memory
  client, because `on_request` is an HTTP-request-level hook and the seam is
  exactly the one D444, D450 and D454 were each found at. One middleware set a
  `ContextVar` in `on_request`; a second read it in `on_list_tools` and saw the
  value. CONTROL: the same pair with the first middleware not setting it — the
  second saw `None` and hid nothing, so a filter that hid unconditionally would
  have failed this arm.
- **M4 — `FastMCP.list_tools()` runs the middleware pipeline.** So the offline
  test that reaches a tool through the real pipeline measures the filter too,
  rather than measuring registration and calling it discovery.

## Decision

**Two levels, both enforced, and neither substitutes for the other.**

1. **Name-level.** A `ToolVisibilityMiddleware.on_list_tools` filters the
   roster by `Tool.discoverable_by(the caller's scopes)`, reading the context
   `AgentContextMiddleware` already resolved for this request (ADR 0125 — one
   resolution per request, nothing about it moves). A registered name the
   deployed lock does not carry is hidden rather than shown: a name nobody
   reviewed is not a name to advertise.
2. **Call-level.** Every tool re-checks the caller's scopes against the lock
   when it is invoked — `_resource_for` for a read, `_write_for` for a write —
   and refuses. **M2 is why this sentence is in an ADR and not a comment**: a
   caller that knows a hidden name can call it, so the roster is a courtesy to
   a well-behaved client and the scope check is the boundary.

The two are proved separately and by different assertions: a **name** hidden
from a caller without its scope set, and a **resource** hidden behind a name
that stays visible. A single proof that conflated them would pass while one of
the two was absent.

## Alternatives rejected

- **Filter the roster and drop the call-time check.** M2 refutes it directly: a
  hidden tool is callable. This would be the most expensive shape of this
  repository's recurring defect — a control that appears to work because
  nothing ever tests the route around it.
- **Keep the resource-level filter only, and refuse writes at call time.**
  Satisfies "cannot invoke" and fails "cannot discover"; `AGT-WRITE-001` names
  both.
- **Resolve the caller's context inside `on_list_tools`.** A second resolution
  per request, a second place deciding what a refusal is, and ADR 0125's whole
  point undone. M3 shows the first resolution is already visible there.
- **Filter inside each tool's registration closure.** Discovery is not a tool
  call; there is no closure to put it in.

## Consequences

- **The deployed document's `mcp.tool_count` is no longer what any caller's
  `tools/list` returns**, and the two answer different questions: the document
  says what the deployment *serves* (six), discovery says what *this caller* may
  see. The live proof for a `meta:read`/`notes:read` agent is therefore three
  names — `describe_resource`, `list_resources`, `query_resource` — with
  `run_report` and both writes absent. The plan expected six from both and was
  written before the filter existed (D496).
- **Session 8's live discovery proof gains a name-level half.** Its resource
  assertion is unchanged and its docstring's *"while the four tool NAMES still
  do"* is no longer true of `run_report`; the sentence is replaced by the
  stricter pair, which is the ADR-authorised form of a test change.
- A tool added to the lock and not to `discovery_scope_sets` is invisible to
  everyone rather than visible to everyone — the fail-closed direction, and the
  `load_lock` check that every tool declares a non-empty set already prevents
  it reaching here.
- Discovery costs one `discoverable_by` per registered tool per `tools/list`,
  over an in-memory lock. No upstream call is added; the round-trip count per
  request is unchanged.
