# Agentic Postgres Primitive

A reusable, isolated, one-project-per-deployment PostgreSQL appliance and
template. One deployment serves exactly one project; isolation comes from the
deployment topology rather than from application correctness.

**Status: Session 18 implemented**, the Stage 2 release candidate, at
`template_version` **1.0.1**. **Adopt `1.0.1`, not `1.0.0`**: the `1.0.0` tag
predates its own documented-path repairs, so the one ref a new adopter has
reason to trust was the one that still had them (D1033). `1.0.1` is Session
19's repair release — nineteen defects found by somebody building an
application on 1.0.0, on a host that started empty; see
[the session plan](docs/plans/session-19-implementation-plan.md) and
[scope closure](docs/scope-closure.md) §8. No manifest field, migration,
contract entry, capability or secret changed, and nothing in it is a change an
operator must act on before upgrading. Session 18's code is in this release — independent
recovery: every backup repository mirrored to a second provider by a host unit
the archiver never knows about (ADR 0188), a disaster kit that names every
secret and holds none and a bootstrap that adopts a provider project by its
recorded id (ADR 0189), a restore onto a replacement host from the mirror alone
(ADR 0192), and eight bounded failure rehearsals that read the readers the
deployment already has (ADR 0190, ADR 0193). Its evidence is **93 of 101
claims**, measured against the live deployment on 2026-09-06: both projects
mirrored, a restore from the mirror alone verified on a replacement host in
247 s with the original identity, the kit from production verified, and the
eight rehearsals read and reversed; `replacement_host_restore` stays `not_run`
by decision and the seven older ones for want of the events they need
([recovery operations](docs/recovery-operations.md), [the Stage 3 decision
report](docs/stage-3-decision-report.md)). `1.0.0` promises what the product
contract's §7 says a major promises, and nothing more. Two isolated
projects run on one hardened host behind one shared Traefik edge on Let's Encrypt
production certificates. Each has its own PostgreSQL 18 cluster under forced
row-level security, two database transports, a REST and an application API behind
its own signing key, object storage, an encrypted off-site backup repository with
continuous WAL archiving, and an MCP agent plane with a durable audit record.

A restore has been rehearsed against a real deployment, not designed on paper.

- **[Documentation index](docs/README.md)** — every page, and what each answers
- **[New here?](docs/new-team-member.md)** — the path from a clean machine
- [Product contract](docs/product-contract.md) — scope, requirement IDs, non-goals
- [Architecture decisions](docs/decisions/README.md) — every ADR, indexed
- [Handoff](docs/handoff.md) — machine specifics, git, known traps

---

## What runs

| Plane | What it is | Reached by |
|---|---|---|
| Edge | Traefik and a Docker socket proxy, shared by every project | the public internet |
| Database | PostgreSQL 18, pgvector, forced RLS, one cluster per project | `bin/connect.sh` over an SSH tunnel |
| Pool | PgBouncer, its own credential and user list | `bin/connect.sh` |
| REST | PostgREST over `api`, generated from database privileges | `/api/rest` |
| Application | FastAPI: identity, tokens, admin | `/api/app` |
| Storage | the same image in its second mode, R2-backed | `/api/app/storage` |
| Agents | FastMCP, six tools behind seven capabilities | `/mcp` |
| Reference | a vendored Scalar page, served first-party | `/docs/rest`, `/docs/app` |
| Backups | pgBackRest to an encrypted R2 repository, WAL archived continuously | `bin/backup.sh` |

Every name above — role, network, volume, router, route — is derived once by
`src/agentic_postgres/naming.py` and published in `outputs.json`. Nothing
re-derives a name anywhere else.

## Local bootstrap

This repository requires POSIX filesystem semantics: `0600` file modes are a
tested contract, and `flock` guards render publication. On Windows, develop
inside WSL2 with the repository on the **Linux** filesystem — not under `/mnt/c`
and not inside a OneDrive-synced folder.

