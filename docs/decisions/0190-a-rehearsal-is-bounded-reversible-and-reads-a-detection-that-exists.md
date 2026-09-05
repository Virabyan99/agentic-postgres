# 0190 — A rehearsal is bounded, reversible, and reads a detection that exists; the disk is never filled

- **Status:** accepted
- **Date:** 2026-09-05
- **Session:** 18, Run 1 (`OPS-REHEARSE-001`–`OPS-REHEARSE-008`, D989, D990)
- **Related:** **ADR 0158** (the deployed document is the address book, not the
  diagnosis), **ADR 0163** (three statuses), **ADR 0165** (`anon` is the memory
  figure), **D145/D548** (the state is in a field), **D553** (a cumulative
  counter cannot answer a point-in-time question), **D976** (a provider hangs),
  **D982** (a proof that had never executed), the alert rules the render emits.

## Context

The stage plan asks for *"bounded failure rehearsals -- service termination,
database restart, backup credential failure, disk threshold breach, WAL
archiving failure, registry loss, capability drift. These test detection and
graceful degradation, not automatic failover."* Checked against the tree
(D989): the detections exist -- the doctor's `disk_headroom`, `repository` and
`archiver` checks; six alert rules per project; `AGT-DRIFT-001` -- and nothing
has ever induced any of these failures on purpose, read the detection, and put
the host back. One detection is missing outright: an absent port registry is
recreated empty by the next allocation, which could hand a running project's
port to another. And one item on the list, *coordinator loss*, names a
component that does not exist (D990).

A reader that has never seen its failure is D982's shape: a proof that had
never executed. The rehearsals exist to execute those readers.

## Decision

**`bin/rehearse.sh SCENARIO --outputs FILE [--plan]` induces one bounded,
reversible failure, reads the detection that exists, reverses the failure, and
prints all three; `--plan` prints and does nothing.** Each scenario is a module
in `agentic_postgres.rehearsal` with `induce`, `observe` and `reverse`, and the
verb refuses to induce a second scenario while one is un-reversed.

The eight scenarios and their readers:

| Scenario | Induce | Read | Reverse |
|---|---|---|---|
| service termination | `docker kill` one stateless service | the doctor's route status and the restart | Compose's restart policy; the doctor again |
| database restart | `docker restart` the database | every dependent service's reconnection; an agent read | none needed; the read is the reversal |
| backup credential failure | a `check` run with a throwaway configuration naming a wrong credential | the check's exit and the repository it names | nothing was changed |
| WAL archiving failure | a firewall rule on the backup egress network blocking the MIRROR's endpoint | the mirror unit's failure and the doctor's mirror check | the rule removed; the next copy |
| registry loss | the port registry moved aside | every verb's refusal; the deploy's refusal | the registry moved back |
| disk threshold | the doctor run with an injected threshold | `disk_headroom` reporting `warn` and `problem` | nothing was changed |
| capability drift | a lock file with a foreign hash beside the deployed one | the doctor's drift check | the file removed |
| provider loss | recorded, not induced: D976 measured it on the trip | -- | -- |

**The disk is never filled, on any host.** The reader is rehearsed with an
injected threshold, and the requirement says so. **Archiving to the primary is
never blocked**: the WAL scenario blocks the mirror's path, whose loss the
archiver does not feel (ADR 0188). **A rehearsal that cannot be reversed is not
a rehearsal**; it is refused and recorded.

**Registry loss becomes a refusal before it is rehearsed**: `load_registry` on
an absent file raises, every verb reports it, and the initial registry is
provisioning's to create, never allocation's.

## What a rehearsal proves, and what it does not

It proves that the reader reads: that the failure this deployment would have
on a bad day is one its own diagnosis names within a bound. It does not prove
recovery time, failover, or resilience under load; none of those is claimed.

## Consequences

- Run 4 builds the verb, the eight modules, the registry refusal, and the
  offline halves with recorded docker, systemctl and iptables; the live halves
  are the `OPS-REHEARSE-*` proofs on the trip.
- Every scenario's reading is pasted into the trip's record; a reader that
  reads nothing is a §1 row, not a passed rehearsal.
