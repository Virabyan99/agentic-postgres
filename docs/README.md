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
| [Scope closure](scope-closure.md) | What ships and what does not: the P0/P1/P2 position, every external dependency, and the questions left open |
| [Handoff](handoff.md) | The machine, git, the environment, and the traps that have cost a run |
| [Architecture decisions](decisions/README.md) | Every ADR, indexed by number and session |

## Operator guides

**Two pages describe operating the release in this checkout, and they are the
only ones a reader is sent to** (ADR 0208). Each is derived by diff from its
predecessors and the trips that executed it, never retyped — D505, D507 and
D602 were all flags or steps lost to retyping a previous session's page — and
each names where every step was measured.

| Page | Answers |
|---|---|
| [Operating a deployment](operator-guide.md) | The current release: where things live on the host, the two accounts, a host from empty and its first project, every day and every week, a project's own tables and the agent plane on a deployment, Studio and the client against it, credentials, the gates, retiring a project, what goes wrong, and what has never been performed |
| [Upgrading a deployment](upgrade-guide.md) | An operator on any earlier release reaching this one: the release table, the checkout half, the host sequence, what each `upgrade plan` verdict means, skipped releases, a `major`, and what to do when a step refuses or fails halfway |
| [What 1.6.1 did about an adopter's upgrade findings](upgrade-findings-response.md) | Every one of the thirty-four findings an outside agent wrote while upgrading a real deployment from 1.0.0 to 1.6.0, with what was fixed, what was only documented, and **what is still open** — including the two product refusals that keep a fork made before `projects/<slug>/` existed from reaching it |

**The per-session guides below are records, not instructions.** Each describes
the host sequence *as of* the session named, is cited by number in the
divergence tables, and is superseded for anything current by the two pages
above. Sessions 12–25 have no guide of their own by decision: their host
sequences are in the two pages above and in their plans' §5 Run 7 *Done*
paragraphs.

| Guide | Added, then |
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

## Developer loop

Before a deployment exists, and on a machine that is not one.

| Page | Answers |
|---|---|
| [The developer loop](dev-environment.md) | `apg dev`: a disposable local cluster built from the render and the release, the six verbs, the seed door, what it costs, and what to do when a migration fails as the migration user |
| [Generated clients](generated-clients.md) | `apg generate`: a typed TypeScript client over your surface, what `init()` checks and its four answers, the two result unions, how the version is derived, and what to do when a client and a deployment disagree |
| [Studio](studio.md) | `apg studio`: a loopback page over your own deployment, holding your token and never handing it to the browser — the four launch answers and why an administrator always sees `stale_contract`, what each of the six views shows and what it cannot, the typed revocation, and what Studio never does |

## Running a deployment

| Page | Answers |
|---|---|
| [API operations](api-operations.md) | The connection budget, statement timeouts, restarting, rotating a credential |
| [Pool operations](pool-operations.md) | PgBouncer: its pool, its users, what a restart costs |
| [Backup operations](backup-operations.md) | The repository, the schedule, and how a restore is rehearsed |
| [Capacity envelope](capacity-envelope.md) | What the deployment does at its limits, which numbers transfer to another machine, and what has not been measured |
| [Database connections](database-connections.md) | Both transports, the tunnel, and the profiles |
| [Client compatibility](client-compatibility.md) | Which clients work against which transport, measured |
| [Migrations](migrations.md) | How a migration is written, rendered, released and applied |
| [Secret handling](secret-handling.md) | Generations, per-consumer materialization, what may never be logged |
| [Provider bootstrap](provider-bootstrap.md) | What is created at a provider, by identifier rather than by name -- and adopted by id on a replacement host |
| [Node-loss runbook](node-loss-runbook.md) | The host is gone: the kit, adoption, the restore from the mirror, the deploy, the cutover last |
| [Recovery operations](recovery-operations.md) | The ordinary days before it: the mirror, the kit, the restore's promises, the eight rehearsals and what each reads |
| [Host baseline](host-baseline.md) | What `provision-host.sh` does to a machine |

## The surface

| Page | Answers |
|---|---|
| [API surface](api-surface.md) | Every published route and what it serves |
| [MCP tool catalog](mcp-tool-catalog.md) | What an agent can do against this deployment, and nothing else |
| [The database](database.md) | Four schemas, the roles, and what each may reach |
| [Database security](database-security.md) | Forced RLS, the request identity, and the privilege model |
| [Project isolation](project-isolation.md) | What two projects on one host do not share |
| [Fleet operations](fleet-operations.md) | Several projects on one host over time: the inventory, the lifecycle, retiring one, and the backup schedule |
| [Capability plan](capability-plan.md) | How a capability manifest becomes a compiled contract |

## Evidence and assurance

| Page | Answers |
|---|---|
| [Acceptance matrix](acceptance-matrix.md) | Every requirement, its node ids, and whether they collect **(generated)** |
| [Evaluation report](evaluation-report.md) | Every case the evaluation harness asks of the agent surface, derived and written counted apart **(generated)** |
| [The second walk](second-walk.md) | How `DX-001` is answered: who may walk the documented path, the task statement a walker is handed verbatim, the record they write and the five readings the product takes of it |
| [Security acceptance](security-acceptance.md) | The security requirements and how each is proved |
| [Threat model](threat-model.md) | What is defended against, and what is not |
| [Source specification](source-specification.md) | The original brief. **Digest-pinned** — quoted, never edited |
| [Stage 3 decision report](stage-3-decision-report.md) | What 1.0.0 measured, what stayed not_run and why, which Stage 3 premises hold, and the template-or-control-plane recommendation |
| [Stage 4 decision report](stage-4-decision-report.md) | What 1.6.0 is, what Stage 3's trip measured, what stayed not_run and why, which of Stage 3's three blockers were removed and what the third costs, and what the DX layer's evidence says about the hosted question |

## Plans

`plans/session-NN-implementation-plan.md`, one per session. **§1 is the
divergence table and is the point of the document**: every conflict between what
a session was asked for and what was measurably true, with the decision and its
reason. §5 is the run-by-run build order, each run carrying what it measured.

Nothing indexes those measured facts (D1–D1387 at Session 26) by subject, so
finding one is a `grep`.

[`plans/stage-2-plan.md`](plans/stage-2-plan.md) sits **above** the six Stage 2
session plans and owns what all of them would otherwise repeat: where Stage 2
starts, the four decisions a new body of work must settle, the open items carried
in from twelve closed sessions, and the thinner shape a Stage 2 session plan
takes. **Its §1 is the audit of the Stage 2 specification against this
repository** — D704–D718, and the reason Stage 2 is six sessions and not twelve.

[`plans/session-13-implementation-plan.md`](plans/session-13-implementation-plan.md)
is the first Stage 2 session: release identity, the `upgrade` verbs, one front
door, and the D697 claim register. **Its §1 measured that a third of that
register cannot become claims at all** (D720) and that three of the rest were
already decided against, in a comment nobody had read (D722).

[`plans/session-14-implementation-plan.md`](plans/session-14-implementation-plan.md)
is the second: observability, alerting, and the capacity envelope — **the one
place the Stage 2 audit found genuinely empty.** Its §1 measured that the
constraint is not effort but **memory**: 3,814 MB, no swap, and 1,536 MB already
budgeted to two database containers (D761). `/metrics` has been reserved since
Session 1 and never used (D760).

[`plans/session-15-implementation-plan.md`](plans/session-15-implementation-plan.md)
is the third: identity lifecycle and credential rotation. **Its §1 measured that
the plane it was briefed to extend does not exist** — no refresh route, no table,
no column across 22 released migrations, and `refresh_token` present in the tree
only as a value the redaction denylist forbids (D812). A token lives at most
930 s and nothing renews it, so the gap is **credential retention rather than
convenience** (D813). Run 1 is D683's one unconditional line, and it closes
`bootstrap_identity`.

---

**Generated pages are marked.** `acceptance-matrix.md` and the table in
`mcp-tool-catalog.md` are rendered from the registry and the compiled capability
contract; editing them by hand is overwritten on the next render and caught by
`--check` in the meantime.
