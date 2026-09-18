# New team member guide

Fourteen steps, **every one of them available now**, and **twelve of them
offline**. None requires editing a file this repository ships, and none needs
a credential or a provider. **One needs root and it is step 2**: two packages
come from `apt-get`. Nothing after it does, and if `sudo` is not yours to use,
step 2's note says how to get the same two tools without it.

**Two of the fourteen wait for your project's first deploy, and both wait on
the same file.** `projects/<slug>/contracts/postgrest-openapi.canonical.json`
is your surface as a running PostgREST serves it, and a checkout cannot serve
one — `apg dev` is the database alone (ADR 0203). So if you add a table of your
own at step 9, then step 11's *compile* and step 12's *generate* refuse with
exit 5 until you have deployed once and captured that snapshot. Each step says
so where you meet it, and step 11 carries the four-line order to follow. A
reader who adds no table of their own meets neither wall.

Every step on this page runs against the release you have. For fifteen
sessions some of them were labelled as belonging to a session still to come,
on steps that had already been built, deployed and measured; a reader who
followed it was told the product could not do things it had been doing for a
year (D1313). One label, and it is true of all fourteen.

This is source specification §1.4 transcribed into the CLI this repository
actually has, extended with what Stage 3 added: a table of your own, an agent
capability over it, a local database, a generated client and Studio.

The specification's positional form (`./deploy.sh project.yaml`) is not
accepted — see decision V in
[the implementation plan](plans/session-01-implementation-plan.md) — because it
cannot express the capability manifest or the mandatory render-only mode.

## Before you start

This repository requires POSIX filesystem semantics: `0600` output modes are a
tested contract and `flock` guards render publication. On Windows, work inside
WSL2 with the repository on the **Linux** filesystem — not under `/mnt/c`, and
not in a OneDrive-synced folder. Implementation plan §1 has the measurements.

---

### 1. Clone the repository — *available now*

```bash
git clone <repository-url> && cd agentic-postgres
```

### 2. Install the local toolchain — *available now*

```bash
sudo apt-get update && sudo apt-get install -y shellcheck jq
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
```

**This is the one step that needs root, and only for the first line.** `uv`
installs into `~/.local/bin` as you. If you cannot use `sudo`, `shellcheck` and
`jq` both ship single static binaries — put them anywhere on your `PATH` and
step 4 will confirm them by name, which is all anything here asks of them. If
they are already installed, this step is a no-op and you should skip it rather
than run it: nothing later distinguishes a package you installed from one that
was there.

### 3. Create the pinned environment — *available now*

```bash
uv venv --seed --python 3.12 .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.txt
```

`--seed` installs pip, which the hash-locked install needs. `--require-hashes`
means a tampered or substituted wheel fails rather than installs.

### 4. Confirm the workstation is ready — *available now*

```bash
bin/doctor.sh
```

Exits `3` and names anything missing. It prints tool versions and repository
paths only — never the environment, never a secret.

### 5. Verify you have the specification you think you have — *available now*

```bash
(cd docs && sha256sum -c source-specification.sha256)
```

**The `cd` is load-bearing** and it is the one command on this page that is not
run from the repository root. The checksum file names `source-specification.md`
with no directory, because that is what `sha256sum` wrote when it was made
beside the file it digests — so run from the root it looks for
`./source-specification.md`, does not find it, and reports *No such file or
directory* with exit 1. The subshell keeps your shell where it was.

### 6. Read the contract — *available now*

[Product contract](product-contract.md), then
[the three founding ADRs](decisions/README.md). The requirement catalog and the
numeric bounds table are generated; the prose around them is not.

### 7. Copy and edit the manifests — *available now*

```bash
cp project.example.yaml project.yaml
cp capabilities.example.yaml capabilities.yaml
```

Set the slug, environment, and domain in `project.yaml`.

