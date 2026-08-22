# 0143 — A query string is parsed strictly, for the same measured reason a request body is

Status: accepted
Date: 2026-08-22
Session: 9, Run 7
Affects: ADR 0087, ADR 0097, ADR 0142, D274, D300,
`services/auth-api/app/strict_query.py`, `services/auth-api/app/openapi_docs.py`,
`services/auth-api/app/routes.py`

## Context

`GET /admin/audit` (ADR 0142) is the **first** endpoint in the auth service to
read a query string. Every route before it takes a path parameter, a JSON body,
or nothing.

The service already refuses what the default stack accepts on the body side, and
`routes.py`'s header says why:

> Starlette's `Request.json` is `json.loads(await self.body())` with no hook, so
> `{"username": "alice", "username": "root"}` reaches a model as `root` and the
> duplicate is gone by the time anything could notice.

A query string is a multidict. The same question had to be asked of it rather
than assumed either way, in either direction.

## What was measured

rig7, on the locked Starlette 0.49.3. **Control arm first**: each key sent
exactly once, which had to read back one value per key and two pairs. It did.

| Arm | Observed |
|---|---|
| `agent_id=aaa&limit=7` (control) | `len(multi_items()) == 2`, one value each |
| `limit=1&limit=9999`, via `__getitem__` | **`"9999"`** |
| the same, via `getlist` | **`["1", "9999"]`** |
| the same, via `multi_items` | **both pairs** |
| `Limit=1&limit=2` | **two distinct keys** |
| `limit=` | present, `""` |
| `limit=7&cursor=x` | `cursor` present and readable |

And of `int()`, which the bound is built on: it accepts surrounding whitespace,
a leading `+`, an underscore separator (`"1_0"` is ten) and **any Unicode
decimal digit** (U+0665 is five). `"5.0"`, `"0x10"` and `""` raise.

**Two facts, and they point in opposite directions.**

`QueryParams.__getitem__` resolves a repeat to its **last value, silently** —
the body defect exactly. A caller that sends a modest bound and an enormous one
gets the enormous one, and an access log written from the first pair describes a
request that did not run.

But **unlike a JSON body, the duplicate survives**. `json.loads` returns a dict
and by then the first value is gone, which is why `strict_json` needs an
`object_pairs_hook` — there is no later check that could find it. A query string
stays a multidict all the way through, so the repeat is still there to be
refused.

## The decision

**`strict_query`, a sibling of `strict_json`, and the route parses rather than
declares.**

* **A repeated parameter is refused**, not resolved. Eleven lines of comparison
  over `multi_items()` rather than a parser hook, because the measurement says
  that is all it takes here.
* **An unknown parameter is refused.** `models.py`'s reasoning, over the query
  string: without `extra="forbid"`, pydantic accepts and *discards* an unknown
  member, so a client's attempt to name its own authority leaves no trace at
  all. A silently ignored `?owner_id=…` is a reader who believes they scoped a
  search and did not.
* **The allowlist is case-sensitive**, because the keys are. Folding case would
  accept `LIMIT` and read nothing.
* **An empty value is a supplied value.** `?limit=` is present, so it is refused
  by the converter rather than falling through to a default — which is the one
  path by which a caller could make a bound disappear by supplying it in a way
  that reads like supplying it.
* **A bound refuses and never clamps.** A clamp answers a different question
  than the one asked and says nothing about having done so.

### The route declares its parameters to the document by hand

FastAPI's `Query` binding would inherit exactly the defect above — a scalar
parameter takes the last value — so nothing here is bound. `openapi_docs
.query_parameter` emits the `parameters` fragment instead, merged through
`openapi_extra` (ADR 0087's mechanism, and it is `parameters` being *added*
rather than merged, because a route declaring nothing generates no such key).

**That split has a cost and it is named rather than absorbed.** The fragment and
the parser's allowlist are two statements of one surface, and nothing in the
framework holds them together. An endpoint whose document names a filter the
parser rejects is **D274's shape**: `/docs/rest` was proved at 401 and 200 for
four runs and had never rendered, because nothing requested the script its own
markup named.

So a contract test compares them —
`test_the_documented_query_parameters_are_the_parsed_ones`, and a second one for
the `limit` range and its default. Both read the generated document on one side
and `routes.py`'s constants on the other, so a parameter added to one and not
the other fails offline.

### The refusals name the parameters, and the order is what makes that safe

`authenticate` → `require_scope` → **then** parse. A route that parsed first
would answer `422 unknown query parameter: 'cursor' (this endpoint takes
agent_id, limit, owner_id)` to a caller holding no credential — handing an
anonymous prober the filter names and the fact that the endpoint exists.

By the time any of these refusals can fire, the caller is an authenticated
administrator, which is the shape `errors.invalid` is reserved for (ADR 0097,
and `_body`'s own comment). A test asserts the ordering from the outside, over
both wrong-caller cases — no token, and a token whose subject holds every other
administrative scope — because reading the handler top to bottom is not a proof
that it stays that way.

## Consequences

Every future query-string endpoint in this service goes through `strict_query`
and declares its parameters through `openapi_docs.query_parameter`. The
allowlist is passed in by the caller, so a second endpoint is a second constant
and a second document fragment, held together by the same comparison test —
which needs one line per endpoint and is the thing that stops being written.

**Nothing generalises this to the storage surface or to PostgREST.** The storage
routes take path parameters and bodies; PostgREST's query string is its own
language and is bounded by `mcp_query`'s escaping rules (ADR 0127), which is a
different problem with a different measurement behind it.

The `int()` breadth is written down where the bound is, because three of the four
accepted forms read like a permissive parser and the fourth reads like a bug, and
neither is true of a value that a range check still has to survive.
