# Scope closure

The twelve-session plan's final activity, and its wording is the standard this
page is held to: *resolve all P0 failures, explicitly list remaining P1/P2 gaps,
remove hidden dependencies, and decide whether the artifact is ready as a
reusable template.*

**Every number here is measured, not recalled.** Where something is unproved it
says so, and where the reason is a decision rather than an omission it says which
decision.

---

## 1. The position, in numbers

| | Count | Note |
|---|---|---|
| Requirements in the acceptance registry | **202** | 194 P0, 8 P1, **0 P2** — nine added in Session 23: eight `GEN-*` and one `AGT-*` |
| Claims in the evidence model | **118** | four added in Session 23 — **two declared offline and two deliberately not**, which is the line ADR 0202 exists to let a session draw |
| Requirements a claim reports on | **178** | 24 belong to no claim (D697), unchanged in number; see §4 |
| Migrations released | **31** | fix-forward only. Session 23 adds none, released or project — it ships no SQL at all |
| Architecture decisions recorded | **204** | 0200–0201 are Session 21's, 0202–0203 Session 22's, **0204 Session 23's** |
| Divergences measured | **D1–D1242** | D1124–D1155 are Session 21's, D1157–D1199 Session 22's, **D1200–D1242 Session 23's** — the last four written after the code was finished: three by Run 6's own red CI and **D1242 by the close's gate** |

---

## 2. P0 — one needs a rotation performed, three await a witness

**`bootstrap_identity` is `not_run`, and what it needs is a ROTATION PERFORMED,
not code** (D860). **The blocker was removed in Session 15 and the claim did not
move**, which is the distinction this entry got wrong for four sessions.

D683 was real and is now closed: `render-jwks.py` appended the bootstrap
issuer's key unconditionally, `MAX_VERIFICATION_KEYS` is 2, and the set had been
full since the auth service existed in Session 6, so **no rotation could be
prepared at all**. Session 15 Run 1 retired the key (ADR 0170), and the
deployment was measured afterwards: each project publishes **exactly one
verification key**, read from off-host and from the one inode its three
non-issuing verifiers share, with all four verifiers recreated. **The slot is
free.**

The claim is still unproved because it is `SEC-BOOT-001`, and **two of that
requirement's three node ids are rotation proofs**:
`test_a_rotated_signing_key_is_the_only_one_the_plane_accepts` and
`test_a_rotated_authenticator_serves_the_plane_and_the_old_password_does_not`,
gated on `APG_ROTATED_JWT_FROM_FILE` and `APG_ROTATED_AUTHENTICATOR_FROM_FILE`.
Nobody has ever rotated a signing key on this deployment. **That was true before
D683 and it is true after it** — the two were inseparable, so the ledger read
one as the other.

* **Effort to close:** an operator sequence, not a run. A new key placed at
  `APG_AUTH_JWT_PREPARED_KEY` at the provider, a redeploy, then
  `bin/rotate-signing-key.sh` `acknowledge` → `promote` → `retire` — `promote`
  is **irreversible** and needs a human at a TTY — plus an authenticator
  rotation for the second proof. Possible for the first time in nine sessions.
* **Risk of not closing it:** unchanged in substance and better understood. The
  signing key *can* now be rotated; what is unproved is that rotating it works
  on this deployment. Nothing is compromised; the *rehearsal* of the response is
  what is missing.
* **What this entry teaches:** **a blocker removed is not a proof obtained.**
  Session 15 planned a whole run against the belief that closing D683 closed the
  claim, and read the effort as *"one run"*. It was one run — and the claim was
  never what that run was measuring.

**`DEP-001` and `DX-001` await a declaration, not code.** Both offline halves are
proved. Neither may report `passed` on that alone — an offline half proves the
documented path *resolves*, never that anybody walked it. Closing them needs a
host that starts empty and a developer who did not build this.

**`DEP-ISO-001` is claimed (`isolation_matrix`) and has passed on every host
gate since Session 12's trip.** This entry said for four sessions that it
awaited a host trip, and the README said it was unclaimed (D954) — the D860
shape in the other direction, finished work described as unfinished, which is
the direction nobody chases.

