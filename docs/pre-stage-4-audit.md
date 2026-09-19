# Pre-Stage-4 audit: everything this project knows is wrong with itself

> **A record, dated 2026-09-16, at `template_version` 1.6.2.** It does not track
> the current release and is not held to it by a test. It exists so that Session
> 28 can be planned against one list instead of six.

> ## ⚠ Read this before working any row below
>
> **Session 28's Run 1 measured all 36 Tier 1 rows against the tree, in both
> directions, on 2026-09-16 at `9bd5ed8`. Fourteen of them are already answered
> in the tree, and three of those fourteen would have caused harm implemented as
> this page writes them.** The measurements, each with the command that shows it,
> are in **`docs/scope-closure.md` §16**, and every one carries a divergence
> number in `docs/plans/session-28-implementation-plan.md` §1 (D1406–D1433).
>
> The three to know before touching anything:
>
> * **F-013** — *"the lint forbids `{{app_runtime}}`, which the release's own
>   `0003` uses — roughly one line."* Migration `0006` revokes schema `app` from
>   `app_runtime` three migrations later, and its own header measures the result:
>   the grant in `0003` reaches nothing. **The lint is correct.** The one line
>   would widen a security boundary to match a dead grant.
> * **D1274** — *"ask the deployment."* `studio.py:464` already decided this
>   under ADR 0195, because no request Studio makes confirms the lock.
> * **D1045** — *"report the body."* The body is withheld on purpose and the code
>   says so at the discard: on identity endpoints it can echo the request, and
>   the message reaches a log. **Reporting it puts a provider's response into a
>   log on a credential path.**
>
> Run 1 also found seven things this page does not say — among them that
> `render-jwks`'s closing act would remove a deliberate property, that the D1276
> row is two findings under one number, and that *47 failures and 49 errors* is a
> reading of somebody else's fork rather than of this tree. Those are D1427–D1433.
>
> **This page is still the right inventory**, and the tier a row sits in is
> sound. What it is not is a work list: the *closing act* column was written from
> the documents rather than from the code, and that is exactly the difference §16
> records.
>
> ### Closed since this page was written
>
> Runs 2 and 3 of Session 28 closed the on-ramp rows. **F-008, F-012, F-013,
> F-020 and F-022 are answered**, by ADR 0210, ADR 0211 and ADR 0212 and the
> code in Run 3; the procedure is **`docs/on-ramp.md`**, which did not exist
> when this page was written. **D1418** (the interpreter on the host) is
> answered *no* with its reason at `bin/doctor.sh`'s own split (D1441) — no
> check was added. Do not work those rows from this page; work them from
> `docs/scope-closure.md` §15, which now marks them closed and says by what.

**Why this page exists.** The operator asked for a single inventory of what is
broken, what works but not as it should, and what is claimed but unproven,
before Stage 4 is planned. Everything here is drawn from documents already in
this repository — `evidence/session-25.json`, `docs/scope-closure.md` §11–§15,
`CLAUDE.md` §9, the session plans' §10, and an adopter's `stage-3-findings.md` —
and nothing is invented. Where a row says *measured*, a command produced it.

**Read the tiers, not just the rows.** They are not a priority order; they are a
statement of *what kind of act closes the row*. That distinction is the whole
value of this page:

| Tier | Closable by | Count |
|---|---|---|
| **1** | Code or documentation, in a session, offline | **36** |
| **2** | A host trip — a deployment must be touched | **12** |
| **3** | A person or a decision. **No amount of engineering closes these** | **8** |

*Counted by walking the tables below, not asserted. The first draft of this page
said 31 for Tier 1 and was wrong by four — written by the same hand that wrote
this page's own instruction to measure rather than recall, which is worth
leaving on the page rather than editing out.*

> **Operator decision, 2026-09-16: the signing-key rotation WILL be performed.**
> It has been offered and declined at four trips (D860). That decision is now
> reversed, which moves it out of Tier 3 and makes it an act Session 28 plans
> rather than a question Session 28 asks. Three `not_run` claims —
> `bootstrap_identity`, `api_authorization`, `credential_rotation_planes` —
> depend on it and on nothing else.
>
> **It is the single highest-value act available to this project**, and also the
> only irreversible one on this page: `promote` cannot be undone, the slot is
> free (ADR 0170), and it has never been exercised on a deployment. It gets its
> own rehearsal and its own run. It is **not** an appendix to a release day.

