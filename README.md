# Agentic Postgres Primitive

A reusable, isolated, one-project-per-deployment PostgreSQL appliance and
template. One deployment serves exactly one project; isolation comes from the
deployment topology rather than from application correctness.

**Status: Session 1 of 12 complete.** This repository currently defines a
contract. It deploys nothing, starts no container, and connects to no
database. See [What is intentionally unavailable](#what-is-intentionally-unavailable).

- [Product contract](docs/product-contract.md) — scope, requirement IDs, non-goals, change control
- [Architecture decisions](docs/decisions/README.md)
- [Handoff — environment and workflow](docs/handoff.md) — machine specifics, git, known traps
- [Session 1 implementation plan](docs/plans/session-01-implementation-plan.md) — environment constraints, decision log, build order

> `bin/session-01-check.sh` exits 0 from a clean tree: 516 active contract
> tests, 566 P0 tests collected, 50 activatable placeholders owned by later
> sessions, 0 identity collisions, 0 floating image references.

---

## Non-goals

Not deferred — outside the product:

- A shared multi-tenant control plane or any cross-project shared catalog
- A hosted web console or SaaS offering
- Autoscaling, scale-to-zero, compute/storage separation
- Database branching or copy-on-write forks
- Automatic failover or multi-region replication
- **Arbitrary SQL execution by an agent, under any authentication**

## Repository map

```text
bin/                 Operator commands. Every one resolves the repo root from
                     BASH_SOURCE, so they work from any directory.
docs/decisions/      ADRs. Required for anything frozen in the runbook §4.
docs/plans/          Implementation plans, including the decision log.
schemas/             JSON Schema (Draft 2020-12). Sole authority for numeric
                     bounds and the capability scope vocabulary.
src/agentic_postgres/
  naming.py          Deterministic identity derivation. Load-bearing:
                     nothing else may re-derive a name.
  config.py          Strict YAML loading, schema + semantic validation.
  rendering.py       Transactional staging and publication.
  evidence.py        Session evidence from test artifacts.
compose.yaml         Validation-only model. Never started in Session 1.
versions.in.yaml     Human-selected candidates.
versions.env         Generated digest lock. Never hand-edited.
tests/contract/      Active Session 1 contract tests.
tests/{integration,recovery,security}/
                     Future-session placeholders. Collectible, skipped by
                     marker, and failing if the marker is removed.
.generated/          Rendered output. Git-ignored. Never hand-edited.
evidence/            Generated session evidence. Git-ignored.
```

## Local bootstrap

This repository requires POSIX filesystem semantics: `0600` file modes are a
tested contract, and `flock` guards render publication. On Windows, develop
inside WSL2 with the repository on the **Linux** filesystem — not under
`/mnt/c` and not inside a OneDrive-synced folder. The implementation plan §1
explains what breaks otherwise, with measurements.

```bash
# Tools
sudo apt-get update && sudo apt-get install -y shellcheck jq

# Pinned interpreter and locking tool (uv version is pinned in bin/lock-dev-deps.sh)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12

# Environment. --seed installs pip, which the hash-locked install below needs.
uv venv --seed --python 3.12 .venv
source .venv/bin/activate

# Dependencies, exact and hash-locked
python -m pip install --require-hashes -r requirements-dev.txt

# Confirm the workstation is ready
bin/doctor.sh
```

`bin/doctor.sh` exits `3` and names what is missing. It prints tool versions
and repository paths only — never the environment, never a secret.

To change a dependency, edit `requirements-dev.in`, then:

```bash
bin/lock-dev-deps.sh --update    # resolves and rewrites requirements-dev.txt
bin/lock-dev-deps.sh --check     # verifies the lock is current; modifies nothing
```

## Rendering a project

```bash
cp project.example.yaml project.yaml
cp capabilities.example.yaml capabilities.yaml
# edit project.yaml — it contains no secret and must never contain one

./deploy.sh \
  --project project.yaml \
  --capabilities capabilities.yaml \
  --render-only
```

`--render-only` is mandatory in Session 1. Without it, `deploy.sh` exits `10`
and says deployment begins in a later session. It does not partially deploy.

Inspect the result:

```bash
jq . .generated/<project-key>/outputs.json
cat  .generated/<project-key>/rendered-summary.txt
```

Output is byte-identical across renders with identical inputs. All three
generated files are mode `0600`.

## Compose

Always through the wrapper. Calling `docker compose` directly lets inherited
shell variables win over `--env-file`, which would silently point a command at
the wrong project or bypass a locked digest.

```bash
bin/compose.sh .generated/<project-key> --profile contract config
bin/compose.sh .generated/<project-key> ps --quiet
```

Session 1 refuses `up`, `run`, `start`, `create`, `restart`, `exec`, `attach`,
and `cp` with exit `10`.

## Version locks

```bash
bin/lock-versions.sh --update   # resolves digests; needs network + Buildx
bin/lock-versions.sh --check    # offline; no registry, no credentials
```

Every image is pinned to an immutable digest for one declared platform. If a
digest cannot be resolved for it, that blocks the session — a floating tag is
not a substitute. See [ADR 0004](docs/decisions/0004-version-lock-format.md).

## Running the checks

```bash
bin/smoke-test.sh          # fast: active contract tests only
bin/session-01-check.sh    # the gate CI runs — clean tree required
```

## Exit-code convention

| Code | Meaning |
|---|---|
| `0` | Success |
| `2` | Invalid operator input or manifest |
| `3` | Missing local prerequisite |
| `4` | Missing bootstrap/runtime prerequisite |
| `5` | Contract, lock, collision, or generated-output validation failure |
| `10` | Capability intentionally unavailable in the current session |

## What is intentionally unavailable

Session 1 renders configuration. It does not deploy. Specifically, none of the
following exists yet, and every command that would use them exits `10` rather
than reporting success:

- PostgreSQL, PgBouncer, PostgREST, FastAPI, FastMCP, Traefik — no service starts
- Database endpoints — rendered as `status: "unavailable"` with `host`, `port`,
  `url`, and `password_secret_ref` all `null`. Not placeholders. Session 4.
- Migrations (`bin/migrate.sh`) — Session 3
- Provider bootstrap (`bin/bootstrap-providers.sh`) — Session 2
- Connections (`bin/connect.sh`) — Session 4
- Restore rehearsal (`bin/restore-test.sh`) — Session 10
- Agent capabilities — `capabilities.yaml` is empty by default, and an entry
  marked `enabled: true` fails with exit `5` because no live backing contract
  exists to validate it against

## Session 2 preview

Session 2 adds provider bootstrap and validation, host hardening, Traefik as a
real edge service, and secret materialization through Docker secrets or
restricted runtime files. It preserves `--render-only`, and activates its own
tests by removing their `future` markers and implementing the bodies.