**`DEP-REMOVE-001` PASSED on 2026-09-05** (D1086). Its proof reads
`APG_REMOVED_PROJECT_FILE`, a record of the removed project's key and resource
names captured *before* the removal, and asserts the survivor serves and holds
its rows while nothing named for the removed key still runs. Closing it needed a
third project created for the purpose and retired, which Session 17 did:
`gamma-dev` was created 2026-09-04, retired 2026-09-05 with `--record`, and
`project_removal` passed for the first time since Session 12.

This paragraph said *"awaits a project actually removed"* for five days after it
did not. **That is D954's shape, three lines below a paragraph describing D954's
shape** -- finished work recorded as unfinished, which is the direction nobody
chases because nothing fails. Corrected in Session 20 Run 5.

What the removal surface does is still narrower than this ledger's warnings once
implied, and that half was and remains true: `bootstrap-providers.sh --destroy`
revokes the runtime identity and unlinks the credential files, and **every
Infisical secret, the repository cipher pass included, stays in place** (D957).
Gamma's own leftovers are the operator's console decision and are recorded in
the launch folder's §9.

**Session 18's trip (2026-09-06) passed three of its four claims on their first
live execution**: `independent_repository` (both projects mirrored to the
second provider, the restore from the mirror alone verified on a replacement
in 247 s), `disaster_kit` (the kit from production verified and holding no
value; adoption by the recorded id with a fresh identity) and
`failure_rehearsal` (eight readings, every one reversed).
**`replacement_host_restore` is `not_run` by decision** (D1028): adoption binds a
replacement to production's Infisical project and environment, so a rehearsal's
copy cannot archive to a bucket of its own and the rehearsal ends at the
restore; its identity half is proved by the restore record. `fresh_host` and
`documented_path` stayed for the same want as before: no outsider, and no
project deployed on a host built to be deleted. Ten defects found on the day
(D1023–D1032), five of them in lines and calls that had never executed live.

---

## 3. P1 and P2

### P1 — six registered, five reported

| Requirement | Session | Claim | Verdict |
|---|---|---|---|
| `STO-COMPLETE-001` | 7 | `object_completion` | passed |
| `STO-BOUND-001` | 7 | `object_completion` | passed |
| `STO-CLEAN-001` | 7 | `cleanup_convergence` | passed |
| `REC-WAL-001` | 10 | `wal_archiving_signal` | passed |
| `OPS-LOG-001` | 11 | `log_correlation` | passed |
| **`DBX-004`** | 4 | **none** | tested, never reported — §4 |

### P2 — zero registered, and that is the finding

The specification names two P2 capabilities. **Neither was ever entered into the
acceptance registry**, so they are not unbuilt requirements — they are scope that
nothing has been tracking. No test, no claim, and no report would have said they
were missing.

| Capability | State | Effort |
|---|---|---|
| **pgvector example and vector-search RPC** | The extension is present and proved at its locked version in the `extensions` schema (`DBX-PG-001`). **No example table and no search function exist.** | Small: one migration adding an embedding column and a `api.search_*` RPC, plus its capability entry. The hard parts — the extension, the migration plane, the RPC pattern — are all built. |
| **Portable nightly `pg_dump` export** | Nothing in `bin/` or `src/` references `pg_dump`. | Small–medium: a command, a timer beside the existing backup timers, and a destination. The backup plane already has scheduling and an off-site credential; this is a second artefact through the same path. |

Both are droppable by the specification's own rule — *"P2 items may be dropped
before any P0 item if the schedule slips"* — and both are dropped. **What is not
acceptable is dropping them silently, which is what an empty P2 row in the
registry does.**

---

## 4. The claim-coverage gap — partly closed, and repriced

> **Corrected in Session 13 Run 6.** This section said the gap was *"small, and
> it is bookkeeping rather than proof."* **That estimate was never measured and
> it is wrong.** Thirteen of the thirty-seven were retrofitted; **twenty-four
> cannot be**, for structural reasons. D720, D721 and D722 record the
> measurement.

