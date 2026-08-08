# 0042 — Host port allocation is state, keyed by the identity the volume carries

Status: proposed
Date: 2026-08-08
Session: 4, Run 1
Affects: DBX-PORT-001, DEP-ISO-004

Accepted in Run 4, the run that writes the allocator.

## Context

Each project needs two stable host-loopback ports, one per transport. Stable
matters more than it sounds: an allocation that moves silently breaks every
developer's saved tunnel, every documented command and every runbook example,
and it does so without any error message — the port is simply someone else's
now, or nobody's.

So an allocation is durable state, and durable state needs a key. The Session 4
runbook proposed minting a fresh `project_instance_id` for the purpose.

The project already has one. `app_private.project_identity.instance_uuid` is
generated once on the first bootstrap of an empty volume and **recovered** on
every bootstrap since. It is the thing `postgres-bootstrap.py` refuses a foreign
volume over (ADR 0030, exit 11), which makes it the only identifier in the
system that is bound to the data rather than to the configuration that produced
it.

A second immutable identity would be a second answer to "which project is this",
and the first one is already the answer the data gives.

## Decision

**The allocation key is the instance UUID the volume carries.**

1. The registry is `/etc/agentic-postgres/database-port-allocations.json`,
   following `edge-state.json` as the precedent for host-level JSON state
   (ADR 0020), validated against a committed schema, and written atomically.

2. Every allocation records the instance UUID, the project key, both ports,
   a state (`reserved` | `active` | `released`), and the timestamps of each
   transition. The project key is recorded for humans; **the UUID is what is
   matched**.

3. The whole reserve → publish → verify sequence runs under a host lock. Two
   deploys racing for the last free port is not a hypothetical: `deploy.sh` is
   run by hand, and a re-run after a timeout is the normal operator response to
   a slow one.

4. `reserved → active` only after the endpoint checks pass. A crashed first
   deploy therefore leaves a reservation that can be proved unadopted, rather
   than an active allocation that nothing is listening on.

5. Reuse is the default. Reassignment requires an explicit release after project
   shutdown *and* identity confirmation. An initialized project is never
   reassigned because a lower port became free.

6. Both ports are allocated as one transaction. A project with a pooled port and
   no direct port is a state nothing knows how to converge.

## Consequences

A restored volume brings its allocation's identity with it, so restoring a
backup onto a fresh host and re-deploying reaches the same two ports without
anyone recording them separately. That is the property the fresh-UUID design
would have lost, and it would have lost it silently.

An allocation whose UUID matches no live project is detectable and, more
usefully, *safe to leave alone*: it is either a project that is currently down
or a volume that will come back. The registry is therefore append-and-amend
rather than a live inventory, and pruning it is an operator action with its own
confirmation, not a side effect of a deploy.

The registry is host-global while everything else Session 4 writes is
per-project. That is the same shape as `edge-state.json` and carries the same
risk: one file whose corruption affects every project. It is validated before
every mutation and never rewritten in place.

## Alternatives considered

**A fresh `project_instance_id` minted by the deploy.** The runbook's proposal.
Rejected: it is a second immutable identity for the same object, and the two
would disagree the first time a volume was restored under a different project
key — the case where getting it right matters most.

**Derive the ports deterministically from the project key by hash.** No state,
no lock, no registry. Rejected: collisions are silent and unresolvable (two keys
hashing to one port cannot both be right), and the first collision would arrive
on a host that already had both projects working.

**Let Docker choose an ephemeral port and record what it chose.** Rejected: the
recording is the same registry, so it buys nothing, and it gives up stability
across recreation, which is the entire requirement.

## Proofs

Written in Run 4 and Run 9. Named here so the ADR can be checked against them:

- `tests/contract/test_port_allocations.py::test_an_allocation_is_matched_by_instance_uuid_not_project_key`
- `tests/contract/test_port_allocations.py::test_both_ports_are_allocated_as_one_transaction`
- `tests/contract/test_port_allocations.py::test_a_reservation_is_not_adopted_as_active`
- `tests/deployment/test_session4_host.py::test_redeploy_reuses_the_existing_allocation`
- `tests/deployment/test_session4_convergence.py::test_allocations_survive_restart_and_reboot`
