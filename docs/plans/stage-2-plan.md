# Stage 2 — plan of record

**This is a stage plan, not a session plan.** It sits above six session plans and
owns what all of them would otherwise repeat: where Stage 2 starts, what the
Stage 2 specification asks for that this repository already has, the four
decisions CLAUDE.md §4 requires a new body of work to settle, and the open items
carried in from twelve closed sessions.

**§1 is the point of this document.** The Stage 2 specification was written
against Stage 1's *specification*, not against Stage 1's *tree*. §1 is the list
of places where those differ, measured rather than recalled. It is why the answer
to *"twelve more sessions?"* is **six**.

**It builds nothing.** No requirement is registered here, no ADR is written here,
and no code changes because of it. Each of the six sessions gets its own plan,
and §11 says what shape those take.

---

## Status — read this first

```
STAGE 1 IS CLOSED.  evidence/session-12.json merged: 57 of 61 claims passed.
HEAD            89db7fb, local and origin/main identical. CLAUDE.md §2 names
                39d5d01 and is one commit stale (D718).
CURRENT_SESSION 12. Stage 2 numbers its releases 13-18 and does not renumber
                anything (D705).
template_version 0.1.0-dev, published in every rendered and deployed document,
                and never once bumped (D704).
outputs schema  v13.   ADRs 161, next free 0162.   migrations 22, released.
divergences     D704-D718 recorded here. **Next free: D719.**
```

**Four Stage 1 claims are unproved and three of them reappear inside the Stage 2
specification as sessions.** They are not Stage 2 work:

| Claim | What it needs | Where the spec puts it |
|---|---|---|
| `bootstrap_identity` | **Code** — the bootstrap-issuer retirement (D683) | one bullet inside its Session 16 |
| `fresh_host` | A host that starts empty | its Session 23 |
| `documented_path` | Somebody who did not build this, following the documentation | its whole Session 24 |
| `project_removal` | A project actually removed | its Sessions 17 and 21 |

**The last three are declarations, not work**, and each already has a written,
gated proof waiting for its evidence file. §4 says when they are arranged.

---

## 0. Where Stage 2 actually starts

Session 12 closed at `39d5d01` with 57 of 61 claims passed, 121 P0 requirements
and 6 P1 registered, two isolated projects live on `62.238.99.122`, 16
containers, backups healthy, and `doctor.sh` at 8 ok / 0 warning / 0 problem /
0 unknown. One commit has landed since — `89db7fb`, documentation.

**The numbers that shape Stage 2's plan, all measured this session:**

- **679 tracked files. 83,356 lines under `tests/`.** The proof apparatus is
  larger than the product, and it is the thing that scales with session count.
- **127 requirements across ten id families** — SEC 35, CFG 16, DBX 15, DEP 14,
  AGT 12, STO 11, API 10, DX 6, REC 5, OPS 3. **37 belong to no claim** (D697),
  which is bookkeeping the ledger already prices as small.
- **~25 operator verbs under `bin/`, essentially all of them with `--json`**, plus
  twelve `session-NN-check.sh` gates and seven `libexec/` launchers.
- **Four agent budgets already deployed** and independent by decision (ADR 0129).
- **Zero lines of OpenTelemetry, Prometheus or OTLP** anywhere in `services/`,
  `src/`, `bin/`, `requirements-dev.in` or `compose.yaml`.

**There is no Stage 2 runbook and no session summary.** What Stage 2 has is
`stage-2-consolidated-spec.md` (Version B+), a planning vision written before
Session 12's evidence existed, whose own §1.2 says nothing in it should be
started until that evidence is in hand. It now is. **So §1's job is the one
Session 9's plan named**: the list of places where the specification asks for
something this repository already has, or asks for it in a shape this repository
refuses. That list is longer than it looks, and it is what makes six sessions the
honest number rather than a schedule concession.

**One thing about the specification is right and load-bearing and this plan keeps
it whole**: Stage 2's differentiator is *governed agent access* — versioned,
budgeted, evaluable, revocable capability policy — and not generic PostgreSQL
hosting. Everything else in the roadmap is in service of being able to operate
several such deployments over time.

---

## 1. The divergence table

Six columns, the house shape. Rows are **measured facts about this repository as
it stands at `89db7fb`**, not predictions about the sessions.

**Next free number after this table is D719.**

