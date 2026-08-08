# 0038 — The deployed document records the generation it verified, not the one that is current

Status: accepted
Date: 2026-08-08
Session: 3, Run 8

## Context

`bin/materialize-secrets.sh` writes a new generation directory on every run and
repoints `active-secret-generation.json` at it. `bin/project-runtime.sh up` runs
it, so every start — deploy, `systemctl restart`, boot — produces a new
generation identifier.

`deploy-project.py` records the generation it observed into the deployed
document's `secrets.generation_id`. That document is written once, by the deploy,
and is not rewritten afterwards.

So the two values agree at the end of a deploy and diverge at the next start.

`tests/security/test_session2_secrets.py::test_the_active_generation_pointer_names_a_real_generation`
asserted they were equal. It passed for two sessions, and passed for the wrong
reason: on this host nothing had ever restarted a project between a deploy and a
gate run. Run 8 restarts projects deliberately, and the reboot restarted them
without asking. The gate then failed with the pointer at `f882cd50405db031` and
the document at `8b8e0a2d7afdc099` — two correct values that were never supposed
to be the same one.

The test's own name says what it is for: *the pointer names a real generation*.
Three of its four assertions measure that. The fourth measured something else.

## Decision

**The deployed document records the generation the deploy verified. The pointer
records the generation that is current. They are different facts and nothing
asserts they are equal.**

Rewriting the document from the boot path was considered and rejected: it would
mean systemd mutating root-owned `/etc` state at every boot, on a path that runs
with no operator present, in order to keep a historical record from being
historical. The document's value is that it says what the deploy saw.

The equality is replaced by a strictly stronger assertion —
`test_the_running_containers_mount_the_generation_the_pointer_names` — which
compares the **running containers' mounts** against the pointer. Two files
agreeing said nothing about any process; this fails if a container is still
holding a superseded generation, which is precisely the state a start that
materialized but did not recreate would leave behind, and precisely what a
rotation must produce and then clear.

## Consequences

`secrets.generation_id` in a deployed document is an audit fact about a
deployment, not a description of the live system. Anything wanting the live
value reads the pointer, which is where the launcher, the bootstrap plane and
the grant surface already read it.

Generations accumulate with no pruning (a carried-in open item). When pruning
arrives it must not remove the generation a deployed document names without
saying so, or the audit trail becomes a dangling identifier.

Replacing an assertion in a currently-passing Session 2 contract test is what
made this an ADR rather than an edit. The replacement is stricter than what it
removes, which is the same standard ADR 0017 sets for leaving `FUTURE_STUBS`.

## Proofs

- `tests/security/test_session2_secrets.py::test_the_active_generation_pointer_names_a_real_generation`
- `tests/security/test_session2_secrets.py::test_the_running_containers_mount_the_generation_the_pointer_names`
