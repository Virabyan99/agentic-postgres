# Session 7 implementation plan — the object-storage vertical slice

> **Source runbook:** `session-07-r2-object-storage-vertical-slice-runbook-audited.md`.
> **This document is not that document.** The runbook was written against a
> repository where Sessions 1–6 had been implemented exactly as *their* runbooks
> described. They were not. Sessions 1–6 produced **98 ADRs and 306 recorded
> divergences**, and a large part of the runbook's account of "what Session 7
> inherits" is an account of a system that does not exist here.
>
> §1 is the point of this document. Everything else is downstream of it.

**What Session 7 does, in one sentence:** add one ownership-aware object
workflow — upload intent, server-generated key, short-lived presigned PUT,
completion verified against the provider, authorized presigned download,
tombstone, and idempotent cleanup — without weakening a single boundary Sessions
1–6 measured.

**What it must not do:** reinterpret an inherited contract silently. That is
CLAUDE.md §5's rule and it is why this file exists.

---

## 0. Where Session 7 actually starts

From a **closed Session 6 carrying one debt**, and that debt is the first thing
to plan around.

```
HEAD               d975800, clean, in sync with origin/main
gate               offline PASSED (x3) · host PASSED (181/0/6) · external PASSED (20/0/8)
claims             23 of 25 proved; evidence/session-07 will be the sixth document
red                api_authorization, bootstrap_identity — Session 5's, and blocked
                   ONLY on the rotation window (three APG_ROTATED_*_FROM_FILE inputs)
projects           alpha-dev and beta-dev, both session 6, outputs v10, 13 migrations,
                   an administrator on each, every route ready
ADRs               98 (0001…0098)
divergences        D1…D306.  **Session 7 owns D307 onward.**
outputs schema     v10
migrations         13 released.  **Session 7's is 0014.**
roles              `storage_service` ALREADY EXISTS in naming.ROLE_SUFFIXES
scopes             closed vocabulary, two classes (ADR 0079)
connection budget  FULLY ALLOCATED: application 23, api 13, auth 6, headroom 5 = 47
                   = max_connections 50 − 3 reserved (ADR 0070)
```

**Three facts decide the shape of this session, and the runbook knows none of
them.**

1. **The connection budget has no slack.** ADR 0070 divides 47 connections
   exactly. A storage service with its own pool cannot be added without
   re-deriving that division, and the division is published in `outputs.json`
   and read by the bootstrap plane. This is the first thing to compute, not the
   last.
2. **The scope vocabulary is closed** (ADR 0079). `storage:read` and
   `storage:write` are not a config edit; they are either an extension of the
   frozen data class (ADR 0003) or a third class, and either needs an ADR. D220
   proposed widening this surface once and D244 refused it.
3. **A bootstrap-issued token can no longer name a subject** (ADR 0095). The
   command that Session 5 and 6 used to test authenticated request paths,
   `bin/dev-token.sh`, mints **role-only** tokens. Every storage proof that
   needs an owner must authenticate as a registered subject through
   `POST /auth/login`. The runbook's whole test plan assumes otherwise.

---

## 1. Runbook divergences

Six columns, the house shape. Every row is a place where the runbook describes a
repository that is not this one. Rows are **predictions made at plan time**;
each is confirmed, corrected or replaced during implementation, and anything
found *during* implementation is appended with the next free number.

| # | Runbook says | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D307** | §10.1: "Create or activate a project-prefixed login role" `storage_service`, as though the name were new. | **`storage_service` has been in `naming.ROLE_SUFFIXES` since Session 3** and is derived for every project already, alongside `mcp_audit_service` and `backup_user`. It exists as a NOLOGIN stub with a null verifier, which is what `secrets.required.yaml` says every service identity is until its owning session activates it. | Session 7 **activates** it, in the shape Session 6 used for `auth_service`: the migration plane creates nothing, the **bootstrap plane** grants LOGIN, the credential and the `CONNECTION LIMIT` (D102, ADR 0067). Nothing is added to `ROLE_SUFFIXES`. | The role's existence is already proved by `test_only_the_activated_roles_may_log_in`, which derives the expected LOGIN set from the deployed document. **That proof will go red the moment `storage_service` logs in**, and the fix is ADR 0096's: re-derive from the event, not restate. Plan for it rather than discover it. | — |
| **D308** | §7.4: outputs schema **version 7**, additive over "v6". | Outputs schema is **v10**. Both projects are on it. v7 was Session 5's. | Session 7 publishes **v11**, and the version is chosen **once, from the session's whole surface** — the storage block, the re-derived connection budget, the route, and the provider-health field together. | **D255 is exactly this mistake**: v9 was chosen one run early with the session's remaining fields in mind and still missed the budget. A version bump is planned from the session's whole surface, not from the run in front of you. | — |
| **D309** | Adds a storage runtime with its own bounded pool and says nothing about the cluster's connection budget. | **The budget is exhausted.** ADR 0070 divides `max_connections` 50 less 3 reserved into application 23, api 13, auth 6 and headroom 5 = 47, computed in `config` and published in `outputs.json`, and the manifest check charges it **unconditionally** (D256). There is no fourth claimant. | **Run 1 re-derives the division for four claimants before any code is written**, in `config`, with the manifest bound and the document field moving together. Taking it out of headroom is not free: headroom is what an operator uses to fix a cluster that has run out. | A pool size chosen after the service is built is a number nobody computed. The division is a single authority (ADR 0002 applied to a number) and the bootstrap plane reads it from the document. | needed |
| **D310** | §4.8: "Add exact scopes `storage:read` / `storage:write`", presented as a registry edit. | **The vocabulary is closed in two classes** (ADR 0079): DATA scopes, one per frozen-domain resource and verb, closed by ADR 0003's example domain; ADMINISTRATIVE scopes over the auth service's own surface. `$defs/agent_scope` is a separate closed subset. The schema is the sole authority and `scope_registry` is a mapping onto it. | An **ADR** decides whether an object is a resource of the frozen example domain (extending the data class) or whether storage is a third class. **`agent_scope` is not widened**, which is the runbook's own "agents deferred" stated where the schema can enforce it. | D220 asked for a scope widening and **D244 refused it** because `$defs/scope` is referenced only by `required_scopes`, so a careless edit widens the agent capability surface. The same edit is available here and must be made deliberately. | needed |
| **D311** | §8.4/§8.6: a "protected broker" ingests the R2 access key over a TTY or file descriptor into an unpublished generation. | **There is no broker and there does not need to be one.** This repository has a provider (Infisical), `bin/bootstrap-providers.sh --plan/--apply`, `bin/materialize-secrets.sh`, per-consumer generations under `/var/lib/agentic-postgres/secrets/<key>/generations/<id>/<service>/`, and `secrets.required.yaml` as the contract. **D249**: no command sets a value at the provider — `--apply` creates what is missing and leaves existing values alone, so an operator-supplied value is pasted into Infisical by hand, exactly as `auth_service_password` was. | The R2 key id and secret are declared in `secrets.required.yaml` with a **new `value_kind`** — the bootstrap cannot generate them, because Cloudflare shows the secret exactly once. `--plan` names them and `--apply` refuses to invent them. The operator guide carries the Cloudflare step. | The runbook's broker would be a **second secret-delivery path** beside a working one, with its own file modes, its own ownership rules and its own bugs. **D257** is the precedent for the widening: `value_kind` was deliberately not widened until a consumer arrived. It has arrived. | needed |
| **D312** | §11: migration `0012_storage_objects.sql.tmpl`. | **Thirteen migrations are released; Session 7's is `0014`.** The naming is `migrations/templates/0014-<name>.sql`, rendered by a deliberately incapable renderer (`{{name}}` → quoted identifier or literal, no conditionals), frozen with `bin/migrate.sh freeze-lock`. | `migrations/templates/0014-object-storage-plane.sql`. **It does not touch the pre-request hook.** | **D270**: the hook is defined in four files — 0008, 0009, 0010, 0013 — and only the last one runs. 0013's body carries the statement-timeout carry, the documentation-role clause and the current-state comparison; a 0014 that redefined it from an older body would silently delete all three. **ADR 0091** applies if 0014 ever needs correcting: fix-forward unless no cluster holds it. | — |
| **D313** | §20.4 and the whole test plan assume a test token can be minted for a human subject. | **A bootstrap-issued token may not name a subject** (ADR 0095). `bin/dev-token.sh` mints `anon`, `authenticated` and `docs` tokens with **no `sub`**, because migration 0013's hook compares a subject against `app_private.users` and `auth_claims_are_current` is an EXISTS over five equalities a bootstrap token cannot satisfy. | Every storage proof that needs an owner uses the **`owner_session`** fixture — a subject created through `app_private.auth_create_user` and a token from `POST /auth/login`. `second_owner_session` exists for the cross-user half. | This is D298's whole lesson arriving in a new session. **The proofs are stronger for it**: a storage authorization test run as an identity the deployment has never heard of would be measuring nothing. | — |
| **D314** | §7.2: a parallel error vocabulary, `STOR100`–`STOR111`, several of which return a *message* to an unauthenticated caller. | The auth service already has a closed error vocabulary with a decided split (**ADR 0097**): `malformed_request` → **400, no message**, for anything refused before domain logic; `invalid_request` → **422 with a message**, for an *authenticated administrator*. An unauthenticated caller is told nothing. | Storage errors **extend `services/auth-api/app/errors.py`** in that shape. A storage-specific code is admissible where it names a *state* the caller can act on (expired intent, not-yet-visible object) and the caller is authenticated; a structural refusal stays 400 with nothing in it. | ADR 0097 was written because a duplicate JSON member in an unauthenticated login body returned the administrator-facing shape naming the duplicated field. A second vocabulary would reintroduce that, and **D264** is what two authorities for one value cost. | — |
| **D315** | §7.1: introduces `storage:` in the manifest as a new section, with a key format `objects/v1/<yyyy>/<mm>/<uuid>` and upload TTL bounded 60–900. | **A `storage:` section already exists** in `project.schema.json` and `project.example.yaml` — `enabled`, `bucket`, **`prefix`** (`objects/<key>/`), `upload_url_ttl_seconds` (bounded **60–3600**), `download_url_ttl_seconds`, `max_upload_bytes` — and the render prints it today. | Session 7 **extends** the existing section and reconciles the two key layouts into one. Narrowing a published bound is a schema change with an ADR; leaving both is two authorities for the key. | The existing `prefix` and the runbook's key template are **two derivations of the same string**, which is D177's shape. `naming.py` is the single authority for derived names (ADR 0002) and the object key belongs there or in one clearly-named module, not in both a manifest field and a service constant. | needed |
| **D316** | §23.1: `bin/session-07-check.sh --project project.yaml --peer-project tests/fixtures/projects/project-b.yaml`. | Gates take **`--mode offline\|host\|external`** plus `--host`, `--project-a-outputs`, `--project-b-outputs`, and where the claims need them `--admin-password-file`, `--sentinel-file`, `--ssh-destination`. Offline mode runs with no host and no root; host mode needs root; external mode must run off-host. | `bin/session-07-check.sh` is written in `session-06-check.sh`'s shape, with a third refusal for whatever Session 7's equivalent of `--peer-project` is. | The three modes exist because a scan run on the host measures its own routing table, and because **D213** proved that a flag mentioned under a command is a flag nobody passes. Every flag a claim depends on goes **in** the usage command, not below it. | — |
| **D317** | §6: a repository layout with `templates/compose/*.j2`, `templates/traefik/*.j2`, `versions/images.lock`, `services/app/app/`, `bootstrap/*.yaml`. | None of those paths exist. The real layout is `bin/*.sh` (operator surface) over `bin/*.py` (the work), `src/agentic_postgres/` (pure logic), `services/auth-api/app/`, one `compose.yaml` with per-session **profiles**, Traefik routers as **labels** rendered in `runtime_override.py` plus a file provider for what must come from root-owned state, `versions.env` + `versions.in.yaml`, `secrets.required.yaml`, `tests/{contract,deployment,security,external,integration}/`. | The delta is restated against the real tree in §5. **No `.j2` templates are added**; label keys are rendered in Python because Compose cannot interpolate inside a label key (ADR 0013). | A plan that names files which cannot exist produces a run that spends its first hour discovering that. | — |
| **D318** | §20 invents a fresh test inventory and §6 a fresh registry. | **Four Session 7 requirement IDs already exist** in `tests/acceptance-registry.yaml`, pointing at placeholders in `tests/integration/test_future_storage.py`: `STO-OWN-001`, `STO-KEY-001`, `STO-URL-001` (all P0) and `STO-COMPLETE-001` (P1). | Session 7 **replaces those placeholders**, keeping the IDs and their descriptions, and adds new IDs only after grepping the registry. | **ADR 0089 / D279**: three of Session 6's six "new" requirement IDs were already taken, and because `claim_session` derives from `max()`, one of them would have turned three earlier sessions' evidence red while the other vanished silently from the gate. **Before adding a requirement ID, grep the registry.** And **D175**: a dropped registry proof is caught only by generated-file drift. | — |
| **D319** | §16.1: an "exact-boundary router" for `/api/app/storage` that must not match `/api/app/storagex`. | Correct, and the reason is measured: **`PathPrefix(/api/rest)` matches `/api/restaurant`** — it is a string prefix, not a path prefix (**D162**). | The storage router uses the same construction Session 5 arrived at for `/api/rest`, and the boundary is proved by request, not by reading the label. | Traefik's own 404 and a routed 404 are identical from outside; Traefik's carries no `RouterName` and a 19-byte body (D186, D187). A boundary test that only checks the status code proves nothing. | — |
| **D320** | Treats the storage runtime as a JWT verifier without saying what that does to the key set. | **There are two verifiers today** — PostgREST, from the rendered `jwks.json`, and the auth service, from its own key. **ADR 0098**: the issuer publishes what it signs with; the verifier is configured with every live issuer's key, and `served ⊆ declared`. **ADR 0088**: after any change to the published set, every verifier must be **recreated**, not restarted. | Storage becomes a **third verifier**, and every place that enumerates verifiers moves with it: `SEC-KEY-002`'s four readings, the cutover's recreate step, and the operator guide. | **D276** is what happens when an issuer's key is not in a verifier's set: 401 on every token, invisible until something asked both. Adding a verifier without adding it to that proof recreates the gap. | — |
| **D321** | §18.1: "Add exact hash-locked versions of boto3, matching botocore." | True, and the mechanism has a trap. **D259/ADR 0083**: adding one package entry with a plain `--update` re-resolves **every image** and once moved `pgvector:pg18` and `python:3.12-slim`, which would have shipped an unmeasured PostgreSQL upgrade inside a storage session. | `bin/lock-versions.sh --update --packages-only`, and the image digests carried forward unchanged. **botocore is a separate distribution at a different version** and must be named — the exact shape of D258, where `psycopg-pool` was a separate distribution the lock never named. | The lock verifies what it can dereference; everything else in it is a comment with a colon in it (D201). | — |
| **D322** | §4.1/§12.1: one image, two runtimes, selected by `APP_MODE=storage`. | There is one service directory, `services/auth-api/`, one build context, and one image per project named `apg-<key>-auth`. **ADR 0084**: a fact both planes need lives in `services/auth-api/app/` and `src/agentic_postgres/` imports it, because the build context cannot reach `src/` and the alternative is the duplicate-plus-test shape D175 and D260 have both already cost. | An **ADR** decides between a mode flag on the existing image and a second service directory. The least-privilege boundary the runbook wants — storage holds no signing key, auth holds no R2 credential — is enforced by the **secret contract's per-consumer materialization**, which already makes "one service cannot read another's credential" a filesystem property, and is independent of which choice is made. | Choosing by habit produces either a duplicated codebase nobody keeps in step or an image whose name lies about what it runs. Both are recoverable; neither should be silent. | needed |
| **D323** | §4.21/§16.2: two CORS policies, one at the edge and one at R2. | **Nothing in this repository does CORS today.** The edge middleware surface is Traefik's, and the docs credential lives inline in the file provider (ADR 0086) after a measured failure of the label-only approach (D202, D208, ADR 0085). | The control-plane policy is a **Traefik middleware rendered from the manifest's origin list**, in the file provider where a root-owned value belongs; the R2 policy is provider configuration applied by the bootstrap. One origin list, two renderings, and a test that ties them together. | **D271/ADR 0085** is the measured lesson about where a middleware may live: moving a middleware to the file provider closes nothing if the *router* stays a label, and a file-provider service resolves its backend by DNS — which went to the wrong project ten times out of ten. | needed |
| **D324** | Starts the storage service like any other Compose service. | Services that authenticate as a **bootstrap-activated role** must be held back until after the bootstrap step, or Compose restarts them five times against a role that cannot log in — with the message `password authentication failed`, which is what a *wrong* credential gets. `runtime_override.POST_BOOTSTRAP_SERVICES` is that list and currently holds `postgrest` and `auth`. | Storage joins `POST_BOOTSTRAP_SERVICES`, and its Compose entry uses `profiles: [session7]`. | The constant's own comment records the diagnosis it exists to keep nobody from having to make. A new service that skips it produces a healthcheck failure that reads as a credential defect. | — |
| **D325** | §20 and §22 assume container-side inspection (`docker exec … cat`, shell probes). | **The locked PostgREST image is distroless** — no shell, no coreutils — and `docker exec … cat` exits 127 with `executable file not found in $PATH` (**D305**). The storage image's own hardening (read-only rootfs, uid 65532, no package manager) is the same direction. | Container-side reads use `docker cp`, measured with a control. Operator commands that need service logic run it **inside the service's container** rather than importing it (**ADR 0093**, after `auth-admin.py` imported a hasher that exists only in the auth image). | D305 was found only because D299's fix let execution reach the next line. **One unrun proof hides the next.** | — |
| **D326** | §22.1: deployment records `storage_credentials_required`, publishes no route, and prints a resume command. | The product already has a shape for this and it is **not** a special deployment state: **D230's two-stage convergence**. `routes.app` records `unavailable` with the operator command printed, and the deploy **exits 0**; a redeploy after the missing input exists observes and publishes it. `published_route` drops the URL when the status is not `ready`, so an unpublished route names nothing. | `routes.storage` follows `routes.app` exactly: `unavailable` until the credential validates, the command printed, exit 0, and `ready` on the redeploy that observes it. | A second convergence mechanism would need its own tests, its own operator documentation and its own failure modes, beside one that is deployed and proved on two projects. | — |