**The honest headline: Tier 3 cannot be finished by Session 28.** Four of the
seven unproven claims need a credential rotation performed on production, which
has been offered and declined at four trips; one is `not_run` *by decision*; one
needs a human being to walk the documentation. A session can make every one of
them *ready*, and only an operator at a keyboard can close them. Planning Session
28 as "everything perfect" will fail on Tier 3 and succeed on Tiers 1–2, so it
is worth deciding now which of Tier 3 you intend to do.

---

## Tier 0 — the seven claims that are not `passed`

This is the project's own evidence, `evidence/session-25.json`: **126 claims,
119 passed, 1 failed, 6 `not_run`.**

| Claim | Status | Why, and what closes it |
|---|---|---|
| `documented_path` | **failed** | The only `failed` claim this project has ever written. Two readers holding nothing but a clone and a task statement recorded **six and then eleven** undocumented steps (ADR 0207). Closing it means repairing what they found and having a *third* reader confirm. **Tier 3** — it needs a reader who has not seen the repository |
| `bootstrap_identity` | not_run | **The rotation was PERFORMED 2026-09-19** (Session 30 Run 8) and this claim did not move. It lists nine node ids; the cutover takes **one** (D1469), and that one has not been taken either — no sweep has yet read the retired JWK with `--rotated-jwt-from-file`. **The audit's pricing of this row was wrong** |
| `api_authorization` | not_run | Same rotation, same answer: performed 2026-09-19, claim unmoved |
| `credential_rotation_planes` | not_run | **PERFORMED 2026-09-19**, on both projects, after being declined at five trips (D860 closed as an act). It stays `not_run`: this claim needs **four** rotations and the signing-key cutover is one of them. The other three — the authenticator password, the documentation Basic Auth password, the application credential on both projects — have still never been performed |
| `deployment_convergence` | ~~not_run~~ **passed** | **CLOSED 2026-09-19**, `not_run` since Session 11. `--redeploy-before-file` was declared on a trip for the first time and one deploy answered both halves: the sentinel row survived and the secret generation moved |
| `port_allocation` | not_run | **Passed 2026-09-17** on Session 29's reboot, and `not_run` again at Session 30 **by choice** (D1568): `--after-reboot` is a declaration that a reboot happened, that trip performed none, and a claim is not kept green by a declaration that is no longer true |
| `replacement_host_restore` | not_run | **`not_run` BY DECISION** (D1028): a rehearsal ends at the restore. Closing it means reversing that decision and building a replacement host. **Tier 3** |

---

## Tier 1 — closable offline, by code or documentation

### 1a. The adopter is blocked right now

| ID | What is wrong | Closing it |
|---|---|---|
| **F-012** | `freeze-lock` refuses a project set authored against an earlier release. `freeze_project_lock` computes the floor from **this checkout's** newest release version and there is no flag to record the release the set was really frozen against. 1.6.2 repaired the *message*; the refusal stands | A way to declare or derive the real `follows_release_version` — a flag, or reading the installed document. **One ADR, one run** |
| **F-013** | The project-set lint forbids `{{app_runtime}}`, which the release's **own migration `0003`** uses. An adopter who copies the platform's example domain writes a set the release will not lint | An ADR (it is a security boundary), then roughly one line |
| **F-008 / F-009** | How a fork made **before** `projects/<slug>/` existed converts to it is undecided, and no rule exists for which side wins each merge conflict. ADR 0198/0206 describe the end state, not the move | A decision, then a documented procedure. **This is the on-ramp question** and it is the first row of `docs/scope-closure.md` §15 |
| **F-020** | A host checkout one commit behind the workstation is invisible: `upgrade check` compares versions and digests, never commits, and both sides read `1.0.0` | Report the commit. Small |
| **F-022** | A fork whose domain is in the release's files **can deploy and cannot pass the gate**, and no page says what an adopter does about that | One paragraph, once F-012/F-013 are decided |
| **F-018 / F-026** | `provision-host.sh` installs neither `uv` nor `.venv` (`grep -ci "uv\|astral\|pip install"` → **0**), so a host provisioned by this product runs every `bin/*.sh` under the distribution's Python — **3.14 on the adopter's host, against a pinned 3.12** — and `bin/doctor.sh` checks the interpreter on a workstation only | A decision about what `--apply` does to a machine, then the interpreter check on the host |

### 1b. Stated, not handled