| # | Spec says | Repository does | Decision | Why | ADR |
|---|---|---|---|---|---|
| **D704** | Session 13: *"Introduce semantic versions for: appliance template, manifest schema, capability bundle, API contract, evidence artifacts."* Read as new versioning machinery. | **A semver product version already exists and is already published.** `VERSION` holds `0.1.0-dev`; `template_version()` (`src/agentic_postgres/__init__.py:88`) reads it; it is written into `renderedDocument.template_version` **and** `deployedDocument.template_version` (`deployed_output.py:494`), carried across document migrations (`output_migrations.py:77`), and it is `pyproject.toml`'s version via `version = { file = "VERSION" }`. The manifest schema is versioned at **v13** with a **migrator across versions**; the capability bundle is hashed into the deployed document as `capability_contract_sha256` and `capability_lock_sha256`; the API contract is frozen under `contracts/` with canonical snapshots. **Four of the five already exist.** | **Session 13 does not introduce versioning. It starts bumping the version that exists** and attaches compatibility rules to it: `0.2.0` at its close, one minor per session, `1.0.0` at Session 18. | A second version axis beside one already published is two answers to *"what is deployed"* — **ADR 0002's rule at the release layer**, and the failure mode is the one this project keeps producing: a value that looks measured because it looks like the other one. What is genuinely missing is not a number; it is the **compatibility rules** that say which manifest, migration, contract, capability and secret-format changes a bump permits. | 0002 |
| **D705** | The specification throughout: a version is a semver, and Session 13 makes the platform version machine-readable. | **The session number is the release ordinal, and it is load-bearing in six places.** `CURRENT_SESSION = 12` (`__init__.py:74`); `deployedDocument.deployed_through_session`; `available_from_session` on every `endpoint` and `accessProfile` in the outputs schema; `target_session` on all 127 registry entries; `claim_session`, which decides **when a claim must first be proved** (D696); and one `session-NN-check.sh` gate per release. `deploy.sh --through-session N` refuses `N > CURRENT_SESSION` (D59). **The spec never names this axis.** | **Both axes are kept and they mean different things.** `template_version` is the product version an operator quotes; the session number is the internal release ordinal the evidence model is keyed to. **Stage 2 numbers its releases 13–18** and refactors neither. | Replacing the ordinal costs a whole session — outputs schema v14, `target_session` across 127 entries, the claims model, twelve gate scripts — and buys a number **already published under another name**. The cost the ordinal actually imposes is *one gate per release*, and the answer to that is **six releases instead of twelve**, not a rename. Moving `CURRENT_SESSION` stays all-or-nothing (D690): every requirement targeted at the new number activates in the same commit. | 0002, D59, D690 |
| **D706** | Session 14: *"Add OpenTelemetry propagation through Traefik, FastAPI, FastMCP…"*, thirteen required metrics, eight required alert rules, an evidence index, and telemetry redaction tests. | **The instrumentation half is genuinely absent** — `opentelemetry`, `prometheus` and `otlp` match nothing in `services/`, `src/`, `bin/`, `requirements-dev.in` or `compose.yaml`. **The correlation half and the redaction half are built and proved.** One request id spans ingress → FastMCP → PostgREST → `app_private.agent_audit.request_id` (migration 0022, `OPS-LOG-001`, Session 11), which is that session's *first* exit criterion. `mcp_telemetry.py` carries a documented forbidden list — no token, no URL, no object key, **no caller value** — with a canary scan behind it, which is its *third*. The evidence index exists as the registry plus `evidence/session-NN.json`. | **Session 14 keeps its whole scope** and is the one session in the spec's mandatory core that is genuinely empty. Its first and third exit criteria are **already met and it says so** rather than re-proving them. | This is where the specification is most right, and naming what exists is what protects the session's budget: it belongs to metrics and alert rules, not to re-deriving a correlation id that took Session 11 a migration and a host trip. **The alert half is the harder one**, and D555/D556 is why: three paths already carry the archiving signal and *by decision* none of them reaches a dashboard. | 0149, 0150 |
| **D707** | Session 15: *"Shell scripts… should no longer be the primary operator interface. A new developer should not need to invoke Docker Compose or internal scripts directly."* Seventeen `apg` verbs, with eight requirements under them. | **~25 operator verbs already exist and machine-readable output is already the norm** — `grep -l json bin/*.sh` matches essentially every one. Most of the eight requirements hold by construction: a documented exit-code convention (D42) in every command's docstring; destructive operations already gated on `--confirm KEY` matching the project (`bootstrap-providers.sh --destroy`); targeting already explicit (`--project KEY`); secret-safe logging enforced by tests rather than by care; and `connect.sh` already owning a bounded tunnel lifecycle across six commands with the authorization decision **on the host, in the release that deployed the project** (ADR 0043). | **`apg` is a thin dispatcher over the verbs that exist, not a rewrite**, and it is folded into Session 13. The genuinely new verbs are `upgrade check|plan|verify` and `project retire`. | **Renaming the surface is the expensive half and it buys nothing.** It invalidates `SHELL_COMMANDS` in `test_cli_contract`, every `--session N` D693's guard scans, all eight operator documents, and twelve gate scripts — 83,356 lines of tests is not a free place to do churn. A dispatcher adds a front door without moving a file, and `apg-diag.sh` is the precedent: one enumerated entry point over checks that live elsewhere (ADR 0158). | 0043, 0158, D42, D693 |
| **D708** | Session 16, one bullet among thirteen: *"JWT signing-key rotation with overlapping JWKS `kid`s"*, and the exit criterion *"Signing keys rotate without distributing private keys to verifiers."* | **This is D683, and it is the one Stage 1 claim that needs code.** `MAX_VERIFICATION_KEYS` is 2, `build_jwks` refuses a third, and `render-jwks.py:229` appends the bootstrap issuer's key **unconditionally** while the auth key and the prepared key are each guarded by `is_file()`. The set has been full since the auth service existed. `retire` cannot free the slot: `retire_after` is `None` and it refuses with *"no rotation is in flight."* CLAUDE.md said this was *"unblocked since Session 6"* for five sessions. | **The bootstrap-issuer retirement is Session 15's Run 1**, and every other item in that session sits behind it. It is an ADR, a run, and **four verifiers recreated** — PostgREST, auth, storage and the agent plane. | It is the session's exit criterion, not a preliminary to it. The specification lists it beside twelve conveniences; until it lands, the session's headline claim cannot be made and `bootstrap_identity` stays red. **A key cutover recreating all four verifiers is already a property** rather than a procedure — ADR 0155's mount-content digest is what makes that happen without anybody remembering to. | 0088, 0113, 0122, 0155, D683 |
| **D709** | Session 17: *"Create a thin project registry… It may begin as a file-based registry."* Seventeen recorded fields, ten capabilities, seven exit criteria. Priced as one of eight mandatory-core sessions. | **Every field the registry is asked to record is already published, per project, in the deployed document**: project identity, environment, host, routes, appliance version (`template_version`), release (`source_commit`, `deployed_through_session`), capability hashes, backup stanza and `backup_state`. `doctor.sh` already produces a live per-project verdict across 8 checks and *deliberately reads the deployed document for identities and nothing else* — every verdict comes from a live read, because that document records what was observed at deploy time. | **The registry is an aggregation over documents that already exist**, and *"can be deleted and reconstructed"* is a property of that rather than a feature to build. **It merges with ephemeral projects and retirement into one Session 17** about operating several projects over time. | Its remaining exit criteria are **negative** — holds no secret, is not in the data path, its loss interrupts nothing — and a non-authoritative read-only aggregator satisfies them *by construction*. Testing that is right and cheap; **spending a mandatory session on it is paying for a property you get for free.** The live-read discipline matters more than the registry: `backup_state` is a deploy-time snapshot nothing refreshes and is stale in **both** directions (D700, D701). | 0158, 0002 |
| **D710** | Session 18: implement a versioned capability bundle with eighteen members, project-local profiles, **eight budget classes**, eight safe-write controls, ten denial reasons, and an evaluation harness over sixteen scenario classes. | **Roughly half is deployed.** `capabilities.schema.json` v1 already carries name, tool, `kind` (read\|write\|**metadata**), `enabled`, `required_scopes`, a one-to-one backing `operation`, a **frozen** column allowlist, structured filter operators, `order_by`, `max_rows` (≤1000), `max_affected_rows` (≤100), `idempotent`, `timeout_ms`, and `audit.redact`. **Four budgets exist and their independence is an ADR** (0129): rows, serialized bytes (`MAX_SERIALIZED_BYTES`), elapsed time (measured — a 5 s body under a 1 s timeout returns at 1.10 s against a 0.09 s control), and concurrency (`ReadSlots`, rendered from `api.rest.pool_size` at half). The bundle is already contract-hashed into the deployed document. **What is absent is narrow**: per-capability version and deprecation, risk class, profiles, **windowed** quotas, idempotency *keys* (the manifest has a boolean, not a mechanism), dry-run, approval — and **three columns `app_private.agent_audit` does not have**: capability version, contract hash, denial reason. Its outcome enum is `started, served, refused, failed, committed`. | **Session 16 keeps the whole scope and is the largest of the six.** Its shape is one schema version bump, **one migration 0023** for the three audit columns, one durable-state mechanism for windowed quotas, and the harness. | Told as eighteen members and eight budget classes it reads as a rewrite of the agent plane; told as *what is missing* it is a bounded session. **The distinction is not cosmetic**: ADR 0129's four budgets are independent **by decision**, and a fifth added by somebody who has not read it becomes a second authority over one of them — which is D264's cost and ADR 0070's rule. **Windowed quotas are the one genuinely new budget class**, and the only one needing state that outlives a process. | 0070, 0129, 0135, 0141 |
| **D711** | Session 19: *"Introduce a PostgreSQL-backed transactional outbox, a narrowly scoped worker service, registered job types only,"* with six allowed job types and eleven features. Placed in the mandatory core. | **Nothing exists** — `outbox`, `job_queue` and `background job` match nothing under `services/`, `src/` or `migrations/`. And **five of the six allowed job types serve ingestion, embedding, export or object cleanup**: `generate_export`, `ingest_object`, `rebuild_embedding`, `refresh_report`, `clean_abandoned_uploads`, `verify_object`. None is required by anything Stage 2 must ship. | **Not in the mandatory core.** It is built only if the semantic track is selected, and then **as that track's substrate**, in the same session. | The specification's own cut order says its job types *"can shrink to the minimum needed by selected evidence tracks"* — which is the admission that it has **no consumer of its own**. A substrate built for a consumer that was cut is the most expensive kind of dead code, because it is correct, tested, and load-bearing for nothing. | — |
| **D712** | Session 20: *"Define three explicit connection tiers,"* run eight load-test scenarios, tune six timeouts, publish a capacity envelope, and gate public pooled access on evidence. | **Tiers 1 and 2 are built and proved.** Ports are host-loopback by decision (ADR 0042, `bin/database-ports.py`, whose probe **binds rather than connects** and deliberately does not set `SO_REUSEADDR`), and `connect.sh` reaches a project over an SSH local forward with the authorization decision on the host (ADR 0043) — `tunnel`, `status`, `stop`, `print-env`, `psql`, `exec`, and the three that require an existing tunnel do not open one. **Tier 3 is the only new one, and the spec makes it opt-in.** Half the tuning targets are already derived and published: `statement_timeouts`, `pooler_pool_size`, and five claimants on `max_connections`. | **The capacity envelope moves into Session 14**, beside the metrics that make it measurable. **Tier 3 stays disabled**, and the decision is recorded with evidence — which the specification's own release gate accepts. | What is left of that session is **measurement, not building**, and measurement without metrics is a stopwatch. One measured fact will dominate the envelope: **`process-max` is 1**, so a 31 MB backup takes six minutes and a restore is ~1330 serialised S3 round trips — latency, not bandwidth (D593, D603). **Any RTO or throughput number taken under backup load is a sample from a band, not a constant**, and an envelope that does not say so is a number about nothing. | 0042, 0043, 0099, 0148 |
| **D713** | Session 21 exit criteria: *"CI creates, tests and destroys an isolated project automatically… Expiration cleanup cannot affect permanent projects… Destruction produces evidence."* | **This is D691 and `project_removal`, already open.** No shipped command removes a project. `project-runtime.sh down` preserves the volume **deliberately** — *"removing it here would make `systemctl restart` a data-loss command"* — and `compose.sh` **refuses `--volumes` in project mode** outright. The removal surface is `down` plus `bootstrap-providers.sh --destroy --confirm KEY`, which removes only what the project's own state file records owning. Meanwhile **isolation is the product**: independent networks, volumes, routes, roles, audiences, storage prefixes, backup stanzas and signing keys are what a deployment *is*, and Session 12's matrix proved it over 179 leaves with 0 project-scoped values shared. | **Ephemeral projects, retirement and the registry are one Session 17.** The destroy-the-data verb it needs is an **ADR-shaped decision taken there**, not a convenience assumed by a TTL. | The hard half of an ephemeral environment — isolation — is already the product; what is missing is a lifecycle. And the missing verb is not missing by oversight: **destroying `pgbackrest_repo_cipher_pass` orphans every backup.** A TTL that expires into that is a data-loss timer. Doing this session also closes `project_removal`, which is a Stage 1 claim. | 0145, D691 |
| **D714** | Session 22: *"Stage 1 includes pgvector as an optional example. Stage 2 activates it only as a governed, RLS-respecting capability."* | **The extension is present and proved at its locked version** (`DBX-PG-001`, `extensions` schema). **No example table and no search function exist** in any of the 22 migrations — and the capability was **never entered into the acceptance registry at all** (D698). It is not scope that was dropped; it is scope nothing was tracking. | **An evidence-selected track**, and if selected it arrives **with its registry entry**, together with the job substrate it needs (D711). | The specification's rule — *"P2 items may be dropped before any P0 item"* — assumes the item is visible enough to be dropped *from* something. **An empty P2 row is how a silent drop looks exactly like an allowed one.** | D698 |
| **D715** | Session 23: *"A project restores onto a clean replacement host using only the independent backup account and documented artifacts. Recovery succeeds with the original VPS and the primary backup account both treated as unavailable."* | **The proof is written and gated and waiting for a host** — `fresh_host`, `APG_FRESH_HOST_OUTPUTS`, one of Stage 1's four unproved claims. The recovery plane itself is deployed: encrypted off-site backups, a rehearsed point-in-time restore that **never mounts the active volume**, `restore-test.sh`, and step 6c failing a deploy on a `pgbackrest check`. **What is genuinely new is the second account**: the repository is already its own bucket with its own credential and cipher pass (ADR 0145), but in the **same provider account** as the storage plane. | **Session 18 adds the independent account and runs the replacement-host restore through the proof that already exists**, closing a Stage 1 claim rather than writing a second one. | Two proofs of one guarantee is D696's shape: **a claim is a guarantee, not a file.** And the residual this closes is real and named — ADR 0147's: the database container can reach the internet, holds the repository credential and the cipher pass, so an attacker inside it owns the backup history as well as the live data. A second account in a second provider is the first thing that has ever bounded that. | 0145, 0147, 0089, D696 |
| **D716** | Session 24: *"A team that did not build Stage 1 or Stage 2 must complete"* sixteen steps, plus a full regression suite, an isolation matrix, a known-gap register and a Stage 3 decision report. A whole session. | **This is `DX-001` and `documented_path`, verbatim and already gated** on `APG_DX_RECORD_FILE` — with an offline half that already proves every command the documented path names exists, is executable, and passes a `--session N` equal to `CURRENT_SESSION` (D693, which found four defects on its first run including a README deploying an earlier session). The isolation matrix exists (`DEP-ISO-001`, 179 leaves). The known-gap register exists as `docs/scope-closure.md`. | **It is not a session.** It is a **declaration**, arranged rather than built — once before Stage 2 starts for Stage 1's sake (§4), and once at the close of Session 18 for Stage 2's. | `documented_path` has been unproved since Session 12 closed **for want of an afternoon**, and `docs/scope-closure.md` §6 already recommends closing it regardless of which product direction is taken: *"the cost is one outsider's afternoon and the alternative is discovering the gap during a customer deployment."* Session 11's rehearsal found `provision-host.sh` naming an operator user it does not create while installing `PermitRootLogin no` — which locks out the person deploying at 3 a.m. exactly as readily as a stranger. | 0045, 0089, D693 |
| **D717** | The specification's §8 *Scope protection*: **never cut** 13, 14, 15, 16, 17, 18, 23, 24; **shrink** 18's breadth, 19's job types, 20's matrix, 23's scenarios; **cut first** 21 and 22. | **The specification's own cut order describes eight mandatory sessions, not twelve** — and two of those eight (24, and half of 23) are declarations rather than work, by D715 and D716. | Recorded. **The release structure in §3 is what the cut order already implies**, arrived at independently and then found to agree. | A roadmap whose scope-protection section contradicts its own session count has already answered the question the count was asked to settle. The twelve is a **shape borrowed from Stage 1**, where it was earned: Sessions 1–12 built planes from nothing. Stage 2 mostly extends planes that exist. | — |
| **D718** | Housekeeping, found by this audit rather than looked for. | **A file named `&1` is tracked in the repository root** — the artifact of a redirect written as `>&1` where the shell took `&1` as a filename. 679 tracked files and this is one of them. Separately, **HEAD is `89db7fb`, one commit past the `39d5d01` CLAUDE.md §2 names**; local and `origin/main` agree, so the status block is stale rather than the tree. | Both corrected in Session 13's first commit. | Small, and it is the shape that survives because nothing reads a root directory listing. It is also the cheapest possible instance of this project's standing question: **has anything looked at this since it changed?** | — |

