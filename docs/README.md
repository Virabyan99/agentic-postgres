# Documentation

Every page in `docs/`, and what each one answers. Kept complete by
`tests/contract/test_documentation_index.py`, which fails when a page is added
here and not listed, or listed and not present — a page nobody indexed is a page
nobody finds, and an index that has quietly stopped being complete is worse than
none, because it tells a reader the set is whole.

## Start here

| Page | Answers |
|---|---|
| [New team member](new-team-member.md) | The path from a clean machine to a rendered project, step by step |
| [Product contract](product-contract.md) | What this is, what it is not, every requirement id and the session that owns it |
| [Handoff](handoff.md) | The machine, git, the environment, and the traps that have cost a run |
| [Architecture decisions](decisions/README.md) | Every ADR, indexed by number and session |

## Operator guides

One per session, each covering the host sequence that session added. **A guide is
derived from its predecessor by diff, never retyped** — D505, D507 and D602 were
all flags or steps lost to retyping the previous session's page.

| Guide | Adds |
|---|---|
| [Session 2](session-02-operator-guide.md) | The host, the edge plane, the secret store |
| [Session 3](session-03-operator-guide.md) | A project with its database and migrations |
| [Session 4](session-04-operator-guide.md) | Both database transports and the access broker |
| [Session 5](session-05-operator-guide.md) | The REST surface and the reference page |
| [Session 6](session-06-operator-guide.md) | Identity, tokens, signing keys, admin |
| [Session 7](session-07-operator-guide.md) | Object storage and its credentials |
| [Session 8](session-08-operator-guide.md) | The agent plane's read half |
| [Session 9](session-09-operator-guide.md) | Agent writes and the audit record |
| [Session 10](session-10-operator-guide.md) | Backups, WAL archiving, the restore drill |
| [Session 11](session-11-operator-guide.md) | The preflight, the deployed doctor, the request id, the rotation windows |

## Running a deployment

| Page | Answers |
|---|---|
| [API operations](api-operations.md) | The connection budget, statement timeouts, restarting, rotating a credential |
| [Pool operations](pool-operations.md) | PgBouncer: its pool, its users, what a restart costs |
| [Backup operations](backup-operations.md) | The repository, the schedule, and how a restore is rehearsed |
| [Database connections](database-connections.md) | Both transports, the tunnel, and the profiles |
| [Client compatibility](client-compatibility.md) | Which clients work against which transport, measured |
| [Migrations](migrations.md) | How a migration is written, rendered, released and applied |
| [Secret handling](secret-handling.md) | Generations, per-consumer materialization, what may never be logged |
| [Provider bootstrap](provider-bootstrap.md) | What is created at a provider, by identifier rather than by name |
| [Host baseline](host-baseline.md) | What `provision-host.sh` does to a machine |

## The surface

| Page | Answers |
|---|---|
| [API surface](api-surface.md) | Every published route and what it serves |
| [MCP tool catalog](mcp-tool-catalog.md) | What an agent can do against this deployment, and nothing else |
| [The database](database.md) | Four schemas, the roles, and what each may reach |
| [Database security](database-security.md) | Forced RLS, the request identity, and the privilege model |
| [Project isolation](project-isolation.md) | What two projects on one host do not share |
| [Capability plan](capability-plan.md) | How a capability manifest becomes a compiled contract |

## Evidence and assurance

| Page | Answers |
|---|---|
| [Acceptance matrix](acceptance-matrix.md) | Every requirement, its node ids, and whether they collect **(generated)** |
| [Security acceptance](security-acceptance.md) | The security requirements and how each is proved |
| [Threat model](threat-model.md) | What is defended against, and what is not |
| [Source specification](source-specification.md) | The original brief. **Digest-pinned** — quoted, never edited |

## Plans

`plans/session-NN-implementation-plan.md`, one per session. **§1 is the
divergence table and is the point of the document**: every conflict between what
a session was asked for and what was measurably true, with the decision and its
reason. §5 is the run-by-run build order, each run carrying what it measured.

Nothing indexes those ~650 measured facts by subject, so finding one is a `grep`.

---

**Generated pages are marked.** `acceptance-matrix.md` and the table in
`mcp-tool-catalog.md` are rendered from the registry and the compiled capability
contract; editing them by hand is overwritten on the next render and caught by
`--check` in the meantime.
