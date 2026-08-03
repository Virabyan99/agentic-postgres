# 0004 — Version lock format and offline verification

- **Status:** Accepted
- **Date:** 2026-08-03
- **Session:** 1
- **Affects:** `CFG-*`, and the release gate's "no floating tag" criterion

## Context

The runbook requires `bin/lock-versions.sh --check` to verify that
`versions.env` is "in sync with committed candidate inputs according to the
chosen lock format" — without ever choosing the format. It also requires
`--check` to make **no network call**.

Those two constraints together decide most of the design. Anything `--check`
verifies must be derivable from two files on disk, because a check that needs
a registry is a check that passes when the registry is down and fails when it
is slow. It would also need credentials in CI, which the runbook forbids.

## Decision

`versions.env` is a flat `KEY=VALUE` file:

- Keys match `^[A-Z][A-Z0-9_]*$`.
- Values are unquoted, untrimmed, and never expanded.
- One assignment per line; comments occupy whole lines.
- No `export`. The file is passed to Compose with `--env-file` and is never
  shell-sourced.

It carries this metadata:

| Variable | Meaning |
|---|---|
| `APG_LOCK_FORMAT` | Format version of this file |
| `APG_VERSIONS_IN_SHA256` | SHA-256 of `versions.in.yaml` at generation time |
| `APG_LOCKED_AT` | Resolution timestamp, ISO-8601 UTC |
| `TARGET_PLATFORM` | The one platform every digest was resolved for |
| `PYTHON_VERSION` | Copied from `versions.in.yaml`; no registry call |
| `COMPOSE_MINIMUM_VERSION` | Floor, not an equality |

Image references use `registry/repository:tag@sha256:<64 lowercase hex>`. The
digest is authoritative; the tag is retained only so an operator can read what
the digest refers to.

**`--check` performs exactly five verifications, all offline:**

1. Parse strictly — reject malformed lines, invalid variable names, duplicate
   variables, and quoted or padded values.
2. Recompute `sha256(versions.in.yaml)` and compare against
   `APG_VERSIONS_IN_SHA256`.
3. For each declared image, confirm the lock has a matching entry whose
   `registry/repository:tag` portion is byte-equal to the candidate, whose
   digest is well formed, and whose tag is not floating.
4. Confirm `TARGET_PLATFORM`, `PYTHON_VERSION` (against both the candidate file
   and `.python-version`), and the package versions agree.
5. Confirm no variable exists in the lock that the candidate file does not
   declare.

`APG_LOCKED_AT` lives here rather than in `outputs.json` because `versions.env`
is not deterministic project output. Putting a timestamp in `outputs.json`
would destroy byte-identical rendering — see plan decision U.

## Consequences

Makes easy:

- Verification works in CI with no registry credentials and no network.
- Step 2 alone detects *any* edit to the candidate file, so no drift can be
  invisible; step 3 exists to make the message point at the offending image
  rather than at an opaque hash mismatch.
- Step 5 means removing a component from `versions.in.yaml` cannot leave a
  stale entry behind that Compose might still interpolate.

Makes hard:

- Every candidate change requires re-running `--update`, which needs network
  and Buildx. That friction is intended: a dependency change should be a
  deliberate, reviewable commit.
- `--check` cannot detect that a digest has been *deleted from the registry*.
  Nothing offline can. That is a real residual risk and is accepted: the
  digest is still immutable, and a pull failure surfaces it loudly.

Enforced by `tests/contract/test_version_lock.py`, which copies the script and
the two files into a temporary directory and breaks one thing at a time.
Asserting only that `--check` passes on the real lock would prove nothing
about whether it can detect anything.

## Alternatives considered

**A generated YAML or JSON lock.** Rejected: Compose consumes `--env-file`,
which is `KEY=VALUE`. Any other format would need a conversion step between
the lock and the thing that reads it, and that step is where drift lives.

**Recording only the digest, dropping the tag.** Rejected: a bare digest is
unreadable in review. `pgvector/pgvector:pg18@sha256:6916733…` tells a reviewer
what changed; `sha256:6916733…` does not.

**Verifying digests against the registry during `--check`.** Rejected: it
makes an offline, credential-free check impossible, and it would fail for
reasons unrelated to the repository being correct.

**Unqualified repository names** (`traefik:v3.5`). Rejected: resolution then
depends on the client's configured registry list, which is not a property of
this repository, so the same lock could mean different images on two machines.
