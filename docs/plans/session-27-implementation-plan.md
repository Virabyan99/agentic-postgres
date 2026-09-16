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
**Next free:** D1402, ADR 0210.

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

D1388–D1401. Rows marked **recorded** are not repaired here, with the reason.

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

**Done.**

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

**Done.**

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

**Done.**

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

**Done.**

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

**Done.**

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

**Done.**

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

**Done.**

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
