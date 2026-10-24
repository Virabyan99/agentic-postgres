# Session 45 — The visual pass, notifications re-earned, D2805 decided, 1.23.0

**Status: COMPLETE — Runs 1–10 DONE (2026-10-24; rows D2844–D2861, ADRs 0288–0289; 1.23.0 tagged on 4f4b207 and published; NEXT FREE D2862, ADR 0290).** Planned at `702671f` (the stage plan's split,
tree clean, `main` = `origin/main`) against the host as read that morning (§0).
Rows **D2812–D2843** at planning; the runs add theirs from **D2844**. ADRs
**0288–0289** are Run 1's. **NEXT FREE after this table: D2844, ADR 0290.**

The tenth session of Stage 5 and the first half of the operator's split of
2026-10-23 (D2808–D2811): the stage plan's *Session 45* brief
(`docs/plans/stage-5-plan.md` §5 *Session 45*, `:1069-1105`; *Builds*
`:1076-1089`, *Must not* `:1091-1095`, *Measures* `:1097-1100`, *Closes*
`:1102`, *Proposed families* `:1104-1105`) — **the operator's design brief
(`docs/design/session-45/design-brief.md`, *"the honest instrument"*) on the
site and the console, inside the current rules**; **`notifications` re-earned**
by a lifecycle on a new `slot9-prod` run in ONE attempt; **D2805 decided and
repaired**; **1.23.0** released, deployed on four, swept and tagged — with **the
four choices the operator took at this planning on 2026-10-23** (§1 D2812).

Ten runs and **one sitting**. **Run 1** is documentation: two rigs, one root
read on the host (Sheet IR2), one threat item and two ADRs. **Runs 2–7** change
code. **Run 8** is the bump. **Run 9** is the sitting: the release on the four
projects (no database restarts — §1 D2836), the dry runs, the walks (console,
editor, and the new look walk), **the seventh re-earning on a new `slot9-prod`
in one attempt**, the branches, the reboot, the sweep, the external half, the
merge, the tag — and the tag publishes `agentic-postgres-cli` 1.23.0. **Run 10**
is the close.

**Brief:** `docs/plans/stage-5-plan.md` §1 rows **D2808–D2811** (`:339-342`) and
§5 *Session 45* (`:1069-1105`); **`docs/design/session-45/design-brief.md`
whole** — the operator's specification; its five prototypes (`Main.dc.html`,
`Docs.dc.html`, `Pricing.dc.html`, `Ledger.dc.html`, `Mobile.dc.html`) are a
**visual reference only** (they load Google Fonts and a prototyping runtime's
script — never copy their markup); `docs/scope-closure.md` §37 (`:1767-1834`);
`docs/plans/session-44-implementation-plan.md` §10 (`:1721-1760`), Runs 8–9's
**Done.** (`:1498-1632`) and rows **D2795–D2807** (`:477-489`). ADRs **0195**,
**0261** (the Ledger), **0275** (usage samples), **0276** (idle sleep — read
whole), **0280** (the console and its policy, `:85-100`), **0283** (the site,
`:92-149`), **0285** (the console policy as amended, `:146-161`, `:202-209`),
**0287**. D2525 and D2539 (`docs/plans/session-41-implementation-plan.md:489`,
`:508`); D2596 (`docs/plans/session-42-implementation-plan.md:481`).

**Shape:** ten runs. **Run 1** reads **no** CI verdict (documentation; the rigs
and IR2 are recorded in its `**Done.**`). **Runs 2–7** each push and read that
commit's own CI verdict by full SHA (`gh api
"repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<40 chars>" -R
Virabyan99/agentic-postgres --jq '.workflow_runs[] | [.name, .status,
.conclusion] | @tsv'` from Git Bash, never inside `wsl`; judged on HTTP status,
three buckets — success / failure / not registered; an empty list is not a
verdict, D1057). **Every push to `main` also starts the `site` workflow after
`contract` succeeds** (ADR 0283) — **so every site change goes live on its push,
before the release**: each run leaves every page whole and true. **Run 8** is
the bump. **Run 9** is the sitting. **Run 10** is the close (Ledger and envelope
rows are code: it reads CI). **Push only after the previous commit's CI lands**
— `ci.yml` cancels in-progress runs on `main` (`.github/workflows/ci.yml:36-38`).

**Product version at close:** `CURRENT_SESSION` **45**; `template_version`
**`1.23.0`** — predicted *minor* (**no** project-manifest, outputs, host, lock or
Ledger-schema-version change; no migration, released or control-set; no new
secret, service, image or DNS name for the four projects; the console image's
files change (fonts, favicon, CSS, `app.js`); the reconciler's sampler changes
(D2805, host-side, read at its restart)) and **read from `upgrade plan` on the
host, never chosen** (Sheet R1). Released migrations stay **39**; the control
set stays **9**. A `major` is §9's stop.

**Written for whoever picks this up cold, and it will be a different model than
the one that planned it.** Every path below was read from the tree on 2026-10-23
at `702671f` — three explore passes (the site builder, its template, pages,
tests, CI and the Ledger; the console's files, views, helpers, policy, routes
and every test and walk driver that pins its DOM; idle sleep, the request
counter, notifications, the commit-pinned records and the trip machinery of
`~/s44/`) and direct reads of `site/static/site.css`, `site/templates/base.html`,
`services/console/public/index.html`, `tests/contract/test_site.py:20-40`,
`tests/contract/test_console_server.py:25-75`, `src/agentic_postgres/usage_reading.py:41-168`,
`bin/reconciler.py:1490-1515`, `docs/decisions/0276-idle-sleep-is-a-trigger.md`
whole, the rendered `otelcol.yaml` — **and the readings taken at planning**
(§0). **Read CLAUDE.md §1 in the launch folder before the first command, then
this plan's §1, then the appendix.** If a step here and the tree disagree, **the
tree wins and the disagreement is a divergence row** (next free `D` after §1's
table), never a silent reconciliation. **When this plan names a line number,
open the file at that line and read the surrounding twenty lines before
editing** — the numbers were right on 2026-10-23 and `ruff format` moves them.

**The twelve sentences the executor most needs, in case nothing else is read:**

1. **Appearance only.** CSS, two self-hosted typefaces, a logo and favicon, the
   site's template and builder, and class names / wrapper elements in the
   console through its element helper `h` (`services/console/public/app.js:52-67`).
   **No new feature, endpoint, flow or claim**; no framework, bundler or npm; no
   byte from another origin (D2596); the prototypes' markup is never copied.
2. **The fonts' ADR is 0288** (D2810, D2813): Schibsted Grotesk and JetBrains
   Mono, variable, subset to Latin, `woff2`, **one copy** under
   `services/console/public/fonts/` with their OFL licences; the site builder
   copies them into the build; `font-src 'self'` on the site and the console.
   **It moves exactly the tests §1 D2813 lists**, each to an equal or stricter
   form — and nothing else.
3. **D2805 is repaired as the operator chose** (D2832, ADR 0289): an absent
   request series reads **0** only when the store holds a **witness** that the
   edge was scraped for THIS project; with no witness it stays *unread*. The
   sampler alone changes (`usage_reading`, `bin/reconciler.py:1502-1505`); **no
   control migration**. The failing test is written first (Run 2).
4. **The pricing page keeps its two per-plan tables** (the operator, D2818):
   `tests/contract/test_site.py:72-86` and the live
   `test_session43_console.py:411-429` stay untouched; **the pricing page's first
   `<p>` is still `plans.BETA_SENTENCE`** — the template's chrome holds no `<p>`.
5. **The console gets hooks only** (the operator, D2828): no restore-window bar
   from data, no relative ages, no link in refusals — each a Stage 6 candidate.
6. **The *What exists* filter is CSS-only** (the operator, D2819): the status
   class sits on a chip `<span>` inside the *Today* cell, never on `<tr>`/`<td>`,
   so `test_site.py:98-106` and `:185-199` keep their literal `<tr><td>` reads.
7. **Every chip, count and bar on the site is generated by the builder from the
   Ledger or the plan table** — never typed in a page (the brief's rule; the
   check covers what the builder emits through `test_no_forbidden_word`).
8. **The SQL editor and all ten docs pages stay** (D2811, D2822): the editor's
   page joins the *Use a project* group; the console's *SQL* tab stays.
