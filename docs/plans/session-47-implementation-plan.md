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
| **D2991** | D2956: Connect's snippets from **`snippets.js`** (DOM-free, Node-tested) in the console. | **The server already serves them**: `services/auth-api/app/connection_snippets.py` (`CLIENTS = psql, prisma, node-pg, psycopg`, measured by rig 39c: `sslrootcert=system`, Prisma's `DIRECT_URL` and no `pgbouncer=true`, the password always `PASSWORD_PLACEHOLDER`), served by `GET /v1/projects/{key}/connections`, tested by `test_connection_snippets.py` and `test_control_connections.py`. | **No `snippets.js`**: Run 6 widens the server's `CLIENTS` by `drizzle`, `go-pgx` and `env`, each executed against a TLS rig in its client's pinned image (`test_connection_snippets` grows the executions; D2956's rule kept) with a **`where`** line per client (which file, which install command). The console fills the placeholder **only inside the shown-once panel**, in the page. ADR 0295 decisions 3 and 7 read *the server's snippets*; the console's module list loses `snippets.js` (ten files, not eleven). | One source for a measured text; the plan would have made a second. | 0295 |
| **D2992** | D2950: *"`src/agentic_postgres/operation_steps.py` … a `SHARED_MODULE` the service loads"*. | A shared module lives **in the service** (`services/auth-api/app/plans.py`, `control_states.py`), and `src/` re-exports it through `service_source.load` (ADR 0084): the service cannot import `src/`. | `services/auth-api/app/operation_steps.py` + the re-export `src/agentic_postgres/operation_steps.py`; `SHARED_MODULES` gains `operation_steps`. ADR 0296 amended. | The tree's direction. | 0296 |
| **D2993** | ADR 0296: a bad `status` is `malformed_request`. | The route answers a bad query `invalid_request`, 422 (a missing `organization` already does; `_query` raises `InvalidRequest`). | **`invalid_request`, 422.** ADR 0296 decision 3 amended. | One answer for one kind of mistake. | 0296 |
| **D2994** | ADR 0296: both readers compute the subject. | Two copies of one CASE would drift; `test_control_set` requires every `app` function be GRANTED, OPERATOR or HELPER. | One helper **`app.control_operation_subject(type, arguments)`**, revoked from PUBLIC, called by both readers as their owner; **`HELPERS` gains it**. | One allowlist, one place. | 0296 |
| **D2995** | D2950: *"typical seconds"* per step. | The envelope has per-step seconds **only for `project.create`** (slot6, 1.20.0); every other type has end-to-end totals (sleep 19.6, wake 20.1, resize 58.8–59.4, export 1.9–9.2, delete 16.4, rotate 1.7–5.1, branch 571.5, restore 486.9, reset 474.5, branch delete 4.5–7.8 s), and creations measured three times (1,375.9 / 1,565.5 / 1,708.4 s). | `expected` = `{steps: [{step, label, typical_seconds or null}], typical_seconds: {low, high}, bound_seconds}`; each number cites its record by subject and words, read back by `test_operation_steps`; `low/high` for creation are 1,375.9 / 1,708.4. The console says *"usually about N to M minutes"*, and a step without a measurement shows no time. | A number on a customer's screen names its measurement. | 0296 |
| **D2996** | ADR 0297: `branch_limit_reached` carries `limit` and `plan`. | Two readers produce it: the route's own (Python, D2430) and the control set's under the lock (`AP409`), which carries the word alone. | **The route's reader carries `limit` and `plan`**; the set's concurrent-request answer stays the bare word, and the model's two members are optional. The four route pins in `test_control_branches` moved to the full body. | The set's answer is a race's; it is rarely seen and still correct. | 0297 |
| **D2997** | — | `test_control_projects::test_plan_limit_reached_is_produced_only_by_the_entitlement_readers` reads every file that contains the word; 0011 re-creates `control_request_operation` from 0008's text. | **`PLAN_LIMIT_PRODUCERS` gains `0011-control-operation-steps.sql`** (exactly the new name, D2901); a docstring in `models.py` that only mentioned the word was reworded instead of widening. | A re-created reader is the same reader; a mention is not a producer. | 0297 |
| **D2998** | D2992: `src/agentic_postgres/operation_steps.py` re-exports the service's module, which joins `SHARED_MODULES`. | **CI on `6e5555c` failed** (contract 40913637017, both jobs, 1 test of ~8,570): `test_repository_contract::test_no_module_is_imported_only_by_its_own_tests` — the re-export had no caller outside tests (D204); `plans` has one (the reconciler), this did not. Run 3's targeted list lacked that module. | **The re-export removed**; the two test modules load the service's module by `service_source.load("operation_steps")` (as `test_connection_snippets` does); `SHARED_MODULES` back to its eight (it means *loaded by `src/`*). ADR 0296 amended. **`test_repository_contract` joins every run's targeted list when a module is added.** | A module nothing calls is a feature that does not exist. | 0296 |
| **D2999** | Brief §2: the mark leads to Projects. | `index.html`'s mark linked `https://agenticpostgresql.com/` (Run 10's domain list counted `index.html:13`). | **`index.html`'s mark → `/console/#/`**; `accept.html` keeps the site link. Run 10's list loses `index.html:13`. | Inside the console the mark is home. | 0295 |
| **D3000** | Brief screen 3: *"stops by itself after 30 min on one step"*. | The reconciler's bound is per **operation**, from its claim (`bin/reconciler.py:371-372`). | The tracker says *"If it has not finished 30 minutes after it started, the server stops it"* (60 for the three branch types). | Say what the server does. | 0296 |
| **D3001** | Brief §2: *Notifications* with an unread count. | A count needs a notifications read on every page; nothing reads one yet. | Run 4: a link without a count (below 900 px in the Menu's organisation group); **Run 7 decides the count**. | Not drawn until it can be read. | 0298 |
| **D3002** | Brief: the organisation's *Projects*, the project's *Overview*. | `#/` was titled *Overview* and the drivers waited for it. | **`#/` is *Projects*** (every organisation), `#/org/<id>` one organisation, **`#/projects/<KEY>` the project's *Overview***; the three drivers rewritten and rehearsed. | The brief's names. | 0295 |
| **D3003** | Brief: one item, *Plan and usage*. | Two routes, `#/org/X/plan` and `#/org/X/usage`. | The item opens the plan page, which links to usage; both mark the item. | No route lost. | 0295 |
| **D3004** | Plan: each view's calls listed in `pages.json`. | The shell reads organisations, projects and a project on every page; `test_console_create` pins `new-project`'s calls exactly; the guard reads the union. | The shell's reads listed under `overview`, `organization` and `operation`; **per-view listing is CON-NAV-001's** (Run 12 registers it). | The guard is the union; the claim is the per-view. | 0295 |
| **D3005** | ADR 0296: the tracker reads the operation on every load. | (a) A requester's read of a succeeded export takes its `download_url` once (D2164); (b) a running creation's `project_key` names an unregistered project, so `GET /projects/{key}` is 404. | The tracker shows the export link once when it has it and never reads an operation only for context; **until a creation succeeds the shell reads only its organisation**. Run 5 keeps both. | A context read must not spend a one-time value or meet a 404. | 0296 |
| **D3006** | ADR 0295 decision 6: every action a busy button; a dialog component. | The editor's Connect/Run/Cancel/Disconnect stay plain (Run 6 rebuilds the editor); *I have saved it* is a text pin in `test_console_create`; no dialog yet. | Busy buttons on every other action; **Run 5 moves the *I have saved it* pin, Run 6 the editor, Run 9 adds the dialog for delete**. | Each in the run that owns its view. | 0295 |
| **D3007** | Brief §1: plain language. | Activity and the tracker print raw ISO times (`2026-10-29T17:00:17.735753+00:00`; seen in the 390 px look). | **Run 5 formats every time** (a relative age with the absolute time beside it). | A machine's timestamp is not a sentence. | 0296 |
| **D3008** | Brief §2: below 900 px the navigation folds into one *Menu*. | The closed Menu left ~160 px empty: `.shell`'s `min-height` was shared between both rows of the one-column grid. | **`grid-template-rows: auto 1fr`** under 900 px; re-read in the look rig at 390. | A closed menu takes its summary's height. | 0295 |
| **D3009** | ADR 0297: the API's words, the relay's closes and `console_unconfigured`. | `api.js` makes two words itself: `console_unconfigured` and `unexpected_answer`. | The console's own words are **derived from `api.js`'s literals** too: 22 `REFUSALS` (20 API + 2) and 8 `CLOSES` (4400, 4408, 4413, 4429, 4502, 1000, 1006, 1011). | Every word a page can show has a sentence. | 0297 |
| **D3010** | ADR 0298 d4: the project's `GET /v1/projects/{key}/usage`. | The checklist reads `GET /v1/organizations/{org}/usage?hours=720` — the same per-project documents, one call per organisation. | Kept; a connection older than 30 days reads *"not seen yet"*. | One call, the longest window. | 0298 |
| **D3011** | Brief screen 2: *"usually 23 to 28 minutes"* before submitting. | `expected` is served only on an operation; the console holds no copy (ADR 0296 d4). | New project's *What happens next* states no number; the tracker shows the served range from its first reading. **Serving `expected` by type before a request is a control-plane widening — a Stage 6 candidate, not this session's.** | No second source of the number. | 0296 |
| **D3012** | ADR 0297: every word, the relay's closes included, worded by `messages.js`. | The editor still words closes through `sql.js` `endSentence` (which also has 1009, not in the derived set). | `messages.js` has `CLOSES`/`closeWords()`; **Run 6 switches the editor and decides 1009**. | The editor is Run 6's. | 0297 |
| **D3013** | D3007: every time formatted. | Branches' restore label shows an RFC 3339 example (an input format). | **Run 9** gives it a `datetime-local` input converted in the page. | An input format is not a displayed time, but it reads like one. | 0295 |
| **D3014** | ADR 0295 d6: every input labelled. | Run 4's `field()` put the hint inside the `<label>`, so the accessible name became label + hint (it broke `get_by_label("Name", exact=True)`). | The hint is **outside** the label, tied by `aria-describedby`. | A label names; a hint describes. | 0295 |
| **D3015** | D3005 (a): never read an operation for context. | Inline `waitFor` (Connect, Branches, Settings) kept polling after the page was left — it could spend an export's one-time link. | `waitFor` takes the route turn and stops; Settings and Branches link to the tracker; Connect's rotate does not (its password is shown on that page). | A poll belongs to its page. | 0296 |
| **D3016** | ADR 0291 d3: the panel shows the operation's id. | The id is in the address (`#/operations/<id>`). | **ADR 0291 amended** (Session 47 Run 5); `journey_walk` j06 reads the id from the URL. | The address is the record. | 0291 |
| **D3017** | D2991: ten console modules. | Connect's password fill and the editor's CSV need DOM-free, Node-tested code that fits no existing module. | **`copies.js`** (a door's string and parts, `fillPassword`, `guide`, `csv`; no snippet text); `ROUTES`, `LISTED` and the parse set widened in the same change; **ADR 0295 decision 3's list is eleven files**. | Pure code is tested in Node. | 0295 |
| **D3018** | D3012: decide `1009`. | The old `sql.js` worded 1009; the page refuses to send over 1 MiB, the relay sends 64 KiB chunks and `max_size` is 1 MiB. | **Not in `CLOSES`**: it cannot arrive; a code with no entry is still worded, with its number. | Word what can happen. | 0297 |
| **D3019** | Brief: copy on every value. | The console's own connection string is `…?sslmode=verify-full` **without `sslrootcert=system`**: libpq then reads `~/.postgresql/root.crt` and psql refuses it on most machines; but node-pg reads `sslrootcert=system` as a file path (D3024), so adding it breaks Node. | **Run 9 measures** which clients take the bare string (rig 47-run6's harness) and labels the generic string for them, pointing everyone else to their tab; the J9 and console proofs read that string, so it moves with them. | One string cannot suit every client; say which. | 0295 |
: psycopg's `sslrootcert=system` was measured (rig 39c). | Rig 39c passed an explicit CA file. **`sslrootcert=system` fails on any machine with `psycopg[binary]`** (3.2.12 and 3.3.4): its bundled OpenSSL's OPENSSLDIR is its build directory (`/host/tmp/libpq.build`). **The psycopg snippet served since Session 39 never verified a certificate.** | **The snippet uses `sslrootcert=certifi.where()`** (executed: verified, query, prepare; misnamed host refused); `test_each_client_verifies_the_server`'s psycopg assertion replaced by the stricter executed one. ADR 0295 decision 7 records it. | *A value that looked measured and was not* (§7). | 0295 |
| **D3021** | — | `services/clients/psycopg/entrypoint.sh` sets `PGSSLROOTCERT=system` in its `verify-full` mode with psycopg[binary] 3.2.12 — the same defect, in a deployment fixture. | **Run 10 repairs it** (its small repairs) and reads which proof uses that mode; untouched by Run 6. | One defect, two places; the second is a fixture's. | — |
| **D3022** | D2956: Drizzle with its migrations. | `drizzle-orm`'s `migrate()` runs `CREATE SCHEMA IF NOT EXISTS` first and is refused (`permission denied for database`) — the customer roles have no CREATE on the database (ADR 0269). | **Drizzle ships for the pooled door**; its migrations' SQL goes through psql's direct line (the snippet's comment says so), and `test_drizzles_own_migrator_is_refused_on_the_direct_door` proves the refusal. Granting CREATE to `customer_admin` is the operator's alternative, not taken. | Ship what runs; say what does not. | 0269 |
| **D3023** | — | Prisma Client does not read `.env`; `directUrl` is Prisma 6's model (7 not measured); `migrate` returns P3005 on a non-empty `public`. | `where` says `node --env-file=.env` and pins `@6`; **Run 8's connecting page says how to baseline** a database that already has tables. | The install line is what was run. | — |
| **D3024** | Brief: an `.env` block for every client. | node-postgres reads `sslrootcert=system` as a file path (ENOENT); psycopg[binary] as D3020. | The `.env` block names only its two measured readers, psql 16+ and Go pgx; the others use their own snippet. | No reader that did not run. | — |
| **D3025** | — | Go needs an image: **`GO_RUNTIME_IMAGE` (golang 1.26-bookworm, Go 1.26.10, by digest)**, read only by tests; `versions.env` feeds every render's `versions_lock_sha256`. | Added with `bin/lock-versions.sh --update --add-images` (the other 15 pins byte-equal); **the next release's outputs move in that field** (Run 12's bump expects it). | A pin, not a guess. | — |
| **D3026** | Brief: does pgx need an exec mode? | pgx's default (cached prepared statements) works through the transaction pooler because the pooler keeps 100 prepared statements per connection (`max_prepared_statements`); `simple_protocol` works too. | No `default_query_exec_mode`; the battery proves the dependency on the pooler's setting. | The pooler's setting is the fact. | — |
| **D3027** | — | psql 17 has no `\parse`; *psql 16+* (for `sslrootcert=system`) is from PostgreSQL's release notes, not a run on 15. | The psql harness uses `\bind`; the `where` line says 16+ and cites it. | Said where it comes from. | — |
| **D3028** | The rig = production's path. | The rig omits the label routers through the socket proxy (it writes the same routers in a file), ACME (a private CA) and the 5432→8432 publication; it adds a `lenient` TLS option (`sniStrict` off) for the wrong-host name only; clients run as root to install the CA. | Accepted and stated in the test's docstring. | A rig names what it leaves out. | 0295 |
| **D3029** | — | Mutation (c) (`max_prepared_statements = 0`) first killed only go-pgx: one sequential connection never switches server connection. | The node-pg, drizzle and prisma harnesses run **3 parallel rounds**; (c) now kills all four. | A survivor named a weak test. | — |
| **D3030** | — | `bin/cloud.py endpoint show` does not print `where`; the packaged CLI changes only in a release of four. | **Run 12** decides whether the CLI shows `where` at the bump; the console renders it (Run 6's console half told). | The console first; the CLI with the release. | — |
| **D3031** | — | CI (p0) and the session-01 gate now build five client images, a golang pull among them; a cache-cold run unmeasured. | **Read on this commit's CI**; if a job's time moves past its limit, a row. | Measured on the next push. | — |
| **D3032** | ADR 0295 decision 8: `sql.js`' decisions are not edited. | Routing closes through `messages.js` (D3012) needed `sql.js`'s close table removed and `endSentence`/`openDoor`/`runStatement` taking the page's `closeSentence` (as they take `call`, `connect`); `test_every_ending_has_a_sentence` moved with it. | **Kept to exactly that**; the protocol decisions untouched; ADR 0295 decision 8 notes it. | The wording moved; the wire did not. | 0295 |
| **D3033** | — | One rehearsal pass of `console_walk` timed out once at *reload: the password is gone* (30 s), at 23:19 — the minute the server half was committed (contention likely, not proven); four repeats green. | The stand-in now loads its module once; **watch at Run 11's rehearsals**. | An unexplained failure is written down. | — |
| **D3034** | Session 40 (D2467): the suite jobs' limit is 30 minutes. | **CI on `8f953b3` was CANCELLED, not failed**: *Session 2 offline contract* reached 30:00 (19:21:04 → 19:51:04); *Session 1 gate* passed in 26:40. The jobs ran 21.7–28.9 min on `c0f9b40`/`ae2da7e`; the executed snippets (five client images, a golang pull) took the offline job over. | **Both suite jobs' `timeout-minutes` 45** (`.github/workflows/ci.yml`, commented); every test that reads `ci.yml` re-run (370 passed). D3031 answered. | A limit the suite outgrows cancels proof, not failure. | — |
| **D3040** | Run 8: `docs/connecting.md`, `docs/sql-editor.md`, `docs/plans-and-usage.md`, `docs/support.md`. | The site's pages are `site/pages/docs/*.md` (ADR 0298 names them). | Written there. | The tree's paths. | 0298 |
| **D3041** | Runnable Debian/Ubuntu install lines. | The site build refuses the word `sudo` in any page (`OPERATOR_TEXT`, ADR 0283). | The page says *"As root:"*; **the second walk is watched for this step** — if the walker stumbles, admitting `sudo apt` lines is an ADR 0283 change for Stage 6. | The build's rule stands until a person shows its cost. | 0283 |
| **D3042** | Cite the official URLs. | `ALLOWED_ORIGINS` refuses a third-party link. | The URLs are code-span text without a scheme. | No foreign link from the site. | 0283 |
| **D3043** | psql 16+ from the distribution. | **Measured in containers 2026-10-29**: Debian 13 17.11, Ubuntu 26.04 18.6, Ubuntu 24.04 16.15 — fine; **Debian 12 15.19 and Ubuntu 22.04 14.24 too old**; PGDG gives 18.6 on both, and PGDG on 22.04 needs `gnupg` (exit 255 without). | Two measured line-sets per OS; macOS/Windows cited (postgresql.org download pages, read 2026-10-29). | Run on each, or cite. | — |
| **D3044** | — | Run 8 confirms D3019 from the docs side: the console's string lacks `sslrootcert=system`. | **Folded into D3019** (Run 9 measures and labels); the site's own string carries `&sslrootcert=system` for psql/pgx readers. | One decision, one row. | — |
| **D3045** | Walk goal 2: *create a table* in the editor. | **Only the direct door's role may create** (in `public`; measured on pinned pg18 from `customer_statements`); the pooled role reads `permission denied for schema public`. The editor opens on the pooled door. | Quickstart and the editor page say *make tables on the direct door*; **Run 7 adds the console's side** — a hint at the editor's door choice and `42501` on `CREATE` worded with *"use the direct door"*. | The walk's own goal must not meet an unexplained refusal. | 0285 |
| **D3046** | ADR 0298: `invite@` at the product's domain. | Markdown has no substitution. | A new `@contact` block renders `INVITATION_ADDRESS` (ADR 0298 amended; ADR 0288's block list widened by one). The page literals that still type the domain are D3063's. | The address is derived. | 0298 |
| **D3047** | — | Prisma's current baselining docs are v7 (`--to-schema`); the served snippet pins Prisma 6. | **Measured Prisma 6.19.1**: `migrate deploy` on a non-empty `public` → P3005; after `db pull`, `migrate diff --from-empty`, `migrate resolve --applied 0_init`, the next migration applies and rows are kept. The page uses those lines. | The version served. | — |
| **D3048** | — | `sslrootcert=system` never run on macOS or Windows (D3020's class: a library whose default store may be empty). | The page says *we have not run it there*. | Said, not assumed. | — |
| **D3049** | — | The site's nav counts every `## ` of the quickstart (*9 steps* for 8; already off by one before). | **Run 12** fixes the count in `site_build`. | A count must count. | 0283 |
| **D3060** | D2960: read `dnsprobe.pool.`/`dnsprobe.direct.`. | `naming.branch_endpoint_hosts` derives branch names. | The probe is derived as a branch name (`slot.WILDCARD_PROBE = "dnsprobe"`); the test types the five names; a wrong name decides `prepared`, an unread one (none wrong) `undetermined` (exit 6). Readers reach it through `slot.observe` — unchanged. | One derivation for a branch's names. | 0195 |
| **D3061** | D3021: repair the fixture with `certifi`, as the snippet. | The fixture image has no `certifi` and a hash-locked requirements file; **measured** (rig `~/s47/run10/rig/`): the old `system` mode failed **closed** (`certificate verify failed` even with the CA trusted). | `PGSSLROOTCERT=/etc/ssl/certs/ca-certificates.crt` (the image's Debian bundle) — connects; `system`, an untrusted CA and a misnamed host each refused. No proof uses that mode today. | No second source of roots in a locked image. | — |
| **D3062** | A.6: `bin/build-cli.py`'s domain lines are harmless now. | The publish job's bare Python cannot import `site_build`; nothing tied its literals to it. | **Parked with `site_build`**; new `test_cli_package::test_the_package_names_the_sites_own_addresses` holds them equal. | The package names what the site names. | 0299 |
| **D3063** | Run 10: *"site text parked with Run 8's"*. | **Run 8's park leaves 7 page literals** of the old domain (`index.md:13,127` incl. a `mailto:`, `quickstart.md:68`, `docs/cli.md:20`, `docs/index.md:12`, `docs/getting-started.md:28,36`); with both parks applied `build-site` refuses (exit 3) on the mailto. | **Run 12 moves the seven** when it applies the parks (Run 8's, then Run 10's), and `build-site --check` must exit 0 before the bump is committed. | Two parks that do not compose are one unfinished move. | 0299 |
| **D3064** | §0: *"tests pin it in 19 files"*. | `test_session43_console:377`, `test_session46_walk:36`, `test_session46_journey:61` pin the site literally (a list of literal pins could not see the first). | All three derived from `site_build.SITE_URL` in the live tree — no park entry needed. | Derived pins move themselves. | 0299 |
| **D3065** | D2969: widen the journey pins. | `tests/external/browser/journey_record.py` stamps `"session": 46` (~:106) and `problems()` refuses `!= 46` (~:158); `journey_walk.py` defaults name `journey-s46-`, `lifecycle-s46`, *Journey s46* and the old domains; `site_look.py:159-160` defaults; `accept.html:13`'s brand link (parked). | Widened in the proofs now; **Run 11 moves the console-lane items** (journey record and walk defaults for Session 47, `site_look` defaults) with the trip's instruments; `accept.html` stays byte-identical until Run 10's park moves it. | The record a Session 47 journey writes must pass its own check. | 0290 |
| **D3066** | D2962: read the constant. | Over the real build the guard passes even when it reads the literal (vacuous). | The parked guard reads `naming.sql_relay_zone(CONTROL_DOMAIN)`; a **planted-host test** proves it finds names; `FORMER_ZONE` still holds `secrets.`, `alpha-db.`, `beta-db.`. | A guard is proved by what it catches. | 0299 |
| **D3067** | — | Renaming the slot test moves `LIFE-SLOT-002`. | Node id and text moved; the matrix and the product contract regenerated. | The registry follows the test. | — |
| **D3068** | *"every other test that pins the old domain"*. | Synthetic slot/zone inputs (`test_branch_*`, `test_capacity_probe`, `test_control_diagnostics`, `test_naming:551`, `test_sql_relay*`, `test_dx_record:425,585`) are not the deployment's. | Left; the move does not make them vacuous. | An example is not a pin. | — |
| **D3069** | Coordinate ADR 0290's two amendments. | — | Run 10's is a separate dated section; Run 8's park applies over it (exit 0). | Two amendments, two sections. | 0290 |
| **D3070** | Brief §2: Notifications with an **unread** count (D3001). | The server keeps no read state (*"In-app only; no read state"*) and the console holds no storage (ADR 0281). | **No count on the link.** The page says *"N in the last 24 hours"* (counting only what the API served; *at least N* when the page read its full 50; undatable notices counted apart) and *"nothing here is marked unread"*. | A number on a link reads as unread. | 0297 |
| **D3071** | — | Since Session 43, Members and keys folded a refused invitations or keys read into an empty list (`.catch(() => ({invitations: []}))`). | Drawn as its refusal (ADR 0195). | A report may not fail closed. | 0195 |
| **D3072** | Run 4: each page's help link. | Members and keys pointed at `/docs/cli/`. | → `/docs/getting-started/` (documents invitations and keys); a test pins every page's help route to a site page naming its label (`TOPIC`: 6 declared aliases). | The link must reach the answer. | 0298 |
| **D3073** | D3045: offer the direct door on a refused creation. | The same 42501 on `app_private` is refused on both doors (the pooled walk's own refused read meets it). | The offer only for 42501 **on schema public on the pooled door**; the match reads PostgreSQL's English message, so a localised server shows no offer — fails closed, the refusal still said. | Offer only what would help. | 0285 |
| **D3074** | — | The support page exists only once Run 8's park is applied. | **Run 12's switch**: `nav.js` `PAGES.help.help` `"/docs/"` → `"/docs/support/"`, enforced by a test that requires exactly the support route when the site builds it (proved with the park applied). | A forcing function, not a reminder. | 0298 |
| **D3075** | — | Notifications draws the limit banner (brief §4). | `pages.json`'s notifications view lists `GET /v1/organizations/{organization}/plan` (an existing route). | The guard reads the union. | — |
| **D3076** | ADR 0298 d4: the checklist hides when every item is done. | A member whose role needs no second factor has no voluntary enrolment control in the console, so *Turn on a second factor* stays *not yet* and the checklist never hides for them. | **Open → Run 9**: the item reads *not required for your role* when `second_factor.required` is false. | A step a person cannot take is not theirs. | 0298 |
| **D3077** | — | `journey_walk`'s usage fixture serves `status: "read"` with 0 samples, which the server never sends. | The console draws the empty state for any document with no sample, so both render; Run 11 aligns the fixture. | Fixtures say what production says. | — |
| **D3078** | Brief §1: plain language. | The `limit_approaching` notification shows the server template's machine word (*"storage_gb is at 4.1 of 5"*; seen in the 390 px look). | **Run 9** words entitlements in the console (*"Storage: 4.1 of 5 GB"*, *"Agent calls today"*), from `plans` names, never the raw key. | A key is not a sentence. | 0297 |

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

**Done.** 2026-10-29. The brief (`docs/design/session-47/design-brief.md`) and the
prototype (`prototypes/console.html`, ten screens, the console's own token block and
typefaces, example data) committed `20b923d`; published as a private page,
https://claude.ai/artifact/YYuCFX7YiqkTfEdu8jh2jG, with the two `woff2` files inlined
(the page host admits no other font source; the console's own bytes). Screenshots of
all ten screens at 390 × 844 and 1280 × 800 from the pinned Playwright image, WSL
`~/s47/run2/shots/`: no overflow, the typeface loaded, no console error, no request off
the origin. The one look found every screen drawn at once (`.page-inner`'s `display:
grid` beat `[hidden]`; the console's own `[hidden]` rule added) and a focus ring
around `<main>` after a screen change (removed); re-shot clean. New text pairs 8.61,
7.33, 5.34:1. **Switchers placed at the top of the left navigation, not the top bar**
(the brief's §2 says why). Found: **D2991** — the snippets are already the server's;
ADR 0295 and Runs 4/6 amended. **Sheet D1: the operator, 2026-10-29, *"Approved"*** —
no revision. Targeted: `test_documentation_index`, `test_acceptance_registry`,
`test_repository_contract`, 308 passed. NEXT FREE D2992.

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

**Done.** 2026-10-29 (notes and scripts WSL `~/s47/run3/`). **Red first**: 16
tests FAILED, 0 ERROR, before any product line (`red.txt`); D2981's test failed
exactly as the person saw it — `{"error":"capacity_exhausted","reason":"no_slot"}`
where `plan_limit_reached` belongs. **0011** generated by `make-0011.py` so its
request and finish are 0008's text with counted insertions (held by
`test_0011s_finish_is_0008s_but_for_the_operation`); the step log, the subject
helper, both readers wider, notifications' `operation_id`/`operation_type`, the kind
`operation_started` and its INSERT policy (the request's definer writes as the
owner under FORCE RLS). Frozen (11 migrations, follows `20261003120039`); proposed
**`f7626621`** (`--by "claude-opus-5-5 Session 47 executor"`): lint passed, **50
migrations from empty, exit 0, 25.1 s**; 21 destructive findings = Session 46's 17 +
exactly 0011's four by design (three readers dropped and re-created, the kind check
replaced). **D2981 repaired** (`_projects_held` counts a keyed, unregistered
creation, as the SQL does); `branch_limit_reached` names `limit` and `plan` from the
route's reader (D2996); `?status=open`; `expected` served from `operation_steps`
(D2992, D2995). Snapshot regenerated (`contracts/control-openapi.canonical.json`).
**Battery `battery3.py` 6/6 killed, every control green**, restored and compared byte
for byte: M1 a step not logged, M2 the digest served, M3 `open` including
`succeeded`, M4 a typical second drifting, M5 D2981 reverted, M6 every request
saying it started (the SQL mutations re-froze the lock and restored it). **Targeted
once** in four shards: C 372 passed + `app-contract --check` 0; A 47; B1 80; B2 72 +
1 failed (`test_plan_limit_reached_is_produced_only_by_the_entitlement_readers`:
D2997) → the module alone 10 passed. Rows **D2992–D2997**. NEXT FREE D2998.

### Run 4 — the console's foundation (ADR 0295)

1. **The module split**: `ui.js` (the components, D2955), `nav.js` (the shell, the
   switchers, the breadcrumb), `messages.js` (D2952), `progress.js` (DOM-free);
   `app.js` draws. **No `snippets.js`** (D2991: the snippets are the server's). `serve.py` `ROUTES`,
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

**Done.** 2026-10-29, built by a delegated agent from this plan, ADR 0295 and the
approved brief, then reviewed in the main session (scripts and outputs WSL
`~/s47/run4/`). **Modules** (ADR 0295 decision 3): `ui.js` (281 lines: `h`
flattening to any depth — the D2713 class found again by the look pass —, copy and
busy buttons, code blocks, callout, banner, empty state, skeleton, toast, tabs,
`STATE_CHIPS` unchanged, `siteDomain` from the host name, one `aria-live` region),
`nav.js` (284: the shell — top bar with Help, Notifications and the account menu
holding Sign out; the left navigation with both switchers; the breadcrumb; the page
template with *Help with this page* to a site route; `loadContext`; a route turn
counter that stops polls), `messages.js` (106: the 16 existing words as `{sentence,
action, link}`), `progress.js` (166, DOM-free: durations, elapsed, the typical
range, step states, a status line with no percent); `app.js` draws through them,
`waitFor` prints words not a percent. **Routes** (no new Ledger row): `#/org/<UUID>`
(projects + open creations by `subject.name`), `#/org/<UUID>/activity`,
`#/operations/<id>` (the first tracker), `#/projects/<KEY>` (the project's Overview),
`#/help`; `#/` is *Projects* (D3002). `ROUTES`, `LISTED` and the parse set widened by
exactly the four files; **budgets split** (`app.css` 21,261 B of 40,960; `site.css`
20,251 of 30,720; together 41,512 B, which the old joint budget would have refused);
**`ANCHORS` counted across every console script** and re-counted, `STATE_CHIPS` read
from `ui.js`; a new `test_console_pages::test_every_view_has_a_page_and_a_built_help_route`
(every help path a route `site_build.build()` produces; no script holds a domain) and
a new module **`test_console_progress`** (5, in the pinned Node image against the
server's own `operation_steps.expected` for all eleven types) — **Run 12 registers
both node ids**. **Battery 7/7** (a module dropped from `ROUTES`, `app.css` over
budget, a label renamed without the count, a step-state off-by-one, an unknown state
drawn ready, the help link removed, a help path the site does not build), controls
green, files restored byte-equal. **Rehearsed twice, all three drivers green**
(`console_walk` 11/11, `--leak` exit 6; `sql_walk` all steps, `--leak` 6;
`journey_walk` j01–j13, `--leak` 6, `--plant-foreign` 5) against the console image
built from this tree. **The main session's review**: a rule scan of every console
script (no markup sink, storage, script-built SVG, typed domain, foreign fetch or
socket) clean; the look at 390 px found the closed Menu taking ~160 px (D3008,
fixed, re-read) and raw ISO times (D3007, Run 5); **targeted re-run by the main
session**: the console set + `test_look` 97 passed; `test_reality_ledger`,
`test_acceptance_registry`, `test_documentation_index`, `test_environment_gates`,
`test_fleet`, `test_suite_shape`, `test_repository_contract` 357 passed, 1 failed —
`test_available_and_beta_rows_name_evidence_that_resolves`, D2945's decided
`plans_live` reading against `session-46.json` (CI skips it). Rows **D2999–D3008**.
**CI on `c0f9b40`: contract 40923498193 success, site 40927940714 success.**

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

**Done.** 2026-10-29, built by a delegated agent from this plan, ADRs 0291/0295–0298
and the approved brief, reviewed in the main session (WSL `~/s47/run5/`).
`progress.js` gains formatted times (`relativeAge`, `absoluteTime` in the browser's
zone), `creationBlocked` and the API-only `checklist` (a failed reading is *not
read*); `ui.js` `when()` draws `<time datetime title>`; **`messages.js` complete** —
22 words + 8 closes, each `{sentence, action, link}`, `plan_limit_reached` and
`branch_limit_reached` worded with their number (D2996). **Projects and organisation
pages**: the checklist (hidden when all five are done), a per-organisation limit
banner linking to `/pricing/` and the Plan page, *New project* disabled with its
reason, pending creations with their step, elapsed and usual time. **`#/operations/<id>`
for all eleven types**: status, subject, start, elapsed, *usually about N to M
minutes*, D3000's bound sentence, named steps done/current/to come with their times,
an indeterminate bar, **no percent anywhere**, the outcome in words with *Connect to
it*. **The creation**: fields disabled while it starts; refused before the form when
the plan is full; on acceptance the address becomes `#/operations/<id>`, the token
panel says *"You do not need it to connect"* and shown-once, the claim behind *Using
it from a terminal (optional)*; *I've saved it, or I don't need it* leaves a one-line
record; after a refresh one sentence says the token is gone and not needed. **ADR 0291
amended.** Notifications: an opening paragraph (*nothing is emailed*), *What makes a
notification*, each kind a sentence with a link. **Every time on every page
formatted** (D3007). New `test_console_refusals` (4 tests) derives the set from the
server's modules and `api.js` by AST/literals; `test_console_progress` +4; pins moved
in `test_console_create`; `ANCHORS` re-counted; `journey_walk` j06 reads the id from
the address (`console_walk`, `sql_walk` unchanged). **Battery 14/14** (an entry
dropped, an entry for no word, a close dropped; the checklist typed or reading
storage; a percent drawn; a raw time drawn twice; New project enabled while blocked
twice; the token kept after dismissal; the branch number dropped; ago/in swapped),
controls green, restored byte-equal. **Rehearsed twice, all green** (`console_walk`
11/11, `sql_walk` 35/35, `journey_walk` j01–j13 with `token_gone_after_dismissal`
true; `--leak` 6, `--plant-foreign` 5, `--dry` 0). The agent's look found and fixed a
squeezed step label at 390 px, tabular spacing in a date and *Your plan* running into
its link. **Main-session review**: rule scan clean (`app.css` 23,930 B); the 390 px
tracker with the token panel and the 1280 px Projects page read as the approved
design; **targeted re-run**: console set + `test_look` 105 passed; the registry,
ledger, documentation, gates, fleet, shape and repository modules 357 passed + D2945's
decided failure. New node ids for Run 12: `test_console_refusals.py::`
`test_every_word_the_api_can_answer_has_an_entry`, `test_every_close_code_has_an_entry`,
`test_each_entry_says_what_happened_and_what_to_do`,
`test_a_refusal_is_drawn_with_its_number_its_action_and_its_word`;
`test_console_progress.py::` `test_every_time_is_an_age_and_a_local_time`,
`test_no_page_draws_a_raw_time`, `test_new_project_waits_for_an_open_creation_and_a_full_plan`,
`test_the_checklist_is_derived_from_the_api_alone`. Rows **D3009–D3016**. NEXT FREE
D3017 (D3020+ reserved for Run 6's server half).

### Run 6 — Connect and the SQL editor

1. Connect (D2956, D2991): the explanations, the password flow per door, copy on
   every value; the snippets from `GET /v1/projects/{key}/connections`, the server's
   `connection_snippets.CLIENTS` widened by `drizzle`, `go-pgx`, `env` with a `where`
   line each; `tests/contract/test_connection_snippets.py` executes each new
   client's text (its image pinned by digest, a TLS rig, `verify-full`) beside the
   existing contract.
2. The editor (D2957).
3. Targeted: the console set, `test_console_sql`, `test_connection_snippets`,
   `test_control_connections`, `bin/app-contract.sh --check`. The battery.

**Done (server half).** 2026-10-29, built by a delegated agent, reviewed and re-run in
the main session (WSL `~/s47/run6/`). `connection_snippets.CLIENTS` = psql, prisma,
node-pg, psycopg, **drizzle, go-pgx, env**; the connections document gains **`where:
{client: {file, install}}`** (snapshot: two descriptions; `app-contract --check` 0).
**Every snippet executed** (`test_connection_snippets.py`, `requires_docker`, images
built at test time from `tests/fixtures/snippet-clients/{drizzle,go-pgx,psycopg}`
with locked dependencies, `GO_RUNTIME_IMAGE` pinned) through Traefik with the
edge's `postgres` TLS option in front of the two customer poolers from
`compose.yaml`'s own entrypoints, `verify-full` against a private CA, a query, a
prepared statement, and a migration on the direct door where the client has one;
**the same text against a misnamed host refused** for every door. **Found: the
psycopg snippet served since Session 39 never verified a certificate (D3020)** —
now `certifi`. Drizzle pooled only (D3022). **Battery** (a) a value instead of the
placeholder, (b/b2) `verify-full` dropped, (c) the pooler's prepared statements off,
(c2) pgx forced to the simple protocol, (d) a `where` line missing, (e) psycopg back
to `system` — all killed, controls green. **Main-session re-run**: the snippet and
connections tests **50 passed, none skipped**; the shape, registry, repository and
every `versions.env` reader **599 passed**; `lock-versions --check` 0. New node ids
for Run 12 (all in `test_connection_snippets.py`):
`test_every_served_client_says_where_it_goes_and_what_to_install`,
`test_each_install_line_names_exactly_what_its_executed_image_pins`,
`test_the_rig_is_the_products_poolers_behind_the_edges_tls`,
`test_each_served_snippet_runs_through_its_doors_with_verified_tls[*]` (7),
`test_each_served_snippet_refuses_a_certificate_for_another_name[*]` (11),
`test_the_misnamed_door_answers_a_client_that_does_not_verify`,
`test_drizzles_own_migrator_is_refused_on_the_direct_door`. Rows **D3020–D3031**.

**Done (console half).** 2026-10-29, built by a delegated agent, reviewed and re-run in
the main session (WSL `~/s47/run6c/`). **Connect** in three numbered steps: the door
(two radio cards, pooled *Recommended*, two lines of use each, *both doors always
exist*); **the password** (made in the browser, only its SCRAM verifier sent, shown
once, replacing the old one — the rotate flow unchanged) in a shown-once panel with
the password and its connection string, both copyable, then *I have saved the
password*; **the code**: one tab per served client in the served order (7), each a
code block with copy and the server's `where` line; the password filled only inside
an amber *held* box and only into its own door's placeholders (`copies.js`
`fillPassword`); *What the connection string means* (each part with copy); *No psql
yet?*. **The editor**: a state bar at the top (connected or not, door, user,
database, *Disconnect*, one live status), **one state function** (`showConnected`) —
connected hides the credentials form, not connected shows it alone; the password
read once, cleared, never stored (ADR 0285); a first statement that changes
nothing; Connect/Run/Cancel/Disconnect busy buttons; results with count, time,
*Copy as CSV* (RFC 4180, `copies.js`) and a sticky header; the session limits beside
*Run* tied by a test to the relay's and `pg.js`'s numbers; **every close worded by
`messages.js`** (D3012, D3018, D3032). Tests: new `test_console_connect` (7) and
`test_console_sql` +4, pins moved, `ANCHORS` re-counted, `console_walk`'s stand-in
built from the server's own module (7 snippets + `where`). **Battery 10/10.**
**Rehearsed twice, green** (`console_walk` 12/12 — `password_outside_the_panel` 0,
`password_gone_after_reload` true; `sql_walk` 36/36 — `form_hidden_while_connected`
true; `journey_walk` j01–j13; controls as before) after one unexplained earlier
timeout (D3033). 48 screenshots: no overflow, no console error, own origin only.
**Main-session review**: rule scan clean (`app.css` 28,705 B); Connect after a password
(390) and the connected editor with results (1280) read as the brief; **re-run**:
console set + `test_look` 116 passed; the registry/ledger/documentation/gates/fleet/
shape/repository modules 357 + D2945's decided failure. **CI on `8f953b3` cancelled at
the 30-minute limit (D3034)** — limit raised to 45 in this commit, whose CI covers the
server half too. New node ids for Run 12: `test_console_connect.py::`
`test_the_password_fills_only_its_own_doors_placeholders`,
`test_a_snippet_holds_a_password_only_inside_the_shown_once_panel`,
`test_every_value_on_connect_has_a_copy_control`,
`test_connect_draws_the_clients_the_server_serves`,
`test_the_guide_line_is_read_when_served`, `test_a_result_is_copied_as_csv`,
`test_the_copies_module_is_dom_free_and_keeps_nothing`; `test_console_sql.py::`
`test_no_close_is_worded_outside_messages_js`,
`test_the_session_limits_beside_run_are_the_relays`,
`test_the_editor_hides_its_form_while_connected`,
`test_the_editors_actions_are_busy_buttons_and_its_first_statement_changes_nothing`.
Rows **D3017–D3019, D3032–D3034**. NEXT FREE D3035 (D3040+ Run 8's, D3060+ Run 10's).

### Run 7 — notifications, help and onboarding

1. Notifications (D2953): the opening paragraph, each kind worded, links to the
   operation.
2. `#/help` and every page's help link (D2958), tested against the site build's
   routes.
3. Empty states with the next action.
4. Targeted: the console set, `test_site`. The battery.

**Done.** 2026-10-30, by a delegated agent (Opus 5.5), reviewed and re-run in the main
session (WSL `~/s47/run7/`). **Notifications**: the intro paragraph, the limit banner,
*Latest* (each a sentence, a time and a link — the tracker, the project or activity),
*What makes a notification*, an empty state; **no count on the link** (D3070). **Help**:
`invite@` + the derived site domain with copy, what to send (the organisation's keys
copyable, the small word, a support bundle from Settings), never a password, the docs
by task (12 built routes); every page's help route pinned to its page (D3072).
**Empty states with one action** on Projects, the organisation, Activity,
Notifications, Branches, Backups, both Usages, Slowest queries, Monitoring, Members
and keys, Connect; skeletons pinned. **D3045 in the console**: the door choice says *to
create tables, connect on the direct door*; a 42501 on schema public on the pooled door
offers *Connect on the direct door* (disconnects, selects direct, focuses the empty
password, keeps the statement — nothing filled, ADR 0285; D3073). Members and keys no
longer hides a refused read (D3071). **Battery 12/12. Rehearsed twice, green**
(`console_walk` 12/12, `sql_walk` 36, `journey_walk` j01–j13; no selector changed).
**Main-session review**: rule scan clean; the refused-on-pooled editor (1280) and
Notifications (390) read as the brief — the look found *storage_gb* in a notice
(D3078, Run 9); **re-run** 124 passed; 357 + D2945's decided failure. New node ids for
Run 12: `test_console_pages.py::` `test_each_help_link_points_at_the_page_that_documents_it`,
`test_the_help_page_asks_a_person_and_links_the_support_route_the_site_builds`,
`test_every_view_that_can_be_empty_says_what_will_appear_and_its_next_action`,
`test_every_view_waits_under_a_skeleton`,
`test_the_notifications_link_carries_no_count_and_no_read_state_is_kept`,
`test_every_notification_kind_is_a_sentence_with_a_link`;
`test_console_progress.py::test_the_notification_count_is_of_what_the_api_served`;
`test_console_sql.py::test_a_creation_refused_on_the_pooled_door_offers_the_direct_door`.
Rows **D3070–D3078**. NEXT FREE D3079.

### Run 8 — the site aligned, PARKED

1. Written in the tree, then parked in `~/s47/run8/park/` with `apply.py`
   (D2911's method): `site/pages/quickstart.md`, `docs/connecting.md` (the
   snippets, per-OS psql), `docs/sql-editor.md`, `docs/plans-and-usage.md`
   (notifications), **`docs/support.md`** (new, `DOCS_GROUPS`); the Ledger texts
   (D2971); `docs/hosted-walk.md` (D2959).
2. Targeted (with the park applied in a scratch copy): `test_site`,
   `bin/build-site.py --check`, `test_documentation_index`,
   `test_session12_documented_path`, `test_dx_record`, `test_reality_ledger`.

**Done.** 2026-10-30, written by a delegated agent in a scratch worktree and **parked**
in WSL `~/s47/run8/park/` (`apply.py TREE`: count-asserted anchors, whole-file copies
only over the sha256 recorded at `99c14b8`, refuses re-apply with exit 3, a changed
base with 5, a partial state with 4; regenerates `docs/reality-ledger.md`); the live
tree untouched. **13 files, +573/−69**: `site/pages/quickstart.md` (eight steps in the
console's words, the tracker's nine steps and *23 to 28 minutes*, the token not needed
to connect), `site/pages/docs/connecting.md` (**generated from the server's own
`connection_snippets`** by `~/s47/run8/gen/make_connecting.py`: the seven clients with
their `where` lines, Prisma's `node --env-file` and P3005 baselining, psycopg's
`certifi`, Drizzle's migrations through psql, per-OS psql measured in containers),
`site/pages/docs/sql-editor.md` (the state bar, the form while disconnected, the limits
read from the code, every close sentence), `site/pages/docs/support.md` (new, in
*Reference*), `plans-and-usage.md` (notifications and the limit banners),
`site_build.py` (`DOCS_GROUPS` + the `@contact` block; the domain constants untouched
— Run 10's), the Ledger's `console`/`projects_self_service`/`notifications` texts (no
status moved), `docs/hosted-walk.md` (goal 2 *run SQL you write yourself*, `slot12-prod`,
`https://nomipg.com`) with `HOSTED_GOALS`, four new `test_site` tests, ADRs 0290 and 0298
amended. Measured on the way: psql per OS (D3043), Prisma 6 baselining (D3047), the
customer roles' grants (D3045). **Battery 7/7.** **Main-session proof**: applied to a
fresh worktree of `99c14b8` → exit 0, again → **exit 3**; `build-site --check` 0;
`test_site`, `test_console_pages`, `test_dx_record`, `test_documentation_index`,
`test_reality_ledger` **112 passed, 1 skipped** (no evidence in a fresh checkout).
**Run 12 applies the park before the bump's push** (it refuses if the quickstart,
connecting or sql-editor page changed since `99c14b8`: regenerate `connecting.md` with
the generator, rebase the others), registers `test_site.py::`
`test_the_connecting_page_shows_the_code_the_server_serves`,
`test_the_quickstart_says_what_the_creation_tracker_says`,
`test_the_sql_editor_page_says_what_the_editor_says`,
`test_the_support_page_gives_the_address_the_build_derives`, and only then lets the
console's Help link `/docs/support/`. Rows **D3040–D3049**.

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

**Done.** 2026-10-30, by a delegated agent, reviewed and re-run in the main session
(WSL `~/s47/run10/`). **Live tree (committed)**: **D2960** — `slot_dns` reads five
names, `ready` requires all five, an unread one is the third outcome (D3060); `bin/slot.py
prepare` prints the five records; operator guide §20/§21 say five; the slot test renamed
`…_all_five_records_are` (LIFE-SLOT-002 moved, D3067). **D2932**'s wording. **D2961** —
the walk proof reads the site by its digest alone, admits an empty `documents_read`
and `commands_run` (ADR 0290 amended). **D2969** — the journey proof's pins read the
record's session (`JOURNEYS = {46: slot11-prod, 47: slot13-prod}`). **D3021** — the
psycopg fixture's `verify-full` mode repaired with the image's CA bundle, measured
with three controls (D3061). The domain in `bin/login.sh`'s usage, `naming.py`'s
docstring and the control example's comment; three literal site pins derived from
`site_build.SITE_URL` (D3064). New module `test_session46_proof_readings` (4) and
`test_cli_package::test_the_package_names_the_sites_own_addresses`. **Parked** (WSL
`~/s47/run10/park/apply.py`, 10 replacements in `site_build.py`, `test_site.py`
(+ a planted-host test, D3066), `accept.html`, `bin/build-cli.py` (D3062)): proved after
Run 8's park in a worktree (exit 0, re-apply exit 3) — **with a stand-in for D3063's
seven page literals, which Run 12 must move**. **Battery 7/7.** **Main-session re-run**:
ruff, `ruff check`, shellcheck 0; 261 passed (slot, reconciler, branch runtime, client
fixtures, compose, proof readings, CLI package, site) and 1,280 passed (naming, CLI
contract, documentation, documented path, registry, gates, admission, shape, fleet,
repository). Rows **D3060–D3069**. **Owed**: Run 11 — the journey record's and walk's
Session 47 defaults (D3065), `s47-dns.sh` reading five names; Run 12 — both parks, then
D3063's literals, then `build-site --check`.

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
