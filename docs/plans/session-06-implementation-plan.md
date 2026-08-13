# Session 6 implementation plan — the auth service and a real claim contract

> **Source runbook:** `session-06-auth-service-asymmetric-jwts-runbook-audited.md`.
> **This document is not that document.** The runbook was written against a
> repository where Sessions 1–5 had been implemented exactly as *their* runbooks
> described. They were not. Sessions 1–5 produced 74 ADRs and 214 recorded
> divergences, and roughly half of the runbook's claims about "what Session 6
> inherits" are claims about a system that does not exist here.
>
> §1 is the point of this document. Everything else is downstream of it.

**What Session 6 does, in one sentence:** replace the root-only bootstrap token
issuer with a FastAPI service that owns the only private signing key, stores only
Argon2id hashes, derives every role and scope from server-side records, and makes
a human's current state authoritative for a PostgREST request.

**What it must not do:** reinterpret an inherited contract silently. That is
CLAUDE.md §5's rule and it is the reason this file exists.

---

## 0. Where Session 6 actually starts

Not from a green Session 5. From a Session 5 that is **green except its rotation
window**, and that difference is the first thing to plan around.

```
HEAD               7a8c68d, clean, in sync with origin/main
gate               offline PASSED · host PASSED (168/0/6) · external PASSED (20/0/8)
claims             16 of 18 proved
unproved           api_authorization, bootstrap_identity  — three rotation node
                   IDs and one reboot node ID have never run
outputs schema     v8
migrations         10 released
ADRs               74 · divergences D1…D214
Session 6 owns     ADR 0075 onward, D215 onward, migrations 0011 onward,
                   outputs v9
```

**Session 6's Run 1 is Session 5's rotation window.** The runbook opens with
"run the complete Session 5 gate once and record its immutable evidence
checksum". Two things are wrong with that here. Evidence is **gitignored by
design** (runbook §6.1 of Session 1; `evidence/*` is generated, never committed),
so there is no immutable checksum to record — the artifact is reproduced, not
retained. And the Session 5 gate does not currently come back fully proved: two
claims are `failed` because their proofs have never executed.

Running the rotation window first is not tidiness -- but the reason it was
written with is wrong, and measuring it is what Run 1 did first. There is no
prepare/promote/retire machinery to exercise: `begin_rotation` and
`complete_rotation` have no callers, the JWKS renderer publishes exactly one key,
and the deploy writes `retire_after: None` unconditionally (**D235**, ADR 0076).
The bootstrap key rotates by **cutover**.

What Run 1 rehearses is therefore everything a cutover shares with an overlap --
capture, provider, materialize, redeploy, admit; the per-consumer generation
layout; the bootstrap plane re-applying a credential; the edge reloading a
rewritten middleware -- and **not** the two-phase logic Run 10 needs. Run 10
builds that without a live rehearsal, and §9 carries it as a risk rather than a
solved problem.

Preparing the window also found that one of its three proofs could not execute
(**D236**, ADR 0075), which is the fifth instance in two runs of a wrong answer
sitting written down inside an unexecuted proof.

---

## 1. Runbook divergences

Six columns, as every session since Session 2. A row is here because the runbook
and the repository disagree and the disagreement was **measured**, not assumed.

