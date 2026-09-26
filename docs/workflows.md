# Workflows

Since `1.10.0`. A **workflow** is a reviewed file in your project that names a
few of your own capabilities in order. A **run** executes it, one step at a
time, as the agent that started it — holding nothing that agent does not hold,
and stopping the moment that agent stops being able to act.

That last sentence is the whole design, and everything below is a consequence
of it. There is no service account, no workflow role, no long-lived token and
no privilege the worker has and an agent does not (ADR 0226).

## A definition

A definition lives in your project's workflow directory, beside its
migrations — `projects/<slug>/workflows/<name>.yaml` — and it is a **project
artefact**: reviewed in the checkout, installed by the deploy, and immutable
once installed (ADR 0228). You fix one forward by publishing a new version.
You never edit an installed one.

```yaml
schema_version: 1
name: notes-roundtrip
version: 1
description: >-
  Creates a note, reads the five most recent notes back, and records a second
  note. The example project's end-to-end proof that a run does work.
timeout_seconds: 300

steps:
  - name: create_the_first_note
    capability: create_note@1.0.0
    arguments:
      p_title: workflow roundtrip, first note
      p_content: Written by the workflow worker as the agent that started the run.

  - name: read_the_notes_back
    capability: query_notes@1.0.0
    arguments:
      limit: 5

  - name: create_the_second_note
    capability: create_note@1.0.0
    arguments:
      p_title: workflow roundtrip, second note
      p_content: Written after the read, so the order of the run is visible in the rows.
```

`schemas/workflow.schema.json` is the contract. The parts worth knowing before
you write one:

- **A step names a capability, never a tool.** `create_note@1.0.0` is a
  capability of *your* lock; which tool serves it is the compiler's business,
  and it can change under you without your definition changing. A definition
  that named `call_function` would be naming something already decided.
- **The version is exact.** There is no `latest`, because a definition that
  asked for one would mean something different on Tuesday.
- **A relation read takes `columns`, `filters`, `order_by` and `limit`** — and
  not `resource`, which the compiler derives from the capability.
- **`name` on a step is `[a-z][a-z0-9_]*`**, narrower than the table allows, so
  that `{{steps.<name>.<field>}}` is unambiguous.
- At most **32 steps**; `timeout_seconds` 1–3600 for the run and 1–600 for a
  step; `retry.max` 0–5 with `backoff_seconds` 1–300.

### References

Two things can be substituted into an argument:

```yaml
    arguments:
      p_task_id: "{{input.task_id}}"          # from the run's input document
      p_content: "{{steps.read_the_notes_back.result}}"   # from an earlier step
```

A reference to a step that comes *later*, or to one that does not exist, is a
compile error and not a run-time surprise. A `{{` or `}}` that is not part of
a well-formed reference is refused outright — a marker the pattern did not
match is a typo, not a literal. **A whole-string reference yields the
referenced value with its type** — `"{{input.limit}}"` over `{"limit": 5}` is
the integer 5, not `"5"`. **A reference inside a longer string is interpolated
as its JSON rendering** (a string value as itself), because that is the only
thing a string can hold.

The second example project definition, `notes-retry.yaml`, exists to exercise
the retry path: it asks for a task transition whose expected status cannot
hold, which the plane names `write_conflict` and treats as retryable, so the
step parks and comes back.

## The six verbs

```bash
bin/workflow.sh init      --project project.example.yaml [--name NAME]
bin/workflow.sh validate  --project project.example.yaml [--file PATH]
bin/workflow.sh run       --definition NAME@VERSION --project-outputs FILE [--input JSON]
bin/workflow.sh dry-run   --definition NAME@VERSION --project-outputs FILE [--input JSON]
bin/workflow.sh status    --run RUN_ID --project-outputs FILE
bin/workflow.sh cancel    --run RUN_ID --project-outputs FILE
```

`init` prints a skeleton derived from your own lock — the first read capability
it serves and the first write that does not require approval — and writes no
file. `validate` compiles every definition in the directory against the lock
and exits 5 naming the file, the step and the reason. Those two need no
deployment.

The other four call a deployment, and they take the token from
`APG_AGENT_TOKEN` — never an argument, because a value in an argument vector is
a value `ps` can read.