**Rows are added during implementation.** Next free number after the tables below
is **D391**.

### Found during Run 1

Four rows, and the first two are why Run 1 needed ADRs rather than edits. Both
were measured with a control before anything was written; neither is a runbook
conflict, which is the point — they are conflicts between the repository and
itself that a fourth claimant was the first change large enough to reach.

| # | Predicted / assumed | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D327** | D309 assumed the connection budget was one arithmetic that a fourth claimant would simply not fit into. | **There are two arithmetics and nothing compares them.** `config._validate_connection_budget` charges `database.pool_size` (20) for the application; `postgres-bootstrap.connection_limits` grants the application the *remainder*. They agreed only by coincidence — 23 against 20, three to spare — and the bootstrap's only guard was `application < 1`. Measured across storage pools 0–8 with the current tree as the control: the manifest check passes up to pool 4 while the remainder falls below the pooler's pool from pool **2** onward. | The relation `application >= database.pooler_pool_size` is checked **in the bootstrap plane**, which is the only plane that knows the live `max_connections` and `superuser_reserved_connections`. Outputs v11 publishes `pooler_pool_size` so it can. The manifest keeps its own cheaper, earlier sum. | `default_pool_size` is per `(user, database)` and `app_runtime` is the pooler's only application user, so a remainder below it is a pool the pooler cannot fill. PostgreSQL refuses the backend with `too many connections for role` and PgBouncer hands that to the client — **the message names the role, and the number that caused it was computed in a different file.** | [0099](../decisions/0099-the-budget-is-divided-four-ways-and-the-remainder-covers-the-pool.md) |
| **D328** | D310 assumed a third scope class was a schema addition plus a registry mapping. | **The administrative class was derived as the complement**, `approved − agent_requestable`, which is correct for exactly two classes and silently wrong for three. Measured with four arms and two controls: adding `objects:*` to `$defs/scope` alone turns `test_the_administrative_class_is_derived_not_listed` red; adding them to `authenticated`'s ceiling as well also turns `test_an_administrative_scope_is_reachable_only_by_the_admin_role` red. The result is not "storage is unclassified" — it is **"storage is administrative", asserted by arithmetic**. | The complement is removed. All three classes are listed in `capabilities.schema.json` and `assert_classes_partition_the_vocabulary` asserts they are pairwise disjoint and their union is exactly `$defs/scope`, raising where the registry is read. | **The misclassification would have survived its own guard.** Both tests that noticed look exactly like tests somebody would update when adding a scope. A relation that catches an *unclassified* name is strictly stronger than one that catches a duplicated one, and a complement has no notion of unclassified — every name it does not recognise is silently a member. | [0100](../decisions/0100-the-scope-vocabulary-has-three-classes-and-they-partition-it.md) |
| **D329** | — | `rendering.build_outputs` wrote `"schema_version": 10` as a **literal**, beside `deployed_output.SCHEMA_VERSION`, which is what the deployed branch and `evidence` read. Three places hold this number and only `test_current_version_agrees_with_the_renderer` tied them — a test doing the work an import does for free, and the fourth version bump to find the literal by hand. | The literal is replaced by `deployed_output.SCHEMA_VERSION`. The test stays: it now compares two authorities that cannot disagree, which costs nothing and would catch a fourth appearing. | Caught by re-rendering the fixtures and reading the version back rather than by the test, which is the order that matters: the render was the first thing to *use* the change. **A generated artifact read back is a cheaper check than the test that would eventually have failed.** | — |
| **D330** | D315 predicted the manifest's `storage.prefix` and the runbook's key template were two live derivations of one string. | **Half right, and the half that was wrong is the half that mattered.** `naming.derive` already applies both defaults — `r2_bucket(bucket or key)` and `prefix or f"objects/{key}/"` — so the manifest's values are *overrides of a derivation*, not inputs to one, and `naming` is already ADR 0002's single authority. Nothing needed fixing. What was genuinely missing was the **per-object suffix**, which no code derives because nothing had needed one. | ADR 0102 leaves the prefix where it is and puts the suffix in `services/auth-api/app/object_keys.py`, composed with the prefix in exactly one function. | **The prediction was checked by reading the deriver rather than by trusting the schema's sentence** — D276's rule run forwards. A row that had been "reconciled" without that check would have moved a working derivation to fix a problem that did not exist. | [0102](../decisions/0102-the-object-key-is-one-derivation-over-the-prefix-naming-owns.md) |

| **D331** | Run 1's last bullet: "Grep the registry, then write the Session 7 entries and claims." | **The evidence model refuses both, and each refusal is correct.** `claim_mode` raises *"has no live proof: every test it names runs in a checkout, so no deployment is being measured"* — Run 1's guarantees are the connection division and the scope partition, both proved entirely offline, so under **ADR 0045** neither is a claim. Separately, `test_every_later_requirement_has_a_placeholder` requires a requirement above the gate's session to exist as a `future` marker, and `CURRENT_SESSION` is still 6 — but these proofs already *run*, so marking them `future` would have been false. | The entries and the claims are **removed**, with the reasoning left in both files. **The tests stay**: they are ordinary suite properties now and become registry requirements in the run that has a deployment to measure them against and that moves `CURRENT_SESSION`. | The registry's model assumes a session's requirements are proved against that session's *deployment*. Run 1 is offline by design, so it produces guarantees that are real and not yet claimable. **Writing them anyway would have made two claims that report `not_run` forever** — which is D211–D214's condition manufactured deliberately, and the plan's own §2 warns against a claim that quietly becomes an unneeded one. | — |

| **D332** | — | **The mutation battery found a field no proof could distinguish from a constant.** M7 replaced the renderer's `int(project["database"]["pool_size"])` with a hard-coded `20` and the whole suite stayed green: nothing asserted `database.pooler_pool_size` at all, and both fixtures declared 20 anyway, so even a test that read it would have agreed with the constant. This is the field the bootstrap plane **refuses a deployment over**. | `project.second.example.yaml` drops to `pool_size: 16`, and four tests now read the published field against its manifest and against the other project's. M7 goes red. | **The pair of fixtures was the actual defect.** Two fixtures that agree on a value cannot prove the value is read — the same reasoning ADR 0070's own budget test states ("the inequality is what does the work"), applied to a field added one run earlier without it. It is also the second time this session that a *difference between the fixtures* was what made a proof possible, the first being the storage budget. | — |

**Predictions confirmed as written:** D307 (`storage_service` is in `ROLE_SUFFIXES`),
D308 (outputs is v10, Session 7 publishes v11), D309, D310, D312 (thirteen
migrations released), D315 in part (the `storage:` section exists with the bounds
listed), D318 (four `STO-*` ids already exist, pointing at
`tests/integration/test_future_storage.py`), D322.

### Found during Run 2

Four rows. **D333 is a live product defect** — the first one this session that
was not a conflict between the plan and the repository but a conflict between an
ADR and its own implementation.

| # | Predicted / assumed | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D333** | ADR 0055: "every secret declares its `value_kind`, and bootstrap generates accordingly", implemented and settled since Session 5. | **It was half implemented, and the missing half is the one that runs on a new project.** `generate_secret_value` had exactly ONE caller — `add_missing_secrets`, the converge path. `apply()`'s fresh-bootstrap loop called `secrets.token_hex(SECRET_ENTROPY_BYTES)` inline, correct in Session 2 when the sentinel was the only declared secret and hex was genuinely what it was. Measured with a control, one contract, one process: the fresh path produced **64 characters of hex** for `bootstrap_jwt_signing_key`; the converge path a PKCS#8 PEM. | `apply()` goes through the generator, and `generate_secret_value` now takes the **secret** rather than its kind, so the origin question is askable at the one place a value is created. A behavioural regression test drives the real fresh-bootstrap branch and reads what came out. | **It never fired because both live projects were bootstrapped in Session 2** and reached every later credential through the converge path. A project bootstrapped from scratch today would store a hex string as its RSA signing key, every check here would pass, and the failure would surface as a JWKS derived from something that is not a key — which is ADR 0055's own opening paragraph, describing itself. *When a decision is implemented, ask which of its callers got the implementation.* | [0103](../decisions/0103-where-a-value-comes-from-is-not-what-kind-of-value-it-is.md) |
| **D334** | D311: the R2 pair are declared with a **new `value_kind`**, because the bootstrap cannot generate them. | **`value_kind` cannot answer that question, and the R2 secret access key is the proof.** Cloudflare's documentation defines it as the SHA-256 of the API token's value — a 64-character lowercase hex string, byte-indistinguishable from `secrets.token_hex(32)`. So `value_kind: random_hex` is **true**, and spelling it `operator_supplied` would make the contract stop describing the value *and* would silently forbid a future operator-supplied credential from ever being written in `pgpass` format, because that rule is keyed on `value_kind == "random_hex"`. | A separate required field, **`origin: generated \| operator_supplied`**, orthogonal to `value_kind`. Eleven existing secrets gained `origin: generated` — a fact that was already true and nowhere stated. | Two questions were being asked of one field, and one of them was being answered by omission. This is ADR 0055's argument for why `value_kind` exists at all, applied one level out. **Read from the vendor's documentation, not measured against a live account**, and recorded as such. | [0103](../decisions/0103-where-a-value-comes-from-is-not-what-kind-of-value-it-is.md) |
| **D335** | Run 2's first bullet: declare three secrets. Run 7 adds the `storage` service. | **The service has to exist several runs earlier than the plan puts it.** `test_every_consumer_names_a_real_compose_service` refuses a compose-plane grant to a service `compose.yaml` does not have (D246), and — the part the plan missed — `bin/postgres-bootstrap.py` recovers a role's password from the *consumer* when it activates it, so **Run 4's activation of `storage_service` needs the declaration too**. Deferring to Run 7 would have blocked Run 4. | The Compose entry lands in **Run 2**, with the three declarations. Measured first: a control (clean tree, 3166 passed) against a probe (the service plus the three secrets), and the probe's only failure was `test_every_required_secret…can_be_recorded_as_managed` — the test that exists to be answered when a secret name is added. It is inert meanwhile: `profiles: [session7]`, and `project-runtime.sh` selects `--profile session<n>` only up to `--through-session`. | The alternative was declaring the R2 pair root-plane "for now", which is against precedent — `auth_jwt_prepared_key` shows this repository promotes by declaring a *second secret*, not by moving a consumer's plane — and would have committed to an unmeasured claim about Cloudflare's permission model that Run 5 is the run to measure. | — |
| **D336** | `bin/bootstrap-providers.sh --help`: "`--plan` … Contacts the provider read-only and writes nothing." | **`--plan` contacts nothing.** `describe_plan` reads the committed contract and the local state file and returns; there is no `ControlPlane` on that path and there never has been. The sentence has been wrong since Session 2. | The help text is corrected to say what it does. **The behaviour is kept**, and it is the better one: `--plan` needs no credential and no network, which is what makes it safe to run anywhere. | Recorded rather than fixed-by-implementing, because the documented behaviour is the worse of the two. It also explains a cost accepted deliberately in ADR 0103: the operator-supplied list prints unconditionally, done or not, because this command genuinely cannot know. | — |

**Also found, and closed in the same commit:** the two example fixtures agreed on
four of the eight storage variables published this run — `memory_limit_mb`, both
TTLs and `max_upload_bytes`. That is **D332 recurring one run after it was
recorded**, and the rule it produced ("when you add a published field, make the
fixtures disagree about it") was applied on the day the fields landed rather than
in the run that would have discovered why. `project.second.example.yaml` now
differs on every one.

### Found during Run 3

| # | Predicted / assumed | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D337** | 0014 grants `storage_service` EXECUTE on its seven functions, which is what the plan's "a grant only to `storage_service`" describes. | **All seven grants were unreachable.** The role had EXECUTE and no `USAGE ON SCHEMA app_private`, and PostgreSQL refuses the call with `permission denied for schema app_private` *before* it looks at the function's ACL. 0011 granted this to `auth_service` in the migration that created the registry, one file before the functions arrived; storage has one file for both, and the line was simply absent. | `GRANT USAGE ON SCHEMA app_private TO {{storage_service}};` beside the revoke, with the reason written where the grant is. | **Caught offline by a test that CALLED a function rather than one that read `pg_proc.proacl`** — the ACL was correct and an ACL test would have stayed green. This is D288/D289/D291's class exactly: *adding a service means touching every list that enumerates roles, and nothing enumerates the lists.* The difference is that this time it cost a test run instead of a host deploy. | — |
| **D338** | Run 3's exit criterion names "the lease claim under concurrency" as though the mechanism were settled. | **Neither mechanism had ever been measured here** — nothing under `docs/`, `migrations/`, `src/` or `tests/` mentioned `SKIP LOCKED` at all. Both were measured on the locked pg18 digest with controls that fired: two claimants with `SKIP LOCKED` take different rows while the same query without it blocks until `lock_timeout` kills the second; and a plain CAS lease under READ COMMITTED produces exactly one winner, because the re-check runs against the new row version. | Both, doing different jobs. The **lease predicate is correctness** — the provider DELETE happens outside the transaction, and a row lock is released at COMMIT and at crash. **`SKIP LOCKED` is throughput** and nothing else. | The battery confirms the ADR rather than contradicting it: removing `SKIP LOCKED` left every test **green**, which is what ADR 0104 says it should do, and is recorded as a deliberate expected-PASS rather than pretended away. Removing the lease predicate went red. **The dangerous half is the one no offline test would notice**, because no offline test spans two transactions with a network call between them. | [0104](../decisions/0104-the-lease-is-the-correctness-mechanism-and-the-row-lock-is-not.md) |
| **D339** | §4 item 1 treats bucket-name collision as an operator-review stop, and ADR 0102/D330 settled the prefix derivation as "nothing needed fixing". | **The bucket is the only derived identifier in this project with no namespace.** Every Traefik router, middleware and database role carries `apg-`/`apg_` — `apg_fixture_alpha_dev_storage_service` — while `naming.storage_bucket_name` returns the bare project key: `alpha-dev`, `beta-dev`. Read from the live Cloudflare account (read-only, no mutation): it already holds six unrelated buckets, `items`, `photos`, `pictures`, `cursor-clone-files`, `note-app-marshal-images`, `vector-attachments`. None collides today. | **Namespaced: the derived name is now `apg-{project_key}`.** An explicit `storage.bucket` override is used **verbatim** and is not prefixed — the override exists so an operator can point at a bucket named by a convention that is not ours. The object-key prefix is unchanged: it is scoped by a bucket this project already owns. | The collision domain for a bucket name is the whole account, and `alpha-dev` is exactly what a human names something else in a shared account. A collision is a hard stop by design, not a silent overwrite — so this is an operational trap rather than a security hole. **It cost nothing to change and could not have been changed after a bucket held objects: R2 has no rename.** D330's prediction was checked by reading the deriver; it was never checked against a real account. | [0105](../decisions/0105-the-bucket-carries-the-namespace-every-other-derived-name-carries.md) |

**D339's second half is the one to carry.** Both fixtures declared `bucket` and
`prefix` as *exactly what the derivation produced*, so **no fixture exercised the
derivation at all** — changing it would have left the whole suite green.
`project.example.yaml` now declares neither and takes both derived names, while
`project.second.example.yaml` overrides both. That is **D332's rule for the third
time this session**, in its sharper form: a fixture that restates a default
cannot prove the default is read.

**And the finding's provenance matters.** D333 was found by running a code path
nobody had run; D339 by listing an account nobody had listed. Both were invisible
to a green suite, and both were about a value that looked settled.

**The Run 3 battery: 13 mutations, 0 unexpected, 0 battery failures, three
controls green.** M2 is a deliberate expected-PASS and is the one worth reading.

### Found during Run 4

| # | Predicted / assumed | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D340** | Cross-project isolation is "a role cannot reach a peer project's database", full stop. | **Every service role can connect to the `postgres` maintenance database**, and always could. `build_statements` issues `REVOKE ALL ON DATABASE … FROM PUBLIC` on the **project** database only, so the maintenance database keeps PostgreSQL's default PUBLIC CONNECT — `app_runtime`, `postgrest_authenticator`, `auth_service` and `storage_service` alike. Measured: the role connects, reads `pg_database`, and is still refused every project table. | **Recorded, not fixed.** Session 7 did not introduce it and Run 4 does not close it: the change touches every role in every session. `test_the_maintenance_database_is_reachable_by_every_service_role` asserts the CURRENT state, so a later session that closes it turns the test red and the fix is to invert it. | Found by writing an isolation test that asserted more than the product ever claimed. The exposure is catalog metadata — database and role names — and **not** project data, which the peer-database test proves separately against a database that exists rather than an absent one. A refusal against an absent database would have passed for the wrong reason. | — |
| **D341** | The LOGIN-set proof is a host proof, so its clauses can only be exercised on a host. | **Every clause is a pure function over a dict**, and the mutation battery proved nothing was exercising them: mutating any one left the whole offline suite green, because the test lives in a module gated on `APG_LIVE_HOST`. "The suite cannot drive this" was never true; only "nothing had" was — D211-D214's condition, produced by where a function happened to live. | The derivation moves to `deployed_output.activated_login_roles`, the host test calls it, and a **decision table over synthetic documents** drives it offline. Several of those documents cannot exist on any single deployment, which is exactly why a host could not have tested them. | It also removed a second authority: the bootstrap decides which roles are credentialed and this test independently re-derived the same set, agreeing only by careful writing (D264's shape). **The battery's real find was not a weak test — it was a testable thing nobody had put anywhere testable.** | — |
| **D342** | The reach test credentials the storage role "through the product's own `apply_credential`", as its docstring said. | **The product's DECISION was never exercised.** The fixture called `apply_credential` directly, so a mutation removing the credential logic entirely — the `materialized_secret_path` check and both branches — left every test green. That is D288/D289/D291's mistake **inside the module whose docstring says it does not make it**: a rig reaching the right end state by a route the product does not take. | `activate_storage_service` is extracted so the decision is reachable, the fixture writes a generation where the materializer writes one, and the product is asked to find it. M2 and M3 now go red. | The docstring was true about the *ALTER ROLE* and false about the *decision*, and the decision is the part that has failed before. **A claim that a rig uses the product's code has to name which part.** | — |

