# Session 15 — identity lifecycle and credential rotation

The third Stage 2 session, and **the first since Session 6 that changes how a
human stays logged in.**

Its Run 1 is D683 — the block that has kept `bootstrap_identity` red for nine
sessions and the reason the signing key cannot be rotated today. Everything else
in the session is behind it, because a session about credential lifecycle that
cannot rotate its own signing key is a session arguing with itself.

**Read `docs/plans/stage-2-plan.md` first.** It owns where Stage 2 starts, why
there are six sessions, and the standing security invariants. This document does
not repeat them.

---

## Status — read this first

```
SESSION 15 IS IN PROGRESS. **RUNS 1-7 ARE DONE. RUN 8 -- THE HOST TRIP -- IS NEXT.**
HEAD d67cb44, main, clean and pushed.
CURRENT_SESSION **15** since Run 7, template_version **0.4.0**.
                 outputs schema **stays v14**: nothing needed publishing (D855).
divergences     **Next free: D857.** D812-D820 planning-time, D821-D825 Run 1,
                D826-D831 Run 2, D832-D837 Run 3, D838-D843 Run 4,
                D844-D848 Run 5, D849-D852 Run 6, D853-D856 Run 7.
ADRs            174. **Next free: 0175.** Run 1 wrote 0170, Run 2 wrote 0171,
                Run 4 wrote 0172 (which closes D503), Run 5 wrote 0173,
                Run 6 wrote 0174.
migrations      **26 released.** Runs 2-5 added 0023, 0024, 0025, 0026.
                D837's function landed in 0026 with its caller, ungranted.
                Fix-forward only; every down block raises AP900.
claims          **86** since Run 7, and five `IDN-*` requirements are
                registered. The four new ones are `not_run` until Run 8's
                trip: each needs a live half, which `claim_mode` requires
                and D856 records.
                **8 inherited not_run**, unchanged from Sessions 13 and 14.
                Run 1 closes `bootstrap_identity` when Run 8 deploys.
evidence        evidence/session-14.json merged: 74 passed / 8 not_run /
                0 failed. Session 15 inherits those eight as not_run.
host            62.238.99.122. **Runs Session 14 on both projects** -- the
                first time in three sessions the host and the tree agree.
                18 containers. 3814 MB, NO SWAP.
suite           Last full run at the Session 14 close gate. **Do not gate at a
                run close.** Before the Run 8 trip, at session close, or when
                asked -- nowhere else.
```

**Four facts shape this session, and all four were measured against the tree
before it was planned:**

1. **There is no refresh-token plane to extend** (D812). The stage plan's brief
   reads as though one exists. It does not — no route, no table, no column,
   across 22 released migrations.
2. **A token lives at most 930 seconds and nothing renews it** (D813). That
   makes the absence a *credential-retention* defect rather than a convenience
   one, and it is the argument for building the plane.
3. **D683 is one unconditional line** (D814). The characterisation in
   `docs/scope-closure.md` is exact, and the fix is a guarded omission — the
   cost is the deploy and the four verifiers, not the code.
4. **The rotation vocabulary already exists on all 19 secrets and nothing reads
   it** (D816). Session 15 does not invent a rotation model. It verifies one
   that has been declared for five sessions and never exercised.

---

## 0. Where the session starts

`docs/plans/stage-2-plan.md` §0 and §3, plus Session 14's close: all eight runs
done, deployed on both projects, evidence merged at 74 passed / 8 not_run / 0
failed.

**One thing is different from the last two sessions and it matters.** The host
runs the release the tree describes. Sessions 13 and 14 both began with a host
several sessions behind, and both paid for it — D811 was an edge still serving
Session 12's static configuration, found by an alert rather than by a preflight.
Session 15 starts from agreement, so **any divergence between host and tree
during this session was introduced by this session**, which is a much cheaper
thing to diagnose.

---

## 1. The divergence table

Six columns, the house shape. **Every row is a fact measured against the tree at
planning time**, not a prediction.

**Next free number after this table is D857.**

| # | The plan says | The repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D812** | Session 15 adds *"rotating human refresh tokens with family reuse detection, session listing and termination"* — read as extending an existing session plane. | **There is no session plane of any kind.** No `/auth/refresh` route: the auth router publishes 11 endpoints and none renews anything. No refresh or session table across **22 released migrations**. No `refresh_token` column anywhere. The string `refresh_token` appears in exactly one place in the whole tree — `config.SENSITIVE_KEY_DENYLIST`, where it is listed as a value that must never be logged. **The only thing this repository knows about refresh tokens is that they must be redacted.** | **Session 15 builds the plane, and the plan says so.** Runs 2 and 3 are new construction — a migration, a table, an endpoint — not an extension. The brief's verb is wrong and the estimate that followed from it was wrong with it. | **A brief that says "rotate X" when X does not exist prices a feature as a modification.** The stage plan was written against Stage 1's specification, which is the same error §1 of that document (D704–D718) was written to catch, recurring one level down. The redaction entry is the tell worth keeping: **somebody designed for this value's existence and nobody built it**, so the guard has been protecting an empty set since Session 4. | — |
| **D813** | A missing refresh plane is a convenience gap — users log in more often than they would like. | **It is a credential-retention defect.** `claims.MAX_TTL_SECONDS` is **900**, `service.TOKEN_TTL_SECONDS` is `MAX_TTL_SECONDS` exactly — the service issues at the ceiling — and `CLOCK_SKEW_SECONDS` is **30**. A token is live for at most **930 seconds**, and `TokenResponse` carries `access_token` and `token_type` and nothing else. **There is no renewal path at all**, so any client staying logged in beyond 15 minutes must hold the password and replay it. | **The plane is justified on credential handling, not on user experience**, and the requirement is written that way. Its proof asserts that a client can maintain a session across the TTL boundary **without retaining the password**. | **This is the strongest argument in the session and it was not in the brief.** A 15-minute token was chosen (correctly) to bound the blast radius of a compromised token — and with no renewal, it silently pushes every client toward storing the more valuable credential instead. **A control that makes the thing it protects more likely to be mishandled elsewhere has moved the risk, not reduced it.** The short TTL is right; what is missing is the half that makes it affordable. | — |
| **D814** | `bootstrap_identity` is red and closing it is a session-scale piece of work. | **It is one unconditional line.** `bin/render-jwks.py:build()` appends the bootstrap issuer's key with no guard, while the auth key and the prepared key are each behind `is_file()`. `jwt_keys.MAX_VERIFICATION_KEYS` is 2 and `build_jwks` refuses a third, so the set has been full since the auth service existed in Session 6. `retire` cannot free the slot — `retire_after` is `None`, and it refuses with *"no rotation is in flight."* | **Run 1, and it is first.** A guarded omission, ADR 0170, a deploy, and **all four verifiers recreated** — which ADR 0155's mount-content digest makes automatic rather than remembered. | **The code is small and the risk is not, which is why it is Run 1 rather than a tidy-up at the end.** Every verifier in the deployment reads the published key set; omitting a key from it is the operation that, done wrong, refuses every live token at once. Doing it first means the rest of the session runs against a key set that can actually be rotated — and a session about credential lifecycle whose own signing key is frozen would be **proving rotation with the one credential that cannot be rotated left out of the proof.** | 0170 |
| **D815** | Session 15 is *"identity lifecycle and credential rotation"*, one session. | **The brief names four planes**: the bootstrap retirement, a human session plane, agent credential expiry with admin password reset, and rotation for every credential class — *"PostgreSQL service credentials, R2 application credentials, backup credentials — each with rotation evidence and a rollback procedure."* Nineteen secrets are declared in `secrets.required.yaml`. Session 14 spent eight runs on **one** plane. | **The first three are built; the fourth ships as a SURFACE with one class proved end to end** (Run 6), and the remaining classes are reachable by the same command once their flags are verified. Named here rather than discovered in Run 6. | **Rotating nineteen credentials in one session would produce nineteen rotations nobody watched.** Each service credential rotation is a live restart of something that is currently serving, and the evidence that matters is *the rollback worked*, which cannot be gathered in bulk. **Scoping this in the plan is the cheap moment; scoping it in Run 6 costs the run.** | — |
| **D816** | Rotation tooling has to define what rotating each credential class means. | **The vocabulary is already declared on every one of the 19 secrets** — `rotate_by_replacement`, `must_refresh_on_start`, `one_time_initialization`, `redaction` — with the reasoning written into the file: *"one_time_initialization: true records \[that a rotation did not happen], so that rotation tooling refuses to report a rotation it did not perform"* (D56). **Nothing in `bin/` or `src/` reads any of the three flags.** The only reader in the tree is `tests/contract/test_backup_plane.py`, which asserts them for **three** secrets. | **Run 6 verifies the flags before it reads them.** The rotation surface is driven by the contract, and the run's first act is to check all 19 against what is true — not to trust 16 fields nobody has ever exercised. | **A declared field with no reader is an unverified field**, and this is the largest instance in the repository: a complete, carefully-argued rotation model, five sessions old, of which 3 of 19 rows have ever been checked against reality. **The model is almost certainly right and that is exactly why it is dangerous** — a rotation command driven by it would inherit sixteen assumptions in one step, and each would fail as a wrong action on a live credential rather than as a refusal. §7's standing defect, at the scale of a whole contract. | 0171 |
| **D817** | `revoked → active` answering 200 is an open question for someone to decide. | **The stage plan assigns the decision to this session**, and the measured position is unchanged: migration 0011 calls a revoked agent credential terminal, `auth_set_agent_status` is an unguarded `UPDATE`, and the bound half is proved — `authz_version` moves on every transition, so no token issued before either state survives. | **Run 4 decides it, and the plan does not pre-decide it.** The run measures what un-revoking currently restores — whether the *credential* comes back or only the *row* — and the ADR follows the measurement. | **The safety half is genuinely proved and that is what makes this a decision rather than a defect.** Nothing is currently unsafe; what is undecided is whether an operator who revokes a credential should be able to undo it, and **that answer depends on whether `revoked` means "compromised" or "switched off"** — a question about meaning, which is what an ADR is for. Deciding it by measurement first avoids ratifying whichever behaviour the unguarded `UPDATE` happens to produce. | 0172 |
| **D818** | Session 15 adds requirements, so `CURRENT_SESSION` moves to 15. | **Moving it is all-or-nothing** (D690). `test_no_requirement_at_or_before_the_gate_session_remains_future` refuses any requirement due by the new number that is still a placeholder, and **there are no `future` placeholders left** — so every requirement targeted at 15 must be activated, with its proofs, in the same commit. | **Run 7, exactly as Session 14 did it**, and §2 fixes the requirement ids before Run 1 rather than discovering them at Run 7. | **Session 14 proved this ordering works and why it has to be planned early**: the registry additions are decided in §2 at planning time precisely because the bump cannot be partial. A requirement invented in Run 5 and forgotten in Run 7 is a gate failure at the least convenient moment. | — |
| **D819** | The host is a known quantity, so Run 8 is a deploy. | **It is the first trip in four sessions that recreates the verifiers as its point** rather than as a side effect. Run 1 changes the published key set; ADR 0088 requires every verifier recreated after that, and there are **four** — PostgREST, auth, storage, the agent plane. ADR 0155's content digest makes it automatic, and **automatic has never been checked against a key-set change on this host.** | **Run 8 verifies the recreation happened, per verifier, and that each one accepts a token signed by the surviving key** — not that the deploy exited 0. | **ADR 0155 was written in Session 10 and its key-cutover case has never fired on the deployment.** A mechanism whose most important trigger has never occurred live is a mechanism with one untested path, and this is the session that pulls it. **`--setup-plan` before the trip** (D671, D676), because the proofs here run against a key set mid-change. | 0088, 0155 |
| **D820** | Session 15's new proofs are offline-provable, like most of Session 14's. | **The load-bearing ones are not.** Reuse detection is a property of *two requests arriving in sequence against one row*; a rotation's evidence is *the service still serves afterwards*; and the verifier recreation is a property of the deploy. Each needs a live half, and the offline half proves the logic, never the event. | **§7 fixes each claim's honest verdict now**, before the proofs are written, and no claim spans both `host` and `external` mode. | **Session 13 wrote §7 before its proofs and Session 14 inherited twelve `not_run` claims it could not close** — which ADR 0163 made legible rather than embarrassing. **Deciding what a claim may honestly report before writing its proof is what stops the proof from being shaped to a verdict.** | 0163 |

