# 0176 — A lock check verifies the tree, not the world

- **Status:** accepted
- **Date:** 2026-09-03
- **Session:** 16, Run 1 (D861–D863, D871–D873)
- **Related:** **D861** (CI has been red for a month — 314 runs, no success in
  the newest 300), **D871** (the workflow is an operator command and no guard
  read it), **D872** (the gate died before its step 4 on every run inside the
  artifact retention window), **D873** (`--exclude-newer` measured against the
  pinned uv, with a control), ADR 0014 (the gate is the only definition of
  passing, and the session is derived), **D695** (`pytest` exits 5 when a marker
  selects nothing), **D701** (a signal that is always red is a signal nobody
  reads), **D533** (the apt pin with an end date nobody diarised), §9's
  *"`requirements-dev.in` pins nothing and has reddened the gate ten times"*.

## Context

`bin/session-01-check.sh` is the only definition of passing, and CI runs it
rather than restating it — deliberately, and the workflow's header says so. That
makes every property of the gate a property of CI.

One of those properties is time-dependent. `bin/lock-dev-deps.sh --check` runs
`uv pip compile` against PyPI and compares the result to the committed
`requirements-dev.txt`. What it asserts is therefore not *"this lock is
internally consistent"* nor *"this lock installs"*, but **"this lock is the
newest resolution available at the instant the check runs"** — a fact about the
world, restated as a fact about the repository.

Roughly ninety distributions are in that resolution. Any release of any one of
them reddens the gate, and through the gate reddens CI, within hours of a push
that was green when it left. §9 has recorded this ten times as *"upstream
drift"*, each time repairing the instance. It was never an instance.

The measurement that made this the run's finding rather than its nuisance: a
clean clone of `345c349` — the exact commit CI last failed on — fails at the
gate's **step 2**, on this check, over `cyclopts 4.23.3 → 4.24.0`. And the
workflow uploads `.generated/session-01/` and `evidence/session-01.json` with
`if: always()`, so a gate that reached step 4 leaves an artifact behind: **every
run inside the seven-day retention window has none** (D872). The runner died
where the clean clone dies, without the log that needs admin rights to read.

**The repository had already decided this question, correctly, one file over.**
`bin/lock-versions.sh --check` says of itself: *"makes no network call at all.
Everything it verifies is derivable."* Image digests are pinned; the check that
verifies them is a property of the tree. The dev-dependency lock is the caller
of that decision that never got it — question 5, in the shape §7 says this
project answers wrong most often.

## Decision

**A `--check` resolves against the cutoff its own artifact carries.**

`requirements-dev.txt`'s first line is `# exclude-newer: <RFC 3339 instant>`, and
it is the only line in the file uv did not write. `--update` stamps *now*, in
UTC, and compiles with `uv pip compile --exclude-newer` at that instant.
`--check` reads the instant back out of the committed lock and compiles against
it, so its answer does not change while the tree does not.

The marker lives in the lock rather than in a file beside it, because a second
file can drift away from the artifact it describes; and `--check` compares the
whole file including that line, because comparing body against body would leave
the one line that decides the resolution unverified.

Moving the resolution forward stays possible and stays deliberate: it is
`--update`, it produces a diff, and §9's standing rule that the result is
committed **separately** is unchanged.

### What this does not claim

- It is **not** offline. `uv pip compile` still fetches metadata; what is fixed
  is the *answer*, not the network.
- It does **not** pin transitively-yanked releases out of existence. If a
  distribution is withdrawn from PyPI, the resolution at the old cutoff stops
  being installable and the check goes red — correctly, and loudly.
- It does **not** keep dependencies current. Nothing does; nothing did before.
  What changes is that the lock now expires **when a human moves it**, which is
  D533's shape with the end date written down rather than implied.

### Two smaller decisions taken with it

**The workflow is an operator command.** `test_no_operator_command_types_the_
current_session` globs `bin/*.py`, so the step asserting the acceptance session
equalled the literal two — under a comment explaining that the value must be
derived — was unguarded, and failed on every push for thirteen sessions.
`test_no_workflow_compares_a_session_against_a_literal` scans
`.github/workflows/*.yml` for the class. It is **broader** than the `bin/` guard
on purpose: it refuses any integer literal, not only today's number, because
nothing in this suite executes a workflow and so nothing can catch a stale bound
by running it. It scans comment lines too, for the same reason — a comment in a
workflow that names a session number is describing the step beside it.

**An informational step tolerates exit 5 and nothing else.** `pytest -m future`
returns 5 when it selects nothing (D695), and there are no `future` placeholders
left. A step that swallowed every code would report a suite that could not
collect as *"no outstanding work"*, so the tolerance is exactly 5.

**A proxy is replaced by the construct it stood in for.** `test_both_modes_
compile_into_a_temporary_destination` asserted the destination was named
`staged` or `tmp` — the two names that existed when it was written — and this
change needs a third temporary, to hold the body before the cutoff line is
stamped onto it. §6 permits widening the allowlist to the measured set; §6 also
requires an ADR to replace a passing test with a stricter one, and this
authorises that instead. The test now asserts every destination is a variable
the script assigned from `mktemp`, with two "the pattern is stale" controls.
**The failure mode is the reason it is worth the paragraph**: the safe change is
what turned it red, while an unsafe destination that happened to be called `tmp`
would have walked straight through it.

## Alternatives rejected

**Drop the lock check from CI and keep it in the gate.** This is the obvious
repair and it is the one the workflow's own header forbids: *"it deliberately
does not maintain a second, divergent definition of passing — if the gate and CI
could disagree, the gate would stop meaning anything locally."* A check the
release gate runs and CI does not is that divergence, arriving quietly.

**Make `--check` verify the lock is installable rather than newest.**
`python -m pip install --require-hashes` already proves that, in three CI jobs,
before anything else runs. A check whose failure mode is identical to a step that
precedes it is not a second control.

**Pin the cutoff as a constant in the script.** It would work, and it would make
`--update` and the lock disagree the moment either moved without the other. The
cutoff belongs to the resolution it produced, which is the file.

**Accept a red CI and read it selectively.** This is what happened, for a month
and 314 runs. The Session 16 brief's enforcement mechanism for the evaluation
harness is *"failing CI"* — a gate added to a signal nobody reads is not a gate.

## Consequences

- CI's answer becomes reproducible: the same commit gives the same verdict
  tomorrow, which is what makes a red one worth reading.
- The dev lock now expires on a date somebody chose. Nothing diarises it, which
  is D533's residual, restated honestly rather than removed.
- `requirements-dev.txt` gains one line that is not uv's. Every reader in the
  tree tolerates it: `test_dependency_lock_uses_hashes` skips `#` lines, and
  `pip install --require-hashes` was measured against the stamped file.
- The `bin/` session-literal guard and the workflow one now differ in strictness,
  and the difference is written down in both. A future session widening either
  must say which rule it is widening.