**The Run 4 battery: 7 mutations, 0 unexpected, 0 battery failures, three
controls green** — after two false starts whose only finding was that the
battery's own anchors go stale when the code under them is refactored mid-run.
Grep every anchor before starting; the battery is ten minutes and a grep is a
second.

**The battery's own finding.** M3 — recording operator-supplied secrets in
`managed_resources` — stayed **green** on the first run.
`test_an_operator_supplied_secret_is_never_recorded_as_ours` was asserting on
`generated_provider_secrets`, the helper the state document is built *from*,
rather than on the document `apply()` builds. An assertion about a function
wearing the name of an assertion about behaviour (D173's shape). It now captures
the real document. Second run: **10 mutations, 0 unexpected, 0 battery failures,
three controls green.**

### Found during Run 5

| # | Predicted / assumed | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D343** | §3's feasibility table lists "Account id, jurisdiction" as operator input, so the value has somewhere to go. | **Nothing in the repository accepts either, and nothing could.** The `storage` service is handed a bucket, a prefix and two credential files and has **no way to know where the bucket is**: no endpoint and no account id in `compose.yaml`'s eight `STORAGE_*` variables, none in `rendering.py`, and `schemas/project.schema.json`'s storage block is `additionalProperties: false`, so an operator could not supply one even by hand. Four runs built the storage plane past this row. | **ADR 0106.** `storage.account_id` (required when enabled, no default) and `storage.jurisdiction` become manifest fields; `naming.storage_endpoint_url` is the one derivation; `STORAGE_ENDPOINT` is rendered and handed to the container finished. Not published in `outputs.json` — that document names what a deployment *exposes*, and this is where one container dials **out**, like `APG_DATABASE_HOST`. | D276's shape from the other side. There, a declaration said the JWKS was derived from a key and nothing derived it; here, a plan says a value is an operator input and nothing reads it. **A plan's input table is not an interface — grep for the reader.** | 0106 |
| **D344** | "Freeze one addressing style" is done by setting `s3={"addressing_style": …}`. | **The config key is not honoured for every bucket name.** Measured with one client configuration: `apg-session7-r2-probe` presigns virtual-hosted, `apg.dotted.probe` silently presigns **path** — botocore falls back when the name is not a usable TLS hostname label, with no warning and a perfectly valid URL. The deciding input is `storage.bucket`, which ADR 0105 uses **verbatim** and the schema bounds only at 3–63 characters. | **ADR 0107: freeze `path`**, the only style botocore always actually emits, and refuse `auto` although it resolves to path today. The test presigns against a dotted and a plain bucket and reads the URLs; asserting the config key would pass in exactly the case the ADR exists to prevent. | Both styles work against R2 — a presigned PUT under each returned 200 with bytes sent — so this is chosen for invariance, not capability. *A value that looked configured and was not*, which is this repository's pattern with the polarity of D192 reversed: there a rig set what the product did not, here the product sets what the library ignores. | 0107 |
| **D345** | `retries={"max_attempts": 3}` means three attempts. | **It means three RETRIES.** Measured at client construction across N = 1, 2, 3, 5, which resolve to `total_max_attempts` 2, 3, 4, 6 — botocore adds one, though the AWS documentation calls the key "the maximum number of attempts". The adapter was silently buying four tries, up to 60s of read timeouts inside a request holding a connection from ADR 0099's budget. | The constant is now `TOTAL_ATTEMPTS = 3` with `_BOTOCORE_MAX_ATTEMPTS` **derived** from it, and the test asserts `total_max_attempts` on the **resolved client** rather than the key that was set. | Found only because the first draft of the test read back the key it had just set, got a `KeyError`, and the fix was to look at what botocore had actually stored. A test that had asserted `config.retries["max_attempts"] == 3` would have been a tautology (D173) **and** would have agreed with an adapter sending four requests. | — |
| **D346** | `DeleteObject` is idempotent on an absent key (ADR 0104 inherits this from the S3 documentation), and a presigned `If-None-Match: *` gives first-write-wins. | **Both true, and now measured against R2 rather than inherited.** Absent-key DELETE returns **204**, identical to deleting a present key, with no `DeleteMarker` and no `VersionId`; the control deleted a real key and `HeadObject` then returned 404. The condition lands in `X-Amz-SignedHeaders`, first write 200, second **412 PreconditionFailed**, with two controls: the same key presigned *without* the condition overwrites at 200, and a caller that **omits** the header gets **403 SignatureDoesNotMatch** rather than an unconditional write. | Recorded; ADR 0104's cleanup design stands unchanged, now on measurement. The omit-the-header arm is the one that matters — it makes the condition cryptographic rather than cooperative, which is the only kind of enforcement worth anything against the holder of a bearer credential. | Three more R2 facts fell out and are in `storage_client.py` beside the code that depends on them: **`HeadObject` returns no checksum of any kind** (so completion cannot verify a provider-computed digest, whatever §8's matrix implies — only `ContentLength` and an ETag measured equal to the body MD5); a mutated key and a mutated signature are **both** 403 `SignatureDoesNotMatch`, indistinguishable to the caller, which is the wanted shape; and `HeadBucket` on a bucket that does not exist returns **403, not 404**, so "absent" and "not in your token's scope" are one answer. | — |
| **D347** | An Object Read & Write token can create the bucket, so one bucket-scoped credential does everything (§3). | **It cannot.** Measured: `CreateBucket` **403 AccessDenied**, `ListBuckets` **403**, `HeadBucket` on an unrelated bucket in the same account **403**, and the R2 REST API refuses the same token outright (`10000`). Bucket creation *did* succeed — through the Cloudflare REST API, which is how the probe bucket exists. So §4 is right that the bootstrap needs a separate credential and §3's assumption is wrong. | Recorded. Run 5's adapter holds the Object R&W token and never creates a bucket, so nothing here is blocked. **Which kind the second credential is — an R2 Admin S3 token via `CreateBucket`, or a Cloudflare API token with R2 write via REST — is unmeasured and belongs to Run 8**, with the bootstrap that needs it. | **The control did not fire, and the honest half of this row is why.** The second token issued as the Admin arm turned out to be behaviourally identical to the first — same refusals, same scope — so the pair discriminated nothing. Recorded as UNINFORMATIVE for the admin arm rather than reported from the arm that did run, which is Session 6 Run 9's rule about a mutation without its control, applied to a credential. | — |

**The Run 5 battery: 9 mutations, 0 unexpected on the second run, 0 battery
failures, both controls green and every file restored byte-identical.**

**The battery's own finding, and it is D260 happening again to me.** M9 removed
`asyncio.shield` from `BoundedR2._run` and **every test stayed green** — including
the one written minutes earlier whose docstring said it covered exactly that
case. The test used `concurrency=1`, so its second caller blocked on the
*semaphore* rather than on the executor, and nothing was ever queued: the leak
needs a **thread pool smaller than `concurrency`**, which is what
`BoundedHasher`'s own test does and says it does. The identical mistake, in the
identical shape, one file away from the module that records having made it
first. *Reading how a prior test solved a problem is not the same as reading
that it had the problem.*

### Found during Run 6