**A run is started as the agent that token was minted for, and the agent's
stored scopes are what authorise it — not the token's.** An agent narrowed
since the token was issued is refused on the next step, not on the last one.

## A run's status

```bash
APG_AGENT_TOKEN=… bin/workflow.sh status --run "$RUN" --project-outputs outputs.json
```

The document is the run row and every step in order: `status`,
`stopped_reason`, `dry_run`, `input`, the four timestamps, and per step
`position`, `name`, `status`, `attempt`, `outcome`, `reason`, `request_id`,
`resume_after`, `result` and its own timestamps. It also carries
`lock_tools_sha256` — the digest `validate` compiled against — so you can see
whether your lock has moved since.

**Another agent's run is a 404, the same as a run that does not exist.**

### The words

A **run** is `queued`, `running`, `succeeded`, `failed`, `cancelled` or
`stopped`.

- **`failed`** — a step refused and the run is over.
- **`stopped`** — *the agent* stopped being able to act: revoked, expired, or
  narrowed out of a scope a later step needs. `stopped_reason` says which.
  These are two different operator actions, which is why they are two words:
  a `stopped` run is one you can fix by reauthorising an agent.
- **`cancelled`** — you asked, and the run stopped at its next step boundary.
  `cancel` is a request, not a kill: a step already in flight finishes.

A **step** is `queued`, `claimed`, `parked`, `succeeded` or `failed`.

- **`parked`** — the step failed retryably and will be attempted again after
  `resume_after`. Nothing is lost; nothing is running.
- **`replayed`** is a step *outcome* the worker never writes, and this is
  stated rather than left to be discovered. The idempotency key is per
  `(run, step)` and never per attempt, so a retried write is refused by the
  plane as a replay — but the plane's result for a first write and a replay are
  indistinguishable to the caller, so the loop does not guess. The word lives
  in the audit record, joined by request id.

## The worker

**A loop inside the `auth` process** (ADR 0226). Not a container, not a role,
not a secret, not a service. It starts with the process in `auth` mode, claims
one step at a time under a lease, mints a token for that step, makes exactly
one call to the agent plane, records the outcome, and asks again.

What that buys is the invariant at the top of this page: the one route that
mints an agent token takes the agent's secret, so a worker in its own container
would have needed some *other* way to become an agent — a shared secret with
`auth`, or a route that mints on demand — and that is a principal holding more
than the identity it acts for. A loop inside the signer needs neither.

What it costs is stated too: **a worker restart is an `auth` restart.** The
`worker-restart` rehearsal exercises exactly that, and reads the heartbeat's
holder before and after to prove the loop came back rather than never having
stopped.

### What a run may not do

- **It holds nothing the agent does not.** No scope, no capability, no tool and
  no row an agent calling the plane by hand could not reach.
- **It calls the plane.** Every step is an ordinary agent tool call, audited,
  scope-checked, budgeted and idempotency-claimed exactly like any other. There
  is no back door into the database, and the four substrate tables grant no
  privilege to any request role.
- **It takes no SQL, path or query.** A definition names capabilities and
  arguments from a closed vocabulary, the same one the tools take.
- **It does not outlive the agent's authority.** Revocation stops the run at
  its next step boundary — and a step already claimed is refused when its token
  is minted, not after the call.
- **It never hands a credential anywhere.** One token per step attempt, held
  for one call, discarded immediately.

## What is not here yet

| Not yet | Where |
|---|---|
| Approval gates — a step a human releases | Session 33 |
| Compensation — undoing the steps before a failure | Session 33 |
| A provenance reader over a run's audit rows | Session 33 |
| `wait` — a step that sleeps on purpose | Session 33 |
| Events — a run started by something other than a call | Session 34 |
| Outbound delivery and inbound connectors | Session 34 |

A run cannot branch, loop, fan out or call another run, and none of those is on
a list above. Workflows here are a short, reviewed sequence over your own
capabilities; a workflow language is a different product.

## On a deployment

`docs/operator-guide.md` §17 is the operator's half: the doctor's `workflow`
check, the rehearsal, the restore drill's member, and what to do when a run is
stopped, parked, or holding a lease nobody is behind.