| **D821** | Run 1 retires the bootstrap issuer's key, which the ledger characterises as inert public material behind one unconditional line. | **The key has a live signer, and the deploy is its consumer.** `bin/dev-token.py` signs with `bootstrap_jwt_signing_key.pem` — measured with a four-arm rig whose fourth arm controls for the omission also dropping the auth key. `deploy-project.py:observe_served_document` mints one **on every deploy**, as the documentation role, to produce `api.served_checksum`, and catches broadly. `bin/api.sh`, `bin/dev-token.sh` and the deployment suite's `dev_token` fixture are the other holders. | **Run 1 became two steps, in this order: move the minter to the issuer's own key, then guard the append.** ADR 0170. The `kid` follows the key path (ADR 0094) and there is one `iss` with several `kid`s, so the switch is claim-neutral. | **Retiring it first would have made every deployed document report `api.status: unavailable`** — silently, through an `except` written to keep a deploy honest rather than to hide a defect. That is D701's shape, a signal always red, and it fails *safe*, which is exactly what would have let it survive. **The ledger was accurate about `render-jwks.py` and incomplete about the system**, which is the difference between reading a file and asking who depends on it. | 0170, 0094 |
| **D822** | The retirement is symmetry: guard the third append like the two beside it. | **The three were never symmetrical.** `signing_key_path()` **raises** `JwksError(5)` on absence; `auth_key_path()` and `prepared_key_path()` return a path the caller guards. And the first draft of ADR 0170 claimed the ceiling became unreachable once only two keys were publishable — **the rig's control arm measured otherwise**: a generation still holding the bootstrap key beside the auth key and a prepared one offers three, and `build_jwks` refused it there exactly as designed. | **`signing_key_path` returns a path, the caller guards it, and the ceiling's proof stays.** Its test now records why: the state this change passes through is precisely an operator preparing a rotation before the retiring deploy has run. | **A bound whose last violation you have just removed is the bound you are most likely to delete the proof of.** The measurement corrected the ADR's own draft, which is what the control arm was for — and the corrected version is the stronger argument, because during the transition the ceiling is not vacuous, it is load-bearing. | 0170 |
| **D823** | `promote` advances a prepared rotation, so the retirement only frees a slot for it. | **`promote` infers the incoming key as *"whichever published kid is not the active one"***, with no guard separating a prepared key from the bootstrap one. `promote_rotation` checks that the kid is published, is not active, that consumers are non-empty and that the digest is a sha256 — none of which distinguishes them. **Today it would promote the bootstrap key.** | **Nothing is added there.** The retirement removes the state in which the existing inference is wrong: with the set holding the auth key alone, or beside a genuinely prepared one, *"not active"* is the prepared key by the only arrangement the renderer can produce. | **Safe only because the set's second member had never been anything else and nobody had run it.** A latent defect whose trigger was blocked by the very thing this run removes — so the retirement had to make the inference sound in the same step, or it would have unblocked a wrong promotion instead of a right one. | 0170 |
| **D824** | Guarding `render-jwks.py`'s append retires the key; that is the one line D814 names. | **It changes nothing on a deployment.** `active_secrets` filters on `introduced_in_session <= session` and **has no upper bound at all**, so a secret introduced in Session 5 is materialized into every generation for ever. Measured: at session 15 the contract still returned **19 secrets, including `bootstrap_jwt_signing_key`**. The file would be on disk, the new guard would pass, and the published set would stay full — the run would have shipped as a no-op. | **`retired_in_session`**: a schema field, an upper bound in `active_secrets`, and `retired_in_session: 15` on the key. Measured after: **session 14 → 19 secrets with the key; session 15 → 18 without it.** The upper bound is strict so a project pinned to an older release keeps the credential its published set still names. | **The whole run was green in a checkout while being a no-op in production**, because a fixture writes only the keys its test wants and the materializer writes them all — **the fixture and the code sharing a belief the deployment does not.** The sixth question, and the fourth time this shape has been the finding (D673, D680/D682, D687). Nothing already offline would have caught it; the mutation that reproduces it (`M5`) is now in the battery. | 0170 |
| **D825** | `jwt.temporary` records whether the bootstrap issuer is still live, and `SEC-BOOT-001` branches on it. | **It is the literal `True`**, hard-coded in `observe_jwt` under a comment reading *"True until Session 6 replaces the issuer"* — written before Session 6 and never revisited after it shipped. So the field claimed a temporary issuer for **ten sessions** while its replacement was live, and the live proof's false branch **had never executed**. That proof's docstring also described a `deployed_through_session` comparison its body does not make. | **Derived from the contract's retirement** (`secrets_contract.secret_is_active`), passed as a **required** keyword so no caller can publish the claim without deciding it. **The live proof reads the FILESYSTEM instead** and asserts the document agrees — two independent readings, deliberately not the same one. | **A value that looks measured and is not, in the document whose whole job is to say what a deployment established** — §7's standing defect, in the field naming this run's subject. It survived because nothing could reach the branch that would have contradicted it. The offline proof asserts **both** values, because one that only ever passed `True` would pass against the constant it replaced. | 0170 |
| **D826** | Reuse detection is logic: consume the token, and if it was already consumed, revoke the family. | **The outcome is decided by the isolation level, and the two answers are different kinds of thing.** Measured against the pinned image with a control that proves the rig has a real race — both transactions win when the guard is removed. Under `read committed`, which is what the deployment runs: **the loser gets 0 rows and no error**, after **blocking 0.61 s** until the winner commits. Under `repeatable read` the identical statement raises **`40001`**. | **The plane is specified against `read committed` and reads its outcome from the row count**, with the measurement recorded in ADR 0171 and in the column comment rather than beside a query. | **`40001` means "reuse" here and looks like a transient error a client should retry — and retrying presents the replay a second time.** A serialization failure is the one error class whose standard handling is exactly wrong for this path. Nothing today raises the isolation level, so this is a decision that could quietly stop holding rather than a bug; recording it where the next reader of the column will be is the difference between a measured value and a remembered one. | 0171 |
| **D827** | The partial unique index enforces "one live token per family", which is the invariant reuse detection rests on. | **It enforces more than that: it makes the write ORDER a catalog constraint.** Measured in one transaction against the pinned image, then re-measured against the rendered migration after it was applied by the server: **consume-then-insert is accepted, insert-then-consume is refused `23505`.** | **Kept and documented as the constraint it is.** The rotation cannot be written in the wrong order by accident — it fails at the database in every environment rather than passing review and being correct only where somebody remembered. | **The invariant was the goal and the ordering is a free strengthening, so it is worth naming before somebody "simplifies" the index.** Without it, two live tokens per family would mean a thief and the legitimate client each hold a valid token and **neither presentation looks like a replay** — every guarantee in ADR 0171 would reduce to a comment. | 0171 |
| **D828** | Credential material in `app_private` is argon2; both neighbouring tables `CHECK (... LIKE '$argon2id$%')`. | **A refresh token cannot be stored that way, for a structural reason rather than a preference.** An agent presents `agent_id` **and** a secret, and a person presents a username **and** a password — so those rows are found by an identifier and the hash is only ever *verified*. **A refresh token presents only itself**, so the row must be found **by** the stored value, and argon2's per-row salt makes that a full scan with a KDF per row. | **A deterministic hex SHA-256, with `CHECK (token_hash ~ '^[0-9a-f]{64}$')`** stating the shape so a row holding a raw token or an argon2 string is refused at write time. | **A KDF's expense buys resistance to guessing a low-entropy secret**, and this value is 32 bytes from `os.urandom` — the property is not one it needs. Recording the reasoning matters because the table now looks inconsistent with its two neighbours, and the next reader's correct instinct will be that somebody took a shortcut. | 0171 |
| **D829** | Session listing needs enough to identify a session, which conventionally means a device or a location. | **Every candidate field is a caller-supplied string.** A user agent, an address and a device label are all values the client chooses, and the agent plane's standing rule is that a caller value is not recorded. | **None of them is stored.** A session is identified by its id, `created_at` and `last_used_at`. | **This costs something real and it is the point of writing it down**: Run 3's listing cannot say *"Firefox, in Berlin"*, which is a worse product than the obvious alternative. A display string carries the same escaping and redaction questions as any caller value, and *"it is only shown back to its own owner"* is the argument that ends with somebody rendering it in an operator console. If a later session decides the listing needs more, that is an ADR rather than a column added because it seemed useful. | 0171 |
| **D830** | Migration 0023 creates the session plane, so it grants the auth service what it needs. | **0011 already set the terms for its own successors**, in its own words: *"the service reaches this data through SECURITY DEFINER functions that arrive in the same commit as the code that calls them. A grant issued now would be a grant nobody can audit against a caller that does not exist."* | **0023 creates no function and issues no grant**, and a contract test asserts both against the shipped SQL. The functions and their grants arrive in Run 3 with the endpoints that call them. | **The rule is five sessions old and this is the first migration since that could have quietly broken it**, because the tables are useless without a grant and adding one is the obvious next keystroke. **A guard that names the rule is worth more than a comment restating it**, since the failure is invisible: a grant to a caller that does not exist looks exactly like a grant to a caller that does. | 0171 |
| **D831** | Run 2 puts the pure state machine in `src/`, per the session plan's own wording. | **`test_no_module_is_imported_only_by_its_own_tests` refused it** — *"a module with no caller is a feature that does not exist, however well it is tested"* (D204). True, and unavoidable: Run 2 deliberately touches no endpoint, so the caller does not arrive until Run 3. | **The module moved to `services/auth-api/app/refresh_sessions.py`**, beside `claims.py`, `tokens.py`, `scopes.py` and `hashing.py` — the auth service's own pure modules. No allowlist entry, and the guard is untouched. | **The guard was right about the package, not just about the timing.** `agentic_postgres` is what `bin/` and the deploy share, and the session plane is read by the auth service and nothing else — no operator command, no deploy step, no renderer. The plan's *"in `src/`"* was a reasonable default written before anyone asked who would import it. **A guard that produces the correct design rather than an exemption is the outcome worth recording**, because the tempting repair was an allowlist and it would have left the module in the wrong package for ever. | 0171 |
| **D832** | Reuse detection catches a stolen chain: a replayed token means a thief has it. | **It also catches a client racing itself.** Measured through the shipped function: two concurrent presentations of one live token resolve to one winner, and the loser reads the row it lost to as consumed — so **the family is revoked for `reuse_detected` and a legitimate client is logged out.** Two browser tabs, a double-tapped button or a retry wrapper is enough. | **No grace window. The behaviour stands and is written down** — in ADR 0171, in the endpoint's published description, and here. A client must serialise its own refreshes. | **The server cannot distinguish a replay by the owner from a replay by a thief**, which is the whole reason the family is revoked rather than the token alone. A grace window that returned the same successor to a second presenter would hand a thief a valid token for the width of the window, and sizing it would be choosing how long to be exploitable. **The cost is real and lands on a client bug rather than an attack**, which is exactly why it belongs in a divergence row instead of being discovered by a user who was logged out for double-clicking. | 0171 |
| **D833** | The transition lives in SQL and its meaning lives in `classify`, so there is one authority for each. | **They overlap on three facts and cannot avoid it.** The consuming UPDATE guards on consumed, expired and revoked; `classify` refuses on the same three. Only consumption RACES, so only consumption needs the database — but a guard checking consumption alone would **CONSUME an expired token before refusing it**, and the next presentation of that token would read as a replay and revoke the family. | **The overlap is declared and TESTED as a correspondence**, not removed: `test_the_sql_guard_and_the_state_machine_refuse_on_the_same_three_facts` reads the guard out of the migration and compares it against `TokenState`'s fields, the way `jwt_claims.sql_required_claims()` is compared against 0011's literal. | **A false reuse alarm on a legitimate late retry is worse than the duplication**, and that is the trade the design makes. The mutation that drops the expiry condition (`M3`) is what proves the test covers it — without that arm the guard could quietly lose a condition and every endpoint test would stay green, because the outcome a caller sees is a 401 either way. **The failure is invisible from outside; only the family's fate differs.** | 0171 |
| **D834** | `/auth/refresh` is an auth route, so it sits behind the same `authenticate` call every other route uses. | **That implementation passes every other test in the file and is useless.** A renewal requiring a live access token only works while the access token is live — which is precisely when nothing needs renewing. The route is reached with an expired token or none at all. | **The refresh token IS the credential**, carried in the body rather than a header or a path so no proxy, access log or `Referer` records it, and `test_refreshing_needs_no_access_token_at_all` exists specifically to fail the obvious version. | **The obvious wrong implementation is invisible to every test that logs in first**, because they all hold a fresh token. Nothing in the suite would have noticed, and the defect would surface as *"users are logged out after fifteen minutes"* — the exact symptom the plane was built to remove, now with a session table to make it look solved. | 0171 |
| **D835** | Adding three routes is adding three routes. | **`test_the_application_serves_exactly_the_declared_paths` refused them**: the application served three paths `main.public_paths()` did not declare. Its docstring gives the reason — *"a new path whose author has not said which side of the edge it belongs on fails here rather than appearing on the internet."* | **All three declared, each with the reason it is on that side**, and the two that require a bearer are separated in the comment from the one that must not. | **A route reaches the internet as soon as the edge publishes it, and nothing else in this repository asks the author to say so.** The guard converts an omission into a decision, and it caught this the first time the session plane grew a surface — which is what it was written for. The same run's regenerated artifacts (`contracts/app-openapi.canonical.json`, both fixture renders) are the rest of what a route change touches. | — |
| **D836** | The grant test asserts that `auth_service` receives EXECUTE on exactly five functions. | **It asserted three.** Its extractor read the migration line by line, and **three of the five GRANTs wrap across lines** — so the parser saw two of them as unrelated fragments, built a smaller set, and the test failed against a migration that was correct. | **The extractor now matches whole `GRANT … ;` statements**, which is what a grant is. | **A parser that misses part of what it checks reports the smaller set as the answer**, and this one failed loudly only because the expected set was written out. Had it been written as *"at least these"*, or had the migration's grants all been single-line at first and wrapped later, it would have gone quiet and kept passing over a shrinking set. **§7's family, in the proof rather than the product**, and the cheapest possible instance of it. | — |
| **D837** | 0024 ships the session plane's callable surface, so it ships every function the plane will need. | **One of them had no caller.** `auth_revoke_user_sessions` ends every live session a subject has, which is what Run 5's password reset needs — a reset otherwise leaves a refresh chain outliving the password it was obtained with — and nothing in Run 3 calls it. It was written, granted `EXECUTE`, and reached by no code. | **Removed from 0024, from the repository and from the grant set**, with a comment in the migration saying why and where it goes. Run 5 adds it with migration 0025 and the caller that uses it. | **This is 0011's rule, broken in the run AFTER the one that turned it into a contract test.** Run 2 asserted that 0023 issues no grant *because its caller does not exist*, and one run later I granted EXECUTE on a function nobody calls — in the migration whose own header quotes that rule. **The guard did not catch it**: `test_the_migration_issues_no_grant_because_its_caller_does_not_exist_yet` names 0023, so it is a rule for one file rather than for the class. What caught it was re-reading the header while writing the Done marker, which is not a control. | — |
| **D838** | `revoked → active` answers 200 and nobody has decided whether it should (D503). The open question is a policy choice. | **It restores the ORIGINAL secret.** Measured end to end through the running service against a live cluster: exchange **200** fresh, **401** revoked, **200 again** after re-activation, with `authz_version` at 1, 2, 3. Revocation frees no credential — it flips a flag. The half D503 always called safe is real: a token issued before the revocation is still refused afterwards, because `authz_version` moved twice. | **The transition is refused** (ADR 0172), `AP409`/`PT409`, and only that transition. | **This is not a policy choice, it is a silent restoration.** An operator who revokes because a secret leaked and later re-activates has handed the leaked secret its authority back, and nothing in the API or the record distinguishes that from a deliberate reinstatement. **The measurement is what changed the question** from *"should un-revoking be allowed"* to *"should a revocation be undoable by flipping a flag"*, and those have different answers. | 0172 |
| **D839** | Refusing `revoked → active` closes D503; rotation is the documented recovery, so the way back already exists. | **Rotation is not a way back.** Measured: rotating a revoked agent answers 200, replaces the secret, moves `authz_version` — and **leaves the agent revoked**, with the new secret refused. So the only path from `revoked` to a working agent was the transition that restores the old secret. | **Rotation clears the revocation**, in the same transaction as the new secret. One operation, so an agent never becomes active holding the credential its revocation answered. | **Refusing the transition alone would have stranded every agent revoked by mistake**, recoverable only by creating a new one with a new id, new grants and a new owner record — and the ADR would have shipped calling that "the documented recovery". **The second measurement is what stopped a correct-sounding decision from being a harmful one**, and it was only taken because the first one made the decision real enough to ask what came next. | 0172 |
| **D840** | Adding a returned column to a released function is a `CREATE OR REPLACE`. | **It is a `DROP`.** `CREATE OR REPLACE` refuses to widen a `RETURNS TABLE` — **42P13**, measured, with an identical replace accepted as the control. And **a `DROP` takes the grant with it**: a grantee present in `information_schema.routine_privileges` before was absent after the recreate. | **Four functions dropped and recreated in 0025, every grant re-issued**, and the migration says why beside them. | **Forgetting a grant is silent in the migration and a `permission denied for function` at runtime**, on a path the offline suite does not exercise as the service's role. Two measurements, both cheap, both decided the file's shape — and the second is the one that would have shipped broken, because a migration that drops and recreates *looks* complete without it. | 0172, 0091 |
| **D841** | The existing test asserting `revoked → active` answers 200 must be replaced, which is a weakening a new ADR has to authorise. | **The test asked for this.** It is named `..._terminality_is_UNENFORCED`, and it ends: *"un-revoking is now refused, which is a product change. If it was intended, **invert this assertion and close D503**; the guard belongs in a migration."* | **Inverted exactly as instructed**, renamed to `..._revocation_is_terminal`, and extended to assert the refusal changes nothing, that rotation is the way back, and that the pre-revocation secret is dead afterwards. | **A test that documents the day it will fail, and what to do then, is the cheapest possible handover** — six sessions later the replacement took no archaeology and no judgement about whether the old assertion was load-bearing. **It is the opposite of the defect this project keeps producing**: not a value that looked measured and was not, but an assertion that stated its own premise and named its own expiry. | 0172 |
| **D842** | An expiry on a credential is a lifecycle field; checking it where the credential is minted is where it belongs. | **That is a policy, not a control.** An expiry consulted only at issuance constrains the mint and nothing else — the credential it produced outlives the rule, and nothing refuses it. | **Enforced at VERIFICATION**, and the database computes `secret_expired` against its own `now()` so there is one clock in the decision. The check sits **after** the hash comparison and beside the status check, so an expired credential costs the same Argon2 verification as a wrong secret and is indistinguishable from an unknown agent. | **The placement is the whole feature.** A test asserting only that an expired secret is refused would pass against a check anywhere in the function, including one that answers in microseconds and makes "this agent exists" measurable by timing — which is precisely what the battery's `M4` demonstrated when it survived. | 0172, 0171 |
| **D843** | Two mutations survived the Run 4 battery, so the mutations were uninformative. | **Both survived because a docstring claimed a property its body did not check.** `M4` moved the expiry check above the hash: no status changed, no body changed, and the endpoint test asserting those two things stayed green while the timing property its docstring claimed was gone. `M5` added a column `DEFAULT`: every fixture creates its agents *after* the migration, so none can observe a backfill. | **Two guards, both over the construct.** An AST check that every state read follows every `verify`, and a check that the `ALTER` carries no `DEFAULT`. | **And the first guard was itself blind on its first write.** It anchored on `min(verify)`, and `agent_token` verifies twice — the earlier call being the dummy hash that exists *for this very timing property* — so a check inserted after the lookup still compared as "after a verify" and `M4` survived again. `max` is the anchor. **Three layers of the same defect in one run**, each found only by running the mutation rather than reading the guard. | 0172 |
| **D844** | Run 5 builds admin-controlled password reset, so the administrator gains the ability to reset a password. | **An administrator has been able to set one since Session 6.** `PATCH /admin/users/{user_id}` accepts a `password` member, and an administrator using it **chooses the value and therefore knows it** — and can log in as that subject afterwards. The capability the run was framed as adding already existed; what did not exist is the half where the administrator does *not* learn the credential. | **The reset issues a TOKEN and the subject chooses the password** (ADR 0173). The direct set stays, because provisioning needs it — somebody has to set the first password. | **"Without learning it" is a contrast, and the thing it contrasts with had to be found before the sentence meant anything.** The residual is stated rather than implied: an administrator who issues a reset could spend it themselves. That is inherent to any administrator-initiated recovery and is not new — the same role can already set a password, disable an account or change its scopes. **What changes is that the ordinary path no longer requires it.** | 0173 |
| **D845** | `credential_version` moves on a password change and refuses every token issued before it, so a reset invalidates the old credential's access. | **It refuses every ACCESS token and reaches no refresh chain.** Session 15 Run 2 added a plane in which **a refresh token names a session rather than a credential**, so a chain obtained with the old password would keep minting access tokens after the password changed. The reset would look complete and leave a live way in. | **`auth_consume_password_reset` ends every session in the same transaction**, with `credential_changed`, calling 0012's `auth_set_password` rather than restating it. | **This is question 5 arriving on the same session's own work.** `credential_version` was complete when it was written in Session 6 and became incomplete three runs ago, when this session gave the deployment a second kind of credential. **The decision did not change; the world gained a case** — and the run that added the case is the run that had to notice. | 0173, 0078 |
| **D846** | `auth_revoke_user_sessions` was removed in Run 3 for having no caller, so Run 5 restores it. | **It is not restored — it is written where its caller is**, in 0026, and it is **not granted to the auth service** at all. Its only caller is inside `auth_consume_password_reset`, so it needs no grant. | **Kept ungranted.** A grant the service does not need is a capability it does not hold, and the class guard added in Run 3 only checks that *granted* functions have callers. | **D837 closes here, and the shape it closes into is better than the one it was removed from.** Run 3 would have granted it to the service beside four others; Run 5 gives it exactly one caller and no grant. **The rule that forced the removal produced a smaller privilege surface than the version that broke it**, which is the argument for enforcing it as a class rather than treating it as bookkeeping. | 0173 |
| **D847** | The reset needs a single-use token, and Run 2 already built one for sessions. | **Reusing it meant deciding where the primitive lives.** `mint`, `hash_token` and `is_wellformed` were in `refresh_sessions`, named for the plane that happened to need them first, and a reset importing `refresh_sessions.mint` reads as the wrong module doing the wrong job. | **Extracted to `app.one_time_tokens`**, with `refresh_sessions` re-exporting them so every existing caller and Run 2's 27 tests keep working unchanged. | **The alternative was a second minting routine**, and two implementations of one value is precisely what ADR 0002 exists to prevent: the second is always slightly weaker and nothing compares them. **The split is also the honest one** — what a token IS belongs to the primitive, and what a presented token MEANS stays with the plane that can answer it. | 0173, 0002 |
| **D848** | A reset's failure modes are: unknown, spent, expired. | **There is a fourth, and it is the one that strands somebody.** If the token is spent *before* the chosen password is screened, a subject who picks a weak password holds a consumed reset and an unchanged credential — **unable to log in and unable to reset**, which is strictly worse than the refusal that produced it. | **The password is screened before the token is spent**, and `test_a_weak_password_does_not_spend_the_reset` asserts the token still works afterwards. | **The ordering is invisible in every response.** Both versions answer 422 to the weak password; they differ only in what the subject can do next, which no status code carries. It is the same class as Run 4's expiry-before-hash mutation — **a property that lives entirely in the order of two statements and shows up in no observable output** — and both were found by mutating rather than by reading. | 0173 |
| **D849** | Sixteen rotation flags are unverified assumptions (D816), so Run 6 verifies them and then drives the surface from all three. | **One of the three cannot be verified, because the behaviour it selects between was never built.** `must_refresh_on_start` chooses between failing closed and starting on a cached last-known-good value. `bin/materialize-secrets.py` has **no cache, no fallback and no last-known-good path** — every provider failure except a 404 on an optional secret fails the whole run. The phrase "bounded last-known-good start" appears in this repository **only inside `secrets.required.yaml`'s own comments**. | **The surface does not report it, and says why.** Six `false` declarations describe leniency that does not exist; the `true` behaviour is the only behaviour. A contract test asserts the materializer still has no fallback, so the day one is built the test goes red and the flag becomes real. | **D816 said the flags were unread. This is worse and more useful: one of them is unREADABLE.** A surface driven by it would have printed a difference between six secrets and thirteen that the deployment cannot act on — a distinction with no consequence, which is the most durable kind of wrong documentation. **Two of three are now verified and driven; the third is a specification awaiting its mechanism**, and this run does not claim to have closed D816 for it. | 0174 |
| **D850** | `one_time_initialization` is one property: the value is read once at initialization. | **It covers two different phenomena.** `postgres_init_superuser_password` is read once and **nothing is bound to it** — the cluster keeps whatever initdb set, and the file is never read again. `pgbackrest_repo_cipher_pass` is the opposite: the value **is** bound, to the repository, at `stanza-create`. Replacing it does not leave the system using the old value; it leaves the reader holding the wrong one for every backup ever taken. | **The consequence is shared and the mechanism is spelled per secret.** The flag stays — it is right that replacement achieves no rotation — and the surface refuses with the sentence that actually describes each. | **One sentence covering both is plausible and wrong for one of them**, which is D278: a repair that works is not evidence its explanation is right. The first draft of the surface printed the `initdb` sentence for the cipher pass, and it read perfectly — an operator would have learned a wrong mechanism from a correct refusal. | 0174 |
| **D851** | The two observable flags are assumed correct because the contract is careful and five sessions old. | **Both measured against the pinned image, and both hold.** Replacing `postgres_init_superuser_password` over the same data directory: the replacement is **refused** and the original **still works** — new=False, old=True. A database role password rotates end to end, with the rollback rehearsed *before* the rotation and working after it. | **Recorded as measured rather than assumed**, and the surface is driven by flags that were checked. | **The control is what makes the first one evidence.** "The new password does not work" is equally consistent with a container that failed to start; "and the old one still does" is what makes it a live cluster keeping its original credential. **The rig also had two of my own bugs first** — a bare `-e POSTGRES_PASSWORD` shadowing the value, and the data volume mounted at the wrong path, which would have compared two unrelated clusters and produced a clean-looking refutation of a true flag. | 0174 |
| **D852** | A mutation that disables the `one_time_initialization` branch should make the surface claim a rotation. | **It survived.** Every secret declaring `one_time_initialization: true` **also** declares `rotate_by_replacement: false`, so the second branch still refuses and the property holds. The mutation is uninformative (D493) — the refusal is over-determined by the data. | **Recorded as uninformative, and the gap it exposed is closed.** Nothing required the two flags to agree: the contract permitted `one_time_initialization: true` beside `rotate_by_replacement: true`. That guard now exists and was **verified firing** by injecting the contradiction. | **The survivor was worth more than a kill.** It did not find a weak test; it found that two independent conditions have always agreed, that nothing required them to, and that a contradictory declaration would produce a plan reporting a rotation the secret's own entry denies. **Asserted as an implication rather than an equality**, deliberately — `rotate_by_replacement: false` without `one_time_initialization` is a legitimate "replacement does not rotate this, for some other reason", and forcing the converse would make a future entry lie to satisfy a test. | 0174 |
| **D853** | A session gate is derived from its predecessor by diff, which D505, D507, D678 and D703 made a rule and Session 13 rewrote its header to honour. | **`bin/session-14-check.sh` opens with "The Session 13 gate" and claims to be derived from `session-12-check.sh`.** Session 14 copied Session 13's header whole and changed only `readonly SESSION=14` — in the file whose next paragraph records that *"nothing diffs the prose a gate carries"* and that around thirty stale references had survived two derivations. **The warning and the defect are eleven lines apart.** | **Session 15's header is rewritten, and Session 14's is corrected in place** rather than left as a record: a wrong header is not a record of a release, it is an error the next derivation copies. | **D693's guard is scoped to the `--session N` an operator TYPES**, and it is right not to flag prose — the numbers a reader would act on are checked, and it caught seven of them this run. What nothing checks is a gate's own account of itself, which has now been wrong in three consecutive derivations. **The chain is broken here by fixing both files rather than only the new one**, because fixing only the new one is precisely what Session 14 did. | — |
| **D854** | The `IDN-*` live proofs read `APG_ADMIN_PASSWORD_FILE`, open a session and reach the identity plane. | **My first draft built all of that itself**, and the deployment suite already had it: `admin_password`, `administrator_username` (read from `outputs.json`, never re-derived), `app_login`, `api_call`, `app_base` and `admin_session`. The draft re-derived the username, composed URLs from the domain, and read the password file with **`.strip()`** where `conftest` deliberately uses `.removesuffix("\n")`. | **Rewritten against the suite's fixtures.** Nothing in the file reads an environment variable or builds a URL. | **`.strip()` is the one that would have shipped.** `conftest`'s comment says why: *a password may legitimately end in a space, and `.strip()` would silently authenticate as something the operator did not type* — which fails as a wrong password and reads as a broken deployment. **Question 6 in the fixture I was writing rather than one I inherited**: the belief was mine, the code under test was mine, and only the suite's existing answer disagreed. `app_base` also refuses a route that is not `ready`, where my version would have composed a URL against which every negative assertion passes on a 404. | 0002, 0158 |
| **D855** | The bump moves `CURRENT_SESSION` and `template_version`, and the outputs schema follows as it did in Session 14. | **Nothing this session built needs publishing.** Session 14 moved to v14 because a *route* had to reach `outputs.json`. Every endpoint Session 15 added — `/auth/refresh`, `/auth/sessions`, `/auth/reset-password` and the admin reset — sits under the `routes.app` prefix the document already carries, and the plan said in advance that the schema moves *only if something needs publishing*. | **The schema stays at v14**, and the gate's header says so rather than leaving the absence to be noticed. | **A schema bump out of habit is a migration nobody needed**, and every deployed document would have had to be migrated to record no new fact. **The plan pre-committed the test for this before the run could rationalise one** — which is the value of deciding it at planning time rather than when the diff is in front of you and v15 looks tidier. | — |
| **D856** | The five requirements activate with their proofs, which Runs 2–6 wrote. | **Every one of those proofs is offline**, including the ones standing up a real cluster in `test_auth_endpoints.py` — and `claim_mode` refuses a claim whose every node id is offline. Four claims would have been unprovable at the moment they were registered. | **`tests/deployment/test_session15_identity.py`**: eight live proofs, at least one per claim, each reaching the identity plane through the published route. | **A cluster this repository stands up is not the deployment an operator runs**, which is ADR 0065/0066 stated the other way round. The contract tests prove the logic; only these prove the edge routes to it, the migrations are applied there, and the credentials that deployment holds work. **The bump is what forced the distinction**: the proofs existed for four runs and nothing required them to reach a front door until a claim had to name them. | 0065, 0066 |
---

