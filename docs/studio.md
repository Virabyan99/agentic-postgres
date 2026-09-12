# Studio

`apg studio` opens a web page on `127.0.0.1` that shows you your deployment.
It is defined by ADR 0205, and the sentence that decides everything else in it
is: **Studio is a client, and it holds nothing you do not hold.**

Not a console, not an admin panel, not a database tool. A client — with your
own short-lived login token in its memory, making the same requests you could
make by hand, and refusing the ones your token would be refused.

Two consequences follow, and they are the reason the rest of this page is
short:

- **There is no SQL box.** Not hidden, not behind a flag, not disabled in the
  page — absent. A human running SQL through a product surface would make
  Studio an authority, and this repository has exactly one door for SQL
  (`bin/db.sh sql`, over hash-verified generated files). The query view builds
  a PostgREST request out of names the surface published, and that is the whole
  of what it can do.
- **The browser never sees the token.** The process holds it; the page holds a
  per-launch cookie. Everything the page can reach, it reaches by asking the
  process to ask.

---

## 1. Launching it

```bash
bin/apg.sh studio --project project.yaml --outputs alpha-outputs.json
```

`--outputs` is a **deployed** document — an op-owned copy of what a deploy
published, not a render (ADR 0158, D132). A render says what was asked for; a
route is an observation of what happened, and Studio is a client of what
happened. On this project the copies live at `/home/op/<key>-outputs.json` on
the host and, fetched, at `alpha-outputs.json` / `beta-outputs.json` in the
checkout root.

```bash
bin/apg.sh studio --project project.yaml --outputs alpha-outputs.json \
  --username ada --password-file ~/.apg-ada
```

The password comes from a **prompt** or from a **`0600` file**, and from
nowhere else. There is no `--password` flag and no environment variable is read
for one: a value in an argument is in `ps` and in a shell history, and a value
in the environment is in `/proc/<pid>/environ`. A password file others can read
is refused with exit 2 and the mode it found.

Studio prints two lines and then waits:

```
surface ok 808ac715c09aeebc…
open http://127.0.0.1:41287/open/GVh0M3…
as ada on alpha
```

Open that URL. The path sets the launch cookie — `HttpOnly`, `SameSite=Strict`
— and redirects to the page. Stop it with Ctrl-C; it ends the login session it
opened.

**It binds `127.0.0.1` and there is no flag for anything else.** Binding
elsewhere would need TLS a workstation process cannot get from the edge, and a
switch that turned the decision off would be the decision.

---

## 2. The four answers

At launch Studio fetches the served REST document **as you** and answers one of
four ways — the same four a generated client's `init()` answers, because it is
the same question (ADR 0204).

| Answer | What it means | What happens to the views |
|---|---|---|
| `ok` | the deployment serves the surface this checkout describes | everything is available |
| `stale_contract` | it serves a **different** one; both digests are printed | Schema and Query are refused (409); Audit, Capabilities, Agents and Session stay |
| `unreachable` | the REST route did not answer at all | same |
| `unreadable` | it answered with something this cannot be read as a document | same |

`unreachable` and `unreadable` are two different *I could not determine it* and
neither is `stale_contract` (ADR 0195). A client that could not reach a service
knows **nothing** about its contract, and reporting that as a disagreement
would send you to re-capture a snapshot that was never in question.

### `stale_contract` has two causes and the launch line names both

```
surface stale_contract served 1da00c119b984b82… expected 808ac715c09aeebc…
  either the capture moved -- run bin/apg.sh generate --project project.yaml --
  or ada holds a role this surface is not granted to; an administrator is
  served the anonymous document
```

**PostgREST serves a document scoped to the caller's grants**, measured in rig
24d against this project:

| subject | bytes | paths | definitions | equals the capture |
|---|---|---|---|---|
| `authenticated` | 16,024 | 8 | 3 | **yes** |
| `project_admin` | 2,393 | 1 | 0 | no |
| `anon` | 2,393 | 1 | 0 | no |

An administrator is served the anonymous document, byte for byte, because the
administrative role administers the auth service's endpoints and holds nothing
in `api`. So **an administrator will always see `stale_contract`, and nothing
is wrong.** Log in as an ordinary subject to use the Schema and Query views;
log in as an administrator to use the Audit, Agents and Session views. That
split is not a limitation of Studio — it is your deployment's authorization,
showing through.

This is why the two contracts are kept apart everywhere in the page: a stale
REST capture says nothing about the audit record, and folding them would let
one wrong snapshot hide every denial in it.

