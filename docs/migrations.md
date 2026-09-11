# Migrations

Schema changes reach a cluster one way: rendered to disk, locked, applied by
dbmate as a least-privileged role, and recorded by the superuser.

## Two artifacts, and only one of them is immutable

`migrations/templates/*.sql` are **templates**. They carry no project identity —
no role names, no database name, no schema owner — because those are derived per
project, and a template that named one would be a second place role names are
decided ([ADR 0002](decisions/0002-configuration-authority.md) forbids that).

Rendering substitutes the derived identities and writes the result to
`<rendered>/migrations/`, beside a `rendered-manifest.json` holding a digest per
file. **The rendered payload is the immutable unit**
([ADR 0028](decisions/0028-source-migrations-are-templates-the-immutable-unit-is-the-rendered-payload.md)):
it is what ran, it is what the ledger records, and it is what a later run
compares against.

Two projects therefore render different bytes from the same template, and
`test_two_projects_render_different_payloads` asserts exactly that. Rendering is
deterministic and carries no deployment metadata — no timestamp, no commit —
because a payload that changed on every render could never be compared with the
one that ran.

## The five that exist

```
20260807120001  schemas_and_default_privileges
20260807120002  project_identity_and_ledger
20260807120003  owner_scoped_tables_and_forced_rls
20260807120004  security_invoker_api_views
20260807120005  write_rpcs
```

`migrations/manifest.json` declares them; `migrations/released.lock.json` freezes
what has shipped. The preflight refuses on any disagreement between its five
sources — manifest, lock, templates on disk, rendered payload, and the ledger —
so an applied migration cannot be silently edited, removed or reordered
(`DBX-MIG-003`). A duplicate version and an out-of-order version are both
refused, and every `-- migrate:down` block refuses rather than running: down
migrations are a data-loss primitive wearing a symmetry argument.

## Running them

```bash
sudo bin/migrate.sh --project project.alpha.yaml --runtime status
sudo bin/migrate.sh --project project.alpha.yaml --runtime up
```

`up` is part of the deploy (step 6), so by the time an operator runs these by
hand they are usually verifications. `status` reports applied and pending
against the ledger.

### How dbmate is invoked, and why it looks like that

dbmate runs as a **container**, in the `migration` profile, through
`bin/compose.sh … run --rm dbmate`
([ADR 0034](decisions/0034-the-migration-plane-runs-a-container-and-assembles-its-own-url.md)).
`run` joins the Compose wrapper's runtime allowlist with `--entrypoint`, `--env`,
`--volume`, `--user` and `--publish` refused, because `run` is otherwise a way to
execute anything at all inside the project's network.

**No connection string exists anywhere a process can be listed.** The URL is
assembled inside the container by its entrypoint, from three derived identifiers
Compose interpolates and one password read out of a mounted file. Nothing that
carries the password appears in `compose.env`, in the resolved model, in
`docker inspect`, or in argv on either side of the daemon.

Two measured details that are not obvious:

- **The password is percent-encoded byte by byte.** A base64 password containing
  `/` was parsed by dbmate as the start of a port, and the error was
  `invalid port ":V55Uj2eS…" after host` — which reads as a malformed host, not
  as a credential problem.
- **dbmate 2.34.1 splits its flags by position.** `--migrations-dir`,
  `--migrations-table`, `--no-dump-schema` and `--env` are **global** and must
  precede the subcommand; `--strict` is **subcommand-only** and exists on `up`
  and `migrate` but not on `status`. A flag in the wrong position is exit 2,
  which is loud. A global flag silently omitted writes the ledger somewhere else
  entirely, which is not.

### The ledger is written by the superuser

`app_private.migration_ledger` records the version, the name, the digest of the
rendered bytes that ran, and when. It is written by `bin/migrate.py` **as the
superuser**, over the bootstrap plane — not by dbmate, and not by
`migration_user`.

That is the point. The migration plane must not be able to forge its own audit
record, so `migration_user` holds no `INSERT` on the ledger table, and a live
test asserts `has_table_privilege(... , 'INSERT')` is `false`. The insert uses
`ON CONFLICT (version) DO NOTHING`, so a re-run converges instead of failing.

dbmate keeps its own `app_private.schema_migrations`; that is dbmate's
bookkeeping and it is not the audit trail.

## Adding one

1. Write `migrations/templates/<version>_<name>.sql`, with `-- migrate:up` and a
   `-- migrate:down` that refuses.
2. Add it to `migrations/manifest.json`.
3. Render (`./deploy.sh --render-only …`) and check the payload is what you meant.
4. Run the contract suite. The preflight tests fail on version ordering,
   duplicate versions, an unlocked migration and a determinism break before any
   cluster is involved.
5. Deploy. `released.lock.json` is updated in the same commit that ships it.

Never edit a template that has shipped. The preflight will refuse, which is the
system working; the fix is a new migration.

## A project's set

ADR 0198. A project may bring migrations of its own. They live **tracked in the
release checkout**, under a directory the project manifest names at schema
version 5:

```yaml
schema_version: 5
migrations:
  set: projects/<slug>
```

```
projects/<slug>/migrations/manifest.json
projects/<slug>/migrations/templates/NNNN-*.sql
projects/<slug>/migrations/released.lock.json
```

Not beside the manifest on the host, and the reason is the one this whole plane
rests on: a release is exactly the commit it is named for. `assert_clean`
refuses a dirty checkout, the deploy runs `release/bin/migrate.sh` from the
checked-out release, and `upgrade plan` diffs two rendered releases. SQL applied
from outside that commit would be a schema no commit determines — which is the
state `assert_clean` exists to refuse.

