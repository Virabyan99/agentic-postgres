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
