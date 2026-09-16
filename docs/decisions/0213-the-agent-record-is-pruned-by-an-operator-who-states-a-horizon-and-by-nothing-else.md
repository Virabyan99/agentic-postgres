# 0213 — The agent record is pruned by an operator who states a horizon, and by nothing else

- **Status:** Accepted
- **Date:** 2026-09-17
- **Session:** 28, Run 6 (D1457–D1462)
- **Affects:** migration `20260917120033` (`agent_record_retention`), the only
  schema this session moves. `bin/doctor.sh --project <key>` gains an eleventh
  check. No requirement id moves; the new claim is registered in Run 9.
- **Related:** ADR 0135 (the audit record is written by a definer function as
  the caller, and names retention in its consequences), ADR 0142 (the record has
  one reader and it is a definer function; *"retention is still decided by
  nobody"*), ADR 0180 (the windowed quota, which solved its own growth by
  keeping one row per agent), ADR 0181 (the idempotency claim, which names
  retention in its consequences and leaves it), ADR 0175 (released arity), ADR
  0195 (three outcomes, the third reported), D940 (a migration over a table with
  history is proved against a cluster with history), D1255 (the open row this
  ADR closes), D1441 (a threshold invented in the command that runs as root on
  production could fail a host that works).

## Context

**Three released migrations state this problem and none of them decided
anything.** 0020: *"What is NOT here: retention. Nothing prunes
`app_private.agent_audit`, exactly as nothing prunes secret generations. Naming
it in ADR 0135's consequences did not make it decided, and a reader is not the
place to decide it."* 0032 repeats the paragraph verbatim, one column later.
0028 solved its own case — the quota table keeps one row per agent, so
*"retention stops being a question rather than being answered"* — and wrote
down in the same breath that the answer does not generalise. ADR 0135, ADR 0142
and ADR 0181 each name retention in their **Consequences** and each leave it to
the next run. `docs/scope-closure.md` has carried the row since Session 24 under
one sentence: *"Nothing prunes either. The decision is a released migration
carrying a policy."*

The one thing every previous run agreed on is that the decision is not an
implementation detail, because the thing being deleted is **evidence**. ADR 0135
exists so that an agent's actions are attributable after the fact; a migration
that silently deletes attribution on a schedule nobody chose destroys the
property the whole plane was built to have.

### What rig 28b measured, before a line of the migration was written

A cluster carrying every released migration and the example project's set,
built by the product's own bootstrap statements and applied as `migration_user`
over TCP — dbmate's route — with history seeded in both tables across the shapes
the plane actually writes: a served call, a refused call carrying
`denial_reason`, a claimed idempotency key, and the historical refused row the
audit-plane fixture has seeded since D940.

1. **Nothing reachable can delete a row today.** The ACL on both
   `app_private.agent_audit` and `app_private.agent_idempotency` is the object
   owner's and nobody else's, and a `DELETE` attempted by `SET ROLE` into
   `auth_service`, `agent_writer`, `agent_reader` and `authenticated` is refused
   with *permission denied for table* in all four.
2. **Neither table carries a foreign key.** The only one among the three agent
   tables is `agent_quota.agent_id`, `ON DELETE CASCADE` to `agents` — 0028's
   own design. Nothing in the schema depends on an audit row existing.
