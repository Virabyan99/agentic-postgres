# Session 27 — The repair session: what a stranger's upgrade found, and the tag that carries the answer

**Status:** planned 2026-09-16, after Session 26 shipped `docs/upgrade-guide.md`
and `docs/operator-guide.md` at `c5ad14d` and an outside agent used them to
upgrade a real application from `1.0.0` to `1.6.0`.
**Brief:** `stage-3-findings.md`, that agent's account. Thirty-three entries
kept live while it worked. It finished — the deployment runs 1.6.0, both
deploys converged first pass, doctor 10 ok, `upgrade verify` exit 0 — and the
entries divide into documentation this session repairs and one product gap it
deliberately does not take.
**Shape:** seven runs, **no host trip**. Runs 1–6 offline and green in CI;
Run 7 is the close and the tag.
**Product version at close:** `VERSION` **1.6.1**, `CURRENT_SESSION` stays
**25**. This session repairs a release rather than building one, and the
release it produces is `1.6.1`.
**Next free:** D1406, ADR 0210.

---

## 0. Where the session starts

Session 19 is the precedent and it is exact. An outsider used `1.0.0`, wrote
`FINDINGS.md`, and the repair session that followed ran seven offline runs,
moved `VERSION` alone, kept `CURRENT_SESSION` where it was, and cut `1.0.1`.
Its first divergence row was **D1033**: *"A user adopting a product at 1.0.0
checks out the version tag … all four documented-path repairs land after it.
Cut 1.0.1 from a repaired main. **Not a documentation fix.**"*

**D1033 has recurred, and this session exists because of it.** Measured
2026-09-16: `git ls-tree -r --name-only 1.6.0 -- docs/` lists the ten
per-session operator guides and neither new page. Both land in `c5ad14d`, the
commit after the tag. The findings file's own sentence is the one to keep:
*an operator who does what the version number tells them gets a product whose
upgrade procedure is not in it.*

**The split, and the findings file drew it.** Its closing line: *"The single
change that would have made this upgrade ordinary: a way to freeze a project
set that records the release it was actually frozen against, plus a
project-level answer for a grant to the runtime identity. Everything else on
this list is documentation."*

This session takes *everything else*. The on-ramp for a fork made before ADR
0198 — F-008, F-012, F-013 and F-022 in the findings file — is **not taken
here**, and §9 makes that a stop condition rather than an intention. It is new
capability, it needs an ADR, it needs a decision the project-set lint's own
docstring explicitly defers to a later session, and it cannot be proved
without a real fork on a real cluster. Holding it here would turn a one-day
repair into a host trip and leave the tag uncut for another week.

**The ordering rule this session follows: code before prose.** Four of the
pages' repairs describe product behaviour this session also changes. A page
written before the repair describes the old behaviour and has to be written
twice. So Runs 2 and 3 repair the product, Run 4 writes the pages against the
repaired tree, and Run 5 makes the pages checkable.

**What the findings file got right that this plan does not re-derive, and
what it did not.** Every premise this session acts on was re-measured against
the tree on 2026-09-16 before this plan was written; §1 records where the
measurement agreed and the one place it did not (D1389). Nothing below is
carried from the findings file's arithmetic.

---

## 1. The divergence table

D1388–D1405. Rows marked **recorded** are not repaired here, with the reason.
D1402–D1404 were opened by Run 1's own measurements and D1405 by Run 2's;
none of the four is in the brief.