**24 of 131 requirements belong to no claim**, down from 37 of 127. The evidence
document now reports **107**, up from 90. The remainder are tested — every one
has node ids, and those tests run and pass in the gate — but no evidence document
reports them.

**Thirteen were grouped into claims**, dated to Sessions 2, 3 and 4 rather than
to 13: their requirements have not moved, and dating them forward would leave
Session 2's evidence permanently silent about its own host while looking closed.
Measured before any were written — those three sessions already carry claims, so
each already runs the claims path in the mode the new ones need. A claim there is
an extra row in a document that is already produced, not a new obligation.

**Why the remaining twenty-four cannot be, and it is not effort:**

* **Twenty-one have no live proof at all.** `claim_mode` raises for a claim whose
  every node id runs in a checkout — *"no deployment is being measured."*
  `CFG-001`–`CFG-015`, `DX-002`, `DX-003`, `DBX-MIG-002`, `DBX-MIG-003`,
  `DBX-PG-002` and `AGT-DRIFT-001` are properties of parsing, rendering and the
  developer's own tooling. Reporting them needs an **offline-only claim**, which
  is a decision about what a claim IS (ADR 0045/0089), a change to `merge`, and
  every gate from 1 up gaining claims to report. **A session's work, not a
  morning's.**
* **`SEC-NET-001` was tried and deliberately removed.** A `public_boundary` claim
  over it existed and was withdrawn: its proofs include an IPv6 scan no available
  network can run, so it could only ever come out `failed`. A second reason
  arrived with the measurement — Session 2 carries no external claim, so adding
  one would make `--external-input` newly required for every Session 2 merge.
* **`OPS-HEALTH-001` and `SEC-TLS-001` each span two modes**, which `claim_mode`
  refuses. ADR 0045 split `direct_transport` from `transport_boundary` for
  exactly this, and that worked because the halves were *separate requirements*.
  Here it is one requirement whose node ids span both, and **a claim names
  requirements rather than node ids** — so splitting these means splitting the
  requirement, which renumbers a Session 2 contract.

**And the guard this section recommended already existed when it was written.**
*"The guard worth writing first: a test that every registered requirement belongs
to exactly one claim"* — that is
`test_no_new_requirement_goes_unreported_by_every_claim`, written in the same
session as this page, carrying the staleness check this page did not ask for
(D727).

---

## 5. Hidden dependencies

Every third party this deployment needs, with what breaks if it is unavailable.
**None is hidden any longer; each is either pinned, declared, or named here.**

| Dependency | Pinned how | If it goes away |
|---|---|---|
| **Infisical** | image digest; account and project id in per-project bootstrap state | No deploy. Every secret is materialized from it, and nothing here caches a value between generations. |
| **Cloudflare R2** — object storage | bucket, prefix and credential per project | Storage plane fails; the database is unaffected. |
| **Cloudflare R2** — backup repository | its **own** bucket, credential and cipher pass (ADR 0145) | No new backups and no restore. Deliberately a separate bucket so a storage compromise is not a backup compromise. |
| **Cloudflare DNS** | records are DNS-only / grey cloud | No certificate renewal, then no ingress. |
| **Let's Encrypt** | `letsencrypt` resolver, production | **Failed validations cap at 5/hour/hostname.** Never retry in a loop. |
| **Container images** (8) | **immutable digests** in `versions.env` | A rebuild cannot resolve; running containers are unaffected. |
| **PGDG apt** — `pgbackrest=2.59.1-1.pgdg12+1` | exact version pin | **This one has an end date, and Session 13 Run 8 diarised it** (D533). PGDG drops superseded versions, so the pin will one day resolve to nothing and the image build fails closed at exit 100. That is the accepted half — it is a pin, not a floating tag. The note now sits **at the pin** in `versions.in.yaml` with the one command that answers *"is it still there"*, to be run before any session that rebuilds this image. |
| **PyPI** | hash-locked `requirements-dev.txt` | Development only; no deployed service installs at runtime. |
| **GitHub** | **not a host dependency.** Transport is `git bundle` + `scp` | Nothing. No GitHub credential exists on the VPS, by decision. |