## 2. What Session 15 adds to the acceptance registry

Decided now, because the `CURRENT_SESSION` bump is all-or-nothing (D818, D690).

**Family: `IDN-*`**, as the stage plan proposed. Five requirements, four new
claims. `bootstrap_identity` is an **existing** claim that Run 1 closes; it gains
no new id.

| Requirement | Claim | What it says |
|---|---|---|
| `IDN-SESSION-001` | `session_lifecycle` | A client maintains a session across the token TTL boundary **without retaining the password**, and a refresh token is single-use: presenting one twice invalidates the whole family. |
| `IDN-SESSION-002` | `session_lifecycle` | A subject's live sessions are listable and individually terminable, and a terminated session's refresh token is refused thereafter. |
| `IDN-AGENT-001` | `agent_credential_lifecycle` | An agent credential carries an expiry, expiry is enforced at verification, and the `revoked → active` transition behaves as ADR 0172 decides. |
| `IDN-RESET-001` | `password_reset` | An administrator resets a user's password without learning it, `credential_version` moves, and every token issued before the reset is refused. |
| `IDN-ROT-001` | `credential_rotation_surface` | Every declared rotation flag matches the credential it describes, and one credential class rotates and rolls back with evidence. |

**`credential_rotation_surface` is not `credential_rotation_planes`.** The latter
is an existing `not_run` claim describing an **event an operator performs**;
this one describes a **surface the repository ships**. Naming them apart is
deliberate — D696 is the record of a claim's session moving by accident, and two
claims one word apart is how that starts.

