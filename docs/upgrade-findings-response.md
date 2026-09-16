# What release 1.6.1 did about an adopter's upgrade findings

> **A record of what releases `1.6.1` and `1.6.2` did, dated 2026-09-16.** Unlike
> `docs/upgrade-guide.md` and `docs/operator-guide.md`, this page does NOT
> track the current release and is not held to it by a test (ADR 0209): it
> describes one release answering one reader, and it stays true by staying
> still. A later release that reopens or closes something here says so in
> its own plan and in `docs/scope-closure.md`, not by editing this page.

On 2026-09-16 an outside agent upgraded a real adopter's deployment from
**1.0.0 to 1.6.0** holding only this repository's documentation, on a host this
project does not administer. It converged — the deploy exited 0, the doctor
read 10 ok, `upgrade verify` matched — and it wrote **thirty-four numbered
findings**, `F-000` through `F-033`.

Release **1.6.1** is the answer to that file. This page is the map: every
finding, what was done, and where to check it. It exists because a findings
file deserves a reply that can be verified rather than a claim that it was
handled.

**Read the status column literally.** Three of the four values mean the finding
is not gone:

| Status | Means |
|---|---|
| **Fixed** | the product or the page changed, and a test or a reading holds it |
| **Documented** | nothing in the product changed; the page now says the true thing, including *this is undecided* |
| **Open** | not addressed in 1.6.1. The finding stands as written |
| **No action** | the finding is an observation, a positive, or about the reader's own environment |

---

## The two that block a pre-1.1.0 fork, and they are still open

**If you forked at 1.0.0 or earlier and your domain lives inside the release's
own files, `projects/<slug>/` is still not reachable for you.** The upgrade
works — that is measured — but the layout the release documents does not.

- **F-012**, `freeze-lock` refuses a set authored against an earlier release.
  `freeze_project_lock` computes the floor from **this checkout's** newest
  release version, and there is no flag to record the release a set was really
  frozen against. **The refusal message was repaired in 1.6.1 and the refusal
  was not.** It now says what is true: re-freezing recomputes the same floor and
  refuses again, and re-stamping amends applied migrations (D912) and breaks ADR
  0206's version-matched ledger move. Those are the two things a reader would
  otherwise try, and both are worse than stopping.
- **F-013**, the project-set lint forbids `{{app_runtime}}`, which the
  release's own migration `0003` uses. An adopter who models a table on the
  platform's example domain writes a set the release will not lint.

Both are named in `docs/scope-closure.md` §15 as the **on-ramp question**, and
they are a product decision before they are a page. `docs/upgrade-guide.md`
§1.0 says so rather than pretending §1 covers it.

---

## Every finding