3. **Both prunes are sequential scans.** 0019's two indexes are `(owner_id,
   started_at DESC)` and `(agent_id, started_at DESC)`, built for the reader and
   neither leading with the timestamp; `agent_idempotency` has only its primary
   key. `EXPLAIN` on a time-bounded `DELETE` over either is a `Seq Scan`.
4. **Pruning an idempotency claim re-arms its key, silently.** With the control
   in the same run: a write replayed while its claim is present is deduplicated
   and `app.notes` stays at one row; the same write replayed after the claim is
   deleted **writes a second row and reports success**. No error on either side,
   nothing a caller or an operator could read. At-most-once becomes at-least-once
   for every key past the horizon — the exact failure 0029 was written to
   prevent.
5. **There is no safe subset of that table.** The obvious candidate — prune the
   claims of agents that are no longer active — does not survive its own
   measurement: `auth_rotate_agent_secret` (0025) clears a revocation and returns
   the **same** agent id to `active`, so a revoked agent's keys are dormant
   rather than dead. No predicate over `agent_idempotency` means *this claim can
   never be replayed*.

Measurement 4 is the finding that shapes this ADR. Two rows in
`scope-closure.md` and one sentence in `CLAUDE.md` §9 treat these tables as one
question — *"`agent_audit` and `agent_idempotency` grow without bound. Nothing
prunes either"* — and they are not one question. One is a record of the past;
the other is a promise about the future.

## Decision

**Retention is an act an operator performs, on a horizon the operator states,
with the counts in front of them. Nothing in this product deletes an agent
record on its own.**

Concretely, migration `20260917120033` adds three functions in `app_private`
and no scheduled anything:

| | What it does | Granted to |
|---|---|---|
| `agent_audit_prune(p_before timestamptz, p_limit integer DEFAULT NULL)` | deletes audit rows with `started_at < p_before`, returns how many | **nobody** |
| `agent_idempotency_prune(p_before timestamptz, p_limit integer DEFAULT NULL)` | deletes claims with `created_at < p_before`, returns how many | **nobody** |
| `agent_record_size()` | four numbers: the two counts and the two oldest timestamps | `auth_service` |

**The grant is to nobody, and measurement 1 is why that costs nothing.** Today
no reachable identity can delete a row from either table; after this migration no
reachable identity can delete a row from either table. The posture is preserved
rather than narrowed. The only candidate grantee was `auth_service`, the audit
record's one reader (ADR 0142) — and granting a delete authority to an identity
that is reachable over HTTP is exactly what 0020 refused when it declined to put
a `DELETE` path in the reader, and is not made acceptable by the delete being one
function further away. What can reach these functions is the object owner and a
superuser: the hand that already holds `docker exec … psql -U postgres` on the
host, which is a human at a TTY.

**`agent_record_size()` is granted to `auth_service` because it adds no
audience and no fact**: that identity already reads whole audit rows through
`auth_list_agent_audit`, so a count of the rows it can already page through tells
it nothing new. It is published into `app_private` and not into `api`, for 0020's
reason unchanged — the audit record is published to nobody, and an object in
`api` is an object the generated document can name.

**Both refusals are stated, not defensive decoration.** A `NULL` horizon
compared with `<` matches nothing, so without the guard the function returns 0
and an operator reads *there was nothing to prune* when what happened is *you
did not say from when* — D600 at the call site. A horizon in the future deletes
rows written between the moment the operator formed the intent and the moment the
statement ran, including calls still in flight. Both raise `PT422`, and neither
message carries a caller value.

**The idempotency prune ships with its consequence in its own comment**, in the
words an operator reads at the moment they are deciding: *every row this removes
re-arms its key*. It exists not because pruning that table is a good idea but
because an operator who has decided to accept the downgrade should be able to
perform it in one statement that says what it did, rather than by hand against a
table whose meaning is not obvious from its columns. Measurement 5 is why the
function takes a horizon and not a cleverer predicate: there is no safe one.

**The doctor gains an eleventh check, and it has no threshold.** `sudo
bin/doctor.sh --project <key>` reports the four numbers as a check whose three
outcomes are ADR 0195's: the reading, the reading, and *I could not read it*.
There is no `warn` at some row count, because **nobody has measured a row count
at which this deployment is unwell**, and a threshold invented in the one command
that runs as root on production could fail a host that works — which is D1441's
finding from Run 3 of this same session, arriving a second time. The check reads
the two **tables**, not the new functions, so it works unchanged against a
deployment that has not applied this migration yet: the pre-upgrade reading at
Session 29 is not disturbed by a checkout that is ahead of it.

**No index is added**, and `p_limit` is what bounds a prune instead. 0019 wrote
that its two indexes exist for one reader and neither is speculative; a third
would be paid on every write the plane makes, to buy a scan for an operation
performed by hand, rarely, at a moment the operator chose. Measured: on 20,004
audit rows over fourteen days, the unbounded prune removed 9,921 in 141 ms and a
bounded one removed 500 in 147 ms — **the bounded form is not the faster one**,
and the plan's own rationale for it was wrong in that direction (D1461). What
`p_limit` bounds is how many rows one transaction touches and holds locks on
until it commits, so that a table nobody has pruned since the deployment was
created can be taken in passes whose size the operator chose: *call it again
until it returns zero*.

## Consequences

- **`agent_audit` and `agent_idempotency` still grow by default**, and that is
  the decision rather than a gap in it. What changes is that the growth is
  visible in the doctor and that removing it is one statement with a stated
  horizon instead of an undecided question. A deployment that never prunes
  behaves exactly as it does today.
- **A row an operator prunes is gone, and nothing records that it was.** The
  audit table cannot record its own pruning: `source` is `agent_plane` or
  `database`, and `agent_id` and `owner_id` are `NOT NULL`, so a row describing
  an operator's act would have to name a principal that does not exist. The
  function returns the count and the operator writes it down. Making the prune
  auditable means a second table and a second decision, and it is named here
  rather than built.
- **`scope-closure.md`'s two-in-one row splits.** `agent_audit` is closed by
  this ADR; `agent_idempotency` is closed **with a consequence stated** — the
  window over which at-most-once holds is now whatever the operator keeps, and
  before this ADR it was forever by accident rather than by choice. Secret
  generations stay open and are a different act entirely (D1432): pruning one
  is a write at the provider and not a migration, on the surface whose rule is
  that no command in this product sets a provider value by itself (D249).
- **The doctor's headline moves from *10 ok* to *11 ok*** on a well deployment,
  in `docs/operator-guide.md`, `docs/upgrade-guide.md`, `docs/recovery-
  operations.md`, ADR 0158's table and `bin/doctor.sh`'s own usage. The
  pre-upgrade reading in the upgrade guide's §2 step 1 is taken from the host's
  own checkout **before** the new release is fetched, so a deployment being
  upgraded reads 10 before and 11 after, and the page says so.
- **Two released functions are reachable by no test that runs as a request
  role**, which is the point and is also a proof problem: a function nothing can
  call is a function nothing exercises. The offline proofs call them as the
  superuser against the cluster-with-history fixture, which is the identity that
  will call them in production.
- **The arity is now released** (ADR 0175). Adding a third argument to either
  prune later costs what every arity move costs.

## Alternatives considered

**A default retention horizon, applied by the migration.** Rejected: it deletes
evidence on a schedule nobody chose, and the number would have been invented.
Every horizon this project could have picked — ninety days, a year — is a
compliance judgement about a deployment this repository does not administer.

**A `pg_cron` job, or a trigger.** Rejected for the same reason plus one more:
it adds a component and a failure mode to the credential-bearing cluster in
order to run a `DELETE` nobody asked for, and a trigger on insert would make
every agent call pay for retention.

**Grant the prunes to `auth_service` and expose them behind `/admin`.**
Rejected. It puts a delete authority over the audit record behind an
HTTP-reachable identity — 0020's refusal, unchanged — and the person who should
be performing this act is the one who can already open a shell on the host, not
one who holds a token. The reading is exposed to `auth_service`; the deletion is
not.

**A partitioned `agent_audit`, dropped a partition at a time.** The efficient
answer and the wrong shape for this release: it is a rewrite of a table with
history on every existing deployment, it makes the reader's two indexes local,
and it buys speed for an operation measured at 141 ms. It is worth revisiting
if a deployment ever reports a prune that is slow; nothing has.

**Prune only the claims of agents that are no longer active.** Rejected by
measurement 5 — `auth_rotate_agent_secret` returns a revoked agent to `active`
with the same id, so those keys are dormant and not dead. This alternative was
the one this run expected to take, and the rig is what stopped it.

**Report the growth in `apg-diag` rather than in the doctor.** Rejected: the
agent record is a property of one project's deployment and the doctor is the
command that asks a project's deployed questions (ADR 0158). `apg-diag` is the
read-only agent surface and its verbs are about containers and routes.