| D | Said | Measured or read | This session | Why it matters | ADR |
|---|---|---|---|---|---|
| **D1388** | ADR 0208 and Session 26's close treat `docs/upgrade-guide.md` and `docs/operator-guide.md` as shipped; `CLAUDE.md` §2 records them as what Session 26 shipped. | **Neither page is in tag `1.6.0`.** `git ls-tree -r --name-only 1.6.0 -- docs/` returns the ten `session-NN-operator-guide.md` files and nothing else; both pages first exist at `c5ad14d`, one commit past the tag. **This is D1033's second occurrence**, and D1033's repair was a patch release cut from a repaired `main`. Session 26 wrote the pages and cut nothing, so the release that needed them shipped without them. | **`1.6.1`, cut from a repaired `main` at Run 7** — not a tag on today's tree, because today's tree carries eighteen documentation defects a cold reader found in these two pages. ADR **0209** decides what holds a release to its own documentation so that a third occurrence fails a test rather than a reader. | The finding that makes every other finding unreachable: a reader who cannot find the page cannot report what is wrong with it. D1033 was written, repaired, and repeated seven sessions later by the person who had read it. | 0209 |
| **D1389** | `stage-3-findings.md` F-014: *"Four of §1's six checks refuse a project manifest below schema 5."* | **Four COMMANDS in the tree refuse, not four of §1's six.** `grep -rn "declares no migrations.set" src/ bin/` finds `bin/migrate.py:349`, `bin/api-contract.py:271`, `bin/agent.py:112` and `bin/dev.py:593` (seeds), plus `capability_manifest.py:283` for a different case. Of §1's six checks the findings file's own transcript shows `mcp-contract check --project` **passing** on a schema-4 manifest and `generate --check` refusing for a stale snapshot rather than for the missing set. So the count is about the tree and the page needs the measured subset, not the number. | **Run 1 measures which of §1's six refuse a schema-4 manifest**, by running all six against `project.example.yaml` reduced to schema 4 in a throwaway copy; Run 4 writes §1 from that reading and gives the `--project`-less form beside each one that refuses. | §4's own rule: a brief that describes what already exists prices a free property as a session, and a brief whose arithmetic is about a different set sends the repair at the wrong thing. The finding is real; its count is not the page's count. | — |
| **D1390** | `client_ir.FORMAT_TYPES`' neighbouring comment (D1216): *"a `vector` COLUMN is served as `extensions.vector(768)` while the same type as an RPC ARGUMENT is served as bare `extensions.vector` … Measured in the example project's snapshot, where the two spellings of one type appear in one document."* | **The lesson was learned for `vector` and generalised to nothing.** The table has 21 entries, `"integer": "number"` among them, and **no `int32` and no array type of any kind**. PostgREST serves an integer *column* as `integer` and an integer *RPC argument* as OpenAPI's `int32`. So the first adopter who writes a function taking a plain `integer` loses `apg generate` **and** `apg studio`, which builds the same IR — refused before the login prompt, with a message telling them to edit `src/agentic_postgres/client_ir.py`. Nothing about that is specific to the fork that found it: the release has never met it because `projects/example/`'s one RPC takes `uuid` and `vector`, and both spellings of `vector` are in the table. **And the refusal's wording is wrong in the argument case**: `client_ir.py:335-340` interpolates `{where}` (which reads `argument search_snippets.p_limit`) and then says *"a column whose type nobody decided is not a column a client should silently accept"*. | **Run 1 measures both spellings of every type in the table** against a real PostgREST (rig 27a, D1211's shape: PostgREST beside a dev cluster, the product's own environment values, one table and one function per type). **Run 2 adds every missing spelling the rig finds**, rewords the refusal so it names what `{where}` actually is, and adds the guard that the table covers both spellings of every format the release's own two snapshots publish. | §7 question 5, in the release written to harden the DX layer: a decision was implemented where somebody was looking, and the site nobody was looking at kept the old behaviour and read as deliberate. Two of the three developer surfaces are unreachable to an ordinary adopter, and the release cannot see it because its example domain is narrower than its own README tells adopters to write. | — |
| **D1391** | `docs/upgrade-guide.md` §2 step 5: *"as op, `stat -c %U .generated/*`, and if any is not `op`, `sudo chown -R op:op .generated` first"*, and *"A render into a root-owned directory dies on a permission error rather than a sentence (D1151; `render_project` names the owner and the remedy since 1.3.0)."* | **Two defects, and they compound.** (1) `rendering.py:132-134`: `STAGING_ROOT = GENERATED_ROOT / ".staging"` and `LOCK_ROOT = GENERATED_ROOT / ".locks"` — **a shell glob does not match a dotfile**, so the check the page prescribes cannot see either, and the findings file reproduced exactly that: the check passed, the render then died on `.generated/.staging`. (2) The named-owner refusal lives in `publish()` at `rendering.py:2214`; the failing `mkdir` is `staging.mkdir(mode=DIRECTORY_MODE)` at **`rendering.py:2424`**, a different site with no guard, which raised a bare `PermissionError` traceback and **exit 1 — not one of the ten codes the README publishes**. | **Run 2** gives the staging and lock `mkdir`s the treatment `publish` has: the owner, the remedy, and the convention's exit code. **Run 4** rewrites the page's check to one that can see a dotfile (`stat -c '%U %n' .generated .generated/.staging .generated/.locks .generated/*`). | The page told the reader this class of failure would arrive "as a sentence", had them run a check that cannot fire, and then handed them a traceback — which is worse than saying nothing, because it spends the reader's trust before the failure arrives. | 0195 |
| **D1392** | `docs/upgrade-guide.md`'s structure: §2 *"Before anything moves on the host"* precedes §3 step 1, which transports and checks out the new release. | **Every command in §2 runs from the release already installed, and the whole section is written in the present tense of the release in the checkout that wrote it.** Measured on the findings file's run: §2 step 2's *"`export` … hands the kit to the operator user"* is `_hand_to_operator()`, added in **1.0.1** (`git show 1.0.0:bin/dr-kit.py \| grep -c _hand_to_operator` → 0; at `1.0.1` → 2), so at 1.0.0 the kit stayed `root:root 0700` and the operator could neither verify it nor copy it off. Its other claim, *"`verify` takes no `--project` (D1316)"*, is a property of 1.6.0. The release table's *what an upgrade meets* column is about what the **deploy** meets and says nothing about which release executes the preparation. | **Run 4 restructures §2**: a standing sentence at its head saying every command in it runs from the installed release and not from this one, and a per-step note wherever the step's behaviour was measured on a later release than the reader may be running. §2 step 2 gains the 1.0.0 hand-over by hand. | The page is addressed to *"an operator running any earlier release"* and then describes every preparatory command as the newest release performs it. That is the premise-wrong-in-the-reassuring-direction class aimed at the one section a reader cannot check by reading the checkout in front of them. | — |
| **D1393** | `docs/upgrade-guide.md` §2 step 1 gives `sudo bin/upgrade.sh check --project <key>` as the first reading, and `bin/upgrade.sh --help`: *"check — Can a comparison be made at all?"* | **`check` never reads a candidate and its `verdict` is about readability alone.** `bin/upgrade.py:194-215`: the payload is `UNDETERMINED` when the installed document could not be read and `OK` otherwise, with `installed_version`, `release_version` and nothing compared. Run from the host's own checkout before §3 step 1, both versions are the *installed* one, and the findings file recorded the consequence: `verdict OK` on a 1.0.0 host about to take 1.6.0. The word is accurate about the question `check` asks and reads as a verdict on the upgrade. | **Run 2** makes the human-readable line say which question was answered (*"a comparison can be made"* / *"nothing installed, so nobody looked"*) rather than printing a bare `verdict`. **The JSON key does not move** — `test_session13_upgrade_plan` and the release proof read it, and renaming a published key to improve a sentence is a contract change for a cosmetic gain. **Run 4** says in §2 step 1 that this reading is about the installed release and that the pricing is §3 step 4's. | ADR 0195's family in a reader an operator is told to run **before** a mutation: the answer is right, the word invites the other question, and the other question is the one the reader came with. | 0195 |
| **D1394** | `docs/upgrade-guide.md` §3 step 4: *"`plan` prints every leaf that differs"*, and the operator is told to read it before the deploy. | **A key the schema gained and a value that became null print identically.** `upgrade_plan.py:106` defines `ABSENT = "<absent>"` and `bin/upgrade.py:126` prints `f"      {item.installed!r} -> {item.candidate!r}"`, so an absent left-hand side renders as the quoted string `'<absent>'` and a JSON null right-hand side as Python's bare `None`. On the findings file's hop two of seven leaves read `'<absent>' -> None`, which is *the v18 schema carries this key and this project leaves it empty* and is indistinguishable from *a value went away*. The classification is right (`implementation`), so nothing is mis-priced; the reading is what is ambiguous. | **Run 2**: the renderer distinguishes a key the document does not carry from a value that is null, in the human-readable form. `!r` on a value out of a JSON document is Python's repr in an operator-facing line, and the two other leaves on the same hop printed JSON values. | ADR 0195 again, on the one output the guide tells an operator to read before an irreversible step. A reader who cannot tell a schema addition from a removal reads the safest change class as the most alarming. | 0195 |
| **D1395** | `bin/dr-kit.sh --help` prints usage for both verbs; the convention throughout this repository is that a verb's `--help` is a read and needs nothing. | **`bin/dr-kit.sh export --help` exits 3 without printing help.** `bin/dr-kit.sh:74-82`: the `case "$1"` arm for `--help` matches only when help is the *first* word; `export` matches first, and the root check inside that arm dies with *"export needs root: the bootstrap state and the deployed document are root-owned"* before the Python side is reached. Measured 2026-09-16 across all 65 verbs in the `--help` capture: **this is the only verb that refuses `--help` for want of privilege.** (Already recorded as D1387 and left for a code session; this is that session.) | **Run 2**: `--help` or `-h` anywhere in `"$@"` prints usage and returns 0 before any privilege check, with a guard over every command in `SHELL_COMMANDS` rather than over this one — D1199's shape, where one command's defect was guarded as a class. | A reader told to read a verb's help is refused for a reason that has nothing to do with reading, on the command whose output is a disaster-recovery artefact. | — |
| **D1396** | `docs/upgrade-guide.md` §3 step 1 ends with `~/.local/bin/uv pip sync requirements-dev.txt` and *"five earlier trips paid for skipping the sync (D384, D297)"*; `docs/host-baseline.md:88-93` lists `~/.local/bin` and `.venv/bin` as things the baseline has. | **Nothing installs either, and the baseline page says so about itself.** `grep -ci "uv\|astral\|pip install" bin/provision-host.sh` → **0**. `host-baseline.md:93` reads *"It has always worked by hand because an operator's interactive shell already has both"* — a description of the maintainer's host presented as the baseline. The findings file's host had neither and ran every `bin/*.sh` under the distribution's Python 3.14 against a `.python-version` of `3.12.13`. **And the step was a no-op for that hop**, which I confirmed independently: `git diff --stat 1.0.0 1.6.0 -- requirements-dev.txt requirements-dev.in .python-version` is empty. | **Run 4, documentation only**: §3 step 1 says the sync is needed only when the hop moves a dependency, gives the one-line way to tell (`git diff --stat <installed source_commit>..HEAD -- requirements-dev.txt requirements-dev.in .python-version`), and says what to do on a host that has no `uv`. `host-baseline.md` gains one sentence saying the two paths are the maintainer's shell and not something `provision-host.sh` creates. **Making the baseline install them is NOT taken here** (§9): it is a change to what `--apply` does to a machine, and it belongs with the interpreter question below. | A mandatory-sounding step nobody can satisfy on a host the product itself provisioned. The interpreter half is worse and is recorded rather than repaired: the release pins 3.12, enforces it on a workstation through `bin/doctor.sh`, and the machine that runs every deploy is unchecked. | — |
| **D1397** | `docs/upgrade-guide.md` §3 step 6 and README's deploy sequence both end `--through-session 25`; `materialize-secrets.sh` takes `--session 25`. | **No page says where the number comes from.** It is `CURRENT_SESSION` in `src/agentic_postgres/__init__.py`, it is not in `VERSION`, no `--help` in the 4,478-line capture prints it, and the upgrade guide's release table carries it in a *Session* column whose stated purpose is something else. An operator upgrading to a release the table does not list has no documented source at all. `deploy.sh` accepts any number **below** `CURRENT_SESSION` silently (D59), so a wrong one deploys the wrong thing and exits 0. | **Run 4**: both pages say where to read it, in the step that needs it. **Run 2 decides whether a command prints it**, measured rather than assumed: if `deploy.sh --help` can name the number this release implements without a Python import (ADR 0093 bounds what a `bin/` command may import), it does; if not, the row records why and the pages carry the source path. | The one argument on the page whose wrong value is accepted, silent and consequential, is the one argument with no documented origin. D678's family, one level up: not a stale number, an unsourced one. | — |
| **D1398** | `docs/upgrade-guide.md` §2 step 2 names the kit `/home/op/kit-$(date -u +%Y-%m-%d)` and approves of the collision guard — *"the day is in the name so two exports on one day collide on purpose"*; §3 step 8 says *"re-export the kit … the one you exported before the upgrade describes a deployment that no longer exists."* | **An upgrade performed in one sitting exports twice on one day, and the naming convention the page prescribes refuses the second.** Neither step mentions the other's name. The guard is right — `export` refuses a directory that exists, deliberately — and the page guarantees the case it refuses. | **Run 4**: §2 step 2's name carries a suffix that distinguishes the two exports (`-pre` / `-post`), and each step names the other. **The guard is not touched.** | A page whose two steps cannot both be followed as written, found on the first sitting that followed both. | — |
| **D1399** | `docs/upgrade-guide.md` §2 step 5: *"a third manifest inside it is untracked and makes every deploy refuse (D971), so it lives at `/home/op/<name>.yaml`."* | **`.gitignore:48-49` carries `/project.yaml` and `/project.*.yaml`**, added by `1.0.1`'s D1034 repair with a comment saying precisely why (*"the first act of adopting this product was to fork it and edit this file"*). A third manifest inside the checkout is ignored, and the findings file's host has `project.snippets.yaml` in the checkout with `git status --porcelain` empty. The advice is left over from before the release fixed the thing it works around, and following it now moves a file that does not need moving. | **Run 4**: the step says the manifest may live in the checkout since 1.0.1 and names the glob, keeping D971's reason for a manifest that is genuinely untracked. | A workaround that outlived its defect by six sessions, in a page written six sessions later — the ledger's own §2 shape, finished work described as unfinished. | — |
| **D1400** | README §*Checks*: *"Each session has its own gate, `bin/session-01-check.sh` through `bin/session-10-check.sh`."* README §*Operating a deployment* is a command menu. | **Both are stale and one is a hole.** `ls bin/session-*-check.sh` gives **01–18 and 20–25** — the sentence understates the set by fifteen, and **there is no `session-19-check.sh`**, which no page accounts for (Session 19 was a repair session and registered no claims; nothing says so where a reader counting gates would look). And `bin/upgrade.sh` — the one command in the product whose entire job is this brief — **is absent from the operating menu**, mentioned in the README only inside a parenthetical about which verbs take `--project KEY`. | **Run 4** repairs both sentences and says why 19 has no gate. **Run 5** adds the guard: `test_documentation_index` already asserts every command the README *names* exists, and gains the other direction for a named set — the operator-facing commands a reader must be able to find. | The README's own D623 is *"Status: Session 3 of 12 complete for eight sessions"*, and the repair was a guard on the status line. The set of gates and the set of operator commands both went stale for the same reason: nothing reads them. | — |
| **D1401** | `REL-STAGE-001`, and `docs/operator-guide.md` §10: a host sweep asserts each project's deployed document carries `template_version` equal to the tree's. | **A patch bump without a deploy makes `stage_release`'s live half fail at the next host sweep**, because the tree will read `1.6.1` and both projects are deployed at `1.6.0`. Measured against the requirement's text rather than assumed. This is not new in kind — Sessions 22 and 23 both closed with the host behind the tree — but it is new for this requirement, which Session 25 registered. | **Recorded, and it is an obligation rather than a defect.** The next host trip deploys the tree before it sweeps, which every trip already does. Named in §10 so the trip that inherits it is not surprised by a red `stage_release` it did not cause. | A requirement that couples a tag to a deployment, met by a session that tags without deploying. Stating it costs nothing; discovering it fifteen minutes into a sweep costs a second one. | — |

