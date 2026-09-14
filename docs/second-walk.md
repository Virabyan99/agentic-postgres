# The second walk

`DX-001` says *a developer who did not build the primitive completes the
documented path without source edits or undocumented commands*. Nothing in a
repository can watch that happen, so somebody walks it and writes down what
they did, and the product reads the record. This page is that arrangement: who
may walk, the statement they are handed, the record they write, and what is
done with it.

It was answered **no** once, on 2026-09-10, over seven files a reader had to
edit inside the release (ADR 0197). Stage 3 removed the cause — a project owns
a directory (ADR 0198), a capability manifest (ADR 0201) and its own migration
ordering space (ADR 0206) — so the claim is walkable again, and this is how it
is walked.

## 1. What a walk is, and who may walk one

A walk is one reader, once, with **nothing in their head but a clone of the
release and the task statement below**. Everything they know about this product
they read on the way. Everything they do, they write down as they do it.

The reader is a session of a model, and that is a decision rather than a
convenience (ADR 0207 §1). A person who has never seen this repository is not
available to this project: the operator has sat every session, and the session
that edited the documentation cannot then measure it — a claim closed by its
author's hands is not closed. So a walker qualifies on what its context holds,
and each of these is checkable rather than asserted:

- **a `git clone` of the release commit**, made inside WSL so file modes
  survive, in a directory that is not the one sessions are launched from — so
  no project instructions are loaded;
- **an empty memory, no transcript, no prior conversation**;
- **`docs/plans/` is not read.** ADRs and every other page are documentation an
  adopter may read; the plans are the builder's notebook, and reading them is
  reading the answers;
- **no conversation with the builder during the walk.** Any exchange at all is
  an `undocumented_steps` entry by rule, which is what makes the rule
  self-enforcing rather than a promise.

**The residual, named rather than buried.** An agent reads faster and skips
less than a person. A clean walk is evidence that the path holds for a reader
who follows it — not that it is pleasant, and not that a distracted human on a
Friday would get through it. A person's walk would be a second and stronger
record, and nothing here makes one unnecessary. This makes the claim answerable
by somebody, which is the alternative to leaving it unanswerable by anybody.