9. **`notifications` moves `planned` → `trial` at the bump (Run 8)**, its
   console view, `pages.json` entry and site mentions restored then (the exact
   inverse of `4d6f892`'s removals), **and → `beta` at the close only on
   `notifications_live` and `notifications_retrial_live`** (D2834).
10. **The lifecycle runs ONCE, detached from the start** (D2796, D2798): a dead
    attempt is §9's stop, never a resume from an earlier record.
11. **The release restarts no database** (D2836): no Postgres image change; the
    console container is recreated on `control-prod` (new files); **the
    reconciler is restarted after the checkout moves** — the D2805 repair lives
    in it (D2179, D2411).
12. **The walks after a reboot** (D2838, D2800's lesson): E0 runs again after B1
    and before the sweep, so the relay's log holds a session the sweep can read.

---

## 0. Where the session starts

```
HEAD            702671ffe96cb608cafbab6ec6b20002a9fc7e2f on main, local = origin
                ("docs(stage-5): the visual pass and the split -- Sessions 45
                and 46 (D2808-D2811)"), tree clean. Last code commit 4d6f892
                (the close: CI contract 39927209097, site 39930380522 success).
                Deployed AND TAGGED: 224b660 (1.22.0, tag object 7102e650) on
                all four projects. main is past the tag with 26c835d, e8f0eaa
                (test-only), 4d6f892 (the console's notifications view REMOVED
                -- deployable, undeployed), e16b38e, 702671f (docs).
VERSION         1.22.0 (VERSION; template_version() src/agentic_postgres/
                __init__.py:1397). CURRENT_SESSION 44 (:1389; Session 44's
                paragraph above it). README.md:7 "Session 44 implemented".
REGISTRY        424 requirements (tests/acceptance-registry.yaml, 8,465 lines;
                Session 44's block from :8306). ID regex tests/contract/
                test_acceptance_registry.py:129 (alternation ends ...|SITE|SQL).
                **No `UI-` id and no `UI` prefix**; USE-IDLE-001 :7610,
                USE-LIVE-001..005 :7691-8020. 331 claims (src/agentic_postgres/
                evidence_claims.py CLAIMS from :580, Session 44's block :1043);
                155 offline (OFFLINE_CLAIMS from :106, Session 44's :517).
                usage_live :989, idle_sleep_live :990, idle_sleep_retrial_live
                :1015. 287 ADRs (docs/decisions/README.md last row 0287).
                NEXT FREE: D2812, ADR 0288.
EVIDENCE        evidence/session-44.json (WSL, gitignored): 331 claims, 328
                passed, 3 failed -- documented_path (D1935), notifications_live,
                notifications_retrial_live (D2798).
LEDGER          docs/reality-ledger.yaml (43 rows): beta 25, planned 9
                (wake_on_connect, notifications -> 45, email, passkeys,
                project_isolation, agents, workflows, connectors, audit),
                not_offered 8, not_metered 1, trial 0, available 0.
                notifications :932-959. schemas/reality-ledger.schema.json
                target_session maximum 45 (:121-128) -- Session 46 exists now.
GATES           bin/session-44-check.sh 2,305 lines (readonly SESSION=44 :102;
                --sql-editor-record-file :182, :1238; mode_offline :1753,
                mode_host :1972, mode_external :2192). tests/contract/
                test_session_forty_four_gate_modes.py 1,133 lines. SHELL_COMMANDS
                tests/contract/test_cli_contract.py (session-44 :271). The roster
                tests/conftest.py (last entry APG_SQL_EDITOR_RECORD_FILE :237).
THREATS         docs/threat-model.md 576 lines; the hosted list's last item 26
                (THR-SQL-DEADLINE, :538).
ENVELOPE        src/agentic_postgres/capacity.py: Session 44's section from
                :2475; UNMEASURED :2636.
HOST            15.204.231.45 (apg-ovh-01), read 2026-10-23 10:10Z (p1-p3).
OPERATOR        2026-10-23 (this planning): D2805 repaired as zero-with-a-
                witness; pricing keeps two tables; the console gets hooks
                only; the ledger filter CSS-only (§1 D2812).
```

**What exists, measured at `702671f`, and the session builds on:**

- **The site builder** — `src/agentic_postgres/site_build.py`, called only by
  `bin/build-site.py` (`--out DIR` refuses a directory inside the repo, exit 2;
  `--check` builds twice and compares, exit 5; a `SiteError` exits 3 —
  `:35-78`). `build()` (`:467-501`) returns `{path: bytes}`: an `index.html` per
  page, `404.html` (`:489-494`), `site.css` (`:495`, the ONLY static file — no
  generic copy) and `_headers` (`:496`). `PAGES_ROOT`, `TEMPLATE`,
  `STYLESHEET` (`:36-38`). `read_page` (`:148-176`): front matter keys
  `title`, `description`, `ledger` only (`:156`). **Its own Markdown subset**
  (`:205-336`): `#`–`###` headings **already carrying `id="{slug(title)}"`**
  (`:300`; `slug` `:214-215`, no de-duplication), paragraphs, one-level lists,
  fenced code → `<pre><code class="language-…">`, pipe tables (no classes), inline
  code/links/strong/em; **raw HTML refused** (`_RAW` `:211`); `@pricing` and
  `@ledger` only as a whole body (`DIRECTIVES` `:106`, `:322`, handled
  `:476-482`). Links (`_href` `:218-231`): the invitation `mailto:`, the
  `ALLOWED_ORIGINS` (`:52-58`), `#…`, `/…`. `_layout` (`:447-464`) replaces six
  keys (`title`, `description`, `digest`, `nav`, `body`, `footer`). `NAVIGATION`
  (`:95-102`): Home, Quickstart, Documentation, Pricing, What exists, Console;
  `aria-current="page"` on an EXACT route match only (`:439-444`). Footer
  (`:449-452`): *"Agentic Postgres {version} · beta · <mailto>"*; `version` read
  from `VERSION` (`:471`). `digest_inputs()` (`:414-424`): every file under
  `site/`, `plans.py`, the Ledger, `VERSION`, `site_build.py`.
  **`CONTENT_SECURITY_POLICY`** (`:62-74`): `default-src 'none'; script-src
  'self'; style-src 'self'; img-src 'self'; connect-src 'none'; font-src 'none';
  base-uri 'none'; form-action 'none'; frame-ancestors 'none'`; `HEADERS_FILE`
  (`:79-88`). `check_page` (`:179-198`): rows reachable
  (`reality_ledger.REACHABLE` = available, beta, trial, `reality_ledger.py:50`),
  `FORBIDDEN_WORDS` (`reality_ledger.py:59-68`: production-ready,
  enterprise-grade, highly available, fault tolerant, multi-region, serverless,
  **autoscaling**, zero downtime), `OPERATOR_TEXT` (`:91`). `pricing_body()`
  (`:358-378`): `BETA_SENTENCE` first, then per plan `<h2 id>`, the
  `PLAN_STATUS_WORDS` paragraph (`:344-349`), a table *Limit | Value | Unit |
  (enforced)*. `ledger_body` (`:392-406`): one `<tr>` per row in YAML order;
  `STATUS_WORDS` (`:382-389`: *available, in the beta, being verified, planned,
  not metered, not offered* — lowercase). `PRICE_MARKS` (`:93`, `:497-500`).
- **The site's files**: `site/templates/base.html` (19 lines; `<title>{{title}} ·
  Agentic Postgres</title>`, `<header><nav>`, `<main>`, `<footer>`; no favicon,
  no logo); `site/static/site.css` **1,595 B** (system fonts, `color-scheme:
  light dark` + a dark block, `--accent #2257c5`, max width 46rem); pages:
  `index.md`, `quickstart.md` (4 numbered `##` steps), `pricing.md` (`@pricing`),
  `ledger.md` (`@ledger`), `docs/index.md` (lists nine pages — **not**
  `sql-editor`), and **ten docs pages**: getting-started, projects, connecting,
  branches, backups, plans-and-usage, insights-and-monitoring, cli, refusals,
  **sql-editor** (linked from no page). Each page's `ledger:` list is in its
  front matter (`site/pages/**/*.md:4`).
- **The site's guards** (`tests/contract/test_site.py`): `POLICY` `:26-30`
  (`font-src 'none'` at `:28`); `test_two_builds_are_byte_equal` `:54`;
  `test_the_pricing_page_follows_the_plans` `:72` (literal
  `<td>projects active</td><td>1</td>`); `test_no_price_is_printed` `:88`;
  `test_the_ledger_page_is_the_rows` `:98` (`count("<tr>") == rows + 1`,
  `<td>{concept}</td>`); `test_raw_html_is_refused` `:108-118`;
  `test_the_site_names_no_host_address` `:121` (**reads every file under `site/`
  as UTF-8**, `:126-127`); `test_every_page_names_reachable_rows` `:153`;
  `test_no_page_holds_an_operator_command` `:174`; `test_no_forbidden_word`
  `:185` (a SUBSTRING scan of every built page, and the ledger page's cells by
  `r"<tr><td>[^<]*</td>(<td>.*?</td><td>.*?</td>)</tr>"`, count 43);
  `test_no_third_party_asset` `:201` (**`"url(" not in site.css`** `:217-219`);
  `test_the_headers_file_carries_the_policy` `:224`. **The live proof**
  (`tests/external/test_session43_console.py:355-429`): every route byte-equal
  to the build (`:370-389`), every `<link>`/`<img>`/`<script>` same-host and 200
  (`:392-408`), **the pricing page's `paragraphs[0] == BETA_SENTENCE` and its
  per-plan `<h2 id>` sections' cell rows** (`:411-429`). `.github/workflows/site.yml`
  (pinned by `tests/contract/test_release_workflows.py:139-170`).
- **The console** (`services/console/`): `public/app.js` 38,086 B, `pg.js`
  17,969, `sql.js` 4,432, `scram.js` 2,858, `api.js` 2,613, **`app.css` 2,759**
  (system fonts, a dark block `:12`), `index.html` 478, `accept.html` 512,
  `pages.json` 4,491; `serve.py` — `ROUTES` (`:53-65`, nine paths), content
  types HTML/JS/CSS/JSON only (`:45-48`), `DIRECTIVES` (`:85-95`, `font-src
  'none'` `:91`), `policy(relay_origin)` (`:103-107`), anything unrouted 404
  (`:199-202`); `Dockerfile` (`COPY public /app/public`, `COPY serve.py` —
  `:17-18`). **Helpers** in `app.js`: `h` (`:52-67`: properties by assignment —
  `className`, `ariaCurrent`, `hidden` work; no `data-*`; **no SVG**), `show`
  (`:72-74`), `refusal` (`:76-83`), `field` (`:85-88`), `once` (`:105-110`),
  `table` (`:116-120`, no classes), `waitFor` (`:123-132`), `outcome`
  (`:134-140`), `frame` (`:334-342`: `header.bar` with *Overview* and *Signed in
  as … Sign out*, `h1`, body — all inside `#main`), `projectNav` (`:344-348`:
  Connect, SQL, Branches, Backups, Usage, Insights, Monitoring, Settings — the
  current tab unmarked), `orgNav` (`:350-353`: Plan, Usage, Members and keys),
  `VIEWS` (`:839-851`), `route` (`:853-892`). Classes in use: `refusal`, `once`,
  `secret`, `qr`, `bar`, `tabs`, `muted`, `inline`, `result`. **Project state is
  plain text** (`:366`, `:495`, `:607`). The type-the-name confirmations exist
  (branch `:479-481`, project `:636-642`) as a check on click.
- **The console's guards**: `tests/contract/test_console_server.py` —
  `ADR_0280_POLICY` `:37-41` and `POLICY` `:43-47` (both `font-src 'none'`),
  `LISTED` `:48-58`, `test_only_the_listed_paths_answer` `:100-113`,
  `test_every_answer_carries_the_policy` `:116-135`, `test_every_asset_is_our_own_file`
  `:164-184` (every `<script|link|img>` in the two HTML files a ROUTES key),
  **`test_the_image_bakes_only_its_own_files` `:194-207`** (two COPY lines;
  `sorted(PUBLIC.iterdir())` names == the ROUTES' files), `test_the_policy_admits_the_relay_alone`
  `:221-230` (only `connect-src` may differ from `ADR_0280_POLICY`).
  `tests/contract/test_console_pages.py`: `_scripts` refuses any `/*` in a
  script (`:45`); `test_no_page_names_an_unreachable_row` `:91-95`;
  `test_no_script_holds_sql` `:98-103`; `test_no_markup_is_built_from_a_value`
  `:115-121`. `tests/contract/test_console_scram.py:87` — the scripts are
  exactly `api, app, pg, scram, sql`. `tests/contract/test_console_sql.py:157-158`
  — two literal substrings of `app.js`. `tests/contract/test_reality_ledger.py:251-280`.
- **The walk drivers pin the console's DOM** (`tests/external/browser/`):
  `console_walk.py` — the accept page's heading and labels (`:266-276`), `img.qr`
  (`:277`), **`code.secret` `.first` = the TOTP seed** (`:284`), *"The next code
  from your app"* (`:292`), heading *Overview* (`:301`), **`#main code.secret`
  `[0]` the password, `[1]` the connection string** (`:335-336`), *Sign out* →
  *Sign in* (`:368-369`); `sql_walk.py` — **one `role=status`** (`:400`),
  `section.result table` (`:412-417`), label *Door* `select_option`
  (`:507`), **label *Password* (substring) unique** (`:508`), **one `#main
  textarea`** (`:519`), buttons *Run* / *Cancel* / *Disconnect* by substring
  (`:521`, `:559`, `:580`), *Connect* exact (`:495`), `get_by_text("Showing the
  first 1,000 rows")` (`:529`).
- **Idle sleep and the request counter** (ADR 0276): the reconciler's usage
  pass reads `requests_counter` by `usage_reading.store_value(key,
  REQUESTS_BELOW_400_QUERY, empty="the store holds no request answered below
  400")` (`bin/reconciler.py:1502-1505`); `REQUESTS_BELOW_400_QUERY =
  'sum(traefik_service_requests_total{code=~"[123].."})'`
  (`src/agentic_postgres/usage_reading.py:44`); **an empty result is
  `(None, empty)`** (`:151-157`: *"Truthfully zero is NOT this case"*); a `None`
  WITH a reason is unread (`reconciler_dispatch.usage_sample`,
  `src/agentic_postgres/reconciler_dispatch.py:762-790`); the decision
  `app.control_request_idle_sleep` (`projects/control/migrations/templates/0008-control-plans-usage.sql:572-632`,
  the window clause `:612-620`: no unread figure, `requests_counter IS NOT
  NULL`, `max = min`, customer activity older than the window; a wake restarts
  the window `:596-601`). **The collector** scrapes the shared edge (`job_name:
  edge`, `apg-edge-proxy:8089`) and KEEPS this project's routers by an
  enumeration and its certificates by `cn` (`src/agentic_postgres/rendering.py:1331-1462`);
  the rendered comment: *"`up` and the `scrape_*` series are NOT filterable here
  … they are the only thing that distinguishes a route nobody used from an edge
  nobody could reach — and both are an absent series."* Guards today:
  `tests/contract/test_idle_sleep.py:159-213`, `tests/contract/test_usage_sampler.py:84-108`
  (its stub always returns a series, `:59` — **no test drives the sampler with
  an empty store answer**).
- **Notifications**: one per finished operation in `control_finish_operation`'s
  own transaction (`0008:378-407`), the daily 80% limit notice
  (`reconciler_dispatch.py:759`, `:836-840`; `0008:636-665`); read by `GET
  /v1/organizations/{organization}/notifications` (`services/auth-api/app/control_routes.py:1435`),
  `apg notifications list` (`bin/cloud.py:1547`). Claims `notifications_live`
  (`USE-LIVE-003`: `test_session41_reearning.py::test_every_finished_operation_was_notified`,
  `::test_no_notification_carries_a_secret`) and `notifications_retrial_live`
  (`USE-LIVE-005`: `test_session42_reearning.py::…_by_its_outcome`,
  `::test_no_notification_carries_a_secret`); both count `operations` +
  `idle_operations` (+ `failed_exports`) of the lifecycle record against the
  product's list (`test_session41_reearning.py:405-444`).
- **What `4d6f892` removed** (to restore at the bump): `app.js` — `orgNav`'s
  `["notifications", "Notifications"]` between usage and settings,
  `notificationsView` after `orgUsageView`, the route
  `[/^#\/org\/([^/]+)\/notifications$/, notificationsView, UUID]` between org
  usage and org settings; `pages.json` — the `notifications` entry after
  `organization-usage`; `site/pages/docs/plans-and-usage.md` — `notifications`
  in its `ledger:` and description and the *Notifications* section;
  `site/pages/docs/cli.md` — the `apg notifications list` row;
  `site/pages/docs/index.md` — *"notifications,"*. **Read `git show 4d6f892 --
  services/console site` before the bump; restore by inverse, count-asserted.**
- **Commit-pinned records** (D2714): the lifecycle record's `source_commit`
  (`tests/external/test_session38_public_lifecycle.py:180-183`) is read by
  Sessions 38–42's lifecycle proofs; the branch record by Sessions 40–41's
  (`test_session40_branches.py:88`, `test_session41_branches.py:79`); the console
  walk's (`test_session43_console.py:205-224`, `session in (43, 44)`); the editor
  walk's (`test_session44_sql_editor.py:97-100`, `== 44`). **Session pins to
  widen to 45**: `test_session38_public_lifecycle.py:83`,
  `test_session39_public_lifecycle.py:76`, `test_session40_reearning.py:83`,
  `test_session41_reearning.py:99`, `test_session42_reearning.py:102`,
  `test_session40_branches.py:77`, `test_session41_branches.py:68`,
  `tests/deployment/test_session40_branch_host.py:103`,
  `tests/deployment/test_session41_branch_host.py:99`. The console and editor
  drivers write their own session (43, 44 — `console_walk.py:78`,
  `sql_walk.py:64`), so their proofs need no widening.
- **The trip's tools from Session 44** (WSL): `~/s44/run6/` (the instruments:
  `s44-derive.py` + `s44-post-derive.py`, `s44-window.py`, `s44-after.sh`,
  `s44-after-reboot.sh`, `s44-units.sh`, `s44-walk.py/.sh`, `s44-sql.sh`,
  `s44-lifecycle.py` (+ `.before-k2-mode`), `s44-branches.py`, `s44-hostyaml.py`,
  `s44-dns.sh`, `s44-free.sh`, `s44-r2shape.py`, `s44-probe-start/stop.sh`,
  `s44-v1.sh`, `s44-x0.sh`, `s44-sweep.sh` + `s44-launch.sh`, `s44-external.sh`),
  `~/s44/run8/` (`NOTES.md`; `bundle.sh`, `s44-checkout.sh`, `renders.sh`,
  `h1.sh`, the detached launchers `life-*.sh`, `br-*.sh`, `ship-records.sh`,
  `offline-place.sh`, `tag.sh`), `~/s44/run9/` (the gate shards; `s44-idle-read.sh`,
  Sheet IR). The pinned Playwright image `PW_IMAGE` (`~/s44/run6/s44-sql.sh:28`,
  `mcr.microsoft.com/playwright/python:v1.63.0-noble@sha256:72bd171a…`).

**Measured at planning** (2026-10-23; no rig was run — every third-party fact
the build relies on is Run 1's, §5):

| # | Reading | Result |
|---|---|---|
| p1 | `apg-diag containers` (agent, 10:10Z) | exit 0; **48 containers**: alpha-dev ×10, beta-dev ×10, control-prod ×12 (the console and the sql-relay among them), slot3-prod ×12, the plane's four (gateway `Up` with no healthcheck); no branch |
| p2 | `apg-diag listeners` | 22, 80, 443, 5432 (+ the resolver's 53, chrony 323, DHCP 68) — unchanged since Session 42 |
| p3 | op: checkout, `free -m`, `uptime`, units, op copies | `224b66022d74adfc96ba71698a6d1e32d7df46c5` clean; total 11,671, **available 8,058 MiB**; up 14 h 41; the reconciler, edge and telemetry units `active`; `/home/op/*-outputs.json`: alpha, beta, control-prod, slot1–8, snippets; `/` 16 G of 96 G |
| p4 | `curl` with `-A agentic-postgres-proof` | `https://agenticpostgresql.com/` 200, `font-src 'none'`, body 2,531 B, every link our own or the mailto; `https://control.agenticpostgresql.com/console/` 200, `connect-src 'self' wss://sql.agenticpostgresql.com; font-src 'none'` |
| p5 | GitHub API (`google/fonts`, read-only) | `ofl/schibstedgrotesk/`: `SchibstedGrotesk[wght].ttf` 176,068 B (blob `78ad61cf…`), `-Italic[wght].ttf`, **`OFL.txt`** (`ba41e114…`), `METADATA.pb`, `upstream_info.md`; `ofl/jetbrainsmono/`: `JetBrainsMono[wght].ttf` 187,208 B (`aa310be8…`), `OFL.txt` (`821a3dac…`). JetBrains' own latest release v2.304 (2023-01-14). PyPI `fonttools` 4.67.0 (MIT), `brotli` 1.2.1 (MIT) — **neither is in the dev lock** (`requirements*.txt`) |
| p6 | `wc -c` | site `site.css` 1,595; console `app.css` 2,759 — **4,354 B combined** against the brief's ~30 KB |

---

## 1. The divergence table

Six columns. Each row is a **measured fact about the tree at `702671f`** (or the
host as the planning readings left it) set against what the brief says, with
the decision this plan takes. **Next free number after this table is D2844.**
Rows the runs add go in a second table below it, in execution order.

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2812** | Stage plan §5 *Session 45* `:1086-1089`: *"D2805 decided"*; the brief's Pricing table, console patterns and ledger filter (`design-brief.md:140`, `:199-216`, `:183`). | Four questions the tree cannot answer: how an absent request series reads; whether the pricing pins move; how far the console's script may move; how the filter is built. | **The operator, 2026-10-23 (this planning): (1) D2805 — an absent series reads 0 with a witness, else unread (D2832); (2) pricing keeps two per-plan tables, restyled (D2818); (3) the console gets hooks only (D2828); (4) the *What exists* filter is CSS-only `:has()` (D2819).** | A product question is the operator's; the plan records the answer, not the argument. | 0288, 0289 |
| **D2813** | D2810: *"`font-src 'self'` … the two pinned tests move WITH it -- `test_site.py:28` and `test_console_server.py:39,45`"*; brief `:24`: *"Contract tests must pass unchanged."* | Self-hosted fonts meet **six** pins, not two: (a) `test_site.py:28` `POLICY`; (b) `test_site.py:217-219` **`"url(" not in site.css`** — `@font-face` needs `url()`; (c) `test_console_server.py:37-47` `ADR_0280_POLICY` and `POLICY` (and `:221-230`, which compares them); (d) `LISTED` `:48-58` (a font is a route); (e) `test_the_image_bakes_only_its_own_files` `:194-207` (`public/`'s names == the routed files; a `fonts/` directory is a name); (f) `test_site.py:126-127` reads every file under `site/` as UTF-8 (a `woff2` there raises). | **ADR 0288 names and moves exactly these, each to an equal or stricter form**: (a)/(c) `font-src 'self'` in all three constants, nothing else in the string; (b) becomes *every `url()` in either stylesheet is one of the font files the build/routes carry* (an allowlist of the measured set — CLAUDE.md §6's *widening to a measured set*), `@import` still refused; (d) `LISTED` gains exactly the routed font, licence and favicon paths; (e) walks `public/` recursively and compares the relative paths with the routed files; **(f) is not moved**: the fonts live outside `site/` (D2814). | A test that must move is named before it is promised unchanged; each moves to what the ADR decides, never loosened. | **0288** |
| **D2814** | Brief `:88-90`: *"Self-host as woff2 from the repo … commit the licence files next to the fonts"*; `:126`: *"Build each [component] once … reuse it on the site and in the console."* | The console's image bakes only `services/console/` (its build context; `COPY public /app/public`, `Dockerfile:17`); the site builder reads any path in the repo but copies only `site.css` (`site_build.py:495`); `test_site.py:126-127` reads `site/` as text. | **One copy of every shared asset, in the console's tree**: `services/console/public/fonts/schibsted-grotesk.woff2`, `jetbrains-mono.woff2`, `OFL-schibsted-grotesk.txt`, `OFL-jetbrains-mono.txt`, and `services/console/public/favicon.svg`. **The site builder copies them** into the build at `/fonts/…` and `/favicon.svg` (a constant `SHARED_ASSETS` in `site_build.py`, the five relative paths listed — never a glob) and adds them to `digest_inputs()`. The console routes them at `/console/fonts/…` and `/console/favicon.svg` (`font/woff2`, `text/plain; charset=utf-8`, `image/svg+xml`). | The one place with a build-context constraint holds the bytes; the place without one copies them. ADR 0002's *derive once*, for files. | **0288** |
| **D2815** | Brief `:88`: *"Prefer the variable font (weight axis 400 to 900) so weights 650 and 750 work"*; `:89`: JetBrains Mono 400 and 500; `:90`: *"Subset to Latin, use `font-display: swap`"*. | No font in the tree; p5: both families exist in `google/fonts` as variable TTFs with `OFL.txt`; `fonttools`/`brotli` are not in the dev lock. | **Run 1's rig 45a makes the two files once**: the TTFs and `OFL.txt` fetched from `google/fonts` at **one pinned commit** (its SHA recorded), subset to Google's *latin* range with `pyftsubset … --flavor=woff2 --layout-features='*'` (the `wght` axis kept; JetBrains Mono's axis limited to 400–500 by `fonttools varLib.instancer` if it saves bytes, else kept whole) in the pinned `PYTHON_RUNTIME_IMAGE` with `fonttools==4.67.0 brotli==1.2.1` installed **in the throwaway container only** — no lock moves, nothing the product runs. The input and output sha256s, sizes and the exact commands go into ADR 0288; `test_the_fonts_are_the_recorded_files` pins the outputs' sha256. | The fonts are artefacts made once and reviewed, like a vendored file — not a build step. | **0288** |
| **D2816** | Brief `:132`: *"Text is the status name in sentence case ("In the beta")"*; `:175`: *"Table text stays exactly as generated today."* | `STATUS_WORDS` are lowercase (`site_build.py:382-389`) and are the ledger page's cell text, read by `test_site.py:185-199`. There is a sixth status, `available` (0 rows), with no colour in the brief's palette. | **The chip's words are `STATUS_WORDS` unchanged**; sentence case is CSS (`.chip { display: inline-block } .chip::first-letter { text-transform: uppercase }`). **`available` takes the beta colours** (the stronger status; a guard holds that every status in `reality_ledger.STATUSES` has a chip class). | One source of the words; the look is the stylesheet's. | 0288 |
| **D2817** | Brief `:141`, `:160`: the stacked status bar and *"In the beta, 25"* legend; the prototype shows *"Being verified, 1"*. | Today `trial` = 0 rows; at the bump `notifications` is `trial` (1), at the close 0 again. | **A segment and a legend entry only for a status with at least one row**; the legend's counts sum to the total, a guard says so; the bar is an inline SVG whose `<rect>`s carry `width`/`x` attributes (presentation attributes — no `style=`, D2820). | A legend entry reading 0 says nothing the Ledger holds; a bar must sum to its whole. | 0288 |
| **D2818** | Brief `:140`, `:171`: ONE pricing table *Limit, Free, Premium* with *"Your plan"* and *"Not available yet"* chips; three notes after it. | Two per-plan tables pinned offline (`test_site.py:72-86`, literal `<td>projects active</td><td>1</td>`) and live (`test_session43_console.py:411-429`: `paragraphs[0] == BETA_SENTENCE`, each `<h2 id>` section's four-cell rows). | **The operator: keep two tables, restyled.** Free's section has the accent wash and a 4 px accent top border, Premium's a 4 px `--border-control` border and muted values; **the chip is the existing `PLAN_STATUS_WORDS` paragraph styled as a caption** (no new words); the enforcement marker is a CSS `::before` on the fourth cell by a class `enforced`/`shown` added to that `<td>` only (its text unchanged). **The template's chrome holds no `<p>`** (the beta bar a `<div>`), so the pricing page's first `<p>` stays `BETA_SENTENCE`. The notes: Markdown after `@pricing` (the builder allows `@pricing` as the FIRST body line followed by Markdown, Run 4) — *"Enforced and shown"* and *"From the terminal"* (`apg plan list` / `show` / `notify-me`) in Run 5, *"Notices at 80%"* only at the bump with `notifications` in the page's `ledger:` (D2834). | The pins are the plan table's own shape, held live; the look moves, the shape does not. | 0283 |
| **D2819** | Brief `:183`: *"a group of visually styled radio inputs and `:has()` rules that hide non-matching rows (each row carries its status as a class)"*; `:175`: *"Showing N of 43 concepts"*. | `test_site.py:98-106` counts literal `<tr>` and reads `<td>{concept}</td>`; `:185-199` reads cells by `<tr><td>…`; a class on `<tr>` or the first `<td>` breaks both. | **The operator: CSS-only.** The builder emits, before the table, one radio per status present (plus *All*, checked) — `<input type="radio" name="status" id="status-<s>">` + `<label for>` with the count (*"Planned, 9"*) — and puts the status class on a **chip `<span class="chip chip-<s>">` inside the *Today* cell**; CSS: `main:has(#status-<s>:checked) tbody tr:not(:has(.chip-<s>)) { display: none }`. **No dynamic *N***: the line reads *"43 concepts"* and each label carries its own count. Without `:has()`, every row shows. No other `<tr>` on the page. | The pins read the row's literal start; a span inside a cell is invisible to them and visible to `:has()`. | 0288 |
| **D2820** | Brief `:128`: the logo as inline SVG; `:132`: chips; `:141` the bar; `:157` the hero's hatched restore window. | Both policies have `style-src 'self'` with **no `'unsafe-inline'`** (site `site_build.py:62-74`; console `serve.py:85-95`): a `style=` attribute in markup is refused. The site's `img-src 'self'` has no `data:`. `h` cannot create SVG (`createElement`, `app.js:52-67`). | **Every SVG uses presentation attributes only** (`fill`, `stroke`, `width`, `x`, `rx`, a `<pattern>` for the hatching); **a guard reads every built page and both console HTML files for `style=` and refuses it**. The console's logo is static markup in `index.html`/`accept.html` (outside `#main`), never built by `app.js`. The favicon is a file (D2814). | The policy is the design's constraint; a guard keeps the next edit inside it. | 0288 |
| **D2821** | Brief `:152-163`: the home's hero (two columns, the restore-window instrument), a 2 × 2 feature grid, the steps, a status band, a plan comparison, a dark invitation band. | The Markdown subset has no blocks (`site_build.py:205-336`); raw HTML is refused (`_RAW` `:211`); a directive is a whole body only (`:106`, `:322`). | **Two builder extensions, both closed sets** (Run 4): (1) **containers** — a line `::: <name>` opens and `:::` closes a `<div class="<name>">` around ordinary Markdown, `<name>` from `CONTAINERS = ("hero", "lead", "actions", "features", "feature", "steps", "band", "band-dark", "note", "warning", "doors")`, nesting one level deep, an unknown name a `SiteError`; (2) **generated blocks** — a line that is exactly `@restore-example`, `@ledger-summary`, `@ledger-examples`, `@plan-summary` or `@docs-index`, or `@chips <row> …` naming only rows in the page's own `ledger:` list (else a `SiteError`), is replaced by builder HTML from the Ledger / `plans.PLANS` / the docs groups; `@pricing` and `@ledger` keep their rule (first line). **All prose stays Markdown, so `check_page` still scans every sentence a person wrote**; raw HTML is still refused. | Layout by a closed vocabulary keeps the page a document; generated blocks keep numbers out of prose. | 0283, 0288 |
| **D2822** | Brief `:143`: sidebar groups listing nine pages (no SQL editor); `:167`, `:185`: *"all nine docs pages"*, *"Docs: 9 pages"*. | **Ten docs pages + the docs index** (§0); `docs/sql-editor.md` is linked from no page; `docs/index.md` lists nine by hand. | **`DOCS_GROUPS` in `site_build.py`** (the brief's four groups) with **the SQL editor in *Use a project* after *Connecting***: Start (Quickstart, Getting started, The command-line client), Use a project (Projects, Connecting, SQL editor, Branches, Backups), Watch and plan (Plans and usage, Query Insights and monitoring), Reference (What a refusal means, What exists). **A guard: every page under `site/pages/docs/` but the index is in exactly one group, and every group entry is a page.** The docs index's list becomes `@docs-index` (each page's front-matter `description`); the mobile menu's *"Docs, N pages"* counts from it (10). Previous/next follow the groups' order. | A visual pass removes nothing (D2811); the count is the builder's, so it cannot drift. | 0288 |
| **D2823** | Brief `:130`: four links (Quickstart, Docs, Pricing, What exists), Console set apart, *Request an invitation* as the primary button; the current page marked. | `NAVIGATION` (`site_build.py:95-102`) has *Home* and *Documentation*; `aria-current` only on an exact route, so no docs page marks *Documentation* (`:439-444`). | **`NAVIGATION` becomes the four** (the wordmark links home), then *Console* and the button (`mailto:invite@agenticpostgresql.com?subject=Invitation%20request` — the address `_href` admits); `aria-current="page"` on the item whose route is a PREFIX of the page's (`/docs/` for every docs page; `/` never a prefix). The `<details>` menu (below 900 px) holds the same items with the brief's one-line descriptions, counts from the builder. Not pinned by any test (§0); the live byte-equality proof follows the build. | Predictable navigation is the brief's fourth principle; the prefix rule is the smallest that marks a section. | 0288 |
| **D2824** | Brief `:41`: no `A · B · C` strings (*"Agentic Postgres 1.22.0, beta"*). | `·` in the site's footer (`site_build.py:450`) and `<title>` (`base.html:9`); the console's footers (`index.html:13`, `accept.html:13`) and the overview's *"state · profile"* (`app.js:366`). None is pinned. | **Rewritten**: footer *"Agentic Postgres {VERSION}, beta"* (plus the four link columns and the feedback line); title *"{title}, Agentic Postgres"*; the console's footer *"Agentic Postgres, beta"*; the overview's state as a chip followed by the profile. | Copy the brief names, at no test's cost. | — |
| **D2825** | Brief `:116`: *"No dark theme in this pass."* | Both stylesheets declare `color-scheme: light dark` with a dark block (`site.css:3`, `:11-20`; `app.css:4`, `:12`). | **Both become `color-scheme: light`, the dark blocks removed.** The tokens block (D2826) is the only colour source. | A dark theme the brief did not design would be a second, unreviewed palette. | 0288 |
| **D2826** | Brief `:26`: *"One CSS file for the site and one for the console (they may share a tokens section by duplication or by an included file if the builder already supports that)"*; target under ~30 KB combined, fonts excluded. | The builder has no include; the console serves its own file. | **Duplication, guarded**: the tokens block is the text between `/* tokens: begin */` and `/* tokens: end */` in `site/static/site.css` and `services/console/public/app.css`; **`test_the_two_stylesheets_share_one_token_block`** holds them byte-equal; **`test_the_stylesheets_fit_the_budget`** holds `site.css + app.css ≤ 30,720 B`. The fonts' bytes are measured and recorded in the envelope, never budgeted. | Two files, one truth, a test between them. | 0288 |
| **D2827** | Brief `:199-204`: states green (ready), blue (creating, starting, updating, suspending, deleting), amber (sleeping), grey (deleted); *"Unknown … must never look like ready."* (D2811 (5)) | `control_states.STATES` (`services/auth-api/app/control_states.py:45-55`): creating, ready, suspending, sleeping, starting, updating, deleting, deleted, unknown. The console shows state as text in three places (`app.js:366`, `:495`, `:607`); branch states come from the branches answer. | **`STATE_CHIPS` in `app.js`** maps those nine to the brief's colours (`state-ready`, `state-busy`, `state-asleep`, `state-gone`, `state-unknown`); **any other value → `state-unknown`** (the dark *not metered* chip); the three places render `h("span", {className: "chip " + cls}, state)` — the text unchanged. Guards: the map's keys equal `STATES` (read from both files), `state-unknown`'s colours differ from `state-ready`'s in `app.css`. The site's hero uses `state-ready` for its example (D2842). | A reader of a state fails toward *I could not tell*, in colour too (ADR 0195). | 0288 |
| **D2828** | Brief `:205-213`: operation rows with ids, a restore-window bar with real data, readings with *"read 3 minutes ago"*, a link to *What a refusal means* in every refusal, a confirm button disabled until the name matches; `:217`: *"No other script changes."* | None of the five exists (§0: `waitFor`/`outcome` print status text; `backupsView` prints a sentence; `monitoringView` one text cell; `refusal` no link; the confirmations check on click). Each needs logic, not a hook. | **The operator: hooks only.** Built: classes and wrappers, the state chips (D2827), the current tab marked (`ariaCurrent: "page"` when the link's `href` equals `location.hash`, in `link`), the shown-once panel's amber border, refusals as the warning callout, tables' numeric columns (`table()` takes an optional set of right-aligned column keys → `className: "num"`), forms, the sign-in panel, empty states' existing sentences. **The navigation maps D2811 (4) with no new view**: the top bar's *Overview* is the existing overview (organisations and projects); the project nav *Connect, SQL, Branches, Backups, Usage, Insights, Monitoring, Settings*; the organisation nav *Plan, Usage, Notifications* (from the bump, D2834) *, Members and keys*; no organisation switcher (none exists — adding one is a flow). **Not built, each a Stage 6 candidate (§10)**: the backups bar, relative ages, the refusal link, operation-id rows, the disabled confirm. | The brief's own rule decides its own extras; the operator chose the rule. | 0288 |
| **D2829** | Brief `:24`: *"the existing element-building helper, no `innerHTML`"*; `:215`: *"SQL editor. Restyle only through CSS … Do not touch its scripts."* | The walk drivers pin the DOM (§0): `code.secret` order, one `role=status`, one textarea, label/button substrings, headings *Overview* / *Sign in*. `sql.js`, `pg.js` are the editor's scripts; its view (`sqlView`, `app.js:778-835`) is in `app.js`. | **`sql.js`, `pg.js`, `scram.js`, `api.js` are not edited.** `sqlView` gains no class; the editor is styled by structural selectors (`#main form`, `#main textarea`, `section.result table`, `[role=status]`). **No new `code.secret`, `role=status`, textarea, heading text, label or button text anywhere**; the sign-in wrapper is a `div`. **Both drivers rehearsed offline after Run 6** (`sql_walk.py --rehearse`, D2789; the console walk's rehearsal from `~/s43/run8/rehearse.sh`) — a driver that needs a change to pass is a row, never a text change in the product. | The drivers are the console's only browser proofs; the pass keeps them reading what they read. | 0285 |
| **D2830** | Brief `:233-239`: no request leaves the origin *"checked in the browser network panel"*; contrast 4.5:1; visible focus; no horizontal scroll at 390 px; *"each page compared side by side with its prototype"*. | Nothing measures any of these: `site_live` checks `<link>/<img>/<script>` hosts (not CSS-loaded fonts), and no proof runs the site in a browser. | **Offline**: contrast from the tokens (`test_every_text_pair_meets_4_5`, the pairs listed in the test with the brief's sizes); `:focus-visible` declared for every interactive selector (a CSS guard). **Live** (new): **the look walk** `tests/external/browser/site_look.py` in the pinned Playwright image — every site route and the console's sign-in at **390 × 844** and **1280 × 800**: `scrollWidth ≤ innerWidth`, every request's origin (the site's own, or the console's own), both families `loaded` (`document.fonts`), a Tab lands on a visible `2px solid rgb(31, 79, 163)` outline, screenshots kept; one 0600 record pinned to the deployed commit and the site's digest → **`ui_look_live`**. **The side-by-side comparison is the operator's** (the screenshots beside the prototypes) and is recorded in Run 9's **Done.**, never as a test. | A browser's own record answers a browser question; a judgement of likeness is a person's. | 0288 |
| **D2831** | Brief `:157`: the hero instrument — *"an example project header with a "ready" chip, the two doors as spec tiles, the hatched restore window … the matching `apg branch create … --at … --wait` command"*; `:16`: sample values labelled as an example. | `apg branch create` takes `--branch`, `--password-dir`, `--at`, `--wait` (`bin/cloud.py:1742-1747`; `site/pages/docs/branches.md:27`). A project's key is its slot's; the name is a display name (`docs/projects.md:28`). | **`@restore-example`** renders a static SVG + HTML block: *"Example project"* caption, the display name *shop-backend*, a `state-ready` chip, doors `pool.[domain]:5432` / `direct.[domain]:5432`, the window *Mon 19 Oct 02:00 UTC* → *Fri 23 Oct 08:40 UTC* with a fixed marker, and **`branches.md:27`'s exact line** with the marker's time (`apg branch create --branch before --password-dir ./branches --at 2026-10-23T08:40:00Z --wait`). A guard: the example's command, minus its values, equals a line on `branches.md`. | The hero shows the real command; an example is said to be one. | 0288 |
| **D2832** | Stage plan `:1087-1089`: *"D2805 decided -- whether an absent request series after a wake reads as zero requests -- and, if repaired, built with its failing test first."* | §0: an empty store answer is unread; the SQL needs `requests_counter IS NOT NULL` and `max = min` (`0008:612-620`); the collector's comment names `up` as the only thing that tells *nobody used it* from *nobody could reach it*; the keep filter keeps this project's certificates by `cn` (`rendering.py:1341-1347`, `:1385`). | **The operator: zero with a witness (ADR 0289).** `usage_reading.requests_below_400(project_key)` → `(int, "")` or `(None, reason)`: the request query; **if empty**, two witness queries — `count(up{job="edge"} == 1)` and `count(traefik_tls_certs_not_after)` (the project's own certificate series, kept by the same filter) — **both ≥ 1 → `(0, "")`**, either empty or the store unreachable → `(None, "the store holds no request answered below 400 and could not show the edge was read")`. The reconciler calls it at `:1502-1505`. **No control migration**: a read 0 satisfies the SQL as written; a later first request (0 → N) reads as moved. **Sheet IR2 (Run 1) reads both witnesses on `slot3-prod`'s store first — if either is absent on a live, awake project, §9's stop.** | D2539 read *no backend* as quiet because the read itself succeeded; this reads *no series* as zero only when the read can show it reached the edge — ADR 0195's third outcome kept for the case it is for. | **0289** |
| **D2833** | Stage plan `:1086-1087`: *"`notifications` re-earned with a lifecycle on a new `slot9-prod`"*; D2805's proof. | The lifecycle's idle step follows the wake, both resizes and the export (`~/s44/run6/s44-lifecycle.py:922-926`, `:1045-1108`) — each recreates services, so the series is absent from then on; attempt 1 of Session 44 slept only because the instrument made requests after its wake (`~/s44/run9/NOTES.md:14-25`). | **`s45-lifecycle.py` makes no HTTP request to the slot's own routes after the last recreation before the idle step** (it reads only the control API and the doors by `psql`, which are customer activity, ended before the setting) **and records it**: `idle.slot_requests_after_recreation` = the instrument's own count (0), and the usage samples of the idle window (`apg usage show --json`). **New claim `idle_after_wake_live`** (`USE-LIVE-006`, external): the window's samples read `requests_counter` **0, never unread**, and the sleep was requested within the window + one interval. | The repair is proved where the defect was found: a woken project left untouched sleeps. | 0289 |
| **D2834** | D2811 (1): *"shown only once `notifications` is `beta` again in that session, by the Ledger check"*. | `reality_ledger.REACHABLE` admits `trial` (`reality_ledger.py:50`); both page guards (`test_console_pages.py:91-95`, `test_reality_ledger.py:251-280`) and `check_page` accept a `trial` row; Session 44 landed the editor's page with its row `trial` (D2746). | **At the bump (Run 8) `notifications` → `trial`** (its `customer_text` says *being verified*, `reality_ledger.py:53`), the console's view, tab, route and `pages.json` entry and the three site mentions restored (the inverse of `4d6f892`), *"Notices at 80%"* on Pricing; **→ `beta` at the close only if `notifications_live` and `notifications_retrial_live` passed** in `evidence/session-45.json`; otherwise `planned` again with the views removed (D2806's precedent). | The Ledger moves in the run that builds the thing; `trial` is the status that says *being verified*. | 0261 |
| **D2835** | D2809: Stage 5 is sessions 36–46. | `schemas/reality-ledger.schema.json:121-128`: `target_session` maximum **45** (*"Stage 5 ends at Session 45"*). | **The bump raises it to 46** with its description (*"since the operator's split of 2026-10-23 (D2809)"*); `test_reality_ledger`'s schema proof runs. | A row Session 46 owns must be writable. | — |
| **D2836** | Stage plan `:1089`: *"1.23.0 released, deployed on four, swept and tagged."* | No Postgres image change on `main` since `224b660`; the console image's files change; the reconciler is a host unit reading the checkout once at start (D2179, D2411). | **Each deploy restarts no database**; `control-prod`'s console container is recreated (its image moved); every new commit recreates auth, mcp and storage (~8–14 s, D2034). **RC1 restarts the reconciler after the checkout moves** — the D2805 repair takes effect then. Run 9's sheets say so. | What a deploy does is named on its sheet. | — |
| **D2837** | Scope-closure §37: *"Session 45's walk needs `slot9-prod`."* | The walk moved to Session 46 (D2809); this session's lifecycle consumes `slot9-prod` (D2748's mechanism, D2714). | **`slot9-prod` is the lifecycle's**; Session 46's person's walk needs **`slot10-prod`** (§10). | A slot is never reused. | — |
| **D2838** | Session 44 Run 8's order: E1 before B1; D2800. | B1's reboot recreates the relay, so its log starts empty and `sql_relay_host` read no session (S1 failed, S1b passed after E0 again). | **E0 runs again after B1 and before S1** (step 6 of Run 9); the look walk (L1) also after B1. | The plan carries the repair the last sitting improvised. | — |
| **D2839** | Run 9 of Session 44: *"shard 7 took 555 of 570 s -- split it."* | `~/s43/run11/shards01.json` (11 shards). | **Run 8 recomputes the shards from the last JUnit times** (`collect-total.sh`) into 12, no shard above 450 s by measurement. | A shard at 97% of its timeout is the next failure. | — |
| **D2840** | Brief `:129`: the beta bar's *"Release 1.22.0 … The version comes from the builder."* | The site deploys on every green push to `main` (ADR 0283); after Run 8's bump it reads `VERSION` 1.23.0 while the four projects run 1.22.0 until Run 9. | **Accepted and said**: the bar names the `VERSION` of the commit the site was built from (the site's own release), as the footer already does. The bump and the deploy are one day apart. | The site's version is the site's; CLAUDE.md §2 already says it can run ahead. | 0283 |
| **D2841** | Stage plan *Proposed families* `:1104-1105`: *"`UI-*` … `LIFE-*` / `NOT-*` re-earned."* | No `NOT` family exists; notifications are `USE-LIVE-003/005`; lifecycle claims re-earn by evidence, never by new ids. | **One new family `UI`**; D2805's ids join `USE` (`USE-IDLE-002`, `USE-LIVE-006`); the re-earning adds no id (§2). | Ids follow the tree's families. | — |
| **D2842** | Brief `:157`: hero heading *"Hosted PostgreSQL 18 that only claims what it has proven."* (*"confirm the checker accepts it"*). | No forbidden word (D2811); `check_page` scans it (`:191-195`). | **Kept**, in `index.md` as the page's `#` heading inside `::: hero`; the fallback is unused. The lead paragraph is `index.md`'s existing first paragraph, edited only where the brief quotes new words. | The checker vouches for it. | — |
| **D2843** | Brief `:160`: *"four example ledger rows (one per status)"*. | `test_no_forbidden_word` is a SUBSTRING scan of every page; the `not_offered` row *Autoscaling* (`reality-ledger.yaml:1047`) would fail it anywhere but `/ledger/`. A page can name only reachable rows in `ledger:` (`check_page`). | **`@ledger-examples`** takes, per status present, the FIRST row in YAML order whose concept and text contain no forbidden word, rendered from the Ledger (concept, chip, `customer_text`) — like `@ledger`, and allowed only on the home page; the page's `ledger:` list is unchanged. | Generated from the Ledger, the examples cannot claim more than the Ledger. | 0283 |

**Rows the runs add** (from D2844):

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2844** | Plan D2815 / Run 1 step 1: the fonts made once by `varLib.instancer` + `pyftsubset`, *"the input and output sha256s … into ADR 0288; `test_the_fonts_are_the_recorded_files` pins the outputs' sha256"*. | **Rig 45a: `fonttools varLib.instancer` 4.67.0 is not reproducible by default** — it stamps `head.modified` with the time of saving. Two fresh containers differed in the `head` table only (`modified` 3875597825 vs 3875565738); `pyftsubset` alone (Schibsted, no instancer) was byte-equal on a re-run. | **The recipe sets `SOURCE_DATE_EPOCH` to the pinned upstream commit's time** (1792720938, `google/fonts` `e7db6ca6`, 2026-10-23T02:02:18Z): two fresh containers then produced byte-equal TTF and `woff2` (`61a4199a…`, 29,232 B), and that build is the one committed and pinned. ADR 0288 records the recipe with the variable. | A pinned hash is reviewable only if the bytes can be made again from the recorded inputs; a clock in the output would make every re-make a different file. | 0288 |
| **D2845** | Plan D2832: the witnesses are `count(up{job="edge"} == 1)` and `count(traefik_tls_certs_not_after)`, read through `store_value`. | `store_value` (`usage_reading.py:160-163`) refuses a series whose `project` label names another project (*"the store answered for another project"*) — but `count(…)` strips every label, so for a bare `count` that check reads `None` and passes **vacuously**. | **The witnesses are `count by (project) (…)`**, so the check applies to them; Sheet IR2 reads each witness's raw label set first. If a witness series carries no `project`, the plan's bare form is used and the reason is recorded in ADR 0289. | Question 3 of CLAUDE.md §7 (whose store answered?) kept for the two readings that decide a zero. | 0289 |
| **D2846** | D2845 / ADR 0289 as accepted at Run 1: the witnesses are `count by (project) (…)`, so `store_value`'s label check applies. | `store_value` refuses only a series labelled with ANOTHER project (`labelled is not None and labelled != project_key`, `usage_reading.py:160-163`); a series with NO `project` label passes it — so `count by (project)` alone would still take an unlabelled `up` (the store's own scrape, or a collector without its `const_labels`) as this project's witness. | **Each witness selects the project inside the query**: `count by (project) (up{job="edge",project="<key>"} == 1)` and `count by (project) (traefik_tls_certs_not_after{project="<key>"})`; the key asserted against `naming.TRAEFIK_NAME_PATTERN` before it enters the matcher (`ValueError` otherwise). IR2 read both witness series carrying `project` on both stores, so the form finds them. ADR 0289 decision 1 says so. Battery m5 (the edge witness without the matcher) and m6 (the key check removed) are killed. | A witness for THIS project must name it; a check that refuses only a wrong name admits no name at all. | 0289 |
| **D2847** | D2813 / ADR 0288 decision 4 (Run 1): six pins move, *"(f) is not moved: the fonts live outside `site/`"*, and *"no seventh test moves"*. | **`test_site.py::test_the_site_names_no_host_address` decodes EVERY built file as UTF-8** (`:125`, `{name: data.decode("utf-8") for name, data in built.items()}`), not only `site/`'s (`:126-127`) — so the build's two `woff2` raise there. Found reading `test_site.py` whole at Run 3, before any build carried a font. A seventh pin; §9's stop. | **The operator, 2026-10-23 (asked at the stop): allowlist the binaries.** The scan reads every text file of the build (`.html`, `.css`, `.txt`, `.svg`, `_headers`) as before, and asserts the files it does not decode are **exactly** the two `woff2` in `SHARED_ASSETS` (pinned by `test_look.py`): stricter — an unexpected binary fails it (battery 3's pin-(g) mutation killed). ADR 0288 decision 4 gains (g), saying its first reading was wrong. | A Run-1 ADR that names the tests it moves must be corrected in the open when the tree shows one more. | 0288 |
| **D2848** | D2813 / D2847: the pins a binary file meets are (a)–(g). | **`test_repository_contract.py::test_no_tracked_file_uses_crlf` (`:393-404`) reads every TRACKED file's bytes and refuses any `\r`** — both `woff2` hold 0x0D by chance (found by running it once the fonts were intent-to-add). A sweep of every whole-tree scan in the suite (`ls-files`, `rglob("*")`) found no other: each filters by suffix or skips an undecodable file. §9's stop again. | **The operator, 2026-10-23: exempt the two fonts by path.** `BINARY_FILES` names them; the test asserts they exist and are the only files skipped, every other tracked file scanned as before; a tracked stray file holding `\r` still FAILED it (control `test_every_text_pair_meets_4_5` passed). `.gitattributes` gains `*.woff2 binary`. ADR 0288 decision 4 gains (h). | The tree's first binary file meets every byte-level guard at once; each exemption names the file, never a kind. | 0288 |
| **D2849** | D2830 / §2 `UI-LIVE-001`: the look walk asserts *"both families `loaded` (`document.fonts`)"* on every site route and the console's sign-in. | **Measured at Run 4** (the local build served with its own `_headers` policy in the pinned Playwright image, Chromium 153): a browser fetches a face only when the page USES it — `JetBrains Mono` reads **`unloaded`** on `/`, `/pricing/` and `/ledger/` (no code on them) and `loaded` on `/docs/connecting/` and `/quickstart/`, at both widths; `Schibsted Grotesk` `loaded` everywhere; no violation, no request off the origin, `scrollWidth` = `innerWidth` at 390 and 1280. | **Run 7's look walk reads each family as `loaded` or `unloaded` and fails on `error`** (a refused or broken font), and asserts `loaded` for both on at least one page that sets code (`/docs/connecting/`). | A face not asked for is not a font that failed; ADR 0195's third outcome is `error`, not `unloaded`. | 0288 |
| **D2850** | Brief `:145`: *"Every page keeps 'Something here wrong or missing? Write to invite@agenticpostgresql.com' above the footer, after a rule."* | Thirteen pages carried the sentence in their own Markdown (`index.md`, `quickstart.md`, the eleven docs pages); `pricing.md` and `ledger.md` did not. With the chrome's feedback line (Run 4), the docs pages showed it twice (seen in the Run 4 screenshots). | **The line is the chrome's** (`_layout`'s `feedback`, `<div class="feedback">`), so every page has it once, the generated pages included; the thirteen pages' own copies were removed, count-asserted (`~/s45/run4/feedback.py`). No test read the sentence. | One place says it, so no page can lose it or say it twice. | 0288 |
| **D2851** | Run 5 step 1: each feature's chips by **`@chips <row> …` — rows the page's `ledger:` already lists**. | `index.md`'s `ledger:` held nine rows; the fourth feature (*Numbers that name their source*) describes `monitoring`, `usage` and `query_insights`, which it did not list — and `@chips` refuses a row outside the page's list (Run 4). | **The three rows join `index.md`'s `ledger:`** (all `beta`, so reachable): a page names the rows it describes, which is ADR 0283's rule and the reason the list exists. | The list is the page's claim; the block may not claim past it, so the list grows with the page. | 0283 |
| **D2852** | Run 5 step 1: *"`::: band` … `::: features` with four `::: feature` blocks"*; brief `:158` *"white band"*; `:160` *"See all 43 in What exists"*. | Containers nest one level (D2821, Run 4): `band > features > feature` is three and is refused. A number typed in prose is what the builder exists to prevent (D2821's rule). | **`::: features` stands alone** under its `##`, its white panel from CSS (`main.home > .features`); the ledger band's link reads *"See every concept in What exists"* — the count is in `@ledger-summary`'s generated heading above it. | The vocabulary's own limit and the counts' own rule, each kept rather than widened for one section. | 0288 |
| **D2853** | D2828: hooks only, *"no behaviour change"*; the sign-in view hides *Code from your app* until the server asks for it (`signInView`, `codeLabel.hidden = true`, shown on `second_factor_required`). | **`app.css`'s `label { display: block }` beats the `hidden` attribute** (an author rule over the user agent's `display: none`), so the field shows from the first paint — in the deployed 1.22.0 too (`224b660`'s `app.css:34`, no `[hidden]` rule). Seen in Run 6's sign-in screenshot, not by any test: neither driver asserts it hidden. | **`[hidden] { display: none !important; }` in `app.css`** restores what the script already says — no script, label or flow changes; guarded by `test_console_look.py::test_a_hidden_field_stays_hidden`. Both drivers' rehearsals pass with it (the editor walk waits for the field after the refusal, as it was written to). | A stylesheet that silently undid a script's state was a behaviour change already made; the pass restores it rather than preserving a defect. | 0288 |
| **D2854** | D2833: *"the window's samples read `requests_counter` **0, never unread**"*, proved from the lifecycle record by an external proof. | The usage answer reports the counter only as `requests: {increase, resets}` over whole hours (`0008:798-854`), never per sample and never its unread count; an hour also holds the probes' requests from before the export, so `increase` is not 0. And no external proof can see the store: the series' ABSENCE -- D2805's case -- is invisible from outside. | **The external proof reads what the outside can show**: the instrument's own count of requests to the slot since the export is 0 (`quiet.slot_requests_after_recreation`), every operation since is an export, and the control set's own decision fired -- which ADR 0276's window clause allows only when every sample READ the counter. **The absence is read at the sitting by a root, read-only sheet (IR3)** while the idle window runs: on `slot9-prod`'s store, `count(traefik_service_requests_total{code=~"[123].."})` **empty** and both ADR 0289 witnesses at least 1 (IR2's script, slot9's container) -- recorded in Run 9's **Done.** beside the claim. | A proof says what it can see; the one fact it cannot see is read once, by the only reader who can, and named. | 0289 |
| **D2855** | D2833 / §2 `USE-LIVE-006`: *"the sleep was requested within the window + one interval"*. | Session 42 measured its idle sleep **1,200.4 s** after the setting (`capacity.ENVELOPE`) -- already past 15 × 60 + 300 = 1,200 s: the reconciler asks after the pass that completes the window, and a pass takes time. | **The proof's bound is the window and two intervals** (1,500 s) -- the plan's own §9 stop line -- and it also holds the sleep no earlier than the window after the last export's finish (a wake or an export restarts the window, ADR 0276). | A bound a measured run already exceeded would fail a correct product. | 0276 |
| **D2856** | Run 7 step 2: the trip scripts derived *"by named substitutions, the counts and the diffs read"*, the detached launchers *"in Session 44's D2796 form"*. | `s45-derive.py` (20 of 20, 65 substitutions; no Session 44 name left in any body; the bare-`44` grep after found only kept lineage headers) also renamed a HISTORICAL comment -- *"Session 45 (ADR 0286)"* in `s45-after.sh`, where the relay is Session 44's -- and Session 44's own `life-start.sh` was not yet in D2796's form (no `PATH`, its output not to a file); no `ext-start.sh` existed (the external half was started detached by hand). | **`s45-post-derive.py` reverts the attribution** and holds every hand edit (the lifecycle's six, `s45-after.sh`'s two, `s45-external.sh`'s two, `s45-x0.sh`'s one), re-applied after any re-derivation; **the four launchers are written in D2796's form** (`life-start.sh`, `br-start.sh`, `br-delete.sh`, and a new `ext-start.sh` wrapper), each refusing a previous attempt's files. | A rename cannot tell a lineage from a claim; the diff read can. | — |
| **D2857** | D2834: *"At the bump (Run 8) `notifications` → `trial` … → `beta` at the close only if `notifications_live` and `notifications_retrial_live` passed"*; §2: seven requirements, `CLAIMS` 338. | **ADR 0261's guards make that row impossible**: `reality_ledger.evidence_problems` refuses a reachable row (`trial` is reachable) with NO evidence, and `trial_problems` refuses a `trial` row naming a claim another session introduced -- and the two claims that verify notifications are Sessions 41's and 42's. No Session 45 claim was about notifications. Found at the bump. | **The operator, 2026-10-23 (asked at the bump): a new Session 45 claim.** `USE-LIVE-007` / **`notifications_reearned_live`** (external): Session 42's two re-earning proofs (`test_every_finished_operation_was_notified_by_its_outcome`, `test_no_notification_carries_a_secret`) read again on slot9-prod's record. The row is `trial` naming it, its console view, tab, route, `pages.json` entry and the site's mentions restored in 1.23.0 as planned; at the close → `beta` only if it AND the two older claims pass. **Counts: 432 requirements (eight new), `CLAIMS` 339, `OFFLINE_CLAIMS` 160, three external** -- the session paragraph, the gate's header and usage and its test's table say so. | A trial row names its own session's evidence; when the evidence is an earlier session's proof re-read, the claim that re-reads it is this session's. | 0261 |
| **D2858** | Run 7: the look driver rehearsed clean (32 readings) against a local build and console image; L0 is a dry run of the same driver against the live site and console. | **L0 exited 4 at 4f4b207: the console's `/console/` failed at both widths, the 30 site pages read.** The driver waited `goto(..., wait_until="networkidle")`; the signed-out console calls `/api/v1/me` (401), then `POST /api/v1/sessions/refresh` (401), and `api.js` `call()` never reads the refused refresh's body -- **Chromium never reports an unread fetch body finished**, so the page never goes idle (measured live with a control: the same 401 fetched from the page with its body READ finishes, UNREAD never does; curl over HTTP/2 and HTTP/1.1 receives the 33-byte body in ~0.7 s -- the server is not the cause). The rehearsal's console had no API behind `/api/v1` (404, no refresh), so it could not see it: the fixture did not share the live answer (D673's class). The product is not wrong for a user (the body is released with the response). | **The operator, 2026-10-23: fix the driver.** A test-only commit: `site_look.read` waits for `load`, `document.fonts.ready` and `SETTLE_MS` 1,500 -- every ATTEMPTED request is still recorded (the `request` event), so the claim stays as strict. Measured as a pair live, one invocation: 4f4b207's driver exit 4 (30 shots, no console), the repaired exit 0 (32, both console widths); Run 7's rehearsal again exit 0 with the planted foreign request named on `/` at both widths. **The deployment stays 4f4b207** (no redeploy, D2799's precedent); `s45-look.sh` accepts a committed checkout ahead of the deployed commit by `tests/` and `docs/` only. `api.js` is untouched (a §9 stop). | A browser's notion of "idle" is a third party's; a walk waits on what it measures. A rehearsal's stand-in that answers less than the live service hides the live service's path. | -- |
| **D2859** | D2833 / Run 7: the export is *"the last recreation before the idle step"*, so after the quiet the slot's request counter has NO series and the idle sleep is ADR 0289's absent-as-0 reading; `test_session45_idle.py`'s docstring says the sleep *"is the reading of an absent series as 0 with its witnesses"*; Sheet IR3 expects `sum(traefik_service_requests_total{code=~"[123].."})` → **0 series**. | **Sheet IR3 at 20:54:43Z (inside the window, before the request): the request series is PRESENT**; the two witnesses one series each, `project=slot9-prod`. slot9-prod's store had run since **20:33:55Z** -- the large resize -- and the instrument's own requests (the resize probes, the export's) followed that recreation before the quiet began at 20:37:05: **the export recreates nothing at the edge**, so the counter was read and unmoved. The idle sleep came at 20:57:48 (origin `idle`, 275.6 s after the setting, 1,213 s after the export's finish) by the ORDINARY path, not by the repaired one. D2805's case -- a recreation with no request after it -- did not arise in this lifecycle. | **Recorded, and the claim's evidence says which** (the plan's own Sheet IR3 sentence). `idle_after_wake_live`'s proofs read only the record (quiet, origin, window, usage) and pass on either path: what this sitting proves is *a woken project left untouched is idle-slept at 1.23.0* (Session 44's attempt 3 was not) and the witnesses live on slot9 (IR3); **ADR 0289's absent-as-0 branch stays proved offline only** (Run 2's `test_usage_sampler` cases). The docstring's last sentence over-claims for this record -- the close decides whether the claim's text moves. | A premise about what an operation recreates is a third-party fact about the edge; the root read that was planned to confirm it is what found it false. | 0289 |
| **D2860** | D2833 (the quiet begins before the export) and D2855 (*"no earlier than the window after the last export's finish"*), written for `test_session45_idle.py` alone; §7: the merge fails `documented_path` only. | **The external half at 4f4b207's records (from 6783f06, 05:53-06:05Z) failed THREE idle proofs; the product slept correctly.** (1) `test_session41_reearning.py:376` and `test_session42_reearning.py:300` assert `15 × 60 − 60 <= seconds_from_setting`: true only while the instrument's quiet began AT the setting (Sessions 41-44). D2833 moved the quiet to 20:37:05, 16 minutes before the setting (20:53:13); the window restarts at the last export's finish, not at the setting, so the reconciler rightly asked at 20:57:48 -- **275.6 s after the setting, 1,213 s after the export**. The plan moved the instrument and missed the two older readers of the field (D979). (2) `test_session45_idle.py::test_the_instrument_made_no_request` -- never executed before -- read every operation from the quiet's start with no end, so the slot's `project.delete` (21:01:19, after the request) joined the two exports; its docstring says *"to the request"*. Merge: 339 claims, 335 passed; `idle_sleep_live`, `idle_sleep_retrial_live`, `idle_after_wake_live` failed beside `documented_path`. | **The operator, 2026-10-24: repair and re-run the external half.** A test-only commit: the two re-earning proofs measure the lower bound from the window's start -- `seconds_from_setting` for a record with no `quiet` reading (unchanged for Sessions 41-44), the later of `quiet.from` and the last export's finish for one with it -- the upper bound `0 < seconds_from_setting <= 1,620` kept; the Session 45 proof's span ends at the request. Battery live against the record, one invocation: controls green before and after, four mutations KILLED as FAILED (the span unbounded; the window from the setting, each module; the start at `set_at`); the start at `quiet.from` alone survives on this record (1,243 s) -- uninformative here (D493). (The battery's first pass ERRORed: separate pytest processes reused a spent TOTP code, `second_factor_invalid`; it now waits a step between runs.) **The deployment, the sweep and the tag stay 4f4b207** (D2799's precedent); the first external run kept in `~/s45/run9/external-1/`. | A reader of a field an instrument change moves is a reader to grep; a span a docstring bounds is a span the code bounds. | 0276 |
| **D2861** | Run 9 step 5 / Sheet B1: `s45-after-reboot.sh` waits for the units with `/home/op/s45-units.sh`, then reads whether the boot started each. | **`s45-units.sh` had never been copied to the host**, and the first read ran while the boot was still under way: `UNITS_EXIT=127`, `multi-user.target` at mono 0, and every unit judged *"NOT the boot"* -- the reader went on without its waiter and folded *could not determine* into seven failures (ADR 0195's class). | Copied at 04:48Z and re-read: the verdict compares the boot's own monotonic timestamps, so a later read is the same reading -- **all seven started by the boot**. The early read kept as `after-reboot-1-early.txt`. | A host-side dependency ships with the sheet that runs it; a reader whose waiter cannot run stops, it does not judge. | -- |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**One new family, `UI`** (D2841): the regex at
`tests/contract/test_acceptance_registry.py:129` gains `UI` after `SQL`, and the
family comments gain one sentence after Session 44's: *Session 45 (ADR 0288)
adds `UI` for the visual pass.* No existing prefix begins `UI`. **Seven
requirements, seven claims, all `target_session: 45`, all P0 — five offline,
two external.** Node ids are **proposed; Run 8 writes what the runs actually
wrote**, read with `pytest --collect-only -q` (D1236, D2129). Committed by Run 8
with the constant (D690), under **`# Session 45 (ADR 0288-0289)`** at the end.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `UI-TOKENS-001` | One token block in both stylesheets, byte-equal; every text pair ≥ 4.5:1; light only; `:focus-visible` on every interactive selector; the two stylesheets ≤ 30,720 B | `tests/contract/test_look.py::test_the_two_stylesheets_share_one_token_block`, `::test_every_text_pair_meets_4_5`, `::test_there_is_no_dark_theme`, `::test_every_interactive_element_shows_focus`, `::test_the_stylesheets_fit_the_budget` | — (`ui_tokens`) |
| `UI-FONTS-001` | The two typefaces are the recorded files, with their licences, served from the origin only: the console routes them as `font/woff2`, the build carries them, both policies say `font-src 'self'`, every `url()` names one of them | `tests/contract/test_look.py::test_the_fonts_are_the_recorded_files`, `::test_each_font_has_its_licence`, `::test_every_url_is_one_of_the_fonts`, `tests/contract/test_console_server.py::test_the_fonts_are_served_as_fonts`, `tests/contract/test_site.py::test_the_build_carries_the_shared_assets` | — (`ui_fonts`) |
| `UI-SITE-001` | The site's chrome and components come from the builder: chips are the page's rows' `STATUS_WORDS`; counts and the bar equal the Ledger's; every docs page is in exactly one group; previous/next follow the groups; heading ids unique and *On this page* lists every `h2`; the navigation's current item; no `style=` and no `<script` in any page; the restore example's command is `branches.md`'s | `tests/contract/test_site_look.py::test_chips_are_the_rows_words`, `::test_the_counts_are_the_ledgers`, `::test_the_bar_sums_to_the_ledger`, `::test_every_docs_page_is_in_one_group`, `::test_previous_and_next_follow_the_groups`, `::test_heading_ids_are_unique_and_listed`, `::test_the_current_section_is_marked`, `::test_no_page_carries_a_style_attribute`, `::test_the_restore_example_is_a_documented_command`, `::test_an_unknown_container_is_refused` | — (`ui_site`) |
| `UI-CONSOLE-001` | The console's look adds no script, route or text: the state map covers every state and fails to `unknown`; `unknown` never looks like `ready`; the logo is static markup; no `style=` in its HTML; the walk drivers' anchors are unchanged | `tests/contract/test_console_look.py::test_every_state_has_a_chip`, `::test_an_unknown_state_is_never_ready`, `::test_the_logo_is_static_markup`, `::test_no_console_page_carries_a_style_attribute`, `::test_the_drivers_anchors_are_unchanged` | — (`ui_console`) |
| `USE-IDLE-002` | The request reading: a series → its value; no series with both witnesses → 0, read; no series without a witness, or the store unreachable → unread with its reason; a woken project left untouched is idle-slept in the control set's own decision | `tests/contract/test_usage_sampler.py::test_an_absent_series_with_a_witness_reads_zero`, `::test_an_absent_series_without_a_witness_is_unread`, `::test_a_present_series_is_its_value`, `tests/contract/test_idle_sleep.py::test_a_woken_project_left_untouched_sleeps` | — (`idle_absent_series`) |
| `UI-LIVE-001` | Through the public origins with no SSH, in Chromium: every site route and the console's sign-in at 390 and 1280 px — no horizontal scroll, every request to the page's own origin, both typefaces loaded, the focus ring drawn; the record pinned to the deployed commit and the site's digest | — | `tests/external/test_session45_look.py::test_the_look_walk_reached_every_page`, `::test_no_page_scrolls_sideways`, `::test_every_request_stayed_on_its_origin`, `::test_both_typefaces_loaded`, `::test_focus_is_visible`, `::test_this_module_uses_no_ssh` (external `ui_look_live`) |
| `USE-LIVE-006` | Live: after the lifecycle's last recreation, with no request to the slot, the idle window's samples read `requests_counter` 0 (never unread) and the reconciler requested the sleep | — | `tests/external/test_session45_idle.py::test_the_idle_window_read_zero_not_unread`, `::test_the_instrument_made_no_request`, `::test_the_sleep_was_requested_in_the_window` (external `idle_after_wake_live`) |

**Expected counts** — Run 8 counts them from the tuples, never from this prose
(D1628): requirements **424 → 431**, `CLAIMS` **331 → 338**, `OFFLINE_CLAIMS`
**155 → 160**, ADRs **287 → 289**.

**Claims** (`src/agentic_postgres/evidence_claims.py` `CLAIMS`, a block commented
*Session 45 (ADR 0288-0289)* after Session 44's `:1043`): offline — `ui_tokens`,
`ui_fonts`, `ui_site`, `ui_console`, `idle_absent_series` — **these five** in
`OFFLINE_CLAIMS` (after Session 44's `:517` block) with the per-session
assertion in `test_session_forty_five_gate_modes.py` (D1237: assert THESE are in
the set, never its size). External — `ui_look_live`, `idle_after_wake_live`.
`CLAIM_INTRODUCED_IN` (`tests/contract/test_evidence_claims.py`) gains a row at
45 for each.

**Existing entries that move** (each a passing proof made stricter or its
fixture moved under ADR 0288 — CLAUDE.md §6):

- **`SITE-DEPLOY-001` / `SITE-BUILD-001`**: `test_site.py`'s `POLICY` (`font-src
  'self'`); `test_no_third_party_asset`'s `url(` refusal becomes the font
  allowlist (D2813 (b)).
- **`CON-SERVE-001`**: `ADR_0280_POLICY` / `POLICY` (`font-src 'self'`),
  `LISTED` (+ five paths), `test_the_image_bakes_only_its_own_files` recursive
  (D2813 (c)–(e)).
- **`CON-LEDGER-001`**: none — `notifications` returns as `trial` (D2834).
- **The record-reading modules** (D2714): the nine session pins of §0 gain 45
  (Run 7, count-asserted); **no `source_commit` check touched**.
- **`THR-*`**: one row added in Run 8 (`THR-UI-FONT`, threat item 27); none
  removed.

**New environment gates: one** — `APG_LOOK_RECORD_FILE`, in the roster
`tests/conftest.py` after `:237`, exported by the gate's external mode
(`--look-record-file`). **The idle proof reads the lifecycle record** already
exported (`APG_LIFECYCLE_RECORD_FILE`) — no second gate. **Read in a test body
with `.get(...)`, never `x["APG_…"]`** (D2381).

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| **Two third-party typefaces committed** (OFL-1.1) | Run 3 | Fetched from one pinned `google/fonts` commit, inputs' and outputs' sha256 in ADR 0288, licences beside them, served from our origins only (D2596 holds: no byte from another host) |
| **The site's new look published** on each push to `main` | Runs 3–5, 8 | `site` workflow after `contract` (ADR 0283); each run leaves every page whole; the Ledger check and the word scans on every build |
| `CURRENT_SESSION` 44 → 45; `VERSION` 1.22.0 → 1.23.0; `notifications` → `trial` with its views; the Ledger schema's maximum → 46; THR row | Run 8 | All-or-nothing (D690); `README.md:7` and every `--session 44` literal on the documented path moved and counted per file (D678/D1484); ADRs 0261, 0288 |
| `bin/session-45-check.sh` | Run 8 | Derived from 44's by diff (D1482); header and usage rewritten whole (D1488); one flag (`--look-record-file`); `SHELL_COMMANDS`; `chmod 755` before `git add` |
| **1.23.0 deployed on the four projects** — no database restart; the console recreated on `control-prod`; the reconciler restarted | Sheets R2a–R2d, RC1 (Run 9) | The reconciler stopped (D2178); one project at a time, each window probed; control-prod last |
| **`slot3-prod`'s `customer_app` password rotated again** (W1′) | Run 9 | The probe organisation's own project; the old creds file kept as `.before-s45`, the new written 0600 by the instrument |
| **A walker account and its membership in `probe-s37`** (W0′, W1′) | Run 9 | Membership removed after; accounts are never deleted (D2065) |
| **`slot9-prod` declared, provisioned, created, slept, woken, resized, exported, idle-slept, deleted — consumed**; its three grey A records and two R2 buckets | Run 9 (H1 … SL4) | Session 44's sheets renamed (D2748); ONE attempt (D2798); a slot is never reused; its identity revoked after the tag |
| Tag `1.23.0` on the deployed commit | Run 9 | After the merge exits 5 for `documented_path` only (§7); from the WORKSTATION (D2041) |
| **`agentic-postgres-cli 1.23.0` published to PyPI** | Run 9, by the tag | `publish-cli`'s `verify` reads that SHA's `contract` success; a PyPI version is never re-uploaded |

---

## 5. Build order, run by run

Each run ends with a `**Done.**` paragraph written by the executor: what was
measured, the numbers, the rows it added, and — for a code run — the CI verdicts
by full SHA (`contract` and `site`). The targeted modules run ONCE at the run's
close and only a failing module is re-run. `ruff format && ruff check` before
every commit; `chmod 755 bin/*.sh bin/*.py deploy.sh libexec/*` before every
`git add`; messages from a file with `-F`, ending with the attribution lines the
session's system reminder gives. **Grep the plans for every third party before
measuring it.** **A run that renames, adds or removes a test function runs
`test_acceptance_registry` and `test_evidence_claims`** (D1119); **a run that
touches a documentation page or a site page runs `test_documentation_index`,
`test_session12_documented_path` and `test_site`**; **a run that touches
`services/console/` runs `test_console_server`, `test_console_pages`,
`test_console_scram`, `test_console_sql`, `test_console_plane` and
`test_reality_ledger`**; **a run that touches `site_build.py` runs
`test_site`, `test_release_workflows` and `bin/build-site.py --check`**;
**every new test module carries `pytestmark` before its first test** (D1240),
and the sweep-selector guard (D1242) AND `test_environment_gates` join the
targeted list of any run that adds a module — **read a model dict with
`.get("APG_…")`, never `x["APG_…"]`** (D2381). **A run that adds a module under
`tests/deployment/` runs `test_deployment_suite_shape`** (D2721; none planned).
**Every mutation battery** follows CLAUDE.md §1: `PYTHONDONTWRITEBYTECODE=1`,
snapshot to `/tmp` and restore by copy with `cmp`, anchors pre-flighted (a miss
fatal), a control the mutation cannot reach, and *how* each failed (`FAILED` vs
`ERROR`). **Never backticks in an inline heredoc; any script with a loop goes
in a file** (CLAUDE.md §1). **A JavaScript check runs in the pinned
`NODE_RUNTIME_IMAGE`** (`versions.env:18`), as `test_console_scram.py` does. **A
browser measurement runs in the pinned Playwright image** (`PW_IMAGE`, §0),
with the Playwright package reused from `~/s44/walk-home/pw` (Session 44's
method).

### Run 1 — the fonts made, the browser and the store measured, ADRs 0288–0289

**Documentation; no code; no CI read.** Grep the plans first for `font`,
`woff`, `:has(`, `traefik_tls_certs_not_after`, `up{job` (CLAUDE.md §4).

1. **Rig 45a — the typefaces** (WSL `~/s45/rigs/45a/`; D2815). Read the
   `google/fonts` default branch's head SHA; fetch at THAT SHA
   `ofl/schibstedgrotesk/SchibstedGrotesk[wght].ttf`, `ofl/schibstedgrotesk/OFL.txt`,
   `ofl/jetbrainsmono/JetBrainsMono[wght].ttf`, `ofl/jetbrainsmono/OFL.txt`, and
   both `METADATA.pb` (the licence field `OFL`, the axis ranges). In the pinned
   `PYTHON_RUNTIME_IMAGE` with `pip install fonttools==4.67.0 brotli==1.2.1`
   (the container thrown away): `fonttools varLib.instancer` to limit JetBrains
   Mono to `wght=400:500` **only if** the subset is smaller by more than 10%
   (record both sizes); `pyftsubset <ttf> --unicodes=<Google's latin range,
   written in the rig file> --layout-features='*' --flavor=woff2
   --output-file=<name>.woff2` for each. **Read back**: `fonttools ttx -l` on each
   output (the `fvar` table present with the expected axis; the `cmap` covering
   A–Z, a–z, 0–9, `£€—–’“”…`); sizes; sha256 of inputs and outputs. **Control**:
   the same subset of a TTF from a second `google/fonts` path (any OFL family)
   produces a different sha256 (the hash reads the file, not the name). Record
   `~/s45/rigs/45a/rig.txt`.
2. **Rig 45b — the browser** (WSL `~/s45/rigs/45b/`; the Playwright image; a
   `python3 -m http.server`-shaped server written in the rig that sends a header
   set). Four pages, each read for console messages and `document.fonts`:
   (1) `font-src 'self'` + `@font-face` to a same-origin `woff2` served as
   `font/woff2` with `nosniff` → both faces `loaded`; **control**: `font-src
   'none'` → `error`, a CSP violation logged. (2) an inline SVG with `fill`,
   `stroke`, `rx`, a `<pattern>` under `style-src 'self'` → no violation;
   **control**: one `style="fill:red"` attribute → a violation logged. (3) a
   table filtered by `main:has(#status-planned:checked) tbody
   tr:not(:has(.chip-planned)) { display: none }` → clicking the label hides
   exactly the other rows; **control**: *All* checked shows every row.
   (4) `<details>` menu at 390 × 844: closed hides its list, open shows it;
   `document.documentElement.scrollWidth` read (the method the look walk uses);
   **control**: a 600 px-wide element makes it exceed 390. Plus: a `:focus-visible`
   outline read by `getComputedStyle` after `keyboard.press("Tab")` (the method,
   `outline-style` / `outline-color`). Record `~/s45/rigs/45b/rig.txt`.
3. **Sheet IR2 — the witnesses on a live store** (the operator; root;
   read-only; D2832): three instant queries against `slot3-prod`'s store through
   its container, as Session 44's Sheet IR read the control database —
   `count(up{job="edge"} == 1)`, `count(traefik_tls_certs_not_after)`,
   `count by (__name__) ({__name__=~"up|traefik_.*"})` — and the same three on
   `alpha-dev`'s store (**the control**: a project with no customer door still
   has both witnesses). **Either witness absent on an awake project → §9's
   stop** (ADR 0289 would need another witness, and that is the operator's).
4. **Threat item 27** — *a font file from a third party's repository* (THR-UI-FONT
   at the bump): a browser parses a font, so a malicious font is code reaching
   the parser; mitigation: one pinned upstream commit, inputs' and outputs'
   sha256 in ADR 0288 and pinned by a test, served same-origin under `font-src
   'self'`, no third-party host at run time. `docs/threat-model.md` after item 26.
5. **ADR 0288 — *The site and the console share one look: self-hosted
   typefaces, one token block, presentation in stylesheets only*** — the
   decisions of D2813–D2830 (the fonts and their provenance from rig 45a; the
   shared assets' one place; `font-src 'self'` on both, as the documentation
   page has had since ADR 0069; the six moved tests named, each with its new
   form; the token block duplicated and guarded; light only; the closed
   container and generated-block vocabularies; the filter; the state chips;
   hooks only, the Stage 6 list; the look walk). **Amends ADR 0280** (the policy
   constant: `font-src 'self'`; the routes) **and ADR 0283** (item 7's policy;
   item 8 reads *"no font … from another host"* — unchanged in substance).
6. **ADR 0289 — *An absent request series reads zero when the store shows the
   edge was read for the project*** — D2832 with IR2's reading. **Amends ADR
   0276** decision 2(a) (the reading of an absent counter) and the module
   sentence of `usage_reading.py:9-10` (*"Nothing here returns a zero for a
   reading that did not arrive"* → *"…unless the store shows the edge was read
   for this project"*). Both ADRs indexed in `docs/decisions/README.md`.

**Done (2026-10-23).** Greps (step 0): `woff`, `:has(` only in this plan and the stage
plan's D2810; `traefik_tls_certs_not_after` and `up{job` in Session 14's
D782–D784 (a stopped edge reads `up` **0, not absent**; `honor_labels: true`
keeps `job="edge"`; the certificate series is kept by `cn`) — ADR 0289 rests on
them. **Rig 45a** (`~/s45/rigs/45a/rig.txt`): `google/fonts` pinned at
`e7db6ca603fd4862010383ff17ffd6cc4ffac1c0`; the four inputs' git blobs equal
planning's p5; both `METADATA.pb` `OFL` (axes 400–900, 100–800); Google's
`latin` range read from its CSS API; JetBrains Mono limited to `wght` 400–500
(28.1% smaller, 29,084 vs 40,460 B); outputs `schibsted-grotesk.woff2`
`b29bc789…` 49,112 B and `jetbrains-mono.woff2` `61a4199a…` 29,232 B (78,344 B
together), `fvar` kept in both, no glyph missing for the brief's set or the
tree's own non-ASCII text (`£§·—…€`); controls: Schibsted re-run byte-equal,
Lexend through the same command a different hash; **D2844** (the instancer's
timestamp, fixed by `SOURCE_DATE_EPOCH`). **Rig 45b** (`~/s45/rigs/45b/rig.txt`,
Chromium 153.0.8010.12): both faces `loaded` under `font-src 'self'`, `error`
with two violations under `'none'`; presentation-attribute SVG no violation,
`style=` a `style-src-attr` violation with the fill unchanged; the `:has()`
filter shows exactly the chosen status, *All* every row; `<details>` closed
hidden / open shown; `scrollWidth` 390/390, 600/390 with the control; `Tab` →
`2px solid rgb(31, 79, 163)` and `:focus-visible`, a mouse click → no ring.
Playwright's `request` event records blocked attempts too (the look walk reads
attempts). No §9 stop met by either rig. **Sheet IR2** (the operator, root,
read-only, 2026-10-23 11:12:10–11:12:14Z, `/home/op/s45-ir2.txt` exit 0; the
agent's copy `~/s45/run1/s45-ir2.txt`; the script, sha256 `84238cac…`, placed
by the agent at the operator's word after the session's permission classifier
had refused the first write): on **`slot3-prod`** (12 containers, store up
since 2026-10-22T19:29Z) `count(up{job="edge"} == 1)` 1 and
`count(traefik_tls_certs_not_after)` 1, each series labelled
`project="slot3-prod"` (`instance="apg-edge-proxy:8089"`; the certificate's
`cn="slot3.agenticpostgresql.com"`, the doors' certificates not kept), each
`count by (project)` form one series `{project="slot3-prod"}`; on the **control
`alpha-dev`** the same (`cn="alpha-db.agenticpostgresql.com"`). Both request
series were present, so the absent case itself waits for the lifecycle (D2833).
**No §9 stop.** **D2845 settled**: the witnesses are built as `count by
(project) (…)`. **Threat item 27** written. **ADR 0288** and **ADR 0289** written
(both Accepted, 0289 on IR2's reading) and indexed; ADRs 0276, 0280, 0283, 0285
carry the amendment in their status lines. No seventh test moves: the live site
proof reads only `index.html` routes and page `<link>/<img>/<script>` assets.
Rows D2844–D2845; **NEXT FREE D2846, ADR 0290.**

### Run 2 — D2805 repaired (`usage_reading`, the reconciler, tests first)

**Read first:** ADR 0289; `src/agentic_postgres/usage_reading.py` whole;
`bin/reconciler.py:1440-1560`; `src/agentic_postgres/reconciler_dispatch.py:740-800`;
`tests/contract/test_usage_sampler.py` whole; `tests/contract/test_idle_sleep.py`
whole; **every reader of `store_value` and `REQUESTS_BELOW_400_QUERY`** (`grep -rn
"store_value\|REQUESTS_BELOW_400" bin src tests` — `bin/doctor.py` included; D979).

1. **The failing tests first** (committed only with the repair, run red once and
   the output kept): in `test_usage_sampler.py`, a stub store that answers the
   request query EMPTY and the witness queries with one series each →
   `requests_counter` read **0**, absent from `unread`
   (`test_an_absent_series_with_a_witness_reads_zero`); empty request query and
   an empty `up` witness → unread with the reason
   (`test_an_absent_series_without_a_witness_is_unread`, and a second case with
   the certificate witness empty); a present series → its value
   (`test_a_present_series_is_its_value`). In `test_idle_sleep.py` (the control
   set in its cluster, `tests/contract/control_cluster.py`): a project woken
   past the window whose samples read `0, 0, 0` with no customer activity →
   ONE `project.sleep`, `origin = idle` (`test_a_woken_project_left_untouched_sleeps`).
2. **The repair**: `usage_reading.requests_below_400(project_key)` as D2832
   says (the three queries constants beside `REQUESTS_BELOW_400_QUERY`; the
   reason sentence one constant); `store_value` itself unchanged (the doctor's
   readings keep their meaning — `bin/doctor.py:949-962` is a report, §10);
   `bin/reconciler.py:1502-1505` calls the new function. The module sentence
   `usage_reading.py:9-10` amended per ADR 0289.
3. **Battery** (`~/s45/run2/battery2.py`): (m1) the witness check removed (empty
   → 0 always) → `…without_a_witness_is_unread` FAILED; (m2) only `up` checked
   → the certificate case FAILED; (m3) the reconciler back on `store_value` →
   `…with_a_witness_reads_zero` FAILED; (m4) a witness count `>= 0` → FAILED;
   control: `test_a_moved_counter_is_not_idle` passes under every mutation.
4. **Targeted, once**: `test_usage_sampler`, `test_idle_sleep`,
   `test_doctor_readings`, `test_reconciler*` (every module the grep named),
   `test_acceptance_registry`, `test_evidence_claims`. Commit, push, read CI.

**Done (2026-10-23).** Readers grepped first: `store_value` is read by
`bin/doctor.py:965` (`probe_store`, unchanged — a report) and the reconciler;
`REQUESTS_BELOW_400_QUERY` by the reconciler and one test; the old empty-reason
sentence by no test. **Red first** (`~/s45/run2/red.txt`, before any product
edit): 8 failed — `test_an_absent_series_with_a_witness_reads_zero`, the six
cases of `test_an_absent_series_without_a_witness_is_unread` (`no-edge-read`,
`no-certificate`, `edge-unanswered`, `certificate-unanswered`,
`another-project`, `zero-count`) and `test_the_witnesses_name_only_a_project_key`
— and 10 passed, two of them new: `test_a_present_series_is_its_value` (a
series, 0 included, asks for no witness; an unanswered request query keeps its
own reason) and `test_idle_sleep.py::test_a_woken_project_left_untouched_sleeps`
(a wake 20 min ago, four samples reading 0 → one `project.sleep`, origin idle;
control: 0, 0, 1, 1 → nothing) — **the control set needed no change for a read
zero**, as ADR 0289 said. The stub store answers by the decoded query, and the
tests write the three queries out literally (D673). **Repair**:
`usage_reading.requests_below_400` with `EDGE_READ_WITNESS_QUERY`,
`CERTIFICATE_WITNESS_QUERY`, `REQUESTS_UNWITNESSED`; the module sentence
amended; `bin/reconciler.py` calls it in place of `store_value`. **D2846**: the
witnesses select `project="<key>"` (an unlabelled series is no witness), the key
asserted against `naming.TRAEFIK_NAME_PATTERN`; ADR 0289 decision 1 updated.
Green: 18/18 (`~/s45/run2/green.txt`). **Battery** (`~/s45/run2/battery2.py`,
`battery2.txt`): m1 witnesses removed, m2 only `up`, m3 the reconciler back on
`store_value`, m4 `seen < 0`, m5 the edge witness without the project matcher,
m6 the key check removed — **6/6 killed, each killer FAILED (not ERROR), the
control `test_idle_sleep.py::test_a_moved_counter_is_not_idle` PASSED in every
invocation**; both files restored and `cmp`-equal. **Targeted, once**: `ruff
format` (one file) and `ruff check` clean; `test_usage_sampler`,
`test_idle_sleep`, `test_doctor_readings`, `test_reconciler_claim`,
`test_reconciler_dispatch`, `test_branch_expiry`, `test_insights_reading`,
`test_acceptance_registry`, `test_evidence_claims` **205 passed**;
`test_backups_reading_from_the_producer`, `test_admin_handoff`,
`test_control_projects`, `test_export_upload`, `test_project_retire`,
`test_restore_promotion_bound`, `test_cli_contract` **903 passed**. The new
test functions are registered at the bump (Run 8, `USE-IDLE-002`). Row D2846;
**NEXT FREE D2847, ADR 0290.** **CI**: `6252690d82cad7f9719353c3d4b557c2f84e3902`
— `contract` 39947645991 **success** (pushed after `1c7b622`'s `contract`
39944615696 success).

### Run 3 — the tokens, the fonts, the logo, the favicon, the two policies

**Read first:** ADR 0288; §1 D2813–D2816, D2820, D2825, D2826;
`services/console/serve.py` whole; `tests/contract/test_console_server.py` whole;
`tests/contract/test_site.py` whole; `site_build.py:36-90`, `:407-501`.

1. **The shared assets** (D2814): rig 45a's two `woff2` and two licences into
   `services/console/public/fonts/` (the names of D2814); `favicon.svg` (the
   brief's mark: 28 × 28 view box, `rect rx=6` 2 px `#142027` stroke no fill, two
   bars 4 × 14 `rx=1` at x 8 / 16, y 7, `#0B6B4F` and `#142027` — presentation
   attributes only) into `services/console/public/`.
2. **The console serves them**: `serve.py` content types `font/woff2`,
   `text/plain; charset=utf-8`, `image/svg+xml`; `ROUTES` + `/console/fonts/…`
   (four) and `/console/favicon.svg`; `DIRECTIVES` `font-src 'self'`.
   `index.html` and `accept.html`: `<link rel="icon" href="/console/favicon.svg"
   type="image/svg+xml">`, the inline SVG logo and wordmark in a `<header
   class="top">` before `<main>` (D2820), the footer's words (D2824).
3. **The site carries them**: `site_build.SHARED_ASSETS` copied into the build
   (`fonts/…`, `favicon.svg`) and into `digest_inputs()`;
   `CONTENT_SECURITY_POLICY` `font-src 'self'`; `base.html` gains the icon link.
4. **The token block** (D2826) at the top of both stylesheets: the brief's
   colour table, the status palette, the dark-surface values, the radii and
   spacing steps as custom properties; `@font-face` for both families
   (`font-display: swap`, `url(/fonts/…)` on the site and `url(/console/fonts/…)`
   in the console — **the only line that differs is outside the block**: the
   `@font-face` rules follow it); light only (D2825). The two files' bodies
   rewritten to the tokens and typography (the brief's type table) — the site's
   layout waits for Run 4; the console's for Run 6.
5. **The moved tests** (D2813, exactly): `test_site.py` `POLICY`;
   `test_no_third_party_asset` → *every `url()` in `site.css` is a `/fonts/`
   path the build carries; no `@import`*; `test_console_server.py`
   `ADR_0280_POLICY`, `POLICY`, `LISTED`, `test_the_image_bakes_only_its_own_files`
   (recursive). **New**: `tests/contract/test_look.py` (`UI-TOKENS-001`,
   `UI-FONTS-001`'s offline half: the sha256s from ADR 0288, the licences, the
   token block, contrast pairs computed by the WCAG formula from the parsed
   tokens, the budget, no dark scheme, `:focus-visible`);
   `test_console_server.py::test_the_fonts_are_served_as_fonts` (GET each font
   route → 200, `font/woff2`, the policy, the bytes);
   `test_site.py::test_the_build_carries_the_shared_assets` (byte-equal to the
   console's copies).
6. **Battery** (`battery3.py`): a font byte flipped → `…recorded_files` FAILED;
   one token changed in one file → `…share_one_token_block` FAILED; `#55626B` →
   `#8899A0` → contrast FAILED; `font-src 'none'` back in `serve.py` →
   `test_every_answer_carries_the_policy` FAILED; an extra `url(https://…)` →
   `…url_is_one_of_the_fonts` FAILED; a licence removed → FAILED; control:
   `test_two_builds_are_byte_equal` green throughout.
7. **Targeted, once** (the console and site lists above, `test_look`).
   `bin/build-site.py --check`. Commit, push, read CI (`contract`, then `site`:
   the live site serves the fonts — read `curl -sI
   https://agenticpostgresql.com/fonts/schibsted-grotesk.woff2` → 200,
   `content-type: font/woff2`, and the page's CSP `font-src 'self'`).

**Done (2026-10-23; CI and the live read follow the push).** Rig 45a's four
files in `services/console/public/fonts/` (sha256 equal to ADR 0288's table;
no CR byte in the licences, so `*.txt text eol=lf` leaves them byte-equal),
`favicon.svg` (312 B, presentation attributes only). `serve.py`: `FONT`,
`TEXT`, `SVG`, `FONTS_DIR`, five routes, `font-src 'self'`. `index.html` /
`accept.html`: the icon link, a static `<header class="top">` with the inline
logo and wordmark outside `#main` (D2820), footer *"Agentic Postgres, beta"*,
the accept page's title *"Accept your invitation, Agentic Postgres"* (D2824).
`site_build`: `CONSOLE_PUBLIC`, `SHARED_ASSETS` (five paths, copied by `build()`
and in `digest_inputs()`), `font-src 'self'`; `base.html` the icon link. **The
token block** written once (`~/s45/run3/tokens.css`) and placed byte-equal at
the top of both stylesheets by `compose-css.py`, the `@font-face` rules after
it; light only; bodies on the tokens and the brief's type (layout waits for
Runs 4 and 6): **site.css 4,611 B + app.css 6,263 B = 10,874 B** of 30,720.
Contrast computed for 31 pairs before the test pinned them (`contrast.py`): the
lowest `text-3` on `surface-hover` 5.30 and `accent` on `accent-tint` 5.43,
all ≥ 4.5. **Two more pins than ADR 0288 named, each a §9 stop put to the
operator**: (g) `test_the_site_names_no_host_address` decodes the BUILD
(D2847), (h) `test_no_tracked_file_uses_crlf` reads every tracked file's bytes
(D2848) — the operator chose an exact-path allowlist for both; `.gitattributes`
gains `*.woff2 binary`; ADR 0288 decision 4 gains (g) and (h). The moved tests
(a)–(e), (g), (h) and the new ones: `tests/contract/test_look.py` (8 tests,
`pytestmark` first), `test_console_server.py::test_the_fonts_are_served_as_fonts`,
`test_site.py::test_the_build_carries_the_shared_assets`. **Battery**
(`~/s45/run3/battery3.py`, `battery3.txt`, `battery3-rerun.txt`,
`battery3h.txt`): a font byte flipped, one token in one file, `text-3`
lightened in both, `font-src 'none'` back, a third-party `url()`, a licence
removed, a dark block back, an unexpected binary in the build (g), a stray file
in `fonts/` (e), a tracked stray file holding `\r` (h) — **10/10 killed, each
FAILED**. The licence mutation's first control (`test_two_builds_are_byte_equal`)
FAILED with it — the build copies the licence, so that control was reachable
(D499); re-run with `test_every_text_pair_meets_4_5` as its control: killed,
control green. Every file restored, `cmp`-equal, `git status` unchanged.
**Targeted, once** (final tree): `ruff` clean; `build-site.py --check` 23
files byte-equal; `test_look`, `test_site`, `test_console_server`,
`test_console_pages`, `test_console_scram`, `test_console_sql`,
`test_console_plane`, `test_reality_ledger`, `test_release_workflows`,
`test_acceptance_registry`, `test_evidence_claims`, `test_environment_gates`,
`test_documentation_index`, `test_repository_contract` **468 passed**. Rows
D2847–D2848; **NEXT FREE D2849, ADR 0290.** **CI**:
`850231875176ee56804f9febfed7f7dfb4d3a155` — `contract` 39950990942
**success**, `site` 39954151784 **success**. **The live read** (from WSL,
`-A agentic-postgres-proof`): `https://agenticpostgresql.com/fonts/schibsted-grotesk.woff2`
→ 200, `content-type: font/woff2`, `x-content-type-options: nosniff`, 49,112 B,
sha256 `b29bc789…` (the pinned file); `/favicon.svg` → 200 `image/svg+xml`; the
apex's policy `… connect-src 'none'; font-src 'self'; …` — Cloudflare Pages
serves the font type unprompted.

### Run 4 — the site's template, chrome and builder components

**Read first:** §1 D2817–D2824, D2831, D2843; `site_build.py` whole;
`site/templates/base.html`; `tests/contract/test_site.py` whole;
`tests/external/test_session43_console.py:139-196`, `:355-429` (what the live
proof parses); the prototypes `Main.dc.html`, `Docs.dc.html`, `Mobile.dc.html`
for layout only.

1. **The template** (`base.html`; `_layout`'s keys grow by name, each listed):
   the beta bar (`<div class="beta-bar">`, the brief's sentence and *"Release
   {VERSION}"*), the header (logo + wordmark linking `/`, `NAVIGATION`'s four
   with `aria-current` by prefix, *Console*, the invitation button), the
   `<details class="menu">` (*Menu*; the same items with descriptions — *4
   steps* (the quickstart's `##` count), *10 pages* (`DOCS_GROUPS`), *Free in
   the beta*, *43 concepts* (the Ledger), *for members* — then the button),
   `<main>`, the feedback line, the footer (four columns, the rule, *"Agentic
   Postgres {VERSION}, beta"*). **No `<p>` in the chrome** (D2818).
2. **The docs layout**: for a page under `/docs/` (and `/quickstart/`), a
   three-column body — the sidebar from `DOCS_GROUPS` (D2822; the current item
   marked; the management API address in small mono under it), the article with
   the breadcrumb (*Docs / <group>*), `h1`, the lead (front-matter
   `description`), **the page's status chips** (its `ledger:` rows,
   `STATUS_WORDS`), the body, previous/next; the *On this page* column from the
   body's `h2`s. **Heading ids de-duplicated** (`slug`, then `-2`, `-3` … — a
   build error if a page links to an id that does not exist).
3. **The components** (D2821): the container syntax and `CONTAINERS`; the
   generated blocks `@restore-example` (D2831), `@ledger-summary` (the
   heading *"{total} concepts. {beta+available} of them work today."*, the SVG
   bar, the legend — D2817), `@ledger-examples` (D2843), `@plan-summary`
   (*Active projects, Branches per project, Compute sizes, Storage* from
   `plans.PLANS`, Free and Premium), `@docs-index`; `@pricing`/`@ledger` as the
   FIRST line followed by Markdown (D2818); the ledger page's filter and chip
   spans (D2819); the pricing cells' marker class (D2818).
4. **Tests**: `tests/contract/test_site_look.py` (`UI-SITE-001`, §2) — built
   pages read by Python's `html.parser`; every existing `test_site.py` proof
   passes untouched.
5. **Battery** (`battery4.py`): a docs page dropped from `DOCS_GROUPS` →
   `…in_one_group` FAILED; a chip word typed instead of looked up → FAILED; the
   bar's widths off by one → `…sums_to_the_ledger` FAILED; a duplicate heading
   left unsuffixed → FAILED; a `style=` emitted → FAILED; the restore command's
   flag renamed → FAILED; an unknown container accepted → FAILED; control:
   `test_the_ledger_page_is_the_rows` and `test_the_pricing_page_follows_the_plans`
   green throughout (the pins of D2818/D2819).
6. **Targeted, once** (the site list). Commit, push, read CI (`site` live: the
   apex 200 and byte-equal to the build — the live proof's own check, run with
   `-k test_the_site_is_the_commits_build` from WSL, writes nothing).

**Done (2026-10-23; CI and the live read follow the push).** `site_build`:
`NAVIGATION` the four (*Quickstart, Docs, Pricing, What exists*),
`INVITATION_HREF`, `DOCS_GROUPS` (the SQL editor in *Use a project*) with
`docs_order()` and `check_groups` (a page no group holds, an entry that is no
page, or a repeat is a `SiteError`), `CONTAINERS`, `BLOCKS`, `CHIP_CLASSES` +
`chip()`, `ledger_summary`, `ledger_examples`, `plan_summary` (`PLAN_SUMMARY`'s
four keys), `restore_example` (`RESTORE_EXAMPLE`), `docs_index`, `chips_for`,
`unique_ids`, `_check_anchors`, `LOGO`; `render_markdown` gains `::: <name>`
containers (one level of nesting) and generated-block lines through a per-page
resolver (`@chips` only from the page's own `ledger:`, `@ledger-examples` only
on `/`); `@pricing`/`@ledger` are the FIRST line and Markdown may follow;
`check_page` holds that `@ledger` opens the one `"*"` page and no other.
`pricing_body`: each plan a `<section class="plan plan-<name>">`, its status
paragraph `class="plan-status"`, the fourth cell `class="enforced|shown"` (its
text unchanged), `BETA_SENTENCE` still the first `<p>`. `ledger_body`: the
filter's radios (*All* + each status present, counts in the labels), *"43
concepts"*, the chip inside the *Today* cell. The template: the beta bar (a
`<div>`, *"Release {VERSION}"*), the header (logo + wordmark to `/`, the four with
`aria-current` by prefix, *Console*, the invitation button, the `<details>`
menu with *4 steps / 10 pages / Free in the beta / 43 concepts / for members* —
every count the build's), the feedback line (D2850), the four-column footer
and *"Agentic Postgres {VERSION}, beta"*, the title *"{title}, Agentic
Postgres"* — **no `<p>` in the chrome**. The docs layout on `/quickstart/` and
`/docs/…`: the sidebar (current page marked, the management API address), the
breadcrumb, the page's own `#` heading, the lead from `description`, the
page's chips, the body, previous / next, *On this page* from the `h2`s.
`site.css` gains the chrome's and components' rules (the six `:has()` filter
rules, the chips' colours, the bar, the instrument, the containers, 1100 /
900 px): **site.css 18,543 B + app.css 6,263 B = 24,806 B** of 30,720 (Run 6
has ~5.9 KB). **The live proof's own parser** (`test_session43_console._parse`)
read the built pricing page offline: `paragraphs[0] == BETA_SENTENCE` and both
plans' section rows equal the plan table's. **Look rehearsal**
(`~/s45/run4/look.py`, the local build under its own `_headers` policy,
Chromium 153, 5 routes × 390 / 1280): `scrollWidth == innerWidth` everywhere,
no violation, no request off the origin; **D2849** (a face not used is
`unloaded`); screenshots `~/s45/run4/shots/` read — the duplicated feedback
line found there (**D2850**: the thirteen pages' copies removed,
count-asserted). New `tests/contract/test_site_look.py` (10 tests, `pytestmark`
first). **Battery** (`~/s45/run4/battery4.py`): a docs page dropped from
`DOCS_GROUPS`, a chip word typed, the bar's widths off by one, a duplicate
heading unsuffixed, a `style=` emitted, the restore flag renamed, an unknown
container accepted, the current section by exact route, previous / next
swapped, the docs count typed — **10/10 killed, each FAILED**, the controls
(`test_the_ledger_page_is_the_rows`, `test_the_pricing_page_follows_the_plans`;
for the dropped group, which breaks the build, `test_every_text_pair_meets_4_5`)
green; restored and `cmp`-equal. **Targeted, once**: `ruff` clean;
`build-site.py --check` byte-equal (23 files); `test_site_look`, `test_site`
(untouched since Run 3), `test_look`, `test_release_workflows`,
`test_documentation_index`, `test_session12_documented_path`,
`test_reality_ledger`, `test_acceptance_registry`, `test_evidence_claims`,
`test_environment_gates`, `test_repository_contract`, `test_console_server`
**471 passed**. Rows D2849–D2850; **NEXT FREE D2851, ADR 0290.**

### Run 5 — the site's pages

**Read first:** the brief's *Site pages* (`:148-175`); every page under
`site/pages/`; the five prototypes for layout.

1. **Home** (`index.md`): `::: hero` (the `#` heading of D2842, the lead,
   `::: actions` with the two links and *"Already invited? Open the console"*)
   + `@restore-example`; `::: features` with four `::: feature` blocks (the
   brief's four titles, each a paragraph from the existing pages' sentences, one
   limit line, a link to its docs page; its chips by the block's first line
   **`@chips <row> …`** — rows the page's `ledger:` already lists); `::: steps` (the four
   quickstart steps, each with its commands); `::: band` + `@ledger-summary` +
   `@ledger-examples` + the link to `/ledger/`; `@plan-summary` + the link to
   `/pricing/`; `::: band-dark` (the invitation text that exists, the two
   actions). **Copy from the existing pages; a new sentence only where the brief
   quotes it** (D2842).
2. **Quickstart**: its four `##` steps inside `::: steps` (numbered by CSS
   counters — the numbers are the list's, D2830's *real sequence*).
3. **Docs**: each page's tables keep their pipe form (styled as the ledger
   table); the *Connecting* doors as `::: doors` (two `::: feature`-styled
   panels from the existing table's facts); notes and warnings as `::: note` /
   `::: warning` where the page already says *"a sleeping project refuses
   connections"* and the like — **no new claim**. `docs/index.md` → the groups
   by `@docs-index`.
4. **Pricing**: `@pricing` then the notes *"Enforced and shown"* and *"From the
   terminal"* (D2818).
5. **What exists**: `@ledger` (the filter, the chips, the table — text
   unchanged), the closing line about `not_available` linking to
   `/docs/refusals/` (an existing sentence of `refusals.md`).
6. **Screenshots for the operator** (the look walk's offline mode, Run 7,
   does not exist yet): the Playwright image screenshots each built page at 390
   and 1280 px from a local server (the rig 45b server), saved in
   `~/s45/run5/shots/`; **the operator compares them with the prototypes**; the
   differences they ask for are made in this run, each recorded.
7. **Targeted, once** (the site list, `test_site_look`). Commit, push, read CI;
   the live site read as in Run 4.

**Done (2026-10-23; CI follows the push).** **The operator compared the
screenshots with the prototypes** (both folders, the site's 30 and the
console's 32) **and asked for no difference.** **Home** (`index.md`): `::: hero` (`::: lead`
with D2842's `#` heading and the page's existing first paragraph; `::: actions`
with *Request an invitation*, *Read the quickstart*, *"Already invited? Open the
console"*; `@restore-example`); *What every project gives you* — `::: features`,
four `::: feature` blocks with the brief's titles, `@chips` from the page's own
list (**D2851**: `monitoring`, `usage`, `query_insights` joined it), each
paragraph and limit an existing page's sentence (`connecting.md`, `branches.md`,
`backups.md`/`projects.md`, `insights-and-monitoring.md`), a link to its page;
`::: steps` (the four quickstart steps condensed from `quickstart.md`, numbered
by a CSS counter); `::: band` with `@ledger-summary`, the page's existing
*"generated from the same file the product checks itself against"*,
`@ledger-examples` and *"See every concept in What exists"* (**D2852**); *Free
during the beta* with `@plan-summary`; `::: band-dark` (*"The beta is
invite-only."* and the page's existing invitation sentences, *Email for an
invitation*, *I have an account, open the console*). **Quickstart**: the four
`##` steps inside `::: steps`, their typed numbers removed (the counter numbers
them; the menu's *4 steps* still counts the `##`s). **Docs**: *Connecting*'s
table → `::: doors` with two `::: feature` panels carrying the same facts;
`::: warning` around three existing sentences (*"A branch is not backed up…"*,
*"While a project sleeps its backups stop…"*, *"It wakes only when someone
asks…"*); `docs/index.md`'s hand list (nine pages, no SQL editor) →
`@docs-index` (ten, by group). **Pricing**: `@pricing`, then *Enforced and
shown* (`plans-and-usage.md`'s *"Storage and agent calls are shown against usage
and not enforced."*) and *From the terminal* (`apg plan list` / `show` /
`notify-me`, `cli.md`'s row), and *"The plans here are generated from the
product's own plan table."*; *Notices at 80%* waits for the bump (D2834).
**What exists**: `@ledger`, then the `not_available` line from `refusals.md`'s
row, linking to *What a refusal means*. CSS: the hero's grid areas, the action
links as buttons, the steps' counter, the home features' panel, the door
panels, inline code wrapping anywhere (found at 390 px: `/docs/`'s API address
made `scrollWidth` 429) — **site.css 20,486 B + app.css 6,263 B = 26,749 B**.
**Screenshots** (`~/s45/run5/shots/`, 15 routes × 390 / 1280, the build under its
own policy): **30 readings, no sideways scroll, no violation, no request off the
origin, no font `error`**; copied to the session scratchpad for the operator.
**Targeted, once**: `ruff` clean; `build-site.py --check` byte-equal; the site
list, `test_site_look`, `test_documentation_index`,
`test_session12_documented_path` and the rest of Run 4's list **471 passed**.
Rows D2851–D2852; **NEXT FREE D2853, ADR 0290.**

### Run 6 — the console's look

**Read first:** §1 D2827–D2829; `services/console/public/app.js` whole;
`app.css`; `tests/external/browser/console_walk.py` and `sql_walk.py` (the
selectors of §0); `tests/contract/test_console_*.py`.

1. **The shell**: `frame()` builds `header.bar` (the *Overview* link, the user,
   *Sign out*), then `div.layout` holding the navs (`projectNav`/`orgNav`
   elements are passed in the body today — `frame` moves any `NAV` child into
   the layout's first column) and `div.content` (`h1`, the rest). The project
   nav in the brief's order with *SQL* after *Connect* (D2828's mapping); the
   org nav *Plan, Usage, Members and keys* (*Notifications* returns at the bump,
   D2834); `link()` sets `ariaCurrent` (D2828). Below 900 px the nav column
   collapses by CSS into a horizontal scroller — **a `<details>` menu built by
   `app.js` is not added** (a new element per view, more script than a hook;
   §10).
2. **The patterns** (D2827, D2828): `STATE_CHIPS` and the three state spans;
   `once()`'s `div.once` styled (amber 2 px `#E3B65A`, white, the *Shown once*
   sentence its heading by CSS — no element added; `code.secret` order
   untouched); `p.refusal` as the warning callout; `table(columns, rows,
   numeric)` with `className: "num"` on those columns' cells (Insights' numbers,
   Usage's figures); forms by CSS; the sign-in views (`signInView`,
   `signInWithNextCode`, `enrolFactor`, `createAccount`, `joinAsSignedIn`,
   `acceptPage`) wrap their content in `div.panel-narrow` (the QR on white with
   16 px padding by CSS); the editor by structural selectors only (D2829).
3. **Tests**: `tests/contract/test_console_look.py` (`UI-CONSOLE-001`, §2) —
   `STATE_CHIPS` parsed from `app.js` against `control_states.STATES`; the two
   chip classes' colours from `app.css`; the logo in the HTML, none in `app.js`;
   no `style=`; **`test_the_drivers_anchors_are_unchanged`**: every literal the
   two drivers select by (the §0 list, read from the driver files) still occurs
   in `app.js`/`index.html` the number of times it did at `702671f` (recorded in
   the test as a table).
4. **The rehearsals** (D2829): `sql_walk.py --rehearse` (Session 44's
   `~/s44/run6/rehearse-sql.sh`, the console image built from the tree) → every
   step ok; the console walk's rehearsal (`~/s43/run8/rehearse.sh`, derived to
   `~/s45/run6/`) → walk exit 0, `--leak` 6, `--dry` 0. Screenshots of every
   view at 390 and 1280 px to `~/s45/run6/shots/` for the operator.
5. **Battery** (`battery6.py`): a state dropped from `STATE_CHIPS` → FAILED;
   `state-unknown` given `state-ready`'s colours → FAILED; a `code.secret`
   added to the enrol view → `…anchors_are_unchanged` FAILED; a `style=` in
   `index.html` → FAILED; control: `test_console_scram::test_every_script_parses`
   green.
6. **Targeted, once** (the console list, `test_console_look`). Commit, push,
   read CI.

**Done (2026-10-23; CI follows the push).** `app.js`, through `h` only:
`link()` marks the current view `ariaCurrent: "page"`; `STATE_CHIPS` (the nine
`control_states.STATES` → `state-ready` / `-busy` / `-asleep` / `-gone` /
`-unknown`) and `stateChip()`, which reads a value the table does not hold, or
an object's own property name (`Object.hasOwn`), as `state-unknown`; the three
state places render the chip with the state word unchanged (the overview's
`·` gone, D2824); `table(columns, rows, numeric)` (Insights' five figures,
Usage's window maximum right-aligned); `frame()` moves a view's `NAV` into
`div.side` and the rest into `div.content` inside `div.layout`; `narrow()` draws
the six sign-in, enrolment and invitation views in `div.panel-narrow`.
`sql.js`, `pg.js`, `scram.js`, `api.js` untouched. `app.css`: the layout, the
nav column with the current tab, the chips, the shown-once panel's amber
border, refusals as the warning callout, `.num`, the narrow panel and the QR's
padding, the editor by structural selectors, below 900 px the nav a
horizontal scroller and every table its own scroller, and **D2853** (`[hidden]`
restored). `site.css`'s three button blocks merged into one selector list.
**app.css 8,642 B + site.css 20,251 B = 28,893 B** of 30,720. **Driver anchors**
(`~/s45/run6/anchors.py`): all 25 literals the two drivers select by occur in
`app.js` as often as at `702671f`; each page keeps one `#main`. **Rehearsals**
(`~/s45/run6/rehearse.sh`, `rehearse-sql.sh`, derived from Sessions 43/44's,
the console image built from the tree; the console walk's launcher gained
`APG_CONSOLE_SQL_RELAY_ORIGIN`, which the console has required since 1.22.0):
**console walk exit 0, all eleven steps ok, `--leak` 6, `--dry` 0; editor walk
exit 0, every step ok (cancel `57014` in 1.07 s, the cap at 1,000 rows), `--leak`
6, `--dry` 0** — no driver changed. **Views rig** (`~/s45/run6/views.py`: the
built image, the API by fixtures shaped from what `app.js` reads, 16 views × 390
/ 1280): the first pass found six views scrolling sideways at 390 px (wide
tables) — fixed; then **32 readings, no sideways scroll, no violation, no
request off the origin**, the current tab marked on every project and
organisation view; screenshots in `~/s45/run6/shots/` and the scratchpad —
**the operator compared them with the prototypes and asked for no difference**
(2026-10-23). New `tests/contract/test_console_look.py` (6 tests, `pytestmark`
first). **Battery** (`~/s45/run6/battery6.py`): a state dropped from
`STATE_CHIPS`, `state-unknown` given `state-ready`'s colours, a `code.secret`
added to the enrol view, a `style=` in `index.html`, the own-property guard
removed, the logo built by a script — **6/6 killed, each FAILED**, the control
`test_console_scram.py::test_every_script_parses` green; restored, `cmp`-equal.
**Targeted, once**: `ruff` clean; the console list, `test_console_look`,
`test_console_pg`, `test_look`, `test_site`, `test_site_look`, the registry,
claims, environment-gates and repository guards **443 passed**
(`test_console_look` re-run alone after `ruff`'s import fix: 6 passed). Row
D2853; **NEXT FREE D2854, ADR 0290.**

### Run 7 — the trip's instruments, written and rehearsed offline

**Read first:** D2830, D2833, D2837, D2838; Session 44's Run 6 text and
**Done.** (`docs/plans/session-44-implementation-plan.md:1235-1330`) and rows
D2786–D2790; `~/s44/run6/` (every instrument); `~/s44/run8/NOTES.md`;
`tests/external/browser/console_walk.py` whole.

1. **The look driver** `tests/external/browser/site_look.py` (the console
   walk's shape): for each site route (read from `site_build.pages()`, never
   typed) and the console's `/console/` (signed out) at 390 × 844 and 1280 ×
   800: wait for `document.fonts.ready`; record `scrollWidth`/`innerWidth`,
   every request URL's origin (Playwright's `page.on("request")`), each family's
   status, the focus outline after one Tab, and a screenshot path; the site's
   `apg-site-digest` and the console's `env.json`-free state. **One record**
   (JSON, 0600; no secret is held — none is used). Modes: live, `--rehearse`
   (a local server of `bin/build-site.py --out` and the console image),
   `--dry` (no record).
2. **The trip scripts** in `~/s45/run7/`, derived from `~/s44/run6/` by `s45-derive.py` (named substitutions, the
   counts and the diffs read — D2790) and `s45-post-derive.py`: `s45-window.py`,
   `s45-after.sh` (+ the console's font route and favicon at R2d),
   `s45-after-reboot.sh`, `s45-units.sh`, `s45-walk.py/.sh` (W0′/W1′),
   `s45-sql.sh` (E0/E1), **`s45-look.sh`** (L0/L1: the Playwright image, the
   checkout read-only), `s45-lifecycle.py` (**D2833's change**: after the last
   recreation it issues no request to the slot's routes, counts its own, and
   records the idle window's samples; **its `--resume*` flags are removed** —
   D2798; a dead run is §9's stop), `s45-branches.py`, `s45-hostyaml.py` (**its
   inserted comment read — D2727, D2804**), `s45-dns.sh`, `s45-free.sh`,
   `s45-r2shape.py`, `s45-probe-*.sh`, `s45-v1.sh`, `s45-x0.sh`, `s45-sweep.sh` +
   `s45-launch.sh`, `s45-external.sh` (`--look-record-file`; **its
   `--offline-input` is the CI artifact of the DEPLOYED SHA**, D2804; its merge
   echo counts read from the tuples). **The detached launchers** (`life-start.sh`,
   `br-start.sh`, `br-delete.sh`, `ext-start.sh`) in Session 44's D2796 form.
3. **The idle proof** `tests/external/test_session45_idle.py` (§2's
   `USE-LIVE-006`; reads the lifecycle record by the existing gate) and **the
   look proof** `tests/external/test_session45_look.py` (`UI-LIVE-001`; reads
   `APG_LOOK_RECORD_FILE`) — both **PARKED** in `~/s45/run7/park/` with the
   roster entry (D2715, D2787); `--setup-plan` with every variable set, and
   `--collect-only`, run here.
4. **The widening** (D2714): the nine session pins of §0 gain 45 (`widen.py`,
   each anchor once, a miss fatal); **no `source_commit` check touched**.
5. **Rehearsed offline**: `site_look.py --rehearse` (every page ok; a planted
   foreign request in a rehearsal page → the record names it and the proof
   would fail); `s45-lifecycle.py --help`; `s45-walk.py --check`.
6. **Targeted, once**: `test_environment_gates`, the sweep-selector guard,
   `test_acceptance_registry`, `test_repository_contract`, the widened modules'
   `--collect-only`. Commit (the driver, the widening), push, read CI.

**Done (2026-10-23; CI follows the push).** **The look driver**
`tests/external/browser/site_look.py` (never collected): the site's routes from
`site/pages` by `route_of`'s rule, the console's `/console/`, 390 × 844 and 1280
× 800 — `scrollWidth`/`innerWidth`, every ATTEMPTED request, each family's
status, the CSP violations, the first Tab's ring, the page's digest, a
screenshot; one 0600 record, no secret held; `--rehearse`, `--plant-foreign`
(rehearsal only), `--dry`; exit 0 / 2 / 4. **Rehearsed** (`~/s45/run7/
rehearse-look.sh`: the build under its own `_headers` policy — read back from the
Docker network, `font-src 'self'` — and the console image built from the tree):
**32 readings, no problem** (no sideways scroll, nothing off the origin, no
violation, no font `error`, the ring `solid 2px rgb(31, 79, 163)` and
`:focus-visible` everywhere), one digest; JetBrains Mono `loaded` on every page
(each now sets code); the control `--plant-foreign` named
`https://third-party.invalid/planted.png` on `/` at both widths; `--dry` wrote
nothing. **The trip scripts** (`~/s45/run7/`): `s45-derive.py` — 20 of 20, 65
substitutions, no Session 44 name in a body (the bare-`44` grep after found only
lineage headers) — and `s45-post-derive.py` (**D2856**): the lifecycle **without
any `--resume*` flag** (argparse refuses each; the paths unreachable behind
defaults) and with **D2833's quiet** — every slot probe paused and the host probe
stopped BEFORE the export, `status()` counting any request to the slot's routes
until the idle sleep is requested, the idle reading gaining `quiet` and the hour's
`window_usage`; `s45-after.sh` reading the console's typefaces and favicon at R2d
(and the relay's lineage reverted); `s45-external.sh` `--look-record-file` and
the counts 338 / 160; `s45-x0.sh` excluding `session45_look` and
`session45_idle`. New: **`s45-look.sh`** (L0/L1; refuses a checkout not at the
control project's commit) and the four launchers in D2796's form
(`life-start.sh`, `br-start.sh`, `br-delete.sh`, `ext-start.sh`);
`~/s45/host-address` copied (never typed). **The parked proofs**
(`~/s45/run7/park/`): `test_session45_look.py` (`UI-LIVE-001`, 6 tests) and
`test_session45_idle.py` (`USE-LIVE-006`, 4 tests; **D2854**: the store-side
absence is Sheet IR3's root read at the sitting; **D2855**: the window and two
intervals) with `roster.py` (`APG_LOOK_RECORD_FILE`) — with the roster entry
applied temporarily, `--setup-plan` with every variable set **exit 0**, 10
collected; `tests/conftest.py` restored `cmp`-equal. **The widening** (D2714):
the nine pins gain 45 (`widen.py`, each anchor once; no `source_commit` count
moved); two lines past 100 columns name their tuple first (`widen-wrap.py`).
**Rehearsed**: `s45-lifecycle.py --help` (and `--resume` / `--resume-at-k2`
refused); `s45-walk.sh --check` — the pinned image pulled, Playwright 1.63.0
installed hash-locked into `~/s45/walk-home/pw`, the preconditions refused
(exit 92: the control project is at `224b660`, not this checkout — as it should
be before the sitting; the temporary control copy moved aside). **Targeted,
once**: `test_environment_gates`, `test_acceptance_registry` (the
sweep-selector guard), `test_repository_contract`, `test_deployment_suite_shape`
**279 passed**; the widened modules **77 collected** (the two wrapped ones
re-collected: 13); `ruff` clean on the tree. Rows D2854–D2856 and Sheet IR3;
**NEXT FREE D2857, ADR 0290.**

### Run 8 — the bump, the registry, the gate, `notifications` to `trial`

**Read first:** §2 whole; `src/agentic_postgres/__init__.py:1330-1395`; Session
44's Run 7 (`:1332-1447`) — the list to copy; `bin/session-44-check.sh:1-240`;
`tests/contract/test_session_forty_four_gate_modes.py:40-120`; `git show 4d6f892
-- services/console site`.

1. **The constant and the version**: `CURRENT_SESSION = 45` with Session 45's
   paragraph (the D690 shape; the class priced in ADR 0162's form in the LAST
   paragraph — D2794); `VERSION` `1.23.0`; `README.md:7`; every `--session 44`
   literal on the documented path moved and counted per file (D678/D1484); the
   operator and upgrade guides' release lines and the upgrade table's 1.23.0
   row (*"no database restart; the console recreated on the control project;
   restart the reconciler after the checkout moves"*). **The price** read by
   D1624's rig against the deployed `224b660` (Session 44's `upgrade44.sh`
   shape) and recorded.
2. **The registry**: §2's seven requirements, node ids from `pytest
   --collect-only -q`; the regex gains `UI`; `CLAIMS` and `OFFLINE_CLAIMS`
   blocks; `CLAIM_INTRODUCED_IN`; `APG_LOOK_RECORD_FILE` in the roster; **the
   two parked modules unparked**.
3. **The gate**: `bin/session-45-check.sh` from 44's by `sed` of the session
   numbers into a copy, then the header and usage block rewritten whole
   (D1488), then `--look-record-file` (external only) — **`diff
   bin/session-44-check.sh bin/session-45-check.sh` read whole; every hunk named
   in the `**Done.**`**; `SHELL_COMMANDS` gains it;
   `test_session_forty_five_gate_modes.py` from 44's, its claims the seven, plus
   `test_the_gate_exports_the_look_record_in_the_external_mode_alone`.
4. **The Ledger** (D2834, D2835): `notifications` → `trial` (its
   `customer_text` with *being verified*; `today` amended; `controls` the CLI
   verb and the console view); the schema's maximum → 46; **the console's view,
   tab, route and `pages.json` entry restored** (the inverse of `4d6f892`,
   count-asserted, styled as Run 6's tables); **the site's three mentions
   restored** and *"Notices at 80%"* on Pricing with `notifications` in its
   `ledger:`; the `console` row's text lists notifications again;
   `bin/render-reality-ledger.py --write`.
5. **The threat row**: item 27 into the table as `THR-UI-FONT` with
   `UI-FONTS-001`.
6. **The derived documents** (CLAUDE.md §5's list): `render-acceptance-matrix.py
   --write`, `render-config.py --bounds-doc --write`, `bin/app-contract.sh
   --check`, `bin/mcp-contract.sh check`, `bin/apg.sh generate --check --project
   project.example.yaml`, `render-mcp-catalog.py --write`,
   `render-evaluation-report.py --write`.
7. **Battery** (`battery8.py`): the gate's literal; the record's export; the row
   left `planned` with its view restored (→ the page guards FAILED); `UI` out of
   the regex; the threat row's test missing; an offline claim undeclared; the
   roster entry dropped; the schema maximum back to 45 with a row at 46 — each
   FAILED, the control passing, restored.
8. **The gates, in shards, once** (D2554, D2839; `~/s45/run8/` from
   `~/s44/run7/`'s by diff; `TMPDIR=~/s45/tmp`; each shard `timeout 570` in the
   foreground; the JUnit merged; the total checked against the collected
   count): `bin/session-01-check.sh` and `bin/session-45-check.sh --mode
   offline`. Commit **before** the gates, push after both pass, read CI. Then a
   documentation commit recording the gates (no CI read).

**Done.** — 2026-10-23, commit `4f4b207` (scripts `~/s45/run8/`). **The
constant and the version**: `CURRENT_SESSION = 45` with its paragraph (the class
priced in ADR 0162's words in the last paragraph); `VERSION` `1.23.0`;
`README.md:7`; **17** `--session 44` literals moved across five documents, counted
per file; the guides' release lines and the upgrade table's 1.23.0 row. **The
price** (D1624's rig, `upgrade45.sh`, against the deployed `224b660`): `bump`
**minor**, `requires` **patch**, `verdict` **ok**, `changes` `[]`, one leaf
(`template_version`) -- 1.23.0 is proposed above that floor. **The registry**:
**eight** requirements, not §2's seven (**D2857**: `USE-LIVE-007`, the
re-earning's own claim `notifications_reearned_live`, because ADR 0261 admits only
this session's claims on a `trial` row and a reachable row needs some -- the
operator's choice): `UI-TOKENS-001`, `UI-FONTS-001`, `UI-SITE-001`,
`UI-CONSOLE-001`, `USE-IDLE-002`, `UI-LIVE-001`, `USE-LIVE-006`, `USE-LIVE-007`,
node ids from the tree's collection; the regex gains `UI`; **432 requirements;
`CLAIMS` 339, `OFFLINE_CLAIMS` 160** (§7's prediction of 338 moves to **339** by
D2857); `CLAIM_INTRODUCED_IN` at 45; `APG_LOOK_RECORD_FILE` in the roster; the two
parked modules unparked. **The gate**: `bin/session-45-check.sh` derived from
44's -- `diff` read whole, **32 hunks**: the session numbers, the header and
usage block rewritten (D1488), one flag `--look-record-file` (external only), the
synopsis' missing continuation added; `test_session_forty_five_gate_modes.py`
with the claim table and the look-record test; `SHELL_COMMANDS`. **The Ledger**:
`notifications` -> `trial` naming `notifications_reearned_live` (controls: the
GET route, `bin/notifications.sh list`, `/console/`; since/target 45); the
console's view, tab, route and `pages.json` entry and the site's mentions
restored (the inverse of `4d6f892`, count-asserted); *"Notices at 80%"* on
Pricing; the console row lists notifications again; the schema's
`target_session` maximum 46. **The threat table** gains `THR-UI-FONT`
(`UI-FONTS-001`). Derived documents regenerated, each `current` after.
**Battery 8/8** (`battery8.py`), each FAILED (no ERROR) with its control green,
restored `cmp`-identical (7 files), unmutated 10 passed: the gate's literal; the
record's export dropped; the row left `planned` with its view restored; `UI` out
of the regex; a threat row's test missing; an offline claim undeclared; the
roster entry dropped; the schema maximum back to 45 with a row at 46.
**Targeted, once**: **1,108 + 439 passed**. **The gates, in shards, once**, on the
committed `4f4b207`, each shard `timeout 570` in the foreground,
`TMPDIR=~/s45/tmp`: **`bin/session-01-check.sh` PASSED** -- steps 1-7 passed, 12
shards (457, 756, 1,328, 112, 49, 69, 886, 539, 1,088, 1,338, 1,400, 418), merged
**8,443 = collected by the selection**, 0 failures, 0 errors, **3 skipped**, step 8
exit 0; **`bin/session-45-check.sh --mode offline` PASSED** -- steps 1-7 and 8-8c
passed, 13 shards (the planner's budget 330 s, D2839; the longest 233 s), merged
**8,452 = collected**, 0 failures, 0 errors, **3 skipped**, step 9 **160 of 160
offline claims passed** (`evidence/session-45-offline.json`, `checkout_commit`
`4f4b207`, `source_commit` null as for every offline half since Session 22).
**Pushed**; CI green on `4f4b2070f4cc67c5a1ea085f71eba35b784b5f0b`: **contract
39974644732, site 39978429705** (the site now runs ahead of the deployed 1.22.0
with the visual pass and the notifications mentions). **NEXT FREE D2858, ADR
0290.**

### Run 9 — the sitting: the release, the dry runs, the re-earning, the walks, the sweep, the tag, the publish

**Read first:** this plan's appendix (every sheet) and §7; Session 44's Run 8
(`:1449-1562`) and rows D2795–D2804 (*what went wrong*, D977);
`~/s44/run8/NOTES.md`. **Before the first sheet**: the checkout on the host
moved to the Run 8 commit by bundle (`git bundle` + `scp` to
`/tmp/apg-<sha>.bundle`, `git fetch`, `git rev-parse FETCH_HEAD` confirmed, `git
checkout`), `uv sync`, the renders of the four projects (`--render-only` as
`op`), `pytest --setup-plan` of the host modules with the variables set; the
Playwright image present.

1. **R1** (the price) → **R2a** beta-dev, **R2b** alpha-dev, **R2c**
   `slot3-prod` by `slot.sh redeploy`, **R2d** control-prod — each with
   `s45-window.py`, each read by `s45-after.sh` before the next sheet (D1510);
   **no database restarts**. After R2d: the console 200 with `font-src 'self'`,
   `/console/fonts/schibsted-grotesk.woff2` 200 `font/woff2`, the relay healthy.
   **RC1** (the reconciler restarted on the new checkout — D2805's repair live).
2. **A1**, **RA** (after the last deploy, D2494), **K1**.
3. **V1**, **X0** (the Session 45 modules excluded), **W0′** (`s45-walk.sh
   --dry`), **E0** (`s45-sql.sh --dry`), **L0** (`s45-look.sh --dry`). **If any
   fails: repair, move the commit, redeploy all four.**
4. **W1′** (the console walk; the creds replaced, `.before-s45` kept), **E1**
   (the editor walk).
5. **The re-earning** (D2748, D2837): **H1**, the agent's DNS (three grey A
   records `slot9`, `pool.slot9`, `direct.slot9`) and R2 buckets
   (`apg-slot9-prod`, `apg-slot9-prod-backup`, EEUR) through the Cloudflare API,
   **SL1** (the operator's B2 bucket + key, R2 tokens, the Infisical secrets —
   `bootstrap-providers --plan` names them), **SL1b**, **SL2**, **SL3**,
   **RC1**; **the lifecycle in ONE attempt, launched detached from the start**
   (`life-start.sh`; org `lifecycle-s45`; **K2** at its pause, run only when the
   instrument asks — D2803); the branches on `slot3-prod` (`br-start.sh`,
   detached, after E1); **A1′**; **B1** (the reboot; `s45-after-reboot.sh`
   BEFORE any sweep; `s45-branches.py --after-reboot`; the relay healthy by
   itself).
6. **E0 again** (D2838) and **L1** (the look walk — the record) after B1.
7. **S1** — the one sweep; **then the branch `--delete-only`** (D2647); **then
   the external half** from WSL (`s45-external.sh` with the lifecycle, branch,
   console, editor and look records); then **the merge** with the CI artifact's
   offline half for the deployed SHA. **Exit 5 for `documented_path` only**
   (§7).
8. **The tag** from the workstation (D2041): `git tag -a 1.23.0 <sha> -F
   msg.txt`, `git push origin 1.23.0`; `publish-cli` read; PyPI `info.version`
   `1.23.0`; `apg --version` → `apg 1.23.0` in a clean `python:3.12-slim`.
9. **SL4** — `slot9-prod`'s identity revoked after the tag; **RC1** — the
   reconciler active after the last sheet that stopped it (D2178).
10. **The operator's side-by-side** (D2830): L1's screenshots beside the five
    prototypes; the operator's verdict recorded verbatim in the **Done.**

**Done.** — 2026-10-23/24, **deployed, swept and tagged on `4f4b207`** (D1425;
the raw record `~/s45/run9/NOTES.md`, scripts `~/s45/run7/` + `~/s45/run9/`).
**The move**: a bundle `224b660..4f4b207` (FETCH_HEAD confirmed), the host
checkout detached at `4f4b207`, clean, no dependency file moved; renders ×5 exit
0. **R1** minor / requires patch / changes `[]` on all three. **R2a-d** exit 0
each with **no database restart** (D2836): rest **never** down, auth down 8.2,
10.3, 8.8, 8.7 s; the console recreated, down 8.0 s; the relay untouched. The
console's policy `font-src 'self'`, both typefaces 200 `font/woff2` (49,112 /
29,232 B), the favicon 200; RC1. **A1** registry agrees ×4; **RA** the declared
manifest admitted (0), the injected one refused (12); **K1**
`kit-2026-10-23-s45` (sha equal). **V1** 412 passed / 1 failed
(`documented_path`) / 8 skipped in 1:09:29. **X0** 40 passed / 44 skipped.
**W0′** 9/9; **E0** exit 0; **L0 exit 4** -- **D2858** (the driver waited on a
network idle the console's unread 401 body never ends; the operator: fix the
driver; `adc35b7` test-only, CI green, L0 then exit 0, 32 pages). **W1′** 11/11
(customer_app rotated, link to connection string 26.1 s); **E1** exit 0
(SELECT 1 median 224.0 ms vs psql 160.2; cancel 57014 1.77 s). **The
re-earning (D2837)**: H1 (the inserted comment corrected first), three grey A
records and two EEUR buckets by the agent through the Cloudflare API, the
operator's providers, SL1b all yes, SL2 (29 files), SL3 ready, RC1; **the
lifecycle in ONE attempt, detached** (19:52 → 21:01Z, exit 0): create 1,708.4
s, wake first answer 19.2 s, resizes 304 / 840 admitted of 4,801 safe, the
export read, **the idle sleep requested by the reconciler** (origin `idle`,
20:57:48, 1,213 s after the export's finish), notifications 14 (each operation
once), deleted, the second creation refused `no_slot`; **IR3** found the request
series present (**D2859**: the absent-as-0 branch stays proved offline). The
neighbours lost nothing (4,216.7 s, 0 down). **The branches** on slot3-prod
(21:03 → 22:15Z, exit 0): `tmp` expired by itself 253.3 s after `expires_at`;
`dev` at T1 (1,047.1 s), migrated on dev only; a second branch refused
`branch_limit_reached`; reset (1,016.2 s), the old password refused. **A1′**
agrees ×4 + slot1-9 `agrees (deleted)`. **B1** booted 04:47:12Z: **all seven
units started by the boot**, NRestarts 0, all active by boot+97 s; 50 healthy
containers; the relay and `dev` back by themselves (**D2861**: the first read
came before its waiter was on the host). **E0 again** exit 0 and **L1** exit 0
(32 pages, 15 routes, the record `~/s45/look/record.json`), both from `6783f06`
(past `4f4b207` by `tests/` and `docs/` only). **S1, the one sweep** (launched
detached by `s45-launch.sh`, 04:56 → 05:34Z): suite **432 passed / 1 failed in
34:11**; host **144 / 1** (`documented_path`); `sql_relay_host`,
`console_live_host`, `branch_host_live` passed -- no second sweep. **The branch
deleted** (exit 0, both names refuse). **The external half** from `6783f06`
failed three idle proofs on proof defects -- **D2860** (the operator: repair,
re-run; `d2e9c40` test-only, battery live 4/4, CI contract 40069691208 success);
**re-run from `d2e9c40`: 141 passed / 0 failed / 7 skipped, external 34 / 0**
(the first run kept in `~/s45/run9/external-1/`). **The merge** with `4f4b207`'s
CI half (contract 39974644732, 160 / 160): **339 claims, 338 passed, 1 failed --
`documented_path`** (D1935); `notifications_live` and
`notifications_retrial_live` **re-earned**; `idle_after_wake_live`,
`ui_look_live`, `sql_relay_live`, `site_live` passed; `evidence/session-45.json`.
**The tag** `1.23.0` (object `8d880308`) on `4f4b207`, pushed 06:45Z;
**publish-cli 40071462285 success**; PyPI `info.version` 1.23.0; `apg --version`
→ `apg 1.23.0` in a clean `python:3.12-slim` (the first install ~15 s before the
simple index caught up). **SL4**: slot9-prod's identity `37de262b` revoked, the
credential shredded, no `slot9-prod` under `projects/`; **RC1** the reconciler
active. **The operator's side-by-side** (D2830), L1's 32 screenshots beside the
five prototypes: *"I checked them, they all look right to me."* (The wordmark's
thin outline in the pricing and console shots was pointed out; the verdict above
stands.) **NEXT FREE D2862, ADR 0290.**

### Run 10 — the close

1. **The Ledger**: `notifications` → `beta` if `notifications_live` and
   `notifications_retrial_live` passed in `evidence/session-45.json`, else
   `planned` with its views removed again (D2834); **no row `trial` at the
   close** (ADR 0261).
2. **The envelope**: `capacity.ENVELOPE` gains a Session 45 section — the
   fonts' bytes (each), the two stylesheets' bytes, the release windows (no
   database restart), the seventh re-earning's numbers (create, wake, resizes,
   export, **the idle sleep after the wake with no request** — D2805's
   repaired number), the look walk's numbers (FCP if recorded, the pages
   walked); `UNMEASURED` loses nothing it did not measure.
3. **The documents**: `docs/scope-closure.md` §38 (*What Session 45 closed, what
   it left, and what Session 46 inherits*) in §37's shape; the stage plan's
   Status block re-read and rewritten; this plan's Status line;
   `docs/operator-guide.md`'s 1.23.0 notes (the fonts, *"restart the reconciler
   after the checkout moves"*).
4. **The handoff** (outside the repository): the launch folder's `CLAUDE.md` §2
   rows (SESSION 45, RELEASE, EVIDENCE, CURRENT_SESSION, HOST — `slot9-prod`
   consumed, **Session 46's walk needs `slot10-prod`**) — copied to the
   scratchpad first; the project memory's state file.
5. Targeted: `test_reality_ledger`, `test_evidence_claims`,
   `test_documentation_index`, the envelope's test, `test_site`,
   `test_console_pages`. `bin/session-01-check.sh` once (generated artefacts
   moved). Commit, push, read CI (`contract` and `site`).

**Done.** — 2026-10-24 (scripts `~/s45/run10/`). **The Ledger** from the
TAGGED evidence (`evidence/session-45.json`, 338 / 339, 1.23.0 on `4f4b207`):
`notifications_reearned_live`, `notifications_live` and
`notifications_retrial_live` passed, so **`notifications` → `beta`** naming all
three, its customer text without *"Being verified"*, its console view kept (it
shipped in 1.23.0); the header's Session 45 paragraph; **no row `trial`**;
`docs/reality-ledger.md` regenerated. **The envelope**: `capacity.ENVELOPE`
gains a Session 45 section of eight rows -- the typefaces' and stylesheets'
bytes (49,112 / 29,232 B; 20,251 + 8,642 = 28,893 B of 30,720), the release with
no database restart, the seventh re-earning, the idle sleep after a wake (with
D2859's note), the editor against psql, the look walk, the branches and the
reboot, the suites; `UNMEASURED` unchanged (nothing in it was measured);
`docs/capacity-envelope.md` regenerated. **The documents**:
`docs/scope-closure.md` **§38**; the stage plan's Status block re-read and
rewritten (8 count-asserted edits: 45 closed, 46 next with `slot10-prod`,
CURRENT_SESSION 45, 289 ADRs, 432 requirements, 339 / 160 claims, next free
D2862); `docs/operator-guide.md`'s release row (1.23.0 / 45) and **§25** (the
typefaces, *"restart the reconciler after the checkout moves"*, ADR 0289's
reading); this plan's Status COMPLETE. **Targeted, once**: `test_reality_ledger`,
`test_evidence_claims`, `test_documentation_index`, `test_capacity_envelope`,
`test_site`, `test_console_pages`, `test_session12_documented_path` -- **169
passed**; ruff clean; both renders current.

---

## 7. Evidence and claims

**Expected at the merge** (Run 9): **338 claims** (160 offline). **`failed` 1:
`documented_path`** (D1935). Everything else **passed** — **`notifications_live`
and `notifications_retrial_live` included** (one attempt's record, D2798),
`idle_after_wake_live` (D2805 repaired), `ui_look_live`, and every Session 38–44
lifecycle, branch, console and editor proof re-earned at 1.23.0 on `slot9-prod`,
`slot3-prod`, W1′ and E1. **Exit 5 for `documented_path` and no other reason.**
Predictions, each moved only by the evidence.

**The three modes.** Offline: CI's artifact for the deployed SHA (160 claims).
Host: S1 with Session 44's flags renamed (`--lifecycle-record-file` the Session
45 record, `--live-slot-outputs` `slot9-prod`'s K2 copy). External: from WSL
with `--control-outputs`, `--control-probe-file`, `--lifecycle-record-file`,
`--customer-credential-dir` (the creds directory W1′ updated),
`--console-record-file` (W1′'s), `--sql-editor-record-file` (E1's) and
`--look-record-file` (L1's). **The Session 45 customer proofs reach only the
site's origins, the console's origin and the control route, and open no SSH.**
**Deploy every project fully, THEN the dry runs, THEN W1′ and E1, THEN the
re-earning and B1, THEN E0 again and L1, THEN sweep, THEN external — every half
at one commit; THEN the tag; THEN the publish.**

**What is not in the evidence, by construction**: the PyPI install (the tag
publishes after the merge); the operator's side-by-side judgement (D2830);
the site's deployment of the tagged commit (the `site` workflow runs on the push
to `main`, before the tag). All three are recorded in Run 9's `**Done.**`.

---

## 8. Security invariants this session touches

| Invariant | How this session keeps it |
|---|---|
| **No third-party byte on the site or in the console** (D2596) | The fonts are committed files served from our origins; `font-src 'self'`, never a host; `test_no_third_party_asset` and `test_every_asset_is_our_own_file` unchanged in substance; the look walk records every request's origin live |
| **The console's policy has no `'unsafe-inline'`; the site's neither** | Every SVG by presentation attributes; a guard refuses `style=` in any built page and in the console's HTML (D2820) |
| **No markup built from a value** (`test_no_markup_is_built_from_a_value`) | The console's changes go through `h`; no `innerHTML`; the logo is static HTML |
| **A page claims no more than the Ledger** (ADR 0283) | Chips, counts, examples and the bar generated from the Ledger; prose stays Markdown under `check_page`; `notifications` shown only while reachable (D2834) |
| **A report may not substitute an answer for a failure to determine one** (ADR 0195) | D2805's zero only with a witness; *unknown* state never green (D2827); readings keep *not read* |
| **The decision that fails closed stays closed** (ADR 0276) | The SQL is unchanged; a missing witness keeps a project awake |
| **The connection budget, the doors, the relay** | Untouched |
| **The deploy, the sweep and the tag land on one commit** (D1425) | Run 9's order |

---

## 9. Stop conditions

Stop and ask the operator, without improvising, when:

- **rig 45a**: a family's `METADATA.pb` names a licence other than OFL, the
  subset loses the `wght` axis, or a needed glyph is missing;
- **rig 45b**: Chromium does not load a same-origin `woff2` under `font-src
  'self'`, or reports a violation for an SVG with presentation attributes only;
- **Sheet IR2**: either witness is absent on an awake project's store (D2832);
- a design here would need `'unsafe-inline'`, a `data:` image on the site, a
  new console script, a change to `sql.js`/`pg.js`/`scram.js`/`api.js`, a new
  console route beyond D2814's five, a new endpoint, or a sentence the Ledger
  does not hold;
- **a test outside D2813's list would have to move**, or a walk driver would
  need a product text changed to keep passing (D2829);
- `upgrade plan` prices 1.23.0 at `major`, or for a reason this plan did not
  name; **a deploy restarts a database**;
- a deploy's window on any project exceeds 5 minutes, or a project's routes do
  not return after its R2 sheet;
- **the lifecycle attempt dies before `finished`** (D2798: no resume from an
  earlier record — the operator decides, and `slot10-prod` would be the next
  slot);
- **the idle sleep is not requested within the window + 2 intervals** on
  `slot9-prod` after the repair;
- a `trial` row would outlive the close, or a row would move to `beta` without
  its claims `passed`;
- a currently-passing test would be weakened to make a new one pass;
- `--render-only` stops working with no host and no root.

---

## 10. Open items this session carries and creates

**Carried, untouched, each still true:** everything in Session 44's §10
*Carried* list (`docs/plans/session-44-implementation-plan.md:1723-1735`) and
its *Created* list's standing items — the relay as a third public surface and
its reading of every session (ADR 0286); no `statement_timeout` on the customer
roles (D2735); branch doors not in the editor (D2738); M7's X1/X2 (Hetzner) and
the store's 443 rule for it (D2640); beta's three rotations (D1995); D2801
(`workflow_revocation`'s race); the walker prefix `walk-s43-` (D2804); the
plane's footprint at rest `UNMEASURED`; `documented_path` (D1935, Session 46's);
`lifecycle-s41`…`-s44` empty.

**Created, and named so Session 46 does not inherit them silently:**

- **Stage 6 candidates from the brief, not built (D2828, D2823)**: the console's
  restore-window bar from data, relative ages on readings, a link to *What a
  refusal means* in every refusal, operation-id rows, a confirm button disabled
  until the name matches, a `<details>` menu for the console's navigation at
  phone width, copy buttons and the hero slider on the site (brief `:184`,
  `:181`), a combined pricing table (D2818), a dynamic *"Showing N of 43"*
  (D2819), the docs search field (brief `:143`).
- **`doctor usage`'s `requests_total` still reads an absent series as *not
  measured*** (`bin/doctor.py:949-962`): a report, correct as a report; ADR
  0289 changed only the sampler that a decision reads.
- **Two third-party typefaces are in the tree**: a new upstream version is a
  deliberate act (rig 45a again, the ADR's table, the pinned hashes).
- **The site can show a release ahead of the deployed one** for the hours
  between a bump's push and the sitting (D2840).
- **Session 46's person's walk needs `slot10-prod`** (D2837), and every release
  re-earns the lifecycle (D2714) — Session 46's release needs a slot too, or
  the walk's and the re-earning's are one (Session 46's plan decides).

---

## Appendix — what to consult, how a run is executed here, and the sheets

**Consult, in this order:** CLAUDE.md §1 (the shell traps); this plan's §0, §1
and the run's own text; the reads its run names. **The tree wins.**

**How a run is executed here**: CLAUDE.md §5. Every `sudo` line is the
operator's, on a sheet, under `script -q -e -c '…' /home/op/s45-<sheet>.txt` when
it execs into a container or deploys (D972, D1501), never piped or redirected;
`sudo -v` in the foreground first (D1376). Every `op` line is the agent's over
SSH; remote loops in a script file with `PATH="$HOME/.local/bin:$PATH"`
exported. **`<sha>` is never typed on a sheet**: the agent fills it from `git
rev-parse HEAD` on the host. **Before any sheet that deploys: `sudo systemctl
stop agentic-postgres-reconciler`, and `start` after** (D2178); **after any
checkout move: restart it** (D2411, D2179). **Read `--help` of every command on a
sheet before handing it.** **A sheet may not hand over a command whose
precondition is the previous sheet's success** (D1510). **No secret value is ever
typed into the conversation.** **Every launcher of a TOTP-computing instrument
runs the checkout's `.venv` python** (D2725). **A long instrument is launched
detached** (D2796; CLAUDE.md §1).

### Sheet IR2 — the witnesses on a live store (Run 1; root; read-only)

```
sudo -v
# the agent writes /home/op/s45-ir2.sh first (the queries of Run 1 step 3, against
# apg-slot3-prod-store-1 and apg-alpha-dev-store-1 by `docker exec ... wget -q -O -`,
# each answer's series count and names printed, no value of any other kind)
script -q -e -c 'sudo bash /home/op/s45-ir2.sh' /home/op/s45-ir2.txt
```

### Sheet IR3 — the absent series, read during the idle window (Run 9; root; read-only; D2854)

```
sudo -v
# the agent writes /home/op/s45-ir3.sh first: IR2's script against apg-slot9-prod-store-1 only,
# run AFTER the lifecycle's idle setting and BEFORE the sleep is requested (life.out's
# "idle-sleep" line, then within ~15 minutes); it prints series counts and labels, no value
script -q -e -c 'sudo bash /home/op/s45-ir3.sh' /home/op/s45-ir3.txt
```

Expected: `count(traefik_service_requests_total{code=~"[123].."})` → **0 series** (the
case); `count by (project) (up{job="edge",project="slot9-prod"} == 1)` and the
certificate witness → one series each. A request series present means the instrument's
quiet did not hold, or the export recreated nothing: recorded, and the claim's evidence
says which.

### Sheet R1 — the release priced (Run 9)

```
sudo -v
cd ~/agentic-postgres && sudo bin/upgrade.sh plan --project-file /home/op/<each>.yaml   # verb and flags read from --help by the agent
                                                                                          # expected 'minor' or below; a 'major' is §9's stop
```

### Sheets R2a / R2b / R2c / R2d — 1.23.0 deployed (Run 9; one per sheet, read before the next)

```
# THIS DEPLOY RESTARTS NO DATABASE (no Postgres image change, D2836).
sudo systemctl stop agentic-postgres-reconciler
script -q -e -c 'sudo ./deploy.sh <the project manifest as Session 44 R2a-c used it>' /home/op/s45-r2<x>.txt
   # R2c: slot3-prod by slot.sh redeploy (refused while the reconciler is active)
   # R2d: control-prod LAST -- the console recreated with the fonts and the favicon
(agent) s45-after.sh <key>: doctor 12 ok; the routes; for R2d the console's policy (font-src 'self'), a font route, the relay
sudo systemctl start agentic-postgres-reconciler          # after R2d only -- RC1: read `reconciler.sh status` active on the new checkout
```

### Sheets A1, RA, K1, V1 (Run 9) — as Session 44's (`session-44-implementation-plan.md:1819`), the commit and file names moved to 45; RA after the last deploy (D2494).

### Sheets H1, SL1, SL1b, SL2, SL3, RC1, K2, A1′, B1, SL4 (Run 9; D2837) — as Session 44's (`:1821`), `slot8-prod` → `slot9-prod`, every script `~/s45/run7/s45-*`, every file `/home/op/s45-*`; DNS and R2 by the agent through the Cloudflare API (Session 44's Run 8); SL4 after the tag, the credential written with `nano` and shredded (D2648).

### Sheets W0′ / W1′ / E0 / E1 / L0 / L1 — the walks (Run 9; the agent, from WSL, no SSH)

```
(agent) ~/s45/run7/s45-walk.sh --dry      # W0': the console walk to the Connect page, no rotation, the walker removed
(agent) ~/s45/run7/s45-sql.sh --dry       # E0:  sign-in, the editor, SELECT 1 on each door, the refusals (again after B1, D2838)
(agent) ~/s45/run7/s45-look.sh --dry      # L0:  every page at 390 and 1280, no record
(agent) ~/s45/run7/s45-walk.sh            # W1': the console walk, customer_app rotated, the creds file replaced (.before-s45 kept)
(agent) ~/s45/run7/s45-sql.sh             # E1:  the editor walk, the record
(agent) ~/s45/run7/s45-look.sh            # L1:  the look walk, the record and the screenshots (after B1)
```

### Sheet S1 — the one sweep (Run 9)

```
sudo -v
script -q -e -c 'sudo bash /home/op/s45-sweep.sh' /home/op/s45-s1.txt
   # derived from ~/s44/run6/s44-sweep.sh by diff; after E0 again (D2838)
```