---

## 4. Irreversible operations

| Operation | Run | What makes it safe |
|---|---|---|
| **Removing the bootstrap issuer's key from the published set** | 1 | It is the operation that, done wrong, refuses every live token at once. Safe because the auth key is published first and has been the signing issuer since Session 6, so the surviving key is the one live tokens actually carry — **verified by measuring which `kid` current tokens present, before the omission, not by reasoning about it.** The bootstrap key's own tokens are ≤930 s old by D813, so the window in which one could exist is bounded and known. |
| **Migration 0023** | 2 | Released migrations are never amended; every down block raises AP900. Additive only — new tables in `app_private`, no column dropped, no existing grant changed. |
| **Recreating four verifiers** | 1, 8 | ADR 0088, automated by ADR 0155's content digest. **Unsafe if it silently does not happen**, which is D819's whole point: Run 8 verifies per verifier rather than trusting the deploy's exit code. |
| **Rotating a live service credential** | 6 | One class only (D815), with the rollback rehearsed **before** the rotation, not after. `one_time_initialization` exists so tooling can refuse to claim a rotation it did not perform — Run 6's command must refuse rather than report success on those. |
| **The `CURRENT_SESSION` bump** | 7 | All-or-nothing (D690). Every requirement in §2 activates in the same commit, with its proofs. |

