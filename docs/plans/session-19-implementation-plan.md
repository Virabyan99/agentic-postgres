# Session 19 — The repair session

**Status:** planned and executed 2026-09-10, after Session 18 closed at
`52c534c` with `evidence/session-18.json` reporting 93 passed / 8 `not_run` /
0 failed of 101, and the `1.0.0` tag on `054f54e`.
**Brief:** `FINDINGS.md`, an adopter's account of building an application on
1.0.0 on a host that started empty. Twenty-five entries; nineteen are defects
in the shipped release.
**Shape:** seven runs, no host trip. Runs 1–7 are offline and green in CI.
**Product version at close:** unchanged at `1.0.0` in the tree;
`CURRENT_SESSION` stays 18. This session repairs a release rather than
building one, and the release it produces is `1.0.1`.

---

## 0. Where the session starts

Stage 2 closed and the artefact went out. Then somebody who had not built it
used it.

The Stage 3 decision report predicted the shape of what that would find:
*"An insider found five; an outsider would find more."* It found twenty-five,
of which nineteen are defects in 1.0.0, five are the tenant extension point
(Stage 3's subject) and one belongs to the application's author.

Two things make this session different from every one before it. It is the
first whose brief comes from outside the project, and it is the first that
repairs rather than builds — so its divergence rows record what the tree
*said* against what an outsider *measured*, and its runs end in repairs rather
than in new surface.

The ordering argument is that none of these get better by building Stage 3 on
top of them, three convert a recoverable situation into a much worse one, and
one had been silently disabling this repository's central invariant since
migration `0004`.

---

## 1. Divergences

D1033–D1059. Rows marked **open** are recorded and not repaired here, with the
reason in the last column.

| D | Said | Measured or read | This session | Why it matters | ADR |
|---|---|---|---|---|---|
| **D1033** | A user adopting a product at 1.0.0 checks out the version tag. | The `1.0.0` tag is `054f54e`, and all four documented-path repairs (`b60814b`, `2e82f46`, `04d71c7`, `e49c5aa`) land *after* it. D1023–D1025 are live for anyone who trusts the only ref they have reason to trust. | Cut `1.0.1` from a repaired `main`. Not a documentation fix. | The first thing a new adopter touches, and it is wrong. The two claims that would have caught it are the two left `not_run`. | — |
| **D1034** | `.gitignore`'s comment: individual names, because *"a glob would silently hide a future project.third.example.yaml"*. | Sound reasoning, wrong consequence. `host.yaml` and `capabilities.yaml` are ignored generically; project manifests by name, and the only names are this operator's. Any adopter's manifest is untracked, the gate fails on any untracked file, and a dirty release makes a deploy refuse (D971). | `/project.yaml`, `/project.*.yaml`, `!/project.*example.yaml`. Measured with `git check-ignore --no-index`, not reasoned: `*.example.yaml` cannot match `project.example.yaml`, and `/project.*.yaml` does not match `project.yaml`. | The first act of adopting this product was to fork it and edit a file upstream conflicts on at every merge. | — |
| **D1035** | `README.md` §Rendering: `cp project.example.yaml project.yaml`. | The product's own quick-start creates a file that fails the product's own gate at step 1. | Closes with D1034. | A quick-start whose first command must not be taken literally is worse than none. | — |
| **D1036** | `test_api_migrations.py` enforces ADR 0050: nothing exists in `api` which the contract does not name. | `_CREATE_FUNCTION` accepts `OR REPLACE`; `_CREATE_VIEW` did not. `0004` creates both views with `OR REPLACE`; the reader saw the surface only because `0007` recreates them bare. A view added with `OR REPLACE` is absent from `final_surface`, so the equality **holds** while an unreviewed view is published. | The view pattern matches the function pattern, plus a guard that the two accept the same forms. | The invariant this module exists for was one keyword from unenforced, and nothing could report it. Found from the opposite direction by luck. | — |
| **D1037** | Six contract fixtures stand a cluster up. | Five call `build_statements()`; `test_auth_endpoints.py` reimplements the bootstrap and stops one statement short of `CREATE EXTENSION vector`. `CREATE EXTENSION` appeared nowhere under `tests/`. | The line, plus a class guard: no fixture creates the `extensions` schema without the extension. | Zero cost for thirty migrations, then 88 errors in a file about authentication, naming vectors nowhere. §5.4 invites the migration that breaks it. | — |
| **D1038** | `test_the_reader_is_not_vacuous` hardcodes `{"notes","tasks"}` as the whole published surface, deliberately, so an empty scrape cannot agree with an empty contract. | The reasoning holds. The consequence is that the platform's *example* domain is frozen as the *entire* surface, so an adopter edits a test to name their own tables. | **Open.** Loosening to containment is what the non-negotiables call weakening, and the ADR it needs is Stage 3's tenant-extension question. Correct in this repository today; costs only an adopter. | One of four faces of one structural fact. | — |
| **D1039** | `api-contract.sh --check`: *"either the migration has not shipped, or its grants keep it out of the document"*. | An adopter hit neither. The migration had shipped and the grants were right; the snapshot predated the surface. `--update` reads a **deployed** document, so on a first bring-up the check is *unsatisfiable*, not unsatisfied. | A third clause naming the stale snapshot and the remedy. The structural half is Stage 3's. | *"I have made a mistake"* and *"this cannot be done yet"* are different states and only the message can distinguish them. | — |
| **D1040** | The facts about adding a table exist in §5.4, in the contract's header, and in `--help`. | Nowhere are they collected into the sequence an adopter performs. Six places, one of which cannot be edited without a running host. | README, *Adding your own tables*, with the snapshot's ordering stated in advance. | The `documented_path` claim's content: the product documents deploying *its* domain, and adopting it means deploying *yours*. | 0197 |
| **D1041** | `test_a_cancelled_caller_whose_hash_is_running_keeps_its_permit_until_it_finishes` proves the permit follows the thread (ADR 0082). | Nothing synchronises the read against the hash *finishing*. Under CPU contention the hash completes, the permit is legitimately released, and the test asserts *"the permit was released while the hash was still resident"* — naming the defect it exists to catch. Failed in a full gate run, passed 3/3 alone, same machine, same commit. | `_BlockingHasher` holds the worker until the test releases it, with its own control asserting the barrier still blocks. | An insider on an idle workstation never sees it. It appears when the machine is busy, which is what CI and a first bring-up both look like. | 0195 |
| **D1042** | `timer_is_armed` guards the two steps that can lock an operator out of their own host. | `systemctl … \| grep -q` under `set -o pipefail` is a SIGPIPE race: **TRUE=19, FALSE=1 of 20** against an armed timer. Six more of the shape in the same file — and `ss \| grep -qE ':(2375\|2376)'` fails toward reporting `no Docker TCP socket` on a host where one is listening. | Capture, don't pipe, at every site; a guard over the class. Proof runs the predicate 30× under `pipefail` against a producer that writes after the match, with the 1.0.0 form as a control. | The only instance whose direction was unsafe was found by sweeping, not by being reported. | 0195 |
| **D1043** | `--apply` prints `systemctl list-timers <unit>'*'` as the verification step. | systemctl pages through `less` on a TTY, and everything with `sudo` here is driven over `ssh -tt`. Measured: blocked over two minutes with a ten-minute rollback timer armed and `--apply` never reached. | `--no-pager` at both sites and in `docs/backup-operations.md`, with a guard over every printed `systemctl list-timers`. | A human presses `q`. Anything driving the procedure hangs at the worst moment this product has. | — |
| **D1044** | `docs/host-baseline.md`: do not run the gate under `sudo`, it leaves root-owned artifacts. | The advice cannot be followed for `provision-host.sh`, which requires root. `__pycache__/` is ignored so the gate never sees them, while re-checking-out the release as the operator fails with `Permission denied`. | `export PYTHONDONTWRITEBYTECODE=1`. | The remedy (`sudo rm -rf`) is written down nowhere, and a fix-and-redeploy cycle needs exactly that checkout. | — |
| **D1045** | `_call`'s comment: the body is withheld because *"on identity endpoints it can echo the request, and this message reaches a log"*. | The provider had answered precisely — *"identity limit reached"* — and the tooling printed `HTTP 400`. 25 minutes of API archaeology plus a wrong turn into the payload shape. | **Open.** Relaxing "no bodies" to "no raw bodies" is a security decision in a credential path and belongs to the owner, not to a diagnosability fix. | Without the body the obvious hypotheses are all wrong and all expensive. | — |
| **D1046** | `--apply` records what it owns in `bootstrap-state.json`. | It writes the state only at the end, because `validate_state` needs a complete document. A failure after the project was created left an orphan nothing recorded; `--plan` then proposed creating what existed, and `--adopt` binds by ID (ADR 0189) so an unrecorded ID cannot be handed to it. | The run prints what it created, with IDs and the remedy. Incremental state is a schema decision, not a repair. | The failure is not idempotent and the recovery tool cannot see what the failure left. | — |
| **D1047** | `edge.initial_acme_environment: staging` is what this product recommends. | So the documented, recommended, correct first deploy emits ~40 `CERTIFICATE_VERIFY_FAILED` lines and exits 0 reporting `tls issued (staging)`. | One line per route per kind, naming the staging certificate. | Forty identical errors in a successful run train an operator to scroll past the class of line they must not, in the run where they are least equipped to judge it. | 0195 |
| **D1048** | `routes.rest: unavailable`. | The route was serving and correctly refusing anonymously with 401. `unavailable` means both "not there" and "this deploy did not observe it", and a first deploy structurally cannot observe a router it creates (D326). | Printed summary only. `unavailable` is a schema enum with `const` couplings forcing a null URL; a third member is an outputs version with a migrator and a guarded reader for every consumer (D600). **Document half open.** | `app` already gets a paragraph explaining the same distinction; the other routes got one word. | 0195 |
| **D1049** | `provision-host: the host meets the Session 2 baseline.` Zero deviations. | `jq` absent; `connect.sh`, `doctor.sh` and `edge.sh` all require it. The only place documentation names it is the *workstation* setup. | `jq` in the apt line `--apply` already runs, and a reportable deviation in `--check`. | A baseline that certifies a host on which the product's own commands cannot run is measuring the wrong thing — and `doctor.sh` is what an operator reaches for when something is wrong. | — |
| **D1050** | `edge.sh status` is *"redacted, and readable without root"*. | `production.json` is 0600 in a 0700 root-owned directory; `except OSError: return "staging"`. So `status` **could never report `production` on any host at any time**. Measured seconds after a successful promotion: `staging` as the operator, `production` as root, a production issuer on the certificate. | Two readers: `acme_environment()` decides and still fails closed; `observe_acme_environment()` returns `None` and `status` prints `unknown`. | The wrong answer invites a second promotion, which spends a rate limit that takes seven days to return. The function's own docstring describes this symptom arriving by a different path, already repaired once. | 0195 |
| **D1051** | `BACKUP_TIMEOUT_SECONDS`' comment: *"nothing in this repository has ever timed a full backup against R2."* | Now false. A 31.7 MB database took **15m36s** (4.1 MB in repository, ~87% compression). And `backup` returns while `expire` runs, so the next documented verb met a busy repository and died on a 300 s bound — three times smaller than the operation beside it. `info` itself: 1 s in the container, 2 s through the wrapper. | `QUICK_TIMEOUT_SECONDS` 900, a note that the repository stays busy, and both measurements recorded where the bounds are chosen. | The message was this product's best example of reporting honestly, and one clause of it had become untrue. | 0195 |
| **D1052** | `dr-kit.sh verify DIR` takes no `sudo`; `export` tells the operator to copy the kit off the host. | The export runs as root and writes the kit root-owned 0700/0600 into the operator's home. `verify` as the operator answers *"this is not a kit"* — a claim about the artifact when the truth is about access. | Distinguish unreadable from invalid, and hand ownership to `ssh.operator_user` with modes unchanged. The rule cuts both ways: an *absent* directory is determinate and still says "not a kit". | An operator who has just watched `export` succeed and is told the result is not a kit goes looking for a broken export. | 0195 |
| **D1053** | `migrate --runtime up` lists the rendered set, then applies it. | `render_set` reads the *checkout's* manifest; `assert_rendered_files_match` compares the installed render against the manifest beside it. The two were never compared. Measured: 34 listed, 33 applied, `ledger recorded for 33`, exit 0. | `assert_installed_render_is_current` compares (version, name, digest) and names `deploy.sh`, before the integrity check. | The third appearance of one defect: D60 was `up` applying nothing and returning 0; D941 recorded that the summary line lies. Neither repair reached the reader holding both numbers. | 0195 |
| **D1054** | `contracts/postgrest-api-surface.yaml` is *"project-neutral, because the domain is."* | Its control fixture is one project's raw capture from `alpha.example.test`. The two statements cannot both hold once any deployment publishes something another does not. | **Open.** The control must be generated from the reviewed contract rather than captured from one deployment — a change to the review model, and Stage 3's. | The third face of D1038 and D1040: one repository, one reviewed surface, many deployments. | — |
| **D1055** | The agent plane publishes six tools; two concern `tasks`, and `update_task_status`'s compare-and-swap is the plane's showcase (ADR 0003, ADR 0116). | `0005` created `api.create_task`; `0007` dropped it, correctly (ADR 0048); nothing replaced it. **Rig 19, all 30 migrations applied:** `api.create_task` 0; INSERT on `app.tasks` held by `object_owner` alone; `app_runtime` and `authenticated` both refused with `permission denied for schema app`; 0 rows. `0003`'s grant is inert because `0006` revokes schema USAGE. | Restore a reviewed `create_task`. Retirement is **blocked**: `update_task_status` is a *tool*, so removing it leaves five and `mcp_lock` refuses at startup — D933. Migration specified, not written: it needs a sitting ending in a deploy. | The published surface names a resource the world cannot reach — ADR 0050's invariant met from the opposite direction. | 0196 |
| **D1056** | The agent plane is the product's differentiator. | The roster is enumerated (ADR 0127) and the scope vocabulary is a closed enum of five names, none of which can refer to an application's data. Both refusals measured; both correct; neither documented. | One README paragraph, written as a decision rather than a defect. | An application here gets a first-class REST surface, a first-class storage surface, and no agent surface at all for its own tables. Nowhere in the README until now. | — |
| **D1057** | *"CI is the full check. Push and read that commit's own verdict."* | `ci.yml` was `on: push: branches: [main]`, so a branch push registered **zero** runs — and `gh api …/runs?head_sha=…` exits 0 with an empty list, which reads identically as "not registered yet" and "will never fire". | `branches: [main, 'session-*']`, and the reader's half recorded: an empty listing is not evidence until the workflow's triggers have been read. Confirmed by use — the next push fired on its own. | Every session until now committed to `main`, so it never surfaced. ADR 0195's class in the CI reader. | 0195 |
| **D1058** | `0003`'s comment: *"the runtime identity works on these tables directly; it is granted USAGE on `app` in 0001."* | False since `0006-app-runtime-least-privilege.sql`, which revokes `ALL ON ALL TABLES IN SCHEMA app` and `ALL ON SCHEMA app`. | **Open, and not repairable in place.** A released template's bytes are what `verify-lock` checks, so editing even a comment changes a recorded digest. Fix-forward like everything else. | A comment in a released migration is as immutable as its SQL, which nothing had said. | 0196 |
| **D1059** | The CI reading procedure: *"judge on the HTTP status, never the body."* | Sufficient for the request, silent about the run. `concurrency: cancel-in-progress: true` means a superseded run's conclusion is `cancelled`, and a reader bucketing anything that is not `success` as failure reports `NOT_GREEN` for a run that never reached a verdict. Observed on this session's own push. | **Open.** The watcher is a session tool rather than product code; the lesson belongs in the handoff's CI section. | ADR 0195's class, sixth instance, in the tool written while repairing the other five. | 0195 |

---

## 5. Build order

### Run 1 — the three that make a bad day worse. **Done.** `d9cf137`
D1042, D1053, D1049. Measured: 30/30 TRUE for the repaired interlock against
19/20 shipped; the 1.0.0 predicate still fails under the same probe, which is
what makes the guard non-vacuous. Battery 3/3, targeted 593 passed.
**Found by sweeping rather than reported:** `ss | grep -qE` over the Docker TCP
ports fails toward certifying an exposed daemon.

### Run 2 — the characteristic defect, as a class. **Done.** `7a40eda`
ADR 0195, D1050, D1052, D1048. The rule needed a distinction the plan did not
anticipate: **a decision may fail closed; a report may not.** Battery 4/4,
targeted 707 passed. The rule cut both ways once — the first `verify_kit`
folded an *absent* directory into "cannot read", and an existing test caught it.

### Run 3 — the instrument. **Done.** `f00f915`
D1036, D1037, D1041. Battery 3/3; 88 passed against a real cluster. **M1's
control is the run's result:** with the regex reverted, the new guard fails and
`test_the_reader_is_not_vacuous` passes — the suite fully green while the
reader cannot see a published view.

### Run 4 — the documented path. **Done.** `da324a5`
D1034, D1035, D1043, D1044, D1047, D1057. Battery 4/4 after a repair.
**The battery found a vacuous assertion in its own guard:** `git check-ignore`
consults the index, so the two committed fixtures answered "visible" because
they are committed, not because the rule is right. `--no-index` makes the
question about the rule.

### Run 5 — diagnosability and recovery. **Done.** `fc929e4`
D1046, D1051, D1039. Battery 3/3, targeted 541 passed. D1045 deliberately
absent; see §1.

### Run 6 — the task domain. **Done.** `29e8dc7`
ADR 0196, D1055, D1058. **The premise was checked before it was built on**:
`0003`'s grant appeared to contradict the finding, so rig 19 measured it, and
both readings of the tree were wrong. The decision turned on an asymmetry —
retirement costs restoration's work *plus* D933's.

### Run 7 — what an adopter has to be told. **Done.** `6278066`
ADR 0197, D1040, D1056. **ADR 0197 is sharper than planned:** `DX-001`'s own
text forbids source edits and the run required seven, so `documented_path`
fails on its stated condition and the agent-versus-person question does not
need answering. Battery 2/2 after a repair — the heading guard was a substring,
which is D200's shape, already paid for once in this repository.

---

## 7. Evidence

CI green on `6278066` — Session 1 gate, Session 2 offline contract, P0
inventory. No host trip, no deployment touched, no evidence document written:
this session changes no claim's verdict by assertion. What it changes about the
claims is recorded in ADR 0197 and is the operator's to act on.

Five mutation batteries, seventeen mutations, all killed after repair, every
one `FAILED` rather than `ERROR`, every paired control green, every file
restored byte-identical.

**Six defects were found by the batteries and by sweeping rather than by the
adopter's account.** Four of those were in guards written during this session.
That is the strongest evidence the session produced that ADR 0195's class is a
trap rather than carelessness.

---

## 9. Stop conditions

- **`1.0.1` is not cut until CI is green on `main`.** D1033 is only repaired by
  a tag an adopter can reach.
- **D1045 stays open until its owner decides.** It is a security decision in a
  credential path, not a diagnosability fix, and no part of this session may
  route around that.
- **ADR 0196's migration is not written offline.** It needs a sitting that ends
  in a deploy, because the snapshot it changes is captured from one.
- **D1038, D1054 and the tenant extension point are not touched here.**
  Recording them is this session's whole contribution to them, and each would
  need an ADR whose real subject is Stage 3's.