| ID | What is wrong | Closing it |
|---|---|---|
| **D1255** | `agent_audit` and `agent_idempotency` **grow without bound**. Nothing prunes either | A released migration carrying a retention policy |
| **D1248** | `GET /admin/audit` filters by agent, owner and limit only — no window, no outcome/boundary filter, no cursor | One migration + one endpoint change; priced, not built |
| **D1275** | A `project_admin` cannot use the schema or query views. That *is* the deployment's authorization, and Studio's own surface disagrees with it | A decision, then a grant or a narrowed surface |
| **D1274** | Studio's capability view shows **the checkout's lock, never the plane's**. D1201 established the running process is the authority | Ask the deployment, as `list_resources` already does |
| **D1374** | `render-jwks` prints *"the key set CHANGED"* from a test of the **file's bytes** — measured on both projects, the kid and the key-set digest are identical before and after. **It reports a rotation that did not happen** | Compare the key set, not the file |
| **D1045** | `ControlPlane._call` discards a provider body that said *identity limit reached* — a security judgement thrown away in a credential path | Report the body, or say why not |
| **D1203** | `app-openapi.canonical.json`'s canonical form is `bin/app-contract.py`'s, not `openapi_normalize`'s. **Two serializers that agree only while the document is ASCII** | One canonicalizer |
| **D942** | ADR 0175's arity guard has two blind spots: an HTTP body naming an RPC's parameters, and a `GRANT … ON FUNCTION` signature | Widen the guard |
| **D930** | Two different fields are both named `capabilities_sha256` — the lock digests the release's example file, the rendered document the host's | Rename one |
| **D1205** | No Python client, and the TypeScript client is a **Node** client (`canonical.ts` uses `node:crypto`) | A second emitter, or a stated decision not to |
| **D380** | `apg-diag`'s log allowlist covers neither `auth`, `storage` nor `mcp` | Widen the allowlist |
| — | Session 9's live proofs check `"error"` and not `isError`, so they **pass on a refused write**. Session 16's `refused()` helper reads both | Move the old proofs onto the helper |
| — | `mcp_tracing.configure()` **has no caller**. No span leaves the process; the collector is on `edge` only | A caller, or delete it |
| — | The completion script is bash's. zsh and fish users have `--list` and `--help` | One `case` arm, or a stated decision |
| — | `requirements-dev.in` **pins nothing** | `bin/lock-dev-deps.sh --update`, committed separately |
| — | The apt pin `pgbackrest=2.59.1-1.pgdg12+1` expires; `lock-versions.sh --update` re-adopts rolling tags; `PYTHON_RUNTIME_IMAGE` is a rolling minor (D533, D540, D762, D99) | A pinning policy |
| — | `MCP_MEMORY_LIMIT` is measured for the interpreter only; `MAX_SERIALIZED_BYTES` was **chosen, not measured** | Measure both |
| — | `tests/deployment/conftest.py` is ~2,100 lines | Split it |
| — | Secret generations accumulate with nothing pruning them | A retention rule |

### 1c. Proofs that do not prove what they look like they prove

**This is the category this project's own §7 says it keeps producing, and it is
the one most worth spending Session 28 on.**

