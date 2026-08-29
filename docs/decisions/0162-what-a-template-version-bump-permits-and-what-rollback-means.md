# 0162 — What a `template_version` bump permits, and what rollback does not mean

- **Status:** accepted
- **Date:** 2026-08-29
- **Session:** 13, Run 3 (`REL-COMPAT-001`)
- **Related:** **D704** (the version already exists and is published, and has
  never been bumped), **D724** (nothing constrains its spelling), **D733** (an
  upgrade plan compares two *rendered* documents, because the deployed one has no
  `inputs` block), ADR 0002 (derive an identity once), ADR 0012/0027 (the outputs
  schema and its migrator), ADR 0157 (three verdicts, because *nobody looked* is
  not *absent*).

## Context

`VERSION` holds `0.1.0-dev`. `template_version()` reads it, and it is published
into every rendered and deployed document and into `pyproject.toml`. **It has
never been bumped, and nothing anywhere attaches a meaning to changing it.**

Session 13 needs `upgrade check` to refuse an incompatible change *before* any
mutation. That requires a rule, and a rule is only useful if it is **decidable
from artifacts the plan can read**. D733 fixed what those are: two rendered
documents, one installed at `deployed_output.rendered_path(key)/outputs.json` and
one freshly rendered from the candidate release.

The rendered document already carries the change detector. `rendering.input_digests`
records five SHA-256 digests and its docstring states the rule they exist for:
*"this block names every file the render depends on."*

**Those five split two ways, and the split is what makes a rule possible:**

| Digest | Of | Whose |
|---|---|---|
| `project_sha256` | the project manifest | **the operator's** |
| `capabilities_sha256` | the capability manifest | **the operator's** |
| `secrets_contract_sha256` | `secrets.required.yaml` | the release's |
| `versions_lock_sha256` | `versions.env` | the release's |
| `source_specification_sha256` | `docs/source-specification.md` | the release's |

**An upgrade changes the release side by definition and must not change the
operator side.** If `project_sha256` or `capabilities_sha256` moves during what
was called an upgrade, the operator also edited a manifest — which is a different
operation, and one this repository already has a word for.

## Decision

### 1. `template_version` is semver 2.0.0, parsed here, never by `packaging`

The spelling is constrained to the official anchored semver 2.0.0 grammar. The
schema gains that pattern; D724 measured that it rejects nothing which validates
today.

**`packaging.version` is not used, and the reasons were measured rather than
assumed:**

| Finding | Measured |
|---|---|
| It implements a **different grammar** | PEP 440, not semver 2.0.0 |
| It **rewrites the value this repository publishes** | `0.1.0-dev` → `0.1.0.dev0`; `1.0.0-rc.1` → `1.0.0rc1` |
| It **accepts three spellings semver refuses** | `1.0.0.rc1`, `1.2`, and `01.2.3` — the last silently normalised to `1.2.3` |
| It is **undeclared** | absent from `requirements-dev.in`; present in the lock only transitively |

**Ordering is where the two agree**, which is exactly why reaching for it is
tempting: `0.1.0-dev < 0.1.0`, `1.0.0-rc.1 < 1.0.0`, and `0.2.0 < 0.10.0` all
come out right. The failure is not in the comparison. It is that a round trip
through the parser returns a string the document does not contain, and that the
validity question — the one a *refusal* rests on — is answered by the wrong
grammar in three of nine cases.

### 2. What each bump permits

Eight change classes, each with the artifact that already detects it. **The rule
is the smallest bump that permits the change.**

| Change | Detected by | Smallest bump |
|---|---|---|
| Implementation only; images may move | `versions_lock_sha256` | **patch** |
| A new released migration | `released.lock.json` gains an entry | **minor** |
| A new API operation | `contracts/*.canonical.json` | **minor** |
| A new capability, or a widened one | `capabilities_sha256` (release side) | **minor** |
| A new **optional** secret | `secrets_contract_sha256` | **minor** |
| `schema_version` moves, migrator total | `output_migrations` | **minor** |
| An operator manifest stops validating | `project_sha256` / `capabilities_sha256` | **major** |
| A published API operation removed or changed | `contracts/*.canonical.json` | **major** |
| A secret gains a **required** member | `secrets_contract_sha256` | **major** |
| `schema_version` moves, migrator needs operator input | `output_migrations` | **major** |

