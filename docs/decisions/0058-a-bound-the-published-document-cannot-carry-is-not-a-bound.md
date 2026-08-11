# 0058 — A bound the published document cannot carry is not a bound

Status: accepted
Date: 2026-08-11
Session: 5, Run 5
Amends: [0048](0048-the-example-domain-the-migrations-shipped.md)
Affects: API-CONTRACT-001, API-RPC-001, AGT-WRITE-001

## Context

ADR 0003 froze a bounded task status of exactly
`pending | in_progress | completed | cancelled`, and argued for the bound: it is
what makes "change one task's status" a capability `capabilities.yaml` can
safely reference, where free text is not. ADR 0048 requires Session 5 to add it.

Neither says *how*, and PostgreSQL offers two spellings that are equally bounded
in the database:

```sql
status app.task_status NOT NULL DEFAULT 'pending'          -- an enum type
status text NOT NULL CHECK (status IN ('pending', …))      -- a check constraint
```

Session 5's job is to publish this surface as a generated OpenAPI document, so
the question is not which one bounds the column — both do — but which one the
document can carry. Run 5 measured it, on a table carrying **both**, served by
the locked PostgREST with `openapi-mode = follow-privileges`:

```json
"status":      {"type":"string","format":"app.task_status",
                "enum":["pending","in_progress","completed","cancelled"]}
"status_text": {"type":"string","format":"text"}
```

The check constraint is nowhere in the document. Not abbreviated, not described
in prose — absent. A generated contract built over the text column would state
that `status` is a string, and every one of the four values ADR 0003 argued
about would be invisible to the client, to the reviewer comparing the snapshot,
and to Session 8's capability catalog.

The measurement also produced the second half of the decision, which nobody had
asked: the `format` string is the type's **schema-qualified name**. An enum in
`app` publishes the literal text `app.task_status` in a document served to the
internet — naming, in the artifact, a schema whose entry in
`forbidden_schemas` exists to keep it unaddressable.

## Decision

**`api.task_status` — an enum type, in the schema that is published.**

- An enum rather than a check constraint, because only the enum reaches the
  generated document, and the document is what this session exists to produce.
- In `api` rather than `app`, so the only schema name the published contract
  carries is the one it is allowed to carry. Verified on the generated document:
  the strings `app.`, `app_private` and `pg_catalog` appear nowhere in it.

**The reviewed surface contract gains an `enums:` section**, naming
`task_status` and its four values in order. ADR 0048 said the contract "gains an
executable form in the same session"; without this, the one clause of ADR 0003
that was argued at greatest length is the one clause with no executable form —
a frozen enumeration checkable only by reading two documents side by side, which
is exactly how the domain drifted for two sessions in the first place.

## Consequences

**The four values are now checkable in three places that must agree**: the
reviewed contract, the catalog, and the generated OpenAPI. `API-CONTRACT-001`
compares them, and a fifth value added to the type without a reviewed change to
the contract fails offline against the contract and live against the document.

**Ordering is part of the contract.** `enumsortorder` decides the order the
values appear in the published document, so adding a value is a decision about
where it goes, not only whether it exists. The contract lists them in order and
the comparison is order-sensitive; a set comparison would let a reordering pass
and change every generated client's idea of the default-looking first value.

**A type in `api` is an object in `api`.** `API-CONTRACT-001`'s rule is that an
unlisted object in the exposed schema fails the gate, and this adds a kind of
object that is not a relation and not a routine. The `enums:` section is what
lists it, so the rule keeps its meaning rather than acquiring an exception.

**Removing a value later is a data migration, not a type change.**
`ALTER TYPE … RENAME VALUE` exists and `DROP VALUE` does not, which is a real
cost of the enum and is accepted: the values are frozen by an ADR, so changing
one is already a decision that has to be written down before it is typed.

**One question is now moot rather than answered.** Whether reading an enum
column through a `security_invoker` view requires `USAGE` on the *type's* schema
was never measured. With the type in `api`, every request role already holds
that USAGE, so the answer cannot affect this design — which is a better outcome
than measuring it, because it stays true if the answer changes.

## Alternatives considered

**A check constraint on `text`.** Cheapest, and it is what a database-first
instinct produces: no new type, no `ALTER TYPE` awkwardness, values trivially
addable and removable. Rejected on the measurement — it publishes nothing. The
bound would be real, enforced, and invisible to every consumer of the artifact
this session ships, which is the shape of defect this project keeps producing:
a constraint that is genuinely there and that nothing downstream can see.

**A `domain` over `text` with a check.** PostgREST reports domains separately
(`Domain Representations` in its schema-cache log), so this was worth measuring
rather than assuming. Not adopted: it is a third mechanism whose published form
would have to be measured on every version bump, to reach a document the enum
reaches directly.

**The enum in `app`, beside the table it constrains.** The conventional
placement, and where the type "belongs" if schemas are organised by what owns
the data. Rejected because it publishes `app.task_status` in the served
document. The type is not private data; it is part of the wire format, and the
wire format lives in `api`.

**A lookup table with a foreign key.** The most extensible answer, and the one
that would let a project add a status without a migration. Rejected for exactly
that: ADR 0003 froze these four deliberately, and a design whose whole advantage
is that the set can change quietly is the wrong answer to a requirement that the
set may not.
