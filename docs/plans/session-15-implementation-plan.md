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
SESSION 15 IS IN PROGRESS. **RUN 1 IS DONE. RUN 2 IS NEXT.**
HEAD 3b85b5f, main, clean and pushed.
CURRENT_SESSION **14**, template_version **0.3.0**, outputs schema **v14**.
                 It moves to 15 in Run 7, ALL-OR-NOTHING (D690).
divergences     **Next free: D826.** D812-D820 planning-time, D821-D825 Run 1.
ADRs            170. **Next free: 0171.** Run 1 wrote 0170.
migrations      22 released. **Session 15 adds 0023** (Run 2) and possibly
                0024 (Run 4). Fix-forward only; every down block raises AP900.
claims          82, reporting 107 of 131 requirements.
                **8 not_run**, carried from Sessions 13 and 14 unchanged.
                Run 1 is the only one of the eight this session can close by
                writing code.
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

**Next free number after this table is D826.**

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

### Run 3 — the endpoints

`POST /auth/refresh`, session listing, session termination. The refusal path is
the subject, not the happy path.

**A relayed upstream status is forbidden** (D433). A refused refresh is
translated from the product's own errcode.

**The proof `IDN-SESSION-001` needs is behavioural**: a client crosses the 930 s
boundary without the password. It cannot be a unit test about a table.

### Run 4 — agent credential lifecycle, and the D503 decision

Configurable expiry, enforced at verification rather than at issuance — an
expiry checked only when the credential is minted is a policy, not a control.

Then **measure** what `revoked → active` currently restores: the row, or the
credential's ability to authenticate. ADR **0172** follows the measurement
(D817). Migration 0024 only if the decision needs state.

### Run 5 — admin-controlled password reset

An administrator resets a password **without learning it**. `credential_version`
moves, which is the existing revocation mechanism from migration 0011 — this run
uses it rather than inventing a second authority (ADR 0002).

**The proof is the negative one:** every token issued before the reset is
refused afterwards.

### Run 6 — the rotation surface

**First act: verify all 19 declared rotation flags against what is true.** Three
have ever been checked (D816). Sixteen are assumptions with a reader about to
arrive.

Then the surface: a command that says what rotating a given class **would** do,
refuses to claim a rotation it did not perform (`one_time_initialization`), and
rotates **one** class end to end with its rollback rehearsed first (D815). ADR
**0171**.

**Expect surviving flags to be wrong.** A survivor is evidence — read it.

### Run 7 — the bump

`CURRENT_SESSION` → **15**, `template_version` → **0.4.0**. All-or-nothing
(D690): every §2 requirement activates with its proofs in the same commit.

Outputs schema moves to **v15 only if something needs publishing.** Session 14's
v14 existed because a route had to reach `outputs.json`; if nothing here does,
the schema does not move, and the plan says so now so that a bump does not
happen out of habit.

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
