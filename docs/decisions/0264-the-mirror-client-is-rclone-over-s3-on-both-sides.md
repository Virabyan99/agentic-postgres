# 0264 — The mirror client is rclone, over S3 on both sides

- **Status:** Accepted
- **Date:** 2026-10-10
- **Session:** 38, migration repairs before Run 11
  (`docs/plans/session-38-migration-plan.md`, D2285, D2295)
- **Affects:** `versions.in.yaml` and `versions.env` (`MC_IMAGE` →
  `RCLONE_IMAGE`), `compose.yaml` (`backup-mirror`'s build argument),
  `services/backup-mirror/Dockerfile` and `mirror.sh`,
  `src/agentic_postgres/backup_report.py` (`count_objects` replaces
  `count_listing`), `bin/backup.py` (`compose_mirror` passes `run --build`),
  `tests/contract/test_backup_mirror.py`, `docs/recovery-operations.md` §1.
- **Supersedes in part:** ADR 0188's choice of client. Everything else in 0188
  stands: a mirror of the primary, at a second provider, under the primary's
  cipher pass, by a host unit, never by the archiver.
- **Related:** ADR 0110 (bucket-scoped keys), ADR 0220 (a pass has three
  outcomes), ADR 0262 (the secret store already pins this image).

## Context

The mirror image was MinIO's client, `mc`, pinned by digest and BUILT on each
host from that base (ADR 0188). On 2026-10-09 the first mirror on a fresh host
(OVH, migration Run M5) failed at the build: the base is no longer served.
Measured from the workstation, 2026-10-09/10:

| Source | Answer |
|---|---|
| `quay.io/minio/mc` (the pinned tag and digest) | 401 |
| `docker.io/minio/mc` (the pinned tag, `latest`) | 401 |
| `dl.min.io` (the pinned release binary, its checksum, `latest`) | **410 Gone** |
| `docker.io/bitnami/minio-client` | 404 |
| `docker.io/bitnamilegacy/minio-client` | 200 -- a frozen archive, last pushed 2025-08-19 |
| `cgr.dev/chainguard/minio-client` | 200 for `latest` only; no shell |
| `proxy.golang.org`, `github.com/minio/mc` | no tagged version; a 2025-11-06 snapshot |

OVH runs the mirror today on an image carried from Hetzner (D2285). Every
other fresh host -- Session 38's customer slot is the next -- cannot build it.

## Decision

**The mirror is `rclone sync`, from the pinned `docker.io/rclone/rclone`
image, with both remotes over S3.** The two actions and their contract with
`bin/backup.py` are unchanged:

- `copy`: `rclone sync --checksum --fast-list --retries 1 source:<bucket>
  mirror:<bucket>`. `sync` copies a changed object and removes one the primary
  expired, as `mc mirror --overwrite --remove` did (D1000). `--checksum`
  compares size and MD5: both providers publish an MD5 for a single-part
  object over S3 (a native B2 remote would offer SHA-1 only, and the two would
  share no hash). `--retries 1`: one invocation is ONE pass, so ADR 0220's
  single extra pass remains the verb's; rclone's per-request retries -- the
  answer to D1546's one-object flake -- stay on.
- `count`: `rclone size --json`, read on the host by
  `backup_report.count_objects`. The client prints its object on every
  success, so an empty or unreadable answer is None, never zero.
- The credential reaches the client as `RCLONE_CONFIG_<REMOTE>_*` exports,
  built from the four mounted secret files, never as an argument; and
  `RCLONE_CONFIG=/dev/null` means no config file is read or written. Each
  remote carries `no_check_bucket`: each key is restricted to its own bucket
  (ADR 0110) and may not create or probe one. A regional mirror endpoint
  (`s3.<region>.<domain>`, Backblaze's shape) names its signing region.
- **`compose_mirror` passes `run --build`.** Compose builds only a MISSING
  image, so without it a host keeps the first mirror image it ever built
  through every release after -- OVH would have kept `mc` forever.
  `project-runtime.sh up` passes `--build` for the same reason.

The reference is the one ADR 0262's backup already pins and measured against
B2: `docker.io/rclone/rclone:1.75.1@sha256:45401ad7…`, re-resolved for
`linux/amd64` with `docker buildx imagetools inspect` and written as ONE key
(D238: a plain `--update` would re-resolve the moving tags too).

## Measured

Locally, on the pinned image under the service's own constraints (uid 65532,
read-only root, tmpfs `/tmp`, `cap_drop: ALL`, `no-new-privileges`):

- `/bin/sh` and `cut` exist; `rclone v1.75.1`.
- Two env-configured remotes: `sync --checksum` copied two objects and REMOVED
  the stale one; `size --json` printed `{"count":2,"bytes":6,"sizeless":0}`.
- `RCLONE_CONFIG=/dev/null`: no notice, and nothing written to `/tmp`.
- The image built from this tree: the region derived as `us-west-004` for
  B2's endpoint shape and not at all for another; `count` against an
  unreachable endpoint printed rclone's error (no credential in it) and exited
  5; the script's refusals keep their codes (6 no mirror, 2 an empty field, 3
  an empty secret).

Against the providers -- **owed to Sheet RP-2** (after 00:00 UTC, when B2's
daily download allowance has reset, D2288): on beta's real buckets, `size`
on both sides, a `--checksum` dry run (what it would transfer and delete, and
whether it re-copies what `mc` already copied), and a real sync whose final
`size` equals the source's.

## Consequences

- One third party fewer (MinIO), and the mirror's client is the one the
  secret store's backup already depends on.
- Every host builds a new mirror image at its first pass after the deploy;
  `--build` makes each pass contact the build cache, and a pass on a host
  with no registry reachable fails at the build exactly as `mc` did on OVH.
- The first rclone pass over a bucket `mc` filled compares by checksum; what
  it transfers is the measurement Sheet RP-2 owes.

## Rejected

- **Re-pin to `bitnamilegacy/minio-client`.** A frozen archive of a vendor
  that has just withdrawn its free images is the failure D2285 already is.
- **Build `mc` from source** through the Go proxy: no tagged version, a
  toolchain image to pin, and a multi-minute build on every host.
- **Chainguard's image:** `latest` only on the free tier, and no shell for
  `mirror.sh`.