| # | Finding, in short | Status | Where to check |
|---|---|---|---|
| F-000 | The task's paths were not on the machine | No action | The reader's environment, not the release |
| F-001 | The checkout was three commits past the tag | Fixed | The pages are now inside the tag; see F-003 |
| F-002 | The index claims completeness; at 1.6.0 there was no upgrade page | Fixed | `docs/README.md`; `git ls-tree -r --name-only 1.6.1 -- docs/` |
| F-003 | The upgrade guide existed one commit **after** the tag | **Fixed, and it is the finding the release is built around** | **ADR 0209**. Each page states the release it is part of, checked against `template_version()`; the release table must carry a row for the release; both pages joined the two documentation scans. `git ls-tree -r --name-only 1.6.1 -- docs/ \| grep -E "upgrade-guide\|operator-guide"` prints both, and the same against `1.6.0` prints neither |
| F-004 | `bin/upgrade.sh` exists and the README never says so | Fixed | README *Operating a deployment* carries `check`, `plan` and `verify`; a test reads that section between its heading and the next `##`, so a mention elsewhere no longer satisfies it |
| F-005 | The README's gate sentence says 01–10 | Fixed | README *Checks*: twenty-four gates, 01–18 and 20–25, **and why there is no 19** |
| F-006 | Upgrading is documented only in ADR 0162 | Documented | `docs/upgrade-guide.md` is the page; ADR 0209 makes it part of the release |
| F-007 | Nothing documents how a **fork** takes a release | Documented | Upgrade guide §1.0. What is written is the shape of the problem and what one operator did, not a rule that does not exist |
| F-008 | §1 describes an adopter this fork is not | **Documented, not solved** | §1.0. **How a pre-1.1.0 fork converts is undecided** — scope-closure §15, first row |
| F-009 | `git merge` produced nine conflicts; the page said "the merge itself is git's" | Documented | §1.0 records the nine conflicts and that **no rule exists** for which side wins. It records what the one operator did as *what happened* |
| F-010 | Four conflicts were the release absorbing 1.0.1's repairs | No action | A positive |
| F-011 | Contract tests hard-code the platform domain as the whole surface | **No action — and you answered it yourself** | Your own resolution is the right one and the release agrees with it in code: at 1.6.0 those equalities are **deliberately not loosened**, because a project's objects live in `projects/<slug>/` and are read by a different set (`test_api_migrations.py` says so at the assertion, D1089). The conflict existed because the fork had loosened them at 1.0.0. Nothing to fix here |
| F-012 | `freeze-lock` refuses a set authored against an earlier release; its remedy would corrupt the deployment | **Open — refusal unchanged, message repaired** | See above. `src/agentic_postgres/migrations.py::_assert_follows_release_version` |
| F-013 | The lint forbids `{{app_runtime}}`, which the release's own `0003` uses | **Open** | Untouched in 1.6.1 |
| F-014 | "Four of §1's six checks refuse a schema-4 manifest" | Fixed, **and the count was wrong** | **Two**, not four, measured 2026-09-16: `migrate verify-lock --project` (exit 5) and `api-contract --check --project` (exit 2). §1 carries the measured table with the `--project`-less form beside each |
| F-015 | The two checks that should go red did | No action | A positive |
| F-016 | `upgrade check` says `OK` where the release was expected | Fixed | `check` now says *a comparison CAN be made … no candidate was read*, or *nothing is installed, so nobody looked*. **No JSON key moved** |
| F-017 | §2 step 1 demands "10 ok" absolutely | Fixed | §2 step 1 sorts the doctor's verdicts into stop / stop-for-backups / note-and-proceed, and tells you to write the pre-upgrade reading down |
| F-018 | The host has no `uv` and no `.venv`, which two pages assume | Fixed | §3 step 1's sync is conditional with the one-line diff that decides it; `docs/host-baseline.md` no longer describes the maintainer's shell as the baseline |
| F-019 | Two drifts in §2 step 5 | Fixed | The `.gitignore` glob has covered a manifest in the checkout since 1.0.1; the ownership check now sees dotfiles |
| F-020 | The host checkout was a commit behind and nothing noticed | **Open** | Untouched in 1.6.1 |
| F-021 | §2 runs the **old** release's commands while describing the new one's behaviour | Fixed | §2 opens with a standing sentence saying exactly that, and step 2 carries the 1.0.0 kit hand-over by hand (`_hand_to_operator` arrives in 1.0.1) |
| F-022 | The gate cannot pass on this fork | **Open, and it is downstream** | Not an independent defect: causes 1 and 2 persist only while the domain is in the release's files, and **F-012 and F-013 are why it cannot leave them**. The residual that is genuinely ours is your last sentence — *no page says what an adopter does about that* — and it is still unwritten. A green gate is not a deploy precondition, so the upgrade proceeds; what cannot be satisfied is §7's *an upgrade without a sweep is deployed, not measured* |
| F-023 | `--through-session` takes a number with no documented source | Fixed | `./deploy.sh --help` prints it, derived from `CURRENT_SESSION`, and names the file; §3 step 6 says where to read it on an older release |
| F-024 | The `.generated` ownership check misses the directory that matters | Fixed | `.staging` and `.locks` are dotfiles a glob cannot match. §2 step 5 names them |
| F-025 | The named-owner refusal did not appear; a traceback did | Fixed | Four `mkdir` sites now name the owner, the caller and the `chown`, and raise the convention's exit code instead of exit 1 |
| F-026 | The host interpreter is 3.14; the repository pins 3.12 | **Recorded, not repaired** | scope-closure §15. Changing what `provision-host.sh --apply` does to a machine is a decision, not a sentence |
| F-027 | `<absent> -> None` is two facts printed as one | Fixed | `plan` prints `(no such key)`, `null` and the JSON value apart |
| F-028 | The no-redirect rule has no stated way to satisfy it over SSH | Fixed | §3 step 6 names **`ssh -tt`** and **`script(1)`**, with why each satisfies D972 rather than working around it |
| F-029 | Two kit exports on one day collide, and the page asks for both | Fixed | `-pre` and `-post`; each step names the other; the guard is untouched |
| F-030 | `apg generate` cannot type a `text[]` column | Fixed | See F-033 |
| F-031 | The return trip names step 1 and not step 3 | Fixed | §3 step 9 carries a nine-row table of what the second pass runs and why the rest are skipped |
| F-032 | The refusals are the product's best part | No action | Recorded in the operator guide §13 |
| F-033 | The same table blocks `apg studio`, and three entries were missing | **Fixed, and it was larger than the finding** | `client_ir.FORMAT_TYPES` went **21 → 44 entries**, every spelling measured against a running PostgREST. See below |

