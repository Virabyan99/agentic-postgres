# 0203 — The local environment is the database, built from the render and the release, and it holds no production secret

- **Status:** accepted
- **Date:** 2026-09-11
- **Session:** 22, Run 1 (D1157, D1158, D1160, D1161, D1170, D1171, D1174)
- **Related:** ADR 0013 (`compose.sh`'s privilege gate — and why this command
  does not use it), ADR 0026 (the migration user reaches the owner by `SET
  LOCAL ROLE` only), ADR 0028 (the rendered payload is the immutable unit),
  ADR 0030 (a bootstrap plane removes nothing), ADR 0065/0066 (a rig is a
  second configuration of the product), ADR 0067 (the bootstrap's statement
  list is tested on both sides of its boundary), ADR 0095 (the issuer names a
  role, the auth service names a subject), ADR 0148 (the connection budget the
  bootstrap issues), ADR 0198 (a project owns a migration set), ADR 0199 (one
  resolver, exit 3/4/5); D105 (nothing prints a token), D285 (the defect a
  superuser rig cannot find), D1066, D1076.

## Context

A developer who wants a cluster with this release's schema on it has exactly
one path today: run a contract test module. Nothing in `bin/` gives them that
cluster, nothing seeds one, and nothing an adopter can run before their first
deploy tells them whether their migration set applies as the role that will
apply it — which is D285's class, the defect that took a live project down in
Session 6.

The stage plan asked for the fixture path made a product, plus "a short-lived
local JWT signed by a throwaway key … and the developer's own PostgREST and
auth service **if the loop needs them** — measured first whether it does."

That was the right question. Run 1 measured it.

### What the tree says, measured at `dd9e2be`

**A token alone reaches nothing a developer wants** (D1157). `bin/dev-token.py`'s
own docstring: *"a token from here can reach the surface and can read no
owner's rows."* The issuer names a role; the auth service names a subject (ADR
0095); migration 0013's pre-request hook compares a subject against
`app_private.users`; and every owner-scoped policy reads `app.user_id`
(`0003:13-19`), a GUC the hook sets from the claims. A REST loop therefore
needs PostgREST **and** the auth service **and** a registered subject: three
containers and the production key flow — the production stack minus Traefik,
as a second Compose model nobody audits. That is precisely what ADR 0013 and
ADR 0065 both refuse.

**The fixture is six fixtures, not one** (D1158). `cluster()` is defined in
`test_storage_plane.py:77`, `test_migrations_apply_as_the_migration_user.py:91`,
`test_auth_service_reaches_its_data.py:78`,
`test_storage_service_reaches_its_data.py:72`, `test_agent_audit_plane.py:107`
and `test_auth_endpoints.py:117`. Only the migration-user one applies the
product's own `build_statements()` and applies as `migration_user`; the others
apply as the superuser, and one reimplements the bootstrap by hand and stopped
a statement short (F-005, its own comment at `test_auth_endpoints.py:170`).
None writes `schema_migrations` or `migration_ledger`.

**Rig 22b, on the pinned image, 2026-09-11.** The production order read from
`bin/deploy-project.py` step 6 — every bootstrap statement first, then every
rendered migration as the migration user — applied **32 of 32** in 8.6 s. The
fixture's order (bootstrap at index 1) applied **0 of 32**: the migration
user has no privilege on `app_private` until the bootstrap grants it, so a
migration that writes its own `schema_migrations` row cannot be the first
thing that runs. A dev cluster that records what dbmate records is therefore
obliged to use the deploy's order, not the fixture's.

**Rig 22a, the same day.** `docker run -p 127.0.0.1:0:5432` records `HostIp
"127.0.0.1"`; the control `-p 0:5432` records `0.0.0.0` **and** `::`. The
pinned image declares `VOLUME /var/lib/postgresql`, so a correct container has
exactly one mount — an anonymous volume — and `docker rm -f` leaves it behind
where `docker rm -f -v` removes it. `Networks` keys are exactly `{"bridge"}`.
`SHOW wal_level` is `replica` with no `-c` passed. `docker exec --env-file`
works on docker 29.5.2, and the discriminating control (rig 22a-3: a client
container reaching the cluster across the bridge) refuses with *"fe_sendauth:
no password supplied"* without it and *"password authentication failed"* with
the wrong one.

