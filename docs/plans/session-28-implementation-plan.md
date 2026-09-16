# Session 28 — Sound before Stage 4: the on-ramp decided, and everything the audit found that a checkout can close

**Status:** planned 2026-09-16, against `docs/pre-stage-4-audit.md` at `ad96673`,
`template_version` **1.6.2**, `CURRENT_SESSION` **25**.
**Brief:** `docs/pre-stage-4-audit.md` whole — one inventory of everything this
project knows is wrong with itself, sorted by *what kind of act closes each row*.
Then `docs/scope-closure.md` §15 and `docs/plans/session-27-implementation-plan.md` §1.
**Shape:** **nine runs, offline. NO HOST TRIP, NO TAG.** The bump lands in Run 9
and the tag does not. **Session 29 is the trip**, and Run 8 writes its sheet.
**Product version at close:** `VERSION` **1.7.0**, `CURRENT_SESSION` moves
**25 → 28**. 26 and 27 are skipped the way 19 is, and the skip is the record.
**Next free:** D1440, ADR 0215. *(Run 1 added D1426–D1433; Run 2 added
D1434–D1439 and wrote ADRs 0210, 0211 and 0212.)*

---

## 0. Where the session starts

The operator asked for the project to be sound before Stage 4 is planned, and
the audit priced three readings of that. **Reading 2 is the one chosen: Tier 1
closed, Tier 2 prepared and then closed by one trip with the rotation
performed.** This plan takes the first half and hands the second half a sheet.

**The brief's own number is wrong, and correcting it is the first row of §1.**
The brief says Tier 1 is 31 rows. The audit page says 36 and shows its working —
its first draft said 31 and was corrected by counting, and it left that fact on
the page deliberately. Counted again here, by walking the three sub-tables:
**1a is 6, 1b is 19, 1c is 11, total 36** (D1406). A plan built on 31 would have
silently dropped five rows, which is the thing the brief itself says is worse
than naming them.

**The second thing measured in planning matters more than the count.** Of those
36 rows, **fourteen are already answered in the tree** — by a stated decision at
the definition, by a docstring that carries the alternatives, by a test that
asserts the current state, or by a page that says the thing the row asks for.
Session 27's own §4 rule is the one that catches this: *a brief that describes
what already exists prices a free property as a session.* Those fourteen are
D1407–D1418, D1420 and **D1426** in §1, each with the command that shows it. They
are not "skipped" — a row the audit calls open and the tree calls decided **is** a
divergence, and §6 of `CLAUDE.md` requires a row rather than a silent
reconciliation.

**So the honest size of Tier 1 is not 36.** It is fourteen rows that close by
writing down what is already true, fifteen that are a repair or a decision this
session takes, and **seven this session defers by name** (§10). Run 1 measured
the nine rows planning had not reached and moved three more into the deferred
column (D1428, D1431, D1432), which is why §10's list is ten rows and not seven.

**Three of the fourteen would have caused harm implemented as the audit writes
them**, and they are the reason Run 1 exists as a run rather than as a paragraph:
D1411 would have widened a security boundary to match a grant the release's own
`0006` makes unreachable; D1416 would have undone a decision taken under ADR
0195; and **D1426 would have put a provider's response body into a log** on an
identity endpoint, against §6's own non-negotiable, to answer a row that reads as
though nobody had decided.

**The third measurement decided the session's shape.** `REL-STAGE-001` couples a
release to a deployment: a host sweep asserts each project's deployed document
carries the tree's `template_version`. ADR 0209 couples a release to its own
documentation. D1033/D1388 is the class where a release's documentation lands
one commit past its own tag — **three occurrences, twice in one day, the third
inside the release built to stop it**. Those three facts are only jointly
satisfiable if **the bump, the deploy and the tag happen in one trip** (D1425).
This session therefore bumps and does not tag; Session 29 deploys, sweeps, and
cuts `1.7.0` on the commit it deployed. That is not a scheduling preference. It
is the only arrangement in which ADR 0209's guard and D1401's obligation are
both true at the moment the tag exists.

**What this session is not.** It builds no plane, opens no surface, and adds no
verifier. It performs no rotation — the rotation is **rehearsed** in Run 8 and
**performed** in Session 29, which is what the audit means by *its own rehearsal
and its own run*.

---

## 1. The divergence table

D1406–D1439. **D1406–D1425 were measured during planning on `ad96673`; D1426–D1433
are Run 1's**, from the nine rows planning had not measured; **D1434–D1439 are Run
2's**, measured on rig 28a and on a pinned PostgreSQL 18.4. Rows marked
**answered** are closed by writing down what the tree already does; rows marked
**recorded** are not repaired here and say why. Runs allocate from **D1440**.

**Run 1's eight rows changed four of this plan's own run descriptions**, and the
changes are in §5 rather than only here: D1426 makes D1045 a fourteenth answered
row rather than a Run 4 decision, D1427 replaces what Run 4 repairs in
`render-jwks`, D1429 splits the audit's D1276 row into two findings that are not
the same finding, and D1430 revives a deferral whose stated reason has expired.

