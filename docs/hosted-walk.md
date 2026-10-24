# The hosted walk

`documented_path` asks whether **somebody who did not build this** gets through
the documented path. Since Session 46 the path is the hosted product's: the
public site, an invitation link and the console (ADR 0290). Nothing in a
repository can watch a person do that, so a person walks it, writes down what
happened, and the product reads the record. This page is the arrangement: who
walks, what they are sent, the statement they hold, how their notes become the
record, and what is done with it.

The appliance's own path — a clone of the release, the workstation, a migration
set — is a different walk with a different claim, `appliance_documented_path`,
arranged by [The second walk](second-walk.md) (ADR 0207).

## 1. Who walks, and what they hold

**One person, once, who did not build Stage 5.** Not the operator, not the
agent that executes the session, and not a driver: ADR 0207's rule that a claim
closed by its author's hands is not closed is kept word for word (ADR 0290 §6).
The operator recruits them (D2862).

They hold **three things and nothing else**:

- the site's address, `https://agenticpostgresql.com`;
- the statement in §2, copied verbatim between its markers;
- an **account invitation link**, which opens an account that belongs to no
  organisation yet.

They need a browser. A terminal is optional: the site documents a command-line
client, and a person who prefers it may use it. They need no repository, no
host, no credential of ours, and no conversation with anyone who built this —
**any exchange with the builders during the walk is a step a page did not give,
and is written down as one**.

## 2. The statement

Everything between the two markers is what the person receives, beside the
link. It is sent **verbatim** — nothing added, nothing explained, no follow-up.
The operator may reword it before it is sent; the markers, the site's address
and the goals stay.

<!-- walk-statement:begin -->
Thank you for trying Agentic Postgres. It is a hosted PostgreSQL service in an
invite-only beta. Its website is https://agenticpostgresql.com.

You will receive an invitation link in a separate email. It is personal: it
opens one account, it works once, and it expires after 72 hours. Do not share
it, and do not copy it into your notes.

**What to try, using only what the website and the pages it leads you to tell
you.** Go as far as you can, in this order:

1. Start from the invitation link and end with a database of your own that you
   can connect to: find its connection details, and connect with any PostgreSQL
   client you already use. If you have none, the website's own way of running
   SQL in your browser counts.
2. Run a few statements of your own against it: create a table, put a few rows
   in it, read them back.
3. Make a branch of your database as it was at an earlier moment, and find out
   which moments you could have chosen from.
4. Find out how much your database has used so far.
5. Find out which of your queries took the most time.
6. Find the support information the service keeps about your database, the
   page you would send to someone helping you.

**The one rule that matters more than finishing:** whenever you had to work
something out that no page told you — a step you guessed, a button you had to
hunt for, an error that did not say what to do next, a question you wanted to
ask somebody — **write it down**, even if you got past it a moment later. Those
notes are the most useful thing you can give us. There is nobody to ask during
the walk; if you want to ask something, write the question down and decide for
yourself.

**Never write a secret into your notes**: no password, no invitation link, no
code from an authenticator app, no connection string, no token the service
shows you. Describe them instead ("I copied the token it showed me").

**Keep your notes as you go**, in plain text, in this form, and send them back
by replying to the email you received this in:

```
STARTED: <the time you opened the invitation link>
TIMES (write the time when you):
  had an account:
  had set up your second factor:
  had an organisation:
  had asked for a database:
  could connect:
STEPS, in order:
  - <what you did, and the page or screen that told you to>
NOT ON ANY PAGE:
  - <each thing you had to work out yourself, in your own words>
GOALS:
  1 connect:          reached at <time> / not reached: <why>
  2 your own SQL:     reached at <time> / not reached: <why>
  3 a branch:         reached at <time> / not reached: <why>
  4 usage:            reached at <time> / not reached: <why>
  5 slowest queries:  reached at <time> / not reached: <why>
  6 support page:     reached at <time> / not reached: <why>
COMMANDS (only if you used a terminal; leave out every secret value):
  - <each command, as you typed it>
FINISHED: <the time you stopped>
```

Stopping before the end is a useful result. Saying you finished when you did
not is the only useless one. You may be asked once, afterwards, to read your
notes typed up as a file and say whether they are yours.
<!-- walk-statement:end -->

## 3. The arrangement

**When.** On a day the operator agrees with the person, after the release the
site describes is deployed and the person's slot (`slot10-prod`) is prepared
alone, so their database lands on it (D2870). From the release's push until the
person confirms their record, **no commit changes anything the site is built
from** (ADR 0290 §7, D2883): the page they read is the page the gate rebuilds.

**What the operator sends** (Sheet P0, the session plan's appendix). The
operator, as the registry administrator, mints an account invitation with the
second factor on their own phone, and sends the link and §2's statement **by
their own email**. The agent that executes the session never sees the link.

**How the notes come back.** The person replies with their plain-text notes.
The operator hands the agent **the notes and nothing else** — if a secret is in
them, it is removed and the person told, before the agent reads them.

**Transcription and confirmation** (ADR 0290 §2–§3). The agent types the notes
into the record **verbatim** — the person's words in `undocumented_steps`, the
goals and their times as written, `transcribed_by` naming the agent. The person
reads the resulting JSON and says it is theirs; the time they say so is
`confirmed_by_walker_at`. Nothing reaches the gate before that, and nothing in
the record is reworded to make it pass.

**The record** is a JSON object with `path: "hosted"`, read by
`src/agentic_postgres/dx_record.py` — the site's digest the person read, the
routes they visited, the commands they typed (if any) checked against the
site's own code blocks, the goals, the timeline, the person's undocumented
steps, and the two hands: `followed_by` (`kind: "person"`) and
`transcribed_by`. It holds no secret; the reader refuses one. It lives in WSL,
0600, never committed.

**At most two walks per release.** The second is for a repair the first found:
a `site/`- or `docs/`-only change, then a **new** person, whose record names
its own `site_commit`. There is never a third — a third walk is a person being
coached through a path until it passes.

## 4. What the builder does with it

The record is an operator input, declared to the gate, never found
(ADR 0202):

```bash
bin/session-NN-check.sh --mode external --walk-record-file <path to the record>
```

`documented_path` reports one of three things (ADR 0163):

- **passed** — a confirmed record from a qualifying walk: the criterion reached
  (goal 1), the site digest the deployed build's, every route a built route,
  every command on the site, no file edited, no undocumented step.
- **failed** — an undocumented step, an unnamed command or a page that moved.
  **Reported as failed and never softened**: a step a page did not give is
  exactly what the walk exists to find.
- **not_run** — no record was declared, or it does not describe a qualifying
  walk (not a person, or not confirmed).

A goal after the first that was not reached, with its reason, is reported and
does not by itself fail the claim: *the person stopped* is not *a page was
wrong*.
