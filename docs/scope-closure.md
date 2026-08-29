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
| Requirements in the acceptance registry | **127** | 121 P0, 6 P1, **0 P2** |
| Claims in the evidence model | **60** | 56 of 57 passed at Session 11's close |
| Requirements a claim reports on | **90** | see §4 — this is the gap worth reading |
| Migrations released | **22** | fix-forward only |
| Architecture decisions recorded | **161** | |
| Divergences measured | **D1–D696** | |

---

## 2. P0 — one red, two awaiting a witness

**`bootstrap_identity` is the single red claim, and it is characterised rather
than open** (D683). The signing-key rotation **cannot be prepared**:
`MAX_VERIFICATION_KEYS` is 2, `build_jwks` refuses a third, and
`render-jwks.py` appends the bootstrap issuer's key **unconditionally** while
the auth key and the prepared key are each guarded by `is_file()`. The set has
been full since the auth service existed in Session 6. `retire` cannot free the
slot either — `retire_after` is `None` and it refuses with *"no rotation is in
flight."*

* **Effort to close:** one run. An ADR for the bootstrap-issuer retirement, a
  guarded omission in `render-jwks.py`, a deploy, and all four verifiers
  recreated afterwards (ADR 0088).
* **Risk of not closing it:** the signing key cannot be rotated. Nothing is
  currently compromised; the *response* to a compromise is unavailable.

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

## 4. The claim-coverage gap

**37 of 127 requirements belong to no claim.** They are tested — every one has
node ids, and those tests run and pass in the gate — but **no evidence document
reports them**. "56 of 57 claims passed" describes **90 requirements**, not 127.

They cluster by session, and that is the explanation: `CFG-001`–`CFG-016`,
`DX-002`, `DX-003`, the Session 2 security set (`SEC-NET-001`, `SEC-HOST-001`,
`SEC-TLS-001`, `SEC-LOG-001`, `SEC-DOCKER-001`, `SEC-NET-002`), `DEP-REL-001`,
`DEP-PROV-001`, `OPS-HEALTH-001`, four Session 3–4 database requirements, three
`SEC-DBX-*`, `AGT-DRIFT-001` and `DBX-004`. **The claim layer arrived after
Sessions 1–4 and their requirements were never retrofitted into it.**

**What this does and does not mean.** It does not mean 37 requirements are
unproved: their tests are in the suite and the suite is green. It means the
*evidence document* — the artefact that says what a release guarantees — is
silent about them, so a reader of `evidence/session-11.json` learns nothing about
whether a service port is publicly reachable (`SEC-NET-001`) even though five
tests answer it.

**Nothing detects this**, which is why it went eleven sessions. `CLAIMS` is
checked for claims naming unknown requirements; nothing checks for requirements
named by no claim.

* **Effort to close:** small, and it is bookkeeping rather than proof — group the
  37 into claims and extend the introduced-in table. **The risk is doing it
  carelessly**: a claim's session decides when it must first be proved, and
  D696 is the record of a Session 2 claim being accidentally moved to Session 12
  by a single line.
* **The guard worth writing first:** a test that every registered requirement
  belongs to exactly one claim. Without it the same gap reopens the next time a
  session adds a requirement in a hurry.

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
| **PGDG apt** — `pgbackrest=2.59.1-1.pgdg12+1` | exact version pin | **This one has an end date** (D533). PGDG drops superseded versions, so the pin will one day resolve to nothing and the image build fails closed. That is the accepted half — it is a pin, not a floating tag — but **nobody has diarised it**. |
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