| D | Said | Measured or read | This session | Why it matters | ADR |
|---|---|---|---|---|---|
| **D1406** | The brief: *"Tier 1 is 31 rows."* | **36.** Counted by walking the audit's three sub-tables: 1a 6, 1b 19, 1c 11. The page itself says 36 and carries the note that its own first draft said 31 — *"written by the same hand that wrote this page's own instruction to measure rather than recall"*. The brief inherited the draft's number. | **The plan is written against 36**, and §10 names every row it does not take. | A plan built on the smaller number drops five rows without anyone deciding to, which is exactly the failure the brief's own instruction forbids. The count was already corrected on the page; the brief is where the stale one survived. | — |
| **D1407** | Audit 1b: *"`requirements-dev.in` **pins nothing**"*, closing act *"`bin/lock-dev-deps.sh --update`, committed separately."* | **It pins twenty-one packages with `==`**, and the six it leaves floating are a recorded decision with its reason in the file: `ruff==0.16.3` *("the only tool here that is … pinning the formatter makes 'the tree is formatted' a statement about a specific formatter")*, then the auth service's nine, the R2 adapter's two, and the agent framework's, every one tied to `versions.in.yaml` by `test_the_development_environment_installs_the_locked_service_versions`. Floating: `pytest`, `pytest-timeout`, `pytest-xdist`, `PyYAML`, `jsonschema`, `httpx` — *"left floating deliberately rather than by omission: none has ever produced a red gate … Recorded as a decision so the next reader does not read the inconsistency as an oversight."* | **Answered.** Run 1 strikes the row and records the six. No edit to the file. | The row asks for the command that would re-resolve a file whose author already answered it in prose at the point of the decision. Running `--update` here would move twenty-one pins for a row that was never true. | — |
| **D1408** | Audit 1b: *"The completion script is bash's. zsh and fish users have `--list` and `--help`"*, closing act *"One `case` arm, **or a stated decision**."* | **The stated decision is already in the command.** `bin/completion.sh:52`: *"Only bash is supported. zsh's `bashcompinit` can usually source a script of this…"*, and the refusal at `:127` is *"unsupported shell: $1. The one this command speaks is bash."* `scope-closure.md` §14 carries the same decision with its reason (*"writing one to be unused is not a decision this session took"*). | **Answered.** Run 1 strikes it. | Two of the row's two closing acts; one of them was performed in Session 25 and the audit did not read the command's own help. | — |
| **D1409** | Audit 1b: *"No Python client … A second emitter, **or a stated decision not to**."* | **`docs/generated-clients.md` §7 carries it verbatim**: *"There is no Python client. The intermediate representation is language-neutral and a second emitter is one module over it, but building one to be deleted is not a decision this session took (D1205)"*, and the `node:crypto` boundary beside it. | **Answered.** Run 1 strikes it and §10 keeps D1205 as Stage 4's inheritance, which is where `scope-closure.md` §14 already puts it. | Same shape as D1408: the alternative the row offers is already taken, on the page the row's own subject documents. | — |
| **D1410** | Audit 1b: *"`MAX_SERIALIZED_BYTES` was **chosen, not measured**"*, closing act *"Measure both."* | **True, and the code says so at the definition**: `services/auth-api/app/mcp_tools.py:136` — *"1 MiB, chosen not measured, and said so where it is defined."* `MCP_MEMORY_LIMIT_MB = 384` carries the same honesty at `rendering.py:1889` (*"inherited, not…"*). And `schemas/capabilities.schema.json` already carries the usage measurements the row asks for: a metadata response is 288–683 bytes, a write's 8–12 KB, `query_resource` over `notes` reaches the ceiling at 42 rows of 4 KiB columns. | **Answered as stated**, and the residue is recorded: the *ceiling* is a choice with its consequences measured, not an unmeasured number. Run 1 adds one sentence to §7 of `docs/product-contract.md`'s neighbouring text only if Run 1's reading finds the two statements disagree. | The row reads as *nobody looked*. Somebody looked, wrote what they found next to the constant, and declined to derive a bound from it. That is ADR 0195's posture and the row asks to undo it. | — |
| **D1411** | Findings F-013 and audit 1a: *"The project-set lint forbids `{{app_runtime}}`, which the release's **own migration `0003`** uses. An adopter who copies the platform's example domain writes a set the release will not lint"*, closing act *"An ADR (it is a security boundary), then **roughly one line**."* | **The grant `0003` makes is inert three migrations later, and `0006`'s own comment measures it.** Only two released templates grant to `{{app_runtime}}` (`0001` schema `USAGE`, `0003` `SELECT, INSERT, UPDATE, DELETE ON app.notes, app.tasks`). `0006-app-runtime-least-privilege.sql` then issues `REVOKE ALL ON SCHEMA app FROM {{app_runtime}}` and its header records the measurement: `has_table_privilege(app_runtime,'app.notes','SELECT')` → **true**, and `SET ROLE app_runtime; SELECT * FROM app.notes` → **denied**. *"THE SCHEMA REVOKE IS THE ONE THAT HOLDS."* So an adopter copying `0003` writes a grant that grants nothing reachable. | **ADR 0211 in Run 2**, and it is not a widening. The measured position is that the lint's allowlist is **right** and the release's own example is what misleads. The decision is between (a) the allowlist stands and the refusal names `0006`, (b) `0003`'s dead grant is removed by a fix-forward migration, (c) the allowlist admits `app_runtime` — which `CLAUDE.md` §6 calls weakening and which would grant an adopter something the release itself revokes. | **The closing act as written would have widened a security boundary to match a dead line of SQL.** The finding is real — the adopter was misled — and the thing that misled them is the example, not the lint. This is the reassuring-direction premise (D930, D957) aimed at the one lint whose docstring says *"Every refusal here is a boundary, not a style rule."* | 0211 |
| **D1412** | Findings F-012 and audit 1a: *"`freeze-lock` refuses a project set authored against an earlier release … 1.6.2 repaired the *message*; the refusal stands"*, closing act *"A way to declare or derive the real `follows_release_version`."* | **Since ADR 0206 the refusal guards nothing a cluster would refuse, and the function's own docstring says so in as many words**: *"**This no longer prevents anything the cluster would refuse** (ADR 0206, D1288) … Since ADR 0206 a project set renders to its own directory and applies against `app_private.project_schema_migrations`, and **each set is ordered against its own applied set only** … **So what survives here is a record, not a guard.**"* And: *"**What it should do when a set was frozen against an EARLIER release is undecided, and it is the on-ramp session's.**"* | **ADR 0210 in Run 2**, and the measurement changes what the ADR is about. It is not *how do we safely relax a guard*; it is *who writes a record, and from what*. Three candidates: the operator declares it (`freeze-lock --project … --follows <version>`), it is derived from the installed deployed document, or the refusal is removed as a released guard that ADR 0206 deliberately left standing. | The audit prices this as a flag. It is a decision about whether a released refusal that protects nothing should be satisfiable by declaration, and ADR 0206 explicitly did not take it — *"removing a released guard is a separate decision from the one that ADR took."* Pricing it as a flag is how a released guard gets removed by an implementation detail. | 0210 |
| **D1413** | Audit 1b: *"`mcp_tracing.configure()` **has no caller**. No span leaves the process"*, closing act *"A caller, or delete it."* | **`configure()` has no product caller; `span()` has one.** `services/auth-api/app/mcp_tools.py:55` imports the module and `:773` opens `mcp_tracing.span("agent.tool_call", tool=tool, resource=resource)` around every tool call. The only callers of `configure()` are `tests/contract/test_mcp_tracing.py:141,148`. So **the plane creates a span per tool call into a tracer nobody configured**, which is not the same defect as dead code: deleting the module removes a working instrumentation point, and adding a caller starts emitting. | **Run 4 decides which**, measured rather than assumed, and the decision is a network question before it is a code question (`scope-closure.md`: *"scraping a project's services must answer the network question first"*). The row's two options are not symmetric and this session may take neither — but it may not leave the row reading as *dead code*. | A row that says *no caller* about a module with a caller sends the next reader at `git rm`. The spans are the part that already works. | 0195 |
| **D1414** | Audit 1b: *"Session 9's live proofs check `"error"` and not `isError`, so they **pass on a refused write**. Session 16's `refused()` helper reads both"*, closing act *"Move the old proofs onto the helper."* | **The refusal assertions in `test_session9_agent_writes.py` already read both**, at `:910`, `:929`, `:1013`, `:1029`, `:1263`, `:1270` — `"error" in result or result.get("result", {}).get("isError")`. What still reads one key is the **success** direction: `:265`, `:961`, `:1233`, `:1240` assert `"error" not in result` alone, so a tool answering `isError: true` passes as a successful write. Four assertions, one direction, and the direction left is the one that is silently green. | **Run 5**, in the Tier 1c run, with the module's own `refused()` shape. The repair is four assertions and a battery that mutates a success into an `isError` refusal and asserts `FAILED` rather than `ERROR`. | The row is half repaired and the repaired half is the loud one. §7 question 5 in a module: a decision reached six call sites and not the four next to them. | — |
| **D1415** | Audit 1c: *"D340 — Every service role reaches the `postgres` catalog"*, closing act *"A decision."* | **A passing test asserts the current state.** Session 7's plan: *"`test_the_maintenance_database_is_reachable_by_every_service_role` asserts the CURRENT state, so a later session that closes it turns the test red and the fix is to invert it."* The exposure measured there is catalog metadata — database and role names — and never project data, which a separate proof covers against a database that exists. | **Recorded, deferred, §10.** Closing it changes every role in every session and inverts a passing contract test, which `CLAUDE.md` §6 permits only with an ADR. It is not a soundness repair; it is a role-model change. | The row's closing act is right and its cost is a session. Naming the cost is what keeps it from being attempted in a run that has four other things to do. | — |
| **D1416** | Audit 1b: D1275 *"A `project_admin` cannot use the schema or query views … A decision, then a grant or a narrowed surface"*, and D1274 *"Studio's capability view shows the checkout's lock, never the plane's … Ask the deployment."* | **Both already carry their decision, under ADR 0195, at the code.** `studio.py:464`'s docstring: the capabilities view is *"**Separate from `schema_view` because it answers a different question** (D1274)"* — no request Studio makes confirms the lock, so *"gating it on one would report a REST document's staleness as though it were the lock's, and that is ADR 0195's folded third outcome"*, and `CAPABILITIES_NOTE` travels with the payload so the caveat cannot come apart from the data. D1275 is documented in `docs/studio.md` §2 with its measurement, and `scope-closure.md` §13 says what is actually undecided: *"whether a human should ever hold both an administrative scope set and a data role"*. | **Answered for what the rows say; recorded for what is open.** Run 1 strikes both rows and §10 carries the one live question — the role model — to Stage 4, where `scope-closure.md` already puts it. | D1274's closing act (*"Ask the deployment, as `list_resources` already does"*) would undo a decision taken under ADR 0195 for a stated reason. This is the row most likely to be implemented by a reader who trusts the audit over the docstring. | 0195 |
| **D1417** | Audit 1b: *"The apt pin `pgbackrest=2.59.1-1.pgdg12+1` expires … A pinning policy."* | **Accepted, stated, diarised at the pin, and it fails closed.** D533: *"an unresolvable pin exits **100** and produces no image — the build **fails closed** … Nothing moves silently."* ADR 0144 carries it; `scope-closure.md` §5 says the note *"now sits **at the pin** in `versions.in.yaml` with the one command that answers 'is it still there'"*. D99's `PYTHON_RUNTIME_IMAGE` is the genuinely different one — a rolling minor tag that can drift into a *different* build rather than into none. | **Answered for the apt pin; D99 recorded.** Run 1 strikes the apt half and §10 keeps the rolling-tag half, which is a real unpinned surface and not the one the row names. | The row bundles a loud fail-closed risk with a quiet drift risk and prices them as one policy. They are opposite defects and only one of them is silent. | — |
| **D1418** | Findings F-026 and audit 1a: *"`bin/doctor.sh` checks the interpreter on a workstation only"*, closing act *"then the interpreter check on the host."* | **Adding it to deployed mode crosses ADR 0158's split, which is load-bearing.** `bin/doctor.sh:3-14`: *"Two modes, split by argument and never run together (ADR 0158) … **The split is what keeps the bare `python` below correct.** Workstation mode … so `--project` runs the deployed checks ONLY, and never reaches it."* Deployed mode needs root and reads the deployed document; workstation mode reads the toolchain. The host's interpreter is a property of *neither* mode as they are drawn. | **ADR 0212's neighbour, taken in Run 3 as a third reading or not at all.** The measured options: a `--host` reading that is explicitly neither mode; `provision-host.sh --check` reporting the interpreter it found (it already runs there and already reports); or the release states that the host interpreter is unchecked and says why. `provision-host.sh --apply` **installing** an interpreter is a change to what this product does to a machine and stays out (Session 27 §9's rule, unchanged). | The one-line closing act lands inside a split whose own comment says the split is what keeps another check correct. This is the §7 question-5 shape in a *reader*: which mode gets the decision, and does adding it to one break the other. | 0158 |
| **D1419** | The on-ramp: *"How a fork made **before** `projects/<slug>/` existed converts to it is undecided"* — `scope-closure.md` §15's first row, and the audit's *"A decision, then a documented procedure."* | **The fork is reproducible offline, so the decision can be measured rather than argued.** `git ls-tree -r --name-only 1.0.0 -- projects/` returns **nothing** over 802 tracked paths: tag `1.0.0` has no `projects/` at all. A synthesized pre-ADR-0198 fork — a checkout of `1.0.0` with a tenant table in `migrations/templates/`, a row in the release's `manifest.json` and `released.lock.json`, and operations in the shared reviewed surface — is buildable from the tag in a throwaway clone. | **Rig 28a in Run 2**, and **ADR 0212** decides from what it measures. The ADR is permitted to decide that **no conversion exists** — re-homing an applied migration is what D912 forbids, and an honest *"a fork at 1.0.0 does not convert; here is what it does instead"* is a decision, not a failure to reach one. | The question has been called a product decision by two sessions and deferred by both, and the reason given each time was that there is no fork to try it on. There is one, and it is `git`'s. | 0212 |
| **D1420** | Audit 1b: D1203 *"Two serializers that agree only while the document is ASCII — One canonicalizer"*, and D930 *"Two fields named `capabilities_sha256` — Rename one."* | **The tree already prices both as a later session's, with the reason.** D1203, `scope-closure.md` §12: *"The client never compares that digest, **which is why this is a decision for a session that versions that snapshot rather than a defect now**."* D930: renaming the field in the rendered document moves the outputs schema (v18 → v19) and owes a migrator, which is a schema session's act. | **Deferred, §10, and the cheap halves taken in Run 5**: a test asserting the two `capabilities_sha256` are different quantities (so the day somebody unifies them it goes red for the right reason), and a test asserting `app-openapi.canonical.json` is ASCII — which is the premise the agreement rests on and which nothing currently reads. | Both rows' closing acts are correct and both cost a schema move. Taking the premise-assertions instead converts a silent future disagreement into a loud one for the price of two tests. This is D1282's shape applied twice. | — |
| **D1421** | Audit 1c: *"D1240 — Four modules collect 0 under every marker-selected sweep … They have never run in any gate."* | **Confirmed, and the shape of the fix is not uniform.** `tests/contract/test_database_function_signatures.py`, `test_storage_client.py`, `test_storage_endpoint.py`, `test_storage_endpoints.py` carry no `pytestmark`. The sweeps select on 136 `[contract, p0]`, 31 `[contract, p0, security]`, and smaller sets. **`test_storage_client` imports `from app.storage_client import …`** and `test_storage_endpoints` imports `httpx` — these are service-tree modules, not repository-tree ones, and giving them a contract marker puts them in a sweep whose environment may not have the service package importable. | **Run 5**, per module and measured: `--setup-plan` under each sweep's own selector **before** the marker is added, then after. D1242's sweep-selector guard is in the run's targeted list, which `CLAUDE.md` §1 requires of any run that adds a module to a sweep. | *"Give them markers, or say why not"* is right and treats four modules as one. Two of them may be a genuine *why not*, and the difference is measurable in a minute and invisible from the audit. | — |
| **D1422** | Audit 1c: D464 *"`dx_record.documented_commands` is a **text scan** … A parser, or a stated limit with a test"*, and the neighbouring row *"Both documentation scans match a command line **by its first word**, so a flag on a `\`-continuation line is unchecked."* | **One regex, and it is the same one for both rows.** `dx_record.py:132`: `_COMMAND = re.compile(r"(?:^|[\s\`(])(\./deploy\.sh\|bin/apg\.sh\s+[a-z][a-z0-9-]*\|bin/[a-z0-9-]+\.(?:sh\|py))")`. It captures the script and, for `apg.sh`, one verb. It reads no flags at all, so *"a flag on a continuation line is unchecked"* understates it: **no flag on any line is checked**, continuation or not. `scope-closure.md` §14 already records the direction — an unmatched *documented* command makes a walker's honest use look unnamed, which is the safe direction. | **Run 5 takes the stated limit with a test**, not a parser. The test asserts what `_COMMAND` can and cannot see, against fixtures that include a continuation line and a flag, so the limit is a measured property rather than a sentence in a ledger. A parser is §10's. | The second row describes a narrower defect than the first row's subject actually has, and both were written about the same regex. A repair aimed at continuations would have left the scan reading no flags and looked like progress. | — |
| **D1423** | Findings F-020 and audit 1a: *"A host checkout one commit behind the workstation is invisible: `upgrade check` compares versions and digests, never commits"*, closing act *"Report the commit. Small."* | **`source_commit` does not appear in `upgrade_plan.py` or `bin/upgrade.py` at all.** The payload carries `verdict`, `installed_version`, `release_version` and the leaf comparison; the commit is a field of the **deployed document** and of nothing the upgrade reader touches. So the repair is not *print a field it has* — it is *read a document it does not currently read on the candidate side*. | **Run 3**, and the reading is stated in ADR 0195's three outcomes: the installed commit, the candidate commit, **or *I could not determine it***, which is the case for a checkout that is not a git working tree — a case an adopter's tarball fork is actually in. | *"Small"* is right about the printing and wrong about the reading. The third outcome is the one an adopter hits, and a reader that folds it into "they match" is the defect the finding is about, one level up. | 0195 |
| **D1424** | Audit 1c, the row that asks for a `D` number: *"A release's documentation landing one commit past its own tag. It has now happened three times, twice of them on one day … ADR 0209's guard caught none of them, correctly … **the habit around it is what fails**."* | **Measured on this tree.** `git tag` → `1.0.0 1.0.1 1.6.0 1.6.1 1.6.2`. `git ls-tree -r --name-only 1.6.0 -- docs/` carries neither release page; `1.6.2` carries both. Between `1.6.1` and `1.6.2`: two product repairs and a reply page, landed past the tag, caught by a reading rather than by a reader. **Nothing in the tree lists what is about to be tagged, and nothing lists what has landed since the last tag.** `grep` for `git tag` and `ls-tree` across `bin/` returns nothing. | **ADR 0214 in Run 7**, deciding **command or checklist** — the question the audit poses and answers with a warning: D1033's row says a checklist already existed in prose and the session that wrote it did not follow it. The measured argument for a command is that a checklist has now failed three times; the argument against is that nothing a command prints can make somebody run it. **The ADR takes a position and Run 9 is where it is first used.** | This is the class that has cost two patch releases. A test cannot see a tag cut after CI is green and ADR 0209 says so; what is missing is the question being asked out loud at the moment it is answerable. | 0214 |
| **D1425** | `REL-STAGE-001` (a host sweep asserts each deployed document carries the tree's `template_version`), ADR 0209 (each release page states its release, checked against `template_version()`), and D1401 (*"the tree is two patches ahead of the deployment"* — an obligation, not a defect). | **The three are only jointly satisfiable inside one trip.** A session that bumps and tags without deploying leaves `stage_release`'s live half red until the next trip — which is D1401, now on its third occurrence (Sessions 22, 23, 27). A session that bumps, deploys and then discovers a documentation defect cuts a second patch — which is `1.6.2`. **The arrangement in which neither happens is: bump offline, deploy, sweep, then tag the commit that was deployed.** | **This session bumps in Run 9 and does not tag.** Session 29 deploys the bump commit, sweeps, and cuts `1.7.0` on it after ADR 0214's reading. §4 records that this session has **no** irreversible operation, which is the first time that is true of a session that moves `VERSION`. | Three sessions have met D1401 and each named it as an obligation the next trip inherits. It is not an obligation; it is a consequence of tagging and deploying in different sessions, and the release that stops doing that stops meeting it. | 0214 |
| **D1426** | Audit 1b: *"D1045 — `ControlPlane._call` discards a provider body that said *identity limit reached* — a security judgement thrown away in a credential path"*, closing act *"Report the body, **or say why not**."* | **It says why not, at the discard, and the reason is the product's own non-negotiable.** `bin/bootstrap-providers.py:370-373`: `except urllib.error.HTTPError as exc:` — *"# The body is not included: on identity endpoints it can echo the request, and this message reaches a log."* — `raise BootstrapStateError(f"{method} {path} failed with HTTP {exc.code}") from None`. A provider body on an identity endpoint can carry the identity name and the request payload, and §6's rule is *never log a URL, key, token or caller value*. The status **is** reported. | **Answered — the fourteenth.** Run 1 strikes it. **The residue is the silence, not the discard**: an operator sees `HTTP 400` and is not told a body was read and dropped, so *the provider explained itself and we refused to repeat it* is indistinguishable from *the provider said nothing*. Run 4 adds that one clause and does not print the body. | The audit's row calls it *thrown away*, which reads as an oversight in a credential path and sends the next reader at a `print`. It was weighed, decided, and written at the line. **This is the row most likely to be "fixed" into a secret in a log.** | 0195 |
| **D1427** | Audit 1b, and `scope-closure.md` §14: *"D1374 — `render-jwks` prints *'the key set CHANGED'* from a test of the **file's bytes** … **It reports a rotation that did not happen***", closing act *"Compare the key set, not the file."* | **The byte comparison is correct and the SENTENCE is the defect.** `bin/render-jwks.py:264` — `write()` byte-compares deliberately and its docstring gives the reason: *"the file's mtime is the only signal a reader has that a rotation happened, and a deploy that rewrote an identical file on every run would destroy it."* So `changed` is a true answer to *did this process touch the file*. `main()` at `:325` then reads it as an answer to *did the key set move*. **And a render makes the two come apart by construction**: `render_project` publishes into `.generated/<key>` through a staging directory (`rendering.py:2273 publish`, `:2438 render_project`), so the destination is a directory that has just been created — `destination.is_file()` is False, `changed` is True, and the sentence prints with no key having moved. That is precisely what the Session 25 trip measured on both projects. | **Run 4, and the repair is not the audit's.** Comparing the key set instead of the file would destroy the mtime signal the docstring protects. The repair is **ADR 0195's third outcome in the caller**: `wrote` / `confirmed` / *there was nothing here to compare against*, and the recreate sentence prints only for the first. `write()` is not touched. | A row whose closing act would have removed a deliberate property to fix a sentence, on the one output an operator reads during a cutover — which **Session 29 performs**. The reader is two-valued and the question has three answers; ADR 0195 is that sentence. | 0195 |
| **D1428** | Audit 1b: *"D380 — `apg-diag`'s log allowlist covers neither `auth`, `storage` nor `mcp`"*, closing act *"Widen the allowlist."* | **Measured: `bin/apg-diag.sh:65` — `readonly SERVICES="postgres pgbouncer postgrest docs edge-probe dbmate"`.** The three absent services are exactly the three that handle a credential: `auth` signs, `storage` presigns, `mcp` is the agent plane. **The file explains every other thing it withholds** — *"What it deliberately cannot show: a secret value, a container's environment, or `docker inspect` output beyond labels. `logs` passes its output through a redaction filter, which is belt to the braces of those services not logging credentials in the first place"* — **and says nothing about why those three are not in `SERVICES`.** | **Recorded, §10.** Widening it is a decision about whether the redaction filter is trusted to carry the three services whose logs could contain a token, made for a surface reached by a read-only agent through a sudoers rule (ADR 0071). It is not a list edit, and Run 1 does not take it. What Run 1 records is that **the absence is unexplained in a file that explains everything else**, which is the state in which somebody widens it believing it was an omission. | The only unexplained boundary in a script whose entire design is explained boundaries. Either it is a decision nobody wrote down, or it is an omission — and the file's own standard means a reader cannot tell which. | 0071 |
| **D1429** | Audit 1c: *"**D1276** — Studio has **no live half** for the query view's RLS off this workstation, **and** a rig that reaches a published loopback port assumes a daemon"*, closing act *"A live half that runs where the gate runs."* | **Two findings under one number, and only the second is D1276.** D1276 (Session 24 §1) is the CI fixture that reached `apg dev up`'s published loopback port: seventeen `PoolTimeout`s while `docker exec` against the same container succeeded. **It is repaired** — `cluster_address()` proves an address before building on one and reports which answered — and its *mechanism* is explicitly unestablished and reported rather than resolved (ADR 0195). The first half is a different, **unnumbered** finding: `tests/deployment/test_session24_studio.py` does carry live proofs (`pytestmark` with `requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")`; revocation through Studio, and the deployed audit read carrying a real refusal's boundary) — and **none of them is the query view's RLS.** | **Split in Run 5.** The query view's RLS live half is the row with work in it; D1276 itself is closed and its residual is a stated unknown, which ADR 0195 permits and a session may not close by asserting a mechanism. | A repaired row and an open row sharing a number is how the repaired one gets re-repaired and the open one stays open. The audit joined them with *"and"*, and the closing act it gives fits only the half that is not D1276. | 0195 |
| **D1430** | Audit 1c: *"D297 / D201 — The environment is not verified against the lock; a lock verifies only what it dereferences"*, closing act *"Verify both."* | **D297's deferral has a stated reason and the reason has expired.** Session 6 §1: the check is *"**recorded rather than built**: a gate step that compares installed distributions against the lock's pins … is a new authority over the environment, and adding one in the run that is about to collect evidence is how a gate change gets attributed to the evidence."* That is a rule about **when**, not whether. And it has since cost a gate run **twice more** — D297 on the host in Session 6 (four `ModuleNotFoundError`s, killing `session-01-check`) and **D384 in Session 7** (`boto3`, four modules, `3421 deselected, 4 errors`). Three occurrences, one per session that added a dependency. | **Run 5 takes it**, which is the run that collects no evidence — Run 9 is. The check compares installed distributions against the lock's pins and **fails with the install command**, which is the half both failures lacked: `No module named 'cryptography'` sends a reader at the test, the release or the host's Python, and the answer was a venv nobody re-synced. | The deferral was right and was written as a *when*. Nothing re-read it, so it has been read as a *whether* for twenty-two sessions, and the thing it deferred has failed three times. | — |
| **D1431** | The same audit row's second half: *"a lock verifies only what it dereferences"* (D201). | **The general repair is stated and carries a constraint the row's closing act ignores.** Session 5 §1: *"resolve package versions against their registry the way images are resolved against theirs — is Run 10's to weigh, **because it needs network access in a check that deliberately has none**."* `bin/verify-versions.sh` resolves every `images:` entry to its recorded digest; a `packages:` entry is a string nothing dereferences, which is how `SCALAR_VERSION: "1.36.4"` — a release that has never existed — survived four sessions. | **Recorded, §10, and separated from D1430.** *"Verify both"* prices two rows as one act; one is a gate step this session can write and the other needs a network in a check built to have none, which is a decision about what the version lock is for. | The two halves of one audit row have different closing acts, different costs, and one of them has a constraint that is the whole reason it was not done. Bundling them is how the cheap half waits for the expensive one. | — |
| **D1432** | Audit 1b: *"Secret generations accumulate with nothing pruning them"*, listed beside D1255 (*"`agent_audit` and `agent_idempotency` grow without bound"*) and closed the same way — *"A retention rule."* | **They are not the same kind of act.** `agent_audit` and `agent_idempotency` are tables this repository's own migrations create, so a retention policy is a released migration (ADR 0213, Run 6). A secret generation is a path at the **provider** — `secrets_contract.generation_directory()` at `:283`, `{SECRET_ROOT}/{project_key}/generations/{generation_id}` — and nothing in `src/` or `bin/` prunes one. **Pruning a generation is a provider WRITE**, on the surface whose rule is that no command in this product sets a provider value by itself (D249, and `rotate-signing-key.sh`'s own help). | **Recorded, §10.** Not taken in Run 6, and not taken in the rotation's run either — **which is the run that creates the next generations.** The decision is what makes a superseded generation disappear and who performs it, and the answer may be *an operator, by hand, with a documented reading of which generations are live*. | Two rows in one table, closed with the same three words, where one is a migration and the other is a mutation of the credential store. A session that read the table as uniform would have written a migration for a thing that has no table. | 0249 |
| **D1433** | Audit 1a: *"F-022 — A fork whose domain is in the release's files **can deploy and cannot pass the gate**"*, with the measurement *47 failures and 49 errors* from Session 27 §10. | **Not re-measurable in this checkout, and Run 1 says so rather than repeating the number.** The reading is of the adopter's fork on a host this project does not administer; this tree has no fork, and `projects/example/` is the state ADR 0198 describes rather than the one F-022 is about. The number is a record of one measurement on one tree at one commit. | **Rig 28a, in Run 2**, is the only instrument that reproduces it, and it is built for ADR 0212 anyway. **Run 1 does not carry the number forward as though it were this tree's.** F-022's paragraph (Run 3) is written from what rig 28a measures, not from the findings file's arithmetic. | Session 27 §1's own D1389 is the precedent: the findings file's *"four of §1's six checks"* was about a different set than the page it addressed, and the repair had to be aimed by measurement. A count copied from a brief into a plan is the same failure one document later. | — |
| **D1434** | `docs/upgrade-guide.md` §1.0 and this plan's own Run 2: *"an adopter who forked at 1.0.0 ran §1's first command against 1.6.0 on 2026-09-16 and `git merge` produced **nine conflicted files**, every one of them a file the release owns and the fork had amended."* | **Nine is that fork's arithmetic, not the release's.** Rig 28a amended **four** release-owned files and `git merge 1.6.2` produced **two** conflicts — `migrations/manifest.json` and `migrations/released.lock.json`, the two that are append-structured and that both sides appended to. **And `contracts/postgrest-api-surface.yaml` did not conflict at all**: the release's `1.1.0` addition landed at a different point in the file, `git` auto-merged, and the fork's own relation survived inside the release's reviewed contract with no marker and no review. | **ADR 0212 §3** states four classes with four rules rather than a file count, and the reviewed-contract rule is the one the measurement forced: *diff against the release's own copy at the tag after every merge, whether or not `git` reported a conflict.* | A rule written as *nine files* is a rule about one adopter. And the file that most needed a rule is the one that produced no conflict — ADR 0050 exists because a contract produced from the thing it constrains cannot refuse it, and a contract that acquires a relation by three-way merge is that failure arriving by another route. | 0212 |
| **D1435** | `docs/scope-closure.md` §15, the upgrade guide and two sessions: converting *"would mean re-homing applied migrations, which D912 forbids"* — the reason the question was deferred twice. | **ADR 0206's one-time ledger move already performs the conversion's cluster half.** `project_ledger_move_statement` is driven by the rendered manifest and matches **by version**. Handed a render in which the re-homed migration is declared `set: project`, it emits `INSERT … SELECT version FROM app_private.schema_migrations WHERE version IN ('20260905120031') … DELETE …` — and the control, the release's own `20260912120031`, does not appear. It was written re-runnable by construction, for D1288. | **ADR 0212 §1 step 7.** The conversion needs exactly one thing the product does not have (ADR 0210's `--follows`); the step everyone assumed was impossible needs nothing. | The mechanism that decides the question was built in Session 24 for a different reason and has been in the tree ever since, while two sessions deferred the question for want of it. *Grep every reader before deciding a thing cannot be done* is question 5 pointed the other way. | 0212 |
| **D1436** | `_assert_follows_release_version`'s own refusal, shipped in 1.6.2: *"there is no supported way forward today, and this refusal is the product being honest rather than helpful … Nothing in this release lets a set declare the release it was actually frozen against."* | **The gap is one computed line wide.** `build_lock` has taken `follows_release_version` as a parameter since ADR 0198; `bin/migrate.py::freeze_project_lock` is its only caller and always passes `newest_release_version()` — the checkout in hand. Measured on rig 28a: the re-homed set is refused at floor `20260912120032`, and with the true record (`20260904120030`, tag `1.0.0`'s newest) `verify_lock` **PASSES** the same set unchanged. The release manifest is append-only, so a declared value is checkable against it. | **ADR 0210** takes the operator declaration, keeps the refusal byte-for-byte, and adds `follows_release_version_source` so a reader can tell a computed record from an asserted one (ADR 0195 applied to a field). | A refusal that says no way forward exists, about a gap that is a missing argument, reads as a design limit. And the sentence becomes **false** in the commit that adds the flag — Run 3 owes the message, not a follow-up (D1116). | 0210 |
| **D1437** | `0006-app-runtime-least-privilege.sql`'s header measurement, which ADR 0211's whole argument rests on: `has_table_privilege(app_runtime,'app.notes','SELECT')` → **true**, `SET ROLE app_runtime; SELECT * FROM app.notes` → **denied**. | **It measures a table that existed BEFORE the revoke, and F-013 is about a fork's table created after it.** Re-measured on the pinned `pgvector/pgvector:pg18` (**18.4**, the deployment's own version) with a control the revoke cannot reach: `app.notes` (before) **denied**, `app.invoices` (created and granted AFTER the revoke) **denied**, `tenant_control.invoices` (schema never revoked) **0 rows, permitted**. `has_table_privilege` answers `true` for all three. | **ADR 0211** carries the table. The refusal of F-013's one-line widening rests on a measurement of the case the finding is actually about, not on an extrapolation from the release's own. | The argument that declines to widen a security boundary is the last argument that should rest on *it probably works the same way*. The control coming out green in the same invocation is what makes the two denials evidence (D499). | 0211 |
| **D1438** | Nothing said it. D1096: *"the ledger is the only record of which bytes ran."* | **A conversion that changes a template's bytes is invisible to the ledger.** `ledger_insert_statement` writes `ON CONFLICT (version) DO NOTHING`, so the row for an already-applied version keeps the `rendered_sha256` of the bytes that ran. Grepped every reader: `bin/doctor.py` counts rows, `bin/apg-diag.sh` lists version and name, `test_dev_environment_cluster` compares digests on a **fresh** cluster it built itself. **Nothing on a deployed host compares a ledger row against the tree**, and after a conversion no checkout contains those bytes. | **ADR 0212 §4**: the operator records the divergence in the project manifest entry's `description` — which line was removed, and why it could not alter the cluster — because the ledger cannot carry it and is right not to. | The ledger is correct as history and stops being checkable as a record, silently, which is the D600 shape: a value that looks measured. ADR 0212 permits the byte change in exactly two cases and this row is why each one has to be written down. | 0212 |
| **D1439** | `docs/upgrade-guide.md` §1.0: *"the collision is structural rather than bad luck: the release occupies `0031` at 1.1.0 and `0032` at 1.5.0 in the same template directory a 1.0.0-era fork was obliged to write into."* | **The collision is not on the filename.** Measured: `0031-create-task.sql` and `0031-tenant-invoices.sql` coexist in one directory after the merge and `git` never conflicts on either — different names, nothing to merge. What is actually unique across sets is the **version**: `rendering.assert_migration_order` refuses a shared version and nothing else, because `app_private.migration_ledger` keys on the version alone and is written `ON CONFLICT (version) DO NOTHING`, so two sets sharing one would apply both and record one (D1096). | **ADR 0212 §3's fourth class**: template bytes do not conflict, and the check is for a shared version rather than a shared number. | A reader repairing a *filename collision* renumbers templates — which moves no version, fixes nothing, and changes the bytes of applied migrations to do it. The sentence describes the right problem in the wrong units. | 0212 |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**It adds requirements and claims, and that is what moves `CURRENT_SESSION`.**
Session 27 added nothing and moved `VERSION` alone; this session lands a released
migration, a declaration an operator makes, and a reading before a tag — each of
which is a property somebody outside could check, so each earns a requirement,
and each new requirement gets its own claim (ADR 0089, D697).