| **D1402** | This plan's D1395, from the 2026-09-16 `--help` capture: *"this is the only verb that refuses `--help` for want of privilege."* | **True as stated, and three more verbs refuse `--help` for a different reason.** `bin/upgrade.sh check --help`, `plan --help` and `verify --help` each exit **2** with *the following arguments are required: --project*. Measured cause: `bin/upgrade.py:157` constructs its parser with **`add_help=False`**, so `--help` is not an argument it knows; the wrapper's `case "$1"` matches `--help` only in first position, `check` matches first and is dispatched, and argparse's required-argument error fires before its unrecognised-argument error. So the class is wider than privilege: **a wrapper that dispatches a verb before considering `--help`**, over a Python side that either checks privilege (`dr-kit`) or requires an argument (`upgrade`). Four verbs across two commands. | **Run 2** takes the wider rule: `--help` or `-h` anywhere in `"$@"` prints the wrapper's usage and returns 0 before the verb is dispatched. The guard derives the verbs to probe from each command's own usage block, line-anchored, which is the derivation D1316's repair already uses for `--project` — so the next command that grows a verb is covered without anybody editing a list. | The plan priced one instance and the measurement found a class. Guarding the instance would have left three verbs of the command this session's whole brief is about still refusing to explain themselves. | — |
| **D1403** | The exit-code convention, and ADR 0195: a reader has three outcomes and reports the third rather than folding it. | **Two commands print a success line AFTER a refusal and exit non-zero.** Measured twice, on two different inputs: `bin/migrate.sh --project <schema-4 manifest> verify-lock` prints *"declares no migrations.set, so it has no lock of its own"*, then prints **"migrate: the released lock agrees with the manifest and templates"**, then exits **5**; `bin/mcp-contract.sh check --project <invalid manifest>` prints *"the project is refused: …"*, then **"the manifest compiles to the approved contract (6 tools)"**, then exits **5**. In both the last line a reader sees reads as success on a failing exit. The findings file noticed the first as *"a small ordering wart"* inside F-014; it is reproducible, it is in two commands, and the second was found by this session's own rig rather than by the brief. | **Run 2**: a refusal is the last thing printed. The release's lock genuinely does agree, and that sentence is still worth printing — before the refusal, not after it. | ADR 0195's family read from the other end: not an unknown reported as an answer, but the right answer printed last. An operator who reads the final line and the exit code disagrees with their own terminal. | 0195 |
| **D1404** | `docs/upgrade-guide.md` §1's sixth check: *"`generate --check` exits 5 after **every** bump, because the client's `templateVersion` is derived from the release (D1238). Regenerate and commit it."* | **For a project that declares no migration set it exits 5 for a different reason, and regenerating is the wrong remedy.** Measured against a valid schema-4 manifest: *"clients/typescript/README.md is missing; the client has not been generated from this contract."* `bin/generate.sh --help` says the default output is `projects/<slug>/clients/typescript` for a project with a set and `clients/typescript` under the checkout root for one without — and **the release tracks no root-level `clients/` directory at all**. So the check refuses for every schema-4 project, always, and the page's remedy would have the reader create a top-level directory the release does not carry. The findings file reached the same wall from the other side and left it, correctly. | **Run 4** says which of the two refusals a reader is looking at and that a project with no set of its own has no client to regenerate. **Whether the release should track a root-level client, or `generate` should refuse a setless project by name, is §10's** — it is a product decision about what `apg generate` is for, not a sentence. | The page gives one cause and one remedy for a refusal that has two causes and, in the more common case, no remedy the page's own advice reaches. | — |

| **D1405** | This plan's D1402, from Run 1: *"Four verbs across two commands."* | **Seven verbs across three commands**, measured in Run 2 by deriving every verb from every command's own usage and probing each one, which is the guard D1402 asked for and is also how the class was finally counted. `bin/database-ports.sh allocate --help`, `verify --help` and `release --help` each exit **3** with *"must run as root: the allocation registry lives under /etc and the lock under /run/lock."* Same shape as `dr-kit export`: the wrapper dispatches the verb, the verb's arm checks privilege, and `--help` is never considered. Run 1 could not have found these — its reading was the 2026-09-16 `--help` capture, which holds each command's top-level help and the verbs somebody thought to capture; the derivation reads the usage text the command itself prints. | **Run 2**, in the same edit as D1395 and D1402: the loop over `"$@"` goes into all three commands. The guard is a class over `SHELL_COMMANDS`, with the verbs derived per command, so this is the last time anybody counts. | Three rounds of counting one class, each larger than the last, and each reading was honest about the evidence it had. The lesson is not that Run 1 was careless: it is that a capture of what somebody thought to run is not a measurement of what the command offers, and only the derivation closed the gap. | — |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**Nothing, and the reason is the shape of the session.** No requirement, no
claim, no registry entry, and no `bin/session-27-check.sh`.

`CURRENT_SESSION` is what the evidence model is keyed to and what
`deploy.sh --through-session` may not exceed; it moves when a session lands a
plane. This session lands no plane. **Session 19 is the precedent and it is
recorded in the constant's own comment**: *"Session 19 moved it to `1.0.1`,
and `CURRENT_SESSION` stays 18. … 19 is skipped, and the skip is the record
(D1063)."* Session 27 skips the same way: 26 and 27 have no session number in
the evidence model, and the gate that measures this tree is
`bin/session-25-check.sh`.

**Tests are added — several — and none of them is a claim.** They are guards
over classes this session repairs (D1390's format coverage, D1395's help
policy, D1400's two directions, ADR 0209's release-to-documentation link).
Every one lands in an existing module or in a module registered the way
`test_acceptance_registry` requires, and every run that adds one runs that
module (D1119).

---

## 4. Irreversible operations

**One: the tag.** `1.6.1`, annotated, on the `main` commit CI measured. A tag
can be deleted and cannot be un-published, and D1311's rule is the one that
binds: *a tag is the promise the compatibility sentence beside it made at the
moment it was cut.* So the tag is Run 7's last act, after CI is green on the
bump commit and after the pages are repaired — not a tag on today's tree,
which carries eighteen documentation defects a cold reader found in them.

Everything else this session does is reversible by `git`. No deploy, no
migration, no provider, no host.

**The one thing that is irreversible and is NOT taken**: re-stamping an
applied migration, which is what `freeze-lock`'s refusal currently advises a
pre-ADR-0198 fork to do. §9 forbids it here and the on-ramp session is where
that advice is repaired.

---

## 5. Build order, run by run

Each run ends `**Done.**` with what it measured. **A targeted list is derived
from the diff, not copied from this plan**, and CI is the full check.

### Run 1 — the measurements, and ADR 0209

No repairs. Every premise Runs 2–6 act on is measured first, in a throwaway
rig with a control, and a measurement that contradicts this plan changes the
run rather than the measurement (D267).

1. **Rig 27a — both spellings of every format** (D1390). PostgREST beside a
   dev cluster, in ADR 0066's shape and D1211's precedent: read
   `compose.yaml`'s `services.postgrest.environment` as YAML and substitute
   only what the rig must. One table with a column of every type in
   `FORMAT_TYPES`, and one `SECURITY DEFINER` function taking an argument of
   each of the same types, plus `text[]`, `double precision[]`, `integer[]`
   and `uuid[]`. Capture the served document and record, per type, the
   **column** spelling and the **argument** spelling. **The control**: the
   pair already known (`extensions.vector(768)` / `extensions.vector`) must
   come back as D1216 recorded it, or the rig is measuring something else.
   Output: the exact set of missing keys, and whether any existing key is
   wrong.
2. **Which of §1's six checks refuse a schema-4 manifest** (D1389). Copy
   `project.example.yaml` to an ignored name, reduce it to `schema_version: 4`
   with no `migrations.set` and no `mcp.capabilities`, run all six, record
   each one's exit code and first line verbatim. This is the reading §1 is
   written from.
3. **`deploy.sh --help` and `CURRENT_SESSION`** (D1397). Whether a `bin/`
   command can print the number this release implements within ADR 0093's
   import bound. Read `bin/deploy.sh`'s existing imports; if the number is
   already reachable there, Run 2 prints it.
4. **The `--help` policy across `SHELL_COMMANDS`** (D1395). Run `<verb> --help`
   and `<verb> <subcommand> --help` for every command as an unprivileged user
   and record every non-zero exit. The 2026-09-16 capture says `dr-kit export`
   is the only one; this re-measures it as the guard's premise rather than
   trusting a capture taken for another purpose.
5. **What reads `upgrade`'s JSON keys** (D1393). `grep` every proof and
   `bin/` reader for `verdict`, `installed_version`, `release_version`, so
   Run 2's change to the human-readable line is known not to move a key
   something asserts.
6. **ADR 0209**, written from 1–5 and from D1388: *the release's own
   documentation is held to the release by a test, not by a habit.* It
   decides what is enforceable (the pages name the version the tree carries;
   the upgrade guide's release table has a row for it) and what is not (that
   a tag will be cut), and it names the alternatives: a release checklist, a
   CI step that refuses a tag, or nothing. Indexed in
   `docs/decisions/README.md`.