**The one genuine residual** (ADR 0147): the database container can reach the
internet, because pgBackRest must reach R2. It holds the repository credential
and the cipher pass, so an attacker inside it owns the backup history as well as
the live data. A host-level egress proxy is the shape that would retire this.
Nothing is planned.

---

## 6. Template, or control plane?

The specification asks this session to decide. **It is recorded here and
deliberately not resolved in a test**, because it is a product decision and not a
property of the artefact.

* **What the product contract freezes:** *"A reusable, isolated,
  one-project-per-deployment PostgreSQL appliance **and template**. One
  deployment serves exactly one project."* Under that reading the customer is a
  team who deploys it on their own host, and `DX-001` is not a nicety — it is the
  product.
* **What the stated direction is:** a hosted service with a UI, where users
  consume the product and nobody self-hosts. That is a **managed control plane**,
  which §2.2 of the specification lists under explicit non-goals.

These are different products, and the divergence is the finding. **What survives
either answer is `DX-001`'s underlying property** — that a deployment needs no
knowledge living in one person's head. Under the hosted reading it matters
*more*, not less: an instance per customer, deployed repeatedly, possibly under
pressure, possibly by somebody hired later.

**Recommendation, offered as one:** close `DX-001` regardless of the direction,
because the cost is one outsider's afternoon and the alternative is discovering
the gap during a customer deployment. Session 11's rehearsal already found
`provision-host.sh` naming an operator user it does not create while installing
`PermitRootLogin no` — which locks out the person deploying at 3 a.m. exactly as
readily as it locks out a stranger.

**Answered as a recommendation in
[stage-3-decision-report.md](stage-3-decision-report.md) §5** (Session 18,
D992): ship `1.0.0` as the template the evidence shows it to be, and put the
control-plane question to a Stage 3 specification that starts from the
premises the tree corrected -- no coordinator, no PostgreSQL 19, no public
port. This entry stays as the record of the question; the report is where
the answer and its numbers live.

---

## 7. What ships

**An appliance whose four access planes are proved against a live deployment**,
two isolated projects on one host with the isolation measured rather than
asserted, a rehearsed point-in-time restore, and a documented path whose commands
all resolve and whose session numbers are checked against the release.

**What does not ship, each named rather than implied:** the signing-key rotation
(D683), the outsider's witness (`DX-001`, `DEP-001`), two P2 capabilities that
were never registered, and the 37 requirements the evidence document does not
report on.


---

## 8. What Session 19 repaired, and what it left open

An outsider built an application on 1.0.0, on a host that started empty, and
recorded twenty-five findings. Nineteen were defects in the shipped release and
are repaired; `docs/plans/session-19-implementation-plan.md` §1 carries the
rows. This section is only what stays open.

**Open, and each needs a decision rather than an afternoon:**

| Item | Why it is open |
|---|---|
| **D1045** — the provider's error message is discarded | The body is withheld deliberately: *"on identity endpoints it can echo the request, and this message reaches a log."* Relaxing "no bodies" to "no raw bodies" is a security decision in a credential path. It cost 25 minutes of API archaeology to recover a sentence the server had already sent. |
| **D1058** — `0003`'s comment has been false since `0006` | Not repairable in place. A released template's bytes are the unit `verify-lock` checks, so editing even a comment changes a recorded digest. |
| **D1059** — a cancelled CI run is not a failed one | `concurrency: cancel-in-progress: true` means a superseded run concludes `cancelled`, and a reader bucketing everything that is not `success` as failure reports a verdict the run never reached. Observed on this session's own push. |
| **D1060** — repaired in code; the LIVE reading is what stays open | Session 20 built the three-outcome readers (ADR 0199): `RenderedDocumentAbsent` exit 4, `RenderedDocumentUnreadable` exit 3, one resolver in `bin/rendered-document.py`, sixteen offline node ids green. **The live half has never executed and could not** — see D1121: it reads as whoever invoked the gate, and the gate runs as root. `honest_readers` is `not_run` in `evidence/session-20.json` for that reason and not because the readers are wrong. |
| **D933** now blocks two things | It blocked a project disabling a write capability (ADR 0183). It now also blocks retiring the task tools, which is why ADR 0196 chose restoration. That asymmetry is the argument for repairing it in Stage 3, beside D1056's closed scope vocabulary. |