**`CURRENT_SESSION` moves 25 → 28.** 26 and 27 have no session number in the
evidence model and never will, the way 19 has none — the skip is the record
(D1063), and the constant's own comment is where it is written. Every gate
selector and `claims_through_session(28)` inherits the cumulative set.

Four requirements, four claims, and the exact ids are Run 9's to register
against the file rather than this plan's to invent (D1347's lesson: a count in a
plan's prose is not a count of the file):

| Subject | Requirement | Claim | Mode |
|---|---|---|---|
| The record a project set carries of the release it was frozen against (ADR 0210) | one `DX-*` | its own | **offline**, declared in `OFFLINE_CLAIMS` (ADR 0202) — it is a property of a checkout and no deployment confirms it |
| What the agent record keeps, and for how long (ADR 0213) | one `SEC-*` or `AGENT-*` | its own | **host**, `not_run` until Session 29 applies the migration. The offline half proves the function and the refusals; the live half proves the prune against a cluster with history |
| The reading before a tag (ADR 0214) | one `REL-*` | its own | **offline** |
| The host interpreter, if Run 3's ADR 0158 reading takes a third mode (D1418) | one `DX-*` | its own | **host**, `not_run` until Session 29 |

**No new claim for the rotation**, and this is worth saying because it is the
session's headline act. `bootstrap_identity`, `api_authorization` and
`credential_rotation_planes` already exist and are `not_run`. Session 29's trip
moves them to `passed` by **running the proofs that are already registered**.
A claim added for a rotation would be a claim about the rotation having been
planned, which is the thing ADR 0163 exists to refuse.

