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
| **D251** | (D250's fix, one deploy later.) The caller was corrected and a guard added for missing keyword arguments, so v9 was complete. | **The second deploy failed too, on the layer below.** v9 added `jwt.verifier_acknowledgements` to `deployedJwt.required`. `JWT_NOT_PUBLISHED` gained it and the test fixture gained it; **`observe_jwt` -- the function the deploy calls when the issuer IS published -- did not**. Every offline test built its jwt block from the constant or the fixture, so every offline test passed, and schema validation failed on the host at step 7 for the second time in one window. | **The producer is fixed and a second guard added**: `observe_jwt` is called with a temporary JWKS and its key set compared against the schema's, and the same for the three `*_NOT_PUBLISHED` constants. Proved by three mutations, the sharpest being **M3 -- producer and constant both lose the key, so they agree with each other and not with the schema**. Then the exact document the host built was taken from its traceback, given only that key, and validated. | **Two producers of one block, and only one of them was ever exercised offline.** D250's guard reads call signatures; this is a dict key, one layer down, and the same class. What both share: **the offline suite tested the shape it constructs, not the shape the product constructs.** | **yes** |
| **D252** | (`publish_docs_credential`, since Run 9a.) "Rewritten on every deploy. bcrypt salts randomly, so the hash differs each time while the password does not; the file changes, **Traefik reloads it**, and the credential an operator holds keeps working." | **It does not reload it.** Measured on the host during the first documentation-credential rotation ever performed: the new password returned 401, the **old password returned 200**, and a wrong password 401 as the control. The htpasswd on disk was correct -- a `$2b$12$` hash that verifies against the active generation's password, written five seconds after it. The middleware names a `usersFile` **path**, so the parsed configuration is byte-identical every deploy, Traefik has nothing to reload, and the only moment it re-reads that file is when it rebuilds the middleware. | **Recovered by restarting the edge**, after which the new password opened the page and the old one was refused. `docs/api-operations.md` now carries the restart as a step. **The fix is not written yet**: inlining the hash in the middleware YAML would make the configuration genuinely change, and that is a claim about Traefik that gets measured against the locked digest before it is written down -- the last claim about this exact behaviour was an untested comment. | **Every documentation-credential rotation this project has documented would have silently failed**, with the deploy reporting success and the page still open to the old password. ADR 0019's lesson -- a configuration fact read from documentation is not a fact -- applied to a sentence in our own docstring. | **yes** |
| **D253** | (`project-runtime.sh resume`, and the whole deploy path.) A deploy materializes a new generation, the bootstrap plane sets the role's verifier from it, and the services start against it. | **PostgREST kept a generation two rotations stale and the cluster moved underneath it.** Measured: the container was created at 21:02, survived two deploys, and mounted `generations/b79c30eae78ef7b9/...` while the secrets override and the active pointer both said `f9fde25ca41f3bdc`. The bootstrap set the cluster's password from the active generation; PostgREST authenticated with the stale file; it exited 1 and crash-looped, and the REST route went to **502**. `resume` runs `compose up -d --build --wait` with **no `--force-recreate`**. | **Recovered with `project-runtime.sh down` followed by a deploy**, which creates the containers fresh; volumes are preserved by design. `docs/api-operations.md` now carries the `down` as a step for any credential a container mounts. **The fix is not written yet** -- `--force-recreate` would restart the cluster on every deploy, and the better shape is probably to make the generation part of the service's config hash. Which of those is right depends on **why** a changed secret-mount source did not already trigger a recreate, and that is measurable. | Worse than D252, because it is an outage rather than a no-op: **the documented authenticator rotation would have taken any deployment down**, at whatever hour the operator chose to rotate, with the deploy reporting success throughout. | **yes** |
| **D254** | (Implicit in five green host runs and 2 776 offline tests.) The deploy path is exercised on every run, so a defect in how it handles secrets would have surfaced. | **Every deploy before tonight materialized a new generation containing identical values**, because no secret had ever actually changed at the provider. A container holding a stale generation and one holding a fresh generation are indistinguishable when the two generations carry the same bytes. | **Recorded as the reason D252 and D253 were unreachable**, not as a separate fault. The rotation window is the only thing that could have found either, which is why "specified, implemented, tested offline, never executed" was worth treating as unproved rather than as done. | **The sharpest instance yet of this project's defect.** Not a value that looked measured and was not -- a whole *mechanism* that looked exercised and was not, because the input that would have exercised it had never varied. 148 generations had accumulated on the host; every one of them held the same credentials. | no |
| **D255** | (Run 4, this session.) v9 was chosen with the session's remaining fields in mind, so that Run 10 would not force a tenth version -- `routes.app_docs` was pulled forward precisely to avoid a second bump. | **It missed the connection budget.** D228, in the same plan, says `connection_limits` gains a third claimant; the bootstrap plane reads only the deployed document (D102, ADR 0067), so the auth service's commitment has to be a field in it. Run 6 therefore needs **v10**, one run after v9 shipped and two host redeploys later. | **v10 adds `database.auth_connection_budget`.** Both branches, a `migrate_v9_to_v10` step, and `tests/fixtures/outputs-v9.json` captured before the bump — the discipline D245 established, applied on the first opportunity. | **A version bump is planned from the session's whole surface, not from the run in front of you.** I reasoned carefully in Run 4 about which fields to carry forward, and reasoned only about the two runs I was looking at. The cost is real: two bumps in one session, and each one is a redeploy of every project. | no |
| **D256** | (Session 5, `_validate_rest_service`.) The manifest's connection-budget check runs on every project. | **It ran only for a project that declared a REST service and enabled it** — the check sat behind two early returns. Meanwhile `rendering.resolve_api_connection_budget` charges the budget *whether or not the service is enabled*, deliberately, so the bootstrap plane's division does not move when somebody toggles a flag. | **The check moves out into `_validate_connection_budget`, called unconditionally**, and covers both services. A manifest with no REST section could otherwise declare a `database.pool_size` the bootstrap plane would refuse — and the refusal would arrive on a host rather than in validation, reading as a cluster problem. | Found while adding the third claimant, not looked for. The document and the validator disagreed about when a budget is charged, and the document was right. | no |
| **D257** | (D227, and §5 Run 7 via D246.) Session 6 declares four secrets, and widens `value_kind` to admit `rsa_private_jwk` and `public_jwks` — because ADR 0055 exists so the kind says what the value *is*. | **Two of the four are not secrets, and the widening is not needed.** `jwt_public_jwks` is a stored copy of PUBLIC material that **ADR 0051 already derives**: `bin/render-jwks.py` builds the verification set from the private key at deploy time, on purpose — *one value, one derivation, and nothing that can drift from the key it claims to describe* — and writes it world-readable, because a `0400` file would imply a confidentiality the content does not have. And `rsa_private_jwk` would store a `kid` beside a key, when the `kid` this project uses is an RFC 7638 thumbprint **derived** by `jwt_keys.py`. | **Three secrets, and the enum does not widen.** `auth_service_password` (compose consumer `auth`, `pgpass`), `auth_jwt_signing_key` (compose consumer `auth`, `rsa_private_pem`) and `auth_jwt_prepared_key` (**root plane only**, never mounted before promotion). The JWKS is derived by the renderer that already derives one. | **D246 moved the widening here so it would arrive with its consumer. Arriving with its consumer is what showed it was not needed.** Both refusals are ADR 0051 and ADR 0055 *applied* rather than new decisions — which is why this is a divergence row and not a fourth ADR. | no |
| **D258** | (`versions.in.yaml`, Run 2's own note.) The Session 6 dependency set needs no build toolchain, and lists the compiled transitive packages — "argon2-cffi-bindings, cryptography, cffi, and **psycopg-binary if the C speedups are wanted**". | **`psycopg` alone does not import at all.** Measured against the locked `python:3.12-slim` digest: no libpq, no `pg_config`, no compiler, and `ImportError: no pq wrapper available` on the first import. Of psycopg's three implementations exactly one is reachable there, and it is the wheel that clause calls optional. **And `psycopg-pool` is a separate distribution at a different version** — 3.3.1 against psycopg's 3.3.4 — which the lock did not name at all. | **ADR 0083.** `psycopg[binary]` in the image, because psycopg's own metadata pins `psycopg-binary==3.3.4` exactly; `PSYCOPG_POOL_VERSION` as a lock entry, because psycopg declares the pool with no version and that makes it a real choice. | The conclusion the note reached was right and one clause inside it was a value that looked measured and was not — **§6's pattern, inside a comment written to record a measurement.** Corrected in place rather than deleted, because the sentence is otherwise the record of what Run 2 did. | **yes** |
| **D259** | (D238, carried as an open item since Run 2.) `--update` re-resolves every image as well as every package; measured immediately before Run 2's update, per image: **zero drift**, because the lock was one day old. | **Run 7 added one package entry and two images moved in the same command** — `pgvector:pg18` and `python:3.12-slim`, both to digests nobody had measured. Locking a dependency would have shipped an unmeasured PostgreSQL upgrade and a new base image for every service, inside a run about authentication. | **`bin/lock-versions.sh --update --packages-only`** (ADR 0083): resolves packages, carries every image digest forward unchanged, needs no Docker, and **refuses** to carry one forward when `versions.in.yaml` names a different tag. Both controls run — no image line moved, and editing `pg18` to `pg17` blocked with exit 5. | D238 wrote down exactly this failure and called it *safe today*. It was safe for eleven days. **The finding is not the drift — it is that the control written in Run 2 was still there in Run 7 and fired.** | **yes** |
| **D260** | (Implicit in every run of this session.) A mutation battery proves the tests it targets. | **Three of Run 7's twenty mutations stayed green, and each was a different way of measuring nothing.** (1) The executor's `asyncio.shield` removed — and **the docstring explaining why it was there had the reason backwards**: cancelling a *started* hash is harmless, and the leak is a *queued* submission whose `finally` never runs. (2) `hash_memory_budget_mb` replaced by `return 224` — the test computed the expected value from the same three constants, so it asserted `224 == 224`. (3) A compose variable renamed to one nothing emits — the test compared environment *keys* and never looked at what they interpolate. | Three new tests: the queued-cancellation case with a deliberately saturated executor; the floor's **slope** across three concurrencies, which no constant can satisfy; and every `${VAR}` the service reads checked against `COMPOSE_ENV_KEYS` and `versions.env`. | **The third one had already happened for real, minutes earlier**, and a render caught it rather than a test — I invented `AUTH_JWT_AUDIENCE` when `JWT_AUDIENCE` had existed since Session 5. D173's shape twice over: an assertion that cannot fail. **A battery is the only thing this session has that finds a tautology.** | no |
| **D261** | (§5 of this plan.) Run 9 carries **migration 0012**, which extends the pre-request hook. | **Run 8 needs a migration first, and 0011 said so.** Migration 0011 granted `auth_service` schema USAGE and nothing else, with the reason written into it: the service reaches the registry *"through SECURITY DEFINER functions that arrive in the same commit as the code that calls them, which is Run 8's"*. Run 8's code cannot call functions that do not exist. | **Run 8 is 0012 and Run 9 becomes 0013.** Twelve released migrations, `freeze-lock` re-run, and the eleventh's own test now asserts 0011's **position** rather than the total -- a test pinned to the count goes red for a migration being added, which is the one event the lock exists to record. | Mechanical, and it is here because the plan numbered Run 9's migration before Run 8's existed. The same shape as D255 one run earlier: a number chosen from the run in front of you rather than from the session's whole surface. | no |
| **D262** | (Migration 0012, and my own Run 8 measurement.) A newly created function is EXECUTABLE BY PUBLIC, and `ALTER DEFAULT PRIVILEGES ... REVOKE ... FROM PUBLIC` records nothing for functions — **a finding.** | **It is not a finding. D57 measured it in Session 3**, in more detail than I did: both inside `SET LOCAL ROLE` and with an explicit `FOR ROLE` from a superuser, with the explicit per-function `REVOKE` measured to work. Session 3 also drew the conclusion this row was reaching for — *"the explicit per-function REVOKE is what carries the requirement"* — and put it beside every `CREATE FUNCTION` in the set. My rig reproduced it on the current image, added the `ROUTINES` spelling, and called it new. | **The measurement stands and the claim of novelty is withdrawn.** 0012's comment cites D57. What is genuinely new is small and worth one sentence: the `ROUTINES` spelling behaves identically, and the behaviour still holds on `pg18`. | **The real finding is that this repository measured the same third-party behaviour twice, three sessions apart, and the second time did not know about the first.** Divergence rows are indexed by number and by session, not by subject, so nothing points from "I am about to depend on how PostgreSQL grants EXECUTE" to the run that already checked. **Every ADR is indexed in `docs/decisions/README.md`; no such index exists for the 260 measured facts in the divergence tables**, and this is what that costs. | no |
| **D263** | (Migration 0011, and every SECURITY DEFINER function in this repository.) A definer body names every object schema-qualified -- 0005: *"a caller who can create a temporary object shadows an unqualified name and executes it as the owner"*. | **`normalize(x, NFC)` cannot be schema-qualified.** The second argument is a KEYWORD in a grammar that exists only for the bare name, and `pg_catalog.normalize(x, NFC)` fails with `column "nfc" does not exist`. 0011's unique index is written in exactly that spelling, so 0012's lookup had to match it or match nothing. | **Neither.** Measured: `pg_catalog.normalize(x)` -- the one-argument form, which IS qualifiable -- equals `normalize(x, NFC)`, and the planner still uses `users_username_normalised_key` for it, against a control predicate that plans as a sequential scan. Nothing is bent and nothing is slower. | The rig built to answer the *other* question -- can `pg_temp` actually shadow an unqualified catalog call -- **could not demonstrate shadowing in either search_path order**. Its control did not fire, so it is recorded as uninformative rather than as evidence that shadowing is impossible. The decision was made on the measurement that did work. | no |
| **D264** | (Run 7, this session, `services/auth-api/app/tokens.py`.) The service's JOSE `typ` is `at+jwt`, RFC 9068's media type for an access token. | **ADR 0078 had already chosen `JWT`, eight runs earlier**, and `jwt_claims.TOKEN_TYPE` says so. Two authorities for one header field, inside one service, in one session -- written by me, in the code written to defend against exactly this. | **`tokens.TOKEN_TYPE` reads the claim contract.** The accepted ADR is the one that stays; changing the value is a decision with alternatives and would need its own. RFC 9068's argument is real and is not dismissed -- what does that work here is `token_use`, which the contract already requires, which `verify_claims` checks, and which is signed inside the payload rather than in a header PostgREST ignores entirely. | Found by writing `keys.jose_header` and having to ask which constant it should read. **Nothing would have caught it**: both spellings were internally consistent, the pre-parser accepted what the issuer produced, and the test asserting the refusals was written from the wrong constant. | no |
| **D265** | (§5 Run 8 of this plan.) *"Generic failures: unknown, wrong, disabled and **locked** all return the same code and the same work class."* | **There is no `locked` state and Session 6 does not add one.** `app_private.user_status` is `active` or `disabled`, and 0011 is released. | **The requirement is kept and the fourth word is not.** All three states that exist -- unknown, wrong password, disabled -- return the same status, the same bytes and the same Argon2 work, and the ORDER is fixed so a disabled subject costs what an active one costs. An automatic lockout is refused: with Argon2id at the frozen profile and the edge's rate limit, a per-account counter mostly buys an attacker a denial of service against a named administrator. An administrator-applied lock is `disabled`. | The underlying requirement -- every authentication failure is indistinguishable -- is the one that matters and it is fully implemented. Recorded rather than reconciled silently, because a reader comparing the plan to the code would otherwise find a state vocabulary with three words where the plan names four. | no |
| **D266** | (§5 Run 9 of this plan.) Migration 0012 *"adds `project_admin` to the authenticator's membership with exact `ADMIN FALSE, INHERIT FALSE, SET TRUE`"*. | **`GRANT role TO role` is the bootstrap plane's**, not the migration plane's (D102). `bin/postgres-bootstrap.py` already grants `anon`, `authenticated` and `api_documentation` to the authenticator with exactly those three options, and its comment already says the agent roles are Session 9's and are not granted. A fourth granted from a migration would be a second authority for role membership. | **`project_admin` joins that loop in the bootstrap plane.** The migration gives the role schema USAGE and EXECUTE on the hook, which is what a migration may do. The plane's `--check` now verifies all four memberships and the ABSENCE of both agent ones -- until this run it read one membership out of five. | Measured first: the syntax parses and records `admin=f, inherit=f, set=t`, against a control (a plain `GRANT`) that records `inherit=t`. **`INHERIT FALSE` is not cosmetic** -- without it the authenticator holds every request role's reach merely by connecting. | no |
| **D267** | (My own first draft of migration 0013.) The blanket `REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_private FROM PUBLIC` takes 0012's eight grants to `auth_service` with it, so 0013 has to restate them — *"measured by applying this file to a cluster carrying 0012 and watching the service lose its access plane"*. | **That measurement was never run.** `REVOKE ... FROM PUBLIC` removes PUBLIC's entry and leaves every named grant intact — measured, with the control being an explicit `REVOKE ... FROM <role>`, which does remove it. | **The eight restatements are deleted and the comment with them.** `test_the_service_keeps_its_access_plane_after_0013` asserts it against a real cluster, because it is a claim about PostgreSQL rather than about the file. | **A fabricated measurement in a comment is worse than no comment**: the next reader has no way to tell it from the dozens in these migrations that are real. Caught by reading the sentence back before shipping — not by a test, and nothing in the suite would have. | no |
| **D268** | (Migration 0008's own rule, applied to 0013.) A definer body names every object schema-qualified, and a placeholder is a placeholder. | **Two ways that goes wrong in one line.** `pg_catalog.current_user` is `missing FROM-clause entry for table "pg_catalog"` — `current_user` is a reserved keyword, not a function to look up, which is the same trap 0008 documents two dozen lines above for `nullif`. And `{{api_documentation}}` renders a QUOTED IDENTIFIER, so comparing it to a string compares against a column that does not exist; `{{api_documentation_name}}` exists for exactly this and 0009 already uses it. | **`current_user` unqualified, compared against the literal placeholder.** Both corrections are written into the file beside the line. | Caught by a test, on a hook that would have failed **every request**. The rule was applied to a construct instead of a name, in a file that already records the same mistake — which is what a rule reads like once it has become a habit. | no |
| **D269** | (Runs 6, 7 and 8's mutation batteries, and this one.) A battery's `expected FAIL got PASS` means the test is weak. | **It can also mean the mutation never happened.** `mutate` asserted its anchor matched exactly once and raised when it did not — **and nothing checked**. The shell carried on, the run executed against an UNMUTATED tree, the tests passed, and the battery reported a weak test. Three of Run 9's twelve did this in one invocation, two of them because I had just added a second copy of the line I was anchoring on. | **A failed mutation is now a battery failure with its own message**, and it skips the run rather than measuring an unmutated tree. The two anchors are rebuilt from lines that really are unique. | **This is the failure a mutation battery exists to prevent, occurring inside one.** Runs 6-8 used the same harness; their results stand only because every anchor in them happened to match, which is luck rather than design. After the fix, M11 and M12 stayed green for the real reason — nothing asserted the bootstrap plane's grants at all, because the catalogue rig answers membership from a fake. Three tests now do. | no |
| **D270** | (Migration 0013's first draft.) The pre-request hook is extended by copying its body forward and adding to it. | **The body it was copied from was two migrations out of date.** `CREATE OR REPLACE` replaces the WHOLE function, and the hook is now defined in four files -- 0008, 0009, 0010 and 0013 -- of which only the last one runs. Writing 0013 against 0008's text silently deleted 0010's statement-timeout carry and 0009's clause refusing the documentation role an identity. **Every request role would have run unbounded**, and a documentation token carrying a subject would have been quietly accepted. | **Rebuilt from 0010's body**, with the current-state comparison added after the two early returns and the timeout carry left where 0010 put it -- before them, because both early-returning callers can hold a connection. | Caught by seven tests, `test_the_effective_hook_is_the_last_migration_that_defines_it` among them -- which exists precisely because a function defined in four files has one definition that runs and three that read like documentation. **The test knew something the person editing the file did not**, which is the only reason this is a row rather than a deployment. | no |

| **D271** | (§5 Run 10 of this plan.) Traefik routers built from `routes.app.url` "with middlewares in the **file provider** (D229, closing D202/D208)". | **Measured against the locked Traefik, and moving a middleware closes nothing.** One upstream carrying three routes -- router and middleware both on labels; router on a label with the middleware `@file`; router, service and middleware all in the file provider -- with every route proved 200 first. Backend stopped: the label route and the `@file`-middleware route both answer **404, 19 bytes, no `RouterName` in the access log** -- Traefik's own 404, byte-identical to an unrouted hostname. Only the wholly-file-provider route answers **502 `Bad Gateway`, logged `fileroute@file`**. A router defined by a container label is withdrawn with the container whatever its middleware is doing. **And moving the router is worse:** a file-provider service addresses its backend by URL, so only by DNS, and the DNS name is the **Compose service name every project shares** -- measured with the edge on two project networks and both backends aliased alike, the name resolved to project A **ten times out of ten** and project B was unreachable by it. A file-provider router for project B would have served project B's requests from project A's container, silently. | **Routers, services and middlewares all stay on container labels** (ADR 0085). The credential middleware stays in the file provider for the reason D163 gave -- no label can carry a user list -- and no longer for the reason D208 gave. D208's trade-off is **answered rather than deferred a third time**: the 502 is genuinely the more legible failure and it is not purchasable at this price. | The plan asserted a fix in a subordinate clause, and the fix was to a component that was not the cause. **The router was never the thing that moved.** The lesson is D204's in a new place -- a design justified by a mechanism nobody measured -- except that here the unmeasured mechanism would have cost three generated files per project and bought nothing, and the *tempting* next step from there would have broken tenant isolation in the routing table. | **0085** |
| **D272** | (`docs/api-operations.md`, written in Run 1 from the host measurement.) D252's repair is `bin/edge.sh --host host.yaml restart`: the middleware names a `usersFile` path, so the parsed configuration never changes and Traefik never rebuilds the middleware that would re-read the file. | **The mechanism is confirmed offline and it admits a fix, so the repair is not needed.** Locked Traefik, `watch: true`, two bcrypt hashes for two passwords, control proving the rig tells them apart. Rewriting the `usersFile` with the definition unchanged: **old password 200, new password 401**, correct hash on disk -- D252 reproduced off-host for the first time. Changing one unrelated byte *inside the middleware's own definition* at the same time: old 401, new 200 -- so the provider is watching and the rebuild is real. The hash written **inline in `basicAuth.users`** and rewritten in place: old 401, new 200. | **The hash goes inline; there is no `.htpasswd` and no `usersFile`** (ADR 0086). The property bought is not that Traefik reloads -- it always did -- but that **the artifact a rotation rewrites and the artifact the provider parses are the same artifact**, so a rotation cannot be applied to something nothing is watching. The edge-restart step leaves `docs/api-operations.md`: an instruction whose reason has been removed is D177's shape. | D252 was diagnosed correctly from the symptom and the diagnosis was never executed against the image -- so the *repair* was chosen without measuring whether the defect had a cheaper one. Run 10's question ("has this run at all, in this environment?") applies to a written-down diagnosis as much as to a test. The fix also removes a cross-project cost nobody had priced: rotating one project's documentation password restarted every project's edge. | **0086** |

| **D273** | (`services/auth-api/app/strict_json.py`, Run 7, and its own docstring.) *"The bound comes first. The size check runs before the parse, because a parser that has already allocated the document is a parser that has already paid for it."* `MAX_BODY_BYTES` is 16 KiB and API-AUTH-002 counts an oversized body among the things refused before any domain logic runs. | **The bound comes before the parse and after the read, and the read is unbounded.** `routes.py::_body` is `parse_object(await request.body())`, and `request.body()` accumulates every byte the client sent before `parse_object` looks at the length. Measured against the locked FastAPI and Starlette with a control: a 108-byte body is read as 108 bytes; an **8 388 616-byte** body is read **in full** and then refused for exceeding 16 384 -- 8 MiB allocated to enforce a 16 KiB limit, a factor of 512, with nothing bounding it above that. | **The service keeps its bound and the edge gains the same one**, as a Traefik buffering middleware on the application router, carrying the number from `strict_json.MAX_BODY_BYTES` through `auth_limits.py` (ADR 0084) rather than from a second constant. Two enforcement points, one declaration, and the docstring now says which of them protects what. | The sentence was true about the parser and was read as being about the process -- and it is the *reason clause* that made it read that way, which is the same shape as D260's `asyncio.shield` docstring having its own reason backwards. A bound that runs after the allocation it exists to prevent is not a bound; it is a check. **And a body limit is the one API-AUTH-002 property no offline test could have caught, because every test sends a body small enough to pass.** | **no** |
| **D274** | (ADR 0061, D177, and every proof `routes.docs` has ever had.) The documentation page is published, measured and green: `observe_docs` records `ready` on a 401 with a Basic challenge, the credential tests assert 401 and 200 against the page URL, and SEC-DOCS-001 is a byte scan of the served files. | **The page does not render, and has not since Run 9a deployed it.** `index.html` references its assets relatively, and the router stripped the whole page path -- so `/docs/rest` and `/docs/rest/` both arrived at the container as `/`, indistinguishable. Measured against the locked Traefik with a control: a browser given `/docs/rest` resolves `<script src="standalone.js">` against `/docs/` and requests **`/docs/standalone.js` -> 404**, while `/docs/rest/standalone.js` -> 200. `routes.docs` publishes the slash-less form. Every existing proof passes against a blank page. | **Both surfaces strip the documentation ROOT, and the container redirects the slash-less form** with a relative `Location` (ADR 0087). One strip-prefix middleware now serves both documentation routers, because they remove the same thing. The proof this repository was missing is added: extract every `src` and `url` the markup names, resolve it, and require it to be a route -- offline against the table, and at the edge where the strip is real. | **The proof asked for the page's URL and never for what the page then asks for.** D142 refused a browser harness and the refusal was right; the cost of it was invisible until a second surface forced the question. This is Run 10's third question and the sharpest: not only *what would have to break for this to go red* and *has it run since the thing it measures changed*, but **does the proof ask for what the artifact itself asks for?** | **0087** |
| **D275** | (Implicit in every scripted edit this session has made.) A Python script that rewrites a source file by replacing an anchored block is a safe way to make a large mechanical change, because the anchors are asserted. | **It removed three functions and nothing noticed.** A pass replacing a documentation block sliced between two anchors, and the region between them also held `_service`, `_body` and `_guard`. The assertions checked that each *anchor* was found; nothing checked what came out between them. Twenty-five tests then failed with `NameError: name '_guard' is not defined` -- which is the good case, and only because those helpers are on the request path. A slice that had removed something no test exercised would have been committed. | **A scripted removal states what it removes.** The restore re-extracted the three helpers from `HEAD` and asserted each one by name before writing. The rule generalises the one D269 already forced on the mutation harness: **assert the postcondition, not the anchor.** An anchor that matched proves where the edit started, not what it did. | This is D269 outside a mutation battery, which is the part worth carrying. That finding was read as being about a harness; it is about **scripted edits in general**, and this session has made dozens. The two failures are the same sentence: *the tool checked that it could find its place, and nothing checked the result.* | **no** |

| **D276** | (`secrets.required.yaml`, Run 7, in the declaration of `auth_jwt_signing_key`.) *"exactly one service holds it, no verifier ever does, and **the JWKS every verifier reads is derived from it**."* | **Nothing derives it.** `bin/render-jwks.py` reads exactly one file, `bootstrap_jwt_signing_key.pem`, and publishes one key. The only reference to `auth_jwt_signing_key` anywhere outside `secrets.required.yaml` is `compose.yaml`'s `APG_SIGNING_KEY_FILE`. So the auth service signs with a key **PostgREST has never been given**, and Run 10 measured what PostgREST does with one: a token signed by a key outside the published set is **401**, with a published key at 200 as the control. Every token the service issues would be refused by the second verifier. | **`render-jwks.py` publishes both issuers' keys**, and the transition between them is modelled as the rotation itself: prepare publishes `[bootstrap, auth]`, promotion makes the auth service the issuer, retirement drops the bootstrap key and with it `bin/dev-token.py`. `MAX_VERIFICATION_KEYS = 2` is exactly right for that and is not raised -- two issuers during the overlap, one after, and no room for a second rotation while this one is in flight. | **D204's shape, in the file that declares the key.** A sentence in the voice of evidence describing a derivation nobody wrote, and it survived because the offline tests exercise the signer and the verifier separately -- the service's own tests verify with the key they just signed with. **The two verifiers are only two verifiers when something makes them read the same set.** ADR 0076 called the bootstrap key's rotation a cutover with no machinery to exercise; it turns out the machinery's first user is that cutover. | **0088** |

| **D277** | (This run's own tests, written and green before the battery ran.) Thirteen mutations across the run's work; the tests that assert its properties measure them. | **Two stayed green, and each is a way of measuring nothing this repository has produced before.** (1) **A source scan that asks whether a function is *mentioned*.** `test_the_key_set_names_the_auth_services_key…` asserted `"auth_key_path" in ast.dump(build)`; the mutation deleted the `keys.append` and left the call, so the builder computed the path and threw it away and the test passed. (2) **A test whose subject could not have answered.** `test_the_application_route_is_not_published_without_an_administrator` called `observe_app` against a hostname that does not resolve, so `curl` failed and the function returned `unavailable` for that reason -- it passed with the administrator gate deleted entirely. | **Both replaced by measurements.** The first builds a real two-key set from two generated RSA keys and asserts the kids, with a prepared-key case and a ceiling case as its controls; the second makes the route answer **401** -- exactly as a publishable one would -- and asserts it is *still* `unavailable`. Thirteen mutations, thirteen expected verdicts, every control green and every file byte-identical to its snapshot afterwards. | The second is D173's shape and the first is new: **an AST scan for a name is satisfied by dead code.** It is worse than a text scan, because it looks rigorous. The general rule both share is the one D260 reached from the other direction -- *the assertion has to be able to distinguish the two worlds*, and "the function is called" does not distinguish "the result is used" from "the result is discarded". | **no** |

| **D278** | (D253, and `docs/api-operations.md`.) A credential a container mounts needs `project-runtime.sh … down` before the deploy, because *"`resume` runs `compose up` without `--force-recreate`, so the container keeps the generation it started with"*. | **Measured against the locked Compose, with the container's ID as the evidence of a recreate and an unchanged `up` as the control.** A changed bind-mount **source path** — which is what a new secret generation is — **does** recreate the container, and it comes up holding the new value. What does not recreate is a mount whose **path is unchanged**: rewritten in place the container sees the new bytes anyway (same inode), and **replaced** — staged and renamed — it keeps reading the **old inode** while the host holds the new file. `--force-recreate` fixes the last case. | **The instruction stands and its reason is replaced.** `down` first is still right, but not because generations do not recreate. The confirmed stale artefact is the one at a **stable path that is replaced**: `{rendered}/jwks.json`, which `render-jwks.py` writes by `staging.replace(destination)` — the same defect ADR 0088 found from the other direction. Whether the host's two-rotations-stale PostgREST was that, or an override whose generation path had not been rewritten, is not answerable from here and is named as the check to run during the window. | **A diagnosis written from a symptom, believed for a session, and wrong about the mechanism.** The fix it prescribed happens to work, which is why nothing caught it — `down` cures both causes. D274 and D276 are the same class in other places: the *conclusion* was fine and the *reason* would have misled the next person, who would have reached for `--force-recreate` and still had a stranded JWKS. **A repair that works is not evidence that its explanation is right.** | **no** |
| **D279** | (§2 of this plan.) *"New IDs, added only where none of the five covers the claim. Prefixes are already admitted by `ID_PATTERN`; none is invented."* The six are `SEC-REV-001`, `SEC-BOOT-001`, `SEC-CRED-002`, `API-AUTH-002`, `SEC-KEY-002` and `DEP-ISO-003`. | **Three of the six already exist, at other sessions, meaning other things.** `SEC-BOOT-001` has been Session 5's since Run 8, with three node IDs and a paragraph about the temporary bootstrap issuer; `SEC-REV-001` has been a Session 9 placeholder about revocation through MCP since Session 1; `DEP-ISO-003` has been Session 3's since Run 6 and is half of `database_isolation`. The prefix was checked. The directory was not. Taken literally, and measured: `project_isolation: (DEP-ISO-003,)` resolves to `claim_session=3`, and the real `merge` then turns Session 3's evidence from exit 0 / `passed` into exit 5 / **`failed`** -- writing the failing document anyway, so nobody gets an error to investigate. `token_non_resurrection: (SEC-REV-001,)` resolves to 9 and is **silently absent** from `claims_for_mode(host, 6)`: no error, no warning, no entry, and the gate exits 0. Controls: the same claims over IDs that really are late-session move with them, and the existing claims resolve unchanged. | **Session 6 uses `SEC-BOOT-002`, `SEC-REV-002` and `DEP-ISO-006`** (ADR 0089), alongside the three that genuinely were new. `SEC-BOOT-002` is also a meaning split: `SEC-BOOT-001` is that the bootstrap *issuer* holds the only private key, and Session 6's property is that the first *administrator* is created locally and exactly once. Two tests enforce it -- one comparing every claim against the session that introduced it, one refusing a requirement named by two claims. | A claim does not declare its session; it **derives** it, as the max of its requirements'. So reusing an earlier ID does not extend a requirement -- it **relocates the claim**, forwards or backwards, and neither direction is loud. The module's commentary reaches this conclusion twice for *extending* an existing claim (D119) and nobody had asked the inverse: what happens when a **new** claim is built from an **old** requirement. **Prefix validity is not availability**, and `ID_PATTERN` answers a different question than the one being asked. | **0089** |
| **D280** | (ADR 0046, and `SEC-BOOT-001`'s proof since Session 5 Run 8.) The bootstrap issuer's expiry is enforced by `assert deployed_through_session < ISSUER_RETIRED_IN_SESSION`, with the constant at 6, *"which is what makes this expire rather than go stale"*. | **Session 6 does not retire the issuer, so the clause fires on a correct deployment.** ADR 0088 built the cutover and §4 of the operator guide forbids starting one this session: two live issuers fill the two-key ceiling, and the transition between them *is* the first rotation. Measured by calling the real test function twice with documents identical but for that field -- the session-5 arm gets **past** the clause and fails later on the filesystem, the session-6 arm fails **at** it. The control is the whole measurement: both arms fail off-host, and only *where* attributes it to the clause rather than to the fabricated document. `deploy-project.py` writes the field from `--through-session` and hard-codes `temporary: True`, so this is what the operator guide's own command produces. | **The clause is re-keyed from the session number to the event** (ADR 0090). While `temporary` is true the bootstrap key must still be published, and the `kid` is **derived on the host from the private key** rather than read from the document that claims it. Stricter in two independent ways, which is the only kind of replacement the non-negotiables permit. | `deployed_through_session` was always a **proxy** for "the retirement has happened", chosen when nothing else in the document could answer. Outputs v9 and v10 added `retire_after` and `verifier_acknowledgements`, so the thing itself became readable and nobody went back to the proxy. **A gate that goes red for a correct deployment is the failure that teaches an operator to ignore gates**, and this one would have fired during the host trip, on the deploy, with nothing wrong. | **0090** |
| **D281** | (Implicit in §7's claim table, and in every session's evidence since ADR 0025.) A claim's proofs are named by the registry, so a test asserting that a claim belongs to its own session is enough to keep the mapping honest. | **It is not, and the mutation battery is what found that out.** `test_a_claim_resolves_to_the_session_that_introduced_it` catches a claim built *entirely* from an older session's requirements -- both of D279's measured failures. Mutating `admin_authorization` to `(API-ADMIN-001, SEC-BOOT-001)`, which is D279's third mistake and the likeliest of them, left it **green**: `claim_session` is a `max()` and `max(6, 5)` is still 6. | **`test_no_requirement_is_named_by_two_claims`**, added in the same run. A requirement belongs to at most one claim -- measured true before it was asserted, across twenty-five claims and five sessions -- and it goes red on the mutation the first test could not see. Ten mutations, ten expected verdicts, both controls green, every file byte-identical afterwards. | The general rule is the one D260 reached from the other direction and D277 restated: **the assertion has to be able to distinguish the two worlds.** "The claim resolves to session 6" is true in both worlds when the mechanism computing it is a maximum. This is also the second run in a row where the battery's value was not finding a weak product test but finding a **test written minutes earlier to enforce a decision made minutes earlier**, which is when a tautology is easiest to write and hardest to see. | no |
| **D282** | (§5 Run 11 of this plan.) *"`bin/session-06-check.sh` in `bin/session-05-check.sh`'s shape (D221) ... Claims added to `evidence_claims.CLAIMS` (D222). Both evidence halves, merged."* | **The third deliverable cannot be produced by this run.** Both evidence halves require a deployment through session 6, and nothing Run 10 built has been deployed: the host is at outputs v9, at commit `34f4801`, and the trip is a human-at-a-TTY operation the assistant cannot perform (`docs/session-06-operator-guide.md` §2--3). Every Session 6 claim is `live_host`, so every one of them reads `not_run` until the trip happens. | **Run 11 ships the gate, the claims and the proofs, and stops before the evidence.** The run is marked `**Done offline.**` as Run 10 was, and nothing is written into `evidence/` claiming a host proof passed. The Session 6 host proofs are written but have **never executed in any environment** -- stated here rather than discovered later, because that is precisely the condition D211--D214 describe. | This is the honest shape of the run and it is worth writing down rather than quietly deferring: a gate whose proofs have not run is not a finished gate, and the difference between "unproved" and "proved" is the whole point of the evidence model. **The risk to name is the one Session 5 already named for `api_authorization`: an unproved claim quietly becoming an unneeded one.** Four Session 6 claims additionally need `--admin-password-file`, a value only the operator holds -- which is D213's shape arriving by design rather than by accident, and is why the flag is in the documented command. | no |
| **D283** | (`secrets.required.yaml`, Run 7, in the declaration of `auth_jwt_prepared_key`.) `required: false`, because the prepared key exists only while a rotation is in flight -- *"there is no service to name, so there is no grant to render, so there is no mount to forget to remove"*. | **Nothing in the materializer reads `required`, and the first Session 6 deploy died on it.** `bin/bootstrap-providers.py:155` is the only place in the repository that consults the field; it filters on it when deciding what to **create**, so the optional secret was correctly never created at the provider. `bin/materialize-secrets.py` then fetched every active secret anyway and called `fail(EXIT_SECRET, ...)` on the resulting **HTTP 404**, so no generation could be written and the deploy stopped at step 5 with the project already down. Session 6 is the **first session to declare an optional secret**, so the field had never been exercised by anything in four sessions of use. | **The materializer reads `required`, and only a 404 counts as absent.** `InfisicalError` now carries the HTTP `status` -- `None` when the failure was not a response -- so a timeout, a 500 or a DNS failure still fails the run. The manifest is built from what was **written** rather than from what was declared, because `write_manifest`'s own comment says a deployment must not "claim secrets are ready and name a file that does not exist". Five mutations, including the three plausible wrong fixes; the battery caught the first version of the test asserting the constructor rather than the client. | **D276's shape, in the file that declares the field.** A property stated in the contract, honoured by one of its two readers, and unexercised because the case it describes had never arisen. The rule this repository already wrote for derivations applies unchanged to declarations: *when a contract says a value may be absent, grep for the reader that tolerates it.* The sharper lesson is about **where it was found** -- offline the provider is unreachable, so every offline proof of materialization uses a fake that returns what it was asked for, and a fake never 404s. This needed the host, and it is the first thing the host trip found. | no |
| **D284** | (`docs/session-06-operator-guide.md` §2, written in Run 10.) The deploy is `down`, then `materialize-secrets.sh --session 6`, then `./deploy.sh --through-session 6`. | **Two steps are missing and both stop the deploy.** Session 6 introduces two *required* provider secrets -- `auth_service_password` and `auth_jwt_signing_key` -- and no command in this repository sets a value at the provider (D249), so `materialize` fails with `HTTP 404` before anything starts. The step that creates them is `bootstrap-providers.sh --apply`, which the guide never mentions. And `--apply` needs the control-plane credential, which `docs/provider-bootstrap.md` says is **deliberately shredded after every bootstrap** -- so a later session always finds it absent and must re-issue a Universal Auth client secret by hand. | **§2 gains the provider step, before `materialize`**, with the plan/apply pair, the credential's two-line format, and the note to keep it until *both* projects are applied rather than issuing two client secrets. The observed failure messages are quoted, so an operator who hits one can search for it. | **Run 10 wrote that guide offline, and the steps it omitted are exactly the ones that cannot be rehearsed offline.** The provider is unreachable from a checkout, so the provider step is the one nothing could have caught -- the same reason D283 survived. A guide written from a rehearsal is complete for everything the rehearsal could reach, and silent about the boundary it stopped at. **The boundary is where the guide needs the most detail and gets the least.** | no |
| **D285** | (`migrations/templates/0012` and `0013`, Runs 8 and 9, and every proof that applied them.) The thirteen released migrations apply to a real cluster -- Run 8 recorded *"twelve rendered migrations on the locked image"* and Run 9 added the thirteenth. | **0012 cannot be applied at all, and the first host deploy is what found it.** Both files place `RESET ROLE;` ABOVE their privileges block, so `REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_private FROM PUBLIC` and the `GRANT EXECUTE` statements after it run as the CONNECTED role -- `migration_user` on a host, which owns nothing, while both statements require ownership. The host failed with `permission denied for function is_scope_set (42501)`. 0011 has the same two statements in the opposite order and applies cleanly. Reproduced against the locked image with both arms: as `migration_user` it fails at 0012 line 396; as `postgres` all thirteen pass. **The superuser arm is the control and also the finding** -- a superuser bypasses the ownership check, and every offline rig applies migrations with `psql -U postgres` (`test_auth_endpoints.py:155`). | **Corrected in place, and that needed a decision** (ADR 0091): `RESET ROLE` moves to the end of the `up` section in both files, matching 0011, and `released.lock.json` is re-frozen in the same commit. Fix-forward is *impossible* here rather than merely inconvenient -- a 0014 would have to run after 0012, and 0012 cannot be applied, so no cluster can reach it. Verified before deciding: both deployed projects are at eleven migrations, so no cluster holds either file. `tests/contract/test_migrations_apply_as_the_migration_user.py` now applies the whole released set as the migration user, with the pre-state built by `postgres-bootstrap.py::build_statements`. | **ADR 0065 and 0066's class, for the fourth time, and the most expensive instance yet: it was found by a deploy that took a live project's API down.** The proofs applied the right SQL as the wrong role and reported success for a migration that cannot run. The standing question -- *what would have to break for this to go red* -- has a companion this adds: **as whom does the proof run, and is it the same identity production uses?** A rig that connects as a superuser is not a stricter test of authorization; it is a test with authorization switched off. | **0091** |
| **D286** | (The deploy's own output, and `deploy.sh --through-session 5`.) `--through-session N` deploys the project through session N, so an operator can step back to a known-good session while a later one is being repaired. | **Migrations are not scoped by session, so `--through-session 5` still applies all thirteen and still fails.** Observed twice on the host: the rollback attempt ran `migrate: the rendered set for this project (13)` and died on the same 42501. The flag holds services back -- `alpha-dev is up without postgrest` -- but the migration step is unconditional. **And the deploy printed `Applied: …0012_auth_access_plane.sql in 33ms` for a transaction that then rolled back**: `app_private.schema_migrations` was read directly afterwards and holds eleven rows, so the whole `up` is one transaction and dbmate's per-migration output is not evidence that anything was committed. | **Recorded, not changed.** Scoping migrations by session would be a new authority over which migrations are released, beside the manifest, and D102's separation of planes is what keeps that from existing. What an operator needs is written down instead: to restore service after a failed session-6 deploy, run `bin/project-runtime.sh … resume`, which starts the held-back services against whatever the cluster already has. That is in the operator guide. | Two readings that look like facts and are not. `--through-session 5` reads as *"go back to session 5"* and means *"start session 5's services"*; `Applied: …0012` reads as committed and means *"executed in a transaction whose fate you have not been told"*. **The ledger is the only statement about what a cluster has**, and it was worth reading before touching anything -- it is what established that the failed deploy left nothing half-applied. | no |
| **D287** | (`compose.yaml`, Run 7, and Run 10's rehearsal of *"the auth container's first start anywhere"* -- healthcheck green, login 200, wrong password 401, read-only rootfs, uid 65532.) The auth service's container posture is measured and starts. | **It cannot start under Compose at all.** The service declares `tmpfs: [/tmp:rw,mode=0700,uid=65532,gid=65532]`, which is a YAML **flow sequence** -- commas separate ITEMS there -- so it parses as four entries: `/tmp:rw`, `mode=0700`, `uid=65532`, `gid=65532`. Docker reads the last three as mount paths and refuses the container: `invalid mount path: 'gid=65532' mount path must be absolute`. Five services carry the flow form -- `auth` and the four `client-*` fixtures -- and `pgbouncer` writes the same options as a **block** sequence, where commas are literal, and has worked since Session 4. **`docker compose config` does not catch it**: the document is valid YAML and valid Compose, because `tmpfs` is a list of strings and four strings are as acceptable as one. Only the daemon refuses, at container-create time. | **All five rewritten as block sequences**, matching `pgbouncer`. `tests/contract/test_compose_mount_specs.py` asserts that every `tmpfs` entry is an absolute path, that no `tmpfs` flow sequence carries options, and the same for `volumes` and `secrets` targets -- the other two places a composed string reaches the daemon's parser. Mutation-tested by restoring the shipped form in one service: both assertions go red, the file comes back byte-identical. | **The fifth instance of ADR 0065/0066's class in this session, and the one that says most about the others.** Run 10's rehearsal started the auth container with `docker run` and translated flags rather than through Compose, so it measured the image, the user, the read-only rootfs and the healthcheck -- everything except the document that starts it in production. The four `client-*` fixtures carry the identical defect and have never failed, for the identical reason. **A rehearsal that reaches the same end state by another route proves the end state is reachable, not that the product reaches it.** And the offline gate's `compose config` is a validity check, not a meaning check: it answers "is this a Compose file" and was read as answering "will this start". | no |
| **D288** | (`bin/postgres-bootstrap.py`, Run 6.) The auth service's role carries its connection ceiling from Run 6 and its credential from Run 7: *"its credential is Run 7's, in the same commit as the compose service that mounts it (D246), so the role stays NOLOGIN here and carries its bound anyway -- which is the order with no window in it."* | **Nothing ever activated it.** The bootstrap applies `apply_connection_limit` for `auth_service` and prints `role NOLOGIN until session 6` -- a sentence written IN session 6, deferring the work to a run that never came. `app_runtime` and `postgrest_authenticator` are both given `apply_credential` ten lines above, in the same function. Run 7 built the service, Run 10 published it, and the role reached the host with no password at all. | **The block mirrors the other two**: if the active generation carries the credential the role gets it together with its bound; if not, the role is left NOLOGIN and the run says so. `read_postgrest_password` generalises to `read_pgpass_password(path, consumer, label)` so two roles do not become two readers of one format. A test asserts that **every role a container logs in as is a role the bootstrap calls `apply_credential` for** -- the general form, which would have failed the moment the service was written. | **D276's shape, in a comment that names its own session.** A sentence in the voice of a plan, describing work nobody wrote, and unfalsifiable from inside the file: a reader would have to know that session 6 was *this* session to see it was already overdue. **A deferral that names a session is a deferral nothing enforces** -- unlike a `future` marker, which the registry gate refuses once the session arrives. | **0092** |
| **D289** | (`compose.yaml`, Run 7.) *"PgBouncer, not the cluster directly: the auth service's queries are short and transactional, which is the shape transaction pooling is for, and the connection budget ADR 0070 divides is a budget on the pooler's side of the same arithmetic."* | **PgBouncer has never heard of the role.** Its userlist is written by its own entrypoint and holds exactly two entries, `app_runtime` and the pool admin, so the auth service is refused with `FATAL: SASL authentication failed` **before postgres is consulted** -- which means D288's fix alone would have changed nothing. Observed on the host as fourteen identical connection failures followed by `PoolTimeout: pool initialization incomplete after 15.0 sec` and `Application startup failed. Exiting.` | **The service connects to the cluster directly, as PostgREST does** (ADR 0092). The alternative -- a third userlist entry -- was rejected on cost rather than on whether it works: it would put a credential reaching the identity registry into a second container, widen the secret contract in a session where D257 declined to widen it for less, and add transaction pooling *underneath* a service that already runs its own psycopg pool (ADR 0083). A test asserts no service reaches the pooler under a role its userlist does not carry. | **Three offline proofs reported this service healthy against a real cluster, and every one of them credentialed the role itself.** `tests/contract/test_auth_endpoints.py` does it with a comment that says so: *"What the bootstrap plane does in production (D102, D246). The rig supplies it because Run 7 shipped the service with the role NOLOGIN."* The rig knew the product did not do this, wrote it down, and did it anyway. That is ADR 0065/0066's class in its sharpest form: **a rig that compensates for a gap documents the gap and hides it at the same time** -- and the comment naming the gap is what makes it look considered rather than missing. | **0092** |
| **D290** | (`tests/contract/test_environment_gates.py::consumed_variables`, and the comment directly above the loop.) *"os.environ[\"APG_...\"] anywhere in the body counts too: reading it directly is the same dependency as taking the fixture."* | **The code matches any subscript at all whose slice is a string starting with `APG_`**, not `os.environ` subscripts. It never had a false positive because no test had subscripted an `APG_`-prefixed key of anything else -- until Run 12 added a module that reads compose environment KEYS out of a parsed YAML document, which the scan then reported as consuming an environment the test never touches. | **Recorded, and the test complies rather than the check being narrowed.** The two keys are named constants in the new module, with a comment saying why they must not be inlined. Narrowing the scan to `os.environ` would need an ADR -- it is a security check -- and would have to keep catching `from os import environ` and `os.getenv`, which is more surface than the one line of constants costs. The over-breadth is a false POSITIVE, so it fails safe. | A comment that describes something narrower than the code beneath it, in a file whose whole subject is tests that declare less than they consume. It cost nothing here because the failure direction is loud -- but the reason it went four sessions unnoticed is the same reason the defects around it did: **nothing had exercised the case**. The check was written against `os.environ`, and the first non-`os.environ` subscript in the repository arrived eleven runs later. | no |
| **D291** | (`bin/postgres-bootstrap.py::build_statements`.) The database's posture is `REVOKE ALL ON DATABASE ... FROM PUBLIC` followed by an explicit `GRANT CONNECT` -- *"PUBLIC loses everything first, so a grant below is the only way any role holds anything."* | **The grant names three roles and `auth_service` is not one of them.** With D288 and D289 fixed, the service authenticated for the first time and was refused one layer later: `FATAL: permission denied for database "alpha_dev"` / `DETAIL: User does not have CONNECT privilege`. Third defect in a row from one cause -- adding a service means touching every list that enumerates roles -- and each was visible only after the previous was fixed, because each failure hid the next. | **The role joins the grant, and the class gets two proofs rather than a third patch.** `test_every_credentialed_role_can_also_connect` compares the two lists in `postgres-bootstrap.py` against **each other** -- a role given a password must be one the CONNECT grant names -- so a fourth service fails at the source rather than on a host. And `test_auth_service_reaches_its_data.py` stops checking lists altogether: it builds a cluster from `build_statements`, applies the released migrations as `migration_user`, credentials the role through the product's own `apply_credential`, and then **connects as that role and calls the functions the service calls**. All four assertions pass, which is also how it is known there is no fourth defect of this class waiting. | **The sequence is the finding, not the missing line.** Three host round trips to add three lines, because each proof stopped at the first refusal and every offline rig had supplied by hand whatever the product had failed to grant. The new module is the shape that ends it: it asks the question the lists exist to answer -- *can this role, credentialed as the product credentials it, do the work the service does?* -- and supplies nothing but a cluster. **A test that enumerates a list can only be as complete as the person who wrote it; a test that exercises the capability cannot.** | no |
| **D292** | (`bin/auth-admin.py`, Run 8, and its own docstring.) The bootstrap is *"created by a human at a terminal on the host, over the container-local privileged socket"*, and Run 8 proved it: *"an administrator bootstrapped through the same function the operator command calls."* | **The command cannot run on the host at all.** It does `sys.path.insert(..."services" / "auth-api")` and imports `app.hashing`, which imports `argon2` at module scope. `argon2-cffi` is pinned in exactly one place -- the auth service's Dockerfile -- so it exists inside that image and nowhere else. The host has no venv and its `python3` has no such package. Observed as `ModuleNotFoundError: No module named 'argon2'` at the first host bootstrap, **after a deploy that had otherwise fully succeeded**, at the last step before `routes.app` could be published. | **The screening and the hashing move inside the auth container** (ADR 0093), over `docker exec` with the password on stdin. `bin/auth-admin.py` imports nothing from `services/`. The rule generalises: an operator command reaches a service's logic by running it in that service's container, never by importing it -- with ADR 0084's seam intact, because `src/` may import pure contract facts and is used by tests, which run in a venv. | **ADR 0065/0066's class in its last hiding place: not a rig that configures the product differently, but an ENVIRONMENT more capable than either place the code runs.** Every proof of this command runs in the repository's venv, which installs the service's dependencies so the service's tests can run -- a superset of both the host and the image, in which code that works in neither works fine. Installing argon2 on the host would have been one line and the wrong one: two Argon2 builds is two answers to *what produced this hash*, which is the question ADR 0081 exists to keep singular. Running it in the container is stronger than the import ever was -- **the hash an administrator is created with is now produced by the very process that will verify it.** | **0093** |
| **D293** | (D292's fix, written minutes earlier in this same run.) `bin/auth-admin.py` finds the running auth container by Compose label and runs the hasher inside it. | **The selector matched nothing, and the command reported the service down while it was running and healthy.** It filtered on `com.docker.compose.project.working_dir=/var/lib/agentic-postgres/rendered/<key>` -- Compose's record of where it was invoked from, which is not a value this repository sets and did not hold what the fix assumed. The operator was told *"no running 'auth' container ... Deploy through session 6 first"* and did, needlessly, because the container had been up since the previous deploy. | **The selector is `apg.project.key`, a FIRST-PARTY label** declared beside every service in `compose.yaml` and carrying the same value the deployed document does (ADR 0002's direction, applied to a container query). The refusal message now names the filters it used, because a selector that matches nothing and a service that is genuinely down are indistinguishable from the caller. Two tests compare the command's selector against `compose.yaml` -- the label must be one the service declares, and its value must be the key the command passes. | **A function written in the same run that fixed a defect, and exercised by nothing.** The module's other tests build their own cluster and never call `auth_container()`, so `pytest` was green over a function that could not work. This is the run's own pattern turned on the run: seven defects were found because a proof took a route the product does not take, and the eighth was written while documenting the seventh. **The gap between "the tests pass" and "the code runs" does not close by knowing about it.** | no |
| **D294** | (`bin/dev-token.py:mint`, and its own docstring: *"the `kid` is the deployed document's active key id, so a token names the key it was signed with"*.) The identifier read from `jwt.active_kid` names the key this command signs with. | **It names the key this command does NOT hold.** `mint` has signed with `bootstrap_jwt_signing_key.pem` since Session 5. Run 10 closed D276 by publishing the auth service's key too, and `render-jwks.py:build` publishes it **first**, while `observe_jwt` takes `active_kid = kids[0]` -- so from that deploy onward every token was signed by one key and labelled with the other's identifier. Measured against the locked PostgREST with four arms: bootstrap-signed/auth-labelled is **401 `PGRST301`**; the same token labelled with its own key's `kid` is 200; with **no** `kid` it is 200; the auth key's own token is 200. **The image selects by `kid`.** Confirmed on alpha-dev through `bin/dev-token.sh` itself: 401 `PGRST301`, with an unauthenticated **200** on the same URL as the control that the route was never the problem, and Traefik's 19-byte 404 as the control for what a missing route looks like. This is why `routes.rest` was `unavailable`: `observe_served_document` could not read the document it had just published. | **The `kid` is derived from the key being signed with** (ADR 0094), through `render-jwks.py:read_public_parameters` loaded rather than reimplemented -- the reason `tests/deployment/conftest.py:jwks_command` already gives. Three tests, the isolating one handing `mint` a document whose `active_kid` is the *other* key's thumbprint; three mutations red with two controls green. Migration 0013's hook is **exonerated by the same measurement**: it raises `PT401`, which is also HTTP 401, but its body begins `AP401` and `PGRST301` is raised before a connection is taken. | **ADR 0090 asked exactly this question of the proof and not of the product, one run earlier.** It re-keyed `SEC-BOOT-001` to derive the bootstrap `kid` from the private key on disk *"rather than read it from the document that names it"*, and called that D276's question asked for the first time. The command that **signs** went on reading the document for one more run -- and that is the run in which the second key arrived. A derived value with one authority (ADR 0002) had quietly grown a second reader who could not tell the two apart while they agreed. **One function mints for every operator command**, so `bin/api.sh`, `bin/api-contract.sh`, `bin/docs.sh check` and the deploy's own observation were all refused together, which is what put `rest_surface` and `api_contract` at risk: not a broken REST surface, but every proof that authenticates to it. | [0094](../decisions/0094-a-tokens-kid-is-derived-from-the-key-that-signed-it.md) |
| **D295** | (`bin/dev-token.py:mint`, `claims["iss"] = jwt["issuer"]`.) The token's issuer claim names the issuer that signed it. | **It names the auth service, which did not.** `jwt.issuer` on alpha-dev is `https://alpha-db.agenticpostgresql.com/api/app/auth`; the signer is the bootstrap issuer, whose key is `keys[1]` of the same set. The deployed document carries **one** issuer name and there are two live issuers -- the same shape as D294, in the claim beside it. | **Recorded, not fixed in Run 13.** ADR 0078 measured that the locked PostgREST never checks `iss`, and no consumer of a dev token verifies it, so nothing rejects the claim today. The fix needs a *name* for the bootstrap issuer that the deployed document does not carry, and inventing one inside a repair is how a second unmeasured value gets published. | Found by reading the four lines below the one that was wrong, which is the only reason it was found at all -- nothing measures it and nothing would have. **The bootstrap issuer has no name of its own in the document**, and that is the gap: `jwt.issuer` was a single-issuer field that Session 6 pointed at the new issuer without asking what the old one would then be called. | no |

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

**The window was held on 2026-08-13 and is two thirds done. Session 5 stands at
17 of 18.**

- **documentation credential — rotated and proved.** Needed an edge restart that
  no procedure mentioned (**D252**).
- **authenticator — rotated and proved.** Needed a `down` before the deploy,
  after it took the REST plane down (**D253**).
- **signing key — deferred.** `bootstrap_identity` needs it and stays `failed`.

`api_authorization` is green. The host ran 162 passed / 0 failed / 4 skipped.

**Two product defects, and neither was reachable before tonight** (**D254**): a
rotated credential does not reach a running Traefik, and a rotated credential a
container mounts takes that container down. Both are fixed in the operator
documentation and **neither has a code fix yet** — each needs a measurement
first, and neither is a maintenance window's work.

**The signing key waits for those fixes.** It is predicted to fail the same way:
the JWKS is rendered to a stable path whose contents change, and PostgREST reads
it at startup — D252's mechanism in a third place. Rotating it against a deploy
that mishandles changed secrets in two known ways, as a cutover with no overlap
where a mistake refuses every token, is not a thing to do tired at one in the
morning.

D233's reason still holds in its corrected form: Session 6 replaces the signing
key's owner, and the repository has still never once replaced a signing key.

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

### Run 6 — The bootstrap plane: `auth_service`  ·  **Done.**

**`connection_limits` re-derived for three claimants**, not extended by
subtraction (ADR 0070). The division is now exact on the example manifests:
application 23, api 13, auth 6, headroom 5 — summing to 47, which is
`max_connections` 50 less the server's 3 reserved.

The chain, each link with one authority: the manifest declares `api.app`
(**new**, beside `api.rest`); `config.auth_connection_budget` computes the
commitment as pool plus reservations; the renderer publishes it; **outputs v10**
carries it to the bootstrap plane, which reads only this document (D102, ADR
0067). That last step is why v10 exists one run after v9 — **D255**, and it is a
miss of mine rather than a discovery.

**The credential is not here.** `auth_service_password` is declared in Run 7, in
the same commit as the `auth` compose service that consumes it (D246). So the
role gets its ceiling and stays `NOLOGIN` with a null verifier — which is what
`secrets.required.yaml` already says every service identity does until its owning
session activates it. `apply_connection_limit` is a new, deliberately narrow
statement: it touches neither `LOGIN` nor the password, so a role that cannot log
in may carry its bound early, and carrying it early is the order with no window
in it.

**Found on the way (D256):** the manifest's budget check ran only for a project
with an *enabled* REST service, while the document charges the budget
unconditionally. It is now its own function, called unconditionally, covering
both services.

Six mutations, each red with a control. The one worth having is **M6** — the
renderer publishing the API's figure for both services — which **stayed green**,
because everything else exercising the auth budget goes through the migration
path and nothing read what the renderer wrote. That gap is now a test.

### Run 7 — The service core, before any route  ·  **Done.**

`services/auth-api/` exists: the frozen Argon2id profile and its bounded
executor, strict request parsing, the bounded compact-JWT pre-parser,
local-only key resolution, the psycopg pool with `open=False` and an explicit
lifespan, and an `auth` Compose service on `internal` **with no Traefik labels**
— Run 10 publishes it, and `test_the_service_is_not_routable_yet` is what makes
that a property rather than a thing nobody has done yet.

**Three ADRs, each from a measurement with a control.**

- **ADR 0081** — the profile is frozen, and frozen means *checked on the stored
  hash*. `PasswordHasher.verify()` returns **True** for a hash made at a weaker
  profile; `check_needs_rehash` reports the mismatch and nothing acts on it. So
  the parameters are read back from the PHC string, by a hand-written parser
  that does not call argon2 — because asking argon2 what argon2 just did is the
  same authority twice.
- **ADR 0082** — D234's relation, computed. Measured one profile per process
  with a no-hash control: **0.0 MiB** for the control, 67.1 for one concurrent
  hash, 131.1 for two, 259.0 for four. Linear, so the floor is
  `concurrency x memory_cost + overhead` and a manifest that declares less is
  refused offline. (The first attempt at this measurement reported 87 MiB for
  every row — `ru_maxrss` is a high-water mark and the mark was already set.)
- **ADR 0083** — the lock names what it can dereference *and what is actually a
  choice*. Three findings, D258 and D259.

**Carried in from Run 4 (D246): three secrets, not four, and the `value_kind`
enum does not widen at all** — D257. `jwt_public_jwks` is a stored copy of
public material ADR 0051 already derives; `rsa_private_jwk` would store a `kid`
beside a key whose `kid` is derived. D246 moved the widening here so it would
arrive with its consumer; arriving with its consumer is what showed it was not
needed.

**D239 decided, where D239 said it would be.** FastAPI stays at 0.121.2, now
for a measured reason: the nine pinned versions **co-resolve** — which Run 2 did
not establish, having asked each registry one package at a time — and the whole
set imports. Control: `pyjwt==2.13.999` fails the same resolver.

**Twenty mutations, and D260 is the finding.** Three stayed green, each a
different way of measuring nothing: a shield whose docstring had its own reason
backwards, a floor test that asserted `224 == 224`, and a variable-name check
that never looked at variable names. The third had already happened for real
minutes earlier — a render caught it, not a test.

### Run 8 — Human endpoints and the local bootstrap  ·  **Done.**

`/auth/login`, `/auth/me`, `/auth/jwks.json`, `GET|POST /admin/users`, `PATCH
/admin/users/{id}`, and `bin/auth-admin.sh bootstrap`. **Migration 0012** is the
access plane underneath them -- eight SECURITY DEFINER functions, which is what
0011 deferred to "the same commit as the code that calls them" (**D261**: Run
9's hook becomes 0013).

**Proved against a real cluster, not a mock.** `tests/contract/test_auth_endpoints.py`
applies all twelve rendered migrations to the locked image, bootstraps an
administrator through the same function the operator command calls, and drives
the same `create_app` the container runs. Twenty-nine tests; the transport is
the only part that is not the product.

**Measured before it was written, each with a control:**

- **The bootstrap race is real.** Two connections driven through the
  interleaving by hand -- not raced by threads and hoped over: without the lock
  each reads "no administrator", each inserts, and the table ends with **two**.
  With `pg_advisory_xact_lock` the second blocks, and on retry is refused by the
  existence check, which is the line that reports something an operator can act
  on. Also measured: a **session** lock is still held after COMMIT, so through a
  transaction-mode pooler it would be stranded -- `bin/auth-admin.sh` connects
  directly and uses the transaction form regardless.
- **`auth_service` reaches nothing but its eight functions.** `SELECT` on
  `app_private.users` is `permission denied for table users`; the two bootstrap
  functions are `permission denied for function`.
- **D262 — a new function is PUBLIC-executable**, and `ALTER DEFAULT PRIVILEGES
  ... REVOKE ... FROM PUBLIC` records nothing for functions at all. **Session 3
  measured this already (D57)** and I did not know; the row is a withdrawal of
  the claim of novelty rather than a finding. The blanket revoke every migration
  in this schema ends with is the only thing that works, and it was already
  there **because D57 put it there**.
- **D263 — `normalize(x, NFC)` cannot be schema-qualified.** The qualifiable
  one-argument form is equal and still uses the unique index, against a
  sequential-scan control. The rig built to ask whether `pg_temp` can shadow an
  unqualified call **could not demonstrate shadowing at all**; its control did
  not fire and it is recorded as uninformative.

**ADR 0084** generalises Run 7's one-off: a fact both planes need lives in
`services/auth-api/app/` and `src/agentic_postgres/` imports it. Four modules
now do, because the build context cannot reach `src/` and the alternative is the
duplicate-plus-test shape D175 and D260 have both already cost this project.

**D264 is mine, from Run 7.** `tokens.TOKEN_TYPE` was `at+jwt` while ADR 0078 had
chosen `JWT` eight runs earlier -- two authorities for one header field inside
one service. Nothing would have caught it: both spellings were internally
consistent and the test asserting the refusals was written from the wrong one.

**Sixteen mutations, and M5 is the one worth having.** Removing the
`authz_version` comparison entirely left "a scope change invalidates an older
token" **green**, because the scope-list comparison below it catches a scope
change too -- so that test proved a redundant guard rather than the one it
named. The test that closes it is disable-then-re-enable: role, scopes and
status all end up identical to what the token carries, and only the version
moved. **M14 is recorded as a deliberate PASS**: dropping the advisory lock
leaves every test green, because no test in the suite drives two concurrent
bootstraps -- the property is real, the measurement is in the run log, and the
suite does not contain it.

### Run 9 — Agents, and migration 0013  ·  **Done.**

**The hook stops trusting a signature.** Until now it read `sub` and took the
rest of the token on the strength of the signature being valid. A signature says
a token was *issued*; it does not say the subject still exists, is still active,
still holds that role or still holds those scopes. From here
`credential_version`, `authz_version`, `role` and sorted `scope` are compared
against current state **inside the request's own transaction**, and any mismatch
is refused. That is SEC-REV-001's mechanism at the second verifier — the one a
request to PostgREST actually touches.

The comparison goes through a definer helper returning a **boolean** over the
whole claim tuple, never the subject's own values: a function answering "what are
X's scopes" would let any authenticated caller enumerate authority through a hook
it cannot avoid running.

**Agents**: `POST /auth/agent-token`, `GET|POST /admin/agents`, `PATCH
/admin/agents/{id}`, `POST /admin/agents/{id}/rotate-secret`. The secret is 256
bits from the OS, shown once, and there is no function in either migration that
returns it — the absence is asserted rather than trusted. Rotation moves
`authz_version`, so the replaced secret's tokens stop working, which is what
makes "rotate again" a recovery rather than a way to accumulate credentials.

**Agent roles stay ungranted**, so an agent token fails at `SET ROLE` before the
hook runs — measured, `permission denied to set role`, connected **as** the
authenticator rather than through a superuser session that would have proved
nothing.

**Three divergences from the plan's own sentence** (**D261** the number,
**D266** the membership plane, **D268** two ways one line of SQL goes wrong), and
**D267**, where I wrote a measurement into a comment that I had never run and
caught it by reading it back.

**D270**: the first draft of 0013's hook was written against 0008's body and
silently deleted everything 0010 added -- the statement-timeout carry and the
documentation-role refusal. `CREATE OR REPLACE` replaces the whole function, the
hook is defined in four files, and only the last one runs. Seven tests caught it.

**D269 is the one to carry.** Twelve mutations; three reported *"expected FAIL
got PASS"* and had **never been applied** — the harness raised on a bad anchor
and nothing checked, so the run measured an unmutated tree and read as a weak
test. Runs 6-8 used the same harness. After the fix, two stayed green for the
real reason: nothing asserted the bootstrap plane's grants at all.

### Run 10 — Cutover, routes, and the second documentation surface  ·  **Done offline.**

**Four ADRs, seven divergences, and three of them are live product defects the
suite could not have reached.** Everything below was measured against a locked
image with a control before it was implemented.

**The auth service is published.** Routers built from `routes.app.url` through
`runtime_override.py`, the boundary pair re-measured for this route
(`/api/application`, `/api/app-extra`, `/api/app2` and `/api` all 404 while
`/api/app` and `/api/app/x` serve), the service on `edge` with
`apg.traefik.scope` and `traefik.docker.network`, and `auth` added to
`POST_BOOTSTRAP_SERVICES`. `routes.app.status` needs **both** an active
administrator and a route that answers 401 (D230); a project without one gets
the bootstrap command printed and a deploy that exits 0.

**D271 — the plan's own sentence was wrong** and ADR 0085 replaces it. Moving a
middleware to the file provider closes nothing: the *router* is a container
label and is withdrawn with the container whatever its middleware is doing --
measured, byte-identical 404s. And moving the router is worse: a file-provider
service addresses its backend by DNS, and the shared Compose service name
resolved to project A **ten times out of ten** with B unreachable. D208 is
answered rather than deferred a fourth time.

**D272 — D252 is fixed** (ADR 0086). The documentation credential's bcrypt hash
moves inline into the document the file provider parses, so a rotation *is* a
change to what Traefik reads. The edge-restart step leaves the runbook.

**D274 — the documentation page has never rendered** when its URL is typed
without a trailing slash (ADR 0087). `/docs/rest` returns 200; the browser then
asks for `/docs/standalone.js`, which 404s. Both surfaces now strip the
documentation *root* and the container redirects the slash-less form relatively.
`/docs/app` is the second surface (D226): a second HTML page, a second mounted
snapshot, one image, one CSP, one credential, one strip.

**D276 is the one to carry.** `secrets.required.yaml` says of the auth service's
signing key that "the JWKS every verifier reads is derived from it", and
**nothing derived it** — `render-jwks.py` published the bootstrap key alone, so
every token the service issues would have been refused by PostgREST. The key set
now carries every live issuer, and the transition between the two issuers *is*
the cutover the four-phase machine was built for.

**The cutover exists and is unexercised.** `prepare_rotation`,
`record_acknowledgement`, `promote_rotation`, `retire_rotation` and
`abandon_rotation` replace the two functions D235 found uncalled, and ADR 0088
is why there are four: `begin_rotation` published the second key and switched
signing in one step, so nothing could check that the verifiers had it. Measured
against the locked PostgREST — a two-key set verifies both keys; `kid` selects
the key and a wrong one is refused; and **a running PostgREST never re-reads its
key set**. Worse, the deploy replaces the file rather than rewriting it, so a
container stays bound to the old inode and a `docker restart` leaves it dead.
So an acknowledgement is read from inside the container, and the operator
command is `bin/rotate-signing-key.sh`.

**D277 — the battery found two weak tests**, one of them a new shape: an AST
scan asking whether a function is *mentioned*, satisfied by code that calls it
and discards the result.

**What is left is the host.** Nothing here has been deployed: the two projects
run outputs v9 and this run needs a `down`-first redeploy (D253) to reach v10
and start `auth`. The rotation itself cannot run until the bootstrap issuer is
retired, because two live issuers fill the two-key ceiling.

### Run 11 — The gate, evidence, and the session close  ·  **Done offline.**

`bin/session-06-check.sh` in `bin/session-05-check.sh`'s shape (D221), with
`--sentinel-file` **and the new `--admin-password-file`** in the documented
command, a hard failure on stale fixtures, and a third refusal for
`--peer-project`. Seven claims added to `evidence_claims.CLAIMS` (D222). Eleven
registry entries at Session 6: the five existing ones repointed and split, and
six new IDs -- three of which are **not** the ones §2 named, because three of
§2's six already existed at other sessions meaning other things (**D279, ADR
0089**). `CURRENT_SESSION` moves to 6, which is what makes the placeholders
unable to come back.

**The evidence halves are NOT merged, and cannot be** (D282). Every Session 6
claim is `live_host` and nothing Run 10 built has been deployed; the host is at
outputs v9. The Session 6 host proofs are written and have **never executed in
any environment**, which is stated rather than discovered.

Two findings, both from measurements with controls. **D280 / ADR 0090**: the
Session 5 proof `SEC-BOOT-001` would have gone **red on the Run 10 deploy** --
its expiry clause compares `deployed_through_session` against a constant 6, and
Session 6 deliberately does not retire the issuer (ADR 0088). Re-keyed to the
event, and the `kid` is now derived from the key on disk rather than read from
the document that claims it. **D281**: the test written to enforce ADR 0089 did
not enforce the half of it that matters most, and the mutation battery is what
found that out.

---

### Run 12 — The first host deploy, and two defects only it could find  ·  **Done.**

Not planned. Run 11 handed the host trip over and the deploy failed twice, each
time on something no offline proof could have reached.

**D283 / the optional secret.** `required: false` has been in
`secrets.required.yaml` since Session 2 and Session 6 is the first session to use
it. `bootstrap-providers.py` was the only file that read the field;
`materialize-secrets.py` fetched every secret and failed the run on the 404.
Fixed so that only a **404**, and only for an optional secret, counts as absent
-- a timeout or a 500 still fails, because treating those as absent would write a
generation silently missing a secret the provider holds.

**D285 / the migration role.** 0012 and 0013 place `RESET ROLE` above their
privileges block, so the revoke and grants run as `migration_user`, which owns
nothing. Every offline rig applies migrations as a **superuser**, which bypasses
the ownership check -- so "thirteen migrations applied to a real cluster" was
true and measured the wrong thing (ADR 0065/0066's fourth instance). Corrected in
place under **ADR 0091**, because fix-forward is impossible when the broken
migration is the one that cannot apply.

**D284 / the guide.** Session 6's operator guide never mentioned the provider
bootstrap or the control-plane credential that `provider-bootstrap.md`
deliberately shreds after every use. Run 10 wrote that guide offline, and the
steps it omitted are exactly the ones that cannot be rehearsed offline.

**D286.** `--through-session 5` does not scope migrations, and dbmate's
`Applied:` line is not evidence of a commit. The ledger is.

**D287 / the tmpfs flow sequence.** With D283 and D285 fixed, the deploy reached
the auth container -- the first time anything had -- and Docker refused it:
`tmpfs: [/tmp:rw,mode=0700,uid=65532,gid=65532]` is a YAML flow sequence, so the
options parse as three extra mount paths. Five services carried it. Run 10's
rehearsal started the container with `docker run` and translated flags, so it
measured everything except the document that starts it in production.

**D288 and D289 / the auth service could not reach its database.** With the mount
spec fixed the container finally started, and failed: `FATAL: SASL
authentication failed`. Two defects at once. The bootstrap never gave
`auth_service` a password -- it printed `role NOLOGIN until session 6` in
session 6, deferring to a run that never came -- and PgBouncer, which the service
dialled, authenticates against a userlist holding only `app_runtime` and the
pool admin. The pooler refuses first, so either fix alone changes nothing. ADR
0092 connects the service directly, as PostgREST has since Session 5.

**Migrations 0011, 0012 and 0013 are applied on `alpha-dev`** -- the ledger
records thirteen. That part of the deploy is done and does not need repeating.
What remains for the project is the deferred services (`auth`, `postgrest`), the
administrator, and the second project.

**D291 / no CONNECT.** With the credential and the backend fixed, the service
authenticated and was refused one layer deeper: the database's `GRANT CONNECT`
names three roles and `auth_service` is not one. Third in a row from one cause,
each hidden by the last. `tests/contract/test_auth_service_reaches_its_data.py`
is what ends the sequence -- it builds a cluster from the product's own
`build_statements`, applies the released migrations as `migration_user`,
credentials the role through the product's own `apply_credential`, and then
connects **as that role** and calls the functions the service calls. It passes,
which is how it is known there is no fourth defect of this class waiting.

**D292 / the bootstrap could not run.** alpha-dev reached `deployed through
session 6` -- tls issued, health ready, docs ready, **app docs ready**, thirteen
migrations, the auth container healthy -- and then `bin/auth-admin.sh` failed
with `ModuleNotFoundError: No module named 'argon2'`. It imported the service's
hashing module, and `argon2-cffi` exists only inside the auth image. ADR 0093
moves the screening and hashing into the container.

**D293 / the fix's own selector.** The command that hashes in the container found it
by `com.docker.compose.project.working_dir`, which matched nothing, so it reported
the service down while it was healthy. Written in this run, exercised by no test.
Now `apg.project.key`, compared against `compose.yaml` by two tests.

**Seven of the nine defects in this run were the same class**, and Run 12's finding
is what they have in common. D283's fake never 404s; D285's rig connected as a
superuser; D287's rehearsal used `docker run` instead of Compose; D288's and
D289's rigs credentialed the role the product had not. **Every one of them was a
proof that reached the right end state by a route the product does not take.**
The standing questions gain a third: not only *what would have to break for this
to go red*, and *has it run since the thing it measures changed*, but **whose
identity, and through which tool, does the proof use -- and are they the ones
production uses?**

### Run 13 — `routes.rest`, and a label that named the wrong key  ·  **Done offline.**

Run 12 left alpha-dev converged with `routes.rest: unavailable` and no
explanation. Two candidates were on the table -- PostgREST verifying against a
key set that refuses the deploy's token, or migration 0013's current-state hook
refusing a documentation-role token -- and **neither had been measured**. Both
answer **401**: the hook raises with `ERRCODE = 'PT401'`, which PostgREST maps to
HTTP 401, so the status code cannot tell them apart. **The body can**, and that
is what the run turned on.

**Measured before anything was changed, in two places.**

*The image, because whether a `kid` selects a key or merely annotates one is a
property of PostgREST.* A throwaway rig on the locked digest with a real cluster
and a two-key JWKS built through `render-jwks.py`'s own derivation; four arms,
three of them controls:

| arm | signed by | header `kid` | result |
|---|---|---|---|
| **A** | bootstrap | **auth's kid** | **401 `PGRST301`** |
| B | bootstrap | bootstrap's kid | 200 |
| C | bootstrap | *omitted* | 200 |
| D | auth | auth's kid | 200 |

**PostgREST selects by `kid`.** B and D prove both keys verify, so the set is
sound; C proves that with no `kid` it tries every key, which is what makes A's
refusal attributable to the label alone.

*Then the deployment*, because a rig is a second configuration of the product
(ADR 0065, 0066) and arm A being the shape the product *builds* is not evidence
it is the shape the product *sends*. Run on alpha-dev through `bin/dev-token.sh`
-- the product's own command, minting as the product mints, presented to the
published route, with the operator at the terminal: **401 `PGRST301`**, the same
body as arm A. `jwt.active_kid` is `keys[0]` of the JWKS PostgREST reads.

**Two controls carried that measurement**, and the run is worth as much as they
are: the same URL with **no** `Authorization` header answered **200** with a
complete OpenAPI document -- the route is present, routed and healthy, and the
credential is what fails -- and a path no router claims answered **404 with a
19-byte body**, Traefik's own (D186). Without the first, "401" is equally
consistent with a broken route.

**D294 / ADR 0094 is the defect.** `mint` signs with the bootstrap key and
labelled the token with `jwt.active_kid`, which has named the **auth service's**
key since Run 10 published it first. One function mints for every operator
command, so `bin/api.sh`, `bin/api-contract.sh`, `bin/docs.sh check` and the
deploy's own `observe_served_document` were refused together. The `kid` is now
derived from the key being signed with. Three tests -- the isolating one hands
`mint` a document whose `active_kid` is the *other* key's thumbprint, which no
reading of the document can satisfy -- and three mutations red with controls
green either side.

**The finding is where the lesson had already been learned.** ADR 0090 changed
`SEC-BOOT-001` one run earlier to derive the bootstrap `kid` *from the private
key on disk rather than read it from the document that names it*, and called
that D276's question asked for the first time. It was asked of the **proof** and
not of the **product**; the command that signs went on reading the document for
one more run, and that is the run in which the second key arrived. Run 12's
question -- *whose identity, and through which tool* -- has a sibling: **when a
defect class is fixed, which side of the system got the fix?**

**D295 is recorded and not fixed.** The same function sets `iss` from the same
document, so a bootstrap-signed token claims the auth service as its issuer.
ADR 0078 measured that PostgREST never checks `iss` and no dev-token consumer
verifies it, so nothing rejects it -- but the bootstrap issuer has **no name of
its own** in the deployed document, and inventing one inside a repair would
publish a second unmeasured value.

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
