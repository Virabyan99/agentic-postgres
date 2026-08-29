# 0163 — A skipped proof is not a failed one

- **Status:** accepted
- **Date:** 2026-08-30
- **Session:** 13, Run 10 (`REL-*` evidence, D755)
- **Related:** **D755** (measured: `not_run` has never been emitted in any
  session), **D686** (exit 5 means the evidence was written and a claim in it is
  not `passed`), ADR 0018 (a quiet skip must not read as a clean run), ADR
  0025/0039 (what an evidence document records), ADR 0089/0045 (what a claim is),
  **D600** (a value that looks measured and is not).

## Context

`claim_result` has said this since Session 2, in its own docstring:

> `not_run` is a distinct status from `failed` and is reported whenever a proof
> is absent, even if every proof that did run passed. **The difference matters to
> whoever reads the evidence: `failed` means the system is wrong, `not_run` means
> the evidence is.**

**It has never been emitted.** Measured across three releases at Session 13's
host trip:

| Release | `passed` | `failed` | `not_run` |
|---|---:|---:|---:|
| `session-11-host.json` | 51 | 1 | **0** |
| `session-12-host.json` | 52 | 4 | **0** |
| `session-13-host.json` | 61 | 12 | **0** |

The reason is one branch. `not_run` fires only when a node id is **absent from
the JUnit**:

```python
missing = [nodeid for nodeid in nodeids if junit_key(nodeid) not in outcomes]
...
if missing:
    status = "not_run"
else:
    status = "passed" if worst == "passed" else "failed"
```

A **skipped** test is not absent. pytest records it, `junit_outcomes` maps it to
`skipped`, and it lands in the `else` — so it becomes `failed`.

**What that produced on the Session 13 trip.** The host suite recorded **330
passed, 28 skipped, 0 failed**. The document reported **twelve claims `failed`**.
Every one of the twelve had at least one *skipped* node id, waiting on a
declaration the operator had not supplied — `--admin-password-file`, the rotation
files, the secret sentinel, and the three Stage 1 witnesses.

So `evidence/session-13.json` asserts that twelve guarantees are broken, when
what is true is that nobody looked at them. **That is D600's family in the
artefact whose entire job is to say what a release guarantees.**

And the operator surface already assumes the fix. Four gate scripts —
`session-05`, `session-07`, `session-08`, `session-09` — document the behaviour
this ADR is about, and the Session 13 gate **printed it at the top of the run
that then contradicted it**:

> `session-13-check: no --admin-password-file, so the proofs needing an
> administrator session will skip and four claims will report not_run.`

They reported `failed`.

## Decision

**A claim's status is computed from three things that can happen to a proof, not
two.**

| Status | When | What it says |
|---|---|---|
| `passed` | every node id ran and passed | the guarantee holds |
| `failed` | **at least one node id failed or errored** | the system is wrong |
| `not_run` | no node id failed, and at least one was **skipped or absent** | the evidence is missing |

`failed` outranks `not_run`: a claim with one failure and one skip is `failed`,
because a real failure is the more important thing to report and the skip does
not soften it.

**The document names which proofs did not run.** `missing_node_ids` already
listed the absent ones; a `skipped_node_ids` member now lists the skipped ones,
so a reader can see *what* was not measured without re-running anything. A status
that says "the evidence is missing" without saying which evidence sends its
reader back to a JUnit file.

**Nothing about pass/fail semantics changes, and that is deliberate.** Every
consumer of a claim status tests `!= "passed"`:

- `write_half` — the `unproved` list, and its exit 5
- `merge` — the `failed` list, the document's own `status`, and its exit 5
- the gates — which read the document's `status`

So a `not_run` claim still makes the half unproved, still makes the merged
document `failed`, and still produces **exit 5**. D686 is untouched: *exit 5
means the evidence was written and a claim in it is not `passed`.* **A skip is
still not a pass** (ADR 0018). What changes is only the word the document uses to
say why — and that word is the whole of what a reader has to go on.

## Consequences

**Twelve claims in `evidence/session-13.json` move from `failed` to `not_run`,
and the release's headline number does not move.** 66 of 78 passed before and
after. The document stops claiming twelve guarantees are broken.

**Sessions 11 and 12's stored documents are not rewritten.** They are records of
runs that happened, and re-deriving them from a model those runs did not use
would make them say something nobody measured — which is the defect this ADR
exists to remove. `evidence/*` is gitignored; the host halves live on the host,
and they stay as written.

**A `not_run` claim is still a gate failure**, and every gate that says so stays
correct. The four gate scripts documenting `not_run` become accurate rather than
aspirational.

**One reading gets harder, and it is worth naming.** `failed` used to mean "not
proved, for any reason", so a reader who wanted "is anything wrong" could count
non-`passed`. Now they must distinguish, which is the point — but a reader who
does not know that will under-read a `failed`. The status vocabulary is in the
document and in this ADR; nothing enforces that a consumer understands it.

## What this does not decide

**Whether a skipped proof should ever be tolerated.** It should not, and nothing
here makes one acceptable: `not_run` blocks exactly as `failed` does. This ADR is
about what the evidence *says*, not about what the gate *permits*.

**Whether the declaration-gated claims should be provable another way.** Twelve
claims skipped on this trip because an operator did not supply flags for a
read-only visit. That is the right outcome for that visit and says nothing about
whether those flags should be easier to supply.

**Whether `not_run` should distinguish *skipped* from *absent*.** They are
different — a skipped proof was collected and declined to run, an absent one was
never collected, and the second can mean a selector that matches nothing (the
failure `static_nodeids_for_mode` exists to prevent). This ADR records both in
separate members and gives them one status, because a reader's first question is
*was this measured* and both answers to that are "no".