```bash
# Tools. `git` because the step above needed it, and `docker` because
# --render-only validates the Compose model with it — a checkout that renders
# nothing is not a checkout that can be checked.
sudo apt-get update && sudo apt-get install -y git shellcheck jq
# Docker Engine and the Compose v2 plugin: follow docs.docker.com for your
# distribution. `docker compose version` and `docker buildx version` must both
# answer before bin/doctor.sh will pass.

# Pinned interpreter and locking tool
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

`bin/doctor.sh` exits `3` and names what is missing. It prints tool versions and
repository paths only — never the environment, never a secret. `--verbose` adds
where each tool resolved from.

To change a dependency, edit `requirements-dev.in`, then:

```bash
bin/lock-dev-deps.sh --update    # resolves and rewrites requirements-dev.txt
bin/lock-dev-deps.sh --check     # verifies the lock is current; modifies nothing
```

## Rendering a project

`--render-only` needs no host and no root, starts nothing, and contacts no
provider. **It does need Docker**, because it validates the staged Compose model
before publishing it — `docker` absent is exit `5`, not a partial render. It
remains the whole of what runs in a checkout:

```bash
cp project.example.yaml project.yaml
cp capabilities.example.yaml capabilities.yaml
# edit project.yaml — it contains no secret and must never contain one

./deploy.sh \
  --project project.yaml \
  --capabilities capabilities.yaml \
  --render-only
```

Inspect the result:

```bash
jq . .generated/<project-key>/outputs.json
cat  .generated/<project-key>/rendered-summary.txt
```

Output is byte-identical across renders with identical inputs.
`outputs.json`, `compose.env` and `rendered-summary.txt` are mode `0600`;
`pgbackrest.conf` is `0444`, because it carries no credential by construction and
the database container reads it as uid 999.

## Deploying

**Deploying is an ordered sequence, and no step makes its own preconditions.** A
deploy that quietly performed them would be one whose failure halfway leaves
nobody able to say which half ran.

**Two steps come before this list**, and the operator guide's step 0 has them:
get the release onto the host (`git bundle` + `scp` — never a GitHub credential
there), and **create the operator user named by `ssh.operator_user`**.
`provision-host.sh` does not create it and its second pass installs
`PermitRootLogin no`, so on a fresh host that step removes the only way in
(D659).

```bash
sudo bin/provision-host.sh      --host host.yaml                  # once per host
sudo bin/edge.sh                --host host.yaml up               # once per host
sudo bin/bootstrap-providers.sh --host host.yaml --project project.yaml --apply
sudo bin/materialize-secrets.sh --project project.yaml --requirements secrets.required.yaml --session 18
sudo ./deploy.sh --host host.yaml --project project.yaml \
     --capabilities capabilities.yaml --through-session 18
```

`deploy.sh --through-session` **refuses before it changes anything** when a
prerequisite is absent, and lists every absent item at once with the command that
supplies each. It reports what it could not check separately from what it found
missing, because "the edge is not running" and "the Docker daemon could not be
reached, so nobody looked" are different sentences (ADR 0157).

The [operator guides](docs/README.md#operator-guides) carry the host sequence per
session, the two rollback timers that stop host hardening from locking you out,
and the Let's Encrypt rate limits.

**Failed ACME validations cap at 5 per hour per hostname. Never retry in a loop.**

## Operating a deployment

```bash
sudo bin/doctor.sh --project <key>            # containers, TLS, database, pool,
                                              # migrations, backups, WAL, mirror, disk, lock
sudo bin/doctor.sh --project <key> --verbose  # the numbers behind each verdict
sudo bin/doctor.sh --project <key> --json     # the same verdicts as a document
sudo bin/fleet.sh [--json] [--window HOURS]   # every project on this host: release,
                                              # live health, backup timers, denials
sudo bin/project-retire.sh --host host.yaml --project <key> --confirm <key> \
     --record <path> --plan                   # what retiring it would remove; nothing changes

