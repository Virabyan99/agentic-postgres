# Session 47 — The console made for a newcomer, nomipg.com, the last re-earning, Stage 5's close

**Status: PLANNED 2026-10-29 at `ec75870`** (Session 46's close, tree clean, `main`
= `origin/main`). Rows **D2946–D2980** at planning; the runs add theirs from
**D2981**. ADRs **0295–0299** are reserved for Run 1. **NEXT FREE after this
table: D2981, ADR 0300.**

**Stage 5's last session** (D2945): the operator's brief is the launch folder's
`session-47-planning-prompt.md`. In order: **the console's UX/UI first and
heavily** (the first person's findings, D2936, and the operator's agreement that
the console *"looks and feels terrible while using"*), **the move to
`nomipg.com`** (D2943), **one fresh slot that re-earns `plans_live`,
`journey_live` and `console_create_live`** (D2940, D2945), then **Stage 5's
close** and **the Stage 6 decision report**.

**Brief:** the planning prompt (whole); `docs/plans/session-46-implementation-plan.md`
§0, §1 (D2862–D2945) and Runs 9–12; `docs/scope-closure.md` §38–§39;
`docs/plans/stage-5-plan.md` Status and §11; the person's own files in WSL
`~/s46/person/` (0600 — read, never copied into the repository) and
`~/s46/run9/NOTES.md` from *"PW 2026-10-28"* to *"GOAL 3 CAUSE CONFIRMED"*. ADRs
**0195**, **0280**, **0281**, **0285–0288**, **0290–0292**. The Stage 6 inputs
outside the repository: `future_stage_specs/agentic-postgres-stage-6-vision.md`
and `future_stage_specs/future-stages-review.md` (launch folder).

**Shape: fifteen runs, one sitting, one release (1.25.0), one re-earning.**
**Run 1** (readings, rigs, research, ADRs) and **Run 2** (the design brief and
prototypes, **Sheet D1: the operator's approval**) are documentation and read no
CI. **No console code changes before D1.** **Runs 3–10** change code; each pushes
and reads that commit's own CI verdict by full SHA (`gh api
"repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<40 chars>" --jq
'.workflow_runs[] | [.name, .status, .conclusion] | @tsv'` from Git Bash, never
inside `wsl`; three buckets — success / failure / not registered; an empty list
is not a verdict, D1057). **Run 11** writes the trip's instruments outside the
tree. **Run 12** is the bump. **Run 13** is the sitting. **Run 14** is the close
(Stage 5's). **Run 15** is the Stage 6 decision report. **Push only after the
previous commit's CI lands** — `ci.yml` cancels in-progress runs on `main`.

**Product version at close:** `CURRENT_SESSION` **47**; `template_version`
**1.25.0** — predicted *minor* (control migration **0011**, the `/v1` read
surface widened, console files, a domain) and **read from `upgrade plan` on the
host (Sheet R1), never chosen**. A `major` is §9's stop. Released migrations stay
**39**; the control set **10 → 11**. **No database restart** unless Run 1's
apt-pin reading (D2974) moves the Postgres image — then R1 says so.

**Written for whoever picks this up cold, and it will be a different model than
the one that planned it.** Every path and number below was read on 2026-10-29 at
`ec75870` — three explore passes (the console; the control API, operations,
notifications and plans; the domain and the walk proofs), direct reads of ADR
0288 §5–§8, `docs/hosted-walk.md`, the Session 46 plan, scope-closure §39, the
stage plan's Status and §11, and a read-only listing of the Cloudflare zones.
**Read CLAUDE.md §1 in the launch folder before the first command, then this
plan's §1, then the appendix.** If a step here and the tree disagree, **the tree
wins and the disagreement is a divergence row** (next free `D`), never a silent
reconciliation. **When this plan names a line number, open the file at that line
and read the surrounding twenty lines before editing** — `ruff format` moves them.

**The fourteen sentences the executor most needs, in case nothing else is read:**

1. **The design is the operator's to approve before a line of console code
   changes** (Sheet D1, Run 2). Runs 3–9 do not start without it.
2. **ADR 0295 supersedes ADR 0288's console clauses** — decision 8 (*"hooks, not
   features"*), the joint 30,720 B budget, the frozen driver anchors and the
   copy-button deferral — and **keeps** the rest: no framework, no npm, **no build
   step**, no third-party byte, no inline style, the self-hosted fonts, light only,
   the CSP (D2946, D2947).
3. **A long operation's state lives in the API, never in the page**: the tracker
   reads it on every load, and the operation's id is in the hash
   (`#/operations/<id>`), so a refresh resumes it (D2948).
4. **Control migration 0011 records when each step started** (ADR 0296);
   `GET /v1/operations` gains `status=open`; a creation's **subject** (name,
   profile) is served — **never its `handoff_sha256`**; step labels and typical
   durations come from one shared module held equal to the envelope by a test.
5. **Every refusal word the API, an operation or the relay can return has a
   sentence and a next action** (ADR 0297), the set **derived** from
   `errors.CONTROL_STATUS`, the generic four, the operation outcomes and the
   relay's close codes — never typed.
6. **Every value in a code block has a copy control with a "Copied" state; every
   action button is busy-disabled while its request is in flight** (D2955).
7. **Every Connect snippet is executed** against a TLS Postgres rig in its
   client's pinned image before it ships (D2956) — a snippet nobody ran is D267's
   class.
8. **The site's docs move with the console**, written in their runs and **parked**
   until the bump (D2911's method): the site publishes on every green push.
9. **The domain move is the customer-facing names only** — the apex, `www.`,
   `control.`, `sql.`, and each slot's five names; `secrets.`, `alpha-db.`,
   `beta-db.` (and `snippets-db.`, not ours) stay (D2964). **The old site and
   console names 301 for 12 months; the API, the relay and the doors cut over at
   the release** (D2946).
10. **Every Cloudflare DNS write waits for the operator's explicit word** (Sheet
    N0): the auto-mode classifier refuses the agent's DNS writes otherwise (D2933's
    experience).
