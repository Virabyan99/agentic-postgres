# 0025 — Evidence names the claim, not the suite that ran

- **Status:** Accepted
- **Date:** 2026-08-07
- **Session:** 2
- **Affects:** `bin/write-session-evidence.py`, `bin/session-02-check.sh`, `evidence/session-02*.json`

## Context

Session 2's evidence halves recorded one thing:

```python
"tests": {f"{mode}_suite": "passed"},
```

That is the name of a command, not of a guarantee. A reader of
`evidence/session-02.json` learns that a pytest invocation exited zero. They
cannot learn whether secrets stayed in, or whether two projects on one host
stayed apart — which are the two things Session 2 exists to establish.

It was also unmeasured. The literal `"passed"` was written whether or not
anything had been observed; the only reason it was ever true is that `set -e`
aborts the gate before the evidence step when the suite fails. That is the same
defect Run 7 found five times in five costumes — a value that looks measured and
is not — and ADR 0023's vacuous network assertions and the hard-coded
`acme_environment` are the two nearest relatives.

The plan's own Run 8 asks a question this document cannot answer:

```
jq -e '.tests.secret_leakage=="passed" and .tests.isolation=="passed"' evidence/session-02.json
```

Neither key can exist. No version of the writer could produce them, so Run 8 as
written could never have passed. Nothing caught this because nothing tested the
half-writer or the merge at all: `write_half` and `merge` had no test, and
`MUST_AGREE` — the rule that refuses two halves describing different deployments
— had never been exercised.

Two smaller consumers were missing their producer in the same place.
`--project-b-outputs` reaches `bin/session-02-check.sh` and stops there, so
`project_keys` listed project A alone and the merged document of a two-project
host could not be told from a one-project one. And `-k`, documented as "for
iterating on one failure", still wrote a full evidence file from whichever
subset the expression happened to match.

## Decision

**Evidence records claims.** A claim is a guarantee named in the session's own
words. `agentic_postgres.evidence_claims.CLAIMS` maps each to acceptance-registry
requirement IDs, and its verdict is computed from the JUnit results of exactly
the node IDs that registry lists. Session 2 declares two, `isolation`
(`DEP-ISO-002`) and `secret_leakage` (`SEC-SECRET-001`, `SEC-SECRET-002`) — the
two the plan checks by name.

The claim table is not a second authority. It names requirements; the registry
names tests; a requirement that gains a test gains it here without anyone
editing the claim table.

**Three rules keep a claim from being weaker than it looks.**

- *Absence is not success.* A registry node ID the JUnit file does not contain
  makes the claim `not_run`, never `passed`, and the missing node IDs are named
  in the document. `failed` means the system is wrong; `not_run` means the
  evidence is.
- *A skip is not a pass.* `requires_environment` skips are how the deployment
  tests behave in a checkout — correct there, worthless as evidence. Counting
  one as a pass would make a full evidence run producible from a laptop.
- *Each claim is measured in one environment.* Which one is derived from the
  `live_host` / `external` markers its proofs carry, not declared beside the
  claim, so a test that moves between environments takes its claim with it. A
  claim whose proofs straddle both is an error, because neither half could
  report it without ruling on tests it did not run.

**The gate runs the proofs it will be judged on.** Each requirement also names
contract tests that carry no environment marker, which the mode's own `-m`
selector therefore never collects. `run_claim_proofs` runs exactly those node
IDs into a second JUnit file, rather than widening the selector — which would
drag the whole contract suite into a deployment run.

**A half that cannot prove its claims writes evidence and exits 5**, following
`evidence.build`'s existing rule that evidence records a failure rather than
being withheld. **A merge where neither half recorded a claim is refused**, so a
claim nobody ran cannot pass by being absent from both files.

**`project_keys` names the deployment, not the measurement.** Both halves list
every deployed project, because `MUST_AGREE` compares that field to decide
whether the two runs saw the same system; a half naming one project of a
two-project host would be read as a different deployment rather than as the same
one seen from outside. What each half actually proved is what `tests` and
`claims` say.

**`-k` writes no evidence**, announced and returned before the writer, in the
same shape as `--baseline-only`.

## Consequences

- `jq -e '.tests.secret_leakage=="passed" and .tests.isolation=="passed"'`
  passes against a real merged document. `tests/contract/test_evidence_claims.py`
  holds that expression as a literal, so renaming a claim without renaming it in
  the plan breaks a test rather than a run.
- The evidence document gains `claims` (per-claim requirements, node IDs and
  status) and `suites` (per-mode passed/failed/skipped/errors counts, parsed
  from JUnit by the existing `evidence.parse_junit`). The skip count is carried
  deliberately: ADR 0018's rule is that a quiet skip must not read as a clean
  run, and Session 2's external half legitimately skips eight cases (see below).
- `write_half` and `merge` acquire their first tests, including the first
  exercise of `MUST_AGREE`.
- A drifted registry now fails offline. `environment_markers` refuses a node ID
  no module defines, which the registry's own collection check cannot see —
  it verifies that every listed node ID collects, not that a claim can find it.
- The gate is slower by four contract tests on the host and one externally.

**One claim was written and removed, and this is the reason.** A
`public_boundary` claim over `SEC-NET-001` would have given the external half
something to say. `SEC-NET-001`'s proofs include
`test_no_service_port_is_publicly_reachable_over_ipv6`, the deployment host
holds a global IPv6 address (`2a01:4f9:…::1`), and no network available to run
the external gate from has IPv6 transit. The claim could only ever come out
`failed` — not because the boundary is open, but because nobody can look at it
from here — and a claim that cannot pass is a blocker invented by the evidence
writer rather than a fact about the system. The gap is recorded as divergence
D35 and in `docs/host-baseline.md`, which is what an unmeasured surface
deserves. Both modes stay implemented; the day a scan can be run from an IPv6
network, the claim is three lines.

## Alternatives considered

**Change the plan's check to `.tests.host_suite=="passed"`.** Rejected. It is
the cheapest fix and it makes the evidence permanently useless: the merged
document would still answer "a command exited zero" and Session 2's two
headline claims would remain unstated. It also resolves a conflict by moving
the goalposts, which the brief forbids.

**Derive claim names from the registry automatically — one claim per
requirement.** Rejected: `.tests["SEC-SECRET-001"]` is not a sentence, and the
plan asks for two names covering three requirements. A hand-written table of
three lines, checked against the registry by test, is clearer than a generated
one nobody can read.

**Let a claim's verdict come from the live proofs alone, and treat the contract
tests as the offline gate's business.** Rejected: it makes "passed" mean a
subset the document does not name, and the subset is invisible to the reader.
Running four more contract tests on the host costs seconds and makes the claim
mean the whole requirement.

**Have the mode's `-m` selector collect the static proofs too.** Rejected: the
only selector that admits them also admits the entire contract suite, which
already runs in `bin/session-01-check.sh` on the same host. The isolation tests
would also run twice, and one of them deliberately stops a project.

**Treat a skipped proof as "not applicable" when its environment variable is
deliberately unset.** Rejected outright. It is a suppression mechanism, and
suppression mechanisms get used. The distinction between "we chose not to
measure this" and "this does not apply" is exactly the judgement an evidence
file must not make on its reader's behalf.