| # | Runbook says | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D215** | Session 6 adds decision records `0017-auth-service-direct-database.md` through `0022-agent-token-preactivation.md`, and outputs schema **version 6** migrated from version 5. | `docs/decisions/` holds **74 ADRs**, `0001`…`0074`, all indexed in that directory's `README.md`; ADRs 0017–0022 were written in Session 2 and say entirely different things. The deployed documents on the host are **`schema_version: 8`**; `output_migrations.CURRENT_VERSION` is 8, reached through a chained `v4→v5→v6→v7→v8` module. | **Session 6 owns ADR 0075 onward and outputs v9.** Every ADR is numbered sequentially at the moment it is written and indexed in the same commit. The version bump pays D40's full price: a `migrate_v8_to_v9` function, a committed `tests/fixtures/outputs-v8.json`, and the standing rule that migration never produces a *deployed* document. | Mechanical, and it is here because it is the cheapest possible instance of the session's standing defect: a number that looks measured and is not. A plan that opens by asserting six ADR numbers it does not own is a plan that has not read the directory. | no |
| **D216** | Outputs v6 adds a top-level `http_api` block with `rest`, `application`, `token_issuer` and `documentation` sub-objects, replacing `bootstrap_issuer`. | **D137 refused exactly this shape one session ago**, and the refusal is why the current document already carries what Session 6 needs. The deployed branch has a top-level **`jwt`** object — `issuer`, `audience`, `algorithm`, `active_kid`, `verification_kids`, `public_jwks_sha256`, `retire_after`, `status`, and an explicit **`temporary: true`** — plus `routes.{rest,docs,health}` as status-carrying objects. There is no `bootstrap_issuer` key to replace. The issuer is *already* `https://<domain>/api/app/auth`. | **v9 extends what exists.** `jwt.temporary` flips to `false`; `jwt` gains `rotation_phase` (`steady`\|`prepared`\|`overlap`) and per-consumer applied-generation acknowledgements; `routes` gains **`app`** as a fourth status-carrying object shaped like the other three. No parallel block. `routes.app.url` is the one authority for the application base URL, exactly as ADR 0061 made `routes.docs.url` the one authority for the documentation router. | D137's reasoning holds verbatim: "a parallel `http_api` block would give `routes.rest` and `http_api.rest.public_url` as two records of one URL, and this repository has watched such a pair drift." It watched it again in D177, where the documentation route was derived twice and the copy carrying a comment saying it was kept in step was the one that had drifted. | **yes** |
| **D217** | Migrations `0009_auth_service.sql.tmpl`, `0010_auth_request_status.sql.tmpl`, `0011_auth_documentation.sql.tmpl`. | **Ten migrations are released and immutable.** `0009` is the documentation role; `0010` makes the pre-request hook carry the role's statement timeout (ADR 0068). `migrations/released.lock.json` is frozen by `bin/migrate.sh freeze-lock` and verified by the gate. | **Session 6's migrations are `0011`, `0012`, `0013`**, applied through the canonical dbmate wrapper, in order, with the lock re-frozen in the same commit. Named for what they do rather than for the session: `0011-identity-registry.sql`, `0012-request-authorization.sql`, `0013-auth-surface-comments.sql`. | Released migrations are fix-forward and the numbering is a filesystem fact, not a preference. A plan that names `0009` for new work is a plan that would have collided with a released file on its first `dbmate up`. | no |
| **D218** | Migration 0009 "extends `app_private.users`" with `role_name`, `scopes`, `last_login_at`, preserving "existing IDs, username rules, display-name rules, status values, and timestamps", and §17.2 requires a nullable-add → backfill → validate → `NOT NULL` sequence for "inherited rows". | **`app_private.users` does not exist.** The four schemas hold exactly `app_private.project_identity`, `app_private.migration_ledger`, `app_private.postgrest_pre_request()`, `app.notes` and `app.tasks`. There are no users, no usernames, no statuses and no inherited rows. `app.notes.owner_id` and `app.tasks.owner_id` hold whatever UUID the `app.user_id` claim carried — **trusted, not authenticated**, which is ADR 0029 stating the boundary in its title. | **Session 6 creates the identity registry from nothing.** The entire nullable-add/backfill/validate/`NOT NULL` sequence and every "preserve inherited" clause is struck: there is nothing to preserve and a backfill of zero rows proves nothing. Columns are `NOT NULL` from creation. **No foreign key from `app.notes.owner_id` to `app_private.users(id)`** — see D219's second half. | The runbook's migration is the more dangerous of the two shapes and it is the one that does not apply. A backfill test that runs against an empty table passes for a reason that is not correctness, which is D213's defect exactly: `assert checked` reporting success on a subset of one. Writing the simpler migration is not the win here; *noticing* that the complicated one would have been green and meaningless is. | no |
| **D219** | "A final-shaped JWT claim contract" is inherited from Session 5, with required claims `iss aud sub role scope token_use jti iat nbf exp`, and Session 6 merely adds `credential_version` and `authz_version` as "a documented versioned extension". | **Measured in `bin/dev-token.py::mint` and `migrations/templates/0010`.** A bootstrap token carries exactly `role`, `iat`, `exp`, `iss`, `aud`, and `sub` **only for non-documentation roles**. There is no `scope`, no `token_use`, no `jti`, no `nbf` anywhere in the system. The hook reads `sub`, shape-checks it as a UUID, and sets `app.user_id`; it reads nothing else. `scope` has never been signed, published, or verified. | **Session 6 does not extend a claim contract. It writes the first one**, and that is an ADR with alternatives rather than a footnote. The required set, the `token_use` discriminator, `jti`, `nbf`, and the two version claims all arrive together in one versioned contract, verified in two places — PyJWT in the service and the pre-request hook in the database — with **one authority for the shape** so the two cannot drift. | This is the largest single misreading in the runbook and it changes the size of the session. "Add two claims to a validated contract" is an afternoon; "write the claim contract, the verifier, the hook's half of it, and the negative matrix that proves each claim is actually load-bearing" is most of a session. It also explains D220: a scope vocabulary is being *invented*, not preserved. | **yes** |
| **D220** | Preserve the inherited scopes `api:read`, `api:write`, `openapi:read` exactly — "changing them to a new prefix would be a versioned cross-session contract migration" — and add `admin:users`, `admin:agents`, `admin:docs`, `agent:read`, `agent:write` in a new `contracts/auth-scopes.yaml`. | **Those three scopes do not exist and never have.** D131 settled the question in Session 5: **ADR 0006 makes `schemas/capabilities.schema.json` the sole authority for the approved scope vocabulary**, in its own words — "the code carries no second copy" — and ADR 0049 is titled *One scope vocabulary*. The vocabulary is `notes:read`, `notes:write`, `tasks:read`, `tasks:write`, `meta:read`, and the schema says it "grows only when `docs/decisions/0003-example-domain.md` is superseded". | **No `contracts/auth-scopes.yaml`.** New scopes are added to the capabilities schema's enum, which is what ADR 0006 exists to force, and the admin capability set is named in that vocabulary's grammar (`admin:users` fits the pattern; `api:read` does not, because there is no `api` resource). The **role→scope registry** the runbook wants is real and needed — it just cannot be a second file that also defines scope *names*. It becomes a mapping keyed on names the capabilities schema already admits. | D131's reason, one session on and now load-bearing: Session 8 builds MCP tools whose `required_scopes` come from that enum. Two vocabularies for one operation means a mapping between them, and the mapping is where a scope quietly widens. The runbook's own instinct is right — a registry is the authority — it just names a file that would become the second authority ADR 0006 forbids. | **yes** |
| **D221** | The gate is `bin/session-06-check.sh --project project.yaml --peer-project tests/fixtures/projects/project-b.yaml`, and §2.6 checks Session 5 with `bin/session-05-check.sh --project project.yaml`. | **D45 settled the gate shape in Session 2 and every session since has kept it**, D82 and D132 restating it against the same mistake: `--mode offline\|host\|external`, `--project-a-outputs`/`--project-b-outputs` naming **deployed documents** rather than manifests, `--sentinel-file`, `-k` (which writes no evidence), verify-only. `bin/session-04-check.sh` and `bin/session-05-check.sh` **refuse `--capabilities` and `--external-probe` by name**, pointing at the right flag. | **`bin/session-06-check.sh` is `bin/session-05-check.sh`'s shape with `readonly SESSION=6`**, three modes, the two refusals kept verbatim, and a third refusal added for `--peer-project`. Two Run 10 findings become part of the shape rather than operator lore: **`--sentinel-file` is written into the operator guide's command, not mentioned below it** (D213), and **the gate fails rather than skips on stale rendered fixtures** (ADR 0073). | A gate that takes manifests measures what was asked for. A gate that takes deployed documents measures what happened. Four sessions of runbooks have proposed the first and four gates have implemented the second; the refusals exist because an operator reading the runbook is asking a reasonable question and deserves an answer rather than a usage error. | no |
| **D222** | `schemas/session-06-evidence.schema.json` plus a Session 6 evidence collector, with §20.3 listing ~25 hand-shaped evidence fields. | **D133 settled this and D49 and D91 settled it before that: a session adds claims, not a format.** ADR 0025 replaced suite-name evidence keys with claims resolved from `tests/acceptance-registry.yaml` and JUnit results; ADR 0039 derives a claim's session from its requirements; ADR 0045 splits a claim where its measurement lives. `bin/write-session-evidence.py` is session-agnostic and has been since Session 2. | **Session 6 adds entries to `evidence_claims.CLAIMS`** (§7 below). Counts come from catalogs and JUnit. Nothing is hand-entered, and a proof missing from the artifact is `not_run` rather than `passed`. | Every hand-shaped boolean is a place a `true` can be written by something that is not a test. Session 5 ended with two claims reading `failed` because four node IDs never ran — that is the model working, and it only works because no human can type the verdict. | no |
| **D223** | A large implied set of new Session 6 requirement IDs scattered through §17's test plan; no IDs are named. | **Five Session 6 requirements already exist** in `tests/acceptance-registry.yaml`, each with a `future` placeholder carrying an exact node ID: `SEC-JWT-001`, `SEC-KEY-001`, `SEC-CRED-001` (in `tests/security/test_future_security_boundaries.py`) and `API-AUTH-001`, `API-ADMIN-001` (in `tests/integration/test_future_api.py`). `test_future_marker_policy.py` enforces registry↔marker agreement in both directions. The admitted prefixes already include `SEC-REV`, `SEC-BOOT`, `SEC-CRED`, `API-ADMIN`, `AGT-*` and `STO-*`. | **Activate the five that exist; add new IDs only where none covers the claim.** Final list in §2. The five carry **one node ID each today and will carry many**, which is deliberate and is the one place this session knowingly walks into a known blind spot — see D232. | Activating a requirement means removing its `future` marker and implementing the body; the placeholder already fails when executed, which is what makes it activatable. An unregistered prefix or a duplicate ID fails offline, so this is cheap to get right and expensive to discover late. | no |
| **D224** | New test directories `tests/integration/`, `tests/isolation/`, `tests/browser/`, and `services/auth/tests/unit/`. | `tests/` holds `contract/`, `deployment/`, `external/`, `integration/`, `recovery/`, `security/` and `fixtures/`. There is **no `tests/isolation/` and no `tests/browser/`** — isolation is a *marker* concern (`deployment`) and **D142 refused a browser harness outright**, on the grounds that a proof whose subject is another project's runtime behaviour is a proof of the wrong thing. | **Session 6 adds no test directory.** Auth-service unit tests live under `tests/contract/` with the `contract` marker, because they test committed source with no service running, which is what that directory means here. Isolation tests are `tests/deployment/` with `live_host`. **D211 is now a rule of the plan, not a footnote: `-m live_host` is not "the host tests"** — `tests/security/` is a directory a path-scoped sweep never reaches, and the gate is the only thing that runs it. | Session 5 lost a run to that exact gap. A Session 6 test placed in a directory the sweep does not select is a test that will be green for three sessions and then fail on its first execution, which is how D211, D212, D213 and D214 all happened inside one run. | no |
| **D225** | A locked baseline of CPython `3.13.x`, FastAPI `0.141.1`, PyJWT `2.13.0`, Pydantic `2.13.4`, Pydantic Settings `2.14.2`, Psycopg `3.3.4`, pwdlib `0.3.0`, argon2-cffi `25.1.0`, Uvicorn `0.50.2`. | The repository's virtualenv is **CPython 3.12.13**. More to the point: **D201 is four months of this project's most expensive lesson.** `SCALAR_VERSION: "1.36.4"` sat in `versions.in.yaml` for four sessions naming a release that **has never existed**, and it survived because `bin/verify-versions.sh` resolves `images:` entries to digests while a `packages:` entry is a string nothing dereferences. D37 and D85 add the standing rule: a session uses what is already pinned and adds to the lock only when a measurement requires it. | **Not one of those nine versions is written into `versions.in.yaml` until it has been resolved against its registry**, in Run 2, with a control that proves the rig can tell a real version from a fictional one. The interpreter is the repository's locked 3.12, not 3.13, unless a measured requirement forces the bump — in which case the bump is its own ADR. `cryptography` is recorded explicitly in the resolved lock even though `PyJWT[crypto]` introduces it transitively; that part of the runbook is right and is kept. | Nine version strings arriving from a document is nine instances of D201 waiting. The runbook's own §4.1 says "do not use floating constraints" and then supplies nine exact numbers with no provenance — which is the same failure one level up: a value that looks measured and is not. | no |
| **D226** | Publish FastAPI documentation through a new `services/scalar-auth/` container with a `scalar.config.json.tmpl`, under `/docs/app`. | **`services/docs/` is a first-party build** — Node builder plus the locked Python runtime, `npm ci --ignore-scripts`, only `standalone.js` crossing the stage boundary, **Scalar 1.64.1**, served by a 200-line `serve.py` under its own CSP (`default-src 'none'`), with a four-path route table and `VOLUME ["/app/snapshot"]`. ADR 0069 decided it. The router is published from `routes.docs.url` (ADR 0061), and the credential middleware lives in Traefik's file provider. | **`/docs/app` is a second surface of the existing service, not a second service.** `serve.py`'s route table gains the application snapshot's paths; the mounted snapshot directory gains a second file; the router is published from **`routes.app_docs.url`**, derived like every other route. One container, one CSP, one credential. | A second Scalar container would double the image, the CSP, the credential, the middleware and the CVE surface to serve a second JSON file. It would also give the repository two answers to "how is a documentation page built", and ADR 0069 exists because the first answer was worth choosing deliberately. | **yes** |
| **D227** | New secret keys `postgres.auth_service.password`, `jwt.active.private_jwk`, `jwt.public_jwks`, `jwt.prepared.private_jwk`, declared in `schemas/secrets-required.schema.json` and consumed through `secret_contract.py`. | `secrets.required.yaml` at the repository root is the contract; `src/agentic_postgres/secrets_contract.py` reads it. A secret declares `value_kind`, `introduced_in_session`, and consumers carrying **`plane: compose\|root`** (ADR 0054), `format: raw\|pgpass`, `uid`, `gid`, `mode`. Session 5 already declares `bootstrap_jwt_signing_key` and `docs_basic_auth_password` as **root-plane** consumers, and **ADR 0055** is titled *the contract declares what kind of value a secret is* — because a generator that wrote 32 bytes of hex under a signing key's name would have passed every check. | **Session 6 appends to `secrets.required.yaml`** with `introduced_in_session: 6`: `auth_service_password` (compose consumer `auth`, `format: pgpass`), `jwt_active_private_jwk` (compose consumer `auth`), `jwt_public_jwks` (compose consumers `auth` **and** `postgrest`), `jwt_prepared_private_jwk` (**root plane only**, never mounted into a running service before promotion). Each declares a `value_kind` that says what it *is*. | The consumer matrix the runbook wants is exactly what this file already computes, and D213 has just made it load-bearing: the materialization proof now stats every consumer the deployment carries, so a Session 6 secret with a wrong `uid` or `mode` fails on the next gate rather than in Session 9. | no |
| **D228** | "Session 6 bootstrap convergence path" activates the `auth_service` role with `LOGIN`, a connection limit of **8**, SCRAM credentials, fixed `search_path` and timeouts; §9 puts role attributes, HBA and grants together in one phase. | **D102 splits them and the split is a contract.** The *migration plane* (dbmate, `SET LOCAL ROLE object_owner`, never a superuser) applies released migrations; the *bootstrap plane* (root on the host, over the container socket) owns roles, role settings and credentials — **anything `ALTER ROLE`**. A migration that touched a role attribute would be in the wrong plane. Separately, **ADR 0070 divides the connection budget**: `connection_limits(maximum, reserved, api_budget)` returns `(application, api)` and raises when the remainder falls below 1. `app_runtime` currently holds 29 and `postgrest_authenticator` 13. | **Role attributes, the connection limit, the SCRAM credential, the role's `statement_timeout` and the HBA rule are bootstrap-plane work in `bin/postgres-bootstrap.py`.** Migration 0011 creates *tables and functions* and grants `USAGE`/`EXECUTE` — nothing else. **`connection_limits` gains a third claimant and its arithmetic is re-derived, not extended by subtraction**; "8" is an output of that function, not an input to it. | ADR 0070 is titled *the connection budget is divided, not granted twice* because the previous shape granted the same headroom to two roles independently. Adding a third role by writing a number into a manifest is that defect returning, and it fails in production under load rather than in the gate. | **yes** |
| **D229** | Four Traefik routers ordered by priority, `PathPrefix('/api/app')`-style boundaries, and rate-limit middlewares with exact token-bucket settings; "`/api/application`, duplicate-slash, and encoded-separator variants must not match". | The runbook has correctly identified a trap this repository already fell into: **D162 measured that `PathPrefix(/api/rest)` matches `/api/restaurant`** — it is a string prefix, not a path prefix. The rest is harder than written. Traefik v3.7 filters on the constraint **`Label(apg.traefik.scope, managed)`**, so a container without that label carries no route no matter how correct its router is (D186); a router label's **key** contains the router name and Compose cannot interpolate inside a key, so keys are rendered in `runtime_override.py` (ADR 0013); a service on two networks needs **`traefik.docker.network`**; and a middleware defined by container labels **vanishes with the container** (D202, D208, both `pending`). | **The boundary rule is adopted verbatim and proved by request, not by configuration.** Routers are rendered through `runtime_override.py` with keys built from `routes.app.url`, never a constant (ADR 0061). Middlewares go in **Traefik's file provider** — which closes D202/D208 rather than deferring them a third time. Every 404 during this work is diagnosed from the **access log** before anything is concluded: Traefik's own 404 carries no `RouterName` and a 19-byte body, and Run 9 produced three in a row with three different causes. | The runbook's list of what must not match is a good list and the repository has failed at exactly one of its items. What it is missing is that the failure mode is *silent*: a correct, measured router attached to a container Traefik cannot see answers 404 while the service serves 200 to its own network. | **yes** |
| **D230** | Deployment stops at a `bootstrap_required` state: outputs are not published, `/api/app` is not routed, and `deploy.sh --through-session 6` is re-run after a local first-admin bootstrap to resume convergence. | **D135 refused inventing a deployment state one session ago**, in these words: the runbook's version "invents a *deployment state* — a project that is deployed but not ready and not public — which is a fifth thing `deployed_through_session` and the endpoint `status` fields would have to be read against, and a state nothing else in the system knows how to reason about." | **The two-stage convergence is kept; the new state is not.** It is expressed in the vocabulary that exists: `routes.app.status` is **`unavailable`** until an active project administrator exists, exactly as `routes.rest` is `unavailable` for a project that declares no REST service (ADR 0062). `deploy.sh --through-session 6` is re-runnable and idempotent, which it already is. The deploy prints the bootstrap command and exits 0 — a project awaiting its first administrator is not a failed deploy. | The runbook's underlying requirement is right and important: no public application route may be published before an administrator exists, or the first request to reach it decides who the administrator is. That requirement needs a *status field*, not a *state machine*, and there is already a status field on every route. | **yes** |
| **D231** | Internal `/health/live` and `/health/ready` endpoints, excluded from every public router and from OpenAPI; "Session 6 publishes no public health route". | The project **already publishes a public health route**: `routes.health` is `https://<domain>/__apg/healthz`, `ready`, served by the `edge-probe` service, and `test_the_probe_can_tell_a_trusted_path_from_an_authenticated_one` is a Session 5 proof about it. So "publishes no public health route" is already false for this deployment, and an auth service that adds two more health paths adds a third and fourth answer to "is this project up". | **The auth service's readiness is container-local and is reported *through* the existing probe, not beside it.** `/health/live` and `/health/ready` bind the container interface, are excluded from the public router by an explicit deny rule proved by request, and are absent from the generated OpenAPI. What the public learns about auth's health is what `__apg/healthz` says, which is the surface that already has a proof. | Three health endpoints is three things to keep in step and one of them will drift. The edge probe exists and has a test that distinguishes a trusted path from an authenticated one; extending it is cheaper than publishing a parallel signal and then writing the test that proves the two agree. | no |
| **D232** | §17 lists roughly 120 discrete test properties across twelve subsections; §21's exit checklist has 60 boxes. | **Five registry entries carry one node ID each.** D175 recorded, and did not fix, the fact that *nothing detects a requirement whose description outgrows its node IDs* — it is a review rule, because enforcing it would need a second authority beside the markers. Session 6 is the largest instance of that gap the project will have produced. | **Every property in §17 that this plan keeps is mapped to a named node ID in §2 before implementation starts**, and the five requirements are split where their measurements live (ADR 0045's rule) rather than accumulating forty node IDs each. Where a property has no node ID, it is not a requirement — it is prose, and it is deleted from the plan rather than left to look like coverage. | A requirement with one node ID and a paragraph of description reads, in `docs/acceptance-matrix.md`, exactly like a requirement with fifteen. That is the review rule's failure mode and it is invisible in every generated document. Doing the mapping first is the only defence this repository has. | no |
| **D233** | §2.6: run `bin/session-05-check.sh` and record its "immutable evidence checksum"; §16 Phase 0 re-runs "the inherited non-destructive Session 5 subset" after Session 6 migrations change the claim shape. | Evidence is **gitignored** (`evidence/*`, with only `.gitkeep` tracked) so that the gate sees no untracked output. There is nothing immutable to checksum — the artifact is regenerated. And Session 5's own state is the sharper problem: **two claims are unproved** because the rotation window was deferred. | **Session 6 Run 1 is Session 5's rotation window**, run to completion, taking Session 5 to 18 of 18 before anything in this session touches a key. The "non-destructive inherited subset" is not enumerated by hand — it is what `-m live_host` collects from the whole tree, which is what the gate already runs. | Cutting an issuer over on top of a prepare/promote/retire path nobody has executed is Run 9's defect with a bigger blast radius: the machinery is built, granted, wired, and unexecuted. Session 5 also left the reboot proof unrun, and a reboot is the one event that tests whether key state survives without an operator present. | no |
| **D234** | §4.10: bound Argon2 to "no more than two concurrent operations per container" and reserve "at least 128 MiB for two concurrent 64 MiB hashes"; §15.2 sets a 384 MiB memory limit. | The repository derives every memory bound from the manifest and checks it against a per-project guardrail: `database.memory_limit_mb` must exceed a *derived unreclaimable budget*, and that budget must not exceed the guardrail — both are `CROSS_FIELD_RELATIONS` entries in `config.py`, generated into the bounds documentation. A service limit typed into a Compose file is outside that arithmetic. | **The auth service's memory limit joins the derived budget** as a named claimant, the way ADR 0070 made the connection budget a division rather than a set of independent grants. `hash_concurrency` and the limit are related by a cross-field relation — `hash_concurrency × memory_cost_kib` plus process overhead must fit the declared limit — so a manifest that raises concurrency without raising the limit **fails validation** instead of being killed by the OOM killer at the first login burst. | The runbook's numbers are probably fine. The failure they leave open is the one this project keeps producing: two values in two files that must agree, with nothing computing the relation. `memory_cost = 65536 KiB` and `hash_concurrency = 2` and `384 MiB` are three numbers with one true relationship between them. | **yes** |
| **D235** | (Session 6's plan, §0 and Run 1.) Running Session 5's rotation window first "is not tidiness" -- it exercises the prepare/promote/retire machinery Session 6's signing-key cutover depends on, which "has never been exercised once". | **Measured: there is no machinery to exercise.** `jwt_keys.begin_rotation` and `complete_rotation` implement a two-phase overlap with a computed retirement deadline and a refuse-early rule, and **nothing outside `tests/contract/test_jwt_keys.py` calls either.** `bin/render-jwks.py::build` returns `build_jwks([jwk])` -- exactly one key -- under a comment reading "A rotation publishes two and is Run 10's"; `bin/deploy-project.py::observe_jwt` writes `retire_after: None` unconditionally under a comment reading "Run 10 is what sets one". Run 10 did neither. | **The bootstrap key rotates by cutover, and Run 1 executes a cutover** (ADR 0076). The proof is unchanged -- it was always written as an *end state*, which is agnostic about the path taken to it -- and only its docstring and `SEC-BOOT-001`'s description lose the phrase "second rotation phase". The overlap functions stay, uncalled and not presented as available. | **This is Run 9's `PGRST_DB_PRE_REQUEST` in a new place**: a plane built, validated, unit-tested, documented, and wired to nothing -- with a comment naming a future run as the tell in both cases. The consequence is the part that matters: **Run 1 does not de-risk Run 10, and the plan said it would.** Run 10 builds its overlap without a live rehearsal, and §9 now carries that. | **yes** |
| **D236** | (Session 5's own proof, inherited as ready to admit.) Run 1 is a maintenance window that runs three rotation proofs which were written, reviewed and committed in Session 5. | **One of the three cannot run.** `test_a_rotated_authenticator_serves_the_plane_and_the_old_password_does_not` asks `materialized_secret` for `postgrest/postgrest_authenticator_password`; the materializer writes `postgrest/postgrest_authenticator_pgpass`, because that consumer declares `format: pgpass` (ADR 0056). It is the **only** entry in `secrets.required.yaml` whose `target_file` differs from its `name`, so the wrong rule held for twelve consumers of thirteen. Measured offline against the committed contract, with a control that resolves. | **A test names a secret and who holds it; the filename and the format are derived** (ADR 0075). `secrets_contract.consumer_named` resolves the pair, `materialized_secret` returns `recover_secret(...)` of the bytes, and no caller can spell a path. Fixed **before** the window, not during it. | Had the filename been right it would have been worse. `new` would have been the pgpass line, so `assert old != new` -- the control that refuses a false declaration -- could never have failed, and a window in which nothing was rotated would have reported *"the verifier was not replaced"*: a diagnosis of the bootstrap plane, for an operator error. **And the correct idiom was already in the repository**, in `test_session5_api_isolation.py`, one file away -- D173's two spellings of one object, with the spelling that had run being the right one. | **yes** |
| **D237** | (D225 and §5 Run 2 of this plan, and D201 before them, and `versions.in.yaml`, and ADR 0069.) `bin/verify-versions.sh` resolves `images:` entries to digests while a `packages:` entry is a string nothing dereferences. | **`bin/verify-versions.sh` has never existed.** The script is `bin/lock-versions.sh`, with `--update` and `--check`, and `git log --diff-filter=AR -- 'bin/*version*'` returns exactly one commit and one path. Four documents name the wrong file, including this plan twice. | **The live references are corrected; the historical ones are not.** `versions.in.yaml` and ADR 0069 now name the real script. Session 5's divergence table keeps its wording, because a divergence row records what was believed at the time and editing one to be right destroys the record. This row is the correction. | The claim *about* the script was true -- packages really were copied through -- so the wrong name rode along inside a correct sentence, four times, for two sessions. It is the cheapest possible instance of this project's defect and it cost nothing until somebody was told to go and change that file. | no |
| **D238** | (Implicit in D225's "resolved against its registry, in Run 2".) Locking a measured package version is an additive act. | **`--update` regenerates `versions.env` wholesale**, so writing one package pin also re-resolves all ten images -- and four are pinned by tags that move: `pgvector:pg18`, `traefik:v3.7`, `node:22-alpine`, `python:3.12-slim`. Measured immediately before Run 2's update, per image, against the recorded digest: **zero drift**, because the lock was one day old. | **Run 2 proceeded, with the image digests as the control**: every `_IMAGE` line came back byte-identical, and that identity is what makes this change a package change. Carried as an open item (§10) rather than fixed, because separating the two resolutions is a change to `--update`'s contract and Run 2 is not the place to make one. | The measurement's result was 'safe', and the finding is that **it was safe today**. On any day when a tag has moved, locking a dependency silently changes what the deployment runs -- a coupling nobody would choose, discovered only because the control was written before the command was run. | no |
| **D239** | FastAPI `0.141.1`, as one of the nine. | **`FASTAPI_VERSION: "0.121.2"` has been in `versions.in.yaml` since Session 1**, and nothing has ever built from it. Both versions were resolved against PyPI in Run 2 and both exist. | **Kept at 0.121.2.** D37's rule is that a session uses what is already pinned; nothing measured requires the newer one, and the place to decide is Run 7, where the service exists and can be *run* against a version rather than assigned one. | The counter-argument is real and is recorded rather than dismissed: twenty minor releases of a web framework, and a pin nothing has ever installed carries no compatibility evidence in either direction. That is an argument for measuring in Run 7, not for taking a number from a document now. | no |
| **D240** | CPython `3.13.x` as the locked interpreter. | **Measured at each pinned version, not at `latest`:** every package in the set declares `requires_python >= 3.10` or looser -- fastapi 0.141.1, pydantic-settings 2.14.2, psycopg 3.3.4, pwdlib 0.3.0 and uvicorn 0.50.2 at `>=3.10`; pyjwt and pydantic at `>=3.9`; argon2-cffi at `>=3.8`. Nothing forces 3.13. Also measured: no build toolchain is needed on `linux/amd64` -- and that answer required asking the **transitive** distributions, because argon2-cffi and psycopg are pure-Python wrappers whose C code lives in argon2-cffi-bindings and psycopg-binary. `cffi`, `cryptography`, `argon2-cffi-bindings` and `psycopg-binary` all publish cp312/abi3 manylinux x86_64 wheels. | **The interpreter stays at the repository's locked 3.12.13**, and `test_the_interpreter_is_not_moved_by_this_dependency_set` makes that an executable statement, so a later bump gets its own decision instead of arriving inside an unrelated commit. | The first pass of this measurement reported "everything is pure Python", which was true of the eight named distributions and false about the question. **A rig whose subject is one level away from the claim** -- caught only because the answer was too convenient for a set containing Argon2. | no |
| **D241** | Tokens are short-lived, and a TTL is what bounds a token's life; §4's rotation safety and the non-resurrection property are both stated in terms of the TTL. | **The locked PostgREST accepts a token up to 30 seconds past `exp`, and 30 seconds before `nbf`.** Bisected against the locked digest: 30s is served, 31s is refused, symmetrically. Nothing in the repository records this, and `jwt_keys.begin_rotation` takes `clock_skew_seconds` as a caller-supplied number with no measured value behind it. | **`CLOCK_SKEW_SECONDS = 30` is a product input** in `jwt_claims`, and anything reasoning about token lifetime reads `MAX_TTL_SECONDS + CLOCK_SKEW_SECONDS`. The service verifies with the *same* leeway: a verifier stricter than the one downstream refuses tokens the deployment still honours, and reports it as an auth failure, which sends the reader to the wrong system. | **A token is live for 930 seconds, not 900**, and every sentence in this plan about revocation latency and rotation windows was written against the smaller number. A key retired on a 900-second window would refuse tokens still inside their own lifetime -- which is the failure `complete_rotation`'s refuse-early rule exists to prevent, arriving through the input rather than the logic. | **yes** |
| **D242** | PostgREST is the second verifier: the negative matrix is asserted "by the service *and* by PostgREST, which are two verifiers and must agree" (§2, `SEC-JWT-001`). | **Measured, configured from `compose.yaml` rather than from a rig's own idea of the settings.** PostgREST enforces the signature (refusing another key, `alg: none` and HS256), `exp` and `nbf` within the 30s leeway, `aud` **when present**, `kid` when present and unmatched, and role membership at `SET ROLE`. It **does not check `iss` at all** -- there is no issuer setting -- **serves a token carrying no `aud`**, and ignores `typ`, `token_use` and `scope` entirely. | **The two verifiers do not overlap the way the requirement assumed, and the split is recorded as data** in `POSTGREST_ENFORCES` / `VERIFIED_ELSEWHERE` rather than as prose. `SEC-JWT-001`'s matrix has a measured expectation per row **including the rows where the correct expectation is *served*** -- a proof asserting PostgREST refuses a bad `iss` would assert something false. | The first pass of this measurement left `PGRST_JWT_AUD` unset and reported that a wrong audience is served. That is a fact about a rig nobody deploys -- **ADR 0065 arriving for the fourth time** -- and it was caught only by reading the product's own compose file before writing the result down. | **yes** |
| **D243** | (ADR 0049, accepted in Session 5 Run 1.) "Session 5 issues bootstrap tokens carrying a `scope` claim, and the pre-request function validates it", with the permitted names reaching the hook "as non-secret `app.settings.*` values rendered from the schema's enum". | **Neither half was ever built.** `bin/dev-token.py::mint` signs `role`, `iat`, `exp`, `iss`, `aud` and an optional `sub` -- no `scope`. No `app.settings.scope_*` is rendered anywhere in `src/` or `bin/`. The pre-request function reads `sub` and nothing else. | **Recorded, not fixed here.** Issuance is Run 7's, with the service; the hook's half is migration 0012's. ADR 0079 says so in its consequences so the next reader is not the third person to assume it works. | **An accepted ADR whose subject does not exist**, and the third instance this session after D235's uncalled rotation plane and D204's rule catching `jwt_claims`. ADR 0049 is not wrong -- its decision is the one this session is still following -- it was simply never implemented, and nothing in the repository could tell the difference. | no |
| **D244** | (D220, in this plan's own table.) New scopes "are added to the capabilities schema's enum, which is what ADR 0006 exists to force". | **Following that literally would have widened the agent capability surface.** `$defs/scope` is referenced by exactly one place -- `capability.required_scopes.items` -- so the approved vocabulary and *what a tool manifest may request* are the same list. Adding `admin_users:write` to it makes it requestable by an agent capability, which is the `admin:everything` drift ADR 0006 names in its own rejected-alternatives section. | **One authority, two closed classes** (ADR 0079). `$defs/scope` is the union; `$defs/agent_scope` is the data class and `required_scopes` binds to *it*; the administrative class is derived as the complement so the four names are written once. `scope_registry` maps role → ceiling and validates every name against the schema on the way out. | D220 was right about the authority and wrong about the mechanism, and the difference is one `$ref` nobody had needed to read before -- the enum had only ever had one job, so nothing distinguished its two. **The mutation that matters is that one word**: repointing it restores the old behaviour while every other assertion about the vocabulary stays true. | **yes** |
| **D245** | (D215, in this plan's own table.) The version bump "pays D40's full price: a `migrate_v8_to_v9` function, a committed `tests/fixtures/outputs-v8.json`, and the standing rule that migration never produces a *deployed* document" -- written as though the fixture-per-version discipline were being continued. | **It had lapsed three versions ago.** `tests/fixtures/` holds `outputs-v1` through `outputs-v5` and stops. `migrate_v5_to_v6`, `v6_to_v7` and `v7_to_v8` are exercised **only by chaining from the v5 fixture**, which is the condition `test_output_migrations.py`'s own docstring names: "a document derived from the migrator is a document that agrees with the migrator by construction". Nothing noticed, because a chained document validates against the schema exactly as a rendered one does. | **A real v8 render is captured and the comparison it enables is written**, before the schema moves -- after the bump, `--render-only` emits v9 and a genuine v8 cannot be produced from this tree again. The comparison is *structural*: the two fixtures describe different projects, so equality is not the question; a key the migrator never adds and a key only it invents are. | **Measured result: the chained v8 and a real v8 render have identical shape.** No defect -- which is the honest outcome and not a reason the check should not exist. The value is that the question is now answerable, and it was answerable for v1→v5 and silently was not for v5→v8. The first draft of the comparison reported two false differences, because `statement_timeouts` is keyed by *role name* and comparing its members compares manifests: a rig one level away from its claim, in the module about exactly that. | no |
| **D246** | (§5 Run 4 of this plan.) "Session 6's four secrets appended to `secrets.required.yaml` with their planes and value kinds (D227)" -- in Run 4, four runs before the service exists. | **The contract forbids it, and says so in its own text.** `test_every_consumer_names_a_real_compose_service` requires a compose-plane consumer to name a service that exists, and `secrets.required.yaml` records why beside `postgrest_authenticator_password`: "It arrives in the same commit as its consumer... a grant to a service that does not [exist] is a grant nobody can audit." Three of the four name `auth`, which is Run 7's. | **The four move to Run 7**, with the service. The value-kind enum widening they need (`rsa_private_jwk`, `public_jwks` -- ADR 0055's rule that the kind says what the value *is*) moves with them, since nothing else needs it. | Attempted and reverted rather than argued: the contract test went red on the first run, which is the rule working. **Landing the entries early would have been this session's own recurring defect** -- a declaration with nothing wired to it, after D235's uncalled rotation plane, D243's unbuilt ADR 0049 and D204's rule catching `jwt_claims` in the same week. | no |
| **D247** | (Implicit throughout.) A schema field's required-ness is proved by the tests that exercise documents lacking it. | **Measured by mutation: removing `app_docs` from the schema's `required` list left every test green.** The documents those refusal tests use are **version 8**, and the version enum refuses them on its own -- so the required-ness was riding on a check that would have refused the document anyway. | **A test that migrates to v9 first and then removes the key**, with the migrated document validating two lines above as its control. | A guard proved by a test that does not need it. The same shape as every finding this session has produced, one layer down: the assertion was green, the code was correct, and nothing connected them. Found only because the mutation was expected to go red and did not. | no |
| **D248** | (§17.2 of the runbook, and D218's decision to strike it.) The registry is created rather than extended, so the migration is the simpler of the two shapes and needs no special care. | **Simpler, and it has a hole the complicated one does not.** ADR 0078 requires `scope` to be a sorted, deduplicated array of non-null strings; the database should hold the same line. `CHECK (scopes = ARRAY(SELECT DISTINCT unnest(scopes) ORDER BY 1))` is refused outright -- "cannot use subquery in check constraint" -- and the function-backed version that replaces it **accepted `ARRAY['a', NULL]`**. Array comparison with a NULL element is NULL, and **a CHECK constraint is satisfied when its expression is NULL**. Measured on the locked image, with a control: the same function refused the unsorted array in the same run. | **ADR 0080.** A CHECK may not be able to evaluate to NULL: every function used in one returns `coalesce(<predicate>, false)`, a predicate over a collection tests for NULL members explicitly, and `NOT NULL` sits beside every emptiness check as a tested rule rather than a convention. | The scalar case is the same: `CHECK (v <> '')` accepts NULL. So every emptiness check in this repository has always depended on a `NOT NULL` beside it to mean anything -- **verified across all thirty CHECK lines in `migrations/templates/` rather than assumed**, and all thirty have one. D218's 'NOT NULL from creation' was doing more work than it looked. | **yes** |
| **D249** | (`docs/api-operations.md`, rewritten in Run 1 by this session.) A rotation's second step is "replace the value at the provider, under the `provider_path` and `provider_key` `secrets.required.yaml` declares for it". | **No command in this repository does that.** `bootstrap-providers.sh --apply` creates secrets that are missing and **deliberately leaves existing ones alone** -- its own docstring says why: "Overwriting would rotate a live credential from a command whose job is to create missing ones." There is no `--rotate`, and nothing else writes to the provider. | **The operator sets the new value by hand in Infisical**, which is consistent with the standing rule that a mutation is a human action; the repository supplies the generation and capture commands around it. A `bin/rotate-secret.sh` was weighed and not taken in this window: it puts a write path to live credentials into the repository, which `create_secret` refused on purpose. | **The procedure I wrote in Run 1 names a step no tooling performs**, and I did not check that it was executable before writing it down. Same shape as D235 and D243, in a document written *by this session to fix exactly that class of problem*. | no |
| **D250** | (Run 4, this session.) Outputs v9 shipped: schema, migration step, renderer, deployed builder, tests, mutation battery, gate green, suite 2 771 passed. | **The one production caller was never updated.** `build_deployed_document` gained `app_status` and `app_docs_status` as *required keyword-only* parameters; the test helper that calls it was updated and `bin/deploy-project.py:1219` was not. The deploy raised `TypeError` on the live host at step 7 -- **after** it had restarted both projects' services and applied migration 0011 to both clusters -- and before `write_deployed_document`, so both deployed documents stayed at the previous release. | **The caller is fixed and a guard added**: `test_every_bin_call_supplies_the_required_keyword_only_arguments` AST-parses every `bin/*.py`, resolves calls to imported `agentic_postgres` modules, and checks each required keyword-only parameter is supplied. Proved by reproducing the failure -- removing `app_status` reports `deploy-project.py:1219: ... requires ['app_status']`, the host's message. | **Nothing could have caught it.** The tests call the function through their own helper; the caller lives inside `main()` of a script needing root, a cluster and an edge, so no offline test executes that line. D204 made an *import* graph a fact about the source; a **call signature** is one too, and was not being read. | **yes** |

---

## 2. What Session 6 adds to the acceptance registry

**The five existing entries are activated and split** (ADR 0045: a claim is split
where its measurement lives). Each keeps its ID; each gains the node IDs its
description already implies, and no entry is left with one node ID and a
paragraph.

| ID | Priority | Measured where | What it guarantees |
|---|---|---|---|
| `SEC-JWT-001` | P0 | contract + `live_host` | The negative matrix: wrong issuer, audience, algorithm, `typ`, `kid`, or expiry is rejected — by the service *and* by PostgREST, which are two verifiers and must agree. |
| `SEC-KEY-001` | P0 | `live_host` | Verifying services hold public material only, in every rotation phase, and no retiring private key is retained after promotion. |
| `SEC-CRED-001` | P0 | `security` | Raw passwords and agent secrets never reach storage, logs, evidence, process arguments, image layers or database error detail. |
| `API-AUTH-001` | P0 | `live_host` | Login issues a short-lived token; `/auth/me` reflects current state and refuses a token whose subject has changed underneath it. |
| `API-ADMIN-001` | P0 | `live_host` | Admin endpoints require an explicit scope, not a role name; a `project_admin` without the scope is refused. |

**New IDs, added only where none of the five covers the claim.** Prefixes are
already admitted by `ID_PATTERN`; none is invented.

| ID | Priority | Measured where | What it guarantees |
|---|---|---|---|
| `SEC-REV-001` | P0 | `live_host` | **Non-resurrection.** Disable→re-enable, revoke→reactivate, and a role or scope change reverted cannot restore a previously issued token. This is the session's sharpest property and it gets its own ID because a passing `API-AUTH-001` would not imply it. |
| `SEC-BOOT-001` | P0 | `live_host` | The first administrator is created only through the local protected path, exactly once, under a project advisory lock; no public bootstrap endpoint exists. |
| `SEC-CRED-002` | P0 | contract | The Argon2id profile is the frozen one, read back **from the encoded hash** rather than from the constructor's arguments. |
| `API-AUTH-002` | P0 | contract + `live_host` | Strict input: duplicate JSON members, unknown fields, non-object roots, oversized bearer tokens and unapproved JOSE headers are refused before any domain logic runs. |
| `SEC-KEY-002` | P0 | `live_host` | Prepare → acknowledge → promote → retire converges with no signing gap, and promotion is blocked until every verifier has acknowledged the prepared public generation. |
| `DEP-ISO-003` | P0 | `live_host` | Project A's tokens, agent secrets, admin session and JWKS are all refused by project B, and the two projects share no key, issuer, audience, lock or credential. |

**Refused as a Session 6 requirement:** a browser-driven documentation proof.
D142 settled it and the reasoning is unchanged — the page is a static local
snapshot, so "no credential in the served bytes" is a byte scan of files this
deployment wrote, which holds for every visitor rather than for the one that was
driven.

---

## 3. Environment feasibility

**What exists and is proved.** Two projects deployed through session 5 on
`62.238.99.122`, both with `routes.rest` and `routes.docs` `ready`; a locked
PostgREST 14.16 with `db-config=false` and a working `db-pre-request`; Traefik
v3.7 with a file provider already mounted; a first-party documentation service; a
root-owned immutable secret-generation tree; and a read-only diagnostic account
(`apg-agent`, ADR 0071) that answers questions about a running deployment
without an operator.

**What is new and needs measuring before it is depended on.**

1. **Every dependency version** (D225). Nine strings, resolved against their
   registries, with a control that can tell a real version from a fictional one.
   D201 is why this is Run 2 and not an assumption.
2. **Argon2id's actual cost on this host.** A 4 GB VPS already running two
   PostgreSQL clusters, two poolers, two PostgREST instances, two documentation
   services and an edge. `memory_cost = 65536 KiB` × `hash_concurrency` is a
   real claim on that budget and D234 makes it a derived one.
3. **Whether PostgREST accepts the claim contract D219 creates**, specifically
   whether a `scope` array and the two version claims survive to
   `request.jwt.claims` intact. Measured against the locked digest, with a
   control.
4. **Traefik's rate-limit middleware against the locked digest.** ADR 0019 is the
   standing lesson that a configuration key read from documentation is not a
   fact; `accessLog.fields.queryParameters` did not exist and took the edge plane
   down.

**What the host cannot do.** No IPv6 from any operator machine so far, so the
eight `APG_PUBLIC_IPV6` proofs stay unrun (carried from Session 5, measured, not
a defect — the edge binds `0.0.0.0` and no hostname publishes an AAAA record).

---

## 4. Safety plan for irreversible operations

Four operations in this session cannot be undone by re-running a deploy.

**The signing-key cutover.** Ordered as prepare → acknowledge → promote →
retire, with the property that makes it safe stated as a rule rather than a
hope: **promotion is blocked until every verifier has applied the same JWKS
checksum**, and that acknowledgement is a recorded per-consumer generation, not
an assumption about propagation. Rollback *before* promotion removes the
unpublished prepared material. Rollback *after* promotion completes forward —
there is no path that silently resumes signing with the old key. The old public
key is retired only after the longest token TTL, the clock-skew allowance and the
published JWKS cache lifetime have all elapsed.

**The first-administrator bootstrap.** One-time, local, TTY or protected FD,
never an argument, refused once an active administrator exists, and holding a
project-scoped advisory lock so two concurrent attempts cannot both win. If the
output is lost, the recovery is to inspect administrator state through the
protected CLI — **not** to re-run with a new password until the state is known.

**One-time agent secrets.** Shown once. If the response is lost after the commit,
the secret is unrecoverable and the documented recovery is to **rotate again**.
No retrieval endpoint is added, and the absence is a tested property rather than
an omission.

**Retiring the bootstrap issuer.** Last, after auth-service issuance and
PostgREST verification are both proved, and never before. The bounded emergency
path stays available until final evidence is green and is then retired according
to state.

**The standing rule, unchanged:** anything privileged that *mutates* is a human
at a TTY — deploys, the bootstrap plane, migrations, rotations, anything that
reads a credential. Read-only diagnosis is not, and `apg-diag` is how it is
reached.

---

## 5. Build order

Eleven runs. Each ends with `ruff format && ruff check` → the full suite →
`chmod 755 bin/*` → commit → **the gate on a clean tree** → push.

### Run 1 — Finish Session 5

Session 5's rotation window: the authenticator password, the signing key, the
documentation credential — three windows, one credential each, because one flag
per credential is what stops a single rotation admitting three proofs. Then the
reboot proof. Session 5 reaches **18 of 18 claims** and `api_authorization` and
`bootstrap_identity` stop reading `failed`.

**Done offline, before the window opens** (this is the half that is complete):

- **D236 / ADR 0075.** The authenticator proof named a file the materializer does
  not write, and would have failed on its first execution — inside a window,
  after a credential had been rotated and could no longer be recovered.
  `secrets_contract.consumer_named` now resolves (secret, holder) → file, and
  `materialized_secret` returns the *value*. Four mutations, each with a paired
  control in the same invocation.
- **D235 / ADR 0076.** The signing key rotates by cutover; the two-phase overlap
  is unbuilt. `docs/api-operations.md` said otherwise and now does not.
- `docs/api-operations.md`'s rotation section is rewritten with commands that
  resolve: the generation directory derived rather than typed (D213), the
  authenticator's password cut out of its pgpass line rather than copied whole,
  and the retired `kid` taken from the deployed document rather than the key.

**What is left is the window itself**, and it is a human at a TTY on the host:
capture, replace at the provider, `materialize-secrets.sh`, redeploy through
session 5, admit with the matching `--rotated-*-from-file`. The signing-key
cutover refuses every outstanding token the moment the deploy finishes, so it is
run when nobody holds one — bounded at 900 seconds by `dev-token.py`'s ceiling.

Nothing in Session 6 starts until this is done. D233's reason still holds, in its
corrected form: Session 6 replaces the signing key's owner, and the repository
has never once replaced a signing key.

### Run 2 — Measure every version, then lock  ·  **Done.**

All eight supplied versions resolved against PyPI, with a control that reports a
fictional version as absent. **Every one exists** — an unremarkable result, and
not a reason to have skipped the measurement. `cryptography` recorded explicitly.
FastAPI stays at the already-pinned 0.121.2 (**D239**); the interpreter stays at
3.12.13, measured per pinned version rather than assumed (**D240**).

**The other half turned out to be solvable, and was solved** (ADR 0077). Session
5 left "resolve package versions against their registry" open on the grounds that
it needs network in a check that deliberately has none — and that framing was the
obstacle. Images do not work because `--check` can reach a registry; they work
because **`--update` writes down something only a successful dereference could
have produced, and `--check` verifies it offline.** So a `packages:` entry now
declares its registry and package name, `--update` resolves it to one canonical
artifact — the sdist on PyPI, the tarball on npm — and records the digest.
`--check` stays entirely offline. Lock format 1 → 2.

A version nobody published now **blocks** `--update`. Proved in a copied
repository with `pwdlib==0.999.999`: exit 5, with the same rig at the real
version exiting 0. **D201 is closed.**

Found on the way: `bin/verify-versions.sh` has never existed (**D237**), and
`--update` re-resolves every image when it locks one package (**D238**), which
was safe on the day and is carried as an open item.

### Run 3 — The claim contract  ·  **Done.**

**Measured first, against both locked digests, with controls throughout.** Every
claim survives to `request.jwt.claims` intact, `scope` as a real JSON array and
the version claims as integers; the control confirms claims absent from the token
are absent from the payload. So the shape the contract wants is deliverable.

What the measurement changed is the *division of labour* (**D242**). PostgREST
does not check `iss` at all, and serves a token carrying no `aud`. It also
applies a **30-second leeway** on `exp` and `nbf` (**D241**), bisected — 30s
served, 31s refused — which nothing in the repository had recorded and which
`begin_rotation` takes as a caller-supplied number.

**Done:** ADR 0078 and `src/agentic_postgres/jwt_claims.py` — twelve required
claims, `verify_claims` as a pure function, `sql_required_claims()` so the hook's
half is rendered rather than restated, and the enforcement split as *data*.
Eight mutations, each red, each with a control in the same invocation.

**The vocabulary, done, and not the way D220 said** (ADR 0079, **D244**).
`$defs/scope` is referenced by exactly one place — what a *capability manifest*
may request — so adding an administrative name to it would have widened the agent
surface, which is the `admin:everything` drift ADR 0006 names. So: one authority,
two closed classes. `$defs/agent_scope` is the data class and `required_scopes`
binds to it; the administrative class is derived as the complement.

Four names, `admin_users:{read,write}` and `admin_agents:{read,write}`, split by
verb for ADR 0049's reason — a ceiling a token can hold half of is enumerable.
`scope_registry.py` maps role → ceiling, validating every name against the schema
on the way out, and refuses a role no token may name. Six mutations, each red,
including the one-word `$ref` repoint that leaves every other assertion true.

Found here: **ADR 0049 was accepted and never implemented** (**D243**). It says
Session 5 issues tokens carrying `scope` and renders the permitted names into the
hook; neither exists. Recorded rather than fixed — issuance is Run 7's, the hook
is migration 0012's.

### Run 4 — Outputs v9  ·  **Done.**  (the secret contract moves to Run 7)

**Done: the v8 fixture and the comparison it makes possible** (**D245**). The
fixture-per-version discipline had lapsed after v5 without anyone noticing, so
three migration steps were proved only against their own output. A real v8 render
is now committed — captured *before* the bump, because afterwards one cannot be
produced from this tree — and the chained v8 is compared against it structurally.
Result: identical shape. Three mutations, each red, controls green.

**Measured, and it corrects D216** — which this session wrote. The rendered
branch already carries **`routes.app`** as a derived URL (`naming.derive` has
`route_app`, and `jwt_issuer` is built from it), and on that branch `rest`, `app`,
`mcp` and `docs` are plain strings: only `health` is a status-carrying object.
Status lives on the **deployed** branch, where `routes` holds exactly `health`,
`rest` and `docs`. So v9's routes work is *deployed-branch only*, and D230's
`routes.app.status` needs no new machinery — `$defs/publishedRoute` already
forces a null URL when a route is `unavailable`, which is precisely the shape.

**Also measured, and it removes a field from the plan:** D216 proposed
`jwt.rotation_phase` (`steady`|`prepared`|`overlap`). That is **derivable** from
`verification_kids` and `retire_after`, which `validate_key_state` already
requires to agree — one key with no deadline is steady, two with one is overlap.
Adding it would be a third record of one fact, which is what ADR 0002 forbids and
what D177 punished. It is not in v9.

**Version 9, shipped.** `migrate_v8_to_v9` adds the rendered
`routes.app_docs`; the deployed branch gains `routes.app` and `routes.app_docs`
as `publishedRoute`s and `jwt.verifier_acknowledgements`. Six files, one bump,
five mutations red with controls green.

`app_docs` is in *this* bump rather than Run 10's deliberately: every version
bump costs a redeploy of every project (ADR 0053), so discovering in Run 10 that
a tenth version was needed would mean redeploying every project twice in one
session. The router and `serve.py`'s route table stay Run 10's; only the derived
URL lands here.

`verifier_acknowledgements` is the one genuinely new state — a consumer name to
the sha256 of the JWKS that consumer has *loaded*. Keyed per consumer because
propagation is per consumer: promoting on the strength of one verifier having
reloaded is promoting on an assumption about the others. Nothing else records it,
which is why it is not derivable and `rotation_phase` was.

**The four secrets move to Run 7** (**D246**): the contract refuses a grant to a
service that does not exist, and `auth` is Run 7's. Attempted, reverted, recorded.

**The materialization proof now stats every consumer** (D213), so a wrong `uid`
or `mode` there fails on the next gate rather than in Session 9.

### Run 5 — Migration 0011: the identity registry  ·  **Done.**

Five tables, one helper function, one placeholder. Created from nothing — no
backfill, `NOT NULL` from creation (D218) — and no `REFERENCES app.` anywhere,
because `app.notes.owner_id` holds a claim value that ADR 0029 calls trusted, not
authenticated.

**Every SQL construct was measured against the locked image before it was
written**, each with a control: `gen_random_uuid()` without an extension;
`normalize` and `lower` both `IMMUTABLE` (read out of `pg_proc.provolatile`) and
therefore indexable, with `Ada`/`ADA` and composed/decomposed `josé` both
colliding on the unique index; a `text[]` CHECK with `<@`; a partial unique index
for "one active X"; and `SET search_path` recorded in `proconfig`.

**Two of those measurements changed the file, and one became ADR 0080**: a CHECK
constraint passes when its expression is NULL, so the scope-shape function had to
stop being able to return one. See D248 — it is the sharper finding of the run
and it applies backwards across every migration in the repository.

**Then all eleven were applied in order to a cluster built from the locked
image**, and the catalog was read back: five tables owned by `object_owner`, two
functions in `app_private` with pinned search paths and neither `SECURITY
DEFINER`, no `PUBLIC` privilege, no function added to `api`, and `auth_service`
holding schema `USAGE` with `SELECT` and `INSERT` on `app_private.users` both
false. Thirteen behaviour checks, each refusing what it exists to refuse with a
control beside it.

The auth service's *functions* are not here. It has schema `USAGE` and nothing
else, and the definer functions it will call arrive in the same commit as the
code that calls them — D246's lesson from Run 4, applied one run later.

`auth_contract_state` seeds the required claim set, tied to
`jwt_claims.REQUIRED_CLAIMS` by a contract test rather than by a manifest
placeholder: the claim list is not a per-project value and does not belong in the
deployed document.

### Run 6 — The bootstrap plane: `auth_service`

Role attributes, connection limit, SCRAM credential, role `statement_timeout`
and the HBA rule — all in `bin/postgres-bootstrap.py`, none in a migration
(D228). **`connection_limits` re-derived for three claimants**, not extended by
subtraction (ADR 0070).

### Run 7 — The service core, before any route

**Carried in from Run 4 (D246):** the four secrets, appended to
`secrets.required.yaml` in the same commit as the `auth` compose service they
name, and the `value_kind` enum widened to admit `rsa_private_jwk` and
`public_jwks` — because ADR 0055 exists so that the kind says what the value
*is*, and declaring a JWK as a PEM would be that ADR's own defect one level in.

Hashing (the frozen Argon2id profile, NFC normalization, the offline blocklist,
dummy verification, the bounded executor whose semaphore is held until the worker
actually finishes), strict JSON, the bounded compact-JWT pre-parser, local-JWKS-only
key resolution, and the psycopg pool with `open=False` and explicit lifespan.

Every one of these is pure enough to test offline, which means **every one of them
gets a mutation battery** — with `PYTHONDONTWRITEBYTECODE=1`, `__pycache__`
cleared, snapshots to `/tmp` and `cp` restore, and a paired control in the same
invocation.

### Run 8 — Human endpoints and the local bootstrap

`/auth/login`, `/auth/me`, `/auth/jwks.json`, the admin user lifecycle, and
`bin/auth-admin.sh bootstrap` under the project advisory lock. Generic failures:
unknown, wrong, disabled and locked all return the same code and the same work
class.

### Run 9 — Agents, and migration 0012

Agent lifecycle and one-time secrets. Migration 0012 extends the pre-request hook
to compare `credential_version`, `authz_version`, role and sorted scopes against
current state, and adds `project_admin` to the authenticator's membership with
exact `ADMIN FALSE, INHERIT FALSE, SET TRUE`.

**Agent roles stay ungranted**, so an agent token fails at role switching before
the hook runs — which is why no agent-specific pre-request error code is defined.

### Run 10 — Cutover, routes, and the second documentation surface

The signing cutover. **Not under exercised machinery** — D235 measured that
there is none, so this run writes the prepare → acknowledge → promote → retire
path from nothing, including the acknowledgement `begin_rotation` has never had.
Rehearsed against a rig, with ADR 0065's warning in force: a rig is a second
configuration of the product. Traefik routers built
from `routes.app.url` with middlewares in the **file provider** (D229, closing
D202/D208). `/docs/app` as a second surface of `services/docs/` (D226).
`routes.app.status` gates publication on an administrator existing (D230).

### Run 11 — The gate, evidence, and the session close

`bin/session-06-check.sh` in `bin/session-05-check.sh`'s shape (D221), with
`--sentinel-file` in the documented command and a hard failure on stale fixtures.
Claims added to `evidence_claims.CLAIMS` (D222). Both evidence halves, merged.

---

## 6. The auth surface

Endpoints, and what each one is allowed to decide:

| Route | Decides | Never decides |
|---|---|---|
| `POST /auth/login` | Whether these credentials match, and what the server already says this subject's role and scopes are | The role or scopes themselves |
| `POST /auth/agent-token` | Whether this credential is current | The agent's authority |
| `GET /auth/me` | Whether the token still describes current state | Anything about another subject |
| `GET /auth/jwks.json` | Nothing. It publishes validated public keys | — |
| `POST /admin/users`, `PATCH /admin/users/{id}` | Role and scopes, from the registry | A scope outside the vocabulary |
| `POST /admin/agents`, `PATCH`, `rotate-secret` | Agent status, role, scopes | Whether PostgREST honours them |

**The one rule underneath all of it:** a client never submits a role or a scope.
Both are read from server-side records, sorted and deduplicated before signing,
and refused outright if the stored value is outside the committed vocabulary.

**Agent tokens are issued before agent access is activated**, deliberately.
PostgREST rejects agent roles during role switching because
`postgrest_authenticator` holds no membership in them, and that rejection is a
*tested property*, not a side effect. Session 9 activates them.

---

## 7. Evidence and claims

Claims added to `evidence_claims.CLAIMS`, resolved from registry node IDs and
JUnit results. Nothing hand-entered; a skip is not a pass.

| Claim | Requirements | Mode |
|---|---|---|
| `token_contract` | `SEC-JWT-001`, `API-AUTH-002` | host |
| `key_ownership` | `SEC-KEY-001`, `SEC-KEY-002` | host |
| `credential_storage` | `SEC-CRED-001`, `SEC-CRED-002` | host |
| `identity_endpoints` | `API-AUTH-001` | host |
| `admin_authorization` | `API-ADMIN-001`, `SEC-BOOT-001` | host |
| `token_non_resurrection` | `SEC-REV-001` | host |
| `project_isolation` | `DEP-ISO-003` | host |

`claim_mode` refuses a claim whose node IDs straddle two environments. D174
recorded that it does **not** refuse a requirement relocated wholesale into the
wrong environment — that stays a review rule, and Session 6 inherits the
question because retiring the bootstrap issuer moves `SEC-BOOT-001`'s proofs.

---

## 8. Security invariant matrix

| Invariant | Prevented by | Detected by |
|---|---|---|
| Only auth holds private signing material | Per-consumer secret materialization | Mount and image scan, every rotation phase |
| PostgREST verifies with public material only | The secret contract's consumer list | JWKS inspection + the D213 materialization proof |
| No raw credential is stored | Normalize → policy → Argon2 before any SQL | Canary scan across logs, images, evidence, process args |
| A client cannot choose its own authority | Server-side registry; no role/scope in any request model | Strict-input negative matrix |
| A disabled subject loses access immediately | Database-backed current-state check inside the request transaction | Same-token disable test |
| A re-enabled subject cannot reuse an old token | Monotonic `authz_version` | Disable→re-enable, revoke→reactivate |
| A password reset invalidates older tokens | Exact `credential_version` comparison | Same-token reset test |
| Rotation cannot open a verification gap | Promotion blocked on per-consumer acknowledgement | Recorded generation checksums |
| Agent access is not live early | No authenticator membership in agent roles | Role-switch rejection test |
| Cross-project tokens fail | Distinct key, issuer and audience | Two-project matrix |
| A proof that never ran is not a pass | Claims resolved from JUnit; skip ≠ pass | The gate, over the whole tree by marker |

That last row is Session 5's Run 10 written as an invariant. It is here because
four of that run's four findings were proofs that had never executed.

---

## 9. Risks and stop conditions

**Stop and record a divergence rather than reconciling inline** if any of these
appears:

- PostgREST does not deliver the full claim set to `request.jwt.claims`. The
  claim contract is then shaped by what the verifier can actually see, and D219's
  ADR is rewritten before the service is built on top of it.
- The Argon2id profile does not fit the derived memory budget. Reduce
  concurrency, not the profile — D234's cross-field relation exists to make that
  the only available move.
- Traefik's rate-limit middleware behaves differently against the locked digest
  than the documentation says. ADR 0019's lesson; measure before depending.
- A rotation phase cannot be resumed after an interruption. That is a release
  blocker, not a rough edge.
- **Run 10's key overlap has no live rehearsal** (D235). The two-phase functions
  Session 6 inherits have never run outside a unit test, and the acknowledgement
  step — the one that makes promotion safe — does not exist in them at all. This
  is the session's largest unrehearsed operation and it is the one that cannot be
  undone by re-running a deploy.

**The largest risk is not technical.** It is that this session's surface is big
enough for a proof to be written, registered, and never executed — and Session 5
demonstrated four separate mechanisms for that inside one run. Every run in §5
ends with the gate, over the whole tree by marker, because that is the only
selection that has been shown to reach every directory.

---

## 10. Open items carried in

Unchanged from Session 5 unless Session 6 touches them:

- `requirements-dev.in` pins nothing — has produced a red gate twice. Session 6
  adds a service dependency tree; this is the run to fix it or to say why not.
- ADR 0019's CI job is unbuilt. The runbook assumes `.github/workflows/ci.yml`
  exists and is commit-pinned. It does not exist.
- ~~`SCALAR_VERSION` named a release that never existed for four sessions
  (D201).~~ **Closed in Run 2** (ADR 0077): a package entry names its registry and
  resolves to an artifact digest, and a fictional version blocks `--update`.
- **`--update` re-resolves every image when it locks one package** (D238). Four
  image tags float, so on a day when one has moved, pinning a dependency would
  silently change what the deployment runs. Separating the two resolutions is a
  change to `--update`'s contract and has not been made.
- **The lock proves a version exists; it does not prove an installed artifact is
  that version.** ADR 0077's digest is recorded, not enforced at install time.
  `requirements-dev.in` pinning nothing is the open item that belongs with it.
- The Infisical control-plane identity holds org admin.
- Secret generations accumulate; nothing prunes them. Session 6 adds key
  generations to that pile.
- `bin/restore-test.sh` is the last `FUTURE_STUB`.
- EdDSA is unmeasured; ADR 0051's "revisit if PostgREST accepts EdDSA" is open.
- The published REST document advertises `DELETE`, `PATCH` and `POST` on both
  views and all three return **403** (ADR 0060) — recorded, not fixed.
- **Two registry properties are review rules, not tests** (D174, D175). D232
  makes Session 6 the largest instance.
- `tests/deployment/conftest.py` is ~1000 lines and is the next thing that will
  be hard to read. Session 6 adds an auth plane to it.
- **Nothing knows which proofs have never executed** (D211–D214). A run-age per
  node ID would have caught all four of Run 10's findings, and no session has
  built it.

---

## 11. Session 7 handoff

Session 7 receives a permanent FastAPI auth service at `/api/app`, outputs
schema v9, an RS256 issuer with an exercised prepare/promote/retire path, private
signing material mounted only into auth, a least-privileged `auth_service`
database role, a reviewed FastAPI OpenAPI contract on a second surface of the
existing documentation service, and reusable request-ID, strict-parser, stable-error
and pool components.

Session 7 must reuse the validated bearer dependency and the current-subject
check rather than writing a second one, require storage scopes from the committed
vocabulary, keep object-storage credentials separate from signing material, and
**not** activate agent PostgREST roles.

The open question it inherits: `SEC-BOOT-001`'s proofs move when the bootstrap
issuer retires, and `claim_mode` will not notice (D174).

---

## Appendix — what to consult, and what to measure instead

| The runbook asserts | Consult | Measure instead |
|---|---|---|
| Nine dependency versions | nothing | each registry, with a control (D201) |
| "Session 5 froze the claim contract" | `bin/dev-token.py::mint`, migration 0010 | what a token actually carries |
| `api:read` / `api:write` / `openapi:read` | ADR 0006, ADR 0049 | `schemas/capabilities.schema.json` |
| "extend `app_private.users`" | migrations 0001–0010 | the four schemas' actual contents |
| outputs v5 → v6 | `output_migrations.py` | `schema_version` in a deployed document |
| a `bootstrap_required` deployment state | D135 | `routes.*.status`, which already exists |
| Traefik rate-limit keys | ADR 0019 | the locked digest |
| PathPrefix boundaries | D162 | a request, not a config |
| a browser proof of the docs page | D142 | the bytes this deployment serves |

**And the standing question, from Session 5's last run:** when a test is green,
ask what would have to break for it to go red — and then ask whether it has run
at all, in this environment, since the thing it measures last changed.