---

## 2. The four decisions CLAUDE.md §4 requires

A new body of work cannot begin until these are settled. They are settled here.

### 2.1 What is the new body of work for?

**A governed appliance system. The template, deepened — not a managed control
plane.**

`docs/scope-closure.md` §6 recorded this and deliberately did not resolve it: the
product contract freezes *"a reusable, isolated, one-project-per-deployment
PostgreSQL appliance and template,"* while the stated direction has been a hosted
service with a UI, which the same contract lists under non-goals.

**The Stage 2 specification resolves it, and this plan adopts its answer**: Stage
2 is *"a governed appliance system, not a miniature managed platform."* The
coordinator is explicitly non-authoritative — it may observe, inventory, validate
and coordinate, and it may not query application tables, hold a project database
password, a signing key or a backup cipher pass, or become a path by which a
request is authorized. **A managed multi-tenant control plane is Stage 3**, with
its own specification and its own threat model.

**What survives either answer, and is therefore not at risk from this decision:**
a deployment must need no knowledge living in one person's head. Under the hosted
reading that matters *more*, not less — an instance per customer, deployed
repeatedly, possibly under pressure, possibly by somebody hired later.

**The decision this stage plan does not take**, and flags rather than hides: if
Stage 2's own multi-project experience turns out to need authority the
coordinator is forbidden, that is **evidence for a Stage 3 specification**, not a
reason to widen Session 17. §9 makes it a stop condition.

