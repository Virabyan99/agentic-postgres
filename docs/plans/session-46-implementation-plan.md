# Session 46 — The journey, the person's walk, the Stage 5 release, the Stage 6 report

**Status: EXECUTING — Run 1 DONE (2026-10-24): the rigs, Sheet IR4 (7.7 s /
6.6 s), ADRs 0290–0293 accepted, threat items 28–30, `docs/hosted-walk.md`
(for the operator to read before Run 4; the person's day not yet arranged).
Rows D2890–D2896 added. Run 2 DONE (the support bundle: control 0010, the
reconciler pass, the route, the CLI, the console; rows D2897–D2901). NEXT FREE
D2902, ADR 0294. Next: Run 3.** Planned at `7b035d9` (Session
45's close record, tree clean, `main` = `origin/main`) against the host as read
that morning (§0). Rows **D2862–D2889** at planning; the runs add theirs from
**D2890**. ADRs **0290–0293** are Run 1's. **NEXT FREE after this table: D2890,
ADR 0294.**

The eleventh and last session of Stage 5 (D2593, D2809): the stage plan's
*Session 46* brief (`docs/plans/stage-5-plan.md` §5 *Session 46*, `:1106-1138`,
and the old Session 43 text it carries, `:971-1005`) — **the executable journey**
(D1981), **a person's walk** from the public site and an invitation link
(`documented_path` is theirs to move, D1935), **the support bundle** (D1971),
**`apg control status` and the node-loss runbook for the control project**
(D1984), **the Stage 5 release** (1.24.0, deployed on four, swept, tagged —
D1425), **the old host retired** (M7 X1/X2), **`scope-closure.md` re-audited row
by row and the Ledger re-read against the evidence** (D1979's second half), and
**`docs/stage-6-decision-report.md`** — with **the four answers the operator gave
at this planning on 2026-10-24** (§1 D2862).

Twelve runs and **one sitting**. **Run 1** is documentation: three rigs, one root
read (Sheet IR4), four ADRs, three threat items, the walk's statement. **Runs
2–6** change code. **Run 7** writes the trip's instruments. **Run 8** is the bump.
**Run 9** is the sitting: the release on the four projects, the dry runs, **the
person's walk on `slot10-prod`**, **the journey on `slot11-prod` opening the
eighth re-earning**, the branches, the reboot, the sweep, the external half, the
merge, the tag, the publish. **Run 10** retires the old host. **Run 11** is the
close — Stage 5's. **Run 12** writes the Stage 6 decision report.

**Brief:** `docs/plans/stage-5-plan.md` §1 rows **D1971, D1979, D1981, D1984**
(`:322`, `:330`, `:332`, `:335`), §5 *Session 46* (`:1106-1138`), §9 (`:1259-1303`),
§10 (`:1307-1350`); `docs/scope-closure.md` **§38** (`:1835-1895`) and **§28**
(`:1212-1282`, what Stage 5 inherited — re-audited row by row at the close);
`docs/plans/session-45-implementation-plan.md` §10 (`:1527-1557`), Runs 9–10's
**Done.** (`:1332-1448`) and rows **D2858–D2861** (`:429-432`). ADRs **0195**,
**0207** (the walker; read whole), **0246**, **0256** (states), **0260** (the
handoff token), **0261** (the Ledger), **0273** (the backups reading — the shape
the bundle copies), **0280/0281/0285** (the console, its session, its policy),
**0283** (the site), **0289**. The Stage 6 inputs, **outside the repository**, in
the launch folder: `future_stage_specs/agentic-postgres-stage-6-vision.md`
(51 KB) and `future_stage_specs/future-stages-review.md` (2026-10-18; its §4 and
§5 are the report's questions).

**Shape:** twelve runs. **Run 1** reads **no** CI verdict (documentation; the rigs
and IR4 recorded in its `**Done.**`). **Runs 2–6** each push and read that
commit's own CI verdict by full SHA (`gh api
"repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<40 chars>" -R
Virabyan99/agentic-postgres --jq '.workflow_runs[] | [.name, .status,
.conclusion] | @tsv'` from Git Bash, never inside `wsl`; judged on HTTP status,
three buckets — success / failure / not registered; an empty list is not a
verdict, D1057). **Every push to `main` also starts the `site` workflow after
`contract` succeeds** (ADR 0283): Run 4 writes the browser-first quickstart but
**parks it** (`~/s46/run4/park/`) — a page goes live on its push, and 1.23.0 has
no *New project* — so the site pages land **with the bump** (Run 8), in the
window between the bump's push and R2d that D2840 already accepts. **Run 7** reads no CI
(scripts outside the tree). **Run 8** is the bump. **Run 9** is the sitting.
**Runs 10–12** are documentation or Ledger/envelope moves (Run 11 reads CI: the
Ledger and the envelope are code). **Push only after the previous commit's CI
lands** — `ci.yml` cancels in-progress runs on `main` (`.github/workflows/ci.yml:36-38`).

**Product version at close:** `CURRENT_SESSION` **46**; `template_version`
**`1.24.0`** — predicted *minor* (D2888: control set migration **0010**, one new
`/v1` operation, a CLI flag and a verb, console files, a reconciler pass; **no**
project-manifest, outputs, host, lock, released-migration or Ledger-schema-version
change; no new secret, service, image or DNS name for the four projects; **no
Postgres image change, so no database restarts**) and **read from `upgrade plan`
on the host, never chosen** (Sheet R1). Released migrations stay **39**; the
control set **9 → 10**. A `major` is §9's stop.

**Written for whoever picks this up cold, and it will be a different model than
the one that planned it.** Every path below was read from the tree on 2026-10-24
at `7b035d9` — three explore passes (the walk record's machinery and its ADR; the
support and operator surfaces; the customer path as the site, the console, the
CLI and every external proof have it) and direct reads of
`docs/plans/stage-5-plan.md` (Status, §1, §5–§10), `docs/scope-closure.md` §37–§38,
`docs/stage-5-decision-report.md` whole, `bin/cloud.py:15-45`, `:640-750`,
`services/console/public/app.js:385-425`, `services/auth-api/app/control_routes.py:839-882`,
`services/auth-api/app/control_states.py:1-40`, `bin/reconciler.py:1205-1260`,
`:1405-1430`, `bin/control.sh:30-60`, `bin/doctor.py:935-975`, `site/templates/base.html`,
`~/s45/run7/s45-lifecycle.py:600-760`, `~/s45/run9/NOTES.md` whole and the M7 run
of `docs/plans/session-38-migration-plan.md:797-835` — **and the readings taken
at planning** (§0). **Read CLAUDE.md §1 in the launch folder before the first
command, then this plan's §1, then the appendix.** If a step here and the tree
disagree, **the tree wins and the disagreement is a divergence row** (next free
`D` after §1's table), never a silent reconciliation. **When this plan names a
line number, open the file at that line and read the surrounding twenty lines
before editing** — the numbers were right on 2026-10-24 and `ruff format` moves
them.

**The twelve sentences the executor most needs, in case nothing else is read:**

1. **The person is the operator's to recruit and the walk is theirs** (D2862,
   ADR 0207): someone who did not build Stage 5, holding **only the site's URL,
   the walk's statement and an invitation link** the operator mints and sends by
   their own email (Sheet P0). **Neither the operator, the agent nor a driver
   walks for `documented_path`.** The agent never sees the link.
2. **The walk's record is a new `hosted` shape** of `dx_record` (ADR 0290): no
   clone, no repository digest — the site's digest the person read
   (`<meta name="apg-site-digest">`, `site/templates/base.html:7`), the site
   routes, every `apg` command against the site's own code blocks, the
   statement's goals each reached or not. **`documented_path` moves to it
   (`DX-002`)**; the clone walk keeps its own claim, `appliance_documented_path`
   (`DX-001`), `failed` by D1935 until a person walks the clone (D2867).
3. **The console creates a project** (D2864, ADR 0291): the page generates the
   handoff token with WebCrypto, sends only its SHA-256 to `POST /v1/projects`
   (`control_routes.py:839-882`), and **shows the token once** the moment the
   creation is accepted; **no cross-origin call, no storage**; `apg project
   claim` gains `--token-file`; the claim is documented as optional. **The
   console's policy does not move** (ADR 0285's `connect-src`).
4. **Two slots, in a fixed order** (D2862, D2870): `slot10-prod` is prepared
   alone and is **the person's** (kept afterwards as a customer project);
   `slot11-prod` is prepared **only after the registry reads `slot10-prod`
   allocated** and is **the journey's and the lifecycle's** (consumed).
5. **The journey opens the lifecycle** (D2872): one creation on `slot11-prod`,
   made in the browser by `tests/external/browser/journey_walk.py`; the lifecycle
   instrument then **enters at `finish_create`** with the journey's operation
   (`--from-journey RECORD`, its D2499 path) and runs the rest — **in ONE
   attempt, detached** (D2796, D2798).
6. **The support bundle's readings are the doctor's verdicts, never its
   evidence** (D2874, ADR 0292): the reconciler records `{name, verdict, detail,
   read_at}` per check per deployed slot every 900 s through a nobody-granted
   definer of control migration **0010**; a member reads them with the
   project's operation history (`GET /v1/projects/{key}/diagnostics`); `apg
   project diagnostics --output FILE` writes the bundle 0600.
7. **`apg control status` is root, read-only, and derives states with the
   service's own function** (D2876, ADR 0293): `control_states` becomes a
   `SHARED_MODULE` (`tests/contract/test_auth_service_shape.py:93-101`); no
   migration.
8. **The site's digest inputs are frozen from the bump's push until the
   person's record is confirmed** (D2883): no commit touches `site/`,
   `src/agentic_postgres/plans.py`, `docs/reality-ledger.yaml`, `VERSION` or
   `src/agentic_postgres/site_build.py` in that span.
9. **Two Ledger rows go `trial` at the bump and `beta` at the close only on
   their claims** (D2884): `projects_self_service` (the console's create, naming
   `console_create_live`) and the new `support_bundle` (naming
   `support_bundle_live`); **no row `trial` at the close.**
10. **The release restarts no database** (D2888); control-prod applies 0010 at
    its deploy; **the reconciler is restarted after the checkout moves** (the
    diagnostics pass lives in it — D2179, D2411).
11. **The old host is retired only after its reading** (Run 10, D2879): Sheet X0
    reads it first; X1/X2 are each their own sheet.
12. **The Stage 6 report is written after `evidence/session-46.json` exists**
    (the stage plan's *Must not*), filled by a script that refuses a placeholder
    (D1890's method); its §6 is the executor's reading, for the operator to
    accept or rewrite.

---

## 0. Where the session starts

```
HEAD            7b035d95677fab81f4c1eaea14d9999019c310d5 on main, local = origin
                ("docs(session-45): Run 10 -- the gate and CI on the close"),
                tree clean. Last code commit a0f8183 (the close: CI contract
                40076024837, site 40077672819 success). Deployed AND TAGGED:
                4f4b207 (1.23.0, tag object 8d880308) on all four projects.
                main is past the tag with adc35b7, d2e9c40 (test-only),
                a0f8183 (Ledger + envelope -- nothing the deployment runs),
                docs.
VERSION         1.23.0 (VERSION; template_version() src/agentic_postgres/
                __init__.py:1445). CURRENT_SESSION 45 (:1437). README.md:7
                "Session 45 implemented".
REGISTRY        432 requirements (tests/acceptance-registry.yaml, 8,600 lines;
                Session 45's block from :8467). ID regex tests/contract/
                test_acceptance_registry.py:130 (alternation ends ...|SQL|UI) --
                **no `JRN`**. DX-001 :1832-1841. 339 claims, 160 offline
                (src/agentic_postgres/evidence_claims.py; Session 45's CLAIMS
                block :1069, OFFLINE :532); documented_path = ("DX-001",)
                :1422. 289 ADRs (README last row 0289). NEXT FREE: D2862, ADR 0290.
EVIDENCE        evidence/session-45.json (WSL, gitignored): 339 claims, 338
                passed, 1 failed -- documented_path (D1935).
LEDGER          docs/reality-ledger.yaml (43 rows): beta 26, planned 8
                (wake_on_connect, email, passkeys, project_isolation, agents,
                workflows, connectors, audit -- the last five target_session 38),
                not_offered 8 (support_access :1047 among them), not_metered 1,
                trial 0. schemas/reality-ledger.schema.json target_session
                maximum 46 (:121-129).
GATES           bin/session-45-check.sh 2,370 lines (readonly SESSION=45 :103;
                --dx-record-file :1180-1184, exported in mode_host :2149;
                --look-record-file external; mode_offline :1814, mode_host
                :2033, mode_external :2253). tests/contract/
                test_session_forty_five_gate_modes.py 1,152 lines. SHELL_COMMANDS
                tests/contract/test_cli_contract.py:273. The roster tests/
                conftest.py (APG_DX_RECORD_FILE :145; last entry
                APG_LOOK_RECORD_FILE :243).
THREATS         docs/threat-model.md 598 lines; the hosted list's last item 27
                (THR-UI-FONT, :553; table row :80).
ENVELOPE        src/agentic_postgres/capacity.py: Session 45's section from
                :2627; UNMEASURED :2781.
CONTROL SET     projects/control/migrations/templates/0001..0009 (nine);
                proposals under projects/control/proposals/.
BIN             169 entries; 41 session-NN-check.sh.
HOST            15.204.231.45 (apg-ovh-01), read 2026-10-24 10:33Z (p1-p3).
OLD HOST        62.238.99.122 (Hetzner CX23): NOT read at planning (D2879).
OPERATOR        2026-10-24 (this planning): a recruited person walks; the
                console creates a project; slot10 the walker's (kept), slot11
                the lifecycle's; every carried item in scope (§1 D2862).
```

**What exists, measured at `7b035d9`, and the session builds on:**

- **The walk record** — `src/agentic_postgres/dx_record.py` (500 lines). Nine
  required fields `followed_by, completed_at, release, project_slug,
  commands_run, files_edited, documents_read, undocumented_steps,
  reached_success_criterion` (`:53-63`), `blocked_by` optional (`:456-490`).
  `followed_by` = four strings `kind/identity/instructed_by/context` (`:72`,
  `:305-308`), `kind` `agent|person` (`:77`, `:309`), **`context` must contain
  "clone"** (`:316-322`) and "statement" or "task" (`:323-324`).
  `DOCUMENT_ROOTS` = eleven repository files (`:113-138`); `documented_commands`
  scans them and `docs/session-*-operator-guide.md` (`:141`, `:383-392`) for
  `./deploy.sh`, `bin/apg.sh <verb>`, `bin/*.sh|py` only (`:161-163`);
  `stale_documents` compares sha256s with the checkout (`:427-448`). **No
  finding counter**: any non-empty `undocumented_steps` fails (`check` and the
  live proof). `bin/dx-record.sh` / `.py`: verbs `digest --record F` (exits 3
  without a checkout, `dx-record.py:156-163`) and `check --record F
  [--project-slug S]`; exits 0 / 2 / 3 / 5 (`:12-19`). **DX-001's live proof**
  `tests/deployment/test_session12_reuse.py::test_a_developer_who_did_not_build_this_completed_the_documented_path`
  (`:235-326`, `live_host`, `APG_DX_RECORD_FILE`). **ADR 0207** §1 (`:41-88`):
  walkers were model sessions because *"a person who has never seen this
  repository is not available"*; a person's walk is *"a second and stronger
  record"* (`:85-86`); §4 (`:243-270`): the criterion is the workstation path;
  Consequences (`:274-276`): *"a walk by the operator or by this plan's executor
  does not count"*. `docs/second-walk.md` is the clone walk's arrangement
  (release 1.13.0, `:61`), pinned by `tests/contract/test_documentation_index.py:700-778`.
  **"Eleven"** is the Session 25 record's count (`docs/plans/session-25-implementation-plan.md:1496-1501`).
- **The customer path** (the site): `site/pages/quickstart.md` — accept the
  invitation (`:11`), the second factor (`:15`), **"Open a project" by the CLI
  only** (`:19-28`: `pipx install agentic-postgres-cli`, `apg login password`,
  `apg project create --name NAME --profile small --admin-username ADMIN`, `apg
  operation wait`, `apg project claim`), Connect (`:33-39`). Ten docs pages under
  `site/pages/docs/` with their `apg` lines (getting-started `:23-34`, projects
  `:8-19`, connecting `:42-45`, branches `:19-41`, backups `:11-31`,
  plans-and-usage `:13-43`, insights-and-monitoring `:13`, `:36`, cli `:20-41`;
  sql-editor and refusals none).
- **The console** (`services/console/public/app.js` 40,505 B; `VIEWS` `:883`,
  router `:898`, `/accept` `:939`): `overview` (`:389-410`) lists organisations
  and their projects and ends **"Creating a project is done with the
  command-line client in this beta: `apg project create` then `apg project
  claim`."** (`:405-408`); `newOrganization` (`:412-424`, `POST /organizations`);
  the project views (connect `:436`, sql `:822`, branches `:479`, backups
  `:551`, usage `:588`, insights `:592`, monitoring `:608`, settings `:620`) and
  the organisation views (plan `:684`, usage `:709`, notifications `:715`,
  settings `:723`). `acceptPage` (`:216`), `createAccount` (`:255`),
  `enrolFactor` (`:176`), `signInWithNextCode` (`:297`). `scram.js` already uses
  WebCrypto.
- **Creation and the claim**: `POST /v1/projects` (`control_routes.py:839-882`,
  *"the token itself never reaches this plane"*, `handoff_sha256` required).
  `bin/cloud.py` `project_create` (`:660-697`: the token kept in
  `handoffs/pending-<16>` BEFORE the request, renamed `handoffs/<operation-id>`)
  and `project_claim` (`:698-744`: presents the token to **the project's own**
  `{app}/auth/reset-password`, never to the control plane, ADR 0260; refuses
  with no held handoff file).
- **Invitations**: `POST /v1/invitations` (`control_routes.py:434-479`):
  `accept_url = {console_origin}/accept#{token}`; with an organisation and a
  role a **membership** invitation (owner/admin), with neither an **account**
  invitation — **only the registry administrator** (`apg org invite --account`,
  `docs/control-plane.md:45-47`; the admin's factor is on the operator's iPhone,
  CLAUDE.md §2 WALK STATE); an account in no organisation reaches nothing but
  `/v1/me` (`docs/control-plane.md:58-60`); an organisation's creator is its
  owner, who must enrol a factor (FACTOR_GATE).
- **Slots**: `project create` lands in **a** ready slot (`docs/control-plane.md:154`,
  `:179-186`); `capacity_exhausted {reason: no_slot}` with none ready; a deleted
  slot is `consumed` (`docs/operator-guide.md` §20, `:1943-2105`).
- **No support bundle**: no `diagnos`/`support`/`doctor` in
  `control_routes.py`, the control contract or `bin/cloud.py`; **the control
  plane holds no credential to the node, so it cannot read a doctor**
  (`control_states.py:1-6`). The pattern to copy: the reconciler's
  `record_backups` (`bin/reconciler.py:1210-1228`, every
  `BACKUP_RECORD_SECONDS = 900` `:130`; `backups_of` `:1405-1430` answers
  *asleep* for a stopped database) into `app.control_record_backups(jsonb)`
  (`projects/control/migrations/templates/0006-control-branches.sql:403-485`,
  REVOKEd from PUBLIC, granted to nobody, called as root through
  `container_exec`). **`app.control_project_operations(p_user, p_key)`** exists
  (`0004-control-operations.sql:284`, granted to `{{auth_service}}` `:660`;
  used by `control_repository.py:281`). The doctor: `bin/doctor.py
  --project KEY --json` (`:1221-1238`), twelve checks in `diagnose()`
  (`:1065-1089`); `--json` = `{project_key, observed_at, worst, exit_code,
  checks:[{name, verdict, detail, evidence}]}` (`src/agentic_postgres/diagnosis.py:750-790`);
  evidence values a customer must not get: the disk check's `mount` (a host
  path, `:413`), the workflow check's `heartbeat_holder` (`:651`).
- **Operator reads**: `bin/control.sh` / `.py` (verbs `adopt`, `registry`,
  `totp-reset`, usage `:35-58`, the `case` `:93-96`); its `psql()` runs
  `container_exec.run(container, "psql", "-U", "postgres", …)` and finds the
  control project by `control_registry.find_control` / `target()`
  (`src/agentic_postgres/control_registry.py:112`, `:137`). **As `postgres` row
  security does not bind** (`0001-control-identity.sql:610-613`): plain SELECTs
  read `app.control_projects`, `control_organizations`, `control_memberships`,
  `control_operations`, `control_slots`, `control_branches`,
  `control_usage_samples`, `control_plan_limits`. **A project's state is derived
  only in Python**, by `services/auth-api/app/control_states.py` (141 lines,
  stdlib only). `bin/fleet.py`, `doctor --reading capacity`, `bin/admit.sh` read
  the node.
- **The node-loss runbook** (`docs/node-loss-runbook.md`, 295 lines, §0–§8)
  names the control project only in §8 *A planned move* (`:242` *"the control
  project LAST (D2253)"*, `:269-270`); nothing on the reconciler, slots, the
  console, the relay or the telemetry plane. Guard
  `tests/contract/test_disaster_kit.py:735-756`.
- **The lifecycle instrument** (`~/s45/run7/s45-lifecycle.py`, 1,388 lines,
  outside the repo): login as the probe (`:610-613`); plans + the probe
  organisation's refusal + its own organisation (`:618-620`,
  `lifecycle_organization` `:1052`); `create_and_claim` (`:689-697`) →
  `finish_create(created, started)` (`:699-727`), which a resume already enters
  with `started=None` (D2499: `create_seconds` from the row's interval,
  `create_seconds_source` says so); `claim` (`:662-687`) runs `apg project
  claim`. Flags `:1316-1357`.
- **D2801**: `tests/deployment/test_session32_workflows.py:973`
  (`test_a_revoked_agents_run_stops_at_the_boundary_with_no_call`); the worker
  names an unknown refusal `unclassified_refusal`
  (`services/auth-api/app/workflow_worker.py:398-408`).
- **`doctor usage`'s request figure** (`bin/doctor.py:943-955`):
  `sum(traefik_service_requests_total)`, empty → *"the store holds no such
  series yet"* (UNKNOWN). The sampler's witnessed reading is
  `usage_reading.requests_below_400` (`src/agentic_postgres/usage_reading.py:197-220`).
- **The site's digest**: every page carries `<meta name="apg-site-digest">`
  (`site/templates/base.html:7`) = `site_build.digest()` over
  `digest_inputs()` (`site_build.py:677-696`: `site/`, `plans.py`, the Ledger,
  `VERSION`, `site_build.py`).
- **The trip's tools from Session 45** (WSL): `~/s45/run7/` (`s45-derive.py` +
  `s45-post-derive.py`, `s45-window.py`, `s45-after.sh`, `s45-after-reboot.sh`,
  `s45-units.sh`, `s45-walk.sh`, `s45-sql.sh`, `s45-look.sh`,
  `s45-lifecycle.py`, `s45-branches.py`, `s45-hostyaml.py`, `s45-dns.sh`,
  `s45-free.sh`, `s45-probe-start/stop.sh`, `s45-v1.sh`, `s45-x0.sh`,
  `s45-sweep.sh` + `s45-launch.sh`, `s45-external.sh`, the detached launchers
  `life-start.sh`, `br-start.sh`, `br-delete.sh`, `ext-start.sh`), `~/s45/run9/`
  (`NOTES.md`, `tag.sh`, `battery-d2860.py`), `~/s45/run10/` (the gate shards:
  `gate01-*.sh`, `shards01.json`). The pinned Playwright image `PW_IMAGE`
  (`mcr.microsoft.com/playwright/python:v1.63.0-noble@sha256:72bd171a…`, as
  `~/s45/run7/s45-look.sh` names it) and the package in `~/s45/walk-home/pw`.

**Measured at planning** (2026-10-24; no rig was run — every third-party fact
the build relies on is Run 1's, §5):

| # | Reading | Result |
|---|---|---|
| p1 | `apg-diag containers` (agent, 10:33Z) | exit 0; **48 containers**: alpha-dev 10, beta-dev 10, control-prod 12 (console, sql-relay), slot3-prod 12, the plane's 4; one without a healthcheck (the gateway, D2636); every one `Up 6 hours` (since B1) |
| p2 | `apg-diag listeners` | 22, 80, 443, 5432 (+ the resolver's 53, chrony 323, DHCP 68) — unchanged |
| p3 | op: checkout, `free -m`, `uptime`, units, copies, `df`, `host.yaml` | `4f4b2070f4cc67c5a1ea085f71eba35b784b5f0b` clean; total 11,671, **available 8,183 MiB**; up 5 h 45; reconciler, edge, telemetry `active`; `/home/op/*-outputs.json`: alpha, beta, control-prod, slot1–9, snippets; `/` 16 G of 96 G; `host.yaml` slots `slot1-prod` … `slot9-prod` (`:137-179`) |
| p4 | Hetzner `62.238.99.122` | **not read** — the planning session's read was refused by the workstation's permission classifier (a production read); Run 10's Sheet X0 is its first reading (D2879) |

---

## 1. The divergence table

Six columns. Each row is a **measured fact about the tree at `7b035d9`** (or the
host as the planning readings left it) set against what the brief says, with the
decision this plan takes. **Next free number after this table is D2890.** Rows
the runs add go in a second table below it, in execution order.

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2862** | Stage plan §5 *Session 46* `:1119-1136`: the journey, the person's walk, the support bundle, `apg control status`, the release, the report. | Four questions the tree cannot answer: who walks; whether the walk needs a terminal; how many slots; which carried items ride with the release. | **The operator, 2026-10-24 (this planning): (1) a person the operator recruits walks** (ADR 0207's *"a second and stronger record"*); **(2) the console creates a project** so the walk needs no terminal (D2864); **(3) `slot10-prod` the walker's, kept afterwards; `slot11-prod` the lifecycle's**; **(4) in scope: `apg control status` + the runbook, the support bundle, M7 X1/X2, the small repairs** (D2880–D2882). | A product question is the operator's; the plan records the answer. | 0290–0293 |
| **D2863** | D1981: *"Appendix C as one ordered proof"* (the specification's thirty-one checkboxes, §57). | **The specification is not in the tree** (`stage-5-consolidated-spec.md`: 0 files in the repository, WSL home or the launch folder; only the stage plan quotes it). | **The journey is the site's documented path as published** — `quickstart.md`'s steps and the docs pages' actions, in the order the site gives them — its steps fixed in Run 6 (J1–J14). The stage plan's *"thirty-one"* is not counted against it; the Stage 6 report says the specification's list was not available. | The person walks the site; a proof of a list nobody can read would be a list the author typed. | 0290 |
| **D2864** | Stage plan `:1119-1124`: *"The walker holds only the link and the site's URL; the success criterion is a working connection string reached in the browser"*; Session 43's target *"with no terminal"* (`:943-945`). | **Creation is CLI-only**: `quickstart.md:19-28` (`pipx install` + `apg project create` + `apg project claim`); the console's overview says so (`app.js:405-408`); D2702 left browser creation to 44/45 and neither built it. | **The operator: build it** (ADR 0291). The overview gains *New project* per organisation (name, profile `small`/`standard`/`large`, administrator's username) calling `POST /v1/projects`; the operation followed with the existing `waitFor` (`app.js:123-132`); the Connect page reached from it. The quickstart and `projects.md` rewritten browser-first (Run 4), the CLI lines kept as *"or, from a terminal"*. | The stage's own success criterion; every route exists. | **0291** |
| **D2865** | ADR 0260: the creator claims the first administrator with a token *"only they hold"*; the CLI keeps it in a 0600 file. | The claim goes to **the project's origin** (`{app}/auth/reset-password`, `cloud.py:698-744`), not the console's; the console's `connect-src` is `'self'` + the relay (ADR 0285); a creation takes **1,375.9–1,708.4 s** (the envelope, Sessions 42–45), so a token held in page memory lives ~25 minutes in a tab. | **The page makes the token (WebCrypto `getRandomValues`, 32 bytes, base64url), sends only its SHA-256, and shows it ONCE in the shown-once panel the moment the creation is ACCEPTED** (before the wait), with the line `apg project claim --project-key KEY --token-file FILE`; the token is dropped from the page when the panel is dismissed. **No cross-origin call, no storage, no policy change.** `apg project claim` gains `--token-file FILE` (0600 required, read once; the operation chosen by the token's SHA-256 against the creations, never the first row — D2316). The claim is documented as **optional** (the doors and the editor need none). **Rig 46a** reads the project auth's answer to a CORS preflight from the console's origin and records it in ADR 0291. | A token shown at acceptance is saved before the wait can lose it; a cross-origin claim would widen every project's surface for a step the connection string does not need. | **0291** |
| **D2866** | Spec §9 and D1981: *"walks the first twenty minutes"*. | Creation alone is 1,375.9–1,708.4 s (23–28.5 min) on this host. | **The walk's criterion is *reached*, never *within twenty minutes***: the record carries the person's times (link opened, account, factor, organisation, creation accepted, connection string, each further goal); the envelope and the Stage 6 report read them. | A bound the product cannot meet in one step is a bound nobody should be asked to walk. | 0290 |
| **D2867** | D1981: *"the record goes to the gate as `APG_DX_RECORD_FILE`"*; stage plan `:1121`: *"never a clone"*. | **The record is the clone walk's**: `context` must contain "clone" (`dx_record.py:316`); documents are repository files with sha256s against the checkout (`:113-138`, `:427-448`); commands are `bin/*.sh`/`deploy.sh` forms (`:161-163`); ADR 0207 §4's criterion is the workstation path; the proof is `live_host` under root (`session-45-check.sh:2149`). | **ADR 0290: a second record path, `hosted`.** `path: "hosted"` (absent = `clone`, unchanged): `followed_by.kind` must be `person`; `context` must contain "site", "invitation" and "statement"; `site_commit` (40 hex) and `site_digest` (the page meta) — the check builds the site at the checkout and requires the digest equal; `documents_read` = site ROUTES (each a route the build produces); `commands_run` = every `apg …` line typed, each matching a line in the built pages' code blocks; `files_edited` empty; `goals` = the statement's goals, each `{goal, reached, at}`; `transcribed_by` and `confirmed_by_walker_at`. **`documented_path` → `("DX-002",)`** (the hosted walk, external); **a new claim `appliance_documented_path` → `("DX-001",)`** (the clone walk, host, the Session 25 record — `failed` by D1935, said so). | A record built for a clone cannot describe a walk that never touches one; renaming the clone's claim keeps its failure true instead of hiding it. | **0290**, 0207 |
| **D2868** | D1981: *"Arranged, never closed by the author."* | ADR 0207 Consequences (`:274-276`): the operator's or the executor's walk does not count; an account invitation is minted only by the registry administrator, whose factor is the operator's phone. | **Sheet P0 is the operator's** (`apg org invite --account --output FILE` as `control-admin`, the code typed by the operator); **the operator sends the link and `docs/hosted-walk.md`'s statement by their own email**; the agent never holds the link. **The person writes their own notes** in the statement's plain-text form; **the agent transcribes them verbatim** into the record (`transcribed_by: agent`), **the person reads the JSON and confirms** (`confirmed_by_walker_at`), and only then is it handed to the gate. | The author may carry the record; never author it. | 0290 |
| **D2869** | Quickstart `:11-28`: accept, factor, project. | An account invitation joins **no** organisation (`docs/control-plane.md:58-60`); the person must create one (`#/new`) and becomes its owner, whose factor is forced. No site page says *"create an organisation"* as a step. | **Run 4's browser-first quickstart states it** (accept → *New organisation* → the factor → *New project* → Connect). Nothing else on the site is pre-walked: finding what the pages do not say is the person's job. | A known gap is repaired; the unknown ones are the walk. | — |
| **D2870** | D2862 (3): slot10 the walker's, slot11 the lifecycle's. | `project create` takes **a** ready slot; with both ready the person's creation could land on `slot11-prod`. | **Order**: H1 declares both; **SL1–SL3 prepare `slot10-prod` alone**; the person walks; **only after A1 reads `slot10-prod` allocated** do SL1′–SL3′ prepare `slot11-prod`. A creation by anyone else between them is §9's stop. | The naming is the operator's; the order makes it true. | — |
| **D2871** | D1981: the journey from *"the invitation"*. | The agent cannot mint an account invitation (the registry administrator's factor is the operator's phone). The console walk (W1′) starts from a **membership** invitation by the probe owner into `probe-s37` (`tests/external/browser/console_walk.py`). | **The journey starts from a membership invitation** minted by the probe owner (`apg org invite --role member`, the probe's seed in `~/s37/probe-otpauth`), then **creates its own organisation `lifecycle-s46`** (owner, factor enrolled), exactly the steps an account invitation's holder takes after accepting; its membership in `probe-s37` is removed after. The record names the start. | The steps after the first are the documented ones; the first is the only one the agent can make. | 0290 |
| **D2872** | D2714: every release re-earns the lifecycle; D2862 (3): one slot for it. | The lifecycle instrument creates its own project (`create_and_claim`); a slot gives one creation; the journey must create one too. | **The journey opens the lifecycle**: `journey_walk.py` creates the project in the console on `slot11-prod` and records the operation id, the account's 0600 credentials and the token; **`s46-lifecycle.py --from-journey RECORD`** runs the probe's steps (plans, the probe organisation's refusal), `logout`, `login` as the journey's account, then **`finish_create(<the journey's operation>, None)`** (D2499's path) and `claim --token-file`, and the rest of the lifecycle. **Run 7 greps every reader of `create_operation`, `create_seconds`, `create_seconds_source`, `claim_narrowed`, `organization_id`, `probe_organization_id` in `tests/external/`** (D979, D2860) and moves any that assumes the instrument made the creation. A dead journey before acceptance costs nothing; after it, `slot11-prod` is consumed — §9's stop. | One creation proves both the browser's door and the lifecycle's — and the record says whose hands made it. | — |
| **D2873** | D1981: *"`tests/external/test_journey.py`"*. | Every live module is `test_sessionNN_*.py` (`tests/external/`). | **`tests/external/test_session46_journey.py`** (the journey) and **`tests/external/test_session46_walk.py`** (the person's record); the driver `tests/external/browser/journey_walk.py`. | The tree's names. | — |
| **D2874** | D1971: *"a member's `/api/v1/projects/{id}/diagnostics`: the doctor's twelve readings and the project's operation history, redacted by the canary."* | No route; the control plane cannot read a doctor (`control_states.py:1-6`); the doctor's `evidence` holds a host path and a lock holder (`diagnosis.py:413`, `:651`); "the canary" is a test discipline (`tests/contract/test_doctor_redaction.py:44-45`), not a runtime filter. | **ADR 0292.** Control migration **`0010-control-diagnostics.sql`**: `app.control_diagnostic_readings (project_key, check_name, verdict, detail, read_at; PK (project_key, check_name))`, FORCE RLS, no policy for the request roles; `app.control_record_diagnostics(p_readings jsonb)` (definer, REVOKEd, granted to nobody — `control_record_backups`'s shape); `app.control_project_diagnostics(p_user, p_key)` (definer, member-scoped through `control_enter`, granted to `{{auth_service}}`). **The reconciler** gains `record_diagnostics` every `DIAGNOSTICS_RECORD_SECONDS = 900`: per deployed slot `bin/doctor.py --project KEY --json` (child budget 300 s), **`{name, verdict, detail}` only — `evidence` never leaves the reconciler**; a stopped database records the slot as *asleep* (one row `state`, verdict `asleep`), never twelve failures. **`GET /v1/projects/{key}/diagnostics`** (member and above): the readings with `read_at` and the project's operations (`control_project_operations`); older than 1,800 s → each reading `stale`. **CLI** `apg project diagnostics [--project-key K] --output FILE` (0600, refused if it exists); **the console**: Settings gains *Support bundle* (the readings with their ages, read-only). **Guard**: a doctor answer whose `evidence` and `detail` carry planted values (`test_doctor_redaction`'s SENSITIVE set) records none of them. | The bundle is the support conversation's first page; it must not become a second door to the node. | **0292** |
| **D2875** | Ledger `support_access` (`reality-ledger.yaml:1047-1063`): *stage5_reality "Grants are not built (D1971); a support bundle a member downloads is."* | Untrue at planning: no bundle exists. | **Left as written until the close**, which reads it true only if `support_bundle_live` passed (else the clause is removed). The bundle gets **its own row**, `support_bundle` (concept *Support bundle*), `trial` at the bump (D2884). | A sentence about a thing is checked against the thing at the close. | 0261 |
| **D2876** | D1984: *"`apg control status` (root, the control project's database read through the container) — owners, plans, entitlements, operations, sleeping projects, branches."* | `bin/control.sh` exists (`adopt`, `registry`, `totp-reset`); `postgres` bypasses row security (`0001:610-613`); **the state is derived only by `control_states.py`** in the service, which a `bin/` command cannot import (ADR 0093) unless it is a shared module. | **ADR 0293.** `sudo bin/control.sh status [--json]`: organisations (name, plan, owners' usernames, projects active of the plan's limit), projects (key, organisation, slot, profile, **state by `control_states.project_state`**, last operation), operations pending/running, branches, slots by state, notifications in the last 24 h — **one SELECT per section, no write, no secret column**; exit 0, or 6 when the control database could not be read. `control_states` joins `SHARED_MODULES` (stdlib only already) and is loaded the way the repository loads `plans`. No migration. | One derivation of a state, read by the API and the operator alike (D704). | **0293** |
| **D2877** | Stage plan `:1326-1329`: *"the node-loss runbook must restore it **first**"*. | `docs/node-loss-runbook.md` names the control project only for a planned move, LAST (`:242`). | **§0–§5 amended**: the reconciler held stopped (`systemctl disable --now`) until every project is restored; **control-prod restored and deployed first** (the console and the relay with it), then the kept customer projects (`slot3-prod`, `slot10-prod`) by `slot.sh redeploy`, then alpha and beta; slots re-read (`slot.sh status`); the telemetry plane **rebuilt empty** (its volumes are not backed up, §10) by `telemetry.sh up`; `control.sh registry` agrees before the reconciler starts. §8's *LAST* for a move stays (D2253) with one sentence saying why the two orders differ. Documentation only. | Without the control project no customer can be told their project is fine. | — |
| **D2878** | D1979's second half: *"the Ledger re-read against the evidence"*; the schema's `target_session`: *"The Stage 5 session that builds it"*. | Five `planned` rows carry **`target_session: 38`**, long passed: `project_isolation` (`:1162`), `agents` (`:1212`), `workflows` (`:1228`), `connectors` (`:1245`), `audit` (`:1262`). Hosted customers cannot configure the agentic layer (the future-stages review §4 item 2). | **At the close**: `agents`, `workflows`, `connectors`, `audit` → `target_session: null`, `stage5_reality` *"Not opened to hosted customers in Stage 5; each project runs its plane, configured by the operator."*; **`project_isolation` → `beta` only if `project_isolation` (and `isolation_matrix`) passed in `evidence/session-46.json` and are named as its evidence**, else `null` as the four. Every other row re-read against the tagged evidence, one line each in Run 11's **Done.** | A target in the past is a promise nobody holds. | 0261 |
| **D2879** | M7 X1/X2 (`docs/plans/session-38-migration-plan.md:797-835`, D2254): allowed since 2026-10-12 ~21:30Z. | Not run; the store still admits 443 from `62.238.99.122` (D2640); the old host was **not read** at planning (p4). | **Run 10**: Sheet **X0** (the operator: `ssh op@62.238.99.122` reads hostname, the three project units `disabled`/`inactive`, the volumes); **X1** `bootstrap-providers --destroy` × 3 on the old host with the store's credential (the rehome-minted identities revoked; read at the store's console: each key ONE identity, OVH's); **X2** the operator deletes the three Infisical Cloud projects and four Cloud identities, reads the Cloud organisation empty, cancels the Hetzner server; **X3** `sudo ufw delete allow from 62.238.99.122 to any port 443 proto tcp` on the store. Each its own sheet, read before the next (D1510). | Retire after reading, never on a premise. | 0187 |
| **D2880** | Scope-closure §38: *"`doctor usage`'s `requests_total` still reads an absent series as not measured."* | `bin/doctor.py:943-955` (`sum(traefik_service_requests_total)`, empty → UNKNOWN *"yet"*); ADR 0289 moved only the sampler. | **`doctor usage` reads it with ADR 0289's two witnesses**: `usage_reading.requests_total(key)` (the sampler's witness loop shared, the query `sum(traefik_service_requests_total)`), absent with both witnesses → **0, measured**; without → UNKNOWN with `REQUESTS_UNWITNESSED`'s reason (the *"yet"* gone). ADR 0289 gains one sentence (Amended). Tests first. | One reading of one series, in the report and the decision alike. | 0289 |
| **D2881** | D2859: `idle_after_wake_live`'s docstring *"the reading of an absent series as 0"*. | The record proved the ordinary path (the series present). | **The docstring says what the record proves** (*a woken project left untouched is idle-slept*), the absent branch named as proved offline (`test_usage_sampler`). A test-only text change. | A docstring is a claim. | — |
| **D2882** | D2801: the proof is order-dependent. | When the worker claims step 1 before the revocation lands the plane refuses the call and the worker names it `unclassified_refusal` (`workflow_worker.py:398-408`) → the run `failed`, not `stopped`. | **Run 5 reads the plane's refusal of a revoked agent's token first** (its status and error code, offline from `mcp`'s own refusal table). **If it is a named shape**, the worker classifies it as the revocation boundary and the run ends `stopped` — a product repair, the proof unchanged, the failing case written first. **If it is not**, the proof reads both arms by their cause (`stopped` at a boundary, or `failed` with the plane's refusal recorded) — and the run's **Done.** says which. | A race needs both arms decided. | — |
| **D2883** | ADR 0283: the site deploys on every green push to `main`; D2840. | The record pins `site_digest`; the digest's inputs are `site/`, `plans.py`, the Ledger, `VERSION`, `site_build.py` (`site_build.py:677-696`). | **Frozen** from the bump's push until `confirmed_by_walker_at`: no commit touches a digest input (docs under `docs/plans/` do not). If a repair is needed after the walk (a second walker, §10), its commit's diff from the deployed commit is `site/`- and `docs/`-only and the second record names its own `site_commit`. | The page the person read is the page the gate rebuilds. | 0290 |
| **D2884** | Stage plan §11: *"The Reality Ledger moved in the run that builds the thing."*; ADR 0261: a `trial` row names its own session's claims. | `projects_self_service` is `beta` on CLI evidence; a console control is new; no `support_bundle` row exists. | **At the bump**: `projects_self_service` → **`trial`** naming `console_create_live` (its `customer_text` *being verified*; controls gain `/console/`), `support_bundle` **new, `trial`** naming `support_bundle_live`. **At the close → `beta`** only on those claims (and, for `projects_self_service`, its existing ones) `passed`; else back to `beta` on its CLI evidence with the console's form removed (D2806's precedent) / `planned`. **No row `trial` at the close.** | Session 45's notifications pattern (D2834, D2857). | 0261 |
| **D2885** | §7 below. | Every Session 38–45 lifecycle, branch, console, editor and look proof pins the deployed commit (D2714) and some a session (`session in (…)`). | **All re-earned at 1.24.0**: the lifecycle on `slot11-prod` (from the journey), the branches on `slot3-prod`, W1′, E1, L1 — and the session pins widened to 46 (Run 7, count-asserted, the nine of Session 45's §0 plus `test_session45_idle.py`'s and `test_session45_look.py`'s). | A release re-earns what it ships. | — |
| **D2886** | D2862 (3): the walker's project is kept. | `slot3-prod` is the one kept customer project; every release redeploys it by `slot.sh redeploy` (Session 45 R2c). | **`slot10-prod` joins it**: Session 46's own sheets redeploy nothing on it (it is created at 1.24.0); **every later release redeploys both** (§10); the person's credentials are theirs — the agent holds none and no proof reads them. A1 reads `agrees` × 5 from Run 9's walk on. | A kept project is a customer's; the operator's proofs stay off it. | — |
| **D2887** | Stage plan §5: *"`docs/stage-6-decision-report.md` … answering the specification's §65 question with numbers."* | The Stage 6 vision and its review are **outside the repository** (`future_stage_specs/` in the launch folder); the Stage 5 report's shape is `docs/stage-5-decision-report.md` (§1–§6, filled by a script, §6 the executor's). | **Run 12** writes the report in that shape, its numbers filled from `evidence/session-46.json`, `capacity.ENVELOPE` and the tree at the tagged commit by `~/s46/run12/fill.py` (refuses a placeholder); §5 prices the vision's assumptions against Stage 5's readings (the review's §4 mismatches); §6 for the operator. **The two input documents are committed under `docs/stage-6/` verbatim only at the operator's word** (asked at Run 12). | The report reads evidence; its inputs are the operator's documents. | — |
| **D2888** | Stage plan: *"the Stage 5 release"*. | No Postgres image input moved since `4f4b207`; the changes are a control migration, a `/v1` operation, console files, a CLI flag and verb, a reconciler pass. | **Predicted minor** (ADR 0162: `api_operation_added`); no database restart; control-prod applies 0010 at its deploy; the console recreated. Read by D1624's rig at Run 8 against `4f4b207` and by Sheet R1 on the host. | What a deploy does is named on its sheet. | 0162 |
| **D2889** | D1981: the person holds *"the invitation and the console URL only"*. | `docs/second-walk.md` is the clone walk's statement (release 1.13.0, the clone path, `kind: "agent"`). | **`docs/hosted-walk.md`** (new): the arrangement (who, when, what the operator sends, how the notes come back, the transcription and the confirmation, the second walker's budget) and **the statement between markers** — the site's URL, *"you will receive an invitation link"*, the goals (a working connection string; then a branch at a past time, its restore point read, usage, Query Insights, the SQL editor, the support bundle), *"write down every step a page did not tell you"*, the notes' plain-text form; **no repository path, no command, no hint**. Pinned by a new `test_documentation_index` case (markers, the URL, no `bin/`, no `git`). | The statement is the walk's only input besides the link; a hint in it would be a step the pages did not give. | 0290 |

**Rows the runs add** (from D2890):

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2890** | Run 1 step 1(c): `OPTIONS https://slot3.agenticpostgresql.com/auth/reset-password`. | That path is the edge's own `404 page not found` (measured 11:02Z). The claim's target is `routes.app` + `/auth/reset-password` (`bin/cloud.py:739`); slot3-prod's `app` route is `https://slot3.agenticpostgresql.com/api/app` (its deployed document, `~/s45/run9/slot3-prod-outputs.json`). | **Rig 46a(c) read the real route**: `/api/app/auth/reset-password` answers `OPTIONS` **405, `allow: POST`, no `Access-Control-*` header**, with and without `Origin` (11:03Z). Recorded in ADR 0291. | A preflight read at the wrong path measures the edge, not the project. | 0291 |
| **D2891** | Twelve sentences #8 / D2883: the freeze covers *"`site/`, `src/agentic_postgres/plans.py`, `docs/reality-ledger.yaml`, `VERSION` or `src/agentic_postgres/site_build.py`"*. | `site_build.digest_inputs()` (`site_build.py:677-689`) is every file under `site/`, **the five shared assets under `services/console/public/`** (four font files, `favicon.svg`; ADR 0288), **`services/auth-api/app/plans.py`** (`src/agentic_postgres/plans.py` only `service_source.load`s it), the Ledger, `VERSION`, `site_build.py`. | **The freeze is `digest_inputs()` itself, never a typed list**: Run 7's freeze check and Run 8's text read the function. A console change touching `fonts/` or `favicon.svg` is inside the freeze; `app.js` is not a digest input. | The list that decides the digest is the one the freeze must follow (D2883's own reason). | 0290 |
| **D2892** | Run 6: the journey's driver in Chromium against the console. | Playwright's `page.wait_for_function("<string>")` evaluates a string in the page and is refused under the console's `script-src 'self'` (*"'unsafe-eval' is not an allowed source of script"*, rig 46a's first run). | **The journey's driver waits with locators and selectors only** (`page.locator(…).wait_for()`), never a string evaluated in the page; Run 6's driver is grepped for `wait_for_function` and `evaluate("` before its first run. | D2858's sibling: the console's policy refuses what a test tool assumes. | 0291 |
| **D2893** | D2867: *"`commands_run` = every `apg …` line typed, each matching a line in the built pages' code blocks"*. | Rig 46b: 24 code blocks, **42 distinct `apg` lines, 30 `apg <noun> <verb>` prefixes, every one with a placeholder** (`KEY`, `NAME`, `ADMIN`, `OPERATION`, `./app-password`, a sample time); other code lines: `pipx` ×3, `uv` ×1, one connection-string template. | **ADR 0290 §3: an `apg` command matches when one documented line has its `apg <noun> <verb>` and every flag it used** (values free); any other command matches a code line after whitespace is normalised; a third-party client is a goal's note, not a command, and the record holds no connection string. | A byte match would read every honest command as undocumented. | 0290 |
| **D2894** | D2874 / §0: `app.control_record_backups` is the shape — *"definer, REVOKEd, granted to nobody"*. | `0006-control-branches.sql:403-406`: **`SECURITY INVOKER`**, REVOKEd from PUBLIC, granted to nobody, called as `postgres` through `container_exec`. The member reader `control_get_backups` (`:191-211`) is `SECURITY DEFINER` with `control_enter` + `control_require_role(…, 'viewer')`. | **ADR 0292 follows the tree**: `control_record_diagnostics` is `SECURITY INVOKER`, granted to nobody; `control_project_diagnostics` a definer with `control_enter` + `control_require_role(…, 'member')`. | The tree wins. | 0292 |
| **D2895** | D2865: `claim --token-file` picks *"the operation … by the token's SHA-256 against the creations, never the first row"*; the shown-once line carries `--project-key KEY`. | `GET /v1/operations` serves no `arguments` (`control_service._operation`, `:1234-1250`), so a member cannot read a creation's `handoff_sha256`; a creation's `project_key` is NULL until its slot is allocated (`_projects_held`, `:740-745`). | **ADR 0291 §5: with `--token-file` no creation is chosen** — the CLI requires one visible `succeeded` creation and the `app_route`, and presents the token to the project, **whose reset plane accepts only its own creation's token** (ADR 0260, rig 38c: any other 401); it never deletes a file it did not write. **§3: the panel at acceptance names the operation, not a key**; the Connect view repeats the claim line with the key once the creation succeeded, without the token. Not §9's *guess* stop: the project decides, deterministically. | A choice the client cannot read is a choice the server already makes. | 0291 |
| **D2896** | D2869: *"Nothing else on the site is pre-walked"*; `docs/hosted-walk.md`'s statement names six goals. | The site documents goals 3–5 with `apg` lines (`docs/branches`, `docs/plans-and-usage`, `docs/insights-and-monitoring`; rig 46b's list) and **no page names the support bundle** (Run 2 builds it). A goal the statement names and no page reaches is a known gap. | **Run 4 reads each of the statement's six goals against the site and makes each reachable by a browser path on a page** (the console view that does it, the CLI line kept as *"or, from a terminal"*), including one sentence on the support bundle (Settings → *Support bundle*; `apg project diagnostics`). D2869's rule — known gaps repaired; the unknown ones are the walk's. | A goal named and undocumented is a finding the builder already holds. | 0290 |
| **D2897** | ADR 0292 (Run 1): *"the detail is replaced by the check's fixed sentence for its verdict when it carries one"*. | Run 2 read every `detail` the twelve probes produce (`diagnosis.py`'s `_check` calls; `bin/doctor.py`'s probe details): the doctor's own sentences (ADR 0159), the host values in them the disk check's `mount` — **in every verdict, `ok` included** (`diagnosis.py:421-430`) — and the unhealthy containers' names. Whole replacement would blank the disk check on every project, always. | **The reduction keeps the sentence and replaces inside it** every host path (`[a host path]`) and every opaque run of ≥ 32 token characters (`[a value not shown]`), bounded at 300; the project's public URL, times and counts stay (`reconciler_dispatch.diagnostic_detail`). ADR 0292 decision 1 corrected before anything shipped. | The disk check's numbers are the support conversation's first question. | 0292 |
| **D2898** | D2874: *"member and above"*; keys unaddressed. | `control_roles.KEY_SCOPES` decides which routes a key reaches; absent = `403 human_session_required`. Every other project read (`backups`, `insights`, `monitoring`) is `projects:read`. | **`get_project_diagnostics` is absent from `KEY_SCOPES`** — a person's session only (ADR 0292 decision 4); proved by `test_the_route_serves_the_readings_and_the_operations` with a `projects:read` key. | The bundle is a person's page for a support conversation; automation reads `monitoring`. | 0292 |
| **D2899** | Run 2's close list: `tests/contract/test_cloud_cli.py` and `bin/build-cli.py --check`; §2's ids for `CTL-DIAG-001` all in `test_control_diagnostics.py` / `test_cloud_cli.py`. | **`test_cloud_cli.py` does not exist** — the CLI's proofs are `tests/contract/test_control_cli.py`; **`bin/build-cli.py` has no `--check`** (`--out` only; `test_cli_package` builds it); the reconciler's simulated host (`Host`, `Children`) lives in `test_reconciler_dispatch.py`. | The CLI case is `test_control_cli.py::test_diagnostics_writes_a_private_file_once`; the reconciler's pass is proved in `test_reconciler_dispatch.py` (its `Children` learns `doctor`); `test_cli_package` ran for the package. **Run 8 registers the node ids Run 2's **Done.** lists**, never §2's proposals. | The tree's names. | — |
| **D2900** | Run 2 step 6: Settings gains *"a table of check, verdict (chip), detail, age"*; *"no new … heading text (D2829)"*. | The console's chips are `STATE_CHIPS`' five classes for project states, pinned by `test_console_look`; there is no verdict palette and ADR 0288 closes the vocabulary. `test_no_page_names_an_unreachable_row` would refuse `support_bundle` in `pages.json` before the row exists. | **The verdict is text** (`ok`, `warn (stale)`, …) in the table; **the section's label is `<strong>Support bundle</strong>` in a paragraph, no heading**; `pages.json`'s `project-settings` gains the call `GET /v1/projects/{key}/diagnostics` now and **the `support_bundle` Ledger row is added to that view's `ledger` list at Run 8**, with the row. | No new class, no new anchor, no page naming a row that does not exist. | 0288 |
| **D2901** | §9: *"a test outside the ones this plan names would have to move"* is a stop. | A new control function and route widen three exact allowlists by construction: `test_control_set.py` `TABLES`/`GRANTED`/`OPERATOR` and its render counts (9 → 10), `test_reconciler_dispatch.py::test_the_reconciler_asks_the_control_set_only_these` (D2531's closed set), and `main.control_paths()` read by `test_auth_service_shape.py::test_the_control_mode_serves_exactly_the_declared_paths` (which failed once, as designed, until the path was declared). | **Each widened by exactly the new name** (`control_diagnostic_readings`, `control_project_diagnostics`, `control_record_diagnostics`, `/v1/projects/{key}/diagnostics`) — the pattern every control session since 40 followed; not §9's stop: an allowlist widened to the measured set is not a weakened test (CLAUDE.md §6). | The guards did their job: each named the new thing until it was declared. | — |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**One new family, `JRN`** (the stage plan's *Proposed families*): the regex at
`tests/contract/test_acceptance_registry.py:130` gains `JRN` after `UI`, the
family comments one sentence after Session 45's: *Session 46 (ADR 0290-0293)
adds `JRN` for the journey.* `DX`, `CTL`, `OPS` and `CON` are existing families.
**Nine requirements, nine claims, all `target_session: 46`, all P0 — four
offline, four external, one host.** Node ids are **proposed; Run 8 writes what
the runs actually wrote**, read with `pytest --collect-only -q` (D1236, D2129).
Committed by Run 8 with the constant (D690), under **`# Session 46 (ADR
0290-0293)`** at the end.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `CTL-DIAG-001` | The bundle records verdicts, never evidence: the record function takes `{name, verdict, detail}` only, is granted to nobody; the reader is member-scoped; a stopped database is one `asleep` row; a reading older than 1,800 s is `stale`; planted values in a doctor answer are recorded nowhere; the CLI writes 0600 and refuses an existing file | `tests/contract/test_control_diagnostics.py::test_the_record_function_is_granted_to_nobody`, `::test_only_verdicts_are_recorded`, `::test_a_planted_value_is_recorded_nowhere`, `::test_a_stopped_database_reads_asleep`, `::test_an_old_reading_is_stale`, `::test_a_non_member_is_refused`, `tests/contract/test_cloud_cli.py::test_diagnostics_writes_a_private_file_once` | — (`support_bundle`) |
| `CTL-DIAG-002` | Live, as a member through the public origin, no SSH: `slot11-prod`'s bundle lists the twelve checks with ages under 1,800 s and its operations; no host path, no secret in it | — | `tests/external/test_session46_journey.py::test_the_support_bundle_lists_the_twelve_checks`, `::test_the_bundle_carries_no_host_path` (external `support_bundle_live`) |
| `OPS-CTLSTATUS-001` | `control.sh status` reads only (every statement a SELECT), as root, every section answered or named unread, the state from `control_states.project_state`; exit 6 when the database could not be read | `tests/contract/test_control_command.py::test_status_runs_only_selects`, `::test_status_states_are_the_services`, `::test_status_names_an_unread_section`, `::test_status_needs_root`, `tests/contract/test_auth_service_shape.py::test_every_service_module_the_repository_imports_needs_only_the_standard_library[control_states]` | — (`control_status`) |
| `OPS-CTLSTATUS-002` | On the host, after the sweep's deploys: `status --json` agrees with `control.sh registry` (every project, its state), counts slots by state as `slot.sh status` does | — | `tests/deployment/test_session46_control_status_host.py::test_status_agrees_with_the_registry`, `::test_status_counts_the_slots` (host `control_status_host`) |
| `CON-CREATE-001` | The console's creation sends only the token's SHA-256, never the token; shows it once at acceptance; keeps it in no storage; refuses with the server's code; the overview's CLI sentence is gone; `project claim --token-file` claims by the token's own creation | `tests/contract/test_console_create.py::test_only_the_digest_is_sent`, `::test_the_token_is_shown_once_at_acceptance`, `::test_no_storage_is_touched`, `::test_a_refusal_is_the_servers`, `tests/contract/test_cloud_cli.py::test_claim_reads_a_token_file`, `::test_claim_picks_the_creation_by_digest` | — (`console_create`) |
| `CON-CREATE-002` | Live in Chromium through the public origins: a project created in the console from an empty organisation; its token shown once; the operation followed to `succeeded`; the Connect page's string connects | — | `tests/external/test_session46_journey.py::test_the_project_was_created_in_the_console`, `::test_the_token_was_shown_once`, `::test_the_string_connected` (external `console_create_live`) |
| `JRN-001` | The journey, in the site's order, from an invitation link to a deleted project, one node id per step (J1–J14, Run 6), the record pinned to the deployed commit and the site's digest, no SSH | — | `tests/external/test_session46_journey.py::test_j01_the_invitation_link_opened_the_console` … `::test_j14_the_project_was_deleted_and_its_names_refuse`, `::test_this_module_uses_no_ssh` (external `journey_live`) |
| `JRN-002` | The journey's driver, rehearsed against a stand-in console: every step reached in order; a planted foreign request named; a missing step fails the record | `tests/contract/test_journey_driver.py::test_the_rehearsal_reaches_every_step`, `::test_a_foreign_request_is_named`, `::test_a_missing_step_fails_the_record` | — (`journey_driver`) |
| `DX-002` | A person who did not build Stage 5, from the site and an invitation link: the hosted record loads, `kind` person, its site digest the deployed build's, every route a built route, every command a documented line, no file edited, no undocumented step, the criterion reached, transcribed and confirmed | — | `tests/external/test_session46_walk.py::test_a_person_who_did_not_build_this_reached_a_connection_string_from_the_site`, `::test_the_record_names_the_deployed_site`, `::test_every_command_is_on_the_site`, `::test_the_walker_confirmed_the_record` (external `documented_path`, ADR 0290) |

**Expected counts** — Run 8 counts them from the tuples, never from this prose
(D1628): requirements **432 → 441**, `CLAIMS` **339 → 348** (`support_bundle`,
`support_bundle_live`, `control_status`, `control_status_host`,
`console_create`, `console_create_live`, `journey_live`, `journey_driver`, and
**`appliance_documented_path`**, the clone walk's claim; `documented_path` keeps
its name and moves to `DX-002`), `OFFLINE_CLAIMS` **160 → 164**, ADRs **289 →
293**. The four offline in `OFFLINE_CLAIMS` with the per-session assertion in
`test_session_forty_six_gate_modes.py` (D1237: assert THESE are in the set, never
its size). `CLAIM_INTRODUCED_IN` (`tests/contract/test_evidence_claims.py`) gains a
row at 46 for each new claim; **`documented_path`'s row stays where it is**, its
requirement moved under ADR 0290 (a contract change with its ADR — CLAUDE.md §6).

**Existing entries that move:**

- **`DX-001`**: unchanged ids, claim `appliance_documented_path` (ADR 0290).
- **`CON-SERVE-001` / `CON-LEDGER-001`**: none — the console serves no new file;
  its pages guard reads the `projects_self_service` row `trial`.
- **The record-reading modules** (D2885): the session pins gain 46 (Run 7).
- **`THR-*`**: three rows added in Run 8 (`THR-CON-HANDOFF`, `THR-CTL-DIAG`,
  `THR-WALK-RECORD`, threat items 28–30); none removed.

**New environment gates: two** — `APG_JOURNEY_RECORD_FILE` and
`APG_WALK_RECORD_FILE`, in the roster `tests/conftest.py` after `:243`, exported by
the gate's external mode (`--journey-record-file`, `--walk-record-file`).
`APG_DX_RECORD_FILE` stays the host mode's (DX-001). **Read in a test body with
`.get(...)`, never `x["APG_…"]`** (D2381).

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| Control migration **0010** frozen and applied on control-prod | Runs 2, 9 | `bin/migrate.sh --project project.control.example.yaml freeze-lock`; the proposal by `propose --by NAME` (ADR 0243); applied as `migration_user`; `AP900` down; never amended once applied (D912) |
| The quickstart rewritten browser-first, **published on the bump's push** | Runs 4, 8 | Written in Run 4 and parked; landed with the bump (Run 8), live hours before R2d deploys the form — D2840's accepted window; the CLI lines kept as *"or, from a terminal"*, so the page's terminal path is true throughout |
| `CURRENT_SESSION` 45 → 46; `VERSION` 1.23.0 → 1.24.0; two Ledger rows `trial`; `documented_path` moved; THR rows | Run 8 | All-or-nothing (D690); `README.md:7` and every `--session 45` literal on the documented path moved and counted per file (D678/D1484); ADRs 0261, 0290 |
| `bin/session-46-check.sh` | Run 8 | Derived from 45's by diff (D1482); header and usage rewritten whole (D1488); two flags; `SHELL_COMMANDS`; `chmod 755` before `git add` |
| **1.24.0 deployed on the four projects** — no database restart; 0010 applied on control-prod; the console recreated; the reconciler restarted | Sheets R2a–R2d, RC1 (Run 9) | The reconciler stopped (D2178); one project at a time, each window probed; control-prod last |
| **An account for a stranger** (P0) and **their organisation and project on `slot10-prod`**, kept | Run 9 | Invite-only; the account and organisation are never deleted (D2065); the project is a customer's from then on (D2886) |
| `slot3-prod`'s `customer_app` rotated again (W1′); walker accounts and their memberships | Run 9 | As Session 45 (the creds kept `.before-s46`; memberships removed after) |
| **`slot10-prod` and `slot11-prod` declared and provisioned**; `slot11-prod` created, slept, woken, resized, exported, idle-slept, deleted — **consumed**; their grey A records and R2 buckets | Run 9 | One slot at a time (D2870); ONE lifecycle attempt (D2798); a slot is never reused; `slot11-prod`'s identity revoked after the tag (SL4) |
| Tag `1.24.0` on the deployed commit; **`agentic-postgres-cli 1.24.0` published to PyPI** | Run 9 | After the merge exits 5 for the expected claims only (§7); from the WORKSTATION (D2041); `publish-cli`'s `verify` reads that SHA's `contract` success; never re-uploaded |
| **The old host retired**: identities revoked, Cloud projects deleted, the server cancelled, the store's rule removed | Run 10 | After Sheet X0's reading; each its own sheet (D1510) |

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
`test_session12_documented_path`, `test_site` and `bin/build-site.py --check`**;
**a run that touches `services/console/` runs `test_console_server`,
`test_console_pages`, `test_console_scram`, `test_console_sql`,
`test_console_plane`, `test_console_look` and `test_reality_ledger`**; **a run
that touches `bin/cloud.py` runs `test_cloud_cli`, `test_cli_contract` and
`bin/build-cli.py --check`** (read its `--help` first); **a run that touches
`control_routes.py` or the control service runs `test_control_*` and
`bin/app-contract.sh --check`** (regenerate with `--update --snapshot control`);
**a run that touches the control set runs `test_project_migration_sets` and the
control-set apply proofs**; **every new test module carries `pytestmark` before
its first test** (D1240), and the sweep-selector guard (D1242) AND
`test_environment_gates` join the targeted list of any run that adds a module —
**read a model dict with `.get("APG_…")`, never `x["APG_…"]`** (D2381). **A run
that adds a module under `tests/deployment/` runs `test_deployment_suite_shape`**
(D2721; Run 3 adds one). **Every mutation battery** follows CLAUDE.md §1:
`PYTHONDONTWRITEBYTECODE=1`, snapshot to `/tmp` and restore by copy with `cmp`,
anchors pre-flighted (a miss fatal), a control the mutation cannot reach, and
*how* each failed (`FAILED` vs `ERROR`). **Never backticks in an inline heredoc;
any script with a loop goes in a file** (CLAUDE.md §1). **A JavaScript check
runs in the pinned `NODE_RUNTIME_IMAGE`** (`versions.env:18`), as
`test_console_scram.py` does. **A browser measurement runs in the pinned
Playwright image** (`PW_IMAGE`, §0) with the package from `~/s45/walk-home/pw`.

### Run 1 — the rigs, Sheet IR4, ADRs 0290–0293, the threat items, the walk's statement

**Read first:** ADR 0207 whole; ADR 0260; ADR 0273; ADR 0285 `:146-161`,
`:202-209`; `src/agentic_postgres/dx_record.py` whole; `docs/second-walk.md`;
`tests/contract/test_documentation_index.py:700-778`; `bin/cloud.py:640-750`.

0. **Greps** (D979, D1187): `handoff`, `reset-password`, `token-file`,
   `diagnos`, `support bundle`, `control status`, `dx-record`, `second-walk`,
   `hosted` across `docs/plans/`, `docs/decisions/`, `src/`, `bin/`, `services/`,
   `tests/` — each hit read, the list in the **Done.**
1. **Rig 46a — the console's creation** (`~/s46/rigs/46a`, the Playwright image,
   the console served from a throwaway container of the checkout's
   `services/console/` with its own policy and a stub `/api/v1` answering `POST
   /projects` 202 with an operation): (a) a page script under the console's exact
   policy makes 32 random bytes, base64url, and a SHA-256 hex with WebCrypto —
   control: the same in Node (`NODE_RUNTIME_IMAGE`) gives the same digest for a
   fixed input; (b) the request body the stub receives holds the digest and not
   the token (the stub logs bodies to a file); (c) **read-only, against the live
   host, no write**: `curl -i -X OPTIONS
   https://slot3.agenticpostgresql.com/auth/reset-password -H 'Origin:
   https://control.agenticpostgresql.com' -H 'Access-Control-Request-Method:
   POST' -A agentic-postgres-proof` — status and every `Access-Control-*` header
   recorded; control: the same `OPTIONS` without `Origin`. The ADR records what
   a cross-origin claim would need.
2. **Rig 46b — the hosted record against the site** (`~/s46/rigs/46b`, no
   network): build the site at the checkout (`bin/build-site.py --out
   ~/s46/rigs/46b/site`); extract every `apg …` line from the built pages' `<pre><code>`
   blocks (the hosted documented set) and every route; read the digest from a
   page's meta and compare with `site_build.digest()` — control: a page from a
   build with one byte changed in `site/pages/index.md` carries a different
   digest. Record the set's size and the routes' count.
3. **Sheet IR4** (root, read-only; the agent writes `/home/op/s46-ir4.sh` **only
   when the operator says so** — the workstation's classifier refuses an
   agent-written root script for production otherwise, Session 45 Run 1): `time
   bin/doctor.py --project slot3-prod --json` and the same for control-prod —
   wall seconds, `worst`, each check's `name` and `verdict` and the KEYS of its
   `evidence` (never a value). Sizes the reconciler pass (`DIAGNOSTICS_RECORD_SECONDS`,
   the 300 s child budget): **a run above 120 s on either is §9's stop**.
4. **The ADRs**, each indexed in `docs/decisions/README.md`:
   **0290** *A walk of the hosted product is recorded from the site, by a person,
   and is the documented path* (D2867, D2868, D2883, D2889: the `hosted` path and
   its fields and checks, the transcription and confirmation, the freeze,
   `documented_path` → `DX-002`, `appliance_documented_path` → `DX-001`; ADR 0207
   amended, not superseded: its clone record stands for the appliance);
   **0291** *A project is created in the console; its handoff token is shown
   once and the claim stays the client's* (D2864, D2865, rig 46a);
   **0292** *The support bundle is the doctor's verdicts, recorded by the
   reconciler, read by a member* (D2874, IR4); **0293** *`apg control status`
   reads the control database as root and derives states with the service's own
   function* (D2876).
5. **The threat items** in `docs/threat-model.md`'s hosted list: **28** the
   handoff token in a browser tab (shown once; lost if the tab closes before it
   is saved — the project then needs the operator's root reset, said so); **29**
   the support bundle (a member learns the node's verdicts and details of their
   own project — `detail` sentences read for host paths in Run 2; evidence never
   recorded); **30** the walk record (a person's notes carried by the agent —
   transcribed verbatim, confirmed, holding no secret: no password, no link, no
   seed). Table rows land in Run 8.
6. **`docs/hosted-walk.md`** (D2889) — drafted here, its statement read by the
   operator before Run 4 (the operator may reword it; the markers, the URL and
   the goals stay), indexed in `docs/README.md`; its pinning test is Run 6's.
   **The operator names the person and the day** (recorded in the **Done.** as
   *"arranged for <date>"*, never the person's name).
7. **Targeted, once** (documentation pages and ADRs land on `main`, and CI runs
   even when nobody reads it): `test_documentation_index` and the ADR index's
   test (grep `decisions/README` in `tests/`). Commit, push, no CI read.

**Done (2026-10-24; recorded in part at `b46d3ba`, IR4 after it).** Executed at `1b2e3e1` (tree clean); scripts and
transcripts in WSL `~/s46/run1/` and `~/s46/rigs/46a`, `46b`.

- **Greps** (step 0, `~/s46/run1/greps.txt`): `handoff` 93 files —
  `bin/cloud.py` (create/claim), **`bin/project.sh`'s usage also documents
  `claim`** (`:52-55`, Run 4 moves it with `--token-file`),
  `test_control_cli.py`, `test_admin_handoff.py`, `reconciler_dispatch.py`,
  `control_client.py`, `test_session41_reearning.py`; `reset-password` 23
  (`routes.py`, `main.py`, ADR 0173/0260); `token-file` only this plan;
  `diagnos` 233 (the doctor's tree — no route, contract or CLI hit, as §0
  says); `support bundle` 6 (plans, one docstring in
  `test_generated_client_runtime.py:647`); `control status` 4, all plans;
  `dx-record` 85 (every session gate since 18 carries `--dx-record-file`);
  `second-walk` 15 (`dx_record.DOCUMENT_ROOTS`, `test_session12_documented_path.py:45`,
  `test_documentation_index.py:695`, registry `:3956`, `bin/dx-record.sh:46`);
  `hosted` 66 — none a reader of the walk record.
- **Rig 46a** (the console's creation; Chromium in `PW_IMAGE` against a rig
  server sending `serve.security_headers("wss://sql.agenticpostgresql.com")`
  imported from the checkout): WebCrypto under the exact policy —
  `isSecureContext` true, a 43-character base64url token, SHA-256 hex; **the
  digest equal in Chromium, Node (`NODE_RUNTIME_IMAGE`) and Python** for a fixed
  input (`7df3c0ae…`) and for the page's random token; **policy control**: an
  inline script under the same headers did not run; the stub's one logged body
  **held the digest and not the token**, answered 202. **(c), read-only, live**:
  slot3-prod's `/api/app/auth/reset-password` answers `OPTIONS` **405, `allow:
  POST`, no `Access-Control-*` header**, with and without `Origin` (D2890: the
  plan's path was the edge's 404). The first run found **D2892**
  (`wait_for_function` refused by the policy).
- **Rig 46b** (the hosted record against the site, no network):
  `bin/build-site.py` → **23 files, 16 HTML pages, 16 routes**, one
  `apg-site-digest` on every page = `site_build.digest()` = `dce4308c…` at
  `1b2e3e1`; **control**: one letter changed in a prose line of
  `site/pages/index.md` in a `git archive` copy → `a6939bcb…` (a change inside a
  link is refused by the builder, exit 3); **24 code blocks, 42 distinct `apg`
  lines, 30 `apg <noun> <verb>` prefixes**, every one with a placeholder
  (D2893); other code lines `pipx` ×3, `uv` ×1, one connection-string template.
  The digest's inputs are wider than §1 named (D2891).
- **Sheet IR4**: the operator's word given; `/home/op/s46-ir4.sh` written as
  `op` (sha256 `9d0651d6…`, identical to `~/s46/run1/s46-ir4.sh`; host checkout
  `4f4b207`). **Run by the operator at 11:53Z** (`/home/op/s46-ir4.txt`, read
  by the agent as `op`): **`slot3-prod` exit 0, 7.7 s; `control-prod` exit 0,
  6.6 s**; twelve checks each (`route health` is one), every one `ok`; the
  evidence keys include `mount`, `heartbeat_holder` and `url` — the values ADR
  0292 never records. **Under §9's 120 s: no stop; ADR 0292 Accepted.**
- **ADRs**: **0290** (the hosted record path, `documented_path` → `DX-002`,
  `appliance_documented_path` → `DX-001`; amends 0207, whose status line says
  so), **0291** (the console creates; the token shown once at acceptance; the
  claim stays the client's, `--token-file` chooses no creation — D2895),
  **0292** (the support bundle — accepted on IR4; the record function
  `SECURITY INVOKER` per the tree, D2894), **0293** (`control.sh status`,
  `control_states` shared). All four indexed in `docs/decisions/README.md`.
- **Threat items 28–30** in `docs/threat-model.md`'s hosted list (the handoff
  token in a tab, the support bundle, the walk record); table rows at Run 8.
- **`docs/hosted-walk.md`** drafted (the statement between
  `<!-- walk-statement:begin -->` / `end`: the site's address, the invitation,
  six goals, the notes' plain-text form, no repository path, no command, no
  hint), indexed in `docs/README.md`. **For the operator to read before Run 4**;
  **the person and the day: not yet arranged** (the operator, 2026-10-24).
  D2896: Run 4 makes each of the statement's six goals reachable from a page.
- **Targeted, once**: `test_documentation_index`,
  `test_session12_documented_path`, `test_repository_contract`,
  `test_acceptance_registry`, `test_edge_config`, `test_mcp_catalog` — **375
  passed**, exit 0.
- Rows **D2890–D2896**. **Next free D2897, ADR 0294.**

### Run 2 — the support bundle (0010, the reconciler, the route, the CLI, the console)

**Read first:** ADR 0292; `0006-control-branches.sql:93-120`, `:403-485`
(`control_backup_readings`, `control_record_backups`); `0004:284-310`, `:660`;
`bin/reconciler.py:1205-1230`, `:1405-1440`, the loop that schedules
`record_backups` (grep `BACKUP_RECORD_SECONDS`); `src/agentic_postgres/reconciler_dispatch.py:184-218`;
`control_routes.py:1213-1235` (`get_backups`) and its service/repository
callers; `tests/contract/test_doctor_redaction.py`; `bin/cloud.py` `project
backups`.

1. **Tests first** (`tests/contract/test_control_diagnostics.py`, §2's ids; the
   CLI case in `test_cloud_cli.py`): each written failing, its failure read.
2. **`0010-control-diagnostics.sql`** (D2874): the table, FORCE RLS, the record
   function (one upsert per `(project_key, check_name)`, a whole slot's rows
   replaced in one call), the member reader (`control_enter`, the project's
   organisation), REVOKEs, the grant to `{{auth_service}}` on the reader only;
   `AP900` down. **No `--` inside a string literal** (D2544). Frozen
   (`bin/migrate.sh --project project.control.example.yaml freeze-lock`) and
   proposed (`propose --by NAME`); the control lock and the proposal committed.
3. **The reconciler**: `RECORD_DIAGNOSTICS_SQL` in `reconciler_dispatch.py`;
   `diagnostics_of(key, document)` beside `backups_of` (the database stopped →
   one `asleep` row; else `doctor.py --project KEY --json` under `_quiet(…,
   300)`, each check reduced to `{name, verdict, detail}` by a pure function in
   `reconciler_dispatch` — **the reduction is the tested unit**); `record_diagnostics`
   scheduled every 900 s like `record_backups`; a failed doctor run records
   nothing for that slot and says why (ADR 0195).
4. **The route** `GET /v1/projects/{key}/diagnostics` (member and above; the
   readings, `read_at`, `stale` past 1,800 s, `operations` from
   `control_project_operations`); the contract regenerated
   (`bin/app-contract.sh --update --snapshot control`), `--check` clean.
5. **The CLI** `apg project diagnostics [--project-key K] --output FILE [--json]`
   (written 0600, refused if it exists, checked before the request);
   `bin/project.sh` shim if the family needs one (read how `project backups` is
   wired first).
6. **The console**: Settings (`projectSettingsView`, `app.js:620`) gains a
   *Support bundle* section — a table of check, verdict (chip), detail, age —
   through `h` only; the walk drivers' anchors unchanged (no new `code.secret`,
   `role=status`, textarea or heading text, D2829).
7. **Battery** (`~/s46/run2/battery2.py`): evidence passed through the reduction;
   the reader's member check removed; the grant widened to PUBLIC; `asleep`
   folded into twelve failures; `stale` dropped; the CLI's 0600 → 0644 — each
   FAILED with its control green, restored `cmp`-identical.
8. Targeted (the lists above), ruff, commit, push, CI.

**Done (2026-10-24).** Scripts and transcripts in WSL `~/s46/run2/`.

- **Tests first** — 26 written and run red before any product code
  (`red.txt`): **26 FAILED, 0 ERROR**, each for its reason (the functions, the
  route, the verb absent). Green after (`green.txt`): 27 passed (the 26 + the
  interval test).
- **Control set `0010-control-diagnostics.sql`** (manifest `20261024120010`):
  `app.control_diagnostic_readings` (`position` keeps the doctor's order;
  verdict CHECK `ok|warn|problem|unknown|asleep`; detail ≤ 300), FORCE RLS;
  `control_record_diagnostics(jsonb)` **`SECURITY INVOKER`, granted to nobody**
  (D2894), a project's set replaced whole, `{checks}` (1–32 of exactly `name`,
  `verdict`, `detail`) or `{asleep: true}` — anything else, an `evidence`
  member included, `AP422: invalid_readings`; `control_project_diagnostics(uuid,
  text)` definer, `control_enter` + `control_require_role(…, 'member')`,
  granted to `{{auth_service}}`; `AP900` down; no `--` in a literal. **Lock
  frozen** (10 migrations, follows 20261003120039); **proposal `65645f2c…`**
  (`--by "claude-opus-5-5 Session 46 executor"`): lint passed, dev apply 49
  migrations from empty in 23.3 s, exit 0; 17 destructive findings, **none new**
  against Session 42's `e131442a…`.
- **The reduction** `reconciler_dispatch.diagnostics_reading` /
  `diagnostic_detail` / `diagnostics_asleep` (D2897), `RECORD_DIAGNOSTICS_SQL`
  (the closed set's fifteenth call). **The reconciler**:
  `DIAGNOSTICS_RECORD_SECONDS = 900` (= `operations.DIAGNOSTICS_RECORD_SECONDS`,
  held by a test), `DIAGNOSTICS_CHILD_SECONDS = 300`, `diagnostics_of` (a
  stopped database → `asleep`, no doctor; else `doctor.py --project KEY --json`,
  exit 0/6 carry a document, anything else records nothing and says why),
  `record_diagnostics` in `run`'s loop after the usage pass.
- **The route** `GET /v1/projects/{key}/diagnostics` (`control_service.diagnostics_document`:
  `read` / `asleep` / `stale` > 1,800 s / `could_not_determine`, each check's
  `read_at`, `age_seconds`, `stale`; the newest 50 operations); MATRIX `ACCOUNT`,
  member in the service and in SQL, **not in `KEY_SCOPES`** (D2898);
  `main.control_paths()` gains it; the control snapshot regenerated (+68 lines),
  `bin/app-contract.sh --check` clean. `docs/control-plane.md` gains *The
  support bundle (Session 46)*.
- **The CLI** `apg project diagnostics [--project-key K] --output FILE [--json]`
  (`bin/cloud.py`; `bin/project.sh`'s usage, verb list and exit text): the output
  refused before the request, written 0600, exit 6 for `stale` /
  `could_not_determine` with the file written.
- **The console**: `supportBundle(served)` in Settings — a `<strong>` label
  (no heading, D2829), the status sentence, a table check/verdict/detail/age,
  a viewer's 403 shown in place; `pages.json` gains the call (D2900).
- **Battery** (`battery2.py`, `battery2.txt`): **7/7 killed**, every control
  green, every file restored `cmp`-identical — M1 evidence passed through the
  reduction (2 targets FAILED), M2 the reader at `viewer`, M3 the writer granted
  to PUBLIC, M4 asleep folded into a doctor run, M5 `stale` dropped, M6 the
  CLI's file 0644, M7 the host path kept (the two SQL mutations re-froze the lock
  inside the battery and restored it).
- **Targeted, once** (`shard.sh A–D`): A 179 passed + 1 failed
  (`test_the_control_mode_serves_exactly_the_declared_paths` — the path not yet
  in `main.control_paths()`, D2901; declared, the module re-run alone: 49
  passed); B 39 passed; C 97 passed; D 1,147 passed. Ruff clean.
- **Node ids for Run 8** (`CTL-DIAG-001`), as written:
  `tests/contract/test_control_diagnostics.py::test_only_verdicts_are_recorded`,
  `::test_a_planted_value_is_recorded_nowhere`, `::test_a_long_detail_is_bounded`,
  `::test_an_answer_not_in_the_shape_asked_for_records_nothing`,
  `::test_a_sleeping_slot_is_one_reading_not_twelve`,
  `::test_a_fresh_reading_is_read_with_its_ages_and_operations`,
  `::test_an_old_reading_is_stale`, `::test_no_reading_is_said_never_an_empty_pass`,
  `::test_the_staleness_bound_is_two_of_the_reconcilers_intervals`,
  `::test_an_asleep_reading_is_named`, `::test_the_record_function_is_granted_to_nobody`,
  `::test_the_writer_refuses_evidence_and_unknown_shapes`,
  `::test_a_stopped_database_reads_asleep`, `::test_a_non_member_is_refused`,
  `::test_the_route_serves_the_readings_and_the_operations`;
  `tests/contract/test_reconciler_dispatch.py::test_the_diagnostics_pass_records_verdicts_never_evidence`,
  `::test_a_sleeping_slot_is_recorded_asleep_without_a_doctor`,
  `::test_a_doctor_that_gave_no_reading_records_nothing`;
  `tests/contract/test_control_cli.py::test_diagnostics_writes_a_private_file_once`.
- Rows **D2897–D2901**. CI: see below.

### Run 3 — `apg control status`, `control_states` shared, the node-loss runbook

**Read first:** ADR 0293; `bin/control.py` whole; `services/auth-api/app/control_states.py`
whole; how the repository loads `plans` from the service (grep `plans` in
`src/agentic_postgres/plans.py` and `tests/contract/test_auth_service_shape.py:93-168`);
`docs/node-loss-runbook.md` whole; `docs/operator-guide.md` §20.

1. **Tests first** (`test_control_command.py` cases of §2;
   `tests/deployment/test_session46_control_status_host.py` written and
   **parked** in `~/s46/run7/park/` until Run 8 — a host module without its
   registry fails `test_deployment_suite_shape`, D2721/D2787).
2. **`control_states`** joins `SHARED_MODULES`; `src/agentic_postgres/control_states.py`
   loads it the way `plans.py` does (no copy of the rules).
3. **`control.sh status [--json]`**: the usage line, the `case`, `--help` before
   root; `control.py`'s `status` — the sections of D2876, each one SELECT through
   `psql()`, the state computed from the operation rows by `project_state`;
   `--json` the same document; exit 0 / 6.
4. **The runbook** (D2877) and `docs/operator-guide.md` §20 (one paragraph:
   *status* beside `registry`).
5. **Battery**: a write slipped into a section; the state computed in SQL instead
   of by the shared function; an unread section folded to empty; root not
   required — each FAILED, controls green.
6. Targeted (+ `test_cli_contract`, `test_disaster_kit`,
   `test_documentation_index`), ruff, commit, push, CI.

**Done.**

### Run 4 — the console creates a project; `claim --token-file`; the site browser-first

**Read first:** ADR 0291; `app.js:52-140` (`h`, `show`, `refusal`, `field`,
`once`, `table`, `waitFor`, `outcome`), `:389-424`, `:436-478`; `api.js` whole;
`bin/cloud.py:640-750`; `site/pages/quickstart.md`, `site/pages/docs/projects.md`,
`getting-started.md`; the console walk's and the editor walk's anchors
(`tests/external/browser/console_walk.py`, `sql_walk.py`).

1. **Tests first** (`tests/contract/test_console_create.py` in the Node image,
   the `--token-file` cases).
2. **The console** (D2864, D2865): the overview's sentence (`:405-408`) replaced
   by a *New project* link per organisation where the caller is a member or
   above; a `newProject` view (name `maxLength` 64, profile select of the three,
   administrator's username) — **the token made and digested in the page, the
   body `{organization, name, profile, admin_username, handoff_sha256}`**; on
   202 the shown-once panel with the token and the claim line, a *Copy* control
   as the existing panel has, and *I have saved it* to dismiss (the token
   dropped); then `waitFor` the operation and a link to the project's Connect
   page. A refusal is `refusal(error)` (the server's code and words). **No
   `localStorage`, `sessionStorage`, cookie or IndexedDB write** (the test greps
   the scripts). The route `#/org/<id>/new-project` added to the router.
3. **`apg project claim --token-file FILE`**: read once (0600 required, refused
   otherwise), the creation chosen by `sha256(token)` against the succeeded
   creations' recorded digests — **read where the digest is visible to a member
   first** (the operation row's arguments, or the handoff column; if none is
   visible to a member, the token's creation is the ONE succeeded creation of
   that key with no held file, and two such is a refusal — the rule written in
   ADR 0291 from what the tree shows); the existing held-file path unchanged.
4. **The site** (D2869): `quickstart.md` — accept, *New organisation*, the
   second factor, **New project in the console** (the token: save it, it is
   shown once; the claim is optional and needs the CLI), Connect; *"or, from a
   terminal"* keeps today's CLI lines; `projects.md`'s *Claiming* says the same;
   `getting-started.md` the account invitation's first step (*New
   organisation*). **Written, built (`bin/build-site.py --check` on a scratch
   copy) and PARKED in `~/s46/run4/park/`** — never pushed in this run (§4);
   Run 8 lands them with the bump.
5. **Rehearse both walk drivers offline** (`console_walk.py --rehearse`,
   `sql_walk.py --rehearse`): a driver that needs a change is a row.
6. **Battery**: the token sent; the panel shown after the wait instead of at
   acceptance; a storage write; `--token-file` accepting 0644; the claim
   choosing the first row — each FAILED, controls green.
7. Targeted (console, CLI, site lists), ruff, commit, push, CI (`contract`,
   `site`); the live site read (`curl -A agentic-postgres-proof`) after `site`.

**Done.**

### Run 5 — the small repairs: `doctor usage`'s witnesses, the docstring, D2801

**Read first:** ADR 0289; `usage_reading.py:160-220`; `bin/doctor.py:930-1000`;
`tests/contract/test_usage_sampler.py`; `tests/external/test_session45_idle.py`;
`tests/deployment/test_session32_workflows.py:940-1010`;
`services/auth-api/app/workflow_worker.py:380-420` and the `mcp` refusal table it
reads.

1. **D2880**: failing tests first (`test_doctor_usage` or the module that pins
   `STORE_EMPTY_REASONS` — grep it); `usage_reading.requests_total(key)`; the
   doctor's figure through it; ADR 0289 *Amended* sentence.
2. **D2881**: the docstring.
3. **D2882**: the reading first (the plane's answer to a revoked token, offline);
   then the repair it decides (§1); the **Done.** names which arm.
4. **Battery**: the witness loop skipped in the doctor; a single witness
   accepted; (D2882's repair reverted) — each FAILED, controls green.
5. Targeted, ruff, commit, push, CI.

**Done.**

### Run 6 — the hosted walk record; the journey's driver and proofs

**Read first:** ADR 0290; `dx_record.py` whole; `bin/dx-record.py`;
`tests/deployment/test_session12_reuse.py:235-326`; `tests/contract/test_dx_record*.py`;
`tests/external/browser/console_walk.py` and `site_look.py` whole (the driver
shape, the record shape, `--rehearse`); `tests/external/test_session43_console.py:190-260`.

1. **`dx_record` `hosted`** (D2867): the fields, `shape_problems` per path,
   `hosted_problems(record, built)` (digest, routes, commands, goals, the
   transcription and confirmation), the clone path's behaviour byte-for-byte
   unchanged (its tests untouched); `bin/dx-record.py check --path hosted
   --record F` (builds the site in memory from the checkout; exit 5 on a
   finding; `digest` refused for `hosted`, exit 2). Tests first
   (`test_dx_record.py` cases for `hosted`).
2. **`tests/external/test_session46_walk.py`** (DX-002's four, `pytestmark`
   external, the record from `APG_WALK_RECORD_FILE`, the module opening no SSH).
3. **The journey's driver** `tests/external/browser/journey_walk.py`
   (`console_walk.py`'s shape; `--rehearse`, `--dry`, `--out DIR`): **J1** the
   membership link opened (the probe mints it, D2871) → **J2** the account made
   → **J3** sign-in → **J4** *New organisation* `lifecycle-s46` → **J5** the
   owner's factor enrolled (the seed captured to `DIR/totp-seed`, 0600) and
   signed in again → **J6** *New project* (profile `small`) accepted, the token
   read from the panel to `DIR/handoff-token` (0600), dismissed → **J7** the
   operation followed to `succeeded` (≤ 3,900 s) → **J8** Connect: `customer_app`
   rotated, the string read → **J9** the string connects (`psql` from the
   workstation, `sslmode=verify-full`, `SELECT 1`) → **J10** the SQL editor:
   `SELECT 1` on the pooled door → **J11** Usage, Insights, Monitoring, Plan,
   Notifications each render a reading or *not read* (never a blank) → **J12**
   Settings' *Support bundle* lists twelve checks with ages (waits up to 1,800 s
   for the first pass) → **J13** sign out. **J14** (the project deleted and its
   names refuse) is read from the lifecycle record that continues the journey.
   The record (0600): `session` 46, `source_commit` from the project's registry
   row, `site_digest` read at J1, each step's time and outcome, every request's
   origin (the look driver's rule), the operation id, the paths of the 0600
   files; the walker removed from `probe-s37` after J5.
4. **`tests/external/test_session46_journey.py`** (JRN-001's J1–J14,
   CON-CREATE-002's, CTL-DIAG-002's, the no-SSH proof) and
   **`tests/contract/test_journey_driver.py`** (JRN-002: the rehearsal against a
   stand-in, as `test_console_walk`'s rehearsal does).
5. **Battery**: a record missing J8; a request off the origin; the digest of
   another build; a `hosted` record with `kind: agent`; a command not on the site;
   `confirmed_by_walker_at` absent — each FAILED, controls green.
6. Targeted, ruff, commit, push, CI.

**Done.**

### Run 7 — the trip's instruments, written and rehearsed offline

**Read first:** `~/s45/run7/` whole (the list in §0), `~/s45/run9/NOTES.md`,
this plan's Run 9 and appendix.

1. **`~/s46/run7/s46-derive.py`** from `s45-derive.py`: every `s45-` script →
   `s46-`, `slot9-prod` → `slot11-prod` for the lifecycle's, the session numbers
   — **on the bodies only, the header split off first** (Session 41's lesson);
   the counts and the diffs read; `s46-post-derive.py` holds every hand edit.
2. **`s46-lifecycle.py --from-journey RECORD`** (D2872): the probe's steps,
   `logout`, `login` as the journey's account (its password and seed files from
   the record's paths), `finish_create(<op>, None)`, `claim --token-file`; the
   record names `create_source: journey`. **Grep every reader** of the fields
   D2872 lists in `tests/external/` and `tests/deployment/` and move what assumes
   the instrument's own creation (each a row).
3. **`s46-journey.sh`** (the driver in the Playwright image, the D2796 detached
   form: `jr-start.sh`), **`s46-hostyaml.py`** (TWO slots, the comment it inserts
   read — D2727), **`s46-dns.sh`** for each slot, **`s46-walk-record.py`** (the
   transcriber: the person's plain-text notes → the `hosted` record, every
   sentence carried verbatim, the digest and the site commit filled from the
   live site and the `site` run, prints the JSON for the person to read; refuses
   a note that holds what looks like a password, a URL with a fragment, or a
   base32 seed), the walks' scripts (`s46-walk.sh`, `s46-sql.sh`, `s46-look.sh`),
   `s46-sweep.sh` + `s46-launch.sh`, `s46-external.sh` (`--journey-record-file`,
   `--walk-record-file`), `ext-start.sh`, `life-start.sh`, `br-start.sh`,
   `br-delete.sh`. **Copy every host-side helper a WSL script calls to the host
   with its sheet** (D2861).
4. **The session pins widened to 46** (D2885), count-asserted per file, parked
   for Run 8.
5. **Rehearsals**: the journey driver against its stand-in (exit 0, then a
   planted foreign request named); the lifecycle's `--from-journey` against
   `rehearse_lifecycle46.py` (Session 41's rehearsal shape, derived); the
   transcriber on a sample note (and on one holding a planted seed — refused).

**Done.**

### Run 8 — the bump, the registry, the gate, two rows to `trial`

**Read first:** §2 whole; `src/agentic_postgres/__init__.py:1380-1450`; Session
45's Run 8 (`session-45-implementation-plan.md:1182-1282`) — the list to copy;
`bin/session-45-check.sh:1-240`; `tests/contract/test_session_forty_five_gate_modes.py:40-120`.

1. **The constant and the version**: `CURRENT_SESSION = 46` with Session 46's
   paragraph (ADR 0162's form in the LAST paragraph — D2794); `VERSION`
   `1.24.0`; `README.md:7`; every `--session 45` literal on the documented path
   moved and counted per file; the guides' release lines and the upgrade table's
   1.24.0 row (*"no database restart; control migration 0010 on the control
   project; the console recreated; restart the reconciler after the checkout
   moves"*). **The price** by D1624's rig against the deployed `4f4b207`.
2. **The registry**: §2's nine, node ids from `pytest --collect-only -q`; the
   regex gains `JRN`; `CLAIMS`, `OFFLINE_CLAIMS`, `CLAIM_INTRODUCED_IN`;
   `documented_path` → `DX-002`, `appliance_documented_path` → `DX-001`; the two
   roster entries; the parked modules unparked.
3. **The gate**: `bin/session-46-check.sh` from 45's by `sed` into a copy, the
   header and usage rewritten whole, `--journey-record-file` and
   `--walk-record-file` (external only) — **`diff` read whole, every hunk named**;
   `SHELL_COMMANDS`; `test_session_forty_six_gate_modes.py` from 45's with the
   two export tests.
4. **The Ledger** (D2884): `projects_self_service` → `trial`; `support_bundle`
   new `trial`; `bin/render-reality-ledger.py --write`. **Run 4's parked site
   pages landed** (count-asserted copies; `test_site`, `bin/build-site.py
   --check`).
5. **The threat rows** `THR-CON-HANDOFF`, `THR-CTL-DIAG`, `THR-WALK-RECORD`.
6. **The derived documents** (CLAUDE.md §5's list).
7. **Battery** (`battery8.py`): the gate's literal; each record's export
   dropped; a `trial` row naming another session's claim; `JRN` out of the
   regex; `documented_path` left on DX-001; an offline claim undeclared; a
   roster entry dropped — each FAILED, controls green.
8. **The gates, in shards, once** (`~/s46/run8/` from `~/s45/run10/`'s by diff;
   `TMPDIR=~/s46/tmp`; each shard `timeout 570` in the foreground; the JUnit
   merged; the total against the collected count): `bin/session-01-check.sh`
   and `bin/session-46-check.sh --mode offline`. Commit before the gates, push
   after both pass, read CI. Then a documentation commit recording the gates.
   **From this push the site's digest inputs are frozen until the person's
   record is confirmed** (D2883).

**Done.**

### Run 9 — the sitting: the release, the dry runs, the person's walk, the journey, the re-earning, the sweep, the tag

**Read first:** this plan's appendix (every sheet) and §7; Session 45's Run 9
**Done.** and rows D2858–D2861 (*what went wrong*, D977); `~/s45/run9/NOTES.md`.
**Before the first sheet**: the checkout on the host moved to the Run 8 commit by
bundle (`git bundle` + `scp` to `/tmp/apg-<sha>.bundle`, `git fetch`, `git
rev-parse FETCH_HEAD` confirmed, `git checkout --detach`), `uv sync` only if a
dependency file moved, the renders of the four projects (`--render-only` as
`op`), `pytest --setup-plan` of `test_session46_control_status_host.py` with the
variables set; the Playwright image present; **the person's day confirmed by the
operator**.

1. **R1** → **R2a** beta-dev, **R2b** alpha-dev, **R2c** `slot3-prod` (`slot.sh
   redeploy`), **R2d** control-prod (0010 applied; the console recreated) — each
   with `s46-window.py`, each read by `s46-after.sh` before the next (D1510); **no
   database restart**. After R2d: `GET /v1/projects/slot3-prod/diagnostics` as
   the probe (401 → sign in → 200, readings arriving within 900 s of RC1); the
   console 200; the relay healthy. **RC1**.
2. **A1**, **RA** (after the last deploy, D2494), **K1**.
3. **V1**, **X0** (the Session 46 modules excluded), **W0′**, **E0**, **L0**, and
   **`control.sh status`** read once by the operator (Sheet CS). **If any
   fails: repair, move the commit, redeploy all four** (no slot consumed yet).
4. **W1′**, **E1** (as Session 45).
5. **H1** (both slots declared, D2870); **SL1–SL3 for `slot10-prod` alone**
   (DNS three grey A records and the two R2 buckets by the agent through the
   Cloudflare API; the B2 bucket + key, the R2 tokens and the six Infisical
   secrets by the operator — `bootstrap-providers --plan` names them; SL1b the
   shape read; SL2 materialised; SL3 `slot.sh status` `ready`); **RC1**.
6. **The person's walk** (Sheets **P0**, **PW**, **PR**): the operator mints the
   account invitation and sends it with the statement; the person walks
   (expected 60–120 minutes; the creation alone ~25); **A1″** reads `slot10-prod`
   allocated as soon as the person's creation is accepted; the person returns
   their notes; the agent transcribes (`s46-walk-record.py`), the person reads
   and confirms; the record checked (`apg dx-record check --path hosted`).
   **Findings are recorded, never argued** — a non-empty `undocumented_steps`
   means `documented_path` fails at this release, and §10's second walker is the
   operator's choice.
7. **SL1′–SL3′ for `slot11-prod`** (only now, D2870); **RC1**.
8. **The journey and the re-earning** (D2872): **J1** `jr-start.sh` (detached;
   the driver through J13); then **`life-start.sh --from-journey`** (detached,
   ONE attempt; org `lifecycle-s46`; **K2** at its pause, only when the
   instrument asks — D2803); the branches on `slot3-prod` (`br-start.sh`,
   detached, after E1); **A1′**; **B1** (the reboot; `s46-after-reboot.sh` BEFORE
   any sweep, with `s46-units.sh` copied first — D2861; `s46-branches.py
   --after-reboot`; the relay healthy by itself).
9. **E0 again** and **L1** after B1 (D2838).
10. **S1** — the one sweep; **then the branch `--delete-only`** (D2647); **then
    the external half** from WSL (`s46-external.sh` with the lifecycle, branch,
    console, editor, look, journey and walk records); then **the merge** with the
    CI artifact's offline half for the deployed SHA. **Exit 5 for the expected
    claims only** (§7).
11. **The tag** from the workstation: `git tag -a 1.24.0 <sha> -F msg.txt`, `git
    push origin 1.24.0`; `publish-cli` read; PyPI `info.version` `1.24.0`; `apg
    --version` → `apg 1.24.0` in a clean `python:3.12-slim` (retry once after
    ~15 s — the simple index lags).
12. **SL4** — `slot11-prod`'s identity revoked after the tag; **RC1** active.

**Done.**

### Run 10 — the old host retired (M7 X1/X2)

1. **X0** (the operator reads the old host; the agent compares with
   `docs/plans/session-38-migration-plan.md` Run M6's final state) — anything
   running, or a volume missing, is §9's stop.
2. **X1**, **X2**, **X3** — each its own sheet, read before the next.
3. **Documentation**: the migration plan's Run M7 **Done.** (the X sheets'
   outcomes, dated); `docs/secret-store.md` §1 (the rule gone); CLAUDE.md §2's
   OLD HOST row (at the close). Commit, push, no CI read.

**Done.**

### Run 11 — the close (Stage 5's)

1. **The Ledger** from the TAGGED evidence (`evidence/session-46.json`):
   `projects_self_service` and `support_bundle` per D2884; the five rows of
   D2878; **every row re-read against the evidence, one line each in the
   Done.**; `support_access`'s clause per D2875; **no row `trial`**;
   `docs/reality-ledger.md` regenerated.
2. **The envelope**: a Session 46 section — the person's times (link →
   account → organisation → creation accepted → string; each goal), the
   console's creation (accepted → succeeded), the journey's steps, the bundle's
   pass (per slot seconds, IR4's and the host's), `control.sh status`'s wall
   time, the release windows, the eighth re-earning (create from the journey,
   wake, resizes, export, the idle sleep), B1, the suites; `UNMEASURED` loses
   only what was measured (the plane at rest if Sheet CS read it).
3. **`docs/scope-closure.md`**: **§39** (*What Session 46 closed, what it left,
   and what Stage 6 inherits*) in §38's shape — **and §28's lists re-audited row
   by row** (each row of *what Stage 5 inherits*: closed by which session, or
   still open and why), the stage plan §10's *Created by Stage 5* list read the
   same way.
4. **The stage plan**: the Status block rewritten — **STAGE 5 CLOSED**, the
   tagged commit, the evidence, the next job (Stage 6's plan, from the report).
   This plan's Status COMPLETE.
5. **`docs/operator-guide.md`**: the release row 1.24.0 / 46; §26 (the support
   bundle's pass, `control.sh status`, the two kept customer projects redeployed
   by every release).
6. **The handoff** (outside the repository): the launch folder's `CLAUDE.md` §2
   and §3.0 rewritten for Stage 6's planner (copied to the scratchpad first);
   the project memory's state file.
7. Targeted: `test_reality_ledger`, `test_evidence_claims`,
   `test_documentation_index`, `test_capacity_envelope`, `test_site`,
   `test_console_pages`, `test_session12_documented_path`.
   `bin/session-01-check.sh` once (generated artefacts moved). Commit, push, CI.

**Done.**

### Run 12 — the Stage 6 decision report

1. **`~/s46/run12/fill.py`** (the Session 35 filler's method,
   `~/s35r11/s35-r11-fill.py`): every number read from
   `evidence/session-46.json`, `capacity.ENVELOPE` and the tree at the tagged
   commit, asserted, a placeholder refused.
2. **`docs/stage-6-decision-report.md`**: §1 what 1.24.0 is; §2 what was measured;
   §3 what stayed `failed` or `not_run`, and why; §4 what Stage 5 built against
   its specification, session by session (36–46, each with its claims added and
   how they stand); §5 **the Stage 6 question priced** — the vision's
   assumptions against Stage 5's readings (a branch's measured creation and reset
   times; one ext4 disk; a project as 10–12 containers and 192–840 MiB admitted;
   slots hand-prepared, their operator minutes; hosted customers who cannot
   configure the agentic layer; the walk's findings; the review's five
   decisions); §6 **the recommendation**, the executor's reading of §1–§5,
   answering the specification's §65 question — *which bonsai implementation is
   the most important bottleneck or false assumption to replace next* — **marked
   as that reading, for the operator to accept or rewrite before it is
   committed**.
3. **The operator reads §6**; their words or acceptance recorded; the inputs
   committed under `docs/stage-6/` only at their word (D2887).
4. `test_documentation_index` (the new page indexed in `docs/README.md`);
   commit, push, no CI read (documentation).

**Done.**

---

## 7. Evidence and claims

**Expected at the merge** (Run 9): **348 claims** (164 offline). **`failed`:
`appliance_documented_path`** (D1935, the Session 25 record — said so), and
**`documented_path` only if the person's record carries a finding** (ADR 0290: a
finding is a fail, never argued). Everything else **passed** — `journey_live`,
`console_create_live`, `support_bundle_live`, `control_status_host`, and every
Session 38–45 lifecycle, branch, console, editor and look proof re-earned at
1.24.0 on `slot11-prod`, `slot3-prod`, W1′, E1 and L1. Predictions, each moved
only by the evidence.

**The three modes.** Offline: CI's artifact for the deployed SHA (164 claims).
Host: S1 with Session 45's flags renamed (`--lifecycle-record-file` the Session
46 record, `--live-slot-outputs` `slot11-prod`'s K2 copy, `--dx-record-file` the
Session 25 record as before). External: from WSL with `--control-outputs`,
`--control-probe-file`, `--lifecycle-record-file`, `--customer-credential-dir`,
`--console-record-file`, `--sql-editor-record-file`, `--look-record-file`,
**`--journey-record-file`** (J1's) and **`--walk-record-file`** (the person's).
**The Session 46 customer proofs reach only the site's origins, the console's
origin, the control route and the doors, and open no SSH.** **Deploy every
project fully, THEN the dry runs, THEN W1′ and E1, THEN the person, THEN the
journey and the re-earning and B1, THEN E0 again and L1, THEN sweep, THEN
external — every half at one commit; THEN the tag; THEN the publish.**

**What is not in the evidence, by construction**: the PyPI install; the
operator's reading of §6 of the report; the old host's retirement. Recorded in
the runs' **Done.**

---

## 8. Security invariants this session touches

| Invariant | How this session keeps it |
|---|---|
| **The control plane holds nothing that opens a project's data** (ADR 0246) | The handoff token never reaches it (only its SHA-256, as the CLI); the bundle is written by the root reconciler, the plane only stores verdicts |
| **A credential shown to a customer is shown once and never logged** | The token in the shown-once panel at acceptance, dropped on dismissal, in no storage; the walk record holds no password, link or seed (the transcriber refuses them) |
| **The console's policy** (ADR 0280/0285) | Unchanged: no cross-origin call is added (D2865) |
| **No markup built from a value** | Every new view through `h` |
| **A report may not substitute an answer for a failure to determine one** (ADR 0195) | The bundle's `asleep` and `stale`; `control.sh status`'s unread sections and exit 6; `doctor usage`'s witnessed zero |
| **No product surface runs SQL** | `control.sh status` is an operator's root read (the `registry` verb's shape); the bundle runs the doctor, which runs only its named reads |
| **A page claims no more than the Ledger** | Two `trial` rows, `beta` only on their claims; the five stale rows re-read |
| **A slot is never reused** | `slot11-prod` consumed; `slot10-prod` kept as a customer's |
| **The deploy, the sweep and the tag land on one commit** (D1425) | Run 9's order |

---

## 9. Stop conditions

Stop and ask the operator, without improvising, when:

- **the person cannot walk on the arranged day**, or the walk would need the
  operator or the agent to take a step for them (beyond P0 and transcription);
- the record would hold a secret, or the person does not confirm it;
- **Sheet IR4**: the doctor takes more than 120 s on a project;
- rig 46a shows the console's policy refusing WebCrypto or the form, or a
  design needs a cross-origin call, a storage write, a new console script or a
  policy change;
- `project claim --token-file` cannot choose the token's own creation from what
  a member can read (ADR 0291 decides; a guess is the stop);
- a test outside the ones this plan names would have to move, or a walk driver
  would need a product text changed;
- `upgrade plan` prices 1.24.0 at `major` or for an unnamed reason; **a deploy
  restarts a database**; 0010 fails to apply;
- a deploy's window exceeds 5 minutes, or a project's routes do not return;
- **a creation lands on the wrong slot** (D2870);
- **the journey dies after its creation was accepted, or the lifecycle attempt
  dies before `finished`** (D2798: no resume — `slot12-prod` would be the next);
- a commit would touch a site digest input between the bump's push and the
  person's confirmation (D2883);
- **Sheet X0** finds a project running or a volume missing on the old host;
- a `trial` row would outlive the close, or a row move to `beta` without its
  claims `passed`;
- a currently-passing test would be weakened to make a new one pass;
- `--render-only` stops working with no host and no root.

---

## 10. Open items this session carries and creates

**Carried, untouched, each still true:** Session 45's §10 *Carried* list
(`session-45-implementation-plan.md:1529-1537`) less what this session closes —
beta's three rotations (D1995); the relay as a third public surface; no
`statement_timeout` on customer roles (D2735); branch doors not in the editor
(D2738); the walker prefix `walk-s43-` (D2804); the plane's footprint at rest
`UNMEASURED` (unless Sheet CS reads it); `lifecycle-s41`…`-s45` empty; the
24 unclaimed requirements; D976; D1045; D1375; the telemetry plane's volumes not
backed up; the Stage 6 candidates from the brief (D2828, D2823).

**Created, and named so Stage 6 does not inherit them silently:**

- **Two kept customer projects** (`slot3-prod`, `slot10-prod`): every release
  redeploys both by `slot.sh redeploy`; the second is a real person's.
- **The second walker** (the stage plan's budget): if the first person's record
  holds findings, the repairs land after them (D1359's shape) and a second
  person walks — at this session's sitting only if the operator arranges it the
  same week and the repairs are `site/`- and `docs/`-only (D2883); otherwise
  Stage 6's first walk, with `documented_path` `failed` in between, said so.
- **`appliance_documented_path`** stays `failed` until a person walks the clone
  (D1935).
- **The handoff token's loss** (threat item 28): a creator who closes the tab
  before saving it can claim only through the operator's root reset.
- **The bundle is node-derived**: a member reads the node's verdicts for their
  own project every 15 minutes; a change to the doctor's `detail` sentences is a
  change to what customers read.
- **`slot1-` … `slot9-prod`, `slot11-prod` consumed**; Stage 6's first
  lifecycle needs `slot12-prod`.

---

## Appendix — what to consult, how a run is executed here, and the sheets

**Consult, in this order:** CLAUDE.md §1 (the shell traps); this plan's §0, §1
and the run's own text; the reads its run names. **The tree wins.**

**How a run is executed here**: CLAUDE.md §5. Every `sudo` line is the
operator's, on a sheet, under `script -q -e -c '…' /home/op/s46-<sheet>.txt` when
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
detached** (D2796; CLAUDE.md §1). **A battery of live proofs that sign in waits
a TOTP step between pytest processes** (D2860).

### Sheet IR4 — the doctor timed (Run 1; root; read-only)

```
sudo -v
# the agent writes /home/op/s46-ir4.sh only at the operator's word: for slot3-prod and
# control-prod, `time bin/doctor.py --project KEY --json`, printing the wall seconds,
# worst, and each check's name, verdict and evidence KEYS -- never a value
script -q -e -c 'sudo bash /home/op/s46-ir4.sh' /home/op/s46-ir4.txt
```

### Sheet R1 — the release priced (Run 9)

```
sudo -v
cd ~/agentic-postgres && sudo bin/upgrade.sh plan --project-file /home/op/<each>.yaml   # verb and flags from --help
                                                                                          # 'minor' or below; 'major' is §9's stop
```

### Sheets R2a / R2b / R2c / R2d — 1.24.0 deployed (Run 9; one per sheet, read before the next)

```
# THIS DEPLOY RESTARTS NO DATABASE (D2888). R2d applies control migration 0010.
sudo systemctl stop agentic-postgres-reconciler
script -q -e -c 'sudo ./deploy.sh <the manifest as Session 45 R2a-c used it>' /home/op/s46-r2<x>.txt
   # R2c: slot3-prod by slot.sh redeploy (refused while the reconciler is active)
   # R2d: control-prod LAST -- 0010 applied, the console recreated
(agent) s46-after.sh <key>: doctor 12 ok; the routes; for R2d the console 200, the relay, 0010 in the control ledger
sudo systemctl start agentic-postgres-reconciler          # after R2d only -- RC1: `reconciler.sh status` active on the new checkout
```

### Sheets A1, RA, K1, V1 (Run 9) — as Session 45's (`session-45-implementation-plan.md:1627`), the commit and file names moved to 46; RA after the last deploy (D2494); from the walk on, A1 reads `agrees` × 5.

### Sheet CS — `control.sh status` (Run 9; root; read-only)

```
sudo -v
script -q -e -c 'sudo bin/control.sh status' /home/op/s46-cs.txt     # the agent reads it against `control.sh registry`
```

### Sheets H1, SL1, SL1b, SL2, SL3 (then SL1′–SL3′), RC1, K2, A1′, B1, SL4 (Run 9) — Session 45's (`:1629`, its Run 9 **Done.**) with these changes:

- **H1**: `s46-hostyaml.py` declares **two** slots, `slot10-prod` and
  `slot11-prod`, in BOTH `host.yaml` copies (the comment it inserts read first,
  D2727); `cmp` equal; RC1.
- **SL1 (slot10)** — the agent: three grey A records `slot10`, `pool.slot10`,
  `direct.slot10` → `15.204.231.45` and the R2 buckets `apg-slot10-prod`,
  `apg-slot10-prod-backup` (EEUR, Standard) through the Cloudflare API; the
  operator: the two R2 tokens, the B2 bucket `apg-slot10-prod-backup-mirror` and
  its key, `bootstrap-providers --apply`, the six Infisical secrets (`--plan`
  names them; SL4's credential written with `nano` and shredded, D2648).
  **SL1b** the shape read; **SL2** materialised; **SL3** `slot.sh status`
  `slot10-prod ready` and **no other slot ready**.
- **SL1′–SL3′ (slot11)**: the same for `slot11-prod`, **only after A1″ reads
  `slot10-prod` allocated** (D2870).
- **K2** at the lifecycle's pause; **A1′** after the lifecycle (slot1–9, 11
  `agrees (deleted)`, five live); **B1** the reboot with `s46-units.sh` on the
  host first (D2861); **SL4** after the tag, `slot11-prod` only.

### Sheet P0 — the person's invitation (Run 9; the operator, at the workstation)

```
# In WSL, as the registry administrator (~/s37/admin-config), the code from your phone:
#   the agent hands the exact `apg login password ... --totp-code-stdin` and
#   `apg org invite --account --output <a 0600 path of your choosing> --expires-hours 72`
#   lines after reading their --help; YOU type the code and open the file.
# Send the link and the statement (docs/hosted-walk.md, between its markers) to the
# person by your own email. Do not paste the link into the conversation.
```

### Sheet PW — the walk (Run 9; the person)

The person follows the statement. The agent watches only what the product
records (the control API's operations for the person's organisation are not the
agent's to read — it reads `slot.sh status` / A1″ for `slot10-prod` allocated,
nothing else). The operator relays only *"started"*, *"finished"*, *"stuck at
<page>"* — never a credential.

### Sheet PR — the record (Run 9; the person, the agent, the operator)

```
(person)   returns the notes in the statement's plain-text form (by email to the operator)
(operator) saves them to WSL as ~/s46/walk/notes.txt (0600)
(agent)    ~/s46/run7/s46-walk-record.py --notes ~/s46/walk/notes.txt --out ~/s46/walk/record.json
           (prints the JSON; refuses a note holding a password, a link fragment or a seed)
(person)   reads the JSON (the operator sends it); confirms or corrects; the agent applies
           corrections verbatim and sets confirmed_by_walker_at
(agent)    bin/dx-record.sh check --path hosted --record ~/s46/walk/record.json   # 0 or 5, recorded
```

### Sheets W0′ / W1′ / E0 / E1 / L0 / L1 / J1 — the walks (Run 9; the agent, from WSL, no SSH)

```
(agent) ~/s46/run7/s46-walk.sh --dry      # W0': the console walk to Connect, no rotation, the walker removed
(agent) ~/s46/run7/s46-sql.sh --dry       # E0:  the editor on each door, the refusals (again after B1, D2838)
(agent) ~/s46/run7/s46-look.sh --dry      # L0:  every page at 390 and 1280, no record
(agent) ~/s46/run7/s46-walk.sh            # W1': customer_app rotated, the creds replaced (.before-s46 kept)
(agent) ~/s46/run7/s46-sql.sh             # E1:  the editor walk, the record
(agent) ~/s46/run7/jr-start.sh            # J1:  the journey, detached, on slot11-prod (after SL3')
(agent) ~/s46/run7/life-start.sh          # the lifecycle --from-journey, detached, ONE attempt
(agent) ~/s46/run7/s46-look.sh            # L1:  the look walk, the record (after B1)
```

### Sheet S1 — the one sweep (Run 9)

```
sudo -v
script -q -e -c 'sudo bash /home/op/s46-launch.sh' /home/op/s46-s1.txt
   # derived from ~/s45/run7/s45-sweep.sh + s45-launch.sh by diff; after E0 again (D2838)
```

### Sheets X0 / X1 / X2 / X3 — the old host retired (Run 10; each read before the next)

```
# X0 (operator, read-only):
ssh -i ~/.ssh/agentic_postgres_ed25519 op@62.238.99.122 'hostname; uptime; systemctl is-enabled agentic-postgres-project@{alpha-dev,beta-dev,control-prod}; systemctl is-active agentic-postgres-project@{alpha-dev,beta-dev,control-prod}; df -h /'
# X1 (operator, on the old host, the store's credential written with nano and shredded):
#   bootstrap-providers --destroy for each of alpha-dev, beta-dev, control-prod (flags from --help, as M7 step 1)
#   then read at the store's console: each key has ONE identity, OVH's
# X2 (operator, at the consoles): the three Infisical Cloud projects and four Cloud identities deleted,
#   the Cloud organisation read empty; the Hetzner server cancelled
# X3 (operator, on the store 15.204.66.146):
sudo ufw delete allow from 62.238.99.122 to any port 443 proto tcp && sudo ufw status numbered
```