**`bin/session-28-check.sh` is owed**, in Run 9, with the three modes
(`offline`, `host`, `external`) and Session 25's shape. Its `--kit-dir` **stays
on `kit-2026-09-11`** — D1282, re-read and still true, and Run 5 is where the
proof is made to state its own premise so the trap cannot be sprung silently.

---

## 4. Irreversible operations

**None. This session has no irreversible act, and that is a decision rather than
an accident** (D1425).

- **No tag.** `1.7.0` is cut in Session 29, on the commit that was deployed,
  after ADR 0214's reading. A tag can be deleted and cannot be un-published, and
  the three occurrences of D1033's class all begin with a tag cut at the wrong
  moment.
- **No deploy, no migration applied anywhere.** Run 6 writes a released
  migration; nothing applies it here. Rig 28b applies it to a throwaway cluster
  with history and destroys it.
- **No rotation.** Run 8 **rehearses** it and writes Session 29's sheet. The
  rehearsal runs against `apg dev` and a rig, never against a deployment.
- **No provider write.** `bin/rotate-signing-key.sh`'s own help is explicit that
  no command in it sets a provider value (D249); the rehearsal does not either.

**The one irreversible act this session prepares** is `promote`, in Session 29:
each project publishes exactly one verification key (ADR 0170), a key cutover
recreates all four verifiers (ADR 0155), and `bin/rotate-signing-key.sh`'s help
says *"After promotion there is no way back — the recovery is to complete
forward."* It is a human at a TTY, as root, and Run 8's sheet is what they hold.

