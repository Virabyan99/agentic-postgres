# The developer loop

`apg dev` is a database of your own, built from the project you rendered and the
release you are sitting on. It exists because the alternative was restoring a
backup — measured at 247 s on the deployment host during the Session 18 trip —
and because a migration that is going to fail should fail on your machine in ten
seconds rather than halfway through a convergence.

It is defined by ADR 0203, and the sentence that decides everything else in it
is: **the local environment is the database.** Not a deployment in miniature.

---

## 1. The six verbs

Every one takes `--project FILE`, the same manifest you render with. The
project's derived key names the environment, the container and the state
directory, so two projects never collide and the same project is always the
same environment.

```bash
./deploy.sh --project project.yaml --capabilities capabilities.yaml --render-only
bin/apg.sh dev up --project project.yaml
```

### `up`

Builds the environment:

1. `docker run` on the locked postgres image **by digest**, from `versions.env`
   — the same image the deployment runs;
2. the deploy's own `build_statements()` applied as the superuser. Not a second
   implementation of the bootstrap: the same function, from
   `src/agentic_postgres/bootstrap_statements.py`, which `bin/postgres-bootstrap.py`
   re-exports;
3. every rendered migration payload, verified against `rendered-manifest.json`
   and applied **as the migration user** in manifest order, each in its own
   transaction carrying its own `schema_migrations` row — the release's
   migrations and, if your manifest declares a set, yours after them;
4. `migration_ledger` written as the deploy writes it;
5. two roles activated with generated passwords, written to `0600` env files;
6. one development subject registered through `app_private.auth_create_user`.

It refuses a project this checkout has not rendered, with exit 4 and the render
command. It prints no password.

### `status`

Four answers, not two: `running`, `stopped`, `absent`, `unknown` — each with its
reason and its own exit code. `unknown` is the one that matters (ADR 0195): a
state file this user cannot read is not the same as no environment, and a
command that folded the two would tell you to run `up` when the fix is a
`chown`.

### `psql`

An interactive session **as the application role**, with the development
subject asserted through `app.user_id`. What you see is what that subject sees
under row-level security, which is the point — a session as the owner shows you
rows your application will never see.

```bash
bin/apg.sh dev psql --project project.yaml
bin/apg.sh dev psql --project project.yaml --as migration-user
bin/apg.sh dev psql --project project.yaml -- -c '\dt api.*'
```

`--as migration-user` applies SQL the way a migration would, which is how you
find out whether a statement you are about to freeze actually works under that
role's privileges. Arguments after `--` are psql's own and are forwarded unread.

### `seed NAME`

See §3.

### `reset`

`down`, then `up`. About ten seconds. This is the verb that makes the others
cheap: there is no reason to repair a development database you have made a mess
of.

### `down`

Removes the container, its anonymous volume and the state directory. Exits 0
when there was nothing to remove and says so, because a teardown that fails on
an absent environment is a teardown nobody puts in a script.

---

## 2. Where the state lives

```
.generated/.dev/<project-key>/
├── state.json              0600  the container, the database, the port, the subject
├── superuser.env           0600
├── migration-user.env      0600
└── app-runtime.env         0600
```

The directory is `0700` and **dot-prefixed**, which is not cosmetic: the
evidence reader walks `.generated/` for rendered projects, and a directory it
took for one would make every deploy and every gate read an environment as a
deployment.

Passwords reach the container through `docker exec --env-file`, never on an
argument list, and nothing the command prints is one. Both properties are
asserted rather than intended — `test_no_password_is_ever_an_argument` and
`test_nothing_the_command_prints_is_a_password`.

---

## 3. Seeds

A seed is development data, and the door it comes through has a lock on it so
that it cannot quietly become a second migration path.

```
projects/<slug>/seeds/manifest.json
projects/<slug>/seeds/example.sql
```

The manifest names each seed and records its SHA-256. `apg dev seed NAME` takes
**a name, never a path**, and refuses:

