# Agentic Postgres Primitive

A reusable, isolated, one-project-per-deployment PostgreSQL appliance and
template. One deployment serves exactly one project; isolation comes from the
deployment topology rather than from application correctness.

**Status: Session 3 of 12 complete.** The repository defines a contract *and*
deploys. Two isolated projects run on one hardened host behind one shared
Traefik edge on Let's Encrypt production certificates, each with **its own
PostgreSQL 18 cluster** — forced row-level security, a locked pgvector, and a
migration plane that cannot write its own audit record. There is still no
client-facing database endpoint: the cluster publishes no host port and joins no
edge network, and connecting to one from outside its project is Session 4. See
[What is intentionally unavailable](#what-is-intentionally-unavailable).

- [Session 3 operator guide](docs/session-03-operator-guide.md) — **start here to deploy a project with its database**
- [The database](docs/database.md) · [Migrations](docs/migrations.md) · [Database security](docs/database-security.md)
- [Session 2 operator guide](docs/session-02-operator-guide.md) — the host, the edge, and the secret store
- [Host baseline](docs/host-baseline.md) · [Provider bootstrap](docs/provider-bootstrap.md) · [Project isolation](docs/project-isolation.md) · [Secret handling](docs/secret-handling.md)
- [Product contract](docs/product-contract.md) — scope, requirement IDs, non-goals, change control
- [Architecture decisions](docs/decisions/README.md)
- [Handoff — environment and workflow](docs/handoff.md) — machine specifics, git, known traps
- [Session 3 implementation plan](docs/plans/session-03-implementation-plan.md) — divergence table, decision log, build order

> `bin/session-01-check.sh` exits 0 from a clean tree, **including on the
> deployment host with both projects running**. `bin/session-02-check.sh` runs
> in three environments — `offline`, `host`, `external` — because a port scan
> run on the host traverses its own routing table and can report "closed" for a
> port the world can reach. `bin/session-03-check.sh` runs in two: there is
> nothing new to see from outside a cluster that publishes no port, and a mode
> that measured nothing would still write evidence saying it had run.

---

## Deploying

`--render-only` needs no host and no root, and it remains the whole of what runs
in a checkout:

```bash
./deploy.sh --project project.yaml --capabilities capabilities.yaml --render-only
```

Deploying is an ordered sequence, and no step makes its own preconditions:
host baseline → edge plane → provider bootstrap → materialize secrets → deploy
→ verify → promote ACME. The
[operator guide](docs/session-02-operator-guide.md) carries the commands, the
two rollback timers that stop host hardening from locking you out, and the
Let's Encrypt rate limits that cost a week if you retry in a loop.

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
  evidence_claims.py Claims resolved from the acceptance registry and JUnit.
infra/host/          Templates provision-host.sh renders into /etc.
infra/edge/          The shared Traefik + socket-proxy stack.
libexec/             Launchers systemd runs. Never a working tree.
systemd/             Installed units, including agentic-postgres-project@.
compose.yaml         Validation-only model. Never started.
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

`--render-only` needs no host and no root and starts nothing. To deploy, pass
`--host` and `--through-session 2` instead — and read the
[operator guide](docs/session-02-operator-guide.md) first, because that form
expects the host, the edge, providers and secrets to be ready already. It does
not partially deploy.

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

The wrapper's scopes decide which subcommands are permitted; the Session 1
fixture scope still refuses `up`, `run`, `start`, `create`, `restart`, `exec`,
`attach` and `cp` with exit `10`. See
[ADR 0013](docs/decisions/0013-compose-wrapper-scopes.md).

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
bin/smoke-test.sh                       # fast: active contract tests only
bin/session-01-check.sh                 # the Session 1 gate — clean tree required
bin/session-02-check.sh --mode offline  # Session 2's checkout-runnable half
```

The other two Session 2 modes need a deployment. See the
[operator guide](docs/session-02-operator-guide.md) §7.

## Exit-code convention

| Code | Meaning |
|---|---|
| `0` | Success |
| `2` | Invalid operator input or manifest |
| `3` | Missing local prerequisite |
| `4` | Missing bootstrap/runtime prerequisite |
| `4` | Missing runtime state — the project was never deployed here |
| `5` | Contract, lock, collision, or generated-output validation failure |
| `6` | A host or gate check failed |
| `7` | The provider rejected an operation, or state disagrees with it |
| `8` | A secret could not be fetched or written |
| `9` | The edge could not be brought to the requested state |
| `10` | Capability intentionally unavailable in the current session |

## What is intentionally unavailable

Session 2 deploys an edge, a health route and a secret-materialization proof.
It does not run a database. Every command that would use the following exits
`10` rather than reporting success:

- PostgreSQL, PgBouncer, PostgREST, FastAPI, FastMCP — no service starts.
  Traefik and the Docker socket proxy **do** run; they are the edge plane.
- Database endpoints — rendered as `status: "unavailable"` with `host`, `port`,
  `url`, and `password_secret_ref` all `null`. Not placeholders. Session 4.
- Migrations (`bin/migrate.sh`) — Session 3
- Connections (`bin/connect.sh`) — Session 4
- Restore rehearsal (`bin/restore-test.sh`) — Session 10
- Object storage — Session 7. Backups — Session 10. Both are `null` in every
  Session 2 project, and two projects that both lack one are not colliding
  ([ADR 0016](docs/decisions/0016-absence-is-not-a-collision.md)).
- Agent capabilities — `capabilities.yaml` is empty by default, and an entry
  marked `enabled: true` fails with exit `5` because no live backing contract
  exists to validate it against

## Session 3 preview

Session 3 adds migrations. `--render-only` is preserved, and Session 3 activates
its own requirements by removing their `future` markers and implementing the
bodies — never by weakening an active test.
