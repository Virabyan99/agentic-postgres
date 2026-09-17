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
**Next free:** D1479, ADR 0216. *(Run 1 added D1426–D1433; Run 2 added
D1434–D1439 and wrote ADRs 0210, 0211 and 0212; Run 3 added D1440–D1443 and
built them; Run 4 added D1444–D1446; Run 5 added D1447–D1456; Run 6 added
D1457–D1462 and wrote ADR 0213; Run 7 added D1463–D1467 and wrote ADR 0214;
Run 8 added D1468–D1478 and wrote **ADR 0215**, which a rehearsal is not
supposed to need.)*

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

D1406–D1443. **D1406–D1425 were measured during planning on `ad96673`; D1426–D1433
are Run 1's**, from the nine rows planning had not measured; **D1434–D1439 are Run
2's**, measured on rig 28a and on a pinned PostgreSQL 18.4; **D1440–D1443 are Run
3's**, from building what Run 2 decided; **D1444–D1446 are Run 4's**, from the
three readers that report a file event as a domain event; **D1447–D1456 are Run
5's**, and all but two came from a proof's FIRST EXECUTION or from the run's own
mutation battery. Rows marked
**answered** are closed by writing down what the tree already does; rows marked
**recorded** are not repaired here and say why. Runs allocate from **D1463**.

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
| **D1440** | `docs/migrations.md`: *"dbmate is handed a directory and orders the whole of it by filename, so the two sets interleave by version stamp … `freeze-lock --project` refuses at freeze so that never reaches a host."* | **The rationale ADR 0206 refuted, in a fourth place nobody grepped.** Session 27 Run 3 replaced it in three — the docstring, `bin/migrate.sh --help`, and the refusal message — and this page kept it. It is not merely stale: it states the two sets share an ordering space, which is the thing ADR 0206 removed, and it credits the freeze-time refusal with preventing a cluster failure it no longer prevents. Found by D1187's rule applied on purpose: grep the moved TEXT, not the moved name. | **Rewritten in Run 3**, with the measurement kept (it is still true of the release that had one directory) and its scope stated, plus the new record, its provenance field and a pointer to `docs/on-ramp.md`. | Session 27's own §4 repaired three readers of one rationale and a fourth survived, which is question 5 exactly — *when a decision is implemented, which of its callers got it?* A page is a caller. | 0206 |
| **D1441** | Audit 1a and D1418: *"`bin/doctor.sh` checks the interpreter on a workstation only"*, closing act *"then the interpreter check on the host."* Run 3's instruction: take it **only if ADR 0158's split admits a third reading**. | **It does not, and the reason is structural.** Workstation mode checks a developer's own interpreter and is unprivileged; deployed mode checks seven live things about ONE PROJECT and needs root. The host's interpreter is a property of the machine and of no project. Adding it to deployed mode puts a bare `python` resolution back under `sudo`, which is the exact failure the split's own comment says the split exists to prevent. The only host-wide checker is `provision-host.sh --check`, which runs as root on production — and **no session has measured which interpreter versions this product requires on a host**: `.python-version` is the workstation pin, and the cold reader's host ran every `bin/*.sh` under 3.14 against a pin of 3.12.13 and worked. | **Stated, not repaired**, at the split itself in `bin/doctor.sh`'s header — where a reader asking *does this check the host's interpreter?* actually looks — and in `scope-closure.md` §15. **No requirement and no claim**, so §2's conditional row resolves to *no*. | A check added on an unmeasured footing, to the one command that runs as root on production, in a session with no host trip, could fail a host that works. Stating the gap is the act ADR 0195 asks for; inventing a threshold would be the folded third outcome. | 0158 |
| **D1442** | Findings F-022 and audit 1a: *"A fork whose domain is in the release's files **can deploy and cannot pass the gate**"*, with *47 failures and 49 errors*. D1433 refused to carry the number forward and named rig 28a as the only instrument. | **Reproduced, and the number is close enough to trust while the SHAPE is the finding.** The release's own `contract and p0` sweep against rig 28a at the merged pre-conversion state: **52 failed, 5,692 passed, 3 skipped, 49 errors** — the errors identical to the adopter's, the failures within five. **The control is the same command on the unforked checkout in the same session: 5,800 passed, 3 skipped, nothing red** (D499), which is also a full contract sweep of Run 3's own code. And they are not spread: they are almost entirely the reviewed-surface family — `test_api_surface_contract`, `test_api_contract_command`, `test_client_ir`, `test_generate_command`, `test_generated_client_runtime`, `test_scope_registry`, `test_scope_vocabulary`, `test_studio_*`. **`test_migrations` passes.** The fork's MIGRATIONS are not what the gate objects to; its relation in `contracts/postgrest-api-surface.yaml` is. | **F-022's paragraph is written from this**, in `docs/on-ramp.md` and the findings reply: the gate's objection is the shared reviewed surface, the conversion moves that relation into `projects/<slug>/contracts/`, and that is why the answer to F-022 is the on-ramp rather than a gate change. | *"The gate cannot pass on this fork"* priced as one defect is a number. Measured, it is one cause with a large blast radius, and knowing which cause is the difference between *convert* and *we cannot say*. The failure families outside that one are not analysed and this row says so. | 0212 |
| **D1443** | Nothing said it. `docs/on-ramp.md`'s first draft ended with `sudo bin/apg-diag.sh --project <key> catalog`. | **That flag does not exist and `catalog` takes two positional arguments.** `apg-diag`'s own usage is `sudo apg-diag catalog <project> <query>`, with four queries. The error was caught not by reading the page but by **measuring it against `dx_record.documented_commands` before adding it to `DOCUMENT_ROOTS`**: the measurement printed `bin/apg-diag.sh` as newly documented, which is only possible if the page names it — and the page had no business naming it that way. | Corrected to the spelling its own `--help` prints (ADR 0208 §3), which also made adding the page to the scan a **measured no-op**: every command it names was already documented elsewhere, so the documented set moved by nothing. | The live reader doubles as a spell-checker for a new page and nobody had used it that way. It is the cheapest available check on a page full of commands, it runs offline in a second, and it found a wrong invocation on the first page it was pointed at. | 0208 |
| **D1444** | `docs/scope-closure.md` and `CLAUDE.md` §9 on D1413: *"No span leaves the process; the collector is on `edge` only … `mcp_tracing.configure()` has no caller; **scraping a project's services must answer the network question first**."* Run 4's instruction: a caller, its deletion, or the network question written down as the reason for neither. | **The stated reason is about the wrong direction and does not survive measurement.** Scraping is a collector reaching a service; `mcp_tracing` is a **push**. Measured in the tree: `compose.yaml`'s `mcp` service is on `internal` AND `edge`; the collector (`metrics`) is on `edge`; and `naming.py:1120` derives the edge network per project — `apg-<key>-edge` — so a runtime pushing OTLP reaches its own project's collector and no other's. The exporter is already in the image: `OTEL_EXPORTER_OTLP_HTTP_VERSION` is a pinned build argument on that service. **Nothing about the network blocks a caller.** | **Neither, and the true reason written at `configure()`** — where a reader reaching for `git rm` is — plus a test that goes red if a caller appears or if `span`'s caller disappears. What is actually undecided: a caller starts a new outbound flow from the container that handles a caller's credential, and `SPAN_ATTRIBUTES` stops being an internal enumeration the canary checks and becomes a published surface. That is a security review and ADR 0164's plane, so Stage 4's. | The ledger gave a reason that reads as a blocker and is not one, so the row has been deferred three times against a constraint that does not exist. A wrong reason is worse than no reason: it stops the question being asked. | 0164 |
| **D1445** | Run 4's own D1045 clause, as first written: *"`exc.length` is the Content-Length header, and a header is not a body."* | **`exc.length` is not a property of the response.** `HTTPError.__getattr__` delegates unknown attributes to the underlying file object, so whether `length` exists depends on what `urllib` happened to wrap. Measured by the proof on its first execution: an `HTTPError` raised around a `BytesIO` gives `AttributeError: '_io.BytesIO' object has no attribute 'length'`. The reading is `exc.headers.get("Content-Length")`. | **Repaired before the commit, and the clause gained a third answer with it.** A response that declares no `Content-Length` is chunked or omitted the header, and the only way to find out whether it carried an explanation would be to read the body — the one thing the clause exists not to do. So it reports *cannot be told from here* rather than folding into *nothing was sent*. | A run repairing ADR 0195's class produced an instance of it in its own first draft: a two-valued reading of a three-valued question, folded in the reassuring direction. The proof caught it on first execution, which is the fourteenth time a never-executed proof has failed the first time it ran. | 0195 |
| **D1446** | The audit and `CLAUDE.md` §9 on D387: *"the REST observation does not retry."* Session 7's row: *"a lost race makes the deployed document understate a working deployment — and a claim computed from it would be wrong in the safe-looking direction."* | **It is one reading among six, and the only one outside a window.** `bin/deploy-project.py`'s step 7 wraps tls, health, docs, app_docs, app and storage in `observation.await_observation`; `observe_served_document` is called once, immediately, and returns `None` on any failure. And `None` folds two states that are not alike: a documentation token that cannot be minted is **deterministic**, while a router Traefik has not wired yet **converges** — which is the note every neighbouring block already carries. | **Run 4 gives it the window its neighbours have, and only for the state that can change.** `ServedDocument` carries the digest, which of three outcomes it is, and the detail; `settled` is false for `unreachable` alone, so a terminal failure does not spend ninety seconds being retried thirty times. The two failures print different sentences because they send an operator to different places. | Retrying everything would have been the obvious repair and would have made a missing signing key cost the full observation window on every deploy, with the same line printed on each poll. The row says *retry*; the measurement says *retry one of the three*. | 0195 |
| **D1447** | Audit 1c and D1421: *"D1240 — four modules collect 0 under every marker-selected sweep … They have never run in any gate"*, with the guess that two of them *"may be a genuine why not"* because they import from the service tree. | **It splits 1 + 3, not 2 + 2, and the stated worry is refuted by a config file.** `pytest.ini` carries `pythonpath = src services/auth-api`, so `app` is importable in every pytest invocation — a property of the config, not of the environment — and all four modules pass here (1 + 28 + 19 + 34 = 82). The real split is elsewhere: **`test_database_function_signatures.py::test_every_call_to_a_released_function_uses_a_released_arity` is a REGISTERED proof of `AGT-AUDIT-002` (P0)**, reached only by the gate's explicit claim-proof run in HOST mode — present in `evidence/session-25-host-claims.xml`, absent from `session-25-offline-tests.xml`. The three storage modules are named by **no** registry entry at all; every STO-* proof is `tests/deployment/`. | **`contract` + `p0` for the registered one** (it belongs in the offline sweep and what it compares is two files in a checkout); **`contract` for the three**, and `security` for `test_storage_endpoints`, whose subject is every route's scope check. **No `p0` for the three**, because `p0` selects the offline CLAIM sweep and a proof there that no claim reads is D697's rule inverted. Measured after: 0 → 82 under the gate's selector, 0 → 1 under the claim sweep. | The row reads as one decision about four files and is four decisions, one of which is not a decision at all: a registered P0 proof that runs only when somebody takes a trip. Sessions 26 and 27 took none, so for two releases nothing anywhere ran the guard built after an arity change cost twenty-one errors and thirteen minutes of host time. | 0175 |
| **D1448** | Run 5's own new SQL-signature guard, as first written: *"matched within one statement (`[^;]*?`) over comment-stripped SQL, so a sentence in a `--` block cannot pair them."* It reported **153** references. | **The pattern paired a `GRANT` with a later `CREATE` across intervening statements.** Its first execution flagged `0014-object-storage-plane.sql: storage_create_upload_intent(p_owner_id uuid, …)` as a reference to a declaration that did not exist — because the match WAS the declaration, reached from a `GRANT` several statements above through `[^;]*?` under `DOTALL`. Excluding `CREATE` from the gap gives **140**, and every one of those names a declaration live at that point. | The exclusion is in the pattern with the measurement beside it, and the count assertion says **140** with the reason it moved, so the next reader does not restore 153. The threshold is `>= 135` rather than `== 140`, because a released migration may add one. | A count written into an assertion before the pattern was right would have frozen thirteen false pairings as the expected state — and the guard would then have failed the day the pattern was corrected. | 0175 |
| **D1449** | Run 5's own new RPC-body guard, twice. | **Two first-execution failures, in opposite directions.** (1) The path pattern required a quote immediately before `/rpc/`, and every deployment proof builds the URL as `f"{base}/rpc/create_note"` — so it read **zero** bodies and the only thing that caught it was the guard's own *did I measure anything* assertion. (2) Taking the next literal dict after the path matched the OpenAPI **schema** documents that `test_client_ir.py` and `test_openapi_normalize.py` build beside such a path — `properties`, `required`, `type`, `in` — producing four failures against a guard that had found nothing real. | `body=`/`json=` is required between the path and the dict; the leading quote is gone. And the two bodies that DO name an undeclared key are named per `(file, function, key)` in `DELIBERATE_UNDECLARED_KEYS`, because both are proofs *about* an undeclared key — a caller-supplied `owner_id` that must be ignored, and `{"nope": 1}` that must be refused without disclosing a role. | A scan whose first execution produces only false positives gets deleted, and a scan that measures nothing passes. Both halves of this guard hit one of those on the way in, and the assertion that saved it is the one that asks *did I look at anything at all* (D173, D260, D509). | 0175 |
| **D1450** | `_arguments` in `test_database_function_signatures.py`, unchanged since Session 16: it walks forward from a `(` until the parens balance. | **It is unbounded, so the arity guard's verdict on an unterminated example depends on text far below it.** The module's own `_is_a_call` docstring contains ``"CREATE FUNCTION api.agent_audit_begin("`` as an example of a prefix string. Its paren never closes, so the walk runs on through whatever follows — and **adding functions to this file flipped that example from *not a call* to *a call with 14 arguments***, measured on this run's first execution of the suite after the two new guards were inserted above the test. | A **400-character bound**: an argument list that does not close within it is not a call. The longest real call in the tree is 84 characters, and `checked > 100` is what says the bound did not narrow the scan. The bound and its measurement are in the code. | This is the guard for ADR 0175 and it had a verdict that could be changed by editing an unrelated part of the same file. Nothing would have reported it: the flip was toward a FALSE POSITIVE this time, which is the loud direction — the same fragility pointing the other way is a call the guard stops seeing. | 0175 |
| **D1451** | `test_no_module_is_imported_only_by_its_own_tests`, the guard for D204 — *"a module nothing calls is a feature that does not exist"* — and its shell half: *"Python embedded in a shell script is still a caller."* | **Its pattern reads a module name plus whatever word follows it.** The import list is captured with `[\w,\s]+`, and `\s` matches a newline, so `from agentic_postgres import dependency_lock` followed by a blank line and `problems = …` yields the name `dependency_lock\n\nproblems`. Measured across `bin/*.sh`: **seven of the thirteen names this scan produces are mangled that way** — `backup_report\n\ndocument`, `deployed_output\n\ndocument`, `installed_release\n\ncheckout`, `migrations\n\ndocument`, `naming\ndocument`, `output_migrations\n\nalpha`. The guard stayed green only because every one of those modules has a second caller in `bin/*.py`. A module imported ONLY from a heredoc is reported as an orphan — which is how Run 5's own new module was greeted. | `[\w,][\w, \t]*`, which cannot cross a line, **plus an assertion that every name the shell scan produces is a module of the package or a name it exports** (read from `__all__`, not listed). A scan producing rubbish is a scan whose real answers cannot be trusted either. | The guard built to catch *a feature that does not exist* could not see a caller, and the direction it failed in is the one that fires: it reported a false orphan rather than missing a real one. The same fragility pointing the other way is a module nothing calls, passing. | — |
| **D1452** | `docs/scope-closure.md` and `CLAUDE.md` §9 on D1282: aiming the gate's `--kit-dir` at the newest kit *"destroys the proof **without failing**, which is the quiet kind."* | **It fails, loudly, and has since Session 21.** `test_the_kit_exported_before_this_release_verifies_at_it` carries a `pytest.fail` on exactly that condition, written with the proof — `git log -L` puts it in `4dde0e5`, the Session 21 bump. The row describes a self-diagnosing guard as a silent trap. | **The characterisation is corrected in the ledger**, and the refusal is made to name **what it found** rather than only what it wanted — an operator holding three kits had to work out which one it meant. The operational half that IS true is kept and given its reason: the claim's premise is the version gap, so at least one kit below the tree's outputs version has to be kept, which is why three are. | A row that calls a loud guard quiet produces the wrong caution: an operator believing they must remember something the product already tells them. It is the inverse of this project's usual defect and it costs the same thing — attention spent where none is needed. | — |
| **D1453** | Audit 1c and D1429: *"Studio has no live half for the query view's RLS"*, the unnumbered half of the audit's D1276 row. | **Confirmed, and it is the one view that returns a tenant's data.** `test_session24_studio.py` carries live halves for revocation (`STU-REVOKE-001`) and for the audit read (`AGT-AUDIT-002`) and nothing for `POST /__apg/query`. Studio holds no policy of its own: the read is forwarded with the human's own token, `api.notes` is `security_invoker`, and `app.notes` carries FORCE row-level security — so the answer is PostgreSQL's, and nothing live said so. | **Written in Run 5, `not_run` until Session 29's trip.** Two owners, one relation: a row written by the auditor and one by a second subject, both through `POST /rpc/create_note` as themselves, with the stranger's row read back **as the stranger** so its existence is not assumed. Both directions asserted — a view returning nothing satisfies *the stranger's row is absent*, and a view with no policy satisfies *my row is present*. | **D1276 itself is closed** and its mechanism is a stated unknown ADR 0195 permits; this run does not re-repair it and asserts no mechanism for it. A repaired row and an open row sharing one number is how the repaired one gets re-repaired and the open one keeps waiting. | 0205 |
| **D1454** | Run 5's own SQL-signature guard, after it went green: *"140 such references across 34 templates, and every one of them names a live declaration."* | **The assertion is vacuous on a healthy tree, and the run's own battery proved it.** A mutation that removed the comparison — `if False:` in place of the staleness test — **SURVIVED**, green, because `stale` is empty whether the walk compares or not when nothing is stale. `checked >= 135` says the guard LOOKED; nothing said it COMPARED. That is D173/D260's shape in a guard written this very run, four hours old. | The walk is extracted as `_stale_sql_signatures` and given a **positive control**: three synthetic templates in version order — a declaration, a grant that matches it (which must NOT be reported), a revoke that does not (which must), and a reference standing before the declaration it names. The battery re-run kills it. | A survivor is evidence (CLAUDE.md §1), and this one says *weak test* rather than *uninformative mutation*. It is also the argument for running the battery over a run's whole output rather than over the tests that felt risky: this guard was the one that had just been measured most carefully. | — |
| **D1455** | `docs/scope-closure.md`: *"`test_honest_readers`' `sudo -u` prefix has still never run … the prefix itself waits for a gate that runs as root."* CLAUDE.md §7: twelve never-executed proofs have failed on first execution. | **It ran, and it passed** — rig 28c, 2026-09-17: `ubuntu:24.04` as **uid 0**, the checkout bind-mounted at its own path so `REPO_ROOT` resolves and still owned by `1000:1000`, the uv interpreter mounted beside it, the owner uid created inside so `sudo -n -u '#1000'` has somebody to become. `euid: 0`, `sudo -n -u` answers `uid=1000`, and **24 passed, 0 skipped** — including `test_an_unreadable_document_is_unreadable_and_never_absent` and `test_the_reading_the_root_branch_makes_gives_the_same_answer`, the two that carry the re-entry. | **Recorded as executed.** The row comes off `scope-closure.md`'s open list, and the rig is a throwaway rebuilt from its script. | **It is the thirteenth never-executed proof and the first not to fail.** The reason is worth more than the result: D1165, D1300, D1301, D1302, D1330 and D1332 each repaired this pair in response to a first execution **elsewhere** — root's `0700` temp directory, the `/tmp` chmod that took the sticky bit off a host, a fixture the re-entered child could not own. Six repairs had already been applied to it from adjacent evidence before it ever ran. | — |
| **D1456** | Audit 1c: *"the uncached first run of `apg dev up` is measured in CI and nowhere else"*, closing act *"measure it where it is claimed."* | **It is already claimed in the one place the row asks for.** `capacity.UNMEASURED` carries the entry verbatim — the subject, the reason (`docker rmi` of the image the whole contract suite shares, and the number obtained would be this machine's link speed), and `unblocked_by: "nothing that should be run mid-session; the CI row is the measurement"`. `scope-closure.md` §11 carries the same. A test asserts `UNMEASURED` is non-empty for as long as anything is. | **Closed by saying so**, and by nothing else. Measuring it here would evict the image six cluster fixtures share, cost every later test in the session a pull, and produce a number about this machine's link. | The row's closing act is already performed, which is the fourteenth instance of Session 28's own §0 finding: the audit's *closing act* column was written from the documents rather than from the code. Here it was written from neither — the claim is in the envelope the row names. | 0203 |
| **D1457** | Four proofs asserting ONE ascending version order across both migration sets — `test_a_declared_set_renders_after_the_release_set_in_version_order` (*"dbmate is handed a DIRECTORY and orders the whole of it by filename"*), two assertions in `test_the_rendered_manifest_names_the_set_of_every_file`, and the same file's *"every project version sorts after every release version, which is the rule `freeze-lock --project` records as `follows_release_version`"*. | **ADR 0206 removed that rule and the product's own code says so.** *"A project's migration set is rendered into its own directory and applied against its own migrations table … Each set is then ordered against its own applied set only"*, and `_assert_follows_release_version`'s docstring calls what survives *"a record, not a guard"*. The four proofs were still enforcing the single ordering space whose collapse took beta's deploy down at Session 24 (D1288) — **the rule that failure produced.** They stayed green because **no release added a migration between ADR 0206 and this run**: Sessions 25, 26 and 27 added none. Run 6's `20260917120033` is the first, it sorts above the example project set's `20260914120001`, and all four went red on first execution. The fourth also conflated the lock's RECORD with the checkout's newest release, which is D1436 one proof over: since ADR 0210 `follows_release_version` may be a declared earlier release. | **All four repaired to assert what ADR 0206 guarantees**, which is the thing that would have to break for D1098 to come back: each set ascends **within itself**, the two sets have different roots, `migrations_subdir` and `migrations_table` differ for the two labels, and no set's payloads are spread across directories. The fourth reads the project lock's own `follows_release_version`. A mutation returning one subdirectory for both labels kills the repaired proof. | A guard can only fire when its subject moves, and this one's subject had not moved in four sessions — so *the release adds a migration* was a path no proof had taken since the ADR that changed what it means. Repairing them is implementing a released decision, not weakening a guard: the replacement asserts the mechanism rather than a side effect of the mechanism it replaced. | 0206 |
| **D1458** | `test_a_project_version_older_than_the_release_lock_is_refused`, whose *equal* arm sets the example project manifest's FIRST migration to `newest_release_version()` and expects `verify_lock` to refuse it. | **It depended on an accident between two unrelated stamps.** The arm only reached `verify_lock` while the release's newest version sorted BELOW the project set's second migration; with `20260917120033` in the manifest the fixture reads `['20260917120033', '20260914120002']` and `load_manifest` refuses it for being out of order — so the proof failed on its own scaffolding rather than on its subject, with a message about a manifest a reviewer would not recognise. | **Every entry is restamped from the candidate upward** (`version + index`), so the fixture stays ascending whatever the release's newest stamp is, and both boundaries still reach the refusal they are about. The control in the same invocation is unchanged. | A proof that fails for a reason other than the one it is named for costs the reader the time it takes to work out which. It is also the cheap half of the same class as D1457: both were written when the two sets shared one ordering space, and both encoded that as an assumption about numbers rather than as a statement about the mechanism. | — |
| **D1459** | `bin/doctor.sh`'s header and usage: *"deployed: seven live checks against one project on this host"*, twice — and quoted a third time in D1441's own argument this session, and a fourth in ADR 0158's table. | **There were ten, and the file has said seven since Session 18.** `diagnose()` appends containers, the health route, TLS, the cluster and pooler, migrations, the backup repository, the WAL archiver, the backup mirror, disk headroom and capability drift. The operator guide says *ten checks* on the same page that quotes this command's help, so the two documents an operator reads disagreed with each other and one of them was the command itself. | **Both places in `bin/doctor.sh` now say eleven**, which is what this run makes true. **ADR 0158's table is left alone**: an ADR is a record of a decision at a date, and the count is not the decision it took. D1441's row and `scope-closure.md` §15 quote the pre-repair text and are marked as quoting it. | A count in a command's own `--help` is the number an operator compares their reading against, and it was three short. Session 26's ADR 0208 §3 binds every command in the operator guide to its own `--help`; this is the first case where the `--help` was the wrong one, and it was found by adding to the thing it counts. | 0158 |
| **D1460** | `docs/scope-closure.md`, `CLAUDE.md` §9 and the pre-Stage-4 audit, all three treating one row: *"`agent_audit` and `agent_idempotency` grow without bound. Nothing prunes either"* — closed the same way, *"a retention rule."* | **They are not one question, and rig 28b measured the difference with its control in the same run.** Pruning an audit row loses history and nothing else: neither table carries a foreign key (the only one among the three agent tables is `agent_quota.agent_id`), and no live behaviour depends on a row being present. Pruning an idempotency claim **re-arms its key silently**: a write replayed while its claim is present is deduplicated and `app.notes` stays at one row; the same write replayed after the claim is deleted writes a SECOND row and reports success, with no error on either side. At-most-once becomes at-least-once for every key past the horizon — the failure 0029 exists to prevent. **And there is no safe subset**: the obvious candidate, the claims of agents that are no longer active, dies on its own measurement, because `auth_rotate_agent_secret` (0025) clears a revocation and returns the SAME agent id to `active`, so a revoked agent's keys are dormant and not dead. | **ADR 0213 splits the row and migration `20260917120033` ships both prunes with different comments.** The idempotency prune carries its consequence in its own `COMMENT ON FUNCTION`, in the words an operator reads while deciding, and a proof holds the consequence measured — with the unpruned replay as the control in the same test. | Two rows closed with the same three words, where one is a disk decision and the other is a change to a guarantee this product advertises. A session reading the table as uniform would have shipped a default horizon and quietly downgraded every caller's at-most-once, and the audit's own closing act invited exactly that. | 0213 |
| **D1461** | This migration's own first draft: *"`p_limit` is the answer to the lock instead of an index"*, written before the rig ran and implying the bounded prune is the cheaper one. | **It is not the faster one.** On a cluster carrying 20,004 audit rows spread over fourteen days, the unbounded prune removed 9,921 in **141 ms** and a bounded one removed 500 in **147 ms** — the `ctid` subquery pays for itself. Both plans are `Seq Scan`s: 0019's two indexes are `(owner_id, started_at DESC)` and `(agent_id, started_at DESC)`, neither leading with the timestamp, and `agent_idempotency` has only its primary key. | **The rationale is corrected in the file to what was measured**: `p_limit` bounds how many rows one transaction touches and holds locks on until it commits, not how long it takes, so a table nobody has pruned since the deployment was created can be taken in passes whose size the operator chose. **No index is added** — 0019 wrote that its two exist for one reader and neither is speculative, and a third would be paid on every write to buy a scan for an operation performed by hand. | A rationale written before the measurement, in a file that ships, is a sentence a later reader will believe. This one was wrong in the direction that produces work: an operator reading it would batch a prune to make it faster and get a slower one. | 0213 |
| **D1462** | Run 6's plan: *"plus the counts in `bin/doctor.sh`'s deployed mode so an operator can see the growth."* | **A count is a reading and not a verdict, and this session already found what inventing the verdict costs.** Nobody has measured a row count at which a deployment is unwell. D1441, three runs earlier, struck the host-interpreter check for exactly this: *"a check added on an unmeasured footing, to the one command that runs as root on production, in a session with no host trip, could fail a host that works."* The same argument arrives a second time, in the same command, in the same session. | **The eleventh check reports the two counts and the date the record starts, and has no threshold** — ADR 0195's three outcomes, where the third is *I could not read it*. A test asserts the absence across five row counts from 0 to 10⁹, so adding a threshold means deleting the test that carries the argument. **And the probe reads the two TABLES rather than migration 0033's functions**, so the count follows the CHECKOUT and not the cluster: a 1.7.0 checkout reads eleven against a deployment at any release, and Session 29's pre-upgrade reading is not disturbed by a tree that is ahead of it. | The deployment is two patches behind the tree already (D1401), and Session 29's first act is a doctor reading taken from the host's own checkout. A check that went `unknown` against an un-upgraded cluster would have made that reading exit 6 for a reason the operator did not cause — which is the shape of the surprise this session exists to avoid. | 0213 |
| **D1463** | D1424 and `docs/pre-stage-4-audit.md`: *"A release's documentation landing one commit past its own tag. **It has now happened three times**, twice of them on one day."* | **Five of five.** Rig 28c walked every tag on `main` and the commits that follow it up to the next `VERSION` change. `1.0.0` → `b60814b` (`bin/bootstrap-providers.py` and a test); `1.0.1` → `a0d853f`; `1.6.0` → `d1a6db0`; `1.6.1` → `f97075d`; `1.6.2` → `ad96673`. Every tag this repository has, without exception. **And the first one is not documentation at all** — `1.0.0`'s next commit is a product repair in `bin/`, which is the shape the row does not describe. | **ADR 0214 §Context.** The count is corrected on the page and the class is widened from *documentation* to *release bytes*, because a repair landing past a tag is the same defect and a worse one. | Three is a habit; five of five is the arrangement. The row's number was what made a checklist sound sufficient. | 0214 |
| **D1464** | Run 7's own first design, and the obvious one: classify each path past a tag as a RECORD (a plan, the ledger, an audit, an evidence document) or as RELEASE BYTES, and report the first release-byte commit — so the reading fires on the defect and stays quiet otherwise. | **Measured over all five tags, twelve commits deep each, and it does not separate them.** `1.0.0` → release bytes at +1, a defect. `1.0.1` → records at +1..+3, release bytes at **+4**, and that one is Session 20 starting the next release. `1.6.0` → release bytes at +2 (Session 26's guides). `1.6.1` → release bytes at +2, a defect. `1.6.2` → release bytes at **+5**, and that one is this session. **The defect and the ordinary between-releases state are the same shape.** | **The command decides nothing**, and `test_the_reading_prints_no_instruction_about_the_tag` is where the argument is kept: adding a verdict means deleting the test. ADR 0214 §Decision 3 and its Alternatives. | What separates *work that belonged inside the release* from *the next release's work* is intent, and **intent is not in the tree**. A verdict here would be D1441's mistake — a threshold on an unmeasured footing — struck earlier in this same session. | 0214 |
| **D1465** | The naive reading a command would print: *is the tree's `VERSION` already tagged, and have commits landed since?* | **Replayed against all 147 commits from `1.0.0` forward: 45 of them answer yes.** Nearly a third of this repository's history is *already tagged, N commits since*, because that is what a repository between releases looks like. | The reading states it as a fact and never as a warning, and the run-length is the reason the exit code stays `0` for it. A reading that shouts at a third of every history is a reading that gets skipped — **which is exactly how the prose checklist failed**. | The measurement that saved the command from becoming the thing it replaces. | 0214 |
| **D1466** | ADR 0209: *"a test runs inside a commit"* and cannot see a tag — the whole reason its guard is not asked to. | **Right, and incomplete.** `.github/workflows/ci.yml` has three jobs and only the gate checks out with `fetch-depth: 0`; the job that runs the contract suite and the P0 inventory job take `actions/checkout`'s default. Measured against a control — a depth-1 clone of this repository beside a full clone of the same commit: `git tag` returns **zero names** and `git describe` is **fatal** in the first, and five names in the second. `--no-tags` at full depth reads identically. | ADR 0214 §Context 5, and `NO_TAGS_IN_THIS_CLONE` — the third outcome (ADR 0195), with exit **3**. A reading taken in CI would be clean by measuring nothing, which is D600's value exactly. | A second, independent reason for ADR 0209's line. The first is about what a test can see; this one is about whether the bytes are even in the checkout. | 0214 |
| **D1467** | The natural next step for any new reading: put it in `bin/session-01-check.sh`, where it would run on every push. | **Refused on the measurement above.** The gate runs in CI, where the suite's job has no tags, so it would print *the reading cannot be taken here* on every run — and a line that is always the same is a line nobody reads. | **It is not in the gate.** It is run by a person at a workstation with a full clone, at the session close, and `docs/operator-guide.md` §14 and this plan's Run 9 say so. | The one place automation would have made it worse, named so a later session does not add it as an obvious improvement. | 0214 |
| **D1468** | Run 8's own plan: *"the three `not_run` claims … have proofs already registered, and a rehearsal that does not run them is a rehearsal of the commands rather than of the evidence. **Run them against the rig** and record which passed."* | **No rig can run them.** All nine node ids behind the three claims are `live_host` and carry `requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", …)`. `--setup-plan` on the nine, with nothing set: **9 skipped**, naming the absent variables. Four of the nine additionally demand a `*_FROM_FILE` declaration that only exists inside a rotation window on a deployment. | **The rehearsal proves the commands and the mechanism; the evidence stays Session 29's.** Rig 28d executes every step of the cutover against real containers holding a real key set, and the sheet says which steps were rehearsed and which were not, step by step. | The plan priced a rig as able to move a claim. A claim is measured in one environment (ADR 0089, `evidence_claims`'s own rule), and this one's is the host. | — |
| **D1469** | Run 8's plan, and the Stage 4 bill: *"the rotation performed"* closes `bootstrap_identity`, `api_authorization` and `credential_rotation_planes`. | **Four rotations, not one — and the signing-key cutover moves ONE of the nine node ids.** `bootstrap_identity` also needs `APG_ROTATED_AUTHENTICATOR_FROM_FILE` (the authenticator password); `api_authorization`'s fifth node id needs `APG_ROTATED_DOCS_FROM_FILE` (the documentation Basic Auth password); `credential_rotation_planes` needs `APG_ROTATED_FROM_FILE` (the application credential, on **both** projects). None of those three is touched by `bin/rotate-signing-key.sh`. And a claim is `not_run` unless **every** node id it lists ran and passed — so performing the cutover alone moves **no claim at all**. | **Session 29's sheet says so on its face**, with the node-id table, and names the other three rotations as provider replacements plus a redeploy. `bin/rotate-secret.sh` is a planner and performs none of them. | Four trips have offered *the rotation* as if it were one act. The claim it was offered to close needs three more. | — |
| **D1470** | The same plan's step 7: *"After the deadline, `retire`, then redeploy and recreate"* — with the sweep unplaced. | **The signing-key proof passes only after `retire`.** `test_a_rotated_signing_key_is_the_only_one_the_plane_accepts` asserts the retired `kid` is **absent** from the deployed document's `verification_kids` — *"a key still listed there is a key the plane still accepts … the second phase did not complete"*. Between `promote` and `retire` both keys are published **on purpose**, so the proof is red by design in that window. Measured in rig 28d: `retire_after` is `promote`'s clock **plus 930 seconds** (`MAX_TOKEN_TTL_SECONDS` 900 + `CLOCK_SKEW_SECONDS` 30, the 30 being D241's bisected reading of the locked PostgREST), and `retire` before it exits **6**. | **The sheet places the sweep after step 7** and prices the wait: the window is ~16 minutes at its narrowest, twice, and no sweep runs inside it. | A proof that has never executed, read for the first time by the run that would have run it at the wrong moment. The thirteenth such proof this project has found; this one was found before it cost a trip. | — |
| **D1471** | `bin/rotate-secret.sh`: `auth_jwt_signing_key` prints **`ROTATES — replacing this value rotates it; every consumer below is re-materialized`**, and `secrets.required.yaml`'s twelve-line comment on that secret never mentions the cutover. Its own header says *"Two of the declared secrets cannot be rotated by replacing them, and both look exactly like the ones that can — that is what this exists to say."* | **Measured in rig 28e.** Replace `auth_jwt_signing_key` in place and render: the published set goes from one key to one key with **zero overlap** — the old `kid` is gone the moment the file changes. Every verifier still holding the previous set refuses every token the issuer now signs, until each is recreated. That gap is the whole reason ADR 0088 exists, and the planner's line is what an operator reads before a window. | **Recorded, not repaired.** The repair is a note field on the declaration, printed by the planner beside `ROTATES` — a schema move on a contract file, which is a decision rather than a run's tidy-up. `docs/operator-guide.md` §9 already sends a reader to the seven steps; the planner does not. | The third secret that looks exactly like the ones that can be replaced. The command exists to say that out loud and says it about two. | — |
| **D1472** | `bin/session-25-check.sh --help`, on `--rotated-jwt-from-file`: *"There are **FOUR** verifiers now (ADR 0113, ADR 0122): the agent plane reads the same rendered `jwks.json` PostgREST and storage do, and every one is RECREATED."* | **Three.** `bin/rotate-signing-key.py`'s `VERIFIERS` table is `postgrest`, `storage`, `mcp`, and `acknowledge` prints three lines — measured in rig 28d, both when they were behind and when they were clean. `compose.yaml` mounts the rendered `jwks.json` into exactly those three services (lines 823, 1473, 1599). The fourth name is `auth`, which is the **issuer**: ADR 0098 is titled *the issuer's published set is not the verifier's set*, and an acknowledgement from it would be the issuer agreeing with itself. | **The sheet says THREE, with the reason.** The help text's repair belongs to Run 9's gate, which is derived from Session 25's by diff. | An operator counting acknowledgements against the number the gate's own help gave them would stop and look for a fourth that does not exist — in the middle of the one window with an irreversible step in it. | — |
| **D1473** | ADR 0088, `bin/rotate-signing-key.sh`'s usage step 3, the `acknowledge` remedy and `docs/operator-guide.md` §9, all four: *"bring the project down and up so every verifier is RECREATED"*. | **The redeploy alone should already do it, and the mechanism is three sessions younger than the instruction.** Since D591, `bin/render-mount-digests.py` runs immediately before `compose up` and writes a label per service carrying the digest of everything it bind-mounts; Compose hashes labels into the config hash, so **a service whose mounted content changed is recreated and one whose content did not is left alone**. `runtime_override` mounts the rendered `jwks.json` into all three verifiers, and `mounted_paths_by_service` picks up every bind mount rather than a maintained list. So a redeploy after step 2 should recreate exactly the three verifiers. | **Not repaired, and turned into a measurement instead.** The sheet keeps the `down`/up and adds step **2b**: take `acknowledge` *before* it. If it reads clean, a later session can retire the instruction with evidence; if it does not, the instruction earned its place. Removing a safety step on an unrehearsed path on the strength of a code reading is the opposite of what this session is for. | Weakening a runbook step by argument is how a rotation becomes a 401 nobody can explain. Measuring it costs one command inside a window that is already open. | — |
| **D1474** | The seven steps, read as a sequence with a redeploy in the middle of it. | **A redeploy between `promote` and the provider move rewrites `active_kid` back to the old key.** `bin/deploy-project.py` derives the jwt block from the key set **file**: `active_kid = kids[0]`, and `bin/render-jwks.py` publishes the auth service's key first and the prepared key last. `retire_after` and `verifier_acknowledgements` are carried forward deliberately; `active_kid` is not carried, it is re-derived. So until step 6 has moved the value at the provider, any deploy silently restores the pre-promotion record while keeping the deadline. | **One line in the sheet**: nothing redeploys that project between step 5 and step 6. Stated rather than guarded — the guard would be a deploy that reads the document it is about to replace, which is a decision. | A code reading, not a measurement: it needs a deploy, and this session has no host. Flagged as a reading so Session 29 can confirm it cheaply or catch it early. | — |
| **D1475** | `bin/rotate-signing-key.sh status`, read at the end of a clean rotation. | **The steady phase reports `promotion BLOCKED on ['mcp', 'postgrest', 'storage']`.** Measured in rig 28d's final `status`, after a successful `retire`: `phase steady -- one key, nothing in flight`, then three lines of `has not acknowledged` and a blocked verdict. The cause is one literal: `retire_rotation` and `abandon_rotation` write `verifier_acknowledgements: {}` where `initial_key_state` writes `None` — and `jwt_keys`'s own docstring says the difference is real, *"an empty object says every verifier was asked and none has answered, and null says nothing has been asked"*. After a retire the second is what is true. | **Recorded, not repaired.** The change is one word in two functions, and `tests/contract/test_jwt_keys.py:468` asserts `{}` after a retire — so it moves a passing contract test and needs an ADR of its own. Session 29's sheet says the line is expected at the end of the window. | The end of a successful rotation looks like a fault, in the one window where an operator is watching for one. | — |
| **D1476** | `loaded_digest`'s own docstring, since Session 8: *"A read of the container's filesystem, not of the host path. The two differ exactly when it matters."* And its test: *"a command written the second way would report every verifier as current no matter what it held."* | **`docker cp` is a command written the second way.** Rig 28j, native `dockerd 27.5.1`, both controls in the same run: before the replace and after a recreate, `docker cp` and `/proc/<pid>/root` agree; **after the atomic replace `render-jwks` performs, `docker cp` returns the HOST's new bytes while the process is still on the unlinked inode.** It re-resolves the bind mount's source path. So `acknowledge` would report every verifier clean the moment the deploy wrote the set, and `promote` — the irreversible step — would unblock on it. Never caught because no rig had ever replaced a key set under a running container: rig 28d made its own "behind" state by recreating onto a different file, which both readers report identically. | **ADR 0215 and the repair.** The reader is `/proc/<pid>/root/<path>`, which traverses the container's own mount namespace, needs no binary inside the image, and needs root — which every step already does. Nine mutations, nine kills. | **D276's symptom arriving through the step built to prevent it.** ADR 0122 chose `docker cp` for a true reason — the distroless PostgREST has no `cat`, exit 127, re-measured today — and fixed READABILITY while silently replacing WHAT WAS READ. Question 4 of §7, exactly: when a defect class was fixed, which side got the fix. | 0215 |
| **D1477** | The obvious next step: measure the new reader on this workstation before shipping it. | **It cannot be measured here.** Docker Desktop runs containers in its own Linux VM, so `docker inspect -f '{{.State.Pid}}'` reports **0** and `/proc/0/root` does not exist; and on the same daemon `docker cp` after an atomic replace does not return the host's bytes either — it **fails at the daemon**, `mount …/docker-desktop-bind-mounts/…: no such file or directory`. Two daemons, two different wrong answers, neither of them the stale bytes the design needs. The measurement that decides the repair is from a native daemon in `dind`. | **The pid of `0` is the third outcome** (ADR 0195): reported, with the cause named, never folded into a reading. And the sheet's step 0 makes it a **pre-flight** — `sudo docker inspect -f '{{.State.Pid}}' <container>` must print a non-zero number before the window opens, not in the middle of it. | A repair verified on a daemon that is not the host's. The pre-flight is what converts that gap from a surprise into a check. | 0215 |
| **D1478** | `test_the_command_prints_no_key_material`'s denylist: `("BEGIN RSA", "BEGIN PRIVATE", "read_bytes()", ".pem")`. | `read_bytes()` was a proxy for *touches a file*, chosen when the command touched none. The repaired reader reads exactly one file — the container's copy of the **public** key set — so the proxy now forbids the reading rather than the material. | **Replaced with a stricter assertion**, which is what an ADR authorises (CLAUDE.md §6): the test now walks the AST and requires that the only functions reading a file are `load_document` and `loaded_digest`. A second read site anywhere in the command fails it, which the string denylist never checked. | A denylist of method names is a proxy; the proxy outlived the shape it stood for. Naming the two legal read sites is narrower than banning a method. | 0215 |
| **D1479** | The live half's first draft, reading a deployed function's shape: `pg_get_function_arguments(p.oid)` compared against `timestamp with time zone, integer`. | **Both halves of that were wrong**, measured in rig 28k against the pinned cluster image. `pg_get_function_arguments` returns `p_before timestamp with time zone, p_limit integer DEFAULT NULL::integer` — the parameter NAMES and the rendered default. `pg_get_function_identity_arguments` drops the default and **keeps the names**. And a zero-argument function answers the identity form with the **empty string**, so `found != ""` cannot tell `agent_record_size` from a function that is not there. | **The proof reads the identity form and asks presence separately**, with the spellings rig 28k printed. The constant carries the measurement and the reason, so the next reader does not re-derive it from the docs. | It would have gone red on its **first execution**, on the host, inside Session 29's window, for a reason about PostgreSQL's spelling rather than about the deployment — the exact cost §7's question 2 exists to avoid, on a proof that by construction cannot run here. |  — |
| **D1480** | Run 3's *Done*: *"`--follows` on any other verb, or without `--project`, is **refused rather than ignored** (exit 2, both in the shell and again in the Python — a flag silently dropped is how an operator comes to believe a record was written that was not)."* | **Both refusals exist and work** — exit 2, with their own sentences, measured — **and no test read either of them.** `grep -rn 'follows' tests/contract/test_cli_contract.py tests/contract/test_printed_commands.py` returns nothing, and Run 3's diff adds no proof over `bin/migrate.sh`. ADR 0210's whole operator surface was unguarded. | **Two proofs in `test_project_migration_sets.py`**, run through `bin/migrate.sh` as an operator runs it (D1114), with **two controls**: the same verb with no flag, and the accepted shape refusing for the manifest's own reason. Both are node ids of `DX-FOLLOWS-001`. Three mutations, three kills. | **A registered requirement clause with no proof is an unverified field one level up** (D1236). Registering `DX-FOLLOWS-001` over the record alone would have registered a requirement whose operator surface nothing checked — and the run that registers it is the only run that would notice. | 0210 |
| **D1481** | Every release since `1.3.0`, in the constant's own comment: *"the next trip's `upgrade plan` is what confirms the class"* — the number left unpriced until a host trip, four releases running. | **The class is decidable here.** ADR 0162's rule is over two RENDERED documents, and a render needs no host and no root. Rig 28l rendered the example project from `72cb2de` (1.6.2) and from this commit and ran `upgrade plan --also migration_added`: **`bump minor`, `requires minor`, verdict `ok`, no blocking reason, and exactly ONE leaf differs — `template_version`.** The control in the same run: without the declaration the same pair requires only a `patch`, so the `minor` is the migration rather than the version string. | **The paragraph above `CURRENT_SESSION` carries the measurement**, and still says Session 29's `upgrade plan` confirms the price against the DEPLOYMENT — an installed document is not a render of the same manifest, and only it can say what an operator must supply. The upgrade guide's `1.7.0` row carries the one-leaf reading. | A stop condition compared against a number nobody computed is a stop condition about whoever is at the terminal. The offline half of it was always available and four releases did not take it. | 0162 |
| **D1482** | Six consecutive gate derivations, and the guard they carry: `assert f"readonly SESSION={SESSION - 1}" in SESSION_PREVIOUS.read_text()`. | **The arithmetic stops being true at this session.** 26 and 27 registered no requirement and have no gate, so Session 28's derives from **25's**; `SESSION - 1` would look for `bin/session-27-check.sh`, which does not exist, and for `readonly SESSION=27`, which nothing holds. Sessions 20-25 each derived from the one before, which is how long it read as a rule. | **`SESSION_PREVIOUS_NUMBER = 25`**, written out with the reason, and **a new proof that no gate exists for either skipped session** — because a `bin/session-27-check.sh` appearing later is what would make the subtraction look right again, quietly. Mutation 12 creates one and the proof kills it. | D719's class inside the guard written to catch a derivation losing something: a literal that was right until the world gained a case. The skip is the record (D1063), and a record has to be asserted somewhere or it is a habit. | — |
| **D1483** | The plan's Run 9: *"`bin/session-28-check.sh`, three modes, Session 25's shape"*, with no note about when its host mode can run. | **Its host mode cannot be run at this commit and must not be.** `agent_record_retention`'s live half reads migration `20260917120033`'s functions, and nothing applies that migration in this session; the deployment is at `1.6.0` / `deployed_through_session` 25. Running it here would report the claim `failed` — the system is wrong — when what is true is that the evidence is not yet collectable. | **The gate's header says so**, in the `--mode host` paragraph and in the preconditions: Session 29 deploys this commit first and sweeps after. `--mode offline` is the only mode this session runs. | `failed` and `not_run` are different verdicts and both exit 5 (ADR 0163). A gate run at the wrong moment turns the second into the first, and this project has written exactly one `failed` claim in its history — its meaning is worth protecting. | — |
| **D1484** | The plan's Run 9 bill: `VERSION`, `CURRENT_SESSION`, both release pages' tables, `apg generate`, the gate, the registry, the derived documents, the ledger and `CLAUDE.md`. | **Sixteen more sites, in five pages, and none of them is on that list.** Moving `CURRENT_SESSION` to 28 left `--session 25` and `--through-session 25` standing in the commands a reader EXECUTES: two in `README.md`, nine in `docs/operator-guide.md` (including the four evidence filenames in its merge block), two in `docs/upgrade-guide.md`, four in `docs/api-operations.md` and one in `docs/pool-operations.md`. `test_the_documented_path_passes_session_numbers_this_release_accepts` caught every one. | **All sixteen moved to 28**, and the guard is in Run 9's targeted list from here on. The bill in §5 was incomplete and this row is the correction. | **`deploy.sh` refuses a number ABOVE `CURRENT_SESSION` and accepts anything below it** (D59), so a reader following the page deploys Session 25 on a Session 28 release and the command **exits 0**. D678's class, fifth occurrence — and the first one a test caught rather than a person. A bump's bill is longer than the artefacts it regenerates. | — |
| **D1485** | `CLAUDE.md`: *"Anything that calls `render_project` must delete what it published under `.generated/<key>`; the gate compares every rendered project for collisions."* | **The rule assumes the directory did not already exist**, and rig 28l rendered `fixture-alpha-dev` — the key the checkout's own test fixtures use. Its cleanup removed a directory it had overwritten rather than created, and two proofs in `test_project_migration_sets.py` then went **red**: `test_each_set_is_rendered_into_its_own_directory_and_names_its_own_table` and `test_the_move_takes_the_project_versions_and_only_those` read the rendered manifest directly, while **five proofs in the same module SKIP** on the same missing precondition with *"no rendered fixture; run ./deploy.sh --render-only"*. | **Recorded, not repaired.** The rig should have rendered under a key of its own; the rule in `CLAUDE.md` should say *delete what you published unless it was already there*. The two hard-failing proofs are arguably the honest pair — a skip is not a pass — but **one missing precondition producing two different behaviours inside one module** is a reading nobody can act on. | A rig that cleans up correctly by the letter of the rule can still destroy workstation state the suite depends on, and the failure arrives several commands later as two tests that look unrelated to it. | — |
| **D1486** | Run 6's *Done* on D1457: *"four proofs still asserted the single cross-set ordering space ADR 0206 replaced … All four now assert what ADR 0206 guarantees."* | **There were five.** `test_dev_environment.py::test_planned_migrations_are_the_rendered_files_in_manifest_order_and_a_moved_digest_is_refused` still asserted `versions == sorted(versions)` over the whole planned list, and **it has been red since `acb08e4`** — Run 6's own commit. Found by `bin/session-01-check.sh` at this run's close: `1 failed, 5999 passed`, *at index 32 diff: `20260917120033` != `20260914120001`*. The rendered manifest lists the release's 33 payloads then the project's 2, each entry carrying its own `dir` and `set`; the concatenation was ascending **by accident** while the example project's `20260914…` stamps sorted after the newest released one, and Run 6's own migration ended the accident. | **Repaired under ADR 0206, no new decision.** The proof now asserts what `bin/dev.py` actually needs: each set ascending **within itself**, one directory per set, the two directories distinct (D1096: two sets sharing one would apply both and record one), and **the release's set planned entirely before any project's** — a project's payloads reference objects the release creates. Three mutations of `verify_rendered_directory`, three kills: interleaving the sets by version, collapsing every `dir` to the release's, and collapsing every `set` label. | **Question 5 of §7, and Run 6 asked it and stopped one reader short.** It greped the render's readers and not `apg dev`'s, which reaches the same manifest through `planned_migrations`. The miss survived the run because `test_dev_environment` was not in Run 6's targeted list and **this project does not read its CI verdict**, so the only instrument that could have caught it was the gate — which is what caught it, five runs later. A per-run targeted list derived from the diff cannot see a caller the diff does not touch; the gate is what does. | 0206 |
| **D1487** | D1373, Session 25: *"the gate ran `set -euo pipefail` with a bare pytest call, so ANY failing proof ended the run before claims were computed … **Both live modes** now write the evidence whether or not the suite passed."* | **The offline mode never got the repair, and this run measured it.** `bin/session-28-check.sh --mode offline` on `c14b0ef` exited **1** — a code the gate's own header does not document — with `evidence/session-28-offline-tests.xml` written and **`evidence/session-28-offline.json` absent**. One red proof anywhere in a 6,008-test sweep, and step 9 never ran. | **The repair, in the third mode.** Step 3 captures `suite_status` and says the half is written anyway; step 9 captures the writer's own status for the exit-5 path, exactly as both live modes do; and a red proof **outside** every claim is reported as exit 6 rather than swallowed. | **Session 28's only half is the offline one.** D1373's own defect, in the mode it was not applied to, would have closed the first session in this project's history whose evidence is entirely offline **with no evidence document at all** — and the operator's signal would have been an undocumented exit 1. D979's rule is the one that was missed: before repairing a function, grep every reader of it. |  — |
| **D1488** | `bin/session-28-check.sh`'s own header: *"This header and the usage block below were REWRITTEN, not patched. Two derivations running have each missed a half of the prose (D853, D858) … both halves are read line by line at every derivation, and the next one should expect to do the same."* | **The third occurrence, in the derivation that carries the warning.** Two comments survived unedited into the body, below the usage block the warning scopes itself to: step 9's said *"TWO of this session's four claims are declared offline — `dx_context`, `dx_walk_instrument` and `dx_hardening`"*, naming Session 25's claims under this session's count, and a D687 note said `deployment_convergence` *"is one of THIS session's four claims"*, which it is not. | **Both corrected**, and the scan that found them is recorded here: `grep` the derived file for every earlier session's claim names, requirement ids and release number, not only for its filename. D693's guard is scoped to the `--session N` an operator TYPES and is right not to flag prose, so nothing automated will catch this. | The warning was read and followed for the header and the usage block, and the body was not — which is what *"each missed a half of the prose"* means, one layer in. A rule that names the two places it applies to becomes a rule about those two places. |  — |


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

