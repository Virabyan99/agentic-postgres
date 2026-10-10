# Session 39 — Public TLS endpoints and customer roles

**Status: PLANNED 2026-10-10 at `f47cee4`.** Not started. Rows **D2325–D2355** at
planning; rows the runs add start at **D2356**. ADRs **0268–0270** are this
session's. **NEXT FREE after this plan: D2356, ADR 0271.**

The fourth session of Stage 5 (`docs/plans/stage-5-plan.md` §3, §5 *Session 39*).
Twelve runs and **two sittings on two days**: the firewall, the edge's one
announced recreation and the release on the three projects, with two customer
slots prepared — `slot2-prod` ready, `slot3-prod` held `prepared` (day 1); then,
from the workstation with no SSH, `slot2-prod` created, claimed, given its two
database credentials, connected through both public URLs, rotated, slept,
woken, resized, exported and deleted, a second creation refused for want of a
slot, then `slot3-prod` made ready, created, claimed and credentialed and **kept**
— the first live customer project with a public Postgres endpoint — then a
reboot, the one sweep, external, merge, tag (day 2).

**Brief:** `docs/plans/stage-5-plan.md` §5 *Session 39* whole (Builds / Already
true / Must not / Measures / Closes) and its rows **D1956** (wake-on-connect's
half), **D1958** (the gateway, five measurements), **D1959** (the customer
roles), **D1960** (snippets), **D1974** (a customer's credential rotates through
`credential.rotate`), **D1975** (router creation moves no neighbour), **D1978**
(threat rows first), **D1979** (the Ledger); `docs/scope-closure.md` **§31**
(what Session 38 hands 39, in order); Session 38's plan §10 *"Created by the trip
and the close"* (`docs/plans/session-38-implementation-plan.md:1879-1904`) and
its rows **D2305–D2324**; ADR **0246** item 2 (`docs/decisions/0246-stage-5s-boundary-a-hosted-product-on-one-node.md:55-64`:
*"80, 443, and one Postgres port whose shape Session 39 measures and records in
its own ADR. Until that ADR, none."*); ADR **0044** (`:112-116`: *"Publish
through Traefik's TCP router with SNI … the direction any future public pooler
would have to take"*); ADR **0260** (`:63-65`); `docs/threat-model.md` hosted
items **#2** (`:192-196`), **#3** (`:197-201`), **#7** (`:216-222`), **#10**
(`:233-246`); `docs/reality-ledger.yaml` rows `management_api` `:109-134`,
the six managed-project rows `:180-337`, `pooled_endpoint` `:359-374`,
`direct_endpoint` `:376-391`, `wake_on_connect` `:393-406`, `postgresql`
`:736-752`; and **the operator's four answers of 2026-10-10** (§1 D2335, D2340,
D2342).

**Shape:** twelve runs. **Run 1** is documentation — six rigs, one host reading
sheet (E0, reads only), the threat list made specific, three ADRs — and reads
**no** CI verdict. **Runs 2–7** change code: each pushes and reads that commit's
own CI verdict by full SHA (`gh api
"repos/Virabyan99/agentic-postgres/actions/runs?head_sha=<40 chars>" --jq
'.workflow_runs[] | [.name, .status, .conclusion] | @tsv'` from Git Bash, judged
on HTTP status, three buckets — success / failure / not registered; an empty list
is not a verdict, D1057). **Run 8** writes the trip's instruments and rehearses
them offline, committing nothing but its `**Done.**`. **Run 9** is the bump.
**Runs 10–11** are the sittings. **Run 12** is the close (Ledger rows and envelope
rows are code: it gates once and reads CI).

**Product version at close:** `CURRENT_SESSION` **39**; `template_version`
**`1.17.0`** — predicted *minor* (project manifest schema 11 and outputs schema
22, each migratable; a new operation type and two new `/v1` routes; **no new
secret, no released migration**) and **read from `upgrade plan` on the host,
never chosen** (§1 D2331). The stage plan predicted *major* for two new required
secrets (`stage-5-plan.md:353-358`); this plan adds no secret (D2330), and the
class it would have priced cannot fire anyway (D2331). The released migration
count stays **39**: the customer roles and their grants are bootstrap-plane
statements (ALTER ROLE is bootstrap work, D102), and the control plane's new
column is the control project's OWN fifth migration. **One new published host
port (5432, the edge's)**, **two new services per enabled project** (the
customer poolers), **one new operator command** (`bin/customer-credentials.sh`,
root), **one new customer command** (`bin/endpoint.sh`), **one new operation
type accepted** (`credential.rotate`). A `major` is §9's stop.

**Written for whoever picks this up cold, and it will be a different model than
the one that planned it.** Every path below was read from the tree on 2026-10-10
at `f47cee4` — four explore passes over `infra/edge/`, `infra/host/`,
`src/agentic_postgres/`, `bin/`, `services/`, `projects/control/`, `schemas/`,
`compose.yaml`, `tests/`, `docs/` and every plan, plus direct reads of
`src/agentic_postgres/slot.py:296-330`, `bin/db.sh:1-40`,
`bin/deploy-project.py:127-162` and `bin/provision-host.sh:1-60`, **and two rigs
run at planning** (§0, *Measured at planning*). Every path is cited `path:line`.
**Read CLAUDE.md §1 in the launch folder before the first command, then this
plan's §1, then the appendix.** If a step here and the tree disagree, **the tree
wins and the disagreement is a divergence row** (next free `D` after §1's table),
never a silent reconciliation. **When this plan names a line number, open the
file at that line and read the surrounding twenty lines before editing** — the
numbers were right on 2026-10-10 and `ruff format` moves them.

**The nine sentences the executor most needs, in case nothing else is read:**

1. **The gateway is the existing edge with one more entrypoint, and it works —
   measured at planning** (§0, D2325). Traefik 3.7.10 handles libpq's
   `SSLRequest` and `sslnegotiation=direct`, routes by SNI, and refuses a wrong
   SNI, no SNI and plaintext. **It needs a TLS option advertising ALPN
   `postgresql`**: without it libpq 18 fails with *"tlsv1 alert no application
   protocol"*. No product-owned TCP proxy is built.
2. **The public door is two customer-only PgBouncers, never the database and
   never the platform's pooler** (D2329). `customer-pool` (transaction mode,
   userlist = `customer_app` only) behind `pool.<domain>`; `customer-direct`
   (session mode, userlist = `customer_admin` only) behind `direct.<domain>`.
   Every platform role — the superuser included — is refused at both with one
   message (*"SASL authentication failed"*), so **a leaked platform credential
   stays useless off the host**. `postgres` and the platform `pgbouncer` keep
   their networks and their guards.
3. **No customer password ever exists on the host or in the control plane**
   (D2330). `bin/endpoint.sh credential` generates 32 random bytes on the
   workstation, writes them to a 0600 file, and sends only the SCRAM-SHA-256
   **verifier** in a `credential.rotate` operation. The reconciler sets it with
   `ALTER ROLE … PASSWORD :'verifier'` over stdin, regenerates the pooler's
   userlist from `pg_authid`, and SIGHUPs the pooler (no restart). Measured:
   PgBouncer 1.24.1 authenticates to Postgres from a verifier-only userlist
   (SCRAM pass-through).
4. **A customer's DDL lives in `public` and nowhere else** (D2332): `USAGE,
   CREATE ON SCHEMA public` for `customer_admin`, default privileges to
   `customer_app`, `USAGE` on `extensions`, **nothing** on `app`, `api`,
   `app_private`, no `CREATE` on the database (so no schema, no extension), no
   role attribute. Export gains `-n public` (D2333).
5. **Only a slot gets endpoints.** Manifest schema 11 `database.public_endpoints:
   {enabled: bool}`, default `false`; `slot.sh prepare` writes `true`; **alpha
   and beta stay off** (alpha's names are the live control); **the control
   project refuses it** (D2337).
6. **Hostnames derive from the project's domain**: `pool.<project.domain>` and
   `direct.<project.domain>`, one Let's Encrypt certificate per project by the
   edge's existing HTTP-01 resolver, **two more grey A records per slot by
   hand** (D2327, D2335 — the operator, 2026-10-10).
7. **Wake-on-connect is not built** (D2336): a stopped container's label router
   disappears, so a sleeping project's endpoint refuses (TLS closed). The Ledger
   row stays `planned`.
8. **Two slots, one alive at a time** (D2342 — the operator, 2026-10-10):
   `slot2-prod` runs the whole lifecycle and is deleted; `slot3-prod` is held
   `prepared` by **withholding its DNS** until `slot2-prod`'s `no_slot` refusal
   is recorded, then created and **kept** (Session 40 branches from it). **No OVH
   upgrade in 39**; it is owed before 41.
9. **Eight Ledger rows go to `trial` in the bump**: the six managed-project rows
   (evidence: Session 39's NEW `lifecycle_retrial_live`, because ADR 0261 admits
   only claims introduced in the current session — D2343) plus `pooled_endpoint`
   and `direct_endpoint`. `management_api` returns to `beta` at the close only
   if `control_plane_live` passes (D2322).

---

## 0. Where the session starts

```
HEAD            f47cee4 on main, local = origin ("Session 38 Run 13: the recorded
                line's commit and gate names restored"), tree clean. Deployed:
                efaef09 (1.16.0) on all three projects; tag 1.16.0 -> efaef09
                (tag object 01109aa). main carries Run 13's close past it
                (f8e00d1: Ledger rows planned, ACCEPTED_TYPES empty, envelope,
                RESIZE_WINDOW_SECONDS 71, four proof repairs).
VERSION         1.16.0. CURRENT_SESSION 38 (src/agentic_postgres/__init__.py:1028;
                Session 38's paragraph :961-1027; template_version() :1036-1042
                reads VERSION). Outputs schema 21 (deployed_output.py:40;
                READABLE_PREVIOUS_VERSION :846; output_migrations.CURRENT_VERSION
                :104, last step migrate_v20_to_v21 :1474-1500, chain end :339).
                Project manifest 1-10 (config.py:64; PROJECT_COMPUTE_FROM = 10
                :94; schemas/project.schema.json enum :18-29, v10 gate
                :1051-1070). host.yaml schema 2|3|4 (schemas/host.schema.json:26;
                v4 gates :11-12; region :59-70; slots :72-128). Capability
                manifest 4, lock 4, project lock 3, api-surface 2. 39 released
                migrations; the control set 4 (projects/control/migrations/
                templates/0001-0004); two committed proposals
                (projects/control/proposals/14699bf6…, d82e2831…).
REGISTRY        332 requirements (tests/acceptance-registry.yaml, 6,837 lines;
                Session 38's block :6398-6773 under `# Session 38 (ADR
                0256-0261)`, the migration's :6774-6837). ID regex
                tests/contract/test_acceptance_registry.py:118 (ends
                `...|LEDGER|CTL|KEY|OPN|LIFE)-...`); family comments :43-48,
                :50-117 (OPN/LIFE :114-117); target_session rule :204. 239 claims
                (evidence_claims.py CLAIMS :432-1284, Session 38's :753-781);
                91 declared offline (OFFLINE_CLAIMS :106-385, Session 38's
                :348-383). CLAIM_INTRODUCED_IN tests/contract/
                test_evidence_claims.py:953-1277 (Session 38's :1216-1239).
                267 ADRs. NEXT FREE: D2325, ADR 0268.
EVIDENCE        evidence/session-38.json (gitignored): 239 claims, 232 passed,
                7 failed -- documented_path (D1935), admission_live (D2292),
                lifecycle_operations_live (D2310), control_plane_live (D2317),
                reconciler_live (D2318), restore_isolation (D2319),
                lifecycle_project_door_live (D2321). The four proof defects were
                repaired at Run 13 and have run in no sweep.
HOST            15.204.231.45, OVH VPS US-East, apg-ovh-01: 4 vCPU, 7,745 MiB,
                no swap. ~op/agentic-postgres = efaef09. Read by apg-diag at
                planning (2026-10-10 ~18:30Z): 30 containers healthy (alpha-dev,
                beta-dev, control-prod x10 each), slot1-prod none; public
                listeners 22, 80, 443 only (`apg-diag listeners`). Reconciler
                installed, enabled. slot1-prod CONSUMED and revoked: NO SLOT IS
                FREE. Available with slot1 live 5,046 MiB; without 5,634 MiB
                (capacity.ENVELOPE, Session 38's rows :1260-1544).
DNS (planning)  control.agenticpostgresql.com -> 15.204.231.45 (grey).
                alpha-dev., beta-dev., slot1-prod. and x.pool.agenticpostgresql.com
                all resolve to Cloudflare addresses (188.114.96.x/97.x): the
                PROXIED wildcard `*.agenticpostgresql.com` (D2083) answers every
                name below it, nested names included -- a Postgres name with no
                explicit grey record reaches Cloudflare, not the host.
OPERATOR        2026-10-10: two slots, one alive at a time; no OVH upgrade in 39
                (owed before 41); HTTP-01 per project; the refusal proofs prove the
                decision (D2335, D2340, D2342).
```

**What exists, measured at `f47cee4`, and the session builds on:**

- **The edge.** `infra/edge/compose.yaml`: Traefik `image: ${TRAEFIK_IMAGE}`
  (`:118`), `mem_limit` 608m / pids 76 / cpus 1.0 (`:122-124`, ADR 0244), `ports:
  "80:8080", "443:8443"` (`:135-137`, the only product publication), mounts
  `${EDGE_STATE_DIR}/traefik.yaml` (`:139-142`), `/dynamic` (`:143-146`),
  `/acme` (`:151-153`); networks `[control, egress]` (`:154`).
  `infra/edge/traefik.yaml` (a template, the STAGING form, `:1-15`): entrypoints
  `ping :8082` (`:63-64`), `apgmetrics :8089` (`:69-70`), `web :8080` redirecting
  to https (`:71-93`), `websecure :8443` (`:94-100`); **no TCP entrypoint**;
  providers docker (`tcp://docker-socket-proxy:2375`, `exposedByDefault: false`,
  constraint `Label(\`apg.traefik.scope\`,\`managed\`)`, `:102-112`) and file
  (`/etc/traefik/dynamic`, watch, `:113-115`); one ACME resolver with
  **`httpChallenge.entryPoint: web`** (`:117-127`), no DNS-01 anywhere.
  `infra/edge/dynamic/baseline.yaml`: `tls.options.default` `minVersion:
  VersionTLS12`, `sniStrict: true` (`:16-23`). Pinned `traefik:v3.7@sha256:9c3b91d5…`
  (`versions.env:23`; measured `3.7.10`). **Rendered by**
  `bin/render-config.py:195` `edge_static` (substitutes the resolver, swaps
  staging→production `:225-233`, copies every `infra/edge/dynamic/*.yaml`
  `:245-252`) into `/var/lib/agentic-postgres/edge` (`bin/edge.sh:35`); **only
  `bin/edge.sh up|restart` re-renders and recreates it** (`do_up` `:198-238`,
  `restart` `:343-346`); `promote-acme` restarts. **A project deploy does not
  touch the edge and REFUSES a release whose static config the edge lacks**:
  `require_edge_serves_this_release` (`bin/deploy-project.py:770-799`, the check
  `:719-733` reads the `apgmetrics` entrypoint, D811) — the precedent this
  session follows. Production ACME on the host (D2064: a new hostname's first
  certificate is a production issuance, one attempt).