sudo bin/dr-kit.sh export --host host.yaml --capabilities capabilities.yaml \
     --project project.yaml --output <dir>     # the disaster kit: identifiers, never a value
bin/dr-kit.sh verify <dir>                    # is the kit whole? (docs/node-loss-runbook.md)
sudo bin/rehearse.sh <scenario> --outputs <outputs.json> [--plan]
                                              # one bounded failure: induce, read, reverse
sudo bin/rehearse.sh reverse                  # replay an interrupted rehearsal's reversal
                                              # (docs/recovery-operations.md)

sudo bin/migrate.sh --project project.yaml status    # applied and pending
sudo bin/backup.sh  --outputs <outputs.json> info --json
sudo bin/backup.sh  --outputs <outputs.json> schedule status  # both timers enabled? 0 if so
sudo bin/restore-test.sh --target-time <iso8601> --project-dir <dir>

# A verified SSH forward, then a session over it. `tunnel` needs the host;
# everything after it needs only the project key, because the tunnel recorded it.
bin/connect.sh tunnel    --project <key> --ssh <user>@<host>
bin/connect.sh print-env --project <key>            # connection variables, no password
bin/connect.sh psql      --project <key>
bin/connect.sh stop      --project <key>
```

**Four ways of naming a project, and the difference is real.** `doctor.sh` and
`connect.sh` take `--project <key>`, the derived `apg-<slug>-<env>` identity;
`migrate.sh` takes `--project <manifest file>`; `backup.sh` takes `--outputs`,
the path to that project's deployed `outputs.json`; `restore-test.sh` takes
`--project-dir`, the generated project directory. Copying the wrong one produces
a refusal rather than a wrong action — but it is the first thing a reader trips
over, and it is worth knowing before you do.

`doctor.sh --project` reads the deployed document for identities only. **Every
verdict comes from a live read**: that document records what was observed at
deploy time, so a project whose archiver died yesterday still publishes the status
it had at its last deploy (ADR 0158).

Read-only diagnosis without a terminal is `apg-diag`, over its own SSH identity:

```bash
ssh -i ~/.ssh/apg_agent_ed25519 apg-agent@<host> sudo apg-diag containers
```

## Adding your own tables

**This product ships one example domain, and adopting it means adding to that
domain in this repository.** There is no tenant extension point:
`migrations.load_manifest()` reads one hardcoded path, and a project manifest
carries no migration keys. `docs/source-specification.md` §5.4 says the same
thing from the other side — *"pgvector data and additional project tables are
optional migrations"*. That is a defensible design, because a fork is a
reviewable diff and reviewability is the property this repository argues for
throughout. It is not an obvious one, and until Session 19 an adopter
discovered it by reading `migrations/loader.py`.

Adding one table, one view and a few RPCs touches six places. Five are ordinary
work; the sixth changes the shape of a first bring-up.

| # | What | Offline? |
|---|---|---|
| 1 | `migrations/templates/00xx-*.sql` — your table, its FORCE-RLS policies, its `api` view, its `SECURITY DEFINER` RPCs | yes |
| 2 | `migrations/manifest.json` — the entry, then `bin/migrate.sh --project FILE freeze-lock` | yes |
| 3 | `contracts/postgrest-api-surface.yaml` — the reviewed surface. Amending it is sanctioned and the file says so: *"a project that needs an object this does not name needs a reviewed change here, not a second contract."* | yes |
| 4 | `tests/contract/test_api_migrations.py` — two hand-written sets name the published surface by hand, deliberately, so an empty scrape cannot agree with an empty contract | yes |
| 5 | `tests/contract/test_api_surface_contract.py` — the same, for the reviewed contract's own assertions | yes |
| 6 | `contracts/postgrest-openapi.canonical.json` — captured from a **running deployment** and refuses a hand edit | **no** |

Row 6 is the one to know about in advance. `bin/api-contract.sh --update` reads
`routes.rest.url` from a deployed document; the surface is served only once the
migrations are applied; and the migrations are applied by the deploy. So the
snapshot check **cannot be satisfied before your first deploy** — it is
unsatisfiable rather than unsatisfied, and the check says so since Session 19.
Expect it red, deploy, then re-capture:

```bash
sudo bin/api-contract.sh --update --project-outputs <outputs.json> > candidate.json
# review it, then commit it as contracts/postgrest-openapi.canonical.json
```

Two rules that are not negotiable and will refuse you rather than warn you:

- **Fix forward.** A released migration is never amended — its bytes are the
  unit `verify-lock` checks, so editing even a comment changes a digest the
  lock records. Every `-- migrate:down` block raises `AP900` on purpose.
- **Your manifest is ignored, not untracked.** `project.yaml` and
  `project.<name>.yaml` are covered by `.gitignore`; the gate fails on any
  untracked file and a dirty release makes a deploy refuse outright (D971).

**What your tables do not get: an agent.** See *What is intentionally
unavailable*.

## Checks

```bash
bin/smoke-test.sh                        # the active contract tests
bin/session-01-check.sh                  # THE gate — needs a clean tree
bin/session-10-check.sh --mode offline   # the backup plane's checkout-runnable half
```

**`bin/smoke-test.sh` is not quick.** Measured on a developer machine: **4,152
tests in about five minutes**, and it starts real containers, so Docker must be
running. It is faster than the gate — which adds a clean-tree check, static
analysis, both fixture renders and evidence generation — and it is not a
seconds-long confidence check. Run a single module while you work:

```bash
python -m pytest tests/contract/test_preflight.py -q
```

Each session has its own gate, `bin/session-01-check.sh` through
`bin/session-10-check.sh`. Most run in more than one mode: `offline` in a
checkout, `host` on the deployment host, and `external` from a different network
— because a port scan run on the host traverses its own routing table and can
report "closed" for a port the world can reach. A session document cannot be
written from one half alone.

**The gate is a release control, not a save button.** It re-runs the whole suite.

## Compose

Always through the wrapper. Calling `docker compose` directly lets inherited
shell variables win over `--env-file`, which would silently point a command at
the wrong project or bypass a locked digest.

```bash
bin/compose.sh .generated/<project-key> --profile contract config
bin/compose.sh .generated/<project-key> ps --quiet
```

See [ADR 0013](docs/decisions/0013-compose-wrapper-scopes.md).

## Version locks

```bash
bin/lock-versions.sh --update   # resolves digests; needs network + Buildx
bin/lock-versions.sh --check    # offline; no registry, no credentials
```

Every image is pinned to an immutable digest for one declared platform. If a
digest cannot be resolved, that blocks the session — a floating tag is not a
substitute. See [ADR 0004](docs/decisions/0004-version-lock-format.md).

## Exit-code convention

| Code | Meaning |
|---|---|
| `0` | Success |
| `2` | Invalid operator input or manifest |
| `3` | Missing local prerequisite |
| `4` | Missing bootstrap/runtime prerequisite, or a project never deployed here |
| `5` | Contract, lock, collision, or generated-output validation failure |
| `6` | A host check, gate check, or diagnostic check failed |
| `7` | The provider rejected an operation, or state disagrees with it |
| `8` | A secret could not be fetched or written |
| `9` | The edge could not be brought to the requested state |
| `10` | Capability intentionally unavailable in the current session |

## What is intentionally unavailable

**Removing a project is not built, and it is the one Session 12 claim still
open.** The runtime comes down with `bin/project-runtime.sh` (the volume is
kept), and provider resources are released with `bin/bootstrap-providers.sh
--destroy --confirm <key>` — which revokes the runtime identity and **leaves
every secret in place**, the backup cipher pass included. The scoped removal
that provably leaves a co-tenant project untouched is `DEP-REMOVE-001`; its
proof is written and gated on a project actually removed, which has not
happened. The two-project runtime isolation matrix, `DEP-ISO-001`, is claimed
and has passed on every host gate since Session 12.

Not deferred — **outside the product**:

- A shared multi-tenant control plane or any cross-project shared catalog
- A hosted web console or SaaS offering
- Autoscaling, scale-to-zero, compute/storage separation
- Database branching or copy-on-write forks
- Automatic failover or multi-region replication
- **Arbitrary SQL execution by an agent, under any authentication**

**The agent plane serves this product's example domain, and not yours.** The
six tools are the whole agent surface and they can only ever address `notes`
and `tasks`. Two things close it, independently, and both are working as
designed:

- The roster is enumerated rather than discovered (ADR 0127). `mcp_lock`
  refuses any lock that does not serve exactly those six names, so a seventh
  tool is refused at startup rather than ignored.
- The scope vocabulary is a closed enum — `notes:read`, `notes:write`,
  `tasks:read`, `tasks:write`, `meta:read`. There is no way to *declare* a
  scope for an application's own data, and the schema says the closure is
  deliberate: the data class is closed by ADR 0003 and grows only when that is
  superseded. A capability that borrows `notes:read` to read something that is
  not a note is representable, and a second gate catches it: the manifest no
  longer compiles to the approved contract, and `bin/mcp-contract.sh` says so.

So an application built on this appliance gets a first-class REST surface, a
first-class storage surface, and **no agent surface at all for its own tables**.
Extending the vocabulary supersedes ADR 0003 and is not a configuration change.

Related and open: `tasks` itself currently has no reviewed way to come into
existence, so two of the six tools address a table nothing can populate
(ADR 0196).

## Repository map

```text
bin/                 Operator commands. Every one resolves the repo root from
                     BASH_SOURCE, so they work from any directory.
