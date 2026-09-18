# Session 30 — Inheritance, the rotation, and the two decisions

**Status:** **IN PROGRESS.** Planned 2026-09-18 at `f89b03a` (the Stage 4
plan commit) on `main`; **Runs 1–3 done 2026-09-18** — Run 1 the mirror,
diagnosed with root (a fourth outcome; D1546 rewritten, D1549 opened); Run 2
the rigs and ADRs 0216–0220 (four of seven measurements came back different
from the plan; D1542, D1544 and D1548 rewritten, D1550–D1552 opened). Run 3 the exec discipline: one helper, one
sourced guard, the class at **0** unguarded sites, 11/11 mutations killed
(D1553–D1554 opened); **Run 4** `release-reading --ref` and `compile --output`
(D1555–D1556 opened; two registry entries deferred to Run 6); **Run 5** the two
suite-shape guards, five shadows repaired, 23 orphans frozen, three counts
(D1557–D1558 opened); **Run 6** the bump — `VERSION` 1.8.0 and
`CURRENT_SESSION` 30, five requirements and five claims, the Session 30
gate, and the redeploy-before recipe the trip needs (D1559–D1564 opened). §1 is D1537–D1548 at planning, each read from the
tree at `f89b03a`. Run 1 measured D1546 and added **D1549**; Run 2 rewrote
D1542, D1544 and D1548 and added **D1550–D1552**; Run 3 added **D1553–D1554**;
Run 4 added **D1555–D1556**; Run 5 added **D1557–D1558**; Run 6 added
**D1559–D1564**; **next free is D1565**, and the runs add theirs below.
ADRs **0216–0220** are this session's, all written in Run 2 and all Accepted;
**0220 went to the mirror fold** (D1549/D1546), not to Run 4, because D1540's
condition was not met (D1550). **0221 is reserved, conditionally, by Run 4.**
**Brief:** `docs/plans/stage-4-plan.md` §5 *Session 30* whole (Builds (a)–(h) /
Already true / Must not / Measures / Closes), its rows **D1518** (ADR 0216),
**D1527** (ADR 0217's boundary), **D1528** and D380 (recorded, not built),
**D1532** (the seven carried-in items), **D1533** (the rotation as its own
sitting), **D1536** (the stale counts); §3's ordering rule *30 before
everything*; §7's row for Session 30; §8 whole; §9's stop condition about the
rotation sheet; §11 (how this plan is shaped). Plus `docs/scope-closure.md`
§22 *What Stage 4 inherits, in order*, `docs/plans/session-29-implementation-
plan.md` §9 and its Appendix (the sheet), and `docs/plans/session-28-
implementation-plan.md` **Appendix R** (the rotation sheet this session
executes verbatim).
**Shape:** nine runs on `main` directly (the tree's practice since Session 26;
a branch is not required and CI reads every code commit). Run 1 is a **live
diagnosis with root** (the mirror). Runs 2–6 are offline. **Run 7 is a trip**
(deploy, one sweep, the tag). **Run 8 is the rotation, on its own day, on its
own sheets**, alpha then beta. Run 9 is the close.
**Product version at close:** `CURRENT_SESSION` **30**; `template_version`
**`1.8.0`** — a new package module and a shell library that every container
exec passes through, `--ref` on `release-reading`, `--output` on
`mcp-contract compile`, two suite-shape guards, one live proof registered;
**no migration, no manifest, outputs, capability, lock or secret schema move,
no new deployed-document field**. ADR 0162: `upgrade plan` will read the
change as `implementation` or `command_added` and require at most `minor`;
the stage rule (D1081, stage plan §2.2) moves one minor per session
regardless, and a `major` there is §9's stop.
**Written for whoever picks this up cold, and it will be a different model
than the one that planned it.** Every path is exact and was read from the
tree on 2026-09-18. Every third-party claim below is either measured in Run 2
with a control, or marked as the measurement Run 2 owes — never assumed. Read
`CLAUDE.md` §1 in the launch folder before the first command, then this
plan's §1, then the appendix. **If a step here and the tree disagree, the
tree wins and the disagreement is a divergence row**, never a silent
reconciliation.

---

## 0. Where the session starts

**The tree and the deployment agree.** `1.7.0` is tagged on
`8c61309b6cf9`, the commit both projects record as `source_commit`;
`HEAD` is `f89b03a`, one documentation commit past it (the stage plan).
`CURRENT_SESSION` 28. `evidence/session-28.json`: 129 claims, 123 passed,
5 `not_run`, 1 `failed` (`documented_path`, deliberately). Both projects
doctor 11 ok / 0 problem; alpha's ledger 33, beta's 35. The host reads
`degraded` for three investigated causes, and **two of them are this
product's units**: `agentic-postgres-backup-mirror@alpha-dev` and `@beta-dev`
failed on 2026-09-18 at 04:50 and 04:38 (D1512), last successful copies
2026-09-17 (3718 and 3329 objects). The R2 primary is healthy.

**What this session inherits, measured again at `f89b03a` rather than
recalled** (every number below is §1's):

- **The D972 guard is on one command and the class is thirteen files, not
  fourteen** (D1537). `[ -t 0 ] && { [ ! -t 1 ] || [ ! -t 2 ]; }` occurs
  exactly once, `deploy.sh:260`, exit 2, before the root check at `:264`,
  with the message *`--through-session with stdin at a terminal and stdout or
  stderr redirected stops at the first docker exec -i under sudo (D972). Run it
  unredirected; the terminal is the log.`* `deploy.sh` itself runs no `docker
  exec`; the string is in its comment (`:254`) and its own message (`:261`).
  **Thirty-nine call sites** build a `docker exec` argv: four in shell
  (`bin/apg-diag.sh:335`, `bin/db.sh:186`, `:191`, `:201`), thirty-two in
  eleven `bin/*.py` files, three in two `src/` modules
  (`dev_environment.py:834`, `rehearsal.py:457`, `:475`). Seven files define
  their own `psql()`/`docker()`/`in_container()`. **There is no `bin/lib/`
  and no `bin/*.sh` sources anything**: `python_bin()` is copied 62 times.
- **The class splits by what the child's stdin is, and only one half can
  hang** (D1538). `bin/doctor.py` (`run()` `:67`), `bin/fleet.py` (`:63`),
  `bin/restore.py` (`:97`) and `bin/rehearse.py` (`:76`) pass
  `stdin=subprocess.DEVNULL` and are structurally immune. `bin/deploy-
  project.py` (`run()` `:184`, and a bare `subprocess.run` at `:1745`),
  `bin/backup.py` (`:246`, `:291` — the seven-minute hang of D1501),
  `bin/restore-test.py` (`docker()` `:120`) and both shell files **inherit
  the terminal**. The rest feed `input=` and never read it. And **D1505's
  hang was not a `docker exec` at all**: `bin/migrate.py:137` reaches dbmate
  through `bin/compose.sh … run --rm dbmate` with inherited stdio (D1544).
- **`release-reading` reads `HEAD` and has a passing contract test that says
  it must** (D1539): `tests/contract/test_release_reading.py:360`
  `test_the_command_takes_no_arguments_and_says_so` asserts exit 2 and the
  text *takes no arguments*, and it is a node id of `REL-READ-001`
  (`tests/acceptance-registry.yaml:4011`). Adding `--ref` replaces that test
  with a stricter one, which needs an ADR (CLAUDE.md §6).
- **`mcp-contract.sh compile` states in its header that having no output
  path is the design** (`bin/mcp-contract.sh:8-13`; D1540), and its `*)`
  arm refuses `--output` with exit 2 today. The documented lines
  (`docs/new-team-member.md:272-273`, `README.md:551-552`) redirect with `>`;
  a refused compile exits 5 **after** the shell has truncated the target,
  and `README.md:558-562` tells the reader to delete the 0-byte file by hand.
  No documentation test can see the omitted flag or the continuation line
  (`test_documentation_index.py:108` is line-anchored and runs only `--help`).
- **The orphan proof errors at setup on one literal**:
  `tests/deployment/test_session24_studio.py:724` passes `ARRAY[]::text[]`
  to `app_private.auth_create_user`, which migration `0011:116`
  (`CHECK (array_length(scopes, 1) IS NOT NULL)`) refuses. Its node id is in
  **no** registry entry (`grep -c` returns 0), and **no test asks the reverse
  question** — every `tests/deployment` proof is registered somewhere — so an
  orphan is invisible by construction (D1542). It **cannot** be registered to
  `studio_surface` as the stage plan says: that claim is in `OFFLINE_CLAIMS`
  and `evidence_claims.py:1008-1026` refuses an offline claim whose proof
  carries a live marker (D1543).
- **One local still shadows a module-level function**:
  `tests/deployment/test_session9_agent_writes.py:709` `refused = api_call(…)`
  over `def refused` at `:91` (callers `:286`, `:984`, `:1256`, `:1263`). No
  selected ruff rule sees it (`F811` is same-scope; `PL` is not selected and
  `PLW0621` would flag ~30 legitimate fixture parameters — `pyproject.toml:
  20-52`). The model for the guard is
  `tests/contract/test_deployment_suite_shape.py:64`'s AST walk.
- **D1536 has a third location** (D1541): `docs/dev-environment.md:177`
  carries the same *31 released* sentence as `docs/capacity-envelope.md:146`;
  `docs/project-isolation.md:86-87` says *fifteen … thirteen* against
  `evidence.ISOLATED_FIELDS`'s 18 pointers (`evidence.py:37-68`). No test
  reads any of the three numbers.
- **The rotation is fully rehearsed and never performed** (D860, D1533);
  its pre-flight is discharged (D1477); it moves **one of nine** node ids and
  closes **no claim** (D1469, D1496). `docs/operator-guide.md` §15 is the
  operator's copy of Appendix R and agrees with it, folding Appendix R's row
  `2b` into its step 3 as an indented paragraph.

**What this session builds, in one paragraph.** A container-exec discipline:
`src/agentic_postgres/container_exec.py` builds every `docker exec` argv the
product runs and runs it with **stdin closed unless input is given**, so no
product child can ever read the terminal; `bin/lib/tty-guard.sh` holds the
D972 refusal moved out of `deploy.sh:260` (not retyped), sourced by
`deploy.sh` and by the two shell commands that exec directly; every one of the
thirty-nine sites goes through the helper, `migrate.py`'s dbmate run gets the
same closed stdin and `-T`, and **the class is guarded against the
definition** by an AST proof that no `subprocess` call anywhere in `bin/` or
`src/` runs `docker` or `compose.sh` with inherited stdin. `apg release-reading
--ref REF` (default `HEAD`), authorised by ADR 0219, so the reading before a
tag can read the commit the tag goes on. `bin/mcp-contract.sh compile --output
PATH`, which writes only after the compile succeeded and never touches PATH on
a refusal, and both documented lines rewritten to it. Two suite-shape guards
under `tests/contract/`: a local that shadows a module-level function (the
D1509 class, with the `:709` shadow repaired) and a `tests/deployment` proof
that belongs to no registry entry (the orphan's class). The orphan's fixture
repaired and the proof registered as **`STU-QUERY-002`** under a new host
claim. Three prose counts corrected. ADR 0216 (no public endpoint in Stage
4), 0217 (Stage 4's boundary), 0218 (the exec discipline), 0219
(`release-reading` takes a ref). **Before any of it, the mirror diagnosed
with root**; after all of it, **two sittings**: the deploy-and-sweep with the
redeploy declared, and the rotation from Appendix R.

**What it does not build, by decision** (§1, stage plan §5): a guard on a
command none of whose children can read the terminal (D1538 — that would
refuse `sudo bin/doctor.sh --project alpha-dev --json > file`, which works
today); any of the other three rotations (D1533, D1510); a sweep inside the
930 s window; a port, a route, a bind (ADR 0216); a control plane or a login
(D1517); a lifetime for `apg-diag` (D1528 — recorded in §10); a widening of
`apg-diag`'s log allowlist (D380 — §10); a test that reads a number out of
prose (D954's direction is fixed by hand, in three files, and the count that
matters — `ISOLATED_FIELDS` — is already guarded against code by
`test_render_isolation.py:105-118`).

**Read before touching anything:** ADR 0002, 0044 (why `publication()`
raises — 0216 keeps it), 0050, 0071 (what `apg-diag` is), 0088/0098/0122/0215
(the rotation and its reader), 0093 (a `bin/` command's imports), 0135, 0155
(what a deploy recreates — the rotation's step 3 rests on it), 0158, 0162,
0163, 0185 (the non-goal 0216 leans on), 0188 (the mirror), 0190/0193 (the
`wal-archiving-failure` rehearsal blocks the MIRROR's path with an iptables
rule — Run 1's first hypothesis), 0195, 0202, 0205, 0209 (a release page
gains a row in the bump's own commit), 0214; D105, D267, D374 (a scan that
matches nothing), D386, D486, D499, D504, D509, D600, D671, D676, D687, D690,
D941, D972, D1014, D1116, D1119, D1146, D1184, D1187, D1188, D1236, D1240,
D1242, D1282, D1425, D1469–D1477, D1482, D1488, D1501, D1504–D1513.

---

## 1. The divergence table

Six columns. Rows D1537–D1548 were read from the tree on 2026-09-18 at
`f89b03a`; where a row's *Repository does* column says *measure*, Run 2 owns
the measurement and rewrites the row with the numbers. **D1546 was rewritten by Run 1 with what it measured, and D1549 is Run 1's
own. Run 2 rewrote D1542, D1544 and D1548 with what its rigs measured and
added D1550–D1552. Run 3 added D1553–D1554, Run 4 D1555–D1556, Run 5
D1557–D1558, Run 6 D1559–D1564. Next free number after this table is
D1565.**

| # | Said | Repository does | This session | Why | ADR |
|---|---|---|---|---|---|
| **D1537** | D1504, D1532, stage plan §5 *(b)*: *"fourteen callers"*, *"three shell entry points spell `docker exec -i` directly (`deploy.sh`, `bin/apg-diag.sh`, `bin/db.sh`)"*. | **Thirteen files invoke `docker exec`; `deploy.sh` is not one of them.** It contains the string only in the guard's comment (`:254`) and the guard's own message (`:261`), and reaches the pattern one layer down through `exec "$(python_bin)" bin/deploy-project.py` (`:270`). D1504's own hedge — *"the rest match by argv spelling"* — is where the fourteenth came from: the spelling matched the refusal text. The real inventory is **two shell files (four sites), eleven `bin/*.py` (thirty-two sites), two `src/` builders (three sites): 39 sites, 15 files.** | **The proof counts sites, not files, and the number is measured by the AST scan Run 3 writes**, with the control that the scan finds the helper's own call (D374). This plan's text says thirteen and thirty-nine; a run that reads a different number rewrites this row. | A count carried from a plan into a test is a count nobody measures twice (D1116's shape). A scan derives it. | — |
| **D1538** | D1504's conclusion and stage plan §5 *(b)*: *"applies the D972 guard … moved, not retyped … every one of the fourteen callers routed through it"* — the guard as the repair, applied to every caller. | **The hang needs a child that reads the terminal, and only some children do.** Four modules already pass `stdin=subprocess.DEVNULL` to every exec (`doctor.py:67`, `fleet.py:63`, `restore.py:97`, `rehearse.py:76`) and cannot hang under any shape; `sudo bin/doctor.sh --project alpha-dev --json > file` at a terminal **works today** and a guard on `doctor.sh` would refuse it. The hanging half is `deploy-project.py`'s `run()` (`:184`, no `stdin=`), its bare `subprocess.run` at `:1745`, `backup.py:246` and `:291`, `restore-test.py:120`, `db.sh:186`/`:191`, `apg-diag.sh:335` — and `migrate.py:137`'s compose run (D1544). | **The repair is that no product child reads the terminal; the guard is the belt on the one command that had it.** `container_exec.run()` passes `stdin=DEVNULL` unless `input=` is given, and `-i` exactly when it is (`test_storage_admin.py:55`'s rule, now the product's); `run_dbmate` gets `stdin=DEVNULL` and `-T`; `db.sh`'s two no-stdin verbs and `apg-diag.sh`'s query get `< /dev/null` on the line. `deploy.sh` keeps its refusal, **moved** into `bin/lib/tty-guard.sh` and sourced. **The class guard is an AST proof**: every `subprocess.run/Popen/check_output/call` under `bin/` and `src/` whose argv literal starts with `docker` or names `compose.sh` either lives in `container_exec.py` or carries `stdin=`/`input=`. **Measured in rig 30a, Run 2**, with both controls, before a line of Run 3 is written. | A guard everywhere refuses working shapes and is still a rule about a symptom; closing stdin removes the mechanism (a stopped process is one that read a terminal it was not given). CLAUDE.md §7 rule 5: guard the class against the definition, never the field that failed — the definition here is *a child with an inherited terminal*, and the AST scan reads exactly that. | **0218** |
| **D1539** | Stage plan §5 *(d)*: *"`apg release-reading --ref REF` (default `HEAD`)"*, and D1513: *"A `--ref` would close it."* | **A passing contract test asserts the opposite**: `test_release_reading.py:360` `test_the_command_takes_no_arguments_and_says_so` runs the command with `--since 1.6.0`, expects exit 2 and *takes no arguments* in stderr, and is a node id of `REL-READ-001` (`acceptance-registry.yaml:4011`). `bin/release-reading.sh:91-94` refuses any argument; `bin/release-reading.py:189` parses none; `:96` is `git("rev-parse", "HEAD")`. | **ADR 0219**: the command takes **exactly one** option, `--ref REF`, resolved by `git rev-parse --verify REF^{commit}` and refused with exit 2 when it does not resolve; `HEAD` when absent; every other argument still exit 2. The test is **replaced by a stricter one** (`test_the_command_takes_exactly_one_option_and_refuses_the_rest`: `--since 1.6.0` → 2, `--ref` with no value → 2, `--ref nonesuch` → 2 naming the ref, `--ref HEAD` → the same bytes as no argument), its node id moved in the registry, `test_acceptance_registry` run (D1119). A new requirement `REL-READ-002` carries the ref half. | CLAUDE.md §6: a passing test may be replaced by a stricter one when an ADR authorises it; widening *no arguments* to *one enumerated option* is that shape. Silently editing the assertion would be the weakening §6 forbids. | 0214, **0219** |
| **D1540** | Stage plan §5 *(c)*: *"`bin/mcp-contract.sh compile --output PATH` (the command writes the file after it succeeds and refuses before touching it)"*. | **The header says no output path is the design** (`bin/mcp-contract.sh:8-13`: *"There is no output-path option and that is the design: the redirect happens in the caller's own shell, so a candidate lands where a human has to read it before committing it"*), the usage line (`:123`) shows `> candidate.json`, and `*)` (`:138-142`) exits 2 on `--output`. `compile` streams (`bin/mcp-contract.py:182`) and its adopter-path refusal is exit 5 raised **after** the shell's `>` has truncated the target — which `README.md:558-562` documents as a cleanup the reader performs. **Measure (Run 2): does any passing test assert `compile` has no output option or writes no file?** `git grep -n "writes no file\|output-path\|no --output" tests/` at planning: no hit in a test body. | **`--output PATH` on `compile` only** (`lock` and `check` stay stdout-only): the candidate is written to `PATH.tmp.<pid>` beside the target and renamed over it **after** `command_compile` returned 0; on any non-zero return PATH is untouched and no temporary is left. The header's paragraph is rewritten to say the same thing the old one meant — the candidate still lands where a human reads it before committing, now without a 0-byte file on refusal — and cites this row. Both documented lines become `bin/mcp-contract.sh compile --project project.yaml --output projects/<slug>/contracts/mcp-capabilities.canonical.json`; `README.md:558-562`'s cleanup sentence is deleted, because there is nothing to clean up. **If Run 2's grep finds a passing test asserting the old design, ADR 0220 authorises the replacement; otherwise the header rewrite and this row are the record.** | The design's reason (a human reads the candidate) survives; its mechanism (a shell redirect) is what leaves a truncated file, and *documentation is not a control* is the sentence Session 29 wrote about exactly this line. A `tmp` + `mv` in the docs would move the defect into a longer line the reader types. | (0220, conditional) |
| **D1541** | D1536: *"`docs/capacity-envelope.md:145-147` says '31 released'"* — one location. | **Two**: `docs/capacity-envelope.md:146` and `docs/dev-environment.md:177` carry the same sentence (*"the 31 released plus the example project's set of"*). The number went stale at Session 24 (`session-24-implementation-plan.md:508` says *31 released* against 33 applied) and both pages inherited it. | Three edits in Run 5: both *31 released* → **33**, `docs/project-isolation.md:86-87` *fifteen parsed semantic fields plus all thirteen derived role names* → **eighteen JSON pointers** (name the constant). `test_capacity_envelope` and `test_documentation_index` run afterwards, though neither reads the numbers. | D954's direction: a number in prose that a program stopped agreeing with is found by grepping for the OLD number, not the file the row named. Run 5 greps `git grep -n "31 released\|fifteen parsed"` and edits every hit. | — |
| **D1542** | Stage plan §11: *"Every proof registered to a claim, checked by the registry test, so an orphan cannot read as `passed`"* — stated as an existing property; and this plan at planning: **Measure (Run 2): how many `def test_` under `tests/deployment/` are node ids of no registry entry?** with *Expected: one, the Studio orphan.* | **MEASURED IN RUN 2: TWENTY-THREE, not one.** The registry names **237** distinct `tests/deployment/…::…` node ids; the tree defines **260** `test_` functions under `tests/deployment/`. Measured by AST walk and verified independently against the registry text with a control (three known-registered names matched once each; five sampled orphans matched zero). The Studio orphan is one of the 23. The other 22 are: `test_session2_host.py` × 5 (`ufw_denies_incoming_by_default`, `sshd_limits_authentication_attempts`, `the_edge_publishes_exactly_eighty_and_four_four_three`, `the_docker_user_chain_is_reachable_from_forward`, `the_daemon_runs_the_configuration_we_installed`), `test_session2_isolation.py` × 5, `test_session2_edge.py` × 4, `test_session9_agent_writes.py` × 3, `test_session11_operations.py`, `test_session12_isolation_matrix.py`, `test_session14_observability.py`, `test_session20_tenant.py`, `test_session8_agent_plane.py`. **Several are security proofs** — the firewall, sshd's limits, and four of the project-isolation proofs are outside the evidence system entirely. | **The guard is built as planned and `KNOWN_UNREGISTERED` is real work, not a formality.** Run 5 writes `test_every_deployment_proof_is_a_node_id_of_some_requirement` with its synthetic-orphan control. The Studio orphan is registered as `STU-QUERY-002` (D1543). **The remaining 22 are NOT silently frozen**: each is triaged in Run 5 into either a registry entry under an existing requirement, or the tuple with the session that owns it. Run 5's Done lists the split. If triage proves larger than Run 5's budget, the tuple takes all 22 and §10 carries the triage as Session 31's, **with the security proofs named**. | The stage plan asserted as an existing property something nothing checked — the third instance this run of a premise that was reassuring and unmeasured. 23 proofs may have been running and passing all along, or not running at all; nothing in the evidence system can tell, which is precisely D1236's `studio_*` lesson at 23× the scale. | — |
| **D1543** | Stage plan §5 *(f)*: the orphan *"registered to `studio_surface` in `tests/acceptance-registry.yaml`"*. | **`studio_surface` is in `OFFLINE_CLAIMS`** (`evidence_claims.py:66-130`) over five `STU-*` requirements whose node ids are all `tests/contract/…`, and `evidence_claims.py:1008-1026` refuses an offline claim whose proof carries a live marker. The orphan is `live_host`. Registering it there would make the claim un-writable in every mode. | **A new requirement `STU-QUERY-002` under a new HOST claim `studio_tenant_read`**, not declared offline, with exactly this proof as its node id, `target_session: 30`, and the session table in `tests/contract/test_evidence_claims.py` (`:1079`'s shape) gaining `"studio_tenant_read": 30`. The fixture at `:724` passes `ARRAY['notes:read']::text[]` (sorted, non-empty — `conftest.py:1447-1448`'s rule, `DEFAULT_PROBE_SCOPES` `:1482` is the vocabulary). | ADR 0089 and D1150: a new requirement gets a claim of its own and is never joined into an older one; ADR 0202: an offline claim is declared, and a live proof cannot hide under one. | 0089, 0202 |
| **D1544** | D1505: *"`migrate.sh` reaches dbmate through `docker exec -i`, stdout was a pipe, and it stopped."* This plan at planning: *"its mechanism is `docker compose run` allocating a pseudo-tty on a terminal stdin and reading it — a second shape of the same class."* | **The path is as described; the MECHANISM IS FALSIFIED.** `migrate.py:137` `run_dbmate` does reach dbmate through `bin/compose.sh <rendered> --runtime --profile migration run --rm dbmate` with `subprocess.run(command, check=False)` and fully inherited stdio — read at `5444c71`, and `migrate.py`'s two genuine `docker exec -i` sites (`:235`, `:300`) both feed `input=`. **But rig 30b2 (compose 5.1.3, `sudo` with `use_pty`, terminal on stdin, stdout redirected) measured that `docker compose run` does NOT read the terminal**: a service whose command is `true` completed (exit 0) in that exact shape, while a service whose command is `cat` hung. Rig 30a2 isolated the same variable for `docker exec`, one at a time: no-read/no-`-i` → 0; no-read/**with `-i`** → 0; reads/no-`-i` → 0; reads **and** `-i` → **hung**. **dbmate does not read stdin**, so `run_dbmate` cannot stop by this mechanism, and D1505's seven-minute stop has a cause that is still not established. | `run_dbmate` gets `stdin=subprocess.DEVNULL` and `-T` in Run 3 anyway — nothing reads that stdin and closing it costs nothing — and the AST guard names `compose.sh` beside `docker`. **ADR 0218 states D1505 as measured NOT to reproduce here** rather than asserting a mechanism, and the class it defines is the measured one: *a child that reads stdin, handed a terminal*. D1505's own cause is a §10 item. | The repair was right and the reason given for it was wrong, which is the more dangerous half: an ADR that had stated compose's pty as the mechanism would have been cited for years by readers who never re-measured it. Rig 30b v1 measured nothing at all (every arm died at `compose: no runtime override for fixture-alpha-dev` before a container started) and that was reported as *could not determine* rather than folded into *the mechanism is wrong* — ADR 0195 applied to this session's own rig. | **0218** |
| **D1545** | Stage plan §5 *Already true*: *"`release-reading`'s eleven facts."* | `render()` (`release_reading.py:259-351`) prints **fifteen** labelled fact lines in four blocks (HEAD: commit, VERSION, tags on HEAD; the last tag: name, commit, date, VERSION at it; since it: commits, files; counts: released migrations, ADRs; the bump: commit, subject, moved with it, commits after it), then the three `CHECKLIST` questions. The word *eleven* occurs nowhere in `bin/` or `src/`. | Nothing changes; `--ref` prints the same fifteen lines for the resolved commit, with the first block's label reading **`ref`** instead of `HEAD` when one was given (so a transcript says which commit it read — D1513's whole point). `test_the_reading_names_the_ref_it_read` asserts the label. | A count in a plan that the tree does not carry is a count a cold executor would go looking for. | 0214 |
| **D1546** | D1512: the mirror units failed on 2026-09-18 at 04:38 (beta) and 04:50 (alpha), *"never diagnosed beyond `exit-code`"*; and this plan at planning: *"a residual rule is the first thing to read"*, with three outcomes (residual rule / the provider refused the key / transient). | **MEASURED IN RUN 1, 2026-09-18, AND IT IS A FOURTH OUTCOME NONE OF THE THREE COVERS: the copy succeeds and the verb still exits 5.** `mc mirror` transferred the whole pass and printed its summary table (alpha 7.21 MiB in 18 s; beta 5.78 MiB in 18 s) and exited **1**, because **exactly one object per pass** failed with `net/http: HTTP/1.x transport connection broken: http: ContentLength=<n> with Body length 0` — the body read from R2 came back empty while its `ContentLength` was advertised. Three occurrences in the retained journal, one per failing run, always a small `.gz`: `…20260914-034912I/pg_data/base/16384/17551.gz` (928), `…20260916-033142I/…/17498.gz` (1856), `…20260918-033212I/…/1249_fsm.gz` (272). `bin/backup.py:690` raises `EXIT_STATE` on any non-zero copy, so the unit fails and `mirror-state.json` is not written. Alpha alternates in the journal — complete 09-13, failed 09-14, complete 09-15, failed 09-16, complete 09-17, failed 09-18; beta completed five days running and failed once, on 09-18. **The other three outcomes are excluded on evidence, not assumption**: the host reached the endpoint (`curl https://s3.eu-central-003.backblazeb2.com/` → 403, connect 0.033 s), no `rehearsal-in-progress.json` existed, and a `REJECT` rule would have broken every object to that endpoint rather than one of ~3,700 — both hand copies completed over exactly that path. No `401`, `403`, `InvalidAccessKeyId` or `SignatureDoesNotMatch` anywhere in the journal. | **Run 1 restored the state and Run 3 owes the repair, which is D1549's.** By hand at a TTY under `script(1)`: alpha exit 0, 3893 objects at `2026-09-18T16:35:42Z`; beta exit 0, 3446 objects at `2026-09-18T16:38:15Z`; both `mirror-state.json` written; both units `reset-failed`; `systemctl list-units --failed` now lists `cloud-init-hotplugd.service` alone; `systemctl is-system-running` still `degraded`, which is D1503 and not this product's. **No iptables rule was deleted and none was found to delete** — Sheet 0a's `grep -c` reading was never obtained in a form that separated *absent* from *could not read*, and it is not needed: the flake's own text excludes the hypothesis. | ADR 0195, and the reassuring outcome was not the one that had to be measured — *transient* was nearly right and materially wrong. The copy is transient at the object level and the product's treatment of it is not transient at all: it is a fold, and folding is what D1549 names. A plan that enumerates three outcomes has to be read as three outcomes it thought of, never as the outcome set. | 0188, 0193, 0195 |
| **D1547** | Stage plan §7: *"`deployment_convergence` — a redeploy declared; Session 30 or 31"*; `bin/session-28-check.sh:357`: *"`--redeploy-before-file`: opened before a redeploy: the generation and the sentinel row that must survive it."* | **The file's format is defined only by the proof that reads it**, `tests/deployment/test_session11_operations.py:355-376`: JSON with non-empty `sentinel_title` and `generation_id`; the proof then counts `app.notes WHERE title = '<sentinel_title>'` as root and expects **1**, and reads `/var/lib/agentic-postgres/secrets/<key>/active-secret-generation.json` expecting a **different** `generation_id` after the deploy. **No guide documents how the sentinel row is written** (`git grep -n "redeploy-before\|sentinel_title" docs/` finds nothing outside the gates' help). The flag has never been given (D1496's list). | **Run 6 owes the recipe** and writes it into Sheet A2 before the trip: read the proof whole, then `bin/api.sh --help` and `bin/dev-token.sh --help`, and write the exact commands that create one `app.notes` row with a unique title on alpha through the product's own surface (D1114) — or, if no product surface writes a note as an operator, as the cluster superuser through the new helper, saying so. The file is written by root to `/root/s30-redeploy-before.json` with `generation_id` read from `active-secret-generation.json` **before** the deploy. The row is swept after the sweep. | A flag never given is a proof never run; the fourteenth never-executed proof failed on first execution (D1508). Writing the recipe from the proof rather than from memory is the cheap half (D671). | — |
| **D1548** | This plan at planning: **"WSL's `sudo` has no `use_pty`"** (`grep -r use_pty /etc/sudoers /etc/sudoers.d/`: no hit), therefore *"without it the rig measures nothing"* and the rig must add it. | **WSL HAS `use_pty`, and so does the production host. The planning grep ran without `sudo` against a 0440 file and reported "no hit" from a read that could not read.** Rig 30a printed `use_pty configured: YES` on its **before-use-pty** run, i.e. before anything was added. The line is in `/etc/sudoers` itself, not `sudoers.d` — the distro default. On the production host the same is true and was printed during Run 1's sheet: `/etc/sudoers:Defaults   use_pty`. | **The before/after pair is void** — both rig 30a runs had `use_pty` — **and the rig's result stands regardless**, because the subject hung in both and the controls completed in both. The sudoers file was added and removed as planned and its absence re-read; `/etc/sudoers.d/` holds `README` alone on the workstation, and on the host the four expected files with no `apg-rig-30a` residue (verified over SSH after the operator ran the rig lines against the host by mistake). **D1551 records the host reading, which nobody had ever taken.** | Third instance in one run of a read that could not read being reported as an answer (with Sheet 0a's `grep -c` and D1542's assumed property). It is the reason ADR 0218's guard is an AST scan over the tree rather than a grep: a scan cannot return *absent* when it failed to look. | — |
| **D1549** | `services/backup-mirror/mirror.sh:36-39` and `bin/backup.py`'s `verb_mirror` docstring both state D1001 as the design: *"A pass may exit non-zero with objects behind and the next pass completes it (D1001); the exit code is the whole of what the verb reads."* `systemd/agentic-postgres-backup-mirror@.service:28-31` states the same intent: *"a pass that exits non-zero with objects behind is completed by the next pass (D1001), so a timeout here reads as one failed copy, not a lost mirror."* | **The code treats the case its own comments call normal as a hard failure, and the fold is operator-visible.** `bin/backup.py:688-695`: any non-zero `copy.returncode` raises `EXIT_STATE`, so (a) the verb exits 5, (b) the unit enters `failed` with no `Restart=`, (c) `systemctl is-system-running` reads `degraded`, (d) `mirror-state.json` is not written, and (e) `diagnosis.py:329-372` reports `WARN … the nightly copy has missed` once `MIRROR_STALE_AFTER_DAYS` (2) elapses — **while the mirror bucket is materially current**, one object behind out of ~3,700. Measured: D1546. An operator reading `list-units --failed`, the doctor, or the fleet inventory cannot distinguish *one object flaked and the next pass will take it* from *the mirror is broken*; only the journal's `mc: <ERROR>` line separates them, and `apg-diag`'s log allowlist does not cover this unit. **There are three outcomes — complete, partial, failed — and the verb reports two.** | **Run 3 owes an ADR and the repair; the ADR is written in Run 2 with the others.** The three candidates, to be decided there: (1) **one immediate retry pass in-process** before the verb judges — "the next pass completes it" made immediate, so a pass that is complete after the retry writes the record and exits 0, and `mirror-state.json` keeps meaning exactly what it means today; (2) **a record that distinguishes a complete copy from an attempt with N behind**, with `diagnosis.py` taught to read both — a record schema move and a doctor change; (3) **declare the present behaviour correct** and move the noise into the doctor's threshold, which leaves the failed unit and the `degraded` host. This plan recommends (1) and Run 2 decides. The proof is offline against a fake `compose_mirror` whose first pass returns 1 and whose second returns 0: the record is written, the verb exits 0, and the control is a fake whose both passes return 1 — the verb still exits 5 and writes nothing. **No change to `--remove`, to retention, or to the primary's path.** | CLAUDE.md §7's rule for the class produced most, and ADR 0195 in its exact words: a reader has three outcomes and the third is reported rather than folded. The comment that says *the exit code is the whole of what the verb reads* is the defect stated as a design — the exit code is one bit and the question has three answers. Also D1247's shape: a declared behaviour (D1001, in three files) with no reader that implements it is an unverified behaviour. | **(0220 or 0221, Run 2 assigns)** |
| **D1550** | D1540: *"**Measure (Run 2): does any passing test assert `compile` has no output option or writes no file?** … at planning: no hit in a test body"*, with the rule *"if Run 2's grep finds a passing test asserting the old design, ADR 0220 authorises the replacement; otherwise the header rewrite and this row are the record."* | **No test asserts it for `compile` — and a passing test asserts exactly that design for its SIBLING command, with a security reason and an ADR behind it.** `tests/contract/test_api_contract_command.py:217` `test_update_names_no_output_path` asserts `"--output" not in help_text` **and** `'"--output"' not in source` for `bin/api-contract.py --update`, with the docstring: *"An `--output` option would put the file's ownership in the privileged process, which is precisely what ADR 0050's 'it writes no source file' is for: the reviewer has to be able to edit and commit what came out."* `tests/contract/test_api_commands.py:103-107` refuses `--output` on `api.sh` among flags *"that a token could reach"*. `bin/mcp-contract.sh` requires no root and has no `require_root`. | **Run 4 may not add `--output` to `compile` without answering the ownership argument**, in the ADR or in the row. The two candidate answers, to be decided in Run 4: (a) `mcp-contract.sh compile` is never run privileged — shown by its lack of a root check and by every documented and tested invocation — so ADR 0050's reason does not reach it, and the header cites this row; or (b) it can be, and `--output` writes as the invoking user with the `PATH.tmp.<pid>` + rename confined to the target's directory, stated in the ADR. **ADR 0221 is reserved for Run 4** if it takes (b) or otherwise needs to reconcile the two commands; ADR 0220 went to D1549's mirror fold. | A grep that answers its literal question and stops is how a decided principle gets contradicted one command at a time. The planning grep asked about `compile` and the tree's answer about `--output` lives under `api-contract`. CLAUDE.md §7 rule 5: grep every reader of a decision before implementing it for one. | 0050, (0221) |
| **D1551** | Nothing. The production host's `sudo` configuration has never been read in any session plan; D972's mechanism (`use_pty` backgrounding the command) has been cited since 2026-09-04 without the setting being confirmed on the machine it matters on. | **The production host carries `Defaults use_pty` in `/etc/sudoers`** — read 2026-09-18 during Run 1's sheet: `/etc/sudoers:Defaults   use_pty`. It is Ubuntu's default and is not set by `provision-host.sh`. So **D972's mechanism is live on production by default**, and every one of the 39 call sites that inherits a terminal is exposed there, not only on a workstation that happens to be configured that way. | Recorded, and cited in ADR 0218's context as the reason the exec discipline is a production repair rather than a developer-ergonomics one. **Nothing is changed on the host**: the setting is correct and removing it would weaken `sudo`'s logging. Run 3's repair is what makes the setting harmless to this product. | The mechanism behind a defect class had been named in twelve rows across five sessions and never confirmed on the deployment. It was true — but it was true the way D930's and D957's premises were true, which is to say nobody had looked. | 0218 |
| **D1552** | This plan §0: *"**One local still shadows a module-level function**: `tests/deployment/test_session9_agent_writes.py:709`"*, and rig 30d's *Expected: **exactly one***. | **Five, not one — and the raw scan says fifty, of which forty-five are not the class.** Measured over `tests/**/*.py` by AST (module-level function and imported names; the function's own arguments excluded). Of 50 hits, **45 shadow a pytest FIXTURE**, which is not the class: a fixture is reached by declaring it as a parameter, never by calling its name, so a local of the same name in a test that does not declare it collides with nothing. **Five shadow a plain module-level helper**: `test_api_contract_command.py:620` (`merged`), `test_deployed_output.py:1361` (`published`), `test_project_agent_surface.py:155` (`tool`), `test_storage_client.py:433` (`adapter`), and `test_session9_agent_writes.py:709` (`refused`). **In none of the five is the helper called by name inside that function**, so all five are latent rather than live; `refused` at `:709` is rebound to an `api_call` response whose `.status` and `.body` are then read, over `def refused(result) -> bool` at `:91`. Zero currently-broken instances. | **Better than planned: the guard needs no exemption list.** Run 5 repairs all five by renaming the local, then `test_no_local_shadows_a_module_level_function` asserts **zero** over `tests/**/*.py`, with the fixture exclusion stated in the test and proved by its two controls (a synthetic shadow it must catch; a rebound fixture parameter and a differently-named local it must pass). The plan budgeted a frozen tuple; none is needed. | A scan whose first answer is 50 and whose right answer is 5 is a scan that had not yet been told what the class is. Reporting the 50 as the finding would have produced either a 45-entry exemption list or a guard nobody could keep green — D1493's shape. The discriminator (fixture versus plain helper) is a property of the definition, not of the failing instance, which is CLAUDE.md §7 rule 5. | — |
| **D1553** | This plan's Run 3 step 2: *"`bin/db.sh` and `bin/apg-diag.sh` also source and call it at the top of their `main` — **these two exec directly**, and closing stdin on the line (step 4) is the repair; the guard is the belt on the same two."* | **After step 4's repair those two commands cannot hang, so the guard would refuse shapes that work.** Rig 30a2 measured that the stop needs `-i` **and** a child that reads stdin. `db.sh`'s `status` and `identity` verbs and `apg-diag.sh`'s query now end `< /dev/null`, so their psql reads `/dev/null` and reaches end of file at once. Adding `refuse_mixed_terminal_shape` to them would refuse `sudo bin/db.sh status --project alpha-dev > out.txt` at a terminal — a correct invocation with no failure mode left. That is D1538's own finding (*a guard everywhere refuses working shapes*) and ADR 0218 forbids it in as many words: the refusal *"is **not** extended to commands whose children cannot read the terminal"*. | **Step 4 applied; step 2's `db.sh`/`apg-diag.sh` half NOT applied.** The guard is sourced and called by `deploy.sh` alone. `-i` is **kept** on all four shell sites, because `bin/db.sh:181-183` records a measurement — without `-i` stdin is not forwarded, psql reads nothing and exits 0 having executed nothing, a silent success indistinguishable from a real one — so the repair is to control what `-i` forwards, not to remove it. `db.sh`'s comment now says so. The shell half is guarded by `test_every_shell_docker_exec_closes_or_supplies_stdin`, which scans `bin/*.sh` **and** `deploy.sh` rather than the three named commands the older scan reads. | The plan was written before Run 2 measured the class, and its step 2 carries the pre-measurement belief that the guard is the repair. Applying both halves would have shipped a refusal for a hang that no longer exists — the shape CLAUDE.md §6 forbids silently reconciling. | **0218** |
| **D1554** | This plan §0 and D1537: *"**Thirty-nine call sites** build a `docker exec` argv: four in shell… thirty-two in eleven `bin/*.py`… three in two `src/` modules… 39 sites, 15 files"*, and Run 3's heading *"thirty-nine sites"*. | **The AST scan counts 27, of which 14 were the hang class, and it is counting a different thing.** D1537 counted places that BUILD a docker argv, including those handed to an intermediary runner. The scan counts `subprocess.*` calls whose argv reaches `docker` or `compose.sh`, which is what the rule is about: a site that builds an argv and passes it to a runner which closes stdin cannot hang. Before Run 3: **27 direct sites, 14 unguarded, 0 in a helper.** The 14 span **nine files, five of which this plan never named** — `bin/auth-admin.py:246`, `bin/postgres-bootstrap.py:86` and `:900`, `bin/rotate-signing-key.py:218` and `:254`, `bin/storage-admin.py:165`, `src/agentic_postgres/access_broker.py:343`. **`rotate-signing-key.py` is the command Run 8 executes.** A second rule (a pass-through runner whose argv is its own parameter) found `deploy-project.py:185`'s generic `run()` with stdin open, which D1538 predicted, and confirmed `doctor.py:91`, `fleet.py:72`, `restore.py:104` and `rehearse.py:85` already closed theirs. | **After Run 3: 0 unguarded outside the helper**, measured by the same scan that becomes the guard. Four true `docker exec` sites go through `container_exec.run()`; `migrate.py`'s compose run goes through `compose_run()`; eight `docker ps`/`inspect` reads and two generic runners take `stdin=subprocess.DEVNULL` (those cannot hang — neither reads stdin — but an inherited terminal on a call nobody re-reads is how the next one arrives). The remaining pass-through runners are `git()` and tool-version readers, outside ADR 0218's scope and named here rather than silently excluded. | A count carried from a plan into a test is a count nobody measures twice (D1116's shape). The scan derives it, and it found five files the hand inventory missed — including the one Run 8 runs against production. | **0218** |
| **D1555** | This plan §2: five requirements *"all `target_session: 30`"*, listed as this session's registry additions; and Run 4's step 2: *"its registry node id moved in the same commit"*. | **A `target_session: 30` entry cannot enter the registry before Run 6.** `test_acceptance_registry.py:163` asserts `1 <= target_session <= CURRENT_SESSION`, which is **28** until the bump, and moving `CURRENT_SESSION` is all-or-nothing (D690). Run 4 added `REL-READ-002` and `CAP-COMPILE-001`, regenerated the matrix, and three registry proofs went red on the session bound. §2 already puts the additions in Run 6; Run 4's own text reached for them early. | **The node-id REPLACEMENT stays in Run 4** — D1119 requires it in the same commit as the rename and `REL-READ-001`'s `target_session` is 28 — **and the two new entries are deferred to Run 6**, parked verbatim in §2 so that run pastes rather than rewrites them. The proofs exist and pass now; only their registration waits. Run 6 pastes, then `python bin/render-acceptance-matrix.py --write`. | A requirement is registered when the session that owns it is current, and the bump is the one edit that cannot be split. Landing the entries early would have meant either a red suite for three runs or moving `CURRENT_SESSION` outside the run that owns it. | — |
| **D1556** | This plan §2's proposed test for `REL-READ-002`: *"`--ref HEAD` → the same bytes as no argument"*, and ADR 0219's decision 5: *"the first block's label reads `ref` when one was given"*. | **The two cannot both hold, and the label is the point.** `--ref HEAD` and no argument name the same commit and report the same facts, but the first block reads `Where the ref HEAD stands` against `Where HEAD stands`, and `tags on it` against `tags on HEAD`. D1513's whole complaint is that a reading which does not name its subject cannot be checked afterwards; a `--ref` that printed nothing to say it was given would reintroduce exactly that. | **The label wins.** `test_the_reading_names_the_ref_it_read` asserts `the ref HEAD` appears with a ref and does not without one; the no-argument form is unchanged byte for byte, which is what ADR 0219 actually promises. The plan's phrase *the same bytes as no argument* is replaced by *the same facts*. **A second reading of `unchanged` was also wrong**: anchoring the ranges to the resolved SHA left the output identical and changed the ARGV, and `test_the_command_finds_the_tag_that_carries_the_version_not_the_one_on_head` — which drives `observe()` through a fake git keyed on argument tuples — went red. With no ref the anchor is the literal `HEAD`, and `describe`/`log` take the ref only when there is one. | Two proposed assertions in one row, both true-sounding, both slightly wrong about what *unchanged* covers. The fake-git test caught the second within a minute of the change; nothing but reading caught the first. | **0219** |
| **D1557** | D1541 (rewritten from D1536): *"Three edits in Run 5: both *31 released* → **33**, `docs/project-isolation.md:86-87` *fifteen parsed semantic fields plus all thirteen derived role names* → **eighteen JSON pointers***". | **None of the three is what the row describes.** (a) Both *31 released* occurrences are **measurement CONDITIONS**, not claims about today: `capacity.py:260` is the `conditions` tuple of the `apg dev up` timing and `dev-environment.md:177` is that measurement's prose. Rewriting either would state that a sample was taken against a tree it was not. (b) The arithmetic is wrong in **both** terms — the tree holds **33 released and 3** in the example set, so a re-run applies **36**, not 33. (c) `docs/capacity-envelope.md` is **generated** and says *Do not edit by hand*; the row implies editing it directly, which the next `render-capacity-envelope.py --write` would undo. (d) The isolation sentence is wrong in **both** halves: `ISOLATED_FIELDS` is **18** pointers and a rendered document carries **14** roles (measured in both fixtures), not fifteen and thirteen. (e) **`evidence.py:271`'s own docstring carries the stale thirteen** — a stale number in the code, which is the one place nobody was grepping. | The two measurement conditions are **annotated, never rewritten**: each now says what the counts were when sampled and what the tree holds now. `capacity.py` is the edit and the envelope is regenerated from it. `docs/project-isolation.md:86` says *eighteen* and *fourteen* and **names `evidence.ISOLATED_FIELDS`** rather than repeating a count, `:96` says fourteen, and `evidence.py:271` is corrected. | D954's direction, one turn further: a number in prose that a program stopped agreeing with is found by grepping the OLD number — and then each hit has to be **read**, because two of them were records of a measurement and one was a generated artefact. A row that says *change 31 to 33 in two places* is a row that has not opened the files. | — |
| **D1558** | Run 5 step 2: *"the local `refused` → `answer` (and its three uses in the two asserts)"* — a rename described as bounded by the lines the plan had read. | **One of the five renames had a reader twenty lines out of view, and it hung the targeted run for ten minutes.** `test_storage_client.py`'s `test_a_cancelled_caller_does_not_leak_its_permit` binds a `Blocking` stub whose `head_object` **busy-waits** on `self.release`; the line that sets it, `adapter.release = True`, sits twenty lines below the binding inside a nested `async def`. Renaming the binding to `blocking` left that line naming a variable that no longer existed, so the loop never ended: pytest sat in state `Sl` with no child process, no container running and no output for 535 s until a `timeout` would have killed it. | Repaired; the module runs in **0.41 s**. Every one of the five renames was then re-grepped over its whole module rather than over the lines on screen, and the remaining `adapter` hits are the module-level helper at `:66` and its legitimate callers — which is the function that was being shadowed, so the rename is complete and correct. | **D979, broken by the executor in the act of applying it.** The rule is *grep every reader before repairing a name*, and the repair here was itself a renaming. A shadow repair is exactly the shape that hides a reader, because the name being renamed is one the module uses for something else. A hang with no output and no child process is also a reminder that a targeted run's silence is not progress. | — |
| **D1559** | §2's `CAP-COMPILE-001` row names `test_session12_documented_path.py::test_no_documented_compile_line_redirects_its_output` as one of its node ids — *(new: no line matching `mcp-contract.sh compile` in `CURRENT_PATH_DOCUMENTS` is followed by a `>` on it or on its continuation)*. | **Run 4 repaired both documented lines and wrote no guard.** `README.md:551` and `docs/new-team-member.md:272` both pass `--output` now, and `git grep -n redirect tests/contract/test_session12_documented_path.py` finds nothing: the proof was proposed and never written. Registering the requirement as §2 words it would have registered a clause whose reader does not exist — a repair made in prose, held by nothing, in the documentation this project has repaired the same way twice (D1359 is itself the second occurrence). | **Written here, with its control, before the entry was registered.** The scan joins backslash continuations, because both lines are written over two physical lines and the redirect was on the SECOND — a scan reading physical lines would find no `>` on the line carrying the command and report both pages clean. A redirection is matched as an OPERATOR (`(?<![\w<])>>?\s`) and not as a character: both lines write `projects/<slug>/contracts/…`, and the first version of the control failed on its own placeholder, which is what an anti-vacuity control is for. Battery **4/4 killed**: the README's redirect restored, the guide's `--output` removed, the continuation joining disabled, and the command regex made to match nothing — each with `test_the_readme_sections_are_in_the_order_an_adopter_walks` green beside it as the control the mutations cannot reach. | D816 and D1247's shape in a plan rather than in the tree: a requirement's TEXT is a promise, and the run that lands the requirement is the last moment anybody compares it against what exists. A node id proposed in a plan is not a proof; it is a note that one is owed. | — |
| **D1560** | §2's `OPS-EXEC-001` row names `test_printed_commands.py::test_a_deploy_with_a_terminal_on_stdin_and_redirected_output_is_refused` *(the existing D972 proof, `:107-152`, unchanged)* among its node ids, together with `test_cli_contract.py::test_every_command_in_bin_is_covered_by_this_module`. | **`tests/contract/test_printed_commands.py` is `p1`.** Its `pytestmark` is `[contract, p1]`, and the sweep that REPORTS every offline claim runs `-m "p0 and not future and not live_host and not external"`. Registering a p1 node id under a claim declared offline turns `test_every_offline_claims_proof_is_swept_by_the_gate_that_reports_it` red — which is **D1242 exactly**, the guard written because a P0 requirement's proof sat in a p1 module and no sweep collected it. The proof is real and it passes; what it is not is a node id an offline half can carry. | **Not registered, and the clause is not dropped.** `deploy.sh` refusing the mixed terminal shape is proved inside `OPS-EXEC-001` by two p0 proofs in `test_container_exec.py` — `test_the_shell_library_and_the_module_print_the_same_sentence` asserts the refusal's bytes are identical on both sides of the move, and `test_the_guard_refuses_a_terminal_on_stdout_with_only_stderr_redirected` drives the sourced guard itself. The D972 proof stays where it is, unchanged and still run by CI. The two general guards are also left out: neither is about this requirement, and a requirement that claims a suite-wide scan as its own proof reports on something it does not own. | A plan may name a node id; only the tree knows what MARK it carries, and the mark decides which sweep can report it. `--collect-only` answers *does this exist*; `--collect-only -m <the gate's selector>` answers *will the half that reports it see it*, and they are different questions (D1240, D1242). | — |
| **D1561** | §5 Run 6: *"`bin/upgrade.sh plan … --json` → expect `bump minor`, `requires patch` or `minor`, `OK`, `reasons []`, **one leaf** (`template_version`). A `major` is §9's stop."* | **Measured, and the answer is `patch`.** Rendering `project.example.yaml` from `8c61309` in a throwaway worktree and from this bump: `bump minor`, `requires patch`, `verdict ok`, `reasons []`, `changes []`, `operator_digests_moved []`, **one leaf, `template_version`, `1.7.0 -> 1.8.0`**. No stop condition is met. But the reason `requires` is `patch` is worth more than the verdict: **ADR 0162's table has no row for a command gaining an OPTION.** Its eight rows price a migration, an API operation, a capability, a secret, a document schema and an operator manifest — every one of them something a rendered document shows — and `release-reading --ref` and `compile --output` show up in no document at all. By the table this release is *implementation only*, which is a **patch**. | **Reported, not reconciled.** `VERSION` moves to `1.8.0` as the plan fixes it: bumping ABOVE what is required is always permitted, and two new options an operator can type is new functionality, which is what a minor means everywhere outside this table. The number is therefore a **choice** and the plan's Done says so, rather than a computation the product performed. No ADR is written: 0162 decides what an upgrade COSTS AN OPERATOR, and the answer here — nothing — is correct. What is missing is a row saying that a command gaining an option is priced by hand, and §10 carries it for the session that next wants one. | The command answered the question it was asked, and the question was not the one the version number was about. `requires` is a floor, not a verdict on the release — and a run that reads a floor as agreement has folded two readings into one (ADR 0195). | 0162 |
| **D1562** | §10: *"`--rotated-from-file` is accepted by the gate and undocumented in its usage block … The 30 gate inherits it; **Session 31's derivation adds the line**."* | **True, and the deferral was made without knowing which run would hold the file open.** `bin/session-30-check.sh:655` accepts the flag, `:1472` exports `APG_ROTATED_FROM_FILE` from it, and `:1412` requires the file to exist — and neither the synopsis nor the option list names it. Run 6 rewrote that usage block **whole**, which is the one act in this session that reads every line of it. | **Answered here, one session early.** The synopsis gains `[--rotated-from-file FILE]` and the option list gains its paragraph, which says what it admits and that every gate since Session 5 accepted it while no `--help` named it. Session 31's §10 row is closed rather than inherited. | A deferral is a bet on when the cost will be lowest, and the cost of this one was lowest at the exact moment the deferring plan did not model: the rewrite it ordered in the same run. **A flag the parser takes and `--help` does not name is a declaration with no reader** (D816, D1247) in the direction that costs a claim — an operator who HAS performed that rotation cannot learn the gate would read their file. | — |
| **D1563** | Run 6's targeted list — 35 contract modules, derived from the tree: every module that reads `CURRENT_SESSION` or `template_version`, every module that reads the registry or the claim table, and every module this run edited. **1986 passed.** | **`bin/session-01-check.sh` on the committed tree exited 1**: `test_scope_vocabulary.py::test_no_data_scope_literal_survives_outside_the_schema_and_the_example_manifest`, on `bin/session-30-check.sh:341` — the sentence in the derived gate's `--mode host` paragraph naming the scope the Studio stranger is registered with. **The scan strips lines beginning with `#` from a `.sh` file, and it is right to**: a shell script's prose is its comments. A gate's usage block is not comments — it is a `cat <<'USAGE'` heredoc, so every line of it is a plain line of the script. The same sentence sits four lines from the top of the header as a `#` comment and is correctly ignored there. No targeted list derived from this diff would have named `test_scope_vocabulary`: nothing in the diff is about scopes. | **Reworded, not exempted.** The paragraph now says the stranger is registered with *a real read scope on the relation rather than an empty scope set*, which is what the sentence was about; naming the scope added nothing a reader of a gate's `--help` needs. `shellcheck -x` and `bash -n` clean after; the gate re-run on the repaired tree. | **D1486 exactly, and the second time this session** — Run 3's `test_fleet` docstring was the first. A per-run targeted list cannot see a caller the diff does not touch; the gate can. It is also D277's inverse: every scan over a shell script that strips comments to avoid reading prose will READ the one block of prose a gate prints about itself, and a derivation that rewrites that block whole is the act most likely to put something in it. | — |
| **D1564** | Run 3's *Done*: the D972 refusal moved into `bin/lib/tty-guard.sh`, sourced by `deploy.sh:27`, with the message bytes asserted identical on both sides; `bin/session-01-check.sh` clean at that run's close. | **`bin/session-30-check.sh --mode offline` exited 1 at STEP 1**, before any claim was computed: `shellcheck deploy.sh bin/*.sh libexec/*` does not hold the sourced library among its inputs, so it emits `SC1091 (info): Not following: bin/lib/tty-guard.sh was not specified as input` and **exits 1** — an info-level finding is still a non-zero exit, and every gate runs under `set -e`. Measured both ways in one rig: the unrepaired form exits **1** with that message, the form carrying `bin/lib/*.sh` exits **0** with **0 bytes** of output. **Run 3 repaired ONE caller of twenty-six.** `grep -n 'shellcheck deploy.sh' bin/session-*-check.sh` returns 26 lines: `session-01-check.sh:118` carries `bin/lib/*.sh`, and **sessions 02–28 — all twenty-four of the remaining gates — do not**. Every one of them fails at step 1 today, on a checkout where nothing is wrong. | **Repaired in this session's gate, which is the one that has to pass**, with the reason in a comment beside it. The other twenty-four are **named and not edited**: each is the released artefact of the session that owns it, nothing in this run re-runs one, and silently rewriting twenty-four gates to make a number look better is the shape this project refuses. §10 carries it, and it is the operator's call whether a mechanical one-line sweep across them is worth taking. | **§7's question 5, and the largest instance this project has recorded**: *when a decision is implemented, which of its callers got it?* Run 3 greped the readers of the moved NAME and the moved TEXT, as D979 and D1187 require, and the caller it missed reads neither — it is a **glob** that silently stopped covering a directory the release gained. `bin/session-01-check.sh` was repaired because Run 3 ran it; the other twenty-five were not run, so nothing said anything. A gate nobody runs is a caller nobody greps. | — |

---

## 2. What the session adds to `tests/acceptance-registry.yaml`

**Five requirements, five claims, all `target_session: 30`, all P0.** Every
requirement belongs to a claim (D697); a new requirement gets a claim of its
own and is never joined into an older one (D1150, ADR 0089). **Node ids below
are proposed; Run 6 writes what the runs actually wrote, read out of the tree
with `pytest --collect-only -q`** (D1236). `CAP` and `EVD` are existing
families (`test_acceptance_registry.py:79`); no prefix is added.

| Requirement | What it states | Offline node ids (proposed) | Live half |
|---|---|---|---|
| `OPS-EXEC-001` | Every `docker exec` and every `compose.sh run` the product performs is built by one function and run with stdin closed unless input is supplied, in which case `-i` is passed and the input is fed; no `subprocess` call under `bin/` or `src/` runs `docker` or `compose.sh` with an inherited stdin; `deploy.sh` refuses the mixed terminal shape with the sentence it has refused it with since D972, through a shell function it sources; the two shell commands that exec directly close stdin on the line | `test_container_exec.py::test_the_argv_carries_dash_i_exactly_when_input_is_given`, `::test_stdin_is_closed_when_no_input_is_given`, `::test_input_is_fed_and_reaches_the_child`, `::test_a_tty_is_never_requested_by_run`, `::test_the_scan_finds_no_docker_or_compose_subprocess_outside_the_helper`, `::test_the_scan_finds_the_helpers_own_call` (control), `::test_the_scan_catches_a_synthetic_inherited_stdin` (control), `test_printed_commands.py::test_a_deploy_with_a_terminal_on_stdin_and_redirected_output_is_refused` (the existing D972 proof, `:107-152`, unchanged), `test_cli_contract.py::test_every_command_in_bin_is_covered_by_this_module`, `test_database_commands.py::test_docker_exec_forwards_stdin` (existing), `test_database_commands.py::test_every_shell_docker_exec_closes_or_supplies_stdin` | — (offline claim `exec_discipline`) |
| `REL-READ-002` | `apg release-reading` takes exactly one option, `--ref REF`, defaulting to `HEAD`; the reading is of the resolved commit and its first block names the ref it read; an unresolvable ref exits 2 naming it; any other argument exits 2; `--ref HEAD` prints the same bytes as no argument | `test_release_reading.py::test_the_command_takes_exactly_one_option_and_refuses_the_rest` (replaces `test_the_command_takes_no_arguments_and_says_so`, ADR 0219), `::test_the_reading_names_the_ref_it_read`, `::test_a_ref_reads_the_tag_target_and_not_the_tip` (a throwaway repository: two commits, VERSION moved at the first, `--ref` at the first reports `commits after it 0` while `HEAD` reports 1), `::test_an_unresolvable_ref_is_refused_naming_it`, `::test_help_names_the_option` | — (offline claim `release_reading_ref`) |
| `CAP-COMPILE-001` | `bin/mcp-contract.sh compile --output PATH` writes the candidate to PATH only after the compile succeeded, atomically, and leaves PATH absent and no temporary file behind when the compile is refused; without `--output` it streams to stdout unchanged; `check` and `lock` take no `--output`; both documented compile lines use `--output` and no documented compile line redirects with `>` | `test_capability_compiler.py::test_a_refused_compile_leaves_no_file_and_no_temporary` (the adopter's own shape: a project naming `mcp.capabilities` with no snapshot → exit 5, PATH absent), `::test_a_successful_compile_writes_the_bytes_it_would_have_streamed` (control: `--output` bytes == stdout bytes), `::test_check_and_lock_refuse_dash_dash_output`, `test_documentation_index.py::test_every_flag_the_readme_shows_appears_in_that_commands_usage` (existing; now covers `--output`), `test_session12_documented_path.py::test_no_documented_compile_line_redirects_its_output` (new: no line matching `mcp-contract.sh compile` in `CURRENT_PATH_DOCUMENTS` is followed by a `>` on it or on its continuation) | — (offline claim `contract_compile_output`) |
| `EVD-SHAPE-001` | No function under `tests/` binds a local whose name is a module-level function or an imported name of the same module (fixture parameters excepted, by construction); every `test_` function under `tests/deployment/` is a node id of some registry entry, or is named in a frozen list the guard compares for equality; each guard is proved against a synthetic module it must catch and one it must pass | `test_suite_shape.py::test_no_local_shadows_a_module_level_function`, `::test_the_shadow_scan_catches_a_synthetic_shadow` (control), `::test_the_shadow_scan_passes_a_differently_named_local` (control), `test_deployment_suite_shape.py::test_every_deployment_proof_is_a_node_id_of_some_requirement`, `::test_the_registration_scan_catches_a_synthetic_orphan` (control) | — (offline claim `suite_shape`) |
| `STU-QUERY-002` | On the deployment, Studio's query view forwarded as a human returns that human's rows and none of a second registered subject's, where the second subject's row is proved to exist by reading it as that subject through the same surface | — | `test_session24_studio.py::test_the_query_view_shows_the_human_their_own_rows_and_not_anothers` (host claim `studio_tenant_read`) |

**Claims** (`src/agentic_postgres/evidence_claims.py` `CLAIMS`, each dated
30 in the comment): `exec_discipline: ("OPS-EXEC-001",)`,
`release_reading_ref: ("REL-READ-002",)`, `contract_compile_output:
("CAP-COMPILE-001",)`, `suite_shape: ("EVD-SHAPE-001",)` — **all four in
`OFFLINE_CLAIMS`**, with the per-session assertion (D1237: assert THESE
four are in the set; never the set's size). `studio_tenant_read:
("STU-QUERY-002",)` is a **host** claim and is deliberately not declared
(D1543). `tests/contract/test_evidence_claims.py`'s session table gains five
rows at 30.

**`REL-READ-001` is edited, not extended**: its node id
`test_the_command_takes_no_arguments_and_says_so` is replaced by
`test_the_command_takes_exactly_one_option_and_refuses_the_rest` (D1539, ADR
0219). No other existing entry moves.

**Run 4 wrote two of these and Run 6 lands them** (D1555). `target_session:
30` cannot enter the registry while `CURRENT_SESSION` is 28 —
`test_every_entry_has_complete_metadata` asserts `target_session <=
CURRENT_SESSION`, and moving it is all-or-nothing (D690). Run 4 built the
proofs and they pass; the entries below are their final text, to be pasted
into `tests/acceptance-registry.yaml` in Run 6's bump commit followed by
`python bin/render-acceptance-matrix.py --write`.

```yaml
- id: REL-READ-002
  priority: P0
  target_session: 30
  test_nodeids:
    - tests/contract/test_release_reading.py::test_an_unresolvable_ref_is_refused_naming_it
    - tests/contract/test_release_reading.py::test_the_reading_names_the_ref_it_read
    - tests/contract/test_release_reading.py::test_a_ref_reads_the_tag_target_and_not_the_tip
    - tests/contract/test_release_reading.py::test_help_names_the_option
  description: >-
    `apg release-reading` takes exactly one option, `--ref REF`, defaulting to
    `HEAD` (ADR 0219). The reading is of the commit that ref resolves to --
    including its `VERSION`, its released lock and its ADR count, so the
    reading describes one commit and never a mixture of a ref's history with
    the working tree's files. The first block names the ref it read, so a
    transcript says which commit was measured. A ref that names no commit is
    refused with exit 2 naming it, before any other read is taken; every other
    argument is still exit 2. The deploy, the sweep and the tag land on one
    commit in that order (D1425), so the commit a tag goes on is behind `HEAD`
    on every trip and a reading of `HEAD` is a reading of the wrong commit.

- id: CAP-COMPILE-001
  priority: P0
  target_session: 30
  test_nodeids:
    - tests/contract/test_capability_compiler.py::test_a_successful_compile_writes_the_bytes_it_would_have_streamed
    - tests/contract/test_capability_compiler.py::test_a_refused_compile_leaves_no_file_and_no_temporary
    - tests/contract/test_capability_compiler.py::test_check_and_lock_refuse_dash_dash_output
  description: >-
    `bin/mcp-contract.sh compile --output PATH` writes the candidate to PATH
    only after the compile succeeded, atomically, and leaves PATH absent with
    no temporary behind when the compile is refused. Without `--output` it
    streams to stdout unchanged, and the bytes are the same either way.
    `check` and `lock` refuse the flag: `check` writes nothing by design (ADR
    0050) and `lock` writes through `--outputs`, and a second way to produce a
    contract would be the way nothing audits. A shell `>` truncates its target
    before the command runs, so the documented compile lines used to leave a
    0-byte contract on every refusal and told the reader to delete it (D1359,
    D1540). ADR 0050's reason for refusing an output path elsewhere -- that it
    would put the file's ownership in a privileged process -- does not reach
    this command, which needs no root (D1550).
```

**`REL-READ-001`'s node id was moved in Run 4**, not deferred: D1119 requires
it in the same commit as the rename, and its `target_session` is 28.

**No new gate variable.** `studio_tenant_read`'s proof reads `APG_LIVE_HOST`
and `APG_PROJECT_A_OUTPUTS`, which the module already declares (`:59-64`).
`deployment_convergence` moves on the trip through the existing
`--redeploy-before-file` (D1547).

---

## 4. Irreversible operations

| Operation | Where | What makes it safe |
|---|---|---|
| A residual iptables rule deleted on the host, if Run 1 finds one | Run 1 | Read first with `iptables -S DOCKER-USER`; deleted only by the exact `-D` form of a rule carrying `apg-rehearsal-` in its comment; the copy re-run after and its exit read; the deletion is what the rehearsal's own reversal does (`rehearsal.py:485-577`) |
| `Defaults use_pty` added to WSL's sudoers for rig 30a | Run 2 | One file, `/etc/sudoers.d/apg-rig-30a`, removed at the rig's end and its absence re-read; the workstation only |
| `deploy.sh:260`'s refusal moved into `bin/lib/tty-guard.sh` | Run 3 | Moved by copy, the deleted lines and the added lines `diff`ed against each other in the Done; the existing D972 proof in `test_deploy_command.py` runs unchanged before and after; the message's bytes are asserted equal |
| Thirty-nine exec sites rewritten through one helper | Run 3 | The AST scan's count before (39 outside the helper) and after (0 outside, ≥1 inside); every module that moved runs whole; the seven `psql()`/`docker()` helpers become one-line wrappers or are deleted with their callers re-pointed, each with a grep of the name and of the moved text (D979, D1187) |
| A passing contract test replaced (`release-reading` takes no arguments) | Run 4 | ADR 0219 first; the replacement is stricter (five refusals where there was one); `test_acceptance_registry` run (D1119); the registry node id moved in the same commit |
| `bin/mcp-contract.sh`'s stated design changed | Run 4 | The header rewritten with the reason and D1540 cited; `lock` and `check` untouched; the proof that a refusal leaves no file runs against the adopter's own refusal (exit 5), not a synthetic one |
| A fixture on a live proof edited (`ARRAY['notes:read']`) | Run 5 | The proof cannot run offline; `pytest --setup-plan` with the variables set before the trip (D671); the sweep is where it first executes and §7 says so |
| `CURRENT_SESSION` 28 → 30; `VERSION` 1.7.0 → 1.8.0 | Run 6 | All-or-nothing (D690); every `target_session: 30` node id in the same commit; the client regenerated (D1238); both release pages gain a `1.8.0` row (ADR 0209); `upgrade plan` on the host confirms or stops |
| `bin/session-30-check.sh` | Run 6 | Derived from 28's by diff (D1482); `SHELL_COMMANDS` gains it and `chmod 755` before `git add` (D1014, D1188); `test_session_thirty_gate_modes.py` copied from twenty_eight's |
| Deploy `--through-session 30` on alpha, then beta | Run 7 | `upgrade plan` OK first (§9); alpha first; unredirected at a terminal under `script(1)`; the ledgers read after (D941) and expected **unchanged** (33, 35 — no migration); ADR 0155 recreates nothing whose mount did not move — read the container ages |
| One sentinel row written on alpha before the redeploy | Run 7 | A unique title carrying `s30`; deleted after the sweep by the same path that wrote it |
| Tag `1.8.0` on the deployed commit | Run 7 | After the sweep is written and the merge exits 0 or 5-for-the-expected-reasons only (§7); `release-reading --ref <that commit>` first — its first real use; `git ls-tree` of both release pages after |
| The signing-key rotation, alpha then beta | Run 8 | Appendix R verbatim; step 0.4's pid pre-flight before the window; `promote` refuses at exit 6 while any verifier is behind; `abandon` available until `promote`; no sweep inside the window; the other three rotations are not on the sheet (D1510) |

---

## 5. Build order, run by run

Each offline run ends with: `ruff format && ruff check` (its **exit code**
printed), the targeted modules (named, each checked for existence — D1104),
derived documents regenerated where a generator's input moved, `chmod 755
bin/*.sh bin/*.py deploy.sh`, one commit with a message written to a file
and passed with `-F`, a push, and **that commit's CI verdict read by full
SHA with three buckets** (D1059) — for code commits only; a documentation-
only commit reads no verdict. A run that writes a test runs its battery
(appendix). Mark the run **Done.** with what it measured. **A targeted list
is derived from the tree** (D1146, D1149, D1184, D1187): a run that moves a
definition greps every reader of the name AND of the distinctive text and
runs every module found, whole.

**Docker is required for Runs 2, 3 and 6** (rigs 30a/30b, the exec proofs
that run a real container, the gate). **Root over SSH is required for Runs 1,
7 and 8** and is typed by the operator. **No network is required by Runs
2–6** beyond what the tree already pins.

### Run 1 — the mirror, diagnosed with root, before anything else

**Read first:** `services/backup-mirror/mirror.sh` whole (49 lines: the
copy is `exec mc mirror --overwrite --remove source/<bucket> mirror/<bucket>`,
exits are `mc`'s own; `3` an empty secret, `6` not enabled, `2` an empty
identifier); `systemd/agentic-postgres-backup-mirror@.service` and `.timer`
(`04:30`, `RandomizedDelaySec=20m`, `Restart=no`, `ExecStart=/usr/local/
libexec/agentic-postgres/project %i backup-mirror` → `libexec/project-
launcher:127-129` → `bin/backup.sh --outputs /etc/agentic-postgres/projects/
<key>/outputs.json mirror`); `bin/backup.py:616-700` (the copy runs
`bin/compose.sh <rendered> --runtime --profile mirror run --rm backup-mirror
copy`; the record `/etc/agentic-postgres/projects/<key>/mirror-state.json` is
written only after exit 0 and a listing that parses); `src/agentic_postgres/
diagnosis.py:329-372` (the doctor's five outcomes for the mirror);
`src/agentic_postgres/rehearsal.py:485-577` (the rule the WAL scenario
inserts and deletes by comment); D1501 (a `sudo` product command under a pipe
stops — **`backup.sh` is the one that stopped**, so Sheet 0 uses `script(1)`
and nothing after any `sudo` line); D1506 (the outputs path is absolute and
one of exactly two files).

**Sheet 0 is in the appendix.** The agent's part, over SSH as `op`, before
the sheet: `ssh -i ~/.ssh/agentic_postgres_ed25519 op@62.238.99.122
'systemctl list-units --failed --no-pager; systemctl list-timers
"agentic-postgres-backup-mirror@*" --no-pager'` (no root needed for either),
recorded. Then the sheet, one outcome at a time.

**The three outcomes, and what each one does next:**

1. **A residual `apg-rehearsal-…` rule in `DOCKER-USER`** — the copy fails
   with a connection refused/reset to the B2 endpoint from the backup
   network while the host reaches it (`curl -sS -o /dev/null -w '%{http_code}'
   https://<BACKUP_MIRROR_ENDPOINT>/` as `op` returns a status). The
   operator deletes the rule by its exact printed spec (`iptables -D
   DOCKER-USER …` with the same match, or `-D DOCKER-USER <n>` by the
   number `iptables -L DOCKER-USER --line-numbers` prints), re-runs the copy,
   reads exit 0 and `mirror-state.json`'s new `last_copied_at`, then
   `systemctl reset-failed` both units. **Then Run 3 owes a product repair**:
   read `rehearsal.py`'s reversal path for the branch that can leave the
   rule (an exception between insert and delete; a delete that matched
   zero rules and returned 0), write the proof that reproduces it in
   `tests/contract/test_rehearsal.py` (a fake `iptables` that records
   calls), repair, and rewrite D1546 with the rule's text. If the leak is
   in the gate's `-k` re-runs rather than the module (a sweep killed
   between insert and delete), the repair is a `trap` in the gate's
   rehearsal step and the row says so.
2. **The provider refused the credential** — `mc`'s line carries `401`,
   `403`, `InvalidAccessKeyId`, `SignatureDoesNotMatch` or *account*. That is
   the owner's, at Backblaze: the key's validity and the bucket's
   lifecycle are read in the B2 console by the operator; a replacement is
   `rotate_by_replacement: true` in `secrets.required.yaml:962-1012` — a
   provider edit at `/backup` plus a redeploy — and it is **not bundled
   into this session's sheets** (D1510); it is a row and a §10 item with
   the exact secret names (`APG_MIRROR_S3_ACCESS_KEY_ID`,
   `APG_MIRROR_S3_SECRET_ACCESS_KEY`).
3. **Transient** — the copy by hand exits 0 with no change made. Recorded
   with the journal's error line from 2026-09-18; `reset-failed` both units;
   the next timer is the control (read `mirror-state.json` on trip day).

**Whichever it is, `systemctl is-system-running` still reads `degraded`**
because `cloud-init-hotplugd` fails at every boot (D1503). That is not this
product's and the sheet says so beside the reading.

**Done.** _(Run 1, 2026-09-18, ~35 minutes. **The mirror was never broken; the
verb's report of it was.**)_

**What the journal said.** Both units failed with `status=5/NOTINSTALLED` —
exit 5, which is `bin/backup.py`'s own `EXIT_STATE`, not `mc`'s. The message
above each failure was `backup: the mirror copy exited 1; the copy record was
not written and the next pass completes what this one left behind (D1001).`
Below it, in every failing pass, `mc`'s own line, verbatim and the same shape
each time:

```
mc: <ERROR> Failed to copy `https://<r2 account>.r2.cloudflarestorage.com/apg-alpha-dev-backup/pgbackrest/alpha-dev/backup/alpha-dev/20260913-021652F_20260918-033212I/pg_data/base/16384/1249_fsm.gz`. Put "https://s3.eu-central-003.backblazeb2.com/alpha-dev/pgbackrest/alpha-dev/backup/alpha-dev/20260913-021652F_20260918-033212I/pg_data/base/16384/1249_fsm.gz": net/http: HTTP/1.x transport connection broken: http: ContentLength=272 with Body length 0
```

Exactly one object per pass, always a small `.gz`: 928 bytes on 09-14, 1856 on
09-16, 272 on 09-18. The rest of the pass transferred and `mc` printed its
summary table (alpha 7.21 MiB / 18 s, beta 5.78 MiB / 18 s) before exiting 1.

**Which of the three: none of them.** It is a fourth outcome — the copy
succeeds and the verb still exits 5 — and both the plan's three and D1512's
`exit-code` stopped one frame short of it. The three are excluded on evidence:
the host reaches the provider (`curl` → 403, connect 0.033 s, the control
named in Sheet 0 step 6); no `401`, `403`, `InvalidAccessKeyId` or
`SignatureDoesNotMatch` in any retained journal line, so not the credential;
and not a residual rule, because a `REJECT` on the endpoint's addresses blocks
every object rather than one of ~3,700, and both hand copies completed over
that same path minutes later.

**The rule's text: there is none.** `/etc/agentic-postgres/rehearsal-in-progress.json`
does not exist, so no rehearsal is recorded as un-reversed. Sheet 0a's step 4
was issued first in a form whose exit code could not separate *no rule* from
*could not read the chain* — `grep`'s exit 1 means both — and the corrected
form was overtaken by the diagnosis. **Recorded as untested rather than
clear**, and it is not load-bearing: D1546 excludes it on the flake's own text.

**Both units' state after.** Alpha copied by hand under `script(1)`: exit 0,
3893 objects at `2026-09-18T16:35:42Z`. Beta: exit 0, 3446 objects at
`2026-09-18T16:38:15Z`. Both `mirror-state.json` written and re-read
(`last_copied_at` matches both timestamps). Both units `reset-failed`;
`systemctl list-units --failed` now lists `cloud-init-hotplugd.service` alone.
`systemctl is-system-running` still reads `degraded` — D1503, not this
product's, exactly as the plan said it would.

**Whether Run 3 owes a repair: yes, and it is D1549's, not D1546's.** The
repair is not to the mirror path, which works; it is to the verb's report of
it. Three files state D1001 — *a pass may exit non-zero with objects behind
and the next pass completes it* — as the design, and `bin/backup.py:688-695`
treats exactly that case as a hard failure, costing a failed unit, a
`degraded` host and, from 2026-09-19, a doctor `WARN … the nightly copy has
missed` over a bucket that is one object behind. Complete, partial and failed
are three outcomes and the verb reports two. **Run 2 writes the ADR** (the
plan recommends an immediate second pass in-process, so that D1001's "next
pass" is the retry and `mirror-state.json` keeps its present meaning) and Run
3 implements it with the offline proof D1549 names.

**One correction to this plan's own §0**, found while reading for Run 1 and
owed to Run 2's inventory: §0 names `backup.py:246` and `:291` as inheriting
the terminal, which stands, but `compose_mirror()` at `:616` passes
`stdin=subprocess.DEVNULL` and `capture_output=True` and is not in the D1538
class. The mirror path never hung; it reported.

### Run 2 — the measurements, and ADRs 0216–0219

**Read first:** `deploy.sh:251-266`; `bin/deploy-project.py:184-186` and
`:1725-1752`; `bin/backup.py:230-311`; `bin/restore-test.py:120-130` and
`:387-406`; `bin/migrate.py:137-170`; `bin/compose.sh:235-245`;
`bin/storage-admin.py:181-251` (the one site that already passes `-i` exactly
when stdin is given, and `tests/contract/test_storage_admin.py:55` that proves
it — the behavioural shape Run 3's proofs copy); `tests/contract/
test_printed_commands.py:100-152` (the existing D972 refusal proof and its control);
`docs/decisions/README.md:30-58` (the ADR template) and `0215` (the newest,
as the live example); `docs/decisions/0044` and `0185`; `docs/product-
contract.md:401-415`; `docs/threat-model.md` (its scope paragraph, for 0217);
`docs/plans/stage-4-plan.md` §2.1 and §8 (the invariants 0217 names).

**Rig 30a — the hang shape, with controls (D1538, D1548).** Typed by the
operator at a WSL terminal via the harness's `!` prefix; the agent writes the
script to the scratchpad and the operator runs it under `script`. A
throwaway container: `docker run -d --name apg-rig-30a --rm
<the pinned postgres image from versions.env, by digest> sleep 3600` — an
image already cached, so no network. Then, with `Defaults use_pty` added
(D1548), each arm run as `sudo bash -c '<arm>' > /tmp/rig30a-<arm>.out` **at
the terminal** with a 20 s `timeout` wrapper OUTSIDE sudo and the process
state read from a second terminal (`ps -o stat,cmd -C docker`):

| Arm | Command inside sudo | Expected |
|---|---|---|
| **subject** | `docker exec -i apg-rig-30a cat` | state `T` within 5 s; killed by the timeout; nothing written |
| control 1 | `docker exec -i apg-rig-30a cat < /dev/null` | exits 0 immediately |
| control 2 | `docker exec apg-rig-30a true` (no `-i`) | exits 0 |
| control 3 | the subject with `< /dev/null` on the OUTER shell (`sudo … < /dev/null > file`), the fully detached shape | exits 0 — the shape D972's guard allows |
| **python subject** | `python3 -c "import subprocess; subprocess.run(['docker','exec','-i','apg-rig-30a','cat'])"` | state `T` |
| **python control** | the same with `stdin=subprocess.DEVNULL` | exits 0 |

The last pair is the whole of ADR 0218's evidence: **the Python layer with
stdin closed cannot hang under the production mechanism**, and the Python
layer with stdin inherited can. Without `use_pty` run the subject once more
and record that it completes — that is D1548's reading. Remove the sudoers
file; `sudo grep -r use_pty /etc/sudoers.d/` prints nothing.

**Rig 30b — `compose run` (D1544).** Same operator terminal, a rendered
fixture (`.generated/fixture-alpha-dev`): `sudo bash -c 'bin/compose.sh
.generated/fixture-alpha-dev --runtime --profile migration run --rm dbmate
--version' > /tmp/rig30b.out` (subject; the exact profile name is read from
`bin/migrate.py:145-160` — write it down) against the same with `-T` after
`run` and `< /dev/null` inside (control 1) and the fully detached shape
(control 2). Expected: the subject stops or hangs on the pseudo-tty; both
controls print dbmate's version. If the subject **completes**, D1544's
mechanism is wrong, the row is rewritten with what `ps` showed, and
`run_dbmate` still gets `stdin=DEVNULL` and `-T` because nothing reads that
stdin — but the sentence about D1505 in the ADR says *measured not to
reproduce here*.

**Rig 30c — the orphan count (D1542).** Offline, the agent: a Python script
in the scratchpad that walks `tests/deployment/test_*.py` with `ast`,
collects every `FunctionDef`/`AsyncFunctionDef` named `test_*`, and
subtracts the set of `tests/deployment/…::name` from
`tests/acceptance-registry.yaml` (parameters stripped). Expected: **one**,
the Studio orphan. Any other name is listed in the Done and decides the
`KNOWN_UNREGISTERED` tuple.

**Rig 30d — the shadow count (D1509).** Same shape over `tests/**/*.py`: for
each module, the set of module-level `FunctionDef` names and imported names
(`Import`/`ImportFrom` aliases); inside each function, every `Name` in
`Store` context (and `NamedExpr` targets) whose id is in that set, excluding
the function's own `args` (fixture parameters). Expected: **exactly one**,
`test_session9_agent_writes.py:709`. Record every hit; if a hit is
legitimate (a name rebound on purpose), it is the guard's first divergence
row rather than an exemption.

**The grep D1540 owes:** `git grep -n "writes no file\|output-path\|no --output\|streams" tests/contract/` — if a **test body** (not a docstring quoting the header) asserts `compile` refuses `--output` or writes nothing, ADR 0220 is written in Run 4 with the same replacement rule as 0219; otherwise say so in the Done and 0220 stays free.

**Four ADRs, each in the template's shape** (`README.md:30-58`; the newest
ADRs use `- **Status:**` bullets and sub-headings inside *Context*; keep
*Alternatives considered*):

- **0216 — No public Postgres endpoint in Stage 4; the seam stays a refusal.**
  Context: D1084 named this Stage 4's first ADR; the decision report said
  *not a consequence of any number*; D1518 is the operator's decision of
  2026-09-18. What exists: `runtime_override.publication()` raises
  (`:504-524`), `compose.yaml` has zero `ports:` keys, the database and
  pooler are on `internal` (+`backup`), `connect.sh` forwards to 127.0.0.1
  (ADR 0043), and `test_port_allocator.py:363` refuses every address including
  loopback. Decision: nothing in Sessions 31–35 adds a `ports:` entry, a
  published Prometheus route, a non-loopback bind or a database transport
  reachable off-host; wanting one is a stop condition (stage plan §9).
  **The preconditions a Stage 5 reading pays** are listed as the ADR's
  *Consequences*: the rotation performed (this session pays it), the tenancy
  non-goal (`product-contract.md:405-406`) changed by ADR, an authoritative
  registry replacing ADR 0185's read, a threat model for external users, and
  an ADR superseding 0042/0043/0044 together. Names the tests: the two in
  `test_port_allocator.py`, `test_deploy_command.py:366-370`.
- **0217 — Stage 4's boundary: nothing built in Sessions 31–35 may require a
  hosted trust model to be safe.** Context: D1517 defers hosting; D1527
  puts each threat beside the plane it threatens; stage plan §2.1's sibling
  invariant. Decision: *a workflow, a connector and a worker hold nothing an
  agent identity does not hold*; a second principal is a scope set the
  existing verifier checks, never a new authority; every `THR-*` row a
  session adds is written before its code; the appliance's threat model
  (`docs/threat-model.md`) stays the document, with no sentence about
  external users. Consequences: the eight rows stage plan §8 marks new, each
  with its session; **what this forecloses**: a control plane as a client,
  an approval granted by the requester, a connector with a scope its
  profile did not narrow to.
- **0218 — No product child reads the terminal.** Context: D972 (the
  mechanism, measured 2026-09-04), D1501 (a read stopped seven minutes),
  D1504/D1505 (the guard on one of thirteen; the rule forgotten in 25
  minutes), D1538/D1544 (the class is a child with an inherited terminal,
  in two shapes), rig 30a/30b's table. Decision: `container_exec.run()` is
  the only way the product runs `docker exec`; stdin is `DEVNULL` unless
  `input=` is given, `-i` exactly then, `-t` never (except
  `dev_environment.psql_arguments`'s interactive `apg dev psql`, which is
  gated on `sys.stdin.isatty()` and is a developer's terminal by design —
  named as the one exception, with its test); `run_dbmate` passes `-T` and
  `DEVNULL`; the D972 refusal stays on `deploy.sh` as a sourced function and
  is **not** extended to commands whose children cannot read the terminal
  (D1538's reason). The AST proof is named. Alternatives: the guard on all
  thirteen (refuses working shapes); `script(1)` in the guide (a sentence,
  not a control).
- **0219 — The reading before a tag takes a ref.** Amends 0214 (whose
  decision — facts, no verdict — is untouched). Context: D1425 puts the tag
  behind `HEAD` on every trip; D1513 measured 14 vs 13 commits after the
  bump on the same day; the throwaway worktree is the procedure today.
  Decision: `--ref REF`, one option, resolved with `git rev-parse --verify
  "REF^{commit}"`, refused at exit 2 when unresolvable; every git read in
  `bin/release-reading.py` that says `HEAD` says the resolved commit; the
  first block's label reads `ref` when one was given; the no-argument form
  is unchanged byte for byte. **Replaces `test_the_command_takes_no_
  arguments_and_says_so` with a stricter test** (D1539) and says which.
  Consequences: `docs/operator-guide.md` §14 *Before a tag* names
  `--ref <the deployed commit>`; Session 30's own tag is its first use.

**ADR index**: four rows in `docs/decisions/README.md` in the format of
`:60-66` (session 30, Accepted). `test_documentation_index`,
`test_acceptance_registry` (the index proofs at `:486-555`) run.

**Targeted:** `test_documentation_index`, `test_acceptance_registry`,
`test_repository_contract`. This run is documentation plus rig transcripts
in the scratchpad (nothing under the tree but the four ADRs and their index
rows) — **documentation only: no gate, no CI read.**

**Done.** _(Run 2, 2026-09-18. **Four of the seven measurements came back
different from the plan, and three of those were a read that could not read
being reported as an answer.**)_

**Rig 30a — the hang shape.** Run by the operator at a WSL terminal, twice
(`before-use-pty`, `with-use-pty`), docker 29.5.2, the pinned pgvector image by
digest, already cached, no network.

| arm | exit | reading |
|---|---|---|
| subject `docker exec -i C cat` | **124** | hung, killed by the timeout |
| control 1 `… cat < /dev/null` | 0 | completes |
| control 2 `docker exec C true` | 0 | completes |
| control 3, fully detached | 0 | completes — the shape D972's guard allows |
| **python subject**, inherited stdin | **124** | hung |
| **python control**, `stdin=DEVNULL` | 0 | completes |

The last pair is the whole of ADR 0218's evidence: **the product's own layer
with stdin closed cannot hang under the production mechanism, and with stdin
inherited it can.** Identical in both runs.

**Two readings in that rig are not what they appear, and both are recorded
rather than quietly used.** The `ps` state column read `-` for five of six arms
because of a defect in my rig, not a property of the system: `p=$(sample …)`
used command substitution, which waits for the background sampler's stdout to
close, so the sampler ran to completion **before** each arm started. The exit
codes are sound and carry the result alone. And `use_pty configured: YES`
printed on the **before** run — D1548 was wrong, see below — so the
before/after pair is void while the result stands.

**Rig 30a2 — the variable rig 30a confounded.** 30a's subject and control 2
differ in *two* things (`-i`, and whether the child reads stdin), so 30a proved
a hang existed without saying what caused it. Four arms, one variable at a time:

| child reads stdin | `-i` | exit |
|---|---|---|
| no | no | 0 |
| no | **yes** | 0 |
| yes | no | 0 |
| **yes** | **yes** | **124 — hung** |

**The class is exactly: a child that reads stdin, handed a terminal.** Neither
`-i` alone nor a reading child alone stops anything.

**Rig 30b — measured nothing; v1 is void.** All three arms exited 3 at
`compose: no runtime override for fixture-alpha-dev` before any container
started. Recorded as *could not determine*, not folded into *the mechanism is
wrong* (ADR 0195 applied to this session's own rig).

**Rig 30b2 — `docker compose run`, compose 5.1.3.** The wrapper dropped; the
third party measured directly, with two services because D1544's claim has two
halves.

| service | flags | exit |
|---|---|---|
| `true` (never reads stdin) | — | 0 |
| `true` | `-T` | 0 |
| `true` | detached | 0 |
| **`cat` (reads stdin)** | — | **124 — hung** |
| `cat` | `-T` + `< /dev/null` | 0 |

**`docker compose run` allocates a pseudo-tty but does not itself read the
terminal.** D1544's stated mechanism is falsified, agreeing exactly with 30a2.
**dbmate does not read stdin**, so `run_dbmate` cannot stop this way and
D1505's seven-minute hang has a cause still not established. It is repaired
anyway and ADR 0218 says *measured not to reproduce here*.

**Rig 30c — orphans: 23, not one.** The registry names **237** distinct
`tests/deployment` node ids; the tree defines **260** test functions. Verified
independently of the AST walk against the registry text, with a control (three
known-registered names matched once each, five sampled orphans matched zero).
Several are security proofs — the firewall, sshd's limits, four project
isolation proofs. D1542 rewritten; Run 5 triages, and the tuple is real work.

**Rig 30d — shadows: five, not one, and none live.** The raw scan says 50; **45
shadow a pytest fixture and are not the class**, because a fixture is reached
by declaring it as a parameter rather than by calling its name. Five shadow a
plain module-level helper, and in none of them is the helper called by name
inside that function. Zero currently-broken instances. **Better than planned:
Run 5 repairs all five and the guard needs no exemption list.** D1552.

**The D1540 grep — answered, and it moved the work.** No test body asserts that
`mcp-contract.sh compile` has no output option. But
`test_api_contract_command.py:217` asserts exactly that for the sibling command
`api-contract --update`, citing ADR 0050 and the reason that *an `--output`
option would put the file's ownership in the privileged process*. **ADR 0220
was therefore free, and went to the mirror fold**; Run 4 must answer the
ownership argument before adding `--output`, and **0221 is reserved** for it.
D1550.

**Five ADRs written, indexed and Accepted** — 0216 (no public endpoint in Stage
4, with the five preconditions a Stage 5 reading pays), 0217 (Stage 4's
boundary: nothing may require a hosted trust model to be safe), 0218 (no
product child reads the terminal), 0219 (the reading before a tag takes a ref,
and reads `VERSION` from it rather than from the working tree), 0220 (a mirror
pass has three outcomes and the verb reports three). Index integrity checked
programmatically: **220 ADRs, every file listed, no dangling row.**

**One fact ADR 0219 carries that the plan did not have.**
`bin/release-reading.py:100-101` reads `VERSION` from the **working tree**, and
`:112` then searches the tags for the one whose `VERSION` equals it. A `--ref`
that resolved a commit and kept that read would report the ref's commit married
to the checkout's `VERSION` — correct on every occasion except the one the
option exists for. The ADR requires `git show REF:VERSION`.

**Targeted:** `test_documentation_index`, `test_acceptance_registry`,
`test_repository_contract` — **306 passed**, exit 0. Documentation only: no
gate, no CI read.

**Left for Run 3:** everything the exec discipline needs is now measured, and
the class is defined by measurement rather than by the spelling of an argv.

### Run 3 — the exec discipline: one helper, one shell function, thirty-nine sites, the class guard

**Read first:** `bin/storage-admin.py:181-251` and `tests/contract/
test_storage_admin.py:40-90` (the behavioural proof: monkeypatch
`subprocess.run`, read the argv); `tests/contract/test_database_commands.py:
20-35` and `:514-535` (the three commands it line-scans; the `set +x` rule);
`tests/contract/test_repository_contract.py:693-760` (an AST walk over
`bin/*.py` that resolves `<module>.<function>(...)` calls — the shape the
class guard copies) and `:531` (a module imported only by its own tests is
refused, D204 — **the helper and its first caller land in ONE commit**,
D1273); `tests/contract/test_cli_contract.py:42`, `:167`, `:323-331`
(the preamble rule: shebang, `set -euo pipefail`, `BASH_SOURCE`), `:975-1009`
(non-recursive `iterdir`, so `bin/lib/` is not a command); `bin/apg-diag.sh:
300-340`; `bin/db.sh:130-205`; every file in D1537's inventory at the lines
§0 gives; `src/agentic_postgres/dev_environment.py:801-840`;
`src/agentic_postgres/rehearsal.py:428-480`; `bin/rehearse.py:70-80`.

1. **`src/agentic_postgres/container_exec.py`** — pure argv building plus one
   thin runner, stdlib only (`subprocess`, `dataclasses`, `os`), with these
   names and no others at module level (a test asserts `__all__` against the
   AST, `studio.py`'s rule):
   - `exec_argv(container: str, *argv: str, user: str | None = None,
     env_file: str | None = None, input_given: bool = False, tty: bool =
     False) -> list[str]` → `["docker", "exec", *(["-u", user] if user),
     *(["--env-file", env_file] if env_file), *(["-it"] if tty else ["-i"]
     if input_given else []), container, *argv]`. `tty=True` requires
     `input_given=False` and raises `ValueError` otherwise (a tty and a fed
     stdin are two different terminals).
   - `run(container, *argv, input: str | bytes | None = None, user=None,
     env_file=None, timeout: float | None = None, text: bool = True) ->
     subprocess.CompletedProcess` → `subprocess.run(exec_argv(…,
     input_given=input is not None), input=input, stdin=(None if input is
     not None else subprocess.DEVNULL), capture_output=True, text=text,
     timeout=timeout, check=False)`. **Never `-t`; never an inherited
     stdin.** A caller that wants `stdout` uncaptured (the interactive
     `apg dev psql`) does not use `run`; it uses `exec_argv(…, tty=…)` with
     `os.execvp`, and that is the one named exception (ADR 0218).
   - `compose_run_argv(compose_sh: str, rendered_dir: str, *rest: str) ->
     list[str]` → `[compose_sh, rendered_dir, "--runtime", *rest]` with
     `-T` inserted immediately after the `run` token (refuses an argv with
     no `run`); `compose_run(...)` runs it with `stdin=DEVNULL`.
   - `MIXED_TERMINAL_SHAPE_MESSAGE` — the exact string `deploy.sh:261`
     prints today, minus the `--through-session` prefix, so the shell
     library and the Python module agree on the sentence (a test compares
     the library's text to this constant).
2. **`bin/lib/tty-guard.sh`** — the first file under `bin/lib/`, mode 644
   (it is sourced, not run; `test_every_command_in_bin_is_covered` does not
   see it; `test_shell_script_preamble` does not apply to it — say so in its
   header). One function, `refuse_mixed_terminal_shape COMMAND-NAME`, whose
   body is **`deploy.sh:260-262` moved**: the `if [ -t 0 ] && { [ ! -t 1 ]
   || [ ! -t 2 ]; }; then die 2 "…"` with the message parameterised on the
   name. It expects `die` to be defined by the sourcing script (every
   `bin/*.sh` defines one; assert that in the header). `deploy.sh` sources
   it after `ROOT_DIR` is set — `. "${ROOT_DIR}/bin/lib/tty-guard.sh"` —
   and calls `refuse_mixed_terminal_shape "--through-session"` where `:260`
   was. The message bytes before and after are compared in the Done.
   `bin/db.sh` and `bin/apg-diag.sh` also source and call it at the top of
   their `main` — **these two exec directly**, and closing stdin on the
   line (step 4) is the repair; the guard is the belt on the same two.
   **No other `bin/*.sh` sources it** (D1538). `shellcheck` on the library
   (`bin/session-01-check.sh` runs shellcheck over `bin/*.sh`; read whether
   its glob reaches `bin/lib/` — if not, add `bin/lib/*.sh` to that step in
   the same commit and say so).
3. **The thirty-two Python sites.** File by file, in this order, each
   followed by that module's whole test module: `doctor.py` (eight sites;
   its `run()` becomes `container_exec.run` — the `-i` those sites pass
   today disappears, which is correct: nothing is fed), `fleet.py`,
   `restore.py`, `rehearse.py`'s runner (the `rehearsal.py` tuples become
   `container_exec.exec_argv(container, …, user="999")`), `backup.py`
   (`pgbackrest()` and `read_archiver()` — the seven-minute site),
   `deploy-project.py` (six sites; `run()` at `:184` is a general runner
   used for more than docker — **grep its callers**; only the docker calls
   move to the helper, and `run()` itself gains `stdin=subprocess.DEVNULL`
   so no other child inherits either), `restore-test.py`, `auth-admin.py`,
   `postgres-bootstrap.py` (the `read_only` branch: `-c sql` with no
   input → `run(..., input=None)`), `storage-admin.py` (`in_container` is
   already the rule; it becomes a one-line wrapper), `migrate.py` (`:235`,
   `:300`, and `run_dbmate` → `compose_run`), `dev.py` (`docker()` at `:70`
   → `container_exec.run`; `await_ready` no `-i`; the `psql` verb keeps
   `os.execvp` over `exec_argv(…, tty=arguments.tty)`), `dev_environment.py:
   834` (`psql_arguments` returns `exec_argv(...)[1:]`, keeping its
   contract). **Grep every reader of every helper name you delete** (D979)
   and the moved text (D1187: `"docker", "exec"` and `docker exec`).
4. **The four shell sites.** `bin/db.sh:186` and `:191` end with
   `< /dev/null`; `:201` already reads the artifact; `bin/apg-diag.sh:335`
   ends with `< /dev/null`.
5. **`tests/contract/test_container_exec.py`** (marks first — D1240:
   `contract`, `p0`, `security`): the seven proofs §2 names. The first three
   run a **real** container (`docker run -d --rm <pinned image> sleep 60`,
   removed in `finally`; skip is not allowed — if docker is absent the
   module fails, as `test_studio_runtime` does): `input="SELECT 1"` reaches
   `cat` (subject) and `input=None` leaves `cat` reading an empty stream
   and exiting 0 at once (control — **this is the no-hang proof**, with a
   5 s timeout that would fire on an inherited terminal). The scan proofs
   walk `bin/*.py`, `src/agentic_postgres/**/*.py` and `bin/*.sh` with the
   rule in D1538, anti-vacuity by the helper's own call and by a synthetic
   module in `tmp_path` fed to the same function. `test_database_commands.py`
   gains `test_every_shell_docker_exec_closes_or_supplies_stdin` over
   **every** `bin/*.sh` and `deploy.sh` (the existing `-i` line-scan stays).
6. **The guard's existing proof.** `test_printed_commands.py:107`
   `test_a_deploy_with_a_terminal_on_stdin_and_redirected_output_is_refused` —
   the deploy proof that runs `deploy.sh --through-session` with a pty on
   stdin and a pipe on stdout expecting exit 2, and the control with no
   terminal expecting exit 3 (session-17 plan, D972's row). It runs
   unchanged; if it reads the message from `deploy.sh`'s text, it now reads
   it from the library and the constant, and says so.
7. **Battery (≥10 mutations)**: drop `stdin=DEVNULL` from `run` (killed by
   the timeout proof); pass `-i` unconditionally (killed by the argv proof);
   pass `-t` (killed); make the scan skip `bin/` (killed by the synthetic
   control); delete `-T` from `compose_run_argv` (killed); put a bare
   `subprocess.run(["docker", …])` back into `backup.py` (killed by the
   scan); remove `< /dev/null` from `db.sh:186` (killed by the shell scan);
   change one character of the library's message (killed by the constant
   comparison); make `refuse_mixed_terminal_shape` test `[ -t 1 ]` only
   (killed by the D972 proof's stderr arm); rename the helper's `run` in
   `doctor.py` back to a local `subprocess.run` with `-i` (killed by the
   scan). Each with a paired control the mutation cannot reach, in the same
   invocation, anchors pre-flighted (D269), restored by copy and `cmp`.
8. **Documentation in the same commit**: `docs/upgrade-guide.md:545-560`
   and `:792`, `docs/operator-guide.md:99-103` and `:628` — the D972
   paragraphs gain *the class is any product child that reads the terminal;
   since ADR 0218 no product child does, and `deploy.sh` keeps its refusal*;
   `CLAUDE.md` §2's *never pipe a sudo command* fact is rewritten at the
   close (Run 9), not here.

**Targeted:** `test_container_exec`, `test_database_commands`,
`test_storage_admin`, `test_printed_commands`, `test_deploy_command`, `test_doctor`, `test_fleet`,
`test_backup*`, `test_restore*`, `test_rehearsal`, `test_auth_admin*`,
`test_postgres_bootstrap*`, `test_migrate*`/`test_migration_command*`,
`test_dev_command`/`test_dev_environment`, `test_diagnostic_surface`,
`test_database_access*` (db.sh), `test_cli_contract`,
`test_repository_contract` (D204 and the keyword scan), plus every module
`git grep -ln '"docker", "exec"\|docker exec\|psql(\|in_container(' -- tests`
names. Existence of each name is checked before it is run (D1104); the
list is the grep's. Push; read CI.

**Done.** _(Run 3, 2026-09-18. **The class is at zero and the guard is a scan
over the tree, not a list.**)_

**The scan's before and after.** Measured by the AST scan that then became the
guard, over `bin/*.py` and `src/agentic_postgres/**/*.py`:

| | before | after |
|---|---|---|
| `subprocess.*` calls whose argv reaches `docker`/`compose.sh` | 27 | 22 |
| of those, **unguarded outside the helper** | **14** | **0** |
| pass-through runners with stdin open | 13 | 5 (all `git`/tool readers, out of scope) |

**It is not the plan's 39, and it is counting a different thing** (D1554).
D1537 counted argv-*building* sites; the rule is about `subprocess` calls,
because a site that hands its argv to a runner which closes stdin cannot hang.
The 14 spanned nine files and **five of them this plan never named** —
`auth-admin.py:246`, `postgres-bootstrap.py:86` and `:900`,
`rotate-signing-key.py:218` and `:254`, `storage-admin.py:165`,
`access_broker.py:343`. **`rotate-signing-key.py` is the command Run 8 runs
against production.**

**The seven helpers' fate.** `doctor.py:91`, `fleet.py:72`, `restore.py:104`
and `rehearse.py:85` already passed `stdin=DEVNULL` and were left alone —
D1538 was right about them. `deploy-project.py:185`'s generic `run()` and
`restore-test.py:120`'s `docker()` gained it, with a docstring saying why a
pass-through runner must. `backup.py`'s `pgbackrest()` and `read_archiver()`
and `postgres-bootstrap.py`'s `await_cluster()` now call `container_exec.run`.
`migrate.py`'s `run_dbmate` calls `compose_run`.

**The message bytes compared.** D972's refusal was moved into
`bin/lib/tty-guard.sh` by a script that extracts the sentence from both files
and **refuses to write if they differ**: identical, 173 characters. `deploy.sh`
sources the library after `ROOT_DIR` and calls `refuse_mixed_terminal_shape
"--through-session"` where the `if` was. The existing D972 proof
(`test_printed_commands.py:107`) passes unchanged, including its control.

**The battery: 11 mutations, 11 killed, every control green, restoration
byte-identical.** Anchors pre-flighted (all 11 matched exactly once),
`PYTHONDONTWRITEBYTECODE=1`, `__pycache__` cleared between every arm, restored
by copy from a `/tmp` snapshot and `cmp`d back.

**But the first run killed only 9, and both survivors were real weaknesses in
the proofs** — which is the whole reason for a battery:

1. **`run()` inherits stdin — survived.** `test_stdin_is_closed_when_no_input_
   is_given` runs a real container and still passed with `stdin=DEVNULL`
   deleted, because inside pytest this process's stdin is not a terminal, so
   `cat` reaches end of file either way. **The behavioural proof asserts the
   rule in the one environment where the mechanism cannot occur.** Repaired by
   adding `test_run_closes_stdin_when_no_input_is_given`, which monkeypatches
   `subprocess.run` and reads the argument directly (`test_storage_admin.py:
   55`'s shape). The container proof is kept — it proves the argv works — but
   it is no longer the only reader.
2. **The guard tests stdout only — survived.** Weakening `[ -t 0 ] && { [ ! -t
   1 ] || [ ! -t 2 ]; }` to `[ -t 0 ] && [ ! -t 1 ]` left the D972 proof green,
   because that proof uses `capture_output=True`, which pipes **both** streams,
   so `[ ! -t 1 ]` is true and the `|| [ ! -t 2 ]` half has never been executed
   by a passing test. Repaired by
   `test_the_guard_refuses_a_terminal_on_stdout_with_only_stderr_redirected`,
   which puts stdin and stdout on the same pty and only stderr on a pipe. **A
   passing test had been carrying half a condition since Session 17.**

A third weakness was found before the battery and closed in the guard itself:
nothing would have caught a scan that looked at **nothing**. The guard now
asserts its own search — more than 80 modules, and three named files present —
because a scan aimed at an empty list reports a clean tree in the same words a
clean tree uses. The battery's *the scan looks at nothing* mutation confirms it.

**Which proofs came back ERROR rather than FAILED: none.** All 11 mutations
produced `failed`, so every one reached its assertion rather than breaking a
fixture on the way (D386).

**One half of the plan deliberately not applied** (D1553). Step 2 asks for the
guard on `bin/db.sh` and `bin/apg-diag.sh` as well. After step 4's `< /dev/null`
those two cannot hang, so the guard there would refuse `sudo bin/db.sh status
--project alpha-dev > out.txt` at a terminal — a correct invocation with no
failure mode left. That is D1538's own finding and ADR 0218 forbids it in as
many words. Step 4 applied; step 2's other half not. `-i` is **kept** on every
shell site, because `db.sh:181` records that without it psql reads nothing and
exits 0 having executed nothing.

**Also in this commit:** `bin/session-01-check.sh`'s shellcheck did not reach
`bin/lib/` — its glob is `deploy.sh bin/*.sh libexec/*` — so `bin/lib/*.sh` was
added to it. A library nothing lints is a library whose refusal nobody checks.
`docs/upgrade-guide.md:545` and `docs/operator-guide.md:100` now say the class
is any product child that reads the terminal, that since ADR 0218 none does,
and that `deploy.sh` keeps its refusal as a belt rather than as the repair.

**Targeted:** 973 passed across `test_container_exec`,
`test_database_commands`, `test_printed_commands`, `test_cli_contract`,
`test_repository_contract`, `test_documentation_index`, `test_deploy_command`,
`test_storage_admin`; and 1389 passed across the full derived list
(`git grep -ln` over the moved names and the moved text). `ruff format` and
`ruff check` clean over `bin src tests`; `shellcheck` clean over
`deploy.sh bin/*.sh bin/lib/*.sh libexec/*`.

### Run 4 — `release-reading --ref`, `compile --output`, and the two documented lines

**Read first:** `bin/release-reading.sh` whole (100 lines); `bin/release-
reading.py` whole (208 lines; `git()` at `:44-65`, `HEAD` at `:96`, the
fourteen other reads at the lines §0 gives); `src/agentic_postgres/release_
reading.py:84-88` and `:259-351`; `tests/contract/test_release_reading.py`
whole (`observation()` `:37`, `command()` `:66`, `fake_git()` `:274`,
`run_command()` `:350`); ADR 0219 as written in Run 2; `bin/mcp-contract.sh`
whole (the header `:8-13`, usage `:39-78`, the case `:100-145`);
`bin/mcp-contract.py:60-90` and `:170-202`; `tests/contract/test_capability_
compiler.py` (how it drives `compile`); `docs/new-team-member.md:260-300`;
`README.md:540-565`; `tests/contract/test_documentation_index.py:108-161`;
`tests/contract/test_session12_documented_path.py:32-90`.

1. **`release-reading`**: the shell loop accepts `--ref` with a value (and
   `--ref=REF`), refuses a missing value with exit 2, still refuses any
   other argument with exit 2 and the usage on stderr (the sentence becomes
   *this command takes one option, --ref REF (got: …)*); it `exec`s the
   Python with `--ref REF` when given. The Python: `argparse` gains
   `--ref` (default `HEAD`); `resolve_ref(ref) -> str | None` runs `git
   rev-parse --verify "<ref>^{commit}"` and returns the SHA or `None`; `None`
   exits 2 naming the ref (before any other read); every read that named
   `HEAD` (`:96`, `:127`, `:129`, `:140`, `:142`, `:149`) names the SHA;
   `render()` labels the first block `ref <what was typed>` when a ref was
   given and `HEAD` otherwise (D1545). Usage block rewritten whole (`--ref
   REF  Read the commit REF names instead of HEAD — the deployed commit,
   before the tag (D1425). Default HEAD.`).
2. **The five proofs** §2 names, in `test_release_reading.py`; the replaced
   test **deleted** and its registry node id moved in the same commit
   (D1119: `test_acceptance_registry` in the list). The tag-target proof
   builds a throwaway repository in `tmp_path` with `git init`, two commits
   and a tag on the first, and runs the product's own command with `--ref`
   (D1114) — copy `test_a_clone_with_no_tags_produces_the_third_outcome_
   through_the_command`'s fixture shape.
3. **`compile --output PATH`**: the shell loop accepts `--output` **only when
   the command is `compile`** (for `check`/`lock` it falls to `*)` with a
   message naming the two that refuse it); the Python's `command_compile`
   takes `output: Path | None`, and when given writes `candidate` to
   `f"{output}.tmp.{os.getpid()}"`, `os.replace`s it over `output`, and
   prints the stderr hook as before. On any exception the `except` arms
   return their codes **before** any file is opened — the temporary is
   created after `candidate` exists and nowhere else. Header paragraph
   rewritten (D1540); usage line `:123` becomes `bin/mcp-contract.sh compile
   [--capabilities FILE] [--project FILE] [--output PATH]` with the flag's
   paragraph. **ADR 0220 only if Run 2's grep said so.**
4. **The three compile proofs** §2 names, in `test_capability_compiler.py`.
   The refusal is the adopter's own (D1114): a temporary project manifest
   naming `mcp.capabilities` at a directory with no snapshot, so
   `CapabilityContractError` → exit 5; assert PATH absent AND `glob(f"{PATH}.
   tmp.*")` empty. Control: `--output` against `project.example.yaml`
   (which has a snapshot) writes bytes equal to the streamed stdout of the
   same command without `--output`.
5. **The documents**: `docs/new-team-member.md:272-273` and
   `README.md:551-552` become the single `--output` form; `README.md:558-562`
   loses the 0-byte cleanup sentence and says instead that a refused
   compile writes nothing; `docs/operator-guide.md` §14 gains the `--ref`
   line (ADR 0219's consequence). `test_session12_documented_path.py` gains
   `test_no_documented_compile_line_redirects_its_output` (the regex reads
   the line and its continuation: `mcp-contract\.sh compile[^\n]*(\\\n[^\n]*)?`
   must not contain ` > `). Control: the test's own regex applied to the
   OLD line text (kept as a string in the test) finds the `>`.
6. **Battery (≥6)**: make `--ref nonesuch` fall through to `HEAD` (killed);
   label `HEAD` when a ref was given (killed); write PATH before compiling
   (killed by the refusal proof); leave the temporary behind on `os.replace`
   failure — simulate by making the target a directory (killed); accept
   `--output` on `check` (killed); put `>` back in the README line (killed
   by the documented-path proof).

**Targeted:** `test_release_reading`, `test_capability_compiler`,
`test_capability_profile`, `test_project_agent_surface`, `test_mcp_catalog`,
`test_generate_command` (it drives `compile`? — grep), `test_documentation_
index`, `test_session12_documented_path`, `test_cli_contract` (a flag's help
text is scanned by `test_no_command_documents_a_secret_argument`),
`test_acceptance_registry`, `test_printed_commands` (a printed command
changed), plus the grep's list for `release-reading\|release_reading\|
mcp-contract`. Push; read CI.

**Done.** _(Run 4, 2026-09-18.)_

**The replaced test and its replacement.**
`test_the_command_takes_no_arguments_and_says_so` →
`test_the_command_takes_exactly_one_option_and_refuses_the_rest`, authorised by
ADR 0219, stricter as CLAUDE.md §6 requires: four refusals in the one function
(`--since 1.6.0`, a positional, `--ref` with no value, and `--ref HEAD`
succeeding) where there was one. `--since 1.6.0` is asserted **by name** so a
second option would have to delete that line rather than merely not add a test.
Its node id was replaced in `REL-READ-001` in the same commit (D1119) and
`test_acceptance_registry` ran.

**`--ref 8c61309b6cf9` on this checkout — the first reading of the deployed
commit without a worktree:**

```
  outcome: nothing_to_decide
  the tree says 1.7.0, tag 1.7.0 carries it, and nothing has landed since:
  there is nothing to decide.

  Where the ref 8c61309b6cf9 stands
    commit            8c61309b6cf9
    VERSION           1.7.0
    tags on it        1.7.0
  ...
  What has landed since 1.7.0
    commits           0
```

The same checkout with no argument reads `Where HEAD stands / 86cfbc9efb92`
and **8 commits since** — D1513's gap, in one screen.

**Two things the plan did not have, both found by reading rather than by a
test going red.**

`bin/release-reading.py:100` reads `VERSION` from the **working tree**, and
`:112` then searches the tags for the one carrying it. A `--ref` that resolved
a commit and kept that read would marry the ref's commit to the checkout's
`VERSION` — right on every occasion except the one the option exists for. The
lock and the ADR count are the same shape. With a ref they are read as
`git show REF:…` and `ls-tree REF`; **with no ref they are read exactly as
before**, because ADR 0219 promises that form is unchanged.

And *unchanged* had to mean the **argv**, not merely the rendered bytes.
Anchoring every range to the resolved SHA turned `rev-list --count TAG..HEAD`
into `rev-list --count TAG..<sha>` and
`test_the_command_finds_the_tag_that_carries_the_version_not_the_one_on_head`
went red — it drives `observe()` through a fake git keyed on the argument
tuples. It was right to. With no ref the anchor is the literal `HEAD`, and
`describe`/`log` take the ref as a positional so it is appended only when there
is one.

**The compile refusal's exit and the absence proved.** Exit **5**, `PATH`
absent, `glob("*.tmp.*")` empty. The contrast is in the same rig: the old `>`
shape truncated an 18-byte file to **0 bytes** on the same refusal. `--output`
and the stream produce identical bytes (3015 on `project.example.yaml`), and
`check`/`lock` refuse the flag with exit 2 — the guard moved ahead of their own
argument requirements, because `lock --output X` was answering *lock requires
--outputs*, which is the right exit and the wrong sentence.

**Whether 0220 was written: it was, but not for this.** D1540's condition —
a passing test asserting `compile` has no output option — was **not met**, so
0220 was free and Run 2 gave it to the mirror fold. What the grep found instead
is D1550: `test_api_contract_command.py:217` asserts exactly that design for
the sibling `api-contract --update`, citing ADR 0050 and *an `--output` option
would put the file's ownership in the privileged process*. **Answered rather
than deferred, and no ADR needed:** `bin/mcp-contract.sh` has no `require_root`,
no `id -u` check and no privileged invocation anywhere documented or tested, so
the file is created by the invoking user exactly as the shell redirect created
it. ADR 0050's reason does not reach this command, and the header now says so
and cites the row. **0221 stays free.**

**Two registry entries deferred to Run 6** (D1555). `REL-READ-002` and
`CAP-COMPILE-001` carry `target_session: 30`, which
`test_every_entry_has_complete_metadata` refuses while `CURRENT_SESSION` is 28;
moving it is all-or-nothing (D690) and Run 6 owns it. The proofs exist and pass
now; the entries are parked verbatim in §2 for Run 6 to paste.

**A Run 3 defect that only CI could see.** Run 3's commit failed CI on
`test_fleet.py::test_nothing_in_the_release_reads_the_inventory`: the new
`run()` docstring in `bin/deploy-project.py` named `fleet.py`, and that scan
strips `#` comments but not docstrings. 6014 tests passed and one did not; no
targeted list derived from that diff would have named `test_fleet`, which is
D1486 and the reason CI is the full check. The sentence is reworded rather than
the rule weakened. **Fixed in this commit.**

**Targeted:** 820 passed across `test_release_reading`,
`test_capability_compiler`, `test_capability_profile`,
`test_project_agent_surface`, `test_mcp_catalog`, `test_documentation_index`,
`test_session12_documented_path`, `test_cli_contract`,
`test_acceptance_registry`, `test_printed_commands`, `test_fleet`,
`test_generate_command`. `ruff` clean over `bin src tests`; `shellcheck` clean.

### Run 5 — the two suite-shape guards, the orphan repaired, three counts

**Read first:** `tests/contract/test_deployment_suite_shape.py` whole (the
model, 113 lines); `tests/contract/test_deployment_module_shape.py`;
`tests/contract/test_acceptance_registry.py:36-60` (`strip_parameters`,
`registry` fixture), `:190-236`, `:594-640`; `tests/deployment/
test_session9_agent_writes.py:85-120` and `:655-725`; `tests/deployment/
test_session24_studio.py:59-120` and `:689-832`; `tests/deployment/
conftest.py:1440-1500`; rigs 30c and 30d's outputs; `docs/project-
isolation.md:80-95`; `docs/capacity-envelope.md:140-150`; `docs/dev-
environment.md:170-185`; `src/agentic_postgres/evidence.py:36-68`.

1. **`tests/contract/test_suite_shape.py`** (new; marks `contract`, `p0`):
   `_module_level_names(tree) -> set[str]` (every module-level `FunctionDef`,
   `AsyncFunctionDef`, and `Import`/`ImportFrom` alias `asname or name`),
   `_shadows(path) -> list[str]` (rig 30d's rule as a function: for every
   function node, `Name` in `Store`/`NamedExpr` targets/`For` targets/`With`
   `as` names whose id is in the module set and not among the function's
   own parameters, reported as `path:line function local`), and the three
   proofs §2 names. The synthetic control writes a module to `tmp_path`
   with `def refused(...)` and a function binding `refused = 1` (found) and
   a sibling binding `answer = 1` (not found).
2. **The shadow repaired**: `test_session9_agent_writes.py:709-721` — the
   local `refused` → `answer` (and its three uses in the two asserts). No
   node id moves; the module's four callers of `refused()` (`:286`, `:984`,
   `:1256`, `:1263`) are untouched. Note `test_session24_studio.py:211` also
   defines a `refused` helper — the guard reads every module and rig 30d
   said it has no shadow; the Done says so.
3. **`test_deployment_suite_shape.py`** gains the two registration proofs
   §2 names. `KNOWN_UNREGISTERED: tuple[str, ...] = ()` unless rig 30c
   listed more than the Studio orphan (D1542's rule; each entry commented
   with the session that owns it and the row that says why).
4. **The orphan's fixture**: `test_session24_studio.py:724` →
   `"ARRAY['notes:read']::text[], "` — one scope, sorted by construction,
   in `DEFAULT_PROBE_SCOPES`' vocabulary; the fixture's docstring gains the
   sentence that an empty scope set is refused by `0011:116` and that a
   stranger with a read scope on the audited relation is the stronger
   subject anyway (the stranger CAN read `notes` and still sees none of the
   auditor's). `pytest --setup-plan tests/deployment/test_session24_studio.py
   -k query_view` with `APG_LIVE_HOST=1 APG_PROJECT_A_OUTPUTS=<an op-owned
   copy in the checkout>` set: the proof is **planned**, not skipped (D671).
   It cannot run here; Run 7 is its first execution and §7 says so.
5. **Registry and claims**: `STU-QUERY-002`, `EVD-SHAPE-001` entries; the
   `studio_tenant_read` and `suite_shape` claims; `test_evidence_claims.py`'s
   session table. (`OPS-EXEC-001`, `REL-READ-002`, `CAP-COMPILE-001` and
   their claims are registered in **Run 6 with the constant move**, because
   `target_session: 30` refuses while `CURRENT_SESSION` is 28 —
   `test_every_entry_has_complete_metadata:151`. **So do these two**: this
   run writes the entries into the registry file but the registry test is
   green only at Run 6. Read `:151-165` first; if `APG_ACCEPTANCE_SESSION`
   lets the targeted run pass at 30 here, use it for the targeted run and
   say so; otherwise Run 5's targeted list omits `test_acceptance_registry`
   and Run 6's runs it.)
6. **The three counts** (D1541): `git grep -n "31 released\|fifteen parsed"`
   → every hit edited; `docs/project-isolation.md:86-87` names
   `evidence.ISOLATED_FIELDS` and says *eighteen JSON pointers*.
7. **Battery (≥6)**: exclude `Store` context from the shadow scan (killed by
   the synthetic control); include function parameters (killed by the
   pass-control, which would then flag a fixture); make the registration
   scan strip nothing (killed if any registered node id is parametrised —
   check; else killed by the synthetic); put `ARRAY[]::text[]` back (the
   `--setup-plan` cannot see it — **this mutation is recorded as
   unreachable offline** (D493) and is the reason §7 names the trip);
   remove the Studio node id from the registry (killed by the registration
   proof); remove one entry from `KNOWN_UNREGISTERED` if any (killed by the
   equality).

**Targeted:** `test_suite_shape`, `test_deployment_suite_shape`,
`test_deployment_module_shape`, `test_capacity_envelope`,
`test_documentation_index`, `test_render_isolation`, `test_evidence_claims`,
`test_acceptance_registry` (per step 5), plus `git grep -ln "test_session9_
agent_writes\|test_session24_studio" -- tests/contract`. Push; read CI.

**Done.** _(Run 5, 2026-09-18.)_

**The shadow scan's count over the whole suite: five, and zero after the
repair.** The guard reproduced rig 30d exactly — `test_api_contract_command.py:
620` (`merged`), `test_deployed_output.py:1361` (`published`),
`test_project_agent_surface.py:155` (`tool`), `test_storage_client.py:433`
(`adapter`) and `test_session9_agent_writes.py:709` (`refused`, D1509's own
survivor) — with both controls green. All five renamed, so
`test_no_local_shadows_a_module_level_function` asserts **zero with no
exemption list**. `test_session24_studio.py:211` defines a `refused` helper too
and has no shadow, as rig 30d said.

**The registration scan's count: 23 orphans, and the tuple holds all 23.**
`KNOWN_UNREGISTERED` is compared for **equality**, so a proof that stops being
an orphan must leave it — Run 6 removes the Studio entry when it registers
`STU-QUERY-002`, and the remaining 22 are Session 31's triage, each named with
the session that owes it. They are frozen rather than registered in a hurry: a
requirement written to make a list shorter is a requirement nobody reviewed.

**The three edits are not the three the row named** (D1557). D1541 said two
*31 released* occurrences to change to 33, plus the isolation sentence:

- **Both `31 released` occurrences are measurement CONDITIONS**, not claims
  about today. `capacity.py:260` is the `conditions` tuple of the `apg dev up`
  timing and `dev-environment.md:177` is that same measurement's prose.
  Rewriting them would state that a measurement was taken against a tree it was
  not. **Annotated, not edited**: the tree now holds 33 released and **3** in
  the example set, so a re-run applies 36, not 33 — the row's arithmetic was
  wrong in both terms.
- `docs/capacity-envelope.md` is **generated** and says *Do not edit by hand*;
  editing it directly, as the row implied, would have been undone by the next
  render. The source is `capacity.py`, and the envelope was regenerated.
- The isolation sentence was wrong in **both** halves: `ISOLATED_FIELDS` is
  **18** pointers, not fifteen, and a rendered document carries **14** roles,
  not thirteen — measured in both fixtures. `docs/project-isolation.md:86` and
  `:96` now say eighteen and fourteen and name the constant; and
  **`evidence.py:271`'s own docstring carried the stale thirteen**, which is a
  stale number in the code that nobody was grepping for.

**The `--setup-plan` line for the orphan.** With `APG_LIVE_HOST=1` and
`APG_PROJECT_A_OUTPUTS` set, the repaired proof is **planned, not skipped**,
with its whole fixture chain:

```
    SETUP    M two_owners_one_relation (fixtures used: api_call, app_base, auditor, project_a, psql, rest_base)
        tests/deployment/test_session24_studio.py::test_the_query_view_shows_the_human_their_own_rows_and_not_anothers
```

`ARRAY[]::text[]` → `ARRAY['notes:read']::text[]`, with the fixture's comment
now recording that `0011:116` refuses an empty scope set and that a stranger
who *can* read notes and still sees none of the auditor's rows is the stronger
subject. It cannot execute here; Run 7 is its first execution.

**Battery: 6 mutations, 6 killed, restoration clean — after the first pass
killed only 4, and both survivors were weak CONTROLS rather than weak guards.**

1. Flipping the shadow scan from `Store` to `Load` context still found exactly
   one hit, because the synthetic's `assert refused` is a *use* of the same
   name. The control could not tell a binding from a use. It now asserts the
   reported **line**, which only the assignment has.
2. Deleting the parameter exclusion changed nothing, because every name the
   pass-control rebound was a **fixture**, which `module_level_helpers`
   excludes one step earlier — so the exclusion was never exercised. The
   control now also rebinds a parameter sharing a plain helper's name, which is
   the only shape that exclusion exists for.

**A defect I introduced and the targeted run caught by hanging.** Renaming
`adapter` → `blocking` in `test_storage_client.py` left `adapter.release = True`
twenty lines below untouched. That test busy-waits on `Blocking.release`, so
the loop never ended and the run sat for ten minutes with no container running
and no output. **D979's rule, broken by me**: grep every reader before
repairing a name — I renamed the two lines on screen. Repaired, and the module
now runs in 0.41 s. The other four renames were checked the same way
afterwards; only this one had a reader out of view.

**Registry entries deferred to Run 6**, as D1555 already established for Run
4's: `STU-QUERY-002` and `EVD-SHAPE-001` carry `target_session: 30`, which
`test_every_entry_has_complete_metadata` refuses while `CURRENT_SESSION` is 28.
`APG_ACCEPTANCE_SESSION` would let a *targeted* run pass at 30, but CI does not
set it, so landing them now means a knowingly-red CI. The proofs exist and pass.

**Targeted:** 363 passed across `test_suite_shape`,
`test_deployment_suite_shape`, `test_deployment_module_shape`,
`test_capacity_envelope`, `test_documentation_index`, `test_evidence_claims`,
`test_acceptance_registry`, `test_api_contract_command`, `test_deployed_output`,
`test_project_agent_surface`, `test_storage_client`, `test_render_isolation`.
`ruff` clean over `bin src tests`.

### Run 6 — the bump, the registry, the gate, and the recipe the trip needs

`VERSION` **1.8.0** and `CURRENT_SESSION` **30**, in one commit with
everything the bump owes (Session 28 Run 9's shape, `session-28-
implementation-plan.md:985-1017`):

- **`src/agentic_postgres/__init__.py`**: `CURRENT_SESSION = 30` and a `#:`
  paragraph in the block above it saying **29 is skipped the way 19, 26 and
  27 are** (D1063, D1514) and naming the five requirements and five claims.
- The three remaining registry entries and claims (`OPS-EXEC-001`,
  `REL-READ-002`, `CAP-COMPILE-001`; `exec_discipline`,
  `release_reading_ref`, `contract_compile_output` in `OFFLINE_CLAIMS`),
  node ids read from `pytest --collect-only -q` (D1236), `REL-READ-001`'s
  node id moved (if Run 4 could not).
- **`apg generate` regenerated and committed** (D1238): `templateVersion`
  `1.8.0` in the example client; `generate --check` exit 0.
- **Both release pages gain a `1.8.0` row** (`docs/upgrade-guide.md` and
  `docs/operator-guide.md` are `RELEASE_PAGES`; ADR 0209's guard is red
  otherwise). The row's text: *a container-exec discipline (ADR 0218),
  `release-reading --ref`, `compile --output`, two suite guards; no
  migration; a redeploy recreates nothing whose mount did not move*.
- **`bin/session-30-check.sh`**, derived from `bin/session-28-check.sh` by
  diff (D1482, D1488): `readonly SESSION=30`; the header and usage block
  **rewritten whole**; `--mode offline` names the four offline claims and
  writes `evidence/session-30-offline.json`; `--mode host` names
  `studio_tenant_read` and says `--redeploy-before-file` is given on THIS
  trip; the `--kit-dir` paragraph still says `kit-2026-09-11` (D1282);
  `run_suite "p0 and not future and not live_host and not external"` verbatim
  (D1242); `SHELL_COMMANDS` gains it (`test_cli_contract.py:42`); `chmod 755`
  before `git add` (D1188). **`tests/contract/test_session_thirty_gate_
  modes.py`** copied from `test_session_twenty_eight_gate_modes.py` with the
  offline claim list, the session literals, and `test_no_gate_exists_for_
  the_two_sessions_that_registered_nothing` rewritten for **one** session,
  29 (the `28` file keeps its own). The `--rotated-jwt-from-file` paragraph
  stays.
- Derived documents: `python bin/render-acceptance-matrix.py --write`,
  `python bin/render-config.py --bounds-doc --write`, `python bin/render-mcp-
  catalog.py --write`, `python bin/render-evaluation-report.py --write`,
  `bin/app-contract.sh --check`, `bin/mcp-contract.sh check`, `bin/apg.sh
  generate --check --project project.example.yaml`. No `freeze-lock` (no
  migration).
- **The price, read not chosen** (D704): render `project.example.yaml` from
  `8c61309` in a throwaway worktree and from the bump commit; `bin/upgrade.sh
  plan --project <fixture> --candidate … --json` → expect `bump minor`,
  `requires patch` or `minor`, `OK`, `reasons []`, **one leaf**
  (`template_version`). A `major` is §9's stop.
- **The redeploy-before recipe (D1547)**, written into Sheet A2 of the
  appendix from `tests/deployment/test_session11_operations.py:355-430` and
  the two `--help`s it names — the exact commands, the file's two fields,
  and the cleanup line — **before** the push.
- `bin/apg.sh release-reading` on the bump commit, quoted in the Done
  (expect `tag_is_owed`, `1.8.0`, last tag `1.7.0`).

**`bin/session-01-check.sh` runs once, on a clean tree** (commit, gate,
repair, commit, gate again — Session 28 needed three commits for this), then
**`bin/session-30-check.sh --mode offline`** writes
`evidence/session-30-offline.json` carrying the four new offline claims plus
the thirteen inherited, every one `passed`. Then `git diff --stat` against
this run's list, one line each, **before** the push (D1116). Then CI by full
SHA. **And then nothing** — no tag. Run 7 deploys this commit, sweeps, and
tags it (D1425).

**Done.** _(the plan's verdict and leaf; the offline half's claim table;
the gate's numbers; the recipe as written into Sheet A2; the reading.)_

### Run 7 — the trip: deploy, one sweep with the redeploy declared, the tag

**Before the day** (agent, offline): read `docs/plans/session-29-
implementation-plan.md` §9 and its Appendix, `docs/upgrade-guide.md` §3
(steps 1–7), `docs/operator-guide.md` §12 *If something goes wrong* (D977);
`pytest --setup-plan` for `test_session24_studio.py`, `test_session11_
operations.py` (with `APG_REDEPLOY_BEFORE_FILE` pointing at a two-field JSON
in the scratchpad) and `test_session28_retention.py` with the variables set
(D671, D676), outputs kept; CI green on the bump commit by full SHA; host
scripts staged under `/home/op` derived from `s29-*.sh` (read each first; the
`EXPECTED=` SHA, the session number, the gate name; **`s29-renders.sh` or its
Session 25 ancestor renders all FOUR** — D1507); the external script in WSL
derived from Session 29's with an ephemeral `ssh-agent` and `--ssh-destination
op@62.238.99.122` (D466); WSL's outbound TCP probed on the day (a `/dev/tcp`
connect timed inside the script — CLAUDE.md §1).

**The day, in order.** `op` steps are the agent's over SSH; **`sudo` steps
are the operator's**, on Sheets A1–A4 in the appendix, **one sheet per
outcome, read before the next is issued** (D1510):

1. *(op)* Transport: `git bundle create /tmp/apg-<sha12>.bundle main`, `scp`,
   on the host `git bundle verify`, `git fetch <bundle> main`, **`git
   rev-parse FETCH_HEAD` equal to the pushed SHA before the checkout**,
   `git checkout -B main FETCH_HEAD`, `cat VERSION` → `1.8.0`, porcelain 0;
   `uv pip sync` **only if** `git diff --stat 8c61309..HEAD -- requirements-
   dev.txt requirements-dev.in .python-version` is non-empty (D1491). Then
   the four renders as `op` (`--render-only`, no root): `project.alpha.yaml`,
   `project.beta.yaml`, `project.example.yaml`, `project.second.example.yaml`.
2. *(Sheet A1)* the reads: `upgrade.sh check` both projects; `upgrade.sh plan
   … --candidate .generated/<key>/outputs.json --json` both (expect `bump
   minor`, `OK`, one leaf); `doctor.sh` both (11 ok; **the mirror check
   reads what Run 1 left**); `fleet.sh`; `backup.sh … info` alpha (a full
   exists); `dr-kit.sh export … --output /home/op/kit-<date>-pre` (the
   operational obligation; the GATE's `--kit-dir` stays `kit-2026-09-11`).
3. *(Sheet A2)* **the redeploy-before file, then alpha's deploy**: the
   recipe Run 6 wrote (a sentinel note on alpha; `/root/s30-redeploy-
   before.json` with `sentinel_title` and the CURRENT `generation_id`);
   `sudo ./deploy.sh --host host.yaml --project project.alpha.yaml
   --capabilities capabilities.yaml --through-session 30` — **nothing after
   it**, under `script -q -e -c '…' /home/op/s30-deploy-alpha.txt`. Expect
   exit 0, **step 6 applies nothing** (the ledger stays 33), auth/storage/mcp
   NOT recreated (their mounts did not move — read `docker ps` ages), step
   7's document naming the new commit and `deployed_through_session 30`.
4. *(Sheet A3)* beta the same (ledger stays 35).
5. *(op)* op-owned copies fetched after *(sudo)* `install -o op -g op -m 0600
   … /home/op/<key>-dev-outputs.json` for both (D1494/D1506: absolute paths,
   the `-dev-` pair only).
6. *(Sheet A4)* **the one sweep**: `sudo bin/session-30-check.sh --mode host
   --host host.yaml --project-a-outputs /etc/agentic-postgres/projects/alpha-
   dev/outputs.json --project-b-outputs …/beta-dev/outputs.json --admin-
   password-file /root/alpha-dev-administrator --sentinel-file "$(…derived…)"
   --redeploy-before-file /root/s30-redeploy-before.json --kit-dir
   /home/op/kit-2026-09-11 --fresh-host-outputs /home/op/snippets-dev-
   outputs.json --replacement-host-outputs … --replacement-bootstrap-state …
   --restore-evidence-file … --rehearsal-evidence-dir … --removed-project-
   file …` — every declaration `--help` lists **except** the `--rotated-*`
   three (nothing has been rotated yet) and `--dx-record-file` (no person
   walked) and `--after-reboot` (no reboot). **Detached**: `setsid nohup
   bash /home/op/g30-host.sh > /dev/null 2>&1 < /dev/null &` with the exit
   code written to a file by the script. ~15 min. Expected: `studio_tenant_
   read` **passed** (first execution of the orphan); `deployment_
   convergence` **passed** (first time ever — both DEP-002 proofs executed:
   the sentinel row survived and the generation moved); the mirror
   preflight in the gate (`:1030-1060`'s shape) satisfied by Run 1's copy;
   every Session 28 host claim unchanged. If a proof FAILS: read it; an
   instrument repaired in the window (Session 29's rule) and re-run with
   `-k` (writes no evidence), then the sweep once more only if a claim's
   reading changed; a product defect **recorded and left**.
7. *(op, then the workstation)* the host half copied to WSL; `--mode
   external` from WSL; the merge: `python bin/write-session-evidence.py
   --session 30 --host-input evidence/session-30-host.json --external-input
   evidence/session-30-external.json --offline-input evidence/session-30-
   offline.json --output evidence/session-30.json`. Expected: **134 claims;
   `not_run` 4** (the rotation trio, `replacement_host_restore`); **`failed`
   1** (`documented_path`); exit 5 for those reasons and no other.
8. **The tag** (D1425, ADR 0219's first use): on the workstation, `bin/apg.sh
   release-reading --ref <the deployed SHA>` quoted; `git tag -a 1.8.0 <the
   deployed SHA>`; `git push origin 1.8.0`; `git ls-tree -r --name-only 1.8.0
   -- docs/ | grep -E "upgrade-guide|operator-guide"` prints both.
9. The sentinel note swept (Sheet A4's last line); the post kit exported;
   D rows for what the day found; this run **Done.** with the claim table,
   the two `upgrade plan` verdicts, the two ledgers, the container ages,
   `mirror-state.json`'s `last_copied_at` on both.

**Done.** _(as above.)_

### Run 8 — the rotation, alpha then beta, on its own day

**This run performs the signing-key rotation for the first time on this
deployment** (D860, D1533). It is **Appendix R of `docs/plans/session-28-
implementation-plan.md` verbatim**, with `docs/operator-guide.md` §15 as
the operator's copy; this plan's Sheets B (alpha) and C (beta) are that
appendix's numbering with the paths filled in, and **nothing else is on
them** (D1510: no other rotation, no sweep, no deploy that is not one of
the rotation's own three).

**What it moves, said at the top of both sheets**: one node id of nine
(`test_a_rotated_signing_key_is_the_only_one_the_plane_accepts`, part of
`bootstrap_identity`); it closes **no claim** (D1469, D1496); the three
claims stay `not_run` in `evidence/session-30.json` with the remaining
rotations named (§7). **The retired key's JWK, captured at step 0.1, is
kept at `/home/op/s30-retired-<key>-jwk.json`** so a later sweep can pass
`--rotated-jwt-from-file` — that sweep is not this session's.

**Before the window (agent, over SSH as `op`)**: `cat /opt/agentic-postgres/
rendered/<key>/jwks.json` captured (0444, no root); the operator's Sheet B
handed over with *Before the window* 0.2–0.4 as its first three lines and
the seven steps after; **step 0.4 (`docker inspect -f '{{.State.Pid}}'`
non-zero) before the window, not inside it** (D1477 discharged it on
2026-09-17; it is re-read because a reboot or a recreate could change
nothing and a daemon upgrade could).

**The window**: steps 1–7 as Appendix R numbers them, including **2b** (the
`acknowledge` reading before step 3 — a measurement, D1473: if it reads
clean, step 3's necessity is answered with evidence for the first time; step
3 is done anyway). `promote` asks for the literal word `PROMOTE` and refuses
at exit 6 while any verifier is behind; the deadline is 930 s from
`promote`; `retire` after it; then the last redeploy and recreate. **Alpha's
`status` reads `steady` before beta's Sheet C is issued.** Every `sudo` line
under `script -q -e -c`, never a pipe (D1501).

**After both**: `sudo bin/doctor.sh --project <key>` both (11 ok);
`bin/rotate-signing-key.sh --outputs … status` both — expect `phase steady`
and the D1475 line `promotion BLOCKED on ['mcp', 'postgrest', 'storage']`,
which is **not** a fault (Appendix R *Two lines that look like faults*);
`GET /auth/jwks.json` on both projects from the workstation shows one `kid`,
the new one. The timings recorded against Appendix R's rig numbers (each
step under a second; the recreate 3–5 s; the deploys dominate).

**If alpha's `acknowledge` comes back dirty**: Appendix R's five-point list,
verbatim; `abandon` is available until `promote` and not after.

**Done.** _(both windows' timings; step 2b's reading — the first evidence on
whether a redeploy alone recreates the verifiers; both `acknowledge` outputs;
the `kid`s before and after; where the retired JWKs are kept; what the
sheets' discipline cost.)_

### Run 9 — the close

`docs/scope-closure.md` **§23** (what Session 30 closed, left, and what
Session 31 inherits — the shape of §22); `CLAUDE.md` §2's block rewritten
(the launch folder's file — **copy it to the scratchpad first**) with
`SESSION 30 COMPLETE`, the HOST block (mirror state, the rotation performed,
kernel, doctor, `deployed_through_session 30`, `source_commit`, the tag),
the *never pipe a sudo command* fact rewritten to ADR 0218's sentence,
`NEXT SESSION 31`, next free D and ADR; §9's rows closed here **removed**;
this plan's status header rewritten; `docs/pre-stage-4-audit.md` rows
touched by this session marked (the rotation row: *performed once,
2026-09-…, closing no claim*). **No code, unless a run found a defect** —
and if it did, §9 says where that goes. Documentation only: push, no CI
read. The memory file for this project updated by the executor's own
session.

**Done.** _(one line per closed item; the numbers the next session should
not re-take.)_

---

## 7. Evidence and claims

A claim's verdict is computed from the registry's node ids and JUnit
results, never hand-entered; three statuses (ADR 0163); a skip is not a
pass; a `-k` run writes nothing; an offline claim is declared, never
inferred (ADR 0202); two live halves naming different commits do not merge
(D1510).

| Claim | Mode | Measured where | Expected at close |
|---|---|---|---|
| `exec_discipline`, `release_reading_ref`, `contract_compile_output`, `suite_shape` | offline | the gate's offline mode here (Run 6); CI | `passed` in `evidence/session-30-offline.json` and in `evidence/session-30.json` |
| `studio_tenant_read` | host | Run 7's sweep on alpha — the orphan's **first execution** | `passed` |
| `deployment_convergence` (DEP-002, Session 11) | host | Run 7's sweep with `--redeploy-before-file` — **first time the flag has been given** | `passed` (both proofs executed; the control asserts the generation moved) |
| `stage_release` | host | Run 7 | `passed` (the tree's `1.8.0` deployed before the sweep) |
| `bootstrap_identity`, `api_authorization`, `credential_rotation_planes` | host | — | **`not_run`**, and the document's `missing_node_ids` names the eight the signing-key rotation does not touch; Run 8 moves one node id and no claim |
| `documented_path` | host | — | **`failed`** (a person has not walked it; D1531) |
| `replacement_host_restore` | — | — | `not_run` by decision (D1028) |
| every claim through 28 | host / external / offline | Run 7 | unchanged |

`evidence/session-30.json` is expected at **134 claims** (129 + 5), `passed`
**129**, `not_run` **4**, `failed` **1**. A fifth `not_run` is a finding, not
a footnote; `deployment_convergence` still `not_run` means the recipe in
Sheet A2 did not produce the file the proof reads, and the row says which
field.

---

## 8. Security invariants this session touches

- **A `sudo` product command cannot be stopped by a redirect** (ADR 0218):
  no product child reads the terminal; `deploy.sh` keeps its refusal
  through a sourced function — `test_stdin_is_closed_when_no_input_is_given`,
  `test_the_scan_finds_no_docker_or_compose_subprocess_outside_the_helper`,
  the D972 deploy proof.
- **No secret value in process arguments** (D105): the helper feeds SQL and
  passwords through `input=`, never argv; `auth-admin.py`'s
  `screen_and_hash` keeps `input=password` — the argv proof asserts the
  password is not in `exec_argv`'s output.
- **The MCP runtime holds no credential**: unchanged; the helper is a
  `bin/`-side runner and is not imported by any service (grep
  `services/` for `container_exec`: none).
- **There is no public Postgres endpoint** (ADR 0044, **0216**):
  `publication()` still raises; `test_no_publication_can_be_built_at_all`
  and `test_the_override_carries_no_ports_entry_for_any_service` unchanged.
- **A second principal holds nothing an agent identity does not hold**
  (**0217**): stated, and not exercised by this session's code.
- **PostgreSQL is the final authorization authority**: `STU-QUERY-002`'s
  live proof — a stranger who CAN read `notes` sees none of the auditor's,
  and the auditor sees none of the stranger's, through Studio's forwarder
  with no policy of its own.
- **A report may not substitute an answer** (ADR 0195): `release-reading
  --ref nonesuch` exits 2 naming the ref and prints no reading; a refused
  compile leaves no file that a reader could mistake for a contract; the
  mirror diagnosis has three outcomes and Run 1 says which.
- **A revoked or rotated credential stops on the next request** (ADR 0088):
  the rotation's `retire` removes the old `kid`; `GET /auth/jwks.json` read
  after; the proof that would assert it is named and **not** claimed moved.
- **The deploy, the sweep and the tag land on one commit** (D1425): Run 7,
  in that order, and the rotation's three redeploys are of the same commit.
- **An offline claim cannot report a live half** (ADR 0202): `studio_tenant_
  read` is undeclared (D1543); the per-session assertion (D1237).

---

## 9. Stop conditions

- Run 1 finds the mirror's failure is **in the copy's own code path** (a
  `mirror.sh` exit 2/3/6, a missing secret file under the generation): stop
  and read; that is a deploy-time defect and the row is D1546's, not a
  transient — nothing on the host is edited by hand to make the copy pass.
- Rig 30a's **python control hangs** (stdin `DEVNULL` still stops under
  `use_pty`): stop; ADR 0218's decision is wrong and the repair is the guard
  on every caller after all — rewrite D1538 and this plan's Run 3 before
  writing a line of it.
- Rig 30a's **subject completes** with `use_pty` present: the mechanism is
  not reproducible on this workstation; Run 3 proceeds on D972's and D1501's
  host measurements, the ADR says *measured on the host, not reproduced
  here*, and the no-hang proof keeps its timeout.
- `test_repository_contract.py::test_no_module_is_imported_only_by_its_own_
  tests` red on Run 3's commit: the helper landed without its callers
  (D1273); the fix is the callers in the same commit, never an import to
  satisfy the scan.
- A passing test would be **weakened** to make a new one pass — including
  `test_the_command_takes_no_arguments_and_says_so` edited rather than
  replaced under ADR 0219, or `test_docker_exec_forwards_stdin` loosened.
- Rig 30c counts orphans in a **Session 31–35 module** (there are none yet)
  or more than five in total: stop; the tuple is not a place to park a
  problem that size, and the count is the operator's decision.
- Run 6's `upgrade plan` prices `1.8.0` at **major**: stop; a row; the
  operator's decision.
- The redeploy-before recipe cannot write a note through a product surface
  as an operator and the superuser path is the only one: **say so in the
  sheet** and proceed — the proof reads the row as root anyway — but record
  it as a §10 item (an operator has no documented way to write a sentinel).
- The sweep's `deployment_convergence` reads `not_run` after the flag was
  given: read `skipped_node_ids`; do not re-run the deploy to "make it
  move"; the row says which precondition the recipe missed.
- Alpha's `acknowledge` is dirty after a `down` + redeploy: Appendix R's
  list; **do not promote**; `abandon` before `promote` is free. `acknowledge`
  exits 5 naming an init pid: step 0.4 failed late — close the window with
  `abandon`, do not carry on blind.
- The rotation sheet would gain a step from another rotation, or anyone
  proposes a sweep between `promote` and `retire` (stage plan §9).
- A port, a route or a non-loopback bind for any reason (ADR 0216).
- WSL has lost outbound TCP on trip day: SSH still works through Git's ssh
  (CLAUDE.md §1); the external half **must** run from WSL and a dead WSL
  network strands it — a Windows reboot first, early.
- CI red on a code commit: stop and read; a cancelled run is not a failed
  one (D1059).

---

## 10. Open items this session carries and creates

**Carried in, untouched, each still true:** D1045 (the provider's error
body — the owner's); `replacement_host_restore` (D1028); D1375 (`op` and the
Docker socket, by decision); the 21 unclaimed requirements (one declaration
at a time); D976, D688, D771, D340, D466, D540, D942, D1203, D1205, D1211;
the Infisical control-plane identity's org admin; `process-max` 1 (D593);
`documented_path` **failed** until a person walks it (Session 35 arranges);
the three rotations this session does not perform — the authenticator
password (`APG_ROTATED_AUTHENTICATOR_FROM_FILE`), the docs Basic Auth
password (`APG_ROTATED_DOCS_FROM_FILE`), the application credential on both
projects (`APG_ROTATED_FROM_FILE`) — each a provider replacement plus a
redeploy, each its own sheet.

**Recorded here, by the stage plan's instruction, and not built:**

| Item | Note |
|---|---|
| **`apg-diag` has no lifetime, expiry or rotation** (D1528) | ADR 0071's standing read-only account; `provision-host.sh` does not create it. Deferred with hosting (D1517): a grant with a lifetime presupposes a grantor who is not the operator. |
| **`apg-diag` cannot read `auth`, `storage` or `mcp` logs** (D380) | The allowlist is six services. Session 34 widens it by one service with a test if the connector route's log must be readable by the agent account. |
| **`--rotated-from-file` is accepted by the gate and undocumented in its usage block** | Found while reading `session-28-check.sh:627-631` against `:279-280`. The 30 gate inherits it; Session 31's derivation adds the line. |
| **The retired signing key's JWK is kept on the host and no sweep has read it** | `/home/op/s30-retired-<key>-jwk.json` after Run 8; the sweep that passes `--rotated-jwt-from-file` moves one node id and belongs to the session that performs the other three rotations. |
| **An operator CAN write a sentinel row and cannot remove one** | D1547, answered in Run 6 and half-open. `bin/dev-token.sh --role authenticated -- bin/api.sh create-note --title …` writes it through the product's own surface and is now Sheet A2's step 2. There is **no `delete-note`**, and a human may not run SQL through a product surface, so Sheet A4's cleanup is a root `docker exec … psql -c DELETE` — outside every product surface, on a production cluster, typed by a person. A trip that re-takes `deployment_convergence` every time leaves a row behind every time unless somebody does that. Session 31's, if the claim is to be routine. |
| **Twenty-four session gates exit 1 at step 1** | D1564. `deploy.sh` has sourced `bin/lib/tty-guard.sh` since Run 3, and `shellcheck deploy.sh bin/*.sh libexec/*` — the line in every gate from `session-02-check.sh` to `session-28-check.sh` — emits SC1091 and exits 1 because the sourced file is not among its inputs. `session-01-check.sh` and `session-30-check.sh` carry `bin/lib/*.sh` and are clean. The repair is one word per file; the question is whether twenty-four released gates should be edited at all, and it is the operator's. Until then, an old gate re-run for any reason fails at step 1 with a message about a library that is not the reason anybody ran it. |
| **ADR 0162 prices no row for a command gaining an option** | D1561. Its eight rows each name something a RENDERED DOCUMENT shows, so `release-reading --ref` and `compile --output` price as *implementation only* — a **patch** — and `upgrade plan` said exactly that while `VERSION` moved a minor. The verdict is right about what the upgrade costs an operator and silent about what the release added. A row saying an option is priced by hand, or a decision that it is always a patch, belongs to the session that next adds one. |
| **`KNOWN_UNREGISTERED`** (if non-empty) | Each entry names its session; the tuple shrinks only. |
| **The mirror's per-pass transport flake is upstream and no repair here removes it** | D1546: one object per pass fails `ContentLength=<n> with Body length 0` reading from R2, ~1 in 3,700, on roughly every other pass. D1549's repair makes the verb report it correctly; it does not stop it. If the rate rises, the reading is `mc`'s line in the unit's journal, which `apg-diag`'s allowlist does not cover (D380's neighbourhood). Nobody has asked Cloudflare or Backblaze which side truncates. |

**Created here, for Session 31:** every container exec goes through
`container_exec` — Session 31's `capacity_reading.py` reads `/proc/meminfo`
and `df` directly and execs nothing, but its doctor verbs do; the mirror's
state after Run 1 is the number `doctor capacity|usage` starts from;
`deployment_convergence` is now a claim every trip can re-take by writing one
file; `release-reading --ref` is the tag procedure and the worktree is
retired from the operator guide.

---

## Appendix — what to consult, how a run is executed here, and the sheets

**Consult, in this order:** this plan's §1 and §5. The stage plan's §5
*Session 30*, §8, §9, §11. `docs/plans/session-29-implementation-plan.md`
§9, its Appendix (the sheet's shape: `#`, run, line, what it must print),
D1501 (`script(1)`), D1506 (the three `-dev-outputs.json` files and which
two are this host), D1507 (four renders), D1510 (one sheet, one outcome).
`docs/plans/session-28-implementation-plan.md` Appendix R and
`docs/operator-guide.md` §15 (the rotation). `docs/upgrade-guide.md` §3
(transport, renders, plan, deploy, read). ADR 0195 before writing any
reader; 0215 before the rotation; 0218 (this session's) before touching any
exec site.

**How a run is executed here** (CLAUDE.md §1 and §5, the parts that bite):
the Bash tool is Git Bash; every WSL command is `wsl bash -lc "cd
~/projects/agentic-postgres && . .venv/bin/activate && …"`; anything with a
loop, a quote inside a quote or a `$` goes in a script file written with the
Write tool to `\\wsl$\Ubuntu\tmp\` and run with its output redirected to a
file that is `rm`'d first; **never pipe a gate into `tail`**; a long gate
runs detached with its exit code written from inside; `chmod 755 bin/*.sh
bin/*.py deploy.sh` before every `git add`; commit messages from a file with
`-F`; `PYTHONDONTWRITEBYTECODE=1` and `__pycache__` cleared before a battery;
restore by copy and `cmp`, never `git checkout --`; every anchor pre-flighted
to match exactly once and a miss fatal; a mutation is evidence only beside a
control it cannot reach, in the same invocation; assert HOW each mutation
failed. **A `sudo` line on any sheet has nothing after it**, and the sheet
is grepped for `|`, `>`, `$(` and `&` on every `sudo` product line before it
is handed over (D1505's rule, until ADR 0218 lands on the host — and after,
because `deploy.sh` still refuses the shape by design).

### Sheet 0 — Run 1, the mirror (one sheet, one outcome)

Every line typed by a human at a TTY on the host as `op`, with `sudo` where
marked. `OUT_A=/etc/agentic-postgres/projects/alpha-dev/outputs.json`,
`OUT_B=…/beta-dev/outputs.json` — absolute, the deployment's own (D1506).

| # | Line | What it must print |
|---|---|---|
| 1 | `systemctl list-units --failed --no-pager` | three units: `cloud-init-hotplugd.service`, `agentic-postgres-backup-mirror@alpha-dev.service`, `@beta-dev.service` — a fourth is a finding |
| 2 | `journalctl -u agentic-postgres-backup-mirror@alpha-dev.service --no-pager --since 2026-09-17 -n 200` | the `mc` line that failed at 04:50 — **write it down verbatim** |
| 3 | the same for `@beta-dev` | the line at 04:38 |
| 4 | `sudo iptables -S DOCKER-USER` | **expect no line containing `apg-rehearsal`**; if one is present, its full text is the finding (D1546's first outcome) |
| 5 | `sudo cat /etc/agentic-postgres/projects/alpha-dev/mirror-state.json` | `last_copied_at` `2026-09-17T04:37:13Z`, objects 3718 |
| 6 | `curl -sS -o /dev/null -w '%{http_code}\n' https://<BACKUP_MIRROR_ENDPOINT from the rendered .env or the document>/` | an HTTP status — the host reaches the provider (the control for outcome 1) |
| 7 | **only if 4 found a rule:** `sudo iptables -L DOCKER-USER --line-numbers`, then `sudo iptables -D DOCKER-USER <n>` for each `apg-rehearsal` line, highest number first | the rule gone on a re-read of 4 |
| 8 | `script -q -e -c "sudo bin/backup.sh --outputs ${OUT_A} mirror" /home/op/s30-mirror-alpha.txt` | **nothing after the sudo inside the quotes**; the copy's own exit line; then `sudo cat …/alpha-dev/mirror-state.json` shows today's `last_copied_at` |
| 9 | the same for beta | — |
| 10 | `sudo systemctl reset-failed agentic-postgres-backup-mirror@alpha-dev.service agentic-postgres-backup-mirror@beta-dev.service` | — |
| 11 | `systemctl is-system-running` | still `degraded` — `cloud-init-hotplugd` (D1503); `systemctl list-units --failed` now shows that one alone |

If 8 fails: the `mc` line decides between outcome 2 (credential — the
owner's, at the provider; nothing more on this sheet) and a network error
that survived 7 (stop; record; do not retry in a loop).

### Sheets A1–A4 — Run 7 (four sheets, four outcomes)

**A1 — the reads** (all `sudo`; write each reading down):
`bin/upgrade.sh check --project alpha-dev` → both versions the installed
one, `verdict OK`; `bin/upgrade.sh plan --project alpha-dev --candidate
/home/op/agentic-postgres/.generated/alpha-dev/outputs.json --json` → `bump
minor`, `OK`, `reasons []`, one leaf `template_version`; the same for
`beta-dev`; `bin/doctor.sh --project alpha-dev` and `beta-dev` → 11 ok, the
mirror line reading today's copy; `bin/fleet.sh` → 2 projects; `bin/backup.sh
--outputs ${OUT_A} info` → a full exists; `bin/dr-kit.sh export … --output
/home/op/kit-<date>-pre …` (the exact line from `bin/dr-kit.sh --help` on the
host, printed on the sheet by the agent).

**A2 — the sentinel, then alpha** (`sudo`). **Written in Run 6 from the
proof that reads the file** (`tests/deployment/test_session11_operations.py:
355-430`) **and the two `--help` pages it needs**, never from memory. Steps
1–5 produce the file the sweep's `--redeploy-before-file` reads; step 6 is
the deploy and **has nothing after it**. `OUT_A` below is
`/etc/agentic-postgres/projects/alpha-dev/outputs.json`, typed in full.

**If any of steps 1–5 does not print what it must, STOP and do not run step
6.** The file is read at the SWEEP and not at the deploy, so a deploy taken
without it cannot be turned into one that had it; the only repair is another
deploy, and §9 says not to take one to make a claim move.

1. **The title, chosen once and written on this sheet**, with the trip's own
   date so that a second trip cannot count the first one's row:

       s30-redeploy-sentinel-<YYYY-MM-DD>

2. **The row, through the product's own surface** (D1114). `api.create_note`
   derives ownership from the request identity, which is why it is an RPC and
   not a table write; the token reaches `api.sh` through the environment and
   through nothing else, and no option prints it:

       sudo bin/dev-token.sh --project-outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json --role authenticated --ttl-seconds 120 -- bin/api.sh --project-outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json create-note --title s30-redeploy-sentinel-<YYYY-MM-DD>

   Must print the created note as JSON carrying **that exact `title`**. The
   proof counts `app.notes WHERE title = '<sentinel_title>'` and expects
   **1**, so a second run of this line breaks the proof rather than helping
   it.

3. **The generation that is active NOW**, before the deploy:

       sudo cat /var/lib/agentic-postgres/secrets/alpha-dev/active-secret-generation.json

   Write the `generation_id` on the sheet. **This is the control's whole
   subject**: a deploy that did nothing preserves every row perfectly, so the
   proof that the redeploy RAN is that this id is *different* afterwards
   (D509).

4. **The file**, root-owned, 0600, with exactly the two fields the proof
   reads — it asserts each is truthy and **fails the fixture rather than
   skipping** when one is missing:

       sudo python3 -c 'import json,pathlib; p=pathlib.Path("/root/s30-redeploy-before.json"); p.write_text(json.dumps({"sentinel_title":"s30-redeploy-sentinel-<YYYY-MM-DD>","generation_id":"<the id from step 3>"})); p.chmod(0o600)'

5. **Read it back**, because step 4 wrote it and nothing has checked it:

       sudo cat /root/s30-redeploy-before.json

   Both fields present and non-empty, the title byte-for-byte the one step 2
   printed.

6. **The deploy**, at the terminal, **nothing after this line**:

       script -q -e -c "sudo ./deploy.sh --host host.yaml --project project.alpha.yaml --capabilities capabilities.yaml --through-session 30" /home/op/s30-deploy-alpha.txt

   → exit 0.

Then the reads: `sudo bin/migrate.sh --project project.alpha.yaml --runtime
status` **at the terminal, nothing after it** → 33 `[X]`, `Pending: 0`
(**unchanged — this release adds no migration**); `sudo docker ps --format
'{{.Names}} {{.Status}}' --filter label=apg.project.key=alpha-dev` → **no
container younger than the deploy** (ADR 0155: no mount moved); `sudo
bin/doctor.sh --project alpha-dev` → 11 ok.

**A3 — beta** the same with `project.beta.yaml`; ledger 33 + 2, `Pending:
0` twice.

**A4 — the sweep**: `sudo install -o op -g op -m 0600 /etc/agentic-
postgres/projects/alpha-dev/outputs.json /home/op/alpha-dev-outputs.json`
and beta; the agent confirms both name the new `source_commit` **before**
this line is issued (D1510): `setsid nohup bash /home/op/g30-host.sh
> /dev/null 2>&1 < /dev/null &` (the script holds the full `session-30-
check.sh --mode host` line from Run 7 step 6, every path absolute); ~15 min;
`cat /home/op/g30-host.exit` → 0 or 5; then **the sentinel row removed**,
which takes two lines because **no product surface deletes a note** —
`bin/api.sh` has `create-note` and no counterpart, and a human may not run SQL
through a product surface, so the removal is the superuser's, exactly as the
proof's own `psql` fixture reads it (§10 carries the gap):

    sudo python3 -c 'import json; d=json.load(open("/etc/agentic-postgres/projects/alpha-dev/outputs.json"))["database"]; print(d["container"], d["name"])'
    sudo docker exec <container> psql -U postgres -d <name> -X -c "DELETE FROM app.notes WHERE title = 's30-redeploy-sentinel-<YYYY-MM-DD>'"

**No `-i`** on that `docker exec`: the statement is in the argv, nothing is
fed on stdin, and `-i` would leave the child holding the terminal — which is
ADR 0218's whole subject. The names are read from the deployed document rather
than derived from a label, because the document is what the proof reads
(`document["database"]["container"]`). Expect `DELETE 1`. Then `bin/dr-kit.sh
export … --output /home/op/kit-<date>-post`.

### Sheets B and C — Run 8, the rotation (alpha; then beta after alpha reads `steady`)

**At the top of each sheet, in these words:** *This rotation moves one node
id of nine and closes no claim (D1469). Nothing on this sheet is another
rotation. No sweep runs between `promote` and `retire`.*
`OUT=/home/op/<key>-dev-outputs.json` (the current pair, D1494).

| # | Who | Line | What it must print |
|---|---|---|---|
| 0.1 | agent | `cat /opt/agentic-postgres/rendered/<key>/jwks.json` → saved as `/home/op/s30-retired-<key>-jwk.json` (the object whose `kid` is active) | the retiring key's JWK, kept |
| 0.2 | sudo | `sudo bin/rotate-signing-key.sh --outputs ${OUT} status` | `phase steady -- one key, nothing in flight`; `acknowledged nothing has been asked`. **Anything else: stop** |
| 0.3 | sudo | `sudo bin/doctor.sh --project <key>` | 11 ok — the reading the window is measured against |
| 0.4 | sudo | `sudo docker inspect -f '{{.State.Pid}}' <any container of the project>` | **a non-zero number** (ADR 0215; D1477) |
| 1 | operator, at the provider | `openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -outform PEM` → pasted into `APG_AUTH_JWT_PREPARED_KEY` at `/auth` for this project | no command here writes a provider value (D249) |
| 2 | sudo | redeploy (the A2 line with this project's manifest), under `script` | `render-jwks` prints *the key set CHANGED* — or *cannot be told from here* (both normal; step 4 answers) |
| 2b | sudo | `sudo bin/rotate-signing-key.sh --outputs ${OUT} acknowledge` | **a measurement** (D1473): three lines; write down whether each reads `holds the published set` or is behind — the first evidence on whether a redeploy alone recreates the verifiers. **Do step 3 anyway** |
| 3 | sudo | `sudo bin/project-runtime.sh --host host.yaml --project-key <key> --through-session 30 down`, then the redeploy | a restart is not enough |
| 4 | sudo | `acknowledge` again | **three** lines `holds the published set`: `postgrest`, `storage`, `mcp` (D1472; `auth` is the issuer, ADR 0098). Dirty: Appendix R's list; **do not promote** |
| 5 | sudo | `sudo bin/rotate-signing-key.sh --outputs ${OUT} promote` → types `PROMOTE` | irreversible; exit 6 if any verifier is behind |
| 6 | operator, then sudo | the prepared value moved to `APG_AUTH_JWT_SIGNING_KEY`, `APG_AUTH_JWT_PREPARED_KEY` **cleared**, redeploy, `down` + redeploy | **nothing else redeploys this project between 5 and 6** (D1474) |
| 7 | sudo | after `retire_after` (930 s from 5): `retire`, then redeploy and `down` + redeploy | `status` → `phase steady` and the D1475 line, which is not a fault |
| 8 | agent | `curl -sS https://<the project's auth route>/auth/jwks.json` | one `kid`, not the retired one |

**Read before the day** (D977): `docs/operator-guide.md` §15 whole,
`docs/plans/session-28-implementation-plan.md` Appendix R whole, `docs/
upgrade-guide.md` §6 and §7, `docs/operator-guide.md` §12.

**If something is wrong that this plan did not anticipate**, the rule is
§9's: record it; nothing is repaired inside a window that can be repaired
after it, and a release is not re-cut in a maintenance window.