### 2.2 Does `CURRENT_SESSION` move, and to what?

**Yes, six times: 12 → 13 → 14 → 15 → 16 → 17 → 18.** Nothing is renumbered and
no axis is replaced (D705).

Moving it stays **all-or-nothing** (D690): `test_no_requirement_at_or_before_the_
gate_session_remains_future` refuses any requirement due by the new number that is
still a placeholder, and there are **no `future` placeholders left** — Session 12
activated the last four. So **every Stage 2 session's requirements arrive with
their proofs, in the commit that moves the constant.** That is the discipline
D690 bought and it is why a session's registry additions (§2 of its own plan) are
decided before its first run rather than after its last.

**`template_version` moves with it**, and this is the new half: `0.1.0-dev` →
`0.2.0` at Session 13's close, one minor per session, **`1.0.0` at Session 18**,
the Stage 2 release candidate. Compatibility rules attach to *that* number, not to
the ordinal.

### 2.3 Which §9 items are actually open?

CLAUDE.md §9 warns that three of its oldest entries turned out **mischaracterised
rather than undone**, and that each took one measurement. Re-measured this
session:

| Item | Verdict |
|---|---|
| **Nothing knows which proofs have never executed** | **Open, and it is Stage 2's most valuable unbuilt thing.** Eight sessions. `pytest --setup-plan` is the cheap half and answers *will this run*; nothing answers *is what it asserts true*. Session 18's evaluation harness is the closest Stage 2 comes, and it only covers the agent plane. |
| **The signing-key cutover is blocked** | **Open. Confirmed by reading, not recalled** — D708. Session 15 Run 1. |
| **Three claims await a declaration** | **Open, and none needs code.** §4. |
| **No shipped command removes a project** | **Open** — D691, confirmed. Session 17. |
| **The IPv6 scan has nothing to scan** | **Open and not addressed by Stage 2.** D688: `host.public_ipv6` is `null` in both documents and `[::]:22` is the machine's only IPv6 listener. Running the eight proofs needs the manifest to declare an IPv6 **and** the edge to bind one — a deployment change, not a gate flag. **Stage 2 does not do it**, and §6 says so. |
| **Template or control plane?** | **Resolved by §2.1.** |
| **`process-max` is 1** | **Open by decision, and now load-bearing** — it is the dominant term in Session 14's capacity envelope (D712). Still not tuned: a drill must measure the deployment as it is. |
| **The agent plane's round trip is untimed** | **Open, and Session 14 closes it as a side effect.** A write is four upstream requests, a read three; each holds a PostgREST connection from a pool shared with human callers. Nothing has ever timed any of it. |
| **`MCP_MEMORY_LIMIT` is measured for the interpreter** | **Open, and it is one command** against a running container. Session 14. |
| **The 37 unclaimed requirements** | **Open** — D697. Session 13, as bookkeeping, **carefully**: a claim's session decides when it must first be proved, and D696 is the record of one being moved by accident. |
| **Two P2 capabilities were never registered** | **Open** — D698, D714. Evidence-selected. |
| **`lock-versions.sh --update` re-adopts unrelated rolling tags** | **Open** — D540. Nothing prevents the next `--update`. Stage 2 does not fix it; §10 carries it. |
| **The apt pin expires, deliberately** | **Open, undiarised** — D533. `pgbackrest=2.59.1-1.pgdg12+1` will one day resolve to nothing and the build fails closed. **Session 13 diarises it**, which costs a line. |
| **The database container can reach the internet** | **Open**, ADR 0147's stated residual — and **Session 18 bounds it for the first time** by putting the backup history in a second account (D715). |