deploy.sh            The one entry point that renders and deploys.
docs/                Documentation. Start at docs/README.md.
docs/decisions/      ADRs. Required for anything the contract freezes.
docs/plans/          Implementation plans, including the divergence tables.
schemas/             JSON Schema (Draft 2020-12). Sole authority for numeric
                     bounds and the capability scope vocabulary.
src/agentic_postgres/
  naming.py          Deterministic identity derivation. Load-bearing:
                     nothing else may re-derive a name.
  config.py          Strict YAML loading, schema + semantic validation.
  rendering.py       Transactional staging and publication.
  preflight.py       What a deploy checks before it changes anything.
  diagnosis.py       What a deployed project's health is.
  evidence.py        Session evidence from test artifacts.
migrations/          Released migrations. Fix-forward only; every down block
                     raises AP900.
services/            First-party images: auth/storage, docs, edge-probe,
                     postgres, and the client examples.
infra/edge/          The shared Traefik and socket-proxy stack.
infra/host/          Templates provision-host.sh renders into /etc.
libexec/             Launchers systemd runs. Never a working tree.
systemd/             Installed units, including agentic-postgres-project@.
compose.yaml         Validation-only model. Never started directly.
versions.in.yaml     Human-selected candidates.
versions.env         Generated digest lock. Never hand-edited.
tests/contract/      Runs in a checkout, needs nothing.
tests/deployment/    Needs a provisioned host.
tests/external/      Needs a different network.
.generated/          Rendered output. Git-ignored. Never hand-edited.
evidence/            Generated session evidence. Git-ignored.
```

## Non-negotiables

- **No secret value** may enter source control, Compose interpolation, process
  arguments, image layers, or logs.
- **A released migration is never amended.** Fix forward.
- `--render-only` keeps working with no host and no root.
- `host.yaml`, `capabilities.yaml` and the project manifests are gitignored
  operator inputs that exist only on the host. **Never commit them.**
- Transport to the deployment host is `git bundle` and `scp`. **No GitHub
  credential goes on the host.**
- `sudo` on the host needs a TTY, so **anything privileged that mutates is run by
  a human at a terminal**, never piped over SSH. Read-only diagnosis is not.
