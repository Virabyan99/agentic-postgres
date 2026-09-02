# 0171 — A refresh family is the session, and one live token per family is a catalog invariant

- **Status:** accepted
- **Date:** 2026-09-02
- **Session:** 15, Run 2 (`IDN-SESSION-001`, `IDN-SESSION-002`, D826–D830)
- **Related:** **D812** (there was no refresh plane to extend), **D813** (a token
  lives 930 s and nothing renewed it, so a client had to hold the password),
  **D826** (the reuse signal is decided by the isolation level), **D827** (the
  partial unique index makes the rotation ORDER a catalog constraint), **D828**
  (a salted hash cannot be looked up, so the storage differs from its two
  neighbours), **D829** (a session carries no caller-supplied string), **D830**
  (functions and grants arrive with their caller, so this migration creates
  neither), ADR 0078 (`credential_version` / `authz_version`, the existing
  revocation mechanism), ADR 0029 (a trusted column is not an authenticated one),
  ADR 0091 (released migrations are fix-forward), ADR 0002 (one derivation per
  identity).

## Context

D813 is the reason this plane exists. `MAX_TTL_SECONDS` is 900 and the auth
service issues at the ceiling, so a token is live for at most 930 seconds and
**nothing renews it** — which means any client that stays logged in longer than
fifteen minutes has to keep the *password* and replay it. The short TTL is right;
what was missing is the half that makes it affordable.

D812 established that there is nothing to extend: no route, no table, no column
across 22 released migrations, and `refresh_token` present in the tree only as a
value the redaction denylist forbids. This migration is new construction, and
the decisions below are what it is built from.

Two of them were measured against the pinned image before anything was written,
because both are properties of the database rather than of the Python.

## Decision

### 1. A family is the session — one object, not two

A refresh family is a chain of single-use tokens sharing an ancestor, created at
login and ending at logout, expiry or reuse detection. **It is also exactly what
a user means by "a session"**, so `IDN-SESSION-002`'s listing and termination are
family operations rather than a second table keyed alongside.

Two tables would have required a rule about what happens when one is present and
the other is not, and this repository has paid for that shape before: a second
authority for one value (ADR 0002) is not created here.

### 2. At most one live token per family, enforced by the catalog

```sql
CREATE UNIQUE INDEX refresh_tokens_one_live_per_family
  ON app_private.refresh_tokens (family_id) WHERE consumed_at IS NULL;
```

**This is the invariant reuse detection rests on.** If two tokens in one family
could be live at once, a thief and the legitimate client would each hold a valid
one and neither presentation would look like a replay — there would be nothing to
detect. Making it an index rather than a rule in the service means it holds for
every writer, including a future one nobody has written yet.

**It also makes the rotation ORDER a catalog constraint** (D827), which was
measured rather than assumed: in one transaction, consume-then-insert is
accepted and **insert-then-consume is refused with `23505`**. So a rotation that
issued the successor before retiring its parent cannot be written by accident —
it fails at the database, in every environment, rather than passing review.

### 3. The stored value is a deterministic SHA-256, and that differs from both neighbours

`user_credentials.password_hash` and `agent_credentials.secret_hash` both carry
`CHECK (... LIKE '$argon2id$%')`. This table stores a hex SHA-256 instead, and
the reason is structural rather than a preference (D828).

**A salted hash cannot be looked up.** An agent presents `agent_id` *and* its
secret, and a person presents a username and a password, so both rows are found
by an identifier and the hash is only ever *verified*. **A refresh token presents
only itself** — there is no accompanying identifier — so the row has to be found
*by* the stored value, and argon2's per-row salt makes that a full scan with a
KDF per row.

The token is 32 bytes from `os.urandom`, so the property a KDF buys — making a
low-entropy secret expensive to guess — is not a property this value needs. What
it does need is that the database never holds the presented value, and a
deterministic digest gives that.

`CHECK (token_hash ~ '^[0-9a-f]{64}$')` states the shape, so a row holding a raw
token, an argon2 string or an empty value is refused at write time rather than
discovered when a lookup silently matches nothing.

### 4. Reuse revokes the family, not the descendants