**Two locks, never one.** The release's covers the platform's migrations; the
project's covers the SQL under `projects/<slug>/`. Neither verb writes the
other's:

```bash
bin/migrate.sh freeze-lock                        # the release's
bin/migrate.sh --project project.yaml freeze-lock # the project's
bin/migrate.sh --project project.yaml verify-lock # both; the release's always
```

A project lock also records `follows_release_version` — the release version its
migrations must all sort **after**. dbmate is handed a directory and orders the
whole of it by filename, so the two sets interleave by version stamp. Measured
on the pinned dbmate 2.34.1, with a control: a pending migration whose version
is older than an applied one makes `up --strict` exit 2 having applied
**nothing**, naming both versions; the same pair on a *fresh* cluster applies in
filename order and exits 0. One set, two schemas. `freeze-lock --project`
refuses at freeze so that never reaches a host, and dbmate's own refusal is the
backstop behind it.

**What a project's set may not contain**, refused before it is rendered:

| Refused | Because |
|---|---|
| anything naming `app_private` | the pre-request hook, the agent audit, the quota and idempotency tables are the platform's state |
| `CREATE`/`ALTER`/`DROP ROLE`, `SCHEMA`, `EXTENSION`; `ALTER DEFAULT PRIVILEGES` | the bootstrap plane owns roles; the migration plane owns objects |
| any `SET ROLE` but `SET LOCAL ROLE {{object_owner}}` | LOCAL, so the authority cannot outlive the transaction dbmate wraps the migration in |
| dropping an object the release publishes | a project adds to the published surface and never removes from it |
| a placeholder outside the six request roles and `database.name` | a project's SQL names its own database and the request roles, not the platform's identities |
| a table in `app` without `FORCE ROW LEVEL SECURITY` | FORCE is what makes the policies apply to the table's **owner**, and every write function here is `SECURITY DEFINER` running as that owner |
| a `down` block that does not raise `AP900` | this plane is fix-forward; a working rollback is one `dbmate down` from dropping a tenant's table |

Each is a boundary rather than a style rule. If an application genuinely needs
one of them, that is a product decision to raise — not a lint to configure.

The deployed document records what was applied: `migrations.release_lock_sha256`
and `migrations.project_set` (the directory, the digest of the project lock, and
the count). The doctor counts both sets against `app_private.migration_ledger`,
which holds a row per migration from either set.

`projects/example/` is a worked one — a pgvector column beside each note, a
`security_invoker` view, and one `SECURITY DEFINER` write function.

**A `security_invoker` view needs two grants, not one.** The view answers with
the CALLER's privileges on what it reads, so granting `api.<name>` and stopping
there refuses every caller — with `permission denied for table <name>`, naming
the table underneath rather than the view they were granted. The release does
both halves in one line for its own objects (`0004`: `GRANT SELECT ON app.notes,
app.tasks TO {{authenticated}}, {{agent_reader}}, {{agent_writer}}`), and the
example project's first migration did not, so for two sessions its view was
readable by nobody (D1189). Grant the view and the table it reads, to every role
that may ask. Neither grant touches whose rows come back: the table keeps FORCE
row level security and its owner-scoped policy.

## Seeds

A project may also ship **seeds** — rows, for a development cluster, applied by
`bin/apg.sh dev seed`:

```
projects/<slug>/seeds/manifest.json
projects/<slug>/seeds/<name>.sql
```

```bash
bin/apg.sh dev seed --project project.yaml example
```

The manifest is an allowlist, and the verb takes a **NAME**:

```json
{
  "schema_version": 1,
  "seeds": [
    {
      "name": "example",
      "file": "example.sql",
      "sha256": "<the file's digest>",
      "description": "What this seed writes."
    }
  ]
}
```

Never a path — the same door `bin/db.sh sql` has, for the same reason: a name
with a separator is refused for *being* one, before anything is joined to a
path, so `../../etc/anything` is answered "not a declared seed" rather than
resolved and then rejected. The digest must match, or the file was edited after
it was reviewed.

**A seed writes rows and creates nothing.** No table, no view, no function, no
grant: a seed that created an object would be an unversioned migration running
on one developer's cluster and on no deployment. It is linted against the same
table its set's migrations are (`app_private`, roles, schemas, extensions), plus
that one rule, and it may set exactly the owner preamble and must set it first.

It is applied as the **migration user**, in one transaction, with `app.user_id`
set to the environment's development subject — so the rows are the subject's,
which is what makes them visible through `apg dev psql`. Without that identity
every owner-scoped write raises `AP401: no request identity for this
transaction`. A seed is applied once per environment; `apg dev reset` is the way
back.

## Two things that bit, and are now grants rather than surprises

- **`CREATE TABLE IF NOT EXISTS` checks `CREATE` on the schema *before* the
  existence check.** dbmate creating its own table in `app_private` therefore
  needs `USAGE, CREATE` on the schema even though the table already exists. The
  error is `permission denied for schema app_private`, on a statement whose
  `IF NOT EXISTS` suggests it should have been a no-op.
- **Two creators, one table.** Bootstrap creates
  `app_private.project_identity` as the superuser; migration `0002` creates the
  same table `IF NOT EXISTS` under `SET LOCAL ROLE object_owner` and then
  `COMMENT`s on it, which failed with `must be owner of table`. Ownership is now
  stated explicitly rather than left to whichever plane got there first.