### 2.4 Are the four unproved claims in scope?

**Yes, and three of them are prerequisites rather than work.** §4.

---

## 3. Release structure — six sessions, not twelve

| Stage 2 session | Absorbs spec sessions | Shape |
|---|---|---|
| **13 — Release identity and the upgrade path** | 13 + 15 | Compatibility rules on `template_version`, `upgrade check\|plan\|verify`, `apg` as a thin dispatcher, the D697 claim-coverage debt, D718's housekeeping |
| **14 — Observability, alerting, and the capacity envelope** | 14 + 20 | OTel propagation, metrics, alert rules, then the load tests and the published envelope the metrics make measurable |
| **15 — Identity lifecycle and credential rotation** | 16 | **Run 1 is the bootstrap-issuer retirement (D683)**, then refresh-token families, sessions, and rotation for every credential class |
| **16 — Agent capability governance v2 and the evaluation harness** | 18 | The differentiator. Capability semver, risk, profiles, windowed quotas, idempotency keys, dry-run, approval, migration 0023's three audit columns, and the harness |
| **17 — Multi-project operation** | 17 + 21 | Registry, ephemeral/preview projects, retirement. Closes `project_removal` |
| **18 — Independent DR, failure rehearsal, and the Stage 2 release candidate** | 23 + 24 | Second backup account, replacement-host restore, coordinator-loss and chaos rehearsal, the external pilot. Closes `fresh_host` and `documented_path` |
| *(evidence-selected)* | 19 + 22 | Bounded jobs **and** semantic ingestion, together or not at all (D711, D714) |

**Two orderings are forced and the rest is preference.**

1. **13 before everything.** Every later session bumps a version and needs the
   compatibility rules to say what the bump permits.
2. **14 before 16 and before 18.** Governance is not trustworthy without
   correlated evidence, and a failure rehearsal without alerts measures whether a
   person was watching.

**15 and 16 are independent of each other** and could swap. 15 is placed first
because D683 has been open longest and because a signing-key cutover touching
four verifiers is better done before a session adds a fifth reader of the key set.

**The count, honestly:** Stage 1's twelve were earned — they built planes from
nothing. Stage 2 mostly extends planes that exist, and §1 is the evidence. Six is
not a schedule concession; it is what is left after subtracting what is built.

---

## 4. Session 0 — closing Stage 1, which is not a session

**Four Stage 1 claims are unproved. One needs code and three need an event.** The
three are arranged now, in parallel with Session 13, and **each writes into an
evidence file that already exists and is already gated.**

| Claim | The event | Its gate variable | Cost |
|---|---|---|---|
| `fresh_host` | A host that starts empty, deployed from the documentation | `APG_FRESH_HOST_OUTPUTS` | A provisioned VPS and a trip |
| `documented_path` | An outsider follows the documentation and records what happened | `APG_DX_RECORD_FILE` | **One afternoon of somebody else's time** |
| `project_removal` | A project actually removed, through the surface that exists | `APG_REMOVED_PROJECT_FILE` | One trip, one project |
| `bootstrap_identity` | Code — the bootstrap-issuer retirement | — | **Session 15, Run 1** |

**An offline half may not stand in for one**, and that rule was fixed before any
of these was written precisely so the end of the plan could not quietly round
them up. It still holds.

**Two of the three do not need a fresh host or a code change**, so nothing blocks
them. `documented_path` in particular has stood unproved since Session 12 for want
of arranging an afternoon, and every session that passes makes the documentation
it tests older.

**A caution about `fresh_host` and Session 18.** They are the same shape — a
deployment onto a machine that starts empty — and it is tempting to fold the first
into the second. **Do not.** `fresh_host` proves the *documented deployment path*
reaches a running project; Session 18 proves a *restore from an independent
account* does. A session that half-closes another's requirement without saying so
leaves the next reader unable to tell a proved guarantee from a plausible one
(D478).

---

## 5. The six sessions

Each gets its own plan. What follows is the sentence each plan starts from, what
it must not do, and where its exit criteria come from. **Requirement id families
are proposed, not fixed** — each session's own §2 settles its ids, because
registering one is a decision about what a requirement *means* (D691).

### Session 13 — Release identity and the upgrade path

**Builds.** Compatibility rules attached to `template_version`, saying what a
patch, minor and major bump each permit across manifest changes, platform
migrations, application migrations, API contract changes, capability changes and
secret-format changes. `upgrade check | plan | verify`, each producing
machine-readable output, with **no mutation before a plan is produced and
validated** — which `--render-only` already half-implements and should be built
*on* rather than beside. `apg` as a thin dispatcher (D707). Rollback boundaries
stated honestly: **configuration rollback, image rollback and database
fix-forward are three different operations** and conflating them is how a runbook
lies. The D697 claim-coverage debt, carefully. D718's housekeeping and D533's
diary line.

**Already true, so do not rebuild it.** The version exists and is published
(D704); the manifest schema is versioned with a migrator; the capability bundle
is hashed; the API contract is frozen with canonical snapshots; `--render-only`
already validates inputs and stages outputs with no host and no root.

**Must not.** Introduce a second version axis (D704, ADR 0002). Renumber anything
(D705). Break `--render-only` with no host and no root. Retrofit the 37 orphan
requirements in bulk — **that is exactly how a Session 2 claim ends up dated
Session 12** (D696).

**Proposed family.** `REL-*`.

### Session 14 — Observability, alerting, and the capacity envelope