**Targeted at the close:** nothing — this run changes no code. The rigs'
outputs are pasted into the `Done.` paragraph, because a measurement that
exists only in a scrollback is one the next session will take on trust.

**Done.** 2026-09-16. Five readings, three new rows (**D1402–D1404; next free
D1405**), one ADR, and **two apparatus defects of my own, caught before either
became a finding**.

**Rig 27a (D1390), and it is larger than the brief.** The rig reuses
`test_generated_client_runtime`'s `served` fixture whole — a dev cluster from
the render and the release, the authenticator activated through stdin, PostgREST
configured from `compose.yaml`'s own environment — and adds one superuser DDL: a
table with a column of every type in `FORMAT_TYPES` plus eight array spellings,
and a function taking an argument of each. **The control holds**: a
`vector` column comes back `extensions.vector(768)` and the same type as an
argument comes back bare `extensions.vector`, exactly as D1216 recorded, so the
rig is measuring what the product serves.

What it measured, column and argument together:

| Declared | Served as a column | Served as an argument | In the table? |
|---|---|---|---|
| `integer` | **`int32`** | **`int32`** | **no** |
| `smallint` | **`int32`** | **`int32`** | **no** |
| `bigint` | **`int64`** | **`int64`** | **no** |
| `text[]`, `integer[]`, `uuid[]`, `double precision[]`, `boolean[]`, `jsonb[]`, `numeric[]` | the same spelling | the same spelling | **no, none of them** |
| `tsvector` | `tsvector` | `tsvector` | **no, and it must stay no** — it is the control in `test_an_unknown_column_format_is_refused_and_never_typed_any` |
| the other seventeen | their SQL name | their SQL name | yes |

**`integer`, `smallint` and `bigint` are dead keys.** PostgREST never emits
those three spellings, for a column or for an argument, so the table's entries
for them can never match. The findings file found this from one direction — an
`integer` RPC argument — and the measurement says it is every integer anywhere.

**And the reason nobody met it is free to read.** The two committed snapshots
between them serve exactly **`text`, `timestamp with time zone`, `uuid`,
`extensions.vector` in both spellings**, and the enum `task_status`. So
**seventeen of the table's twenty-one entries have never matched a served
format in this repository's history** — §7 question 2, answered by counting:
they have not run at all, in any environment, since the day they were written.

**Step 2 (D1389), the count the page needs.** Against a valid schema-4 manifest,
of §1's six checks: `migrate verify-lock --project` refuses (exit 5) and
`api-contract --check --project` refuses (exit 2) for want of a set; **the other
four do not** — `mcp-contract check --project` exits 0 and compiles the
release's six tools, `--render-only` exits 0, `apg dev status` exits 4 about
state rather than the manifest, and `generate --check` exits 5 for D1404's
reason. **Two of six, not four.** The `--project`-less forms the two refusals
name both exit 0.

**Step 3 (D1397), and the repair is cheaper than the plan priced it.**
`deploy.sh` already carries `max_deployable_session()`, which imports
`CURRENT_SESSION` and prints it; the number is simply not in the usage text,
whose heredoc is quoted (`<<'USAGE'`) and interpolates nothing. Run 2 prints it
after the block.

**Step 4 (D1395), widened to D1402.** Every `bin/*.sh --help` and
`./deploy.sh --help` exits 0 as an unprivileged user. Four VERB-level helps do
not: `dr-kit export` (exit 3, privilege) and `upgrade check|plan|verify` (exit
2, a required argument over `add_help=False`).

**Step 5 (D1393), and the JSON is safe to leave alone.** Outside
`bin/upgrade.py` and `upgrade_plan.py`, exactly one proof reads the payload —
`test_upgrade_command.py:271`, `payload["verdict"] == "blocked"`, which is
`plan`'s JSON rather than `check`'s. Nothing anywhere reads `installed_version`
or `release_version`. So Run 2 moves the human-readable line and no key.

**The two apparatus defects, recorded because the apparatus being the defect is
this project's standing risk (D736, D742).** Reducing `project.example.yaml` to
schema 4 by deleting the `set:` line left the parent `migrations:` key with a
null value; `migrations` is `required: ["set"]`, so the manifest was invalid and
all six commands refused on **schema validation** — six identical refusals that
would have read as a finding about the product. The second attempt changed the
slug and domain and not the CORS origin lists that derive from the domain, and
was refused by semantic validation. **Both were caught by a load check placed
before the readings**, which is the only reason neither was written down. The
third attempt changes only the two keys under test, and protects
`.generated/fixture-alpha-dev` — a fixture the gate reads (D1284) — by
snapshot and digest: `32a621d1c11d720b…` before and after, byte-identical.

**ADR 0209** is accepted and indexed: a release is held to its own
documentation by a test, not by a habit. It decides what is enforceable (the
pages exist, name `template_version()`, carry a row for the release, and join
both scans) and what is not (that a tag exists), with five alternatives and the
reason each lost. The rig and every reading are in the scratchpad under
`s27-scripts/`; the throwaway module is deleted and the tree is clean.

### Run 2 — the product repairs the pages will describe

Five repairs, each with its own battery. `PYTHONDONTWRITEBYTECODE=1`, caches
cleared, anchors pre-flighted to match exactly once, every mutation paired
with a control it cannot reach, and `FAILED` asserted rather than `ERROR`
(D386).

1. **`client_ir.FORMAT_TYPES`** (D1390). Add every spelling rig 27a found
   missing — at minimum `int32`, `text[]` and `double precision[]`, and
   whatever else the rig names. **The refusal's wording** is rewritten so the
   sentence agrees with `{where}`: a column and an argument are both named
   correctly, and ADR 0204's reason for refusing `any` is kept. **The guard**:
   a test that every format appearing in the release's own
   `contracts/postgrest-openapi.canonical.json` and in
   `projects/example/contracts/postgrest-openapi.canonical.json` is a key in
   the table, and that both spellings of every type either appear or are
   explicitly recorded as unserved. **The control that keeps it honest**:
   `test_an_unknown_column_format_is_refused_and_never_typed_any` must still
   refuse `tsvector`, which none of the new entries names — the property that
   an undecided format is never silently `any` is what this repair must not
   weaken.
2. **`rendering.py`'s staging and lock `mkdir`s** (D1391). The site at
   `rendering.py:2424` and the two `exist_ok=True` roots above it gain what
   `publish()` has: the owner resolved upward when the path itself cannot
   answer, the `chown` named, and the convention's exit code rather than a
   traceback. Battery: the mutation that removes the guard must fail a proof
   that renders into a directory the invoking user does not own.
3. **`bin/upgrade.sh`'s usage** (D1381, recorded in Session 26 and repaired
   here). The eight `--also` classes named, with D743's sentence: a rendered
   document records no migration count and the checkout's lock describes the
   checkout, so `migration_added` is an operator's declaration. **The guard is
   scoped to this command** — a proof that every flag `bin/upgrade.py`'s
   parser declares appears in `bin/upgrade.sh`'s usage. Generalising it to all
   65 verbs is §10's, priced there, because a sweep over every parser is a
   measurement nobody has made and could produce a dozen rows on a repair
   session's clock.
4. **`bin/dr-kit.sh`'s `--help`** (D1395). Help anywhere in `"$@"` prints and
   returns 0 before any privilege check. Guarded as a class over
   `SHELL_COMMANDS`, from Run 1 step 4's reading.
5. **`bin/upgrade.py`'s two readers** (D1393, D1394). The human-readable
   `check` line says which question was answered; the leaf renderer
   distinguishes a key the document does not carry from a null value. **No
   JSON key moves**, confirmed against Run 1 step 5.

Plus, if Run 1 step 3 came back yes: `deploy.sh --help` names the session this
release implements (D1397).

