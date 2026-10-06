# 0251 — The control plane is a project: `control-prod`, its own set, and a fourth app mode of its `auth` container

- **Status:** Accepted
- **Date:** 2026-10-04
- **Session:** 37, Run 1 (D2043–D2049, D2059, D2068, D2073–D2079)
- **Affects:** `CTL-SET-001`, `CTL-API-001`, `CTL-REG-001`, `CTL-REG-002`
  (registered by Run 9). `services/auth-api/app/main.py` and `settings.py`
  (`APP_MODES` gains `control`), `compose.yaml` (`APP_MODE` interpolated),
  `schemas/project.schema.json` (schema 9, `control`), `src/agentic_postgres/config.py`,
  `src/agentic_postgres/deployed_output.py` (outputs 20), `rendering.py`,
  `naming.py` (`CONTROL_PATH_SUFFIX`, `route_control`, the control router),
  `runtime_override.py` (the control router and the app router's negation),
  `migrations.lint_project_set` (`control=`), `projects/control/`,
  `project.control.example.yaml`, `bin/control.sh` / `bin/control.py`.
- **Related:** ADR 0246 (the hosted boundary and its sentence that the control
  plane holds no credential that opens a project), ADR 0185 (superseded in part
  — for the control plane only), ADR 0198 and 0206 (a project's own migration
  set), ADR 0218 (`container_exec.run` for new code), ADR 0158 (the deployed
  document is the address book), ADR 0241 (a reader reads its own outputs
  version and the one before it), ADR 0162 (what a bump permits), ADR 0252,
  0253, 0254 (the accounts, the keys and the guard this plane carries),
  `docs/plans/stage-5-plan.md` D1950.

## Context

Stage 5's plan (D1950) makes the control plane a Python project the product
deploys, with a fourth `APP_MODE` of the auth image serving `/api/v1`, its own
migration set under `projects/control/`, and an authoritative `projects` table
in place of ADR 0185's read-only inventory for the control plane's purposes.
Session 37's planner read the tree against that sentence and found that a mode
is not a container: each existing mode (`auth`, `storage`, `mcp`) runs in a
container of its own, and the private signing key, the identity registry's
write functions (`app_private.auth_create_user` is granted to `auth_service`
alone, migration 0012) and the login all live in the `auth` container.

Run 1's rigs measured what the design rests on:

- **37b** — the control tables' row security under FORCE, on a development
  database of the release's 39 migrations. A policy on `app.control_memberships`
  that reads `app.control_memberships` raises `42P17 infinite recursion
  detected in policy for relation "control_memberships"` at call time from a
  PL/pgSQL function, and at `CREATE FUNCTION` time from a `LANGUAGE sql` one
  (the control). Design G — memberships visible where `user_id =
  app.current_user_id()` or `org_id::text = current_setting('app.control_org',
  true)`, organisations visible through the caller's memberships, and each
  definer function reading the caller's own membership row before it sets
  `app.control_org` — returned the organisation's three members to a member,
  **zero rows** to a non-member with the setting left empty, zero rows to a
  non-member who preset the setting to the foreign organisation, and the
  caller's own organisation only from the organisations list. Two further
  facts: **the setting survives the function's return** for the rest of the
  transaction, with or without a `SET` clause on the function (D2074); and
  **`auth_service` has no `USAGE` on schema `app`** — every call failed
  `permission denied for schema app` until the rig granted it (D2073). With the
  grant, `auth_service` reading a control table directly was still refused
  (`permission denied for table control_memberships`), and the `authenticated`
  role could not name the function at all.
- **37d** — Traefik v3.7 at the pinned digest
  (`sha256:9c3b91d5…dcb2ac`), a file provider, two echo backends. With the app
  router's rule ending `&& !PathPrefix(`/api/app/v1`)`, `/api/app/v1/organizations`
  and `/api/app/v1` answered Traefik's own `404 page not found`, while
  `/api/app/auth/me` reached the app backend as `/auth/me` and
  `/api/v1/organizations` reached the control backend as `/v1/organizations`.
  The control: without the negation, `/api/app/v1/organizations` reached the
  app backend as `/v1/organizations` — a second address for the same handler.
  But `!PathPrefix(`/api/app/v1`)` also hid `/api/app/v1x` (a string prefix);
  the form `!(Path(`/api/app/v1`) || PathPrefix(`/api/app/v1/`))` hid exactly
  `/api/app/v1` and below and passed `/api/app/v1x` to the app (D2075).
- **37e** — a draft control project rendered in a throwaway worktree:
  `--render-only` exits 0 for a set with **no `contracts/` directory**; a
  disabled REST or storage block must carry `allowed_cors_origins: []` and a
  `null` storage `account_id` (the schema refused the first draft); the R2
  storage pair is owed with storage disabled (it carries no facility); the
  `api_documentation` ceiling over the release vocabulary is exactly
  `["meta:read"]`; the only HTTP path anything requests of an auth container
  is `{routes.app}/auth/me` (the deploy's `observe_app`) beside the health
  routes, and the verification key set is a file read through `/proc`, never
  a route (D2076–D2079).

## Decision

**The control plane is the project `control-prod`** (slug `control`,
environment `prod`, domain `control.agenticpostgresql.com`, manifest at
`/home/op/control.yaml`, never in the checkout — the operator's answers of
2026-10-04, D2071). It is deployed, backed up, mirrored, kitted and swept like
every project.

1. **A fourth app mode, run by the control project's existing `auth`
   container** (D2043). `APP_MODES` gains `control`; `compose.yaml`'s literal
   `APP_MODE: auth` becomes `${AUTH_APP_MODE:?required}`, rendered `control`
   where the manifest enables the facility and `auth` everywhere else, so
   `alpha-dev` and `beta-dev` render the value they run today. The environment
   is auth's exactly. In `control` mode the container serves **`/health/live`,
   `/health/ready`, `/auth/me` and `/v1/*` — and nothing else**: no
   `/auth/login` (the login is `POST /v1/sessions`, which enforces the second
   factor, ADR 0252), no `/auth/jwks.json` route (nothing requests one, D2079),
   no `/admin/*`, no workflow or connector route, and **no worker** (the
   lifespan's auth-only branch is not taken). One process stays the issuer,
   the verifier and the control plane: no second holder of the private key, no
   second pool, no new role, secret, network or volume.
2. **Project manifest schema 9 adds `control: {enabled: boolean}`** (D2044) —
   optional, forbidden below 9, absent meaning off, the connectors facility's
   shape. One control project per host is assumed and not enforced by the
   schema; `bin/control.sh` refuses to choose between two (exit 5). Session
   38's `compute` becomes schema 10.
3. **Outputs schema 20 adds `routes.control`** =
   `https://{domain}{api.public_base_path}/v1`, named for every project and
   observed `ready` on the deployed branch only where the facility is on — the
   storage route's honesty (D326) — and the document records `control:
   {enabled}`, so a reader finds the control project from documents alone
   (D2045). ADR 0241's bound reads 20 and 19.
4. **The control set is `projects/control/`, linted like every set, with two
   widenings and no third** (D2046, D2073). A set whose project enables the
   `control` facility may name `{{auth_service}}` in exactly two statement
   forms: `GRANT EXECUTE ON FUNCTION app.<name>(…) TO {{auth_service}}` and
   `GRANT USAGE ON SCHEMA app TO {{auth_service}}`. Every other set is refused
   both, and a control set naming `{{auth_service}}` anywhere else is refused.
   **The second form is the operator's decision of 2026-10-04**, taken when
   rig 37b found the first insufficient: without `USAGE` the role cannot name
   a function in `app` however it is granted. What the grant gives
   `auth_service`, measured: the ability to name objects in `app` in the
   control project's database only; execution of functions granted to it and
   of the one release function `app` leaves PUBLIC-executable
   (`app.current_user_id()`, which reads the caller's own setting); no table.
   The set still never names `app_private`: invitation acceptance composes
   `app_private.auth_create_user(…)` and `app.control_accept_invitation(…)` in
   Python, on one `auth_service` connection, in one transaction.
5. **Design G** (D2047, D2074). Every control table is in `app` with FORCE row
   security and policies `TO {{object_owner}}` scoped by the caller:
   `app.current_user_id()` (set by the control mode with
   `set_config('app.user_id', …, true)` at the top of each request's
   transaction) and, for an organisation's rows, `app.control_org` — set by a
   definer function **only after it has read the caller's own membership row**,
   and **reset to empty as every control function's first statement**, because
   the setting outlives the function that set it. Every control function is
   `SECURITY DEFINER`, owned by `{{object_owner}}`, `SET search_path =
   pg_catalog, pg_temp`, revoked from `PUBLIC` and granted to
   `{{auth_service}}` alone — never in `api`, so the control project's
   PostgREST publishes nothing and its agent vocabulary gains nothing — except
   `app.control_adopt_project` and `app.control_totp_reset`, granted to
   nobody and reached by root (item 8). Tables in Session 37:
   `control_accounts`, `control_organizations`, `control_memberships`,
   `control_invitations`, `control_totp`, `control_keys`, `control_projects`,
   `control_operations`. `regions` is Session 38's and `notifications` 41's.
6. **No PostgREST contract** (D2048, D2076). The render passes a set with no
   `contracts/` directory, and every reader of a project's surface is
   conditioned on `mcp.capabilities` or on `propose`, neither of which the
   control project uses; the control manifest carries no
   `migrations.approvals_required`. If Run 10's deploy refuses for want of the
   contract, the reader that refuses is widened to accept a set that creates
   no `api` object, with a stricter test beside it — never a decoy contract.
   **It did** (Session 37 Run 10, D2136): the deploy's proposal gate (ADR 0243)
   refused the control set's three pending versions for want of a proposal,
   and `propose` needed the contract. `propose` now records an EMPTY surface
   for a set whose final `api` holds no function, view or enum, and still
   refuses a set that publishes anything without its contract; the control
   set's proposal is committed beside it like any project's.
7. **Accounts are `api_documentation` users holding `["meta:read"]`** (D2049,
   D2078) — the narrowest authority the identity registry can describe, reading
   no row of the control project's own data plane. The control manifest sets
   `api.rest.enabled: false` and `storage.enabled: false` (with empty origin
   lists and a null account id) and names no `mcp.capabilities`; `mcp` stays
   rendered, because it has no switch, and no agent is created on the control
   project. The R2 storage pair is still owed (D2077), so the operator creates
   the storage bucket and its token like any project's.
8. **The control router, and no second address** (D2059, D2075). A router
   `apg-<key>-control` with ``Host(…) && (Path(`{api}/v1`) ||
   PathPrefix(`{api}/v1/`))`` and a strip of `{api}`, so the application sees
   `/v1/…`, carrying the app router's baseline chain and buffering; and, only
   where the facility is on, the app router's rule gains
   ``&& !(Path(`{api}/app/v1`) || PathPrefix(`{api}/app/v1/`))``. Run 2
   renders the strings 37d measured.
9. **The registry is the control plane's own record, written by root**
   (D2068). `bin/control.sh` (root): `adopt --project KEY --organization ORG
   --confirm control-prod` reads KEY's deployed document and writes
   `app.control_projects` through `app.control_adopt_project(…)` with `docker
   exec … psql -U postgres` through `container_exec.run`, the arguments as
   `psql -v` variables; `registry [--json]` reports, per project, `agrees`,
   `differs: <field>` or `could not determine: <reason>` and exits 0, 5 or 6
   (ADR 0195); `totp-reset --username NAME --confirm control-prod` disables one
   factor. The control project is found by the `control.enabled` member of its
   deployed document, never by its name. **ADR 0185 is superseded for the
   control plane by this registry, and stands for everything else**: `fleet.sh`
   stays a read over documents, and no route lets a customer adopt a project.

## Alternatives rejected

- **A new `control` container.** Minting a login token there needs the signing
  key — a second issuer — or leaves the login in `auth`, where the second factor
  would then live and change every project's login.
- **The control tables as released migrations in `app_private`.** Every project
  would carry the control plane's schema, and alpha and beta would hold empty
  tables describing customers they do not have.
- **The `/v1` routes in `auth` mode.** Every project would serve the management
  API.
- **Owner-wide policies with every check in the function bodies (design T).**
  Rig 37b showed design G scopes a member's reads in the database itself, so the
  final authority stays PostgreSQL's (stage plan §8); T would move it into code.
- **A released migration granting `USAGE ON SCHEMA app` to `auth_service` on
  every project**, and **the control functions in `public`** (where the role
  already has `USAGE`). The first moves both production databases and adds a
  released migration for a privilege only the control project uses; the second
  puts the control plane in the schema every role can name, guarded by nothing
  but a `REVOKE` beside each function. The operator chose the facility-gated
  grant.
- **`!PathPrefix(`{api}/app/v1`)` alone.** Measured to hide `/api/app/v1x` as
  well.

## Consequences

- The control project is **the platform's single point of failure** (stage plan
  §10). Its backup and schedule are owed from its first day (D2062), every kit
  names it (D2069), and its unit is enabled by the operator on day one, because
  no command enables a project unit (D2060).
- `alpha-dev` and `beta-dev` render `AUTH_APP_MODE=auth`; the interpolation
  moves their `auth` definition, so a deploy of the release recreates their
  `auth` container — which a new commit does anyway (D2034).
- A `GRANT USAGE ON SCHEMA app` in a control set makes every function the set
  creates in `app` callable by `auth_service` unless it is revoked from
  `PUBLIC`, because default privileges do not cover functions here (migration
  0001, D57). The set's test asserts the exact executable set for every role.
- One more widening of the lint would be a third form; that is a stop, not a
  run's call.