11. **Two slots, in a fixed order** (D2870's rule): `slot12-prod` is **the new
    walker's** (KEPT); `slot13-prod` is prepared **only after A1 reads
    `slot12-prod` allocated** and is **the journey's and the lifecycle's**
    (consumed). **Every slot has five records and `ready` requires all five**
    (D2960).
12. **The re-earning's order**: the plan refusal (`--plans-only`) while
    `slot13-prod` is ready, then the journey, **J9 read inside it**, then the
    lifecycle in **ONE attempt, detached**, `--from-journey` with the journey's
    administrator name (D2938, D2970).
13. **The person on `slot10-prod` is told of their new connection strings before
    R2d** (Sheet M0) — their project is theirs, and the agent holds none of its
    credentials.
14. **Stage 5 closes only from the TAGGED evidence**: the Ledger moves (D2884,
    D2878, D2875), **no row `trial`**, scope-closure's stage section with §28
    re-audited, the stage plan's Status — **then** the Stage 6 report (Run 15).

---

## 0. Where the session starts

```
HEAD            ec75870a200b616e5f8b452d694b18666c720da0 on main, local = origin
                ("Session 46 Run 11: the close of Session 46 -- Stage 5
                extended to Session 47 (D2945)"), tree clean. CI contract
                40886010829 SUCCESS, site 40890698100 success. Deployed AND
                TAGGED: 55467b5 (1.24.0, tag object 3305c68e) on five projects;
                PyPI agentic-postgres-cli 1.24.0.
VERSION         1.24.0. CURRENT_SESSION 46 (src/agentic_postgres/__init__.py:1489).
EVIDENCE        evidence/session-46.json (WSL, gitignored): 348 claims, 343
                passed, 5 failed -- appliance_documented_path (D1935),
                documented_path (the person's 11, D2936), plans_live,
                journey_live, console_create_live (D2940).
LEDGER          docs/reality-ledger.yaml, 44 rows: beta 25, planned 8,
                not_offered 8, not_metered 1, trial 2 (projects_self_service ->
                console_create_live; support_bundle -> support_bundle_live).
                plan_free / plan_premium beta naming the failed plans_live
                (D2945). Five planned rows at target_session 38
                (project_isolation, agents, workflows, connectors, audit; D2878).
CONTROL SET     projects/control/migrations/templates/0001..0010.
GATES           bin/session-46-check.sh; tests/contract/
                test_session_forty_six_gate_modes.py. Roster tests/conftest.py
                ends APG_WALK_RECORD_FILE (:249), APG_JOURNEY_RECORD_FILE (:256).
ZONES           (Cloudflare API, read-only, 2026-10-29) nomipg.com ACTIVE on the
                account's nameservers (created 2026-10-29 08:08Z), 0 records.
                agenticpostgresql.com 50 records: grey A for control, sql,
                secrets, alpha-db, beta-db, snippets-db, slot1..slot11 and their
                pool./direct. names, the wildcards *.pool/*.direct for slot3,
                slot10, slot11; proxied CNAMEs for the apex and www (Pages); MX
                x3, SPF TXT, DKIM cf2024-1 (Email Routing).
HOST            15.204.231.45 (apg-ovh-01): beta-dev, alpha-dev, control-prod,
                slot3-prod, slot10-prod (the person's, KEPT) at 1.24.0 on
                55467b5. slot12 never provisioned; /home/op/s46-hostyaml12.py
                and s46-h1-12.sh present, unused.
```

**What exists, measured at `ec75870`, and the session builds on:**

- **The console** (`services/console/`): `public/app.js` 1,019 lines / 43,909 B;
  hash routes in `VIEWS` (`app.js:957-971`), dispatched by `route()`
  (`:973-1012`); `frame()` (`:366-377`) draws a top bar with one link
  (*Overview*) and *Sign out*; `projectNav` (`:379-383`) and `orgNav`
  (`:385-388`) are tab lists; **no organisation or project switcher**, no
  breadcrumb. `REFUSALS` (`:20-37`) holds **16** codes, each a sentence, **none a
  next action**; `refusal()` (`:82-89`). **`waitFor`** (`:153-162`) polls `GET
  /operations/{id}` every 2 s and prints `"Operation ${status}, ${step}
  (${progress}%)"` — the person's *"Operation running, backup (90%)"*. **The
  console never calls `GET /v1/operations`**; a refresh re-renders an empty form
  and nothing reconnects to the operation. `newProjectView` (`:431-472`) disables
  *Create project* only during the request; the shown-once panel's *"I have saved
  it"* is `panel.remove()`. **Copy** exists only inside `once()` (`:133-138`),
  with no feedback; the Connect table's strings have none. `sqlView`
  (`:896-953`): one `p.muted[role=status]` under the form; the password field
  stays visible after connecting. `create.js` 55 lines, `sql.js` 94, `pg.js` 476,
  `api.js` 83, `scram.js` 70, `pages.json` 17 views.
- **The server and its guards**: `serve.py` `ROUTES` (`:58-79`, exact order)
  equal to `tests/contract/test_console_server.py` `LISTED` (`:54-70`);
  `test_console_scram.py::test_every_script_parses` (`:80-97`) pins the scripts
  as exactly `api, app, create, pg, scram, sql`; the CSP (`serve.py:100-110`):
  `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:;
  connect-src 'self' wss://sql.<zone>; font-src 'self'; base-uri 'none';
  form-action 'none'; frame-ancestors 'none'`. `test_console_look.py` `ANCHORS`
  (`:33-47`) counts literals in `app.js` that the three drivers read
  (`::test_the_drivers_anchors_are_unchanged`, `:125-142`); it forbids
  `createElementNS`/`"svg"` in scripts and any `style=`/`.style`.
  `tests/contract/test_look.py:61` `BUDGET = 30_720` over `site.css` (20,251 B) +
  `app.css` (8,642 B) = **28,893 B — 1,827 B left**; `::test_there_is_no_dark_theme`
  (`:132`). `test_every_console_page_maps_to_a_reachable_row` is in
  `test_reality_ledger.py:251`.
- **ADR 0288 decision 8** (`docs/decisions/0288-…md:308-324`): *"The console gets
  hooks, not features"* — `sql.js`, `pg.js`, `scram.js`, `api.js` not edited; no
  heading, label or button text added or changed; copy buttons, operation-id
  rows, confirm-disabled-until-match and a phone-width menu deferred
  (Consequences `:348-350`).
- **The control API** (`services/auth-api/app/`): 49 method+path routes on 42
  paths (`main.control_paths()` `main.py:493-536`, pinned by
  `test_auth_service_shape.py:958-979`); every role in `control_roles.MATRIX`
  (`:48-120`), key scopes in `KEY_SCOPES` (`:202-241`). Refusal words in **one
  registry**, `errors.CONTROL_STATUS` (`errors.py:258-275`), raised at ~37 sites;
  the generic four `authentication_failed`, `authorization_failed`,
  `malformed_request`, `invalid_request`; operation outcomes
  `capacity_exhausted`, `invalid_request`, `operation_failed`, `interrupted`,
  `could_not_determine` (`errors.py:248-256`). **`branch_limit_reached` carries
  nothing else** (`models.py:731-735`); `plan_limit_reached` carries
  `entitlement`, `limit`, `plan`, `message` (`control_service.py:700-707`).
- **Operations**: `app.control_operations` (`0003:29-47`, widened `0004`, `0006`,
  `0008`) holds the **current** `step` and `progress` only, advanced by
  `control_advance_operation` (`0004:433-449`) from the reconciler's
  `Operation.step()` (`bin/reconciler.py:381-391`); `result.steps
  [{step, seconds}]` only at finish (`:391`, `:1416-1418`). Eleven types
  (`operations.py:59-71`). `GET /v1/operations?organization=` (required, no other
  filter, newest first, `control_routes.py:1263`); **`arguments` are never
  served** (`0007:32-33`), so a pending creation shows neither name nor key
  (D2895). The creation's steps and their progress (`reconciler_dispatch.STEPS`,
  `:82-117`), with slot6's seconds (`capacity.py:2173-2193`): allocate 10 / 1.0,
  admit 10 / 0.8, deploy-1 30 / 63.8, admin 40 / 1.4, ports 60 / 1.4, deploy-2
  60 / 41.2, unit 70 / 0.9, **backup 90 / 1,259.1**, registry 90 / 0.2 — total
  1,375.9 s; slot9 1,708.4 s, the journey 1,565.5 s. Time bounds 30 min, 60 for
  `branch.create`, `restore.create`, `branch.reset` (`reconciler.py:155-164`).
- **Notifications** (`0008:161-185`): kinds `operation_succeeded`,
  `operation_failed`, `idle_sleep`, `branch_expired`, `limit_approaching` (80 % of
  `storage_gb` and `agent_calls_per_day` only); text a fixed template
  *"`{type}` on `{key|'a new project'}` `{status}`"*; served by `GET
  /v1/organizations/{org}/notifications?limit` as `id, project, kind, text,
  created_at`. In-app only; *"Nothing is emailed"* (`site/pages/pricing.md`).
- **Plans** (`plans.py:76-103`): Free 1 project, 1 branch; `GET …/plan` serves
  `projects_active {held, limit}` (`control_service.py:869`); the site's
  `/pricing` exists.
- **The domain** (D2943, re-read): 312 lines in 79 files; **10 code files** —
  `src/agentic_postgres/site_build.py` (`:55` `INVITATION_ADDRESS`, `:58`
  `CONTROL_DOMAIN`, `:61` `SITE_URL`, `:66-68` `ALLOWED_ORIGINS`; **the CSP holds
  no domain**), `naming.py:473` (a docstring), `capacity.py:2391,2518,2526`
  (measurement records), `services/console/public/index.html:13` and
  `accept.html:13`, `bin/login.sh:48`, `bin/build-cli.py:75,77,117`,
  `infra/secret-store/compose.yaml:33` and **`infra/secret-store/Caddyfile:10`**
  (D2943 missed it), `project.control.example.yaml:35` (a comment). Tests pin it
  in 19 files; **`tests/contract/test_site.py:146-147` is a regex over
  `agenticpostgresql.com` that would check nothing after the move.** Names come
  from `host.yaml` `slots.declared[].domain` (`naming.endpoint_hosts`,
  `naming.py:599-614`; branches `:1158-1172`) and the control manifest's
  `project.domain` (`naming.console_origin` `:442`; the relay's `sql.` from the
  control domain, `:471-494`). **The CLI has no default endpoint**:
  `bin/cloud.py:1618,1624` require `--endpoint`, saved in
  `${XDG_CONFIG_HOME:-$HOME/.config}/apg/context.json`
  (`control_client.py:7,51,78`).
