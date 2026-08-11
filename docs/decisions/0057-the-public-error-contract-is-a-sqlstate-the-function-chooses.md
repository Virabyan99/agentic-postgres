# 0057 — The public error contract is a SQLSTATE the function chooses

Status: accepted
Date: 2026-08-11
Session: 5, Run 5
Affects: API-ERR-001, API-RPC-001, SEC-ANON-001, SEC-PRIV-001

## Context

D130 struck an error table the runbook froze and replaced it with a rule: the
HTTP mapping is written from the codes that exist, and any further code is
created *by the RPC that raises it*, with a test that produces it. What D130
could not say is **how** a code becomes a status, because that is a property of
the locked PostgREST and nobody had run it.

Session 3 raises three codes — `AP401`, `AP404`, `AP900` — as message prefixes.
The SQLSTATE stays PostgreSQL's default `P0001` for all of them, because
`RAISE EXCEPTION 'AP401: …'` sets no `ERRCODE`. Run 5 measured what v14.16 does
with that, and with the alternatives, against a real migrated cluster:

| raised as | HTTP | body |
|---|---|---|
| `RAISE EXCEPTION 'AP401: …' USING HINT = …, DETAIL = …` | **400** | `{"code":"P0001","hint":"<the hint>","details":"<the detail>","message":"AP401: …"}` |
| `… USING ERRCODE = 'PT401'` | **401** + `WWW-Authenticate: Bearer` | `{"code":"PT401", …}` |
| `… USING ERRCODE = 'PT404'` | **404** | |
| `… USING ERRCODE = 'PT409'` | **409** | |
| `… USING ERRCODE = 'PT422'` | **422** | |
| `… USING ERRCODE = '28000'` | **403** | |
| a JSON document as the message | status of the SQLSTATE | the JSON arrives as a **string** in `message`, unparsed |
| an uncaught error (`1/0`) | **400** | `{"code":"22012","message":"division by zero"}` |

Two of those lines are the decision.

**`P0001` is 400.** Every application error Session 3 raises would have reached
an HTTP caller as a generic bad request — including "no request identity", which
is the one status a client needs in order to know it should authenticate.

**`HINT` and `DETAIL` are published verbatim.** This is the one that would have
shipped. `0005-write-rpcs.sql` raises `AP401` with
`HINT = 'SET LOCAL app.user_id before calling this function.'`, written for a
developer at a `psql` prompt in a session where nothing served HTTP. Published,
it is a public sentence naming an internal GUC and an internal mechanism, in
answer to an unauthenticated request, on the most frequently hit error path in
the API. Nothing about it looks like a leak in the migration that contains it.

## Decision

**The SQLSTATE carries the status, and nothing a caller can reach carries a
`HINT` or a `DETAIL`.**

- `PT401` — no request identity, or claims that could not be read. 401, with the
  `WWW-Authenticate: Bearer` challenge PostgREST attaches to it.
- `PT404` — no such object. Raised where "not yours" and "does not exist" are
  answered identically, because distinguishing them is itself a read.
- `PT409` — the row is not in the expected state. Optimistic concurrency.
- `PT422` — the request is well-formed and asks for something the domain does
  not permit, such as a transition that changes nothing.
- `AP900` stays `P0001` with a `HINT`, and that is deliberate: it is raised only
  by a `migrate:down` block, which no HTTP request can reach. Its audience is an
  operator holding a terminal, and the hint is the useful part.

The `AP…` prefix stays in the message. It is the code Session 3's direct-database
tests match on, it survives into the HTTP body unchanged, and dropping it to make
the SQLSTATE the only identifier would rewrite passing assertions to say the same
thing differently.

**A code is created by the function that raises it.** `PT409` and `PT422` arrive
in this session because `api.update_task_status` arrives in this session; they
were not available to be asserted before, and D130 refused to let them be.

## Consequences

**Every error the write surface produces is now a measured pair.** Against the
real migrated schema: a missing identity is 401 with the challenge, a fictional
task and another owner's task are both `PT404`, a stale `p_expected_status` is
`PT409`, and a no-op transition is `PT422`. The happy path is 200.

**Two error paths are still PostgreSQL's, not ours, and are accepted.** A value
outside the enum is `22P02 invalid input value for enum task_status: "abandoned"`
— 400, naming the type but not its schema — and a malformed body is PostgREST's
own. Both are caller mistakes about a shape the published OpenAPI document
states, so what they disclose is what the document already says.

**`API-ERR-001` gets an executable form.** "Discloses no SQL, role name, schema
path, or hint containing an internal name" becomes: no response body carries a
non-null `hint` or `details`, which is a property of every raise site and is
checkable both offline against the migration text and live against the service.

**The rest of the runbook's table stays struck.** `AP001`, `AP002` and `AP500`
still have nothing that raises them, and this ADR does not add them. `AP002`
is the tempting one — a validation code feels like it must be needed — and the
answer is that PostgreSQL already produces a specific, non-leaking status for
every input this surface rejects.

## Alternatives considered

**Keep `P0001` and map the status in PostgREST configuration.** There is no such
mapping to configure; the SQLSTATE is the mechanism. The nearest real option is
a reverse proxy rewriting statuses by body inspection, which puts the error
contract in a middleware that cannot see which function raised what.

**A structured JSON document as the exception message.** Measured, and it does
not work the way it appears to: the JSON arrives in `message` as an escaped
string, so the client gets a document containing a document. It also duplicates
`code`, which the SQLSTATE already supplies.

**Strip `HINT` and `DETAIL` at the edge instead of at the source.** Rejected.
It would work for the responses that pass through Traefik and not for the ones a
direct-transport client sees, and it puts the redaction furthest from the person
writing the `RAISE`. The rule "a caller-reachable raise carries no hint" is
checkable in the migration diff, where it is being introduced.

**Use `28000` (invalid authorization) for the missing identity, since it is
semantically exact.** Measured as **403**, which is the wrong answer: 403 says
"authenticated and not permitted" to a caller that presented no identity at all,
and it carries no `WWW-Authenticate` challenge. Semantics lost to the status
code that actually ships.
