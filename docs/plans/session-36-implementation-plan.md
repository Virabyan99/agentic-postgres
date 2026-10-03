# Session 36 — Preconditions: the boundary, the rescale, and the operating debt

**Status: IN PROGRESS — Run 1 done 2026-10-03 (rows D2006–D2012).** Planned
2026-10-03 at `1ea6259`. The first session of
Stage 5 (`docs/plans/stage-5-plan.md` §3). Eleven runs and **two sittings on
two days** — the server rescaled in place and the release deployed (one outage
of both projects, measured), then the three rotations, a reboot and the one
sweep. **Revised the same day** from a move to a new VPS: the operator chose to
rescale the existing Hetzner server, CPU and RAM only (§1 D1991). The plan
spends **D1985–D2005** and **ADR 0246–0250** (0250 only if Run 6 builds; §2);
rows the runs add start at **D2006**. **NEXT FREE after this plan: D2006, ADR
0251.**

**Brief:** `docs/plans/stage-5-plan.md` §5 *Session 36* whole (Builds / Already
true / Must not / Measures / Closes), its rows **D1946** (the hosted decision;
§6's four items become this session's preconditions), **D1948** (a new, larger VPS — superseded by the operator's in-place rescale,
§1 D1991), **D1949** (ADR 0246,
the lapsed boundary), **D1973** (the retention plane), **D1974** (the three
rotations and a schedule), **D1975** (the edge window: nothing here recreates
the edge; the rescale and the reboot restart it with the host), **D1976** (D1581 answered by a rig before Session 38
builds on it), **D1977** (D1918, D1547), **D1978** (the hosted `THR-*` rows
before any code), **D1979** (the Reality Ledger and its guard), §2.3 (the open
items), §2.4 (every `not_run` touched, none promised), §4's caution about the rotations (its caution about a move is moot: the host is rescaled, §1 D1991), §8–§9, §11. Plus `docs/stage-5-decision-report.md` §5–§6,
`docs/scope-closure.md` §28, `docs/operator-guide.md` §9 (`:497-545`), §13
(`:702-730`), §15 (`:830-1170`), §16 (the node as a finite resource),
`docs/api-operations.md` §*Rotating a credential* (`:84-200`), and Hetzner's
rescale rules (docs.hetzner.com/cloud/servers/faq, read 2026-10-03, quoted in
§1 D1991).

**Shape:** eleven runs. **Run 1** is documentation — four rigs, one host
reading sheet (E0, reads only), the hosted threats, five ADRs,
the product contract amended — and reads **no** CI verdict. **Runs 2–6** change
code: each pushes and reads that commit's own CI verdict by full SHA (`gh api
"repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<40 chars>" --jq
'.workflow_runs[] | [.name, .status, .conclusion] | @tsv'`, judged on HTTP
status, three buckets — success / failure / not registered; an empty list is
not a verdict, D1057). **Run 6 is conditional** on Sheet E0's answer (§1
D1997). **Run 7** writes the trip's instruments and rehearses them offline,
committing nothing but its `**Done.**`. **Run 8** is the bump. **Runs 9–10**
are the sittings. **Run 11** is the close (the envelope's new rows are `src/`,
so it gates and reads CI).

**Product version at close:** `CURRENT_SESSION` **36**; `template_version`
**`1.14.0`** — predicted *minor by declaration* (two released migrations, a new
command; `upgrade plan` reads a migration only when declared, D1703, so Run 8
declares `--also migration_added`) and **read from `upgrade plan` on the host, never chosen** (§1 D2001). **Migration 0038** (`approval_withdrawn`: one
`ALTER TYPE … ADD VALUE 'withdrawn'`), **migration 0039** (`record_retention`:
three prunes, one withdrawal, one size reading — all in `app_private`, no
table, no column, no `api` object, so no `NOTIFY pgrst`), **the worker calls the
withdrawal on an idle iteration**, **`bin/record.sh size|prune`** (root, the
first verb that calls ADR 0213's two prunes and the three new ones), **a stdout
handler for the `apg.*` and `app.workflow_worker` loggers** (D1918), **the
Reality Ledger** (`docs/reality-ledger.yaml`, its schema, its renderer, its
guard, its page), **the hosted threats** as a list in `docs/threat-model.md`,
**ADR 0246** (the hosted boundary; 0042/0043/0044/0216/0217 superseded;
`product-contract.md` §2 and §5 amended), and — if E0 allows — **a secret-age
reading** (`doctor --reading secrets`, ADR 0250). **Outputs stay at schema 19,
manifest at 8, host.yaml at 3. No new container, role, network, route, router,
secret, scope or port.** A `major` is §9's stop.

**Written for whoever picks this up cold, and it will be a different model
than the one that planned it.** Every path below was read from the tree on
2026-10-03 at `1ea6259` — three explore passes over `migrations/templates/`,
`services/auth-api/app/`, `src/`, `bin/`, `schemas/`, `tests/` and `docs/`, and
direct reads of `docs/node-loss-runbook.md`, `docs/operator-guide.md` §2–§3,
§9, §13, `docs/api-operations.md` §*Rotating*, `bin/backup.sh --help`,
`bin/project-runtime.sh --help`, `bin/upgrade.sh --help`, `bin/provision-host.sh`
`:85-140`, and Sessions 30 and 35's plans. **The rescaled size is the operator's
choice on the day; every fact about the host after the rescale is a reading
Run 9 owes.** Every path is cited by
`path:line`. Every third-party or product claim is measured in Run 1's rigs
with a control, or is marked as the measurement a run owes — never assumed.
**Read CLAUDE.md §1 in the launch folder before the first command, then this
plan's §1, then the appendix.** If a step here and the tree disagree, **the
tree wins and the disagreement is a divergence row** (next free `D` after §1's
table), never a silent reconciliation. **When this plan names a line number,
open the file at that line and read the surrounding twenty lines before
editing** — the numbers were right on 2026-10-03 and `ruff format` moves them.

**The seven sentences the executor most needs, in case nothing else is read:**

1. **The host is rescaled in place, not replaced** (§1 D1991, the operator's
   decision of 2026-10-03). Hetzner's rescale needs the server OFF, keeps its
   disk with **"CPU and RAM only"** (so a downgrade stays possible), keeps the
   architecture (x86), and may change the CPU vendor. The order is fixed: an
   incremental backup and the row counts → `sudo systemctl poweroff` → the
   console rescale → **the Primary IPv4 read on the console BEFORE power-on**
   → power on → the units `active` → the doctors and the counts `EQUAL` →
   `host.yaml`'s `memory_mb` re-declared with the reserve UNCHANGED (D1992).
   Nothing moves: same address, disk, documents, kits, timers and identities.
2. **One sweep, on day 2, after the rotations and a reboot** (§1 D1998). It is
   the only run that writes `evidence/session-36-host.json`; day 1 verifies the
   rescale and the release with `-k` (which writes nothing). `port_allocation` needs
   `--after-reboot` in the sweep that writes the evidence, and the rotation trio
   needs its four `--rotated-*` files in the same one.
3. **The three rotations are alpha's, one sheet each** (§1 D1995). The proofs
   read `APG_PROJECT_A_OUTPUTS` only; the fourth file is the retired signing
   JWK Session 30 kept at `/home/op/s30-retired-alpha-dev-jwk.json`. Every rotation is: capture the old value to
   a root-only file → replace it at the provider by hand → `project-runtime.sh
   … down` (D253, still live) → materialize → deploy → doctor.
4. **Retention prunes by AGGREGATE, never per table, and nothing prunes on its
   own** (§1 D1986, ADR 0248, ADR 0213's rule kept). Three new prunes —
   `workflow_run_prune`, `connector_delivery_prune`, `agent_prune` — each
   deleting its children in FK order inside one function, each granted to
   NOBODY, each called only by `sudo bin/record.sh … prune --confirm KEY`. Humans,
   definitions, connectors and the worker singleton are never pruned.
5. **A pending approval on an ended run becomes `withdrawn`** — a NEW enum value
   added by its OWN migration (0038) because a value added by `ALTER TYPE … ADD
   VALUE` cannot be used in the transaction that added it (rig 36a measures it);
   0039's `workflow_withdraw_ended_approvals()` is granted to `{{auth_service}}`
   and called by the worker on an IDLE iteration. **No 0035 function is
   replaced** (§1 D1987).
6. **ADR 0246 changes what is ALLOWED, not what RUNS.** After this session
   `publication()` still raises, `compose.yaml` still has zero `ports:` keys,
   the edge still publishes 80 and 443 only, and no customer exists. The ADR
   names what Sessions 37–42 may build and the ports Session 39 may add; this
   session builds none of it.
7. **The Reality Ledger is a program's input from its first commit** (§1 D2000,
   ADR 0247): a YAML with a JSON Schema, a renderer with `--check` in
   `bin/session-01-check.sh`, and a guard that fails when an `available` or
   `beta` row names evidence that does not resolve, when a `planned` row has a
   control, or when a customer-facing sentence uses one of the specification's
   §59 words.

---

## 0. Where the session starts

```
HEAD            1ea6259 on main, local = origin (the Stage 5 plan, documentation
                only). Deployed: f7fb96d (1.13.0) on both projects; the tag
                1.13.0 names f7fb96d. `git diff --name-only 1.13.0..HEAD`
                filtered to src/ bin/ services/ migrations/ schemas/
                compose.yaml deploy.sh VERSION names ONE file:
                src/agentic_postgres/capacity.py (Session 35's envelope rows,
                da55df1) -- measured 2026-10-03.
VERSION         1.13.0 (repo root; template_version() __init__.py:842).
                CURRENT_SESSION 35 (__init__.py:834; Session 35's paragraph
                :769-833). Outputs schema 19. host.yaml schema 3 (enum [2,3],
                schemas/host.schema.json:9-18). Project manifest 1-8.
                Capability manifest 4, lock 4, project lock 3, api-surface 2.
                37 released migrations (migrations/manifest.json; the last
                20261001120037 approval_gate).
