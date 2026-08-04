# 0014 — The Session 1 gate measures Session 1's claims, at the session the tree targets

- **Status:** Accepted
- **Date:** 2026-08-04
- **Session:** 2
- **Affects:** every requirement, indirectly — this is the gate that reports them

## Context

`bin/session-01-check.sh` was written when the repository could only be in one
state: Session 1, nothing deployed, two fixtures rendered and nothing running.
Two of its steps encoded that state as a literal rather than as a question, and
both become wrong the moment Session 2 exists.

**Step 7 iterates every directory under `.generated/`.** It fails if
`bin/compose.sh <dir> ps --quiet` reports anything. The claim it was written to
make is "Session 1 started no container". The claim it actually makes is "no
container is running for anything ever rendered on this machine". Those agree
exactly until a Session 2 project is deployed, at which point `.generated/`
holds a third directory whose probe *is* running by design, and the Session 1
gate fails on a Session 2 success.

**Step 2 exports `APG_ACCEPTANCE_SESSION=1` as a literal.** With that value,
`test_every_later_requirement_has_a_placeholder` demands a `future` placeholder
for every requirement whose `target_session` exceeds 1 — including the Session 2
requirements whose placeholders Session 2 has just replaced with real tests. The
inverse ordering fails too: raising `CURRENT_SESSION` before removing the
markers trips `test_no_requirement_at_or_before_the_gate_session_remains_future`.
The two policies are correct and mutually exclusive, which means there is no
sequence of two commits that keeps the tree green. There is only a sequence of
one.

The tempting fix for both is to relax the assertion — scope step 7 to "project
directories we recognise", or drop the gate session to an environment variable
that defaults to unset. Both would make the gate quieter about exactly the
condition it exists to detect.

## Decision

**Step 7 checks the directories step 3 just published, and nothing else.**
Step 3 records the directory of each fixture it renders; step 7 iterates that
recorded list. The list is data produced by this run, never a literal in the
script — hard-coding `fixture-alpha-dev` would put a fixture identity into
deployable source, which `tests/contract/test_repository_contract.py` forbids,
and would silently stop checking anything if a fixture were renamed. A run that
publishes fewer than two directories still fails, so the narrowing cannot empty
the check.

The claim step 7 makes is therefore, precisely: *the fixtures this gate rendered
have no container running*. Any broader claim about the host belongs to
`bin/session-02-check.sh`, which owns the deployed system and will assert it
against the deployment's own inventory.

**The gate derives its acceptance session from the package.** `bin/session-01-check.sh`
exports `APG_ACCEPTANCE_SESSION` from `agentic_postgres.CURRENT_SESSION` rather
than from a literal. `tests/contract/test_gate_contract.py` asserts no literal
session number remains in the script.

**The flip is one commit.** Raising `CURRENT_SESSION` to 2, removing the `future`
markers from `SEC-NET-001` and `SEC-SECRET-001`, and registering their real
tests happen together. Split in either direction, the tree is red — not
because a check is wrong, but because both checks are right and the tree is
briefly inconsistent.

## Consequences

`test_session_one_requirements_are_active` is hard-coded to session 1 and is
untouched: Session 1's requirements are proved unconditionally, at every gate
session, forever. Nothing about this decision lets a Session 1 guarantee lapse
as later sessions raise the number.

What it makes harder: `bin/session-01-check.sh` no longer answers "is anything
at all running on this machine". Nothing did answer that before Session 2 — the
old step only appeared to, because `.generated/` could not contain a running
project. The answer now comes from `bin/session-02-check.sh --mode host`, which
enumerates the deployment rather than guessing from a rendering artifact.

What it forecloses: running the Session 1 gate to prove a *deployment* is idle.
That was never a supported reading and is now impossible to mistake for one.

Enforced by:

- `tests/contract/test_gate_contract.py::test_the_gate_does_not_hard_code_a_session_number`
- `tests/contract/test_gate_contract.py::test_the_gate_derives_the_acceptance_session_from_the_package`
- `tests/contract/test_gate_contract.py::test_step_seven_iterates_what_step_three_recorded`
- `tests/contract/test_gate_contract.py::test_the_gate_names_no_fixture_identity`
- `tests/contract/test_acceptance_registry.py::test_session_one_requirements_are_active`

## Alternatives considered

**Leave step 7 iterating everything and stop the Session 2 probe before running
the gate.** Makes the gate's result depend on the order the operator ran things,
and turns a green gate into evidence that someone remembered a manual step.

**Add a `--session 2` flag to `bin/session-01-check.sh`.** Two gates in one
script, and the interesting failure — running it with the wrong flag — is
silent. Separate scripts with separate names fail loudly instead.

**Default `APG_ACCEPTANCE_SESSION` to unset and skip the policy when absent.**
This is the weakening the rule against loosening a passing test exists to stop.
A bare `pytest` run would silently stop enforcing registry policy, and the
enforcement that mattered would exist only inside CI.