Four requirements, four claims — **three after Run 3 resolved the fourth to
*no*** — and the exact ids are Run 9's to register
against the file rather than this plan's to invent (D1347's lesson: a count in a
plan's prose is not a count of the file):

| Subject | Requirement | Claim | Mode |
|---|---|---|---|
| The record a project set carries of the release it was frozen against (ADR 0210) | one `DX-*` | its own | **offline**, declared in `OFFLINE_CLAIMS` (ADR 0202) — it is a property of a checkout and no deployment confirms it |
| What the agent record keeps, and for how long (ADR 0213) | one `SEC-*` or `AGENT-*` | its own | **host**, `not_run` until Session 29 applies the migration. The offline half proves the function and the refusals; the live half proves the prune against a cluster with history |
| The reading before a tag (ADR 0214) | one `REL-*` | its own | **offline** |
| ~~The host interpreter, if Run 3's ADR 0158 reading takes a third mode (D1418)~~ | — | — | **RESOLVED `no` in Run 3.** The split admits no third reading (D1441): the host's interpreter is a property of the machine and of no project, and adding it to deployed mode puts a bare `python` resolution back under `sudo`. Stated at the split, no check added, **no requirement and no claim**. §10 row 11. |

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

**Done.** 2026-09-16, on `3c1e48f`. ADR 0210 and ADR 0211 built, F-020 closed,
D1418 answered *no*, `docs/on-ramp.md` written, and **D1440–D1443**. Six
mutations, six kills, no survivors, every control green in the same invocation.

