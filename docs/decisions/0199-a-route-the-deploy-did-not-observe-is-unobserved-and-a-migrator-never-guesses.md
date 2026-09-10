# 0199 — A route the deploy did not observe is `unobserved`, and a migrator never guesses which one that was

- **Status:** accepted
- **Date:** 2026-09-10
- **Session:** 20, Run 1 (D1048, D1060, D1094)
- **Related:** **ADR 0195** (a report may not substitute an answer for a failure
  to determine one; a decision may still fail closed), **ADR 0158** (the
  deployed document is the address book, not the diagnosis), **ADR 0163**
  (`failed` means the system is wrong, `not_run` means the evidence is),
  **D600** (a `null` that looks measured is worse than an absent field),
  **D230**, **D326**, **D1047**.

## Context

ADR 0195 was written at Session 19 from twelve instances of one class, and its
rule has three outcomes rather than two: the answer, the other answer, and
*I could not determine it*. Two sites in this tree still have two, and both were
found after 1.0.1 was tagged.

**`routes.*.status` has two words for three states.** The enum is `ready` and
`unavailable`, with a `const` coupling that forces a null URL on `unavailable`.
The deploy writes `unavailable` for a route it observed not serving — and for
one it never looked at. The first-deploy router race (D326's shape), a docs
probe that met a staging certificate (D1047), a timeout: all of them record the
same word as a route that answered with a failure. Nothing in the document
tells them apart.

**`migrate.sh render` reports a directory it cannot read as one that does not
exist.** After a root deploy `.generated/<key>` is root-owned, so `op` cannot
traverse it, and the command says *"the project was never deployed here"* and
exits 4. That sentence is false about a project deployed forty minutes earlier.
Measured on the host on 2026-09-10, with beta as the control (D1060) — the
third live site of ADR 0195's class, and the reason it belongs to the next
release rather than to a second tag.

## Decision

### The third word

`routes.*.status` gains **`unobserved`**, with the same `const` coupling to a
null URL that `unavailable` carries. A URL is still withheld, because a route
nothing observed is a route nothing can promise; what changes is that the
document stops asserting a failure it did not witness.

The three words divide as follows, and the division is by **what was
determined**, never by what was convenient:

| Word | Means |
|---|---|
| `ready` | The deploy observed the route serving. |
| `unavailable` | The deploy determined the route is not published, or observed it failing. **D230** (no project administrator), **D326**'s no-credential branch, a probe that answered non-200, a session that publishes the surface at all. |
| `unobserved` | The observation was not made. The first-deploy router race, a probe that met a staging certificate, a timeout, a reader that could not run. |

The printed summary and the document take the word from **one function**, so a
deploy cannot say one thing on the terminal and record another — D701's rule (a
status computed twice is wrong the second time) applied to a field that outlives
the run.

### The migrator does not guess

`migrate_v16_to_v17` **leaves every route's recorded word exactly as it found
it** and adds only the `migrations` block.

This is the part worth stating, because the tempting alternative is available
and wrong. A migrator could look at a v16 document and reason about which
`unavailable` was probably an unobserved one — an `unavailable` on `docs` with
a staging certificate recorded elsewhere, say. It must not. **The information is
not in the document**: the writer that had it wrote one word for two states, and
nothing downstream can recover the distinction. A migrator that guessed would be
ADR 0195's own defect applied to itself — a report substituting an answer for a
failure to determine one — and it would write the guess into a record that
outlives the guess and is read by six consumers as fact.

Only a **v17 deploy** writes `unobserved`, and only where the observation was
actually not made. A v16 document that says `unavailable` migrates saying
`unavailable`, and a test asserts exactly that.

### Every reader learns the third word

A widening whose readers do not move is D600's shape, so they are named:

- `diagnosis.py` reports the word and never folds it into `unavailable`.
- `fleet.py` passes it through the doctor's JSON.
- `bin/api-contract.py published_address` refuses an unobserved route **with the
  remedy** — *redeploy so the route is observed* — rather than treating it as
  absent.
- `deployed_output.py`'s validation accepts three words.
- `tests/deployment/test_session14_observability.py`'s `in {"ready",
  "unavailable"}` widens to the three. **This is a widening to a measured set,
  not a loosening to a subset check** — the non-negotiables permit the first and
  forbid the second, and the distinction is that the allowlist still enumerates.

### D1060's sibling rule

The same rule, in the same session, for the six readers of a rendered document:

> A reader that cannot read a thing says so. **Unreadable** (exit 3, naming the
> path, the owner and the remedy) is not **absent** (exit 4, *never deployed
> here*).

One reader in Python —
`installed_release.rendered_document(key, *, runtime)` — raising
`RenderedDocumentUnreadable(path, owner)` on `PermissionError` and
`RenderedDocumentAbsent(path)` on `FileNotFoundError`, and the six commands
(`migrate.sh`, `db.sh`, `postgres-bootstrap.sh`, `doctor`, `upgrade`,
`project-retire`) map those two to 3 and 4. The three shells lose their
`[ -f … ] || die 4`, and a guard test asserts none of them tests `-f` on a
rendered document again — because the defect is not any one script's, it is the
shape, and guarding the class rather than the instance is what D600, D918 and
D926 each cost this project once.

ADR 0195's own asymmetry is preserved and is the reason `exit 3` is not simply
"fail": **a decision may fail closed; a report may not.** A deploy that cannot
read an ACME store and proceeds as though the certificate were not promoted is
right. `edge.sh status` doing the same could never print `production` on any
host at any time, which is what made it a defect. `migrate.sh render` is a
report. It says which of the two it could not tell.

## Consequences

- Outputs goes to **v17**. `routes.*.status` gains a member and the `migrations`
  block arrives in the same version, so there is one migrator and one bump
  rather than two.
- Nine tests chain the outputs migrator by hand (D965) and each gains the v17
  step. That is mechanical and is called out in the commit rather than hidden in
  it.
- A deployment redeployed under v17 should carry **no** `unobserved` route on a
  healthy project: every route is either observed serving or determinately not
  published. `unobserved` appearing on a settled deployment is a signal, and the
  live half of `OPS-READ-002` reads exactly that.
- The word is not a diagnosis (ADR 0158). It says what the deploy did, not what
  is wrong; the doctor is what says whether it matters.
