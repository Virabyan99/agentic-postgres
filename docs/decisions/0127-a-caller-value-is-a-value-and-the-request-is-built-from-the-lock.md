# 0127 — A caller value is a value, and the request is built from the lock

Status: accepted
Date: 2026-08-20
Session: 8, Run 6
Affects: ADR 0097, ADR 0100, ADR 0119, ADR 0120, ADR 0125, ADR 0126,
D437, D438, D439, AGT-SQL-001, AGT-READ-001, AGT-SCOPE-001, AGT-DRIFT-001,
`services/auth-api/app/mcp_query.py`, `services/auth-api/app/mcp_lock.py`,
`services/auth-api/app/mcp_tools.py`

## Context

`AGT-SQL-001` is the requirement the four tools exist under: **no SQL, no
fragment, no raw query string, no path, no runtime-selected operation.** Stated
that way it is a list of absences, and a list of absences is satisfied by any
implementation that has not yet been written badly. Run 6 has to turn it into a
construction rule that a reader can check.

The shape of the danger is specific. PostgREST takes its filters in the query
string, as `column=operator.value`. A caller supplies the *value*. If that value
can carry a `&`, it becomes a second parameter; if it can carry a `,` inside an
`in.(…)` list, it becomes two values. Neither is SQL injection, and both are the
same class of defect: **caller data crossing into the position of syntax.**

## What was measured

Against a live PostgREST on the locked digest, all eighteen migrations applied,
with two owners and two agents so that "the filter worked" cannot be confused
with "the result was empty anyway".

**The operators the contract names, and their spellings.** `eq.`, `neq.`, `gt.`,
`gte.`, `lt.`, `lte.`, `in.(a,b)` and — the one that is not its own name —
`is_null` on the wire is **`is.null`**. `select=` restricts the returned columns
exactly; `order=col.asc`; `limit=`. An unknown column, in `select` or in a
filter, is refused **400 `42703`**.

**The injection arm, with a control that can fail.** The first version of this
measurement proved nothing: the hostile value `alpha&owner_id=eq.<owner B>`
returned zero rows both encoded and unencoded — encoded because it is a literal
nobody's title matches, unencoded because **RLS already excludes owner B**. Two
arms agreeing for different reasons is not a control. Re-measured with an
injection whose effect is visible:

| `title=neq.<value>`, value = `zzz&limit=1` | rows |
|---|---|
| percent-encoded | **3** — the whole string is one literal, so `neq` matches everything |
| unencoded | **1** — parsed as `title=neq.zzz` **and** `limit=1` |

So percent-encoding defeats it, and the control shows the arms can differ.

**The in-list rule, which is not percent-encoding.** A member containing a comma:

| spelling | rows |
|---|---|
| `in.(weird,title)` | 0 — silently split into two members |
| `in.(weird%2Ctitle)` | **0 — percent-encoding the comma does NOT help** |
| `in.("weird,title")` | 1 |

PostgREST decodes the query string *before* parsing the list, so the comma must
be removed from list syntax by **quoting**, not by encoding. And inside a quoted
member, an embedded `"` needs a **backslash** escape, not the doubled quote SQL
uses:

| member | rows |
|---|---|
| `"he said "hi""` | 0 |
| `"he said ""hi"""` | 0 |
| `"he said \"hi\""` | **1** |

The full rule — escape `\` then `"`, wrap in `"`, percent-encode — was then
checked against eight awkward values (comma, quote, backslash, trailing
backslash, both together, close-paren, dot, plain), each compared against the
same value fetched by `eq.`, which needs no list syntax and is therefore the
answer the list form must reproduce. **Eight of eight agree**, and a value that
is not present returns 0, so the rig can tell a match from a miss.

## Decision

**Every part of a request except the caller's values comes from the lock; every
caller value is escaped for the position it occupies and can occupy no other.**

1. **The operation is chosen by name from the lock**, never assembled. A tool
   call names a *resource*; the resource's `operation.method` and
   `operation.path` are read from the lock, and there is no code path that
   accepts a path, a method or an operation id from a caller.
2. **Columns, filter columns, operators and orderings are checked against the
   lock's frozen sets** before a request is built. A column the lock does not
   list is refused here, not by PostgREST's 400 — because a 400 from upstream
   would mean a caller's string reached the query.
3. **Values are escaped by position.** A scalar operand is percent-encoded. An
   `in` member is backslash-escaped, quoted, then percent-encoded. `is_null`
   takes no operand at all and is emitted as `is.null`.
4. **Filters are AND-only and ordering is explicit.** There is no `or=`, no
   nesting, and no default order — an unordered page is a different page each
   time, and a tool that paginates over one is lying about its results.
5. **`limit` is the lock's `max_rows`, never the caller's**, and the caller may
   ask for fewer but not more.
6. **The metadata tools reach nothing.** `list_resources` and
   `describe_resource` answer from the loaded lock alone: no OpenAPI request, no
   database, no upstream call of any kind.
7. **Exactly four tools are registered**, their names asserted
   lexicographically, and their input schemas hashed against the canonical
   contract — so a fifth tool, or a changed schema, fails offline.

## Alternatives rejected

**Let PostgREST reject bad columns.** It does, with a 400 naming the column
(`42703`). Relying on it means the caller's string reached the upstream query,
and the refusal then depends on a schema cache rather than on the reviewed
contract. It also leaks the table name to a caller (ADR 0097).

**Percent-encode in-list members and stop.** Measured false: `%2C` still splits
the member. This is the specific belief a careful implementer would have held.

**Double the quotes inside a quoted member**, as SQL does. Measured false: 0
rows. Both wrong answers look right and fail silently by matching nothing, which
is the worst failure mode available here — a filter that quietly matches
nothing reads as an empty result, not as an error.

**Accept a caller-supplied `order` string and validate it with a regular
expression.** A regex over a caller's string is a parser nobody reviewed. The
lock already enumerates the permitted orderings; picking one by index is not a
restriction of the same feature, it is a different feature.

**Serve `list_resources` from the live OpenAPI document.** It would make
discovery depend on a document PostgREST builds from privileges at request time,
which is a different question from "what did a human approve" — and ADR 0119
already settled that capabilities resolve against the reviewed contract.

## Consequences

- **A caller cannot express anything the lock does not already permit**, so the
  reviewed contract is the whole surface and AGT-DRIFT-001 stays true: adding a
  PostgREST operation exposes nothing.
- The adapter refuses before it dials, so an invalid tool call costs no upstream
  request — and the refusal says which *input* was rejected without saying
  anything about schema or state.
- **The escape rule is measured, not conventional**, and it is written at the
  function that applies it. Anyone who changes it to the SQL convention will find
  a test that fails for the right reason.
- `run_report` shares the construction path but takes no filters, so its request
  is a POST to a named RPC with an empty body — the one place a method other
  than GET is reached, and it is still read-only.