**Builds.** OpenTelemetry propagation through Traefik, FastAPI, FastMCP and the
protected downstream calls. Metrics: pooler saturation, connections, transaction
duration, PostgREST latency and errors, MCP calls and **denials by reason**,
audit-write failures, backup and WAL freshness, disk headroom. Alert rules for
backup failure, WAL archiving failure, disk pressure, unhealthy database, API and
MCP, certificate failure, and a high agent-denial rate. Then the load tests, the
timeout and pool tuning, and **a published capacity envelope with measured
numbers** (D712).

**Already true, so do not rebuild it.** The correlated request id (D706) — that
is `OPS-LOG-001`, proved in Session 11 across ingress → MCP → PostgREST → the
audit row. The redaction contract and its canary. Three timeout and pool values
already derived and published.

**Must not.** Log a URL, an object key, a token or any caller value — the agent
record's forbidden list is the telemetry plane's too, and Session 7's canary scan
exists because a presigned URL reached one. Publish an envelope number taken
under backup load without saying it is a sample from a band (D593, D603). Add a
read replica or a cache — this session produces the evidence that would justify
one **later**, and that is the whole point of measuring first.

**Closes cheaply, as side effects.** The agent plane's untimed round trip, and
`MCP_MEMORY_LIMIT` measured against a running container rather than an
interpreter. Both are CLAUDE.md §9 items and both are one command once the
instrumentation exists.

**Proposed families.** `OPS-*` extended, `CAP-*`.

### Session 15 — Identity lifecycle and credential rotation

**Run 1 is D683**, and everything else is behind it: an ADR for retiring the
bootstrap issuer, the run, and **four verifiers recreated** — which ADR 0155's
mount-content digest makes automatic rather than remembered. It closes
`bootstrap_identity`.

**Then builds.** Rotating human refresh tokens with **family reuse detection**,
session listing and termination, admin-controlled password reset, configurable
agent credential expiry, and rotation for every credential class — PostgreSQL
service credentials, R2 application credentials, backup credentials — each with
rotation evidence and a rollback procedure.

**Already true, so do not rebuild it.** Agent-secret rotation exists
(`POST /admin/agents/{agent_id}/rotate-secret`). Secrets are already materialized
**per consumer** into immutable generations whose active generation changes on
every deploy — so "one service cannot read another's credential" is a filesystem
property and rotation has a shape to fit into rather than to invent.

**Must not.** Put a secret value into source control, Compose interpolation,
process arguments, image layers or logs. Type a path into a generation — the
active one changes every deploy, so any path into it is derived. Add OIDC, SSO,
MFA, public self-registration or account recovery: out of scope unless a
consuming project forces the issue.

**One open decision it inherits.** `revoked → active` answers 200 (D503):
migration 0011 calls a revoked agent credential terminal and
`auth_set_agent_status` is an unguarded `UPDATE`. The bound half is proved —
`authz_version` moves on every transition — but **nobody has decided whether
un-revoking should be refused.** This is the session that should decide.

**Proposed family.** `IDN-*`.

### Session 16 — Agent capability governance v2 and the evaluation harness

**The differentiator, and the largest of the six.** Its shape, from D710: one
capability-schema version bump adding per-capability semver, deprecation state,
risk classification, byte and concurrency limits, dry-run and approval; **one
migration 0023** adding capability version, contract hash and denial reason to
`app_private.agent_audit`; project-local **profiles**; **windowed quotas**, the
one genuinely new budget class and the only one needing durable state;
**idempotency keys**, where the manifest today has only a boolean; a denial-reason
taxonomy; and the **evaluation harness** with positive and adversarial cases per
capability, failing CI when a capability changes without them.

**Already true, so do not rebuild it.** Four budgets, independent by decision
(ADR 0129). The frozen column allowlist and structured operators. The bundle
contract hash in the deployed document. Fail-closed audit initialization on
writes — and **not** on reads, which is ADR 0141's decision, not an omission. A
denial *is* audited, which is why `begin` runs before the scope check.

**Must not.** Hand the MCP runtime any credential — it holds none, and that is
enforced. Relay an upstream status code to a caller (D433). Weaken an allowlist to
a subset check — D300 arrived three times in one session, and every allowlist
failure since has been right to fail. Add a generic mutation dispatcher, an
`execute_sql`, or any schema-management tool. Add a fifth budget without reading
ADR 0129 first (D710).

**Its own hardest question.** The harness must not become a proof written by the
author of the code under test — that is CLAUDE.md §7's sixth question, and D673,
D680/D682 and D687 were each invisible to a green offline suite for exactly that
reason. **An adversarial case whose expected denial was written from the
implementation is a description of the implementation.**

**Proposed families.** `AGT-*` extended, `EVAL-*`.

### Session 17 — Multi-project operation: registry, ephemeral projects, retirement

**Builds.** A thin, file-based, non-authoritative registry aggregating the
deployed documents that already exist (D709), with a cross-project inventory view
showing health, backups and agent-denial rates. Ephemeral/preview projects with
TTL metadata, automatic cleanup, masking hooks and CI integration. **A retirement
workflow, and the ADR that decides what a destroy-the-data verb may destroy**
(D713). Closes `project_removal`.

**Already true, so do not rebuild it.** Every registry field is published per
project. `doctor.sh` is the live health source and **reads the deployed document
for identities and nothing else**. Isolation is the product, proved over 179
leaves. The removal surface exists and is scoped by derivation.

**Must not.** Let the registry hold a password, a signing key, an agent secret, a
provider token, backup encryption material or application row data. Let it enter
the data path or become required for local revocation. Read a key the deployed
document does not have (D600) — the guard scans every such module against the
schema, and the deployed document has **no `compose` block**. Ship a TTL that can
expire into destroying `pgbackrest_repo_cipher_pass`, which orphans every backup.

**Proposed family.** `FLEET-*`.

### Session 18 — Independent DR, failure rehearsal, and the Stage 2 release candidate

**Builds.** A secondary backup account or provider with independent credentials
and an independent encryption key. A restore-to-new-host workflow and a complete
node-loss runbook. Bounded failure rehearsals — service termination, database
restart, backup credential failure, disk threshold breach, WAL archiving failure,
registry loss, capability drift. **These test detection and graceful degradation,
not automatic failover.** Then the external pilot, the isolation matrix extended
to Stage 2's surfaces, the known-gap register, and the Stage 3 decision report
written from actual evidence.

**Already true, so do not rebuild it.** The recovery plane: encrypted off-site
backups, a rehearsed PITR that never mounts the active volume, `restore-test.sh`,
and a deploy that fails on a `pgbackrest check`. The `fresh_host` and
`documented_path` proofs, written and gated (D715, D716). The isolation matrix,
and the known-gap register as `docs/scope-closure.md`.