**At most two walks per release** (the session plan's §9). The second is for a
repair the first found, and it is walked by a *new* session after a
documentation-only change. There is never a third: a third walk is a session
being coached through a path until it passes.

## 2. The task statement

Everything between the two markers below is the whole prompt of the walking
session. It is copied **verbatim** — nothing added, nothing explained, no
follow-up.

<!-- task-statement:begin -->
You have a clone of a product called Agentic Postgres at `~/walk/agentic-postgres`.
It is a release: the commit is the one its version names, and the working tree
is clean. Read it and follow it.

The machine is yours, not the product's. You are inside WSL2 on Linux, with
Docker, `git`, `curl` and a shell; if you are driving it from Windows, every
command goes through `wsl bash -lc "cd ~/walk/agentic-postgres && ..."`. Nothing
you do reaches any other machine.

**What to accomplish, using only what the repository's own documentation tells
you:**

1. Get the workstation ready and render the example project.
2. Add a table of your own choosing — one table, with one view over it and one
   write function — as a migration set that belongs to a project you name.
3. Declare an agent capability over that view, and follow the documentation
   to wherever it tells you the declaration stops.
4. Build a local database and see your migration set applied to it.
5. Generate a typed client, and follow the documentation to wherever it tells
   you that stops for a project shaped like yours.
6. Read what Studio is and what it needs. You have no deployment, so you will
   not open it; find out what it says when you point it at what you do have,
   and write that sentence down.
7. Get the repository's own gate to exit 0 on a clean tree with your project
   directory tracked.

**The rules of the walk, and they matter more than finishing:**

- **Do not read `docs/plans/`.** Every other page, including the architecture
  decisions, is documentation you may read. The plans are the builder's
  notebook.
- **Ask nobody anything.** There is no one to ask. If you find yourself wanting
  to, write the question down as an undocumented step and decide for yourself.
- **Nothing needs `sudo`, a host, a credential or a provider.** If a step looks
  like it needs one, that is a finding: write it down, skip the step, and carry
  on.
- **Two steps do wait for a deploy, and the documentation says which.** You have
  no deployment and will not get one. Where a page tells you a step needs one,
  reaching that sentence, recording it, and carrying on IS completing the step —
  it is not a finding and it is not a block. Where a page tells you a step runs
  now and it does not, that IS a finding, and it is the most valuable thing you
  can write down.
- **Do not edit any file the repository ships.** Copying an example to a name
  the repository ignores, and editing the copy, is expected. Editing a tracked
  file is the thing this walk exists to detect.

**Keep a record as you go**, at `~/walk/dx-record.json`. Write to it while you
work rather than reconstructing it at the end — a reconstructed record is a
memory of a walk, not a measurement of one. It is a JSON object with these
members:

```json
{
  "followed_by": {
    "kind": "agent",
    "identity": "<the model you are>",
    "instructed_by": "<who started this session>",
    "context": "<one sentence: what this session was given>"
  },
  "completed_at": "<ISO 8601 UTC, when you finished>",
  "release": "<the full commit sha of the clone>",
  "project_slug": "<the slug you chose for your project>",
  "commands_run": ["<every command you ran, in order, as you typed it>"],
  "files_edited": ["<every file you created or changed, repository-relative>"],
  "documents_read": {},
  "undocumented_steps": ["<every step the documentation did not give you>"],
  "reached_success_criterion": true
}
```

`documents_read` is filled in for you by the command below; leave it as an empty
object.

An **undocumented step** is anything you had to work out rather than read: a
command no page names, an argument you guessed, an ordering you inferred, a
question you wanted to ask, an error whose remedy was not written down. Record
it even when you got past it. These entries are the point of the walk — a clean
record with a real one in it is worth more than a clean record with none.

**The last two commands of the walk, in this order:**

```bash
bin/apg.sh dx-record digest --record ~/walk/dx-record.json
bin/apg.sh dx-record check  --record ~/walk/dx-record.json
```

`digest` fills in `documents_read`. `check` prints what the record says and a
verdict; read it, and do not edit the record to make it happier. If it reports
findings, they are the documentation's, not yours.

**Set `reached_success_criterion` honestly.** It is true only if all seven
goals above are done — a goal whose documented answer is *this waits for a
deploy* counts as done when you have found that sentence and recorded it —
`check` reports no findings, and the gate exits 0 on a clean tree with your
project directory tracked. If it is false, add a
`"blocked_by"` member: one sentence naming the step you stopped at and what
refused you. A walk that stops is a useful result; a walk that says it finished
when it did not is the only useless one.
<!-- task-statement:end -->

## 3. The record

Nine members, all required. The reader that decides the claim is
`src/agentic_postgres/dx_record.py`, and `bin/apg.sh dx-record check` is the
same reader with a report around it — the walker sees exactly the verdict the
sweep will reach, which is the point of shipping it as a verb (ADR 0207 §3).

| Member | What it answers |
|---|---|
| `followed_by` | Whether the walk counts. An object, never a sentence — see below |
| `completed_at` | When the walk ended, ISO 8601 |
| `release` | The commit walked. A walk measures a document at a commit |
| `project_slug` | The walker's own project. It is what makes `projects/<slug>/` tellable from the release's files, and it is validated before it becomes a path prefix |
| `commands_run` | Every command, in order, as typed. Compared against the commands the documentation names |
| `files_edited` | Every file created or changed, repository-relative. Compared **by path**: anything under `projects/<slug>/` is the walker's own, and so are the five operator inputs at the checkout root. Anything else is a source edit |
| `documents_read` | `{path: sha256}`, written by `dx-record digest`. A document that moved after the walk means the record measures a page that no longer exists |
| `undocumented_steps` | Everything the documentation did not give. A non-empty list is a finding, and the claim does not pass with one |
| `reached_success_criterion` | The walker's own verdict, and `blocked_by` beside it when it is false |

`followed_by` is structured because it is the member that decides whether the
walk counts, and a free-text answer to that cannot be read by anything:

```json
"followed_by": {
  "kind": "agent",
  "identity": "the model id, or the person's name",
  "instructed_by": "the human who started the session",
  "context": "one sentence: what the session was given"
}
```

`kind` is `agent` or `person`. `context` is asserted to **name the clone and
the statement** rather than merely to exist — "a fresh session" is a sentence
that is also true of a session holding the whole plan directory.

`blocked_by` is optional and is read only when `reached_success_criterion` is
not true, in which case it is required: a failed walk that does not say where
it stopped tells the builder the path is broken and nothing about where, which
spends the second walk on a search instead of a repair.

`dx-record check` prints five readings and two lines out of the record itself,
and exits 0 only when all five are clean: **source edits**, **commands the
documentation does not name**, **documents that moved after the walk**,
**`followed_by`** and **`blocked_by`** — then the documents the walk did not
record reading, and the undocumented steps the walker recorded. `digest` is run
first, in the walk's own clone, or the third reading is answering about pages
the record never named.

## 4. What the builder does with it

The record is an operator input, declared to the sweep rather than found
(ADR 0197, ADR 0202):

```bash
APG_DX_RECORD_FILE=<path to the record> bin/session-NN-check.sh --mode host
```

The live proof reads it through the same four functions the verb does — that is
asserted against the source rather than assumed, because two readings written
on the same afternoon drift apart afterwards. Three readings decide the claim:
**no source edit**, **no command the documentation does not name**, and **no
undocumented step**; the `followed_by` shape decides whether the walk counted at
all, and a document that moved since the walk means the record is about an
earlier release.

`documented_path` reports one of three things (ADR 0163):

- **passed** — a clean record from a qualifying walk.
- **failed** — a walk that hit a source edit, an undocumented command or an
  undocumented step. **This is reported as failed and never softened.** The
  claim exists to detect exactly this, and a documentation defect found by a
  walk is the cheapest one this project ever buys.
- **not_run** — no record was declared, or the record does not describe a
  qualifying walk.

A failed walk is followed by a **documentation-only** repair and, if the
operator chooses, one more walk by a **new** session. Never a third (§9).
Opening Studio against a real deployment stays an optional operator step, taken
only if the walker's project is deployed; the record then gains a `studio`
member and the claim is unchanged either way, because the path an adopter walks
alone ends where a host begins (ADR 0207 §4).
