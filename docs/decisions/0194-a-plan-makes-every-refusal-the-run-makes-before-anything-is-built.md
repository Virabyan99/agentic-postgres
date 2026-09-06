# 0194 — A restore plan makes every refusal the run makes, before anything is built

- **Status:** accepted
- **Date:** 2026-09-06
- **Session:** 18, Run 6 (`REC-NODE-001`, D1031)
- **Related:** **ADR 0192** (the restore precedes the first deploy; the
  refusals), **ADR 0189** (the replacement host), **D1012** (`PG_VERSION` is
  present in a restored volume and absent in a fresh one), **D972** (a plan
  that prints and does nothing), the first host gate of Session 18.

Amends [0192](0192-the-restore-precedes-the-first-deploy-and-reads-the-mirror-through-its-own-environment.md),
whose refusals were made by the run and not by the plan.

## Context

`bin/restore.sh --plan` printed the volume, the stanza, the generation and
every mount and exited 0 -- against the production host's live volume, in
the first host gate of Session 18 (2026-09-06). The two refusals ADR 0192
promised, a volume a container mounts and a volume that holds a cluster,
were made by the run only, after the plan had returned. A plan that says
*"would restore into `apg-alpha-dev-postgres`"* about the volume the
production cluster is running on is a plan an operator cannot trust, and the
proof that expected the refusal was right to fail.

The alternative was to leave the plan as a print and make the proof run the
real command, relying on its refusal. That would put a real `restore.sh` on
the production host, which the session plan forbids, to prove a property the
plan should have shown.

## Decision

**`--plan` makes the same two refusals the run makes, in the same order and
with the same exit code (7), before it prints that nothing was started.** A
volume a container mounts is read with `docker ps`; a volume that holds a
cluster is read through a probe container from the pinned runtime image in
`versions.env`, never through a build, so the plan still builds nothing and
starts nothing that outlives the probe. A plan against an absent volume
prints and exits 0 as before.

## Consequences

- `REC-NODE-001`'s live proof runs the plan where the volume is and expects
  7, on the replacement after a restore and on production against the
  running cluster alike; either refusal satisfies it.
- The offline proof of the plan asserts the reads it makes and the writes it
  does not, rather than that it makes no call at all.
