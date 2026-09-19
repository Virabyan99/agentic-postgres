# 0221 — Capacity is declared, admission decides, and a reading reports

- **Status:** Accepted
- **Date:** 2026-09-19
- **Session:** 31, Run 1 (D1583, D1584, D1585, D1587, D1592, D1596, D1601,
  D1606, D1608)
- **Affects:** `schemas/host.schema.json` (enum `[2]` → `[2, 3]`),
  `host.example.yaml`, a new `src/agentic_postgres/capacity_reading.py`, a new
  `bin/admit.sh` / `bin/admit.py`, `bin/deploy-project.py` step 0,
  `bin/doctor.sh` and `bin/doctor.py` (two readings behind two verbs),
  `docs/session-02-operator-guide.md`'s exit-code table (a twelfth code). **No
  migration, no deployed-document field, no outputs/capability/lock/secret
  schema move** (D1591).
- **Related:** ADR 0195 (a reader has three outcomes and reports the third),
  ADR 0162 (what a bump permits), ADR 0169 (`CONFIGURATION` vs `MACHINE`), ADR
  0213 (a reading with no threshold), ADR 0157/0158 (the doctor/deploy split;
  the document is the address book), D52, D765, D767, D959, D1441.

## Context

The node is a 3814 MiB, 2 vCPU, 38 G machine with **no swap**, and until this
session nothing in the product knew that. `host.yaml:13-14` carried *"38 G
disk, 3.7 GiB RAM"* as a **comment, read by nothing**. `/proc/meminfo`,
`shutil.disk_usage`, `os.statvfs` and `free` have zero hits across `src/` and
`bin/`.

What does exist is a **per-project, compile-time** memory budget.
`config.unreclaimable_mb(budget)` is `shared_buffers + maintenance_work_mem +
max_connections × PER_BACKEND_ANON_MB` — **304 MiB** at the release defaults —
and `config._validate_memory_budget` refuses a project whose figure exceeds
`HOST_MEMORY_GUARDRAIL_MB` (1600). **That check is per project and is never
summed across projects.** Two projects at 304 each are admitted
independently, and nothing anywhere adds them up.

The obvious rule — refuse when the deployed projects' `mem_limit`s plus the
candidate's exceed the host's RAM — **refuses the deployment that is running
today**. Six services carry a `mem_limit` (768 + 384 + 384 + 384 + 128 + 192 =
**2240 MiB per project**, 4480 for two) against a 3814 MiB host. D767 measured
this in Session 14 and said it plainly: the caps in aggregate already exceed
the machine's RAM, **so they were never a reservation**. A decision built on
them would refuse the thing it exists to protect, which is a stop condition,
not a feature.

The figure that *is* a claim on the host — the number the schema computes and
the document publishes on both branches as what the host must actually find —
is `database.budget.unreclaimable_mb`.

Three further facts were measured in Run 1 and shape the decision:

- **`op` cannot read a deployed document.**
  `/etc/agentic-postgres/projects/<key>/` is `drwx------ root root`, so the
  committed sum is legible only to root (D1606). A reader that ran unprivileged
  and quietly summed zero would admit everything.
- **A candidate budget that fails admission must still be a legal project**,
  or the live refusal proves nothing. At `shared_buffers_mb: 896` alone,
  `_validate_memory_budget` refuses for `shm_size_mb`, and with shm raised it
  refuses again for `memory_limit_mb` (D1608).
- **There is no per-project disk claim anywhere**, and a candidate's PGDATA is
  unknowable before it runs (D1596).

## Decision

**Capacity is a declaration the operator types, admission is a decision that
may fail closed, and the two doctor readings are reports that may not.**

1. **`host.yaml` schema 3** requires a `capacity` object with exactly four
   positive-integer members — `memory_mb`, `reserve_memory_mb`, `disk_gb`,
   `reserve_disk_gb`. The enum widens to `[2, 3]`; **schema 2 stays valid and
   reports the declaration absent**. There is no migrator: a default *measured
   at first read* would be a reading standing in for a declaration, which is
   the exact fold ADR 0195 forbids. `host.example.yaml` moves to schema 3 and
   declares `memory_mb: 3814` and `reserve_memory_mb: 2214`, so that
   `memory_mb − reserve_memory_mb == HOST_MEMORY_GUARDRAIL_MB` — asserted by a
   test, which is how the existing per-project guardrail becomes a host-level,
   cross-project number **without moving**.