REGISTRY        291 requirements (tests/acceptance-registry.yaml; Session 35's
                block from :5760 under `# Session 35 (ADR 0242-0245)`). 198
                claims (evidence_claims.py CLAIMS :356; Session 35's block
                ~:628-643), 60 declared offline (OFFLINE_CLAIMS :106; Session
                35's names ~:287-307). CLAIM_INTRODUCED_IN tests/contract/
                test_evidence_claims.py:953 (asserted == CLAIMS at :1377). ID
                regex tests/contract/test_acceptance_registry.py:~106 (ends
                `…|WF|EVT|CONN|GOV)-[A-Z0-9]+(-\d+)?$`). 245 ADRs (index
                docs/decisions/README.md, last row :311). NEXT FREE: D1985,
                ADR 0246.
EVIDENCE        evidence/session-35.json: 198 claims, 192 passed, 5 not_run,
                1 failed (documented_path, by decision D1935). not_run:
                api_authorization, bootstrap_identity,
                credential_rotation_planes, port_allocation,
                replacement_host_restore. Host 1082/1/7, external 25/0/8,
                offline 60/60.
HOST            62.238.99.122 (apg-vps-01), ~op/agentic-postgres at f7fb96d.
                Both projects 1.13.0, doctor 12 ok, ledgers 37 / 37+4. 3,814
                MiB, no swap, 2 vCPU; host.yaml capacity 3814 / 2214 reserve /
                38 GiB / 8 GiB reserve. Beta: manifest 7, connectors ON (four,
                all disabled), 83 revoked probe agents, 35 probe humans, 7
                pending approvals on ended runs, 5 dead deliveries. Alpha:
                manifest 4. Op-owned copies /home/op/<key>-dev-outputs.json.
                Retired JWKs /home/op/s30-retired-<key>-jwk.json. Kits through
                kit-2026-10-03-post (host + WSL ~/dr-kits, 0700/0600). The
                gate's --kit-dir stays kit-2026-09-11 (D1282). Session 35's
                script set s35-r10-* in /home/op and WSL ~/s35r10/ (deriver
                ~/s35r10/s35r10-derive.py -- THE MODEL for this trip's).
RESCALE         A Hetzner Cloud server. Rescaled IN PLACE, CPU and RAM only
                (D1991): powered off first; an x86 plan of the operator's
                size (at least 4 vCPU / 8 GB; 8 / 16 if Session 41's ClickStack
                is to fit); the disk stays 38 GB; the Primary IPv4 is read on
                the console before power-on.
```

**What exists, measured at `1ea6259`, and the session builds on:**

- **The retention precedent.** `migrations/templates/0033-agent-record-
  retention.sql` (337 lines): `-- migrate:up` (`:1`), a banner-sectioned header
  (`:2-125`), `SET LOCAL ROLE {{object_owner}};` (`:126`),
  `app_private.agent_audit_prune(p_before timestamptz, p_limit integer DEFAULT
  NULL) RETURNS bigint` (`:148-194`: plpgsql, VOLATILE, SECURITY DEFINER, `SET
  search_path = pg_catalog, pg_temp`; refusals `AP422: a retention horizon is
  required` / `…is in the past` (the file's wording for a FUTURE horizon) / `a
  prune bound is at least one row`, all `ERRCODE = 'PT422'`; the bounded form
  deletes `WHERE ctid IN (SELECT … LIMIT p_limit)` because `DELETE … LIMIT` is
  refused on 18.4), `agent_idempotency_prune` (`:212-249`, the same shape on
  `created_at`), `agent_record_size()` (`:282-299`, STABLE, granted to
  `{{auth_service}}`), `COMMENT ON FUNCTION` after each (`:196`, `:251`,
  `:301`), `REVOKE ALL … FROM PUBLIC` (`:318-322`), *"There is no `GRANT` for
  either prune, and that absence is the decision"* (`:316`), `RESET ROLE;`
  (`:326`), *"Nothing in `api` moved, so no NOTIFY"* (`:328-331`), and the down
  block (`:333-337`) — `DO $$ BEGIN RAISE EXCEPTION 'AP900: released platform
  migrations are fix-forward only' USING HINT = 'Write a new migration. Do not
  roll this one back.'; END $$;`. Its proofs:
  `tests/contract/test_agent_audit_plane.py:2722-2949`. **No `bin/` verb calls
  either prune** (ADR 0213 `:88-106`: *"a human at a TTY"*).
- **The ten Stage 4 tables and their foreign keys** (every FK is NO ACTION —
  `0034:39`: *"No trigger, no schedule, no `ON DELETE`"*):
  `workflow_run.definition_id → workflow_definition`, `.agent_id → agents`
  (`0034:198-199`); `workflow_step.run_id → workflow_run` (`0034:252`);
  `workflow_approval.run_id → workflow_run`, `.step_id → workflow_step`
  (UNIQUE), `.decided_by → users` (`0035:100-110`); `workflow_attempt.step_id →
  workflow_step` (`0035:135`, PK `(step_id, attempt, event)`);
  `connector.agent_id → agents`, `.enabled_by/.disabled_by → users`
  (`0036:79-82`); `connector_delivery.event_id → connector_event`,
  `.connector_id → connector` (`0036:127-128`); `connector_receipt.connector_id →
  connector`, `.run_id → workflow_run` (nullable, `0036:162-165`, PK
  `(connector_id, delivery_id)`). `workflow_definition`, `workflow_worker`
  (a singleton, `0034:304-309`) and `connector_event` (*"`agent_id` carries no
  foreign key, the audit's convention"*, `0036:111`) reference nothing.
  **Time columns**: `workflow_run.created_at|started_at|finished_at`;
  `workflow_step.started_at|finished_at`; `workflow_approval.requested_at|
  expires_at|decided_at`; `workflow_attempt.recorded_at`;
  `connector_event.emitted_at`; `connector_delivery.created_at|delivered_at|
  dead_at`; `connector_receipt.received_at`. **Run statuses**
  `queued|running|succeeded|failed|cancelled|stopped` (`0034:119-120`) +
  `compensating` (`0035:57`). **Approval statuses**
  `pending|approved|rejected|expired` (`0035:59-60`), with `CHECK ((status IN
  ('approved','rejected')) = (decided_by IS NOT NULL AND decided_at IS NOT
  NULL))`. **Delivery statuses** `pending|delivered|dead` (`0036:52`).
- **`app_private.agents`** (`0011:174-187`): `status app_private.agent_status`
  (`'active'|'revoked'`, `0011:37`), `updated_at`, **no `revoked_at`**;
  `agent_credentials` (`0011:200`) and `agent_quota` (`0028:103`) reference it
  `ON DELETE CASCADE`; `agent_idempotency` carries no FK (`0029:88`: the first
  draft's was removed); `agent_audit` carries the id with no FK. A rotation
  moves a revoked agent back to `active` (`0025:135`).
- **What ends a run, and what happens to its approval.**
  `workflow_begin_compensation` (`0035:185`, granted to nobody; `:243-246` sets
  `failed`/`cancelled`), `workflow_finish_step` (`0035:462`; `succeeded`,
  `stopped`, the compensation cause), `workflow_cancel` (`0034:817`, a queued
  run → `cancelled`), `workflow_claim_step` (`0035:282`, cancel/timeout through
  compensation). **Nothing writes `workflow_approval` but
  `workflow_expire_approval` (`0035:930`, needs a live claim on the step) and
  `workflow_decide_approval` (`:1005`, `:1014`; a decision on a non-running run
  is `AP404: no such run`, `:1000-1001`)**, so an approval parked on a run that
  ended stays `pending` forever (D1775). Every reader filters `r.status =
  'running'` (`workflow_counts` `:763-772`, `workflow_pending_approvals`
  `:1066-1068`, `workflow_approval_for_token` `:1105`, `app.require_approval`
  `0037:118`). Python readers of an approval status:
  `services/auth-api/app/workflow_worker.py:746` (`if status in ("pending",
  "expired")`) and `service.py:1035`.
- **The worker loop.** `workflow_worker.run_forever` (`:766`), `POLL_SECONDS =
  5` (`:96`), the two idle sleeps at `:828` and `:896`; it runs as the auth
  service's own role (`0034:1019`: *"Eight are granted to `{{auth_service}}`,
  which is the role the loop … "*).
- **Adding a released migration** (commit `4920c96`, 0037): `migrations/
  manifest.json` gains an entry `{"version": "YYYYMMDD12NNNN", "name":
  "<snake>", "template": "templates/NNNN-<kebab>.sql", "placeholders": [...],
  "description": "..."}`; `bin/migrate.sh freeze-lock` (the only writer,
  `bin/migrate.sh:64-69`, `:114`) rewrites `migrations/released.lock.json`;
  `tests/contract/test_migrations.py` gains a per-migration test (0037's
  `test_0037_creates_the_guard_and_grants_it_to_nobody`, `:301-333`); the count
  pin `tests/contract/test_workflow_substrate.py:274` (`assert
  len(applied["versions"]) == 37`, its per-session comments `:267-273`) moves
  (commit `994d86f` did it separately — do it in the same commit). Readers that
  count dynamically: `test_rendered_migrations.py:80`,
  `test_migration_ledger.py:111,163`, `test_database_commands.py:291`,
  `test_change_proposal.py:484`, `bin/doctor.py` ~`:375`. `RELEASE_FUNCTIONS`
  (`test_project_migration_sets.py:916-930`) lists `api`/`app` functions only —
  this session adds none there.
- **The doctor.** Twelve checks in order (`bin/doctor.py:1166-1182`; *"a check
  appended is a check every existing reader keeps finding where it was"*,
  `:1178-1180`); `AGENT_RECORD_QUERY` (`:665-670`) and `probe_agent_record`
  (`:686-740`) read the two tables directly as `postgres` through `docker exec
  -i <container> psql -U postgres -d <db> -X -qtA` (timeout 30), three outcomes
  through `diagnosis.agent_record` (`src/agentic_postgres/diagnosis.py:529-580`,
  no threshold, D1441). `--reading {capacity,usage}` at `:1215`.
- **Logging.** `services/auth-api/app/main.py:233` `create_app(mode=None)`;
  middleware `StructuredRequestLog` and `StampRequestId` (`:366-367`);
  `logging.getLogger("apg.http")` (`:391`) emits `self.logger.info(
  "apg.http.request %s", json.dumps({request_id, method, route (the TEMPLATE),
  status, elapsed_ms}, sort_keys=True))` (`:412-427`); `apg.mcp`
  (`mcp_telemetry.py:46`) emits `apg.mcp.read` (`:172`) from a fixed field set
  (`RECORD_FIELDS` `:58-67`); `app.workflow_worker` (`workflow_worker.py:90`,
  `main.py:205`). **No `basicConfig`, `dictConfig`, `setLevel` or `addHandler`
  anywhere under `services/auth-api/app/`**, and the image runs `python -u -m
  uvicorn --factory app.main:create_app … --no-access-log`
  (`services/auth-api/Dockerfile:118-121`), so Python's last-resort handler
  prints WARNING and above only (D1918, rig 35r5a; D1837 for the worker). The
  canaries: `tests/contract/test_mcp_budgets.py:516-543` (`caplog` on
  `apg.mcp`), `:658` (an AST scan of `mcp_*.py` sinks),
  `tests/deployment/test_session7_storage.py:696-753` (STO-URL-001: `docker
  logs --tail 2000` holds no signature or object key).
- **Notes** (D1547). `api.create_note` (latest `0030:128-235`, SECURITY
  DEFINER, the agent write path inside it); `app.notes` has FORCE RLS and a
  `notes_owner_delete` policy (`0003:66-74`) but no request role holds DELETE
  (`0006:33` revoked `app_runtime`; `0004:53` granted SELECT only). The reviewed
  contract names three RPCs (`contracts/postgrest-api-surface.yaml:60-62`;
  pinned by `test_api_surface_contract.py:79`, `test_api_migrations.py:207-218`);
  the canonical snapshot is captured from a deployment (`sudo
  bin/api-contract.sh --update … > candidate.json`; there is no `--write`), and
  the generated client embeds its digest (`client_ir.py:288-312`).
- **The host's own restart path.** `provision-host.sh` installed and enabled
  `agentic-postgres-project@<key>.service`, `agentic-postgres-edge.service` and
  the docker firewall; the backup timers are enabled by `bin/backup.sh
  --outputs … schedule enable` (`bin/backup.sh --help`). The last reboot
  (2026-09-17, a kernel update) cost 8 s and `port_allocation` passed on it
  (D1500); `bin/project-runtime.sh --host FILE --project-key KEY
  --through-session N up|resume|down|status` (`down` detaches the edge and
  stops the project, volumes kept). `host.yaml` declares `capacity:
  {memory_mb: 3814, reserve_memory_mb: 2214, disk_gb: 38, reserve_disk_gb: 8}`;
  admission is `memory_mb − reserve_memory_mb − committed`
  (`capacity_reading.py:433`); `HOST_MEMORY_GUARDRAIL_MB = 1600` (`config.py:646`)
  is a per-project database check, not a host cap (`config.py:1342-1348`).
- **The claims the reboot and the rotations can move — and one they cannot.**
  `replacement_host_restore` stays `not_run` by D1028 (a rescale is not a
  replacement); for the record it = REC-NODE-001 (`test_node_restore.py` × 6 +
  `tests/deployment/test_session18_recovery.py::test_restore_refuses_the_
  populated_volume_on_the_replacement`, which needs `APG_KIT_DIR` +
  `APG_RESTORE_EVIDENCE_FILE` whose `project_key` is project A's, `:307`) and
  REC-NODE-002 (`…::test_the_restored_project_publishes_the_originals_identity_
  and_every_route_ready`, which needs `APG_KIT_DIR`,
  `APG_REPLACEMENT_HOST_OUTPUTS`, `APG_RESTORE_EVIDENCE_FILE`, `:347-349`).
  `port_allocation` = DBX-PORT-001, six node ids; the reboot proof
  (`test_session4_convergence.py:361-445`) needs `APG_AFTER_REBOOT`. The trio:
  nine node ids (stage plan D1974 lists them; `test_session5_convergence.py:
  422-433` reads a file as the plaintext PREVIOUS value, `.rstrip("\n")`;
  `:596-598` reads the retired JWK as JSON, `retired["kid"]`). The gate exports
  all of these from flags it already parses (`bin/session-35-check.sh:1526-1596`).
- **The gate to derive from.** `bin/session-35-check.sh` (1,721 lines; header
  `:1-109`; `readonly SESSION=35` `:118`; usage `:183-506`, every flag its own
  entry; parser `:590-784`; exports `:1526-1596`, external `:1673-1676`).
  `tests/contract/test_session_thirty_five_gate_modes.py` (988 lines).
  The Session 35 bump commit `f7fb96d` touched 21 files (README, VERSION, the
  gate, acceptance-matrix, three docs, product-contract, threat-model,
  upgrade-guide, the example client's two generated files, `__init__.py`,
  `evidence_claims.py`, the registry, four tests).
- **Documentation.** `docs/threat-model.md`: table `:19-41` (nine columns,
  parsed line by line by `tests/contract/test_acceptance_registry.py:425`;
  `test_every_threat_row_names_at_least_one_requirement` `:484`), `## Scope`
  `:157`. `docs/decisions/README.md` index (`:65-66` header;
  `test_every_adr_is_indexed` `:515`; `test_the_index_status_agrees_with_each_
  adr` `:552`; `test_no_source_file_cites_a_missing_adr` `:584`). ADR template:
  `# NNNN — Title`, then `- **Status:** Accepted`, `- **Date:**`,
  `- **Session:** 36, Run N (D…)`, `- **Affects:**`, `- **Related:**`, then
  `## Context`, `## Decision`, `## Alternatives rejected`, `## Consequences`
  (0245). `docs/product-contract.md` §2 `:31-60`, §5 `:470-493` — **read by no
  test** (only the generated blocks are). `docs/README.md` must link every
  `docs/*.md` page exactly once (`test_documentation_index.py:454-482`).
  `bin/session-01-check.sh` step 6 (`:212-228`) runs three renderers with
  `--check`.

---

## 1. The divergence table

Six columns. Each row is a **measured fact about the tree at `1ea6259`** (or
about the host as the Session 35 records left it) set against what the brief
(the stage plan's §5 *Session 36*, its §1 rows, §2.3, §4, §8–§9, the Stage 5
report §6 and scope-closure §28) says, with the decision this plan takes.
**Next free number after this table is D2006.** Rows the runs add go in a
second table below it, in execution order.

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D1985** | Stage plan D1973: *"the doctor's `agent record` check widened to every table it can prune"*. | The doctor's twelve checks are positional and read by position (`bin/doctor.py:1178-1180`); `agent record`'s sentence is built in `diagnosis.agent_record` (`:529-580`) and the `workflow` check already reports the run counts (`workflow_counts()`). Widening one check's query and sentence moves every reader of that sentence. | **The doctor is unchanged. The reading is `sudo bin/record.sh --project KEY size`** over a new `app_private.record_size()` (one row per prunable relation: rows and oldest time, plus one row counting pending approvals on ended runs), three outcomes per row (ADR 0195). The doctor's `agent record` sentence keeps saying *"nothing prunes either unless an operator asks (ADR 0213)"*, which is now true with a verb to ask. | One reader per question: the doctor answers *is the project healthy*; `record size` answers *how big is the record*. A thirteenth check is an option Session 42's `apg control status` may take with the evidence of a hosted operator's needs. | **0248** |
| **D1986** | Stage plan D1973: *"one definer function per table in FK order (attempts → approvals → steps → receipts → runs; deliveries → events; then agents with no run)"*. | Every FK among the ten tables is NO ACTION (`0034:39`); a step, an approval, an attempt and a receipt have no meaning without their run; `workflow_definition` and `connector` are installed configuration (deploy steps 6d/6e), not record; `workflow_worker` is one row; humans (`users`) are referenced by approvals, connectors, refresh families and storage objects. | **Three prunes, by aggregate**, each deleting its children in FK order inside one function: **`workflow_run_prune(p_before, p_limit)`** (ended runs — `succeeded\|failed\|cancelled\|stopped` — whose `finished_at < p_before`; deletes their attempts, approvals, receipts, steps, then the runs); **`connector_delivery_prune(p_before, p_limit)`** (deliveries `delivered\|dead` whose `coalesce(delivered_at, dead_at) < p_before`, then events older than the horizon that no delivery and no waiting step references, D1989); **`agent_prune(p_before, p_limit)`** (agents `revoked` whose `updated_at < p_before` and that no run and no connector references; credentials and quota go by their CASCADE; audit and idempotency rows keep the id by convention). **Never pruned**: definitions, connectors, the worker row, humans, a `queued\|running\|compensating` run, a `pending` delivery. `p_limit` bounds the number of ROOTS (runs, deliveries, agents). | A prune per table would let an operator delete a run's steps and leave the run, which no reader can explain; the aggregate is the unit the record means. Humans are referenced from six places and their deletion is an identity question, not a retention one. | **0248** |
| **D1987** | Stage plan D1973: *"an approval on an ended run moved to a new `cancelled` status by the run's end (D1775)"*. | Four definer functions end a run (`workflow_begin_compensation` `0035:185`, `workflow_finish_step` `:462`, `workflow_cancel` `0034:817`, `workflow_claim_step` `0035:282`), each hundreds of lines; replacing them "byte for byte plus one statement" is D1834's method and its largest risk. `ALTER TYPE … ADD VALUE` is accepted in a transaction on PostgreSQL ≥ 12 but **the new value cannot be used in that transaction** (to be measured on 18.4, rig 36a); dbmate runs each migration in its own transaction. *"cancelled"* already names a RUN status, and a run cancelled is not an approval cancelled. | **The value is `withdrawn`, added by migration 0038 alone; migration 0039 adds `workflow_withdraw_ended_approvals() RETURNS bigint`** (pending approvals whose run is `succeeded\|failed\|cancelled\|stopped` → `withdrawn`), **granted to `{{auth_service}}` and called by the worker on an IDLE iteration** (immediately before each `await sleep(POLL_SECONDS)`, `workflow_worker.py:828`, `:896`) — so a parked approval is withdrawn within one poll of its run ending, and the 7 on beta are withdrawn by the first idle loop after the deploy. **No 0035 function is replaced.** `workflow_run_prune` also deletes withdrawn approvals with their run. The CHECK (`decided_by`/`decided_at` set exactly for approved/rejected) holds for `withdrawn` unchanged. | Fix-forward with the smallest surface (D912): one enum value and one function, called by the process that already owns the run lifecycle. The rig decides whether 0038 and 0039 must be two files; if rig 36a shows the value is usable in the same transaction on 18.4 the plan still keeps two (the down of each is `AP900`; two is the shape that works on every supported version). | **0248** |
| **D1988** | ADR 0213: a prune refuses only a missing or future horizon. | An inbound connector's receipt is its replay protection: `POST /connectors/{name}` refuses a signature outside ±300 s and a `(connector_id, delivery_id)` already received (0036's receipt PK). A receipt older than 300 s cannot be replayed anyway. A run can finish two seconds after its receipt arrived. | **`workflow_run_prune` refuses a horizon newer than `now() - interval '600 seconds'`** with `AP422: a retention horizon inside the inbound replay window`, so no receipt younger than twice the signature window is ever deleted with its run. The other two prunes keep ADR 0213's two refusals. | Deleting a receipt inside the window would re-open a replay the route refuses today; the bound is the window itself, doubled. | 0248 |
| **D1989** | — | An event resumes a parked `wait` step whose `await_event` names it (0036: `workflow_step.await_event\|await_match\|await_payload\|await_served_at`, `:172-176`; the emitter `:250`, `:855`). Whether a parked step can be served by an event emitted BEFORE it parked is in 0036's matching function and **was not read by this plan**. | **`connector_delivery_prune` never deletes an event that a `parked` step of a non-ended run names in `await_event`**, whatever the matching rule; **Run 1's rig 36b reads 0036's event-matching function** (grep `await_event` in `0036-connectivity.sql`) and, if an event is matched only at emission, writes a row saying the guard is belt-and-braces. | A guard that costs one `NOT EXISTS` is cheaper than a wrong reading of a 1,000-line migration. | 0248 |
| **D1990** | Stage plan D1977: *"`api.delete_note(id)` under the notes grants, owner-only by RLS, with the release's next migration"*. | A new `api` function moves the reviewed contract (`postgrest-api-surface.yaml`), the canonical snapshot (captured only from a deployment, `api-contract.sh --update`), the generated example client's embedded digest (`client_ir.py:288-312`, D1690), and four pinned sets (`test_api_surface_contract.py:79`, `test_api_migrations.py:207-218`, `RELEASE_FUNCTIONS`, the MCP catalog if a capability names it). What it buys: an operator removing a sentinel row without root `psql` — which the operator already has. From Session 39 a customer deletes rows with the customer's own credential. | **Deferred.** D1547 stays open in §10 with this cost written beside it; Session 36 changes no `api` object. | The cost is five artefacts and a deployment-captured snapshot for a convenience the one person who needs it already has. | — |
| **D1991** | Stage plan D1948: *"A new, larger VPS — the operator's decision of 2026-10-03. Session 36 moves alpha and beta onto it with `bin/dr-kit.sh export` → `provision-host.sh` → `bin/restore.sh --from mirror` → deploy … switches the DNS A records … The old host is retired on a later day."* | The host is a **Hetzner Cloud** server (`apg-vps-01`, 62.238.99.122: 3,814 MiB, 2 vCPU x86, 38 GB disk). **Hetzner's rescale** (docs.hetzner.com/cloud/servers/faq, read 2026-10-03) upgrades the same server in place from the Hetzner Console: the server is **powered off** first; the target plan must have the **same architecture** (x86 → x86; no Arm CAX); the **CPU vendor (Intel or AMD) may change**; with **"CPU and RAM only"** the disk keeps its size and a later downgrade stays possible (a plan with a smaller disk is never offered); the disk, its data and the server object are kept. | **The operator decided on 2026-10-03, after this plan was first written, to RESCALE the existing server — CPU and RAM only — instead of moving to a new VPS. The stage plan's D1948 move is superseded by this row.** Nothing moves: same address, same disk, same deployed documents, kits, timers, Infisical identities and buckets; **no** provisioning, adoption, restore, DNS change or certificate issuance. **The target size is the operator's on the day** (at least 4 vCPU / 8 GB; 8 vCPU / 16 GB if Session 41's ClickStack is to fit). **The Primary IP staying attached is read on the console before power-on** (Sheet H2), and the address is read again by the agent after boot. `replacement_host_restore` stays `not_run` **by D1028's decision, unchanged** — a rescale is not a replacement. | The move existed only to buy memory and CPU; a rescale buys the same with one power cycle instead of two restores, two deploys, a DNS cutover and a one-writer-per-repository hazard. The one thing lost — the first end-to-end replacement — was a side benefit, not the session's purpose. | — |
| **D1992** | Stage plan D1948: *"declares its capacity in `host.yaml`"*. | Admission computes `safe_available = memory_mb − reserve_memory_mb − committed` (`capacity_reading.py:433`); `HOST_MEMORY_GUARDRAIL_MB = 1600` (`config.py:646`) is a **per-project database** check (`config.py:1342-1348`), not a host cap; `host_config.py:106` notes that on the reference host the reserve equals 3814 − 1600. `host.yaml` declares `capacity: {memory_mb: 3814, reserve_memory_mb: 2214, disk_gb: 38, reserve_disk_gb: 8}`. | **After the rescale, `memory_mb` is the new `free -m` total; `reserve_memory_mb` stays 2214** — it stands for what is NOT the projects' (the OS, Docker, the edge, the margin), which a bigger RAM does not grow; **`disk_gb` and `reserve_disk_gb` are unchanged** (CPU and RAM only). Claimable rises from 1,600 MiB to `memory_mb − 2214`. The agent edits `/home/op/agentic-postgres/host.yaml` as `op` with a backup and the diff printed; the operator installs it (`/etc/agentic-postgres/host.yaml`, `provision-host.sh --apply` or the path `doctor capacity` reads — Run 7 reads `bin/provision-host.sh` and `host_config.py` for which copy admission reads, and the sheet names it). **Session 38 re-derives both numbers** with the control project, ClickStack and the profiles in view. | A reserve copied unchanged is honest because what it reserves did not change; a reserve recomputed from a bigger total would hand projects memory the OS still needs. | 0221, 0222 |
| **D1993** | — | `provision-host.sh` installed and enabled `agentic-postgres-project@<key>.service`, `agentic-postgres-edge.service` and the docker firewall (the backup timers are enabled by `backup.sh schedule enable`); `port_allocation`'s reboot proof (`test_session4_convergence.py:361-445`) passed after the 2026-09-17 reboot, which cost 8 s (D1500). A power-off from the console is a hard stop; `systemctl poweroff` stops every unit, and Docker stops the cluster with SIGTERM — a fast shutdown, which checkpoints. | **The rescale is a clean shutdown from inside the OS, then the console**: before it, a `backup --type incr` per project and the row counts recorded (`s36-counts.py --before`); then `sudo systemctl poweroff`; the console rescale (CPU and RAM only); power on; the agent waits for SSH, then for the three units to read `active` three times 10 s apart; the doctor (12 ok each); the counts compared (`EQUAL`); `free -m`, `nproc`, `lscpu`'s model name read. **The backup timers stay enabled** — they fire at night, and the window is daytime. **The window — `poweroff` issued to both doctors ok — is measured** into the envelope. | The documented reboot path, with a bigger machine on the other side of it; the counts are the evidence that nothing was lost, not the shutdown's exit code (D145). | — |
| **D1994** | — | The envelope's latency rows (Session 35's neighbour phases, the deploy windows) were sampled on the old 2-vCPU CPU; Hetzner may hand the rescaled server another vendor's CPU. Nothing in the product reads the CPU model; `cpus` limits (`SERVICE_RESOURCE_DEFAULTS`, `config.py:686`) are counts. | **Every envelope row Session 36 adds names the CPU it ran on** (`lscpu` model, vCPU count) in its conditions; the Session 35 rows keep theirs (*"the 3,814 MB deployment host, no swap, 2 vCPU"*) and are not re-labelled. The deploy windows are re-measured on R2 (the probe). | A number moves with the machine it was sampled on (D593, D603); saying which machine is what keeps an old row from reading as a new one. | — |
| **D1995** | Stage plan D1974: *"the three remaining rotations"*; D1469: *"the application credential, on both projects"*. | The nine node ids read **project A only** (`test_session5_convergence.py`, `test_session4_convergence.py:454-512` reads `APG_PROJECT_A_OUTPUTS` for the comparison; the B document only for context). Each rotation is a provider replacement, a `down`, a materialize and a deploy — an outage of the project's API each time. | **Three rotations, all on alpha, one sheet each (X1 authenticator, X2 documentation, X3 application credential), on day 2 before the sweep.** Beta's three are named in §10 as the first entries a rotation schedule must carry. The sheet says at its top that the trio moves on alpha's evidence because that is what the proofs read. | Rotating beta too would cost three outages that no proof reads; the claim is about the plane's ability to rotate, which one project proves. | 0088, 0174 |
| **D1996** | — | `docs/operator-guide.md` §9 (`:507-513`) says the authenticator and documentation rotations were *"Performed … on 2026-08-13 and in Session 11's window"*; §13 (`:710-712`) says the three *"have still never been performed"*. The trio was `not_run` at every evidence document since. | **Run 1 reads the Session 6 and Session 11 plans' Done records** (`grep -n "2026-08-13" docs/plans/session-0[6-9]*.md docs/plans/session-1[01]*.md`) and writes which is true; **Run 8 corrects the guide** to one sentence with its date. Either way the trio is moved only by Run 10's sweep. | A guide that contradicts itself about whether an irreversible act has been done is the sentence an operator reads before doing it. | — |
| **D1997** | Stage plan D1974: *"each declared secret gets a `max_age_days` … the doctor reads each secret generation's age"*. | **No per-secret time exists anywhere**: a generation id is `secrets.token_hex(8)`, *"Not a timestamp"* (`materialize-secrets.py:64-72`); a generation's `manifest.json` carries one `materialized_at` for the whole set, and every deploy materializes a new generation with identical values; `infisical_client.read_secret` (`:254-287`) reads `secretValue` and nothing else. Whether the provider's response carries a per-secret `version`, `createdAt` or `updatedAt` **has never been measured**. | **Sheet E0 measures it** (one root read: the KEY NAMES of `response["secret"]` for `docs_basic_auth_password`, never a value). **If a per-secret update time exists**, Run 6 builds `doctor --reading secrets` (ADR 0250): `max_age_days` optional per secret in `secrets.required.yaml` (schema field, default absent = no reading), each read as `ok \| overdue \| unknown`, never a rotation. **If it does not**, Run 6 is replaced by a row and no code, ADR 0250 is not written, and the schedule waits for a session that records rotation times itself. | A schedule needs an age; an age the system cannot read is a value that looks measured (D600). The branch is decided by one reading before any code. | **0250** (conditional) |
| **D1998** | Stage plan §5: *"one sweep"*. | `port_allocation`'s reboot proof needs `APG_AFTER_REBOOT` in the sweep that writes the evidence; the trio needs the four `--rotated-*` files in the same one; a `-k` run writes no evidence; one sweep per trip (the last ran ~53 min, 1,083 tests). The rescale's own boot is on day 1, and three deploys follow it on day 2. | **One sweep, on day 2**, after X1–X3 and a reboot (B1, so the reboot the sweep declares is the last thing before it): every declaration the gate accepts **except** `--replacement-host-outputs` and `--replacement-bootstrap-state` (no replacement exists, D1991) and `--dx-record-file`'s new walk (it keeps the Session 25 record) — §7 lists them. **Day 1 verifies with `-k` only.** The tag goes on the deployed commit after day 2's merge (D1425). | The evidence document is one sweep's; splitting the claims across two sweeps is a merge `write-session-evidence` refuses. | — |
| **D1999** | Stage plan D1978: *"Session 36 writes the hosted rows before any code"*. | `parse_threat_table` reads **every `\|` line** in `docs/threat-model.md` (`test_acceptance_registry.py:425`) and `test_every_threat_row_names_at_least_one_requirement` (`:484`) fails a row with no registered requirement. The hosted controls (invitations, keys, the reconciler, the gateway, branches, plans) have no requirement until Sessions 37–41 register them. | **The hosted threats are a numbered LIST under a new heading `## Hosted threats, written before their controls (Stage 5)`**, placed before `## Scope`, one item per surviving specification §49 threat (the stage plan's D1978 list) naming the session that builds its control and the negative test it owes. **Each moves into the table, as a `THR-*` row with its requirement, in the run that registers the requirement.** The Scope paragraph gains the sentence D1978 writes. | A row with an invented requirement would be a control that looks measured; a list is the honest form of a threat whose control does not exist yet. | 0246 |
| **D2000** | Stage plan D1979: the Ledger's guard checks *"(1) every console control and every `/api/v1` operation type maps to an entry; (2) an entry `planned` has no operation type and no enabled control; (3) the forbidden words appear in no served page, no `docs/` page and no API string"*. | There is no console, no `/api/v1`, no operation type and no served customer string. `docs/` uses *autoscaling*, *multi-region* and *failover* in the non-goals (`product-contract.md:476-479`) and in the specification's quotation in the stage plan — negations. | **The guard ships with the halves that have a subject**: the schema; every `available`/`beta` row's `evidence` resolves (a claim in `CLAIMS` that is `passed` in the newest `evidence/session-*.json`, or a `capacity.ENVELOPE` subject); every `planned` row's `controls` is `[]`; **the §59 words appear in no row's `customer_text`**; the rendered page is current. **The control and operation-type halves land in Sessions 37 and 42** — Run 5's test says so in a docstring and asserts the two sets it would read are empty today. | A guard over a set that does not exist yet passes vacuously; one that names its empty set fails loudly the day the set appears. | **0247** |
| **D2001** | Stage plan §2.2: *"one minor per session — unless `upgrade plan` prices it at major"*. | ADR 0162: a released migration is minor; `upgrade plan` reads a migration only when declared (D1703); a new `bin/` command is not a manifest, contract or secret change. No manifest, outputs or host schema moves here (the rescale changes `host.yaml`'s VALUES, not its schema). | **`1.14.0`, minor by declaration**: Run 9's Sheet R1 runs `upgrade plan … --also migration_added` against the deployed documents before the first 1.14.0 deploy, and the release paragraph says the floor is minor *by declaration*. A `major` is §9's stop. | The version is read, never chosen (D704). | 0162 |
| **D2002** | ADR 0213: *"Retention is an act an operator performs, on a horizon the operator states … Nothing in this product deletes an agent record on its own"*; its prunes are called by *"a human at a TTY"*. | No verb exists; the documented removal is a root `psql` with names typed by hand. | **`bin/record.sh` is the operator's TTY act made a command**: root, `--project KEY` resolved to the deployed document, `--before` REQUIRED (ISO 8601, validated before any connection), `--confirm KEY` equal to the project key, `--what runs\|deliveries\|agents\|audit\|idempotency`, counts printed before and after from `record_size()`; never run by a unit, a timer or another command (a test greps `systemd/`, `bin/` and `services/` for a caller). ADR 0248 extends 0213 and says the rule is kept. | A verb that requires a stated horizon and a typed confirmation is the TTY act with fewer ways to mistype a container name. | 0213; **0248** |
| **D2003** | Stage plan D1977: *"one `logging` handler configured in `create_app` for `apg.*` at INFO, JSON lines on stdout"*. Scope-closure §28: D1918 is *"a product change with a log-volume question; the operator's"*. | The `apg.http.request` line carries the route TEMPLATE, the request id, the method, the status and the elapsed time, never a path, a header or a body (`main.py:412-427`); `apg.mcp.read` a fixed field set (`mcp_telemetry.py:58-67`); Docker's `local` driver keeps 10 MB × 5 per container. The operator's acceptance of the Stage 5 plan carried D1977. | **ADR 0249: one stdout handler, installed once, on the loggers `apg` and `app.workflow_worker` at INFO**, in a new `services/auth-api/app/log_setup.py` called first in `create_app` — idempotent (a marker attribute on the handler; `create_app` called twice installs one), `propagate = False` on both so a host harness's root handler never doubles a line, the formatter `%(message)s` (the lines are already `<name> <json>`). **The log-volume answer, in the ADR**: one line of ~200 bytes per request; 50 MB per container holds ~250,000 requests — at Session 35's saturation (~480 req/s) nine minutes, at the measured idle-to-light traffic days. | The lines were designed to be safe to print and were never printed; the canary already guards their content. The volume figure is the operator's question answered with the tree's own numbers. | **0249** |
| **D2004** | Stage plan D1949: *"amends `product-contract.md` §5"*. | §2 *"Outside the boundary — deliberately not reproduced"* (`:51-56`) lists *"A hosted control plane, web console, or multi-region availability"* and *"Autoscaling, scale-to-zero, and compute/storage separation"* and *"Instant branching and copy-on-write database forks"* — the same decisions §5 records, in a second place. | **ADR 0246 amends §2's list and §5's together**, with one sentence in each pointing at the ADR; the generated blocks (`:88-395`, `:404-468`) are not touched. | Two lists stating one boundary must move together or one becomes a stale promise (D954's direction). | **0246** |
| **D2005** | Stage plan §2.3: *"D1936 … the sheet offers the edit as a separate line the operator may skip."* | Beta's manifest is schema 7, `approvals_required` absent (= 0), so the host does not read beta's committed approval (D1936). | **Sheet R2b offers ONE optional line before beta's 1.14.0 deploy**: the manifest raised to `schema_version: 8` with `migrations.approvals_required: 1` (the agent edits `/home/op/agentic-postgres/project.beta.yaml` as `op` with a backup, the operator says yes or no on the sheet). The deploy then reads the committed approval for the example set (already applied, so nothing pending — the gate refuses only an act). The answer is recorded in Run 9's Done. | The operator's edit, offered at a moment the release is being deployed anyway. | 0243 |

**Rows the runs add** (D2006 onward), in execution order:

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2006** | §1 D1998, §5 Run 7 item 9, Run 10 S1: *"every declaration the gate accepts **except** `--replacement-host-outputs` and `--replacement-bootstrap-state`"*. | **Session 35's F6 sweep DECLARED `--replacement-bootstrap-state /home/op/replacement-bootstrap-state.json`** (`~/s35r10/s35-r10-gate.sh:151`); the flag admits REC-KIT-002's live half (`session-35-check.sh:441-447`; `test_session18_recovery.py:267` requires `APG_REPLACEMENT_BOOTSTRAP_STATE`), and **`disaster_kit` (REC-KIT-001, -002) is `passed` in `evidence/session-35.json`** — measured in Run 1. The file is the record Session 18's adoption left; it names no replacement this session makes. | **S1 declares `--replacement-bootstrap-state` exactly as F6 did.** Only `--replacement-host-outputs` (which F6 did not declare either) stays undeclared, and `replacement_host_restore` stays `not_run` by D1028. Run 7's `s36-sweep.sh` is derived from F6 by diff, so the flag survives by construction; the derivation's token diff must show it present. | Following D1998 as written would have moved a `passed` claim to `not_run` — a regression produced by a plan sentence, caught by reading the previous sweep's actual line (D977's habit). | — |
| **D2007** | §2 `OPS-LOG-002` and §5 Run 4: *"after a request with a known `X-Request-Id` … `docker logs` … holds one `apg.http.request` line naming that request id"*. | **Rig 36c: the line's `request_id` is never the caller's.** `request_id.py:1-5`: *"Nothing in this module reads an inbound `X-Request-Id`"*; the plane mints the id and returns it on the response's `X-Request-Id`. In the rig, three requests carrying caller ids `…0001`–`…0003` produced lines naming three other ids, and `…0001` appeared in no line. | **The live proof reads the id from the RESPONSE's `X-Request-Id`** and asserts exactly one line names it; it also sends a planted caller id and asserts that id appears in no line (the control that the minting holds). `OPS-LOG-002`'s text is written that way in Run 8. | A proof that sent an id and looked for it would fail on first execution (CLAUDE.md §7 question 2) — or, worse, pass the day someone made the plane trust a caller's id. | 0160, **0249** |
| **D2008** | §1 D1989 / §5 Run 2 item 2: *"no `parked` step … whose `await_event` equals the event's `name`"*. | `workflow_step.await_event` holds **`name@version`** (`0036:173`'s CHECK regex); `connector_event` holds `name` and `version` in two columns (`:116-117`). **D1989's question, read in Run 1**: `0036:877-878` — *"An event emitted before the park does not serve it"*; `app.emit_event` serves waits only at emission (`:230-241`), `workflow_await_event` clears the payload when it parks (`:899-902`), and the only other readers of `connector_event` join it through a delivery (`:453`, `:823`). | **The guard compares `s.await_event = e.name \|\| '@' \|\| e.version`** (rig 36b ran it that way and kept the awaited event). The guard is **belt-and-braces**: no reader would serve a parked step from a stored event. Kept, because it costs one `NOT EXISTS`. | The plan's wording would have compared `order.paid@1` with `order.paid` and never matched — a guard that silently guards nothing. | 0248 |
| **D2009** | §1 D1998's header row and ADR 0247's field list (§5 Run 1): `today_evidence` — *"a claim or envelope subject or `null`"*; §1 D2000 and §2 `LEDGER-001`: *"every `available`/`beta` row's `evidence` resolves"*. | The plan names two different fields for the evidence, in two places, without saying whether they are one. | **Two fields, two meanings** (ADR 0247): `today_evidence` proves the `today` sentence (what the appliance does now for its operator, nullable); `evidence` proves a customer-facing `available`/`beta` status (non-empty exactly then, empty otherwise). The guard resolves both. | A substrate claim that passed for the operator is not evidence that a customer can reach the thing; one field would let the first be read as the second. | **0247** |
| **D2010** | §5 Run 1, ADR 0246 item (1): *"their index rows' Status cells become `Superseded by 0246`"*. | `test_the_index_status_agrees_with_each_adr` (`test_acceptance_registry.py:552-581`) compares the FILE's first word with the index cell **up to its first comma, whole** — `Superseded by 0246` read as `superseded by 0246` ≠ `superseded`; measured red in Run 1's first targeted run. | **The cells read `Superseded, by 0246`** (the house shape: `Accepted, superseded in part`); the files' status lines begin `superseded by [0246](…)` / `Superseded by [0246](…)`. Re-run: 24 passed. | The test is right; the plan's cell text was a transcription of the ADR template's line, not of the index's convention. | 0246 |
| **D2011** | §5 Run 1, the Scope sentence: *"The Scope section gains: … Denial of service is in scope for the creation paths and the public Postgres port as admission and rate limits"*. | `docs/threat-model.md`'s Scope list excluded *"Denial of service"* outright (`:166-167` before the edit). Adding the sentence alone would leave the section contradicting itself. | **The bullet is narrowed** to *"Denial of service as availability"*, pointing at the new sentence; the sentence is added as the plan wrote it. | One section saying DoS is in and out of scope is the self-contradiction D1996 is about, one document over. | 0246 |
| **D2012** | §1 D2003: *"at Session 35's saturation (~480 req/s) nine minutes"*. | Session 35's saturation was measured **against the REST path (PostgREST)**, which never passes through the auth container whose log this is; the auth container serves `/api/app/*` only. | **ADR 0249 states the figure with its condition**: ~250,000 requests per container before rotation; *"at a sustained 480 requests per second (Session 35's saturation rate, measured against the REST path, not this container) it would be about nine minutes"*, and days at measured traffic. | A rate from another service presented as this one's would be a number that looks measured (D593, D603). | **0249** |
| **D2013** | §1 D1987, §5 Run 2 item 4: call the withdrawal *"immediately before each `await sleep(POLL_SECONDS)` (`:828`, `:896`)"*. | `workflow_worker.py:828` is `run_forever`'s IDLE sleep; **`:896` is `supervise`'s restart sleep, reached only after the loop RAISED** (`log.exception("the workflow loop raised; restarting it")`) — an error path, where the database is a likely cause. | **Only the idle sleep** (`_withdraw_ended_approvals(repository)` before `await sleep(POLL_SECONDS)` in `run_forever`). The supervisor's sleep is unchanged; the loop it restarts reaches the idle call within one poll anyway. | Housekeeping on the error path would add a database call exactly when one just failed, and log a second warning for one fault. | 0248 |
| **D2014** | §5 Run 2 item 4: *"make each one say what it does with `withdrawn` — `workflow_worker.py:746` and `service.py:1035` at least (D979)"*. | **`service.py:1035`'s `"expired"` is the PASSWORD-RESET refusal** (`consume_password_reset`), not an approval reader. The approval-status readers (grepped in `services/auth-api/app/`, `bin/`, `src/`, and every `0035`–`0037` SQL reader): `workflow_worker.py:746` (`_close_gate`: `pending`/`expired` → expire, anything else → `approval_<status>` by its own word, ADR 0195), and SQL that filters `= 'pending'`/`= 'approved'` or passes `a.status::text` through (`0035:692-694`, `:892-893`, `:1223-1225`; `0036:938-939`). `models.py:381`'s `Literal["approved", "rejected"]` is a DECISION input, not a status. | **No Python reader changes.** `_close_gate` reads a gate only on a step this worker holds on a `running` run, and a `withdrawn` approval exists only on an ENDED run, so its `else` branch (`approval_withdrawn`) is unreachable and already honest if reached. | D979 asks for every reader to be grepped, not edited; the grep found one that is not a reader and none that misreads the new value. | 0248 |
| **D2015** | §1 D2002 and §5 Run 3: `record.sh` calls *"the five function names"*, including 0033's two; §2 names no existing test that moves. | **`test_agent_audit_plane.py::test_nothing_in_this_release_calls_a_prune` (`:2952`, AGT-RETAIN-001, passing) asserts that NOTHING in `src/`, `bin/`, `services/` or the templates names `agent_audit_prune` or `agent_idempotency_prune`** — `bin/record.py` does, by D2002's decision. The plan did not see the collision. | **Replaced by a stricter test under ADR 0248** (which now says so): the callers are EXACTLY `bin/record.py`'s two — a second caller fails, and so does the command losing its call — and `test_record_command.py::test_nothing_schedules_a_prune` proves nothing calls `record.sh`/`record.py`. AGT-RETAIN-001's description says *"nothing … calls either prune on its own … the ONE caller is `bin/record.py`"*. | A contract test changes only with an ADR (CLAUDE.md §6); widening an allowlist to a measured, named set is not weakening, and the exact-set form asserts one thing more than the old one did. | **0248** |
| **D2016** | §5 Run 3's usage: *"`sudo bin/record.sh --project KEY size [--json]`"*, and *"the command in `COMMANDS_WITH_VERBS`"*. | `test_cli_contract.verbs_documented_by` (`:495-520`) derives a verb as the FIRST lowercase word after the command's name on a usage line; `--project` first derives none, and `test_every_command_documenting_verbs_is_named_in_the_control` would then refuse the entry. | **Verb first**: `sudo bin/record.sh size --project KEY [--json]` and `… prune --project KEY --what … --before … [--limit N] --confirm KEY`. `size --help` and `prune --help` are reads (no root, no docker). | The derivation is the guard; the usage line is written so the guard can read it, never the guard narrowed (D464's habit). | 0248 |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**One new family, `LEDGER`** (ADR 0247): the regex at
`tests/contract/test_acceptance_registry.py:~106` gains `LEDGER`, and the family
paragraphs gain one sentence: *Session 36 (ADR 0246-0250) adds `LEDGER` for the
Reality Ledger — the record of what each product concept is today, read by a
program; record retention extends `OPS-RETAIN` and the request log `OPS-LOG`.*
**Six requirements, six claims, all `target_session: 36`, all P0 — four
offline, two host** (eight, five and three if Run 6 builds, below). Every
requirement belongs to a claim (D697); a new requirement gets a claim of its
own (ADR 0089). **Node ids below are proposed; Run 8 writes what the runs
actually wrote, read out of the tree with `pytest --collect-only -q`** (D1236,
D1762). Registry entries are committed by Run 8 with the constant (D690), in a
block under **`# Session 36 (ADR 0246-0250)`**.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `OPS-RETAIN-001` | Migrations 0038 and 0039 add the approval status `withdrawn` and five `app_private` functions: `workflow_run_prune`, `connector_delivery_prune` and `agent_prune` (each `(p_before timestamptz, p_limit integer DEFAULT NULL) RETURNS bigint`, SECURITY DEFINER, executable by NO role, refusing a missing, future or bound-less horizon with `PT422`, `workflow_run_prune` also one newer than `now() - 600 s`), `record_size()` (executable by no role) and `workflow_withdraw_ended_approvals()` (executable by `auth_service` alone); a run prune removes ended runs and exactly their attempts, approvals, receipts and steps, never a `queued`, `running` or `compensating` run; a delivery prune never removes a `pending` delivery or an event a parked step awaits; an agent prune never removes an active agent or one a run or connector references; the withdrawal moves exactly the pending approvals of ended runs; the worker calls it on an idle iteration | `tests/contract/test_record_retention.py::test_every_prune_is_executable_by_no_role`, `::test_the_withdrawal_is_executable_by_the_auth_service_alone`, `::test_a_horizon_is_required_past_and_bounded`, `::test_a_run_horizon_inside_the_replay_window_is_refused`, `::test_a_run_prune_removes_ended_runs_and_exactly_their_children`, `::test_a_live_run_is_never_pruned`, `::test_a_delivery_prune_keeps_pending_deliveries_and_awaited_events`, `::test_an_agent_prune_keeps_active_and_referenced_agents`, `::test_the_bound_counts_roots`, `::test_the_withdrawal_moves_only_pending_approvals_of_ended_runs`, `::test_the_size_reading_names_every_prunable_relation`, `tests/contract/test_workflow_worker.py::test_an_idle_iteration_withdraws_ended_approvals` (or the module that holds the loop's tests — grep `run_forever` in `tests/`), `tests/contract/test_migrations.py::test_0038_adds_only_the_withdrawn_value`, `::test_0039_grants_the_prunes_to_nobody` | — (offline claim `record_retention`) |
| `OPS-RETAIN-002` | `bin/record.sh --project KEY size [--json]` reads `record_size()` through the project's database container and prints one line per relation with three outcomes; `… prune --what runs\|deliveries\|agents\|audit\|idempotency --before ISO8601 [--limit N] --confirm KEY` refuses without root, without `--before`, with an unparseable or future horizon (before connecting), with `--confirm` not equal to the key, and prints the size before, the function's count and the size after; no unit, timer or other command calls it | `tests/contract/test_record_command.py::test_prune_requires_a_horizon_and_a_confirmation`, `::test_an_unparseable_or_future_horizon_is_refused_before_any_connection`, `::test_the_container_and_database_are_read_from_the_deployed_document`, `::test_prune_prints_before_count_and_after`, `::test_size_reports_unknown_when_the_cluster_does_not_answer`, `::test_nothing_schedules_a_prune`, `tests/contract/test_cli_contract.py` (the command registered; parametrised cases) | — (offline claim `record_command`) |
| `OPS-RETAIN-003` | On the deployment: beta carries no `pending` approval on an ended run within two worker polls of the 1.14.0 deploy; `record.sh --project beta-dev size --json` agrees with a direct count of every relation it names | — | `tests/deployment/test_session36_operations.py::test_no_pending_approval_outlives_its_run`, `::test_the_record_size_reading_matches_the_tables` (host claim `record_retention_live`) |
| `OPS-LOG-001` | `create_app` installs exactly one stdout handler on the `apg` and `app.workflow_worker` loggers at INFO (twice-called, still one), with `propagate` off; a request produces one `apg.http.request` line carrying the route template and the request id and no path, header, token, URL or body; the existing canaries hold | `tests/contract/test_request_log.py::test_create_app_installs_one_handler_on_each_logger`, `::test_a_request_prints_one_line_with_the_template_and_no_caller_value`, `::test_the_worker_logger_prints_info`, `::test_no_line_is_printed_twice` | — (offline claim `request_log`) |
| `OPS-LOG-002` | On the deployment: after a request with a known `X-Request-Id` to alpha's auth service, `docker logs` of alpha's `auth` container holds one `apg.http.request` line naming that request id and holds no bearer token | — | `tests/deployment/test_session36_operations.py::test_a_request_line_reaches_the_auth_containers_log` (host claim `request_log_live`) |
| `LEDGER-001` | `docs/reality-ledger.yaml` validates against `schemas/reality-ledger.schema.json`; every `available` or `beta` row names evidence that resolves (a claim `passed` in the newest evidence document, or a `capacity.ENVELOPE` subject); every `planned` row has no control; no row's `customer_text` uses a specification §59 word; `docs/reality-ledger.md` is the renderer's current output; the operation-type and console-control sets the guard will read are empty today | `tests/contract/test_reality_ledger.py::test_the_ledger_validates`, `::test_available_and_beta_rows_name_evidence_that_resolves`, `::test_a_planned_row_has_no_control`, `::test_no_customer_text_uses_a_forbidden_word`, `::test_the_page_is_current`, `::test_the_sets_the_guard_will_read_are_empty_today` | — (offline claim `reality_ledger`) |
| *(Run 6, if built)* `OPS-ROTATE-001` | `secrets.required.yaml` admits an optional `max_age_days` per secret; `doctor --reading secrets --project KEY` reads each such secret's provider update time and reports `ok`, `overdue` or `unknown` (never a value, never a rotation) | `tests/contract/test_secret_age.py::…` (named by Run 6) | — (offline claim `secret_age`) |
| *(Run 6, if built)* `OPS-ROTATE-002` | On the deployment: the reading reports every secret that declares an age on alpha with a non-`unknown` outcome | — | `tests/deployment/test_session36_operations.py::test_every_declared_secret_age_is_read` (host claim `secret_age_live`) |

**Expected counts** — Run 8 counts them from the tuples, never from this prose
(D1628): requirements **291 → 297** (299 with Run 6), `CLAIMS` **198 → 204**
(206), `OFFLINE_CLAIMS` **60 → 64** (65), ADRs **245 → 249** (250).

**Claims** (`src/agentic_postgres/evidence_claims.py` `CLAIMS`, in a block
commented *Session 36 (ADR 0246-0250)*): offline — `record_retention:
("OPS-RETAIN-001",)`, `record_command: ("OPS-RETAIN-002",)`, `request_log:
("OPS-LOG-001",)`, `reality_ledger: ("LEDGER-001",)` (+ `secret_age:
("OPS-ROTATE-001",)`) — **these in `OFFLINE_CLAIMS`**, with the per-session
assertion in `test_session_thirty_six_gate_modes.py` (D1237: assert THESE are
in the set, never the set's size). Host — `record_retention_live:
("OPS-RETAIN-003",)`, `request_log_live: ("OPS-LOG-002",)` (+ `secret_age_live:
("OPS-ROTATE-002",)`) — not declared. `CLAIM_INTRODUCED_IN`
(`tests/contract/test_evidence_claims.py:953`) gains a row at 36 for each.

**Existing entries that move** (each a passing proof made stricter or a
sentence corrected, never weakened — CLAUDE.md §6):

- **`test_workflow_substrate.py:274`** (`== 37`) → `== 39` in Run 2, its
  per-session comment extended, in whatever registry entry holds it.
- **`OPS` entries that say the record is never pruned** — grep `prune` and
  `ADR 0213` in the registry's descriptions in Run 3; a description that says
  *no command* is corrected to name `record.sh`.
- **`THR-*` table rows**: none move; the hosted threats are a list (D1999).
- **The rotation trio, `port_allocation`, `replacement_host_restore`**: no
  entry moves — the evidence does (§7).

**New environment gates: none.** The live proofs read `APG_PROJECT_A_OUTPUTS`
and `APG_PROJECT_B_OUTPUTS` (both in the roster, `tests/conftest.py`). **The
Session 36 gate therefore accepts exactly the flags the Session 35 gate
accepts** — the derivation diff proves it (D1133).

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| Migrations **0038** and **0039** frozen into `migrations/released.lock.json` | Run 2 | `bin/migrate.sh freeze-lock` is the only writer; the proofs apply every released migration as `migration_user` on a fresh container before the freeze; each down is `AP900`; once applied on the host they are the floor (ADR 0162 §3); **no earlier migration is amended** (D912); 0038 adds one enum value and nothing else, 0039 adds five functions and no table, column or `api` object |
| **The server rescaled** (CPU and RAM only) | Run 9, Sheets H1–H2 | An incremental backup and the counts first; a clean `systemctl poweroff`; **"CPU and RAM only"** keeps the 38 GB disk and therefore the option to downgrade — the only part of a Hetzner rescale that is one-way is a disk upgrade, which this plan never takes; the Primary IPv4 read before power-on; the counts compared after |
| `host.yaml`'s `memory_mb` re-declared | Run 9, Sheet H4 | A backup (`host.yaml.pre-s36`) and the diff first; the reserve and the disk fields refused by the script if they would move (D1992) |
| **Rows deleted on beta** by `record.sh prune` | Run 9, Sheet R4 | The operator states each horizon on the sheet (the plan proposes `2026-10-01T00:00:00Z` for runs and deliveries — before Session 35's trip — and the operator may write another); `size` is printed before and after; the backups taken that night still hold every deleted row for the retention window (`repo1-retention-full` 2); **no prune runs on alpha** |
| `CURRENT_SESSION` 35 → 36; `VERSION` 1.13.0 → 1.14.0 | Run 8 | All-or-nothing (D690); every `target_session: 36` entry in the same commit; the upgrade guide gains a `1.14.0` row; `README.md:7` moves; every `--session 35` / `--through-session 35` literal on the documented path moved and counted per file (D678/D1484) |
| `bin/session-36-check.sh` | Run 8 | Derived from 35's by diff (D1482); header and usage rewritten whole (D1488); `SHELL_COMMANDS` gains it and `chmod 755` before `git add` (D1014, D1188); the flag diff empty |
| Deploy `--through-session 36` on alpha, then beta | Run 9, Sheets R2a/R2b | `upgrade plan` OK first (R1); alpha first; under `script(1)`; **0038 and 0039 applied** (ledger 37 → 39; beta 39 + 4) |
| **Three credentials rotated on alpha** | Run 10, Sheets X1–X3 | The old value captured to a root-only file before the provider is touched (the proofs refuse a false declaration); one rotation per sheet; `project-runtime.sh … down` before each deploy (D253); the doctor read after each |
| The reboot | Run 10, Sheet B1 | After X3's doctor; the units' `active` state read before the sweep |
| Tag `1.14.0` on the deployed commit | Run 10 | After the merge exits 0 or 5 for the expected reasons only (§7); `release-reading --ref <deployed sha>` first |

---
## 5. Build order, run by run

Each run ends with a `**Done.**` paragraph written by the executor: what was
measured, the numbers, the rows it added, and — for a code run — the CI verdict
by full SHA. A run that changes code pushes and reads CI; the targeted modules
run ONCE at the run's close and only the failing module is re-run (the user has
asked thirteen times). `ruff format && ruff check` before every commit;
`chmod 755 bin/*.sh bin/*.py deploy.sh` before every `git add`; commit messages
from a file with `-F`, ending with the attribution line the session's system
reminder gives. **Grep the plans for every third party before measuring it**
(`grep -rn -i '<term>' docs/plans/*.md docs/decisions/*.md`). **A run that
renames, adds or removes a test function runs `test_acceptance_registry` and
`test_evidence_claims`** (D1119, D1674); **a run that adds a `GRANT` ships its
caller in the same commit** (D1680 — 0039's grant to `auth_service` ships with
the worker's call); **a run that adds a migration re-renders BOTH example
projects** before its targeted list (D1678: `./deploy.sh --project
project.example.yaml --capabilities capabilities.example.yaml --render-only`
and the same for `project.second.example.yaml` — read `./deploy.sh --help` for
the exact spelling, and delete what the render publishes under `.generated/`
afterwards, CLAUDE.md §1); **a run that adds or removes a `bin/` command runs
`test_cli_contract` and `git add`s the command first** (D1014, D1188); **a run
that touches a documentation page runs `test_documentation_index` and
`test_session12_documented_path`**; **every new test module carries
`pytestmark` before its first test** (D1240) and the sweep-selector guard
(D1242) is in the targeted list of any run that adds one.

**The Docker-backed modules are the slow ones** (~3 min each). Keep two lists
per run: the fast modules after each edit, the Docker-backed ones ONCE just
before the commit.

### Run 1 — the rigs, Sheet E0, the hosted threats, the product contract, and ADRs 0246–0249


**Documentation only. Push, say it is pushed, read NO CI verdict** — except
that, because `docs/threat-model.md` and `docs/decisions/README.md` are parsed
by tests, run `python -m pytest tests/contract/test_acceptance_registry.py -q
-p no:randomly` ONCE locally before the push and fix what it names.

**Reads first** (agent, no edits): `migrations/templates/0033-agent-record-
retention.sql` whole; `0034-workflow-substrate.sql:100-320`, `:540-580`,
`:800-860`, `:950-1030`; `0035-workflow-gates.sql:50-150`, `:180-260`,
`:900-1110`; `0036-connectivity.sql:40-180`, and every line matching
`await_event` (`grep -n await_event migrations/templates/0036-connectivity.sql`)
with twenty lines around it (D1989); `0011-identity-registry.sql:30-210`;
`services/auth-api/app/workflow_worker.py:80-110`, `:730-900`;
`services/auth-api/app/main.py:225-440`; `mcp_telemetry.py:40-180`;
`docs/operator-guide.md:92-420`,
`:497-545`, `:702-730`; `docs/api-operations.md:84-200`; `docs/decisions/0042-*.md`,
`0043-*.md`, `0044-*.md`, `0185-*.md`, `0213-*.md`,
`0216-*.md`, `0217-*.md`, `0221-*.md`, `0245-*.md`; `docs/product-contract.md:
1-60`, `:470-545`; `docs/threat-model.md` whole; this plan's §1; the Stage 5
plan's §1 rows D1949, D1973–D1979.

**The rigs.** Each is a script written with the Write tool to
`\\wsl$\Ubuntu\tmp\rig36\rig36x.py` (or `.sh`) and copied to the scratchpad;
each names its image by digest (`versions.env`'s `POSTGRES_IMAGE`); each has a
control; each prints its own exit status from inside. Any Python that imports
`agentic_postgres` needs `PYTHONPATH=src`. **A heredoc inside `wsl bash -lc
"…"` is forbidden (CLAUDE.md §1)** — every SQL body is a file the script reads.

- **36a — an enum value and its first use.** A throwaway container from
  `POSTGRES_IMAGE` (`docker run -d --rm -e POSTGRES_PASSWORD=x …`); create a
  type `t AS ENUM ('a','b')` and a table using it. **Measure**: (i) `BEGIN;
  ALTER TYPE t ADD VALUE 'c'; UPDATE … SET v = 'c'; COMMIT;` — expect `unsafe use
  of new value "c" of enum type t` (record the exact text); (ii) the same ALTER
  in one transaction and the UPDATE in a second — expect success (the control);
  (iii) both run through **dbmate** with `--strict` as two migration files (the
  release's own runner: read `bin/migrate.py`'s `run_dbmate` `:157-161` for the
  arguments) — expect success; (iv) the same two files through `psql -1 -f`
  each, as `apg dev up` applies them (`bin/dev.py:403-429`). The answer decides
  D1987's two-file shape; record it in the Done either way.
- **36b — the prunes' deletion order.** On the same container: `apg dev up
  --project project.example.yaml` is the cheaper cluster if it starts (it applies
  every released migration as `migration_user`); otherwise apply 0001–0037 by
  the contract suite's `cluster` fixture's method (read
  `tests/contract/conftest.py` for it). Insert, as the bootstrap superuser, one
  definition, two agents (one revoked), runs in every status, steps, attempts,
  a pending approval on an ended run, a receipt naming a run, an event with a
  delivered and a pending delivery, and a parked step awaiting an event name.
  Write `workflow_run_prune`'s body as **sequential `DELETE … WHERE … =
  ANY(victims)` statements in FK order** after `SELECT array_agg(id) INTO
  victims FROM (SELECT id … ORDER BY finished_at LIMIT p_limit) q` — **measure**
  that it removes exactly the ended runs' rows and that a reversed order
  (runs first) raises a foreign-key violation (the control that the order is
  load-bearing). Then the delivery and agent prunes the same way. **Read 0036's
  event-matching code first** and record whether a parked step is ever served by
  an event older than its parking (D1989).
- **36c — the handler reaches stdout through the image's entrypoint.** Build
  nothing: run the auth application from the checkout as Session 34's rig did
  (read `docs/plans/session-34-implementation-plan.md` Run 1's `**Done.**` for
  the method: both application modes run from the checkout as subprocesses with
  the image's own entrypoint, against `apg dev up`'s cluster), once as the tree
  is (**control**: an `apg.http.request` line ABSENT from the child's stdout)
  and once with a scratch copy of `log_setup.py` imported at the top of
  `create_app` (expect exactly one line per request, carrying the template). If
  the method will not start in an hour, run `python -c` against `create_app()`
  with Starlette's `TestClient` and `capsys`, and say the rig measured the
  factory, not uvicorn.
- **36d — the withdrawal is cheap enough for an idle loop.** On 36b's cluster,
  10,000 approvals across 2,000 runs (half ended): `EXPLAIN (ANALYZE, BUFFERS)
  SELECT app_private.workflow_withdraw_ended_approvals()` twice (the second finds
  nothing). Record the times. **If the second call costs more than 50 ms**, the
  function gains a partial index `ON workflow_approval (run_id) WHERE status =
  'pending'` in 0039 and the rig re-measures.

**Sheet E0 — readings before anything is built** (appendix; `sudo`, reads
only, one script that tees its own transcript to `/home/op/s36-e0.txt`). The
agent writes `/home/op/s36-e0.sh` over SSH as `op` (read it back), the operator
runs it. It reads: (1) `free -m`, `nproc`, `lscpu`'s model, `df -BG
/var/lib/docker /`, `cat /sys/class/dmi/id/sys_vendor /sys/class/dmi/id/
product_name` (the provider's own name for the machine, for the record); (2)
for each project, `systemctl is-enabled is-active agentic-postgres-project@<key>`
and the three timers, and `systemctl is-enabled is-active agentic-postgres-edge`
— the units the rescale's boot depends on; (3) **the KEY NAMES of the
provider's response for `docs_basic_auth_password` on alpha** (D1997), through
the runtime credential the deploy uses — a Python one-off under
`PYTHONPATH=src` that calls the same endpoint `infisical_client.read_secret`
calls (`:254-287`) and prints `sorted(response["secret"].keys())` and NOTHING
else (read the client first; if it cannot be made to print keys without the
value passing through a variable the script also prints, the line is dropped
and D1997 is decided `no reading` with that reason); (4) on beta, `SELECT
app_private.workflow_counts()` and a direct count of pending approvals whose
run is not running (the 7 of D1775); (5) `ls -l` of every file Session 35's
Sheet F6 line names (they are on this host and stay on it — the sweep reuses
them).

**Then the documents.**

- **`docs/threat-model.md`**: a new section **`## Hosted threats, written
  before their controls (Stage 5)`** placed before `## Scope` (`:157`) — a
  numbered list, NOT a table (D1999), one item per threat of the specification's
  §49 that survives the Stage 5 plan's §1, each naming the session that builds
  its control and the negative test it owes: invitation abuse and enumeration
  (37); API-key compromise and replay (37); organisation privilege escalation
  (37); project and branch enumeration (37, 40); endpoint confusion and gateway
  attacks, plaintext and wrong-SNI (39); wake-on-connect abuse (39);
  project-creation and branch-creation exhaustion (38, 40); plan-limit bypass
  and usage tampering (41); restore abuse (40); control-plane / data-plane
  credential confusion (37, 38, 39); project-deletion races and slot reuse
  (38); connector abuse by a customer (42); observability poisoning and
  ClickStack exhaustion (41); cross-project leakage through any new surface
  (every session); storage exhaustion (38). Signup abuse is out (invite-only,
  D1951); support-grant misuse is replaced by D1971's sentence. The Scope
  section gains: *"From Stage 5 (ADR 0246) external users are in scope.
  Denial of service is in scope for the creation paths and the public Postgres
  port as admission and rate limits — still not as an availability SLA."*
- **`docs/product-contract.md`**: §2's *"Outside the boundary"* list (`:51-56`)
  and §5 (`:470-493`) amended per ADR 0246 (D2004): removed — the hosted control
  plane and the hosted console; narrowed — scale-to-zero (*sleep that stops a
  project's containers, triggered by its owner or by idleness*), branching (*a
  branch restored from a backup at a recovery point; copy-on-write forks stay
  out*), cross-project reporting (*the control plane counts its own records and
  reads each project's readings; it never reads a project's rows*); kept whole —
  autoscaling and compute/storage separation, automatic failover and
  multi-region, arbitrary agent SQL, the ORM non-goal. One sentence under each
  heading: *"Amended by ADR 0246 (Session 36)."* The generated blocks are not
  touched.
- **ADR 0246** — *Stage 5's boundary: a hosted product on one node; ADRs 0042,
  0043, 0044, 0216 and 0217 superseded together.* Decision: (1) the five are
  superseded and their index rows' Status cells become `Superseded by 0246`
  (check `test_the_index_status_agrees_with_each_adr` `:552`: the FILE's
  `- **Status:**` line must say the same — edit both); (2) **the ports the host
  may publish: 80, 443, and one Postgres port whose shape Session 39 measures and
  records in its own ADR; until that ADR, none** — `publication()` keeps raising
  and `compose.yaml` keeps zero `ports:` keys; (3) the product contract's
  amendments (D2004); (4) **the boundary sentences** — the control plane holds
  nothing that opens a project's data or admin plane; the reconciler runs only a
  closed set of typed operations; a product surface runs no SQL; a customer's
  own client with the customer's own credential may; an agent never does; (5)
  external users enter the threat model (ADR 0217's third commitment lapses
  with it); (6) what does NOT change in Session 36: nothing at runtime.
  Alternatives rejected: superseding piecemeal per session; keeping ADR 0216 and
  writing exceptions. Consequences: CLAUDE.md §6's *"There is no public
  Postgres endpoint"* stays TRUE until Session 39 and is rewritten then.
- **ADR 0247** — *The Reality Ledger is a program's input.* The file, its
  fields (`id`, `concept`, `status` ∈ `available|beta|planned|not_metered|
  not_offered`, `customer_text`, `today` — what the appliance does now for its
  operator, `today_evidence` — a claim or envelope subject or `null`,
  `stage5_reality`, `eventual`, `controls` — a list, `since_session`,
  `target_session`), the guard's halves (D2000), the rule that a row moves in
  the run that builds the thing.
- **ADR 0248** — *Retention extends ADR 0213 to the Stage 4 record, by
  aggregate, with a verb* (D1985–D1989, D2002).
- **ADR 0249** — *The request and worker lines are printed* (D2003, with the
  log-volume figures).
- **ADR 0250 is NOT written in Run 1**; Run 6 writes it if E0 allows.
- All four indexed in `docs/decisions/README.md` (after `:311`).

**Done.** 2026-10-03, at `b151779`. Rigs in WSL `~/s36/rig36/` (scripts,
SQL and transcripts; backed up to the scratchpad's `rig36/`).

- **36a** (`POSTGRES_IMAGE` 18.4, `DBMATE_IMAGE` 2.34.1): (i) `ALTER TYPE t ADD
  VALUE 'c'; UPDATE … SET v = 'c'` in ONE transaction → `ERROR: unsafe use of
  new value "c" of enum type t`, `HINT: New enum values must be committed before
  they can be used.` (55P04); the type rolled back with it (`a,b`). (ii) **The
  control** — two transactions → rc 0, value `c`. (iii) two dbmate files, `up
  --strict` → both `Applied`, rc 0. (iv) `psql -1 -f` per file (`apg dev up`'s
  shape) → rc 0 each. (v) **ONE dbmate file → dbmate prints `Applied:
  20261003120001_both.sql in 2.457985ms` and THEN `Error: … unsafe use of new
  value "c" … (55P04)`**, rc 2, ledger 0 rows, value `a` — D941's class again.
  **D1987's two-file shape is REQUIRED, not merely safer.**
- **36b** (`apg dev up` on `project.second.example.yaml`, 37 migrations as the
  migration user; the rig in one transaction, rolled back): fixtures 8 runs (every
  status + one ended 1 min ago), 8 steps, 16 attempts, 3 approvals, 3 receipts,
  6 deliveries, 4 events, 4 agents. **Control — runs deleted first → `23503 …
  violates foreign key constraint "workflow_step_run_id_fkey"`.** The FK graph
  read from `pg_constraint` matches §0 exactly (every Stage 4 FK `NO ACTION`;
  `agent_credentials`/`agent_quota` `CASCADE`). Run prune bounded to 2 → 2, then
  unbounded → 2: survivors `queued`, `running`, `compensating`, the
  1-minute-old `succeeded`; approvals left: the running run's `pending`;
  receipts left: the running run's and the run-less one. `LIMIT NULL` = no limit
  (5 of 5). Delivery prune → 4: events left `ev_awaited` (a parked step awaits
  `order.paid@1`), `ev_new`, `ev_pending`; deliveries left: the recent
  `delivered`, the `pending`. Agent prune → 2 (the free revoked one and the one
  whose run was just pruned; credentials and quota 4 → 2 by CASCADE); kept
  `ag_active`, `ag_rev_conn`. `0025:143` moves `updated_at` on every status
  change, so a revoked agent's `updated_at` is no earlier than its revocation.
  **D1989: belt-and-braces** (D2008).
- **36c** (the image's uvicorn argv from two copies of `app/`, `APP_MODE=auth`,
  `--lifespan off`, 5 requests each): **control 0 `apg.http.request` lines;
  arm exactly 5** (one per request; `"route": "/health/live"` ×4,
  `"<unmatched>"` for the 404 POST); planted token, query, body and path: 0
  occurrences in either; **the caller's `X-Request-Id` in no line** (D2007).
  Lines ~140 bytes.
- **36d** (10,000 approvals across 2,000 runs, half ended, 2,000 pending; on the
  same throwaway cluster with `withdrawn` committed first): first call 82.7 ms
  (1,000 withdrawn); the UPDATE's plan on the second pass 0.84 ms (bitmap scan
  of the existing `workflow_approval_status_requested_idx`, hash join to 1,000
  ended runs); the function three more times 1.06 / 1.43 / 1.15 ms. **Under 50
  ms: no partial index.**
- **D1996**: §9 is right — the authenticator and documentation passwords were
  rotated and proved on 2026-08-13 (`session-06-implementation-plan.md:309-316`)
  and again in Session 11's window (`session-11-…:974-976`, `:1243`). **§13's
  *"have still never been performed"* is wrong for those two.** No plan records
  an application-credential rotation. The trio stays `not_run` because no sweep
  since has declared all four files together. Run 8 corrects §13.
- **Documents**: ADRs 0246–0249 written and indexed; 0042, 0043, 0044, 0216,
  0217 → *Superseded, by 0246* (file and index; D2010); `docs/threat-model.md`
  gains *Hosted threats, written before their controls (Stage 5)* — fifteen
  items, no `|` line — and the Scope sentence (D2011); `docs/product-contract.md`
  §2 and §5 amended (D2004). `test_acceptance_registry` (after D2010's fix: 24
  passed), `test_documentation_index` and `test_session12_documented_path`
  (with it: 80 passed, 1 failed → the D2010 cell, fixed, module re-run green).
- **Rows added**: D2006–D2012. D2006 is the one that mattered: the plan would
  have dropped a declaration that keeps `disaster_kit` passing.
- **Sheet E0**: *(pending — the operator's)*.

### Run 2 — migrations 0038 and 0039, and the worker's call

**Code. Push and read CI by full SHA.**

**Reads first**: Run 1's rigs 36a, 36b, 36d and their Done; `migrations/
manifest.json`'s last two entries; `bin/migrate.sh:60-120`;
`tests/contract/test_migrations.py:280-340`; `tests/contract/
test_agent_audit_plane.py:2722-2949` (the prune proofs to copy);
`tests/contract/test_workflow_substrate.py:255-280`; `services/auth-api/app/
workflow_worker.py:730-900`; the repository module the worker calls (grep
`workflow_counts` in `services/auth-api/app/` for the module and its pattern).

**Build.**

1. `migrations/templates/0038-approval-withdrawn.sql`: `-- migrate:up`, a short
   header (why a separate file — rig 36a's measured sentence), `SET LOCAL ROLE
   {{object_owner}};`, `ALTER TYPE app_private.workflow_approval_status ADD
   VALUE 'withdrawn';`, `RESET ROLE;`, the `AP900` down. Manifest entry
   `{"version": "<YYYYMMDD of the day>120038", "name": "approval_withdrawn",
   "template": "templates/0038-approval-withdrawn.sql", "placeholders":
   ["object_owner"], "description": "…"}` — the version must sort after
   `20261001120037`.
2. `migrations/templates/0039-record-retention.sql`, 0033's shape exactly
   (banner sections, `SET LOCAL ROLE {{object_owner}}`, one banner + comment
   block per function, `COMMENT ON FUNCTION` after each, `REVOKE ALL … FROM
   PUBLIC` for all five, **one `GRANT EXECUTE ON FUNCTION
   app_private.workflow_withdraw_ended_approvals() TO {{auth_service}};`** and
   the sentence *"There is no GRANT for any prune or for the size reading, and
   that absence is the decision"*, `RESET ROLE`, *"Nothing in `api` moved, so no
   NOTIFY"*, the `AP900` down). The five functions per D1986–D1988 and rig 36b:
   - `workflow_withdraw_ended_approvals() RETURNS bigint` — `UPDATE
     app_private.workflow_approval a SET status = 'withdrawn' FROM
     app_private.workflow_run r WHERE a.run_id = r.id AND a.status = 'pending'
     AND r.status IN ('succeeded','failed','cancelled','stopped')`; returns
     `ROW_COUNT`. (Plus rig 36d's partial index if it was needed.)
   - `workflow_run_prune(p_before, p_limit)` — 0033's three refusals, plus
     `IF p_before > pg_catalog.now() - interval '600 seconds' THEN RAISE
     EXCEPTION 'AP422: a retention horizon inside the inbound replay window'
     USING ERRCODE = 'PT422'`; victims = ended runs with `finished_at <
     p_before` (`ORDER BY finished_at LIMIT p_limit` when bounded); then, in
     order, DELETE attempts of their steps, approvals of the runs, receipts naming
     the runs, steps of the runs, the runs; returns the number of runs.
   - `connector_delivery_prune(p_before, p_limit)` — 0033's refusals; deliveries
     `status IN ('delivered','dead') AND coalesce(delivered_at, dead_at) <
     p_before` (bounded likewise); then events with `emitted_at < p_before`, no
     remaining delivery, and **no `parked` step of a run not in the ended set
     whose `await_event` equals the event's `name`** (D1989); returns
     deliveries removed.
   - `agent_prune(p_before, p_limit)` — 0033's refusals; agents `status =
     'revoked' AND updated_at < p_before` with no `workflow_run` and no
     `connector` naming them (credentials and quota go by CASCADE); returns
     agents removed.
   - `record_size() RETURNS TABLE (relation text, row_count bigint, oldest
     timestamptz)` — one row each for `agent_audit` (`started_at`),
     `agent_idempotency` (`created_at`), `workflow_run` (`created_at`),
     `workflow_step` (`started_at`), `workflow_attempt` (`recorded_at`),
     `workflow_approval` (`requested_at`), `connector_event` (`emitted_at`),
     `connector_delivery` (`created_at`), `connector_receipt` (`received_at`),
     `agents (revoked)` (`updated_at`), and **`workflow_approval (pending on an
     ended run)`** (count, `min(requested_at)`).
   Manifest entry `"name": "record_retention"`, `"placeholders":
   ["auth_service", "object_owner"]` (sorted as the other entries sort them).
3. `bin/migrate.sh freeze-lock` (clean tree first: commit the templates on a
   scratch branch or follow `--help`'s rule; never hand-edit the lock).
4. **The worker's call.** In the repository module (Reads first), one method
   `withdraw_ended_approvals()` running `SELECT
   app_private.workflow_withdraw_ended_approvals()`; in `workflow_worker.
   run_forever`, call it **immediately before each `await sleep(POLL_SECONDS)`**
   (`:828`, `:896`), inside a `try` that logs a WARNING with the exception's
   TYPE only and never stops the loop; log one INFO line `apg`-free under the
   worker's own logger when the count is non-zero
   (`"workflow.approvals_withdrawn %s", json.dumps({"count": n})`).
   **Grep every reader of the approval status** (`"expired"`, `'expired'`,
   `approval_status`, `status in (` in `services/auth-api/app/`, `bin/workflow.py`,
   `src/agentic_postgres/`) and make each one say what it does with
   `withdrawn` — `workflow_worker.py:746` and `service.py:1035` at least (D979).
5. **Tests**: `tests/contract/test_record_retention.py` (new; `pytestmark`; the
   cluster fixture the other Docker-backed modules use — read
   `test_agent_audit_plane.py`'s module header for it) with §2's names;
   `test_migrations.py` gains `test_0038_adds_only_the_withdrawn_value` and
   `test_0039_grants_the_prunes_to_nobody` (0037's `:301-333` is the model);
   `test_workflow_substrate.py:274` → `39`; the worker's idle call in the module
   that tests `run_forever` (a fake repository counting calls; an idle iteration
   calls it once, a busy one not at all).
6. **The battery** (CLAUDE.md §1): `PYTHONDONTWRITEBYTECODE=1`, `__pycache__`
   cleared, snapshot to `/tmp`, every anchor pre-flighted once. Mutations, each
   with the control named: (M1) `workflow_run_prune`'s status list gains
   `'running'` → `test_a_live_run_is_never_pruned` FAILED (control:
   `test_a_horizon_is_required_past_and_bounded` passes); (M2) the 600-second
   bound removed → `…inside_the_replay_window…` FAILED; (M3) the `await_event`
   guard removed → `…awaited_events` FAILED; (M4) `GRANT EXECUTE … TO
   {{auth_service}}` added for `workflow_run_prune` → `…executable_by_no_role`
   FAILED; (M5) the withdrawal's status list gains `'running'` →
   `…only_pending_approvals_of_ended_runs` FAILED; (M6) the worker's call moved
   to every iteration → the idle test FAILED. Assert HOW each failed (`FAILED`,
   not `ERROR`, D386); restore by copy and `cmp` each file back.
7. Re-render both example projects (D1678), delete what they published under
   `.generated/`, then the targeted list ONCE: `test_record_retention`,
   `test_migrations`, `test_workflow_substrate`, the worker's module,
   `test_agent_audit_plane`, `test_migrations_apply_as_the_migration_user`,
   `test_migration_ledger`, `test_rendered_migrations`, `test_database_commands`,
   `test_change_proposal`, `test_database_function_signatures` (grep it for
   `app_private` pins first), `test_acceptance_registry`, `test_evidence_claims`.

**Done.** 2026-10-03, commit `7cd3372db4c05f31759e932d083e5d3c072fa7b5`.
`migrations/templates/0038-approval-withdrawn.sql` (ONE statement under `SET
LOCAL ROLE`, rig 36a's reason in its header) and `0039-record-retention.sql`
(0033's shape: five functions, all `REVOKE`d from PUBLIC, one `GRANT` — the
withdrawal to `{{auth_service}}` — after every revoke; no table, column, type,
index or `api` object). Versions `20261003120038`/`20261003120039`;
`freeze-lock` → 39, `verify-lock` agrees. The new future-horizon refusal reads
*"must be in the past"* (0033's reads *"is in the past"* for the same case; 0033
is not amended, D912). `WorkflowRepository.withdraw_ended_approvals()`;
`run_forever` calls `_withdraw_ended_approvals` before the IDLE sleep only
(D2013) — a WARNING naming the exception's type on failure, INFO
`workflow.approvals_withdrawn {"count": n}` when non-zero. Approval-status
readers grepped: none changes (D2014). Tests: `test_record_retention.py` (new,
11 proofs, **11 passed on first execution**); `test_migrations.py` +2;
`test_workflow_worker.py` + the idle/busy proof, the fake gains the method and
the heartbeat test's idle sequence gains the call (stricter);
`test_workflow_substrate.py:274` → 39. **Battery 6/6 killed** (anchors
pre-flighted — the first pass refused on an M1 anchor that did not match, with
nothing mutated; each target FAILED, never ERROR, with its control PASSED; both
files restored `cmp`-equal): M1 run prune takes `running`; M2 the 600-s bound
removed; M3 the awaited-event guard removed; M4 `workflow_run_prune` granted to
`auth_service` (killed by the cluster proof AND the text proof); M5 the
withdrawal takes `running`; M6 the worker withdraws every iteration. Both example
projects re-rendered (rc 0). **Targeted list once: 394 passed, 0 failed, 0
skipped** (7 m 51 s; the plan's modules plus `test_workflow_repository.py`, which
holds D1680's guard). A detached `setsid nohup` launch from `wsl bash -lc` died
with its shell before writing a byte; the harness's background mode ran it. CI
for `7cd3372`: *(read in Run 3's Done)*.

### Run 3 — `bin/record.sh size|prune`

**Code. Push and read CI.**

**Reads first**: `bin/doctor.py:640-760` (how the container and database are
derived from the deployed document, and the `docker exec` it builds);
`src/agentic_postgres/container_exec.py` whole (ADR 0218: **new code execs
through `container_exec.run`**); `bin/backup.sh` + `bin/backup.py`'s argument
shape and exit codes (the closest sibling: root, `--outputs`, verbs);
`tests/contract/test_cli_contract.py:42-230` (`SHELL_COMMANDS`,
`PYTHON_COMMANDS`, `COMMANDS_WITH_VERBS` `:469`); ADR 0093 (a `bin/` command
imports only `agentic_postgres` and `yaml`); D1184 (`document` means the
deployed document in `bin/`).

**Build.** `bin/record.sh` (the shell preamble every command has: `#!/usr/bin/env
bash`, `set -euo pipefail`, `BASH_SOURCE`; `--help` honoured anywhere; root
required for every verb but `--help`) exec'ing `bin/record.py`:

```
Usage: sudo bin/record.sh --project KEY size [--json]
       sudo bin/record.sh --project KEY prune --what runs|deliveries|agents|audit|idempotency \
            --before ISO8601 [--limit N] --confirm KEY
```

`--project KEY` resolves `/etc/agentic-postgres/projects/<KEY>/outputs.json`
(the deployed document, D1184) and derives the database container and name the
way `doctor.py` does (one function — if `doctor.py`'s derivation is private,
move it to `src/agentic_postgres/` and have both call it: ADR 0002, grep every
caller first, D979). `prune`: `--before` parsed with `datetime.fromisoformat`,
timezone REQUIRED, refused if in the future — **before any container is
touched**; `--confirm` must equal `KEY`; `--limit` a positive integer. The SQL
is `SELECT app_private.<fn>(:'before'::timestamptz, <limit or NULL>)` with the
horizon passed as a `psql -v before=…` variable, never interpolated; `--what`
maps to exactly five function names in one dict. It prints `record_size()`
before, the count, `record_size()` after. A `PT422`/`AP422` refusal from the
database is printed verbatim and exits 5. `size`: one line per relation —
`relation  rows  oldest` — or, when the cluster does not answer, *"the record
could not be read: <reason>"* and exit 6 (ADR 0195; the doctor's sentence
shape). Exit codes: 0 read/pruned; 2 usage; 3 not root, no document, no docker;
5 refused or failed; 6 could not determine.

**Tests**: `tests/contract/test_record_command.py` (new; `pytestmark`;
subprocess with a fake `docker` on `PATH` the way other `bin/` tests fake it —
grep `fake_docker` or `FAKE_DOCKER` in `tests/contract/` for the existing
helper) with §2's names; `test_nothing_schedules_a_prune` greps `systemd/`,
`bin/` and `services/` for `record.sh` and the five function names and finds
only `bin/record.*` and the migration. Register `bin/record.sh` in
`SHELL_COMMANDS` and `bin/record.py` in `PYTHON_COMMANDS`, and the command in
`COMMANDS_WITH_VERBS`. Battery: (M1) the future-horizon check removed →
`…before_any_connection` FAILED (control: the confirm test passes); (M2)
`--confirm` compared case-insensitively → the confirm test FAILED.

**Docs** (in this run, because the command is new): `docs/operator-guide.md` §5
— the *"Two tables grow without bound and nothing prunes them (D1255)"*
paragraph (`:316-321` in Session 35's numbering; re-find it) rewritten to name
`record.sh`, the five relations and ADR 0248; `docs/workflows.md` and
`docs/connectors.md` *what is not here* sections lose the retention sentence if
they carry one. Targeted: `test_record_command`, `test_cli_contract`,
`test_documentation_index`, `test_session12_documented_path`.

**Done.** 2026-10-03. `bin/record.sh` (preamble, `--help` anywhere is a read,
docker checked only for a verb) and `bin/record.py` (stdlib +
`agentic_postgres` only, ADR 0093): **verb-first usage** (D2016); the key
matched against `^[a-z][a-z0-9-]{0,62}$` before a path is built; the document
read through `deployed_output.read_deployed_document`; every exec through
`container_exec.run` (ADR 0218); the horizon `fromisoformat`, timezone required,
refused in the future, all before root, the document or a container; the
statement `SELECT app_private.<fn>(:'before'::timestamptz, <int|NULL>)` with the
horizon as `psql -v before=…`; size → call → size; a database refusal printed
verbatim, exit 5; an unreadable or ill-shaped reading *"the record could not be
read"*, exit 6; a prune that did not answer is exit 6 saying its outcome is
unknown. Root (3) measured by hand as a user: `size --project alpha-dev` → 3.
`tests/contract/test_record_command.py` (new, 8 proofs, `pytestmark`; 8 passed
first run) — the plan's six plus `…refusal_is_printed_verbatim_and_exits_5` and
`test_size_refuses_without_root` (the real `require_root`); the no-scheduler scan
needs a word boundary (`bin/dx-record.py` names `dx-record.sh`). Registered in
`SHELL_COMMANDS`, `PYTHON_COMMANDS`, `COMMANDS_WITH_VERBS`; `git add`ed first
(D1188). **D2015**: `test_nothing_in_this_release_calls_a_prune` replaced by its
exact-set form under ADR 0248; AGT-RETAIN-001's description corrected;
`render-acceptance-matrix --write` (matrix + product contract). Docs: operator
guide §5's two paragraphs rewritten around `record.sh` and the withdrawal, its
migrations row 37 → 39 (0037–0039 described); the *"Pruning events, deliveries
and receipts"* rows removed from `docs/workflows.md` and `docs/connectors.md`.
**Battery 2/2 killed** (M1 the future check removed →
`…unparseable_or_future_horizon…` FAILED; M2 `--confirm` case-folded →
`…requires_a_horizon_and_a_confirmation` FAILED; each control PASSED;
`record.py` restored `cmp`-equal). shellcheck clean. **Targeted once: 849
passed** (`test_record_command`, `test_cli_contract`, `test_documentation_index`,
`test_session12_documented_path`, `test_agent_audit_plane`,
`test_acceptance_registry`, `test_evidence_claims`; 5 m 22 s). CI: *(Run 4's
Done)*.

### Run 4 — the request log (D1918)

**Code. Push and read CI.**

**Reads first**: Run 1's rig 36c and its Done; `services/auth-api/app/main.py:
225-440`; `mcp_telemetry.py:40-180`; `workflow_worker.py:80-110`;
`tests/contract/test_mcp_budgets.py:500-560`, `:640-680`;
`tests/deployment/test_session7_storage.py:690-760`; ADR 0249.

**Build.** `services/auth-api/app/log_setup.py`: `configure_logging()` —
for each of `("apg", "app.workflow_worker")`: if no handler carrying the
attribute `_apg_stdout = True` is attached, attach a `logging.StreamHandler
(sys.stdout)` with `logging.Formatter("%(message)s")` and that attribute;
`setLevel(logging.INFO)`; `propagate = False`. Called as the FIRST statement of
`create_app` (`main.py:233`), so every mode — `auth`, `storage`, `mcp` — gets
it. Nothing else changes: the lines' content is already fixed.

**Tests**: `tests/contract/test_request_log.py` (new; `pytestmark`) with §2's
names — `capsys`, not `caplog` (the point is the stream); a request through
Starlette's `TestClient` carrying a planted bearer token, a planted query
string and a planted body: exactly one `apg.http.request` line, the route
template present, none of the three planted values present; `create_app()`
called twice → one handler per logger. The existing canaries in the targeted
list. Battery: (M1) `propagate = False` removed and a root handler attached by
the test → `test_no_line_is_printed_twice` FAILED (control: the template test
passes); (M2) the marker check removed → `…installs_one_handler…` FAILED.

**The live proofs** (written now, run by the sweep) — all three of the
session's host proofs live in one new module. In
`tests/deployment/test_session36_operations.py` (`pytestmark` with the live
marker the other `test_session35_*.py` modules use — copy theirs),
`test_a_request_line_reaches_the_auth_containers_log`: `GET` alpha's
`/api/app/auth/jwks.json` through the edge with `X-Request-Id: <uuid4>`; then
`docker logs --since <t0> <alpha auth container>` (the container name from the
deployed document); exactly one line contains the id and starts with
`apg.http.request`; no line contains `Bearer `. Run `pytest --setup-plan` on it
with the variables set (D671). In the same module: `test_no_pending_approval_outlives_its_run` (beta: `record.sh --project
beta-dev size --json`'s *pending on an ended run* row is 0, read up to three
times 5 s apart — two worker polls and a margin) and
`test_the_record_size_reading_matches_the_tables` (beta: every relation's
`row_count` equals a direct `count(*)` through the container, both read inside
one `REPEATABLE READ` transaction so the two cannot drift).

**Done.** *(executor)*

### Run 5 — the Reality Ledger

**Code. Push and read CI.**

**Reads first**: ADR 0247; `bin/render-capacity-envelope.py` whole (the
renderer to copy: `--write|--check`, exit 5 on a stale page, the *"Generated
by … Do not edit by hand"* header); `tests/contract/test_capacity_envelope.py:
140-170`; `bin/session-01-check.sh:205-230`; `src/agentic_postgres/
evidence_claims.py:356` (`CLAIMS`); `capacity.ENVELOPE`'s `subject` field;
`docs/README.md` (where a page is indexed); the specification's §50 table and
Appendix A (`c:\Users\gmpar\Downloads\stage-5-consolidated-spec.md`
`:1725-1762`, `:2632-2662` — read on the workstation; do not commit the
specification).

**Build.**

- `schemas/reality-ledger.schema.json` (draft 2020-12, the other schemas'
  style): a list of rows with ADR 0247's fields, `additionalProperties: false`,
  the status enum, `controls` an array of strings.
- `docs/reality-ledger.yaml`: one row per concept, **today's truth**. Rows and
  statuses (the executor writes the texts; `customer_text` is what a customer
  would read, `today` what the appliance does for its operator now):
  `accounts`, `organizations`, `api_keys`, `management_api`, `cli_remote`,
  `console`, `projects_self_service`, `region`, `compute_profiles`, `sleep`,
  `wake_on_connect`, `pooled_endpoint`, `direct_endpoint`, `branches`,
  `branch_promotion`, `restore_to_branch`, `in_place_restore`,
  `query_insights`, `monitoring`, `usage`, `plan_free`, `plan_premium`,
  `notifications`, `email`, `passkeys`, `support_access`, `sql_editor`,
  `export`, `project_deletion` — all **`planned`**, each with `target_session`
  from the Stage 5 plan's §3, except: `sql_editor`, `in_place_restore`,
  `branch_promotion` → `not_offered` (cut, Stage 5 plan D1962/D1963/D1969);
  `support_access` → `not_offered` with D1971's sentence as its
  `customer_text`; `autoscaling`, `high_availability`, `multi_region`, `sla`,
  `billing` → `not_offered`; `egress_metering` → `not_metered`. The substrate
  rows that ARE true today for the operator — `postgresql` (18.4),
  `project_isolation`, `backups_and_pitr`, `agents`, `workflows`, `connectors`,
  `audit` — carry `status: planned` (no customer can reach them) and a
  `today_evidence` claim that is `passed` in `evidence/session-35.json` (grep
  `CLAIMS` for a claim whose requirements are DEP-ISO-*, REC-PITR-*, AGT-*, WF-*,
  CONN-* and pick one each; name it in the Done).
- `src/agentic_postgres/reality_ledger.py`: `load()`, `validate()` (the schema
  through the `jsonschema` the tree already pins — grep `import jsonschema`),
  `FORBIDDEN_WORDS` (the specification §59 list, lower-cased:
  `production-ready`, `enterprise-grade`, `highly available`, `fault tolerant`,
  `multi-region`, `serverless`, `autoscaling`, `zero downtime`), `render()`.
- `bin/render-reality-ledger.py --write|--check` (exit 5 when stale) writing
  `docs/reality-ledger.md`; `--check` added to `bin/session-01-check.sh` step 6
  beside the other three; the page indexed once in `docs/README.md`.
- `tests/contract/test_reality_ledger.py` (new; `pytestmark`) with §2's names.
  `test_available_and_beta_rows_name_evidence_that_resolves` and the
  `today_evidence` check read the NEWEST `evidence/session-*.json` by session
  number. `test_the_sets_the_guard_will_read_are_empty_today` asserts no
  `src/agentic_postgres/operations.py` and no `services/console/` exist and
  says in its docstring that Sessions 37 and 42 replace it with the real guard
  (D2000). Battery: (M1) one `planned` row given a control → FAILED (control:
  the forbidden-word test passes); (M2) one row's `customer_text` gains
  *"autoscaling"* → FAILED; (M3) one `today_evidence` renamed to a claim that
  does not exist → FAILED.
- Register `bin/render-reality-ledger.py` in `PYTHON_COMMANDS`.

Targeted: `test_reality_ledger`, `test_cli_contract`,
`test_documentation_index`, `test_session12_documented_path`, then
`bin/session-01-check.sh` ALONE on the clean tree after the commit (generated
artefacts, CLAUDE.md §5's table).

**Done.** *(executor)*

### Run 6 — the secret-age reading (conditional on Sheet E0)

**If E0 found no per-secret update time in the provider's response**: write
D-row(s) saying so with the key names E0 printed, mark this run **Done.** with
*"not built: no age to read"*, do not write ADR 0250, and §2's two `OPS-ROTATE`
rows are not registered (the counts in §2 take their lower values). **Stop
here.**

**If it did**: ADR 0250 (*a secret's age is the provider's update time, read,
never acted on*); `schemas/secret-contract.schema.json` gains optional
`max_age_days` (integer 1–3650) per secret; `secrets.required.yaml` declares it
for `postgrest_authenticator_password`, `docs_basic_auth_password`,
`app_runtime_password` (90) and nothing else yet; `infisical_client` gains a
read that returns the update time and NEVER the value (a separate function; the
value never enters its return); `src/agentic_postgres/secret_age.py` (the
three outcomes); `bin/doctor.py --reading secrets` (beside `capacity` and
`usage`, `:1215`); `tests/contract/test_secret_age.py` (a fake provider; the
value absent from every return and every printed line — plant one and grep);
the live proof in `test_session36_operations.py`. Battery: (M1) the reader
returns the value too → the planted-value test FAILED.

**Done.** *(executor)*

### Run 7 — the trip's instruments, written and rehearsed offline

**Commits nothing but its `**Done.**`** (no CI). Everything here is a script in
WSL `~/s36/` (backed up to the scratchpad's `s36/`) and, where it runs on the
host, copied to `/home/op` by the agent and read back.

**Reads first**: `~/s35r10/NOTES.md` and `~/s35r10/s35r10-derive.py` (**the
model**: it derives each trip script from the plan's sheet text and the
deployed documents so nothing is typed twice); Session 35's Sheets F1–F8
(`docs/plans/session-35-implementation-plan.md:2399-2552`) and what went wrong
on them (D1941–D1944); Session 29's reboot (D1500) and Session 30's Run 7 Done
(the redeploy-before recipe, D1570); `bin/provision-host.sh` and
`src/agentic_postgres/host_config.py` for **which copy of `host.yaml` admission
and `doctor capacity` read** (the checkout's, or `/etc/agentic-postgres/
host.yaml` that `provision-host.sh --apply` installs) — D1992's sheet line
depends on it; this plan's appendix.

**Write**, each with a `--help` and its own transcript (`tee`), each deriving
container, database and volume names from a deployed document and never typing
one (D1184):

1. `s36-counts.py` (root) — per project, through `docker exec … psql -U
   postgres`: `app.notes`, the release ledger, the project ledger,
   `app_private.agents`, `workflow_run`, `connector_delivery`, and
   `pg_postmaster_start_time()`; `--before` writes `/root/s36-counts-<key>.json`
   (and a 0644 copy in `/home/op/`), `--after` compares and prints `EQUAL` or the
   differing relation. Rehearse against a throwaway `apg dev` cluster on the
   workstation (no root there: a `--document` flag points it at the dev
   render), the control a row inserted between `--before` and `--after`
   producing the differing relation's name.
2. `s36-host-read.sh` — `free -m`, `nproc`, `lscpu | grep -E 'Model name|^CPU\(s\)'`,
   `df -BG /var/lib/docker /`, `ip -4 addr show <public interface>` (the
   interface from `host.yaml`'s `host.public_interface`), `uptime -s`.
3. `s36-hostyaml.py` (op) — edits `/home/op/agentic-postgres/host.yaml`'s
   `capacity.memory_mb` to the read `free -m` total and NOTHING else (D1992), a
   backup first (`host.yaml.pre-s36`), the diff printed; refuses if
   `reserve_memory_mb`, `disk_gb` or `reserve_disk_gb` would change.
4. `s36-units.sh` (op) — polls `systemctl is-active
   agentic-postgres-project@alpha-dev agentic-postgres-project@beta-dev
   agentic-postgres-edge` every 10 s until all three read `active` three times
   in a row; prints the elapsed seconds from its start; gives up at 15 minutes.
5. `s36-d1581.py` (root) — before and after a deploy: every project container's
   id, image id, `Created` and `StartedAt`, and the active secret generation id
   (`active-secret-generation.json`), as one JSON line each; a `--diff` mode.
   **This answers D1581/D1713 on R3** (stage plan D1976).
6. The probe pair `s36-probe-start.sh` / `s36-probe-stop.sh`, derived from
   Session 35's (the probe stops itself after 4 hours: start it when the sheet is
   handed, D1943) — **it runs on the host as `op`, through the edge**.
7. `s36-capture.py` and `s36-shape.py` (root) — after reading
   `docs/api-operations.md` §*Rotating a credential* step 1: the first copies
   the ACTIVE generation's value of one secret to `/root/s36-prev-<name>`
   (0600), the path derived from `active-secret-generation.json` and the
   generation's manifest; the second reads the NEW generation's value and prints
   only its length, its character class and whether it differs from the
   captured one. Neither prints a value. Rehearse both against a throwaway
   generation directory the script builds in `/tmp`.
8. `s36-redeploy-before.py` (root) — Session 30's redeploy-before recipe as
   D1570 corrected it: a sentinel note on alpha and
   `/root/s36-redeploy-before.json` with `sentinel_title` and the CURRENT
   `generation_id`.
9. `s36-sweep.sh` — the sweep line (Sheet S1), derived from Session 35's F6 by
   diff: the gate's name, `--after-reboot`, the four `--rotated-*` flags,
   `--redeploy-before-file /root/s36-redeploy-before.json`, `--kit-dir
   /home/op/kit-2026-09-11`, and every other declaration F6 named; **NOT**
   `--replacement-host-outputs` / `--replacement-bootstrap-state` (D1998).
   Detached: `setsid nohup bash /home/op/g36-host.sh > /dev/null 2>&1 <
   /dev/null &`, the exit code written to a file by the script.
10. `s36-external.sh` (workstation) — Session 35's external line unchanged
    (`--public-ipv4 62.238.99.122`, `--ssh-destination op@62.238.99.122`), an
    ephemeral `ssh-agent` (D466).

**Done.** *(executor: each script's rehearsal and its control's result; which
`host.yaml` copy admission reads.)*

### Run 8 — the bump, the registry, the gate, the documents

**Code. Push and read CI.** The shape of Session 35's Run 9 (`f7fb96d`, 21
files).

**Build.**

- `src/agentic_postgres/__init__.py`: a `#:` paragraph for Session 36 above the
  constant (the shape of `:769-833`: what the release adds, the pricing,
  **`VERSION` moves to `1.14.0`**), `CURRENT_SESSION = 36`. `VERSION` → `1.14.0`.
- `tests/acceptance-registry.yaml`: the block `# Session 36 (ADR 0246-0250)`
  with §2's entries and the node ids COLLECTED (`pytest --collect-only -q` over
  the new modules); `LEDGER` in the ID regex and the family sentence.
- `evidence_claims.py`: `CLAIMS` and `OFFLINE_CLAIMS` per §2;
  `CLAIM_INTRODUCED_IN` rows at 36.
- **`bin/session-36-check.sh`, derived from 35's by diff** (D1482): `readonly
  SESSION=36`; the header and the usage block REWRITTEN whole (D1488) — what
  1.14.0 adds, the four (or five) offline claims, the two (or three) host
  claims, that this gate's sweep is the first to declare all four `--rotated-*`
  files (D1995) and that `--replacement-*` stay undeclared because the host was
  rescaled, not replaced (D1991); **no flag added or removed** (the sorted
  flag-token sets equal — prove it in the commit message as Session 35 did).
  `tests/contract/test_session_thirty_six_gate_modes.py` derived from 35's
  (`SESSION = 36`, `SESSION_PREVIOUS`, the new claims asserted in the offline
  set). `SHELL_COMMANDS` gains the gate; `chmod 755`.
- **Documents**: `docs/upgrade-guide.md` a `1.14.0` row (minor by declaration;
  two migrations; a new command); `README.md:7` (*Session 36 implemented*) and
  the `template_version` phrase; every `--session 35` / `--through-session 35`
  literal a reader executes, moved and counted per file (D678/D1484; the
  `test_documentation_index.py:435` guard); `docs/operator-guide.md` §9/§13
  corrected per D1996, and §16 (*the node as a finite resource*) gains
  **a paragraph on rescaling a Hetzner server** — CPU and RAM only, the clean
  shutdown, `memory_mb` re-declared with the reserve unchanged (D1992, D1993);
  `docs/product-contract.md`'s requirement block regenerated
  (`bin/render-acceptance-matrix.py --write`; read `--help`).
- `bin/render-acceptance-matrix.py`'s `AREAS` (`:42-53`) lists ten families and
  not `NODE`, `GOV`, `CONN` and the rest — **do not widen it here**; a row
  records it (the matrix is generated from what it lists, and widening it is a
  change of the matrix's meaning, not of this session).

**Before the push**: `ruff format && ruff check`; `bin/render-acceptance-
matrix.py --write`, `bin/render-config.py --bounds-doc --write`,
`bin/render-reality-ledger.py --write`, `python bin/render-mcp-catalog.py
--write`, `python bin/render-evaluation-report.py --write`; targeted:
`test_acceptance_registry`, `test_evidence_claims`, `test_cli_contract`,
`test_session_thirty_six_gate_modes`, `test_documentation_index`,
`test_session12_documented_path`, `test_reality_ledger`; then commit, then
**`bin/session-36-check.sh --mode offline`** on the clean tree (it writes
`evidence/session-36-offline.json` — keep it; it is the offline half the merge
reads if no code moves before Run 10) and `bin/session-01-check.sh`, both
ONCE, both run detached with their exit codes written to files (CLAUDE.md §1).
Push; read CI by full SHA.

**Done.** *(executor: the counts read from the tuples, the gate's flag diff,
the offline half's numbers, CI.)*

### Run 9 — sitting 1 (day 1): the rescale, then the release

**Before the day** (agent, offline): CI green on Run 8's commit by full SHA;
`pytest --setup-plan` for `tests/deployment/test_session36_operations.py` and
`test_session4_convergence.py` with the variables SET (D671, D676), outputs
kept; WSL's outbound TCP probed (a `/dev/tcp` connect timed inside a script —
CLAUDE.md §1); Run 7's scripts read once more against the sheet text; **the
previous trips' *"if something goes wrong"* sections read** (operator guide
§12, Session 35's Run 10 and D1941–D1944, Session 29's reboot — D977).
**Announced: both projects are down from H1's `poweroff` to H3's doctors.**

In order, one sheet per outcome, each read before the next is issued (D1510):

1. *(op)* the 1.14.0 commit transported: `git bundle create /tmp/apg-<sha12>
   .bundle main`, `scp`, `git bundle verify`, `git fetch <bundle> main`, **`git
   rev-parse FETCH_HEAD` equal to the pushed SHA**, `git checkout -B main
   FETCH_HEAD`, `cat VERSION` → `1.14.0`, porcelain 0; `uv pip sync` only if
   `git diff --stat f7fb96d..HEAD -- requirements-dev.txt requirements-dev.in
   .python-version` is non-empty (D1491); the FOUR renders as `op` (D1507):
   `project.alpha.yaml`, `project.beta.yaml`, `project.example.yaml`,
   `project.second.example.yaml`. **The checkout moving does not touch what
   runs**: the deployed release lives under `/opt/agentic-postgres/releases/
   f7fb96d…`.
2. *(H1, before the rescale)* a `backup --type incr` per project; `s36-counts.py
   --before` per project; `s36-host-read.sh` (the OLD size, for the envelope);
   then `sudo systemctl poweroff`. **The window starts at this line** — the
   agent records the time it was issued.
3. *(H2, the operator at the Hetzner Console)* the server is off; **Rescale**,
   **"CPU and RAM only"**, an x86 plan of the size the operator chose (write it
   on the sheet); **before power-on, the server's Primary IPv4 read on the
   console and written on the sheet** — it must be `62.238.99.122`; power on.
4. *(op)* `ssh` as `op` until it answers; `s36-units.sh`; `s36-host-read.sh`
   (the NEW size: `free -m`, `nproc`, the CPU model); `ip -4 addr` shows
   `62.238.99.122`.
5. *(H3)* `sudo bin/doctor.sh --project alpha-dev` and `--project beta-dev` →
   12 ok each; `sudo python3 /home/op/s36-counts.py --after` per project →
   `EQUAL`. **The window ends at the second doctor's ok** — recorded per project.
6. *(op, then H4)* `s36-hostyaml.py` (the new `memory_mb`, nothing else, D1992);
   the operator installs it where Run 7 found admission reads it; `sudo
   bin/doctor.sh capacity --host host.yaml` — the declared memory, the reserve
   unchanged, committed 608 MiB, safe available `memory_mb − 2214 − 608`.
7. *(R1)* `sudo bin/upgrade.sh check --project <key>` and `sudo bin/upgrade.sh
   plan --project <key> --candidate .generated/<key>/outputs.json --json` (with
   `--also migration_added` — read `--help`), both projects: expect `bump
   minor`, verdict `ok`.
8. *(R2a, R2b)* the probe started (`s36-probe-start.sh`); `sudo ./deploy.sh
   --host host.yaml --project project.<name>.yaml --capabilities
   capabilities.yaml --through-session 36` under `script`; alpha, then beta —
   **R2b's optional first line is D2005's manifest edit, the operator's yes or
   no**. Expect ledgers 39 / 39+4. The probe stopped; the windows per class read.
9. *(R3)* `s36-redeploy-before.py` (for `deployment_convergence`), then
   `s36-d1581.py --before`, the SAME deploy of alpha again with nothing
   changed, `s36-d1581.py --after --diff`: **which containers are new, which
   restarted, whether the generation moved** (D1581/D1713 answered, D1976).
10. *(R4, beta)* `sudo bin/record.sh --project beta-dev size`; the operator writes
    the horizons on the sheet (proposed: `2026-10-01T00:00:00Z` for `runs` and
    `deliveries`, the same for `agents` after runs); `prune --what runs …`,
    `--what deliveries …`, `--what agents …` each with `--confirm beta-dev`; `size`
    after. Expect `workflow_approval (pending on an ended run)` = 0 already (the
    worker withdrew them after R2b).
11. *(V1)* the verification, `-k` (writes no evidence): `sudo bin/session-36-
    check.sh --mode host … -k "session4_transports or session36"`.

**Done.** *(executor: the old and new sizes and CPU models; the Primary IP on
the console; the rescale's window per project; the counts; the capacity
reading; the upgrade plans; the deploy windows per class from the probe;
D1581's answer; the prune counts; V1's result; the rows.)*

### Run 10 — sitting 2 (day 2): the three rotations, the reboot, the one sweep, the tag

**The rotations are alpha's, one sheet each** (D1995): **X1** the authenticator
password (`postgrest_authenticator_password`, consumer `postgrest`), **X2** the
documentation password (`docs_basic_auth_password`, the root plane — the
middleware is written inline since ADR 0086, so no edge restart), **X3** the
application credential (`app_runtime_password`, consumers `pgbouncer` and the
client fixtures). **What they move, said at the top of every sheet**: with the
retired signing JWK Session 30 kept at `/home/op/s30-retired-alpha-dev-jwk.json`,
the four files the nine node ids need; a claim moves only if every one of its
node ids passes in S1.

Each sheet, from `docs/api-operations.md` §*Rotating a credential* (read it
whole first — its traps D252–D254 are why the steps are in this order):

1. the current value captured to `/root/s36-prev-<name>` (0600 root) by
   `s36-capture.py`;
2. **the operator replaces the value at Infisical by hand** (a new random value
   of the same shape — the contract's `format` for the secret) and confirms it
   saved;
3. `sudo bin/project-runtime.sh --host host.yaml --project-key alpha-dev
   --through-session 36 down` (D253 — still live);
4. `sudo bin/materialize-secrets.sh --project project.alpha.yaml --requirements
   secrets.required.yaml --session 36`, then `s36-shape.py` (the new value's
   length and class, differing from the captured one; never printed — Session
   30 Run 8's lesson);
5. `sudo ./deploy.sh … --project project.alpha.yaml … --through-session 36` under
   `script`;
6. `sudo bin/doctor.sh --project alpha-dev` → 12 ok.

Then **B1**: `sudo systemctl reboot`; the agent runs `s36-units.sh`.

Then **S1, the one sweep** (`s36-sweep.sh`, detached; ~55 min): every
declaration `--help` lists except the two `--replacement-*` (D1998), with
**`--after-reboot`**, **`--rotated-from-file /root/s36-prev-app_runtime_password`**,
**`--rotated-authenticator-from-file /root/s36-prev-postgrest_authenticator_password`**,
**`--rotated-docs-from-file /root/s36-prev-docs_basic_auth_password`**,
**`--rotated-jwt-from-file /home/op/s30-retired-alpha-dev-jwk.json`**,
`--kit-dir /home/op/kit-2026-09-11`, `--redeploy-before-file
/root/s36-redeploy-before.json`, and the rest as Session 35's F6 named them;
`--dx-record-file` keeps the Session 25 record (no person walked, D1935). If a
proof FAILS: read it; an instrument repaired in the window and re-run with
`-k`; the sweep once more only if a claim's reading changed; a product defect
**recorded and left**.

Then the external half from WSL (`s36-external.sh`), the host half copied to
WSL, and the merge: `python bin/write-session-evidence.py --session 36
--host-input evidence/session-36-host.json --external-input evidence/session-
36-external.json --offline-input evidence/session-36-offline.json --output
evidence/session-36.json`. **If any code commit landed after Run 8**, re-run
the offline half at the deployed commit first (Session 30 Run 7's lesson: the
merge reports the commit difference rather than folding it).

**The tag** (D1425): `bin/apg.sh release-reading --ref <deployed sha>` quoted;
`git tag -a 1.14.0 <deployed sha>`; `git push origin 1.14.0`. A post kit:
`sudo bin/dr-kit.sh export --host host.yaml --capabilities capabilities.yaml
--output /home/op/kit-<date>-post --project project.alpha.yaml --project
project.beta.yaml`, copied to WSL `~/dr-kits/`.

**Done.** *(executor: the three rotations' timings and doctor readings; the
reboot's downtime; the claim table; the halves; the tag; the kit.)*

### Run 11 — the close

**Code (the envelope rows) — `bin/session-01-check.sh` once and CI.**

- **`capacity.ENVELOPE`**: Session 36 rows, read from the trip's own files by a
  script that pastes them (`~/s36/s36-envelope.py`, Session 35's
  `s35-r11-envelope.py` the model — never retyped), each naming the CPU model
  and size it ran on (D1994): **the rescale's window** per project (H1's
  `poweroff` → H3's doctor ok), **the rescaled host's capacity** (`free -m`,
  `nproc`, the CPU model, the new claimable), **the deploy windows per class on
  the rescaled host** (R2's probe), **the reboot's window** (B1), and — as a
  CONFIGURATION row — D1581's answer. `bin/render-capacity-envelope.py --write`.
- **The Reality Ledger**: no row changes status this session (nothing a customer
  reaches was built). `bin/render-reality-ledger.py --write`.
- `docs/scope-closure.md` **§29** — what Session 36 closed, what it left, what
  Session 37 inherits (the shape of §28).
- `docs/plans/stage-5-plan.md`: the Status block re-read and rewritten (Session
  36 done, the rescaled size, next free numbers); its D1948 row already carries the supersession, written 2026-10-03 with this plan's revision
- `docs/operator-guide.md` §13: *"The kernel restart and `--after-reboot`"* line
  updated with B1.
- CLAUDE.md §2 rewritten for Session 37's planner (copy it to the scratchpad
  first): the HOST block with the new size; the gate's script set `s36-*`; the
  envelope's new rows.
- The plan's header `Status:` set to COMPLETE with the rows each run added.

**Done.** *(executor)*

---

## 7. Evidence and claims

**Expected at the merge** (Run 10): **204 claims** (206 with Run 6). **Passed:
everything that passed at Session 35, plus the six (eight) new ones, plus — for
the first time since Session 29 — `port_allocation` (declared after B1), and
— for the first time on this deployment — the rotation trio**
(`api_authorization`, `bootstrap_identity`, `credential_rotation_planes`: all
nine node ids, D1995). **`failed` 1: `documented_path`**, by decision (D1935;
the person's walk is Session 42's). **`not_run` 1: `replacement_host_restore`**,
by D1028's decision, unchanged (D1991). These are predictions: each of the four
claims expected to move is moved only by evidence the sweep actually produces,
and any that does not is reported with its reason. Exit 5 for `documented_path`
and `replacement_host_restore` and no other reason.

**The three modes.** Offline: `bin/session-36-check.sh --mode offline` at the
deployed commit (64 or 65 claims). Host: S1. External: from WSL, unchanged
address. Two live halves naming different commits do not merge (Session 29's
rule) — deploy fully, THEN sweep.

---

## 8. Security invariants this session touches

| Invariant | How this session keeps it |
|---|---|
| **An unauditable write does not happen** / the audit is the record | The prunes delete ONLY what an operator names with a horizon; the audit's own prune is unchanged; nothing schedules a prune (`test_nothing_schedules_a_prune`) |
| **A function granted to nobody is reached only by the owner or a superuser at a TTY** | Four of 0039's five functions are granted to nobody; `record.sh` requires root and `--confirm` |
| **The worker holds nothing the agent does not** (ADR 0217's first commitment, carried by ADR 0246) | The worker gains one function that moves `pending` approvals of ENDED runs to `withdrawn` — a state no agent can act on and no token is minted from (`workflow_approval_for_token` requires `approved` on a `running` run) |
| **No URL, key, token or caller value in a log line** | The handler prints lines whose fields are fixed by the code that builds them; `test_a_request_prints_one_line_with_the_template_and_no_caller_value` and the live proof plant and grep |
| **One service cannot read another's credential** | The rotations re-materialize per consumer; the captured old values are root-only 0600 files read only by the sweep; no value is printed (`s36-shape.py`) |
| **A deploy over a broken archiver fails** | Unchanged; the rescale stops nothing but the machine, and step 6c runs on every R deploy |
| **There is no public Postgres endpoint** | Still true: ADR 0246 permits Session 39 to measure one and changes nothing at runtime; `publication()` raises; zero `ports:` keys |
| **A report may not substitute an answer for a failure to determine one** (ADR 0195) | `record.sh size` reports *could not be read* and exits 6; the secret-age reading (if built) reports `unknown`; the counts print the differing relation, never `EQUAL` by default |

---

## 9. Stop conditions

Stop and ask the operator, without improvising, when:

- the incremental backup on H1 fails (nothing is shut down);
- the Hetzner Console offers no x86 plan of the chosen size with **"CPU and RAM
  only"**, or the Primary IPv4 on the console is not `62.238.99.122` before
  power-on;
- the units do not reach `active` within 15 minutes of power-on, or a count
  differs after the rescale (`s36-counts.py` not `EQUAL`);
- a migration would need to replace a 0035 function, or a prune would need to
  touch `users`, `workflow_definition`, `connector` or `workflow_worker`;
- `upgrade plan` prices 1.14.0 at `major`, or for a reason this plan did not name;
- a rotation's capture file would hold the NEW value (the proof would refuse it;
  re-capture is impossible once the provider moved — the sheet's order is the
  guard);
- the sweep would run without `--after-reboot` after B1, or after a code commit
  past the deployed one;
- a currently-passing test would be weakened to make a new one pass;
- `--render-only` stops working with no host and no root.

---

## 10. Open items this session carries and creates

**Carried, untouched, each still true:** D1547 (`delete_note`, deferred with its
cost, D1990); D1798 (no redelivery); D1869, D1871, D1722/D1806, D1784, D1792,
ADR 0241's bound; D1045; D1375; D976; D688; D771; D340; D466; D540; D942; D1203;
D1205; D1211; the 24 unclaimed requirements; `process-max` 1 (D593);
**`replacement_host_restore`, `not_run` by D1028** — a rescale is not a
replacement, and the first end-to-end replacement waits for a session that
needs one.

**Created, and named so Session 37 does not inherit them silently:**

- **Beta's three rotations** (D1995) — the first entries a schedule must carry;
  if Run 6 built the age reading, it reports them `overdue` only after their
  declared age.
- **The doctor does not report the record** (D1985) — `record.sh size` does;
  Session 42's `apg control status` decides whether an operator's view needs it.
- **Humans are never pruned** (D1986) — 35 probe humans on beta; an identity
  question for Session 37's accounts.
- **The hosted threats are a list** (D1999) — each moves into the table with its
  requirement in Sessions 37–42.
- **The Reality Ledger's control and operation-type guards** (D2000) — 37 and 42.
- **The reserve is the old host's** (D1992) — Session 38 re-derives it with the
  control project, ClickStack and the profiles.
- **The disk is still 38 GB** (D1991: CPU and RAM only) — Session 40's branches
  and Session 41's ClickStack retention are the two readers that may need more,
  and a disk rescale is one-way; each of those sessions measures its need first.
- **`render-acceptance-matrix.py`'s `AREAS` lists ten families** of twenty-six —
  recorded, not widened (Run 8).

---

## Appendix — what to consult, how a run is executed here, and the sheets

**Consult, in this order:** CLAUDE.md §1 (the shell traps — every one of them
has cost a run); this plan's §0, §1 and the run's own text; the reads its run
names. **The tree wins.**

**How a run is executed here**: CLAUDE.md §5. Every `sudo` line is the
operator's, on a sheet, under `script -q -e -c '…' /home/op/s36-<sheet>.txt`
when it execs into a container or deploys (D972, D1501), never piped or
redirected; `sudo -v` in the foreground first (D1376). Every `op` line is the
agent's over SSH. Remote loops go in a script file run with `ssh host 'bash -s'
< script`, which exports `PATH="$HOME/.local/bin:$PATH"`.

**The sheets.** One outcome each; the next is issued only after the previous is
read.

### Sheet E0 — readings before anything is built (Run 1; `sudo`; reads only)

```
sudo -v
sudo bash /home/op/s36-e0.sh      # tees /home/op/s36-e0.txt; changes nothing
```

### Sheet H1 — before the rescale (Run 9, day 1) — **the outage begins at the last line**

```
sudo -v
sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json backup --type incr
sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/beta-dev/outputs.json  backup --type incr
sudo python3 /home/op/s36-counts.py --before --project alpha-dev
sudo python3 /home/op/s36-counts.py --before --project beta-dev
sudo systemctl poweroff
```

### Sheet H2 — the rescale (Run 9, day 1; the operator at the Hetzner Console)

1. The server shows **off**.
2. **Rescale** → an x86 plan (shared or dedicated vCPU) of the size you chose:
   ________ (vCPU / RAM).
3. Tick **"CPU and RAM only"** — the disk stays 38 GB, and a downgrade stays possible.
4. Confirm; wait for the rescale to finish.
5. **Before powering on**: the server's Primary IPv4 on the console reads ________
   (must be `62.238.99.122`).
6. Power on. Tell the agent.

### Sheet H3 — the doctors and the counts (Run 9, day 1) — **the outage ends**

```
sudo bin/doctor.sh --project alpha-dev
sudo bin/doctor.sh --project beta-dev
sudo python3 /home/op/s36-counts.py --after --project alpha-dev
sudo python3 /home/op/s36-counts.py --after --project beta-dev
```

### Sheet H4 — the capacity re-declared (Run 9, day 1)

```
# the agent has edited /home/op/agentic-postgres/host.yaml (memory_mb only) and shown you the diff
<the install line Run 7 found — e.g. sudo install -o root -g root -m 0600 host.yaml /etc/agentic-postgres/host.yaml>
sudo bin/doctor.sh capacity --host host.yaml
```

### Sheet R1 — the release priced (Run 9, day 1)

```
sudo bin/upgrade.sh check --project alpha-dev
sudo bin/upgrade.sh plan --project alpha-dev --candidate .generated/alpha-dev/outputs.json --json
#   (beta the same; `--also migration_added` per `bin/upgrade.sh --help`)
```

### Sheets R2a / R2b — 1.14.0 deployed (Run 9, day 1)

```
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project project.alpha.yaml --capabilities capabilities.yaml --through-session 36' /home/op/s36-r2-alpha.txt
# R2b, optional first line (D2005): "raise beta's manifest to schema 8 with approvals_required: 1?"  yes / no: ____
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project project.beta.yaml --capabilities capabilities.yaml --through-session 36' /home/op/s36-r2-beta.txt
```

### Sheet R3 — the no-change redeploy and D1581 (Run 9, day 1)

```
sudo python3 /home/op/s36-redeploy-before.py        # writes /root/s36-redeploy-before.json
sudo python3 /home/op/s36-d1581.py --before --project alpha-dev
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project project.alpha.yaml --capabilities capabilities.yaml --through-session 36' /home/op/s36-r3-alpha.txt
sudo python3 /home/op/s36-d1581.py --after --diff --project alpha-dev
```

### Sheet R4 — beta's record pruned (Run 9, day 1)

```
sudo bin/record.sh --project beta-dev size
# horizons, written by you: runs ________  deliveries ________  agents ________
sudo bin/record.sh --project beta-dev prune --what runs       --before <runs horizon>       --confirm beta-dev
sudo bin/record.sh --project beta-dev prune --what deliveries --before <deliveries horizon> --confirm beta-dev
sudo bin/record.sh --project beta-dev prune --what agents     --before <agents horizon>     --confirm beta-dev
sudo bin/record.sh --project beta-dev size
```

### Sheet V1 — the day verified, writing nothing (Run 9, day 1)

```
sudo bin/session-36-check.sh --mode host <the declarations s36-sweep.sh names, without --after-reboot and the --rotated-* four> -k "session4_transports or session36"
```

### Sheets X1 / X2 / X3 — one rotation each (Run 10, day 2; alpha)

**At the top of each: this rotation moves no claim by itself; the trio moves
only if all nine node ids pass in S1 (D1469, D1995).** With `<name>` =
`postgrest_authenticator_password` (X1), `docs_basic_auth_password` (X2),
`app_runtime_password` (X3):

```
sudo python3 /home/op/s36-capture.py --project alpha-dev --secret <name>   # writes /root/s36-prev-<name>, 0600
#   YOU: replace <name> at Infisical by hand; confirm it saved
sudo bin/project-runtime.sh --host host.yaml --project-key alpha-dev --through-session 36 down
sudo bin/materialize-secrets.sh --project project.alpha.yaml --requirements secrets.required.yaml --session 36
sudo python3 /home/op/s36-shape.py --project alpha-dev --secret <name>     # the shape check; prints no value
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project project.alpha.yaml --capabilities capabilities.yaml --through-session 36' /home/op/s36-x-<name>.txt
sudo bin/doctor.sh --project alpha-dev
```

### Sheet B1 — the reboot (Run 10, day 2)

```
sudo systemctl reboot
```

### Sheet S1 — the one sweep (Run 10, day 2)

```
sudo -v
sudo setsid nohup bash /home/op/g36-host.sh > /dev/null 2>&1 < /dev/null &
```
