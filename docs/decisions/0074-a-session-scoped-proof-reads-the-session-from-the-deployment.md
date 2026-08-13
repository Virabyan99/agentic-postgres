# 0074 — A session-scoped proof reads the session from the deployment

Status: accepted
Date: 2026-08-13
Session: 5, Run 10
Amends: [0054](0054-a-secret-may-be-consumed-by-the-root-plane.md)
Affects: SEC-SECRET-002

## Context

`tests/security/test_session2_secrets.py` proves that a materialized secret is
readable only by its consumer, and it does so from the mount list rather than by
comparing bytes — a digest comparison shows two services hold different files, it
does not show that the ungranted one *could not have read* the other's.

Two of its proofs ask the contract which services are granted, and both passed a
literal:

    active_secrets(contract, session=2)
    granted_services(contract, session=2)

Session 2 was the only session that existed when they were written, so the
literal and the truth coincided. They have coincided ever since, because these
thirteen proofs need `--sentinel-file` and **the flag was not passed once in
Session 5** — so their first execution against a Session 5 deployment was the
gate run on 2026-08-13, and it failed:

    apg-alpha-dev-postgrest-1 mounts a secret it was not granted:
      .../generations/781b7e3182ff99a5/postgrest/postgrest_authenticator_pgpass

The mount is correct. `postgrest_authenticator_password` declares exactly one
Compose consumer — service `postgrest`, `format: pgpass`, mode `0400`, uid 65532
— with `introduced_in_session: 5`. A grant from a session the constant cannot
reach is indistinguishable, to this test, from a service helping itself.

## Decision

**The session comes from `deployed_through_session` in the deployed document.**

The number is already published, by the deployment, about itself. Both call
sites read it through one module fixture rather than each restating it, so a
third proof cannot reintroduce a third constant.

This makes both proofs **stricter**, not weaker:

- `granted_services` — a container mounting a secret introduced in a session
  *later* than the deployment still fails, which a hard-coded `5` would not
  catch. So would a container mounting another service's copy: the path
  component is the consumer's service name, which is the whole point of
  per-consumer materialization.
- `active_secrets` — the mode, uid, gid and non-emptiness of every secret the
  deployment actually carries are now checked, including the two `root`-plane
  consumers ADR 0054 introduced. Under the literal, five of eleven consumers
  were checked and the assertion `checked > 0` reported success.

## Alternatives

**Bump the literal to 5.** Rejected. It is the same defect with a fresher value,
and it would be wrong the moment Session 6 deploys — silently, in the direction
that permits a mount rather than the direction that fails one.

**Derive from `CURRENT_SESSION`.** Rejected: that is the *repository's* session,
not the deployment's. A checkout at session 6 measuring a host still deployed at
session 5 would expect grants the deployment has never made. The document is the
authority on what was deployed (ADR 0002); the constant in the source is the
authority on nothing.

## Consequences

- Session 6 needs no edit here, and the failure mode if it does is a red test
  rather than a silent widening.
- **The wider finding is not this constant.** Thirteen security proofs were
  environment-gated on a flag nobody passed for a whole session, so they reported
  as skips in every run and a skip is not a pass. This is the third Session 5
  instance of *a proof that did not execute* — after Run 8's sixteen deselected
  node IDs and D211's `tests/security/` directory — and it is the one that hid a
  wrong constant for three sessions. The operator guide's gate invocation should
  carry `--sentinel-file`, not mention it as optional; that is a Run 10 doc
  change, not a decision.