2. **Admission charges the unreclaimable claim, not the ceiling:**

   ```
   Σ_deployed unreclaimable_mb (projects other than the candidate)
     + candidate's unreclaimable_mb
     + reserve_memory_mb
     ≤ memory_mb
   ```

   `Σ mem_limit` is reported on its own line of the reading, labelled
   *ceilings, not reservations (D767)*, and decides nothing.

3. **Disk is a floor, not a sum.** Refused when
   `free_gb at the Docker root − reserve_disk_gb < 0`. `disk_gb` exists for the
   reading to compare against `df`'s total; a declaration that disagrees with
   the measurement by more than 5 % is **reported as such, not refused**.

4. **Admission runs on every deploy**, at step 0, before any render, with the
   candidate's own key excluded from the committed sum. A redeploy that raises
   `shared_buffers_mb` is the same decision as a new project. A refusal at step
   0 changes nothing on the host.

5. **With no declaration** (a schema-2 manifest), a candidate **with no
   deployed document is refused** and one **with a document is admitted**. This
   is what keeps the release `minor`: no operator edit precedes the upgrade.

6. **An undetermined figure refuses, naming the figure.** A decision may fail
   closed. This is why an unprivileged run cannot admit by accident.

7. **Exit code 12 — *admission refused: the declared capacity cannot hold this
   project***. `EXIT_ADMISSION_REFUSED = 12` lives in `capacity_reading.py`
   and is named in the header blocks of `deploy.sh`, `bin/deploy-project.py`,
   `bin/admit.sh` and `bin/admit.py`, and in the one convention table
   (`docs/session-02-operator-guide.md:259-276`). A refusal is neither a
   precondition the operator creates (4) nor a check that failed (6): it is a
   decision against a declaration, and `$?` must tell the three apart.

8. **The two readings have two outcomes, never four.** `doctor capacity` and
   `doctor usage` print **`OK` with every figure, or `UNKNOWN` naming the one
   figure they could not read** — `agent record`'s shape (ADR 0213, D1441),
   never `WARN`, never `PROBLEM`. A threshold in the one command that runs as
   root on production could fail a host that works. `--json` carries every
   figure as a number or as `null` beside a `reason`.

9. **`doctor usage` reports seven figures and not `storage_objects`** (D1601):
   the object listing is reachable only through the credential the storage
   container alone holds, and a second holder of that credential is this
   stage's declared failure mode. A member reported `unknown` forever is a
   field with no reader.

**Not built here:** load shedding, `apg tune`, a per-project disk declaration,
a capacity figure in the deployed document, and any automatic adjustment of a
running project. Admission refuses a new project; it never degrades a running
one.

## Consequences

- The host declaration and the release move together for the first time:
  `host.yaml` gains a schema version the product reads rather than a comment.
- Two projects at the release defaults commit 608 MiB against a declared 3814
  with a 2214 reserve, leaving **992 MiB safe available** — measured in rig
  31e. A third project at the defaults is admitted; one at 1072 is refused.
- The reserve is where the sidecars' anonymous memory (D959 measured 348 MB
  per project against 304 claimed), the edge's 31 MB and the OS live. It is
  deliberately large, and it is the number an operator will want to argue
  with — which is the point of making it a declaration.
- `bin/admit.sh` is a **root** command on the operator's sheet, because the
  committed sum is root-readable only (D1606).
- Nothing in the deployed document changes, so the isolation matrix is
  unchanged and the stage plan's expectation that Session 31 classifies a new
  field is **recorded as unmet for a reason** (D1591): there is nothing per
  project to classify.

## Alternatives considered

- **Sum the `mem_limit`s.** Refuses today's own deployment (D767). Rejected.
- **Measure the host at first read and use it as the default.** A reading
  standing in for a declaration; ADR 0195's fold. It also makes the answer
  depend on when the first read happened. Rejected.
- **Require the operator to edit `host.yaml` before upgrading.** Four numbers
  would price the release `major` under ADR 0162. Rejected in favour of
  *undeclared → new refused, redeploy admitted*.
- **A thirteenth ADR 0162 class for capacity.** Nothing rendered establishes
  it; the declaration is a host input, not a project artefact. Rejected.
- **Thresholds on the readings.** `doctor` exits 6 on a problem and runs as
  root on production; a capacity threshold could fail a host that works, which
  is D1441's lesson from `agent record`. Rejected.