**Must not.** Treat a successful backup as a proved recovery. Record a recovery
time it did not measure — and remember `process-max` is 1, so the number is a
sample from a band. Let an offline half report a claim whose live half was never
run. Fold `fresh_host` into the replacement-host restore (§4).

**Proposed family.** `REC-*` extended.

---

## 6. What Stage 2 does not build

The Stage 1 non-goals hold unchanged. The Stage 2 specification's §9 deferrals
are adopted whole: **no managed multi-tenant control plane, no automatic high
availability or failover, no true copy-on-write branching, no scale-to-zero or
compute/storage separation, no global authenticated edge caching, no
zero-downtime major-version upgrades, no generic natural-language-to-SQL, and no
agent path that bypasses `capabilities.yaml`.**

**Three more, which the specification does not name and this plan does:**

- **The session ordinal is not replaced** (D705). It stays the evidence model's
  key.
- **The IPv6 scan is not run.** Eight proofs exist and there is nothing to scan
  (D688): the manifest declares no IPv6 and the edge binds none. Running them from
  a machine without IPv6 reports every port closed — a fact about the scanner.
  Closing it is a deployment change.
- **`lock-versions.sh --update`'s tag re-adoption is not fixed** (D540). It is
  real drift, it is known, and Stage 2 does not spend a session on it.

**And one the specification names as optional that this plan makes an explicit
default: public pooled access stays disabled** (D712). The decision is recorded
with evidence, which the specification's own release gate accepts.

---

## 7. Evidence and claims across Stage 2

**Unchanged, and none of it is renegotiated.** A claim's verdict is computed from
the acceptance registry's node ids and JUnit results, **never hand-entered**. A
skip is not a pass. A filtered (`-k`) run writes nothing. The host and external
halves must describe the **same release** or the merge refuses. `evidence/*` is
gitignored and the host half lives on the host.

**Three things Stage 2 adds to that model:**

1. **Every new requirement belongs to a claim** (D697). The guard already refuses
   a new orphan; Stage 2 must not add to the 37 grandfathered ones, and Session 13
   removes them from the register rather than growing it.
2. **A claim's session stays the session that introduced it** (D696). Extending a
   Stage 1 claim with a Stage 2 requirement **moves it**, which excuses it from
   every session in between. A new guarantee gets a new claim.
3. **`template_version` joins the evidence document's identity.** Both halves
   already agree on a release; from Session 13 they agree on a product version
   too, and that is the number a Stage 2 gap register quotes.

**Exit 5 remains the expected shape** of a run whose evidence was written and one
of whose claims is not `passed` (D686) — not a suite failure. Read the "not proved
by this run" line; it names them.

---

## 8. The security invariants Stage 2 may not weaken

| Invariant | Control | Where Stage 2 puts it at risk |
|---|---|---|
| PostgreSQL is the final authorization authority | RLS, FORCE, and the pre-request hook | The registry (17) — it must never authorize |
| A project's identities are derived once, in `naming` | ADR 0002, single authority | The version axis (13), the registry (17) |
| An agent cannot run SQL | No input accepts one; the compiler cannot emit one | Governance v2 (16), semantic search if selected |
| A revoked token stops on its next request, locally | `agent_claims_are_current`, per request | Registry loss must not affect it (17, 18) |
| An unauditable write does not happen | `agent_audit_begin` before the scope check | Migration 0023's new columns (16) |
| An agent record carries no URL, key, token or caller value | `audit.redact` from the lock, plus the canary | Telemetry (14), the harness's reports (16) |
| The MCP runtime holds no credential | `FORBIDDEN_VARIABLES`, `McpSettings`' shape | Windowed quotas (16) — durable state is not a credential |
| One service cannot read another's credential | Per-consumer immutable generations | Every rotation class (15) |
| A restore never overwrites the active volume | The restore path's own refusal | Replacement-host restore (18), ephemeral projects (17) |
| Projects share no project-scoped value | The isolation matrix, 179 leaves classified | Ephemeral projects (17) — each needs its own everything |
| A deploy over a broken archiver fails | Step 6c's `pgbackrest check` | The second account (18) |

**The matrix's `MUST_MATCH` half is the control and it is easy to lose** (D702): a
list derived from one observation encodes that observation's accidents.
`runtime.release_path` was classified project-scope because it *differed*, and it
differed only because two projects were mid-rollout. **Every Stage 2 session that
adds a deployed-document field owes that field a classification.**

---

## 9. Risks and stop conditions

**Stop and ask** rather than proceeding, when:

- **the registry needs authority it is forbidden** — to read a project's data, to
  hold a credential, or to be consulted before a request is authorized. That is
  not a wider Session 17; **it is evidence for a Stage 3 specification** (§2.1);
- a version bump would require a second answer to *"what is deployed"* (D704);
- an evaluation's expected denial was written from the implementation rather than
  from the policy (§5, Session 16);
- a capacity number would be published without saying which band it was sampled
  from (D712);
- an ephemeral project's cleanup could reach a permanent project's volume,
  stanza, or cipher pass (D713);
- a currently-passing test would be weakened to make a new one pass, or an
  equality turned into a subset check;
- `--render-only` stops working with no host and no root;
- a Stage 1 claim goes red and the tidy fix is on the proof's side.

**The failure mode Stage 2 is most exposed to is not Stage 1's.** Stage 1 kept
producing *a value that looked measured and was not*. Stage 2's shape is
different and worse to spot: **re-implementing something that already exists, one
layer over, because the specification described it and nobody checked.** Every
row in §1 is an instance caught at plan time. **The ones caught at run time will
look like progress** — a new metric beside a published one, a second budget over
ADR 0129's four, a second proof of `fresh_host`, a registry field derived twice.

**The six standing questions apply unchanged**, and CLAUDE.md §7 says question 5
is the one this project answers wrong most often — *when a decision is
implemented, which of its callers got it?* **Stage 2 makes it sharper**, because
five of the six sessions extend a decision rather than take one. Ask it at every
boundary, and ask question 6 of every fixture the harness writes.

---

## 10. Open items carried in

Everything in CLAUDE.md §9 that §2.3 did not resolve, plus what Stage 2 creates.

**Carried in and not addressed by Stage 2:** the IPv6 scan (D688);
`lock-versions.sh --update`'s tag re-adoption (D540); D340, where every service
role can reach the `postgres` maintenance database and read its catalog — closing
it means *inverting* the test that asserts the current state; `apg-diag`'s log
allowlist covering neither `auth`, `storage` nor `mcp` (D380, which has sent an
operator to a terminal in three sessions and is an ADR-shaped decision nobody has
taken); the rotation command's repairs unproved on a host (ADR 0122);
`--ssh-destination` not derivable (D466); the text scan standing in for a
construct (D464); `requirements-dev.in` pinning nothing, which has reddened the
gate nine times; the environment not verified against the lock (D297); the two
registry properties that are review rules rather than tests (D174, D175);
`tests/deployment/conftest.py` past 2,097 lines; ADR 0060's advertised-and-403
methods; and migration 0021's unmeasured `NOTIFY`.

