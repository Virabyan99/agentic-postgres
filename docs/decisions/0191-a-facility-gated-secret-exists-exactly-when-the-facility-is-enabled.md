# 0191 — A facility-gated secret exists for a project exactly when the facility is enabled, and is required whenever it exists

- **Status:** accepted
- **Date:** 2026-09-05
- **Session:** 18, Run 2 (ADR 0188's mirror; D1005, D1007)
- **Related:** **ADR 0054** (two planes), **ADR 0103** (origin: who creates the
  value), **ADR 0188** (the mirror), **ADR 0002** (derive once), **D276** (a
  field the contract states and no code reads), **D600/D918** (the reader that
  did not move), `test_every_optional_secret_is_root_plane`.

## Context

The mirror (ADR 0188) needs two secrets a project without a mirror has no use
for -- the second provider's key pair -- and one container that reads the
primary's existing pair as well. `secrets.required.yaml` had two states for a
secret: `required: true`, which every project must hold at the provider and
materialize, and `required: false`, which the materializer tolerates as absent
(a 404) and which `test_every_optional_secret_is_root_plane` confines to the
root plane, because Compose refuses to start a service whose mount source is
missing -- an optional compose consumer is a service that cannot start.

Neither state fits. Required everywhere fails every materialization on the
two host projects, whose manifests are schema 1 and have no mirror. Optional
is refused for a compose consumer, and rightly: on a mirrored project the
credential is not optional at all.

The alternatives considered:

1. **A second contract file** for the mirror, loaded only for mirrored
   projects. Two contracts are two authorities for one generation directory,
   and every reader of the contract (nine: the bootstrap, the deploy's
   preflight, the materializer, the override, the render, the rotation
   planner, the generation manifest, the retirement, the contract tests)
   would need to know when to load the second.
2. **Widening `required: false`** to compose consumers when a manifest flag
   is set. That is the state the guard refuses, with a condition bolted on;
   the materializer would still tolerate a 404 for a project that needs the
   value.
3. **A third state on the secret**, `facility: <name>`: the secret exists for
   a project exactly when the manifest enables the facility, and is required
   by construction whenever it exists.

## Decision

**Option 3.** A secret may declare `facility: backup_mirror`; a consumer may
declare the same, for a secret that every project holds but that one
container reads only with the facility (the mirror container's read of the
primary's pair). The rules, enforced by `secrets_contract._validate_facility`
and the schema:

- A facility-gated secret declares `required: true`. `required: false` beside
  a facility is refused with a message that says why.
- A facility named on a secret and on one of its consumers is refused: one
  statement of the fact.
- The set of a project's facilities is read by ONE function,
  `config.backup_mirror_enabled` under `secrets_contract.enabled_facilities`,
  from the manifest or the rendered document alike -- both carry
  `backup.mirror.enabled` at the same place.
- `active_secrets(contract, session, facilities=...)` is the project's view:
  a facility-gated secret only with its facility, a facility-gated consumer
  likewise. `facilities=None` is the declared view, for readers that ask what
  the contract holds rather than what one project materializes.

**Every reader that writes, mounts, requires or creates for ONE project asks
the project's view**: the materializer (`plan` and `materialize`), the secret
override (through `bin/render-secret-override.py`, which reads the rendered
document beside the override it writes), the render's `required_names`, the
deploy's preflight (`_secrets_the_provider_is_missing`), and the bootstrap's
three lists (declared, generated, operator-supplied) -- so `--plan` names the
mirror's pair for a mirrored project and for no other. The declared view stays
for the rotation planner (`rotate-secret.py` has no project), the contract
tests, and `consumers_of`.

## Consequences

- An unmirrored project materializes no mirror file, grants no mirror mount,
  is not told to paste the pair, and is not refused for lacking it. Both host
  projects deploy this release unchanged (D1007).
- A mirrored project treats the pair like the archiver's own credential: a
  404 at the provider fails materialization, and the deploy's document lists
  the pair under `secrets.required_names` -- from the generation manifest,
  which is what the materializer wrote, not from the render (D1005).
- A new facility is a new enum value in two schemas and one branch in
  `enabled_facilities`; a reader that asks the declared view for a project's
  decision is the defect this repository keeps producing, and the mirror
  proof module's contract section is the guard.
