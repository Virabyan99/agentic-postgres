# 0010 — Secrets are individual files in immutable generations

- **Status:** Accepted
- **Date:** 2026-08-04
- **Session:** 2
- **Affects:** `SEC-SECRET-001`, `SEC-SECRET-002`, `SEC-SECRET-003`, `DEP-ISO-002`

## Context

Session 1's strongest inherited invariant is that no secret value enters source
control, Compose interpolation, process arguments, image layers, or logs. It
was cheap to hold because Session 1 had no secrets. Session 2 has real ones, and
every convenient mechanism for getting a credential into a container violates
it:

- `--env-file production.env` puts every value in a file on disk and in
  `docker compose config` output;
- `KEY=$(get-secret) docker compose up` puts the value in `ps aux` and in shell
  history;
- `infisical export > .env` fetches secrets nobody declared and persists them;
- environment variables of any kind appear in `docker inspect`, which any
  process that can reach the Docker socket can read.

There is a second, less obvious problem. Secrets published one file at a time
produce windows in which a container can start against a half-written set — new
password, old certificate — and that failure is intermittent and looks like a
provider outage.

## Decision

**A secret is an individual file, granted to one service.** Not an environment
variable, not a bundle. Files are exposed through Compose `secrets` and appear
at `/run/secrets/{target_file}`. A service receives exactly the files listed for
it in `secrets.required.yaml` and nothing else.

**Retrieval is by exact declared key, one at a time**, with secret-reference
expansion and imports disabled, through the direct HTTPS API client in
`src/agentic_postgres/infisical_client.py`. Responses are parsed in memory. No
bulk export is ever written to disk.

**Publication is by complete immutable generation.** The materializer fetches
every declared key into memory, writes a *new* generation directory under
`/var/lib/agentic-postgres/secrets/{project_key}/generations/{generation_id}/`,
validates names, ownership, modes and presence across the whole set, `fsync`s
files and directories, and only then atomically replaces
`active-secret-generation.json`. Running containers keep their previous complete
generation until the new one is validated and the affected services are
recreated successfully. Nothing ever binds an in-progress directory.

**Ownership is set by the host, not by Compose.** Each file is `0400` and owned
by the fixed numeric UID/GID its consumer declares. Compose's file-backed secret
`uid`/`gid`/`mode` fields are not relied upon. Root ownership is rejected at
contract-validation time: a root-owned file mounted into a container that drops
privileges is unreadable by the process that needs it, and the usual fix is to
widen the mode.

**One file per consumer, even for one provider key.** Two services sharing a
file would need one permission set to satisfy two runtime users. Separate files
in separate per-service directories make "A cannot read B's copy" a filesystem
property rather than a convention.

**Paths are derived, never supplied.** `{project_key}` and the service name are
path components computed by the materializer. A target filename must be a simple
basename — the schema pattern excludes `/`, and `secrets_contract.py` re-checks
it — so a declaration cannot escape its generation directory. A project manifest
that could name its own secret directory could name another project's.

**Reboot policy fails closed.** Systemd attempts fresh materialization first. A
bounded last-known-good fallback is permitted *only* when the provider is
temporarily unreachable, the existing generation is complete, its contract hash
and provider identity match deployment state, permissions pass, and no required
secret is marked `must_refresh_on_start`. Invalid or revoked credentials are
never a fallback condition — that is an authorization failure wearing an outage
costume. Every fallback is recorded as `fresh: false` in deployment state and
evidence.

## Consequences

Makes easy:

- The leak surface is enumerable, and Session 2 enumerates it: repository,
  `.generated/`, evidence, rendered Compose output, `docker inspect`,
  `docker history`, container logs, the systemd journal. A random sentinel is
  materialized through the real path and searched for in all of them.
- Rotation is a new generation plus a restart of affected services. The old
  generation stays until convergence succeeds, so a failed rotation is not an
  outage.
- Adding a grant is a reviewable diff in one committed file.

Makes hard:

- Secret material persists on disk between boots, unencrypted at rest beyond
  filesystem permissions. This is the deliberate trade against tmpfs, which
  cannot survive a reboot without re-fetching and therefore cannot start a host
  whose provider is briefly unreachable. A later ADR may replace persistent
  generations with tmpfs or encrypted systemd credentials **without changing the
  per-service secret contract** — that is why the contract is a separate file.
- Old generations accumulate and need a bounded retention rule. A generation
  referenced by running or rollback state is never pruned.
- Services cannot read configuration from the environment, so every consumer
  needs file-reading code.

Secret-zero is **not** eliminated and this ADR does not claim it is. The
organization control-plane credential and one per-project Universal Auth client
secret live on the host as root-owned files. What is bounded is how far they
travel: the bootstrap credential is used only by `bin/bootstrap-providers.sh`,
is never copied into project runtime state, and is never held by a runtime
service.

## Alternatives considered

**Environment variables from a generated `.env`.** Rejected: the value lands in
`docker inspect`, in `docker compose config`, and in a file whose lifetime
nobody manages. This is the single most common way a credential leaks in a
Compose deployment.

**Docker Swarm secrets.** Rejected: requires Swarm mode, which is out of scope,
and Swarm secrets are still delivered as `/run/secrets` files — the same
mechanism with an orchestrator attached.

**tmpfs generations.** Rejected for P0, not on merit: it is strictly better at
rest and strictly worse at boot, because a host that reboots while the provider
is unreachable cannot start. Named as the successor in the paragraph above.

**Publishing files individually into a stable directory.** Rejected: it creates
a window in which a service can start against a mixed set, and the failure is
intermittent. Generations exist to make that state unrepresentable.

**Trusting Compose's secret `uid`/`gid`/`mode`.** Rejected: it moves ownership
into the file that also declares the mount, so a mistake there is invisible in
a permission audit of the host. Setting ownership before Compose sees the file
makes `namei -l` the check.