- **The walk proofs**: `tests/external/test_session46_walk.py:91-96` requires
  `site_commit` to be an ancestor of the checkout running the test; **`:106`
  fails an empty `documents_read`** (the person's record holds `commands_run: []`
  AND `documents_read: []`; Run 9's failure is at `:106`) — D2941 named the wrong
  field. `HOSTED_GOALS` is pinned in `tests/contract/test_dx_record.py:419`,
  `:631`. `tests/external/test_session46_journey.py` pins `slot11-prod` (`:214`),
  `journey-s46-` (`:184`), `lifecycle-s46` (`:195`); `journey_walk.py:87,91-92,
  412,711-712`. `read_the_string` (`:121-138`) is called only from WSL
  `~/s46/run11/s46-j09.py`.
- **Slot DNS**: `slot.slot_dns` (`src/agentic_postgres/slot.py:334-353`) reads
  three names with `dns_reading` (`:301-331`, `dig @1.1.1.1`), used by
  `bin/slot.py:196,408` and `bin/reconciler.py:509,1170`. **Only
  `bin/branch-runtime.py:277-289` checks the wildcards**, at a branch's creation.
  `~/s46/run7/s46-dns.sh` checks them only with `--wildcards`.

---

## 1. The divergence table

Six columns. Each row is a **measured fact about the tree at `ec75870`** (or the
zones and the host as read that day) set against what the brief says, with the
decision this plan takes. **Next free number after this table is D2981.** Rows the
runs add go in a second table below it, in execution order.

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2946** | Prompt §5: ask the operator the domain, a build step, dark mode, a logo, the second walker, a split. | Eight questions the tree cannot answer. | **The operator, 2026-10-29 (this planning), each as recommended**: (1) **the domain only** — the product stays *Agentic Postgres*, `agentic-postgres-cli` and `apg` keep their names; (2) **light only**, tokens structured so dark is one more token set later; (3) **Session 45's two-door mark** stays; (4) **a NEW person** walks the released console, on their own KEPT slot; (5) **ADR 0288's console clauses superseded, build-free** (D2947); (6) **the old site and console names 301 for 12 months; the API, relay and doors cut over at the release**; (7) **the secret store keeps its name**; (8) **one session, one release (1.25.0), one re-earning**, with D1 and the operator's go before the sitting as hard checkpoints. | A product question is the operator's; the plan records the answer. | 0295, 0299 |
| **D2947** | Prompt §1.4: *"if a constraint stands between the console and a professional result, say so"*. | ADR 0288 decision 8 forbids new script, flows and text; `test_look.py:61` leaves 1,827 B; `ANCHORS` freezes the drivers' literals; Consequences defer copy buttons. Every finding the person made needs one of these. | **ADR 0295 supersedes ADR 0288 decision 8, its joint budget and its anchor freeze**: the console may gain features, views and script; `app.js` is split into fixed-route ES modules; **the console's stylesheet has its own budget, ≤ 40,960 B; the site's keeps ≤ 30,720 B**; the anchors stay a test, **re-counted in the same commit that rewrites the drivers** (D2918's rule, D2968). **Kept**: no framework, npm, bundler or build step; no third-party byte; no `style=`/`.style`; no script-built SVG (icons are static markup in `index.html` `<template>`s, cloned — rig 47a); the self-hosted fonts and the shared token block (byte-equal); light only; the CSP. | The constraint was the project's own; replacing it is an ADR, not a loosening in passing. | **0295** |
| **D2948** | Person: *"after I refreshed the page there was no record of that project anywhere"*; *"the Overview page said no project while one was being created"*. | No `GET /v1/operations` call; `arguments` unserved (D2895); the token and the progress live in page memory. | **ADR 0296**: `GET /v1/operations?organization=<id>&status=open` (open = `pending`/`running`); each operation serves a **`subject`** — `{name, profile}` for `project.create`, `{branch}` for branch types — **never `handoff_sha256` or any other argument**; the Overview lists open creations as pending projects; **`#/operations/<id>` is the tracker**, so a refresh resumes it from the API. The token stays shown-once (ADR 0291): after a refresh it is gone **and the page says so** (*"You do not need it to connect"*). | State a customer must see after a refresh is the server's, not the tab's. | **0296**, 0291 |
| **D2949** | Person: *"no loading state or progress tracker, only … backup (90%)"*. | One current step; `backup` reads 90 % for ~90 % of the creation; no step's start time is kept while it runs. | **Control migration `0011-control-operation-steps.sql`**: `app.control_operation_steps (operation_id, step, started_at; PK (operation_id, step))`, FORCE RLS, no request-role policy; `control_advance_operation` inserts a row per new step; both operation readers serve `steps [{step, started_at}]`. **The tracker shows named steps (done / current / to come), the elapsed time and the typical time — no percent bar** for a time-dominated step. | A percent that sits still for twenty minutes reads as a hang. | **0296** |
| **D2950** | Prompt: *"named steps, elapsed time and the expected duration"*. | Typical durations exist only in `capacity.ENVELOPE`'s per-session rows. | **`src/agentic_postgres/operation_steps.py`** (stdlib only, a `SHARED_MODULE` the service loads the way it loads `plans`): per type, the ordered steps, a plain label each, and typical seconds; **`tests/contract/test_operation_steps.py` holds those seconds equal to the envelope's newest measured rows**; the console's wording is *"usually about N minutes"*, never a promise. Run 14 moves the numbers from the step log's own readings. | One source for a number the customer reads. | **0296** |
| **D2951** | Person: *"input fields should disappear so users won't … create same project couple times"*; the second create read `capacity_exhausted`. | `create.disabled` only during the request; the server refused the second creation for want of a ready slot before any plan reading. | **The console disables *New project*** while the organisation has an open creation or `held ≥ limit` (`GET …/plan`), saying why. **Run 3 reads the server's refusal order** in `control_service.create_project`: if capacity is checked before the plan, `plan_limit_reached` (the customer's to act on) is answered first — tests first, the order an ADR 0297 clause. | The customer should hear the refusal they can do something about. | **0297** |
| **D2952** | Prompt §1.2: *"every refusal … mapped to a sentence and a next action. Derive the list from the API."* | `REFUSALS` 16 codes, sentences only; `branch_limit_reached` bare. | **ADR 0297**: `services/console/public/messages.js` maps **every** word — `CONTROL_STATUS`, the generic four, the operation outcomes, the relay's close codes (ADR 0286), the TOTP refusals — to `{sentence, action, link}`; **`tests/contract/test_console_refusals.py` derives the set from the server's modules** and fails on a word without an entry. **`branch_limit_reached` gains `limit` and `plan`**, as `plan_limit_reached` has. | A refusal that does not say what to do next is the person's finding. | **0297** |
| **D2953** | Person: *"notifications about that my project is being created, and … when it finishes"*. | No *started* kind; template text *"project.create on a new project succeeded"*; no link to the operation. | **0011** adds kind **`operation_started`** for `project.create`, `branch.create`, `restore.create`, `branch.reset`, written by `control_request_operation`; every notification carries `operation_id` and `operation_type` (nullable); the console words each kind in plain language and links to `#/operations/<id>`; the page opens with one paragraph saying what notifications are and which events make them. **No email** (unchanged; pricing says so). | The page answers the question the person asked. | **0297** |
| **D2954** | Person: *"a limit warning … by clicking in it users should be able to go to pricing page"*. | `limit_approaching` only for two *shown* limits; nothing before `projects_active` or `branches_total`. | **Banners derived from `GET …/plan`** (`held`, `limit`) on the Overview, *New project* and Branches; `plan_limit_reached` and `branch_limit_reached` link to the site's `/pricing` and the console's Plan page. **No notification is written on a refusal** — *"No resources were created"* stays true. | A limit the customer can see coming is not a refusal. | **0297** |
| **D2955** | Person: *"no copy and copied state for buttons and no autodisable"*. | One Copy, no feedback; no debounce anywhere. | **`services/console/public/ui.js`**: a copy button (*Copied* for 2 s, announced through one `aria-live` region), a busy button (disabled and labelled while its promise runs), a toast region, `<dialog>`, tabs, chip, code block (with copy), skeleton, empty state, callout. **Every code block carries copy; every action button is a busy button.** | Build each control once. | **0295** |
| **D2956** | Person: *"no steps … for newcomers … for every operating system … like Neon or Convex"*. | Connect is a table and two password buttons. | **Connect rebuilt**: pooled versus direct explained in two sentences each; one *Create a password* step per door (what it does, that it is shown once, that the old one stops working); snippets for **psql, Node `pg`, Prisma, Drizzle, Python `psycopg`, Go `pgx`, an `.env` block** from **`snippets.js`** (DOM-free, Node-tested), the password a placeholder unless inside the shown-once panel. **Each snippet is executed** by `tests/contract/test_console_snippets.py` in its client's pinned image against a TLS Postgres rig with `sslmode=verify-full`. Per-OS psql install lines live on the site's connecting page, each either run in Run 1 (Debian/Ubuntu in a container) or cited with its source URL and date. | A snippet nobody ran is a value that looks measured. | **0295** |
| **D2957** | Person: *"messages appear in the bottom … the new-password option is still there even though we are already connected"*. | The status line under the form; the credentials form stays. | **The editor**: a state bar at the top (door, role, state); the credentials form hidden while connected (*Disconnect* in the bar); a two-row layout (statement above, results below); results with a sticky header, the row count and the time; ADR 0285's rules unchanged (password read once, input cleared, never stored). **`sql.js`'s decisions are not edited** unless a test moves with an ADR 0295 clause. | The editor is the customer's own client; its state must be where they look. | **0295**, 0285 |
| **D2958** | Person: *"I didn't find any support page"*. | No support page; Settings holds the support bundle. | **ADR 0298**: `site/pages/docs/support.md` (new, in `DOCS_GROUPS`) — how to get help, what to send, the support bundle, the refusals page, `invite@`; **the console's `#/help`** with the same and links; **every console page carries a contextual help link to a route the site build produces** (a test reads the routes). | Help must be found from where the question arises. | **0298** |
| **D2959** | Person: goal 2 *"didn't understand this question"*. | The statement's goal label *"your own SQL"*; `HOSTED_GOALS` pinned (`test_dx_record.py:419,631`). | **The prose and the label reworded** (*"run SQL you write yourself"*), `HOSTED_GOALS` moved, **ADR 0290 amended** (a contract test changes with its ADR). `docs/hosted-walk.md` names `slot12-prod` and `https://nomipg.com`. | A goal the walker cannot read is a step the statement did not give. | 0290 |
| **D2960** | D2933: *"the slot sheet creates five records, and the DNS check verifies the wildcards before `ready`"*. | `slot.slot_dns` reads three names; `ready` passes without the wildcards; the console offers a branch on every slot. | **Product**: `slot_dns` reads **five** — the three plus `dnsprobe.pool.<domain>` and `dnsprobe.direct.<domain>`; `ready` requires all five to resolve to the host alone; a name that could not be read is the third outcome (exit 6, ADR 0195). Every reader grepped (`bin/slot.py:196,408`, `bin/reconciler.py:509,1170`). The operator guide's §20/§21 say five. | What every customer is offered, every slot must be able to do. | — |
| **D2961** | D2941: *"read the site by digest, admit an empty `commands_run`"*. | `commands_run []` already passes (`hosted_unnamed_commands([]) == []`); **`:106` fails on an empty `documents_read`**; the ancestor check (`:91-96`) depends on where the test runs. | **The ancestor check removed**; identity by the digest (`:82`, `:88`); **an empty `documents_read` and `commands_run` admitted**, every named route still a built route. ADR 0290 amended. | A reading must not depend on where it ran; a person need not list pages. | 0290 |
| **D2962** | D2943: *"9 code files … `site_build.py`'s origin and CSP"*. | 10 files (the Caddyfile); the CSP holds no domain (`ALLOWED_ORIGINS` does); `test_site.py:146-147` would pass vacuously. | **The Caddyfile and the store's compose stay** (the store keeps its name, D2946). **`test_site.py:146-147` rewritten to read `site_build`'s own constant**, so it checks the new name. `capacity.py`'s three lines stay: they record what was measured. | A guard tied to a literal goes silently empty when the literal moves. | 0299 |
| **D2963** | Prompt §2: *"the CLI's default endpoint, given that a PyPI version cannot be re-uploaded"*. | **No default endpoint**: each saved `context.json` names `control.agenticpostgresql.com`. | **Every saved context logs in again** after the cutover: the operator re-logs `control-admin` (Sheet L1, their phone's code); the agent re-logs the probe, `person-config` and `member-config` from WSL; the site's `--endpoint` lines move. The 1.24.0 package's README stays as published. | A redirect cannot carry an API POST (rig 47c measures urllib). | 0299 |
| **D2964** | Prompt §2: *"~25 DNS records"*. | The new zone is empty; the old holds 50 (§0). | **Moving**: apex and `www` (proxied CNAMEs to Pages, D2719), MX ×3, SPF, DKIM (Email Routing), `control.`, `sql.`, `slot3`'s five, `slot10`'s five — **19 at the cutover**, then `slot12`'s and `slot13`'s five — **29**. **Staying**: `secrets.`, `alpha-db.`, `beta-db.` (the operator's appliance projects, not customer-facing), `snippets-db.` (not ours). **The old zone stays registered** (the store lives in it). Stale `slot1-9`, `slot11` records deleted (Sheet N3). | Move what a customer reads; leave what only the operator reaches. | 0299 |
| **D2965** | D2943: *"a release of five"*. | Unknown: whether `slot.sh redeploy` reads a moved domain from `host.yaml` or the slot's own manifest (`/etc/agentic-postgres/slots/<key>/manifest.yaml`), and which control tables or deployed documents hold hostnames. | **Rig 47b (Run 1)** re-renders the control project and a slot with the new domain into a temporary `.generated/` (deleted after), diffs the outputs, greps every reader of a route or door hostname, and reads the redeploy path. **If a domain move needs a new project identity, §9's stop.** | Measure a move before pricing it (D2943's own rule). | 0299 |
| **D2966** | D2946 (6): the old console name 301s for 12 months. | Grey-cloud rule; `control.agenticpostgresql.com` is a grey A record to the host. | **One exception, the operator's**: the old `control.` record becomes **proxied and redirect-only** (it no longer reaches the host); Single Redirect rules on the old zone send the apex, `www.` and `control.` to the same path on `nomipg.com` (301). The removal date (2027-10-29) is in §10. | A redirect is answered by Cloudflare; nothing behind it is exposed. | 0299 |
| **D2967** | Prompt: *"decide dark mode explicitly"*. | `test_look.py::test_there_is_no_dark_theme`. | **Light only** (D2946 (2)); the test stays; ADR 0295 names how a dark token set would be added. | The operator's answer. | 0295 |
| **D2968** | ADR 0288: the drivers' anchors frozen. | `ANCHORS` counts and the three drivers' labels, buttons and selectors (`console_walk.py`, `journey_walk.py`, `sql_walk.py`). | **Each run that changes the DOM rewrites the drivers it breaks in the same commit**, re-counts `ANCHORS`, and rehearses the driver (`~/s46/run6/rehearse-journey.sh`'s successor). Waits by locator only (D2892). | A driver that reads yesterday's page proves nothing tomorrow. | 0295 |
| **D2969** | Prompt §3: re-earn `journey_live`, `console_create_live`. | Their node ids are in `test_session46_journey.py`, pinned to `slot11-prod`, `journey-s46-`, `lifecycle-s46`. | **Widen, never derive**: the pins read the record's session (46 or 47) and its slot, count-asserted (D2922's method); `test_session46_walk.py` likewise for the second walker's record. | The claims to re-earn are those node ids. | — |
| **D2970** | Prompt §3: the plan refusal before the journey; J9 inside its record; ONE attempt. | Built and rehearsed at Session 46's close (`s46-lifecycle.py --plans-only/--plans-record`; test-only `24d926e`; `~/s46/run11/s46-j09.py`). | **Order on `slot13-prod`**: PL (`--plans-only`, the probe's `plan_limit_reached` recorded while the slot is ready) → J1 (the journey, then J9 at once) → LC (`--from-journey --plans-record`, the journey's administrator name, ONE attempt, detached). | D2940's three causes were order. | — |
| **D2971** | Prompt: *"every console view maps to a reachable Ledger row"*. | `pages.json` 17 views; no help or activity view. | **No new Ledger row**: `#/help` maps to `support_bundle` and `console`; the activity view and `#/operations/<id>` to `projects_self_service`; the `console`, `notifications` and `projects_self_service` texts move **at the bump** (the Ledger is a site digest input). | No concept is new; their pages are. | 0261 |
| **D2972** | D2883: the site frozen during the walk. | `site_build.digest_inputs()` (`:677-688`). | **Frozen again** from the bump's push until the new walker confirms (D2891: the function is the list). | The page the person read is the page the gate rebuilds. | 0290 |
| **D2973** | ADR 0283: the site deploys on every green push to `main`. | The bump's site links to `control.nomipg.com`, which serves nothing until R2e. | **Accepted window** (D2840's precedent): **the bump is pushed on the sitting's first day, after N0 and N1**, so the window is the release's length. | Hours, said, rather than a mechanism. | 0299 |
| **D2974** | D540, D2731: the apt pins expire. | Both repinned 2026-10-21 (D2731). | **Run 1 reads both indexes** (`ca-certificates`, `pgbackrest`). If one expired: repinned in Run 10, the Postgres image moves, **the release restarts every database** and Sheet R1 says so. | Known to expire; read before a release. | — |
| **D2975** | Prompt: *"creation, branch, restore, resize, sleep, wake and export"*. | The same `waitFor` everywhere; a refresh loses each. | **All eleven types use the tracker and the step log**; their bounds (30 min; 60 for branch create, restore, reset) shown as *"stopped after"* limits, never estimates. | One pattern, every long operation. | 0296 |
| **D2976** | Prompt: *"a getting-started checklist … from the invitation to a connected application"*. | Nothing. | **ADR 0298**: an Overview checklist **derived from API state only** — the factor, an organisation, a project (or one being created), a password made (a succeeded `credential.rotate`), a connection seen (the project's usage `connections > 0`; *not read* when unread — ADR 0195). **No storage.** | A checklist that remembers in the tab forgets on another device. | **0298** |
| **D2977** | Prompt §1.3: *"study the leaders, and borrow patterns only"*. | No study in the tree. | **Run 1** reads Neon's and Convex's public docs, changelogs and screenshots (Supabase, Vercel, PlanetScale for contrast) on creation progress, connect dialogs, branches, empty states, navigation and help; **`docs/design/session-47/research.md`** records each pattern, its source URL and the date read, adopted or not and why. **No markup, wording, icons or brand copied.** | A pattern is free; a brand is not ours. | — |
| **D2978** | Prompt §1.3: *"clickable prototypes … at both widths"*. | Session 45's prototypes were a design tool's (Google Fonts, a runtime) — reference only. | **Run 2**: first-party static HTML, CSS and script with the console's own tokens and fonts, in `docs/design/session-47/prototypes/`, **published to the operator as a private Artifact**, screenshots at 390 × 844 and 1280 × 800 from the pinned Playwright image. | The operator approves what the build will be made of. | 0295 |
| **D2979** | Prompt §1.3: *"a second person's walk"*. | `documented_path` failed on the first person's 11 (D2936). | **A new person** the operator recruits, holding the site's URL, the updated statement and an account invitation the operator mints (Sheet P0); **`slot12-prod` is theirs, KEPT**; their record read by `apg dx-record check --path hosted`; **findings recorded, never argued**. | ADR 0290: the claim is a person's to move. | 0290 |
| **D2980** | Prompt §4: the stage close. | D2884, D2878, D2875 moved to Session 47 by D2945. | **Run 14** moves them from `evidence/session-47.json`; **Run 15**'s report reads both persons' findings and the second walk's result. | Close from the tagged evidence. | 0261 |

**Rows the runs add** (from D2981):

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2981** | D2951: *"if capacity is checked before the plan, `plan_limit_reached` is answered first"*; Run 3 *"reads the server's refusal order"*. | **The order is already plan-first** (`control_service.py:689-716`). The defect is a reader: `_projects_held` (`:730-747`) counts an open creation only while `project_key IS NULL`; the control set (`0008:233-249`) counts it while the key is NULL **or not yet in `control_projects`**. A creation is keyed at `allocate` and registered at `registry`, so for ~99 % of it the service counts it nowhere: the plan passes, the slot reading refuses — the person's `capacity_exhausted` (Session 46 notes `:83`). The same function serves `GET …/plan`'s `held`: **0 of 1** during a creation. | **Run 3**: `_projects_held` counts as the SQL counts; a test seeds a running, keyed, unregistered creation and reads `plan_limit_reached` from `POST /v1/projects` and `held = 1` from `GET …/plan` (control: the creation finished). Run 3 step 3's *"refusal order … changed"* becomes this. | Two readers of one fact must agree; the planning row guessed the wrong one. | 0297 |
| **D2982** | — | The banners (D2954) and *New project* disabled (D2951) read `held` from `GET …/plan`. | **Both wait on D2981's fix**; Run 5's tests seed a running creation, never only a finished one. | A banner over the wrong count is a wrong banner. | 0297 |
| **D2983** | Sheet H0: *"`slot3`'s and `slot10`'s `domain` and the control manifest's `project.domain` moved"*. | `slot.sh redeploy` deploys from the slot's **own** manifest `/etc/agentic-postgres/slots/<key>/manifest.yaml` (`bin/slot.py:391-448`), not `host.yaml`; a render whose domain moved without `api.rest.allowed_cors_origins` is **refused, exit 2** (rig 47b). `allocated` reads the file's presence only (`slot.state`). | **H0 moves three places** per slot: both `host.yaml` copies, **and the slot manifest's `project.domain` and `allowed_cors_origins` together** (the old origin replaced by the new, as `slot.prepare` writes it), backups first; the control manifest's `project.domain`. Sheet H0 amended below. | Rig 47b; the product's own refusal is the guard. | 0299 |
| **D2984** | — | `jwt.issuer` is `https://<domain>/api/app/auth` (`naming.py:1515`; rig 47b). | **Every token a moved project issued stops verifying at its redeploy**: console sessions, and any customer application's sessions on `slot3-prod` / `slot10-prod`. **Sheet M0 says so** to slot10's person. No identity moves (rig 47b: no key, role, network, volume, bucket or stanza). | Said before, not discovered after. | 0299 |
| **D2985** | D2946 (6), D2966: the old site **and console** names 301. | urllib (the CLI's transport) follows a **301 POST as a body-less GET** and does **not** follow a 308 (`HTTPError 308`); measured on Python 3.12.15 and 3.14.4, control a direct POST (rig 47c). A 301 on the old `control.` name would turn `POST /v1/projects` into `GET /v1/projects` → 200. | **Apex and `www.` 301; old `control.` 308 for every path** (a browser follows it for pages as a 301). Sheet N2 amended below. | A redirect must not change what a request does. | 0299 |
| **D2986** | D2892: a string-evaluated Playwright wait is refused under the console's policy. | **Not reproduced** (rig 47a, Playwright 1.63.0, the same policy imported from `serve.py`): `wait_for_function` with an expression string and with an arrow-function string both ran; the inline-script control did not run, so the policy was applied. | **The locator-only rule stays** (it costs nothing); D2892's reason recorded as not reproduced. | A reason that did not hold twice is not a reason. | 0295 |
| **D2987** | D2974: read both apt pins. | Rig 47d (in the pinned base image, control `0.0.0-nope` ABSENT): `ca-certificates 20250419~deb12u2` **PRESENT**, `pgbackrest 2.59.3-1.pgdg12+1` **PRESENT**; `2.60.0-1.pgdg12+1` now offered. | **No repin; the Postgres image does not move; no database restart** at R1. 2.60.0 not taken (a product change for its own session). | Read before a release. | — |
| **D2988** | Sheets N1/N2 as if the endpoints existed. | Neither zone has an `http_request_dynamic_redirect` entrypoint (GET 404 10003); Free = 10 Single Redirect rules per zone, wildcards, no regex, 301/302/307/308; Email Routing `unconfigured` on `nomipg.com`, `ready` on the old zone; Pages `agentic-postgres-site` serves the old apex and `www.` (rig 47c, read-only). | N2 **creates** the entrypoint with a `PUT` (two rules); N1 enables Email Routing by `POST /zones/{id}/email/routing/dns` and adds the Pages domains by `POST …/pages/projects/agentic-postgres-site/domains`. **Whether the MCP's grant holds Pages Write, Zone Settings Write and a rulesets write** is read by the first write after the operator's word — a 403 names the permission (§9: read, never retried). | Measure a third party before a sheet names it. | 0299 |
| **D2989** | D2952: *"the generic four"*. | The inventory (derived, `~/s47/run1/inventory.py` → `docs/design/session-47/inventory.md`): **20 words** reach `/v1`; `malformed_request` only through the helper `errors.malformed()` (`control_routes.py:202`), so a scan of names alone misses it; **5 without an entry**: `could_not_determine`, `interrupted`, `last_owner`, `malformed_request`, `operation_failed`; eight agent-plane documents are not `/v1`'s. | **`test_console_refusals` uses the inventory's method** — the AST of `errors.py`, the control modules' uses including through `errors.*()` helpers, `OPERATION_ERROR_CODES`, the relay's `CLOSE_*` with 1000/1006/1011, `console_unconfigured`. | The set is derived; a typed list goes stale. | 0297 |
| **D2990** | D2949: a step log. | Rig 47e: the draft table, policy and advance work on a real control set — three steps in order, a repeat keeps its first time (`ON CONFLICT DO NOTHING`, `clock_timestamp()`), the request role denied (control: superuser 3), a non-member 0 rows, a late advance `not_running` with no row; the subject `{name, profile}` without the digest or the administrator name. | **0011 is written from the rig's draft** (ADR 0296 decisions 1–2); `expected` steps, labels and typical seconds served by the service from `operation_steps` (one source; the console holds no copy). | Measured before migrated. | 0296 |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

All `target_session: 47`, all P0. Families exist (`CON`, `CTL`, `UI`, `OPS`).
**Node ids are proposed; Run 12 writes what the runs actually wrote**, read with
`pytest --collect-only -q` (D1236, D2129). Committed by Run 12 with the constant
(D690) under **`# Session 47 (ADR 0295-0299)`**.

| Requirement | Claim | What it states | Mode |
|---|---|---|---|
| `CON-NAV-001` | `console_navigation` | Every view within two clicks of any other; each has a title, a breadcrumb and a help link to a built site route; the organisation and project switchers list what `/v1` returns | offline |
| `CON-OPS-001` | `console_progress` | `progress.js` (DOM-free): resumes from `GET /v1/operations` after a reload, names every step, never holds state in storage; forms disabled while an operation of that kind is open | offline |
| `CTL-STEPS-001` | `operation_steps` | 0011: the step log granted to nobody, written by `control_advance_operation`; `status=open`; the subject served, the digest never; typical seconds equal to the envelope | offline |
| `CTL-STEPS-002` | `operation_steps_live` | Live: the journey's creation shows every step with its start, in order | external |
| `CON-REFUSAL-001` | `console_refusals` | Every word derived from the server's modules has a sentence, an action and a link | offline |
| `CON-COPY-001` | `console_copy` | Every code block has copy with *Copied*; every action button is a busy button | offline |
| `CON-CONNECT-001` | `console_snippets` | Each snippet executed against a TLS rig with `verify-full` | offline |
| `CTL-NOTIFY-002` | `notifications_started`, `notifications_started_live` | `operation_started` written at request; notifications carry the operation's id and type | offline + external |
| `UI-A11Y-001` | `console_a11y` | Every text pair ≥ 4.5:1, focus on every interactive element, every input labelled, targets ≥ 24 px | offline |
| `UI-A11Y-002` | `console_look_live` | Every signed-in console page at 390 and 1280: no overflow, own origin only, the focus ring | external |
| `CON-RELOAD-001` | `console_reload_live` | The journey reloads during its creation and finds it on the Overview and at `#/operations/<id>` | external |
| `OPS-DOMAIN-001` | `domain_live` | The site, console, API, relay and doors answer under `nomipg.com`; the old site and console names 301 to the same path; the old API name no longer serves the API | external |
| `OPS-SLOTDNS-001` | `slot_dns_five` | `ready` requires five names; an unread name is the third outcome | offline |

**Expected counts** — Run 12 counts from the tuples, never this prose (D1628):
requirements ~**441 → 454**, claims ~**348 → 361**. The re-earned Session 46
claims keep their ids. **New environment gates**: none beyond the record flags
`bin/session-47-check.sh` exports; read model dicts with `.get("APG_…")`
(D2381).

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| Control migration **0011** frozen and applied on control-prod | Runs 3, 13 | `freeze-lock`; the proposal by `propose --by NAME` (ADR 0243); applied as `migration_user`; `AP900` down; never amended once applied (D912) |
| `CURRENT_SESSION` 46 → 47; `VERSION` 1.24.0 → 1.25.0; registry; Ledger texts | Run 12 | All-or-nothing (D690); every `--session 46` literal on the documented path moved and counted (D678/D1484) |
| **The cutover**: the new zone's records; Pages custom domains; Email Routing on the new zone; the old zone's redirects; stale old records deleted | Run 13, Sheets N0–N3 | The operator's explicit word before any DNS write; each read back by `dig @1.1.1.1` / `curl -sI` before the next sheet |
| `slot3-prod`'s and `slot10-prod`'s names change | Run 13, R2c/R2d | Sheet M0 tells slot10's person first; rig 47b showed the identities unchanged; one project at a time |
| Saved CLI contexts re-logged | Run 13, L1 | The operator's own (phone code); the agent's from WSL |
| **`slot12-prod`** (the walker's, KEPT) and **`slot13-prod`** (consumed) | Run 13 | One slot at a time (D2870); five records each; ONE lifecycle attempt (D2798); `slot13`'s identity revoked after the tag (SL4) |
| The new walker's account and organisation | Run 13 | Invite-only; never deleted (D2065) |
| Tag **1.25.0**; **`agentic-postgres-cli` 1.25.0** on PyPI | Run 13 | After the merge exits 5 for the expected claims only (§7); from the workstation (D2041); never re-uploaded |

---

## 5. Build order, run by run

Each run ends with a `**Done.**` paragraph written by the executor: what was
measured, the numbers, the rows it added, and — for a code run — the CI verdicts
by full SHA (`contract` and `site`). The targeted modules run ONCE at the run's
close and only a failing module is re-run. `ruff format && ruff check` before
every commit; `chmod 755 bin/*.sh bin/*.py deploy.sh libexec/*` before every
`git add`; messages from a file with `-F`, ending with the attribution lines the
session's system reminder gives. **Grep the plans for every third party before
measuring it.** The standing targeted-list rules of Session 46's §5 apply unchanged
(registry and claims after a rename; documentation and site; `services/console/`;
`bin/cloud.py`; the control service and set; `pytestmark`, the sweep-selector
guard and `test_environment_gates` for any new module; `test_suite_shape` and
`test_fleet` in every run's list). **Every mutation battery** follows CLAUDE.md §1.

### Run 1 — readings, rigs, research and ADRs 0295–0299 (documentation, no CI)

1. **The inventory** (`~/s47/run1/inventory.py`, output committed as
   `docs/design/session-47/inventory.md`): every view and its calls
   (`pages.json`), every refusal word **derived** from `errors.CONTROL_STATUS`,
   the generic four, the operation outcomes and the relay's close codes, and every
   operation type's steps with the envelope's seconds.
2. **Rig 47a — the console's capabilities under its own policy**: the real
   `serve.py` (its `ROUTES` widened in the rig's copy only) in the pinned
   Playwright image, at 390 and 1280: `navigator.clipboard.writeText` from a click
   (permission granted), `<dialog>.showModal()`, `<progress>`, a static SVG icon
   cloned from a `<template>`, an `aria-live` region, `:has()`, static ES-module
   imports from routed files. **Control**: a string-evaluated wait is refused
   (D2892). Each reading recorded with its result.
3. **Rig 47b — the domain** (D2965): the control project's and a slot's renders
   with `nomipg.com` into a temporary `.generated/` (deleted after); the outputs
   diffed; every reader of a route or door hostname grepped (`naming`,
   `rendering`, `control_registry`, the control tables, `slot.py`'s redeploy);
   how `pool.`/`direct.` certificates are issued read from the edge's
   configuration.
4. **Rig 47c — Cloudflare and redirects**, read-only through the Cloudflare API
   MCP: the Pages custom-domain endpoints for `agentic-postgres-site`; Single
   Redirect rules (`http_request_dynamic_redirect` phase) and the free plan's rule
   limit; Email Routing's setup on a new zone. Python `urllib` against a local
   301 and 308 on a POST (control: a direct POST), the reading recorded in ADR
   0299.
5. **Rig 47d — the apt pins** (D2974).
6. **Rig 47e — the step log**: a throwaway control cluster (rig 46c's method)
   with 0011's table and the widened `control_advance_operation`; a step written,
   read back by the member reader, refused to a request role.
7. **The research** (D2977) into `docs/design/session-47/research.md`.
8. **ADRs 0295** (the console reworked inside first-party rules; supersedes ADR
   0288 decision 8, its budget and its anchor freeze), **0296** (long operations
   made visible: the step log, `status=open`, the subject, `operation_steps`),
   **0297** (every refusal and notice a sentence with a next action; refusal
   order; `operation_started`; limit banners), **0298** (help, support and the
   getting-started checklist), **0299** (the move to `nomipg.com`: which names,
   the redirects, the cutover, the re-logins) — written, indexed in
   `docs/decisions/README.md`. Commit, push, no CI read.

**Done.** 2026-10-29, at `de996bf` (the plan committed `4c7db66`; the stage
plan's Status line `de996bf`, pushed by the planning session). Notes and rigs in
WSL `~/s47/run1/` and `~/s47/rigs/47a..47e/`.
(1) **The inventory**, derived (`inventory.py` → `docs/design/session-47/inventory.md`):
20 refusal words reach `/v1`, 16 in `REFUSALS`, 5 without an entry, none with a
next action; the relay's 5 close codes all worded; 11 types' steps; 17 views, 45
calls, `GET /v1/operations` called by none. **`backup` is 92 % of a creation at
progress 90** (D2989). (2) **Rig 47a** in the pinned Playwright image, the
console's own policy imported: a static module import, `:has()`, a cloned static
SVG (16 × 16, SVG namespace), `<progress>`, a modal `<dialog>`, `aria-live`, the
clipboard written and read back, no overflow at 390 and 1280, the first `Tab` on
the first link; the inline-script control did not run. **D2892 not reproduced**:
both string forms of `wait_for_function` ran (D2986). (3) **Rig 47b**: a domain
move changes routes, the issuer, the doors, the CORS origin and (control) the
console and relay origins — **no identity**; a domain without its CORS origin is
refused at render, exit 2; `redeploy` deploys from the slot's own manifest
(D2983, D2984). No §9 stop. (4) **Rig 47c**: urllib follows a 301 POST as a
body-less GET and does not follow a 308 (Python 3.12.15 and 3.14.4; control the
direct POST) → **the old `control.` answers 308** (D2985); Cloudflare read-only:
no redirect entrypoint on either zone, Free 10 rules, Email Routing unconfigured
on `nomipg.com` (D2988). (5) **Rig 47d**: both apt pins PRESENT (control ABSENT)
— no repin, no database restart (D2987). (6) **Rig 47e**: the step log's draft on
a real control set, 1 passed in 34.4 s (D2990). **Found on the way, a product
defect: D2981** — the service's `_projects_held` and the control set count an
open creation differently, which is why the person read `capacity_exhausted`
and why `GET …/plan` reads 0 held during a creation; Run 3 repairs it. (7) **The
research** (D2977): `docs/design/session-47/research.md`, 64 patterns over nine
topics from Neon, Convex, Supabase, Vercel and PlanetScale, each row a fetched
URL; gathered by a research sub-agent and read whole before commit; no copy
controls, creation-progress screen or checklist were documented by any source
read — ours to design. (8) **ADRs 0295–0299** written and indexed; **ADR 0288
marked *"Accepted, decision 8 superseded by 0295"*** (the index's status is read
to the first comma, `test_the_index_status_agrees_with_each_adr`). Sheets H0, N2
and M0 amended by D2983–D2985. Targeted once: `test_documentation_index`,
`test_repository_contract`, `test_mcp_catalog`, `test_suite_shape`, `test_fleet`
passed; `test_acceptance_registry` failed on the index separator, fixed, re-run
alone: 24 passed. Rows **D2981–D2990**. **NEXT FREE: D2991, ADR 0300.**

### Run 2 — the design brief, the prototypes, Sheet D1 (documentation)

1. **Load the `artifact-design` skill** before writing a page.
2. **`docs/design/session-47/design-brief.md`**: the information architecture (a
   top bar with the organisation switcher, the project switcher, *Help* and the
   user's menu; a left navigation with the project's group — Overview, Connect,
   SQL editor, Branches, Backups, Usage, Insights, Monitoring, Settings — and the
   organisation's — Projects, Activity, Plan and usage, Notifications, Members and
   keys; a breadcrumb *Organisation / Project / Page*; every page within two
   clicks; below 900 px the navigation in a `<details>` menu); one page template
   (title, one-line purpose, help link, primary action); the component set; the
   tokens extended, light only; the tracker pattern; the refusal pattern;
   Connect, the editor, notifications, help, the checklist, empty states and
   skeletons; the floors (WCAG 2.2 AA, 390 and 1280); Session 45's copy rules
   kept. **Each of the person's 11 findings mapped to the screen that answers
   it.**
3. **The prototypes** (D2978) of the overview (the checklist, a pending
   creation), create with progress (and the same page after a refresh), connect,
   the SQL editor, notifications, settings and help, at both widths, in
   `docs/design/session-47/prototypes/`; published as a private Artifact;
   screenshots from the Playwright image.
4. **Sheet D1**: the operator clicks through; their words and the date go into
   the brief's *Approval* section; revisions repeat until approved. Commit, push,
   no CI read.

**Done.**

### Run 3 — operations and notices made visible (the control plane)

1. Tests first: `tests/contract/test_control_operation_steps.py` (new,
   `pytestmark` first) and the widened `test_control_set`,
   `test_control_routes`, `test_operation_steps`.
2. **`projects/control/migrations/templates/0011-control-operation-steps.sql`**:
   the step log (D2949); `control_advance_operation` widened; both operation
   readers serve `steps` and `subject` (D2948); the `status` filter; kind
   `operation_started` and its write in `control_request_operation` (D2953);
   notifications gain `operation_id`, `operation_type`. Frozen (`freeze-lock`),
   proposed (`propose --by NAME`).
3. **`branch_limit_reached`** gains `limit` and `plan` (`models.py`,
   `control_service.py:1035-1036`); **the refusal order** read and, if needed,
   changed (D2951).
4. **`src/agentic_postgres/operation_steps.py`** joins `SHARED_MODULES`
   (`test_auth_service_shape.py:93-101`).
5. Widened by exactly the new names (D2901): `CONTROL_STATUS` if a word is added,
   `MATRIX`, `control_paths()` if a path is added, `test_control_set`'s `TABLES`,
   `GRANTED`, `OPERATOR`, `test_reconciler_dispatch`'s closed set; the snapshot
   regenerated (`bin/app-contract.sh --update --snapshot control >
   contracts/control-openapi.canonical.json`).
6. Targeted: `test_control_*`, `test_auth_service_shape`, `test_reconciler_dispatch`,
   `test_project_migration_sets`, `test_operation_steps`, `bin/app-contract.sh
   --check`, `test_acceptance_registry`, `test_evidence_claims`,
   `test_environment_gates`, `test_suite_shape`, `test_fleet`. The battery (a
   step not logged; the digest served; `open` including `succeeded`; a typical
   second drifting from the envelope), each with its control.

**Done.**

### Run 4 — the console's foundation (ADR 0295)

1. **The module split**: `ui.js` (the components, D2955), `nav.js` (the shell, the
   switchers, the breadcrumb), `messages.js` (D2952), `progress.js` and
   `snippets.js` (DOM-free); `app.js` draws. `serve.py` `ROUTES`,
   `test_console_server.py` `LISTED` and `test_every_script_parses` widened
   together (D2908's method).
2. **The shell and the page template** from the approved brief; new routes
   `#/projects/<KEY>`, `#/org/<UUID>`, `#/org/<UUID>/activity`,
   `#/operations/<id>`, `#/help`, each in `pages.json` with its Ledger rows
   (D2971).
3. **The budget split** in `test_look.py` (ADR 0295); the shared token block
   still byte-equal.
4. **The drivers and `ANCHORS`** rewritten in the same commit (D2968);
   rehearsed.
5. Targeted: the console set (`test_console_*`, `test_look`,
   `test_reality_ledger`), `test_environment_gates`, `test_suite_shape`,
   `test_fleet`. The battery.

**Done.**

### Run 5 — long operations, creation and refusals

1. The Overview: pending creations from `status=open`, the checklist (D2976), the
   limit banners (D2954).
2. **`#/operations/<id>`** for all eleven types (D2975); forms disabled (D2951).
3. **The creation page**: the token panel says in plain words what the token is
   and that the claim is **optional**; *I have saved it* collapses the panel to a
   confirmation line and the tracker stays; `test_console_create`'s text pins
   moved with ADR 0291 amended where they pin `panel.remove()`.
4. `messages.js` complete (D2952).
5. Targeted: the console set, `test_console_create`, `test_console_refusals`.
   The battery.

**Done.**

### Run 6 — Connect and the SQL editor

1. Connect (D2956): the explanations, the password flow per door, the snippets,
   copy on every value; `tests/contract/test_console_snippets.py` (each client's
   image pinned by digest, a TLS rig, `verify-full`).
2. The editor (D2957).
3. Targeted: the console set, `test_console_sql`, `test_console_snippets`. The
   battery.

**Done.**

### Run 7 — notifications, help and onboarding

1. Notifications (D2953): the opening paragraph, each kind worded, links to the
   operation.
2. `#/help` and every page's help link (D2958), tested against the site build's
   routes.
3. Empty states with the next action.
4. Targeted: the console set, `test_site`. The battery.

**Done.**

### Run 8 — the site aligned, PARKED

1. Written in the tree, then parked in `~/s47/run8/park/` with `apply.py`
   (D2911's method): `site/pages/quickstart.md`, `docs/connecting.md` (the
   snippets, per-OS psql), `docs/sql-editor.md`, `docs/plans-and-usage.md`
   (notifications), **`docs/support.md`** (new, `DOCS_GROUPS`); the Ledger texts
   (D2971); `docs/hosted-walk.md` (D2959).
2. Targeted (with the park applied in a scratch copy): `test_site`,
   `bin/build-site.py --check`, `test_documentation_index`,
   `test_session12_documented_path`, `test_dx_record`, `test_reality_ledger`.

**Done.**

### Run 9 — the quality floors

1. Contrast for every new token pair (`test_look.py`'s `TEXT_PAIRS`); focus on
   every interactive selector; every input labelled and every target ≥ 24 px, by
   scans of `ui.js` and `app.js`; the 390/1280 rules; skeletons on every view
   that waits.
2. **`tests/external/browser/console_look.py`** (new): every signed-in page at
   both widths — overflow, origins, the focus ring, the Playwright accessibility
   snapshot. **No axe or Lighthouse**: third-party test tools the rules do not
   need. Rehearsed against a local console.
3. Targeted: `test_look`, the console set. The battery.

**Done.**

### Run 10 — the domain move and the small repairs

1. **ADR 0299's code**: `site_build.py` (`INVITATION_ADDRESS`, `CONTROL_DOMAIN`,
   `SITE_URL`, `ALLOWED_ORIGINS`), `index.html`, `accept.html`, `bin/login.sh`,
   `bin/build-cli.py`, `naming.py`'s docstring, `project.control.example.yaml`'s
   comment; the tests' pins; **`test_site.py:146-147` rewritten** (D2962). The
   Caddyfile and the store's compose unchanged. Site text parked with Run 8's.
2. **D2960** (five names), **D2961** (the walk proofs), **D2969** (the pins
   widened), D2932's wording in `slot.py`, and D2974's repin if Run 1 found one
   expired.
3. Targeted: `test_naming`, `test_site`, `test_secret_store_files`,
   `test_dx_record`, `test_slot*`, `test_reconciler_dispatch`,
   `test_console_server`, `test_cli_contract`, `test_cli_package`. The battery.

**Done.**

### Run 11 — the trip's instruments (WSL `~/s47/`)

1. The `s46-*` instruments derived to `s47-*`, **functional strings only**
   (D2926), count-asserted: lifecycle (`--plans-only`, `--plans-record`), branches,
   journey launcher (**a reload during the creation**, `console_reload_live`; J9 at
   once after the driver), external, sweep, the detached launchers.
2. **`s47-dns.sh`** checks five names by default; the cutover scripts — the
   records generated from the manifests, read back by `dig @1.1.1.1`; the
   redirects read back by `curl -sI`.
3. **The external half rehearsed on a journey-mode record** (D2940).
4. **The `/home/op` copy list** by `grep -oh '/home/op/[^ "]*'` over the trip's
   scripts (D2937).

**Done.**

### Run 12 — the bump

1. `CURRENT_SESSION` 47, `VERSION` 1.25.0, `README.md:7`, every `--session 46`
   literal on the documented path; the registry (§2); `CLAIM_INTRODUCED_IN`.
2. **`bin/session-47-check.sh` derived from 46's by diff** (D1482), header and
   usage rewritten whole (D1488); `SHELL_COMMANDS`;
   `test_session_forty_seven_gate_modes.py`.
3. The parked site and Ledger applied; threat items `THR-OPS-SUBJECT`,
   `THR-REDIRECT`.
4. Both gates in shards (the `~/s43/run11` method). **Committed; not pushed until
   the sitting's first day** (D2973).

**Done.**

### Run 13 — the sitting

**Read first:** the appendix, §7, Session 46's Run 9 **Done.** and rows
D2930–D2945. **Before the first sheet**: the operator's go for the sitting.

1. **N0** (the operator's explicit word) — the agent writes the new zone's 19
   records through the Cloudflare API and reads each back. **N1** — Pages custom
   domains `nomipg.com` and `www.`; Email Routing `invite@nomipg.com` to the
   operator's address.
2. **The bump pushed**; its CI read by full SHA.
3. The checkout on the host moved by bundle (`FETCH_HEAD` confirmed); the renders;
   `pytest --setup-plan` with the variables set; the `/home/op` copies read back
   by sum (D2937).
4. **H0**: `/home/op/etc-host.yaml` refreshed from `/etc` first (D2930); `slot3`'s
   and `slot10`'s domains and the control manifest's `project.domain` moved, with
   backups.
5. **R1**; **M0** (the operator emails slot10's person); **R2a** beta, **R2b**
   alpha, **R2c** `slot3-prod`, **R2d** `slot10-prod`, **R2e** control-prod
   (0011; the console and the relay on the new origin) — each window probed, each
   read before the next. **N2** (the old zone's redirects). **RC1**.
6. **L1** (the operator's re-login); the agent's re-logins; **A1**, **RA**,
   **K1**, **V1**, **X0**, **W0′**, **E0**, **L0** under the new names. **N3**
   (stale old records deleted).
7. **H1** (`slot12-prod` and `slot13-prod` declared); **SL1–SL3 for `slot12-prod`
   alone** (five records; `ready`).
8. **P0, PW, PR** — the new walker (D2979); **A1″** reads `slot12-prod` allocated.
9. **SL1′–SL3′ for `slot13-prod`**; **PL** (`--plans-only`); **J1** (the journey
   with its reload, then J9); **LC** (the lifecycle, ONE attempt, detached).
10. **BR** (branches on `slot3-prod`), **B1** (the reboot), **E0** again, the look
    walk (`console_look.py`).
11. **S1** — the one sweep; **then** the branch `--delete-only`; **then** the
    external half; **then** the merge. Exit 5 for the expected claims only (§7).
12. **The tag** 1.25.0 from the workstation; `publish-cli` read; PyPI
    `info.version`; `apg --version` → `apg 1.25.0` in a clean `python:3.12-slim`.
13. **SL4**.

**Done.**

### Run 14 — the close (Stage 5's)

1. **The Ledger** from the TAGGED `evidence/session-47.json`: D2884
   (`projects_self_service`, `support_bundle`), D2878 (the five `target_session:
   38` rows), D2875 (`support_access`'s clause); every row re-read, one line each
   in the **Done.**; **no row `trial`**; `docs/reality-ledger.md` regenerated.
2. **The envelope**: Session 47's section — per-step creation seconds from the
   step log, the walk's times, the cutover's windows, the certificates' issue
   times, the re-earning; `UNMEASURED` loses only what was measured.
3. **`docs/scope-closure.md` §40** — Stage 5's close — with **§28's lists
   re-audited row by row**.
4. **The stage plan's Status: STAGE 5 CLOSED.** This plan's Status COMPLETE.
5. **`docs/operator-guide.md`**: the release row; the cutover; the five-record
   slot sheet.
6. **The handoff** (CLAUDE.md copied to the scratchpad first; the memory state).
7. Targeted: `test_reality_ledger`, `test_evidence_claims`,
   `test_documentation_index`, `test_capacity_envelope`, `test_site`,
   `test_console_pages`, `test_session12_documented_path`;
   `bin/session-01-check.sh` once. Commit, push, CI.

**Done.**

### Run 15 — the Stage 6 decision report

1. **`~/s47/run15/fill.py`** (`~/s35r11/s35-r11-fill.py`'s method): every number
   from `evidence/session-47.json`, `capacity.ENVELOPE` and the tree at the tagged
   commit; a placeholder refused.
2. **`docs/stage-6-decision-report.md`**: §1 what 1.25.0 is; §2 what was
   measured; §3 what stayed `failed` or `not_run`, and why; §4 what Stage 5 built,
   session by session (36–47); §5 the Stage 6 question priced against the vision
   and the review's §4–§5, with **both persons' findings** and the second walk's
   result; §6 **the recommendation — the executor's reading, for the operator to
   accept or rewrite**.
3. The inputs committed under `docs/stage-6/` only at the operator's word (D2887).
4. `test_documentation_index`; commit, push, no CI read.

**Done.**

---

## 7. Evidence and claims

**Expected at the merge** (Run 13): ~**361 claims**. **`failed`**:
`appliance_documented_path` (D1935, the clone walk, unchanged) and
`documented_path` **only if the new walker records an undocumented step**
(recorded, never argued). **`plans_live`, `journey_live`,
`console_create_live` passed.** Every other claim, including Session 47's, passed.
**Exit 5 for the expected claims only.** Host: one sweep (S1). External: from
WSL with every record. Offline: the deployed SHA's CI artifact.

---

## 8. Security invariants this session touches

- **The console's policy does not move** except that the relay's origin follows
  the domain (`wss://sql.nomipg.com`). No storage; no cross-origin fetch (help
  links are navigations); no inline script or style; no third-party byte.
- **The handoff token is shown once** (ADR 0291) and lost on a refresh by design,
  and the page says so. **An operation's subject never carries the digest** or any
  other argument.
- **No secret in a snippet outside the shown-once panel; none in a
  notification.**
- **Grey-cloud everywhere** except the site's CNAMEs (D2719) and the old
  `control.` name's redirect-only record (D2966).
- No SQL on the platform's side; the relay holds nothing (ADR 0285–0286).
- No GitHub credential on the VPS. Every `sudo` line is the operator's. No secret
  value in the conversation (D2934).

---

## 9. Stop conditions

- **Sheet D1 not given** — no console code.
- A test outside the ones this plan names would have to move.
- **A `major`** at R1.
- **A domain move that needs a new project identity** (D2965).
- **An ACME failure** — read, never retried in a loop.
- `slot3-prod` or `slot10-prod` unreachable under its new names after its deploy:
  stop and read before anything else.
- A creation by anyone else between `slot12-prod` and `slot13-prod`; the walker's
  creation landing on `slot13-prod`.
- **A second lifecycle attempt** without the operator's word (D2938).

---

## 10. Open items this session carries and creates

- **The old site and console redirects end 2027-10-29** — the rules removed then;
  the old zone stays registered for the store.
- The store's rename; a product rename; dark mode; email notifications — each a
  Stage 6 candidate.
- D2932 if `slot.py` was not touched.
- `UNMEASURED`: the plane at rest; the support bundle's pass per slot.

---

## Appendix — what to consult, how a run is executed here, and the sheets

**How a run is executed** is CLAUDE.md §1 and §5, unchanged. Every `op`-side
step is the agent's over SSH; every `sudo` line is on a numbered sheet for the
operator; one sheet, one outcome, read before the next (D1510).

### Sheet D1 — the design approved (Run 2; the operator)
The operator opens the prototypes' Artifact, clicks every screen at both widths,
and answers *approved*, or names what to change. Their words and the date go into
`docs/design/session-47/design-brief.md`'s *Approval* section.

### Sheet N0 — the operator's word for the DNS writes (Run 13)
The operator says, in their own words, that the agent may write the listed
records to `nomipg.com`. The agent writes them through the Cloudflare API and
reads each back with `dig @1.1.1.1`.

### Sheet N1 — Pages and Email Routing (Run 13)
`nomipg.com` and `www.nomipg.com` attached to the Pages project
`agentic-postgres-site`; Email Routing enabled on `nomipg.com` with
`invite@nomipg.com` to the operator's address.

### Sheet H0 — the domains moved on the host (Run 13)
As Session 46's H1, with `slot3`'s and `slot10`'s `domain` and the control
manifest's `project.domain`; backups first; `/home/op/etc-host.yaml` refreshed
from `/etc` first (D2930). **And (D2983) each slot's own manifest,
`/etc/agentic-postgres/slots/<key>/manifest.yaml`: `project.domain` and
`api.rest.allowed_cors_origins` together**, the old origin replaced by the new —
`slot.sh redeploy` deploys from that file, and a render with one moved and not
the other is refused (exit 2). A `--render-only` of each edited manifest, read
for `jwt.issuer` and the two door hosts, before the sheet's deploy.

### Sheet M0 — the message to slot10's person (Run 13; the operator, by their own email)
A short message: the service's new address, that their project's connection
strings change at a stated time, where to read the new ones (*Connect*), that
nothing is lost, and **that anyone signed in to an application built on their
project signs in again after the change** (D2984: the issuer moves).

### Sheets R1, R2a–R2e (Run 13)
As Session 46's, with **R2d** `slot10-prod` by `slot.sh redeploy` after M0, and
**R2e** control-prod applying 0011 with the console and the relay on the new
origin.

### Sheet N2 — the old zone's redirects (Run 13)
Single Redirect rules on `agenticpostgresql.com` (the entrypoint created by `PUT`,
D2988): the apex and `www.` → the same path and query on `nomipg.com`, **301**;
`control.` → the same path and query on `control.nomipg.com`, **308** (D2985: a
301 turns the old CLI's POST into a GET); the old `control.` record proxied,
redirect-only (D2966). Read back with `curl -sI` (the code and `Location`) and a
`curl -sI -X POST` on the old `control.` (308, not followed).

### Sheet L1 — the operator's re-login (Run 13)
`apg login password --endpoint https://control.nomipg.com/api/v1` as
`control-admin`, the code from the operator's phone.

### Sheet N3 — the stale records deleted (Run 13)
The old zone's `slot1-9`, `slot11`, `slot3` and `slot10` names, and the old
`sql.` name, deleted; `secrets.`, `alpha-db.`, `beta-db.`, `snippets-db.` and the
email records kept.

### Sheets H1, SL1–SL3 / SL1′–SL3′, P0, PW, PR, A1″, PL, J1, LC, BR, B1, S1, SL4
As Session 46's (`session-46-implementation-plan.md` appendix and Run 9), with:
five records per slot; `slot12-prod` the walker's and `slot13-prod` the journey's
(D2870); the statement from `docs/hosted-walk.md` as Run 8 rewrote it; PL before
J1 (D2970); J9 inside J1; LC one attempt, detached.