**Rig 22b-2.** `PGOPTIONS='-c app.user_id=<subject>'` carries the subject
through a connection: as the application role, `api.notes` returns the
subject's row with it, **0** without it, and **0** with a different subject.
The `authenticated` role cannot log in at all (*"permission denied for
database"*) — it is a role PostgREST switches into, not one that connects. And
`app_private.auth_create_user` accepts a `role_name` this deployment does not
derive: nothing in the database refuses it, so deriving it is the command's
job.

## Decision

### 1. The environment is the database

`apg dev` builds **one container**: the locked PostgreSQL image, this
release's schema, this project's set, one development subject. It builds no
PostgREST, no auth service, no JWT, and it has no `token` verb.

The developer's loop is `apg dev psql` (the **application** role, with
`app.user_id` preset to the development subject through `PGOPTIONS`), `apg dev
seed`, and any client on the loopback port. Session 23's generated client and
Session 24's loopback Studio each decide what they need on top of the
database; this session gives them the database.

### 2. `docker run` on the locked image, not `compose.sh`

`compose.sh`'s privilege gate (ADR 0013) is right for a deployment's model,
and a deployment's model is not what this is. A dev cluster is one container,
root-free, with no network to audit and no secret to materialise. Reusing the
project's Compose model would make a second way to start the product's
containers — unaudited, and diverging the first time either changed.

The image is named **by digest**, from `versions.env`. Nothing else is passed:
no `--network`, no `-v`, no `-c`.

### 3. The product path is extracted, and the fixture is pointed at it

`build_statements` and the rendered-payload verifier and the ledger statement
move into `src/agentic_postgres/` (`bootstrap_statements.py`,
`migrations.verify_rendered_directory`, `migrations.ledger_insert_statement`).
`bin/postgres-bootstrap.py` re-exports every moved name and `bin/migrate.py`'s
two functions keep their names and arities (ADR 0175), so every reader that
loads either by path sees what it saw.

`test_migrations_apply_as_the_migration_user.py` is pointed at the module —
that is what makes the product path the fixture path rather than a claim that
it is. **The other five fixtures are not rewritten.** Each is a rig with
reasons of its own: a superuser is what they need to plant the state they
measure. Rewriting five rigs is not this session, and F-005 stays recorded.

### 4. What the environment applies, and in what order

The deploy's order, settled by rig 22b: the bootstrap's statements as the
superuser, then every **rendered** migration payload — the bytes dbmate
applies, verified against `rendered-manifest.json` by the same check
`bin/migrate.py` runs — as the **migration user**, in manifest order, each in
its own transaction carrying its own `app_private.schema_migrations` row. Then
`migration_ledger`, written as the superuser exactly as `record_ledger` writes
it.

Both ledgers, because a dev cluster whose ledger has production's shape is one
`migrate.sh status` can read the same way, and a dev cluster built from
re-rendered templates would be a second render nobody compares (ADR 0028).

The environment **reads** `.generated/<key>/outputs.json` through the one
resolver (ADR 0199, exit 3/4/5) and **renders nothing itself**. An unrendered
project is refused with exit 4 naming the `--render-only` command.

### 5. Two generated passwords, in `0600` files, never in an argument vector

`migration_user` and `app_runtime` are activated with passwords generated per
environment and written to mode-`0600` files under `.generated/.dev/<key>/`.
They reach `psql` through `docker exec --env-file` — measured in rig 22a —
and never through `-e NAME=VALUE`, which puts the value in the **host's**
`docker` argument vector where `ps` reads it. That is the construction
`test_root_script_policy.py` already scans `bin/` for, and D105's rule: a
credential in an argument vector, a scrollback or a log is a credential in a
support ticket.

*"No production secret"* is the other half and is meant literally: no
repository key, no cipher pass, no provider token, no deployed document from a
host. The two passwords above exist only for a container that `down` destroys.

### 6. One development subject, with a verifier that verifies nothing

`up` registers exactly one subject, `dev`, through the product's own
`app_private.auth_create_user` as the superuser:

- `role_name` is the document's **`authenticated`** role, in full — what the
  auth service's `_role_name` stores;
- `scopes` is `scope_registry.vocabulary(merged surface)`, sorted: the whole
  data class the reviewed surface derives, which is what the issuer's ceiling
  would admit (ADR 0200);
- `password_hash` is a **well-formed argon2id encoding of random bytes with no
  password behind it** — `$argon2id$v=19$m=65536,t=3,p=4$<22 b64>$<43 b64>` —
  which satisfies `user_credentials_password_hash_check` and verifies nothing.

The environment has no login path, so a verifier for no password is the honest
row. It is stated here rather than smuggled into a helper. An operator command
may import only the standard library, `agentic_postgres` and `yaml`
(`HOST_PACKAGES`, D292/ADR 0093), so there is no `argon2` to hash with even if
there were a password to hash.

The subject's id goes in `state.json` — it is an identifier, not a secret —
and `seed` and `psql` assert it through `app.user_id`.