- **How routes reach the edge.** Labels only (ADR 0013), rendered by
  `src/agentic_postgres/runtime_override.py` (`build_override` `:567-702`; eight
  `traefik.http.*` label builders, `_rest_labels` `:1596-1660` the model, every
  one `tls.certresolver: ${ACME_RESOLVER_NAME:?required}`); every routed service
  carries `apg.traefik.scope: managed` and `traefik.docker.network:
  ${EDGE_NETWORK_NAME}` (`compose.yaml:96-102` and siblings). **Traefik is
  attached to each project's `edge` network and nothing else** (`bin/edge-network.sh`
  `attach` `:187-212`, `--alias apg-edge-proxy` `:51`/`:209`; callers
  `bin/project-runtime.sh:323,358,420` attach, `:370,392` detach; the unit
  `systemd/agentic-postgres-project@.service:35,41`). **The file provider holds
  basicAuth middlewares only and must never hold a router**: *"a file-provider
  service … resolves to whichever project the edge attached to first … would
  serve one tenant's requests from another tenant's container"*
  (`src/agentic_postgres/edge_credentials.py:165-173`; ADR 0085 `:62-80`).
- **The database and the platform pooler.** `postgres` (`compose.yaml:185-291`):
  `listen_addresses=*` (`:237-238`), **no `ssl`, no `hba_file`**, networks
  `internal` and `backup` (`:274-283`; *"`edge` would work and is refused"*
  `:281-282`). **`pg_hba` is the image's default** — `host all all 127.0.0.1/32
  trust` above `host all all all scram-sha-256` (`docs/database-security.md:138-151`).
  `pgbouncer` (`compose.yaml:563-700`): ini rendered INLINE by its entrypoint
  (`:602-641`); userlist = `APG_APP_RUNTIME_ROLE` + `APG_POOL_ADMIN_USER` only
  (`:608-613`); `auth_type = scram-sha-256`, `auth_file` (`:625-626`), `pool_mode`
  transaction (`rendering.py:961`), `max_prepared_statements > 0` asserted by the
  healthcheck (`:681-695`); `networks: [internal]` (`:699-700`); read_only, tmpfs
  `/etc/pgbouncer`, `user: "70:70"` (`:578-585`). Image
  `edoburu/pgbouncer:v1.24.1-p1` (`versions.env:17`; measured PgBouncer 1.24.1).
- **Everything that says "no public Postgres"** (each moves in ONE run, Run 4,
  under ADR 0268 — D2338): `runtime_override.publication()` raises
  (`:532-552`; callers `:686`, `:695`; `publications=` never passed,
  `bin/deploy-project.py:2236,2422`); `test_port_allocator.py`
  `test_no_publication_can_be_built_at_all` (`:364-377`),
  `test_the_override_carries_no_ports_entry_for_any_service` (`:380-395`);
  `test_deploy_command.py:370-373`; `compose.yaml` zero `ports:`;
  `test_compose_contract.py` `:233` (no project service publishes),
  **`:1190` `test_only_traefik_publishes_host_ports` `published == {"80","443"}`
  `:1194-1195`**, `:312` postgres networks `["internal","backup"]` and `"edge" not
  in` (`:325-330`); `test_pooler_contract.py:222,232`; `test_edge_config.py:82`
  entrypoints `== {"apgmetrics","ping","web","websecure"}` (`:100`) and ports
  `["80:8080","443:8443"]` (`:103-104`), `:181` (`:203-206`);
  `tests/deployment/test_session2_host.py:131,163,174`;
  `test_listeners.py` `BASELINE_PORTS = (22, 80, 443)` (`:46`);
  `tests/contract/test_host_infrastructure.py:151` (`ports == {80, 443}` v4 and
  v6); **the host firewall** `infra/host/docker-user-rules.v4:37-50` (NEW only to
  80 and 443, everything else DROPped; SEC-NET-001 `:43-46`) and `.v6`, copied to
  `/etc/agentic-postgres/` by `bin/provision-host.sh:633-634`, applied by
  `bin/docker-firewall.sh` (`:227-228`, `reconcile` `:1052`), ufw `:1005-1007`,
  the listener check `:488-501`; external `FORBIDDEN_PORTS = (5432, 6432, 8080,
  8443, 9000, 2375, 2376, 5433)` (`tests/external/test_session2_public_edge.py:48`),
  `test_every_reported_endpoint_is_loopback_or_absent` (`:115-165`),
  `test_session4_public_transports.py` `:119-142` (**5432 closed `:142`**);
  DBX-005 (`tests/acceptance-registry.yaml:700-705`); `config.py`
  `UNSUPPORTED_PUBLIC_POOL` (`:1443-1448`, `_validate_pooled_public`
  `:1451-1473`, CFG-010) — **the platform pooler's refusal, kept** (D2337).
- **The roles.** `naming.ROLE_SUFFIXES` (`src/agentic_postgres/naming.py:167-190`,
  fourteen, *"order reaches rendered output"* — append last `:181-189`);
  `database_role` `:934-942` (`apg_<key_sql>_<suffix>`, truncated with a
  fingerprint `:202-240`). `bootstrap_statements.build_statements` (`:78-412`):
  every role `NOLOGIN NOINHERIT` then `NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS` (`:106-115`); `REVOKE ALL ON DATABASE … FROM PUBLIC`
  (`:129-132`); **`GRANT CONNECT` to an exhaustive list** (`:156-161`, *"each new
  role has broken deploys before"* D291/D337 `:133-155`); schemas `extensions` and
  `app_private` (`:314-324`). `migrations/templates/0001-schemas-and-default-privileges.sql:34`
  `REVOKE CREATE ON SCHEMA public FROM PUBLIC`. `bin/postgres-bootstrap.py`:
  `apply_credential` (`:383-407`, `ALTER ROLE … LOGIN [CONNECTION LIMIT n]
  PASSWORD` over stdin), `apply_connection_limit` (`:410-425`), `connection_limits`
  (`:487-580`, application = max − reserved − api − auth − storage − backup −
  headroom 5 `:470`), `check_violations` (`:147-380`). The deploy runs it at step
  6 (`bin/deploy-project.py:2629-2639`).
- **ADR 0070's budget.** `config._validate_connection_budget` (`:1531-1597`) sums
  rest, auth, storage budgets, `database.pool_size`, backup 2, administration 5;
  the AST guard `BUDGET_CLAIMANTS` (`tests/contract/test_agent_plane_contract.py:295-304`,
  `_summands_of_the_budget_check` `:307-335`). Profiles
  (`services/auth-api/app/compute_profiles.py`): small `:40-52` (max_connections
  48, app pool 2, rest pool 6, storage pool 2), standard `:53-65` (56; 4/10/4),
  large `:66-78` (100; 6/16/6); `RESIZE_WINDOW_SECONDS = 71` (`:87`).
- **The control plane.** `services/auth-api/app/operations.py`: `OPERATION_TYPES`
  `:45-57` (**`credential.rotate` → `direct_endpoint`**), `EXECUTED_TYPES` the six
  `:60-69`, **`ACCEPTED_TYPES = frozenset()` `:75`**, `RESULT_MEMBERS` `:88-95`;
  `schemas/operation-arguments.schema.json` (create `:8-26`, resize `:27-40`, no
  `credential.rotate` branch). `control_routes.py` (`APIRouter(prefix="/v1")`
  `:64`; the project writes `:726-872`, `GET /v1/projects/{key}` `:879-888`);
  `control_roles.py` (`MATRIX` `:48-88`, `PROJECT_WRITES` `:95-103`,
  `OPERATION_OF_ROUTE` `:106-113`, `KEY_VOCABULARY` `:118-124`, `ROLE_SCOPES`
  `:127-139`, `KEY_SCOPES` `:141-159` — anything absent is human-session only).
  **`result_secret` is CHECKed to `project.export` only**
  (`projects/control/migrations/templates/0004-control-operations.sql:57-59`).
  `app.control_projects` (`0003:17-27`) has `domain` and no endpoint member.
- **The reconciler.** `bin/reconciler.py` `HANDLERS` (`:845-852`), the six
  handlers (`create` `:573-611` … `delete` `:825-841`), **`slot_project` refuses a
  non-slot project** (`:629-641`), `FINISH_SQL` carries `:'secret'` (`:154-157`);
  `src/agentic_postgres/reconciler_dispatch.py`: `STEPS` (`:75-98`),
  `ARGV_MEMBERS = {"profile","admin_username"}` (`:105`), `COMMANDS` (`:111-123`),
  `dump_argv` **`-n app -n api`** (`:398-407`). The unit
  `systemd/agentic-postgres-reconciler.service`: `After=… docker.service
  agentic-postgres-edge.service` (`:9`), **no ordering on the control project's
  unit** (D2168), `Restart=on-failure` `RestartSec=30` (`:29-30`).
- **The client CLI.** `bin/cloud.py` (1,012 lines; `project_create` `:585-618`,
  `project_claim` `:621-652` — the selection `len(created) != 1` `:638-639`,
  D2316; `deliver_secret` `:190`; `parser()` `:836-`); `bin/project.sh`,
  `bin/compute.sh`, `bin/operation.sh` dispatch into it. **`bin/db.sh` EXISTS
  and is the operator's root "narrow SQL door"** (ADR 0030, `bin/db.sh:1-30`) —
  D2355.
- **The slot.** `bin/slot.py` (`prepare` `:124-184`, `status` `:192-207`,
  `revoke` `:215-307`); `src/agentic_postgres/slot.py`: `slot_manifest`
  (`:112-180`, schema 10, `compute.profile: small`), `state()` (`:198-244`:
  consumed → quarantined → allocated → declared → **DNS false = `prepared`, true =
  `ready`**), `dns_reading(domain, expected_ipv4)` (`:296-330`: `dig @1.1.1.1` A
  and AAAA; True only for exactly the host's address and no AAAA).
- **The readers a prepared slot breaks** (D2305/D2307/D2312):
  `capacity_probe.read` lists every state-root directory (`:280`) and records a
  missing `outputs.json` as unreadable (`:78`, `:291-295`), popping only the
  candidate (`:303`) → `capacity_reading.decide` refuses `committed undetermined`
  (`:420-430`) → **exit 12 for every other project's deploy while a slot is
  prepared**; `bin/control.py` `compare` reads a key with no row and no document as
  `no_deployed_document` (`:269-270`) → `registry` exit 5 (`:303-306`).
- **Profiles that select services.** `bin/project-runtime.sh` passes `--profile
  session<n>` for every `n` up to `--through-session` (`bin/deploy-project.py:127-128`,
  `:162`); a profile that is not a session exists (`mirror`, `compose.yaml:346`,
  used by `bin/backup.sh`). **A service gated on a facility has no precedent** —
  D2344.
- **The driver fixtures** (`services/clients/{psql,node-pg,psycopg,prisma}`,
  compose profile `session4-verify`, `internal` only, `PGSSLMODE: disable`,
  `compose.yaml:1375-1531`); psql 17.5 in the pgbouncer image; `pg` 8.16.3;
  `psycopg[binary]` 3.2.12; Prisma 6.19.1 (`versions.env:44`), `url.mjs`
  hard-codes `sslmode: "disable"` (`:95`). DBX-001..004 prove the platform's
  transports and **stay as they are** (D2350).
- **The gate to derive from.** `bin/session-38-check.sh` (1,931 lines; header
  `:1-103`, `readonly SESSION=38` `:112`, defaults `:130-177`, `usage`
  `:179-706`, `parse_arguments` `:742-959`, `mode_offline` `:1403-1620`,
  `mode_host` `:1622-1833` (exports `:1702-1779`), `mode_external` `:1835-1920`
  (exports `:1873-1879`)). `tests/contract/test_session_thirty_eight_gate_modes.py`
  (1,062 lines; `SESSION = 38` `:58`, `SESSION_PREVIOUS_NUMBER = 37` `:73`,
  claims table `:86-112`, offline-set assertion `:670-735`, lifecycle variables
  `:961`, usage-per-flag `:1029`). The roster `tests/conftest.py:86-208`
  (Session 38's two `:206-207`); `fresh_totp_code` session-scoped `:333-359`.
  `test_cli_contract.py`: `SHELL_COMMANDS` `:42-249`, `PYTHON_COMMANDS`
  `:251-328`, `COMMANDS_WITH_VERBS` `:512-553`.
- **The live modules to extend or read.** `tests/external/test_session38_public_lifecycle.py`
  (328 lines; `LIFECYCLE` `:58-67`, the five tests `:202-309`);
  `tests/deployment/test_session38_reconciler.py` (232 lines);
  `tests/deployment/test_session31_capacity.py` (`:142-207` the refusal half,
  `:210` the control).
- **Isolation.** `evidence.ISOLATED_FIELDS` (`src/agentic_postgres/evidence.py:37-68`,
  18); the categories in `tests/deployment/isolation_matrix.py` (`MUST_DIFFER`
  `:37-87` incl. `database.pooled.port`/`direct.port` `:50-51`, `routes.*.url`
  `:64`; `classify()` `:243-255`, MUST_DIFFER first); the offline leaf proof
  `tests/contract/test_isolation_leaves_offline.py:138`. The deployed document's
  `database` uses `deployedDatabase` (`schemas/outputs.schema.json:792`, `pooled`
  `:824`, `direct` `:827` → `$defs/endpoint` `:1738`); built at
  `deployed_output.py:675-679`.

**Measured at planning** (2026-10-10, WSL, throwaway; scripts and transcripts in
WSL `~/s39p/rig/` — `rig.sh`, `rig2.sh`, `verifier.py`, `traefik.yaml`,
`dynamic.yaml`, `rig1.txt`…`rig4.txt`, `rig2.txt` — copied to the scratchpad
`s39p/rig/`). The pinned images: Traefik 3.7.10, `pgvector/pgvector:pg18`
(psql/pg_dump 18.4), PgBouncer 1.24.1; a CA and a server certificate for
`a.direct.rig.test` + `a.pool.rig.test` made with openssl; one Traefik
entrypoint `:5432`, two file-provider TCP routers `HostSNI(...)` with `tls`.

| # | Case | Result |
|---|---|---|
| 0a | libpq 18 default negotiation, verify-full, **default TLS options** | **refused**: *"SSL error: tlsv1 alert no application protocol"*; Traefik: *"tls: client requested unsupported application protocols"* — the `SSLRequest` WAS handled (the failure is inside the handshake) |
| 0b | the same with a TLS option `alpnProtocols: [postgresql]`, `minVersion: VersionTLS12` | **connected**; the server reads `ssl=false` (Traefik → backend is plaintext) and the client address is **Traefik's** |
| 0c | `sslnegotiation=direct` | connected |
| 0d | pool hostname → PgBouncer (transaction) on the same port | connected (`show port` 5432; `create temp table` ok) |
| 0e | **control**: `sslmode=disable` | refused: held **~61.6 s**, then *"expected authentication request from server, but received H"* (Traefik's HTTP answer after its read deadline); never reaches a backend |
| 0f | wrong SNI (`wrong.rig.test`), require and verify-full | refused, *"unexpected eof while reading"* |
| 0g | `sslsni=0` | refused, the same |
| 0h | `channel_binding=require` | refused: *"server did not offer an authentication method that supports channel binding"* — expected through a terminating proxy |
| 0i | a 75 s query, client silent, direct and pool | **survived** both (76.5 s) — the 60 s deadline does not apply to a routed connection |
| 0j | **control**: the backend reached without Traefik | connected (`ssl=false`, the client's own address) |
| 1a | customer pooler, userlist = ONE SCRAM **verifier** (no password), right password | **connected** (SCRAM pass-through) |
| 1b | wrong password; the superuser `postgres`; the other customer role; at either pooler | refused, **every one** *"FATAL: SASL authentication failed"* — no role-existence oracle |
| 1c | `customer_admin` through the session pooler | `CREATE TABLE public.t` ok; `app_private` *"permission denied for schema"*; `CREATE SCHEMA` *"permission denied for database"*; `CREATE ROLE` refused; `SET application_name` + advisory lock kept across statements; `pg_dump -n public` ok |
| 1d | `customer_app` through the transaction pooler | INSERT/SELECT on the admin's table through default privileges ok; `CREATE TABLE` *"permission denied for schema public"* |
| 1e | rotation: `ALTER ROLE … PASSWORD :'verifier2'`, new userlist, `docker kill -s HUP` | old password refused, new accepted, **container not restarted** |
| 1f | **control**: userlist salt ≠ server salt | **uninformative** (D493): connected — most likely because PgBouncer reused the server connection R2 had opened (an inference, not read), so the pass-through with a mismatch was never exercised. **Owed in Run 1 (rig 39d)** with a fresh pooler |

---

## 1. The divergence table

Six columns. Each row is a **measured fact about the tree at `f47cee4`** (or the
host as Session 38's records and the planning readings left it, or the planning
rigs above) set against what the brief says, with the decision this plan takes.
**Next free number after this table is D2356.** Rows the runs add go in a second
table below it, in execution order.

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D2325** | D1958 (1): *"whether Traefik v3.7's TCP router can route the Postgres protocol by SNI and terminate TLS for libpq's default `SSLRequest` negotiation and for `sslnegotiation=direct` … If (1) fails, the gateway is a small TCP proxy of the product's own."* | Measured at planning (§0 0a–0d, 0i, 0j): 3.7.10 handles `SSLRequest` and direct TLS and routes by SNI to two backends on one port; **with the default TLS options libpq 18 is refused for ALPN**; with `alpnProtocols: [postgresql]` both modes connect verify-full; the backend leg is plaintext on the Docker network and Postgres sees Traefik's address; a 75 s silent query survives. | **The gateway is the edge**: a fifth entrypoint `postgres` (container `:8432`, published `5432:8432`, unprivileged like `web`/`websecure`) and a TLS option **`postgres`** in `infra/edge/dynamic/baseline.yaml` (`alpnProtocols: [postgresql]`, `minVersion: VersionTLS12`, `sniStrict: true`). Every TCP router names `tls.options: postgres@file`. **No product TCP proxy.** The Ledger's Connect text says *channel binding is not offered* (0h) and the threat row says *Postgres sees the gateway's address, so no per-client address rule exists*. Rig 39a (Run 1) re-runs the matrix with the EXACT option file the edge will ship and the remaining cases. | The cheapest gateway is the one that is already bounded, measured and recreated on a sheet (ADR 0244); the ALPN fact is the kind no document would have predicted and would have failed the first live connection. | **0268**, 0044, 0244, 0246 |
| **D2326** | D1958 (2): *"a wrong SNI refused (control: the right one served)"*; §5: *"a plaintext `SSLRequest`-less start is refused"*. | 0e–0g: wrong SNI and no SNI → TLS EOF; plaintext → **held ~61.6 s** then Traefik answers HTTP bytes; nothing reaches a backend in any case. | **All three are refusals, kept as standing proofs** (EP-LIVE-002, external). **The 61.6 s hold is a resource an unauthenticated peer can spend**: rig 39a measures `entryPoints.postgres.transport.respondingTimeouts.readTimeout: 10s` (expected: plaintext refused in ~10 s) **with the 75 s silent-query case as its control** (must still survive); if the control fails at any value, the default stays and THR-EP-GATEWAY says so. | A refusal that ties a socket for a minute is still a refusal, but it is the number a connection-exhaustion row is about. | **0268** |
| **D2327** | D1958 (3): *"`<key>.pool.<domain>`, `<key>.direct.<domain>`"*. | ADR 0002: every name is derived once, in `naming`; a project's one operator-declared name is `project.domain` (a slot's `slots.declared[].domain`, `host.example.yaml:64-82`). `slot1-prod`'s was `slot1.agenticpostgresql.com`. Measured 0d: one port carries two names to two backends. | **`naming.endpoint_hosts(domain)` → `pool.<domain>`, `direct.<domain>`**; one host port 5432 for both. For `slot2-prod`: `pool.slot2.agenticpostgresql.com`, `direct.slot2.agenticpostgresql.com`. | Deriving from the declared domain keeps the operator's one declaration the only input, and the slot's grey-record discipline (D2148) extends by two lines rather than by a new zone layout. | **0268**, 0002 |
| **D2328** | §5: *"per-project TCP routers for `<key>.pool.<domain>` (PgBouncer) and `<key>.direct.<domain>` (the database)"*. | Traefik joins each project's `edge` network only (`edge-network.sh:209`); `postgres` joins `internal`+`backup` and its guard forbids `edge` (`compose.yaml:281-282`, `test_compose_contract.py:325-330`); `pgbouncer` joins `internal` only (`test_pooler_contract.py:232`). A file-provider router cannot address a tenant safely (`edge_credentials.py:165-173`). | **Neither `postgres` nor the platform `pgbouncer` moves** (their guards stand unchanged). **Two new services** per enabled project, `customer-pool` and `customer-direct`, join **`edge` and `internal`**, and carry **label** TCP routers (`traefik.tcp.routers.*`, the Docker provider, `apg.traefik.scope: managed`, `traefik.docker.network: ${EDGE_NETWORK_NAME}`). | The label path is the one measured for tenancy (D271, ADR 0085); the two containers that straddle are the two whose only job is to be the door. | **0268**, 0085, 0013 |
| **D2329** | D1959: *"`customer_app` (pooled) and `customer_admin` (direct) … both reached only over TLS through the gateway"*; the direct endpoint is *"the database"*. | The image's `pg_hba` admits **every role** from any non-loopback address by SCRAM (`docs/database-security.md:138-151`); the platform pooler's userlist holds `app_runtime` and the pool admin (`compose.yaml:608-613`). Routed straight to either, the public port would accept a platform credential — and `bin/connect.sh print-env` hands `op` the app runtime password today. Measured 1a–1b: a pooler whose userlist names one role refuses every other, the superuser included, with one message. | **The door is customer-only by construction**: `customer-pool` (`pool_mode = transaction`, userlist `customer_app`) behind `pool.<domain>`, `customer-direct` (`pool_mode = session`, userlist `customer_admin`) behind `direct.<domain>`. **"Direct" is a session-mode connection — one server connection per client, session state kept, `pg_dump` and migrations work (1c)** — and the Ledger's `direct_endpoint` text says exactly that. No `hba_file` is rendered. | A public port that admits the platform's roles turns every platform secret into an internet credential; an allowlist that is the pooler's own userlist needs no address the gateway hides (D2325). | **0269**, 0044 |
| **D2330** | D1959: *"passwords are generated secrets materialised like every other and shown once through `/api/v1`"*. | ADR 0260 `:63-65` **rejected** *"the reconciler writes a one-time password into the operation's result"* (the control database, its WAL and its backups would hold it); `0004:57-59` CHECKs `result_secret` to `project.export`. ADR 0260's own handoff sends only `sha256(T)`. Measured 1a, 1e: a verifier-only userlist authenticates (pass-through); rotation is `ALTER ROLE` + userlist + SIGHUP. | **By verifier, ADR 0260's shape again.** `bin/endpoint.sh credential --project-key K --role app\|admin --password-file F` generates `secrets.token_urlsafe(32)` on the workstation, writes F (0600, `O_EXCL`), computes the SCRAM-SHA-256 verifier (4096 iterations, 16-byte salt — `~/s39p/rig/verifier.py` is the model), and posts **only the verifier**. The reconciler's `credential.rotate`: `ALTER ROLE <role> PASSWORD :'verifier'` through `container_exec.run` with the value on stdin as a psql variable (never argv), then `bin/customer-credentials.sh sync` regenerates both userlists **from `pg_authid`** and SIGHUPs both poolers. **No secrets-contract entry, no Infisical value, no plaintext on the host.** A customer cannot choose a password (the CLI has no such flag). | The control plane holds nothing that opens a project's data (§8): a verifier of a 256-bit random password opens nothing and cannot be brute-forced. `pg_authid` stays the one source, so a restore or a branch carries the credential with the data. | **0269**, 0260 |
| **D2331** | Stage plan §2.2: Session 39's two secrets *"`secret_required_added`, which ADR 0162 prices at major"*. | `secrets.required_names` is rendered at `RENDER_SESSION = 2` (`rendering.py:53`, `:353-360`; pinned `["session2_sentinel"]`, `test_output_schema.py:218`); `classify_document_changes` derives `secret_required_added` only from that list (`upgrade_plan.py:247-248`), so a later secret prices as `implementation` (patch, `:239-241`), and the class is not `--also`-declarable (`bin/upgrade.py:129-138`). **A published port has no class** (`compatibility.py:89-105`). | **No secret is added (D2330), so neither defect is met this session.** 1.17.0 is predicted *minor* — `document_schema_migratable` (manifest 11, outputs 22) and `api_operation_added` (`credential.rotate`, two routes) — **read from `upgrade plan`, never chosen.** The port is the edge's and is enforced by the deploy's refusal (D2339), not by the price. **The unreachable class is carried to §10 unrepaired**, named as a reader that cannot see what it prices. | Repairing the pricing reader is a session's worth of migration-graph work for a class this session does not produce; recording it keeps the next secret from shipping at patch silently. | 0162 |
| **D2332** | D1959: *"`customer_admin` (direct; DDL in `app` and in schemas it creates, never `app_private`, `api`'s definer internals, `extensions`, roles or `SUPERUSER`)"*. | The project-set lint requires FORCE RLS on every `app` table (`migrations.lint_project_set`); `CREATE` on the database grants `CREATE SCHEMA` **and** trusted extensions; `0001:34` revokes `CREATE` on `public` from PUBLIC. Measured 1c–1d. | **Customer DDL in `public` only**: `GRANT USAGE, CREATE ON SCHEMA public TO customer_admin`; `GRANT USAGE ON SCHEMA public TO customer_app`; `ALTER DEFAULT PRIVILEGES FOR ROLE customer_admin IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO customer_app` and `USAGE, SELECT ON SEQUENCES`; `GRANT USAGE ON SCHEMA extensions` to both (pgvector's types; rig 39c reads `extensions.vector(3)` in a customer table); `GRANT CONNECT` to both (the exhaustive list `:156-161` gains two). **Nothing** on `app`, `api`, `app_private`; no `CREATE` on the database; `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`. | `app` is the platform's reviewed schema with an invariant a customer's DDL would break; `public` is where every client (Prisma's default) looks, and it is empty here. | **0269** |
| **D2333** | ADR 0259: an export dumps the customer's schemas. | `dump_argv` is `-n app -n api` (`reconciler_dispatch.py:398-407`); with D2332 the customer's own tables live in `public`. | **`-n app -n api -n public`**; LIFE-EXPORT-001's `test_the_export_names_only_the_customer_schemas` names exactly the three (stricter). ADR 0259 amended by one paragraph. | An export that omits the tables the customer made would be the worst kind of success. | 0259 |
| **D2334** | D1959: *"each with a `CONNECTION LIMIT` summed into ADR 0070's budget as two new claimants"*; §5 *Must not*: *"Raise `max_connections` to fit the new claimants without the budget test"*. | Six summands (`config.py:1531-1597`) held by an AST guard (`test_agent_plane_contract.py:295-304`); `postgres-bootstrap.connection_limits` divides the remainder (`:487-580`); profiles set `max_connections` 48/56/100. | **Two claimants, only when `database.public_endpoints.enabled`**: `customer_pool_connections` and `customer_direct_connections`, per profile in the profile table, **proposed small 2/2, standard 3/3, large 5/5 and fixed by rig 39e** (each profile must still pass `_validate_connection_budget` and leave the application remainder ≥ `pool_size`). Each pooler's `max_db_connections` and each role's `CONNECTION LIMIT` equal the claimant. `BUDGET_CLAIMANTS` widened by the two names under ADR 0269; `max_connections` not raised. | The two doors are bounded the way every other claimant is, and the budget test proves the sum rather than trusting it. | **0269**, 0070 |
| **D2335** | D1958 (4): *"HTTP-01 per hostname against the issuance limits, versus one wildcard by DNS-01 … a security decision ADR-recorded"*. | Every router uses HTTP-01 (`traefik.yaml:126-127`); no DNS credential on the host; production ACME, one attempt per hostname (D2064); the proxied wildcard catches every unlisted name (§0). **Whether Traefik issues a certificate for a TCP router's HostSNI by HTTP-01 is unmeasured.** | **The operator, 2026-10-10: HTTP-01 per project.** Each enabled project's `customer-pool` router carries `tls.certresolver` and `tls.domains[0].main = pool.<domain>`, `sans = direct.<domain>` — **one certificate, two names**; `customer-direct`'s router names the same domains so the store serves it. **Rig 39b (Run 1)** proves it against Pebble with `pebble-challtestsrv` (**control**: an HTTP router's certificate on the same rig); **if a TCP router does not trigger issuance, the fallback measured in the same rig** is an HTTP router `Host(pool.<d>) \|\| Host(direct.<d>)` on `customer-pool`'s labels pointing at the edge-probe (it answers 404; its only job is the certificate). DNS: **two more grey A records per slot** (`pool.`, `direct.`), by hand; `slot.dns_reading` reads all three before `ready`. Let's Encrypt: one issuance per project (50 per registered domain per week, `bin/edge.sh:12-18`). | No DNS-edit token on a host that already holds root's other keys; the per-name record is what HTTP-01 needs anyway because the wildcard is proxied. | **0268** |
| **D2336** | D1956/§5: *"Wake-on-connect built only if the rig allowed it"*; threat #3. | A stopped container's label router disappears (D271; rig 38b); Traefik has no hold-and-wake for TCP. | **Not built.** `wake_on_connect` stays `planned` with `target_session: null` and its `today` saying *a sleeping project's endpoints refuse the connection (TLS closed); wake it with `apg project wake`*. Rig 39a records the sleeping case (the router gone → wrong-SNI refusal). Threat #3 closes as *not built*. | A connection that waits for a 22 s wake would need a proxy of our own — the thing D2325 avoided. | **0268** |
| **D2337** | §5: *"Publish any port beyond ADR 0246's list"* (must not); D1959's roles *"per project"*. | Nothing chooses which projects get an endpoint. `pooled_public` is a refused platform-pooler field (CFG-010, `config.py:1443-1473`). | **Manifest schema 11: `database.public_endpoints: {enabled: boolean}`**, default `false`, absent below 11, migratable. `slot.slot_manifest` writes `true` (schema 11). **alpha-dev and beta-dev stay off** (alpha's names are the live control); **a manifest with `control.enabled: true` and `public_endpoints.enabled: true` is refused** (`ManifestError`, a named code). `pooled_public` and CFG-010 are untouched. | The control plane's database must never have a public door; the operator's dev projects need none; a slot is what a customer holds. | **0268** |
| **D2338** | ADR 0246 item 2: *"`publication()` keeps raising … Session 39 changes them under its own ADR"*. | §0 lists every guard: the compose and edge tests, the host firewall (`docker-user-rules.v4:37-50`, `.v6`), ufw, `provision-host.sh`'s listener check, `test_listeners.py:46`, `test_host_infrastructure.py:151`, `test_session2_host.py`, external `FORBIDDEN_PORTS`, `test_session4_public_transports.py:142`, DBX-005. | **One run (Run 4), one ADR (0268), every guard moved to the measured set `{80, 443, 5432}`** — widening an allowlist to a measured set, not weakening (CLAUDE.md §6). `publication()` **keeps raising** (no project publishes; the edge does). DBX-005 is reworded *"the platform's transports are not publicly reachable"* and its 5432 assertion is replaced by EP-LIVE-002's stricter one (5432 answers only TLS with a known SNI and only customer roles). 6432, the loopback range, 8080, 8443, 9000, 2375/6 and 5433 stay forbidden. On the host: `provision-host.sh --check` (expected exit 6, the firewall out of policy) → `--apply` (Sheet F1). | A port is real only when the firewall, the edge and the scan agree; moving them in one run is what keeps a reviewer from finding one of the four still saying "never". | **0268**, 0040, 0044 |
| **D2339** | D1975: *"the edge's one announced recreation"*; 24.4 s measured on the CX23. | `require_edge_serves_this_release` (`deploy-project.py:770-799`) refuses a release whose static config the edge lacks (D811). | **The check also requires the `postgres` entrypoint** (`:719-733` widened); Sheet E1 is `sudo bin/edge.sh --host host.yaml restart` **once, announced, with the probe on all three projects** — the EDGE class re-measured on OVH into the envelope. | The deploy already knows how to refuse a stale edge; the window is the one number a tenant would ask about. | 0244 |
| **D2340** | D2310 / D2292: the two refusal proofs cannot be forced on OVH (`large` 840 MiB admitted; the guardrail 1,600 < safe available 4,620). | `test_session31_capacity.py:142-207` asserts exit 12; `test_session38_public_lifecycle.py` `LIFECYCLE` `:58-67` and `:224-239` assert the `large` resize `failed capacity_exhausted`. | **The operator, 2026-10-10: prove the decision (ADR 0270).** Each live refusal proof asserts **the outcome equals what the recorded reading implies** — refused (exit 12, `capacity_exhausted/admission`) **iff** the candidate's charge exceeds `safe available` in the SAME admission JSON — and prints both numbers. NODE-ADMIT-002's direct refusal test, on a host where the guardrail is below safe available, asserts that arithmetic and **requires the rehearsal's injected refusal record** (`test_the_admission_rehearsal_recorded_a_refusal_and_a_control`, already a node id) to have been written on this host at this commit. The lifecycle instrument records admission's JSON for each resize. **Stricter**: a wrong decision in either direction fails, which the fixed assertion could not see. | A proof that needs a full host to say *no* measured the host, not the rule; the rule is *the decision follows the reading*, and that is checkable on any host. | **0270**, 0221, 0258 |
| **D2341** | §31 item 4: the readers of a prepared slot before any deploy meets one. | §0: admission exit 12 and registry exit 5 while a slot is prepared; D2305: the storage observer spends 31 attempts on a route the manifest disables. | **A key that is a declared slot (`host_config.declared_slots`) with `bootstrap-state.json` and no `outputs.json` commits nothing**: `capacity_probe.read` records it under a new `prepared` list (named on the committed line as *"slot3-prod prepared, commits nothing"*), never `unreadable`; `bin/control.py compare` reads it `prepared` (agreeing, exit 0, printed `prepared (slot)`). Anything else without a document stays a difference. **The storage observer skips a facility the manifest disables** (D2172's REST shape). Needed: Session 39 holds `slot3-prod` prepared through `slot2-prod`'s whole lifecycle. | Two readers that predate the directory kind fail closed correctly and stop every deploy; the repair names the kind instead of guessing. | 0257, 0195 |
| **D2342** | §31 item 1: *"prepare the next, with the OVH plan upgrade deferred to it"*. | One slot at `small` left 5,046 MiB available on OVH; `slot.state()` reads DNS false as `prepared` (`slot.py:198-244`). | **The operator, 2026-10-10: two slots, one alive at a time; no OVH upgrade in 39 (owed before 41).** `slot2-prod` (domain `slot2.agenticpostgresql.com`) and `slot3-prod` (`slot3.agenticpostgresql.com`) are declared, bootstrapped and materialized on day 1 with ONE placement of the credential; **`slot3-prod`'s three A records are created only after `slot2-prod`'s second creation has been refused `no_slot`** (Sheet P2), so the reconciler cannot allocate it early. `slot3-prod` is kept. | Re-earning `project_deletion` needs a delete; a live customer project needs a slot that is not deleted; holding one by its DNS uses a state the product already derives. | 0257 |
| **D2343** | §31 item 2: *"the six rows to `trial` at the bump"*. | ADR 0261 / `reality_ledger.trial_problems` (`:165-194`): a `trial` row's evidence must name only claims whose `CLAIM_INTRODUCED_IN` equals `CURRENT_SESSION`. `lifecycle_operations_live`, `lifecycle_project_door_live`, `reconciler_live` were introduced in 38. | **Session 39 introduces `lifecycle_retrial_live` (external, LIFE-LIVE-003)** — Session 39's lifecycle read through `/v1` and the slot's own door: every one of the six types succeeded on `slot2-prod` at the deployed commit, the resize decided per ADR 0270, the export holding exactly `app`, `api`, `public`. **The six rows' `trial` evidence names it**; the Session 38 claims are re-run against the same record and must pass too, but no row cites them. ADR 0261 unchanged. | The guard is right: a row re-trialed in 39 is proved by 39's claims. | 0261 |
| **D2344** | — | `project-runtime.sh` selects `--profile session<n>` up to `--through-session` (`deploy-project.py:127-128`); a service with `profiles: [session39]` would start on alpha, beta and control-prod. | **The customer poolers carry `profiles: [public-endpoints]`**, and `bin/project-runtime.sh` (and every caller that builds the profile list — grep `--profile` in `bin/` and `src/`, D979) adds `public-endpoints` **iff** the rendered `compose.env` carries `APG_PUBLIC_ENDPOINTS=1` (rendered from the manifest). A facility-keyed profile is new; `mirror` is the nearest precedent. | A session profile is about *when*; this one is about *which project*. | **0268** |
| **D2345** | D2316: the claim says *two* when there are two, and picks the creation this CLI holds. | `bin/cloud.py:631-639`: `len(created) != 1` → *"no succeeded creation of {key} is visible"*. | **Choose the succeeded creation whose `handoffs/<operation-id>` file exists**; exactly one → claim it; none → *"no handoff token for {key} is held here"* exit 3; more than one held → *"{n} succeeded creations of {key} have a token here"* exit 3. | The CLI holds the token; the token names the creation. | 0260 |
| **D2346** | D2315: `--s3-no-head`; a 403 named as a provider refusal. | `services/backup-mirror/mirror.sh:71-72` (`rclone sync --checksum --fast-list --retries 1`), the count `:75`; `bin/backup.py:703-795`. | **Rig 39f (Run 1)** counts HEAD requests with `--dump headers` against a throwaway MinIO for a 50-object sync, with and without `--s3-no-head` (**control**: the count listing still equals the source). If the flag removes one HEAD per upload and the count still agrees, Run 2 adds it; **`verb_mirror` names a 403 on both passes as *"the provider refused the requests (403): read the account's transaction caps"***. | One Class B call per uploaded object is what stopped a creation on day 2 of Session 38. | 0264 |
| **D2347** | D2320: the database access policy belongs in the DR kit. | `dr_kit.plan_export` (`src/agentic_postgres/dr_kit.py:124-214`) carries host, capabilities and per-project files; the policy (`/etc/agentic-postgres/database-access-policy.json`, `access_policy.py:45`) is in none. | **An optional host artefact `database-access-policy.json`** (digest in `kit.json`, `verify` checks it) when the file exists; `docs/node-loss-runbook.md` §8 names `database-access.sh publish` from the kit. | A file outside every kit is a file a move forgets (it did). | 0189 |
| **D2348** | §10: *"The reconciler restarted once during the boot (NRestarts 1): read, not explained."* | The unit orders on Docker and the edge only (`:9`); at boot the control project's containers arrive ~40 s after the edge (B1: edge 40 s, units 80 s); `start()` raises exit 6 on a control-database error (`bin/reconciler.py:1056-1077`), systemd restarts it 30 s later. | **`start()` waits for the control database for up to 180 s**, retrying `control_target()` every 10 s and printing *"waiting for the control project's database (n s)"*, before failing exit 6. B1 in Run 11 reads `NRestarts` 0. | A restart that is expected should not look like a fault in the one reading taken after a reboot. | 0256 |
| **D2349** | — | `test_session2_public_edge.py` `test_every_reported_endpoint_is_loopback_or_absent` (`:115-165`) asserts `database.pooled`/`direct` hosts and URLs are loopback. | **The public endpoints are a NEW member, `database.public`** (outputs schema 22): `{enabled, pooled: {host, port, user, database, sslmode}, direct: {…}}`, `sslmode` `"verify-full"`, **no URL, no password**; `null` members when disabled. The loopback assertion keeps its meaning. `host` and `user` are MUST_DIFFER; `port` (5432 on every project) and `sslmode` MUST_MATCH; `ISOLATED_FIELDS` gains `database.public.pooled.host`, `database.public.direct.host` (18 → 20). | Two meanings of `database.pooled` would make an old proof pass or fail for the wrong reason. | **0268**, 0002 |
| **D2350** | D1960: *"the four driver fixtures re-pointed at the TLS endpoint"*. | The fixtures run on `internal` as `app_runtime`, `sslmode=disable`, and DBX-001..004 prove the platform's transports; `url.mjs:95` hard-codes `disable`. | **DBX-001..004 stay as they are.** The fixture IMAGES gain one input, `APG_SSLMODE` (default `disable`; `verify-full` with `sslrootcert=system` for libpq clients and Node's bundled CAs for `pg`/Prisma), and are **run from the workstation** in external mode against `slot3-prod`'s public names with the customer passwords (EP-LIVE-001). **Rig 39c (Run 1)** runs the four images against rig 39a's Traefik with the rig CA (**control**: psql, already measured) and decides two facts: whether Prisma's engine and `pg` send SNI and accept ALPN `postgresql`, and whether Prisma needs `pgbouncer=true` with `max_prepared_statements = 100`. **A driver that cannot connect gets no snippet** (D1960) and its Ledger line says so. | A snippet is shown only for a client that has connected through it. | **0268** |
| **D2351** | D1960: snippets *"rendered from the endpoint metadata `/api/v1` serves"*. | `app.control_projects` (`0003:17-27`) holds `domain`, no endpoint; `control_adopt_project` (`0003:161-182`) refreshes from the deployed document (ADR 0158: the document is the address book). | **The control set's fifth migration `0005-control-endpoints.sql`** adds `endpoints jsonb NULL` to `control_projects`, written by `control_adopt_project` from the document's `database.public`, adds the `credential.rotate` argument CHECK if the set validates arguments in SQL, and a committed proposal (ADR 0243, D2136). `GET /v1/projects/{key}/connections` serves `endpoints` plus snippets; `409 not_available` (`ledger_row: pooled_endpoint`) when `endpoints` is null. | The control plane reads the address the deploy recorded; it never derives one of its own. | **0268**, 0243 |
| **D2352** | D1960: one function in `src/agentic_postgres/`. | The `auth-api` image cannot import `agentic_postgres` (`operations.py:9-18`); `src` loads service modules through `service_source.load`. | **`services/auth-api/app/connection_snippets.py`** (standard library only), loaded into `src` by `service_source` for tests: psql (`psql "host=… port=5432 user=… dbname=… sslmode=verify-full sslrootcert=system"`), Prisma (`DATABASE_URL` pooled, `DIRECT_URL` direct, the flags rig 39c decides), `pg` (a config object), psycopg (a conninfo). **The password is always the placeholder `<password from your file>`**; a test holds that no snippet can carry a value. | The image's code is the one place the API can run; one implementation. | 0204 |
| **D2353** | §5: *"`apg db connect\|status`"*. | **`bin/db.sh` is the operator's root narrow SQL door** (ADR 0030, `bin/db.sh:1-30`); `apg` dispatches verb X to `bin/X.sh`. | **The customer verbs are `bin/endpoint.sh`** (`apg endpoint`): `show --project-key K [--json]` (`GET …/connections`), `credential --project-key K --role app\|admin --password-file F [--wait]` (the rotation), `connect --project-key K --role app\|admin --password-file F [-- psql args]` (execs the local `psql` with the URL and `PGPASSFILE` written 0600 to a temp file, removed after). Dispatched into `bin/cloud.py` like `project.sh`. | Two meanings of `apg db` — root SQL and a customer's connection — would be the confusion the threat model's item 7 is about. | — |
| **D2354** | — | `ROLE_SUFFIXES` order reaches rendered output (`naming.py:181-189`); `bootstrap_statements` creates every derived role. | **`customer_app` and `customer_admin` are appended LAST** and created `NOLOGIN` on **every** project (uniform statements, `check_violations` reads them everywhere); `LOGIN` and `CONNECTION LIMIT` are applied **only when the facility is enabled**, and **never a `PASSWORD`** — `postgres-bootstrap` must not reset a customer's verifier on a redeploy (a test holds that no statement it builds names a customer role with `PASSWORD`). | A role that exists everywhere but logs in only where it should is easier to prove than a role that exists sometimes. | **0269** |
| **D2355** | CLAUDE.md §9: *"The 24 unclaimed requirements"*; the stage plan's citations. | Stale citations met while planning: `stage-5-plan.md:144-158` cites `config.py:1354` (now `:1443`), `runtime_override.py:527-547` (`:532-552`), `compose.yaml:1813-1817` (`:1834-1838`), `rendering.py:925` (`:961`); the stage plan's D1959 cites ADR 0028 for NOINHERIT/SET ROLE (it is **ADR 0026**, `0026:48-60`); ADR 0256 `:58-62` says the reconciler runs after the control project's unit (the unit does not, D2348); `tests/acceptance-registry.yaml:16` still says `target_session 1-12`; `APG_ADMIN_PASSWORD_FILE` is exported by the gate (`:1720`) but absent from the roster. | **Recorded so the executor does not chase them.** The registry header and ADR 0256's sentence are corrected in Run 9 (documentation); the roster gap is checked by `test_conftest_roster` (or whatever holds the roster — grep `ENVIRONMENT_VARIABLES` in `tests/contract/`) in Run 9 and, if the guard does not cover exported-but-unlisted, a D row. | A citation that looks measured and is not is the class this project keeps producing. | — |

**Rows added during execution** (D2356 onward, in execution order):

| # | Brief says | Tree does | Decision | Why | ADR |
|---|---|---|---|---|---|

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**One new family, `EP`** (the stage plan's proposal, D691): the regex at
`tests/contract/test_acceptance_registry.py:118` gains `EP`, and the family
comments gain one sentence: *Session 39 (ADR 0268-0270) adds `EP` for the public
Postgres endpoints — the edge's entrypoint, the customer poolers, the customer
roles and their credentials.* **Fourteen requirements, fourteen claims, all
`target_session: 39`, all P0 — ten offline, three external, one host.** Node ids
below are **proposed; Run 9 writes what the runs actually wrote**, read out of the
tree with `pytest --collect-only -q` (D1236, D2129). Registry entries are
committed by Run 9 with the constant (D690), under **`# Session 39 (ADR
0268-0270)`**.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `EP-EDGE-001` | The edge's static config has exactly the `postgres` entrypoint added (`:8432`, published `5432:8432`); the `postgres` TLS option has ALPN `postgresql`, TLS 1.2 minimum, `sniStrict`; the firewall rules v4 and v6 admit exactly 80, 443, 5432; the deploy refuses an edge without the entrypoint | `tests/contract/test_edge_config.py::test_the_postgres_entrypoint_is_the_only_one_added`, `::test_the_postgres_tls_option_offers_only_the_postgres_protocol`, `tests/contract/test_host_infrastructure.py::test_policy_permits_exactly_the_three_ports`, `tests/contract/test_deploy_command.py::test_the_deploy_refuses_an_edge_without_the_postgres_entrypoint` | — (`edge_postgres_entrypoint`) |
| `EP-ROUTE-001` | An enabled project renders exactly two TCP routers (pool → `customer-pool:6432`, direct → `customer-direct:6432`), each with the resolver, `postgres@file`, both names on one certificate; a disabled one renders none; no TCP router targets `postgres` or `pgbouncer`; no router is written to the file provider | `tests/contract/test_endpoint_routes.py::test_an_enabled_project_renders_exactly_two_tcp_routers`, `::test_a_disabled_project_renders_none`, `::test_no_router_reaches_the_database_or_the_platform_pooler`, `::test_one_certificate_names_both_hosts`, `::test_no_tcp_router_is_a_file_provider_router` | — (`endpoint_routes`) |
| `EP-DOC-001` | Manifest 11 accepts `database.public_endpoints`; the control project refuses it; outputs 22 carries `database.public` with no URL and no password; `migrate_v21_to_v22`; the hosts derive from the domain; every new leaf is classified; `ISOLATED_FIELDS` has 20 | `tests/contract/test_project_manifest.py::test_public_endpoints_is_refused_below_schema_eleven`, `::test_the_control_project_refuses_a_public_endpoint`, `tests/contract/test_output_migrations.py::test_v22_adds_the_public_endpoints`, `tests/contract/test_naming.py::test_the_endpoint_hosts_derive_from_the_domain`, `tests/contract/test_isolation_leaves_offline.py::test_every_leaf_of_a_built_deployed_document_is_classified` (existing, stricter) | — (`endpoint_document`) |
| `EP-ROLE-001` | Both customer roles exist NOLOGIN everywhere, LOGIN with a limit only when enabled, never a `PASSWORD` from the bootstrap; grants exactly as D2332; `check_violations` reads them back; on a real cluster `customer_admin` does DDL in `public` and is refused on `app`, `api`, `app_private`, `CREATE SCHEMA`, `CREATE EXTENSION`, `CREATE ROLE`; `customer_app` does DML and no DDL | `tests/contract/test_bootstrap_statements.py::test_the_customer_roles_are_created_without_login`, `::test_no_statement_sets_a_customer_password`, `::test_the_customer_grants_are_exactly_these`, `tests/contract/test_customer_roles_on_a_cluster.py::test_the_admin_writes_only_in_public`, `::test_the_admin_is_refused_everything_else`, `::test_the_application_role_writes_rows_not_tables` | — (`customer_roles`) |
| `EP-BUDGET-001` | The two customer claimants are summed only when enabled; every profile fits with them; each role's limit and each pooler's `max_db_connections` equal the claimant; the bootstrap's application remainder subtracts them | `tests/contract/test_agent_plane_contract.py::test_the_connection_budget_has_no_term_for_the_agent_plane` (existing, its claimant set widened by two under ADR 0269), `tests/contract/test_compute_profiles.py::test_every_profile_fits_with_the_customer_claimants`, `tests/contract/test_bootstrap_statements.py::test_the_application_gives_way_to_the_customer_claimants` | — (`customer_connection_budget`) |
| `EP-POOL-001` | Each customer pooler's userlist is generated from `pg_authid` and names only its role; it refuses every other role with one message; `customer-direct` is session mode, `customer-pool` transaction; both join `edge` and `internal` only, are bounded (mem, pids, cpus) and start only under `public-endpoints`; a SIGHUP rotates without a restart | `tests/contract/test_customer_poolers.py::test_the_userlist_names_only_its_role`, `::test_every_other_role_is_refused_with_one_message`, `::test_the_modes_are_session_and_transaction`, `::test_the_poolers_join_edge_and_internal_only`, `::test_the_poolers_are_bounded`, `::test_the_poolers_start_only_for_an_enabled_project`, `::test_a_reload_rotates_without_a_restart` | — (`customer_poolers`) |
| `EP-CRED-001` | The CLI generates the password, writes it 0600 once, sends only a well-formed verifier; `credential.rotate`'s arguments are `{role, verifier}` validated twice; the reconciler sets it through stdin and syncs; the verifier is in no argv and no log line; old password refused, new accepted | `tests/contract/test_endpoint_cli.py::test_the_password_never_leaves_the_workstation`, `::test_the_password_file_is_private_and_written_once`, `tests/contract/test_reconciler_dispatch.py::test_a_rotation_sets_the_verifier_through_stdin`, `::test_the_verifier_reaches_no_argv_and_no_log`, `tests/contract/test_customer_poolers.py::test_a_rotated_password_refuses_the_old_one` | — (`credential_rotation`) |
| `EP-API-001` | `GET /v1/projects/{key}/connections` serves the document's endpoints and snippets with no password, `409 not_available` when disabled; `POST /v1/projects/{key}/credentials` answers `202` with an operation, human session only; the matrix; the contract snapshot | `tests/contract/test_control_projects.py::test_connections_serve_the_recorded_endpoints`, `::test_a_project_without_endpoints_is_not_available`, `::test_a_rotation_is_an_operation`, `::test_a_key_cannot_rotate_a_credential`, `tests/contract/test_app_contract_aggregate.py::test_the_control_snapshot_is_what_this_checkout_generates` (existing) | — (`connection_api`) |
| `EP-SNIP-001` | Snippets exist exactly for the clients rig 39c connected; each parses back to the served host, port, user and `verify-full`; none can carry a value | `tests/contract/test_connection_snippets.py::test_one_snippet_per_proved_client`, `::test_each_snippet_names_the_served_endpoint`, `::test_no_snippet_can_carry_a_password` | — (`connection_snippets`) |
| `LIFE-SLOT-002` | A prepared, declared slot commits nothing at admission and reads `prepared` at the registry; an undeclared directory without a document is still a difference; the storage observer skips a disabled facility | `tests/contract/test_capacity_probe.py::test_a_prepared_slot_commits_nothing`, `::test_an_undeclared_directory_is_still_undetermined`, `tests/contract/test_control_command.py::test_a_prepared_slot_agrees`, `tests/contract/test_deploy_command.py::test_a_disabled_storage_route_is_not_observed` | — (`prepared_slot_readers`) |
| `LIFE-LIVE-003` | Session 39's lifecycle on `slot2-prod`, through `/v1` and the slot's door: the six types succeeded at the deployed commit; the resize decided per ADR 0270; the export holds exactly `app`, `api`, `public`; two credentials set, the slot reached through both names while it lived, a rotation refused the old password; asleep, both names refused; delete; a second creation refused `no_slot` with no row | — | `tests/external/test_session39_public_lifecycle.py::test_every_accepted_type_ran_on_the_slot`, `::test_the_resizes_followed_the_admission_reading`, `::test_the_export_holds_the_three_customer_schemas`, `::test_the_slot_was_reached_through_both_names`, `::test_a_sleeping_slot_refused_both_names`, `::test_the_second_creation_was_refused_without_a_row` (external `lifecycle_retrial_live`) |
| `EP-LIVE-001` | Through `slot3-prod`'s public names from the workstation, with no SSH: psql verify-full on both; Prisma client pooled and `migrate deploy` direct; `pg` and psycopg pooled; `customer_admin` DDL in `public`, `app_private` refused; the superuser and a platform role name refused at both doors; alpha's names refused | — | `tests/external/test_session39_public_endpoints.py::test_psql_reaches_both_names`, `::test_the_four_drivers_reach_the_pooled_name`, `::test_prisma_migrates_through_the_direct_name`, `::test_the_admin_writes_only_in_public`, `::test_no_platform_role_passes_either_door`, `::test_a_project_without_endpoints_has_no_door`, `::test_this_module_uses_no_ssh` (external `public_endpoints_live`) |
| `EP-LIVE-002` | On the public address: 22, 80, 443 and 5432 answer and nothing else; 5432 refuses plaintext, a wrong SNI and no SNI; the platform's allocated ports stay closed | — | `tests/external/test_session39_public_endpoints.py::test_only_the_four_ports_answer`, `::test_plaintext_is_refused`, `::test_a_wrong_or_absent_sni_is_refused` (external `public_port_scan`) |
| `EP-LIVE-003` | On the host: the edge serves the `postgres` entrypoint; the firewall policy is the measured one; `slot3-prod`'s two poolers run bounded on `edge`+`internal` and its `postgres` still joins only `internal`+`backup`; its routers came back after the reboot; its document shares no `ISOLATED_FIELDS` value with A, B or the control project | — | `tests/deployment/test_session39_endpoints.py::test_the_edge_serves_the_postgres_entrypoint`, `::test_the_firewall_admits_exactly_the_three_ports`, `::test_the_customer_poolers_are_bounded_and_placed`, `::test_the_database_is_still_unrouted`, `::test_the_slot_was_isolated_from_every_project` (host `endpoints_host_live`) |

**Expected counts** — Run 9 counts them from the tuples, never from this prose
(D1628): requirements **332 → 346**, `CLAIMS` **239 → 253**, `OFFLINE_CLAIMS`
**91 → 101**, ADRs **267 → 270**.

**Claims** (`src/agentic_postgres/evidence_claims.py` `CLAIMS`, a block commented
*Session 39 (ADR 0268-0270)*): offline — `edge_postgres_entrypoint`,
`endpoint_routes`, `endpoint_document`, `customer_roles`,
`customer_connection_budget`, `customer_poolers`, `credential_rotation`,
`connection_api`, `connection_snippets`, `prepared_slot_readers` — **these ten in
`OFFLINE_CLAIMS`**, with the per-session assertion in
`test_session_thirty_nine_gate_modes.py` (D1237: assert THESE are in the set,
never its size). External — `lifecycle_retrial_live`, `public_endpoints_live`,
`public_port_scan`. Host — `endpoints_host_live`. `CLAIM_INTRODUCED_IN` gains a
row at 39 for each.

**Existing entries that move** (each a passing proof made stricter, never
weakened — CLAUDE.md §6, under the ADR named):

- **The publication guards** (D2338, ADR 0268): `test_only_traefik_publishes_host_ports`
  → `{"80","443","5432"}`; `test_no_dashboard_entry_point_is_published` → five
  entrypoints and three ports; `test_policy_permits_exactly_eighty_and_four_four_three`
  → renamed `…_exactly_the_three_ports`; `test_session2_host.py`'s three;
  `test_listeners.py` `BASELINE_PORTS` `(22, 80, 443, 5432)`; external
  `FORBIDDEN_PORTS` loses 5432 only; `test_session4_public_transports.py:142`'s
  5432 assertion removed **in the same commit as** EP-LIVE-002's stricter one;
  **DBX-005** reworded. `publication()`'s two tests stay byte-identical.
- **NODE-ADMIT-002** and **LIFE-LIVE-001** (D2340, ADR 0270): the fixed refusals
  become decision assertions; node ids unchanged where the function keeps its
  name; a renamed function moves its registry node id in the same commit (D1119).
- **LIFE-EXPORT-001** (D2333): exactly `app`, `api`, `public`.
- **LIFE-HANDOFF-001** gains `tests/contract/test_control_cli.py::test_the_claim_picks_the_creation_whose_token_is_held` (D2345).
- **The mirror's requirement** (grep `REC-` for ADR 0264's) gains
  `::test_a_refused_mirror_names_the_provider` (D2346), and the DR kit's
  (grep `ADR 0189` in the registry) `::test_the_access_policy_travels_in_the_kit`
  (D2347).
- **OPN-DISPATCH-001** gains `credential.rotate`'s handler in
  `test_every_accepted_type_has_one_handler` (the table, not a new test).
- **CTL-OPS-001**: `test_no_type_is_accepted_and_the_six_stay_executed`
  (`test_operation_types.py:95`) is REPLACED by its exact-set form for 39 — seven
  executed types, accepted iff the row is reachable (D2343).
- **`THR-*` table rows**: four added in Run 9 (Run 1 item 3); none removed.

**New environment gates: two**, in `tests/conftest.py`'s roster:
`APG_CUSTOMER_CREDENTIAL_DIR` (external — the directory holding
`slot3-prod/customer_app` and `slot3-prod/customer_admin`, 0700/0600, written by
`bin/endpoint.sh credential`) and `APG_LIVE_SLOT_OUTPUTS` (host — `slot3-prod`'s
deployed document, copied on Sheet K3). `APG_LIFECYCLE_RECORD_FILE` and
`APG_SLOT_OUTPUTS` are reused for `slot2-prod`. **The Session 39 gate accepts
exactly the Session 38 gate's flags plus `--customer-credential-dir DIR` and
`--live-slot-outputs FILE`** (the derivation diff proves it, D1133).

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| The control set's `0005` frozen into `projects/control/migrations/released.lock.json`, and its proposal committed | Run 6 | `bin/migrate.sh --project project.control.example.yaml freeze-lock`; the proofs apply the release set then the control set's five as `migration_user` before the freeze; `AP900` down; the proposal by the product's own `propose` (D2183); no released migration (D912) |
| `CURRENT_SESSION` 38 → 39; `VERSION` 1.16.0 → 1.17.0; eight Ledger rows → `trial` | Run 9 | All-or-nothing (D690); `README.md:7`; every `--session 38` / `--through-session 38` literal on the documented path moved and counted per file (D678/D1484); the `trial` rules (ADR 0261) |
| `bin/session-39-check.sh` | Run 9 | Derived from 38's by diff (D1482); header and usage rewritten whole (D1488); exactly two flags added; `SHELL_COMMANDS`; `chmod 755` before `git add` |
| **The host firewall admits 5432** | Sheet F1 (Run 10) | `provision-host.sh --check` read first (expected: exit 6, the firewall out of policy and nothing else); `--apply`; `iptables -S DOCKER-USER` read after; the external scan in Run 11 is the proof |
| **The edge recreated with the `postgres` entrypoint** | Sheet E1 (Run 10) | Once, announced, the probe on all three projects; `edge.sh status` and `apg-diag listeners` (5432 present) after; the window recorded |
| **host.yaml declares `slot2-prod` and `slot3-prod`, both copies** | Sheet H1 (Run 10) | The agent writes the candidate as `op` (`s39-hostyaml.py`, a backup first), `diff` read; the operator installs `/etc/agentic-postgres/host.yaml` (root) |
| **Provider resources for two slots** (two Infisical projects and identities, four R2 buckets and tokens, two B2 buckets and keys, six DNS records — three for `slot3-prod` only on day 2) | Sheets P1, SL1, P2 | By hand and by `bootstrap-providers --apply` as for `slot1-prod` (D2061: shred by hand); `--plan` read before `--apply` |
| **Two production certificates** (`pool.slot2…` + `direct.slot2…`; the same for `slot3`) | Run 11, each creation's first deploy | `slot.sh status` reads all three records `ready` first; one attempt; a failed issuance finishes the operation `failed` and is a stop |
| **`slot2-prod` created, credentialed, slept, woken, resized, exported and deleted; `slot3-prod` created and kept** | Run 11 | Through `/v1` only; one operation at a time; the probe running; a failure at any step is read before the next is sent (D1510) |
| **`slot2-prod` consumed** | Run 11 | The tombstone; the repository kept (ADR 0187) |
| `slot2-prod`'s Infisical identity revoked | Sheet SL4 (after the tag) | `slot.sh revoke` with the operator's credential, shredded after |
| The reboot | Sheet B1 | After `slot3-prod` is live and A1' reads `agrees`; every unit and `slot3-prod`'s routers read before the sweep |
| Tag `1.17.0` on the deployed commit | Run 11 | After the merge exits 5 for `documented_path` only (§7); from the WORKSTATION (D2041) |

---

## 5. Build order, run by run

Each run ends with a `**Done.**` paragraph written by the executor: what was
measured, the numbers, the rows it added, and — for a code run — the CI verdict by
full SHA. The targeted modules run ONCE at the run's close and only a failing
module is re-run. `ruff format && ruff check` before every commit; `chmod 755
bin/*.sh bin/*.py deploy.sh` before every `git add`; messages from a file with
`-F`, ending with the attribution line the session's system reminder gives. **Grep
the plans for every third party before measuring it.** **A run that renames, adds
or removes a test function runs `test_acceptance_registry` and
`test_evidence_claims`** (D1119); **a run that adds a module under
`src/agentic_postgres/` runs `test_repository_contract`** (D2114); **a run that
adds a deployed-document member runs `test_doctor_redaction`** (D2091) and
`test_isolation_leaves_offline`; **a run that changes rendering re-renders BOTH
example projects and the control example** (`./deploy.sh --project
project.example.yaml --capabilities capabilities.example.yaml --render-only`, the
same for `project.second.example.yaml` and `project.control.example.yaml`; delete
what each publishes under `.generated/` except the two fixture renders the gate
reads, D1507); **a run that adds or removes a `bin/` command runs
`test_cli_contract` and `git add`s it first** (D1014); **a run that adds a
`document[...]` read to a `bin/` command runs `test_container_selectors`** (D1184);
**a run that touches a documentation page runs `test_documentation_index` and
`test_session12_documented_path`**; **every new test module carries `pytestmark`
before its first test** (D1240) and the sweep-selector guard (D1242) joins the
targeted list. **Docker-backed modules reuse Session 37's
`tests/contract/control_cluster.py`** (`docker rm -fv`, D2098) and the planning
rig's shape (`~/s39p/rig/rig2.sh`) for a cluster plus two poolers.

### Run 1 — the rigs, Sheet E0, the threat list, and ADRs 0268–0270

**Documentation only. Push, say it is pushed, read NO CI verdict** — except that,
because `docs/threat-model.md` and `docs/decisions/README.md` are parsed by
contract tests, run `test_acceptance_registry`, the ADR-index test (grep
`decisions/README` in `tests/contract/`) and `test_documentation_index` once
before the push.

Rigs live in WSL `~/s39/run1/rig39/` (start from `~/s39p/rig/`; copy the whole
directory there first) and are copied to the scratchpad. **Each names its
control and is recorded with what it printed.** Every rig uses the pinned images
from `versions.env` and removes what it made (`docker rm -fv`, `docker network
rm`), read back with `docker ps -a | grep -c rig39` = 0.

1. **Rig 39a — the gateway with the shipped option file** (D2325, D2326, D2336):
   re-run `rig.sh`'s matrix with the TLS option written EXACTLY as Run 4 will
   ship it in `baseline.yaml` (ALPN, min version, `sniStrict`), the routers
   naming `tls.options: postgres@file`, and **label** routers (two containers
   with `traefik.tcp.routers.*` labels and a Docker-provider Traefik over the
   socket, Session 38's rig 38b the template) in place of file routers. Add:
   (a) `respondingTimeouts.readTimeout: 10s` on the entrypoint — plaintext
   refused at ~10 s, **control**: the 75 s silent query still survives (if it
   does not, record and keep the default); (b) the backend container stopped
   (`docker stop`) — the client's error and the router's disappearance (expected:
   the wrong-SNI refusal), **control**: started again → connects; (c) a cancel
   request (`timeout -s INT 3 psql -c "select pg_sleep(30)"` → *"canceling
   statement due to user request"*) through Traefik to PgBouncer, **control**:
   the same without Traefik.
2. **Rig 39b — a certificate for a TCP router by HTTP-01** (D2335): Pebble and
   `pebble-challtestsrv` (pin both images by digest in the rig's notes, read
   from Docker Hub that day), Traefik with the resolver pointed at Pebble
   (`caServer`, `certificatesResolvers.*.acme.httpChallenge.entryPoint: web`,
   `LEGO_CA_CERTIFICATES` for Pebble's root), the challenge server answering
   `pool.a.test` and `direct.a.test` with Traefik's address. Case 1: a TCP router
   with `tls.certresolver` and `tls.domains[0] {main: pool.a.test, sans:
   [direct.a.test]}` — read `acme.json` for one certificate with both names and
   `openssl s_client -connect … -starttls postgres -servername pool.a.test` for
   its issuer. **Control**: an HTTP router with the same resolver issues. **If
   case 1 issues nothing**, case 2 (the fallback): an HTTP router `Host(…) ||
   Host(…)` on the same names and the TCP router with `tls: {}` — the TCP
   handshake serves the stored certificate. Record which one Run 5 builds.
3. **Rig 39c — the four drivers through the gateway** (D2350): build the four
   fixture images (`services/clients/*`) as Session 4's compose does, then run
   each against rig 39a's Traefik and a `customer-pool`/`customer-direct` pair
   with the rig CA mounted: psql (`sslmode=verify-full sslrootcert=…`), `pg`
   (`ssl: {ca, servername}`), psycopg (libpq conninfo), Prisma client (pooled)
   and `prisma migrate deploy` (direct). Read: connected or not, and the error;
   **whether Prisma needs `pgbouncer=true`** with `max_prepared_statements = 100`
   (run the client probe without it; the failure, if any, is the answer); a
   table with an `extensions.vector(3)` column created by `customer_admin`
   (D2332). **Control**: psql, already measured.
4. **Rig 39d — the verifier control, and an empty userlist** (D2330, the §0 1f
   owed control): a FRESH pooler (`docker restart` between cases, so no server
   connection survives) whose userlist verifier has a different salt than the
   server's → refused (expected: the server rejects the pass-through), **control**:
   the matching verifier → connects. Also: a pooler started with an EMPTY
   userlist (a role with no password yet) starts healthy and refuses every login.
5. **Rig 39e — the budget per profile** (D2334): on a copy of `project.example.yaml`
   at schema 10, each profile's members plus the proposed claimants (2/2, 3/3,
   5/5) through `config._validate_connection_budget` (summing them by hand until
   Run 5 adds the terms) and `postgres-bootstrap.connection_limits`; the largest
   pair that fits each profile with the application remainder ≥ `pool_size` is
   the table. Read one customer pooler's resident memory from rig 39c (`docker
   stats --no-stream`) and set its `mem_limit` by ADR 0244's 4× rule.
6. **Rig 39f — the mirror's HEADs** (D2346): a throwaway MinIO as both source and
   mirror (two buckets), 50 small objects, `rclone sync --checksum --fast-list
   --retries 1 -vv --dump headers` with and without `--s3-no-head`; count `HEAD`
   lines; **control**: `rclone size --json` of the mirror equals the source both
   times.

**Sheet E0** (the operator; reads only — `s39-e0.sh` written by the agent,
shipped to `/home/op`, sha256 printed): `free -m`; `docker stats --no-stream
--format '{{.Name}} {{.MemUsage}}'`; `sudo iptables -S DOCKER-USER`, `sudo
ip6tables -S DOCKER-USER`; `sudo ufw status numbered`; `ss -ltn`;
`sudo cat /var/lib/agentic-postgres/edge/traefik.yaml | grep -n -A2 entryPoints`;
`sudo bin/provision-host.sh --help` (its flags, for Sheet F1); `dig +short A` and
`AAAA` of `slot2.`, `pool.slot2.`, `direct.slot2.`, `slot3.`, `pool.slot3.`,
`direct.slot3.agenticpostgresql.com` at `@1.1.1.1` (expected today: the
wildcard's Cloudflare addresses); `systemctl show -p NRestarts
agentic-postgres-reconciler`; `df -h /var/lib/docker`.

**The threat list made specific** (D1978): hosted items #2 (`:192-196`), #3
(`:197-201`), #7's 39 half (`:216-222`) and #10's 39 half (`:233-246`) rewritten
with the negative test each owes BY NODE ID (§2), plus **one new item**: *the
public door admits a platform credential* (EP-POOL-001, EP-LIVE-001's
`test_no_platform_role_passes_either_door`). Item #3 is closed as *not built*
(D2336). They stay list items until Run 9 moves them into the table as
`THR-EP-GATEWAY`, `THR-EP-PLANE-CONFUSION`, `THR-EP-DOOR`, `THR-EP-ISOLATION` —
**no `|` inside a cell** (the parser drops the row silently). The residuals say:
Postgres sees the gateway's address (no per-client rule); a plaintext peer holds a
socket for the measured read deadline; a customer's password is the customer's
to keep (the operator can read the verifier, never the password).

**ADRs** (each indexed in `docs/decisions/README.md`): **0268** the public
Postgres port — the edge's entrypoint, the TLS option, label TCP routers to the
customer poolers, HTTP-01 per project, hostnames, the facility, the guards
moved, wake-on-connect not built (D2325–D2328, D2335–D2339, D2344, D2349–D2351);
**supersedes ADR 0044's *"there is no publication"* for the edge only** (a
project still publishes nothing; `publication()` still raises) and **amends ADR
0246 item 2** (the port is 5432). **0269** customer roles and their credentials
by verifier — the two roles, their grants, the customer poolers as the
allowlist, the budget claimants, the CLI-generated password (D2329–D2334,
D2354). **0270** a refusal proof proves the decision (D2340). **Amended**: ADR
0259 (`-n public`, D2333), ADR 0257 (a prepared slot's readers; the slot's three
records, D2341, D2335), ADR 0256 (one sentence: the unit does not order on the
control project's unit; `start()` waits, D2348).

### Run 2 — the debts: prepared slots, the claim, the mirror, the kit, the reconciler's start, the refusal proofs

**Code.** CI read by full SHA.

1. **D2341** — `src/agentic_postgres/capacity_probe.py` `read()` (`:215-321`):
   take the host manifest's declared slots (the caller passes them; grep every
   caller of `capacity_probe.read` first — `bin/deploy-project.py:2341-2358`,
   `bin/admit.py:162`, `bin/doctor.py:927`, the reconciler via `admit` — D979) and
   move a declared key with `bootstrap-state.json` and no `outputs.json` into a new
   `prepared` tuple; `capacity_reading.decide` (`:369-430`) names it on the
   committed line and does not refuse for it. `bin/control.py compare`
   (`:247-283`): the same key with no row reads `prepared`; `registry` (`:286-306`)
   accepts `{"agrees","deleted","prepared"}`; `OUTCOME_TEXT` (`:106-113`) gains it.
   **The storage observer** (find it from D2305's message, *"the storage route
   answered 404 rather than 401"*, in `bin/deploy-project.py`) skips when
   `storage.enabled` is false, printing *"storage disabled by the manifest … not
   observed"* (REST's sentence, D2172).
2. **D2345** — `bin/cloud.py project_claim` (`:621-652`) as §1 says.
3. **D2346** — if rig 39f says so, `--s3-no-head` in `mirror.sh:71-72` (the
   comment `:63-70` extended); `bin/backup.py verb_mirror` (`:703-795`) names a 403
   on both passes.
4. **D2347** — `dr_kit.plan_export` gains the optional policy artefact; `verify`
   checks its digest; the runbook §8 sentence (documentation, same commit).
5. **D2348** — `bin/reconciler.py start()` waits ≤ 180 s.
6. **D2340, ADR 0270** — `tests/deployment/test_session31_capacity.py:142-207`
   and `tests/external/test_session38_public_lifecycle.py` (`LIFECYCLE`
   `:58-67`, `:202-239`) rewritten as decision assertions. The lifecycle record
   gains `admission` (the JSON `admit.sh --json` printed for each resize) — **the
   Session 39 instrument writes it (Run 8)**. The rewritten tests **require** the
   member; Session 38's record has none and so fails them, which changes nothing
   (that claim already failed). No fallback to an envelope row.

**Battery** (§1 of CLAUDE.md): M1 a prepared slot left in `unreadable` (killed by
`test_a_prepared_slot_commits_nothing`); M2 `registry` without `prepared` in its
accepting set; M3 the claim choosing `created[0]`; M4 the decision test's `iff`
reduced to `if refused`; **control** for each: a test the mutation cannot reach,
green in the same invocation. Targeted: `test_capacity_probe`, `test_control_command`,
`test_control_cli`, `test_backup_command` (or the mirror's module — grep
`verb_mirror` in `tests/contract/`), `test_dr_kit`, `test_reconciler_dispatch`,
`test_acceptance_registry`, `test_evidence_claims`.

### Run 3 — the schemas: manifest 11, outputs 22, naming, isolation, the slot's manifest and DNS

**Code.** CI read by full SHA.

1. **Manifest 11** (D2337): `config.SUPPORTED_PROJECT_SCHEMA_VERSIONS` (`:64`) to
   11; `PROJECT_PUBLIC_ENDPOINTS_FROM = 11` beside `PROJECT_COMPUTE_FROM` (`:94`);
   `schemas/project.schema.json` enum (`:18-29`) and a v11 gate after the v10 gate
   (`:1051-1070`) forbidding `database.public_endpoints` below 11; the member
   `{enabled: boolean}` (additionalProperties false) under `database`; the control
   refusal in `config` with a named code (`CONTROL_PUBLIC_ENDPOINT`), message
   *"the control project's database has no public endpoint (ADR 0268)"*.
2. **Naming** (D2327, D2354): `naming.endpoint_hosts(domain) -> (pool, direct)`;
   `ROLE_SUFFIXES` (`:167-190`) gains `customer_app`, `customer_admin` **appended
   last**; two service names (`customer-pool`, `customer-direct`) and the two TCP
   router names derived like the HTTP ones (grep `router_name` in `naming.py`).
3. **Outputs 22** (D2349): `deployed_output.SCHEMA_VERSION` 22;
   `output_migrations.migrate_v21_to_v22` adds `database.public` = `{enabled:
   false, pooled: null, direct: null}`; `schemas/outputs.schema.json` (`deployedDatabase`
   `:792`) gains `public`; `build_deployed_document` (`:675-679`) fills it from the
   manifest and naming. `READABLE_PREVIOUS_VERSION` follows (`:846`) — **rig the
   version bump against the neighbour's OLD document** (Session 34's lesson):
   deploying alpha at 22 must read beta's 21.
4. **Isolation**: `ISOLATED_FIELDS` 18 → 20; `tests/deployment/isolation_matrix.py`
   `MUST_DIFFER` gains `database.public.*.host` and `database.public.*.user`,
   `MUST_MATCH` gains `database.public.*.port`, `…sslmode`, `database.public.enabled`
   is RELEASE_STATE or NOT_AUTHORITY (read `classify()` `:243-255` and choose by
   its rules; a D row if none fits).
5. **The slot** (D2335, D2337): `slot.slot_manifest` (`:112-180`) writes schema
   11 and `database.public_endpoints.enabled: true`; `slot.observe` reads
   `dns_reading` for the domain AND both endpoint hosts and is `ready` only when
   all three are True (the first False is the reason).

Targeted: `test_project_manifest`, `test_output_migrations`, `test_output_schema`,
`test_naming`, `test_isolation_leaves_offline`, `test_doctor_redaction`,
`test_slot_command`, `test_repository_contract`. Battery: M1 the v11 gate removed;
M2 the control refusal removed; M3 a public host classified MUST_MATCH; M4 `ready`
on the domain's record alone.

### Run 4 — the edge, the firewall and every publication guard (ADR 0268)

**Code.** CI read by full SHA. **One commit moves every guard §0 lists** (D2338).

1. `infra/edge/traefik.yaml` gains `postgres: {address: ":8432"}` with the read
   deadline rig 39a chose; `infra/edge/compose.yaml:135-137` gains `"5432:8432"`;
   `infra/edge/dynamic/baseline.yaml` gains `tls.options.postgres` exactly as rig
   39a ran it.
2. `require_edge_serves_this_release` (`bin/deploy-project.py:719-733`) requires
   the `postgres` entrypoint too; its refusal names `sudo bin/edge.sh --host
   host.yaml restart` (the existing sentence).
3. `infra/host/docker-user-rules.v4:37-40` and `.v6` admit NEW to 5432;
   `bin/provision-host.sh` ufw (`:1005-1007`) and the listener check (`:488-501`).
4. The tests and the external list as §2 *Existing entries that move*; DBX-005's
   text in the registry; `docs/database-connections.md` and
   `docs/operator-guide.md` §1's port sentence (documentation pages: run
   `test_documentation_index`).

Targeted: `test_edge_config`, `test_compose_contract`, `test_host_infrastructure`,
`test_deploy_command`, `test_port_allocator`, `test_listeners`,
`test_acceptance_registry`. Battery: M1 a sixth entrypoint; M2 the ALPN list
emptied; M3 the firewall admitting 6432; M4 the edge check reading only
`apgmetrics`.

### Run 5 — the database side: roles, budget, the customer poolers, their labels, the sync verb

**Code.** CI read by full SHA. The largest run; **commit at each numbered item
that leaves the suite green**, read CI once at the end.

1. **Roles** (D2332, D2354): `bootstrap_statements.build_statements` creates both
   NOLOGIN everywhere, adds them to the CONNECT list (`:156-161`), and the grants
   (only when the facility is enabled — the document says so); `bin/postgres-bootstrap.py`
   applies `LOGIN CONNECTION LIMIT n` **without `PASSWORD`** when enabled
   (`apply_connection_limit`'s shape plus LOGIN), `NOLOGIN` when not;
   `check_violations` reads attributes, grants and the absence of any grant on
   `app`, `api`, `app_private`.
2. **Budget** (D2334): the profile table (`services/auth-api/app/compute_profiles.py`)
   gains `customer_pool_connections`, `customer_direct_connections` from rig 39e;
   `config._validate_connection_budget` adds both when enabled;
   `postgres-bootstrap.connection_limits` subtracts them; `BUDGET_CLAIMANTS`
   widened by two under ADR 0269.
3. **The poolers** (D2328, D2329, D2344): two services in `compose.yaml` beside
   `pgbouncer`, image `${PGBOUNCER_IMAGE}`, `profiles: [public-endpoints]`,
   `user: "70:70"`, read_only, tmpfs `/etc/pgbouncer`, the ini rendered inline by
   the entrypoint as `pgbouncer`'s is (`:602-641`) with `auth_type =
   scram-sha-256`, `auth_file` = **a read-only bind of the userlist the sync verb
   writes**, `pool_mode` transaction / session, `max_db_connections` and
   `default_pool_size` = the claimant, `max_prepared_statements = 100`,
   `ignore_startup_parameters = extra_float_digits`; networks `edge` and
   `internal`; `mem_limit`/`pids_limit`/`cpus` from rig 39e and ADR 0244's rule;
   a healthcheck asserting the mode through the admin console as `pgbouncer`'s
   does. `bin/project-runtime.sh` adds `--profile public-endpoints` iff
   `APG_PUBLIC_ENDPOINTS=1` in the rendered `compose.env` (`rendering.build_compose_env`
   writes it).
4. **The labels** (D2328, D2335): `runtime_override._endpoint_labels` on
   `customer-pool` and `customer-direct` — `traefik.enable`, `apg.traefik.scope:
   managed`, `traefik.docker.network`, `traefik.tcp.routers.<r>.entrypoints:
   postgres`, `rule: HostSNI(\`<host>\`)`, `tls.options: postgres@file`,
   `tls.certresolver: ${ACME_RESOLVER_NAME:?required}`, `tls.domains[0].main/sans`
   (on `customer-pool`), `traefik.tcp.services.<s>.loadbalancer.server.port: 6432`
   — and, **only if rig 39b chose the fallback**, the HTTP router for the
   certificate.
5. **`bin/customer-credentials.sh` + `.py`** (root; one verb `sync --outputs O`):
   reads `SELECT rolname, rolpassword FROM pg_authid WHERE rolname IN (…)`
   through `container_exec.run` as `postgres`, writes each pooler's userlist
   (`"<role>" "<verifier>"`, or empty when NULL) to
   `/etc/agentic-postgres/projects/<key>/customer-poolers/{pool,direct}.userlist`
   (dir 0750 `root:70`, files 0640 `root:70`, written beside and renamed), then
   `docker kill -s HUP` both poolers by their derived container names. Exit 0 / 3
   (not root, no document) / 6 (the cluster or a pooler could not be reached). **A
   deploy step 6f** runs it for an enabled project after bootstrap (a restore or a
   branch then carries the credential). Never prints a verifier.

Targeted (fast): `test_bootstrap_statements`, `test_agent_plane_contract`,
`test_compute_profiles`, `test_project_manifest`, `test_compose_contract`,
`test_pooler_contract`, `test_endpoint_routes` (new), `test_cli_contract`,
`test_container_selectors`; (Docker, once before the commit)
`test_customer_roles_on_a_cluster` (new), `test_customer_poolers` (new). Battery:
M1 `customer_admin` granted CREATE on the database; M2 the pool's userlist naming
both roles; M3 a TCP router targeting `postgres`; M4 the budget term dropped; M5
the bootstrap setting a customer PASSWORD; **controls** green.

### Run 6 — the control plane: `0005`, the routes, `credential.rotate`, the snippets

**Code.** CI read by full SHA.

1. **`projects/control/migrations/templates/0005-control-endpoints.sql`** (D2351):
   `SET LOCAL ROLE {{object_owner}}`; `ALTER TABLE app.control_projects ADD COLUMN
   endpoints jsonb NULL`; `control_adopt_project` replaced to take the endpoints;
   `AP900` down; `bin/control.py adopt` and the reconciler's registry refresh pass
   `document["database"]["public"]` (grep every `control_adopt_project` caller);
   freeze; the proposal.
2. **Routes**: `GET /v1/projects/{key}/connections` (viewer; key scope
   `projects:read`) and `POST /v1/projects/{key}/credentials {role, verifier}`
   (member; **human session only** — absent from `KEY_SCOPES`); `MATRIX`,
   `PROJECT_WRITES`, `OPERATION_OF_ROUTE`; models; `bin/app-contract.sh --check`
   after regenerating the control snapshot.
3. **`credential.rotate`** (D2330): `schemas/operation-arguments.schema.json`
   branch `{role: enum [customer_app, customer_admin], verifier: pattern
   ^SCRAM-SHA-256\$4096:[A-Za-z0-9+/]{22}==\$[A-Za-z0-9+/]{43}=:[A-Za-z0-9+/]{43}=$}`;
   `RESULT_MEMBERS["credential.rotate"]` = common + `{role}`; `STEPS` = `check,
   alter, sync`; the handler in `bin/reconciler.py` (`slot_project` first; refuses
   a sleeping project with `could_not_determine`/`{"reason":"asleep"}`); `alter`
   runs `psql -U postgres -v role=… -v verifier=… -f -` with `ALTER ROLE
   :"role" PASSWORD :'verifier'` on stdin through `container_exec.run`; `sync`
   runs `bin/customer-credentials.sh sync`. `EXECUTED_TYPES` gains it;
   **`ACCEPTED_TYPES` stays empty until Run 9.**
4. **Snippets** (D2352): `services/auth-api/app/connection_snippets.py` for the
   clients rig 39c connected.

Targeted: `test_control_projects`, `test_control_roles` (or whatever holds
`MATRIX`), `test_operation_types`, `test_reality_ledger`, `test_reconciler_dispatch`,
`test_reconciler_claim`, `test_connection_snippets` (new), `test_app_contract_aggregate`,
`test_migration_lint` (the control set). Battery: M1 a key allowed to rotate; M2
the verifier pattern loosened to `.*`; M3 the verifier passed in argv; M4 a
snippet with a password member.

### Run 7 — the CLI: `bin/endpoint.sh` and the fixtures' TLS input

**Code.** CI read by full SHA.

1. `bin/endpoint.sh` (dispatch, `apg endpoint`) and the three verbs in
   `bin/cloud.py` (D2353): `credential` generates with `secrets.token_urlsafe(32)`,
   writes `--password-file` with `os.open(…, O_WRONLY|O_CREAT|O_EXCL, 0o600)`,
   refuses an existing file (exit 2), computes the verifier, posts it, and with
   `--wait` waits on the operation (`_wait` `:775`); `connect` writes a temporary
   `PGPASSFILE` 0600 and `exec`s `psql` with `sslmode=verify-full
   sslrootcert=system`; `show` prints the served metadata and the snippets.
2. The four fixture images accept `APG_SSLMODE` (D2350); `url.mjs:95` reads it;
   `test_client_fixtures.py` holds the default `disable`.

Targeted: `test_cli_contract`, `test_endpoint_cli` (new), `test_control_cli`,
`test_client_fixtures`. Battery: M1 the file opened without `O_EXCL`; M2 the
password included in the request body; M3 `connect` leaving the passfile.

### Run 8 — the trip's instruments, written and rehearsed offline

WSL `~/s39/run8/` (backed up to the scratchpad): **`s39-lifecycle.py`** from
`~/s38/run9/s38-lifecycle.py` — adds `credential` ×2 after `claim`, a `connect`
through both names (psql `select current_user`), a second rotation of
`customer_app` and the old password refused, `connect` while asleep refused, the
`admission` JSON per resize, the export's schema list read with `pg_restore
--list`; records `source_commit`. **`s39-endpoints.sh`** — the four driver images
built locally and run against a named project's public hosts with the credential
files (EP-LIVE-001's raw material, also the proof's helper). **`s39-dns.sh`** —
the three records per slot. **`s39-hostyaml.py`**, **`s39-e0.sh`**, the sweep's
launch script (refuses while the reconciler is *working*), the external script.
Rehearse every instrument against the planning rig's containers and a rendered
example — nothing touches the host. Commit only the `**Done.**`.

### Run 9 — the bump, the registry, the gate, the threat rows, the Ledger to `trial`, the documents

**Code.** `bin/session-01-check.sh` once and the new gate `--mode offline` once,
detached (CLAUDE.md §1), then CI.

- `CURRENT_SESSION = 39`, Session 39's paragraph in `__init__.py`; `VERSION`
  1.17.0; `README.md:7`; every `--session 38` / `--through-session 38` literal on
  the documented path (D678/D1484).
- The registry block (§2), `CLAIMS`, `OFFLINE_CLAIMS`, `CLAIM_INTRODUCED_IN`, the
  regex; the registry header `:16` corrected (D2355).
- **`bin/session-39-check.sh`** derived from 38's by diff; two flags;
  `test_session_thirty_nine_gate_modes.py` derived from 38's; the roster's two
  variables.
- **The Ledger** (D2343): the six managed-project rows → `trial` (evidence
  `lifecycle_retrial_live`; `customer_text` *"… being verified"*); `pooled_endpoint`
  and `direct_endpoint` → `trial` (evidence `public_endpoints_live`,
  `public_port_scan`); `wake_on_connect` `target_session: null` and its text
  (D2336); `postgresql` stays `planned` until the close; **`ACCEPTED_TYPES` = the
  six + `credential.rotate`**; `docs/reality-ledger.md` rendered (`--write`).
- `THR-*` rows from Run 1's list; `docs/operator-guide.md` **§21 Public endpoints**
  (the facility, the edge sheet, the firewall, the sync verb, a customer's
  rotation) and §20's slot sheet with three records; `docs/database-connections.md`
  a customer section; ADR 0256's sentence (D2355).

### Run 10 — sitting 1 (day 1): the firewall, the edge, the release, two slots

The agent: bundle + `scp` + checkout on the host (`git rev-parse FETCH_HEAD`),
`uv` sync, renders; then the sheets in order, **each read before the next**:
**E0** (if not already run) → **P1** → **F1** → **E1** (probe running on all
three; the window recorded) → **R1** → reconciler stopped → **R2a/b/c** →
**A1** → **RC1** (restart; `status` *idle*) → **H1** → **SL1** (both slots, one
credential placement) → **SL2** ×2 → `s39-dns.sh` → **SL3** (`slot2-prod ready`,
`slot3-prod prepared`) → **K1** → **V1** (`-k`, writing nothing). **Stop** if
R1 prices `major` or for a reason this plan did not name, if F1's `--check`
reports anything but the firewall, or if E1's edge does not come back healthy.

### Run 11 — sitting 2 (day 2): the lifecycle, slot3, the reboot, the sweep, the tag

1. **The lifecycle on `slot2-prod`** (`s39-lifecycle.py`, the probe on alpha,
   beta, control and the slot): create `small` → claim → `credential` app and
   admin → `connect` both names → rotate app, old refused → sleep (both names
   refused, the routes 404) → wake → resize `standard` → resize `large` (decided
   by the reading) → export (three schemas) → K2 → delete → second create →
   `409 capacity_exhausted {reason: no_slot}`, no row.
2. **Sheet P2** — `slot3-prod`'s three grey A records; `s39-dns.sh`; **SL3'**
   (`slot3-prod ready`).
3. Create `slot3-prod` (`small`) → claim → `credential` app and admin into
   `~/s39/run11/creds/slot3-prod/` (0700/0600) → `s39-endpoints.sh slot3-prod`
   once (all four drivers) → **K3**.
4. **A1'** (`agrees` ×3, `slot2-prod agrees (deleted)`, `slot3-prod agrees`) →
   **B1** (the reboot; five units + the reconciler `NRestarts` 0 + `slot3-prod`'s
   unit; `s39-endpoints.sh` psql only, through both names, before the sweep) →
   **S1** (the sweep) → external (`--customer-credential-dir`, the lifecycle
   record) → merge (expected §7) → **tag `1.17.0`** from the workstation → **SL4**
   (`slot2-prod` revoked; the repository's listing read).

### Run 12 — the close

**Code** — `bin/session-01-check.sh` once and CI.

- **The Ledger**: each `trial` row → `beta` if every named claim reads `passed`
  in `evidence/session-39.json`, else → `planned` with its types removed from
  `ACCEPTED_TYPES` and the Done saying why; `management_api` → `beta` iff
  `control_plane_live` passed (D2322); `postgresql` → `beta` iff
  `public_endpoints_live` passed.
- **`capacity.ENVELOPE`**: the EDGE class on OVH (E1); a credential rotation's
  time; a TLS connect's time through each name; `slot2-prod`'s lifecycle rows;
  the resize window **as the slot's own route saw it** (D2324's `UNMEASURED` row
  closed if the probe measured it); memory with `slot3-prod` live. A Session 39
  section comment (D2355's sibling: 38's rows have none).
- `docs/scope-closure.md` **§32**; the stage plan's Status block; CLAUDE.md §2
  rewritten for Session 40's planner (copy it to the scratchpad first); this
  plan's `Status:` COMPLETE.

---

## 7. Evidence and claims

**Expected at the merge** (Run 11): **253 claims** (101 offline). **`failed` 1:
`documented_path`** (D1935). Everything else **passed** — including the seven
that failed at Session 38: `admission_live` and `lifecycle_operations_live` under
ADR 0270, `control_plane_live`, `reconciler_live`, `restore_isolation`,
`lifecycle_project_door_live` with the Run 13 repairs, run in a sweep for the
first time. **Exit 5 for `documented_path` and no other reason.** Predictions,
each moved only by the evidence.

**The three modes.** Offline: CI's artifact for the deployed SHA (101 claims).
Host: S1 with `--lifecycle-record-file`, `--slot-outputs` (`slot2-prod`) and
`--live-slot-outputs` (`slot3-prod`). External: from WSL, with
`--control-outputs`, `--control-probe-file`, `--lifecycle-record-file` and
`--customer-credential-dir`; **the Session 39 customer proofs reach only
`routes.control`, the slot's recorded `routes.app` and the public names on 5432,
and open no SSH** (`test_this_module_uses_no_ssh` holds the module's text).
Deploy every project fully, THEN run the lifecycle, THEN sweep.

---

## 8. Security invariants this session touches

| Invariant | How this session keeps it |
|---|---|
| **The public Postgres port accepts only TLS, routed by name** | The `postgres` TLS option; label routers by `HostSNI`; plaintext, wrong SNI and no SNI refused (EP-LIVE-002) |
| **The public door admits only customer roles** | Customer-only poolers whose userlists name one role each; the database and the platform pooler unrouted (EP-POOL-001, EP-LIVE-001, EP-LIVE-003) |
| **A customer role never reaches `app_private`** | Grants and a negative test per schema (EP-ROLE-001, EP-LIVE-001) |
| **The control plane holds nothing that opens a project's data** | It holds a verifier, never a password; the password never leaves the workstation (EP-CRED-001) |
| **A credential shown to a customer is shown once and stored hashed** | Written once to the customer's own 0600 file; stored only as a SCRAM verifier in `pg_authid` and the userlists |
| **The reconciler runs only a closed set of typed operations** | `credential.rotate`'s two members, schema-validated twice; the verifier on stdin, never argv (EP-CRED-001) |
| **A product surface runs no SQL** | `bin/endpoint.sh connect` execs the customer's own `psql` with the customer's credential; nothing in `/v1` takes SQL |
| **Projects share no project-scoped value** | `ISOLATED_FIELDS` 20; the slot's document compared with A, B, control (EP-LIVE-003) |
| **No URL, key, token or caller value in a log line** | No verifier, password or URL with a password is printed by the CLI, the reconciler or the sync verb |
| **Nothing `planned` has a control** | `wake_on_connect` planned and unbuilt; `trial` resolved at the close |
| **A report may not substitute an answer for a failure to determine one** | `prepared` is a named outcome; `sync` exits 6 when it cannot read; `connections` 409 when unrecorded |

---

## 9. Stop conditions

Stop and ask the operator, without improvising, when:

- rig 39a, 39c or 39d contradicts the planning rig (a driver that the door must
  serve cannot connect; the pass-through control does not refuse);
- rig 39b issues no certificate by either path;
- a guard would have to move to a set other than `{80, 443, 5432}`, or
  `publication()` would have to stop raising;
- the customer door would need `postgres` or the platform `pgbouncer` on `edge`,
  an `hba_file`, or a platform role in a customer userlist;
- a customer role would need anything on `app`, `api`, `app_private`, `CREATE`
  on the database, or a role attribute;
- a customer password would have to exist on the host, in the control database,
  in an argv or in a log;
- `upgrade plan` prices 1.17.0 at `major`, or for a reason this plan did not name;
- `provision-host.sh --check` reports a violation other than the firewall's;
- the edge does not come back healthy after E1, or a certificate is not issued on
  a creation's first deploy;
- a `trial` row would outlive the close, or a row would move to `beta` without its
  claims `passed`;
- a currently-passing test would be weakened to make a new one pass;
- `--render-only` stops working with no host and no root.

---

## 10. Open items this session carries and creates

**Carried, untouched, each still true:** the OVH upgrade — **owed before
Session 41** (D2342); beta's three rotations (D1995); D1936/D2005; D1547;
D2020/D2025; D2031; D1642, D1798, D1869, D1871, D1722/D1806, D1784, D1792, ADR
0241's bound; D1045; D1375; D976; D688; D771; D340; D466; D540; D942; D1203;
D1205; D1211; the 24 unclaimed requirements; `process-max` 1 (D593);
`documented_path` (D1935); accounts never deleted (D2065, D1986); TOTP seeds
plaintext (ADR 0252); `/v1/sessions` unthrottled (D2166); the reconciler and the
operator serialised by a rule, not a lock (D2178); a slot's provider resources
outlive it (D2181); the export URL crosses the control database (ADR 0259);
`storage.enabled: false` still emits storage's router (D2144); a sleeping
project's doctor and backups unread (D2182); `materialize-secrets` has no
last-known-good fallback; M7's X1/X2 (Hetzner), not before 2026-10-12 ~21:30Z.

**Created, and named so Session 40 does not inherit them silently:**

- **`secret_required_added` cannot fire** (D2331): the next session that adds a
  required secret prices it at patch unless the reader is repaired first.
- **Postgres sees the gateway's address** (D2325): no per-client rule; a
  customer cannot allowlist addresses.
- **Channel binding is not offered** through the terminating gateway (D2325).
- **A plaintext peer holds a socket** for the measured read deadline (D2326).
- **A customer's verifier lives in two places** (`pg_authid` and the userlists);
  `sync` is the one writer of the second and a deploy re-syncs. A branch (40)
  restored from the parent carries the parent's verifiers — **Session 40's
  re-key must rotate both customer roles** before the branch's names open.
- **`slot3-prod` is the only live customer project** and Session 40's branch
  parent; no slot is free after it.

---

## Appendix — what to consult, how a run is executed here, and the sheets

**Consult, in this order:** CLAUDE.md §1 (the shell traps); this plan's §0, §1
and the run's own text; the reads its run names. **The tree wins.**

**How a run is executed here**: CLAUDE.md §5. Every `sudo` line is the
operator's, on a sheet, under `script -q -e -c '…' /home/op/s39-<sheet>.txt` when
it execs into a container or deploys (D972, D1501), never piped or redirected;
`sudo -v` in the foreground first (D1376). Every `op` line is the agent's over
SSH; remote loops in a script file with `PATH="$HOME/.local/bin:$PATH"` exported.
**`<sha>` is never typed on a sheet**: the agent fills it from `git rev-parse
HEAD` on the host before handing the sheet. **Before any sheet that deploys,
retires, restores or recreates the edge: `sudo systemctl stop
agentic-postgres-reconciler`, and `start` after** (D2178). **Read `--help` of
every command on a sheet before handing it** and correct the line to it.

### Sheet E0 — readings before anything is built (Run 1; reads only)

```
sudo -v
sudo bash /home/op/s39-e0.sh      # tees /home/op/s39-e0.txt; changes nothing
```

### Sheet P1 — the consoles (any day before Run 10's SL1)

1. **Cloudflare DNS**, **DNS only**, no AAAA: `A slot2.agenticpostgresql.com`,
   `A pool.slot2.agenticpostgresql.com`, `A direct.slot2.agenticpostgresql.com`
   → `15.204.231.45`. **Do NOT create `slot3`'s records yet** (D2342).
2. **Cloudflare R2**: buckets `apg-slot2-prod`, `apg-slot2-prod-backup`,
   `apg-slot3-prod`, `apg-slot3-prod-backup`, in alpha's location; four Account
   API tokens, *Object Read & Write*, one per bucket. **Never paste them into the
   conversation.**
3. **Backblaze B2**: `apg-slot2-prod-backup-mirror` and
   `apg-slot3-prod-backup-mirror`, an application key scoped to each.
4. Tell the agent 1–3 are done and the two mirror bucket names.

### Sheet F1 — the firewall (Run 10, day 1)

```
sudo bin/provision-host.sh --check      # (flags corrected from --help on E0) expected exit 6: the firewall only
sudo bin/provision-host.sh --apply
sudo iptables -S DOCKER-USER | grep -- '--ctorigdstport'     # 80, 443, 5432
```

### Sheet E1 — the edge, recreated once (Run 10, day 1; announced)

```
sudo systemctl stop agentic-postgres-reconciler
sudo bin/edge.sh --host host.yaml restart          # the agent's probe runs on all three projects
sudo bin/edge.sh --host host.yaml status
```

### Sheet R1 — the release priced (Run 10, day 1)

```
sudo bin/upgrade.sh plan --project alpha-dev    --candidate .generated/alpha-dev/outputs.json    --also document_schema_migratable --also api_operation_added --json
sudo bin/upgrade.sh plan --project beta-dev     --candidate .generated/beta-dev/outputs.json     --also document_schema_migratable --also api_operation_added --json
sudo bin/upgrade.sh plan --project control-prod --candidate .generated/control-prod/outputs.json --also document_schema_migratable --also api_operation_added --json
```

### Sheets R2a / R2b / R2c — 1.17.0 deployed (Run 10, day 1)

```
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project project.alpha.yaml   --capabilities capabilities.yaml --through-session 39' /home/op/s39-r2-alpha.txt
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project project.beta.yaml    --capabilities capabilities.yaml --through-session 39' /home/op/s39-r2-beta.txt
script -q -e -c 'sudo ./deploy.sh --host host.yaml --project /home/op/control.yaml --capabilities capabilities.yaml --through-session 39' /home/op/s39-r2-control.txt
```

### Sheet A1 — the registry after the last deploy (Run 10, day 1)

```
sudo bin/control.sh adopt --project alpha-dev    --organization 10234b92-b2d7-4573-bebb-f012ce5c8f02 --confirm control-prod
sudo bin/control.sh adopt --project beta-dev     --organization 10234b92-b2d7-4573-bebb-f012ce5c8f02 --confirm control-prod
sudo bin/control.sh adopt --project control-prod --organization 10234b92-b2d7-4573-bebb-f012ce5c8f02 --confirm control-prod
sudo bin/control.sh registry                     # agrees x3, slot1-prod agrees (deleted); exit 0
```

### Sheet RC1 — the reconciler back (Run 10, day 1)

```
sudo systemctl start agentic-postgres-reconciler
sudo bin/reconciler.sh status                    # idle
```

### Sheet H1 — two slots declared (Run 10, day 1)

```
sudo install -o op -g op -m 0600 /etc/agentic-postgres/host.yaml /home/op/etc-host.yaml
#   the agent runs s39-hostyaml.py on both copies (slots.declared += slot2-prod, slot3-prod) and prints the diffs; read them, then:
sudo install -o root -g root -m 0600 /home/op/etc-host.yaml.slots /etc/agentic-postgres/host.yaml
```

### Sheet SL1 — both slots' providers (Run 10, day 1; one credential placement)

```
sudo bin/slot.sh prepare --host host.yaml --slot slot2-prod
sudo bin/slot.sh prepare --host host.yaml --slot slot3-prod
sudo bin/bootstrap-providers.sh --host host.yaml --project /etc/agentic-postgres/slots/slot2-prod/manifest.yaml --plan
sudo bin/bootstrap-providers.sh --host host.yaml --project /etc/agentic-postgres/slots/slot3-prod/manifest.yaml --plan
#   YOU: place the control-plane credential (two lines: client id, client secret):
sudo install -d -m 0700 /root/.config/agentic-postgres/bootstrap
sudo nano /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo chmod 0600 /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo bin/bootstrap-providers.sh --host host.yaml --project /etc/agentic-postgres/slots/slot2-prod/manifest.yaml --apply \
     --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo bin/bootstrap-providers.sh --host host.yaml --project /etc/agentic-postgres/slots/slot3-prod/manifest.yaml --apply \
     --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo shred -u /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo ls -la /root/.config/agentic-postgres/bootstrap/      # empty, no nano .save copy (D2061)
#   YOU: in Infisical, projects `slot2-prod` and `slot3-prod`, environment `dev`:
#   the storage pair at /storage (create the folder), the backup pair at /backup,
#   the mirror pair at /backup -- each into the EXISTING key if --apply made it, else a new key.
```

### Sheet SL2 — materialized (Run 10, day 1)

```
sudo bin/materialize-secrets.sh --project /etc/agentic-postgres/slots/slot2-prod/manifest.yaml --requirements secrets.required.yaml --session 39
sudo bin/materialize-secrets.sh --project /etc/agentic-postgres/slots/slot3-prod/manifest.yaml --requirements secrets.required.yaml --session 39
```

### Sheet SL3 — the slots read (Run 10, day 1)

```
#   the agent has run s39-dns.sh: slot2-prod's three records exit 0; slot3-prod's absent (expected)
sudo bin/slot.sh status --host host.yaml         # slot2-prod ready; slot3-prod prepared (no DNS)
sudo bin/control.sh registry                     # ... slot3-prod prepared (slot); exit 0 (D2341)
```

### Sheet K1 — the kit and the copies (Run 10, day 1)

```
sudo bin/dr-kit.sh export --host host.yaml --capabilities capabilities.yaml \
     --project project.alpha.yaml --project project.beta.yaml --project /home/op/control.yaml \
     --output /home/op/kit-<today>-s39
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/outputs.json    /home/op/alpha-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/beta-dev/outputs.json     /home/op/beta-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/control-prod/outputs.json /home/op/control-prod-outputs.json
```

### Sheet V1 — the day verified, writing nothing (Run 10, day 1)

```
sudo bash /home/op/s39-v1.sh       # the sweep's declarations without --after-reboot and the slot flags; -k
```

### Sheet P2 — slot3's records (Run 11, day 2, after the second creation was refused)

1. **Cloudflare DNS**, **DNS only**, no AAAA: `A slot3.agenticpostgresql.com`,
   `A pool.slot3.agenticpostgresql.com`, `A direct.slot3.agenticpostgresql.com`
   → `15.204.231.45`.
2. Tell the agent; it runs `s39-dns.sh slot3-prod`, then:

```
sudo bin/slot.sh status --host host.yaml         # slot3-prod ready
```

### Sheet K2 — slot2's document, before its deletion (Run 11, day 2)

```
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/slot2-prod/outputs.json /home/op/slot2-prod-outputs.json
```

### Sheet K3 — slot3's document (Run 11, day 2, after its creation)

```
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/slot3-prod/outputs.json /home/op/slot3-prod-outputs.json
```

### Sheet A1' — the registry after the lifecycle (Run 11, day 2)

```
sudo bin/control.sh registry                     # agrees x3, slot2-prod agrees (deleted), slot3-prod agrees; exit 0
```

### Sheet B1 — the reboot (Run 11, day 2)

```
sudo systemctl reboot
```

### Sheet S1 — the one sweep (Run 11, day 2)

```
sudo -v
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/alpha-dev/outputs.json    /home/op/alpha-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/beta-dev/outputs.json     /home/op/beta-dev-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/control-prod/outputs.json /home/op/control-prod-outputs.json
sudo install -o op -g op -m 0600 /etc/agentic-postgres/projects/slot3-prod/outputs.json   /home/op/slot3-prod-outputs.json
sudo bash /home/op/s39-launch.sh      # refuses while the reconciler is working; detaches s39-sweep.sh
```

### Sheet SL4 — slot2's identity revoked (Run 11, day 2, after the tag)

```
#   YOU: place the control-plane credential as on SL1, then:
sudo bin/slot.sh revoke --host host.yaml --slot slot2-prod --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential --confirm slot2-prod
sudo shred -u /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
sudo ls -la /root/.config/agentic-postgres/bootstrap/      # empty
```
