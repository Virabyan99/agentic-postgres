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

Counted from the files at this session's close, never recalled (D1194).

| | Count | Note |
|---|---|---|
| Requirements in the acceptance registry | **219** | 211 P0, 8 P1, **0 P2** — six added in Session 25: four `DX-*`, one `SEC-*`, one `REL-*`. The plan's own prose said seven and §7's arithmetic said six; the file was counted (D1347) |
| Claims in the evidence model | **126** | four added in Session 25 — **three declared offline and one deliberately not**, which is one more offline claim than any session has declared |
| Requirements a claim reports on | **195** | 24 belong to no claim (D697), unchanged in number for the fifth session running; see §4 |
| Migrations released | **32** | fix-forward only. **Session 25 adds none**, and it is the first session in four of which that is true — part of why ADR 0162 prices this release a minor |
| Architecture decisions recorded | **207** | 0202–0203 are Session 22's, 0204 Session 23's, 0205 Session 24's, **0206–0207 Session 25's** (0206 landed in Session 24's Run 8) |
| Divergences measured | **D1–D1377** | D1200–D1242 are Session 23's, D1259–D1281 Session 24's, **D1303–D1377 Session 25's** — 75 rows, of which twelve were planning rows and **eight were product defects found by walking the adopter's path, by a battery, or by the trip's first sweep** rather than by reading. D1351–D1377 are the two walks, the host trip and their repairs |
| Claims declared offline | **11** | Sessions 22's four, 23's two, 24's two, **25's three**. Declared, never inferred (ADR 0202) |
| `template_version` | **1.6.0** | a minor, priced by ADR 0162 in `CURRENT_SESSION`'s own comment — and the comment now has a reader (`test_release_contract.py`, D1346). **Confirmed on the host 2026-09-15**: `upgrade plan` returned `minor` on both projects with exactly one leaf differing, and both are deployed at it |

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
| **D1189 shipped broken for two sessions and only a proof that READ could find it** | The example set granted `api.note_embeddings` and never `app.note_embeddings`, and the view is `security_invoker` — so every caller was refused on the table, including the role the migration did grant. Repaired in `0002-agent-grants.sql`. The lesson is registered rather than left in a divergence row: a grant proof that stops at `has_table_privilege` measures the catalog; one that ends in `SET ROLE …; SELECT` measures the answer. |
| **`test_honest_readers`' `sudo -u` prefix has still never run** | D1165 replaced a `skipif` with a re-entry as the checkout's owner, and that branch runs only under root. `sudo -n` is refused on this workstation, so everything about it except the prefix is exercised (`test_the_reading_the_root_branch_makes_gives_the_same_answer`) and the prefix itself waits for a gate that runs as root. **Session 25 Run 3b removed the last thing standing in its way**: `test_render_atomicity.py` still carried a bare `skipif(geteuid() == 0)`, so the claim could not pass on any gate that could record it (D1302), and the repair was shown OFFLINE rather than costing a second host sweep (D1310 — a container running as uid 0 is the identity the gate has). `honest_readers` is expected to pass in both halves at Session 25's sweep, for the first time. |
| **The `--kit-dir` trap is LOUD, not quiet** | D1282, re-measured 2026-09-17 (D1452). This ledger and `CLAUDE.md` §9 have described aiming `--kit-dir` at the newest kit as destroying the proof *"without failing"*. It fails: `test_the_kit_exported_before_this_release_verifies_at_it` has carried `pytest.fail` on exactly that condition since Session 21, written with the proof. The row made a self-diagnosing guard sound like a silent trap, which produces the wrong kind of caution — an operator believing they must remember something the product already tells them. What is true and worth keeping is the operational half: **the claim's premise is the version gap, so at least one kit exported below the tree's outputs version has to be kept**, which is why three are. Run 5 made the refusal name the kit and its contents rather than only what it wanted. |
| ~~**test_honest_readers' sudo -u prefix has still never run**~~ | **CLOSED 2026-09-17: it ran, and it passed** (D1455). Rig 28c: ubuntu:24.04 as uid 0, the checkout bind-mounted at its own path and still owned by 1000:1000, the uv interpreter beside it, the owner uid created inside so sudo -n -u has somebody to become. 24 passed, 0 skipped, including both proofs that carry the re-entry. **The thirteenth never-executed proof and the first not to fail** -- because D1165, D1300, D1301, D1302, D1330 and D1332 had each already repaired it in response to a first execution elsewhere. |
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

---

## 13. What Session 24 left open

Session 24 built `apg studio` — a loopback page over a deployment, holding the
human's token and handing the browser nothing but a launch cookie (ADR 0205) —
and migration 0032, which makes the audit reader return the boundary that
refused (D1247, ADR 0178). It is the third session in a row to close on an
offline half, and its Run 7 is the trip that pays Sessions 22, 23 **and** 24 in
one sweep.

The find worth carrying out of the session is not in this table: **the served
REST document is scoped to the caller's grants**, so an administrator is served
the anonymous document and Studio answers `stale_contract` for them (D1275).
Nothing was wrong; the sentence was, and one answer with two causes and only one
named is ADR 0195's folded outcome in the reassuring direction.

| Item | Position |
|---|---|
| **`agent_audit` and `agent_idempotency` still grow without bound** | **CLOSED 2026-09-17 by Session 28 Run 6 — and as TWO rows, not one; see §18 and ADR 0213.** What Session 24 recorded, unchanged: STATED, not handled (D1255). Nothing prunes either. Studio's audit view makes the shape visible — the newest 500 rows, with a header that says the page is the newest 500 — which is honest about what it cannot count and is not a bound on the table. The counts on the deployment are unmeasured until the trip records them. A retention policy is a released migration carrying a decision about how long a denial must remain readable; that decision has not been taken, and taking it in a session that also had to deploy it is why it was not taken here. |
| **`GET /admin/audit` still filters by agent, owner and limit only** | D1248, priced and not built: a window, an outcome/boundary filter and a cursor are one migration over 0032's reader plus one endpoint change. Studio's forwarder deliberately refuses every parameter but the endpoint's own two, with 400 — so there is no request shape in which a filter narrows what was READ, and therefore none in which a viewer is shown a count that silently excludes refusals. That refusal is what a later widening has to preserve: whatever filters are added upstream, the page's count must remain a count of the page. |
| **An administrator cannot use the schema or query views, and that is the deployment's authorization** | D1275. `project_admin` holds nothing in `api`; PostgREST serves it the anonymous document. Documented in `docs/studio.md` §2 with the measurement beside it. What is NOT decided is whether a human should ever hold both — an administrative scope set and a data role — and that is a question about the project's role model rather than about Studio. |
| **The capability view is the checkout's lock, never the plane's** | D1274. Studio does not ask the deployment which lock it loaded, because `list_resources` reports that (D1201) and it is an agent call, and ADR 0205's rule is that Studio holds nothing the human does not hold. The view says so in a sentence that travels with the data. A human-readable *is the plane serving this lock* remains `bin/apg.sh doctor`'s question. |
| **The launch URL is readable by any local process, and that residual is accepted** | Terminal scrollback, `/proc/<pid>/cmdline`, the port list. A process running as you can already read your SSH keys; a launch URL is not the weakest thing available to it. It is bounded by the process's lifetime and by the token's 900 seconds, and by nothing else: there is no idle timeout in the page, deliberately, because a control on the page is a control on the wrong side. `docs/threat-model.md` states it. |
| **A rig that reaches a published loopback port is a rig that assumes a daemon** | D1276. Run 4's CI errored seventeen times on `Connection refused` to the port `apg dev up` publishes — while `docker exec` against the same container, in the same fixture, worked. `apg dev` publishes `127.0.0.1:0:5432` by decision (D1175), and a host-to-loopback DNAT is something a daemon can be configured not to make work. The fixture now proves an address before building on it and says which it used. Every other rig in this suite that reaches a dev cluster from the test process inherits the assumption and has not been asked. |
| **Studio has no live half for the query view's RLS, off this workstation** | The runtime module proves it against `apg dev` + the real auth application + real PostgREST, which is a deployment in every respect except that it is not THE deployment. The trip's module exercises the launch and the surface answer against beta; the RLS pair is not repeated there, because it would need two subjects created on a production project. Recorded as a choice. |
| **The three envelope rows are this machine's** | `apg studio` start 0.74/0.66/0.74 s, the page 1.3/3.1/2.4 ms, the schema view 1.3/1.1/1.2 ms. MACHINE measurements, and the views that make an upstream request are deliberately unmeasured: those are a deployment's numbers and no arithmetic converts one machine's into another's. |
| **A closed environment roster, and a live module that wanted a third name** | D1278. `APG_ADMIN_PASSWORD_FILE` is read by `admin_password` and is not in `tests/conftest.py::ENVIRONMENT_VARIABLES`, so no module can GATE on it — only fail on it at fixture time. That is right for a password file and the wrong shape for a sweep that would rather skip than fail; whether the roster should carry it is a decision about the roster, not about this session. |

---

## 14. What Session 25 left open

**`documented_path` closed `failed`, and it is the first `failed` claim this
project has written.** Two walks were run (ADR 0207, §9 allows no third). The
first, on `040f733`, recorded six undocumented steps and found that two of the
adopter's seven goals are unreachable offline (D1357). The second, on the
repaired `a4b9685`, recorded **eleven** — two of them against the first
repair's own prose, and one a product defect the repaired documentation walked
the reader into: the documented `compile … > contract.json` leaves a 0-byte
file when it refuses, and every reader of it exited 1 with a traceback (D1359).

**Producing that status required repairing the gate**, which could not emit it
(D1373): `set -euo pipefail` plus a bare pytest call ended every run before
claims were computed, so in twenty-five sessions no evidence document had ever
carried a `failed` claim. That read as nothing ever having been wrong and meant
the path had never executed.

**What is still owed.** The seventeen documentation findings the two walks
produced were repaired, and **nine of them after the last cold reader had
gone**. The product defects carry proofs and batteries; the prose carries the
judgement of the session that wrote it, which is the thing a walk exists to
distrust. **Stage 4's first act should be a walk of this release's
documentation, before anything is added to it** — second only to the rotation,
and for the same reason: both are things built and never exercised.

**Three rows the trip found and did not repair.** D1374: `render-jwks` reports
a file event as a domain event — *the key set CHANGED* is printed from a test
of the file's bytes, and on both projects the kid and the key-set digest were
identical before and after. D1375: `op` on the host cannot reach the Docker
socket and Session 25 is the first release whose offline mode needs one; the
group membership was deliberately not granted, so the host's offline half — a
control, never an input — cannot be produced there. D1376 and D1377 are process
rows about this session's own sheet and its own shellcheck severity, kept
because both cost real time.


Session 25 built no plane. It hardened the three developer surfaces against
every security invariant Stage 3 declares, gave the outsider's second walk an
instrument the product itself reads, re-derived the documentation an adopter
follows by walking it, and took the Stage 3 release to `1.6.0`. It is the
fourth session in a row to close on an offline half and the first to declare
three offline claims.

**The find worth carrying out of the session is not in this table: three
product defects were found by WALKING the documented path rather than reading
it** (D1340, D1341, D1342). A render printed a Python traceback and exited 1
for a project's own bad migration, because `ProjectSetError` is a
`MigrationError` and the render was the one caller of three that never got the
decision. Studio's refusal named what the file IS rather than what was
missing. And `blocked_by` was about to be asked of a walker by a task statement
with nothing reading it. None of the three was visible from the plan; each
appeared in the first minute of doing what the documentation says.

| Item | Position |
|---|---|
| **A person's walk has not happened** | ADR 0207's residual. An agent's clean walk proves the path holds for a reader who follows it; a person's would be a second record. `docs/second-walk.md` carries the task statement between two fixed markers precisely so a person can be handed the same words, and `dx_record` reads either record the same way. Whoever has a person available runs Run 6 again and adds the record beside the first. |
| **Studio was read, not opened, in the walk** | D1303. A walker has no deployment, and `apg studio` against a rendered document can only refuse — so the walk's criterion is `--help` exiting 0 and that refusal naming the deploy, recorded verbatim. The deployment-side half of an adopter's path — capture the snapshot, generate again, open Studio against one's own deployment — is documented and is `fresh_host`'s shape to prove, on a host built to be deleted. |
| **`dx_record.documented_commands` is a text scan** | D464's shape, over five documents and the session guides. A command written in a code block the regex does not match is invisible to it — which makes the check STRICTER, not weaker: an unmatched documented command makes a walker's honest use of it look unnamed. That is the safe direction, and it is written here so the first false failure is read as this rather than as the walker's. |
| **`APG_PROJECT` reads a verb's `--help` on every invocation it applies to** | ~15 ms, measured in rig 25a. A verb whose usage were expensive would make the default expensive; none is today. The envelope does not carry the number because it is below anything the envelope measures. |
| **The completion script is bash's** | A zsh or fish user has `--list` and `--help` and nothing else. A second shell is one more `case` arm printing a second script; nobody has asked, and writing one to be unused is not a decision this session took. |
| **The DR kit re-export, and the gate's `--kit-dir`** | D1282. The v18 export was taken 2026-09-13 and verifies, so the operational obligation is discharged — but `REC-KIT-003`'s claim IS the version gap between a kit and the tree that reads it, and its proof `pytest.fail`s on exactly that. The gate's `--kit-dir` stays on `kit-2026-09-11`, and the flag's own help text now says so in as many words. The next release that moves the outputs schema must re-read this row before pointing the gate anywhere. |
| **The rotation has still not been performed** | D860. **Offered on Run 7's sheet and DECLINED by the operator on 2026-09-15**, recorded as declined and never as failed — the fourth trip at which it has been offered. It is the first item on Stage 4's bill: the stage plan's §6 rule is that a credential which travels rotates first, and this one has never travelled because it has never rotated. |
| **The intermediate versions 1.3.0–1.5.0 have no tag** | D1311, by decision. `1.0.1` and `1.2.0` are tagged and `1.6.0` will be; the three between were released into a tree nobody outside was tracking. README says so once. |
| **A count in a name, twice in one session** | D1349 and the two names Run 5b repaired. `dx-record`'s usage said four readings while the command printed five; a test was called `..._the_eight_declared_claims_...` while eleven were declared. Both were created by a correct change that moved a count and not the sentence about it. The general repair is not available — nothing can hold every English number in the tree to a Python one — so what is written down is the habit: when a change moves a count, grep for the count. |
| **The gate-modes guard read its gate's prose for four sessions** | D1350, found by a battery and repaired in all four modules. The near miss is what makes it worth carrying: the helper that fixes it was already in each file, added by an earlier run for the same reason, three assertions further down. A repair that reaches one caller and not the next is §7 question 5, and it is the class this project produces most. |
| **What Stage 4 inherits, named so no session inherits it silently** | The public-endpoint decision as its first ADR (D1084), with `runtime_override.publication()` still raising; the rotation performed before any credential travels; ~~a retention policy for `agent_audit` and `agent_idempotency` before any hosted reading (D1255)~~ **— taken 2026-09-17, ADR 0213, §18**; the two fields named `capabilities_sha256` (D930); the Python client (D1205); the four unswept storage modules (D1240); the audit filters (D1248); a person's walk. `docs/stage-4-decision-report.md` §4 prices the first of these against the tree. |

---

## 15. What Session 27 left open

Session 27 built no plane and registered no requirement. It is the second
release where `VERSION` and `CURRENT_SESSION` come apart (1.0.1 was the first),
and for the same reason: an outsider found defects in a shipped release and a
session repaired them. `VERSION` moves to **1.6.1**, `CURRENT_SESSION` stays
**25**.

**What produced it.** An outside agent upgraded a real adopter's deployment
from **1.0.0 to 1.6.0** on 2026-09-16, holding only this repository's
documentation, on a host this project does not administer. It converged — exit
0, 10 ok / 0 problem, `upgrade verify` matching — and wrote eighteen findings.
Session 27's §1 carries them as D1388–D1405, of which **four were opened by the
session's own measurements and are not in the reader's file**.

**The finding that makes the others unreachable, and it is closed.** D1388:
`docs/upgrade-guide.md` and `docs/operator-guide.md` were not in tag `1.6.0` —
they land one commit past it. That is D1033's failure a second time, seven
sessions later, committed by the session that had read the first. ADR 0209
decides what a test can hold and what it cannot, and the guard ships in this
release.

| Item | Position |
|---|---|
| ~~**How a fork made before `projects/<slug>/` existed converts to it**~~ | **CLOSED by Session 28 Run 2, and the answer is `docs/on-ramp.md`** (ADR 0212). Measured on rig 28a, a fork rebuilt from tag `1.0.0`: re-homing moves no bytes and no version, so D912 was never the blocker; ADR 0206's ledger move already relocates a re-homed version BY STAMP, for free, on the next deploy (D1435); and the whole of what blocked it was one computed line in `freeze_project_lock` (D1436), now `--follows` (ADR 0210, Run 3). The conversion is bounded: a set that cannot reach a passing lint without a change that would alter the cluster it already ran on does not convert, and staying a fork stays supported. The row below it is closed too. **What the release still cannot prove is step 7** — the ledger move against a cluster carrying a fork's history (D940), which is the adopter's. The original position, for the record: |
| ~~**Which side wins each merge conflict is written down nowhere**~~ | **CLOSED: four classes, `docs/on-ramp.md` §2** (ADR 0212 §3). Not nine files — the count is a property of how many release-owned files a fork amended. The class that needed the rule most produced **no conflict at all**: the reviewed surface auto-merges and a tenant relation survives inside the release's contract unreviewed (D1434). The original position, for the record: |
| *(superseded)* | **The largest thing this release does not answer.** A fork at 1.0.0 was obliged to put its domain inside the release's own files — migrations in `migrations/templates/`, rows in the release's `manifest.json` and `released.lock.json`, operations in the reviewed surface. ADR 0198 and ADR 0206 create the mechanism and **neither says how an existing fork enters it**; entering would mean re-homing applied migrations, which D912 forbids. The upgrade guide's new §1.0 says so plainly rather than pretending §1 covers it, and records what the one operator did about the nine merge conflicts as *what happened*, not as instruction. **It is the on-ramp session's first question**, and it is a product decision before it is a page. |
| **Which side wins each merge conflict is written down nowhere** | Nine conflicted files on the one recorded upgrade, two of them generated artefacts carrying digests where *resolve by hand* and *a released migration is never amended* pull in opposite directions. A rule for this is a decision, not a paragraph. |
| **`generate --check` refuses every project with no set of its own** | D1404. The default output for such a project is `clients/typescript` under the checkout root and **the release tracks no such directory**, so the refusal is permanent and the page's old remedy would have had a reader create something the release does not carry. Run 4 says which of the two refusals a reader is looking at. **Whether the release should track a root-level client, or whether `generate` should refuse a setless project by name, is undecided** — it is a question about what `apg generate` is for. |
| ~~**`follows_release_version` when a set was frozen against an EARLIER release**~~ | **CLOSED by ADR 0210, built in Session 28 Run 3.** The operator declares it: `bin/migrate.sh --project <manifest> freeze-lock --follows <version>`, checked against the release's append-only manifest. **The refusal is unchanged byte for byte** — ADR 0206 declined to remove it and this did not either. What moved is that a record can now be TRUE: measured on rig 28a, `verify_lock` passes the re-homed set the moment the record carries the real value (D1436). The lock records `follows_release_version_source`, `computed` or `declared`, because a value that is sometimes measured and sometimes asserted with no way to tell which is the D600 shape; project lock schema 2 → 3, and a schema-2 lock reads as `computed`, which is what every lock written before ADR 0210 is. |
| **The interpreter on the deployment host is unchecked — and it is a consequence of ADR 0158's split** | D1418, D1441, re-measured in Session 28 Run 3 and **stated rather than repaired**, at the split itself in `bin/doctor.sh`'s header. Workstation mode checks a developer's interpreter and is unprivileged; deployed mode checks seven live things about ONE PROJECT and needs root. The host's interpreter is a property of the machine and of no project, so it belongs to neither question as they are drawn — and adding it to deployed mode would put a bare `python` resolution back under `sudo`, which is the exact failure the split exists to prevent. The only command that asks host-wide questions is `provision-host.sh --check`, which runs as root on production, and **no session has measured which interpreter versions this product actually requires on a host**: `.python-version` is the workstation pin. A check added on that footing could fail a host that works. |
| **`provision-host.sh` installs neither `uv` nor the venv** | D1396. A grep of that script for `uv`, `astral` or `pip install` returns **0**, and `host-baseline.md` described the maintainer's interactive shell as the baseline. Run 4 corrected the page and made the sync conditional. **Making `--apply` install them is not taken**: it changes what this product does to a machine. It belongs with the interpreter question below. |
| *(the interpreter row moved up, beside the decision that closed its neighbour)* | The measurement it carried is kept: the cold reader's host ran every `bin/*.sh` under the distribution's Python 3.14 against a `.python-version` of `3.12.13`. |
| **`stage_release`'s live half fails until the next trip deploys** | D1401, an obligation rather than a defect. The tree reads `1.6.1` and both projects are deployed at `1.6.0`. Every trip deploys before it sweeps; this is named so the trip that inherits it is not surprised by a red claim it did not cause. |
| **The operator guide has not been read cold** | The *upgrade* guide has, and eighteen findings came out of it. The operator guide was written by the session that read the material, and §13 says so. Its own cold reading is the instrument, and nothing substitutes for it — no test reads prose for truth (ADR 0209's *Consequences*). |
| **Seventeen of the format table's twenty-one entries had never matched a served format** | D1390, and the repair is shipped: the table is 44 entries, measured against a running PostgREST for every type and every array form, with the measurement committed as `RIG_27B_SERVED`. What remains open is the shape of the lesson — **a table written from SQL type names rather than from what the server emits looks correct and is untestable by the documents the release happens to carry.** The two committed snapshots between them serve five formats and one enum. |
| **The self-check's blind spot, inherited by the guard that replaced it** | Session 26's self-check matched a command line by its first word, so a flag on a backslash-continuation line went unchecked. Run 5's proofs read the pages through the two real scans instead, which is stricter — but neither scan reads a continuation line either. Written down so the first false pass is read as this. |
| **Everything Stage 4 already inherited** | §14's last row, minus the retention policy, which ADR 0213 takes (§18): the public-endpoint decision, the rotation performed before any credential travels, the two fields named `capabilities_sha256`, the Python client, the four unswept storage modules, the audit filters, and **a person's walk**. Session 27 adds the on-ramp question at the top of that list. |

---

## 16. What Session 28's Run 1 struck, and what it found instead

Session 28 was planned against `docs/pre-stage-4-audit.md`, one inventory of
everything this project knows is wrong with itself. Run 1's job was to measure
all **36** of its Tier 1 rows against the tree in both directions before any of
them was worked — `CLAUDE.md` §4's rule, that a row describing what already
exists prices a free property as a session.

**Fourteen of the thirty-six are already answered in this tree.** Each is struck
below with the command that shows it. **Three of the fourteen would have caused
harm implemented as the audit writes them**, which is the reason the measurement
was a run rather than a paragraph.

> A struck row is not a row somebody decided to skip. It is a row where the
> audit's closing act is not the act the tree needs, and §6's rule applies: a
> conflict between a record and the code is a divergence with a number, never a
> silent reconciliation. All fourteen carry one — D1407–D1418, D1420, D1426 in
> `docs/plans/session-28-implementation-plan.md` §1.

### The three that would have done damage

| Row | What the audit says | What the tree says |
|---|---|---|
| **F-013** (D1411) | *"The lint forbids `{{app_runtime}}`, which the release's own migration `0003` uses"* — closing act *"roughly one line"* | `grep -n 'TO {{app_runtime}}' migrations/templates/*.sql` finds `0001` and `0003` only, and `0006-app-runtime-least-privilege.sql` then issues `REVOKE ALL ON SCHEMA app FROM {{app_runtime}}` — with the measurement in its own header: `has_table_privilege(app_runtime,'app.notes','SELECT')` → **true**, `SET ROLE app_runtime; SELECT * FROM app.notes` → **denied**, *"THE SCHEMA REVOKE IS THE ONE THAT HOLDS."* **The lint is correct and the release's own example is what misleads.** The one line would have widened a security boundary to match a grant that grants nothing. ADR **0211** is the decision. |
| **D1274** (D1416) | *"Studio's capability view shows the checkout's lock, never the plane's … Ask the deployment, as `list_resources` already does"* | `src/agentic_postgres/studio.py:464` decides it under ADR 0195: no request Studio makes confirms the lock, so *"gating it on one would report a REST document's staleness as though it were the lock's, and that is ADR 0195's folded third outcome"* — and `CAPABILITIES_NOTE` travels with the payload so the caveat cannot come apart from the data. The closing act would have undone a recorded decision. |
| **D1045** (D1426) | *"`ControlPlane._call` discards a provider body that said *identity limit reached* — a security judgement thrown away in a credential path"* — closing act *"Report the body, or say why not"* | `sed -n '370,373p' bin/bootstrap-providers.py` **says why not, at the discard**: *"The body is not included: on identity endpoints it can echo the request, and this message reaches a log."* That is §6's own non-negotiable. The status is reported. **This is the row most likely to be "fixed" into a secret in a log.** The residue is the silence — an operator cannot tell *the provider explained itself and we refused to repeat it* from *the provider said nothing* — and that is one clause, in Run 4, printing no body. |

### The other eleven, each with its command

| Row | Struck because | Shown by |
|---|---|---|
| `requirements-dev.in` **pins nothing** (D1407) | It pins **twenty-one** packages with `==`, and the six it leaves floating are a recorded decision with its reason in the file | `grep -c '==' requirements-dev.in` |
| The completion script is bash's (D1408) | The stated decision the row offers as an alternative is already in the command's own help and in its refusal | `bin/apg.sh completion --help`, and `bin/completion.sh:52,127` |
| No Python client (D1409) | *"a stated decision not to"* exists verbatim, on the page the row's subject documents | `docs/generated-clients.md` §7 |
| `MAX_SERIALIZED_BYTES` chosen not measured (D1410) | The code says *"1 MiB, chosen not measured, and said so where it is defined"* at the constant, and the capability schema carries the usage measurements | `services/auth-api/app/mcp_tools.py:125-137` |
| F-012's refusal (D1412) | It is a **record, not a guard**, since ADR 0206 — *"This no longer prevents anything the cluster would refuse"* — so the decision is about who writes a record, not about relaxing safety | `src/agentic_postgres/migrations.py::_assert_follows_release_version` |
| `mcp_tracing.configure()` has no caller (D1413) | True of `configure()` and **false of the module**: `span()` is called on every tool call, so the plane emits spans into an unconfigured tracer. Deleting it removes working instrumentation | `services/auth-api/app/mcp_tools.py:55,773` |
| Session 9's proofs read `"error"` and not `isError` (D1414) | The **refusal** assertions already read both, at six sites. Four **success** assertions do not, and that is the direction that is silently green | `grep -n isError tests/deployment/test_session9_agent_writes.py` |
| D340 (D1415) | A passing test asserts the current state, so closing it inverts one — which `CLAUDE.md` §6 permits only with an ADR | `test_the_maintenance_database_is_reachable_by_every_service_role` |
| The apt pin expires (D1417) | Accepted, stated, diarised **at the pin**, and it fails closed at exit 100. D99's rolling minor tag is the genuinely silent one and is a different row | `versions.in.yaml`, ADR 0144, D533 |
| F-026's interpreter check (D1418) | Adding it to `bin/doctor.sh --project` crosses ADR 0158's mode split, whose own comment says *"The split is what keeps the bare `python` below correct"* | `sed -n '1,20p' bin/doctor.sh` |
| D1203 and D930 (D1420) | Both are priced by this ledger itself as a later session's — one needs a snapshot version, the other an outputs-schema move and a migrator. Session 28 takes the **premise assertions** instead, so the day either premise stops holding it is loud rather than quiet | §12 and §14 above |

### What Run 1 found that the audit does not say

| Found | Position |
|---|---|
| **`render-jwks`'s closing act would have removed a deliberate property** (D1427) | The audit says *"compare the key set, not the file."* `write()` byte-compares **because** the file's mtime is the only signal a reader has that a rotation happened — its docstring says so. The defect is that `main()` reads a two-valued answer (*did I touch the file*) as an answer to a three-valued question (*did the key set move*), and a render publishes into a directory that has just been created, so `changed` is True with no key having moved. The repair is ADR 0195's third outcome **in the caller**. It matters because the next session performs a cutover and this is the sentence read during it. |
| **`apg-diag`'s three absent services are the three that handle a credential** (D1428) | `readonly SERVICES="postgres pgbouncer postgrest docs edge-probe dbmate"`. `auth` signs, `storage` presigns, `mcp` is the agent plane. The file explains every other thing it withholds and says nothing about these, so **a reader cannot tell a decision from an omission** — and the audit's *"widen the allowlist"* assumes the second. Left open with the ambiguity named. |
| **The audit's D1276 row is two findings** (D1429) | D1276 is the CI fixture that assumed a published loopback port; it is repaired, and its mechanism is explicitly unestablished and reported rather than resolved (ADR 0195). *"Studio has no live half for the query view's RLS"* is a separate, unnumbered finding and is the half with work in it. A repaired row and an open row sharing a number is how the repaired one gets re-repaired. |
| **D297's deferral was written as a *when* and has been read as a *whether*** (D1430) | Session 6 deferred the environment-versus-lock check because *"adding one in the run that is about to collect evidence is how a gate change gets attributed to the evidence."* That is a rule about timing. Nothing re-read it for twenty-two sessions, and the thing it deferred has killed a gate in collection three times (D297, D384, Session 6's host gate). Session 28 takes it in the run that collects no evidence. |
| **D201's half of the same row carries a constraint the row drops** (D1431) | Resolving a `packages:` entry against its registry needs a network in a check built to have none. *"Verify both"* prices two rows as one act; one is a gate step and the other is a decision about what the version lock is for. |
| **A secret generation is a provider write, not a migration** (D1432) | It sits beside `agent_audit` in the audit's table, closed with the same three words. `agent_audit` is a table this repository's migrations create; a generation is `{SECRET_ROOT}/{project_key}/generations/{generation_id}` at the provider, and nothing in `src/` or `bin/` prunes one. **Not taken in the rotation's run either — which is the run that creates the next generations.** |
| **F-022's *47 failures and 49 errors* is not this tree's number** (D1433) | It is a reading of the adopter's fork on a host this project does not administer. Session 28 reproduces the fork from tag `1.0.0` — measured to carry no `projects/` at all — rather than carrying the arithmetic forward. D1389 is the precedent: a count copied from a brief aims the repair at the wrong thing. |

---

## 17. What Session 28's Runs 3 and 4 built, and what each one refused

Run 1 measured and Run 2 decided; these are the two runs that changed code.
Every row names the ADR or the divergence that authorised it, and every row
says what was **not** done, because in four of the six the obvious repair was
the wrong one.

| Built | What was refused, and why |
|---|---|
| **The declared ordering record** (ADR 0210, Run 3). `bin/migrate.sh --project <manifest> freeze-lock --follows <version>`, checked against the release's append-only manifest, with `follows_release_version_source` in the lock so a computed record is distinguishable from an asserted one. Project lock schema **2 → 3**. | **The refusal was not relaxed, removed or made advisory** — it is byte-for-byte what it was, and ADR 0206 had already declined to remove it. What moved is its *remedy*. And the example project's lock was moved to schema 3 **surgically rather than by re-freezing**: a re-freeze recomputes the record from the checkout in hand, which would have moved that set's `follows_release_version` by accident. |
| **The lint refusal that says why the copied grant is dead** (ADR 0211, Run 3). It names `0006`, states that the grant reaches nothing, and ends *"removing the line changes nothing your cluster does"*. | **`PROJECT_PLACEHOLDER_SOURCES` was not widened**, and F-013's own one-line repair is refused in writing. The detail is **keyed on the source**, so the other six forbidden placeholders get the message they always had — a sentence appended to every refusal is noise rather than an answer. |
| **Both commits in `upgrade check`** (D1423, Run 3). The one the deployed document records and the one this checkout is at, with `--deployed FILE` for a checkout. | **It was not a matter of printing a field the verb had.** A *rendered* document carries no `source_commit` at all; the field belongs to the **deployed** document, which this command never read. And `commits_agree` is `null` unless both sides were read: a checkout that is not a git working tree — a tarball fork, or anything unpacked from this product's own `git bundle` transport — says so rather than reading as agreement. |
| **The host interpreter, stated rather than checked** (D1418, D1441, Run 3). At `bin/doctor.sh`'s own split, where a reader asking *does this check the host's interpreter?* looks. | **No check was added.** ADR 0158's split admits no third reading: the host's interpreter is a property of the machine and of no project, and putting it in deployed mode returns a bare `python` resolution to `sudo`, which is the failure the split exists to prevent. No session has measured which interpreter versions a host requires — `.python-version` is the workstation pin — so a check on that footing could fail a host that works. **No requirement and no claim.** |
| **`render-jwks`'s three readings** (D1374, D1427, Run 4). *wrote* against a copy that was here, *confirmed* one byte-identical, or *published* with no previous copy and therefore no answer — and only the first carries the recreate sentence. | **`write()` was not touched.** The audit asks for the key set to be compared instead of the file, and that destroys the property `write()`'s own docstring protects: the file's mtime is the only signal a reader has that a rotation happened. The third outcome names the reading that does answer — `rotate-signing-key.sh … acknowledge` — rather than reporting nothing. **It landed before the cutover**, because step 2 of the rotation is where this sentence is read for a decision. |
| **The provider refusal's clause** (D1045, D1426, Run 4). Whether the provider explained itself, read from `Content-Length`. | **No body, in any arm**, and the proof asserts that on all three. The clause itself has **three** answers rather than two: a response that declares no `Content-Length` is chunked or omitted it, and the only way to find out would be to read the body — which is the thing the clause exists not to do. Folding that into *nothing was sent* is the reassuring direction (D930, D957). |
| **The served document waits like its neighbours** (D387, Run 4). `observe_served_document` returns a reading rather than `None`, and the deploy wraps it in `await_observation` as it already does for tls, health, docs, app and storage. | **Only the state that can change is waited on.** A documentation token that cannot be minted is terminal — retrying it would spend ninety seconds on a deterministic failure and print the same line thirty times — so it is `settled` immediately. The two failures are reported separately, because *the service cannot serve its document* and *the edge had not finished attaching* send an operator to different places. |
| **`mcp_tracing.configure()`'s decision, written down** (D1413, D1444, Run 4). At the function, where a reader reaching for `git rm` is, with a test that goes red if a caller appears or if `span`'s caller disappears. | **Neither a caller nor a deletion — and the reason recorded in this document was wrong.** *"Scraping a project's services must answer the network question first"* is about a collector reaching a service; this is a **push**. Measured: `mcp` is on `internal` and `edge`, the collector is on `edge`, `edge` is per project (`apg-<key>-edge`), and the exporter package is already a pinned build argument on the service. Nothing about the network blocks a caller. What is actually undecided is whether this deployment should emit spans at all: a caller starts a new outbound flow from the container that handles a caller's credential, and the attribute set stops being an internal enumeration and becomes a published surface. That is Stage 4's. |

---

## 18. What Session 28's Run 6 decided, and the row it split in two

**One released migration, `20260917120033`, and it is the only schema this
session moves.** ADR 0213 is the decision; `docs/plans/session-28-implementation-
plan.md` §5 Run 6 is the record, and D1457–D1462 are in its §1.

| Row | Closed how |
|---|---|
| **`agent_audit` grows without bound** (D1255) | **Closed.** `app_private.agent_audit_prune(p_before, p_limit)` deletes rows older than a horizon the OPERATOR states and returns how many, **granted to nobody**: the object owner and a superuser can execute it and no request role can reach it. Measured in rig 28b before it was written — the ACL on the table is already the owner's alone and a `DELETE` by `SET ROLE` into `auth_service`, `agent_writer`, `agent_reader` and `authenticated` is refused in all four — so granting to nobody **preserves the posture rather than narrowing it**. Nothing deletes a row on a schedule, and a proof scans `src/`, `bin/`, `services/` and the templates for a caller so that stays true. |
| **`agent_idempotency` grows without bound** (D1255, D1460) | **Closed WITH A CONSEQUENCE STATED, and it is a different row from the one above.** Pruning a claim **re-arms its key**: measured in rig 28b with the control in the same run, a write replayed while its claim is present is deduplicated and `app.notes` stays at one row, and the same write replayed after the claim is deleted writes a SECOND row and reports success — no error on either side. At-most-once now holds for **whatever window the operator keeps**, where before it was forever by accident rather than by choice. **There is no safe subset**: `auth_rotate_agent_secret` (0025) returns a revoked agent to `active` with the same id, so a revoked agent's keys are dormant and not dead. `agent_idempotency_prune` exists so an operator who has decided to accept that can perform it in one statement that says what it did. |
| **The growth is visible** | `sudo bin/doctor.sh --project <key>` gains an **eleventh** check: the two counts and the date the record starts, with **no threshold** (D1462). Nobody has measured a row count at which a deployment is unwell, and D1441 — three runs earlier, in this same command — is the argument against inventing one. It reads the two TABLES and not the migration's functions, so the count follows the **checkout**: a 1.7.0 checkout reads eleven against a deployment at any release. |
| **A pruned row leaves no record that it was pruned** | **Stated, not built.** The audit table cannot record its own pruning: `source` is `agent_plane` or `database` and `agent_id` and `owner_id` are `NOT NULL`, so a row describing an operator's act would name a principal that does not exist. The function returns the count and the operator writes it down; making the prune auditable is a second table and a second decision. |
| **A secret generation is still open** (D1432) | Unchanged, and it never belonged in this row. Pruning one is a write at the **provider**, on the surface whose rule is that no command in this product sets a provider value by itself (D249), and **it is not taken in the rotation's run either** — which is the run that creates the next generations. |

### What Run 6 found on the way in

| Found | Position |
|---|---|
| **Four proofs still asserted the ordering space ADR 0206 replaced** (D1457) | *"Each set is then ordered against its own applied set only"* is the ADR; `_assert_follows_release_version`'s own docstring calls what survives *"a record, not a guard"*. Four proofs were still enforcing one ascending list across both sets — **the rule whose collapse took beta's deploy down at Session 24** (D1288). They were green because **no release added a migration between ADR 0206 and this run**: Sessions 25, 26 and 27 added none. All four now assert what ADR 0206 actually guarantees — each set ascending within itself, two roots, two subdirectories, two tables. |
| **`bin/doctor.sh` said seven live checks and `diagnose()` appended ten** (D1459) | Since Session 18, in the command's own header and usage, while `docs/operator-guide.md` said *ten checks* on the page that quotes this command's `--help`. Repaired to eleven. **ADR 0158's table is left alone** — an ADR is a record of a decision at a date, and the count is not the decision it took; §15's D1441 row quotes the pre-repair text. |
| **The migration's own rationale was wrong in the direction that produces work** (D1461) | It said `p_limit` is the answer to the lock *instead of an index*, implying the bounded prune is cheaper. Measured: 20,004 rows over fourteen days, unbounded removed 9,921 in **141 ms**, bounded removed 500 in **147 ms**. `p_limit` bounds the rows one transaction holds locks on, not the clock. Corrected in the file that ships. |

---

## 19. What Session 28's Run 7 decided about the tag, and what it refused to decide

**One new operator command, `bin/release-reading.sh`, and no schema.** ADR 0214
is the decision; `docs/plans/session-28-implementation-plan.md` §5 Run 7 is the
record, and D1463–D1467 are in its §1.

| Row | Closed how |
|---|---|
| **A release's documentation lands one commit past its own tag** (D1033, D1388, the pair that cost `1.6.2`, and D1424) | **Closed as far as a checkout can close it, and the page says how far that is.** `bin/apg.sh release-reading` prints, at the moment the question is answerable, what the last tag carries against what the tree carries — including the two counts nobody reconstructs by hand: released migrations and ADRs, at the tag against the tree. **It is not an enforcement and ADR 0214 does not claim one.** Somebody can still cut a tag without running it, exactly as somebody could ignore the prose checklist; what changed is that the question now costs one command. |
| **Command, or checklist?** (D1424's open question) | **Both, and the split is decided by what is computable.** The command supplies every fact — a checklist cannot produce `32 -> 33`. The three questions it cannot answer are printed **by the command**, not kept on a page: a page can go stale, can be skipped by somebody who ran the command, and asks a person to gather the facts as well as judge them, which is the arrangement that failed at all five tags. |
| **Whether a tag is owed** | **Refused, and the refusal is the measurement** (D1464). Records-versus-release-bytes does not separate the two defects from the three ordinary cases: release bytes land within one to five commits of every tag, always, because the next session starts. Intent is not in the tree, and a verdict would be D1441's mistake one run later. `test_the_reading_prints_no_instruction_about_the_tag` is where the argument is kept. |
| **A test that reads the tags** | **Refused twice over.** ADR 0209's reason stands — a test runs inside a commit — and D1466 adds a second: two of CI's three jobs check out without tags, so the proof would be green by measuring nothing. The command's third outcome, `no_tags_in_this_clone`, exits **3** rather than reporting clean. |
| **Putting the reading in the gate** | **Refused on the same measurement** (D1467). The gate runs where the tags are not, so it would print *cannot be taken* on every CI run, and a line that is always the same is a line nobody reads. It is run by a person, at a session close, in a full clone. |

### What Run 7 corrected on the pages that asked for it

| Found | Position |
|---|---|
| **D1424 said the class had happened three times** | **Five of five** (D1463). Every tag on `main` has release bytes landing past it, and `1.0.0`'s next commit is a product repair in `bin/` rather than documentation — so the class is release bytes, not prose. |
| **The naive verdict fires on a third of the history** | 45 of the first 147 commits answer *already tagged, commits since* (D1465). It is the normal condition of a repository between releases, which is why the reading states it and never warns about it. |

---

## 20. What Session 28's Run 8 rehearsed, and what the rehearsal found out about the claim

**A rehearsal is supposed to decide nothing and this one wrote an ADR**, which
is the whole story of the run: executing the steps in order found a defect in
the step that guards the irreversible one. `docs/plans/session-28-implementation-
plan.md` §5 Run 8 is the record, **Appendix R** is Session 29's sheet,
`docs/operator-guide.md` §15 is the operator's copy, **ADR 0215** is the
decision, and D1468–D1478 are in the plan's §1.

| Row | Where it stands now |
|---|---|
| **The signing-key rotation has been built, tested offline and never performed** (D860) | **Still never performed** — this session takes no trip. What changed is that every step of it has now been *executed* at least once: rig 28d ran `bin/rotate-signing-key.sh` through `status`, `acknowledge`, `promote`, `retire` and `abandon`, in order, against three real containers holding a real key set published by `bin/render-jwks.py`, including the refusals. The two steps that touch the provider are the two that were not rehearsed, and the sheet says so on each. |
| **The rotation closes three `not_run` claims** | **It closes none of them on its own** (D1469), and that is the row's premise corrected rather than its work done. Between them the three claims need **four** rotations — the signing key, the authenticator password, the documentation Basic Auth password, and the application credential on both projects — and a claim is `not_run` unless every proof it lists ran and passed. The signing-key cutover moves exactly **one of nine** node ids. |
| **The three claims' proofs, run against the rig** | **Impossible, measured** (D1468): all nine are `live_host` and demand `APG_LIVE_HOST` and a deployed document; `--setup-plan` with nothing set skips all nine. A claim is measured in one environment and this one's is the host. |
| **The cutover's timing, never measured** (Tier 2) | Measured as a shape rather than as host numbers: every step is seconds, and the only thing that takes time is the deadline — `promote` plus **930 s** before `retire` is allowed. So the window is about sixteen minutes at its narrowest, twice. |
| **The step that guards the irreversible one could not tell what a verifier held** | **Found by the rehearsal, repaired under ADR 0215** (D1476). `acknowledge` read each verifier's key set with `docker cp`, which resolves the bind mount's SOURCE PATH: measured on a native `dockerd 27.5.1` with both controls in one run, after the atomic replace `render-jwks` performs it returns the **host's** new bytes while the process is still on the unlinked inode. `loaded_digest`'s own docstring and its own test said a command written that way *"would report every verifier as current no matter what it held"* — and it was written that way since Session 8, when ADR 0122 fixed readability on a distroless image and silently replaced what was being read. The reader is now `/proc/<pid>/root/<path>`, the container's own mount namespace; a pid of `0` is reported and never folded. |
| **D1374, `render-jwks` reporting a change it could not have seen** | **Read for a decision for the first time, and all three of its readings fired in one rig run**: `published` on a directory with no previous copy, `confirmed` on an unchanged re-render, `wrote … the key set CHANGED` when the prepared key joined the set. Run 4 built the three; Run 8 is the first caller that needed them. |

### What the rehearsal found that nobody was looking for

| Found | Position |
|---|---|
| **The signing-key proof is red between `promote` and `retire`, by design** (D1470) | It asserts the retired `kid` is absent from `verification_kids`, which is what `retire` does and what `promote` deliberately does not. A sweep taken in the overlap would report `SEC-BOOT-001` failed during the one window with an irreversible step in it. Never executed before; found by reading it rather than by running it at the wrong moment. |
| **The gate's own help says FOUR verifiers and the command acknowledges THREE** (D1472) | `auth` is the issuer, and ADR 0098 is titled *the issuer's published set is not the verifier's set*. `compose.yaml` mounts the rendered key set into three services. The sheet says three; the help's repair belongs to Run 9's gate. |
| **`down` and up may no longer be needed, and the instruction is three sessions older than the mechanism** (D1473) | D591's mount digests recreate exactly the services whose mounted content moved, and `jwks.json` is a bind mount of all three verifiers. **Not repaired** — the sheet keeps the step and adds a free reading before it, so a later session can retire it with evidence instead of with an argument. |
| **A redeploy between `promote` and the provider move restores the pre-promotion record** (D1474) | `active_kid` is re-derived from the key set file's first key on every deploy, while `retire_after` is carried forward. A code reading, not a measurement: it needs a deploy. One line in the sheet forbids it. |
| **`auth_jwt_signing_key` reads as replaceable** (D1471) | `bin/rotate-secret.sh` prints `ROTATES` for it beside the eighteen that genuinely are, and rig 28e measured what that path publishes: a set with **zero overlap** with the previous one, which is the gap ADR 0088 exists to close. Recorded, not repaired: the repair is a note field on a contract file. |

---

## 21. What Session 28 closed, what it left, and what Session 29 inherits

**Session 28 is an audit acted on.** `docs/pre-stage-4-audit.md` was its single
input; Run 1 re-measured all thirty-six Tier 1 rows against the tree in both
directions and found **fourteen already answered and three whose closing act
would have done damage as written**. `VERSION` moves to **1.7.0**,
`CURRENT_SESSION` to **28** — 26 and 27 registered nothing and are skipped the
way 19 is (D1063) — and **no tag is cut**. Sections 16 to 20 are the runs'
records; the plan's §1 carries **D1406–D1485**, eighty rows.

### What this session added to the registry

| Requirement | Claim | Mode | Where it stands at the close |
|---|---|---|---|
| `DX-FOLLOWS-001` — a project set's record of the release it was frozen against, and the flag that declares it (ADR 0210) | `project_set_release_record` | **offline**, declared | Reported by `bin/session-28-check.sh --mode offline`. Its operator surface had no proof at all until this run (D1480). |
| `AGT-RETAIN-001` — what the agent record keeps and for how long (ADR 0213) | `agent_record_retention` | **host** | **`not_run`, by design.** Migration `20260917120033` is in this release's set and nothing applies it here. Session 29 deploys, then sweeps. |
| `REL-READ-001` — the reading before a tag (ADR 0214) | `release_reading` | **offline**, declared | Reported by the offline half. Deliberately not in any gate (D1467). |

**No claim was added for the rotation**, although it is the session's headline
act, and D1469 is why that is not modesty: the three `not_run` claims it is
supposed to close need **four** rotations between them and the cutover moves one
of nine node ids. A claim about a rotation having been rehearsed is a claim
about the planning, which is what ADR 0163 refuses.

### The rows this session closed

| Row | How |
|---|---|
| **How a fork made before `projects/<slug>/` existed converts to it** — §15's first row, and the audit's on-ramp question | **Closed.** ADR 0212 decides that it converts by re-homing and that only a RECORD has to change; ADR 0210 gives the record (`follows_release_version_source`) and `bin/migrate.sh --project M freeze-lock --follows V` writes it; ADR 0211 makes the refusal an adopter meets say why the grant they copied is dead. `docs/on-ramp.md` is the procedure, and its step 7 says plainly which step a checkout cannot prove. **No applied migration is re-stamped and nothing here advises one** (D912). |
| **D1424 — nothing in the tree lists what is about to be tagged** | **Closed by ADR 0214 and `apg release-reading`**, which states the facts and names the judgement it cannot make. The verdict was refused on a measurement, not on taste: the records-vs-release-bytes discriminator was measured across all five tags and does not separate the two defective releases from the three ordinary ones. |
| **D1430 — the environment is not verified against the lock** | **Closed in Run 5.** Session 6 deferred it with a reason written as a *when*; it was read as a *whether* for twenty-two sessions and cost three gate runs. The check compares installed distributions against the lock's pins and fails with the install command. |
| **D1240's four modules outside every sweep** | **Closed in Run 5.** They collect 0 under no selector now. |
| **`agent_audit` and `agent_idempotency` grow without bound** | **Closed as a decision, not as a schedule** (ADR 0213). Two prune functions granted to NOBODY, a size reading granted to the record's existing reader, and a proof that nothing in this release calls either. The doctor's eleventh check reports the two counts and the date the record starts, with **no threshold** — D1441's argument, three runs earlier in the same command. |
| **The gate's help said four verifiers where the roster is three** (D1472) | **Closed in `bin/session-28-check.sh`**, with ADR 0098's reason written into the flag's help: `auth` is the issuer. |

### What it did NOT close, and the reason on each

| Row | Reason |
|---|---|
| **`documented_path` is `failed`** | **Left failed, deliberately.** The audit's own closing line is the rule: a session that repairs what the readers found and then declares victory without a THIRD reader has not closed it — it has gone back to the state where the status had never been emitted at all. This session did not re-run `dx-record check` against its own prose and call the result a walk. |
| **`bootstrap_identity`, `api_authorization`, `credential_rotation_planes`** | **Still `not_run`, and the premise is now correct.** Rehearsed end to end (§20); performed on nothing. Four rotations, nine node ids, all `live_host`. |
| **`replacement_host_restore`** | `not_run` by decision (D1028). Unchanged. |
| **The operator guide has not been read cold** | Unchanged, and no test reads prose for truth. The cold reading is a person's, and §20's rehearsal is the closest this session came to one — it read the pages by executing them. |
| **`--kit-dir` stays on `kit-2026-09-11`** | D1282, re-read and still true. `bin/session-28-check.sh`'s flag help says so and says why: REC-KIT-003's claim IS the version gap, and aiming the flag at the newest kit destroys the proof **without failing**. |
| **D1471, `auth_jwt_signing_key` reads as replaceable** | Recorded in §20, not repaired: the repair is a note field on a contract file and belongs with the rotation. |
| **D1473, the rotation's `down`/up may be three sessions stale** | Kept and turned into a free measurement on the trip, rather than removed on a code reading. |
| **D1485, a rig that deleted a render fixture the checkout already held** | Recorded this run. Two proofs in one module hard-fail on a missing render fixture while five skip on the same precondition. |

### What the gate found at the close, after every run had said Done

**Three defects, none of them from the run that was closing.** The first pass of
`bin/session-01-check.sh` on the bump commit came back `1 failed, 5999 passed`,
and the second pass — after the repairs — came back **exit 0, `6000 passed`**.
This is the argument for the gate in one paragraph: a targeted list derived from
a diff cannot see a caller the diff does not touch, and this project does not
read its CI verdict.

| Found | What it was |
|---|---|
| **D1486 — the fifth reader of a rule ADR 0206 replaced** | `test_dev_environment.py` still asserted one ascending list across **both** migration sets. Run 6's *Done* says D1457 found four such proofs and repaired all four; there were five, and the fifth reaches the rendered manifest through `apg dev` rather than through the render. **Red since `acb08e4`, Run 6's own commit** — the concatenation was ascending by accident until Run 6's own migration ended the accident. Repaired under ADR 0206: each set ascending within itself, one directory per set, the release's set before any project's. |
| **D1487 — D1373's repair never reached the third mode** | `--mode offline` exited **1** with the JUnit written and **no evidence half**. Session 25 repaired the failing-suite path in both live modes and left the offline one under `set -e`. Session 28's only half is the offline one, so this would have closed the first entirely-offline session with no evidence document at all. **And the guard against exactly this checked two of the three callers**, pinning the count at 2 so that repairing the third went red — a test whose docstring warns about repairing one caller and leaving the other. It is derived now, not listed. `bin/session-25-check.sh` is **not** edited: it owns its session and its evidence is written. |
| **D1488 — the derivation lost a half of its prose, for the third time** | `bin/session-28-check.sh`'s header carries the warning (D853, D858) and scopes itself to the header and the usage block; two comments in the **body** survived naming Session 25's claims under this session's count. A rule that names the two places it applies to becomes a rule about those two places. |

### What Session 29 inherits, in order

1. **Deploy this commit**, both projects, `--through-session 28`. It applies
   `20260917120033` — the first ledger move in four sessions.
2. **Then sweep.** `bin/session-28-check.sh --mode host` and `--mode external`,
   merged with the offline half this session wrote. `stage_release` goes green
   because the trip deployed before it swept, which ends **D1401's third and
   last occurrence** — the arrangement is the point (D1425).
3. **Then take the reading and cut `1.7.0`** on the commit that was deployed.
   `apg release-reading` is what to run first, and its third question —
   *is a tag being cut on this commit?* — is the one this session answered *no*.
4. **The rotation, if the operator wants it**, from the plan's **Appendix R** and
   `docs/operator-guide.md` §15. Its pre-flight is `sudo docker inspect -f
   '{{.State.Pid}}' <container>` printing a non-zero number **before** the
   window opens (D1477). If it is performed, the sweep goes **after** step 7
   (D1470).

**The one thing this session must not be read as having done is tagging.** It
did not, and the tree between this commit and Session 29's tag is a release that
exists and is not yet promised to anybody.

---

## 22. What Session 29 closed, what it left, and what Stage 4 inherits

**Session 29 was the trip, and it is the first session in this repository's
history where the deployment, the evidence and the tag all name one commit.**
`8c61309b6cf9`, tagged **1.7.0**. Nine runs, `D1489`–`D1513`, **twenty-five
divergence rows of which sixteen were written by executing the plan rather than
by writing it.**

### What it closed

| Row | How |
|---|---|
| **D1401** — the tree two versions ahead of the deployment | **Closed, and structurally.** Deploy, sweep, tag, in that order (D1425). `stage_release` passed. There is no fourth occurrence available. |
| **D1189** — beta never got the grant repair `20260914120002` | **Closed by reading the ledger** (D941), not the document: `[X] 20260914120002_agent_grants.sql`, `Applied: 2, Pending: 0`. True when Session 22 wrote it, closed by ADR 0206's ledger move at Session 24's trip, unread for five sessions (D1489). |
| The host is `DEGRADED` and it was **never investigated** | **Closed as an answer, not a repair** (D1503): `cloud-init-hotplugd.service` fails **at every boot**, 2 min 42 s after `btime`, on a NIC hotplug event cloud-init cannot find in its refreshed metadata. It is the provider's, not this product's, and both projects doctor clean with it failed. |
| The kernel restart and `--after-reboot` have **never happened** | **Both done** (D1500). `7.0.0-29` → **`7.0.0-31`**, a two-release hop skipping 30, plus `libc6`. Forty days of uptime ended in **eight seconds** of downtime, both projects came back by themselves, and `--after-reboot` was declared to the sweep. **`port_allocation` passed for the first time in twelve sessions.** |
| `agent_audit` and `agent_idempotency` grow without bound | **Closed as a decision, now applied.** `20260917120033` is on both clusters; `agent_record_retention` **passed**; the doctor's eleventh check took its first live reading anywhere — alpha **1598 audit rows since 2026-08-22, 258 idempotency claims**; beta **26 since 2026-09-11, 0**. No threshold, by design (D1441). |
| **D688** — the IPv6 scan has nothing to scan | **Confirmed rather than closed**: `host.yaml` declares `expected_public_ipv6: null`, and the external half skips 8 proofs naming `APG_PUBLIC_IPV6`. A skip that is declared is not a gap. |

### What it left, and why

| Row | Why it is still open |
|---|---|
| **D860** — the signing-key rotation | **Not performed, and the audit's reason for performing it was wrong.** The audit prices it as closing `bootstrap_identity`, `api_authorization` and `credential_rotation_planes`; D1469 measured that those three need **four** rotations between them and the cutover moves **one of nine** node ids, so it closes **none** on its own (D1496). What this trip did buy: **ADR 0215's reader is usable on this host** — all ten alpha containers report a non-zero pid, which Session 28 could not verify because Docker Desktop reports 0 (D1477). The pre-flight is discharged; the sitting is not. |
| **D1375** — `op` cannot reach the Docker socket | **Unchanged deliberately** (D1493). Docker group membership is root-equivalent on production. The consequence is that the host produces no offline half, and the one merged is the workstation's. |
| `documented_path` | **`failed`, and deliberately not `not_run`.** The record of the last walk was **declared** rather than withheld, so the claim reports what was measured. Its message is the finding: step 11's compile line uses `>`, which truncates the contract before the command refuses, leaving a 0-byte JSON that makes the next documented command die in an unhandled `JSONDecodeError`. |
| `deployment_convergence`, `replacement_host_restore` | `not_run` for want of `--redeploy-before-file`, and by standing decision (D1028). |
| The B2 mirror | **Failed on both projects since 2026-09-18 04:38** (D1512). The R2 primary is healthy with a proven-recoverable point from 03:32. The guide's own table puts this in *note it and proceed*. |

### What Stage 4 inherits, in order

1. **A guard, not a sentence** (D1504, D1505). `deploy.sh:260` refuses a
   stdin-at-a-terminal-with-redirected-output invocation; **fourteen callers
   reach a container the same way and none of the other thirteen has it**, and
   there is no shared helper for one to live in. This session proved the cost
   twice — once on a read that hung for seven minutes, and once **twenty-five
   minutes after committing the row about it**. A rule that has to be remembered
   is not a control.
2. **`apg release-reading --ref`** (D1513). The one command written to be run
   *before a tag* reads `HEAD`, and D1425 puts the tag on the deployed commit,
   which is behind `HEAD` on every trip that records itself.
3. **A third reader for the documented path.** Two models have walked it; a
   person has not, and no test reads prose for truth.
4. **A lint rule for a local shadowing a module-level function.** D1509 cost a
   claim; the same module still binds a second `refused` that has not been bitten.
5. **The rotation as its own sitting**, from Appendix R and
   `docs/operator-guide.md` §15 — with the knowledge that it closes no claim by
   itself, so it should be planned for what it actually is.


## 23. What Session 30 closed, what it left, and what Session 31 inherits

**Session 30 is the first session in this repository's history to deploy a
release and then perform a credential rotation on it.** Nine runs,
`D1537`–`D1581`, **forty-five divergence rows of which thirty-three were
written by executing the plan rather than by writing it** — the highest ratio
any session has recorded, and the reason is that Runs 7 and 8 were both live.
`1.8.0` is deployed, swept and tagged at one commit, `be987cf` (D1425), and
both projects sign with a key that did not exist that morning.

### What it closed

| Row | How |
|---|---|
| **D860** — the signing-key rotation has never been performed | **Closed as an act**, 2026-09-19, on **both** projects, after being declined at five trips and rehearsed once offline. alpha `w4OqVzyJ…` → `snuFu_ZGOVAe…`, beta `IlFWmP6x…` → `U6fUwgg1hMOa…`; `GET <app route>/auth/jwks.json` returns **one key, the new one**, on each, read from off the host with no root. It closes **no claim** (D1469) and it moves **one node id of nine**, which no sweep has yet taken. |
| **D1504 / D1505** — D972's guard exists on one of fourteen callers | **Closed, and by measurement rather than by a list** (ADR 0218). Rig 30a2 isolated the class to one variable — *a child that reads stdin, handed a terminal* — so the repair is `container_exec`, one helper that closes stdin, plus `bin/lib/tty-guard.sh` sourced by `deploy.sh` as a belt. An AST scan over `bin/` and `src/` read **14 unguarded sites before and 0 after**, and that scan *is* the guard. Five of the fourteen were files no plan had named, including `rotate-signing-key.py` — the command Run 8 then ran against production. |
| **D1512** — the B2 mirror has failed on both projects since 04:38 | **Closed as an answer** (D1546, ADR 0220). It is a **fourth outcome**, and the plan's three and D1512's own `exit-code` both stopped one frame short of it: **the copy succeeds and the verb still exits 5.** One object per pass, always a small `.gz`, `ContentLength=<n> with Body length 0` reading from R2, ~1 in 3,700. Three files stated D1001 — *a pass may exit non-zero with objects behind* — as the design while `backup.py` treated exactly that as a hard failure. The verb now reports complete, partial and failed, and retries in-process. |
| **D1513** — `release-reading` reads `HEAD` and takes no ref | **Closed** (ADR 0219). `--ref`, with `VERSION` read from the ref rather than from the working tree — a `--ref` that kept the working-tree read would be right on every occasion except the one the option exists for. Its first real use was Run 7's tag: the deployed commit prices **16** commits since 1.7.0 where `HEAD` prices 18. |
| **D1359** — the documented compile line truncates its target | **Closed.** `mcp-contract compile --output PATH` refuses *before* it writes: exit 5, `PATH` absent, no temporary left behind. The same refusal under the old `>` shape truncated an 18-byte contract to **0 bytes**, which is what made the next documented command die in an unhandled `JSONDecodeError`. |
| **D1509** — a lint for a local shadowing a module-level function | **Closed, and the count was five, not one** (D1552). Of a raw scan's fifty, forty-five shadow a *fixture* and are not the class. All five renamed; the guard asserts **zero with no exemption list**. |
| **D1236 / D1543** — a `studio_*` proof errors at setup and belongs to no claim | **Closed as a registration, which is not the same as a green claim.** `STU-QUERY-002` is registered, the proof executed on the trip for the first time anywhere, and it reports **`failed`**. Before this session three Studio claims read `passed` while it had never run. **It reports now, which is what registering it was for** (D1572). |
| `deployment_convergence` — `not_run` since **Session 11** | **Closed: `passed`.** `--redeploy-before-file` was declared on a trip for the first time, and one deploy answered both halves — the sentinel row written through `api.create_note` survived, and the secret generation moved `59ce4a78cafc3be6` → `c18ea3c95b89521f`, which is the control that stops a no-op deploy passing. |
| **D1536** — stale counts in the isolation page and the envelope | **Closed, and the row was wrong in both terms** (D1557). Both *31 released* occurrences are measurement **conditions**, not claims about today, and rewriting them would have stated that a measurement was taken against a tree it was not; the envelope is **generated** and the edit the row implied would have been undone by the next render. The isolation sentence was wrong in both halves — **18** pointers, not fifteen, and **14** roles, not thirteen — and `evidence.py`'s own docstring carried the stale thirteen. |
| **D1084** — the public-endpoint decision · **the template-or-control-plane question** | **Decided, not built** (ADR 0216, ADR 0217). No public Postgres endpoint in Stage 4; `publication()` stays a refusal, and the five preconditions a Stage 5 reading would pay are written down. Nothing built in Sessions 31–35 may require a hosted trust model to be safe. |

### What it left, and why

| Row | Why it is still open |
|---|---|
| `studio_tenant_read` | **`failed`, and the product is right.** The fixture creates its subjects as `project_admin` and then writes through an API only `authenticated` may write to, one layer below the error Run 5 repaired. The instrument is wrong; **Session 31 repairs it** (D1572). |
| `documented_path` | **`failed` by decision**, until a person walks the path. Both of the repairs the second walk found — the compile line and the guide's own gaps — are now made, and neither changes the verdict: only a third reader does. |
| `port_allocation` | **`not_run` again, and it is a choice** (D1568). `--after-reboot` is a *declaration that a reboot happened*; this trip performed none, so the claim is reported `not_run` rather than kept green by a declaration that is no longer true. |
| `bootstrap_identity`, `api_authorization`, `credential_rotation_planes` | **`not_run`, with the rotation performed.** They need **four** rotations between them; this was one, and it moves one node id of nine. The other three — the authenticator password, the documentation Basic Auth password, and the application credential on both projects — are each a provider replacement plus a redeploy, and each is its own sheet. |
| `replacement_host_restore` | `not_run` by standing decision (D1028). |
| **D1375** — `op` cannot reach the Docker socket | Unchanged deliberately. The host still writes no offline half; the one merged is the workstation's, and Run 7's had to be **re-taken rather than reused**, because the 01:30 half came from a checkout two commits before `mirror_retry` was registered. |
| **The 22 orphaned deployment proofs** | Frozen in `KNOWN_UNREGISTERED`, which is compared for **equality**, so a proof that stops being an orphan must leave the tuple. Several are security proofs — the firewall, sshd's limits, four project-isolation proofs. They are frozen rather than registered in a hurry: **a requirement written to make a list shorter is a requirement nobody reviewed.** |
| **An operator can write a sentinel row and cannot remove one** | D1547, half-answered. `dev-token.sh --role authenticated -- api.sh create-note` writes it through the product's own surface; there is no `delete-note`, and a human may not run SQL through a product surface, so the cleanup is a root `docker exec … psql -c DELETE` typed by a person on a production cluster. A trip that re-takes `deployment_convergence` every time leaves a row behind every time. |
| **The mirror's per-pass transport flake** | Upstream, and no repair here removes it (D1546, D1566). ADR 0220's retry makes the verb *report* it correctly; nobody has asked Cloudflare or Backblaze which side truncates. Tomorrow's 04:42/04:48 passes are the first to run the retry on `1.8.0`. |

### What Session 31 inherits, in order

1. **A refusal that cannot fire for the reason it is watching for** (D1580).
   `retire`'s early-refusal branch — the one whose docstring says *refusing
   early is the half that matters* — is **unreachable on the only path an
   operator can walk**. Step 6's mandatory deploy rewrites the `jwt` member
   from the rendered key set, so `retire_after` is `None` before `retire` is
   called, and it refuses for the wrong reason. Measured on **both** projects.
   A rehearsal could not find it: rig 28d edited the document directly, and
   **the deploy is what overwrites it**. This is D509's shape in a credential
   path, and it needs an ADR before it needs code.
2. **The `studio_tenant_read` fixture** (D1572). The one instrument this
   session registered and did not repair.
3. **An operator-supplied PEM that nothing validates** (D1578). The product
   checks the delimiters of the key *it* generates and nothing checks the one a
   human pastes; `render-jwks` is where a bad one lands, mid-deploy, and it
   deliberately suppresses openssl's stderr because openssl names the key's
   path. On 2026-09-19 the value was malformed **four distinct ways in one day**
   and none was caught by anything but a script written during the window.
   A `value_kind: rsa_private_pem` checked at materialization is the repair;
   so is a `materialize-secrets` that can say *the name you typed is not a name
   I read* instead of `absent at the provider, and optional`.
4. **Why `auth` was recreated by Run 7's deploy and not by Run 8's**
   (D1581) — **UNDETERMINED, and recorded as such.** `mounted_paths_by_service`
   parses **one** rendered compose payload and the secret mounts live in
   another, so a new generation is invisible to the mount digest; that explains
   Run 8, where `auth` was not recreated on either project, and it contradicts
   D1571, written seven hours earlier off Run 7, where it was. One of the two
   readings has a cause nobody has established, and the row says so rather than
   folding it.
5. **The 22 orphans** (D1542), each named with the session that owes it.
6. **`agent_record` counts with no threshold** — the doctor's eleventh check
   reports and judges nothing by design (D1441). It is the number Session 31's
   `doctor capacity|usage` starts from.
7. **Two small stale facts found while reading.** The D587 comment at
   `runtime_override.py:42` lists **six** services as carrying
   `apg.project.key`; a `docker ps` filtered on that label returns **eight** on
   this host — `metrics` and `store` joined at Session 14 and the comment did
   not. And ADR 0162 prices no row for a command gaining an option (D1561) — `upgrade plan` read this release as
   `requires patch` while `VERSION` moved a minor, which is right about what
   the upgrade costs an operator and silent about what the release added.


## 24. What Session 31 closed, what it left, and what Session 32 inherits

**Session 31 is the session that taught this node it is finite.** Eight runs,
`D1582`–`D1644`, **sixty-two divergence rows of which forty-two were written by
executing the plan rather than by writing it**. `1.9.0` is deployed, swept,
merged and tagged at `4344a1f` (D1425, with D1641's one stated exception), and
the merged evidence reads **145 claims: 139 passed, 5 not_run, 1 failed** — ten
more claims than Session 30, and the ten new ones all passed.

**The sentence this session would most want carried forward: seven of its
defects were the instrument rather than the product**, and the product's own
refusals diagnosed two of them in one line each. Every one was a value that
looked measured and was not, and every one was caught by running the check
against the real thing instead of the expected thing.

### What it closed

| Row | How |
|---|---|
| **D1580** — `retire`'s early refusal cannot fire on the only path an operator can walk | **Closed** (ADR 0224). The overlap window is closed by the step-six deploy, not by `retire`, and `retire_rotation` gained a third outcome so the state *no rotation is in flight* is distinguished from *a rotation is in flight and not ready*. `rotate-signing-key.sh` no longer writes when nothing changed. |
| **D1578** — nothing validates an operator-supplied PEM | **Closed** (ADR 0225). `check_value_kind` runs at materialisation, before the value touches disk, and `bin/materialize-secrets.py` deletes the value and exits on a refusal. **The ADR's own claim was then measured FALSE and corrected**: *catches every malformation actually observed* caught one of four, and strengthening it to require RFC 7468 boundaries on lines of their own brought it to two — the other two are named as out of reach rather than implied to be covered (D1618). |
| **D1572** — the `studio_tenant_read` fixture | **Closed, and not the way Run 5 closed it.** Run 5 moved the auditor's role from `project_admin` to `authenticated` on the grants reading, which was right about the grants and unaware of the ceiling: the auth service validates a stored record's scopes against `permitted_scopes(role)` before signing and **refuses rather than truncating**, and `project_admin` is the only role of six whose ceiling carries the three admin scopes. All three Studio proofs then errored at setup on the trip. **The subject is split in two** — an administrative `auditor` and a tenant `note_owner`, with two Studio launches, because Studio takes its subject once at start-up and forwards that token for the process's life (D1638). `studio_tenant_read` **passes**, which it had never done anywhere. |
| **D1542** — 22 orphaned deployment proofs | **Triaged, not emptied.** Ten requirements registered with their own claims; twenty orphan node ids attached to requirements that already existed, which makes those requirements stricter and moves no count. `KNOWN_UNREGISTERED` shrank by exactly what was registered and by nothing else — **a requirement written to make a list shorter is a requirement nobody reviewed.** |
| **D1595** — five stale statements in the tree's own prose | **Closed, including the fifth, which was a measurement rather than an edit.** `APG_ADMIN_PASSWORD_FILE` was exported by the gate and absent from the closed roster; the grep said which fixture consumes it and the row says which. |
| `deployment_convergence` | **Passed again**, a second trip running, with `--redeploy-before-file` declared. |
| **The collector, unconsumed since Session 14** | **Closed** (ADR 0223). `telemetry_read` passed on the trip: **the project's own Prometheus answered on production for the first time in this product's life**, and every series it returned named its project. |
| **Nothing set `pids_limit` or `cpus`, and host RAM was never read** | **Both closed** (ADR 0221, 0222). Twenty service definitions carry `pids_limit` and nine carry `cpus`; `host.yaml` declares the machine at schema 3 and admission charges every deploy against it. |

### What it left, and why

| Row | Why it is still open |
|---|---|
| **D1636** — `ceilings` excludes the database and under-reports by the largest cap on the host | **Reported and deliberately not repaired mid-trip.** Production reads **2,944 MiB** where the real sum is **4,480** against 3,814 MB of RAM, because `apg.project.key` is not applied to `postgres`, `pgbouncer` or `dbmate` (D587). The figure **decides nothing** — `decide` charges `unreclaimable_mb`, never the caps — but it under-reports in the **reassuring** direction, and D767's whole point is that the caps in aggregate already exceed the machine. The repair is to group by Compose's own labels, as `runtime_override` already does for the database selector. **This is Session 32's first item.** |
| **D1642** — a DR kit names the checkout's commit as its release | New, and harmless in this instance only because D1641 measured the deployable diff empty. `export` reads `release` from the tree it runs in and the deployed document beside it in the same kit names another; nothing compares them. Belongs to a session already in `dr-kit.py`. |
| **D1643** — `doctor usage` exits 6 on beta | **Not a defect, and recorded so nobody repairs it.** `tool_calls_total` has no series because no agent tool call has ever been made on beta, and `exit_code` returns 6 for `UNKNOWN` as well as `PROBLEM` because *a check that could not run is not a healthy check*. The product declined to fold *no series* into *zero calls* even though the audit table agreed the answer was zero. The default `doctor` is a separate verb and still reads 11 ok on both. |
| **D1547** — an operator can write a sentinel row and cannot remove one | **Still half-open, and it cost a root `psql` again this trip.** The removal is now a staged script that derives the container, the database and the title from the deployed document and the before-file rather than taking them typed, which removes the transcription risk but not the gap: `bin/api.sh`'s `OPERATIONS` is a closed set of six with no counterpart to `create-note`. A `delete_note` RPC is a migration plus an `api` contract move plus a client regeneration, and belongs to a session that moves that contract anyway. |
| **D1581** — why `auth` was recreated by one deploy and not another | Unchanged and still **UNDETERMINED**. The mount digest parses one compose payload and the secret mounts live in another. |
| `documented_path` | **`failed` by decision**, until a person walks the path. |
| `port_allocation` | **`not_run` by choice** for the second trip running (D1568). This trip performed no reboot, and `--after-reboot` is a declaration that one happened. |
| `bootstrap_identity`, `api_authorization`, `credential_rotation_planes` | `not_run`. They need four rotations between them; Session 30 performed one, and this session performed none. |
| `replacement_host_restore` | `not_run` by standing decision (D1028). |
| **D1375** — `op` cannot reach the Docker socket | Unchanged deliberately. The host writes no offline half; the merged one is the workstation's. |
| The mirror's per-pass transport flake | Upstream. ADR 0220's retry makes the verb report it correctly; nobody has asked which side truncates. |

### What Session 32 inherits, in order

1. **The worker is a seventh claimant, and it must be charged against a
   declared capacity** — which is why the stage plan ordered 31 before 32.
   That declaration now exists: `host.yaml` schema 3, admission at step 0, and
   a refusal at exit 12 that has fired on production against a real third
   project. **A worker that does not declare `unreclaimable_mb` is a worker
   admission cannot see.**
2. **D1636's label gap, first.** It is the third wrong reading D587 has
   produced and the first that is a capacity figure. Session 32 adds a
   long-running process to a host whose reported ceilings already understate
   the truth by 1,536 MiB; fixing the reading before adding the claimant is
   cheaper than explaining the number afterwards.
3. **`storage_cleanup.py`'s lease-based GC is the one pattern to copy**
   (unchanged from §23). There is still no worker, queue, outbox, scheduler or
   workflow.
4. **A worker holds nothing an agent identity does not hold** — the stage's
   sibling invariant, and the one D1638 just demonstrated has teeth: this
   product refuses to mint a token whose stored scopes exceed its role's
   ceiling, and it refuses at issuance rather than truncating. A worker
   identity will meet the same check, and **a worker that needs both
   administrative scopes and tenant grants cannot exist** any more than
   Session 24's auditor could.
5. **D1248's audit filters** remain Session 33's, for the provenance reader.

## 25. What Session 32 closed, what it left, and what Session 33 inherits

**Session 32 is the session that gave this product a worker, and the worker
holds nothing an agent identity does not hold.** Nine runs, `D1645`–`D1713`:
twenty-three rows written at planning and **forty-six written by executing
it**. `1.10.0` is deployed, swept, merged and tagged at `275a19e` (D1425, with
D1641's method stated in the tag for D1710), and the merged evidence reads
**158 claims: 152 passed, 5 not_run, 1 failed**. All thirteen claims the
session added passed, and the five host ones did so on their first execution
anywhere.

**The sentence this session would most want carried forward: the defect that
would have cost the trip was found by WRITING the proof, before the trip**
(D1696). The loop recorded the request id it sent; the agent plane mints its
own and ignores an inbound one (ADR 0160); so the live proof's join of step
to audit row would have returned nothing on production. Run 5's end-to-end
rig had passed because its plane was a fake that believed what the loop
believed. The trip then found the opposite case: one proof failed while the
product was right (D1710), because its fixture held a narrower definition of
*unbounded* than the reading did. Both are CLAUDE.md §7's question 6: who
wrote the fixture, and does it share a belief with the code?

### What it closed

| Row | How |
|---|---|
| **D1636** — `ceilings` excluded the database | **Closed on production.** The reading groups by `com.docker.compose.project` and reads **4,480 MiB across 2 projects, by compose project**, where 1.9.0 read 2,944. `ceilings_read` passed: for each project the figure equals the independent sum of its running containers' caps, the database's among them. |
| **D1516** — one durable substrate, not three | **Closed.** Migration 0034: `workflow_definition`, `workflow_run`, `workflow_step` and `workflow_worker` in `app_private`, no RLS and no request-role grant (D1647), reached only through nine definer functions. Sessions 33 and 34 build on it rather than beside it. |
| **D1521's first half** — the spec's Sessions 61–62 | **Closed, as far as the proofs reach**: versioned definitions compiled against the capability lock and installed by the deploy (ADR 0228); durable run and step state (ADR 0227); restart safety (`workflow_resume`, three `worker-restart` kills on production, a new holder in 7.5–8.8 s); retries with backoff (a step parked and resumed at attempt 2); an idempotency key per (run, step), never per attempt, so a replay after a crash writes ONE row (D1646); cancellation; step timeouts through the lease (D1687); revocation checked at the step boundary (`workflow_revocation`); every step correlated to the plane's own audit row by the plane's request id (D1696). **Not in this half**: approval gates, compensation, external-event waits, provenance. Those are D1521's second half. |
| **D1527** — `THR-WORKER` before code | **Closed.** The row is in `docs/threat-model.md` after `THR-NOISY-NEIGHBOUR`. |
| **D1529** — the restore-test row | **Closed.** The drill carries the runs by status, and `workflow_restore` passed: a restored cluster holds the runs the live one held at the target. |
| **The seventh claimant** (§24 item 1) | **Priced and found to be none** (D1653, ADR 0226). The worker is a loop inside the `auth` process: it uses the sixth claimant's pool, so `BUDGET_CLAIMANTS` is unchanged. On production the container reads **56 MiB against its 384 MiB cap**. |

### What it left, and why

| Row | Why it is still open |
|---|---|
| **D1707** — `migrate.sh … status` prints no ledger | **New, a product defect, recorded and left** (found on the trip; nothing deployable moves mid-trip). Since 1.8.0 dbmate's output goes through `container_exec.compose_run`, which always captures, and `run_dbmate` returns only the exit code, so the verb exits 0 having listed nothing. The doctor's `migrations` check and the deploy's ledger line are the readers meanwhile. Owed: the output printed, and a proof that the `[X]` lines appear. |
| **D1711** — no memory figure under a run | **Unmeasured, and listed in `capacity.UNMEASURED`.** ADR 0226's second flip criterion (an under-load delta of 96 MiB) was not read: every sweep recreates the services early, so the sampled container vanished, and the samples taken were of an idle loop. A later trip samples during the run proof, finding the container through `/proc/<pid>/mountinfo` as `op`. |
| **D1712** — `doctor usage` on beta still exits 6 | **The verdict is right and the wording is wrong.** Tool calls were made (100 audit rows), but each `mcp` process mints its own series (D1609), and the sweep recreated `mcp` after its last call. *"No such series **yet**"* asserts *never*; the truth is *none in this process*. D1643's premise, that it exits 6 until the first call, was too narrow. |
| **D1713** — the generation moves on every deploy, and something inside the sweep moves it again | **A lead on D1581, not an answer.** D1665 assumed a generation moves only on a rotation. Measured: alpha's moved `14f76e…` → `f9fc38…` at the deploy and → `9817eb…` during the first sweep, with no rotation. The same sweep recreated `auth` with no image change: the event D1581 needs, observed once. Which proof did it, and whether it was a deploy or a `down`/`up` (which would recreate everything regardless), is not identified. **D1581 stays UNDETERMINED.** |
| **D1705** — two behaviours of step 6d have no offline proof | *Nothing to install, saying which reason* and *an uninstallable definition refuses at exit 5*. Both were READ on the trip's transcripts (alpha's line, beta's two installs); neither is a proof. Owed by the next run in `bin/deploy-project.py`. |
| **D1704** — a revoked agent cannot read the run its revocation stopped | `authenticate_agent` refuses a non-active agent before the route runs. Whose read that is (the owner's? an operator's?) is the second principal's question. Session 33. |
| **D1700** — probe agents accumulate on beta | Four revoked agents and one subject nobody can log in as, per sweep: eight and two after this trip. They cannot be deleted while their runs reference them, and the runs are the substrate's record. A retention story for runs is owed before it matters. |
| **D1642** — a DR kit names the checkout's commit | Happened twice on this trip (`-pre` names `275a19e`, `-post` names `176a7f0`, while the documents inside name the deployments). Harmless both times because the deployable diff was measured empty; still unguarded in general. |
| **The edge's two containers are unbounded** | `docker-socket-proxy` and `traefik` set no `mem_limit` (D1710 found them). Outside every project's budget by design; noted for Session 35's hardening beside the edge's missing `pids_limit`/`cpus`. |
| **D1547** — the sentinel row is removed by a root `psql` | Unchanged: this session moved the `app` OpenAPI contract, not the `api` one, so `delete_note` is still nobody's. |
| `documented_path`, `port_allocation`, the rotation trio, `replacement_host_restore` | Unchanged and for the same reasons: a person's walk, no reboot, no rotations, D1028. |

### What Session 33 inherits, in order

1. **The substrate's API, by name**: `workflow_install_definition`,
   `workflow_enqueue`, `workflow_claim_step`, `workflow_finish_step`,
   `workflow_park`, `workflow_heartbeat`, `workflow_cancel`,
   `workflow_run_status`, `workflow_counts` — nine definer functions in
   `app_private`, eight granted to `auth_service` and the install to nobody.
   **An approval gate is built ON these, not beside them.**
2. **`approval_required` is still a terminal refusal**, and `validate` refuses
   a definition naming such a capability. Session 33 turns the refusal into a
   parked step resumed by an approval, under a scope the second principal
   holds.
3. **The `wait` step's park is already built**: `workflow_park` with no
   `resume_after`. Session 33 adds the step kind; Session 34 adds the event
   that resumes it.
4. **D1248's audit filters, for `apg workflow inspect`**: provenance from
   `agent_audit` by the plane's request id is the join the reader does not
   yet make. The correlation itself is proved on production (D1696).
5. **The second principal's scope**: it approves, it may not act. D1638 and
   D1704 are the two places this product has already met the question —
   a token whose stored scopes exceed its role's ceiling is refused at
   issuance, and a revoked agent cannot read its own stopped run.