---

## 5. Build order, run by run

Each run gets a `**Done.**` marker and a retrospective half saying what it
**measured**. That is what a later session reads to find out why something is
the way it is.

The mutation-battery rules apply to every run that writes a test: pre-flight
every anchor and make a failure fatal (D269), a control the mutation **cannot
reach** (D499), and an assertion about **how** each mutation failed, since
pytest distinguishes `FAILED` from `ERROR` (D386).

### Run 1 — retire the bootstrap issuer

**Closes `bootstrap_identity`, the only one of the eight `not_run` claims this
session can close by writing code.**

Measure first, in this order, because the omission is only safe if the second
answer is what D814 predicts:

1. Which `kid` does the auth service currently sign with, and which keys are in
   the published set? Read the deployed `jwks.json`, not the renderer's output.
2. Does any live token carry the bootstrap `kid`? Bounded by D813's 930 s.
3. What does `retire` do once a slot is free — the ADR depends on whether
   retirement becomes reachable or merely stops being refused.

Then: a **guarded omission** in `render-jwks.py:build()`, symmetrical with the
two guards already beside it. ADR **0170**. Deploy, and recreate all four
verifiers.

**The control that matters:** a token signed by the surviving key is accepted
**and** a token signed by the retired key is refused — both, in the same
invocation. Only one of those going the right way is consistent with having
broken the key set entirely.

