# 0193 — A service is terminated by a signal to its process, a rehearsal reads the reader that reads, and the recorded lock digest is an identity

- **Status:** accepted
- **Date:** 2026-09-06
- **Session:** 18, Run 4 (`OPS-REHEARSE-001`–`OPS-REHEARSE-008`, D1015–D1019)
- **Related:** **ADR 0190** (a rehearsal is bounded, reversible, and reads a
  detection that exists), **ADR 0188** (the mirror), **ADR 0015** (the reserved
  health route), **ADR 0158** (the deployed document is the address book),
  **ADR 0159** (`--verbose` adds resolution, never a third party's bytes),
  **D1009** (the environment overrides a pgBackRest configuration file),
  **D976** (a provider hangs), rig 4 (`~/rig18/rig4.sh`, `rig4.txt`).

Amends [0190](0190-a-rehearsal-is-bounded-reversible-and-reads-a-detection-that-exists.md),
whose table of scenarios was written before any of them had been measured.

## Context

ADR 0190 fixed what a rehearsal is and named, per scenario, an induce, a
reader and a reversal. Run 4 measured the three of them that name a third
party's behaviour, and each came out differently from the table:

1. **`docker kill` is not restarted, under any restart policy** (rig 4, four
   arms with controls, D1015). The daemon records a `docker kill` as a manual
   stop and cancels the container's restart manager: an `on-failure:5`
   container killed that way sits at exit 137 with restart count 0 until
   somebody runs `docker start`. A SIGKILL sent to the container's main
   process from the daemon's PID namespace is an unexpected exit, and the same
   policy restarts it within two seconds with restart count 1. `kill -9 1`
   from inside the container's own namespace is ignored by the kernel. The
   table's reversal, *"Compose's restart policy"*, therefore never fires for
   the table's induce.
2. **The doctor reads one route, and `edge-probe` serves it** (D1019). The
   table says *"one stateless service"* and reads *"the doctor's route
   status"*; the doctor asserts 200 on the reserved health route only (ADR
   0015), and that route is `edge-probe`'s. Killing PostgREST would leave every
   doctor check green, which is a rehearsal of nothing.
3. **The doctor's mirror check does not see a failed copy** (D1016). It reads
   the copy record, which `backup.sh mirror` writes only after a pass that
   exits 0; a failed pass writes nothing, so the check reports the previous
   copy until it is two days stale. The reader that names one failed copy is
   the verb's exit, which is the unit's failure.

Two more were gaps rather than measurements. **The doctor had no drift check**
(D1017): `AGT-DRIFT-001` proves the compiler offline, and nothing on a host
compared the lock on disk with the digest the deploy recorded. And **the
registry refusal had three readers, not one** (D1018): `bin/database-ports.py`
read an absent file as an empty registry, `bin/deploy-project.py` read it as
`None` and published the transports `unavailable`, the access broker already
refused; and nothing created the initial registry but an allocation.

## Decision

1. **Service termination sends SIGKILL to the container's main process** (its
   host PID, read from `docker inspect`) **and never runs `docker kill`.** The
   restart policy is the reversal; `docker start` is a fallback the plan
   prints and runs only when the policy did not bring the service back within
   the bound, and that outcome is a rehearsal that read nothing (exit 6), not
   a reversal that failed.
2. **The service terminated is the one whose route the doctor reads:
   `edge-probe`.** The readers are the restart count, the health route, and
   the doctor's `containers` and `route health` checks taken at the moment
   after the kill; whether the doctor saw the gap is recorded either way,
   because a sub-second restart is one the containers check cannot see.
3. **The WAL-archiving scenario's reader is the mirror verb's exit**, which is
   what the unit runs and how the unit fails. The doctor's `backup mirror`
   check is read and recorded as what it reports; the doctor's `wal archiver`
   check is read before and under the block as the control that the primary's
   path was never touched; the copy after the reversal is part of the
   reversal. `OPS-REHEARSE-005` says so.
4. **The doctor gains a tenth check, `capability drift`**: the live SHA-256 of
   the lock on disk against `mcp.capability_lock_sha256` in the deployed
   document. That digest is the one member of an observed block the doctor
   reads, and it is an **identity** — which lock the deploy compiled, as
   `database.container` is which container — compared against a live read and
   never echoed (ADR 0159: the check receives booleans, not digests). ADR
   0158's guard in `test_diagnosis` is replaced by a stricter one that pins
   this single read by its exact shape; `mcp.status` stays unreadable. The
   rehearsal exercises the reader through `--lock-file` against a lock with a
   foreign hash written beside the deployed document; the deployed lock is
   never touched. `--disk-warn-copies` and `--disk-problem-copies` inject the
   disk thresholds the same way, and every injection is carried in the
   check's evidence.
5. **An absent port registry is refused by every reader and created by
   provisioning.** `port_allocations.RegistryMissing` is raised by
   `database-ports.py`'s loader (exit 4 from every verb), the deploy fails by
   name (exit 5) instead of publishing `unavailable`, and
   `provision-host.sh --apply` creates the empty registry exactly once,
   `--check` reporting its absence. An existing registry is never rewritten.
6. **One rehearsal at a time, and a crash is reversible.** An in-progress file
   beside the projects' state directory names the un-reversed scenario and
   records its reversal; a second scenario is refused while it exists;
   `rehearse.sh reverse` replays the record. The reversal runs in a `finally`,
   an observer that raises is a reading not taken (exit 6), and a reversal
   that does not verify keeps the file (exit 7).

Provider loss stays recorded, not induced (D976, D990). The disk is never
filled and the primary's archiving is never blocked (ADR 0190, unchanged).

## Consequences

- `bin/rehearse.sh`, `agentic_postgres.rehearsal`, the doctor's tenth check
  and three flags, the registry refusal in three readers and provisioning's
  creator, `tests/contract/test_rehearsal.py`; the live halves are the trip's
  eight readings on the production host (`OPS-REHEARSE-002`..`008`).
- A rehearsal's evidence record carries the plan as printed, every reading
  as a value the command produced, the verification and the verdict; a
  reader that read nothing is a `§1` row, never a pass.
- The WAL scenario needs the mirror the trip enables; until then it refuses.