**`capabilities.yaml` is the reviewed release set and you keep it as copied.**
It is not empty — it carries the release's capabilities, enabled, and step 8
will print `Capabilities 7 enabled` from it. (Empty was the correct state
through Session 7 only; `capabilities.example.yaml`'s own header says so.) This
file is the RELEASE's surface; the capability over a table of your own is a
different file in a different place, and step 11 is where you write it.

**Two keys in the copied `project.yaml` point at the example project, and both
must move.** `mcp.capabilities` and `migrations.set` are each
`projects/example` in the file you just copied:

- **`migrations.set`** — delete it now. Left as copied it renders *another
  project's* migration set into yours, and step 9's `freeze-lock` freezes
  `projects/example` while appearing to work. You put it back at step 9,
  pointing at your own directory.
- **`mcp.capabilities`** — delete it now and put it back at step 11. The
example manifest you just copied carries it, and it names a file that does not
exist yet in your project — the manifest loader refuses that, so the first
`freeze-lock` at step 9 would be refused before it read a single migration. The
key is added back once `bin/agent.sh init --head` has written
`projects/<slug>/capabilities.yaml`. The order is: a migration set first, then
the capability over it, which is also the order the two steps appear in below.

**Neither file may ever contain a secret.** The loader rejects secret-bearing
keys at any depth.

### 8. Render — *available now*

```bash
./deploy.sh --project project.yaml --capabilities capabilities.yaml --render-only
```

`--render-only` is mandatory and it does not partially deploy: it needs no host,
no root and no provider, and it contacts nobody. It does need Docker, because it
validates the staged Compose model before publishing it.

Then look at what it wrote:

```bash
jq . .generated/<project-key>/outputs.json
cat  .generated/<project-key>/rendered-summary.txt
bin/compose.sh .generated/<project-key> --profile contract config
bin/compose.sh .generated/<project-key> ps --quiet     # empty
```

**A project's own migrations render to their own directory.** The release's
set lands in `.generated/<project-key>/migrations/` and yours in
`.generated/<project-key>/migrations-project/` — a separate ordering space, so
that a set of yours can never interleave with a released migration (ADR 0206).
If you look for your migration under the first directory after step 9 you will
not find it, and nothing has gone wrong.

Database endpoints read `"status": "unavailable"` with null host, port, URL and
secret reference. That is correct rather than incomplete — there is no tunnel
host or bound port yet, and a placeholder that looked like a DSN would
eventually be pasted into a connection dialog. Always reach Compose through the
wrapper: calling `docker compose` directly lets inherited shell variables
override the generated identity and the locked digests.

### 9. Add a table of your own — *available now*

Everything you add lives under `projects/<slug>/` and you edit none of the
release's files (ADR 0198). Write the migration, declare it, and freeze:

```bash
mkdir -p projects/<slug>/migrations/templates
# projects/<slug>/migrations/templates/0001-<name>.sql
#   your table with FORCE ROW LEVEL SECURITY and its owner-scoped policy, its
#   `api` view, its SECURITY DEFINER write function, and a `-- migrate:down`
#   block that raises AP900
# projects/<slug>/migrations/manifest.json
#   the entry: version, name, template, placeholders
# projects/<slug>/contracts/postgrest-api-surface.yaml
#   your reviewed surface: the view and the function you just published, at
#   api-surface schema 2. `projects/example/contracts/` is the worked one.
```

**Point your manifest at the directory before you freeze**, at schema version
6 — this is the `migrations.set` key you removed at step 7:

```yaml
schema_version: 6
migrations:
  set: projects/<slug>
```

**Then, and not before:**

```bash
bin/migrate.sh --project project.yaml freeze-lock
```

The order is the whole point. `freeze-lock` freezes the set the manifest names
at the moment it runs, so freezing first freezes whatever the copied manifest
still pointed at — silently, and with a lock that looks correct.

**Write the reviewed surface now too, in the same step.** It is listed in the
block above because it belongs to the table rather than to the agent:
`projects/<slug>/contracts/postgrest-api-surface.yaml` is what publishes your
view and your function to every later comparison, and step 11's
`bin/agent.sh init` reads it. Without it that command refuses with exit `2` and
*the merged reviewed surface names no operation* — which is a step you have not
done yet rather than a mistake you made.

`projects/example/` is a worked set — a pgvector column beside each note, a
`security_invoker` view and one write function — and reading it first is
cheaper than meeting the refusals.

Two of those refusals are the ones to know about. Your versions must sort
**after** the release lock's newest at the moment you freeze, and `freeze-lock`
records that version in your own lock; a table in `app` without FORCE row
level security is refused before a byte of it is rendered, because FORCE is
what makes the row policies apply to the table's owner and every write function
this product publishes is SECURITY DEFINER running as that owner. Both are exit
`5` from `freeze-lock`, both name the migration, and both are in the table at
the end of this page.

One thing here is **not** offline and it is the only one on this page: the
OpenAPI snapshot at `projects/<slug>/contracts/postgrest-openapi.canonical.json`
is captured from a running deployment and refuses a hand edit, so the contract
check stays red until your first deploy. That is expected rather than a mistake
you made — [Adding your own tables](../README.md#adding-your-own-tables) has
the capture command.

### 10. Build a local database — *available now*

```bash
bin/apg.sh dev up --project project.yaml
bin/apg.sh dev psql --project project.yaml
```

About ten seconds, and it is the first thing in this guide that gives you
something to type SQL at. It builds a disposable PostgreSQL cluster from what
you just rendered: the locked image, the deploy's own bootstrap, and every
migration applied **as the migration user** — the release's and **the set you
wrote in the step before**, in manifest order, each in its own transaction. The
migration user is the role that will apply them on a deployment, so a migration
of yours that fails here fails in ten seconds rather than in a convergence.

`psql` puts you in the application role with a development
subject asserted, so what you see is what that subject sees under row-level
security.

`bin/apg.sh dev down --project project.yaml` removes the container, its volume
and its state; `reset` does both. Nothing here is durable, nothing is backed up,
and nothing reaches a provider — see [the developer loop](dev-environment.md).

It needs Docker, which step 2 installed and step 4 confirmed.

### 11. Give an agent your table — *the manifest now, the compile after your first deploy*

An agent reaches your relations through a capability manifest you own, beside
your migration set, and through nothing else (ADR 0201). **The first two
commands run here; the last three do not, and the reason is a file only a
deployment can produce** — see the note under this block before you run them:

```bash
bin/agent.sh init --head > projects/<slug>/capabilities.yaml
bin/agent.sh init --project project.yaml --operation <your view> \
  >> projects/<slug>/capabilities.yaml
bin/mcp-contract.sh compile --project project.yaml \
  --output projects/<slug>/contracts/mcp-capabilities.canonical.json
bin/mcp-contract.sh check --project project.yaml
bin/render-evaluation-report.py --write --project project.yaml
```

**Where this stops, and why.** `bin/agent.sh init` runs here and writes you a
correct manifest. The three commands after it — `compile`, `check` and the
report — each refuse with exit 5:

> `projects/<slug> has no approved snapshot at
> contracts/postgrest-openapi.canonical.json. It is captured from the project's
> deployment with bin/api-contract.sh --update ...`

That snapshot is the surface **as a running PostgREST serves it**, and there is
no way to produce it in a checkout: `apg dev` is the database alone and stands
up no PostgREST (ADR 0203, and D1211 in the ledger records the cost of changing
that). So a capability over your own view is *declared* on your machine and
*compiled* after your project's first deploy, in this order:

1. here: `bin/agent.sh init` writes `projects/<slug>/capabilities.yaml`, and you
   commit it;
2. deploy the project once — a host, a domain, certificates and providers,
   which is [Operating a deployment](operator-guide.md) §3, not this page;
3. `bin/api-contract.sh --update --project project.yaml --project-outputs
   <the deployed outputs.json>`, review the captured snapshot and commit it;
4. then the three commands above, and step 12's `generate`, all run offline
   from then on.

Nothing is lost by the wait — the deploy does not need the capability, and the
agent plane serves the release's six tools until your own is compiled into the
lock. **If you are following this guide to the end without a deployment, stop
at `bin/agent.sh init` and read step 13.**

**If you ran the compile line anyway, delete the file it left behind.** The
redirect is the shell's, not the command's: `>` creates and truncates the
target before `compile` runs, so a compile that refuses still leaves a 0-byte
`mcp-capabilities.canonical.json` in your contracts directory. Every command
that reads it will tell you it is empty and say to delete it (exit `5`), and
the gate at step 14 would otherwise ask you to commit an empty contract:

```bash
rm -f projects/<slug>/contracts/mcp-capabilities.canonical.json
```

**A fourth command waits on the same file**, and it is the one below rather
than one of the three named above:

```bash
bin/render-mcp-catalog.py --write --project project.yaml
```

It renders your tools a page of their own from the compiled contract, so it
runs when `compile` does and not before — after your first deploy, with the
other three.

`init` scaffolds **one entry** from your reviewed surface and writes no file, so
you read what it wrote before it becomes a file. An operation your surface does
not publish is refused with the ones it does; so is one the release already
serves, and the refusal says which of the two it is. Point your manifest at the
directory, at schema version 6:

```yaml
schema_version: 6
migrations:
  set: projects/<slug>
mcp:
  capabilities: projects/<slug>
```

`check --project` is the approval: it compares your manifest against your
reviewed surface and your snapshot, and refuses a drift with exit `5`. The last
two lines write the two documents that describe what you just declared — the
evaluation report beside your contract, and your own tool catalog at
`projects/<slug>/docs/mcp-tool-catalog.md`, which says in its first lines that
these are your tools and not the whole of what a deployment serves.

**The SQL grant is yours and nothing above it can see one.** A tool over your
view is served the moment the lock carries it and refused by the database until
your own set grants `SELECT` on the view to `{{agent_reader}}` and
`{{agent_writer}}`, and `EXECUTE` on the write function to `{{agent_writer}}`.
That is a second migration, because the first is frozen; fix forward, never an
amendment. `projects/example/migrations/templates/0002-agent-grants.sql` is the
worked example.

### 12. Generate a client — *after your first deploy, if you added a table*

```bash
bin/apg.sh generate --project project.yaml
```

A third of a second, and it writes a typed TypeScript package over the
surface your project publishes — including the view and the write function you
added in step 9, and the tool you declared in step 11: one method per published
object, one per agent tool, and the digests that say which surface and which
lock they came from.

**It reads four committed artefacts and nothing live — but one of the four is
`projects/<slug>/contracts/postgrest-openapi.canonical.json`, and only a
deployment can produce it.** So this command works today for a project with no
migration set of its own, over the release's surface alone, and refuses with
exit 5 for a project that HAS one until that project has been deployed once and
its snapshot captured. If you followed step 9 you have one, and this step waits.
The note under step 11 is the same wall and says what to do about it.

You cannot *call* anything with it yet — there is no REST service until a
deploy — and that is worth seeing rather than reading about: `init()` is the
first thing a caller runs, and against nothing it answers `unreachable`
rather than pretending the contract is stale. Read the generated `README.md`
and [generated clients](generated-clients.md).

### 13. Read Studio — *available now*

```bash
bin/apg.sh studio --help
```

Studio is a loopback page over a **deployment**, and you do not have one — so
this is the step where you read what it does rather than open it (ADR 0205).
`--help` exits `0` and describes it: one standard-library process bound to
`127.0.0.1`, holding your access token in memory, serving three first-party
files and a same-origin forwarder with an enumerated table of the requests it
may make. There is no SQL box, not hidden and not behind a flag.

Point it at the document you rendered in step 8 and it refuses, on purpose:

```bash
bin/apg.sh studio --project project.yaml \
  --outputs .generated/<project-key>/outputs.json
```

```
studio: that is a rendered document; the REST route is an observation, and a
render has made none. Deploy the project, then pass --outputs the outputs.json
that deploy published (ADR 0158). Until then `studio --help` is what there is
to read.
```

Exit `2`. A render says what was asked for and a route is an observation of
what happened, so a rendered document has no address to open. That refusal is
the same shape as `init()`'s `unreachable` in the step before, and it is worth
meeting once: a clear sentence naming what is missing is this product working,
not failing. [Studio](studio.md) is the longer form.

### 14. Run the gate — *available now*

The gate refuses a tree with untracked or uncommitted changes, so everything
you wrote under `projects/<slug>/` is committed first — that is what "your
project directory tracked" means in the criterion below:

```bash
git add projects/<slug>
git commit -m "<slug>: a project's own migration set, surface and capability"
bin/session-01-check.sh
```

**A clone you have just made may have no committer configured**, and `git
commit` then stops with *Author identity unknown*. Set one for this repository
rather than globally:

```bash
git config user.name  "Your Name"
git config user.email "you@example.com"
```

CI runs this exact script; there is no second, divergent definition of
"passing".

---

## What "done" looks like

**Steps 1–14 complete, `bin/apg.sh dx-record check` reports none, none and
none, and the gate exits 0 on your clean tree with your project directory
tracked.** That sentence is the success criterion, and it is what a walk's
record means when it says `reached_success_criterion: true` (ADR 0207 §4).

The record is the walk's own artefact rather than something every reader owes:
if you are following this page as [a second walk](second-walk.md) you keep one
as you go and `dx-record digest`, then `check`, are your last two commands. If
you are not, the first clause of that sentence and the last are your whole
criterion.

Concretely, you have:

- a rendered project, byte-identical across renders with identical inputs;
- **a table of your own** under `projects/<slug>/`, frozen into your own lock,
  with none of the release's files edited;
- **an agent capability over it**, compiled, checked and catalogued;
- **a local database** with that set applied by the role that will apply it on
  a deployment;
- **a generated client** over the surface you extended, whose `init()` answers
  `unreachable` against nothing rather than pretending the contract is stale;
- **Studio read**, and its refusal against a render recorded;
- **the gate green**, the same script CI runs.

You do not have a deployment, and nothing on this page needs one. A deployment
is a host, a domain, certificates and providers, and it is
[Operating a deployment](operator-guide.md) rather than this page: its §3 is a
host from empty and a first project, in the order the commands impose, with
where each step was measured. When that deploy exists, three things on this
page that stopped come back: step 11's three commands and step 12's `generate`
run once the snapshot is captured (the operator guide's §6 step 4 is the
capture), and step 13's Studio opens against the deployed document (its §8).
Moving that deployment to a later release is
[Upgrading a deployment](upgrade-guide.md), whose §1 is the half you do here,
in the checkout, before any host is touched.

## If something fails

| Symptom | Cause | Fix |
|---|---|---|
| `bad interpreter: /usr/bin/env bash^M` | Cloned on Windows without `.gitattributes` honoured | `git config core.autocrlf false && git checkout -- .` |
| `python resolves to a Windows interpreter` | WSL inherited the Windows `PATH` | `source .venv/bin/activate` |
| `chmod 600` reports `666` | Repository is on NTFS or a `/mnt/c` mount | Move it to the Linux filesystem |
| `lock-versions: BLOCKED` | A digest will not resolve for the target platform | Do not substitute a tag; change the candidate deliberately |
| Gate fails on a clean checkout | Generated documentation drifted | `python bin/render-acceptance-matrix.py --write` |
| `freeze-lock` exit **5**: *these project migrations do not sort after the release version this set was frozen against (…)* | A migration of yours is stamped at or below the release version your set was frozen against. dbmate applies one directory in filename order, so the same set would produce two schemas — refused on a deployed cluster, applied silently on a fresh one | Re-stamp the migration with a version later than the release's newest, and freeze again |
| `freeze-lock` exit **5**: *… creates a table in app without FORCE ROW LEVEL SECURITY: app.&lt;name&gt; (ENABLE without FORCE)* | `ENABLE` alone does not apply the policies to the table's **owner**, and every write function here is SECURITY DEFINER running as that owner | Add `ALTER TABLE app.<name> FORCE ROW LEVEL SECURITY;` to the migration and freeze again |
| `agent init` exit **2**: *the merged reviewed surface names no operation '…'. It names: …* | The capability names something your reviewed surface does not publish. An object the surface does not publish cannot be given to an agent (ADR 0050) | Publish it in `projects/<slug>/contracts/postgrest-api-surface.yaml` first, or pick one of the names the refusal lists |
| `deploy.sh --render-only` exit **5**: *the previous valid render, if any, is unchanged* | Your set was refused before anything was published — the lock, the ordering or the lint | Read the line above it: it names the migration and what is wrong with it |

Each of the last four sentences is quoted from a run of the command, not from
its source.
