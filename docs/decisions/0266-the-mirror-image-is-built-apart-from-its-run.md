# 0266 — The mirror image is built apart from its run

- **Status:** Accepted
- **Date:** 2026-10-10
- **Session:** 38, Run 12 (`docs/plans/session-38-implementation-plan.md`,
  D2311)
- **Affects:** `bin/backup.py` (`compose_mirror` builds, then runs),
  `tests/contract/test_backup_mirror.py`.
- **Amends:** ADR 0264's `run --build`. Its reason (a host must rebuild the
  mirror image every release) stands; its form does not.

## Context

ADR 0264 made `compose_mirror` pass `run --build`, because Compose builds only
a MISSING image and OVH had kept an `mc` image carried from Hetzner (D2285).
Its measurement on the real buckets (Sheet RP-2) ran the image with a plain
`docker run`; the product's own path, `bin/compose.sh … run --build --rm
backup-mirror count`, had never executed.

It executed first in Run 12, inside the slot's creation (operation
`91bc154a`): the full backup succeeded, the copy succeeded (exit 0, first
pass), and the step failed with *"the copy completed and the mirror bucket
could not be listed afterwards (exit 0)"*. `bin/compose.sh` sets
`BUILDKIT_PROGRESS=plain`, and with stdout a pipe `docker compose run --build`
writes BuildKit's progress (`#1 [internal] load local bake definitions …`) to
STDOUT ahead of the container's output, so `count_objects` met text, not JSON,
and read None. Every mirror pass through the verb fails the same way: the
nightly units of every project would exit 5 with the copy made and the record
not written.

## Measured (2026-10-10, WSL, Compose v5.1.3; OVH runs v5.6.0)

A one-service rig whose container prints `{"count":2,…}`, with
`compose.sh`'s environment (`DOCKER_BUILDKIT=1`, `BUILDKIT_PROGRESS=plain`),
stdout to a file, stdin `/dev/null`:

- `run --build --rm`, image missing: exit 0, stdout **does not parse**
  (BuildKit's progress first). Image present: the same.
- `run --rm` without `--build`, image present: parses (the control).
- `--progress quiet run --build --rm`: parses, missing or present; a broken
  build still exits 1 with its error on stderr.
- `build svc`, then `run --rm svc`: parses; under `profiles: [mirror]` the
  build works with `--profile mirror` (and without).

## Decision

`compose_mirror` makes two calls through `bin/compose.sh --runtime --profile
mirror`: **`build backup-mirror`**, then **`run --rm backup-mirror <action>`**.
A build that exits non-zero is the call's answer — its exit and output — and
nothing runs, so a container never runs on whatever image the host held
before. The run's stdout is the container's alone.

Rejected: `--progress quiet` on the run. It parses in the rig, but it makes a
parsed answer depend on a display flag beating an environment variable the
wrapper sets on purpose, and a quiet build that succeeds is indistinguishable
in the log from no build at all. Rejected: reading the last line of stdout as
the JSON — a parser that tolerates whatever precedes the answer is the shape
ADR 0195 refuses.

## Consequences

- Each pass pays two Compose invocations; an unchanged build is the layer
  cache's (about 2 s measured on the host in the failing operation's log).
- The proof is the product's own command on the host after the redeploy:
  `bin/backup.sh mirror` on a project, the record written, then the slot's
  creation in the lifecycle (Run 12).
