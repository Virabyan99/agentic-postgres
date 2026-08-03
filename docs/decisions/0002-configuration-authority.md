# 0002 — Configuration authority and transactional rendering

- **Status:** Accepted
- **Date:** 2026-08-03
- **Session:** 1
- **Affects:** `CFG-*`

## Context

Configuration that is authoritative in more than one place is configuration
that will disagree with itself. The failure is always the same: a value is
corrected in the file someone was looking at, and the other copy keeps
running.

Two further constraints shape this decision:

- Generated output must never contain a secret, and must never present an
  endpoint that does not exist as though it were usable. Session 1 has no
  tunnel host, no bound port, and no provisioned credential.
- A render that fails validation must not be able to replace a render that
  passed. Otherwise the recovery path from a bad manifest is "restore from
  memory".

## Decision

**Authority.**

| Concern | Authority |
|---|---|
| Non-secret deployment configuration | `project.yaml` |
| Agent-visible capability surface | `capabilities.yaml` |
| Version candidates | `versions.in.yaml` |
| Immutable version lock | `versions.env` (generated) |
| Numeric bounds | `schemas/project.schema.json` |
| Template version | `VERSION` |
| Requirement identity | `tests/acceptance-registry.yaml` |

Neither manifest may contain a secret value or a secret-bearing URL. Project
identities are never hard-coded in deployable source. Generated files are
disposable products of manifests, source version, and locks.

**Endpoints.** Session 1 emits database and role names, and sets pooled and
direct endpoint status to `unavailable` with `host`, `port`, `url`, and
`password_secret_ref` all `null`. It does not emit angle-bracket placeholders
that resemble connection strings. Session 4 activates real endpoint metadata.

**Rendering is transactional.** `deploy.sh --render-only` validates inputs and
locks, stages into a private directory under `.generated/.staging/`, refuses
symlinked targets, writes each file owner-only, validates the staged
`outputs.json` against its schema, validates the staged Compose model, and
only then publishes.

Publication is a **directory swap**, not a sequence of per-file renames: the
existing project directory is renamed aside, the staging directory is renamed
into place, and on any failure the original is renamed back. Both renames are
on one filesystem. This is a real rollback guarantee rather than a claim of
crash-atomic replacement of several independent files, which is not
achievable. Every generated file additionally records the same input hashes,
so a torn set is detectable.

Publication holds an exclusive `flock` on `.generated/.locks/{project_key}.lock`
for the duration; contention exits `5`.

## Consequences

Makes easy:

- Byte-identical output for identical inputs, because there is no timestamp
  in `outputs.json` and every value has exactly one source.
- Reviewing a configuration change: the diff is in the manifest, never in
  generated output.
- Recovering from a bad manifest: the previous valid render is still there.

Makes hard:

- Every new generated value needs a named authority before it can be added.
  This is the intended friction.
- The renderer cannot run on a filesystem without POSIX mode bits or `flock`.
  See the implementation plan §1 for why that constrains the dev environment.

Enforced by `tests/contract/test_output_schema.py`,
`test_render_atomicity.py`, and `test_render_isolation.py`.

## Alternatives considered

**Per-file atomic rename on publish.** Rejected: three independent `os.replace`
calls have two windows in which the directory holds a mixed set, and no
rollback path once the second succeeds and the third fails.

**Emitting placeholder connection URLs** so that downstream tooling has a
shape to parse. Rejected: a string that looks like a DSN will eventually be
used as one. `null` fails loudly; a placeholder fails at 3am.

**Writing the resolution timestamp into `outputs.json`.** Rejected: it
destroys byte-level reproducibility for no operational benefit. Lock metadata
carries the timestamp instead, in `versions.env`, which is not deterministic
project output.