**Targeted:** the modules the diff touches, plus `test_acceptance_registry`
(D1119 — this run adds test functions) and `test_cli_contract` (two `bin/`
commands' usage moves).

**Done.** 2026-09-16. Seven repairs, eleven mutations, **eleven kills, no
survivors, no errors and no dead controls** — after the battery's first pass
found three defects in the PROOFS and none in the product.

**The repairs.**

1. **`client_ir.FORMAT_TYPES` (D1390), and rig 27b measured the rest of it.**
   Run 1's rig answered for the twenty-one declared types and seven array
   spellings. Run 2 re-ran the same apparatus over the array form of *every*
   base type — one container, ~43 seconds, the D1216 control holding — because
   deriving fourteen entries from a rule measured on seven is exactly the
   "value that looked measured and was not" this project keeps producing. The
   table goes from 21 entries to **44**: `int32` and `int64`, and twenty-one
   array spellings. **An array carries the base type's SQL name and never
   `int32`** (`integer[]` is served `integer[]`), and PostgREST drops a
   `varchar` modifier in an array as it does for a column — but **keeps
   `vector`'s**, so `extensions.vector(768)[]` is served whole and
   `_FORMAT_MODIFIER` had to stop being anchored at the end of the string.
   The refusal takes its noun from `{where}` rather than saying "column" to
   somebody looking at an argument. The rig's whole measurement is committed as
   `RIG_27B_SERVED` beside the new guard, which asserts every served spelling
   resolves **and that a type's two spellings resolve to the SAME TypeScript
   type** — the property the old table broke. `tsvector` and `tsvector[]` are
   named as unserved on purpose, and a mutation that widens the table to reach
   `tsvector` is one of the eleven kills.

   **One correction to Run 1's account.** "`integer`, `smallint` and `bigint`
   are dead keys" is right about PostgREST and wrong about the table: the
   APPLICATION snapshot is typed through the same map, and `_openapi_type`
   reduces JSON Schema `integer` to `"integer"` and `number` to `"numeric"`.
   So two of the three are live from the other document and all three are
   kept, with the reason written where somebody tidying up will read it.

2. **`rendering.py`'s four `mkdir`s (D1391).** `make_directory` gives the
   generated root, `.staging`, `.locks` and the per-render staging directory
   what `publish` has had since 1.3.0 — the owner resolved upward, the `chown`
   named, and `RenderError` rather than a bare traceback and **exit 1, which is
   not one of the ten codes the README publishes**. The lock FILE's `os.open`
   is guarded too (D65's trip). The remedy names the whole generated root
   deliberately: `.staging` and `.locks` are dotfiles, and the check the
   upgrade guide prescribed (`stat -c %U .generated/*`) cannot see either —
   which is why the cold reader's check passed and the render then died inside
   one of them.

3. **`bin/upgrade.sh`'s usage names `--also` (D1381)**, with all eight classes
   and D743's reason. **The first draft of that block invented four of the
   eight class names from memory**, and what caught it was writing the guard
   before trusting the text: the proof reads `DECLARABLE` by AST and asserts
   every flag the parser declares and every class it accepts appears in the
   usage. Nothing shipped; it is recorded because the apparatus being the
   defect is this project's standing risk.

4. **`--help` anywhere in `"$@"` (D1395, D1402, D1405), and the class was
   bigger a third time.** The guard the plan asked for — derive each command's
   verbs from its own usage, probe each one — found **seven verbs in three
   commands**, not four in two: `bin/database-ports.sh allocate|verify|release`
   refuse `--help` for want of root exactly as `dr-kit export` does (**D1405**).
   All three wrappers now consider help before dispatching. The derivation had
   its own defect on first run and it is worth naming: `\s+` matches a NEWLINE,
   so a usage block whose lines each start with the command name derived the
   next line's first word as a verb of this one — it read `bin` out of
   `bin/rotate-secret.sh`. Fixed to spaces and tabs before anything was
   asserted.

5. **`bin/upgrade.py`'s two readers (D1393, D1394).** `check`'s human-readable
   form says which question was answered — *"a comparison CAN be made … no
   candidate was read"* or *"nothing is installed … so nobody looked. This is
   NOT 'no changes'"* — and **no JSON key moves**, as Run 1 step 5 established.
   The leaf renderer prints `(no such key)`, `null` and a JSON value as three
   different things. **`Difference.ABSENT` is a CLASS attribute, not a module
   one** — Run 1's row said `upgrade_plan.py:106` and the first version of the
   repair read `upgrade_plan.ABSENT`, which raised an `AttributeError` on the
   first real hop it was tried against. Caught by running the command rather
   than by reading the diff. And the model had always distinguished the two
   cases: `Difference`'s own docstring cites D600 for choosing a sentinel over
   `None`. Only the renderer put them back together.

6. **`deploy.sh --help` names the session (D1397)**, and Run 1 was right that
   this is cheap: `max_deployable_session()` already imports `CURRENT_SESSION`.
   It is derived from that function rather than typed, printed after the quoted
   heredoc, and **degrades to a sentence rather than an error when no
   interpreter can be found** — `--help` is a read that must need nothing.

7. **A refusal is not preceded by a success sentence (D1403).**
   `verify_project_lock` returns its sentence instead of printing it, so both
   halves print together after both agree; `mcp-contract check` holds its
   report until the `--project` half has passed. Both measured before and
   after on the inputs that reach the arm — and the mcp instance needs a
   manifest the SCHEMA refuses, not a schema-4 one, which the reading found.

**What the battery found, and all three were mine.**

* The `.generated` remedy assertion was a substring test, so a remedy naming
  `.generated/*` — the glob that cannot reach either dotfile, which is the
  whole of D1391 — **survived**. It now asserts the path is followed by the
  closing backtick.
* **The refusal-ordering proof could not fail.** It took the last line of
  `stdout + stderr`, and in that concatenation stderr is *always* last, so a
  refusal on stderr satisfied it whatever stdout said. The mutation survived.
  **And the property as this plan's D1403 states it — "a refusal is the last
  thing printed" — is not readable through a pipe at all**: what an operator
  sees depends on which stream is a tty and how Python buffers it. The
  checkable property is stronger and is the one that matters: **a command that
  is going to refuse writes no success sentence to stdout in the first place.**
  True on a terminal, in a pipe, and in a log. The test is renamed to say so.
* The control for the `--help` mutation was **reachable by it**: deleting
  `bin/upgrade.sh`'s loop takes its top-level `--help` with it, because the
  loop is that path now. Re-pointed at `dr-kit`'s verb help, in a file the
  mutation does not touch (D499).

**Targeted at the close, once:** `test_client_ir`, `test_client_typescript`,
`test_render_atomicity`, `test_cli_contract`, `test_upgrade_command`,
`test_upgrade_plan`, `test_capability_profile`, `test_mcp_catalog`,
`test_acceptance_registry`, `test_documentation_index` — **730 passed** after
the acceptance matrix was regenerated (the registry gained seven proofs and two
widened clauses). `bin/apg.sh generate --check` exits 0: the release's snapshot
serves only formats whose mapping did not move, so the committed client is
unchanged, which is itself the measurement of how narrow that snapshot is.
`ruff format` reformatted three files and `ruff check` passes. The rig module is
deleted; the fixture the readings could have damaged was snapshotted and is
byte-identical (`32a621d1c11d720b…`).

### Run 3 — the refuted rationale, in the code and in the two places that repeat it

Small, separate, and no battery, because nothing executable changes.

`src/agentic_postgres/migrations.py::_assert_follows_release_version` carries,
at lines 549–554 and still shipped at `1.6.1`'s parent:

> The direction is not symmetric and that is the whole rule. … a release
> migration newer than an applied project migration is fine … So the rule
> constrains only what a project may author, and never what the release may.

ADR 0206 §Context quotes that paragraph and answers **"That is false, and
Session 24's trip is where it was refuted"** (D1288). `bin/migrate.sh --help`
repeats the same reasoning in its own words.

**The explanation is replaced; the enforcement is not touched** (§9). What
goes in its place is what ADR 0206 says is true now: the two sets render to
separate directories and apply into separate tables, so a project version
below a release version can no longer produce the `up --strict` refusal the
rule was written to pre-empt, and `follows_release_version` survives as a
record of which release a set was reviewed against. The docstring cites ADR
0206 and D1288, and says in one line that **what the rule should do when a set
was frozen against an earlier release is undecided and is the on-ramp
session's** — which is the sentence the findings file needed and could not
find.

**Targeted:** `test_documentation_index` (a `bin/` usage moved),
`test_session12_documented_path`.

**Done.** 2026-09-16. Three texts replaced, no executable behaviour changed,
and one thing the plan did not price.

**The docstring** now says what ADR 0206 established: the rule was written for
a world with one directory, one `dbmate` invocation and one
`app_private.schema_migrations`, where a project version below an applied
release version was an `up --strict` refusal on a deployed cluster and a silent
apply on a fresh one (rig 20a, D1098); each set now has its own directory and
its own table and is ordered against its own applied set only. It quotes the
false paragraph rather than deleting it, and says why it was false — *authored
later* is not *sorts higher*, versions are authoring-date stamps, and a project
set stamped ahead of the release's clock **to clear this very rule** left the
release a window that Session 24's `0032` landed in. It ends with the sentence
the findings file needed and could not find: **what the rule should do when a
set was frozen against an earlier release is undecided, and it is the on-ramp
session's.**

**The REFUSAL MESSAGE was carrying the same refuted reasoning and the plan did
not name it.** It told an operator that dbmate applies one directory in
filename order and that they were about to produce *"the same set producing two
different schemas"* — a consequence that has not been possible since ADR 0206.
It is explanation rather than enforcement, so it is repaired here: it now says
that `follows_release_version` is a record, names the two ways forward
(re-stamp above the recorded version, or re-freeze the project's lock), and
says which of them is intended is undecided. **The enforcement is byte-for-byte
the same**: the same `re.fullmatch`, the same comparison, the same
`ProjectSetError`.

**`bin/migrate.sh --help`** carries the same correction in its own words.

**Measured, not assumed, in two directions.** The refusal still fires on a set
that does not sort after the recorded version, and a set that does sort after
is still accepted — the control, in the same reading. And `grep` for the moved
TEXT rather than the moved name (D1187) found every remaining copy of the false
paragraph to be a RECORD quoting it in order to refute it: ADR 0206 §Context,
the Session 24 plan's D1288 row, this plan, and the new docstring itself. No
fourth copy was still asserting it.

**Targeted, once:** `test_documentation_index`,
`test_session12_documented_path`, `test_project_migration_sets`,
`test_migration_ledger`, `test_rendered_migrations` — **86 passed**. `ruff
check` passes and `bin/migrate.sh --help` exits 0. No battery, because nothing
executable changed; the one reading above is what stands in for it.

### Run 4 — the two pages, against every documentation finding

Documentation only, written against the tree Runs 2 and 3 leave.

**`docs/upgrade-guide.md`:**

| Finding | Repair |
|---|---|
| D1392 | §2 gains a standing sentence: every command in it runs from the **installed** release, not this one. Each step whose behaviour was measured on a later release says which, and §2 step 2 carries the 1.0.0 kit hand-over by hand |
| D1389 | §1 gives the measured subset that refuses a schema-4 manifest, each with the `--project`-less form beside it, and points at the release table's own sentence that a schema-4 manifest still deploys |
| D1393 | §2 step 1 says what `check` compares and that the pricing is §3 step 4's |
| D1391 | §2 step 5's ownership check sees dotfiles |
| D1399 | §2 step 5 drops the stale `/home/op/<name>.yaml` advice and names the glob that replaced it |
| D1396 | §3 step 1's sync is conditional, with the one-line way to tell, and what to do on a host with no `uv` |
| D1397 | §3 step 6 says where `--through-session`'s number comes from |
| F-028 | §3 step 6 names `ssh -tt` as the way to satisfy the no-redirect rule from anywhere but a keyboard, and `script(1)` as the way to have a transcript without a redirect |
| D1398 | §2 step 2 and §3 step 8 name each other and use distinguishable names |
| F-031 | §3 step 9's return trip names **step 3** as well as step 1, and says which of the nine steps the second pass skips |
| D1394 | §3 step 4 says how to read a leaf where the schema gained a key |
| F-008 | A new §1.0: **what this page does not cover** — a fork made before ADR 0198, with the two refusals named, the ledger row that tracks it, and no pretence that §1 applies |

**`docs/operator-guide.md`:** §1's release facts re-read from the tree at
`1.6.1`; §10's gate arguments unchanged; §13 gains what the findings file
established has never been performed here and what it established *has* now
been performed elsewhere — an upgrade from 1.0.0 by a reader who did not build
this, which is the first end-to-end operator-path reading this project has.

**`README.md`** (D1400): the gate sentence, the Session 19 hole, and
`upgrade.sh` in the operating menu with the pointer to the upgrade guide.

**`docs/host-baseline.md`** (D1396): one sentence saying `~/.local/bin` and
`.venv` are an operator's shell rather than something `--apply` creates.

**Checked with Session 26's own self-check** (in the scratchpad at
`s26-scripts/s26-selfcheck.py`) as an interim, until Run 5 makes it a test.

**Targeted:** nothing. Documentation only, per §5's table.

**Done.** 2026-09-16. Twelve findings answered on `docs/upgrade-guide.md`, two
sections on `docs/operator-guide.md`, two sentences on `README.md` and one
paragraph on `docs/host-baseline.md`. The guide grows from 580 lines to 794.

**The new §1.0 is the one that matters, and it is the finding the brief did not
have a row for** (F-008). §1 assumes the reader owns `projects/<slug>/`, a
mechanism that arrives at 1.1.0 and is completed at 1.2.0. A fork made at 1.0.0
had no such thing and was obliged to put its domain **inside the release's own
files** — its migrations in `migrations/templates/`, its rows in the release's
`manifest.json` and `released.lock.json`, its operations in the release's
reviewed surface. §1.0 says so, says that `git merge` produced **nine
conflicted files** for the one fork that tried it, says that it nonetheless
converged and doctors 10 ok, and says plainly that **how such a fork converts to
`projects/<slug>/` is undecided** — ADR 0198 and ADR 0206 create the mechanism
and neither says how an existing fork enters it, and entering would mean
re-homing applied migrations, which D912 forbids. It records what the one
operator did about the conflicts as *what happened*, not as instruction,
because no rule for it exists to cite.

**D1389/D1404 are answered with the measured table rather than the count.** §1
now carries which of the six checks refuse a schema-4 manifest — **two, not
four** — each with its `--project`-less alternative and its exit code, and says
both refusals are correct rather than a blocker. `generate --check`'s two
different refusals are separated, and the one an adopter actually meets is the
one whose remedy the page used to get wrong: a project with no set of its own
has no client of its own to regenerate, and the directory the page would have
had them create is one the release does not track.

**D1392's repair is a standing sentence plus per-step notes.** §2 opens by
saying every command in it runs from the release ALREADY INSTALLED, that the
page describes each as 1.6.0 performs it, and that a step whose behaviour was
measured on a later release says so. §2 step 2 carries the 1.0.0 hand-over by
hand: `_hand_to_operator` arrives in **1.0.1**, so at 1.0.0 the kit stays
`root:root 0700` and the operator can neither verify it nor copy it off.

**D1398 is repaired by naming both kits.** §2 step 2 exports `-pre`, §3 step 8
exports `-post`, each step names the other, and the guard that refuses an
existing directory is untouched — the page was guaranteeing the case its own
guard refuses, and two suffixes cost nothing.

**F-031's table is the shape the finding asked for.** §3 step 9's return trip
now names **step 3** as well as step 1, with a nine-row table saying which
steps the second pass runs and why the others are skipped. The reason step 3
matters is stated: the render on the host is from the previous commit, and a
second deploy over it republishes the digest it was meant to replace, at exit 0.

**F-028** gets `ssh -tt` and `script(1)` by name, with why each satisfies D972
rather than works around it. **D1396** makes the sync conditional with the
one-line diff that decides it, says nothing installs `uv`, and says what to do
on a host that has none; `host-baseline.md` stops describing the maintainer's
shell as the baseline. **D1391** replaces the ownership check with one that can
see a dotfile. **D1399** drops the six-session-stale advice to move a manifest
out of the checkout and names the `.gitignore` glob that replaced it.
**D1393**, **D1394** and **D1397** say what the repaired commands now print and
what an earlier release prints instead. **D1400** repairs the README's gate
sentence — twenty-four gates, 01–18 and 20–25, with the Session 19 hole
explained — and puts `bin/upgrade.sh`'s three verbs in the operating menu they
were missing from.

**The operator guide's §13 gains a second half**, and it is the first
end-to-end reading of the operator's path this project has: what an outside
agent established on 2026-09-16 by upgrading a real deployment from 1.0.0 to
1.6.0 on a host this project does not administer. It includes the reader's own
positive finding, that the refusals are this product's best part and that where
they were stuck it was about what to do NEXT — which is the difference between
eighteen documentation findings and eighteen product faults.

**SIX FORWARD REFERENCES, and Run 6 owes each one a reading.** The page says
*"since 1.6.1"* at `upgrade-guide.md` lines 253, 321, 460, 472, 474 and 537 —
`check`'s worded answer, the named-owner refusal on every render directory, the
three-way leaf rendering, `--also` in the usage, and `deploy.sh --help`'s
session number. Every one is a repair Run 2 made and none of them is true of a
release that has not been bumped. **Run 6's checklist gains: grep the page for
`1.6.1` and confirm each claim against the bumped tree.**

**§1's version cells are deliberately NOT edited here.** ADR 0209 §3 makes the
release statement the bump commit's job, and pre-editing it would leave the
tree carrying a page that names a release the tree does not. Run 6 moves them.

**Checked with Session 26's self-check** as the plan says (the interim until
Run 5 makes it a test): every `bin/*.sh` named on either page exists and is
executable, every `--session`/`--through-session` equals `CURRENT_SESSION`, and
every flag written on a command line appears in that command's own `--help` —
**19 usages, 0 problems**. Its one blind spot is worth recording: it matches a
command line by its first word, so a flag on a `\`-continuation line is not
checked. Run 5's test inherits that and should not.

`test_documentation_index` and `test_session12_documented_path`: **28 passed**
(run because the README moved, not because this run needed them).

### Run 5 — the pages become checkable, and ADR 0209's guard

1. **Both pages join both scans** (D1383): `dx_record.DOCUMENT_ROOTS` and
   `test_session12_documented_path.CURRENT_PATH_DOCUMENTS`. Run the module and
   read what the existing assertions now say about them — every command exists
   and is executable, every `--session`/`--through-session` is 25, no step
   asks a reader to edit a tracked file. **An assertion that now fails is a
   finding about the page**, repaired in the page; an assertion that would
   have to be weakened is §9's stop.
2. **ADR 0209's guard**: the release's own documentation names the release.
   Concretely, from the ADR: both pages carry `template_version()` where they
   state the release, and the upgrade guide's release table has a row for the
   current version. A release that bumps and does not move them fails here
   rather than fourteen sessions later.
3. **D1400's other direction**: an enumerated set of operator-facing commands
   must appear in the README, so the next command whose job is the reader's
   task is not discoverable only by `ls bin/`.

Each with a battery, each mutation paired with a control.

**Targeted:** `test_documentation_index`, `test_session12_documented_path`,
`test_dx_record`, `test_acceptance_registry`.

**Done.** 2026-09-16. Six proofs, six mutations, six kills — after the first
pass produced one survivor that turned out to be a real gap between the guard
and the finding it was written for, and a second that turned out to be an
uninformative mutation.

**1. Both pages joined both scans, and both modules passed on the first run.**
That is the answer §7 question 1 demands be checked rather than enjoyed, so it
was: a probe measured what the widening actually reaches. `dx_record`'s scan now
reads 26 commands from the operator guide and 19 from the upgrade guide, and
**eight commands are documented that were reachable through neither of the four
pages it read before** — `bin/database-ports.sh`, `bin/dev-token.sh`,
`bin/edge-network.sh`, `bin/rotate-secret.sh`, `bin/rotate-signing-key.sh`,
`bin/storage-admin.sh`, `bin/upgrade.py`, `bin/write-session-evidence.py`. The
offline half reads both pages whole (47,683 and 41,935 bytes). Nothing failed
because Run 4 had already repaired what these assertions test; the widening is
real, not silent.

**2. ADR 0209's guard needed the pages to say something they did not say.**
Neither carried a statement of the release it describes — the upgrade guide
mentions `1.6.0` a dozen times as a git tag, a merge target and a measurement,
and *any* of those would satisfy a substring check while the page went stale. So
each page gains one canonical line, **`This page is part of release ` `N` `.`**,
and the guard reads it against `template_version()`. Three proofs: the pages
exist and their statement matches the tree; the upgrade guide's release TABLE
has a row for the current release, read as a table row and not as a substring;
and both pages are inside both scans, so removing one is red rather than quiet.
What is deliberately not asserted is the tag, for ADR 0209 §2's reason.

**3. D1400's other direction was weaker than D1400, and the battery said so.**
The first guard asked whether the README NAMES each operator-facing command. The
mutation that deleted `bin/upgrade.sh` from the operating menu **survived** —
correctly, because the command is still mentioned elsewhere in the file. That is
precisely the state D1400 records: mentioned once, inside a parenthetical about
which verbs take `--project KEY`, for six sessions. `in readme` cannot tell
*findable* from *present*. So a second guard reads the *Operating a deployment*
section between its heading and the next `## ` and asserts each menu command is
in **that**, with a length check so it cannot pass over an empty string.

**And the second mutation on it was uninformative** (D493) rather than a
survivor worth acting on: removing one of the three `upgrade.sh` lines left the
command in the section through the other two. Widened to the whole block, it
kills. Recorded because a survivor nobody explains gets read as a weak test, and
this one was a weak mutation.

**The six kills, each with a control it cannot reach**: a release statement one
patch stale; a release statement removed; a release table row renamed so the
current release has none; the upgrade guide dropped from the live scan; the
operator guide dropped from the offline scan; the upgrade block removed from the
README's menu. Every file byte-identical after.

**Targeted, once:** `test_documentation_index`, `test_session12_documented_path`,
`test_dx_record`, `test_acceptance_registry` — **86 passed**, after the
acceptance matrix was regenerated for five new proofs and a widened DX-DOC-001
clause. `ruff check` found one unsorted import block in the new code and it was
fixed rather than ignored.

**What this leaves for Run 6.** The release statement is `1.6.0` in both pages
and the release table's newest row is `1.6.0`. **All three now fail the moment
`VERSION` moves**, which is the whole point: Run 6's bump cannot be committed
without moving them, and Run 4's six `since 1.6.1` forward references get their
reading in the same commit.

### Run 6 — the bump, all-or-nothing

One commit (D690). In this order, because the order is enforced:

1. `VERSION` → **`1.6.1`**. `CURRENT_SESSION` stays **25** (§2).
2. The paragraph above `CURRENT_SESSION` rewritten for this release.
   `test_release_contract::test_the_constants_comment_states_the_class_it_proposes`
   reads it and requires: the form **`ADR 0162 prices it a PATCH`** exactly
   once; a sentence saying **which schemas did not move** (none of the
   manifest, outputs, capability, lock and secret schemas move, and no
   released migration is added); and either `Run 7` or `upgrade plan` named as
   what confirms the class on a deployment. **This session has no trip**, so
   the paragraph says the next host trip's `upgrade plan` is what confirms it,
   which is also D1401's obligation stated where a reader of the constant will
   meet it.
3. README's status line to `template_version` **1.6.1**, and its *Adopt*
   paragraph to name `1.6.1` while keeping D1311's sentence about 1.3.0–1.5.0.
4. `bin/apg.sh generate --project project.example.yaml` (D1238 — a bump moves
   `templateVersion` in the committed client), and the derived documents the
   gate compares: `render-config.py --bounds-doc --write`,
   `render-mcp-catalog.py --write`, `render-evaluation-report.py --write`,
   `render-acceptance-matrix.py --write`.
5. `chmod 755 bin/*` before `git add` — this session edits shell files through
   the Windows share and the index mode is the contract.

**Then the gate**, once, on a clean tree: `bin/session-01-check.sh`, which is
what §5's table asks of a run whose generated artefacts could drift.

**Done.** 2026-09-16. `VERSION` **1.6.0 → 1.6.1**, `CURRENT_SESSION` **25**,
one commit.

**The constant's paragraph took two attempts and both were the guard doing its
job.** `test_the_constants_comment_states_the_class_it_proposes` reads the
**final** `#:` paragraph, not the comment block: the first draft put *"ADR 0162
prices it a PATCH"* in an earlier paragraph and a closing one after it, so the
guard found **zero** priced classes. The second draft moved the pricing into
the final paragraph and still failed, because the guard reads the raw comment
including its `#: ` prefixes and *"…or secret schema\n#: moves…"* does not
contain the string `schema moves`. Reflowed, not reworded. Both failures are
worth recording: the guard is stricter than it reads, and a paragraph that
*says* the right thing in the wrong place is exactly what it exists to catch.

**The three assertions Run 5 armed all fired as designed.** Moving `VERSION`
with the pages untouched fails `test_the_operator_pages_exist_and_name_the_release_they_describe`
on both pages and `test_the_upgrade_guides_release_table_has_a_row_for_this_release`.
They were satisfied by moving the two release statements and adding the
**1.6.1 row** to the release table — the row an operator upgrading TO this
release reads — and the operator guide's §1 version cell, which now says why
the two numbers have come apart for only the second time.

**The six forward references Run 4 wrote get their reading, and all six hold**
(21 assertions, run against the bumped tree):

| Page says *since 1.6.1* | Measured |
|---|---|
| `check` says which question it answered | prints *a comparison CAN be made* and *no candidate was read* |
| every directory a render creates names its owner | **five** `make_directory` sites; the message carries the owner, the caller, `chown -R` and the whole `.generated` root |
| a leaf prints `(no such key)`, `null` and a JSON value apart | all three, and `<absent>` reaches no terminal |
| `--also` and its eight classes are in `bin/upgrade.sh --help` | all eight, by name |
| the verb-level `--help` no longer exits 2 | `check`, `plan`, `verify` each exit 0 |
| `deploy.sh --help` names the session | *implements session 25*, and `CURRENT_SESSION` as its source |

**Two of those twenty-one first read as failures and were my probe's fault**, a
`grep -A 12` window too short for `_cannot_create`'s docstring. Re-measured by
calling the function and reading the sentence it produces, which is the only
form of that reading worth having.

**The derived artefacts.** `apg generate` moved `templateVersion` to `1.6.1`
in the committed client and reported *version 1.0.0 (no contract change)* —
the client's own version does not move, because no contract moved (D1238's
point exactly). `render-config --bounds-doc`, `render-mcp-catalog` and
`render-evaluation-report` each reported **already current**, which is the
expected reading for a patch that moves no schema and no tool, and
`render-acceptance-matrix` had already been written in Run 5. `chmod 755
bin/*` before `git add`.