---

## 3. The views

### Schema

Relations with their columns, types and nullability; the RPCs with their
arguments; the enums. All of it from the four committed contracts this checkout
holds — **confirmed** by the deployment, which is what the `ok` answer is, but
not *fetched* from it. Served only under `ok`.

### Query

Pick a relation, tick columns, add `[column] [operator] [value]` filter rows,
choose an order and a limit. The form sends **structure** and never a URL: the
process turns it into exactly one PostgREST `GET`, with every name checked
against the surface and every operator against the contract's closed set.

Values are percent-encoded with no safe characters, so `,` `.` `(` `)` and `&`
reach the service as characters rather than as syntax. Reads only — there is no
write anywhere in the forwarder's REST half.

**RLS applies, because nothing here decides anything.** PostgREST verifies a
token the auth service signed and the database applies the policy. You see what
your token can see.

### Audit

`GET /admin/audit` as you, rendered whole. Every column the endpoint returns,
with `denial_reason` in a column of its own and refused rows marked — ADR 0178:
a denial names the boundary that refused it, and since migration 0032 the
reader returns it.

Above the table, always visible:

```
showing 500 of 500 rows on this page; the page is the newest 500
```

**The filter boxes hide rows in the page and nowhere else.** They do not become
query parameters, and the forwarder refuses any parameter but `agent_id` and
`owner_id` with a 400 — so there is no request shape in which a filter narrows
what was *read*. A viewer who could ask for `outcome=served` and be shown a
count would never learn there had been refusals (D1248).

**What this view cannot tell you is how many rows there are.** The page is the
newest 500 and says so. `agent_audit` grows without bound and nothing prunes
it; the total is a question for `bin/db.sh`, and a retention policy is a
released migration nobody has written yet (D1255).

### Capabilities

The tools compiled into this project's capability lock — name, kind, arguments,
scopes — and the lock's `tools_sha256`.

> This is the checkout's compiled lock. Whether the plane serves it is
> `bin/apg.sh doctor`'s question, not this page's.

That sentence travels with the data rather than being written into the page,
and this view is **served whatever the surface answered**: the lock and the
REST document are two contracts, and no launch answer is evidence about the
first (D1274). `list_resources` on the agent plane reports the lock the running
process actually loaded (D1201); Studio does not ask, because Studio holds a
human's token and a human's token is not an agent credential.

### Agents

`GET /admin/agents` as you, and a **Revoke** control per row.

The control reveals a box that says *type the agent id to confirm*. Typing
anything else is refused with 422 and the sentence names both values and says
nothing was changed — `--confirm`'s meaning everywhere in this repository, and
the refusal happens **in the process**, before any upstream request exists to
have changed anything. A confirmation the page checked and the process did not
would be a hidden control: whoever drives the process is not necessarily the
page (ADR 0140).

A confirmed revocation is `PATCH /admin/agents/{agent_id}` — the existing
endpoint, not a second path. The agent stops on its **next request**, not at
its token's expiry, because `agent_claims_are_current` no longer matches.

### Session

`GET /auth/me`, `GET /auth/sessions`, and one line saying whether this launch
knows which row is its own.

It usually does: the launch records the time before it logs in and takes the
single newest live session created after it. When two sessions share a
timestamp it says it **could not determine** which was its own and ends none,
rather than guessing and revoking somebody else's (ADR 0195). The rows are
there either way.

---

## 4. What Studio never does

Each with the proof that keeps it true.

| It never | Because | Proved by |
|---|---|---|
| runs SQL | a human running SQL through a product surface would make this an authority | `test_the_forwarder_table_has_no_rest_write`, `test_studio_core.py`'s query-builder proofs — the only path to a request is `rest_query`, which builds one `GET` out of validated names |
| holds anything you do not hold | the DX layer holds nothing the human does not hold | `test_a_token_without_the_audit_scope_is_refused_and_classified` — as an ordinary subject the audit view answers `refused` |
| show the page your token | the process exists precisely so the credential stays on one side of the socket | `test_no_page_response_header_or_asset_carries_the_token` |
| log a value you sent | a default request logger writes the query string, and a query string carries a query builder's values and the launch key | `test_nothing_studio_prints_is_a_token_a_key_or_a_value` |
| relay an upstream body | a 403 carrying a column name would reach a browser through a tool that promised not to do that (D433) | `test_an_upstream_refusal_is_classified_and_its_body_is_not_relayed` |
| verify a JWT | Studio is a holder, not a verifier; four verifiers exist and only auth signs | `test_studio_holds_no_key_and_verifies_nothing` |
| bind anywhere but loopback | see §1 | `test_the_listener_is_on_loopback_and_nowhere_else`, `test_there_is_no_bind_flag_and_the_address_is_a_constant` |
| load third-party code | a `<script src>` at a CDN is a supply chain | `test_studio_assets_carry_no_third_party_code`, `test_the_page_carries_no_inline_script_and_no_external_reference` |
| answer a request that failed a check | five checks run first, on every request | `test_studio_server.py`'s refusal proofs |