**What the session says about the two claims that have been open since Session
12** is ADR 0197, and it separates them:

- **`fresh_host`** — the artefact exists. An empty host reached a working
  deployment, and who drove the bring-up does not bear on that question.
  Supplying `APG_FRESH_HOST_OUTPUTS` is mechanical and is the operator's.
- **`documented_path`** — answered, and the answer is no. `DX-001` requires the
  path be completed *without source edits*, and the run edited seven tracked
  files. Two are already gone (D1034, D1035); the remaining five are one design
  question and it is Stage 3's. The claim has moved from *"nobody has tried"* to
  *"somebody tried and the path does not hold"*, which is a stronger statement
  and should not be softened into a green tick.

**The pattern worth carrying forward.** Six of the twenty-five findings were one
defect — a check whose failure path returns one of the answers it was supposed
to choose between — and ADR 0195 states the rule. Six *more* instances were
found during the repair itself, four of them in guards written that day. The
class is a trap rather than carelessness, and the cheapest defence is the one
`bin/backup.sh` already had: say that you did not get an answer.

---

## 9. What Session 20 left open

Session 20 built the tenant extension point (ADR 0198), the third route word
(ADR 0199) and ADR 0196's `api.create_task`, and closed four rows above. Its
divergence table is `docs/plans/session-20-implementation-plan.md` §1, rows
D1098–D1121. This section is only what stays open.

| Item | Why it is open |
|---|---|
| **D1121** — `honest_readers`' live half cannot run under the gate that admits it | The proof's docstring says *"Run as the GATE'S OWN USER against the checkout, unprivileged"*; the gate is invoked under `sudo`, so its user is root, `os.access` is unconditionally true and the test takes its own skip branch on every host run. Past the skip, `migrate.sh render` as root would exit 0 rather than 3. Two offline siblings skip in the same run with *"root traverses a 0000 directory"*. **The repair is named and is Session 21's**: make the reading as the unprivileged checkout owner (`sudo -u` the owner of `REPO_ROOT` when `geteuid()` is 0) AND have the proof construct and restore the root-owned precondition itself, because D1110 shows a `sudo` deploy undoes it. Both halves are needed; either alone still measures the wrong thing. |
| **D1122** — a DR kit stops verifying when the outputs schema moves | `bin/dr-kit.sh verify` validates a stored deployed document against the READING checkout's `outputs.schema.json`, so the kit exported at v16 exits 5 against a v17 checkout — in the one scenario a kit exists for, rebuilding a lost host from a current checkout. The migrator that would make it readable (`migrate_v16_to_v17`) exists and the reader does not call it. **Session 21**: migrate, then validate. The kit itself was re-exported on 2026-09-11, which was owed anyway — the old one described a session-18/v16 deployment that no longer exists. |
| **D1105** — eleven test sites chain the outputs migrator by hand | Every version bump edits all of them and every instance is found by CI at the end of a run. The repair is one helper that carries a document to the current version, and a change to eleven modules deserves a battery of its own. |
| **D1099** — `migrate.sh status` exits 0 on an out-of-order pending migration | dbmate reports it as an ordinary `Pending: 1`, and the condition that will refuse the very next `up` is nowhere in the verb an operator reads first. Third-party, so ADR 0195's rule cannot be applied to it; `follows_release_version` refuses at freeze instead, from the other end. |
| **D1119/D1120** — the cheap checks existed and were not run | Renaming a test drifted the acceptance registry, which `test_acceptance_registry` catches offline in 44 seconds, and CI reported it red twice before a host gate spent thirteen minutes rediscovering it. Not a product defect; a discipline one, recorded so the rules it produced (`test_acceptance_registry` belongs in the targeted list of any run that renames a test) survive the session that learned them. |

**Still open from earlier sessions**, unchanged by this one: `fresh_host` and
`documented_path` (ADR 0197, §8), `replacement_host_restore` (D1028, by
decision), `bootstrap_identity` (a rotation performed, D860), and the five
claims D478 names.

