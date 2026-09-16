# 0211 — A project set names the request roles and its own database, and the refusal says why the line the adopter copied is dead

- **Status:** Accepted
- **Date:** 2026-09-16
- **Session:** 28, Run 2 (D1411, D1437)
- **Affects:** no requirement id moves. `TEN-SET-002` is the claim; its proofs
  keep every assertion they hold. **No allowlist is widened.**
- **Related:** ADR 0198 (`PROJECT_PLACEHOLDER_SOURCES` and the lint that reads
  it), ADR 0196 and D1058 (`0003`'s comment has been false since `0006`, found
  by the session that restored `create_task`), D912 (never amend an applied
  migration — which is why the comment cannot be repaired in place), D930 and
  D957 (a premise wrong in the reassuring direction survives longest), F-013
  (the adopter's finding), D1411, D1437.

## Context

**The finding is real and its stated repair is backwards.** An adopter who
forked this product copied the platform's example domain into their own
migration set, including `0003`'s last grant, and `lint_project_set` refused the
set:

```
placeholder 'app_runtime' reads 'database.roles.app_runtime', which a project
set may not read. Allowed: ['database.name', 'database.roles.agent_reader',
'database.roles.agent_writer', 'database.roles.anon',
'database.roles.api_documentation', 'database.roles.authenticated',
'database.roles.object_owner']. A project's SQL names the request roles and its
own database, and none of the platform's other identities.
```

F-013 reads this as an inconsistency — *the lint forbids what the release's own
migration uses* — and prices the repair at *an ADR, then roughly one line*. The
one line would be `"database.roles.app_runtime"` added to
`PROJECT_PLACEHOLDER_SOURCES`, which is a security boundary whose own docstring
says *"Every refusal here is a boundary, not a style rule."*

**The grant the adopter copied does not grant anything, and this project
measured that two sessions before the finding was filed.** Only two released
templates name `{{app_runtime}}`: `0001` grants schema `USAGE`, and `0003`
grants `SELECT, INSERT, UPDATE, DELETE ON app.notes, app.tasks`. Three
migrations later `0006-app-runtime-least-privilege.sql` issues `REVOKE ALL ON
SCHEMA app FROM {{app_runtime}}`, and its own header carries the measurement:

```
--   has_table_privilege(app_runtime, 'app.notes', 'SELECT')  ->  true
--   SET ROLE app_runtime; SELECT * FROM app.notes            ->  denied
-- THE SCHEMA REVOKE IS THE ONE THAT HOLDS.
```

Migration `0031`'s manifest entry says the same thing in the release's own
words: *"`0003`'s grant to `app_runtime` is inert because `0006` revokes ALL ON
SCHEMA app, so `0003`'s comment has been false since `0006` (D1058)."*

**What `0006` measured was a table that already existed. A fork's table does
not.** That gap is the whole of what this ADR rests on, so it was measured
rather than reasoned, on the pinned `pgvector/pgvector:pg18` image — PostgreSQL
**18.4**, the deployment's own version — with a control the revoke cannot reach:

| | `has_table_privilege` | `SET ROLE app_runtime; SELECT count(*)` |
|---|---|---|
| `app.notes` — created **before** the revoke | `true` | **permission denied for schema app** |
| `app.invoices` — created **after** the revoke, granted after it | `true` | **permission denied for schema app** |
| `tenant_control.invoices` — CONTROL, schema never revoked | `true` | **0** (permitted) |

So a fork's own table in `app`, granted to `app_runtime` by a copied line, is as
unreachable as the release's. The control came out green in the same
invocation, which is what makes the two denials evidence rather than a broken
rig (D499).

**The thing that misled the adopter is a comment, and the comment cannot be
fixed.** Above `0003`'s grant stands: *"The runtime identity works on these
tables directly; it is granted USAGE on `app` in 0001."* It is false, D1058 says
so, and `scope-closure.md` records why it is open by construction: *a released
template's bytes are the unit `verify-lock` checks, so editing even a comment
changes a record*. D912 forbids the amendment. A fix-forward migration can
change the database; it cannot change a sentence in a file an adopter reads.

## Decision

### 1. `PROJECT_PLACEHOLDER_SOURCES` stands, byte for byte

No source is added. A project's SQL names the six request roles and its own
database, and none of the platform's other identities. **`app_runtime` in
particular is refused**, and this ADR is the written refusal `CLAUDE.md` §6
requires: admitting it would grant an adopter a placeholder for an identity the
release itself revokes, and widening an allowlist to match a dead line of SQL is
weakening, not the measured-set widening §6 permits.

### 2. The refusal says why the copied line is dead

The message keeps its current text and gains the reason, because a refusal that
lists an allowlist answers *what is permitted* and leaves the adopter's actual
question — *why does the release do it then?* — unanswered. It must name `0006`,
state that the schema revoke makes the copied grant unreachable, and say that
removing the line changes nothing the cluster does.

That sentence is what makes the refusal act on the adopter's belief rather than
on their file. It is Run 3's code and it is the whole of the repair.

### 3. `0003`'s comment is not repaired, and where a reader meets it is

The comment stays false in `0003`'s bytes, permanently, for D912's reason. What
this ADR adds is that the correction must live where the adopter reads **before**
copying: the project-set documentation, and the refusal in §2. A correction that
exists only in a manifest description, an ADR and a ledger row is a correction
three readers deep, which is how this one reached an adopter uncorrected after
two sessions had recorded it.

### 4. Removing the dead grant by fix-forward is not done

A released migration whose only effect is to revoke a privilege already
unreachable through its schema would change no cluster, would not touch the
comment, and would add a thirty-fourth released migration to every deployment in
order to tidy a line. The grant is inert; the ADR records it as inert and leaves
it.

## Consequences

- **The one-line repair F-013 proposes is refused in writing**, with the
  measurement. A later session that meets the finding again meets this ADR
  first.
- The refusal message moves, so `test_project_migration_sets`'s assertion on it
  moves with it in the same commit, and the assertion gets **stricter**: it
  names `0006` as well as the allowlist.
- **An adopter converting a pre-`projects/` fork hits this refusal**, and ADR
  0212 depends on what removing the line costs: nothing on the cluster, and a
  change to an applied template's bytes. ADR 0212 decides that case.
- The audit's F-013 row and `docs/upgrade-guide.md` both describe the lint as
  inconsistent with the release. Run 3 corrects both, from this ADR.

## Alternatives considered

**Admit `app_runtime` to the allowlist** (F-013's own repair). Rejected. It
widens a security boundary to match SQL that grants nothing, and it hands every
future project set a placeholder for the platform's runtime identity — an
identity whose whole design since `0006` is that it reaches `app` through
nothing. The finding's premise, *the release uses it so a project may*, is true
about the text and false about the effect.

**Delete the grant from `0003`.** Rejected: D912. A released template's bytes
are the unit `verify-lock` checks and the unit `migration_ledger` records; an
edit for the sake of a comment would invalidate the record of what ran on every
deployment of every earlier release.

**Make the lint configurable, so an adopter may permit a source.** Rejected by
`lint_project_set`'s own docstring, which is quoted here because it is the
argument: *"A lint that could be configured is a lint an adopter would
configure."* If a set genuinely needs an identity this refuses, that is a
product decision recorded as one, not an exception in a config file.

**Leave the refusal message alone and fix only the documentation.** Rejected.
The adopter met the refusal, not the page. A refusal is the last documentation a
person reads before they change their file, and this one sent them at the lint.
