# 0182 — A dry-run attempts the write and rolls it back, and approval is a refusal

- **Status:** accepted
- **Date:** 2026-09-04
- **Session:** 16, Run 7 (`AGT-DRYRUN-001`, `AGT-APPROVE-001`, D870, D892, D923–D928)
- **Related:** **ADR 0181** (the claim is taken in the write's own transaction),
  **ADR 0179** (a capability narrows a budget and may never widen one),
  **ADR 0178** (a denial names the boundary that refused it), **ADR 0141**
  (`begin` runs before the scope check, so a denial is audited), **ADR 0130 /
  0097** (silence by default; one explicit type for what a caller may be told),
  **D489** (a row written inside the transaction it describes is rolled back
  with it), **D600** (a `null` that looks measured is worse than an absent
  field), ADR 0002.

## Context

`supports_dry_run` and `requires_approval` are already declared: ADR 0177
requires a capability field at the version that introduces it, so Run 4 landed
both at `schema_version` 3 rather than moving the manifest format a third time
in one session (D892). **This run is their behaviour**, and until it lands they
are two more declared fields with no reader — the thing §9's rotation-flag entry
exists to warn about.

D870 already fixed approval's scope: **a declaration and a named refusal, never a
workflow.** Approval implies a pending request, durable state holding it, a
second principal, and a path by which the caller learns the outcome — the last
of which is a notification plane this product does not have.

### The question the plan does not answer: whose validation?

Run 7's text says a dry-run runs *"authorization, scope and validation"*. The
runtime's validation is the lock's: argument names checked in both directions,
filters against the allowlist. **The product's validation is somewhere else
entirely** — `length(title) BETWEEN 1 AND 200` is a `CHECK` on `app.notes`, the
row policies are RLS, and the compare-and-swap is inside
`api.update_task_status`. None of it fires unless the write is attempted.

So a dry-run that simply skips the write reports success for a title the table
would refuse, which is the single thing a caller most wants a dry-run to tell
them. That is not a dry-run; it is a spell-check of the request.

### What was measured

One rig, every arm with a control.

| arm | result |
|---|---|
| a plpgsql `BEGIN … EXCEPTION` block that INSERTs then raises a sentinel | the INSERT is **rolled back** — `notes rows = 0` — and the surrounding transaction **commits its audit row**: `audit rows = 1, outcome = dry_run` |
| the `RETURNING` variable after that rollback | **survives**, complete, with the values the write would have stored |
| CONTROL — the same function without the sentinel | writes for real: one note, a real id |
| a genuine `CHECK` violation inside the block (`''` and a 201-character title) | **propagates** — `new row for relation "notes" violates check constraint "notes_title_check"` — and is not swallowed by the handler |
| after those two failures | no note, and **no audit row**: the aborting transaction took it, exactly as D489 says |
| the dry-run inside an explicit transaction that then does more work | the transaction is intact and commits |

**So a dry-run can attempt the real write, let every constraint the product owns
fire, roll it back, and still keep its own record.** D489 has denied that to
every previous run in this session — the quota refusal (ADR 0180) and the
idempotency conflict (ADR 0181) both had to avoid `RAISE` to keep their audit
rows. This is the first place the rule can be worked *with* rather than around,
because the rollback is scoped to a subtransaction rather than the whole one.

## Decision

### 1. A dry-run attempts the write and rolls it back

Inside the reviewed write function, guarded by a `dry-run` header read the same
way ADR 0181 reads the idempotency key. The INSERT or UPDATE is executed; a
sentinel `RAISE` unwinds it to the block's implicit savepoint; the handler
re-raises anything that is not the sentinel.

The re-raise is the load-bearing half. `WHEN OTHERS` swallowing everything would
turn a `CHECK` violation into a successful dry-run, which is the exact inversion
of what the caller asked. So the handler matches the sentinel and nothing else.

**A dry-run's refusal is identical to the refusal the real call would have
produced.** That is the strongest promise a dry-run can make, and it is a
property rather than an intention: the same statement runs, so the same errcode
comes back and the same translation applies (ADR 0139). A constraint violation
is `23514`, which is in no translation table and therefore stays masked — a
caller learns *no*, not *why*, and learns exactly as much as the real call would
have told them.

### 2. The returned row has a NULL id

The `RETURNING` variable survives the rollback complete, id included — and that
id belongs to a row that does not exist and never will. Publishing it is D600's
defect with a fresh coat: a plausible uuid nothing holds, in a field a client
would reasonably store.

So the id is nulled before the composite is returned. The caller sees the values
the write would have stored and no identity, because **nothing was created, so
nothing has one.** At the MCP boundary the result carries `"dry_run": true` and
`row_count` **0**.

### 3. A dry-run spends no idempotency key

The dry-run branch runs before ADR 0181's claim. A dry-run changes nothing, and
dedupe state is something; burning a key on a rehearsal would mean the real call
that follows is refused as a replay of a write that never happened.

It still **requires** a key, for ADR 0181's reasons unchanged: the rule stays
"every agent write carries a key" with no exception a caller has to remember,
and the forwarded-header rosters stay two exact sets rather than one loose one.

### 4. `dry_run` joins the outcome enum

`app_private.agent_audit_outcome` gains a seventh member. The plan's sentence is
the whole argument: *a dry-run recorded as a write would make every write count
in the audit table a lie.* `served` with a zero row count would encode it and is
refused for D495's reason, the same as `replayed` one run earlier.

**The `database`-source row carries it and the `agent_plane` row does not.** The
plane row says whether the call was served, and it was; the database row says
what the write did, and it did nothing. `agent_audit_complete`'s three-value
check is therefore untouched, which keeps a released function's validation where
Run 3 left it.

### 5. Approval is refused in the runtime, before anything is dialled

A tool whose compiled contract says `requires_approval: true` is refused by
`invoke_write` beside the scope check — so the record is already open (ADR 0141)
and the refusal is audited, and no upstream request is made for a call that
cannot proceed.

`app_private.agent_denial_reason` gains a ninth member, `approval_required`,
derived from a real refusal site exactly as ADR 0178's eight were. And
`CALLER_FACING_TOKENS` gains `approval_required`: the caller must be told, and
none of the six existing tokens is honest here — `scope_not_held` is the closest
and is false, because the caller does hold the scope.

**A caller asking for a dry-run of a write that does not support one** is a
different thing and reuses existing vocabulary: `not_in_allowlist`, surfaced as
`input_not_permitted`. The lock does not permit that input; there is no new
concept.

### 6. `supports_dry_run` aggregates with `all`, not `any`

Run 4 folded both write declarations with `any`, in one loop, with a comment
saying a fold was chosen over `declared[0]` so that grouping a write later would
not silently take the first. The fold is right and **one of the two polarities is
wrong**: `requires_approval` is a restriction, so any backing capability
requiring it makes the tool require it; `supports_dry_run` is a permission, so a
tool supports a dry-run only if **every** backing capability does.

A write is one-to-one with its operation today (D486), so both folds are
identities and nothing is presently wrong. It is corrected now because this run
is the first to read the field, and a permission folded with `any` is the
direction that grants what nothing granted.

## Alternatives rejected

**Skipping the write and validating in the runtime.** Cheap, and it answers a
different question: whether the request is well-formed, not whether it would
succeed. Every `CHECK`, every policy and the compare-and-swap live in the
database, so a runtime-only dry-run is confident about exactly the half a caller
could have checked themselves.

**`Prefer: tx=rollback`.** PostgREST can end a transaction in rollback, and it
needs `db-tx-end` configured for it and a caller-supplied `Prefer` header — which
the forwarded allowlist excludes deliberately, because `Prefer` also carries
`count=exact` and `return=representation` and would let a caller change the
response shape and cost. Reopening that header for one feature is a wide door for
a narrow need.

**Raising a distinguished errcode and translating it into success.** A `RAISE`
that means "it worked" is a lie in the one namespace this plane translates
faithfully, and D489 would take the audit row with it — the third run in a row to
meet that rule, and the first with an alternative.

**Returning the fabricated id.** It is real-looking, unusable, and the field a
client is most likely to keep. D600 exactly.

**An approval workflow.** D870, unchanged and now implemented as written.

## Consequences

- **A dry-run costs what the real write costs**, less the commit: the same four
  upstream requests, the same statement, the same locks briefly held. It is a
  rehearsal, not a preview, and an agent hammering dry-runs is doing real work.
- **A dry-run of `update_task_status` takes `FOR UPDATE` and releases it at the
  rollback.** Brief, real, and stated rather than discovered: a caller
  rehearsing a transition contends with one performing it.
- `agent_audit_outcome` has seven members and `agent_denial_reason` nine. Both
  gained one by `ALTER TYPE … ADD VALUE` in a migration whose plpgsql bodies name
  the new value, which Run 6 measured commits in one transaction where a
  `LANGUAGE sql` body does not.
- **`AGT-APPROVE-001` is proved by a refusal, and that is the whole claim.** No
  capability in `capabilities.example.yaml` declares `requires_approval: true`
  today, so the live half needs a manifest that does — which is a fixture in the
  proof, not a change to the deployment's own file.