---

## The one the reader understated, measured

F-033 said three entries were missing. **Seventeen of the table's twenty-one
entries had never matched a served format in this repository's history.**

PostgREST serves `integer`, `smallint` and `bigint` as **`int32`/`int64`** —
as a column *and* as an RPC argument — so the table could not type an integer
anywhere, and it had never been asked for an array at all. The release had not
met this because its example project's one RPC takes `uuid` and `vector`, and
the two committed snapshots between them serve five formats and one enum.

The repair was measured rather than reasoned: a rig built one column and one
RPC argument of **every** type plus **every** array form against a real
PostgREST and read the served document. What it found beyond the finding:

- an array carries the base type's SQL name and **never** `int32`
  (`integer[]` is served `integer[]`);
- PostgREST drops a `varchar` modifier inside an array and **keeps `vector`'s**,
  so `extensions.vector(768)[]` arrives whole and the modifier normaliser had to
  stop being anchored at the end of the string.

The measurement is committed as `RIG_27B_SERVED` in
`tests/contract/test_client_ir.py`, and a guard asserts every served spelling
resolves **and** that a type's two spellings resolve to the same TypeScript
type. `tsvector` is deliberately still absent: it is the control proving an
undecided format refuses rather than becoming `any` (ADR 0204).

---

## How to check any of this yourself

```bash
git fetch origin --tags
git show 1.6.1:VERSION                       # 1.6.1
git ls-tree -r --name-only 1.6.1 -- docs/ | grep -E "upgrade-guide|operator-guide"
git log --oneline 1.6.0..1.6.1               # seven commits, one per run
```

`docs/plans/session-27-implementation-plan.md` §1 is the divergence table:
**D1388–D1405**, six columns each, one row per defect, with what was measured
and what was decided. Its §5 carries a `Done.` paragraph per run saying what
that run measured — including the mistakes, of which there were several.

`docs/scope-closure.md` §15 is what 1.6.1 **left open**, and its first row is
the on-ramp question.

---

## What this release does not claim

- **It was not verified against your deployment.** Session 27 took **no host
  trip**. The class `1.6.1` proposes is priced by ADR 0162 and confirmed by
  nothing yet; the maintainer's own two projects are still deployed at `1.6.0`.
- **The operator guide has not been read cold.** The upgrade guide has, which is
  why this page exists. `docs/operator-guide.md` was written by the session that
  read the material, and its §13 says so.
- **No test reads prose for truth.** ADR 0209 holds that a page names the right
  release and that every command it names exists. Whether a sentence is *true*
  is what a reader like you finds out, and it is the only instrument for it.
