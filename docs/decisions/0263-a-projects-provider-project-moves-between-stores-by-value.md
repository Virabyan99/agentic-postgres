# 0263 — A project's provider project moves between stores by value

- **Status:** Accepted
- **Date:** 2026-10-09
- **Session:** 38, migration Run M3 (`docs/plans/session-38-migration-plan.md`;
  D2240, D2241, D2242, D2256, D2259, D2275–D2278)
- **Affects:** `bin/bootstrap-providers.py` and `.sh` (modes `rehome-check` and
  `rehome`, exit 6), `src/agentic_postgres/secret_age.py` (the carried file,
  `judge(carried=)`), `bin/doctor.py` (`doctor secrets` reads it),
  `src/agentic_postgres/dr_kit.py` (an optional artefact),
  `tests/contract/test_provider_rehome.py` (new, `REC-REHOME-001`),
  `docs/provider-bootstrap.md` § *Moving to another store*.
- **Related:** ADR 0011 (ownership recorded by id), ADR 0189 (the kit and
  `--adopt`), ADR 0195 (three outcomes), ADR 0250 (a secret's age), ADR 0255
  (the 429 budget), ADR 0262 (the self-hosted store).

## Context

ADR 0262 moves the deployment's secret store from Infisical Cloud to a
self-hosted instance. Three projects' Infisical projects -- 63 values, among
them every project's pgBackRest cipher pass -- have to arrive there intact, on
the host that already serves them, before the host itself moves (D2240: the kit
that carries a project to a new host binds by project id at the recorded
`api_url`, so the store must move first).

Nothing in the product could do it:

- `--adopt` binds a host to a project BY ID within one store; it refuses a
  different `api_url` and a different provider-inputs digest.
- `--apply` creates the project and GENERATES every generated value. A new
  cipher pass makes every existing backup unreadable (D999).
- A console copy puts every value on a screen, twice, and proves nothing about
  what arrived.

## Decision

**Two modes of `bootstrap-providers`, `--rehome-check` and `--rehome`, copy a
project's values by value from the store its state records to the store the
host manifest names, in one root process on the host, printing names only.**

1. **The source is read as the project's own runtime identity** (D2275), with
   the runtime client (`InfisicalClient`: login and raw reads, its D976 retry
   and ADR 0255's 429 budget). That identity reads every one of these values on
   every start, so the read is the product's proven path. Reading as the
   source store's control-plane identity was the alternative; whether it may
   read values in projects it created was never measured (D2256), and it would
   be one more credential on a sheet.
2. **Everything is read before anything is written.** The set is the
   contract's for the project at the session (facilities applied, the optional
   secrets included). Only a 404 is *absent*; a required value absent stops
   both modes (exit 7) before the destination is contacted.
3. **`--rehome-check` writes nothing anywhere**: the reads, the destination's
   login, one line per name -- `present <8 hex of the value's sha256>`,
   `absent (optional)`, `ABSENT (required)`.
4. **`--rehome`, in this order:** the destination's project (`POST
   /api/v2/workspace` -- a destination that already has the slug refuses here,
   before any value exists there; nothing is looked up by name, D1013); every
   value read, written; the identity `<key>-runtime`, Universal Auth and one
   client secret, the secret written to `*.rehome-pending` files (0400) before
   anything else can fail, as `--apply` writes it; the `viewer` membership;
   **every value read back as the NEW identity, its digest compared in
   memory.** A difference, or a value the new identity cannot read, is **exit
   6**: the pending files removed, the identity revoked, the destination's ids
   printed (D1046), this host unchanged.
5. **Only then the switch**: the old state to
   `bootstrap-state.rehomed-<utc>.json`, the old credential files to
   `*.rehomed-<utc>`, the pending files into place, the new state (schema
   unchanged, so `c3eec1d`'s readers read it -- D2244; the provider-inputs
   digest of the NEW block, so `--plan` reports no changes), the carried ages,
   and a record `rehome-<utc>.json` beside the state (D2277). The source is
   never written to: its project and identity still work, and the rollback is
   the kept files moved back with the block restored.
6. **The ages travel** (D2242, D2276). The new store dates every value to the
   move. `secret-ages-carried.json` holds each value's times AT THE SOURCE
   (re-rendered, never the provider's string; a list of entries, because a
   secret's name ends in `_password` and the sensitive-key guard refuses it as
   a key). `doctor secrets` reads it: while the new store's version is **1**
   the value is still the one the move wrote and the carried time answers
   (`carried`); a later version is a replacement since the move and the
   provider answers; no version is `unknown`, because which one is the age
   cannot be told. A second move keeps the first's times. A file that is
   there and unreadable is `unknown` for every secret, never a fall back to the
   move's date (ADR 0195).
7. **The kit carries the file when there is one**, as an optional artefact:
   exported, hashed and validated when present; `PROJECT_ARTIFACTS` and every
   older kit unchanged.

## Consequences

- The move of a store is two commands per project on the host and one block
  edit, measured by the product's own reader at both ends.
- **The window** (D2259): materialization reads the store the HOST names with
  the project id the STATE records, so between the block changing and a
  project's rehome that pair is wrong for that project. The rehomes of every
  project on a host run back to back, with no deploy, restart or
  materialization between them.
- Not done: moving values the contract does not declare (nothing reads them);
  retiring the source (a later, separate act); a rehome across organisations of
  ONE instance (the same command does it, unmeasured).
- `version` = 1 on a fresh write was measured on the self-hosted store
  (2026-10-09, 13 values, `createdAt` = `updatedAt`) and on the Cloud (D2022);
  the API's `version` field at the self-hosted store is read on the first real
  rehome (Run M4).
