# 0291 — A project is created in the console; its handoff token is shown once, and the claim stays the client's

- **Status:** Accepted
- **Date:** 2026-10-24
- **Session:** 46, Run 1 (`docs/plans/session-46-implementation-plan.md`, D2864,
  D2865, D2869; Run 1's rows D2890, D2892, D2895; rig 46a)
- **Affects:** `services/console/public/app.js` (`overview` gains *New project*
  per organisation; a creation view; the shown-once panel at acceptance; the
  overview's CLI sentence removed; Run 4), `bin/cloud.py` and `bin/project.sh`
  (`project claim --token-file FILE`; Run 4), `site/pages/quickstart.md` and
  `site/pages/docs/projects.md` (browser-first; written in Run 4, published
  with the bump, D2883), `tests/contract/test_console_create.py` (new),
  `tests/contract/test_cloud_cli.py`. Requirements `CON-CREATE-001`,
  `CON-CREATE-002` (Run 8).
- **Related:** ADR 0246 (the control plane holds nothing that opens a project),
  ADR 0254 (`not_available`), ADR 0260 (the handoff by hash — this ADR changes
  where the token is made, never what reaches the plane), ADR 0273, ADR 0274
  (the plan limit read first), ADR 0280/0281 (the console, its session), ADR
  0285/0288 (its policy, unchanged here), D2165, D2316/D2345 (a key reused after
  a deletion), D2702.

## Context

Stage 5's success criterion for a person is *a working connection string
reached in the browser* (the stage plan `:1119-1124`). Creation has been
CLI-only since Session 38: the quickstart sends a person to `pipx install`,
`apg project create` and `apg project claim` (`site/pages/quickstart.md:19-28`),
and the console's overview says so (`app.js:405-408`). D2702 left browser
creation to Sessions 44/45 and neither built it. The operator chose to build it
(D2862 (2)), so the walk needs no terminal.

`POST /v1/projects` already takes everything a page can send
(`control_routes.py:839-882`): `organization`, `name`, `profile`,
`admin_username` and `handoff_sha256` — *"the token itself never reaches this
plane"* (ADR 0260). What the CLI does with the token is the question: it mints
it, keeps it in a 0600 file **before** the request, and later presents it to
**the project's own** `{routes.app}/auth/reset-password` (`bin/cloud.py:662-745`).
A creation takes 1,375.9–1,708.4 s on this host (the envelope), so a token
held only in page memory lives ~25 minutes in a tab.

### Measured (rig 46a, 2026-10-24, at `1b2e3e1`)

Chromium in the pinned Playwright image (`PW_IMAGE`, the plan's §0), against a rig server that answers
with **the console's exact deployed policy** —
`serve.security_headers("wss://sql.agenticpostgresql.com")` imported from the
checkout, never retyped — and a stub `POST /api/v1/projects` that logs every
body it receives:

- **(a)** A first-party module script makes 32 bytes with
  `crypto.getRandomValues`, encodes them base64url (**43 characters**, the
  length and alphabet of `secrets.token_urlsafe(32)`) and digests the UTF-8
  with `crypto.subtle.digest("SHA-256")`: `isSecureContext` true, no policy
  violation. **Control:** the same fixed input digests to the same hex in Node
  (`NODE_RUNTIME_IMAGE`) and in Python's `hashlib` (`7df3c0ae…`), and the
  page's random token digests identically in all three. **Policy control:** an
  inline script served under the same headers did not run (*"violates …
  'script-src 'self''"*), so the policy was applied to the rig's pages.
- **(b)** The stub's one logged body holds the digest and **does not hold the
  token**; the answer was the stub's 202.
- **(c)** Read-only, against the live host:
  `OPTIONS https://slot3.agenticpostgresql.com/api/app/auth/reset-password`
  with `Origin: https://control.agenticpostgresql.com`,
  `Access-Control-Request-Method: POST` and `…-Headers: content-type` answers
  **405, `allow: POST`, and no `Access-Control-*` header**; the control without
  `Origin` answers the same. (The plan named the host's root path, which is the
  edge's 404 — the claim's target is `routes.app` + `/auth/reset-password`,
  D2890.)
- **A test driver may not evaluate a string in a console page** (D2892):
  Playwright's `wait_for_function("…")` is refused under `script-src 'self'`
  (*"'unsafe-eval' is not an allowed source of script"*). The journey's driver
  waits with locators only.

**What a cross-origin claim would need**, read from (c): every project's auth
service answering a CORS preflight for the console's origin (allowing
`POST` and `content-type`), **and** the console's `connect-src` naming every
project's origin — which a fixed, rendered policy cannot do without a wildcard
over the zone. Both widen surfaces that hold more than this step needs.

## Decision

1. **The overview offers *New project* per organisation** (member and above,
   `control_roles.PROJECT_WRITES["create_project"]`; the server decides, the
   page shows its refusal): name, profile (`small`, `standard`, `large`) and
   the administrator's username, then `POST /v1/projects` through `api.js`'s
   `call`. The operation is followed with the existing `waitFor`, and the page
   leads to the new project's Connect view when it succeeds. The sentence
   *"Creating a project is done with the command-line client in this beta"* is
   removed. A refusal — `plan_limit_reached`, `capacity_exhausted {reason:
   no_slot}`, `conflict`, `not_available`, the factor gate — is the server's
   code and message, rendered through `refusal`, never reworded.
2. **The page makes the token and sends only its SHA-256.** 32 bytes from
   `crypto.getRandomValues`, base64url without padding, SHA-256 hex of its
   UTF-8 — byte-for-byte the CLI's `secrets.token_urlsafe(32)` /
   `hashlib.sha256(token.encode()).hexdigest()` (rig 46a). The token is held in
   one closure of the creation view.
3. **The token is shown once, the moment the creation is ACCEPTED** — before
   the wait, so a tab closed during the ~25 minutes has already shown it — in
   the existing shown-once panel (`once`, *"Shown once — copy it now."*), with
   the operation's id and the sentence that claiming is optional and how: save
   the token to a file readable only by you, then, once the project is ready,
   `apg project claim --project-key KEY --token-file FILE`. **The key is not
   known at acceptance** (D2895: a creation's `project_key` is NULL until the
   reconciler allocates its slot), so the Connect view repeats the claim line
   with the key filled once the creation has succeeded — **without the token**,
   which the page no longer holds. The token is dropped when the panel is
   dismissed or the view is left. *(Amended at Run 4, D2910: the line with the
   key is shown by the creation view itself once the operation has succeeded,
   beside its link to Connect; the Connect view, which every project shares —
   adopted ones no token can claim included — is unchanged.)*
4. **No cross-origin call, no storage, no policy change.** The page calls
   `/api/v1` and nothing else (`test_only_api_js_calls_fetch` stands);
   `test_no_script_writes_storage` stands; the console's policy — ADR 0285's,
   with ADR 0288's `font-src 'self'` — is byte-equal before and after.
5. **The claim stays the client's.** `apg project claim` gains
   **`--token-file FILE`** (refused unless the file is a regular file, not a
   symlink, owned by the caller and 0600 or narrower — `control_client.read_private_file`,
   checked on the open descriptor — read once). With
   it, **no creation is chosen and no held handoff file is looked for**: the CLI
   reads the project (its `app_route`), requires one `succeeded` creation of the
   key to be visible to the member, and presents the token to the project's own
   `/auth/reset-password`. **The project decides which creation the token
   belongs to**: its reset plane holds only its own creation's hash and answers
   any other token 401 (ADR 0260, rig 38c's controls). The CLI never deletes a
   file it did not write; on 200 it says the token is spent. Without the flag,
   `claim` is unchanged (D2316's held-file choice).
6. **The claim is documented as optional.** The connection string and the SQL
   editor need no project administrator; the quickstart (Run 4) says the claim
   is for the project's own admin API, from a terminal, and that a lost token
   can be replaced only by the operator's root reset (ADR 0260's
   Consequences).

## Alternatives rejected

- **The console claims cross-origin.** (c): no project answers a preflight,
  and the console's policy would have to name every project's origin. It would
  widen every project's surface and the console's policy for a step the
  connection string does not need.
- **The control plane relays the claim.** The token would transit the plane
  ADR 0246 and 0260 keep it out of.
- **Choose the creation by the token's digest** (the plan's D2865 wording).
  Not readable: `GET /v1/operations` serves no `arguments`
  (`control_service._operation`, `:1234-1250`), so a member cannot see a
  creation's `handoff_sha256`; exposing it would be a new read for nothing,
  because the project already refuses every token but its own (D2895).
- **Keep the token in `sessionStorage` until the wait ends.** A storage write
  is a value outliving the view that showed it; the console's guard forbids
  storage, and the panel at acceptance already survives a long wait.
- **Show the token only after `succeeded`.** A tab closed during the wait would
  lose a token the plane can never give back.

## Consequences

- A person reaches a working connection string without a terminal; the claim
  remains a terminal step for those who want the project's admin API.
- **A creator who closes the tab before saving the token cannot claim** except
  through the operator's root reset — threat item 28, `THR-CON-HANDOFF`.
- `projects_self_service` moves to `trial` at the bump naming
  `console_create_live`, and to `beta` at the close only on its claims
  (D2884).
- The CLI's two claim paths read the same project and present to the same
  route; only where the token comes from differs.
