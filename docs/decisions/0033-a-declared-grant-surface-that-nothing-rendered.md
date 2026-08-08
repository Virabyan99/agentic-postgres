# 0033 — A declared grant surface that nothing rendered

- **Status:** Accepted
- **Date:** 2026-08-08
- **Session:** 3
- **Affects:** `src/agentic_postgres/secret_override.py` (new),
  `bin/render-secret-override.py` (new), `bin/project-runtime.sh`,
  `bin/compose.sh`, `compose.yaml`, `tests/contract/test_secret_override.py` (new)

## Context

`compose.yaml` has never carried a top-level `secrets:` block or a per-service
grant. The comment above `secret-check` says why, and has since Session 2:

> The `secrets:` grant and the top-level secrets block are NOT here: the source
> path is an immutable generation directory whose identifier does not exist
> until materialization runs, so the runtime override supplies them.

The runtime override did not supply them. `runtime_override.build_override`
returns router labels and nothing else. `bin/compose.sh` has a function called
`assert_secret_sources_are_project_scoped` that scans the resolved model for
`file:` sources; the resolved model contained none, so it scanned an empty list
and passed.

Session 2 could not notice. Its only secret is consumed by `secret-check`, a
`session2-verify` service no deploy starts, and every Session 2 proof reads the
materialized *files* — ownership, mode, generation directory — rather than a
container's view of them. `SEC-SECRET-002` is green and measures a filesystem.

Session 3 is where it stops being invisible. `POSTGRES_PASSWORD_FILE` names
`/run/secrets/postgres_init_superuser_password`; with nothing mounting it, the
entrypoint finds no file and the cluster does not initialise. Measured before
the host: `docker compose config` for the `session3` profile reported
`top-level secrets: None`.

## Decision

**A generation's grant surface is rendered at start, into a second override.**

`src/agentic_postgres/secret_override.py` builds the block from
`secrets.required.yaml` and one generation identifier;
`bin/render-secret-override.py` writes it into the project's rendered directory;
`bin/project-runtime.sh` runs it **after** materialization and **before**
`compose up`; `bin/compose.sh` loads it in `--runtime` mode and *requires* it for
`up`, `restart` and `run`.

Two overrides, not one, because the two facts have different lifetimes. The
router labels and the rendered directory's path are fixed for the life of the
deployment and are written once by the deploy. The generation identifier changes
on **every start** — materialization writes a new immutable generation each time
— so a grant surface written at deploy time names the directory the previous
start used, and every file in it still exists, so nothing fails until the next
rotation.

Grants are keyed per `(service, target_file)`:

```yaml
secrets:
  dbmate__migration_user_password:
    file: /var/lib/agentic-postgres/secrets/<key>/generations/<gen>/dbmate/migration_user_password
services:
  dbmate:
    secrets:
      - source: dbmate__migration_user_password
        target: migration_user_password
```

The Compose secret *name* carries the service because two services may
legitimately receive the same basename from two directories; `target:` is the
basename alone, so each container still sees `/run/secrets/<target_file>` exactly
as `secrets_contract.container_secret_path` says. Keyed by basename alone, the
second grant would overwrite the first and one service would silently mount the
other's copy.

## Consequences

`assert_secret_sources_are_project_scoped` now has sources to scan, so the
refusal it was written for can actually fire.

A missing grant surface is refused rather than read as "this project has no
secrets". Only the contract can make that claim, and it makes it by rendering an
empty block — which is a file that exists. An absent file and an empty one now
mean different things, which is the whole reason to require the file.

The session filter applies: rendering session 2's surface on a session-2 host
does not mount a database credential that host never materialized. Compose
refuses to start a service whose `file:` source is absent, so without the filter
the addition of a Session 3 secret would have stopped every Session 2 project at
its next restart.

## Alternatives considered

**Put the grants in `compose.yaml` with an interpolated generation.** The
generation identifier is deliberately random and unordered, and it changes per
start; it would have to enter `compose.env`, which is rendered with no host and
must stay a pure function of the digested inputs.

**Extend the existing runtime override.** One file, written by the deploy, with
a value that is stale one restart later. The failure would appear at the first
rotation, attributed to rotation.

**Mount the generation directory itself and let services find their own file.**
Every service would see every other service's secret. The per-consumer directory
is what makes "service A cannot read service B's copy" a filesystem property.
