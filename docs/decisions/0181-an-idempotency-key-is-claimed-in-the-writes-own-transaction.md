# 0181 — An idempotency key is claimed in the write's own transaction, and the outcome is re-read rather than stored

- **Status:** accepted
- **Date:** 2026-09-04
- **Session:** 16, Run 6 (`AGT-IDEM-001`, D864)
- **Related:** **ADR 0161 / D633** (a caller header is guarded before it is cast,
  and a correlation field must never destroy the write it annotates — this ADR
  inverts that deliberately), **ADR 0139** (a write refusal is *translated* from
  the product's own errcode, never a relayed status), **ADR 0141** (`begin` runs
  before the scope check so a denial is audited), **ADR 0180** (the fifth budget,
  counted where the record is already opened), **D479** (the lock's
  `audit.redact` is the one authority over caller values), **D489** (a row
  written inside the transaction it describes is rolled back with it), ADR 0002.

## Context

D864 settled what this is: **new construction.** The manifest's `idempotent:
bool` declares a property of an *operation* — replaying this is harmless — and
an idempotency key is a caller-supplied token meaning the opposite: *do not
replay this*. The boolean is left alone as the separate thing it is.

`AGT-IDEM-001` asks for three things: the same key performs the work once, a
replay returns the outcome, and a different key with the same body performs it
twice.

### The plan named the hard part, and it is not the hard part

Run 6's text says the stored outcome is the difficulty — that returning a
recorded response means the plane holds a caller's prior result, which
`audit.redact` must cover *before* it is stored. That is right about the danger
and wrong about the necessity. **The outcome does not have to be stored**, and
§5 of this ADR is the alternative.

### What was measured

Two rigs against the locked image, each arm with a control.

**M1 — a released ENUM gaining a member inside one transaction.** dbmate wraps a
migration in one, so this decides whether `replayed` can be an outcome at all:

| arm | result |
|---|---|
| `ALTER TYPE … ADD VALUE 'replayed'` then `INSERT … 'replayed'`, one transaction | **`ERROR: unsafe use of new value "replayed"`** — and the whole transaction rolls back, so the member is *not* added |
| CONTROL — the same transaction shape using an existing member | commits, one row |
| the ALTER in one transaction, the INSERT in the next | commits, two rows |

**M4/M5 — the question that actually decides migration 0029's shape**, because
the migration adds the member and *creates functions naming it* rather than
inserting:

| arm | result |
|---|---|
| ADD VALUE + `CREATE FUNCTION … LANGUAGE plpgsql` whose body names it | **commits**; members = `served,refused,replayed` |
| CONTROL — the same with `LANGUAGE sql`, which is fully parsed at creation | **`ERROR: unsafe use of new value "reviewed"`**, transaction rolled back |
| the plpgsql function called in a later transaction | inserts, `o = replayed` |

And the control that proves M4's answer is about plpgsql's laziness rather than
about the check being unreachable: **a plpgsql function naming a member that
does not exist is CREATED without complaint**, where the SQL-language form is
refused at creation. So creation-time validation proves nothing here, and the
path has to be exercised by a test that runs it.

**M2 — the fingerprint needs no extension.** `sha256(bytea)` is a built-in on
the locked image; the control, pgcrypto's `digest()`, does not exist
(`pg_extension` holds nothing but `plpgsql`).

**M3 — two overlapping claims of one key at `read committed`**, ADR 0171's
pattern:

| arm | result |
|---|---|
| loser's `INSERT … ON CONFLICT DO NOTHING RETURNING` | **blocked 576 ms** (the winner held 750 ms and the loser started 150 ms in), and `RETURNING` produced **no row** |
| the loser's next `SELECT`, same transaction | **sees the winner's `row_id`** |
| final table | **one row**, the winner's |
| CONTROL — the same pair against a table with no unique constraint | no block (1 ms), **two rows** |

So the loser waits, learns it lost by getting nothing back, and can read the
winner's outcome in its own transaction. The control shows the rig can plainly
tell blocking from not-blocking.

**PT412 crosses HTTP as 412.** rig4 measured `PTxxx → xxx` over four codes;
a fifth is an *extension* of that rule, not an instance, so it was measured —
and it was measured by adding an arm to `test_a_pt_sqlstate_carries_its_status`
rather than in a throwaway rig, so the extension stays exercised.

## Decision

### 1. The claim happens inside the write RPC's own transaction

A separate claiming RPC cannot deduplicate. Two calls in two transactions can
both pass a check and both write; atomicity is the entire guarantee, and it is
only available where the write is.

**This is a different argument from ADR 0180's and the difference matters.** The
quota went into `agent_audit_begin` because a separate request would *cost* a
fifth round trip on a path nobody has timed (D904). The key goes into the write
function because a separate request would be *wrong*. One is economy; this is
correctness, and it would hold at any price.

### 2. The key arrives as a header, and the signatures do not move

`idempotency-key`, read exactly as migration 0022 reads `x-request-id` —
`current_setting('request.headers', true)`, lowercase key, two-argument form
because these functions are reachable from psql. That situation was measured in
Session 11 through PostgREST at the pinned digest, through a role switch, behind
the `db-pre-request` hook, inside a `SECURITY DEFINER` function with
`SET search_path = pg_catalog, pg_temp` — which is this function's exact
situation and not an approximation of it (D632).

`CREATE OR REPLACE` with unchanged signatures, so nothing in `api` is created,
dropped or re-signatured, no grant moves, **the human REST surface is untouched**,
and ADR 0175's arity guard has nothing to catch.

**The guard is inverted from 0022's, deliberately.** A malformed request id
records NULL and lets the write proceed, because *a correlation field must never
destroy the operation it annotates* (D633). A malformed idempotency key
**raises**, because ignoring it performs the write **without the guarantee the
caller asked for** — a silent downgrade from at-most-once to at-least-once, which
is the failure this whole run exists to prevent. Same mechanism, opposite
failure mode, and the reason is that one field describes the write while the
other governs whether it happens.

### 3. Every agent write requires a key; no manifest field

Required, so the guarantee is unconditional rather than something an agent has
to remember. It is derived from the lock's existing `kind == write`
classification, so **no capability-manifest field is added and `schema_version`
stays 3** — which is what keeps D892's two-formats arithmetic true rather than
forcing a v4 in the session that argued against a third format.

A **human** caller is unaffected: the claim is taken only when `app.agent_id` is
set, which is the property 0019 already relies on. A human sending the header
gets no idempotency, and that is a stated limitation rather than an oversight —
extending it would change the human REST contract, which this run is not for.

### 4. One row per claim, and a fingerprint rather than the arguments

```sql
CREATE TABLE app_private.agent_idempotency (
  agent_id         uuid        NOT NULL REFERENCES app_private.agents (id) ON DELETE CASCADE,
  idempotency_key  text        NOT NULL,
  tool             text        NOT NULL,
  arguments_sha256 text        NOT NULL,
  row_id           uuid,
  replay_count     integer     NOT NULL DEFAULT 0,
  created_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (agent_id, idempotency_key)
);
```

`INSERT … ON CONFLICT DO NOTHING RETURNING` claims it — M3's measured shape. A
claim that returns a row is this call's; one that returns nothing means somebody
else got there first, and the next `SELECT` sees them.

**The fingerprint is a hash, computed in the database from the function's own
parameters** (M2). One authority: the runtime cannot compute it differently
because the runtime does not compute it. A key presented with a different tool
or a different fingerprint raises **`PT412`**, translated by ADR 0139's existing
machinery to the existing `input_not_permitted` token with a sentence of this
repository's own. **No new denial reason, no new caller-facing token.**

`PT412` and not `PT409`: 409 is already the compare-and-swap conflict, one
errcode cannot carry two sentences, and *"re-read and retry"* is precisely the
wrong advice for a key bound to different arguments — the right move is a new
key. 412 is honest: the caller supplied a precondition and it does not hold.

**The tool comparison cannot currently fire, and is kept anyway.** A surviving
mutation is what established this: the fingerprint is built from each function's
own parameter names, the two reviewed writes share none, so two tools can never
produce the same hash and the fingerprint clause always refuses first. It stays
because the claim's `tool` column is what an operator reads, and because a third
write tool sharing another's parameter names would make the comparison
load-bearing overnight. What changed is the **proof**: a check that cannot be
reached end to end is measured at the boundary that can reach it — a direct call
to `agent_idempotency_claim` with the fingerprint held equal across two tool
names — rather than through a path that appears to reach it and does not.

### 5. The outcome is re-read, not stored

The claim stores `row_id`. A replay **re-selects the row** and returns it.

- **The plane stores no caller value.** `audit.redact` stays the single
  authority over caller values (D479) because nothing here is a caller value to
  govern — a hash and a uuid the caller already holds. The plan's hard part is
  dissolved rather than solved.
- **It is more truthful than a snapshot.** A stored response returned later
  claims to describe a row that may have moved on. Re-reading answers the
  question the caller is actually asking — *did my write happen, and what is
  the row* — with the row's current state, which is the only state anything can
  honestly report.

The re-read is predicated on the owner, so a replay cannot cross an ownership
boundary even if a key somehow did.

### 6. A replay is audited as `replayed`, with `row_count` 0

`app_private.agent_audit_outcome` gains a sixth member. `served` with a zero row
count would encode the same fact and is refused for D495's reason: **one value
carrying two meanings is the defect this repository produces most**, and "a
write that served nothing" is not a fact anybody should have to infer from an
arithmetic coincidence.

The raw key is **not** written to `agent_audit`. It is a caller value, and an
agent record carries none (ADR 0130). Where it legitimately lives is the
idempotency table, which *is* the dedupe state rather than an annotation of it,
and `replay_count` there is what an operator reads to see a key being retried.

## Alternatives rejected

**Storing the response.** The plan's own shape. It requires the redaction rules
to cover a second store with different needs — the audit record wants
`p_content` redacted, and a replay wants it returned verbatim, so one authority
cannot serve both and a second one is what ADR 0002 forbids. It is also the less
truthful answer (§5).

**A separate `claim` RPC before the write.** Two transactions, so two callers
can both claim. Not a cost objection like D904's — an outright correctness one.

**The key as a function argument.** It would move both signatures, which drops a
parameter onto the human REST surface for an agent-plane concept, needs a DROP
and CREATE with grants re-issued (0007's shape), and buys nothing the header
does not already give — in a mechanism that was measured for this exact
situation three sessions ago.

**`(agent_id, key, arguments_sha256)` as the primary key**, so a reused key with
different arguments is simply a different claim. It needs no refusal and no
`PT412`, and it is wrong quietly: a caller retrying with a corrupted body gets a
second write and no signal, which is exactly the outcome a key was supplied to
prevent.

**Refusing with `PT409`.** One code, two sentences. The advice differs — retry
versus use a new key — so sharing the code makes one of them a lie.

## Consequences

- **Both write tools gain a caller-facing parameter.** The compiled contract's
  hash moves, which is what `contract_hash` on the audit row exists to record.
- **A failed write does not burn its key.** The claim is written in the
  transaction the write aborts, so D489 takes it with the RAISE — and here that
  is the behaviour anyone would want: a key is retryable after a failure.
  D489 has been a constraint in three previous runs and is a feature in this one.
- **Nothing prunes `app_private.agent_idempotency`.** Unlike ADR 0180's quota
  table it is genuinely unbounded — one row per key a caller ever mints — so it
  joins `agent_audit` and the secret generations in §9's list rather than
  escaping it. Retention is a decision this run does not take, and it is named
  here so the next one does not discover it.
- **A replay costs a `SELECT` and no write.** The four upstream requests a write
  makes are unchanged, so a replayed write costs the same as a real one at the
  MCP boundary and less at the database.
- **`app_private.agent_idempotency` is readable by no request role**, the same
  posture as `agent_audit` and `agent_quota`.