Everything this session does is reversible by `git`.

---

## 5. Build order, run by run

Each run ends `**Done.**` with what it measured. **A targeted list is derived
from the diff, not copied from this plan**, and CI is the full check. The gate
runs once, in Run 9, on a clean tree. Runs allocate `D` numbers from **D1426**.

### Run 1 — what the audit says is open and the tree says is decided

Re-measure all 36 Tier 1 rows against `ad96673`, in both directions, and write
§1's table. The thirteen rows D1407–D1418 and D1420 are the ones planning already
found; **the run's job is to find the rest, and to be wrong out loud where
planning was wrong.**

For each row, three questions in order: *does the subject exist as the row
describes it*; *does the tree already carry the row's own alternative*; *is the
row's closing act the one the measurement supports*. A row that fails the third
question is the expensive kind — D1411 would have widened a security boundary
and D1416 would have undone an ADR 0195 decision.

Then write the rows down where a reader will meet them: each struck row gets its
sentence in `docs/scope-closure.md` §16 (this session's section) with the command
that shows it, and `docs/pre-stage-4-audit.md` gains a dated note at its head
saying which rows this session struck and why — the page says of itself that it
*"does not track the current release and is not held to it by a test"*, so the
note is how it stops being read as current.

**Nothing runs before the push** (documentation only), and **nothing waits on
CI**: a documentation commit is pushed, said to be pushed, and left. CI still
runs on GitHub — measured on both of this session's commits, one workflow each,
both `success` — and nobody reads the verdict for a documentation push unless
the operator asks. **This is a standing instruction the project has broken four
times** (Sessions 26–27 at `c5ad14d`, `7032f82`, `90d7b34`, and this run at
`cbccb0e`), every time by starting a background poll on the pushed SHA. It
applies to Runs 1 and 2, which are the documentation-only runs.

**Done.** 2026-09-16, on `9bd5ed8`. All 36 Tier 1 rows measured in both
directions; the nine planning had not reached produced **D1426–D1433**, and four
of the eight changed a later run's description rather than only this table.

*What the run measured, and what changed because of it:*

- **A fourteenth row is already answered, and it is the dangerous one.** D1045's
  closing act is *"report the body, or say why not"*; the code says why not at
  the discard — `bin/bootstrap-providers.py:370-373`, *"on identity endpoints it
  can echo the request, and this message reaches a log"* — which is §6's own
  non-negotiable. **Run 4 no longer decides this**; it adds one clause saying a
  body was read and dropped, and prints no body (D1426).
- **D1374's closing act was wrong and would have removed a deliberate
  property.** `write()` byte-compares *because* the mtime is the only rotation
  signal a reader has; the defect is that `main()` reads a two-valued answer as
  an answer to a three-valued question, and a fresh render makes `changed`
  always true. **Run 4's repair is now the caller's third outcome, not the
  comparison** (D1427). This matters to Session 29, which reads that sentence
  during the cutover.
- **The audit's D1276 row is two findings** (D1429). D1276 is repaired and its
  mechanism is a stated unknown; the query view's RLS having no live half is
  unnumbered and is the half with work in it. Run 5 takes the second only.
- **D297's deferral was written as a *when* and has been read as a *whether***
  for twenty-two sessions, while failing three times (D297, D384, and Session 6's
  host gate). **Run 5 takes it** — Run 5 collects no evidence, which is the
  condition the deferral named (D1430).
- **Three rows moved to §10 rather than into a run**: D1428 (`apg-diag`'s three
  absent services are the three that handle a credential, and the absence is the
  only unexplained boundary in a file of explained boundaries), D1431 (D201's
  repair needs a network in a check built to have none), D1432 (a secret
  generation is a provider write, not a migration — it was sitting beside D1255
  and closed with the same three words).
- **F-022's *47 failures and 49 errors* is not this tree's number** (D1433) and
  is not carried forward as though it were. Rig 28a is the instrument.

*Written where a reader meets it*: `docs/scope-closure.md` §16, one sentence per
struck row **with the command that shows it**; and a dated note at the head of
`docs/pre-stage-4-audit.md` naming what Session 28 struck, because the page says
of itself that it is not held to the tree by a test and would otherwise keep
being read as current.

*Nothing ran before the push.* Documentation only.

### Run 2 — the on-ramp, decided: three ADRs and the fork that proves them

**Rig 28a: a synthesized pre-ADR-0198 fork.** A throwaway clone at tag `1.0.0`
(measured in D1419 to have no `projects/`), given a tenant table in
`migrations/templates/`, a row in the release's `manifest.json` and
`released.lock.json`, and operations in the shared reviewed surface — the fork
the adopter actually built, reproduced from the tag rather than described. It is
a rig and a control: the same clone with the tenant objects in
`projects/<slug>/` at `1.6.2`, which is the end state ADR 0198 describes.

Three ADRs, each deciding something different, and none of them the same
question:

- **ADR 0210 — the record a project set carries of the release it was frozen
  against.** What `follows_release_version` is *for*, now that ADR 0206 has made
  it a record rather than a guard (D1412), and who may write it. Alternatives to
  weigh with the rig: the operator declares it; it is derived from the installed
  deployed document; the refusal is removed. **It is not a flag decision.** The
  ADR states which of the three it takes and what a set that declares a false
  record can do — because a record nobody can check is a record that reads as
  measured.
- **ADR 0211 — which platform identities a project's SQL may name.** D1411's
  measurement is the whole input: `0003` grants to `app_runtime` and `0006`'s
  schema revoke makes the grant unreachable, so the lint's allowlist is correct
  and the release's own example is what misleads. The ADR decides between
  leaving the allowlist alone and repairing the refusal's message and the
  README's pointer; removing `0003`'s dead grant by fix-forward; or admitting
  `app_runtime`, which `CLAUDE.md` §6 calls weakening and which the ADR must
  refuse in writing if it refuses it at all.
- **ADR 0212 — how a fork made before `projects/<slug>/` enters it, or that it
  does not.** Two halves. The **conversion**: measured on rig 28a, what happens
  when a tenant's applied migrations are re-homed — D912 forbids amending them,
  and ADR 0206's one-time ledger move matches rows **by version**. The
  **merge-conflict rule**: the nine conflicted files the one recorded upgrade
  produced, sorted into classes, with a rule for which side wins each — and two
  of them are generated artefacts carrying digests, where *resolve by hand* and
  *a released migration is never amended* pull opposite ways. **The ADR is
  permitted to decide that no conversion exists** and to say what a 1.0.0-era
  fork does instead.

ADRs and the index only; no product code. `docs/decisions/README.md` gains three
entries. **Nothing runs before the push and nothing waits on CI** — Run 1's rule,
which this run is the second and last to be covered by.

**Done.** 2026-09-16, on `2db97a5`. Rig 28a built and measured end to end;
**ADR 0210, ADR 0211 and ADR 0212** written and indexed; **D1434–D1439**.

*Rig 28a, built and what it measured.* A clone at tag `1.0.0` on a branch `fork`,
given `migrations/templates/0031-tenant-invoices.sql` (copying `0003` faithfully,
`{{app_runtime}}` grant included), a row in `migrations/manifest.json`, a row in
`migrations/released.lock.json` written by the release's own `freeze-lock`, and a
relation in `contracts/postgrest-api-surface.yaml` — the four places §1.0 says
such a fork had to write. Then `git merge 1.6.2`, resolved the way the one
recorded upgrade resolved it, then re-homed into `projects/tenant/`. Its control
is the same clone's `1.6.2` side, where `projects/example/` is the end state ADR
0198 describes. Rebuilt from `/tmp/r2-rig-a*.sh` (copied to the scratchpad); it is
deterministic from the two tags and nothing about it is committed.

- **The conversion exists, and the blocker everyone named is not the blocker.**
  Re-homing moves no bytes (`git mv`, *1 file changed, 0 insertions, 0 deletions*)
  and no version, so D912 is not engaged by it. What blocks it is one computed
  line in `freeze_project_lock` (D1436) — and ADR 0206's ledger move already does
  the cluster half, by version, for free (D1435).
- **What the lint forces is the real boundary.** A 1.0.0-era set that copied
  `{{app_runtime}}` cannot pass `lint_project_set`, and satisfying it moves
  `template_sha256` and `canonical_render_sha256` of a migration that has already
  run. ADR 0212 decides that case by what the change would do to a **cluster**:
  two byte changes that provably cannot alter one are permitted in place and
  recorded; everything else is a new migration; a set that can reach neither does
  not convert, and staying a fork stays supported.
- **F-013's one line is refused in writing** (ADR 0211), on a measurement of the
  case the finding is about rather than the release's own (D1437).
- **The merge rule is four classes, not a file count** (D1434), and the class that
  needed it most produced no conflict at all.

*What Run 2 deliberately did NOT do.* No product code, no test, no edit to
`docs/scope-closure.md` §15 or to `docs/upgrade-guide.md` §1.0 — both become false
only when ADR 0210's flag exists, and Run 3 owns the flag, the refusal message
`_assert_follows_release_version` still ends with, and both pages in one commit.
**No conversion was performed against a cluster carrying a fork's history** (D940);
ADR 0212 names step 7 as the step a checkout cannot prove.

*Nothing ran before the push.* Documentation only — `test_acceptance_registry`
and `test_documentation_index` are run because three ADR files and an index row
are what they read, and nothing waits on CI.

### Run 3 — the on-ramp, built, and the two readings an adopter is missing

What ADR 0210 and ADR 0211 decided, in the code, plus the two adopter-facing
readings the findings file left open:

- **ADR 0210's declaration**, in `migrations.py` and `bin/migrate.sh`'s usage,
  with the refusal's message rewritten from the decision rather than from the
  old rationale. Session 27 Run 3 already replaced the refuted rationale in three
  places (the docstring, `--help`, and the refusal text); **all three move
  again**, and `grep` for the moved TEXT as well as the moved name (D1187).
- **ADR 0211's refusal**, naming `0006` and what it revokes, so an adopter who
  meets it learns why the grant they copied would not have worked.
- **F-020 / D1423**: `upgrade check` reports the commit, with ADR 0195's third
  outcome for a checkout that is not a git working tree — which is the case an
  adopter's tarball fork is actually in.
- **F-022's paragraph**: what an adopter does about a fork that can deploy and
  cannot pass the gate. Writable now that ADR 0211 and ADR 0212 exist, and not
  before — the findings reply says so (*"causes 1 and 2 persist only while the
  domain is in the release's files, and F-012 and F-013 are why it cannot leave
  them"*).
- **D1418**, only if ADR 0158's split admits a third reading. If it does not,
  the row is recorded in §10 with the split as its reason and nothing is edited.

**`docs/on-ramp.md`** is the new page: ADR 0212's procedure, or its statement
that no conversion exists and what to do instead. **`docs/README.md` gains its
line** — `test_documentation_index` goes red otherwise, which is the constraint
working. Targeted: the migration modules, `test_cli_contract` (a `bin/` command's
usage moves), `test_documentation_index`.

### Run 4 — the readers that report a file event as a domain event

ADR 0195's class, in three product readers, with the rule that **a decision may
fail closed and a report may not**:

- **D1374, as D1427 measured it and NOT as the audit writes it.** `render-jwks`
  prints *"the key set CHANGED: every verifier must be RECREATED"* whenever
  `write()` returns `True` — and `write()` byte-compares **deliberately**, because
  the file's mtime is the only signal a reader has that a rotation happened.
  A render publishes into a directory that has just been created, so
  `destination.is_file()` is False and `changed` is True with no key having
  moved; that is what the Session 25 trip measured on both projects. **The
  repair is ADR 0195's third outcome in the caller** — `wrote` / `confirmed` /
  *there was nothing here to compare against* — with the recreate sentence on the
  first alone. **`write()` is not touched**: comparing the key set instead of the
  file, which is what the audit asks for, destroys the property its docstring
  protects. The proof is a render into a fresh directory with an unchanged key,
  and a control that is a genuine key change. **It lands before Session 29
  rotates**, because step 2 of the cutover is the one place this sentence is read
  for a decision.
- **D1045 is answered and this run adds a clause, not a decision** (D1426).
  `bin/bootstrap-providers.py:370-373` already says why the body is not
  included — *"on identity endpoints it can echo the request, and this message
  reaches a log"* — and the status is reported. The residue is that an operator
  cannot tell *the provider explained itself and we refused to repeat it* from
  *the provider said nothing*. One clause, and **no body is printed**.
- **D387** — the REST document observation does not retry, and Session 7's row
  names the consequence precisely: *"a lost race makes the deployed document
  understate a working deployment — and a claim computed from it would be wrong
  in the safe-looking direction."* `routes.app` and `routes.storage` already
  retry through `observation.await_observation`; this one reader does not. The
  run either gives it the two-stage convergence its neighbours have, or
  distinguishes *the service cannot serve its document* from *the edge had not
  finished attaching* — which the field three away already does.

**D1413** is decided here too: a caller for `mcp_tracing.configure()`, or its
deletion, or the network question written down as the reason for neither. The
spans at `mcp_tools.py:773` are what the decision is actually about.

Targeted: the modules the diff touches, once, at the close.

### Run 5 — Tier 1c, and it gets the run to itself

**The category `CLAUDE.md` §7 says this project keeps producing: a value that
looked measured and was not.** Scattering these across the other runs is how the
class survives, so they are one run and each is asked §7's first question —
*what would have to break for this to go red* — before anything is written.

- **D1421 / D1240** — the four unswept modules, per module and measured:
  `--setup-plan` under each sweep's own selector before and after. Two of them
  import from the service tree and may be a genuine *why not*. D1242's
  sweep-selector guard is in the targeted list, and every module that gains a
  marker carries `pytestmark` before its first test (D1240's own rule).
- **`test_honest_readers`' `sudo -u` re-entry branch**, which has still never
  run. `tests/contract/checkout_owner.py` is where the decision lives and both
  modules import it; D1310 is the precedent for showing it offline in a
  container running as uid 0, which is the identity the gate has. Running it is
  the point — this is the thirteenth-never-executed-proof position and twelve of
  the first twelve failed on first execution.
- **D1422 / D464** — the stated limit with a test: what `_COMMAND` can and
  cannot see, against fixtures carrying a flag and a backslash continuation.
  **Not a parser.**
- **D1282** — the kit trap. `REC-KIT-003`'s proof `pytest.fail`s on the version
  gap, so aiming `--kit-dir` at the newest kit destroys the proof **without
  failing**. The repair is the proof stating its own premise, so that a kit at
  the tree's own outputs version makes it go red rather than green.
- **D1414** — Session 9's four success assertions, onto the module's `refused()`
  shape.
- **D1420's two premise assertions** — the two `capabilities_sha256` are
  different quantities; `app-openapi.canonical.json` is ASCII.
- **D942** — ADR 0175's two blind spots, both measured by a host trip and
  neither guarded: an HTTP body naming an RPC's parameters, and a
  `GRANT … ON FUNCTION` signature. Widened against the definition rather than
  against the two instances (D600, D918, D926).
- **D1430 / D297 — taken, not recorded, and Run 5 is where the deferral said to
  take it.** The check compares installed distributions against the lock's pins
  and **fails with the install command**. The deferral's stated reason was that
  a new authority over the environment must not be added *in the run that is
  about to collect evidence*; Run 9 is that run and Run 5 is not. It has cost a
  gate run three times (D297, D384, Session 6's host gate), each time in
  collection, each time naming neither cause nor remedy.
- **D1431 / D201 — recorded, §10, and separated from D1430.** Resolving a
  `packages:` entry against its registry needs a network in a check built to
  have none. That constraint is why it was deferred and the audit's *"verify
  both"* does not carry it.
- **D1429's live half** — the query view's RLS, which `test_session24_studio.py`
  does not prove although it carries live proofs for revocation and the audit
  read. **D1276 itself is closed** and its mechanism is a stated unknown that
  ADR 0195 permits; this run does not re-repair it and does not assert a
  mechanism for it.
- **The uncached first run of `apg dev up`** — recorded, with `scope-closure.md`
  §11's reason restated: measuring it here means evicting the image the whole
  contract suite shares, and CI already times it on a fresh runner. **The row
  asks for it to be measured where it is claimed, and the envelope's
  `UNMEASURED` list is where it is claimed.** If that reading holds, the row
  closes by saying so; if it does not, it is §10's.

**Every test written in this run gets a battery** — `PYTHONDONTWRITEBYTECODE=1`,
caches cleared first, anchors pre-flighted to match exactly once with a miss
fatal (D269), a paired control the mutation cannot reach and green in the same
invocation (D499), and `FAILED` asserted rather than `ERROR` (D386). Restore by
copy and `cmp`, never `git checkout --`. `test_acceptance_registry` runs because
test functions are added and renamed (D1119).

### Run 6 — what the agent record keeps, and for how long

**One released migration, and it is the only schema this session moves.**
`app_private.agent_audit` and `app_private.agent_idempotency` grow without bound
and three migrations say so about themselves — `0020`: *"What is NOT here:
retention. Nothing prunes `app_private.agent_audit`"*; `0032` repeats it;
`0028`'s quota table solved its own case by `ON DELETE CASCADE` and wrote down
why that does not generalise.

**ADR 0213 decides the policy, and the policy is not a timer.** The shape to
weigh first, because it is the one that adds no new authority: a SECURITY
DEFINER prune function granted to nobody the caller can reach, plus the counts
in `bin/doctor.sh`'s deployed mode so an operator can see the growth — rather
than an automatic deletion nothing asked for. A migration that silently deletes
an audit record is a migration that destroys the evidence ADR 0135 exists to
keep, and the ADR says which it is choosing and what an operator must do to make
a row disappear.

**Rig 28b: a cluster with history.** D940's rule — *a migration over a table
with history must be proved against a cluster with history* — so the rig seeds
both tables across the shapes the plane actually writes (a served call, a
refused call carrying `denial_reason`, a claimed idempotency key) and applies the
migration over them. `bin/migrate.sh freeze-lock` after, and the ledger read
rather than the migrator's line (D941).

Targeted: the migration modules, `test_database_function_signatures` (its subject
moves, and D1421 may have just given it a marker), the agent-plane contract
modules. **Nothing is applied to a deployment.**

### Run 7 — the reading before a tag

**ADR 0214**, deciding command or checklist (D1424). The measured argument is on
the page: a checklist existed in prose at `1.0.0` and the session that wrote it
did not follow it; a test cannot see a tag cut after CI is green and ADR 0209
says so. What is missing is the question asked out loud at the moment it is
answerable — *is this commit the one the tag goes on*, and *what has landed since
the last tag*.

If the ADR takes a command, it is a `bin/` verb that lists what is about to be
tagged and what has landed since the last tag, importing only
`agentic_postgres` and `yaml` (ADR 0093), and `test_cli_contract` runs with the
command `git add`ed first (D1014, D1188). If it takes a checklist, the ADR says
why a command would not have been followed either, and the checklist lands where
Session 29 will actually be standing — in this plan's §5 Run 9 and in
`docs/operator-guide.md`.

**Either way the requirement and the claim are registered in Run 9**, and the
first use is Session 29's tag.

### Run 8 — the rotation, rehearsed, and Session 29's sheet

**The rotation gets its own run because it is the one credential path in this
product that has been built, tested and never run.** Offered and declined at four
trips; decided on 2026-09-16; performed in Session 29.

Walk `bin/rotate-signing-key.sh`'s seven steps end to end against something that
is not production, and write down what each one printed:

1. The new key at `APG_AUTH_JWT_PREPARED_KEY` **by hand** — no command here
   writes a provider value (D249).
2. Redeploy; `render-jwks.py` publishes the prepared key's public half beside the
   active one. **This is where Run 4's D1374 repair is first read for a
   decision**, so the rehearsal is also that repair's live proof.
3. Down and up, so every verifier is **recreated**. A restart is not enough — a
   running PostgREST never re-reads its key set, and after the file is replaced a
   restart is measured to leave the container unable to start at all (ADR 0155,
   `jwt_keys.py:316`).
4. `acknowledge` — what each verifier actually holds, from its **running
   container**.
5. `promote` — refused unless step 4 came back clean. **Irreversible.**
6. Move the promoted key to `APG_AUTH_JWT_SIGNING_KEY`, clear the prepared slot,
   redeploy.
7. After the deadline, `retire`, then redeploy and recreate.

**What the rehearsal is for**: the three `not_run` claims —
`bootstrap_identity`, `api_authorization`, `credential_rotation_planes` — have
proofs already registered, and a rehearsal that does not run them is a rehearsal
of the commands rather than of the evidence. Run them against the rig and record
which passed, so Session 29 knows what a red one means.

**The deliverable is Session 29's numbered sheet**, in this plan's §5 as a Run 9
appendix entry and in `docs/operator-guide.md`: the `op`-side steps the agent
runs over SSH, and the `sudo` lines a human at a TTY runs, in order, with the
timing nobody has ever measured (the cutover, ADR 0122's rotation repairs, and
the agent plane's round trip — all named in Tier 2 as never timed). **Alpha
first, then beta**, and the sheet says what to do if alpha's `acknowledge` comes
back dirty.

### Run 9 — the bump, the registry, the gate, and the close. No tag.

`VERSION` **1.7.0** and `CURRENT_SESSION` **28**, in one commit with everything
the bump owes:

- **ADR 0162 prices the class.** A minor: a released migration that is additive,
  a new declaration on `freeze-lock`, a new `bin/` verb if ADR 0214 took one.
  If `upgrade plan` prices it above `patch`-or-`minor`, the class is re-decided
  before the commit, not after.
- **Both release pages' tables gain a row for `1.7.0`, in the bump's own
  commit** — ADR 0209's guard is what makes this red otherwise, and ADR 0208's
  *Consequences* named the gap that ADR 0209 closed. `docs/upgrade-guide.md` and
  `docs/operator-guide.md` are `RELEASE_PAGES`.
- **`apg generate` regenerated and committed in the same commit** (D1238): the
  client's `templateVersion` is derived from the release, so every bump owes it.
- **`bin/session-28-check.sh`**, three modes, Session 25's shape, `--kit-dir` on
  `kit-2026-09-11` (D1282) with the flag's help still saying so.
- The registry's four requirements and four claims (§2), the offline claims
  **declared** in `OFFLINE_CLAIMS` and never inferred (ADR 0202).
- Derived documents regenerated: the acceptance matrix, the bounds doc, the MCP
  catalog, the evaluation report, `bin/app-contract.sh --check`,
  `bin/mcp-contract.sh check`, `bin/migrate.sh freeze-lock`.
- `docs/scope-closure.md` §16 — what Session 28 left open — and `CLAUDE.md` §2's
  Session 28 block.

**`bin/session-01-check.sh` runs once, on a clean tree, before the push**, and
`bin/session-28-check.sh --mode offline` writes `evidence/session-28-offline.json`.
Then `git diff --stat` against this plan's list, one line each, **before** the
push — a commit message is not evidence that the diff contains what it says
(D1116). Then CI's verdict on that commit by full SHA.

**And then nothing.** No tag. Session 29 deploys this commit, sweeps, and tags it.

---

## 7. Evidence

**One half, and it is the offline one.** `bin/session-28-check.sh --mode offline`
writes `evidence/session-28-offline.json` at Run 9's commit, carrying this
session's offline claims and the cumulative set through 28.

**The host half is Session 29's**, and the claims it will move are named now so
the trip is not surprised:

| Claim | Now | After Session 29's trip |
|---|---|---|
| `bootstrap_identity` | `not_run` | **passed**, by the rotation performed |
| `api_authorization` | `not_run` | **passed**, by the rotation performed |
| `credential_rotation_planes` | `not_run` | **passed**, by the rotation performed |
| `deployment_convergence` | `not_run` | depends on what the trip exercises |
| `port_allocation` | `not_run` | depends on what the trip exercises |
| `stage_release` | **passed offline, red live until the deploy** | passed, because the trip deploys before it sweeps |
| `documented_path` | **failed** | **still failed.** Tier 3 |
| `replacement_host_restore` | `not_run` | **still `not_run`.** By decision (D1028) |
| the new `agent_record_retention` claim | — | `not_run` here, passed there |

**`stage_release`'s live half is red for the whole gap between Run 9 and Session
29's deploy, and that is by construction** (D1425). It is the third occurrence of
D1401 and the last one that should happen, because the tag now waits for the
deploy.

**`documented_path` stays `failed`, and Session 28 must not make it look
otherwise.** It is the only `failed` claim this project has ever written, and the
audit's own closing line is the rule: *a session that repairs what the readers
found and then declares victory without a third reader has not closed it — it has
gone back to the state where the status had never been emitted at all.* This
session repairs documentation the walks touched. **It does not re-run
`dx-record check` against its own prose and call the result a walk.**

---

## 8. Security invariants this session touches

**Three, and two of them are the reason ADR 0211 exists.**

1. **A project's SQL names no platform identity but the request roles and its own
   database.** `PROJECT_PLACEHOLDER_SOURCES` is seven entries and the lint's
   docstring is the standard: *"Every refusal here is a boundary, not a style
   rule … A lint that could be configured is a lint an adopter would configure."*
   **ADR 0211 may not widen it to admit `app_runtime`** — `CLAUDE.md` §6 calls
   loosening an allowlist to a subset check weakening, and D1411 measured that
   the grant an adopter would gain is one `0006` makes unreachable anyway.
2. **A released guard is removed by a decision, not by an implementation.**
   ADR 0206 left `_assert_follows_release_version` standing deliberately. ADR
   0210 may remove it, keep it, or make it declarable — and it says which, in
   writing, with what a false declaration can do.
3. **The audit record is evidence, and a migration that deletes it silently is a
   migration that destroys evidence** (ADR 0135, ADR 0142). ADR 0213 states what
   makes a row disappear and who can make it happen; the grant goes to
   `auth_service` or to nobody, on `0020`'s reasoning, and never to a request
   role.

**Carried and not touched:** F-022's residual — a fork whose relations are in the
release's **shared** reviewed surface thereby puts `<relation>:read` and
`<relation>:write` into the scope vocabulary the release offers **every**
project, because ADR 0200 derives the vocabulary from that surface. Nothing
grants those scopes and nothing is reachable, and the repair is the on-ramp
rather than a lint. ADR 0212 is where it is named.

**What this session must not do**, repeated in §9: widen the project-set lint,
loosen any surface equality, weaken a contract test to make a fork's tree pass,
or re-stamp an applied migration.

---

## 9. Stop conditions

- **No host trip, no deploy, no rotation performed.** If a repair turns out to
  need one, it moves to Session 29 rather than growing this session.
- **No tag.** Not on the bump commit, not at the close, not "so the release
  exists". D1425 is the whole reason the session is shaped this way, and cutting
  one here reproduces the class three times over.
- **No applied migration is re-stamped, and nothing this session writes advises
  one** (D912). ADR 0212 may decide that a conversion requiring it does not
  exist; it may not decide to do it.
- **No contract test is weakened.** If a proof would have to be loosened to admit
  a fork's tree or a page, stop — that is an ADR and the subject is what moves.
  Widening an allowlist to a **measured** set is not weakening; loosening it to a
  subset check is.
- **A measurement that contradicts this plan changes the plan.** Planning already
  found thirteen rows where the audit's closing act is not the one the
  measurement supports; Run 1 will find more, and two of the thirteen would have
  been active harm.
- **If Run 2's rig says the on-ramp needs a cluster with history to decide**, ADR
  0212 splits to Session 29 or 30 and Runs 3–9 proceed without it. ADR 0210 and
  ADR 0211 do not depend on it, and F-022's paragraph is written from those two.
  **Say so in §10 rather than shipping a procedure nobody measured.**
- **If ADR 0213's rig cannot seed a cluster with history**, the migration does not
  ship. A retention migration proved against an empty table is D940 exactly.
- **If `bin/session-01-check.sh` is not exit 0 on a clean tree at Run 9**, the
  bump does not land. The gate's last lines are its least executed code (D1199).
- **The rehearsal in Run 8 runs the three claims' proofs, not just the
  commands.** A rehearsal of the commands is not evidence that the evidence works.

---

## 10. Open items this session carries and creates

### Deferred by name, with the reason — ten rows

Each of these is a Tier 1 row this session does **not** close. The brief's rule
is that a plan which silently drops rows is worse than one that names them.
**Seven were named at planning; Run 1's measurements added three more** (8–10),
and each of those three was deferred for a reason the audit's row does not
carry.

1. **D1203 — one canonicalizer for `app-openapi.canonical.json`.** The tree's own
   position: *"a decision for a session that versions that snapshot rather than a
   defect now."* Run 5 takes the premise assertion (the document is ASCII) so the
   day it stops being true is loud.
2. **D930 — the two fields named `capabilities_sha256`.** Renaming the one in the
   rendered document moves the outputs schema to v19 and owes a migrator. A
   schema session's act. Run 5 takes the premise assertion (they are different
   quantities).
3. **D1248 — `GET /admin/audit`'s window, outcome filter and cursor.** New
   capability, not a defect, and it moves a released function's arity in a
   session whose purpose is soundness — which is exactly what `0032` declined to
   do, with its reasons written down. Stage 4's.
4. **D340 — every service role reaches the `postgres` catalog.** Closing it
   inverts a passing contract test and touches every role in every session
   (D1415). The exposure is catalog metadata and never project data, proved
   separately.
5. **D1275 / D1274 — Studio's role model.** Both rows' *stated* subjects are
   answered in the code under ADR 0195 (D1416). What is open is whether a human
   should ever hold both an administrative scope set and a data role, which is a
   question about the project's role model and is Stage 4's.
6. **`tests/deployment/conftest.py` at 2,101 lines.** A mechanical split, and the
   act most likely to create another module outside every sweep — which is
   D1240, the row two rows above it in the same table. It is taken in a session
   that can afford `--setup-plan` across every selector afterwards.
7. **D99 — `PYTHON_RUNTIME_IMAGE` is a rolling minor tag.** The genuinely
   unpinned surface that D1417's row bundles with the fail-closed apt pin. A
   pinning policy, and a decision about digest-pinning a base image.
8. **D1428 — `apg-diag`'s `SERVICES` excludes `auth`, `storage` and `mcp`.**
   Measured: those are exactly the three services that handle a credential, and
   the absence is **the only unexplained boundary in a file that explains every
   other thing it withholds**. Widening it is a decision about whether the
   redaction filter is trusted to carry them on a surface a read-only agent
   reaches through a sudoers rule (ADR 0071) — not the list edit the audit
   prices. Left open **with the ambiguity named**, so the next reader does not
   widen it believing it was an omission.
9. **D1431 — resolving a `packages:` entry against its registry** (D201's general
   repair). It needs network access in a check that deliberately has none, which
   is the reason it was deferred in Session 5 and which the audit's *"verify
   both"* does not carry. D1430's half is taken in Run 5; this half is a decision
   about what the version lock is for.
10. **D1432 — secret generations accumulate.** Sitting beside D1255 in the audit
    and closed with the same three words, and it is a different kind of act: a
    generation is a path at the **provider**, so pruning one is a provider write
    on the surface whose rule is that no command in this product sets a provider
    value by itself (D249). **Not taken in the rotation's run either — which is
    the run that creates the next generations**, and the trip should know that it
    adds to a set nothing prunes.

### Created here, for Session 29 — the trip

- **The rotation, performed.** Run 8's sheet, alpha then beta, `promote`
  irreversible, and the three claims' proofs run in the same sweep.
- **The deploy that moves both projects to `1.7.0`**, before the sweep, which
  every trip already does — and which is what makes `stage_release` green and the
  tag cuttable.
- **`1.7.0` tagged**, on the deployed commit, after ADR 0214's reading.
- **The migration from Run 6 applied**, with the ledger read rather than the
  migrator's line (D941), and the counts recorded.
- **The rest of Tier 2, which only a host answers**: D1375 (`op` cannot reach the
  Docker socket, so the host's offline half cannot be produced there — a control,
  never an input); the host's `systemctl is-system-running` = **DEGRADED**, never
  investigated; the kernel restart and `--after-reboot`, never performed, 38+
  days up; the database container reaching the internet (ADR 0147's residual);
  D688 (the IPv6 scan has nothing to scan); D771 (the OOM history is unknown);
  D976 (Infisical's intermittent hangs); the Infisical control-plane identity
  holding org admin; **D1189 — the example project's grant repair
  `20260914120002` has never been applied on beta.**

### Tier 3 — what this session cannot close, and who must act

**The audit's honest headline stands and this plan does not soften it.** Session
28 makes every one of these *ready* and closes none of them. Each needs a person
at a keyboard or a decision the operator takes.

| What is open | Who must act, and why no session substitutes |
|---|---|
| **`documented_path` is `failed`, and closing it needs a THIRD reader** | A reader who has not seen the repository. `docs/second-walk.md` carries the task statement between fixed markers so a person can be handed the same words. Two *models* have walked it; a person has not. **This session repairs prose the walks found and does not re-walk its own writing.** |
| **The operator guide has never been read cold** | The *upgrade* guide was, and produced 34 findings and two releases. Only a reader who did not write it can do this, and **no test reads prose for truth** (ADR 0209's *Consequences*). The operator is arranging it; its findings are the evidence. |
| **Studio has never been opened in a browser by a person** (D1303) | The sweep has driven it. A person has not. |
| **`replacement_host_restore` is `not_run` BY DECISION** (D1028) | Reversing the decision means building a replacement host. The decision is the operator's. |
| **The public-endpoint decision** (D1084) | Stage 4's first ADR. `runtime_override.publication()` still raises, and `docs/stage-4-decision-report.md` §6 says nothing measured in Stage 3 argues for or against it. |
| **Template, or managed control plane?** | The question Stage 4 exists to answer. `scope-closure.md` §6; ADR 0185 drew the inventory's line without resolving it. |
| **The 21 unclaimed requirements** | Reportable one DECLARATION at a time under ADR 0202. Each is a decision, and a session that declared them in a batch would be inferring rather than declaring. |
| **`1.3.0`–`1.5.0` have no tag, by decision** (D1311) | Tagging them retroactively would be a record that looks measured and was not. |

**What the operator must decide before Session 29 runs**, in order:

1. **That the rotation is still on.** It was decided 2026-09-16 after four
   declines. Run 8's rehearsal is built on that decision and `promote` cannot be
   undone.
2. **ADR 0213's retention policy** — what makes an audit row disappear, and
   whether anything automatic is acceptable at all. The ADR proposes; the
   operator owns the answer, because it is the evidence ADR 0135 keeps.
3. **Whether a person is available for the operator guide's cold reading and for
   `documented_path`'s third walk.** If not, both stay open and the plan says so
   rather than substituting another model.

### Carried in, unchanged

The public-endpoint decision (D1084); a person's walk; the four unswept storage
modules if Run 5 finds two of them are a genuine *why not*;
`docs/stage-4-decision-report.md` §6, which is still what a Stage 4 plan starts
from.

---

## Appendix — what to consult, and how a run is executed here

**Read before Run 1**, in this order: this plan's §1; `docs/pre-stage-4-audit.md`
whole, **and its note that its own Tier 1 count was wrong by four in the first
draft** — the page is a record dated 2026-09-16 and is not held to the tree by a
test; `docs/scope-closure.md` §14 and §15; `docs/plans/session-27-implementation-
plan.md` §1 (D1388–D1405) and §10; `docs/upgrade-findings-response.md`, which maps
all 34 of the adopter's findings and whose **five Open rows are F-008, F-012,
F-013, F-020 and F-022** — the whole of Tier 1a's adopter half.

**ADRs this session is built on**: **0195** (three outcomes, the third reported;
a decision may fail closed, a report may not) before writing any check, status
line or reader; **0206** (the ordering space, and the paragraph it refutes)
before ADR 0210; **0198** and **0200** before ADR 0212; **0135**, **0142** and
**0178** before ADR 0213; **0209** (what holds a release to its documentation,
and what a test cannot assert) and **0162** (what a minor promises) before Run 9;
**0158** (the doctor's two modes, and why the split is load-bearing) before
D1418; **0088** and **0170** before Run 8; **0093** (what a `bin/` command may
import) before any new verb.

**Do not read the audit as measurement.** It says so of itself — *"Everything
here is drawn from documents already in this repository … Where a row says
*measured*, a command produced it"* — and thirteen of its rows were found in
planning to be answered, differently shaped, or pointed at a repair the
measurement does not support. **Two of the thirteen would have caused harm if
implemented as written**: D1411 would have widened a security boundary to match a
dead grant, and D1416 would have undone a decision taken under ADR 0195.

**How a run is executed here** is `CLAUDE.md` §5. Four of its rules are
load-bearing for this session in particular:

- **Documentation only runs nothing before push, and waits on nothing after it.**
  Runs 1 and 2 are documentation and ADRs: push, say it is pushed, move on. **Do
  not poll the pushed SHA and do not report a verdict nobody asked for** — four
  occurrences now, and this plan's own Run 1 text caused the fourth before it was
  corrected. A `paths-ignore` is not the remedy either: `test_mcp_catalog` reads
  `docs/plans/*.md` and fails when the catalog cites a `D` number no plan
  records, so a plan file is load-bearing, and an empty `runs?head_sha=` listing
  reads identically as *not registered yet* and *will never fire* (D1057).
- **A run that adds a page owes `test_documentation_index`** (Run 3's
  `docs/on-ramp.md`, and `docs/README.md` must carry its line); **a run that adds
  or renames a test function owes `test_acceptance_registry`** (D1119, Runs 5, 6
  and 9); **a run that adds or moves a `bin/` command owes `test_cli_contract`
  with the command `git add`ed first** (D1014, D1188, Runs 3 and 7); **a run that
  adds a `document[...]` read to a `bin/` command owes `test_container_selectors`**
  (D1184).
- **Every run that writes a test writes a battery**, and Run 5 is nothing but
  tests. Caches cleared, `PYTHONDONTWRITEBYTECODE=1`, anchors pre-flighted to
  match exactly once with a miss fatal, a paired control the mutation cannot
  reach and green in the same invocation, `FAILED` asserted rather than `ERROR`,
  and the tree restored by copy and `cmp`.
- **A commit message is not evidence that the diff contains what it says**
  (D1116). `git diff --stat` against this plan's list, one line each, before every
  push.

**The gate runs once**, in Run 9, on a clean tree, and `bin/session-01-check.sh`
step 2 reaches PyPI — which cannot run from WSL when outbound TCP is lost
(D1239). Run that one step inside the pinned Python image and say so.

**Rigs this session builds**, each a throwaway with a control (ADR 0065/0066):

| Rig | What it is | Which run |
|---|---|---|
| **28a** | A synthesized pre-ADR-0198 fork from tag `1.0.0` — measured to have no `projects/` (D1419) — with the same clone at `1.6.2` as its control | Run 2 |
| **28b** | A cluster with history: both agent tables seeded across the shapes the plane writes, then the retention migration applied over them (D940) | Run 6 |
| **28c** | The rotation walked end to end against `apg dev` and a rig, running the three `not_run` claims' proofs rather than only the commands | Run 8 |

**The scratchpad** carries Session 26's `--help` capture and release-table reader
under `s26-scripts/`, and this session's planning measurements as
`s28-m1.sh`–`s28-m5.sh`. WSL's `/tmp` does not survive `wsl --shutdown`; those
copies do.
