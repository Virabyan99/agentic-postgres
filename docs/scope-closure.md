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
| Requirements in the acceptance registry | **131** | 125 P0, 6 P1, **0 P2** — four `REL-*` added in Session 13 |
| Claims in the evidence model | **78** | 61 at Session 12's close; 13 retrofitted in Session 13 Run 6, 4 added in Run 7 |
| Requirements a claim reports on | **107** | was 90; see §4 — **the gap was repriced, not just narrowed** |
| Migrations released | **22** | fix-forward only |
| Architecture decisions recorded | **162** | 0162 is Session 13's |
| Divergences measured | **D1–D753** | D704–D718 are the Stage 2 audit; D719–D753 are Session 13 |

---

## 2. P0 — one unproved, two awaiting a witness

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

**`DEP-ISO-001` and `DEP-REMOVE-001` await one host trip.** Their proofs are
written and dry-run clean against both deployed documents.

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