*ADR 0210, in the code.* `build_lock` carries
`follows_release_version_source`; `follows_record` reads it, treating a
schema-2 lock as `computed` (which is what every lock written before ADR 0210
is) and **refusing a schema-3 lock that omits it**, because there the absence
means something was lost rather than something predates the field.
`assert_declarable_release_version` checks a declaration against the release's
append-only manifest and says at its own definition what that proves and what
it does not. `bin/migrate.sh --project <manifest> freeze-lock --follows
<version>` is the operator surface; `--follows` on any other verb, or without
`--project`, is **refused rather than ignored** (exit 2, both in the shell and
again in the Python — a flag silently dropped is how an operator comes to
believe a record was written that was not). **The refusal is unchanged byte for
byte**; its remedy is not, and `bin/migrate.sh --help` moved with it.

- **The project lock schema moves 2 → 3, and Run 9's bump note owes that
  sentence.** `projects/example/migrations/released.lock.json` was moved to 3
  **surgically rather than by re-freezing**: a re-freeze recomputes
  `follows_release_version` from this checkout, which would have moved the
  example's record from `20260912120031` to `20260912120032` — a different
  statement about when that set was reviewed, made by accident. Measured both
  ways before choosing.

*ADR 0211, in the refusal.* The allowlist is byte-for-byte what it was. The
message now names `0006`, states that the copied grant reaches nothing, and
ends *"removing the line changes nothing your cluster does"* — and the detail is
**keyed on the source**, so the other six forbidden sources get the message they
always had. Both arms are asserted, because a sentence appended to every
placeholder refusal would be noise rather than an answer.