**The gate**, once, on the clean tree this commit left:
`bin/session-01-check.sh` → **exit 0, `session-01-check: PASSED`**, 14m42s.
**5,809 passed, 0 failed, 3 skipped, 0 errors**, 6,265 P0 nodes collected, 0
future placeholders, 0 identity collisions, 0 floating image refs, both fixtures
rendered, no container running. `source commit ce2f42fd18a8`, and a skip count
of 3 is the healthy reading for a contract run on this workstation (CLAUDE.md
§5). Step 6 confirms the derived documentation is current in all four
renderers, which is the half of D1238 a bump can get wrong silently.

**One apparatus note, because it cost ten minutes.** The gate was first
launched with `setsid nohup … &` from a `wsl bash -lc` invocation, which
CLAUDE.md §1 recommends — and **it never ran**: the WSL session ends when the
wrapper's command exits and took the detached child with it, leaving no log
and no exit-code file. Re-run as a harness-tracked background task, which keeps
the WSL process alive for the duration, it completed normally. The advice in
§1 assumes something holds the session open; a bare `wsl bash -lc` does not.

### Run 7 — the close, and the tag

1. Push; **read that commit's CI verdict by full SHA**, three jobs, judged on
   HTTP status.
2. **The tag**: `git tag -a 1.6.1 -m "1.6.1: the repair release"` on the
   CI-green `main` commit, pushed once. The operator cuts it at their
   keyboard; the message file is written with the Write tool, never a heredoc.