---

## 5. The five checks

Every request, before anything else, and each answers a different question:

| Status | When |
|---|---|
| **405** | `OPTIONS`. Refusing it is what makes the custom header a boundary: a cross-origin page cannot set `X-Apg-Studio` without a preflight, and no preflight succeeds |
| **421** | the `Host` is not the address this process bound — what a DNS-rebinding attempt looks like from in here |
| **403** | an `Origin` that is present and is not this page's. Absent is not foreign: same-origin navigations send none |
| **401** | no launch cookie. The one exempt path is `/open/<key>`, which is where the cookie is issued |
| **403** | a `/__apg/` call without `X-Apg-Studio` |

A refused request's **body is never read**: a POST announcing a megabyte with
one byte sent gets its refusal and `Connection: close`, and does not hang.

---

## 6. Exit codes

Runbook §2's convention.

| Code | Meaning |
|---|---|
| 0 | success |
| 2 | invalid operator input, including a password file others can read |
| 3 | a missing local prerequisite |
| 4 | the project has not been rendered; the message names the command that renders it |
| 5 | the deployed document publishes no usable route, or an `http` route to a host that is not loopback |
| 6 | the deployment refused this credential |
| 9 | the deployment could not be reached |

---

## 7. If something goes wrong

**`that is a rendered document; the REST route is an observation` (exit 2).**
You pointed `--outputs` at `.generated/<key>/outputs.json`. Fetch the deployed
copy instead: `scp op@<host>:/home/op/<key>-outputs.json .`

**`the deployed document publishes no ready rest route` (exit 5).** The
document is from a deploy that did not finish, or from a first pass, where
ports and the app route are reported `unavailable` by design. Deploy the
project, or use a document from one that was deployed.

**`routes.app.url is 'http' to host '…'` (exit 5).** Studio requires `https` to
anything but loopback. A token crossing a network in cleartext is the one thing
this tool exists to avoid. There is no flag.

**`the deployment refused this credential` (exit 6).** The endpoint fails
identically four ways by decision (ADR 0097) and so does this line: an unknown
subject, a wrong password, a disabled subject and a locked one are one sentence
here. Check the username; if you are sure of it, an administrator can look at
`GET /admin/users`.

**`could not reach <url>` (exit 9).** A transport failure, not an answer.
Check the route, then the edge: `bin/apg.sh doctor --project project.yaml`.

**`<file> is mode 0644; it must be 0600 or stricter` (exit 2).** A password
file others can read is a password others have. `chmod 600` it.

**`surface stale_contract` and you expected `ok`.** Read §2 first: if you are
logged in as an administrator, that is the correct answer and nothing is wrong.
Otherwise the capture has moved — `bin/apg.sh generate --project project.yaml
--check` says so, and `bin/api-contract.sh` re-captures.

**The page says the studio process did not answer.** The process stopped, or
the browser is on a stale URL from an earlier launch. Each launch binds a new
port and mints a new key; there is no way to reconnect a browser to a launch
that ended, by design.

---

## 8. What it is built from

One standard-library Python process, three first-party files, and zero lines of
anybody else's code.

| Piece | Where |
|---|---|
| the decisions | `src/agentic_postgres/studio.py` — no I/O in any of them, so a battery can drive every refusal without a socket |
| the process | `bin/studio.py` — the socket, the token, every upstream request |
| the operator surface | `bin/studio.sh` |
| the page | `services/studio/index.html`, `studio.js`, `studio.css` |

`services/studio/` is not a service: it builds no image and no deploy runs it.
It is three files an operator command hands to a browser on loopback.

Related: [Generated clients](generated-clients.md) (the same surface question,
answered for a package), [The developer environment](dev-environment.md),
[Threat model](threat-model.md), [Capacity envelope](capacity-envelope.md).
