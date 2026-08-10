# 0048 — The example domain the migrations shipped, and the one four documents describe

Status: accepted
Date: 2026-08-10
Session: 5, Run 1
Amends: [0003](0003-example-domain.md)
Affects: SEC-RLS-001, SEC-VIEW-001, SEC-FUNC-001, API-SCHEMA-001, API-RPC-001, API-CONTRACT-001, AGT-WRITE-001

## Context

Session 5 publishes the `api` schema as a reviewed contract and a generated
OpenAPI document. Before it can do that, it has to know what the surface is —
and four source-controlled documents give one answer while six applied
migrations give another.

**What ADR 0003 froze**, and what `docs/source-specification.md` §7 and
`docs/capability-plan.md` both restate:

- `notes` — owner-scoped `title` and `content`.
- `tasks` — owner-scoped `title`, `description`, and a bounded `status` of
  exactly `pending | in_progress | completed | cancelled`.
- Four minimum operations: read notes, create one note, read tasks, and
  **change one task's status through a narrow operation**.
- Operation 4 is "deliberately not 'update a task'", because a narrow status
  transition "is expressible as a single PostgREST RPC with an approved shape,
  which is what `capabilities.yaml` can safely reference; a general update is
  not."

`docs/capability-plan.md` carries the consequence: a row mapping
`update_task_status` one-to-one onto the `tasks:write` scope, owned by
Session 9.

**What Session 3 shipped**, in `0003-owner-scoped-tables-and-forced-rls.sql`
and `0005-write-rpcs.sql`:

```sql
app.notes (id, owner_id, title, body, created_at, updated_at)
app.tasks (id, owner_id, note_id, title, done, created_at, updated_at)

api.create_note(p_title text, p_body text DEFAULT '')     RETURNS api.notes
api.create_task(p_title text, p_note_id uuid DEFAULT NULL) RETURNS api.tasks
```

`content` is named `body`. `description` does not exist. `status` is a boolean
called `done`. There is a `note_id` attachment nothing asked for. And the fourth
operation — the one ADR 0003 argued about at length — **does not exist at all**;
in its place is a second create.

None of this was recorded. It is not in a divergence table, not in an ADR, and
not in a comment. It shipped, three P0 requirements were proved against it, and
two sessions passed.

The reason it survived is worth stating, because it is this repository's own
pattern in a place nobody looks: **every test that could have caught it was
written from the code.** `SEC-RLS-001` proves user A cannot read user B's rows;
it does not care what the columns are called. `SEC-FUNC-001` proves the RPCs are
hardened; it reads their signatures out of the catalog and asserts they match
the catalog. `test_session3_authorization.py` names
`api.create_task(text,uuid)` — so the one test that mentions the divergence
asserts it. The frozen contract had no executable form, and a contract with no
executable form drifts silently by construction.

## Decision

**The code converges to ADR 0003. The documents are not edited to match the
code.**

Session 5 adds one migration that:

- adds a bounded `status` to `app.tasks` with exactly the four frozen values,
  derives it from `done` for existing rows (`true → completed`,
  `false → pending`), and drops `done`;
- adds `description` to `app.tasks`;
- renames `app.notes.body` to `content`;
- adds `api.update_task_status(p_task_id uuid, p_expected_status …,
  p_new_status …)` with optimistic concurrency, as operation 4;
- retires `api.create_task` by revoking its grants, and drops it;
- recreates `api.notes` and `api.tasks` over the new columns;
- ends with `NOTIFY pgrst, 'reload schema'`.

`note_id` **stays**. It is additive, it breaks nothing ADR 0003 states, and
removing it would drop a foreign key and its cascade from live data to tidy a
document. It is recorded here as an extension rather than left as a discrepancy.

**The contract gains an executable form in the same session.**
`contracts/postgrest-api-surface.yaml` becomes the machine-readable statement of
this ADR, and `API-CONTRACT-001` compares it against the catalog and against the
generated OpenAPI in both directions. That is the half ADR 0003 was missing.

## Consequences

**This is a data migration against two live projects**, and it is the first one
this repository has performed. Released migrations are immutable and
fix-forward, so this is additive plus a drop, applied through the ordinary
wrapper, recorded in the ledger by the superuser (ADR 0034). The `done → status`
derivation is total: every existing row maps, and the migration fails rather
than defaults if any row does not.

**Session 3's proofs move with it.** `tests/security/test_session3_authorization.py`
names `api.create_task(text,uuid)` in its signature assertions and must name
`api.update_task_status` instead. That is not a weakening — the requirement is
"every api function is hardened", and it will assert the same property about the
function that exists. `SEC-RLS-001`, `SEC-VIEW-001` and `SEC-DEFAULT-001` are
column-agnostic and are unaffected.

**Session 8 inherits a capability plan that is true.** `update_task_status` with
`tasks:write` has a backing operation for the first time. Under ADR 0006 the
scope vocabulary is `notes:read`, `notes:write`, `tasks:read`, `tasks:write`,
`meta:read`, and every one of those now maps onto something that exists.

**`docs/source-specification.md` is not touched.** It is the frozen input
specification and carries a committed `.sha256` for exactly that reason. A
specification-versus-implementation gap is not repaired by editing the
specification, and the fact that doing so is mechanically possible —
`test_source_specification_checksum_matches` would happily accept a new digest —
is an argument for saying so here rather than a licence.

**ADR 0003 is amended, not superseded.** Its decision stands; this record adds
`note_id` as an approved extension and states that the shipped implementation
diverged from it for two sessions. Its number stays where every existing test
marker and requirement description already points.

## Alternatives considered

**Supersede ADR 0003 to state what is deployed.** The cheapest option by a wide
margin: no migration, no data movement, no test changes. Rejected on the
strength of what would have to be rewritten with it — ADR 0003's own reasoning
about why operation 4 is a narrow transition, `docs/capability-plan.md`'s
`update_task_status` row, and a line in the frozen input specification. Three
documents and an argument are not overruled by an omission, and the omission is
what this is: nobody decided to ship `create_task`, and there is no record of
anyone weighing it.

**Keep `done` and add `update_task_status` over it.** A boolean is bounded, so
ADR 0003's stated rationale for an enum — that free text would force the write
path to accept an arbitrary string — is technically satisfied. Rejected: it
leaves a two-valued status behind an RPC whose whole shape is a transition
between four, and `pending → in_progress` would be unrepresentable. The
capability that Session 8 references would be narrower than the capability the
plan describes, which is the same defect one layer down.

**Defer the whole thing to Session 8, which is when `update_task_status` is
first needed.** Rejected, and this is the decisive one: Session 5 writes the
reviewed contract, the OpenAPI snapshot, the SQL documentation comments and the
published documentation page. Deferring means all four are produced from a
surface that is known to be wrong, and then regenerated three sessions later —
including the approval, the snapshot and the deploy that produced them.

**Add nothing and record the divergence.** Rejected because Session 5 is the
session that makes the divergence load-bearing. Up to now the two descriptions
disagreed in prose; from here one of them is a generated artifact compared
against a catalog by a P0 test, and disagreement stops being possible.