| # | Predicted / assumed | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D348** | Migration 0014 gives the endpoints everything they need; Run 6 is "the endpoints" and adds no schema. | **Completion could not be written.** It must ask the provider how many bytes arrived before moving an object to `available`, and to ask it needs the key — which 0014 exposes only through `storage_lookup_for_download` (`state = 'available'`) and `storage_claim_cleanup_batch` (`state = 'tombstoned'`). **The pending state completion operates on was the one state with no reader.** Returning the key from the intent and having the client hand it back is refused by STO-KEY-001, whose entire content is that no client-supplied key reaches a presign. | **Migration 0015**, `storage_completion_key(uuid, uuid)`. Not an edit to 0014: ADR 0091's three conditions were checked rather than assumed, and **condition 2 fails** — 0014 applies perfectly well, and the ADR says in as many words that "a migration that merely did the wrong thing does not qualify". | Found by writing the completion path and having nowhere to get the key from. Nothing offline could have found it earlier: every Run 3 test calls the functions that exist. **A plane is complete when a caller can be written against it, not when its tests pass.** | — |
| **D349** | 0014's comment: the compare-and-set "is what makes completion idempotent". | **True of the function and false of the path through it.** The endpoint reads the key first, and the first `storage_completion_key` filtered on `state = 'pending'` — so a retried completion 404'd *before* reaching the CAS that provides the idempotency. Caught by `test_completion_is_idempotent`, which failed on its first run. | 0015's predicate is `pending OR available`. Tombstoned stays excluded: completing one would resurrect it, and the state machine is one-way. | **A claim about a component is not a claim about the path through it.** The comment was accurate and the property was absent, which is a sharper version of D267 — there the measurement was fabricated, here it was real and about the wrong scope. | — |
| **D350** | `APP_MODE` selects the mode, and the auth service is unaffected by Run 6. | **Adding the mode check would have broken the running auth container.** The entrypoint is `--factory app.main:create_app`, called with no arguments, so `create_app` reads `APP_MODE` from the environment — and the `auth` Compose service did not set it. A required mode with no default is right (ADR 0055's reasoning applied to behaviour), but it makes the variable load-bearing for a service that already exists. | `APP_MODE: auth` on the auth service, and `test_the_compose_service_supplies_every_setting_the_service_requires` is now parametrised over **both** services. | The test was comparing only `auth` against `REQUIRED_VARIABLES`, so the eight `APG_STORAGE_*` variables the `storage` service sets had been checked against **nothing at all** since Run 2. Parametrised rather than unioned: one combined list is satisfied by a compose file that hands every variable to both services, which is the boundary ADR 0101 rests on. | — |
| **D351** | Storage mode reuses `settings.load`, which requires `APG_SIGNING_KEY_FILE`. | Storage holds **no** signing key, so `load` could not run at all in that mode. Making the field optional is not enough: a container that had somehow been handed a key would then start normally and hold one. | `load(mode=...)`, and in storage mode the variable must be **absent** — present is a refusal to start, not an ignored value. `Settings.signing_key_file` is `Path \| None`, and `FORBIDDEN_VARIABLES` states the rule so a compose test can assert the file never presents it. | ADR 0101 says one image, two modes, and the boundary is the secret contract's per-consumer materialization. That is only a boundary if something refuses when it is crossed — otherwise it is a description of what the file happens to say today. Storage is a third **verifier** (ADR 0098) and never an issuer. | — |

**The Run 6 battery: 11 mutations, 1 stayed green — and that one is a
deliberate no-op control.** Both controls green, every file restored
byte-identical.

**Three of the four the battery caught first time round were gaps in tests
written minutes earlier**, which is the same finding Run 5 had and a different
mechanism each time:

* **M1** — every download test asserted a *refusal*, and none asserted that an
  owner can download at all. Breaking the owner filter so `lookup_for_download`
  matched nothing left the suite green. *A surface tested only through what it
  denies is one nobody has checked answers.*
* **M4** — replacing `uuid.uuid4()` with a constant stayed green, because
  nothing asserted two intents get different keys. A fixed uuid4-shaped string
  is a well-formed one, so `is_derived_key` still matched; ADR 0102's
  "independent random values" was a claim with no test.
* **M11** — mutating the **real** repository's ownership filter changed nothing,
  because the endpoint suite replaces that module wholesale with a fake. The SQL
  is proved against a cluster in `test_storage_plane.py` and the callers are
  proved nowhere. `tests/contract/test_storage_repository.py` now records the
  statement and the parameters, because the ownership filter *is* an argument
  and swapping two `uuid`s is a type-correct mistake no signature catches.

**And the battery lied once, in my own tooling.** The patch script that added the
repository module to the battery's suite printed success without checking that
its replacement had matched, so M11 stayed green a second time for a reason that
had nothing to do with the code. That is D269 exactly — "a mutation that cannot
be applied is a battery failure" — reproduced one level up, in the script
maintaining the battery rather than in the battery itself. The harness's own
anchor check is what makes the battery trustworthy; the script editing it had no
such check.

### Found during Run 7

| # | Predicted / assumed | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D352** | The storage router is the same construction as every route before it, with the boundary proved by request (D319). | **It is the first route published INSIDE another one**, and the plan does not mention that at all. `/api/app/storage` lies under `/api/app`, which the auth service has served since Session 6 Run 10, so every request to the storage surface matches **two** routers. No request has ever matched two before — every route so far is a sibling — so no ordering has ever been measured. | Measured on the locked Traefik and read back from its own API: **the default priority is the rule string's length, exactly** (`priority=68` for a 68-character rule, `priority=84` for an 84-character one). The storage rule is the application rule with `/storage` inserted into both matchers, so it is exactly sixteen characters longer for every project and every domain — correct by construction. **ADR 0108**: the ordering is derived and no `priority` is pinned anywhere. | **Priority is length, not specificity**, and that is the trap. With a control: a router ruled ``PathPrefix(`/api/app/deep`)`` is *strictly more specific* than the application router and **loses to it**, at 50 characters against 68. A storage rule written the concise way — one `PathPrefix`, which is what anyone reaching for brevity writes — would be shorter than its parent's and would never match a request, with a 404 from the auth service as the only symptom. | **0108** |
| **D353** | D319: the boundary is proved by request, and D162's shape applies — a sibling path answers 404. | **A sibling of a NESTED path is not a 404.** Measured: `/api/app/storagex`, `/api/app/storage-extra` and `/api/app/storage2` all reach the **application** backend, because the parent router catches them. `/api/application` is the control at 404, Traefik's own. | The boundary proof is a claim about **which service answered**, never about a status code. Offline: the rule shapes and the interpolated rule lengths. On the host: `RouterName` from the access log. | This is D186 and D187 arriving through a door the existing tests do not cover. A sibling reaches FastAPI, which answers 404 for a path it does not serve — and from outside that is byte-for-byte the same 404 as Traefik's for a route that does not exist. Every previous boundary test in this repository asserts a status code, and every one of them is about a *sibling* route. | 0108 |
| **D354** | D323: the CORS middleware belongs in the file provider, "where a root-owned value belongs". | **The origin list is not a root-owned value.** It is `storage.allowed_cors_origins` — a manifest field, rendered into `compose.env` and published in `outputs.json`. ADR 0086's rule for the file provider is about where a **secret** may go (an inline bcrypt hash), and ADR 0085 already measured that the file provider buys nothing for lifecycle. | **ADR 0109**: a container label on the `storage` service, with the origin list reaching it as one comma-separated `compose.env` value. Measured: Traefik parses a comma-separated label into a list, read back from its own API as `['https://a.example', 'https://b.example']`. | And splitting them costs something measured: a router referencing a middleware defined **elsewhere** goes `status=disabled` with `middleware "…" does not exist` when that definition goes away, and the route answers Traefik's own 404. A label on the storage container has exactly the router's lifetime; a file-provider document is a second artifact with a second one. | **0109** |
| **D355** | §4.21/§16.2: "two CORS policies" — the edge one being a policy that decides who may reach the storage surface. | **The edge CORS middleware does not refuse anybody.** Measured with controls: a request from an unlisted origin is **forwarded to the service and answered normally**, with only `Access-Control-Allow-Origin` withheld; the preflight is answered by Traefik itself (200, no ACAO) and never reaches the container. What refuses the page is the browser. | Recorded in ADR 0109, in `naming.storage_cors_middleware_name`'s docstring, in `_storage_labels`, and in the operator guide's §5.1 — every place a reader could otherwise infer an access decision from an allowlist. It is attached unconditionally, because an empty list was measured to parse to `None`, leave the middleware `enabled`, and permit nothing. | An allowlist reads like a control and is not one. `curl` is unaffected in both directions, and a caller that sends no `Origin` header is indistinguishable from a server-side client — which is a legitimate and supported way to use this API. Every claim this project makes about who may reach the storage surface rests on the bearer token and the ownership filter, and the documentation now says so where the allowlist is. |  0109 |
| **D356** | A browser uploads an object: it calls the storage surface, then `PUT`s to a presigned R2 URL. | **The login that produces the token is not reachable cross-origin.** `/api/app/auth/login` carries no CORS middleware and there is no `api.app.allowed_cors_origins` field, so a browser-only flow — log in from a page, then upload — is not possible today. | **Recorded, not fixed.** A second origin list is a manifest change and a decision about the *auth* surface, not the storage surface. The alternative reading is that the application logs in server-side and hands the browser a token, which needs no CORS on `/auth` at all. | Neither reading is Run 7's to choose, and choosing by habit would publish a cross-origin login surface nobody asked for. Named here so the next session decides it deliberately rather than discovering it from a browser console. | — |
| **D357** | — | The deploy's closing summary printed five routes by hand and **`rest` was not one of them** — the one route Session 5 was entirely about. Nothing noticed for two sessions, because a missing line looks exactly like a route that does not exist. | The summary is derived from `document["routes"]`, so a sixth route is printed by existing. | Found while adding `storage` to the list, which is the same edit that would have perpetuated it. **A hand-maintained list of a derived thing is a list that is one addition behind.** | — |

**The Run 7 battery: 15 mutations, both controls green, every file restored
byte-identical.** After the fix below, none survived.

**M8 survived the first round, and it is the finding to carry.**
`test_the_router_names_the_port_the_container_binds` compared `compose.yaml`'s
`APG_LISTEN_PORT` against `runtime_override.STORAGE_SERVICE_PORT` — **two
constants, neither of which is what the router publishes.** Pointing the label
at `REST_SERVICE_PORT` (3000, against the container's 8080) left it green: the
two constants still agreed, and the thing under test was never read.

That is D173's tautology and D260's `224 == 224`, in a test written specifically
to prevent a routing defect — and the reason a reader would not catch it either
is that `AUTH_SERVICE_PORT` and `STORAGE_SERVICE_PORT` hold the same number, so
naming the wrong one renders identically today. The comparison is now against the
**rendered label**.

**M4 was added because M3 was not enough.** M3 makes the router name a middleware
it does not define; M4 leaves the definition in place and drops it from the
chain. The first version of the middleware test asserted only the first
direction, so a defined-but-unattached CORS middleware — a policy that exists,
parses, and is applied to no request, which Traefik reports as `enabled` — would
have been green. *An assertion that every name resolves is not an assertion that
every definition is used.*

---

### Found during Run 8

| # | Predicted / assumed | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D358** | Run 8 writes the cleanup worker against the plane migration 0014 released in Run 3. | **0014's claim collects an object whose presigned upload URL is still live.** `storage_tombstone` moves a PENDING object deliberately, and a tombstone does not revoke the presigned PUT minted for it — a presigned URL is a bearer credential and nothing in this system can withdraw one. So DELETE at T+10, cleanup at T+11, and a PUT at T+20 lands bytes under a key whose row is already `cleanup_completed_at` and will never be returned again. Section 4 forbids an orphan scan, so nothing would ever find them. Measured on the locked pg18 digest with two controls that came out the other way: an expired intent is claimed, a completed object is claimed. | **Migration 0016, ADR 0111.** The claim gains a fourth argument and the predicate `completed_at IS NOT NULL OR intent_expires_at < now() - grace`; the three-argument form is DROPPED rather than overloaded, and a contract test calls it and requires the call to fail. | **D348, a second time in one session, and the rule it produced was exactly right.** *A plane is complete when a caller can be written against it, not when its tests pass.* Every Run 3 test called the claim with an object it had tombstoned a moment earlier and got it back — which is the behaviour that is wrong, asserted as if it were the requirement. Five runs and two test modules covered this plane and none of them could see it, because none of them was a caller. | 0111 |
| **D359** | `tests/contract/test_cli_contract.py` covers the operator command surface, so adding a command to `bin/` brings it under nine checks. | **Its two lists are hand-kept and twelve commands had accumulated outside them** — `bin/auth-admin.{sh,py}`, `bin/rotate-signing-key.{sh,py}`, `bin/session-06-check.sh`, `bin/apg-diag.sh`, `bin/app-contract.{sh,py}`, `bin/deploy-project.py`, `bin/migrate.py`, `bin/render-jwks.py`, `bin/render-secret-override.py`. None was checked for a CRLF, for a working `--help`, for the executable bit in the git index, or by `test_no_command_documents_a_secret_argument` — the check that enforces D105. | All twelve listed, and `test_every_command_in_bin_is_covered_by_this_module` derives the expectation from the directory in both directions. | **Every one of them passed all nine checks the moment it was listed, and that is the uncomfortable half**: nothing was wrong, so nothing ever drew attention to the omission across two sessions. D175's shape — a property kept by review rather than by a test — and D211's from the other side: not a green test measuring nothing, but a suite of green tests measuring a set nobody had stated the boundary of. | — |
| **D360** | (`bin/apg-diag.sh`, found while closing D359) A command absent from the list is an oversight. | **One of them was absent for a real reason that had never been written down.** `apg-diag.sh` runs as `/usr/local/bin/apg-diag` under a `NOPASSWD` rule over that exact path (ADR 0071) and must NOT resolve a repository root — a `BASH_SOURCE`-derived `ROOT_DIR` would point at `/usr/local`. It failed the preamble check on its first listing. | `INSTALLED_COMMANDS`, a named exemption from **one** of the nine checks, guarded by a test asserting the repository names an absolute installed path for it somewhere other than the exemption list. | **An exemption that is written down is a decision; an omission is not.** Out of the list it escaped the other eight checks too, for a reason that only ever applied to one. The guard's first version asserted `provision-host.sh` installs the file — it does not, ADR 0071 records that the copy is placed by hand — and the premise was corrected rather than the assertion loosened. | — |
| **D361** | D347 left open which kind the bucket-administering credential is, and Run 8 would measure it. | **It is decided without that measurement, on different grounds, and the capability question is left open on purpose.** An R2 Admin S3 token would be *interchangeable with the runtime's at every call site* — same protocol, same endpoint, same botocore client, same four method names — so the only thing keeping them apart would be which file a process read. | **ADR 0110.** The credential is a Cloudflare API token used against the REST API, held by a human, and no process in this repository holds it. `bin/storage-admin.sh` has **no bucket-administering verb** — not one that refuses, none — and a contract test walks its AST and its container programs for an administering call. | This project withholds a capability by making it **unreachable**, not by scoping it: per-consumer materialization is what makes "the auth service cannot read the R2 credential" a filesystem property. The storage image contains no code that can speak the Cloudflare REST API, and the network-name scan makes adding one a test failure. Deciding on structure also avoids issuing an account-wide admin token to answer a question whose answer would not change the design. | 0110 |
| **D362** | ADR 0111's grace is a number the run produces. | **It is REASONED and not measured, and it says so where it is defined.** `WRITE_GRACE_SECONDS = 60` is twice the largest signature leeway this project has measured in any validator — PostgREST's thirty seconds on `exp` and `nbf`, D241. R2's own tolerance for a just-expired presigned URL is unmeasured: Run 5 established that an expired URL is refused (`ExpiredRequest`, 403) and not where the boundary sits. | Recorded, with the rig that would replace it written down at the constant: presign with a short `ExpiresIn`, PUT at increasing delays past it, control being the same PUT before expiry at 200. A contract test refuses a value at or below thirty. | The asymmetry decides the direction. Too generous costs a delay before bytes stop being billed; too small orphans an object nothing will ever find, because there is no orphan scan by design. **An unmeasured value that errs toward the recoverable failure, and names its own replacement, is not the same thing as a value that looked measured and was not.** | 0111 |
| **D363** | §5 Run 8: "R2 permission changes are eventually consistent, so revocation is polled within a bounded window." | **True as an instruction and unmeasured as a fact** — this repository has never timed one. So the window is a bound chosen rather than a bound measured. | `confirm-revoked` reports **three** outcomes, not two: `revoked`, `not_observed` (still accepted after N seconds — explicitly *not* "the revocation failed"), and `control_failed`. It never declares a credential revoked without having watched the refusal happen. | **The poll carries its own control**: the LIVE credential is probed in the same iteration. Without it, a retired credential failing because the bucket, the network or the endpoint moved would read as a successful revocation — Session 6 Run 9's rule about a mutation without its control, applied to a credential. That control is also what makes the unmeasured window acceptable rather than a guess dressed as a result. | — |
| **D364** | `storage-admin status` can report what is collectable by asking the plane. | **It cannot ask the claim** — the claim LEASES what it returns, so a status verb that called it would mutate the queue it was reporting on. And the two cannot be collapsed into one authority either: the claim's `FOR UPDATE SKIP LOCKED` is ADR 0104's throughput mechanism and has to sit on the base table, so the collectable set cannot be factored into a function or view the claim then selects from. | The predicate exists twice, deliberately, and `test_the_operator_status_agrees_with_the_claim_about_what_is_collectable` runs **both** against a real cluster with a mixed population and requires the counts to match, with arms proving the agreement is not an agreement at zero. | D177 is the record of the documentation route being derived twice, the two disagreeing, and **the copy carrying a comment saying it was "kept in step" being the one that had not drifted**. When two derivations cannot be collapsed, the answer is a test that runs both — a comment is not a mechanism. | — |
| **D365** | A mutation battery's value is the survivors it finds. | **Twenty-six mutations across two batteries, zero survivors — and the honest reading is that the first battery's value arrived before it ran.** Four of the tests it exercised were written *anticipating* the survivors: the lease margin was only asserted as arithmetic, `sweep_from_environment` was the production entry point and nothing reached it, and the repository's three cleanup calls had their parameter order covered by nothing. The genuinely independent finding came from asking what the battery could **not** reach — `bin/storage-admin.py`'s own logic, which had no tests at all, so a mutation in the `-i` on `docker exec`, in a verb's exit code, or in what crosses on stdin would have survived silently. | `tests/contract/test_storage_admin.py`, and a second battery of eleven mutations against it. Both batteries: controls green before and after, every file restored byte-identical, anchors pre-flighted. | Runs 5, 6 and 7 each ended with a survivor that was a test written minutes earlier. Run 8 ended with none, and *that is not evidence the tests are stronger* — it is evidence the predictions were made first. **The question that produced the real finding was not "what survived" but "what could this battery not have reached".** | — |
| **D366** | (small, and the reasoning is the point) `socket.gethostname()` is a harmless way to label a cleanup worker. | **`test_the_service_never_constructs_a_network_jwks_client` refuses any network-capable module reference anywhere under the service**, and it fired on the first run of the new module. | `os.uname().nodename` — the same fact from a call that cannot open a connection. | **The right response was to drop the capability, not to find another spelling of it.** `storage_client.redact` makes the identical choice about `urllib.parse` and says so: `urlsplit` would have been harmless, and buying an exemption for the safe half of a network module is how the unsafe half arrives. The scan is deliberately a NAME scan; routing around it with an equivalent import would have defeated it while passing it. | — |

### Found during Run 9

| # | Predicted / assumed | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D367** | §5 Run 9: "the aggregate app OpenAPI through the existing workflow" — a capture step. | **Aggregating it for the first time showed the storage half publishes a contract the service does not serve.** Every operation documented `200`, including the one that answers **201** and the one that answers **204**; no failure response was documented at all, though the routes return 400, 401, 403, 404 and 409; and a `422` was published in FastAPI's `HTTPValidationError` shape, which this service never emits — a malformed object id is `MalformedRequest`, a **400** in the house shape. | **ADR 0112.** Every storage route gains `status_code=`, `openapi_extra=` and `responses=`, built from the same `errors.py` constants the code returns, and `tests/contract/test_app_contract_aggregate.py` asserts the document against the surface rather than against itself. | **`openapi_docs.py` exists to prevent exactly this and says so in its own docstring**, recording the same measurement made for the auth router in Session 6: *"the document FastAPI generates from the signatures alone is nine paths, no request bodies, and a single 200 apiece."* It was written for one router and never applied to the other. D333's question — *when a decision is implemented, which of its callers got the implementation* — for the second time in one session, and it survived three runs because nothing aggregated the document until now. | 0112 |
| **D368** | A route's published responses are what it declares. | **FastAPI adds a `422` to every operation with a parameter**, whether or not any input on that route can fail its validation. `DELETE /objects/{object_id}` takes one `str` path parameter, which accepts every string, so FastAPI's layer rejects nothing. The auth surface avoided this only by coincidence: every auth route with a path parameter happens to declare a real 422, which *replaces* FastAPI's. | Pruned in `create_app`, and **derived rather than listed**: an operation keeps its 422 when its route declared one. Pruned in the application rather than at capture time, so `create_app(mode).openapi()` and the committed snapshot cannot describe different surfaces. | **The prune had to run to a FIXED POINT** and the first version did not. `HTTPValidationError` references `ValidationError`, so one pass computed against a single snapshot removes the first and then finds the second still referenced — by the schema it has just deleted. It published an orphaned `ValidationError` that nothing pointed at, which `test_every_published_schema_is_referenced` now refuses. | 0112 |
| **D369** | `contracts/auth-openapi.canonical.json` is the app contract. | It stopped being the auth document the moment it became an aggregate, and **the constant that names it was already `CANONICAL_APP_OPENAPI`** while the rendered artefact was already `app-openapi.json`. Only the file said `auth`. | Renamed to `contracts/app-openapi.canonical.json`, five references updated, `git mv` so the rename is recorded as one. | Cheapest at the moment the content changed, and a stale label on a *reviewed* artefact is the exact shape this repository keeps finding attached to a value nobody re-read. | — |
| **D370** | `owner_session` is the fixture a Session 7 proof uses for an owner (§0, and it is what Session 6 built it for). | **It cannot reach the storage surface at all.** Its subject holds `notes:read` and `tasks:read`, and the fixture's own docstring explains that the write proofs still work because **nothing in the data plane reads `scope`** — migrations 0003, 0004 and 0005 contain the word nowhere. **Storage is the first surface where that stops being true**: `require_scope(principal, OBJECTS_WRITE)` runs on every write endpoint. Every storage proof would have been a 403. | `storage_probe_subject` and `second_storage_probe_subject`, holding `objects:read` and `objects:write`; `_registered_subject` takes its scopes with the old default unchanged. | **Two subjects rather than one widened subject**, deliberately. A single widened probe would make it impossible to prove the negative that matters most here — that a registered, authenticated human *without* the scope is refused — and a suite of 403s from an under-scoped fixture would have looked exactly like a working boundary. | — |
| **D371** | A probe subject is torn down by deleting its rows and then the subject. | **`app_private.storage_objects.owner_id` is `ON DELETE RESTRICT`**, chosen in 0014 so that deleting a subject who still owns objects cannot orphan bytes at the provider. So the existing teardown would fail to delete any subject that had run a storage proof, and its own `remaining == "0"` assertion would fire on a foreign-key violation. | `_collect_owned_objects` ages the rows, tombstones them through `storage_tombstone`, and runs **the product's own `bin/storage-admin.sh cleanup`** — bytes before metadata. What the sweep cannot finish is reported and the rows are deliberately **not** deleted. | Found while writing the proofs, before a host run met it. The tempting teardown is `DELETE FROM storage_objects` — which would strand bytes at the provider, in the fixture written to test the plane that exists to prevent exactly that. | — |
| **D372** | (small, and it is Run 8's mechanism working) A new gate script joins the operator surface. | `test_every_command_in_bin_is_covered_by_this_module` — written in Run 8 after twelve commands were found outside the CLI contract's lists — **failed on `bin/session-07-check.sh` within a minute of it existing**. | Listed. | Worth a row because the previous twelve accumulated over two sessions in silence. The gap between "a rule somebody keeps" and "a test" is one run of a suite. | — |
| **D373** | §5 Run 9: `bin/session-07-check.sh` in three modes (D316) — and Session 7's claims are all host-measured, so external mode would record nothing. | **Session 7 does have an external guarantee**: from off-host, every storage endpoint must refuse an anonymous caller with **401 and never 404**. A 404 would mean the ownership filter ran before authentication, and an anonymous prober could then distinguish a real object id from an invented one — precisely what STO-OWN-001 denies to an authenticated stranger. | **`STO-PUBLIC-001`**, a new id with its own module, and the claim `public_storage_boundary`. Three modes are meaningful for this session rather than ceremonial. | **A new id rather than widening `SEC-API-001`.** A claim is measured in exactly one environment (ADR 0045), and `claim_session` derives from `max()` — so widening Session 5's requirement to cover a Session 7 surface would move that claim into Session 7's evidence and withdraw it from Session 5's, which is ADR 0089 and D279. | — |
| **D374** | The page-text assertions check what the page says. | **One of them checked a string the page cannot contain.** The note is HTML wrapped at 80 columns, so the sentence a reader sees as *"there is no endpoint that lists your objects"* is `"no endpoint\n        that lists your objects"` in the file — and `"no endpoint that lists" in note` was therefore never true. It passed because it was joined by **`or`** to a clause that was. | Every prose check goes through `_surface_note`, which normalises whitespace; the `or` became `and`, because the two clauses are two distinct facts and a reader told only the first still loses objects. | **The battery found it, and the first reading was wrong.** Both docs mutations survived, and the tempting conclusion was "two weak tests". One was a mis-targeted mutation and uninformative; the other was an assertion whose subject does not exist in the text being searched, passing for a reason unrelated to what it claims. That is worse than a weak assertion and it is D173's shape with the polarity reversed. | — |
| **D375** | (process, recorded because it nearly became a fabricated finding) A gate's refusal exits 2. | Reading the exit code **through the shell tool** reported `0` for `--peer-project`, `--capabilities` and `--bucket` alike, on three different gates. The refusals are correct: measured from a **script file**, every one exits 2. | Nothing to fix. Recorded. | This is the trap CLAUDE.md documents — `$?` inside `wsl bash -lc "…"` is expanded before WSL sees it, so a command that exited 2 is reported as 0, silently and with a plausible number. It was one step from a divergence row asserting a defect in a release control that does not have one. **Never read an exit code except from a script file**, including when the answer looks like a finding. | — |

### Found during Run 10

| # | Predicted / assumed | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D376** | Operator guide §2: the buckets are created **in the Cloudflare dashboard**, by hand, once per project key. | The session had **Cloudflare MCP tools bound to the operator's own account** (`ddfa208f…`), and the operator chose that route. Measured rather than assumed: `r2_bucket_create` takes **only a name** — there is no jurisdiction parameter, so it commits silently to `default`; and **no MCP tool issues an R2 API token**, so §3 remains a dashboard step regardless of how the bucket was made. | The buckets were created over MCP and then **read back the way §4 item 1 says the bootstrap must**: account, name, jurisdiction, creation time and public-access state. Both are `jurisdiction: default`, `location: EEUR`, managed `r2.dev` domain **`enabled: false`**, no custom domains. The token half is unchanged and remains the operator's. | The guide's rule is *ownership continuity*, not which button was pressed, and continuity here is proved by construction: the pre-creation listing showed six buckets with **neither derived name among them**, and both creation timestamps fall inside this run. The route was worth writing down because the dashboard offers a jurisdiction and this API cannot set one — a jurisdictional bucket is reachable only through its own endpoint, and nothing in the MCP path would have said so. | — |
| **D390** | The `agent_session` fixture builds "a real agent and a token the deployment issued for it", to prove an agent token cannot reach the storage surface (ADR 0100). | **It names a role that has never existed.** `conftest.py:1837` is `project_a["database"]["roles"]["agent"]`, and `naming.ROLE_SUFFIXES` has no `agent` — it has **`agent_reader`** and **`agent_writer`**, and has since Session 3. `KeyError: 'agent'` at fixture setup, so the proof never ran and reported an ERROR rather than a refusal. | **Run 13**: `agent_writer`, deliberately the more capable of the two — the refusal is worth more against the agent role that can write than against the one that cannot. | **A fixture that has never executed is indistinguishable from one that works**, and this one is `live_host`, so its first execution was this gate. The suite was green with a `KeyError` sitting in a fixture body the whole time. This is D211–D214's family — *nothing knows which proofs have never executed* — and it is the open item no session has built, now cited for the fifth session running. | — |
| **D389** | Outputs **v11** adds a `storage` block — `enabled`, `bucket`, `prefix`, `upload_url_ttl_seconds`, `download_url_ttl_seconds`, `max_upload_bytes`, `allowed_cors_origins` — and `rendering.py` emits it unconditionally, with a comment explaining that the defaults are resolved **there** because "the document is the one thing every plane reads (ADR 0002), and a service applying its own default would be a second authority for a bound the deploy was checked against". | **The DEPLOYED document has no `storage` block at all.** Read from the host's own published copy: `schema_version: 11`, `deployed_through_session: 7`, and `storage: ABSENT`. `deployed_output.py` builds its document from an explicit key list and carries **`routes.storage`** (line 349) while never carrying the settings block — so the fields exist in the rendered artefact, which nothing at runtime reads, and are missing from the one every plane does. `STO-BOUND-001` failed on exactly this: *"the deployed document publishes no storage.max_upload_bytes, so there is no bound here to measure"*. | **Run 13**, and the fix is deeper than one carried key: **the schema forbade it too.** `$defs/deployedDocument` has `additionalProperties: false` and no `storage` property, so carrying the block was *rejected by validation* — 25 contract tests went red saying so. The block is extracted to **`$defs/storageSettings`** and referenced from both branches, and `deployed_output.py` carries `rendered["storage"]` whole. One definition, not a copy per branch, because a copy is what let the two disagree. | **The renderer's comment states the invariant this breaks, three lines above the fields it breaks it for.** The intent was explicit and the second half was never written. **No fixture could catch it**: both example manifests set `max_upload_bytes` explicitly (26214400 and 10485760), so the *rendered* document has the field either way, and nothing compares the rendered document's storage block against the deployed one — D332's shape, where the artefacts that could disagree are never put side by side. It took a proof that reads the value from the **deployed** document, on a real host, to notice. | — |
| **D388** | ADR 0099 divides `max_connections` 56 four ways and charges storage `pool_size + STORAGE_RESERVED_CONNECTIONS`; ADR 0093 puts the cleanup sweep **inside the storage container**, so it runs as the same role. | **The sweep opens a SECOND FULL POOL and the budget has no term for it.** `storage_cleanup.py:264` is `db.build_pool(settings.conninfo, size=settings.pool_size)` — 4 connections, the serving process's own width — on top of the serving process's 4, against a `CONNECTION LIMIT` of **6** (measured live: `apg_alpha_dev_storage_service\|6`). The gate's cleanup proof failed with `FATAL: too many connections for role "apg_alpha_dev_storage_service"`. And the reserve was never the admin path's: `STORAGE_RESERVED_CONNECTIONS = 2` documents itself as **"the startup-and-recovery overlap, where a pool being re-established while the old connections are still closing is briefly over its own size"**. | **Run 13**: `size=1`. Measured, not assumed — `sweep` is a plain `for claim in claims:` loop with `await` inside and **no `gather`, `create_task` or `TaskGroup`**, so one connection is all it can ever use and a pool of four buys nothing. A test ties the sweep's width to `STORAGE_RESERVED_CONNECTIONS` so the two cannot drift apart again. | **The author reasoned about the budget and got the wrong axis.** The docstring says the pool is closed between passes because "holding connections from ADR 0099's budget between passes would charge the deployment for a worker that is not running" — correct about **duration**, silent about **width**. A sweep that runs for two seconds four connections wide is exactly as over-budget as one that runs forever, and the sentence proves the constraint was in mind. **Nothing offline could catch it**: a `CONNECTION LIMIT` only bites when two processes hold connections at once, which needs a deployed container and a sweep running beside it. | — |
| **D387** | `routes.app` and `routes.storage` are observed through `observation.await_observation`, which retries until the route answers — the two-stage convergence D230 established and D326 extended. | **The REST document observation does not retry at all.** `served_digest` is one `api_contract.fetch_live(rest_url)`; any failure returns `None` and `observe_api` records `unavailable`. Run 12's alpha redeploy hit the window before the edge finished reconciling, printed *"no served document: the service answered 404"*, and published **`rest: unavailable` with the URL dropped** — while the route was serving. Measured off-host minutes later: `/api/rest` answers **200 with 2412 bytes of swagger**, and beta, untouched, answers 200 with 2411 (the one byte is the project key). Two earlier alpha deploys published `ready` from the same code, so **this is a race, not a defect that reproduces**. | Recorded. The immediate remedy is the one the design already has: **re-run the deploy**, and the second pass observes 200 and publishes `ready`. | **The consequence is not cosmetic.** `outputs.json` is what the gate, the evidence and `published_route` read, so a lost race makes the deployed document **understate a working deployment** — and a claim computed from it would be wrong in the safe-looking direction. The docstring's posture is right — *"a deploy that cannot read its own document has published something it cannot describe"* — but it conflates *the service cannot serve its document* with *the edge had not finished attaching yet*, and its neighbour three fields away already distinguishes them. | — |
| **D386** | (process, recorded because it nearly certified a battery that proved nothing.) A mutation that turns a test red has demonstrated the test measures the mutated thing. | **Not if it kills the fixture.** Run 12's headline mutation replaced 0017's `GRANT` with a comment, and the battery reported `KILLED (rc=1)`. It was an **ERROR, not a FAILURE**: removing the grant left `{{storage_service}}` unused, and `migrations.py` refuses a template that "declares placeholders its template never uses", so the run died building the cluster and never reached the assertion. The battery's own summary line was indistinguishable from a real kill — only M2 and M3 emitted a `FAILED …` line, and M1 emitted none. | The mutation grants `USAGE ON SCHEMA app_private` — which storage already holds from 0014 — so the placeholder stays used, the migration applies cleanly, and the only missing privilege is the one under test. It then fails **at the assertion**, with `permission denied for function auth_user_state`: **the exact string the host produced**, which is the strongest available evidence that the test reproduces D385. | **D269 says an unapplied mutation reports as "expected FAIL got PASS".** This is the other half of that rule and it is not written down anywhere: a mutation can also report a **false kill**, and a red test is exactly what the battery is hoping for, so nobody looks twice. What caught it was noticing that M1 printed no `FAILED` line where its siblings did. **A battery must assert HOW each mutation failed, not merely that it did** — pytest distinguishes `FAILED` from `ERROR` and the battery was reading neither. | — |
| **D385** | ADR 0098 makes storage the third verifier, so it runs the same `AuthService.authenticate` the auth service runs — including ADR 0095's current-state comparison, which is what makes a stale token useless. | **`storage_service` was never granted the privilege that comparison needs.** `0012-auth-access-plane.sql:407` grants `EXECUTE ON app_private.auth_user_state(uuid)` to the auth service role **only**. So every authenticated storage request answered `500 Internal Server Error` in **plain text** — Starlette's default handler, because the exception escaped before this service's error middleware could shape it — on `psycopg.errors.InsufficientPrivilege: permission denied for function auth_user_state`. **Thirteen deployment proofs failed and one error, all with that single cause**; 184 proofs passed and **no Session 1–6 proof regressed**. | **Migration 0017**, granting that one function. Traced rather than assumed: `authenticate` calls exactly **one** repository method, `state(user_id)`, so there is no second missing grant behind it (D305's rule applied before the next trip rather than after). **One function, not the set** — the auth role holds eleven here including `auth_create_user`, `auth_set_password` and `auth_set_status`, and a storage compromise must not be able to mint or re-authorize identities. | **D333's question for the FIFTH time in one session, and D381's shape three runs later**: 0012 granted the set to its only caller at the time, correctly; Session 7 added a second caller of `authenticate` and the grant did not move with it. **No offline test could see it** — nothing offline authenticates as `storage_service` against a real cluster, and `test_the_auth_role_can_execute_the_functions_the_service_calls` does exactly the right thing for the auth role and had no storage twin. Run 12 adds one. | — |
| **D384** | §5.4's host sequence goes transport → restart → migrations → deploy → gate. Nothing in it syncs the host's **dev** environment. | **The gate died in collection**: `ModuleNotFoundError: No module named 'boto3'`, four contract modules, `3421 deselected, 4 errors`. Session 7 added `boto3==1.43.72` and `botocore==1.43.72` to `requirements-dev.in` in Run 2, and the host's `.venv` was last synced before that. The gate resolves `${ROOT_DIR}/.venv/bin/python` deliberately — `sudo` resets PATH to `secure_path`, so an operator-activated venv is invisible to it — which means the venv it uses is exactly the one nobody updated. | `.venv/bin/python -m pip install --require-hashes -r requirements-dev.txt`, run **as the operator** and not under `sudo`, added to §5.4 between transport and the gate. | **This is D297, and it is the second session it has cost a gate run** — the open item already records "a stale venv on the host killed a gate in collection", from Session 6. `lock-dev-deps --check` verifies the lock *file* against `requirements-dev.in`; **nothing verifies the installed distributions against the lock**, so the one machine where the environment drifts is the one that runs the release control. A session that adds a dev dependency guarantees this failure and no step names it. | — |
| **D383** | Operator guide §5.4 step **0**: *"Before leaving the workstation. Re-render the fixtures, **or the host gate reads stale ones** and reports interpolation errors as a defect in `compose.yaml` (D212)."* Two `--render-only` commands follow. | **The workstation's fixtures never reach the host.** `.gitignore` carries `.generated/*` with only `.gitkeep` tracked, so the rendered projects are not in the transport bundle and the host keeps its own `.generated/`, last written in the session-6 era. Run 10 followed step 0 exactly, on the workstation, and the host gate still refused at exit **6**: *"rendered fixtures are stale: fixture-alpha-dev at v10, fixture-alpine-dev at v10; the code renders v11"*. The instruction cannot achieve the thing it names. | The two commands move to **the host**, after transport and before the gate. They need neither root nor a running project — `--render-only` is the one mode that runs in a bare checkout — so this is not a new privileged step. The workstation render stays, for the workstation's own offline gate. | **The gate was not fooled, and that is the whole story.** D212 is the rule that a gate does not skip this check, and it held: the refusal is specific, names both fixtures, names both versions, and prints the fix. A weaker gate would have run the compose-model proofs against v10 fixtures and **passed**, having measured a release nobody deployed. The defect is in the instruction, which was written from the workstation's point of view about an artefact that only ever exists per-machine. | — |
| **D382** | `observe_storage`'s probe message names a serious condition: its own docstring says a 404 there means **the storage router did not match and the application router one segment above it did** (ADR 0108), or the strip failed, or the process is not up. | **It is printed on every failed attempt inside the settle loop**, where an early 404 is the ordinary state of a container that has not finished starting. `await_observation` retries until `ready`, so Run 10's redeploy printed *"the storage route answered 404 rather than 401"* and then published `storage ready` four lines later — two contradictory signals, with no attempt counter, no timestamp and no indication a retry followed. | Recorded. The status itself is **correct**: measured off-host and anonymous immediately afterwards, all four storage endpoints answer **401 `authentication_failed`**, and the neighbour probes place the answer in FastAPI rather than Traefik — `/api/app/storage` and `/api/app/storagex` return a 22-byte `{"detail":"Not Found"}` where Traefik's own 404 is 19 bytes of `404 page not found` (D186, D187, D353). | **D296's shape exactly**: a message that is load-bearing when it is true, printed routinely enough that a reader learns to skim it. The cost here was an investigation to establish that a published `ready` was not a false green — which is the right investigation to have run, and would have been unnecessary had the line said "attempt 2, still settling". A settle-loop retry and a routing defect must not print the same sentence. | — |
| **D381** | ADR 0098/D320, `compose.yaml` and `main.py` all state it: storage is the **third verifier** — it verifies the tokens auth issues, holds no signing key, and there is "no `APG_SIGNING_KEY_FILE` here and there must not be". | **Storage is given no verification material of any kind, so it cannot start.** `AuthService.__init__` derives its only key set from the signing key — `service.py:83`, `LocalKeySet.load(json.dumps(signing_key.jwks()))`, unconditional, with the parameter typed `SigningKey` rather than `SigningKey \| None`. In storage mode `signing_key` is `None` **by design**, so the first start anywhere raised `AttributeError: 'NoneType' object has no attribute 'jwks'` and uvicorn exited `3` (`STARTUP_FAILURE`) three times under `restart: on-failure:5`. There is no `APG_JWKS_FILE`, nothing in `STORAGE_VARIABLES`, and no JWKS mount on the service. **`LocalKeySet.from_path` — the exact machinery a file-based verifier needs — exists at `tokens.py:240` and its only caller in the entire repository is a contract test.** | **ADR 0113 and Run 11.** Storage takes the rendered `jwks.json` PostgREST already reads, by path, through `from_path`; `AuthService` is handed its key set rather than deriving one, so both modes state their source. Not fixed at the terminal: it is an ADR, a settings contract, a Compose mount, the suite and a redeploy. | **D320 predicted every consequence of the third verifier and the key set was never wired** — the decision was implemented in `settings.load` (refuses the key), in `lifespan` (passes `None`), in `create_app` (mounts by mode), and not in the one place that consumes it. D333's question a **fourth** time this session. The offline suite stayed green because the declared `STORAGE_VARIABLES` and `compose.yaml` **agree** — and neither names a verification key, so the test comparing them is satisfied by two incomplete lists (D332's shape). Nothing constructed the storage lifespan in any environment, which is the 49-unrun-proofs problem arriving exactly where it was expected to. | 0113 |
| **D380** | `apg-diag` is the read-only diagnosis surface, so that "a question about a running deployment does not need a human" (ADR 0071). | **Its service allowlist has never been updated for either service a session added.** `bin/apg-diag.sh:65` reads `postgres pgbouncer postgrest docs edge-probe dbmate` — **no `auth`, no `storage`**. Session 6 shipped the auth service without adding it; Session 7 shipped storage and repeated it. Found the moment it mattered: the storage container `Exited (3)` on its first start anywhere, and `apg-diag logs alpha-dev storage` refused with exit 5, forcing an operator to a terminal for a **read-only** question. | Recorded now, **not fixed mid-trip** — `apg-diag.sh` is code, so a fix costs the suite, the gate, transport and a redeploy inside an open window. It also widens what the agent account may read, which is a decision with an ADR's shape rather than a one-line allowlist edit. | **D333's question for the third time in this session**: when a decision is implemented, which of its callers got it. The verb list's own comment says "adding one is a reviewable diff", and the service list's says it is deliberately *not* derived from what is running — both true, both correct, and neither is a reminder to extend the list when a service is added. **The gap is invisible until the new service is the one that breaks**, because every older service still answers. | needed |
| **D379** | Operator guide §4: *"The folder does not have to exist first — `bootstrap-providers.sh --apply` creates it while adding `APG_STORAGE_SERVICE_PASSWORD`"*, with a stated **"order that avoids the 404"**. | **`--apply` never creates `/storage`.** `storage_service_password`'s `provider_path` is **`/database`**, with every other role password. Grepped across the contract, the folders are `/database`, `/auth`, `/runtime` and `/storage` — and **`/storage` is the only one holding no `generated` secret**, both its entries being `operator_supplied`. So no command in this repository can create it, and the prescribed order changes nothing. **Measured on the host, not reasoned**: `--apply` reported `created storage_service_password`, and `/storage` still did not exist. | The guide now says to create the folder in the UI first, and says why no command will. | **The remedy was wrong in the same direction as the failure it was written for**, which is why it survived review: it names a real 404, gives a real cause, and prescribes a step that does not address it. The operator followed it exactly, found no `/storage` folder, reasonably used `/database`, and got the 404 anyway — **one `down` project later**, because materialization is where absence is detected, not the paste. `must_refresh_on_start` is true for both halves, so the deploy failed **closed** and started nothing; the damage was a stopped project and a stray credential copy, not a broken deployment. | — |
| **D378** | Operator guide §5.4: step **1** is "the provider — §2, §3 and §4", and step **2** is transport. So Infisical is filled before the release reaches the host. | **§4's `--apply` cannot run before transport.** It reads the repository's `secrets.required.yaml`, and `r2_access_key_id`, `r2_secret_access_key` and `storage_service_password` entered that file in **Run 2 (`6bcce29`)** — Session 7 code the host does not have. Run on a Session 6 checkout, `--apply` creates no `storage_service_password` and names neither operator-supplied secret, which is the *silent* half: it exits having done nothing wrong-looking. **Session 6's own guide has the right order** — transport, `down`, provider secrets, materialize, deploy — and Session 7's §5.4 inverted it. | Transport moves **before** the Infisical step. Only the two dashboard operations (bucket, token) are genuinely first, because they are the operator's and depend on nothing in the tree. §5.4 is reordered and says why. | The bucket and the token really do come first, which is what made the inversion plausible — the whole of §1 reads like "do the provider, then ship the code". But `--apply` is not a provider operation; it is a **repository** operation that talks to a provider, and it is only as current as the checkout under it. **D284 is the same shape**: a missing provider-secret step stopped a Session 6 deploy, and the fix put the step in the guide — in the position the code required, which §5.4 then did not copy. | — |
| **D377** | Operator guide §2: *"Note your **account ID** while you are there."* | **Nothing in the guide ever consumes it.** §3 issues the token, §4 goes to Infisical, and §5.4's Run 10 host sequence runs transport → restart → migrations → deploy with no step that writes `storage.account_id` — or `storage.enabled: true` — into `project.alpha.yaml` / `project.beta.yaml`. The only places that say where the value goes are **ADR 0106** and this plan, neither of which is the operator-facing document; confirmed by grep, `account_id` appears in `docs/` in those two files alone. | Recorded here and carried to the operator as a prerequisite **of** the deploy rather than discovered **at** it. The guide gains the step. The manifests are operator-owned and gitignored — `apg-agent` gets `Permission denied` on both — so only the operator can make the edit. | **The product is not at fault, and that is the point.** `config.py:1127` refuses with *"storage is enabled, so storage.account_id is required"*, and the schema defers to it deliberately for a better message (its own comment at 1125 says so). This fails **loudly and closed** — the good failure, not a silent wrong answer. It earns a row because the deploy at §5.4 step 5 sits several irreversible operations downstream of the moment the operator had the value in front of them and was not told to keep it. | — |

## 2. What Session 7 adds to the acceptance registry

**Grep the registry before choosing any requirement ID** (ADR 0089, D279). The
prefix is not the check; the directory is.

**Four IDs already exist** and are replaced rather than re-invented:

| ID | Priority | Current node ID | What it becomes |
|---|---|---|---|
| `STO-OWN-001` | P0 | `tests/integration/test_future_storage.py::test_cross_user_object_download_is_denied` | A live proof that a second registered subject cannot obtain a download URL for the first's object, and that the refusal is indistinguishable from a nonexistent id. |
| `STO-KEY-001` | P0 | `…::test_client_supplied_object_keys_are_rejected` | The request model admits no key or bucket field, and the generated key matches the derived format. |
| `STO-URL-001` | P0 | `…::test_presigned_urls_never_reach_logs_or_the_audit_table` | A canary scan over application logs, the edge log, the journal, evidence, outputs and container inspection. |
| `STO-COMPLETE-001` | P1 | `…::test_abandoned_upload_intents_are_not_downloadable` | Only an object verified against the provider becomes downloadable. |

New IDs are chosen after a grep and follow the existing prefixes. The likely set,
each of which must be **one guarantee** (D47, ADR 0089):

- upload-intent bounds and the per-caller cap,
- completion verification and its idempotence,
- tombstone-before-grant linearization,
- cleanup convergence including the late-writer case,
- the runtime credential's bucket scope and peer denial,
- the secret-consumer matrix (storage holds no signing key; auth holds no R2 key),
- two-project isolation for buckets, credentials and object ids.

**Claims** go in `src/agentic_postgres/evidence_claims.py::CLAIMS`, one claim per
guarantee, built **only from Session 7's own IDs** — ADR 0089's rule, because
`claim_session` derives from `max()` and an older ID mixed in either drags the
claim into an earlier session or hides it from this one's gate. After editing
the registry, `python bin/render-acceptance-matrix.py --write`.

Two registry properties remain **review rules, not tests** (D174, D175): nothing
detects a requirement relocated wholesale into the wrong environment, and nothing
detects a requirement whose description outgrows its node ids. Session 7 does not
fix that and must not assume it is fixed.

---

## 3. Environment feasibility

| Requirement | Status | Note |
|---|---|---|
| Cloudflare account with R2 | **operator input** | Account id, jurisdiction, and the ability to create a bucket-scoped Object Read & Write token. The account is also the collision domain: bucket names are unique per account and jurisdiction. |
| Infisical control-plane credential | **re-issued per session** | `docs/provider-bootstrap.md` shreds it after every bootstrap on purpose. Session 7 needs one for the two new secrets, exactly as Session 6 did. |
| R2 reachable from the host | **must be measured** | Not assumed. The first live call is a `HeadBucket` from the host, through the same egress the runtime uses. |
| Connection budget | **blocking** | See D309. Recomputed before any code. |
| Memory | **must be measured** | A second application container has a floor. **ADR 0082** measured the auth service's the hard way: the first attempt reported 87 MiB for every row because `ru_maxrss` is a high-water mark already set by earlier work. One profile per process, with a no-work control. |
| boto3 / botocore | **lock first** | `--packages-only` (D321). And **ADR 0083's lesson**: a wheel that "seems optional" may be the only reachable implementation — `psycopg` alone does not import on the locked base image. |
| Docker, Compose, host baseline | **green** | Unchanged from Session 6; `session-01-check.sh` passes on the host. |

**The unmeasured boundary that stays unmeasured:** IPv6. Eight
`APG_PUBLIC_IPV6` proofs have never run, and running them from a machine without
IPv6 would report every port closed — a fact about the scanner. Session 7 does
not change that and must not claim to.

---

## 4. Safety plan for irreversible operations

Five operations in this session cannot be undone by re-running a command.

**1. Creating the bucket.** A bucket name is unique within the account and
jurisdiction tuple, and a same-named bucket is **not** ownership proof. The
bootstrap reads back account, name, jurisdiction, creation time and public-access
state and stops for operator review when continuity cannot be proved. **It never
deletes a bucket as rollback.**

**2. Issuing the R2 token.** Cloudflare shows the secret once. The operator
guide says so before the step, not after, and the value goes to Infisical, not
to a terminal that scrolls. (Session 6 put an administrator password in a
transcript by following an instruction that echoed it; the guide's §5 now says
so explicitly. Do not repeat the shape.)

**3. Publishing a secret generation.** Materialization writes a **new
generation** and the deploy recreates every container onto it. Anything reading
"what a container holds" reads the **live pointer**, never the deployed
document's `secrets.generation_id` (**D76, D306**). A stable path that is
*replaced* strands the mounted inode (**D278**), which is why the JWKS change
needs `down` and not `restart`.

**4. Applying migration 0014.** Forward-only. `bin/migrate.sh freeze-lock` after
writing it. Applied as `migration_user`, never as a superuser — **D285**: every
offline rig applied migrations as `psql -U postgres`, and a superuser bypasses
the ownership check that made 0012 and 0013 fail on a real cluster.

**5. Deleting objects.** Cleanup is **metadata-driven** and never lists the
bucket. There is no orphan scan, and adding one later is a separate decision:
a reconciler that lists and deletes untracked objects can delete data a human
put there to recover something.

**The standing rules apply unchanged.** `sudo` needs a TTY, so anything
privileged that mutates is run by a human at a terminal. Read-only diagnosis is
not: `apg-diag` has eight allowlisted verbs (ADR 0071) and the agent account can
run unprivileged commands and write `/tmp`, which is how bundles and evidence
move without the operator key.

---

## 5. Build order

Runs are the unit. Each ends with the offline gate green on a clean tree, and
CLAUDE.md §4's procedure applies to every one of them: measure third-party
behaviour with a **control** before writing anything that depends on it, write
the ADR when the measurement decides something with alternatives, then implement,
then **try to break the tests** with a mutation battery whose failures are fatal
(D269).

### Run 1 — The budget, the scopes, and the shape of the boundary

**Done.** Four ADRs (**0099–0102**), six divergence rows (**D327–D332**), outputs
**v11**, and the suite green on a clean tree.

**The battery: seven mutations, zero unexpected, both controls green.** M1–M6
each killed the tests written for them. **M7 did not, and it is the run's last
finding** — a hard-coded `20` for `database.pooler_pool_size` left the whole
suite green, because nothing asserted the field and both fixtures declared the
same value. That is D332, and it is now closed rather than recorded: the second
fixture drops to 16 and four tests read the published figure against its
manifest. **The field the bootstrap plane refuses a deployment over was
published by a line no proof could distinguish from a constant.**

What was measured, each with a control that had to pass first:

- **The budget cannot hold a fourth claimant at `max_connections` 50.** Both
  arithmetics were run for storage pools 0 through 8 against the example
  manifest. The control — the current tree, no storage claimant — shows the
  manifest sum at 44/50 and the application's remainder at 23 against a pooler
  pool of 20. A storage pool of 2 already puts the remainder below 20.
  **`max_connections` rises to 56**, which keeps the remainder at exactly 23;
  the memory cost was measured at 12 MiB per cluster, 608 MiB of a 1600 MiB
  guardrail for two projects. **D327** is the finding that outranks the number:
  two arithmetics, never compared.
- **A third scope class is not a schema addition.** Four arms, two controls,
  tree left clean. The complement made `objects:*` administrative by
  arithmetic, and the two tests that noticed both look like tests somebody would
  update while adding a scope. **D328.**
- **The runtime boundary** is one image and two modes, decided on ADR 0084's
  constraint one level out: build contexts do not overlap, so a second service
  directory could not import the JWT verifier, the strict parser or the error
  vocabulary any more than either can reach `src/`. The least-privilege boundary
  is the secret contract's per-consumer materialization and is independent of
  the choice.
- **The object key** needed no reconciliation on the half the plan predicted:
  `naming.derive` already applies both defaults, so the manifest's `bucket` and
  `prefix` are overrides of a derivation. **D330.** What was missing is the
  per-object suffix.

Shipped: `storage.pool_size` and `storage.allowed_cors_origins` in the manifest
schema with their negative cases; `config.storage_connection_budget`;
`connection_limits` taking four claimants and refusing a remainder below the
pooler's pool; outputs **v11** with `storage_connection_budget`,
`pooler_pool_size`, `routes.storage` and the resolved storage bounds, chosen
together from the session's whole surface (D308/D255); `migrate_v10_to_v11` with
a **genuine v10 render** as its fixture, produced in a detached worktree at
`d975800`; `$defs/storage_scope` and `$defs/administrative_scope` with the
partition check; `naming.STORAGE_PATH_SUFFIX` and `route_storage`;
`STO-BUDGET-001` and `STO-SCOPE-001` in the registry with the claims
`connection_budget_division` and `storage_scope_class`.

**The two fixtures now differ in their storage budget** — alpha at pool 4, alpine
at 2 — so the pair proves the division is resolved per project rather than read
from one place.

**What Run 1 did not do, stated rather than left to be discovered:** the clusters
are still running `max_connections` 50. Until they are restarted, a redeployed
project renders v11 and `connection_limits` **refuses**, naming the restart. That
is the intended behaviour and it belongs to Run 10's host sequence.

---

*The original plan text for this run follows.*

**Offline. Nothing is built until these three are decided**, because each of them
changes what the rest of the session may assume.

- **Re-derive the connection budget for four claimants** (D309) in `config`,
  with the manifest bound, the document field and the bootstrap plane's division
  moving together. Publish it in **outputs v11** and nowhere else.
- **Decide the scope class** (D310) with an ADR. `agent_scope` is not widened.
- **Decide the runtime boundary** (D322) with an ADR: a mode on the existing
  image, or a second service directory.
- **Decide the key derivation** (D315): one authority for the object key,
  reconciling the manifest's `prefix` with the generated layout.
- Extend `schemas/project.schema.json`'s existing `storage` section; add the
  negative cases (wildcard origin, http origin outside development, a bound
  outside its range, a bucket name that is not the derived one).
- Grep the registry, then write the Session 7 entries and claims.

**Exit:** two fixtures render with different buckets, different budgets and
identical structure; `--render-only` still works with no host and no root.

### Run 2 — The secret contract and the provider plan

**Done.** One ADR (**0103**), four divergence rows (**D333–D336**), and a live
product defect that had been latent for two sessions.

**D333 is the finding.** `generate_secret_value` had exactly one caller. The
fresh-bootstrap path in `apply()` called `token_hex` inline, so a project
bootstrapped from scratch at Session 5 or later would have stored 64 characters
of hex as its RSA signing key — ADR 0055's own opening paragraph, describing
itself, two sessions after the ADR was accepted. It never fired because both live
projects were bootstrapped in Session 2, when the only declared secret genuinely
was hex, and every later credential reached them through the converge path.
Measured with a control: one contract, one process, fresh path hex, converge path
PEM. **When a decision is implemented, ask which of its callers got the
implementation** — the Run 14 question, asked of a caller rather than of a side.

**The plan's own proposal was refused, and the refusal is ADR 0103.** D311 asked
for a new `value_kind`. Cloudflare defines the R2 Secret Access Key as the
SHA-256 of the API token's value, so it *is* a 64-character hex string:
`random_hex` is true about it, and a widened `value_kind` would have made the
contract unable to state that while also breaking the `pgpass` rule, which is
keyed on `value_kind == "random_hex"`. `origin` is a second field instead, and
the eleven existing secrets now say `origin: generated` — a fact that was already
true and nowhere written.

**The Compose entry moved forward four runs, and it was measured before it moved
(D335).** `postgres-bootstrap.py` recovers a role's password from the consumer,
so Run 4's activation of `storage_service` needs the declaration as much as Run 7
does. A control (clean tree: 3166 passed) against a probe (the `storage` service
plus the three secrets) left the whole offline suite green but for one test — the
one that exists to be answered when a secret name is added. It is inert
meanwhile: `profiles: [session7]` against `CURRENT_SESSION` 6.

Shipped: `origin` in the schema, the contract and `secrets_contract`;
`storage_service_password`, `r2_access_key_id` and `r2_secret_access_key`;
`generate_secret_value(secret)` with the origin refusal first; `--plan`/`--apply`
naming operator-supplied secrets and never proposing to create them;
`managed_resources` refusing them in the schema and the stricter test that
enforces it; the `storage` Compose service in `POST_BOOTSTRAP_SERVICES`; eight
`STORAGE_*` variables with `naming.storage_bucket_name`/`storage_object_prefix`
as their single derivation; `storage.memory_limit_mb`, declared and marked
**unmeasured**; and `docs/session-07-operator-guide.md` with the Cloudflare steps
written before they are needed.

**Two things to know before Run 3.** The fixtures agreed on four of the eight new
storage variables — D332 recurring one run after it was recorded — and now
disagree on all eight. And the battery caught the run's own test being a
tautology: M3 stayed green because the test read the helper rather than the
document `apply()` builds. Final battery: **10 mutations, 0 unexpected, three
controls green.**

---

*The original plan text for this run follows.*

- Declare `r2_access_key_id`, `r2_secret_access_key` and
  `storage_service_password` in `secrets.required.yaml`, with the new
  `value_kind` for the two the bootstrap cannot generate (D311) and `pgpass`
  format for the third where the consumer needs it.
- Extend `bin/bootstrap-providers.sh` so `--plan` **names** the operator-supplied
  secrets and `--apply` refuses to invent them, with a message that says where
  the value comes from.
- Write the Cloudflare steps into `docs/session-07-operator-guide.md` **before**
  they are needed, including the one-time secret display.

**Exit:** `--plan` on a fixture prints exactly the new secrets; a fake provider
proves the refusal path. Remember that **a fake never 404s** (D283) — the
optional/absent case needs its own fixture.

### Run 3 — Migration 0014 and the storage plane

**Done.** One ADR (**0104**), three divergence rows (**D337–D339**), migration
**0014** released and frozen, and twenty tests against a real cluster.

**D337 is the finding, and it was caught offline for once.** `storage_service`
held EXECUTE on all seven functions and **no `USAGE` on the schema**, so
PostgreSQL refused every call with `permission denied for schema app_private`
before it ever looked at an ACL. An ACL test would have been green — the ACLs
were right. It went red because the test *called the function*. D288/D289/D291's
class, at the cost of a test run rather than a host deploy.

**Neither cleanup mechanism had ever been measured in this repository** — nothing
mentioned `SKIP LOCKED` anywhere. Both were, on the locked pg18 digest, with
controls that fired: without `SKIP LOCKED` the second claimant blocks until
`lock_timeout` kills it, and a plain CAS lease under READ COMMITTED yields
exactly one winner because the re-check runs against the new row version. ADR
0104 takes both, doing different jobs: **the lease is correctness** (the provider
DELETE is outside the transaction, and a row lock dies at COMMIT and at crash),
**`SKIP LOCKED` is throughput**. The battery's M2 removes `SKIP LOCKED` and stays
**green**, which is what the ADR says should happen and is recorded as a
deliberate expected-PASS.

Shipped: `app_private.storage_objects` under a one-way state machine with five
coherence constraints written against ADR 0080; `storage_contract_state`; seven
SECURITY DEFINER functions granted to `storage_service` and nothing else, with no
privilege of any kind on the table; the `storage_service` placeholder in
`migrations/manifest.json`; the frozen lock at fourteen; and
`tests/contract/test_storage_plane.py` — ownership, ACLs, the transition matrix,
cross-owner indistinguishability, the lease across transactions, expiry reclaim,
and two concurrent workers partitioning the queue.

**What Run 3 does NOT prove, stated rather than left to be discovered.**
`storage_service` still cannot log in: it has a connection limit from Run 1 but
is absent from the `CONNECT` grant `build_statements` issues, and its LOGIN
attribute and credential are bootstrap-plane work (D102). So the privilege proofs
reach the role by `SET ROLE`, which exercises the grants and says nothing about
the login path. **That is Run 4's exit criterion** and the test module's docstring
names the gap rather than implying coverage.

**D339 was found by leaving the repository, and is closed.** Listing the live
Cloudflare account read-only showed six unrelated buckets — `items`, `photos`,
`pictures` and three more — and the R2 bucket was the only derived identifier in
this project without the `apg` namespace every router, middleware and role
carries. **ADR 0105** namespaces the derived name; an explicit override stays
verbatim. Free to do now, impossible after Run 5 creates a bucket, because R2 has
no rename. The half worth carrying is that **both fixtures restated the
derivation**, so nothing exercised it — alpha now takes the derived names and
alpine overrides them.

---

*The original plan text for this run follows.*

- `migrations/templates/0014-object-storage-plane.sql`: the object table, its
  state constraints, the cleanup lease columns, the contract-state row, and the
  narrow `SECURITY DEFINER` functions.
- Every function: owned by the non-login object owner, `SET search_path =
  pg_catalog, pg_temp`, fully qualified names, **an explicit per-function revoke
  from PUBLIC beside every `CREATE FUNCTION`** (D57, D262 — a new function is
  PUBLIC-executable and `ALTER DEFAULT PRIVILEGES … REVOKE … FROM PUBLIC`
  records nothing for functions), and a grant only to `storage_service`.
- **A CHECK constraint passes when its expression is NULL** (ADR 0080). Every
  state constraint is written and tested with that in front of you.
- Do not touch the pre-request hook (D312).
- Prove against a **real cluster**, applying all fourteen migrations as
  `migration_user` (D285), not as a superuser.

**Exit:** fresh apply, repeat no-op, ownership and ACLs, the transition matrix,
the lease claim under concurrency, and cross-owner lookups returning nothing.

### Run 4 — Activate `storage_service`

**Done.** Three divergence rows (**D340–D342**), no ADR — every decision here was
an existing one applied.

`storage_service` is now activated by the bootstrap plane exactly as
`auth_service` is: it joins the `CONNECT` grant, `STORAGE_SERVICE_CONSUMER` is
cross-checked against the contract, and `activate_storage_service` sets the
credential and the `CONNECTION LIMIT` together when the active generation carries
the file — or leaves the role NOLOGIN and says so. **The deferral is discharged
in the run that owns it**, rather than restated as a comment pointing at a later
run: that sentence is what D288 cost, and the previous version of this block
carried it verbatim.

`tests/contract/test_storage_service_reaches_its_data.py` is Run 4's exit
criterion — the role connecting over TCP with a password the product set, running
all seven functions, holding no membership, unable to become another role, and
refused a peer project's database. Run 3's module keeps its `SET ROLE` form
deliberately: 0014 decides grants, not logins, and the two together are what
D211-D214 asks for.

**The battery found two things worth more than the mutations.** The reach test
was credentialing the role itself, so the product's decision was untested
(**D342**) — D288's mistake inside the module written to avoid it. And every
clause of the LOGIN-set proof was untestable offline purely because of where the
function lived (**D341**); it is now `deployed_output.activated_login_roles` with
a decision table over documents no single deployment can produce. The storage
clause is keyed on `secrets.required_names`, **not** on `routes.storage` — that
key means "the document is v11", and v11 exists while `CURRENT_SESSION` is 6, so
it would have failed a correct deployment.

**D340 is recorded rather than fixed:** every service role can reach the
`postgres` maintenance database and read its catalog, because `REVOKE ALL ON
DATABASE` only ever touches the project database. Pre-existing, project data
still unreachable, and asserted as current so a later session closing it goes red.

---

*The original plan text for this run follows.*

- Bootstrap-plane activation: LOGIN, the credential, the `CONNECTION LIMIT` from
  Run 1's division, `INHERIT FALSE` where a membership exists at all (**D266**:
  without it the holder gets every request role's reach merely by connecting).
- No membership in `authenticated`, `project_admin`, the agent roles, the owner
  role or the migration role.
- **Move the two proofs that will go red** rather than discovering them: the
  LOGIN set derivation and the authenticator's membership set both derive from
  the document and the bootstrap enumeration (ADR 0096).

**Exit:** the role connects directly, executes exactly the storage functions, and
can reach nothing else — proved by attempting, not by reading a catalog bit
(**D103**: `has_table_privilege` returned true for a table the role could not
read).

### Run 5 — The R2 adapter, measured before it is trusted

**Done.** Two ADRs (**0106**, **0107**), five divergence rows (**D343–D347**),
boto3/botocore locked, and the adapter written against nine measured arms rather
than against the S3 documentation.

**What the measurement changed rather than confirmed.** Three things: the
addressing style cannot be frozen by setting the config key (D344), botocore's
`max_attempts` is retries rather than attempts (D345), and an Object Read &
Write token cannot create a bucket, so §3's one-token assumption is wrong
(D347). What it *confirmed* is ADR 0104's foundation: `DeleteObject` on an
absent key is a 204, and the first-write condition is enforced inside the
signature rather than by client cooperation (D346).

**And the gap that had to be closed before any client could exist (D343):**
nothing in the repository accepted a Cloudflare account id, so the container had
no way to know where its bucket was. Four runs had built the storage plane past
a feasibility-table row that named it as an operator input.

Shipped: `BOTO3_VERSION`/`BOTOCORE_VERSION` in the lock via
`--update --packages-only` with all ten image digests carried forward;
`storage.account_id` and `storage.jurisdiction` in the schema, `config` and both
example manifests, which **disagree on both**; `naming.storage_endpoint_url` as
the single derivation and `STORAGE_ENDPOINT` rendered from it;
`services/auth-api/app/storage_client.py` — the frozen client, `StorageConfig`
read from mounted credential files, `R2Adapter`'s four operations and no list
operation, `BoundedR2`, and `redact`; and 47 tests.

*The original plan text for this run follows.*

**Measure the provider before writing the client.** A throwaway rig against a
real bucket, with controls, answering at minimum: does a presigned PUT with a
signed `If-None-Match: *` behave as the runbook claims; what exactly does
`HeadObject` return for content type, cache control, disposition, custom
metadata and checksum under the locked SDK; what is the observed failure shape
for an expired URL, a mutated key and a mutated signature.

- One low-level client: region `auto`, the jurisdiction endpoint derived from
  the account id, `s3v4`, one addressing style **frozen after being proved**,
  explicit timeouts, bounded retries, **no ambient credential chain** and no
  IMDS lookup.
- A bounded executor. Not an unbounded threadpool.
- **A fake adapter is a second configuration of the product** (ADR 0065, 0066).
  If one exists, a test ties every setting the fake configures to the setting the
  product configures — the shape of
  `test_every_setting_the_behaviour_rig_configures_is_configured_by_the_product`,
  which exists because a rig set `PGRST_DB_PRE_REQUEST` and the product never
  did.

**Exit:** every provider operation exercised against a real bucket, with the
negative arms, and no URL or key in any log.

### Run 6 — The endpoints

**Done.** Four divergence rows (**D348–D351**), migration **0015**, and the four
endpoints under `/api/app/storage`.

**No ADR.** Every decision this run made was already decided: ADR 0097 owns the
error vocabulary (D314 asked for a parallel one and got two constants extending
the existing split), ADR 0101 owns the two modes, ADR 0102 owns the key, ADR
0104 owns the ordering, and **ADR 0091 answered the migration question without
needing a new one** — its three conditions were checked, condition 2 failed, and
the rule's own text says that case gets a new migration.

**The finding is D348**: the plane Run 3 released could not have a caller
written against it. Completion needs the key of a *pending* object and 0014
exposed the key only for `available` and `tombstoned` rows. Every Run 3 test
called the functions that existed, so nothing was red.

Shipped: `object_keys.py` (ADR 0102's suffix, and a validator written
independently of the generator); `storage_models.py`, whose `UploadIntentRequest`
has no key or bucket field and whose `CompleteUploadRequest` is deliberately
empty; `storage_repository.py`, eight functions and no table reference;
`storage_service.py`, with `verify_uploaded_bytes` and `finalize` split so the
subject can be re-authenticated **between** them; `storage_routes.py`;
`OBJECT_UNAVAILABLE` and `OBJECT_STATE_CONFLICT` extending `errors.py`;
`APP_MODE` on both Compose services; mode-aware `settings.load`; and 46 tests.

*The original plan text for this run follows.*

Upload intent, completion, download URL, delete. Strict request parsing on the
inherited path, errors in ADR 0097's shape (D314), no-store on every response
that carries a URL, and the ownership-obscuring lookup that makes a cross-user id
and a nonexistent id the same answer.

**Completion holds no database transaction across the provider call**, and the
finalize is a compare-and-swap that **revalidates the subject** — because a token
that was current when the intent was created may not be current when it
completes.

### Run 7 — Publish: the route, the CORS pair, the container

**Done.** Six divergence rows (**D352–D357**) and two ADRs, **0108** and
**0109**, both from measurements against the locked Traefik with controls.

**The finding is D352**, and the plan does not mention it: `/api/app/storage` is
the **first route this project publishes inside another one**. Every route
before it is a sibling, so no request has ever matched two routers and no
ordering has ever been measured. Traefik's default priority is the rule string's
**length** — not its specificity — and a storage rule written the concise way
would be shorter than the application rule it sits inside and would never match
a request.

Shipped: `naming.storage_router_name` and its three middleware names, four
`ProjectIdentity` members, five `compose.env` keys,
`runtime_override._storage_labels` and `STORAGE_CORS_METHODS`, the four entries
in `OVERRIDE_NAME_KEYS` that reach both call sites, `STORAGE_PLANE_SESSION` and
`observe_storage` with `STORAGE_CREDENTIAL_NAMES` as its gate, a second origin in
the alpha fixture so the join and the sort are measurable (D332), §5.1 of the
operator guide, and `tests/contract/test_storage_route.py` — 16 tests.

**The Compose service needed nothing.** Run 2 built it with `profiles:
[session7]`, the block-sequence `tmpfs` (D287), a read-only rootfs, uid 65532,
no host port, and `internal` + `edge`; Run 2 also added it to
`POST_BOOTSTRAP_SERVICES` (D324) rather than deferring to this run. Both are
asserted here rather than assumed.

*The original plan text for this run follows.*

- The Compose service with `profiles: [session7]`, **`tmpfs` as a block
  sequence** (D287 — the flow form parses as four mount paths and only the
  daemon refuses, at container-create time), read-only rootfs, uid 65532, no
  host port, internal and edge networks only.
- `POST_BOOTSTRAP_SERVICES` gains it (D324).
- The router, with the boundary proved by request (D319), and the control-plane
  CORS middleware in the file provider (D323).
- `routes.storage` follows D230's two-stage convergence (D326).

**Read the access log before concluding anything about a 404** (D186, D187).

### Run 8 — Cleanup, rotation, and the operator surface

**Done.** ADRs **0110** and **0111**, migration **0016**, and D358–D366.

Measured, each with a control in the same run:

* **The cleanup claim collects an object whose upload URL is still live** (D358).
  On the locked pg18 digest, all sixteen migrations applied as `migration_user`:
  a pending object tombstoned one statement earlier, with `intent_expires_at` an
  hour away, comes back from the claim. Controls: an expired intent is claimed,
  and a completed object is claimed — so the rig could tell a claim that
  collects from one that does not. **Migration 0016 and ADR 0111.**
* **The write grace reaches both queries.** A sixty-second grace holds back an
  object ten seconds past its deadline; the same object with a zero grace is
  collected. The second arm is the control.
* **`status` and the claim agree about the collectable set**, run against a
  mixed population on a real cluster, with arms so the agreement is not an
  agreement at zero (D364).
* **Two mutation batteries, twenty-six mutations, zero survivors**, controls
  green before and after, every file restored byte-identical, anchors
  pre-flighted. D365 is the honest reading of that zero.

Shipped: migration **0016** and the lock re-frozen; `StorageRepository`'s three
cleanup calls; `services/auth-api/app/storage_cleanup.py` — the sweep, its three
orderings and the lease margin derived from the adapter's own constants;
`bin/storage-admin.{sh,py}` with five enumerated verbs, none of which names a
bucket or a key and none of which administers a bucket; four new contract
modules or sections — `test_storage_cleanup.py`, `test_storage_admin.py`, the
three repository cleanup tests and five plane tests; and `test_cli_contract.py`
brought back into contact with its own directory (D359, D360).

**Not shipped, and named rather than discovered later:**

* **Nothing has run against R2 or against a container.** `verify-credential`,
  `credential-digest`, `confirm-revoked` and `cleanup` all reach the storage
  container, and no storage container has ever started — it sits on
  `profiles: [session7]` and `CURRENT_SESSION` is 6. Their container-side
  programs are asserted for what is readable from their text and for nothing
  else, and the module says so. **This is D211–D214's condition, stated while it
  is true.**
* **`WRITE_GRACE_SECONDS` is reasoned, not measured** (D362), and the rig that
  would replace it is written down at the constant.
* **The revocation window is a bound chosen, not measured** (D363).
* **The `storage.memory_limit_mb` floor is still 384 and still inherited.**


- `bin/storage-admin.sh` in the house shape: `bin/*.sh` over `bin/*.py`,
  enumerated verbs, no arbitrary bucket or key, **no flag that prints a
  credential** (D105), and service logic reached **through the container**
  (ADR 0093).
- Credential rotation modelled on `bin/rotate-signing-key.sh`'s phases rather
  than invented. Note that R2 permission changes are **eventually consistent**,
  so revocation is polled within a bounded window and never asserted
  instantaneously.

### Run 9 — The contract, the docs, the evidence

**Done.** **ADR 0112**, twelve activated requirements, ten claims,
`bin/session-07-check.sh`, and D367–D375.

Measured:

* **The storage half of the application reference described a surface the
  service does not serve** (D367) — read operation by operation against what the
  routes return. Three independent defects, invisible until the document was
  aggregated for the first time.
* **FastAPI publishes a `422` on any operation with a parameter** (D368),
  whether or not its validation can reject anything. Pruned, derived from the
  route declarations, to a fixed point.
* **Fifteen mutations, zero survivors** after two real findings — controls green
  before and after, files restored byte-identical, anchors pre-flighted.

Shipped: the aggregate contract and its rename; five response models and two
shared error models; the four storage routes documented; the 422 pruner;
`/docs/app`'s storage section; `tests/contract/test_app_contract_aggregate.py`
(11), the three docs-page tests, `tests/deployment/test_session7_storage.py`
(17) and `tests/external/test_session7_public_storage.py` (2);
`storage_probe_subject`, `second_storage_probe_subject`, `agent_session`,
`completed_object`, `storage_admin_command` and a teardown that respects
`ON DELETE RESTRICT` (D370, D371); **twelve requirements activated and the four
placeholders deleted**; **ten claims**; `bin/session-07-check.sh` and
`tests/contract/test_session_seven_gate_modes.py` (30).

**`CURRENT_SESSION` is now 7**, which is what makes the activated requirements
enforceable — and it **arms the `session7` Compose profile**. Until this run
nothing could start a storage container and nothing had. A deploy from here on
will try to, so the two R2 secrets must exist at the provider first.

**Not shipped, and named rather than discovered later:**

* **Every Session 7 claim will report `not_run` until a host trip.** All twelve
  requirements are proved by `live_host` or `external` tests that have **never
  executed in any environment**. D282 is Session 6 writing this sentence one run
  before its own trip found nine defects; it is written here for the same
  reason, and the same expectation applies.
* No evidence document exists and none can be written offline.
* `WRITE_GRACE_SECONDS` is still reasoned (D362) and the revocation window is
  still a bound chosen (D363).


- The aggregate app OpenAPI through the existing workflow: `bin/app-contract.sh
  --check` compares, `--update` streams a candidate you redirect yourself.
  **Deployment never approves.**
- `/docs/app` gains the storage surface. The page must **fetch its own assets**
  (D274 — `/docs/rest` rendered 200 with a blank page for four runs because
  nothing ever requested the script its own markup names).
- `bin/session-07-check.sh` in three modes (D316), the claims, the evidence.

### Run 10 — The host trip

Everything above is written and only the offline suite has executed. **The
measurement is the host run.** Session 6's Run 12 found nine defects on its
first host trip and Run 13's first gate returned twenty failures, nineteen of
which were proofs that had never executed. Plan for the trip to find things;
that is what it is for.

**In progress.** The provider half is done and the host half is part-way.
Measured: both R2 buckets created and read back (**D376**); the guide never told
the operator where the account id goes (**D377**); `--apply` cannot run before
transport (**D378**); nothing creates the `/storage` folder (**D379**);
`apg-diag` cannot read the new service's logs (**D380**).

On the host, **alpha-dev**: `max_connections` **56, reserved 3** — the restart
landed; `storage_service` credential set with `CONNECTION LIMIT 6`; migrations
**0014, 0015 and 0016 applied** as `migration_user`, ledger at 16. Then the
storage container `Exited (3)` on the first start of that service anywhere, which
is **D381** and Run 11.

**After Run 11, alpha-dev deployed clean at `887cf5578257`.** The storage
container is healthy — the first time that service has run anywhere. Every route
publishes `ready`, including `storage`. `credential-digest` then
`verify-credential` in that order: the container holds the generation's
credential, and it **reaches `apg-alpha-dev`** at
`ddfa208f…c626.r2.cloudflarestorage.com` — a `HeadObject` on an absent key
answering 404, having written nothing. **The R2 credential is proved end to end
for the first time.**

Measured off-host and anonymous straight afterwards: all four storage endpoints
answer **401 `authentication_failed`**, never 404, which is STO-PUBLIC-001's
guarantee (D373) holding under a real request rather than a written one. The
deploy's own 404 line during settling is **D382**.

beta-dev remains untouched at session 6, 13 migrations, `max_connections` 50.

### Run 11 — The third verifier's key set

**Done.** Fixing D381, found by Run 10's first host start.

Measured before anything was written: the **platform's** JWKS producer
(`jwt_keys.public_jwk` + `build_jwks`, what `bin/render-jwks.py` uses) against
the **service's** verifier parser (`LocalKeySet`) — a pair nothing had ever put
together, since `from_path`'s only caller in the repository was a contract test.
It emits `kty` RSA, `alg` RS256, `use` sig and a computed `kid`; one key, two
keys, and a file written the way `render-jwks.py` writes one all parse. Four
controls — a private RSA member, `alg: HS256`, an empty set, a key with no `kid`
— were each refused, so the acceptances mean something.

**ADR 0113.** `AuthService` is **handed** its key set rather than deriving one,
so both modes state their source at the call site and no branch leaves it
implied. `signing_key` becomes `SigningKey | None`, which is what it has been in
fact since ADR 0101. Storage gains `APG_JWKS_FILE`, a `STORAGE_VARIABLES` entry
and a read-only mount of **the same rendered file PostgREST reads** — not a copy,
which would be a second authority for one value (D264). `issue()` refuses at its
first line when there is no signing key, rather than reaching an
`AttributeError` on `None.private_pem` further down.

`tests/contract/test_verifier_key_sets.py` — nine tests, including the one that
would have caught D381: **construct the service the way storage mode constructs
it.** Every existing construction passed a real key, so the line that
dereferenced it was covered by every test and exercised by none in the shipping
configuration.

**Mutation battery, six mutations, all killed**, control green in the same
invocation before and after and all three files restored byte-identical:
removing the issue guard, making the key set optional, letting auth accept a
second set, dropping the mount, giving storage its own **copy**, and dropping
`APG_JWKS_FILE` from `STORAGE_VARIABLES`. Anchors pre-flighted — each matched
exactly once before the battery ran.

Suite **3477 passed, 261 skipped**.

### Run 12 — The privilege the verifier was never given

**Done.** Fixing **D385**, found by Run 10's first host gate: thirteen deployment
proofs failed and one errored, all on one cause — `permission denied for function
auth_user_state`, surfacing as a plain-text `500` because the exception escaped
before the service's error middleware could shape it. **184 proofs passed and no
Session 1–6 proof regressed.**

**Migration 0017**, one grant. Traced rather than assumed: `authenticate` calls
exactly one repository method, `state(user_id)`, so there is no second missing
grant behind this one — D305's rule applied *before* the next trip instead of
after it. **One function, not the set**: the auth role holds eleven here,
including `auth_create_user` and `auth_set_password`, and a storage compromise
must not be able to mint or re-authorize identities.

The renderer earned its keep again — the first draft wrote `{{auth_service}}`
inside a *prose comment* and `render` refused it, since the placeholder scan does
not care that the braces are in a comment. **A capable template engine would have
substituted it silently.**

`test_auth_service_reaches_its_data.py` gains the storage half: the fixture
credentials `storage_service` through the product's own `apply_credential`, and
three tests run **as that role** — the positive that would have caught D385, and
two controls (it may not administer identities, and it may not read the identity
tables directly). Seven pass against a real cluster.

**Mutation battery, three mutations, all killed** — and **D386** is the reason
that sentence is worth anything. The headline mutation first reported `KILLED`
while having produced an **ERROR, not a FAILURE**: removing the grant left a
declared placeholder unused, so the fixture died before the assertion ran.
Rewritten to grant `USAGE ON SCHEMA app_private` — which storage already holds —
it fails at the assertion with **`permission denied for function
auth_user_state`, the exact string the host produced.**

### Run 13 — Three defects the second host gate found

**Done.** The gate went from **13 failed + 1 error** to **2 failed + 2 errors**,
195 proofs passing, with **no Session 1–6 regression** — and the four remaining
symptoms were three defects, one of them downstream of another.

**D388 — the sweep spent the budget twice.** `sweep_from_environment` opened a
pool of `settings.pool_size` beside the serving process's pool of the same
width, as the same role, against `pool_size + STORAGE_RESERVED_CONNECTIONS`.
`SWEEP_POOL_SIZE = 1`, measured rather than assumed: `sweep` is a sequential
`for` loop with no `gather`, `create_task` or `TaskGroup`. The teardown ERROR on
`test_no_presigned_url_or_object_key_reaches_any_sink` was **this defect
downstream** — the fixture ages, tombstones and sweeps, the sweep died on the
limit, and ten objects stayed uncollected.

**D389 — the deployed document forbade what the runtime reads.** Not one missing
key: `$defs/deployedDocument` has `additionalProperties: false` and no `storage`
property, so carrying the block was **rejected by validation**, and 25 contract
tests said so the moment it was added. The block moved to
`$defs/storageSettings`, referenced from both branches. The rendered block's own
description says *"the runtime reads them from HERE"* — and the schema forbade
the document the runtime reads from having them.

**D390 — a fixture named a role that has never existed.** `roles["agent"]`,
where `naming.ROLE_SUFFIXES` derives `agent_reader` and `agent_writer` and has
since Session 3. `live_host`, so its first execution anywhere was this gate.
Now `agent_writer` — the refusal is worth more against the agent role that can
write.

Two tests that would have caught them: the deployed document must carry the
rendered storage block **whole** (compared as a unit, so a field added later
cannot be dropped silently), and the sweep's width is captured from the **real**
entry point and asserted against `STORAGE_RESERVED_CONNECTIONS` — with a
`pool_size` of 9 in the fake, so a sweep taking the serving width shows up as
that number rather than as a coincidence.

---

## 6. The storage surface

Under `/api/app/storage`, human tokens only, no-store on every response.

| Method | Path | Scope | Notes |
|---|---|---|---|
| `POST` | `/upload-intents` | write | Server generates the id and the key. No bucket or key field exists in the request model. |
| `POST` | `/upload-intents/{id}/complete` | write | `HeadObject` outside any transaction; CAS finalize; idempotent. |
| `GET` | `/objects/{id}/download-url` | read | Owned and available only; the ownership check is the linearization point. |
| `DELETE` | `/objects/{id}` | write | Tombstone commits before any later grant can be authorized. |

**No list endpoint.** The vertical slice proves operations by known id; a list
endpoint needs pagination, ordering, filtering and its own review.

**What the responses do not carry:** bucket, key, ETag, checksum, provider
request id, or another user's existence.

**What a presigned URL is:** a bearer credential with a short life. Issuing one
is an authorization decision made at issue time; it is **not** revoked by a later
tombstone. The documentation says so plainly rather than implying revocation,
and the residual is bounded by TTL, unique keys, the first-write condition,
provider deletion and repeated absence verification.

---

## 7. Evidence and claims

Same model, unchanged: a claim's verdict is computed from the registry's node ids
and JUnit results, never hand-entered, and **a skip is not a pass**. Host and
external halves are written separately and merged by
`bin/write-session-evidence.py --session 7`.

`evidence/*` is gitignored by design. It is generated; regenerating it is how you
get it back.

**The two inherited red claims are Session 5's**, blocked only on the rotation
window. Session 7 does not close them and must not appear to: if the window is
held during this session, it closes them and the plan says so; if it is not, the
Session 7 evidence document carries them red for the same stated reason.

---

## 8. Security invariant matrix

| Invariant | Control | Proof |
|---|---|---|
| A client cannot choose a key or bucket | No such field exists in the request model | Schema plus a request that tries |
| A user cannot reach another's object | Owner-filtered functions; identical answer for absent and foreign | Cross-user matrix with two registered subjects |
| A pending or tombstoned object is not downloadable | State-gated lookup | State matrix |
| A reused URL cannot overwrite a completed object | Unique key plus signed first-write condition | Replay PUT |
| Metadata matches the bytes | `HeadObject` before availability | Mismatch arms |
| A tombstone precedes every later grant | Database commit order | Race test with a deterministic order |
| The storage runtime cannot sign a token | Per-consumer secret materialization | Mount and inspection scan |
| The auth runtime holds no R2 credential | The same contract, from the other side | The same scan |
| The runtime credential cannot administer the bucket | Bucket-scoped object token | Named operations attempted, not "management denied" |
| A stale token cannot use storage | Current-subject check per request | Disable, reset, re-scope |
| An agent token cannot use storage | Human-only verifier; `agent_scope` unwidened | Agent negative arms |
| Cross-project authority is denied | Distinct buckets, credentials, issuer, audience, roles | Two-project gate |
| No URL or key reaches a sink | No-store, allowlist logging | Canary scan across every sink |

---

## 9. Risks and stop conditions

**Stop and ask** rather than proceeding, when:

- the connection budget cannot be divided four ways without taking headroom to
  zero;
- the bucket name exists in the account and ownership cannot be proved;
- the runtime credential can reach the peer project's bucket;
- `--render-only` stops working without a host or root;
- a Session 1–6 claim goes red and the fix would weaken a passing test.

**The failure mode this session is most exposed to** is the one this project
keeps producing: *a value that looked measured and was not*. Storage adds a
provider whose behaviour is documented by somebody else, an SDK with defaults
that reach the network, and a URL that is a credential. Every one of those is a
place where a plausible wrong answer passes for exactly as long as nobody asks.

The three standing questions, and the fourth Session 6 earned:

1. What would have to break for this test to go red?
2. Has it run at all, in this environment, since the thing it measures changed?
3. Whose identity, and through which tool, does the proof run — and are they the
   ones production uses?
4. When a defect class was fixed, **which side of the system got the fix** — the
   product or the proof?

---

## 10. Open items carried in

- **The rotation window.** Two Session 5 claims are red pending three
  `APG_ROTATED_*_FROM_FILE` inputs. **ADR 0088's signing-key cutover is now
  unblocked** — it required auth-service issuance and PostgREST verification to
  be proved, and both are green.
- `requirements-dev.in` has produced a red gate twice; adding boto3 is the third
  chance to do it carefully.
- **Nothing knows which proofs have never executed** (D211–D214). A run-age per
  node id would have caught four defects in one Session 5 run and nineteen in
  one Session 6 run. No session has built it. Session 7 will add roughly a dozen
  host-only proofs to the pile.
- **The environment is not verified against the lock** (D297). `lock-dev-deps`
  checks the lock file, not the installed distributions, and a stale venv on the
  host killed a gate in collection.
- `render-jwks` prints *"the key set CHANGED"* on **every** deploy (D296),
  because `install_rendered` replaces the rendered directory and the byte
  comparison has nothing to compare against. Adding a third verifier makes that
  message more load-bearing, not less.
- Secret generations accumulate; nothing prunes them.
- `tests/deployment/conftest.py` is past a thousand lines and now carries the
  REST plane, the app plane and the identity fixtures. Storage will add more.
- The published REST document advertises `DELETE`, `PATCH` and `POST` on both
  views and all three return 403 (ADR 0060) — recorded, not fixed.

---

## 11. Session 8 handoff

Session 8 receives a private per-project bucket, a bucket-scoped runtime
credential isolated from auth and from any future backup service, an activated
`storage_service` role with function-only authority, a tested object lifecycle
with cleanup leases and late-writer handling, human storage scopes, and a storage
runtime that verifies public JWTs without holding signing material.

Session 8 **must not** hand FastMCP the R2 credential, register storage tools
implicitly from OpenAPI, admit an agent token to a storage endpoint without a
committed capability and audit representation, or log a URL or a key in an agent
audit record.

---

## Appendix — what to consult, and what to measure instead

**Consult:** `docs/decisions/README.md` (98 ADRs, indexed); §1 of this document;
`docs/plans/session-06-implementation-plan.md` §1 rows D215–D306 and §5 runs 13–15;
`docs/session-06-operator-guide.md` for the host sequence this session extends.

**Measure instead of consulting**, every time: what the provider returns, what
the SDK does by default, what a header does to a signature, what a container
holds, and whether a proof has ever run. Roughly half of Session 5's measured
claims turned out wrong, and Session 6's first host gate returned twenty
failures against a suite that was green offline.

**Before measuring how a third party behaves, grep the plans for it.** Run 8
measured how PostgreSQL grants `EXECUTE` on a new function and recorded it as a
finding; Session 3 had measured the same thing three sessions earlier, in more
detail, and the house pattern already reflected it (D57, D262). Every ADR is
indexed; **nothing indexes the ~300 measured facts in the divergence tables by
subject**, so the pointer has to be a grep.

**Never write a measurement you did not run** (D267).