*F-020 / D1423, and the finding's own prediction was right.* *"Report the
commit"* was not printing a field this verb had: a **rendered** document carries
no `source_commit` at all — the field belongs to the **deployed** document,
which `upgrade check` never read. It reads it now, through `--deployed FILE` for
a checkout the way `--installed` already worked. `upgrade_plan.read_checkout_commit`
answers the other side with three outcomes and a `CommitReading` that renders
each of them as a sentence: a checkout that is not a git working tree — which is
what an adopter's tarball fork and this product's own `git bundle` transport
both produce — says so. **`commits_agree` is `null` unless both sides were
read**, and the human line says UNDETERMINED rather than THE SAME.

*D1418, answered `no`, and §2's conditional row resolves with it.* ADR 0158's
split admits no third reading (D1441). Stated at the split in `bin/doctor.sh`'s
own header and in `scope-closure.md` §15; **no check added, no requirement, no
claim.**

*F-022, reproduced rather than quoted* (D1442). The release's own `contract and
p0` sweep against rig 28a at the merged pre-conversion state: **52 failed, 5,692
passed, 3 skipped, 49 errors** against the adopter's *47 failures and 49
errors*, with the unforked checkout as the control in the same session — **5,800
passed, nothing red**. The shape is the finding: the failures are almost entirely the
reviewed-surface family, and **`test_migrations` passes**. The gate does not
object to the fork's migrations; it objects to the fork's relation sitting in
`contracts/postgrest-api-surface.yaml`. That is why F-022's answer is the
conversion and not a gate change.

*What Run 3 did NOT do.* No released migration and no bump — Run 9 owns
`VERSION`, `CURRENT_SESSION` and the registry, and the project lock schema move
is on its bill. **No conversion performed against a cluster with history**
(D940); `docs/on-ramp.md` names step 7 as the step a checkout cannot prove and
tells the adopter to read their own ledger on a copy first.

*Ran before the push*, once: `test_project_migration_sets`, `test_migrations`,
`test_migration_ledger`, `test_rendered_migrations`, `test_upgrade_plan`,
`test_upgrade_command`, `test_cli_contract`, `test_dx_record`,
`test_documentation_index`, `test_session12_documented_path`,
`test_acceptance_registry` (D1119 — this run adds test functions),
`test_mcp_catalog` (it reads `docs/plans/*.md`). Plus the battery. CI is the
full check.

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

**Done.** 2026-09-17, on `873bdfd`. Four readers repaired or decided, **seven
mutations, seven kills, no survivors**, every control green in the same
invocation. **D1444–D1446.**

*`render-jwks` (D1374, D1427).* Three readings, in the caller, from a
module-level `key_set_reading()` rather than a branch inside `main()` — because
`main()` refuses a non-root caller before it reaches anything, and a proof that
needed root to read a sentence would never run in the suite that matters.
`had_previous` is read **before** the write, which is the only moment the answer
exists. **`write()` is untouched**, and a proof asserts that it still
byte-compares: the repair the audit asks for — compare the key set, not the file
— destroys the property its docstring protects, because the file's mtime is the
only signal a reader has that a rotation happened. The third outcome names the
reading that does answer (`rotate-signing-key.sh … acknowledge`) rather than
reporting nothing, and the operator guide and the upgrade guide both moved,
each saying which release the old sentence belongs to.

*The provider refusal (D1045, D1426), and Run 4 produced ADR 0195's own class
in its first draft* (D1445). The clause reads `Content-Length` and has **three**
answers: explained, not explained, and *cannot be told from here* — a response
declaring no length is chunked, and finding out would mean reading the body,
which is the thing the clause exists not to do. The first draft used
`exc.length`, which is not a property of the response at all but a delegation
through `HTTPError.__getattr__`; **the proof caught it on first execution**. No
body appears in any arm and the proof asserts that on all three.

*The served document (D387, D1446).* `observe_served_document` returns a
`ServedDocument` instead of `None`, and the deploy wraps it in
`await_observation` as it already does for its five neighbours. **Only
`unreachable` is unsettled**: a documentation token that cannot be minted is
deterministic, and retrying it would spend the window and print one line thirty
times. The two failures print different sentences.

*`mcp_tracing.configure()` (D1413, D1444), and the ledger's stated reason is
refuted.* *"Scraping a project's services must answer the network question
first"* is about a collector reaching a service; this is a push. Measured: `mcp`
is on `internal` and `edge`, the collector is on `edge`, `edge` is per project
(`apg-<key>-edge`), and the exporter is already a pinned build argument on the
service. Nothing about the network blocks a caller. **Neither a caller nor a
deletion**, with the true reason at the function and a test that goes red if a
caller appears **or** if `span`'s caller disappears.

*Ran before the push*, once: `test_runtime_override`, `test_secret_origin`,
`test_observation`, `test_mcp_tracing`, `test_deploy_command`,
`test_jwt_keys`, `test_rotate_signing_key`, `test_verifier_key_sets`,
`test_cli_contract`, `test_acceptance_registry` (D1119 — this run adds test
functions), `test_mcp_catalog`. Plus the battery. CI is the full check.

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

**Done.** 2026-09-17, in two commits — `edc3b41` and this one. **D1447–D1456**,
and all but two came from a proof's first execution or from the run's own
battery. Eleven mutations, **eleven kills after one survivor was repaired**,
every control green in the same invocation.

*The survivor is the run's own finding and it is the shape Tier 1c is about*
(D1454). The SQL-signature guard went green over 140 references, and a mutation
that removed its comparison **survived**: `stale` is empty whether the walk
compares or not, on a tree where nothing is stale. `checked >= 135` said the
guard LOOKED and nothing said it COMPARED. The walk is extracted and given a
positive control — three synthetic templates, including one grant that matches
its declaration and must NOT be reported. *A value that looked measured and was
not*, in a guard four hours old, found by the battery the run owed anyway.

*What each item cost, and what it found:*

- **D1240 / D1421 split 1 + 3** (D1447). A registered P0 proof that only a host
  trip ever ran; three modules no registry names. The stated worry about the
  service tree is refuted by `pytest.ini`. 0 → 82 under the gate's selector.
  **Guarded against the class**, not the four: every test module that defines a
  test carries a module marker, asserted over 180+ modules with the empty
  placeholder excluded by condition rather than by name.
- **D942's two blind spots, built** — 140 SQL signatures checked against the
  declaration live *at that migration*, and RPC bodies checked by parameter
  NAME. Three findings on the way in (D1448, D1449, D1450), one of which —
  `_arguments` being unbounded — meant the ADR 0175 guard's verdict on a
  docstring example could be changed by editing an unrelated part of the same
  file.
- **D1422's stated limit**, in both directions, not a parser.
- **D1414** onto the module's own `refused()` shape; **D1420**'s two premises,
  each with a control.
- **D1430 / D297 taken** — `bin/lock-dev-deps.sh --check-environment`, in the
  gate's step 2, beside the `--check` it was confused with for twenty-two
  sessions. The remedy is the point: three gate deaths ended in a module name.
  **It found a second defect on the way in** (D1451): the orphan guard's shell
  scan reads a module name plus the word that follows it, and mangles seven of
  the thirteen names it produces.
- **`test_honest_readers`' `sudo -u` re-entry RAN** (D1455, rig 28c), as uid 0
  in a container, and **passed** — the thirteenth never-executed proof and the
  first not to fail. Six repairs had already reached it from adjacent
  evidence.
- **D1429's live half written** (D1453), `not_run` until the trip; **D1282
  corrected** (D1452) — the trap is loud, not quiet; **the uncached `apg dev up`
  row closes by saying so** (D1456), because the claim is already in the
  envelope the row names.
- **D1431 / D201 recorded in §10** and separated from D1430, as planned.

*Ran before the push*, once: the twelve modules of the first half, plus
`test_repository_contract`, `test_acceptance_registry`, `test_session24_studio`
(collection), `test_session21_agent` (collection), `test_honest_readers`, and
the gate's two collection selectors. Plus the battery. CI is the full check.

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

**Done.** 2026-09-17. **D1457–D1462**, ADR **0213**, migration
`20260917120033` — the only schema this session moves. Eleven mutations,
**eleven kills, zero survivors**, every control green in the same invocation and
all four mutated files restored byte-identical.

**Rig 28b decided the ADR, and the finding is that this was never one question.**
A cluster carrying every released migration and the example project's set, built
by the product's own bootstrap statements and applied as `migration_user` over
TCP, with history seeded in both tables across the shapes the plane writes.
Six measurements, before a line of the migration was written:

1. **Nothing reachable can delete a row today** — the ACL on both tables is the
   object owner's alone, and a `DELETE` by `SET ROLE` into `auth_service`,
   `agent_writer`, `agent_reader` and `authenticated` is *permission denied* in
   all four. So **granting the prunes to nobody preserves the posture rather
   than narrowing it**, which is what makes that the cheap answer rather than
   the cautious one.
2. **Neither table carries a foreign key.** The only one among the three agent
   tables is `agent_quota.agent_id`, 0028's own `ON DELETE CASCADE`.
3. **Both prunes are `Seq Scan`s**, and no index is added (D1461).
4. **Pruning an idempotency claim re-arms its key, silently** — with the control
   in the same run (D1460). The two tables are a record of the past and a
   promise about the future, and three documents closed them with one sentence.
5. **There is no safe subset of that table**: `auth_rotate_agent_secret` returns
   a revoked agent to `active` with the same id, so a revoked agent's keys are
   dormant, not dead. **This was the alternative this run expected to take.**
6. **20,004 rows, fourteen days**: unbounded removed 9,921 in 141 ms, bounded
   removed 500 in 147 ms. The bounded form is not the faster one, which is the
   opposite of what the file said before the rig ran (D1461).

*What shipped:* three functions in `app_private` and **no scheduled anything** —
`agent_audit_prune` and `agent_idempotency_prune`, granted to nobody, each
refusing a missing horizon, a future horizon and a bound below one; and
`agent_record_size()`, granted to the record's existing reader because it adds
no audience and no fact. A proof scans `src/`, `bin/`, `services/` and the
templates for a caller of either prune, so *nothing deletes an agent record on
its own* is structural rather than remembered.

*The doctor's eleventh check* (D1462) reports the two counts and the date the
record starts and **has no threshold**, because D1441 — three runs earlier, in
this command — is the argument against inventing one. It reads the two tables
and not the new functions, so the count follows the checkout: a 1.7.0 checkout
reads eleven against a deployment at any release, and Session 29's pre-upgrade
reading is untouched.

*Found on the way in, and both are first executions.* **D1457**: four proofs
still asserted the single cross-set ordering space ADR 0206 replaced — the rule
whose collapse took beta's deploy down at Session 24 — green for four sessions
because no release had added a migration since that ADR. **D1459**:
`bin/doctor.sh` has said *seven live checks* since Session 18 while `diagnose()`
appended ten, and the operator guide on the same page said ten. **D1458** is the
cheap half of D1457: a fixture that only reached its subject while two unrelated
stamps happened to sort a particular way.

*Ran before the push*, once: the agent-plane module whole (62), the migration
and ledger modules, `test_diagnosis`, `test_doctor_redaction`,
`test_migrations_apply_as_the_migration_user`,
`test_database_function_signatures`, `test_acceptance_registry` (D1119 — a test
was renamed and the registry's node id moved with it), `test_rehearsal`,
`test_backup_mirror`, `test_fleet`, `test_diagnostic_surface`,
`test_cli_contract`, `test_documentation_index`, `test_repository_contract`.
Both fixtures re-rendered. CI is the full check.

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

**Done.** 2026-09-17. **D1463–D1467**, ADR **0214**, one new operator command
and one pure module. Eleven mutations, **eleven kills, zero survivors**, every
control green in the same invocation, all three files restored byte-identical.

**The ADR took the command — and the measurement changed what the command is
allowed to say.** Rig 28c, five passes over this repository's own history, every
number read from `git`:

1. **Five of five.** Every tag has release bytes landing past it, and `1.0.0`'s
   next commit is a product repair in `bin/` (D1463). D1424 said three times.
2. **The obvious discriminator does not exist** (D1464). Records-versus-release-
   bytes puts the two defects and the three ordinary cases in the same bucket:
   release bytes land within one to five commits of every tag, always, because
   the next session starts.
3. **The naive verdict fires on 45 of 147 commits** (D1465) — a third of the
   history, which is how the prose checklist earned its reputation.
4. **The counts are the part a person cannot supply.** At `acb08e4`: 32 released
   migrations at the tag against 33 in the tree, 209 ADRs against 213, 61 files,
   ten commits, and `VERSION` unmoved. Nobody reconstructs that by hand.
5. **A test could not take this reading in CI** (D1466). Only the gate job checks
   out with `fetch-depth: 0`; the suite's job and the inventory job take
   `actions/checkout`'s default, and a depth-1 clone measured beside a full clone
   of the same commit reports **zero** tags and a fatal `git describe`.

*So it is a command AND a checklist, and the split is decided by what is
computable.* `bin/release-reading.sh` prints where HEAD stands, the last tag and
the `VERSION` it carries, what has landed since, released migrations and ADRs at
the tag against the tree, and the bump commit with everything after it — then
three questions in the second person that it does not answer. **The checklist is
inside the command rather than beside it**: a page can go stale, can be skipped
by somebody who ran the command, and asks a person to gather the facts as well
as judge them, which is the arrangement that failed five times.

*Four outcomes, three of them ordinary and one of them ADR 0195's third*:
`tag_is_owed`, `tag_does_not_contain_these`, `nothing_to_decide`, and
`no_tags_in_this_clone` — the only one that is not exit `0`. **It never fails
closed on a judgement, because it makes none**; it exits `3` when it could not
take the reading at all, which is the opposite. And it is deliberately **not in
the gate** (D1467).

*The battery's one survivor, repaired*: a mutation that gave the untakeable
reading the three questions anyway lived, because
`test_a_reading_that_could_not_be_taken_asks_nothing` read only the rendered
lines — and `render` returns early for that outcome. The test now asserts the
`Reading` as well as the print. The re-run is eleven kills, zero survivors.

*Ran before the push*, once: the new module (22), `test_cli_contract`,
`test_acceptance_registry` (a module was added), `test_printed_commands`,
`test_documentation_index`. **Nothing is applied to a deployment. No bump, no
tag.**

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
**Done.** 2026-09-17. **D1468–D1478**, and **ADR 0215** — which a rehearsal is
not supposed to need. Nine mutations over the repair, **nine kills, zero
survivors**, every control green in the same invocation, both files restored
byte-identical. The sheet is **Appendix R**; `docs/operator-guide.md` §15 is the
operator's copy.

**Rig 28d ran the cutover end to end**, as root through a user namespace (the
identity the gate has in CI, D1310), against three containers carrying the real
Compose labels and the real container paths — `postgrest` being the **locked
distroless image**, measured to stay up retrying a database that is not there,
which is what makes it usable as a live verifier. Every step was
`bin/rotate-signing-key.sh`, including `promote`'s typed confirmation:

| | |
|---|---|
| `render-jwks`, three readings | `published` (no previous copy), `confirmed` (unchanged), `wrote … the key set CHANGED` — **D1374's repair, read for a decision for the first time** |
| `acknowledge`, all three behind | three remedies printed, exit 0 |
| `status` | `promotion BLOCKED on ['mcp', 'postgrest', 'storage']` |
| `promote`, blocked | **exit 6**, naming the three |
| `acknowledge`, after a recreate | three × `holds the published set` |
| `promote` | accepted, `retire_after` set, the follow-up printed |
| `retire`, early | **exit 6**, naming the moment |
| `abandon`, after promotion | **exit 6**, *"complete it forward"* |
| the wait | **930 s**, waited out rather than edited |
| `retire` | accepted, one kid left, `retire_after` back to `None` |

**Then the rehearsal found what it was for, and it is not in the seven steps.**
Rig 28j, a native `dockerd 27.5.1`, both controls in one run: `docker cp` — the
reader behind `acknowledge`, and therefore behind `promote`'s refusal —
**returns the HOST's bytes after an atomic replace**, while the process is still
on the unlinked inode (D1476). `loaded_digest`'s own docstring and its own test
say that a command written that way *"would report every verifier as current no
matter what it held"*. It was written that way. **ADR 0215** replaces the reader
with `/proc/<pid>/root/<path>`, which traverses the container's own mount
namespace and needs no binary inside a distroless image; a pid of `0` is the
third outcome, reported, never folded (D1477), and the sheet turns it into a
pre-flight.

*What the rehearsal could not do*, measured rather than assumed: **no rig can
run the three claims' proofs** (D1468) — all nine node ids are `live_host` and
`--setup-plan` skips all nine. And **the three claims need four rotations**
(D1469): the cutover moves one of the nine node ids, and a claim is `not_run`
unless every one passed, so this window alone moves **no claim**. Four trips
have offered *the rotation* as if it were one act.

*Also found*: the signing-key proof is red between `promote` and `retire` by
design, so the sweep goes after step 7 (D1470); `auth_jwt_signing_key` reads as
replaceable and replacing it publishes a set with **zero overlap** (D1471, rig
28e); the gate's help says four verifiers where the roster is three (D1472); the
`down`/up may be three sessions out of date, and the sheet makes it a
measurement rather than removing it (D1473); a redeploy between `promote` and
the provider move restores the pre-promotion record (D1474); and the end of a
clean rotation prints `promotion BLOCKED`, because `retire_rotation` writes `{}`
where `initial_key_state` writes `None` (D1475).

*Ran before the push*, once: `test_rotate_signing_key` (20), `test_jwt_keys`,
`test_rotation_surface`, `test_cli_contract`, `test_acceptance_registry`,
`test_documentation_index`, `test_repository_contract`. **Nothing is applied to
a deployment. No bump, no tag.**


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
- **`bin/apg.sh release-reading`, run on the bump commit, and what it printed
  quoted in this plan's Run 9 Done** (ADR 0214). It will read `tag_is_owed`:
  `VERSION` `1.7.0` with no tag carrying it. **That is the reading's first use,
  and Session 29 takes it again on the commit it actually tags** — this session
  does not tag, so the answer to its third question here is *no*.

**`bin/session-01-check.sh` runs once, on a clean tree, before the push**, and
`bin/session-28-check.sh --mode offline` writes `evidence/session-28-offline.json`.
Then `git diff --stat` against this plan's list, one line each, **before** the
push — a commit message is not evidence that the diff contains what it says
(D1116). Then CI's verdict on that commit by full SHA.

**And then nothing.** No tag. Session 29 deploys this commit, sweeps, and tags it.

**Done.** 2026-09-17, in three commits — `c14b0ef` (the bump), `1cde025` (three
defects the gate found) and this one. **D1479–D1488**, three requirements, three
claims, and **nineteen mutations with nineteen kills and zero survivors**, every
control green in the same invocation and every mutated file restored
byte-identical.

**The run is three commits because the gate found three defects and one of them
was in the gate this run wrote.** That is the shape of the close rather than an
accident of it: `bin/session-01-check.sh` refuses a dirty tree, so the sequence
is commit, gate, repair, commit, gate again — and the second pass is the one
that counts.

*The bump.* `VERSION` **1.6.2 → 1.7.0**, `CURRENT_SESSION` **25 → 28**, in one
commit with the client regenerated (D1238 — `templateVersion` moved in
`contract.ts` and `generated.json`, and `apg generate --check` exited 5 before
it did), both release pages' tables carrying a `1.7.0` row, the acceptance
matrix and the product contract regenerated from the registry, and
`app-contract --check`, `mcp-contract check` and `apg generate --check` all 0.

*The class was priced here, and four releases did not do that* (D1481). ADR
0162's rule is decidable from two RENDERED documents and a render needs no host
and no root, so rig 28l rendered the example project from `72cb2de` and from
this commit and ran the product's own `upgrade plan --also migration_added`:
**`bump minor`, `requires minor`, verdict `ok`, no blocking reason, and exactly
one leaf differs — `template_version`.** The control in the same run is what
makes that mean something: without the declaration the same pair requires only a
`patch`, so the `minor` is the migration rather than the version string.

*The registry.* `DX-FOLLOWS-001` → `project_set_release_record` (offline,
declared), `AGT-RETAIN-001` → `agent_record_retention` (**host**, `not_run`),
`REL-READ-001` → `release_reading` (offline, declared). **No claim for the
rotation**, on D1469's measurement rather than on modesty.

*Registering the first of them found that ADR 0210's whole operator surface was
unproven* (D1480). Both `--follows` refusals work — exit 2, their own sentences,
measured — and **no test read either of them**; Run 3 built the refusal and
wrote no proof over `bin/migrate.sh`. Two proofs now do, run as an operator runs
them, with two controls: the same verb with no flag, and the accepted shape
refusing for the manifest's own reason. Three of the battery's mutations are
theirs.

*The live half is written and cannot be run here, which is the design* (D1483).
Six proofs in `tests/deployment/test_session28_retention.py`, `live_host`, over
both projects. **Nothing in it deletes a row of the agent record**: the one
proof that runs a prune against the real record runs it inside a transaction it
rolls back, with the row count before and after as the control — ADR 0182's
shape applied to the one function in this release whose job is destructive. Rig
28k measured the two readings it depends on **before it was written** (D1479):
`pg_get_function_arguments` returns the parameter NAMES and the rendered default
(`p_before timestamp with time zone, p_limit integer DEFAULT NULL::integer`),
the identity form keeps the names and drops the default, and a zero-argument
function answers the identity form with the **empty string** — so the first
draft would have gone red on its first execution, on the host, inside Session
29's window, for a reason about PostgreSQL's spelling.

*The gate.* `bin/session-28-check.sh`, derived from 25's by diff with every
substitution asserted to match exactly once, three modes, `--kit-dir` still on
`kit-2026-09-11` with the flag's help still saying why (D1282), and **the
four-verifier count repaired to three** with ADR 0098's reason written in
(D1472). `apg release-reading` is deliberately not a step in it (D1467).
`test_session_twenty_eight_gate_modes.py` carries **`SESSION_PREVIOUS_NUMBER`
rather than `SESSION - 1`** (D1482): 26 and 27 have no gate, the subtraction was
true for six derivations running, and a new proof kills a `bin/session-27-check.sh`
appearing later — which is what would make the arithmetic look right again,
quietly.

*Found by a guard, late, and the plan's bill was short* (D1484). **Sixteen
`--session 25` and `--through-session 25` in the commands a reader EXECUTES**,
across `README.md`, the operator guide, the upgrade guide, `api-operations.md`
and `pool-operations.md`. `deploy.sh` refuses a number above `CURRENT_SESSION`
and accepts anything below it, so a reader following the page deploys Session 25
on a Session 28 release and the command exits 0. D678's class, fifth occurrence,
first one a test caught rather than a person.

*Recorded, not repaired* (D1485): rig 28l's cleanup removed `.generated/fixture-alpha-dev`
— a render fixture the checkout already held rather than one the rig created —
and two proofs in `test_project_migration_sets.py` went red on its absence while
five in the same module SKIP on the same missing precondition.

*The reading, taken on the bump commit* (ADR 0214, D1424's close), quoted as
`bin/apg.sh release-reading` printed it at `c14b0ef`:

```
  outcome: tag_is_owed
  the tree says 1.7.0 and no tag carries it: a tag is owed, and what follows is what it would contain.

  The last tag            1.6.2 at e2ba6e7f184b, 2026-09-16, VERSION at it 1.6.2
  What has landed since   13 commits, 83 files
                            25  tests/contract      15  bin        13  docs
                             8  src/agentic_postgres 7  docs/decisions
                             4  tests/deployment     3  projects/example
  Counts a release moves and nobody remembers
    released migrations        32 -> 33       <- moved
    ADRs                      209 -> 215      <- moved
  The bump                c14b0ef519b8, 21 file(s) moved with it, commits after it 0

  What this command does not decide
    - Does everything in this window belong inside 1.7.0?
    - Is there anything you intended to be in 1.7.0 that is not in this list?
    - Is this commit the one the tag goes on?
```

**The answer to its third question, here, is no**, and that is the whole shape
of the session (D1425). It prints no instruction about the tag, which
`test_the_reading_prints_no_instruction_about_the_tag` keeps honest, and both
counts it flags as moved are this session's: migration `20260917120033` and ADRs
0210–0215.

*What the gate found, and it is the reason this run is two commits.* The first
pass, on the clean tree at `c14b0ef`, came back **`1 failed, 5999 passed`** —
and the failure was five runs old. `test_dev_environment.py` still asserted
`versions == sorted(versions)` across **both** migration sets, the single
ordering space ADR 0206 replaced; Run 6's *Done* says D1457 found four such
proofs and repaired all four, and **there were five** (D1486). This one reaches
the rendered manifest through `apg dev`'s `planned_migrations` rather than
through the render, so a grep of the render's readers never saw it. It had been
red since `acb08e4`, Run 6's own commit: the manifest lists the release's 33
payloads then the project's 2, and the concatenation was ascending **by
accident** while the example project's `20260914…` stamps sorted after the
newest released one. Run 6's own `20260917120033` ended the accident. Repaired
under ADR 0206 — each set ascending within itself, one directory per set, the
two distinct (D1096), and the release's set planned entirely before any
project's — with three mutations of `verify_rendered_directory` and three kills.

*And the same pass found a defect in the gate this run wrote* (D1487).
`--mode offline` exited **1** — a code the gate's own header does not document —
with the JUnit written and **`evidence/session-28-offline.json` absent**. D1373
repaired the failing-suite path in **both live modes** and left the offline one
under `set -e` with a bare pytest call, so one red proof in a 6,008-test sweep
ended the run before step 9. **Session 28's only half is the offline one**, so
that defect would have closed the first session in this project's history whose
evidence is entirely offline with no evidence document at all. Repaired in the
third mode, the way the other two were.

**The guard against exactly this checked two of the three callers.** Session
25's `test_a_failing_suite_does_not_stop_the_evidence_being_written` asserts the
repair in `live_host` and `external`, pins `suite_status=0` at **2**, and closes
its own docstring with *repairing one caller of a decision and leaving the other
is §7's fifth question* — while leaving the offline caller unrepaired and making
the count a tripwire against repairing it. It is now derived rather than listed:
every sweep that writes a JUnit captures its status, which stays true when a
fourth mode arrives, and step 4's collection check is excluded by that same rule
because it writes no JUnit and is a prerequisite that *should* end the run.
Three more mutations, three kills. **Session 25's gate is not edited** — it owns
its session and its evidence is written; the row is where a reader of that gate
will find the defect.

*The third one is this derivation's own* (D1488). The gate's header warns that
two derivations have each missed a half of the prose (D853, D858) and says to
read it line by line — and two comments **below the usage block the warning
scopes itself to** survived unedited: step 9's named Session 25's three claims
under this session's count, and a D687 note called `deployment_convergence`
*"one of THIS session's four claims"*. A rule that names the two places it
applies to becomes a rule about those two places.

*The gates, on the clean tree at `1cde025`.* `bin/session-01-check.sh` **exit 0,
PASSED** — `6000 passed, 0 failed, 3 skipped, 0 errors`, 6382 P0 collected, 0
future placeholders, 0 identity collisions, 0 floating image refs.
`bin/session-28-check.sh --mode offline` **exit 0, PASSED** — `6009 passed, 0
failed, 3 skipped, 0 errors` — and it wrote `evidence/session-28-offline.json`
carrying **thirteen claims, every one passed**, including this session's two:
`project_set_release_record` and `release_reading`.
`agent_record_retention` is not in it and must not be: it is a host claim and
Session 29 collects it after the deploy that applies the migration.

*The D1116 check*, against this section's own list rather than against the
commit messages: `VERSION` 1.7.0 · the paragraph prices it once · both release
pages state 1.7.0 and the upgrade guide's table has the row · 222 requirements
with the three new ids present · the three claims resolving `offline`,
`host`, `offline` at session 28 · 129 claims and 13 declared offline ·
`bin/session-28-check.sh` `100755` in the index, `SESSION=28`, `kit-2026-09-11`
kept, **three** verifiers and no *four*, three sweeps and three writers
capturing their status · the live half's six proofs, one `live_host` mark and
three `ROLLBACK`s · `templateVersion: "1.7.0"` in the committed client · 83
divergence rows · **no tag on HEAD, `migrations/` untouched since `72cb2de`, no
operator input and no evidence tracked**.

**Nineteen mutations across the run, nineteen kills, zero survivors**, every
control green in the same invocation and every mutated file restored
byte-identical. Three of the first six were uninformative or reached their own
control and were replaced rather than counted (D493, D499).


*Ran before the push*, once: `test_project_migration_sets`,
`test_release_contract`, `test_documentation_index`, `test_acceptance_registry`
(D1119 — this run adds test functions and registry node ids),
`test_evidence_claims`, `test_cli_contract` (D1014/D1188 —
`bin/session-28-check.sh` was `git add`ed first), the new
`test_session_twenty_eight_gate_modes`, `test_session_twenty_five_gate_modes`
(a derivation must not edit what it derived from), `test_session12_documented_path`,
`test_mcp_catalog`, `test_repository_contract`, `test_printed_commands`,
`test_client_typescript`, `test_generate_command`, `test_dx_record`,
`test_release_reading`, `test_rendered_migrations`, `test_migrations`. Plus the
battery, rig 28k and rig 28l. CI is the full check.

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

### Deferred by name, with the reason — eleven rows

Each of these is a Tier 1 row this session does **not** close. The brief's rule
is that a plan which silently drops rows is worse than one that names them.
**Seven were named at planning; Run 1's measurements added three more** (8–10),
and each of those three was deferred for a reason the audit's row does not
carry. **Run 3 added the eleventh**, which its own plan text anticipated: D1418
is deferred only if ADR 0158's split admits no third reading, and it does not.

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

11. **D1418 / F-026 — the interpreter on the deployment host is unchecked, and
    it is a consequence of ADR 0158's split** (D1441, measured in Run 3).
    Workstation mode checks a developer's own interpreter and is unprivileged;
    deployed mode checks seven live things about one PROJECT and needs root. The
    host's interpreter is a property of the machine and of no project, so it
    belongs to neither question as they are drawn, and adding it to deployed
    mode puts a bare `python` resolution back under `sudo` — the exact failure
    the split's own comment says the split prevents. The only host-wide checker
    is `provision-host.sh --check`, which runs **as root on production**, and no
    session has measured which interpreter versions this product requires on a
    host: `.python-version` is the workstation pin, and the cold reader's host
    ran every `bin/*.sh` under 3.14 against a pin of 3.12.13 and worked. A check
    added on that footing could fail a host that works, in a session with no
    trip to measure it on. **Stated at the split rather than repaired**, and
    §2's conditional requirement row resolves to *no requirement, no claim*.

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

---

## Appendix R — Session 29's signing-key rotation, numbered

**Rehearsed offline in rig 28d on 2026-09-17** (Session 28 Run 8): every step
below except the provider edits and the deploys was executed against real
containers holding a real key set, with `bin/rotate-signing-key.sh` as the only
operator command. What was *not* rehearsed is named in each step.

**Alpha first, then beta.** Beta's window does not start until alpha's `status`
reads `steady`.

**Who does what.** The agent runs every `op`-side line over SSH. Every line
below marked **[sudo]** is for the human at a TTY: `rotate-signing-key` requires
root for *every* step including `status`, because the deployed document and the
secret generations are root-owned and reading a verifier's key set means
reaching its container.

### Before the window

| # | Who | What |
|---|---|---|
| 0.1 | agent | `ssh op@… 'cat /opt/agentic-postgres/rendered/<key>/jwks.json'` — **capture the retiring key's JWK now.** After step 7 it is not in the published set, and `--rotated-jwt-from-file` wants exactly this object. The file is `0444` by design, so `op` can read it without root. |
| 0.2 | **[sudo]** | `sudo bin/rotate-signing-key.sh --outputs /home/op/<key>-dev-outputs.json status` — expect `phase steady -- one key, nothing in flight` and `acknowledged nothing has been asked`. **If it says anything else, stop**: a rotation is already in flight. |
| 0.3 | **[sudo]** | `sudo bin/doctor.sh --project <key>` — the reading this window is measured against. Session 28's tree adds an eleventh check; a deployment at 1.6.x reads ten. |
| 0.4 | **[sudo]** | **`sudo docker inspect -f '{{.State.Pid}}' <any container of this project>` must print a NON-ZERO number.** `acknowledge` reads each verifier's key set through `/proc/<pid>/root/…` — the container's own mount namespace — because `docker cp` resolves the bind mount's source path and returns what the deploy wrote rather than what the process holds (ADR 0215, D1476). A daemon that does not run its containers on this kernel reports `0`, and `acknowledge` refuses rather than reading another way. **Ask this before the window, not inside it.** |

### The seven steps

| # | Who | What | Rehearsed? |
|---|---|---|---|
| 1 | operator, at the provider | Generate the prepared key **the way the product does**: `openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -outform PEM`. Paste it into `APG_AUTH_JWT_PREPARED_KEY` at `/auth` in this project's Infisical project. **No command here writes a provider value** (D249). | not rehearsed — a provider edit |
| 2 | **[sudo]** | Redeploy. `render-jwks.py` sees the prepared key and publishes its public half beside the active one; it prints **`wrote … the key set CHANGED: every verifier must be RECREATED`**. | rehearsed: all three of `render-jwks`'s readings fired (D1374's repair, live) |
| 2b | **[sudo]** | **`sudo bin/rotate-signing-key.sh --outputs … acknowledge` — before step 3, and this is a measurement rather than a step** (D1473). Since D591 the deploy labels each service with a digest of its mounted content and Compose recreates exactly the services whose content moved; `jwks.json` is a bind mount of all three verifiers, so the redeploy above should already have recreated them. If this reads clean, step 3 is unnecessary and a later session can say so with evidence. **Whatever it says, do step 3 anyway.** | the mechanism is read from the code; nothing has measured the deploy |
| 3 | **[sudo]** | `sudo bin/project-runtime.sh --host host.yaml --project-key <key> --through-session N down`, then redeploy. **A restart is not enough.** | rehearsed as a recreate; `down` + redeploy on a host is not |
| 4 | **[sudo]** | `sudo bin/rotate-signing-key.sh --outputs … acknowledge`. Expect three lines, each `holds the published set`. **THREE, not four** (D1472): `postgrest`, `storage`, `mcp`. `auth` is the issuer and is deliberately not a verifier — an acknowledgement from it would be the issuer agreeing with itself (ADR 0098). **What this reads is now the process's copy** (ADR 0215): before Session 28 it read the host's, which would have said `holds the published set` for a verifier that had never been recreated. | rehearsed, both ways: three behind, then three clean |
| 5 | **[sudo]** | `sudo bin/rotate-signing-key.sh --outputs … promote`. It prints `status` first, then asks for the literal word `PROMOTE`. **Irreversible.** It refuses with exit 6 if any verifier is behind. | rehearsed, both ways: refused at exit 6, then accepted |
| 6 | operator, at the provider, then **[sudo]** | Move the prepared key's value to `APG_AUTH_JWT_SIGNING_KEY`, **clear** `APG_AUTH_JWT_PREPARED_KEY`, redeploy, and recreate. Until this is done the document says the new key signs and the service still uses the old one — **the one state the command cannot detect**, and it says so in its own follow-up text. | not rehearsed — a provider edit |
| 7 | **[sudo]** | Wait for the deadline, then `sudo bin/rotate-signing-key.sh --outputs … retire`, then redeploy and recreate. | rehearsed, both ways: refused before the deadline, accepted after |

### The wait, measured

`retire_after` is `promote`'s clock plus **930 seconds** — `MAX_TOKEN_TTL_SECONDS`
900 plus `CLOCK_SKEW_SECONDS` 30, where the 30 is D241's bisected measurement of
the locked PostgREST (30 s past `exp` served, 31 refused). Rig 28d waited it out
rather than editing the document, because the deadline is the subject of the
refusal and moving it would rehearse a document edit instead of a rotation.

**So the window is ~16 minutes wide at its narrowest**, and alpha and beta are
two of them. Do not plan a sweep between `promote` and `retire`.

### What the sweep can and cannot collect

**Performing this rotation moves no claim to `passed` on its own** (D1469), and
that is not a defect — it is what the registry says. A claim is `not_run` unless
**every** node id the registry lists for it ran and passed.

| Claim | Node ids | What the signing-key rotation moves |
|---|---|---|
| `bootstrap_identity` (SEC-BOOT-001) | 3 | **one**: `test_a_rotated_signing_key_is_the_only_one_the_plane_accepts`. The other two need `APG_ROTATED_AUTHENTICATOR_FROM_FILE` — the **authenticator password**, a different rotation. |
| `api_authorization` (SEC-ANON/PRIV/ROLE/DOCS-001) | 5 | **none.** Four need only a live host; the fifth needs `APG_ROTATED_DOCS_FROM_FILE` — the **documentation Basic Auth password**. |
| `credential_rotation_planes` (SEC-DBX-004) | 1 | **none.** It needs `APG_ROTATED_FROM_FILE` — the **application credential**, on both projects. |

**Four rotations, not one.** If Session 29 wants those three claims green it
performs all four in the same window and passes all four `--rotated-*-from-file`
flags to the gate. Each of the other three is a provider replacement plus a
redeploy (`bin/rotate-secret.sh` is a **planner**: it reads
`secrets.required.yaml` and changes nothing).

**And the signing-key proof runs after step 7, not after step 5** (D1470). It
asserts the retired `kid` is **absent** from the document's
`verification_kids`, which is exactly what `retire` does and what `promote`
deliberately does not: between them both keys are published on purpose.

### If alpha's `acknowledge` comes back dirty

It is not an error and nothing is broken: it is the refusal working. The
verifier named is still holding the previous key set.

1. **Do not promote.** `promote` refuses anyway, at exit 6, and the refusal
   names the services.
2. Recreate that project's runtime — `down`, then redeploy — and take
   `acknowledge` again. A restart is not enough and, after the key set file has
   been replaced, is measured to leave the container unable to start at all.
3. If it is still dirty, read what the container actually holds:
   `sudo docker ps --filter label=apg.project.key=<key>` and compare
   `jwks.json`'s digest inside it against `jwt.public_jwks_sha256` in the
   document. A mismatch that survives a recreate means the deploy did not
   republish the set — look at step 2's `render-jwks` line, not at the
   rotation.
4. **`abandon` is available until `promote` and not after.** Before promotion
   nothing signs with the incoming key, so withdrawing it costs nothing: clear
   `APG_AUTH_JWT_PREPARED_KEY` at the provider and redeploy. After promotion
   there is no way back and the recovery is to complete forward.
5. **If it exits 5 naming an init pid**, the daemon is not giving this host a
   usable handle on the container's mount namespace. That is step 0.4's
   pre-flight failing late. Nothing is wrong with the rotation and nothing has
   been promoted; the reading simply cannot be taken here, and the window
   should be closed with `abandon` rather than carried on blind.

### Two lines that look like faults and are not

**At the end**, after a successful `retire`, `status` prints `phase steady` and
then `promotion BLOCKED on ['mcp', 'postgrest', 'storage']` (D1475). Nothing is
blocked: `retire` resets the acknowledgements to an empty object, which
`describe` reports as *asked and unanswered* rather than as *nothing has been
asked*. Expected, recorded, and not repaired in this session — the repair moves
a passing contract test.

**At step 2**, `render-jwks` may print *"whether the key set CHANGED cannot be
told from here"* instead of *"the key set CHANGED"*. That is the normal case for
a deploy that replaced the whole rendered directory, and it is neither evidence
of a rotation nor evidence against one. What answers it is step 4.

### Timings nobody had measured before this rehearsal

Every step of the cutover completed in **under a second** in rig 28d —
`render-jwks`, `acknowledge` across three containers, `status`, `promote`,
`retire` — and the recreate of three containers took **3 to 5 seconds**. The one
thing that takes time is the deadline, at **930 s**.

These are rig timings on a workstation, not host timings, and the host's deploys
are what dominate the window in practice. What they establish is the **shape**:
nothing in the rotation itself is slow, so a step that hangs on the host is a
step to look at rather than to wait out.