The three levels, stated as what an operator has to do:

- **patch** — an existing deployment upgrades with **no operator action**. No
  interface moves: no new migration, no contract change, no capability change, no
  secret change, no `schema_version` change.
- **minor** — an existing deployment upgrades and **the operator's manifests
  still validate unchanged**. Additive only.
- **major** — **the operator must act before the upgrade.** Something they supply
  no longer validates, or something published is gone.

**The major/minor line is already implemented, and the ADR names it rather than
inventing it.** `output_migrations.migrate_v1_to_v2` takes
`secrets_contract_sha256` as a **required argument and refuses without it**,
because it is a digest of a file that did not exist when a v1 document was
written and *"guessing it would be worse than useless."* That is precisely the
distinction: **a migrator that can complete alone is minor; one that needs a value
only the operator has is major.**

### 3. Rollback is three operations and never one word

A runbook that says "roll back" blurs three things with different reversibility,
and the blur costs data in exactly one direction.

| Operation | What it is | Reversible |
|---|---|---|
| **Configuration rollback** | Re-render and redeploy from the previous manifests | **Yes** |
| **Image rollback** | `versions.env` to the prior digests, redeploy | **Yes, conditionally** — see below |
| **Database fix-forward** | A new migration that corrects the last one | **Not a rollback at all** |

Migrations are forward-only and every down block raises **AP900**. So:

> **Once a release applies a migration, that release is the floor.** An image
> rollback below it is not a rollback; it is running old code against a schema it
> has never seen.

The operational consequence, stated plainly because it is the one that gets
blurred: **a minor bump that includes a migration is not reversible by image
rollback.** The plan says so before the mutation, or the rule is decoration.

### 4. A comparison that cannot be made is not a pass

`upgrade check` inherits ADR 0157's three verdicts rather than two. An installed
rendered document that is absent, unreadable, or of an older `schema_version`
than this release migrates from yields **`undetermined`**, which blocks exactly as
an incompatibility does. A missing left-hand side is not "no changes detected".

## Consequences

**The rules are decidable offline**, from two rendered documents and the release's
own artifacts. `upgrade check` needs no host to say a bump is wrong — which is
what lets `REL-COMPAT-001`'s refusal half be proved in a checkout.

**The version becomes load-bearing, so bumping it becomes a decision.** Until now
`VERSION` could be edited freely because nothing read it for meaning. From here a
release that adds a migration and bumps only the patch component is refused by its
own gate.

**Three of the five digests move on almost every release**, so a digest
difference is a trigger for the leaf comparison and never a verdict on its own.
A rule that read *"`versions_lock_sha256` changed, therefore incompatible"* would
refuse every upgrade this repository will ever perform.

**`packaging` stays undeclared and unused.** If a later session wants it, it is
declared in `requirements-dev.in` first — and it still is not the semver parser.

## What this does not decide

**Whether the semver pattern needs `schema_version` 13 → 14.** D724 measured that
the pattern rejects nothing currently valid, which makes it safe *for the
corpus*. Whether tightening a published contract is breaking *for the contract* is
a policy question, and this ADR deliberately leaves it to the run that adds the
pattern — with the measurement in hand rather than an argument about it.

**What a `0.x` major means.** Semver's own rule is that anything may change below
`1.0.0`, and this repository is at `0.1.0-dev`. The table above is applied at
`0.x` anyway, because the point is to *record* what changed rather than to claim
stability nobody promised. `1.0.0` at the close of Session 18 is where the rule
starts also being a promise.

**Whether a major bump may be performed at all by `apg upgrade`.** The plan says
what is required; whether the command performs it or refuses and hands the
operator a runbook is Run 4's decision, and Session 13's host trip is read-only
either way.
