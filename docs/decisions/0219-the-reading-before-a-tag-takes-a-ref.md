# 0219 — The reading before a tag takes a ref

- **Status:** Accepted
- **Date:** 2026-09-18
- **Session:** 30, Run 2 (D1513, D1539, D1545)
- **Affects:** `REL-READ-001` (its node id is replaced), `REL-READ-002` (new,
  Session 30). No schema, no migration, no deployment.
- **Amends:** ADR 0214. That ADR's decision — the reading states facts and
  names the one judgement it cannot make — is **untouched**. This changes only
  which commit the facts are read from.

## Context

D1425 fixed the order of a release: **deploy, sweep, then tag**, and the tag
goes on the commit that was deployed. That commit is behind `HEAD` on every
trip, because the sweep's own evidence commit lands after it.

`apg release-reading` reads `HEAD` and takes no arguments. `bin/release-
reading.sh:92-94` refuses any argument with exit 2 and the text *this command
takes no arguments*; `bin/release-reading.py:189` parses none; `:96` is
`git("rev-parse", "HEAD")`. So the reading taken before a tag is a reading of
the wrong commit, and the present procedure is a throwaway worktree — a
workaround an operator performs correctly only while they remember why.

D1513 measured the gap concretely: 14 commits after the bump versus 13, on the
same day.

### The constraint that makes this an ADR rather than an edit

`tests/contract/test_release_reading.py:360`
`test_the_command_takes_no_arguments_and_says_so` **passes today** and asserts
exactly what this change removes. It is a node id of `REL-READ-001`
(`tests/acceptance-registry.yaml:4024`). A contract test changes only with an
ADR, and a passing test may not be weakened — it may be replaced by a stricter
one when an ADR authorises it (`CLAUDE.md` §6). Widening *no arguments at all*
to *exactly one enumerated option, everything else still refused* is that
shape; silently editing the assertion would be the weakening §6 forbids.

### The trap this ADR has to name

`bin/release-reading.py:100-101` reads the version from the **working tree**:

```python
version_path = REPO_ROOT / "VERSION"
version = version_path.read_text(encoding="utf-8").strip() if version_path.is_file() else ""
```

and `:112` then searches the tags for the one whose `VERSION` equals it. A
`--ref` that resolved a commit but kept this read would report **the ref's
commit married to the checkout's VERSION** — a reading that looks right and is
a mixture. The same applies to `:127` and `:140`, which spell `HEAD` inside
`rev-list` ranges, and to `:116`'s `git describe --tags --abbrev=0`, which
describes `HEAD` implicitly.

## Decision

`apg release-reading` takes **exactly one** option, `--ref REF`.

1. `REF` is resolved with `git rev-parse --verify "REF^{commit}"`. A ref that
   does not resolve is refused with **exit 2**, naming the ref.
2. Absent, the ref is `HEAD`, and the no-argument form's output is **unchanged
   byte for byte**.
3. Every argument that is not `--ref REF` or `--help` still exits 2.
4. **Every git read that resolves `HEAD` resolves the given commit instead** —
   `:96`'s `rev-parse`, `:116`'s `describe`, `:127`'s and `:140`'s `rev-list`
   ranges — and **`VERSION` is read as `git show REF:VERSION`**, never from the
   working tree, so the reading describes one commit and not a mixture.
5. The first block's label reads **`ref`** instead of `HEAD` when one was
   given, so a transcript says which commit was read. That is D1513's whole
   point: a reading that does not name its subject is a reading nobody can
   check.
6. The fifteen labelled fact lines and the three `CHECKLIST` questions are
   otherwise unchanged (D1545 — the stage plan's "eleven facts" is a count the
   tree does not carry; the word *eleven* occurs nowhere in `bin/` or `src/`).

**`test_the_command_takes_no_arguments_and_says_so` is replaced by
`test_the_command_takes_exactly_one_option_and_refuses_the_rest`**, which is
stricter: five refusals where there was one (`--since 1.6.0` → 2; `--ref` with
no value → 2; `--ref nonesuch` → 2 naming the ref; and `--ref HEAD` printing
the same bytes as no argument). Its node id replaces the old one under
`REL-READ-001` in the same commit, and `test_acceptance_registry` runs (D1119).

## Consequences

**Makes easy:** the tag procedure becomes one command against the deployed
commit. `docs/operator-guide.md` §14 *Before a tag* names `--ref <the deployed
commit>`, and the throwaway worktree is retired from it.

**Makes hard:** nothing measurable. The option is additive and the default path
is byte-identical.

**Forecloses:** the command does not grow a second option. `--since`, a format
flag and a `--json` mode are all refusable with the same sentence, and the
replacement test asserts `--since 1.6.0` still exits 2 precisely so that the
surface cannot drift open one flag at a time.

**First use:** Session 30's own tag, in Run 7 — which is also the first
execution of the new proofs. `pytest --setup-plan` with the variables set is
the cheap half before the trip (D671); fifteen never-executed proofs in this
project's history have failed on first execution.

**Enforced by:** `test_release_reading.py::test_the_command_takes_exactly_one_
option_and_refuses_the_rest`, `::test_the_reading_names_the_ref_it_read`,
`::test_a_ref_reads_the_tag_target_and_not_the_tip` (a throwaway repository:
two commits, VERSION moved at the first; `--ref` at the first reports *commits
after it 0* where `HEAD` reports 1 — the proof that the VERSION read moved with
the ref), `::test_an_unresolvable_ref_is_refused_naming_it`,
`::test_help_names_the_option`.

## Alternatives considered

**Keep the worktree procedure and document it harder.** It is documented now
and D1513 still happened. Documentation is not a control.

**Take a positional argument rather than `--ref`.** `release-reading <commit>`
reads well but makes the refusal of every *other* argument harder to state and
harder to test; an option keeps "exactly one option, everything else exits 2"
as a single assertable rule.

**Resolve the ref but keep reading `VERSION` from the working tree.** Simpler,
and wrong in the reassuring direction — it would agree with the correct answer
on every occasion except the one the option exists for (a tag going on a commit
whose VERSION differs from the checkout's). D930 and D957 are this project's
record of premises wrong in the reassuring direction surviving longest.

**Have the command take a ref and also print a verdict.** Out of scope and
already decided: ADR 0214 says the reading states facts and names the judgement
it cannot make. This ADR amends the subject of the facts, not their nature.