## 10. What Session 21 left open

Session 21 opened the agent plane to a tenant's domain (ADR 0200, ADR 0201)
and closed D1121's live half, D1122 and D1123 above. Its divergence table is
`docs/plans/session-21-implementation-plan.md` §1, rows D1124–D1155; its
evidence is 108 claims, 99 passed, 9 not_run, 0 failed at `f61f716`. This
section is only what stays open.

| Item | Why it is open |
|---|---|
| **D1153** — the deployed document's `mcp.tool_count` and the doctor's *capability drift* read the lock file, not the plane | For eight minutes on 2026-09-11 both said seven while beta's plane served six (D1152). The container already answers a one-line probe for its protocol constants; the same probe can report the loaded lock's `tools_sha256`, and `observe_mcp` can refuse to publish a count the container did not confirm. A run's change. |
| **D1155** — `honest_readers`' offline half skips under root | The live half was repaired (D1131) and passed; the two offline proofs carry `skipif(geteuid() == 0)` and the gate runs its static claim proofs as root, so the claim reads `not_run` in one sweep for the other half. D1131's shape applied to the two proofs, or the gate's static proofs run as the checkout owner. |
| **D1151 / D1154** — the gate sweep leaves `.generated/alpha-dev` root-owned, and two readers crash on it | The sudo deploy hands the directory back (D1110, read on the day); the sweep does not (mtime 12:27, its first minute). `rendering.publish` and `evidence.load_rendered` then fail with a traceback rather than naming the owner and the chown — ADR 0195's class in two more readers. |
| **D1156** — the example set grants its view and RPC to no agent role | Measured in the round trip: an agent holding `note_embeddings:read` is listed the resource and `query_resource` over it is refused upstream (PostgREST as the agent role, audit reason `upstream_refused`). The compiler and the snapshot cannot see grants. Fix forward: a second migration in the example set granting the two agent roles, a README sentence that the grant is the adopter's, and a live proof that READS through a tenant tool. Session 22's first item. |
| **D1150** — the plan's claim joins | Recorded: a Session 21 requirement joined into a Session 16 or 18 claim re-dates the claim (ADR 0089), so `EVAL-HARNESS-002` and `REC-KIT-003` are claims of their own. Not a defect; a rule the next plan should apply when it writes §2. |
| **Beta has no recorded administrator password** | `/root` holds `alpha-dev-administrator` only. Every proof and reading on beta creates its agents through `auth_create_agent`; the ceiling at creation is measured on alpha through the endpoint. Recording one is an operator decision (`bin/auth-admin.sh`), not a run. |

**Still open from earlier sessions**, unchanged by this one: `fresh_host`,
`documented_path`, `replacement_host_restore`, `bootstrap_identity`, and the
five claims D478 names. D1099 and D1105 above: D1105 closed in Run 4
(`carry_to_current`, D1134); D1099 stands.

---

## 11. What Session 22 left open

Session 22 built `apg dev` and gave the evidence model a third mode. It made no
host trip, deliberately (D1163): four of its six claims are about a command a
developer runs on their own machine, and the session closes on the first offline
evidence half this project has written.