| What | Exit |
|---|---|
| A path, or a name containing `/` or starting `.` | 2 |
| A name the manifest does not carry (naming the ones it does) | 2 |
| A digest that does not match the file | 5 |
| DDL — `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `GRANT`, `REVOKE`, `COMMENT`, `VACUUM`, `ANALYZE` | 5 |
| Anything touching `app_private` | 5 |
| A role change other than the owner preamble | 5 |
| A seed already applied to this environment | 5, until `reset` |

What survives is rendered with your migration set's placeholders — the same
substitution the migrations get, and nothing more — and applied in **one
transaction** as the migration user with the development subject asserted
before any statement runs. So the rows a seed writes are the subject's rows, and
`apg dev psql` sees them.

The lint reads statements, not comments: a seed may explain why it does not
create a table.

`projects/example/seeds/example.sql` is a worked one — two notes and an
embedding, written through `api.create_note` and `api.set_note_embedding`,
which is to say through the project's own reviewed surface rather than around
it.

---

## 4. What this is not

* **Not a deployment.** No REST, no auth service, no storage, no agent plane, no
  token, no login. The subject's verifier verifies no password, because nothing
  here authenticates anybody. A developer who wants the HTTP surface wants a
  deployment, and that is `./deploy.sh`.
* **Not a branch.** No parent, no promotion, no durability. `down` and `reset`
  destroy the data, the volume is anonymous, nothing is archived and nothing is
  backed up. If you want to keep what is in it, write a seed.
* **Not near production.** The command reads `.generated/<key>` and the release,
  and never `/var/lib/agentic-postgres`, `/etc/agentic-postgres`, a provider, a
  backup repository or a cipher pass. The container joins no network but the
  default bridge, has no bind mount, holds no name the secrets contract
  declares, and publishes its port on `127.0.0.1` only. The control for that
  assertion is the rendered project's own Compose model, read in the same test:
  it joins `backup` and mounts `pgbackrest.conf`, and this does not.

---

## 5. What it costs

| | This workstation, image cached | A fresh CI runner, image pulled |
|---|---|---|
| `apg dev up` | 10.98 s, 9.89 s | see the run's log |
| `apg dev reset` | 10.07 s, 10.28 s | see the run's log |

33 migrations — the 31 released plus the example project's set of two — on an
8 GB development machine under WSL2 with Docker server 29.5.2. These are
`MACHINE` numbers: they describe the machine they were sampled on and do not
transfer, which is why they are published with their conditions and why the
image-cache state is one of them. The first `up` you ever run pulls the image,
and that is most of what you will wait for.

[The capacity envelope](capacity-envelope.md) is where they live, beside the
numbers that *do* transfer and the list of what nobody has measured.

---

## 6. What to do when

### Docker is absent

`up` cannot build anything and says so. So does `bin/session-22-check.sh --mode
offline`, which needs a daemon and **refuses** rather than running — because the
cluster proofs would skip, a skip is not a pass, and the offline evidence half
would be written with `dev_environment` reading `not_run`: a document that looks
like evidence of a command nobody ran.

### The state is stale

`status` says `stale` when the state names a container that is gone, or a
release the checkout is no longer at. The answer is `reset` — or `down` if you
want the disk back. There is nothing in the environment worth recovering; that
is what makes it disposable.

### A seed is refused

Read which of §3's rows it hit. The two that surprise people:

* **a digest that moved** — you edited the seed and did not update the manifest.
  That is the check working: a seed whose bytes nobody recorded is not reviewed.
* **DDL** — you want a migration, not a seed. Put it in
  `projects/<slug>/migrations/templates/` and `freeze-lock` it; then `apg dev
  reset` applies it as the migration user, which is the whole loop this command
  exists for.

### A migration fails as the migration user

**This is the case the environment exists to surface.** The migration user is
not a superuser and is not the object owner; on the deployment it is the role
dbmate connects as, and a statement it cannot execute is a deploy that stops at
step 6 after the containers are up. Finding that here costs ten seconds.

Read the error, fix the migration, `freeze-lock` again, `apg dev reset`. If you
want to see the privilege the statement needs, `apg dev psql --as
migration-user` puts you in exactly that role.

### The environment is running but `psql` shows no rows

Almost always row-level security doing its job. `apg dev psql` asserts the
development subject; rows written by anything else, or written before the
subject existed, belong to nobody it can see. `--as migration-user` will show
you what is actually there.

---

## 7. Where the rules are

| | |
|---|---|
| The decision | [ADR 0203](decisions/0203-the-local-environment-is-the-database-built-from-the-render-and-the-release.md) |
| The command | `bin/dev.sh`, `bin/dev.py` |
| The logic, with no daemon in it | `src/agentic_postgres/dev_environment.py` |
| What it tells docker | `tests/contract/test_dev_environment.py` |
| What the cluster then is | `tests/contract/test_dev_environment_cluster.py` |
| The requirements | `DEV-ENV-001`, `DEV-SUBJECT-001`, `DEV-SEED-001`, `DEV-ISO-001`, `DEV-CHURN-001`, `DEV-CI-001` |
