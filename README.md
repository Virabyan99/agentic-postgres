# Agentic Postgres Primitive

A reusable, isolated, one-project-per-deployment PostgreSQL appliance and
template. One deployment serves exactly one project; isolation comes from the
deployment topology rather than from application correctness.

**Status: Session 1 of 12, in progress.** This repository currently defines a
contract. It deploys nothing, starts no container, and connects to no
database. See [What is intentionally unavailable](#what-is-intentionally-unavailable).

- [Product contract](docs/product-contract.md) — scope, requirement IDs, non-goals, change control
- [Architecture decisions](docs/decisions/README.md)
- [Session 1 implementation plan](docs/plans/session-01-implementation-plan.md) — environment constraints, decision log, build order

> **Build progress.** Run 1 of 5 is complete. Sections below marked
> _(Run N)_ describe commands that do not exist yet. Nothing in this file
> claims a capability the code does not have.

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
                     bounds and the capability scope vocabulary.        (Run 2)
src/agentic_postgres/
  naming.py          Deterministic identity derivation. Load-bearing:
                     nothing else may re-derive a name.                 (Run 2)
  config.py          Strict YAML loading, schema + semantic validation.  (Run 2)
  rendering.py       Transactional staging and publication.              (Run 3)
  evidence.py        Session evidence from test artifacts.               (Run 5)
tests/contract/      Active Session 1 contract tests.
tests/{integration,recovery,security}/
                     Future-session placeholders. Collectible, skipped by
                     marker, and failing if the marker is removed.       (Run 5)
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

## Rendering a project _(Run 3)_

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

## Running the checks

```bash
bin/smoke-test.sh          # fast: active contract tests only
bin/session-01-check.sh    # the gate CI runs — clean tree required   (Run 5)
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
