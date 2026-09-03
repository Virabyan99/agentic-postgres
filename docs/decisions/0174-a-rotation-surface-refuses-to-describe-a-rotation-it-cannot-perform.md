# 0174 — A rotation surface refuses to describe a rotation it cannot perform

- **Status:** accepted
- **Date:** 2026-09-03
- **Session:** 15, Run 6 (`IDN-ROT-001`, D816, D849–D852)
- **Related:** **D816** (the vocabulary declared on 19 secrets and read by one
  test covering three), **D56** (rotation tooling must refuse to report a
  rotation it did not perform), **D849** (`must_refresh_on_start` selects between
  two behaviours and one was never built), **D850** (one flag, two different
  phenomena), **D851** (the two observable flags, measured), **D852** (the
  surviving mutation and the consistency nobody required), **D249** (no command
  sets a value at the provider), ADR 0103 (`origin`), ADR 0170 (a retired secret
  leaves the release), ADR 0002 (one authority per value).

## Context

The plan's instruction for this run was unusually specific: *"First act: verify
all 19 declared rotation flags against what is true. Three have ever been
checked. Sixteen are assumptions with a reader about to arrive."*

That ordering is the decision this ADR mostly records. A surface driven by
sixteen unverified fields would inherit every one of them in a single step, and
each would fail as **a wrong action on a live credential** rather than as a
refusal.

**Two of the three flags describe observable behaviour** and were measured
against the pinned image (D851):

- `one_time_initialization` on `postgres_init_superuser_password`: after
  replacing the value and restarting over the same data directory, the
  replacement is **refused** and the original **still works** — new=False,
  old=True. The control matters: without "the original still works", this would
  equally describe a container that failed to start.
- A database role password rotates end to end, with its rollback rehearsed
  *before* the rotation and working after it.

**The third does not describe behaviour at all** (D849). `must_refresh_on_start`
chooses between failing closed and starting on a cached last-known-good value,
and **the materializer has no cache**: every provider failure except a 404 on an
optional secret fails the whole run. The phrase "bounded last-known-good start"
appears in this repository **only inside `secrets.required.yaml`'s own comments**.

## Decision

### 1. The surface reports what replacement would achieve, and refuses when it achieves nothing

`bin/rotate-secret.sh` answers one question per secret. Seventeen rotate by
replacement; two do not, and **those two are the reason it exists**.

Both refusals look exactly like the seventeen that work — same shape, same
consumers, same plane — so a plan that printed their files and services would be
describing, in detail, a rotation that does not happen. An operator who followed
it would report one. That is D56, written down five sessions ago and until now
enforced by nothing.

### 2. Every refusal names the operation that does work

A refusal without a way forward makes an operator guess, and the guess for a
credential is usually *do it anyway*. Each names a real, different operation: a
coordinated `ALTER ROLE` through the privileged local path, or a new repository
with a new full backup chain.

### 3. The two refusals do not share an explanation

`one_time_initialization` is one flag covering **two different phenomena**
(D850). `postgres_init_superuser_password` is read once and **nothing is bound to
it** — the cluster keeps whatever initdb set. `pgbackrest_repo_cipher_pass` is
the opposite: the value **is** bound, to the repository, at `stanza-create`, so
replacing it does not leave the system using the old value — it leaves the reader
holding the wrong one for every existing backup.

The flag is right about the consequence and imprecise about the mechanism, so the
mechanism is spelled per secret. One sentence covering both would have been
plausible and wrong for one of them, which is D278's shape.

### 4. `must_refresh_on_start` is not reported, and the surface says why

Printing it would describe a choice the deployment cannot make. Six `false`
declarations claim a leniency that does not exist, and the "true" behaviour is
the only behaviour.

**The flag is not wrong — it is unimplemented**, so this is a stated omission
rather than a silent one, and a contract test asserts that the materializer still
has no fallback. The day somebody builds one, `must_refresh_on_start` becomes a
real difference, that test goes red, and this section is what has to change.

### 5. The surface writes nothing, anywhere

No provider call, no credential, no file, no subprocess — asserted over the
source, because "it did not write" is not observable from a successful run and
the interesting case is the verb somebody adds later. D249's rule, which
`rotate-signing-key.sh` already keeps: **a command that could both decide a
rotation and perform it would be one mistake away from performing one nobody
decided.**

### 6. A retired secret is not offered for rotation

`plan_all` takes a session, so the bootstrap signing key — retired at 15 by ADR
0170 and still declared — appears at 14 and not at 15. Planning a rotation for a
credential the release no longer issues would name a file nothing writes.

## Consequences

- **One class is proved end to end and the rest are not** (D815). A database
  role password was rotated in a rig with its rollback rehearsed first; the other
  sixteen rotate *by the same mechanism* and have not each been performed. The
  surface says what would happen, and only Run 8's trip can say what did.
- **Four secrets rotate but cannot be generated here** — the R2 pairs, whose
  values come from a third party's console (ADR 0103). Reported as such, because
  a plan that said "rotates" without saying so would send an operator looking for
  a `--generate` flag that must never exist.
- **Nothing requires the two observable flags to agree** until this run's guard
  (D852). The contract permitted `one_time_initialization: true` beside
  `rotate_by_replacement: true` — a value both read once and rotatable by
  replacement — and the surface would have reported a rotation the secret's own
  declaration denies.
- **`must_refresh_on_start` remains unread by anything that acts on it.** This
  run did not implement the last-known-good path and does not claim to have
  closed D816 for that flag: two of three are now verified and driven, and the
  third is documented as a specification awaiting its mechanism.