### 7. The seed door is the door `db.sh sql` already has

`apg dev seed NAME`, never a path. The name is looked up in
`projects/<slug>/seeds/manifest.json`; the file's digest must equal the
recorded one; the text is linted with the set's forbidden statements **plus
every DDL verb**; it is rendered with the set's declared placeholders and
applied in **one transaction** as the migration user, with `app.user_id` set
to the development subject and the owner preamble as its first statement. A
seed already recorded in the state is refused until `reset`.

`bin/db.sh sql` takes a name from a fixed allowlist and no flag relaxes it. A
`FILE` argument is the door that command was built not to have, and the reason
it takes a name is the same reason here.

### 8. `reset` is `down` then `up`

Byte for byte the same code, and no in-place variant. A role survives `DROP
DATABASE`, so a reset that kept the container would carry role passwords,
settings and the superuser's state across resets — and would be a second
bring-up path with defects of its own. Two paths to one state is the defect
class this project keeps producing; one path measured twice is a number.

`down` runs `docker rm -f -v`: without `-v` the anonymous volume outlives the
container (rig 22a).

### 9. What the environment never has

No network but the default bridge. No bind mount, and no mount destination
under `/etc/pgbackrest` or naming `pgbackrest.conf`. No name the secrets
contract declares — checked against `secrets_contract.active_secrets(contract,
CURRENT_SESSION)` over **every** facility, not the narrowed view, because the
environment has no facilities. `wal_level` `replica`, asserted rather than
assumed. Its port published on `127.0.0.1` only. Its state under
`.generated/.dev/<key>/`, dot-prefixed so `evidence.load_rendered` skips it and
the gate's collision count never sees it.

The proof of all of that reads the **rendered project's own model** in the same
test, through the same Compose helper `test_compose_contract.py` uses, as its
control: that model puts `postgres` on `["internal", "backup"]` and mounts
`pgbackrest.conf`. A claim that a thing cannot reach the chain is a property
of where it runs, and a proof written against an imagined container shape —
*no mounts* — would be red on a correct environment and green on nothing.

## Alternatives

**PostgREST plus auth plus a throwaway signing key on the workstation.** The
stage plan's reading. Measured: it is three containers and the production key
flow, and it is the production stack minus Traefik expressed as a second
Compose model. Rejected (D1157); Session 23 may measure whether its generated
client needs one, and if so that is its decision to take with its own ADR.

**A token verb with no auth service.** A subject-less token reads no owner's
rows — `bin/dev-token.py` says so itself. It would ship a thing that appears
to work and returns nothing. Rejected.

**Reusing the project's Compose model with a dev profile.** ADR 0183 says a
profile only narrows; this would need it to substitute — different networks,
no backup, no secrets. Rejected.

**Keeping the container and dropping the database on `reset`.** Faster by the
container's ~4 s. It carries role state across resets and is a second
bring-up path. Rejected (D1174).

**Seeding from a path the developer names.** Rejected; §7.

**Hashing a real development password.** Needs `argon2`, which an operator
command may not import, and invents a credential for a login path that does
not exist. Rejected (§6).

**Rewriting all six `cluster()` fixtures onto the module.** Five of them want
a superuser to plant state; converting them is a session of its own and would
bury this one. Rejected; recorded in §10 of the plan.

## Consequences

- `src/agentic_postgres/dev_environment.py` (pure: argv, statements, state)
  and `src/agentic_postgres/bootstrap_statements.py`; `bin/dev.sh` and
  `bin/dev.py`; `apg.sh dev` by construction (the dispatcher holds no list).
- `migrations.verify_rendered_directory` and `migrations.ledger_insert_statement`;
  `bin/migrate.py` delegates and keeps its two names and arities (ADR 0175).
- `test_migrations_apply_as_the_migration_user.py` is pointed at the module.
  The other five fixtures are unchanged and F-005 stays open.
- `.generated/.dev/<key>/` — `state.json`, two `0600` env files,
  `seeds-applied.json`, directory mode `0700` — invisible to
  `evidence.load_rendered` and to the gate's collision check.
- `projects/<slug>/seeds/manifest.json` (schema 1) and
  `projects/example/seeds/example.sql`.
- Churn published in the capacity envelope as `MACHINE` measurements naming
  the machine and the image-cache state (D593); the uncached workstation case
  named `UNMEASURED`.
- CI runs the round trip — `up`, `status`, `seed`, `reset`, `down` — which is
  what a PR environment is here (D1073).
- D1076 is proved by construction, with the rendered model as the control.
- The six-fixture family stays a family; D1158 records it and the five keep
  their superusers.