3. `git ls-tree -r --name-only 1.6.1 -- docs/ | grep -E "upgrade-guide|operator-guide"`
   must print both paths. **That command is the session's whole point** and
   its output goes in the `Done.` paragraph — D1388 is closed by a reading,
   not by an intention.
4. `CLAUDE.md` §2 in the launch folder (copied to the scratchpad first, its
   own rule): a `SESSION 27 COMPLETE` block, §9's row for the two pages
   replaced with what the cold reading found and what is still open, and the
   next free `D` and ADR numbers.
5. `docs/scope-closure.md` §15: what Session 27 left open, with the on-ramp
   priced against the tree.
6. Memory: the state file, and a file for what a stranger's upgrade measured.
7. This run's `Done.` in a documentation-only commit after the tagged one — a
   record cannot be inside the commit it describes.

**Done.** 2026-09-16. **Tagged `1.6.1` at `9b2fc3a`**, the fourth tag this
repository has (1.0.0, 1.0.1, 1.6.0, 1.6.1).

**CI on the tagged commit: `contract`, completed, success**, read by full SHA
`9b2fc3a663f9088f5fd28c2ad7040b7d431c1bed`. The tag was cut on that commit and
on no other, after the verdict and not before it — D1311's rule, that a tag is
the promise the compatibility sentence beside it made at the moment it was cut.

**The reading that closes D1388**, which is this session's whole point and is a
reading rather than an intention:

```
$ git ls-tree -r --name-only 1.6.1 -- docs/ | grep -E "upgrade-guide|operator-guide"
docs/operator-guide.md
docs/session-02-operator-guide.md
...
docs/session-11-operator-guide.md
docs/upgrade-guide.md

$ git ls-tree -r --name-only 1.6.0 -- docs/ | grep -E "^docs/(upgrade|operator)-guide"
   (no such path in that tag)
```

Twelve paths in `1.6.1` where `1.6.0` has ten, and the two that are new are the
two an operator holds. **And they say so from inside the tag**: `git show
1.6.1:docs/upgrade-guide.md` and `…:docs/operator-guide.md` each print *This
page is part of release `1.6.1`*, and `git show 1.6.1:VERSION` prints `1.6.1`.
That is ADR 0209's property demonstrated on the artefact it was written for,
rather than asserted about the working tree.