| ID | What is wrong | Closing it |
|---|---|---|
| **D1240** | **Four modules collect 0 under every marker-selected sweep**: `test_database_function_signatures`, `test_storage_client`, `test_storage_endpoint`, `test_storage_endpoints`. They have never run in any gate | Give them markers, or say why not |
| — | `test_honest_readers`' `sudo -u` re-entry branch **has still never run** | Run it, in the identity the gate has |
| **D464** | `dx_record.documented_commands` is a **text scan**, so a command in a block the regex misses is invisible — which makes a walker's honest use of it look undocumented | A parser, or a stated limit with a test |
| — | Both documentation scans match a command line **by its first word**, so a flag on a `\`-continuation line is unchecked. Inherited from Session 26's self-check into Session 27's guards | Read continuations |
| **D1282** | **A trap, not a defect**: the gate's `--kit-dir` must stay on `kit-2026-09-11`, because `REC-KIT-003`'s claim *is* the version gap and its proof `pytest.fail`s on exactly that. Pointing it at the newest kit destroys the proof **without failing** | Make the proof state its own premise so the trap cannot be sprung silently |
| **D1276** | Studio has **no live half** for the query view's RLS off this workstation, and a rig that reaches a published loopback port assumes a daemon | A live half that runs where the gate runs |
| — | The uncached first run of `apg dev up` — the run a new developer actually has — is measured **in CI and nowhere else** | Measure it where it is claimed |
| **D297 / D201** | The environment is not verified against the lock; a lock verifies only what it dereferences | Verify both |
| **D1424 — CLOSED 2026-09-17, ADR 0214; and the count below is wrong, see D1463** | **A release's documentation landing one commit past its own tag. It has now happened three times, twice of them on one day.** D1033 at `1.0.0`, repaired by cutting `1.0.1`. D1388 at `1.6.0`, where `docs/upgrade-guide.md` and `docs/operator-guide.md` both landed in the next commit — and ADR 0209 was written for exactly that. Then **on 2026-09-16, in the release that shipped ADR 0209, it happened twice more**: two repairs and a reply page landed past `1.6.1`'s tag, which cost a `1.6.2`; and commits continued after `1.6.1` was cut before anyone asked whether they belonged inside it. **ADR 0209's guard caught none of them, correctly** — a test runs inside a commit and cannot see a tag cut after CI is green, and the ADR says so in as many words. So the guard is right about what it can assert and **the habit around it is what fails**: nothing asks *is this commit the one the tag goes on* before the tag is cut, or *does this commit belong in the release* after | A pre-tag reading the operator runs, not a test: something that lists what is about to be tagged and what has landed since the last tag, so the question is asked out loud. Possibly a `bin/` verb. **Decide whether it is a command or a checklist** — D1033's row says a checklist already existed in prose and the session that wrote it did not follow it |
| **D387** | The REST observation does not retry | Retry, or state why not |
| **D340** | Every service role reaches the `postgres` catalog | A decision |

---

## Tier 2 — needs a host trip

| ID | What is wrong |
|---|---|
| ~~**D860**~~ | **PERFORMED 2026-09-19 — on both projects, by Session 30 Run 8, and it closes no claim.** Read the row below as the pricing it was, not as a forecast: it says the rotation *unblocks* three claims, and D1469 measured that those three need four rotations between them while this one moves one node id of nine. What it did buy is an act that had been declined at five trips, two windows (~49 minutes and ~25), and three findings that only performing it could produce — D1579, D1580 and D1581, in `docs/scope-closure.md` §23. **The original text follows.** **The signing-key rotation, and it is now DECIDED rather than offered.** Built, tested offline, declined at four trips, and the operator has reversed that on 2026-09-16: Session 28 performs it. It unblocks `bootstrap_identity`, `api_authorization` and `credential_rotation_planes`, and it is the first item on Stage 4's own bill. **Plan it with its own rehearsal**: `promote` is irreversible, each project publishes exactly one verification key (ADR 0170), and a key cutover recreates all four verifiers (ADR 0155). The one credential path in this product that has been built, tested and never run |
| **D1375** | `op` on the host **cannot reach the Docker socket**, and Session 25 is the first release whose offline gate mode needs one. The group membership was deliberately not granted (root-equivalent on production) |
| ~~**D1401**~~ | **CLOSED 2026-09-18 by Session 29.** Both projects deployed at `8c61309`, swept, then tagged **1.7.0** on that commit. `stage_release` passed. Structurally closed: the tag now waits for the deploy (D1425) |
| ~~—~~ | **INVESTIGATED 2026-09-18 (D1503).** `cloud-init-hotplugd.service`, socket-activated, fails **at every boot** 2 min 42 s after `btime` on a NIC hotplug event (`hotplug_hook.py:110`). The provider's cloud-init, not this product; both projects doctor clean with it failed. **D1512:** two `backup-mirror` units joined it on 2026-09-18 |
| ~~—~~ | **BOTH DONE 2026-09-17 (D1500).** `7.0.0-29` → `7.0.0-31`, skipping 30, plus `libc6`; 40 days of uptime ended in 8 s of downtime; both projects came back by themselves; `--after-reboot` declared and **`port_allocation` passed for the first time in twelve sessions** |
| — | ~~The signing-key cutover~~ **timed 2026-09-19**: every command under a second, the recreate 3–5 s, the deploys dominating; a window that goes as written costs **~25 minutes** end to end. ADR 0122's rotation repairs and the agent plane's round trip on a host **have still never been timed** |
| — | The database container **can reach the internet** (ADR 0147's residual) |
| **D688** | The IPv6 scan has nothing to scan |
| **D771** | The host's OOM history is unknown |
| **D976** | Infisical reads hang intermittently; the client retries idempotent calls three times |
| — | The Infisical control-plane identity **holds org admin** |
| ~~**D1189**~~ | **ALREADY CLOSED, and this audit did not know it** (D1489). Beta's ledger prints `[X] 20260914120002_agent_grants.sql`, `Applied: 2, Pending: 0`. True when Session 22 wrote it; closed by ADR 0206's ledger move at Session 24's trip; unread for five sessions. Confirmed against the LEDGER, not the document (D941) |

---

## Tier 3 — a person, or a decision. Engineering does not close these.

| ID | What is open | Why no session closes it |
|---|---|---|
| — | **A person's walk of the documented path** (ADR 0207's residual) | Two *models* have walked it. A person has not. `docs/second-walk.md` carries the task statement between fixed markers precisely so a person can be handed the same words |
| — | **The operator guide has never been read cold** | The upgrade guide has, and it produced 34 findings. Only a reader who did not write it can do this |
| **D1303** | **Studio has never been opened in a browser** against this deployment by a person | The sweep has driven it; a person has not |
| **D1028** | `replacement_host_restore` is `not_run` **by decision** | Reversing the decision means building a replacement host |
| ~~**D1084**~~ | **DECIDED 2026-09-18, ADR 0216**: no public Postgres endpoint in Stage 4. `publication()` stays a refusal by decision rather than by omission, and the five preconditions a Stage 5 reading would have to pay are written down | Closed as a decision, which is the only way this row could close |
| — | **DECIDED 2026-09-18, ADR 0217**: appliance first, hosting deferred, and the boundary stated as a rule — nothing built in Sessions 31–35 may require a hosted trust model to be safe | Closed as a decision. The hosted platform is a Stage 5 reading with preconditions, not a Stage 4 build |
| — | **The 21 unclaimed requirements** | Reportable one DECLARATION at a time under ADR 0202; each is a decision |
| **D1311** | `1.3.0`–`1.5.0` have no tag, **by decision** | Tagging them retroactively would be a record that looks measured and was not |

---

## What "perfect before Stage 4" can actually mean

Three readings of the operator's goal, priced:

1. **Every Tier 1 row closed.** Achievable in one long session or two. It is the
   largest single improvement available and it needs no host and no person.
2. **Tier 1 + Tier 2. THIS IS THE ONE THE OPERATOR CHOSE, 2026-09-16.**
   **DONE 2026-09-18: Tier 1 by Session 28, Tier 2 by Session 29's trip.**
   *The pricing below was wrong in one place and the correction is worth more
   than the row:* it says the trip adds **the rotation performed** and that this
   **closes four of the seven unproven claims**. D1469 measured otherwise — the
   three rotation claims need **four** rotations between them and the signing-key
   cutover moves **one of nine** node ids, closing **none** on its own. **The
   rotation was therefore not performed on that trip** (D1496), which still
   moved the deployment to the tree, closed D1401 structurally and brought
   `agent_record_retention` and `port_allocation` to `passed`. **It was
   performed on 2026-09-19 by Session 30, on its own day and its own sheets,
   and it closed none of the three claims — exactly as D1469 said it would
   not.** What remains unproven afterwards is three claims, each
   for a reason that names an event: `documented_path` until a third reader
   walks it, `replacement_host_restore` by a standing decision, and
   `studio_tenant_read` until a fixture is repaired. `deployment_convergence`
   **passed** on 2026-09-19 and `port_allocation` is `not_run` again by the
   trip's own choice.
3. **Tier 1 + 2 + 3.** Requires a person to walk the documentation, a person to
   open Studio, and two open product questions to be *decided* rather than
   built. The decisions are Stage 4's subject, so this reading asks Session 28
   to do Stage 4's job first. **Both decisions were taken on 2026-09-18** —
   ADR 0216 and ADR 0217 — by the stage plan rather than by Session 28, which
   is where this reading said they belonged. The two rows that remain are the
   two that need a **person**.

**The one row that should be read twice**: `documented_path` is the only `failed`
claim this project has ever written, and it is failing *because* somebody finally
looked. A session that repairs what the readers found and then declares victory
without a third reader has not closed it — it has gone back to the state where
the status had never been emitted at all, which is what the previous twelve
sessions did.