**Done.** — D821–D825, ADR **0170**. **The measurement changed the run before any
code was written, and then changed it again after the tests were green.**

**Two steps, not one.** `bin/dev-token.py` was the last live signer on the key
this run retires (D821), and the deploy mints one on every run to fetch its own
served document — so retiring first would have published `api: unavailable` for
ever, silently, through a broad `except`. The minter moved to the auth service's
key; then the append was guarded.

**The finding is D824, and it arrived after the tests were green.**
`active_secrets` had no upper bound, so the retired key would have been
materialized into every new generation anyway: the file present, the new guard
passing, the set still full. **The run was green in a checkout while being a
no-op in production.** `retired_in_session` is the half that makes it real —
measured at 19 secrets with the key at session 14 and 18 without it at 15, so an
older release keeps the credential its own published set still names.

**What is now true, measured through both modules rather than read off either:**
the published set holds one key; a rotation **can be prepared** (auth + prepared
= 2, which is D683's slot, free for the first time since Session 6); a legacy
generation still publishes its bootstrap key while it is on disk; and a set that
would be empty is refused where the cause is visible.

**Two mutation batteries, eight mutations, all killed with green controls**, and
both batteries restored their files `cmp` clean against the snapshots. `M5` is
the one worth keeping: it undeclares the retirement and reproduces exactly the
state this run was in before D824 was found.

**Not done, and named rather than implied:** `bootstrap_identity` is **still
`not_run`**. All three of `SEC-BOOT-001`'s node ids are live proofs, and Run 8's
deploy is what executes them — the retirement does not take effect until
`CURRENT_SESSION` moves to 15 in Run 7, exactly as Session 14's metrics
credential worked. `SEC-BOOT-001`'s own proof was rewritten here so that it *can*
pass afterwards (D825); it has not been run, and nothing in this run has been run
against a host.

### Run 2 — the session plane's state

Migration **0023**, additive: refresh token families in `app_private`.

The design decision the run must make and record is **what a family is** — a
chain of single-use tokens sharing an ancestor, where presenting a consumed
token invalidates every descendant. Reuse detection is the reason the plane
exists; a refresh token that can be replayed is a long-lived credential wearing
a short-lived name.

Pure logic first, in `src/`, with the state machine testable without a database.
**Nothing about this run touches an endpoint.**

**Measure:** what the database does under concurrent presentation of the same
refresh token. Two requests racing on one row is the case reuse detection exists
for, and it is decided by the isolation level and the lock, not by the Python.
Build the rig with a control that proves it can observe the race at all.

**Done.** — D826–D831, ADR **0171**, migration **0023**. **The state, and the
part of the logic that is neither SQL nor HTTP.**

**Three measurements, each with a control, and the third is the one that
counts.** The first two used a schema typed into a rig; the third rendered
migration 0023 through `render_migration`, applied it to the pinned image, and
re-asked the same questions of the artifact that actually ships — because a rig
that tests its own copy of the subject is testing the copy.

- **The reuse signal is an empty result, and the isolation level decides that**
  (D826). Under `read committed` the loser gets 0 rows, no error, after blocking
  0.61 s; under `repeatable read` the same statement raises `40001`. The control
  — both transactions winning with the guard removed — is what makes "exactly
  one" attributable to the guard rather than to a rig that never had a race.
- **The partial unique index makes the rotation ORDER a catalog constraint**
  (D827): consume-then-insert accepted, insert-then-consume refused `23505`.
- **The shipped migration applies and enforces every claim ADR 0171 makes**,
  including the half-revocation `CHECK` and the cascade from `users`.

**What shipped:** migration 0023 (two tables, one enum, the partial unique index,
no function and no grant), `app.refresh_sessions` (mint, digest, and a five-outcome
state machine with an explicit precedence), and 21 contract assertions.

**D831 is the one to keep.** The plan said the pure logic goes in `src/`, and
`test_no_module_is_imported_only_by_its_own_tests` refused it: *"a module with no
caller is a feature that does not exist."* That is true and unavoidable here, since
Run 2 touches no endpoint. **The guard was right about the package, not merely
about the timing** — the session plane is read by the auth service and nothing
else, so it belongs beside `claims.py` and `tokens.py`. The tempting repair was an
allowlist entry, and it would have left the module in the wrong package for ever.

**Seven mutations, all killed with green controls**, files restored `cmp` clean,
and the released lock re-verified afterwards because the migration was among the
mutated files. `M1` is the sharpest: it checks the family before the replay, which
silences the alarm in exactly the case where somebody is actively replaying a
stolen chain.

**Not done, and named rather than implied:** nothing is renewable yet. There is no
route, no SECURITY DEFINER function and no grant, so `IDN-SESSION-001` and
`IDN-SESSION-002` cannot pass — their live halves are Run 3's work and Run 8's
deploy. **Migration 0023 has not been applied to a cluster this repository
deploys**; it has been applied only to a rig, and the first real application is
Run 8's trip.

### Run 3 — the endpoints

`POST /auth/refresh`, session listing, session termination. The refusal path is
the subject, not the happy path.

**A relayed upstream status is forbidden** (D433). A refused refresh is
translated from the product's own errcode.

**The proof `IDN-SESSION-001` needs is behavioural**: a client crosses the 930 s
boundary without the password. It cannot be a unit test about a table.

**Done.** — D832–D836, migration **0024**. **The plane renews now, and the
refusal path is what was built.**

**What shipped:** five SECURITY DEFINER functions and their grants (0024, 24
released), the repository and service layers, `POST /auth/refresh`,
`GET /auth/sessions`, `DELETE /auth/sessions/{session_id}`, and `/auth/login`
now carrying the session's first refresh token. No new ADR: 0171 already decided
the model, and applying a decision to the surface it was written for is not a new
one (ADR 0021).

**Seven behavioural proofs against a live cluster**, in `test_auth_endpoints.py`
with all 24 migrations applied through the product's own render path — so 0023
and 0024 have now been applied by a server, not only by a rig. The one the plan
asked for is `test_a_client_renews_across_the_token_lifetime_without_the_password`:
holding the refresh token **alone**, a client obtains a working access token and
reaches an authenticated route with it. The boundary is crossed by discarding the
password rather than by sleeping 930 seconds, and the docstring says so.

**The refusal path carries the run.** Unknown, replayed, revoked and malformed
answer 401 with the same bytes and the same challenge — asserted as a set of four
rather than one at a time, because the property is that they are
*indistinguishable*. Nothing relays a status (D433): there is no upstream here,
and the outcome is computed from facts this deployment holds.

**Three findings worth the rows.** **D832**: two concurrent *legitimate*
presentations revoke the family — a client racing itself is logged out, no grace
window, and the reason is that the server cannot tell that race from a thief.
**D833**: the SQL guard and `classify` overlap on three facts and cannot avoid it,
so the overlap is a tested correspondence rather than a second authority — and
`M3` is what proves the test covers it, since a guard silently losing a condition
looks identical from outside. **D834**: the obvious implementation, behind the
same `authenticate` every other route uses, passes every other test in the file
and is useless, because a renewal needing a live access token only works while
nothing needs renewing.

**Six mutations, all killed with green controls**, four of them against a real
cluster; files restored `cmp` clean and the lock re-verified.

**Not done, and named:** `IDN-SESSION-001` and `IDN-SESSION-002` are **not
registered requirements yet** — the registry entries and their claims land with
the `CURRENT_SESSION` bump in Run 7, which is all-or-nothing (D690), so the
proofs exist and report into no claim until then. **Nothing here has run against
the deployment**; the live halves are Run 8's. Password reset does not yet end a
subject's sessions — `auth_revoke_user_sessions` exists and has no caller, which
is Run 5's work and is deliberately not wired here.

**One more, and it is the run's sharpest.** **D837**: `auth_revoke_user_sessions`
shipped granted and callerless -- 0011's rule, broken in the run *after* the one
that turned it into a contract test, in the migration whose own header quotes it.
The guard could not see it because it named 0023. So the rule is now guarded as a
class: `test_every_granted_function_has_a_caller` scans every migration's grants
against every Python and SQL caller.

**And that guard was defective when written.** Verifying it -- by injecting
exactly the grant this run shipped by mistake -- left it **green**, because 0024's
`--` comment explaining the omission mentions the name and the caller haystack
kept comment lines. A comment cannot call anything. **A text scan standing in for
a construct, twice in one run**, both times silenced by prose written to document
the decision being checked. It fires now, and it was verified firing rather than
read.

### Run 4 — agent credential lifecycle, and the D503 decision

Configurable expiry, enforced at verification rather than at issuance — an
expiry checked only when the credential is minted is a policy, not a control.

Then **measure** what `revoked → active` currently restores: the row, or the
credential's ability to authenticate. ADR **0172** follows the measurement
(D817). Migration 0024 only if the decision needs state.

**Done.** — D838–D843, ADR **0172**, migration **0025**. **D503 is closed, and
the measurement is what decided how.**

**The plan required the measurement before the decision, and it earned its
place twice.** The first (D838) turned the question from *"should un-revoking be
allowed"* into *"should a revocation be undoable by flipping a flag"*: measured
end to end, `revoked → active` returns 200 and the **original secret
authenticates again**. Revocation frees no credential.

**The second (D839) stopped a correct-sounding decision from being a harmful
one.** Rotating a revoked agent replaces the secret, moves `authz_version` — and
leaves it revoked with the new secret refused. So refusing the transition *alone*
would have stranded every agent revoked by mistake, and the ADR would have
shipped calling rotation "the documented recovery" while measurement showed it
was not one. Rotation now clears the revocation in the same transaction as the
new secret: one operation, so an agent never becomes active holding the
credential its revocation answered.

**The expiry is enforced at verification** (D842), after the hash comparison and
beside the status check, with the database computing `secret_expired` against its
own clock. Placement is the whole feature: an expiry consulted at issuance
constrains the mint and nothing else.

**D841 is the one worth keeping for its own sake.** The test that had to change
is named `..._terminality_is_UNENFORCED` and ends *"if it was intended, invert
this assertion and close D503; the guard belongs in a migration."* Six sessions
later the replacement took no archaeology — **a test that names the day it will
fail, and what to do then, is the cheapest handover this repository has
produced.**

**The battery is the rest of the run.** Six mutations; **two survived**, and both
survived for the same reason — a docstring claiming a property its body did not
check (D843). `M4` moved the expiry check above the hash and changed no status
and no body; `M5` added a column `DEFAULT`, which no fixture can observe because
they all create agents after the migration. Two construct-level guards closed
them — **and the first guard was blind on its first write**, anchoring on
`min(verify)` when `agent_token` verifies twice, the earlier call being the dummy
hash that exists for this very timing property. Three layers of one defect,
each found by running the mutation rather than reading the guard. All six killed
after the repair.

**Not done, and named:** `IDN-AGENT-001` is not a registered requirement yet —
the registry entries land with the `CURRENT_SESSION` bump in Run 7 (D690).
Nothing here has run against the deployment; migrations 0023–0025 have been
applied by the contract suite's cluster and by no cluster this repository
deploys. `auth_revoke_user_sessions` is still absent and still Run 5's, now with
migration **0026**.

### Run 5 — admin-controlled password reset

An administrator resets a password **without learning it**. `credential_version`
moves, which is the existing revocation mechanism from migration 0011 — this run
uses it rather than inventing a second authority (ADR 0002).

**The proof is the negative one:** every token issued before the reset is
refused afterwards.

**Done.** — D844–D848, ADR **0173**, migration **0026**. **The reset exists, and
the run's finding is that `credential_version` no longer finishes the job.**

**What shipped:** `app_private.password_resets`, three functions (one of them
ungranted), `POST /admin/users/{user_id}/reset-password`,
`POST /auth/reset-password`, and `app.one_time_tokens` — the single-use token
primitive extracted so the reset did not grow a second copy of it.

**D845 is the row that matters.** `credential_version` moves on a password change
and refuses every ACCESS token issued before it — 0012's design, and it was
complete when written. **It became incomplete three runs ago**, when this session
gave the deployment a second kind of credential: a refresh token names a session
rather than a credential, so a chain obtained with the old password would have
kept minting access tokens after the reset. Question 5, arriving on the same
session's own work — the decision did not change, the world gained a case, and
the run that added the case is the run that had to notice.

**D844 is why the phrase needed measuring.** "Without learning it" is a contrast,
and the thing it contrasts with already existed: `PATCH /admin/users/{user_id}`
has accepted a `password` member since Session 6, and an administrator using it
chooses the value. That surface stays — provisioning needs it — and the reset is
the other half. The residual is stated rather than implied: an administrator who
issues a reset could spend it themselves, which is inherent to any
administrator-initiated recovery and not new.

**D846 closes D837, and into a better shape than the one it was removed from.**
Run 3 would have granted `auth_revoke_user_sessions` to the service beside four
others; here it has exactly one caller, inside another function, and **no grant
at all**. The rule that forced its removal produced a smaller privilege surface
than the version that broke it.

**Seven behavioural proofs against a live cluster**, including the negative one
the plan asked for — every token issued before the reset is refused afterwards,
with the same token working beforehand as the control.

**Six mutations, all killed with green controls.** The battery's own pre-flight
refused to run first, because `M5`'s replacement was a tuple: a stray comma after
a closing string. That is the check working — nothing ran until every anchor was
sound. **D848 is `M5`'s subject**: screening the password before spending the
token is a property that lives entirely in the order of two statements and shows
up in no response, the same class as Run 4's expiry-before-hash.

**Not done, and named:** `IDN-RESET-001` is not a registered requirement yet —
Run 7's bump (D690). Nothing here has run against the deployment. **Whether
`PATCH … {"password"}` should also end sessions is open** and recorded in ADR
0173: a direct set moves `credential_version` and leaves the refresh chains
alone, which falls out of that surface predating the session plane rather than
from a decision anybody made.

### Run 6 — the rotation surface

**First act: verify all 19 declared rotation flags against what is true.** Three
have ever been checked (D816). Sixteen are assumptions with a reader about to
arrive.

Then the surface: a command that says what rotating a given class **would** do,
refuses to claim a rotation it did not perform (`one_time_initialization`), and
rotates **one** class end to end with its rollback rehearsed first (D815). ADR
**0171**.

**Expect surviving flags to be wrong.** A survivor is evidence — read it.

**Done.** — D849–D852, ADR **0174**. **The plan said to verify the flags before
reading them, and that ordering is what the run found.**

**What shipped:** `agentic_postgres.rotation`, `bin/rotate-secret.{sh,py}`, and
eleven contract assertions. The surface answers one question per secret — *if you
replaced this value, what would happen* — and **the two refusals are the reason
it exists**: both look exactly like the seventeen that rotate, so a plan printing
their files and services would describe, in detail, a rotation that does not
happen. That is D56, written down five sessions ago and until now enforced by
nothing.

**D849 is the finding, and it is sharper than D816's.** D816 said the flags were
unread. One of them is **unreadable**: `must_refresh_on_start` selects between
failing closed and starting on a cached last-known-good value, and the
materializer has **no cache** — the phrase appears in this repository only inside
`secrets.required.yaml`'s own comments. Six `false` declarations describe
leniency that does not exist. The surface does not report it and says why, and a
test asserts the materializer still has no fallback so the day one is built the
flag becomes real.

**Two of three flags were measured, not assumed** (D851). Replacing
`postgres_init_superuser_password` over the same data directory: replacement
refused, original still works — and the control is what makes that evidence
rather than a broken container. A role password rotated end to end with the
rollback **rehearsed first**. The rig carried two of my own bugs before it
carried a result, and the second — the data volume at the wrong path — would have
compared two unrelated clusters and produced a clean-looking refutation of a true
flag.

**D850: one flag, two phenomena.** The first draft printed the `initdb` sentence
for the cipher pass and it read perfectly — an operator would have learned a
wrong mechanism from a correct refusal.

**Seven mutations, six killed, and the survivor was worth more than a kill**
(D852). `M1` disabled the `one_time_initialization` branch and the surface still
refused, because every secret declaring it also declares
`rotate_by_replacement: false`. Uninformative as a mutation, and it exposed that
**nothing required the two to agree** — a contradictory declaration would have
produced a plan reporting a rotation the secret's own entry denies. That guard
now exists and was verified firing.

**Not done, and named rather than implied:** **one class is proved end to end and
sixteen are not** (D815). A database role password was rotated in a rig; the
others rotate by the same mechanism and have not each been performed. Nothing
here touched the provider, and no verb in this command can. `IDN-ROT-001` is not
a registered requirement yet — Run 7's bump (D690) — and **D816 is not closed**:
two of three flags are verified and driven, the third awaits its mechanism.

### Run 7 — the bump

`CURRENT_SESSION` → **15**, `template_version` → **0.4.0**. All-or-nothing
(D690): every §2 requirement activates with its proofs in the same commit.

Outputs schema moves to **v15 only if something needs publishing.** Session 14's
v14 existed because a route had to reach `outputs.json`; if nothing here does,
the schema does not move, and the plan says so now so that a bump does not
happen out of habit.

**Done.** — D853–D856. **One commit, which is what all-or-nothing means** (D690).

`CURRENT_SESSION` **15**, `VERSION` **0.4.0**, five `IDN-*` requirements
activated with their proofs, four claims and their session map, `IDN` registered
as a requirement family, `bin/session-15-check.sh` derived by diff and
registered, the documented path moved, and the acceptance matrix regenerated.

**The outputs schema stays at v14** (D855). Every endpoint this session added
sits under the `routes.app` prefix the document already carries, and the plan
pre-committed the test — *v15 only if something needs publishing* — before the
run could rationalise one. Deciding it at planning time is the point: with the
diff in front of you, v15 looks tidier.

**D856 is what the bump forced.** Every proof Runs 2–6 wrote is offline,
including the ones that stand up a real cluster — and `claim_mode` refuses a
claim whose every node id is offline. So four claims would have been unprovable
at the moment they were registered. `tests/deployment/test_session15_identity.py`
is the answer: eight live proofs, at least one per claim, each reaching the
identity plane through the published route. **The proofs existed for four runs
and nothing required them to reach a front door until a claim had to name them.**

**D854 is the one I would keep.** My first draft of those live proofs built its
own fixtures — read `APG_ADMIN_PASSWORD_FILE`, re-derived the administrator's
username, composed URLs from the domain, and used **`.strip()`** on the password
file where `conftest` deliberately uses `.removesuffix("\n")` because *a
password may legitimately end in a space*. That draft would have authenticated as
something the operator did not type and reported it as a broken deployment.
Question 6 in a fixture I was writing rather than one I inherited: my belief, my
code under test, and only the suite's existing answer disagreeing.

**D853: the gate header chain.** `bin/session-14-check.sh` opens with *"The
Session 13 gate"* and claims descent from Session 12's — Session 13's header
copied whole, eleven lines above the paragraph recording that nothing diffs the
prose a gate carries. Session 15's is rewritten and **Session 14's is corrected
in place**, because fixing only the new one is exactly what Session 14 did.

**Three guards fired and each was right**: the requirement-prefix registry
refused `IDN` until it was declared, D693's documented-path check named seven
stale `--session 14` flags, and the README's own session statement. None was
worked around.

**Not done, and named:** **nothing here has run against the deployment.** All
eight live proofs skip in a checkout, correctly — `--setup-plan` resolves their
whole fixture graph and every fixture is wired (D671), which answers *will this
run* and not *is what it asserts true*. The five claims are `not_run` until Run
8's trip. **The gate has not been run in any mode**; it is Run 8's first act.

### Run 8 — the host trip

Gate in every mode the evidence needs, **once**, before the trip. `--setup-plan`
first (D671, D676) — the proofs run against a key set that changed in Run 1.

**Verify the four verifiers were recreated, per verifier** (D819), and that each
accepts a token signed by the surviving key. Not the deploy's exit code.

---

## 7. Evidence and claims

What each claim may honestly report **before its live half exists**, fixed now
so no proof gets shaped to a verdict (D820).

| Claim | Offline may report | Needs a live half for |
|---|---|---|
| `bootstrap_identity` | Nothing — it is `not_run` until Run 1's deploy | The published set, on the host, with the retired key refused |
| `session_lifecycle` | The family state machine and the refusal logic | The TTL-boundary crossing and the concurrent-reuse race |
| `agent_credential_lifecycle` | Expiry enforcement, the transition's decided behaviour | Verification against the deployed verifiers |
| `password_reset` | `credential_version` moves; pre-reset tokens are refused | The refusal at a live verifier |
| `credential_rotation_surface` | All 19 flags match their credential; the refusal to over-claim | The one rotation, and its rollback |

**No claim spans both `host` and `external` mode.** **A skip is not a pass**, and
an offline half may not stand in for a live one.

**The eight inherited `not_run` claims stay `not_run`** — except
`bootstrap_identity`, which Run 1 closes. Session 15 does not close the other
seven and **must not appear to** (D478). Four are flag-gated and three are
declarations nobody has performed.

---

## 8. Security invariants this session touches

| Invariant | Control | Proof |
|---|---|---|
| A refresh token is single-use | Family invalidation on reuse | `IDN-SESSION-001`, live, under concurrency |
| Retiring a key refuses only that key's tokens | Guarded omission, both directions asserted | Run 1's paired control |
| An administrator never learns a reset password | Reset writes a hash the admin path never sees | `IDN-RESET-001` |
| Revocation is not undone by accident | ADR 0172's decided transition | `IDN-AGENT-001` |
| A rotation is never reported unperformed | `one_time_initialization` refusal | `IDN-ROT-001` |
| No secret value reaches logs, argv, images or source | Standing (§6 of CLAUDE.md) | The sentinel scan, unchanged |

**`refresh_token` is already in `SENSITIVE_KEY_DENYLIST`** (D812). Run 2 is the
first time that entry protects a value that exists — and the redaction proof
must be re-run against a real one, because a denylist entry verified only
against an empty set is verified against nothing.

---

## 9. Stop conditions

Stop and ask when:

- **Run 1's measurement shows a live token carrying the bootstrap `kid`.** The
  omission is safe because nothing depends on that key; if something does, the
  order changes and the ADR changes with it.
- **Retiring the bootstrap key does not free the slot.** D814 predicts it does.
  If `build_jwks` still refuses a third key afterwards, the characterisation in
  `scope-closure.md` is wrong and Run 1 is not what this plan says it is.
- **Reuse detection would need a second identifier** for something
  `authz_version` or `credential_version` already answers. That is ADR 0002's
  second authority, and this repository has paid for it twice in one session
  (D680, D682).
- **A rotation flag turns out wrong on a credential a service is currently
  using.** A wrong flag is a finding, not a blocker — but acting on it against a
  live credential is not a run-level decision.
- **The session plane would require storing anything the denylist forbids in a
  place it can be read.** The plane exists to stop the password being retained;
  a plane that retains something equivalent has moved the problem.
- **More than one credential class would rotate in Run 6.** D815 scoped it to
  one deliberately.

---

## Appendix — what to consult

`docs/plans/stage-2-plan.md` §1 and §3. `docs/scope-closure.md` §2 for
`bootstrap_identity`'s characterisation — **and check its premise still holds
before acting on it** (§9 of CLAUDE.md: three of that list's oldest entries were
mischaracterised rather than undone). ADR 0088 and 0155 for the verifier
recreation, 0002 for single authority, 0163 for what `not_run` means.

**Grep the plans for anything this session touches.** Nothing indexes the ~811
measured facts by subject.