| Item | Position |
|---|---|
| **Two claims are `not_run` and Session 24's trip collects them** | `plane_confirmed_count` (`OPS-PLANE-001`) and `agent_tenant_read` (`AGT-TENANT-002`). Both are about a RUNNING plane — whether the deployed document's tool count is the one the container confirmed, and whether an agent reads a tenant's rows — and a checkout cannot answer either. They were deliberately **not** declared offline: a checkout answering the first would have reported beta green through the eight minutes it served the wrong lock (D1152). Their offline halves are written and pass; what is owed is the live half. |
| **What Session 24's trip owes this session** | A deploy `--through-session 22` on both projects (which applies the example set's second migration on beta and nothing on alpha), `bin/session-22-check.sh --mode host` and `--mode external`, and a **three-half merge** — `--offline-input evidence/session-22-offline.json` is REQUIRED, because the session has offline claims. Run the merge from a checkout at the commit the offline half measured, or the writer prints the difference. |
| **D1189 shipped broken for two sessions and only a proof that READ could find it** | The example set granted `api.note_embeddings` and never `app.note_embeddings`, and the view is `security_invoker` — so every caller was refused on the table, including the role the migration did grant. Repaired in `0002-agent-grants.sql`. The lesson is registered rather than left in a divergence row: a grant proof that stops at `has_table_privilege` measures the catalog; one that ends in `SET ROLE …; SELECT` measures the answer. |
| **`test_honest_readers`' `sudo -u` prefix has still never run** | D1165 replaced a `skipif` with a re-entry as the checkout's owner, and that branch runs only under root. `sudo -n` is refused on this workstation, so everything about it except the prefix is exercised (`test_the_reading_the_root_branch_makes_gives_the_same_answer`) and the prefix itself waits for a gate that runs as root. `honest_readers` is expected to pass in both halves at the next sweep, for the first time. |
| **The uncached first run is measured in CI and nowhere else** | `apg dev up` with the image not cached is the run a new developer actually has, and measuring it on this workstation means evicting the image the whole contract suite shares. It is named in the envelope's `UNMEASURED` list with that reason, and CI's round-trip step times the same two verbs on a fresh runner. |
| **Nothing prunes a development environment nobody took down** | `down` removes the container, its anonymous volume and the state directory, and `status` reports a stale state — but a developer who renames a project or deletes its manifest leaves `.generated/.dev/<key>/` behind with two `0600` password files in it. They are passwords to a container that no longer exists, which is why this is a tidiness item rather than a security one. A `dev prune` verb, or nothing. |
| **The seed lint is a statement scan, not a parser** | `SEED_DDL` is a word-boundary regular expression over statements with comments stripped. It refuses what a seed should never contain and it is not a SQL grammar; a sufficiently determined seed could express DDL it does not match. That is the same judgement D464 records elsewhere in this tree — a text scan standing in for a construct — and it is deliberate here because the alternative is a parser nobody would maintain. The seed is reviewed and digested; the lint is the second lock, not the first. |

---

## 12. What Session 23 left open

Session 23 built `apg generate` — a typed TypeScript client over the surface a
project publishes, and the claim such a client makes about it (ADR 0204). It
made no host trip, and it is the second session to close on an offline evidence
half. The split is what is worth reading: **two of its four claims are declared
offline and two deliberately are not**, and unlike Session 22 that was a choice
rather than a necessity. A generated client meets a deployment; the reason the
second pair stayed host claims is that a checkout cannot answer what a
deployment serves a caller, nor which lock a running plane loaded.