**Carried in and addressed:** the bootstrap-issuer retirement (15), the three
declarations (§4), the 37 unclaimed requirements (13), the two unregistered P2
capabilities (evidence-selected), `process-max` and the untimed round trip and
`MCP_MEMORY_LIMIT` (14), the removal surface (17), the same-account backup
residual (18), the undiarised apt pin (13).

**Created by Stage 2, and named here so no session inherits them silently:**

- **Windowed quotas need durable state, and nothing prunes it** — the third such
  table, beside `app_private.agent_audit` and the secret generations. Session 16
  owns naming the retention decision even if it does not take it.
- **The registry is a fourth artefact that can go stale.** `backup_state` already
  is, in both directions (D700, D701). An inventory view aggregating deploy-time
  snapshots inherits every one of their staleness properties and multiplies the
  audience.
- **Six more gate scripts**, each derived by diff from the newest and registered
  in `SHELL_COMMANDS` — which Session 11 forgot and its first offline run caught.
  D505, D507, D678, D693 and D703 are five instances of the same loss, and
  **D703's half — the prose a gate *prints* — is still unguarded.**

---

## 11. How a Stage 2 session is planned

**Yes, each of the six still gets its own plan.** What changes is the shape: this
document owns what the six would otherwise repeat, so a Stage 2 session plan is
**seven sections instead of twelve**, and is expected to run 400–700 lines rather
than Stage 1's 1,000–1,700.

| § | Kept? | Note |
|---|---|---|
| 0 — Where the session starts | **Compressed to a pointer** | This document's §0 and §3, plus the previous session's close |
| **1 — The divergence table** | **Never cut** | **Still the point of the document.** Six columns, next free `D` number, grows all session. It is what a later session reads to find out why something is the way it is |
| 2 — Registry additions | **Kept** | Claim ids and node ids. Decided before the first run, because moving `CURRENT_SESSION` is all-or-nothing (D690) |
| 3 — Environment feasibility | **Dropped as a section** | The host is known and stable. A measured fact about it is a §1 row, which is where it will actually be read |
| 4 — Irreversible operations | **Kept** | Each named, with what makes it safe. Sessions 15, 17 and 18 each have several |
| **5 — Build order, run by run** | **Never cut** | Each run gets a `**Done.**` marker and a retrospective saying what it *measured* |
| 6 — The surface, described once | **Folded into §5** | It was always a restatement of the runs that build it |
| 7 — Evidence and claims | **Kept, short** | This document's §7 is the model; a session's §7 says only what *its* claims may honestly report before their live halves exist |
| 8 — Security invariant matrix | **Kept** | Scoped to what the session touches; this document's §8 is the standing set |
| 9 — Stop conditions | **Kept** | Session-specific ones only |
| 10 — Open items carried in | **Dropped** | This document's §10 |
| 11 — Next session handoff | **Dropped** | This document's §3 fixes the ordering; anything genuinely new goes in §10 here |

**What is deliberately not simplified**, because it is what caught the defects
rather than what cost the time:

- **§1's six columns.** A row with four columns is a note.
- **The mutation battery** in every run that writes a test: failures fatal (D269),
  a control the mutation **cannot reach** (D499), and an assertion about **how**
  each mutation failed, since pytest distinguishes `FAILED` from `ERROR` and a
  battery reading neither reports `KILLED` for a mutation that broke the fixture
  (D386).
- **Measuring a third party with a control before writing anything that depends on
  it.** Roughly half of Session 5's measured claims turned out wrong, and every
  session since has found more.
- **`pytest --setup-plan` before a trip.** Seconds, and it caught four wrong
  fixture assumptions and one fatal one green since Session 5 (D671, D676).

**The gate cadence does not change and is not a save button.** Documentation only
→ nothing. Generated artifacts could drift → `bin/session-01-check.sh` alone.
Code → the full suite once, then `session-01-check.sh`. Before a host trip, a
deploy or a session close → all applicable gates, in every mode the evidence
needs. **Gate at milestones**, and read the skip count: locally 3 is healthy, 72
means leftover fixture containers.

---

## Appendix — what to consult, and what to measure instead

**Consult, in this order:** this document's §1 and §3. `docs/scope-closure.md` —
the ledger, blunter than the README, and the document to read before proposing
work. `stage-2-consolidated-spec.md` §5 (governed agent access) and §9 (the Stage
3 deferrals), which are the two halves this plan adopts whole.
`docs/plans/session-09-implementation-plan.md` for what a full session plan looks
like when the session builds a plane, and `session-12`'s for what one looks like
when it builds proofs. `docs/decisions/README.md`, 161 ADRs indexed.

**The ADRs Stage 2 most needs**, rather than all 161: **0002** (derive an identity
once — and D680/D682 are it broken twice against the component that implements
it); **0129** (four budgets, independent by decision — read before adding a
fifth); **0135/0140/0141** (the audit record written as the caller; a hidden tool
is still callable; a denial is audited, which is why `begin` precedes the scope
check); **0149/0150** (what a repository can honestly report, and how a broken
archiver stays visible); **0155** (a deploy recreates a container whose mounted
*content* changed — what makes a key cutover recreate four verifiers);
**0158** (the deployed document is the address book, not the diagnosis);
**0065/0066** (a proof that reaches the right end state by a route the product
does not take proves the end state is reachable, not that the product reaches
it); **0089/0045** (what a claim is, and why its session is load-bearing).

**Measure instead of consulting**, every time: what a third party's exit code
means when the state is in a field (`postgrest --ready` returns 0 while every
request 404s; `pgbackrest info` exits 0 for a stanza that does not exist);
whether a cumulative counter can answer a point-in-time question
(`failed_count` stood at 26 on a healthy cluster); what a container actually
holds; and **whether a proof has ever run**.

**Before measuring how a third party behaves, `grep` the plans for it.** Session 8
re-measured how PostgreSQL grants `EXECUTE` on a new function; Session 3 had
measured it three sessions earlier in more detail (D57, D262). Every ADR is
indexed; **nothing indexes the ~718 measured facts in the divergence tables by
subject**, so the pointer has to be a `grep`.

**Never write a measurement you did not run** (D267).