The plan said *"presenting a consumed token invalidates every descendant"*. In a
linear chain those are the same set — everything after the replayed token is the
live token and nothing else — so this is a simplification rather than a change.
**Revoking the family is the spelling**, because it is one write against one row
and it also covers the case the descendant framing does not: a replay arriving
after the family was already revoked for another reason.

Reuse is classified even when the family is already revoked, because a second
replay is evidence and suppressing it would lose the alarm that matters.

### 5. A session carries no caller-supplied string

No user agent, no IP address, no device label (D829). A session is identified by
its id, its creation time and its last use.

This costs something real and it is the deliberate choice: session listing cannot
say *"Firefox on a Mac in Berlin"*. The rule it keeps is the one the agent plane
already keeps — **no caller value is recorded** — and a caller-supplied display
string is a caller value however harmless it looks, with the same escaping and
redaction questions attached. If a later session decides the listing needs more,
that is a decision with an ADR, not a column added because it seemed useful.

### 6. The reuse signal is an empty result, and the isolation level decides that

Measured against the pinned image, with a control proving the rig had a real race
(both transactions win when the guard is removed):

| | under `read committed` (the deployment's level) | under `repeatable read` |
|---|---|---|
| the winner | 1 row | 1 row |
| the loser | **0 rows, no error** | **`40001`** |

So under the level this deployment actually runs, a replay is an **empty result**,
and the loser **blocks until the winner commits** — measured at 0.61 s in the rig.

**This is the part that must not be treated as a transient error.** `40001` is a
serialization failure, and the ordinary response to one is to retry; retrying a
replayed refresh token presents the replay a second time. The plane is therefore
specified against `read committed` and its outcome is read from the row count.
**If anything ever raises the isolation level for this path, this decision has to
be revisited rather than inherited** — which is why the measurement is recorded
here rather than in a comment beside the query.

A replayed token and an unknown one are distinguishable after the fact, which is
what makes the alarm possible: the replayed row is present with `consumed_at`
set, and an unknown hash has no row at all.

### 7. This migration creates no function and no grant

`app_private` tables only. Migration 0011 set the terms for its own successors:

> `auth_service` gets schema USAGE and nothing else … the service reaches this
> data through SECURITY DEFINER functions that arrive in the same commit as the
> code that calls them. **A grant issued now would be a grant nobody can audit
> against a caller that does not exist.**

Run 3 brings the endpoints, so Run 3 brings the functions and the grants (D830).
Until then these tables are reachable by the owner alone, which is what the
blanket `REVOKE ALL … FROM PUBLIC` at the end of every migration in this schema
already establishes.

### 8. The state machine lives with the auth service, not in `agentic_postgres`

The session plan said *"pure logic first, in `src/`"*, and that was wrong for this
repository's layout (D831). `agentic_postgres` is the package `bin/` and the
deploy share; the session plane is read by the auth service and by nothing else —
no operator command, no deploy step, no renderer. It belongs beside `claims.py`,
`tokens.py`, `scopes.py` and `hashing.py`, which are the auth service's own pure
modules.

**A guard said so rather than a review.**
`test_no_module_is_imported_only_by_its_own_tests` refused the module in
`src/agentic_postgres/` with *"a module with no caller is a feature that does not
exist, however well it is tested"* (D204) — true, because Run 2 deliberately
touches no endpoint and the caller arrives in Run 3. The guard was right about
the package, and following it produced the correct placement instead of an
allowlist entry.

## Consequences

- **Nothing is renewable yet.** This run delivers state and a pure state machine;
  no endpoint changes, and `IDN-SESSION-001` cannot pass until Run 3 exists and
  Run 8 runs it live.
- **A family has no absolute lifetime**, so a continuously-used session survives
  indefinitely. That is the ordinary shape of refresh rotation and it is recorded
  as a decision rather than an oversight: adding a ceiling is one column and one
  comparison, and it belongs with whoever can say what the ceiling should be.
- **Nothing prunes consumed tokens or revoked families**, exactly as nothing
  prunes `app_private.agent_audit` or secret generations. The chain is the audit
  trail of a session, and discarding it would discard the evidence a reuse alarm
  is read against.
- **`credential_version` still ends every session.** A password change moves it,
  and Run 5's reset is specified to move it too, so the existing revocation
  mechanism reaches this plane without this plane restating it (ADR 0078).
