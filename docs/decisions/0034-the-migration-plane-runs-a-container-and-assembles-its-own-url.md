# 0034 — The migration plane runs a container, and assembles its own URL

- **Status:** Accepted
- **Date:** 2026-08-08
- **Session:** 3
- **Affects:** `bin/migrate.py`, `bin/migrate.sh`, `bin/compose.sh`, `compose.yaml`,
  `secrets.required.yaml`, `src/agentic_postgres/rendering.py`,
  `src/agentic_postgres/runtime_override.py`,
  `tests/contract/test_compose_contract.py`, `tests/contract/test_database_commands.py`,
  `tests/contract/test_rendered_migrations.py` (new), DBX-MIG-001, DBX-MIG-002

## Context

Run 6 promoted `bin/migrate.sh` out of `FUTURE_STUBS` with `status` and `up`.
What those two did was print the rendered set and return `0`:

```python
print(f"migrate: {mode} is executed by dbmate over the project network …")
for version, name, sha in render_set(document):
    print(f"  {version}  {sha[:16]}  {name}")
return 0
```

`migrate up` reported success having applied nothing. Around it, three things
were missing in the same direction:

* nothing rendered the migration SQL to disk — `.generated/<key>/` held three
  files, and D43's `migrations/*.sql` did not exist;
* the `dbmate` service had no `/migrations` mount, so there was nothing for
  `--migrations-dir` to read;
* `--env APG_MIGRATION_DATABASE_URL` named a variable nothing set, and the
  declared secret was a whole connection URL.

`bin/compose.sh` also refused `run` in every mode, with a comment inviting the
ADR this is: *"exec, attach, run and cp reach inside a running container and
nothing in Session 2's documented path needs them. An operator who does can say
so in an ADR."*

## Decision

**The rendered payload is a file, dbmate is a one-shot container, and the URL is
assembled inside it.**

*The payload.* `rendering.write_rendered_migrations` writes
`<rendered>/migrations/<version>_<name>.sql` plus a `rendered-manifest.json`
recording each file's digest. ADR 0028 makes the rendered text the immutable
unit; this is where it becomes a thing that can be handed to something. The
files are `0644` inside a `0700` root-owned directory, because dbmate reads them
as uid 65532 — the enclosing mode is what keeps them private, not their own.

*The container.* `run` joins `RUNTIME_ALLOWED`. `up` is the wrong shape for a
process that applies a set and exits; it would leave a finished service in the
project's steady state. `run` arrives with two refusals that the rest of the
allowlist does not need: `--entrypoint`, which would replace the reviewed
command, and `-e`/`--env`, which is how a credential enters a container through
argv. Without those, `run` is a way to execute anything as root inside a
project's network with its secrets mounted.

*The URL.* The declared secret becomes `migration_user_password` — a password,
not a URL — and the entrypoint assembles

```
postgres://$APG_MIGRATION_ROLE:$password@postgres:5432/$APG_DATABASE_NAME?sslmode=disable
```

from three interpolated identifiers and the mounted file. A stored URL embeds a
role name, a host and a database name that `naming.py` also derives; when they
drift the cluster answers *password authentication failed*, which is the one
error nobody debugs by re-reading a manifest.

Every byte of the password is percent-encoded, not only the ones that look
dangerous. Measured: a base64 credential containing `/` produced
`invalid port ":V55…" after host`, a message naming neither the password nor its
file. Encoding the whole value cannot be wrong for an input nobody anticipated,
and the provider chooses this value.

*The ledger.* `app_private.migration_ledger` has existed since migration 0002
and nothing ever wrote to it. `bin/migrate.py` records one row per applied
migration — version, name, template digest, rendered digest — **as the
superuser over the container socket, not as the migration plane**.
`migration_user` holds no privilege on that table. dbmate's `schema_migrations`
records that a version ran; this records which bytes ran, and a role that could
write its own audit record could record bytes it did not execute.

## Consequences

`migrate status` now needs root, because reading the ledger starts a container.
It was in `test_status_and_render_need_no_root` and passed there for a reason
that has stopped being true.

`app_private.schema_migrations` is created by the **bootstrap** plane (plan
§6.1), owned by the object owner, with `USAGE, CREATE` on the schema and
`SELECT, INSERT, DELETE` on the table granted to `migration_user`. `CREATE` is
required and was measured: dbmate issues `CREATE TABLE IF NOT EXISTS` on every
run and PostgreSQL checks `CREATE` on the schema before `IF NOT EXISTS`
short-circuits. It concedes nothing the membership did not already imply —
`migration_user` can `SET ROLE` to the schema's owner — and dbmate has no way to
issue a `SET ROLE`.

`ON CONFLICT (version) DO NOTHING` on the ledger insert is what makes a second
`up` produce an identical ledger rather than fresh timestamps, which is what the
plan's convergence check compares.

## Alternatives considered

**Keep the URL as the secret.** Rejected above: three derived names inside an
operator-entered value.

**Pass the URL with `docker compose run -e`.** It would appear in the docker
client's argv on the host. No secret value may enter process arguments.

**Use Compose's `env_file:` for the credential.** Compose reads it on the host
at config time and injects the values into the container's environment, where
`docker inspect` shows them — which is what the Session 2 secret scan searches
for.

**Percent-encode only the characters that are invalid.** A shorter expression
and a longer list of assumptions about a value this repository does not choose.

**Have dbmate create its own ledger table with `CREATE` on the schema and no
bootstrap involvement.** Then the table is owned by `migration_user`, and the
one object the migration plane cannot be allowed to rewrite freely is the record
of what it applied.