| Item | Position |
|---|---|
| **Two claims are `not_run` and Session 24's trip collects them** | `generated_client_hash` (`GEN-HASH-001`) and `agent_lock_reported` (`AGT-META-001`). The first runs the committed example client in the toolchain image against beta (`ok`) and against alpha (`stale_contract` naming both digests — alpha publishes the release surface alone, which is the control that says `init()` discriminates rather than merely passes). The second calls `list_resources` on beta and compares the reported `lock.tools_sha256` with what the plane's own probe reports AND with the digest compiled into the client. Both offline halves are written and pass; what is owed is the live half, and `tests/deployment/test_session23_client.py` **has never executed** — the thirteenth never-executed proof this project has carried to a host. |
| **What Session 24's trip owes this session** | A deploy `--through-session 23` on both projects. It applies no migration — this session ships no SQL — but it **recreates the auth/mcp container**, whose mounted lock digest moved, and that is what makes `list_resources` answer with its `lock` member at all (ADR 0155, D1152/D1153: read the container, never the file). Then `bin/session-23-check.sh --mode host` and `--mode external`, and a **three-half merge** with `--offline-input evidence/session-23-offline.json`. Session 22's own three halves are still owed and are a separate merge. |
| **The bump moves a committed generated artefact, and nothing said so** | `contract.ts` carries `templateVersion`, so `VERSION` 1.3.0 → 1.4.0 made `apg generate --check` exit 5 on a client nobody had touched (D1238). The version rule behaved correctly — `clientVersion` stayed `1.0.0` because no digest moved, which is exactly what "an unchanged contract keeps its number" means — but **every release bump from now on owes a regeneration in the same commit**, and the gate and CI both refuse one that forgets. |
| **A registered requirement can outrun its proofs** | Two clauses of `GEN-EMIT-001` as the plan wrote it — the emitted `PtCode`/`AgentRefusal` unions, and a write wrapper's required `idempotency_key` and `dry_run` — had **no proof at all** (D1236). The emitter did all of it; nothing asserted any of it, because the proofs that existed were about what the *IR* carries. Both were written before the requirement was registered. The shape is D816/D929 one level up: an unverified field is bad, and an unverified requirement CLAUSE goes into an acceptance matrix and a claim's verdict. |
| **A session-scoped assertion written as a global equality** | Session 22's `test_exactly_the_four_declared_claims_are_offline` asserted `OFFLINE_CLAIMS` equals its own four. Correct while it was the only offline session; on the day a second session declared any, it became a rule that no later session may ever have an offline claim (D1237). Narrowed in both modules to what each is about. Worth carrying because the assertion was not wrong about Session 22 — it was stated one scope too wide, and a scope too wide reads as correct for exactly as long as nothing else exists. |
| **A guard can ask a real question of the wrong reader** | D1242, found by the close's own gate and not by anything standing in for it. Run 6's repair for D1240 collected with `contract and not future` — the Session 1 gate's selector — while the sweep that **reports an offline claim** selects `p0 and not future and not live_host and not external`. One registered P0 proof sat in a `p1` module: in the first collection, absent from the second, and so `not_run` at the close. Both strings are real selectors collecting thousands of tests, and **the wrong one was green** — mutation M2 puts it beyond doubt, because with the selector set back the offline guard passes and only the new drift test fails. The selector is a constant now, checked against the newest gate script (D486). D1240 said collectible and collected are different questions; this says **collected by WHICH sweep** is a third. |
| **Four modules outside every marker-selected sweep, and they are not this session's** | D1240 found four of Session 23's own modules carrying no `pytestmark`, so no gate collected them. Measured with the same selector, four MORE have the same shape: `test_database_function_signatures`, `test_storage_client`, `test_storage_endpoint`, `test_storage_endpoints` — each collects **0** tests under `-m "contract and not future"`. None belongs to a declared offline claim, so the new guard is silent about them by design; whether their proofs should be in a sweep is a question for whoever owns the storage plane. What is not in doubt is that they are not being run by one. |
| **No Python client, and this one is not a browser client** | D1205: the intermediate representation is language-neutral and a second emitter is one module over it; building one to be deleted is not a decision this session took. And `canonical.ts` uses `node:crypto` — a browser build needs Web Crypto's asynchronous `subtle.digest` and a bundler nobody has pinned. Both boundaries are recorded rather than hidden, in `docs/generated-clients.md` §7. |
| **`app-openapi.canonical.json`'s canonical form is not `openapi_normalize`'s** | D1203. `bin/app-contract.py` writes it with `ensure_ascii=True` and Pydantic's float literals; two serializers agree today only because the document is ASCII. The day it is not, `app-contract.sh --check` and a reader using `canonical_bytes` disagree about the same file. The client never compares that digest, which is why this is a decision for a session that versions that snapshot rather than a defect now. |
| **Nothing regenerates a client automatically, by decision** | D1208. The capture and the compile each print the command, and the gate refuses a stale committed client. An adopter who ignores both holds a client whose `init()` will refuse — which is the designed outcome and not a gap. |
| **PostgREST beside `apg dev` is a rig, not a verb** | D1211. Session 23's runtime proof stands up a cluster, a PostgREST configured from `compose.yaml`'s own block and the pinned Traefik, and takes ~150 s to do it — the most expensive module in the suite. If Session 24's Studio wants a served surface on a workstation, that is the session to decide whether ADR 0203's boundary moves, with this rig as the measured cost. |
| **The filter-operator set is the capability schema's, for humans too** | D1210. A human wanting `ilike` through the generated client is a reviewed widening of the capability schema, which then reaches agents. The coupling is deliberate and is written down so it is not undone by accident. |