**`docs/scope-closure.md` §15** is written: eleven rows, and **the first is the
on-ramp question** — how a fork made before `projects/<slug>/` existed converts
to it. ADR 0198 and ADR 0206 create the mechanism and neither says how an
existing fork enters it, and entering means re-homing applied migrations, which
D912 forbids. It is a product decision before it is a page, and the upgrade
guide's §1.0 says so rather than pretending §1 covers it.

**`CLAUDE.md` §2** carries a `SESSION 27` block, the `CURRENT_SESSION` block now
records that **the tree and the deployment disagree by one patch** (D1401), and
§9's row for the two pages is replaced: the half that closed, and the half that
did not — **the operator guide has still not been read cold.** The pre-session
copy is in the scratchpad as `CLAUDE.md.pre-session-27`, which is that file's
own rule.

**What this session did not do, stated so nothing reads as measured.** No host
trip, no evidence document, no claim moved, no requirement registered, no
migration added, no schema moved. The class `1.6.1` proposes is priced by ADR
0162 and **confirmed by nothing yet**: the next trip's `upgrade plan` is what
prices it against a running deployment, and that trip inherits D1401.

**Next free: D1406, ADR 0210.**

---

## 7. Evidence

**No evidence document, and none is owed.** This session changes no claim's
verdict by assertion, deploys nothing, and runs no gate in a mode that writes
a half. Session 19 closed the same way and said so: *"No host trip, no
deployment touched, no evidence document written: this session changes no
claim's verdict by assertion."*

**CI is the check.** Every run pushes and reads its own commit's verdict by
full SHA. The bump commit additionally runs `bin/session-01-check.sh` locally
on a clean tree, because its generated artefacts could drift.

**`stage-3-findings.md` is not a walk record and must not be given to
`dx-record check`.** It is Session 19's `FINDINGS.md` again: an outsider's
account of using a release, structured as its author chose. ADR 0207's record
has nine required members and a reader that decides `documented_path`; this
file has none of them and is about the operator's path rather than the
adopter's. Whether the operator's path earns a claim of its own is §10's, not
this session's — and the honest reading of the file today is that if such a
claim existed it would be `failed`, on nine release-owned files edited and
several undocumented steps.

**What the next host sweep inherits**, so it is not discovered mid-run: the
tree will read `1.6.1` and both projects are deployed at `1.6.0`, so
`stage_release` fails its live half until that trip's deploy (D1401). Deploy
first, then sweep, which is what every trip already does.

---

## 8. Security invariants this session touches

**It touches none, and one finding in the brief is security-shaped and is not
repaired here.**

`stage-3-findings.md` F-022 measured that a fork which puts its relations in
the release's **shared** reviewed surface thereby puts `<relation>:read` and
`<relation>:write` into the scope vocabulary the release offers **every**
project, because ADR 0200 derives the vocabulary from that surface. The
findings file's own reading is the correct one: nothing grants those scopes,
`mcp-contract check` still compiles the same six tools, and nothing is
reachable. **But a vocabulary one tenant's tables can extend is a property
nobody chose**, and it is the strongest argument in the brief for the on-ramp
being taken soon.

Recorded in §10 and in the ledger. It is not repairable by documentation and
it is not repairable without the on-ramp: the mechanism that keeps a tenant's
relations out of the shared surface is `projects/<slug>/`, which is exactly
what a pre-ADR-0198 fork cannot reach.

**What this session must not do**, and §9 repeats it: widen the project-set
lint, loosen any surface equality, or weaken a contract test to make a fork's
tree pass. The release's own words in `test_api_migrations.py` are the rule —
*containment is what the non-negotiables call weakening* — and the findings
file independently reached the same conclusion and put the release's side back.

---

## 9. Stop conditions

- **No host trip, and no deploy.** If a repair turns out to need one, it moves
  to the on-ramp session rather than growing this one.
- **The on-ramp is not taken.** `follows_release_version`'s **enforcement**
  does not change (Run 3 changes only its explanation); `lint_project_set`'s
  `app_runtime` refusal does not change; no project-level extension point for
  a client format is added. Each is new capability with an ADR and a cluster
  behind it.
- **No applied migration is re-stamped, and nothing this session writes
  advises one.**
- **No contract test is weakened.** If Run 5's scans produce an assertion that
  would have to be loosened to admit a page, stop: that is an ADR, and the
  page is what moves.
- **The tag is not cut before CI is green on the bump commit**, and not on a
  commit whose pages still carry a known finding from the brief.
- **If `upgrade plan` would price this release above `patch`**, the class is
  re-decided before the tag. ADR 0162's class is a promise about what an
  adopter must do, not a number chosen in a comment.
- **A measurement in Run 1 that contradicts this plan changes the plan.**
  Three of the brief's entries were already found to be about a different set
  than the page they are addressed to (D1389); more may be.

---

## 10. Open items this session carries and creates

**Created here, for the on-ramp session (28, or Stage 4's first):**

- **A project set frozen against an earlier release cannot be frozen against
  this one** (findings F-012). `freeze_project_lock()` computes `follows` from
  the current release lock and refuses everything below it; there is no way to
  record the release a set was *actually* frozen against; and the remedy the
  refusal prints breaks ADR 0206's version-matched ledger move and then fails
  on apply, which ADR 0206's own *Alternatives rejected* already says. **This
  is the single change the findings file names as the one that would have made
  the upgrade ordinary.**
- **A project set may not grant to `app_runtime`** (findings F-013), which is
  the one grant the release's own migration `0003` makes and which README
  §*Adding your own tables* tells an adopter to model. The lint's docstring
  defers it: *"that is a product decision for a later session, recorded."*
  Recorded.
- **A fork's relations in the shared surface widen the agent scope vocabulary
  for every project** (findings F-022, §8).
- **A pre-ADR-0198 fork cannot pass the gate** (findings F-022): 47 failures
  and 49 errors, of which the largest class is `projects/example/`'s snapshot
  comparison against a merged surface it never served. No repair exists while
  the tenant's objects are in the release's files.

**Created here, for any later session:**

- **The `--help`-versus-parser guard, generalised.** Run 2 builds it for
  `bin/upgrade.sh` alone. Over all 65 verbs it is a measurement nobody has
  made, and D1316 found the opposite direction (a usage naming a flag the
  command refuses), so the general guard is bidirectional and worth having.
- **The host's interpreter is unchecked** (D1396). The release pins 3.12 and
  `bin/doctor.sh` enforces it on a workstation; the machine that runs every
  deploy ran 3.14 on the findings file's host, and `provision-host.sh --check`
  reported nothing. Whether the baseline installs a pinned interpreter, or the
  doctor's deployed mode checks the one in use, is a decision about what
  `--apply` does to a machine.
- **Whether the operator's path earns a claim** (§7). `documented_path` is the
  adopter's; nothing measures the operator's, and the first reading of it came
  from outside the project and is not in the evidence model.
- **`client_ir.FORMAT_TYPES` has no project-level extension point** (findings
  F-030). Run 2 adds the spellings the rig finds, which fixes the instance; a
  project whose column type the release has never served still has nowhere to
  declare it but a release file.

**Carried in, unchanged:** the rotation (D860), the Docker question on the
host (D1375), `render-jwks`'s file-event-as-domain-event sentence (D1374), the
retention policy for `agent_audit` and `agent_idempotency` (D1255), the audit
endpoint's filters (D1248), the four modules outside every sweep (D1240), the
public-endpoint decision (D1084). `docs/stage-4-decision-report.md` §6 is
still what a Stage 4 plan starts from.

---

## Appendix — what to consult, and how a run is executed here

**Read before Run 1**, in this order: this plan's §1; `stage-3-findings.md`
whole; `docs/plans/session-26-implementation-plan.md` §1 (D1379–D1387, four of
which this session repairs); `docs/plans/session-19-implementation-plan.md`
whole, because it is this session's shape and its D1033 is this session's
first row; ADR 0162 (what a patch promises), ADR 0195 (three outcomes, the
third reported), ADR 0204 (a generated client is a claim about a surface), ADR
0206 (the ordering space, and the paragraph it refutes), ADR 0207 §9, ADR 0208
(what the two pages are and what holds them); `docs/scope-closure.md` §14.

**Do not read** `stage-3-findings.md` as measurement. It is a careful record
by a reader who could not ask anybody anything, and §1 already found one place
where its arithmetic is about a different set than the page it addresses
(D1389). Every premise gets re-measured in Run 1.

**How a run is executed here** is `CLAUDE.md` §5, and three of its rules are
load-bearing for this session in particular:

- **Documentation only runs nothing before push**; a run that adds a page owes
  `test_documentation_index`; a run that adds or renames a test function owes
  `test_acceptance_registry` (D1119); a run that moves a `bin/` command's
  usage owes `test_cli_contract`.
- **Every run that writes a test writes a battery** — caches cleared,
  `PYTHONDONTWRITEBYTECODE=1`, anchors pre-flighted to match exactly once, a
  paired control the mutation cannot reach, `FAILED` asserted rather than
  `ERROR`, and the tree restored by copy and `cmp` rather than by
  `git checkout --`.
- **A commit message is not evidence that the diff contains what it says**
  (D1116): `git diff --stat` against this plan's list, one line each, before
  the push.

**The scratchpad carries Session 26's instruments** under `s26-scripts/`: the
whole-`--help` capture and the script that made it, the release-table reader,
and the self-check Run 4 uses as an interim and Run 5 replaces with a test.
WSL's `/tmp` does not survive `wsl --shutdown`; those copies do.
