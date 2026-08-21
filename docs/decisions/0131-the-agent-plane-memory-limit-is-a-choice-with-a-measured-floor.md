# 0131 — The agent plane's memory limit is a choice with a measured floor, and it gets no validator

Status: accepted
Date: 2026-08-21
Session: 8, Run 8
Affects: ADR 0082, ADR 0121, ADR 0129, D234, D456,
`services/auth-api/app/mcp_budgets.py`, `src/agentic_postgres/rendering.py`

## Context

`MCP_MEMORY_LIMIT_MB` has been **384 since Run 4, inherited from the application
API and measured nowhere.** Its own comment says so, and says what would have to
happen before it stopped being a guess: *"ADR 0082 is the shape the measurement
must take … It cannot be taken before Run 6 has four registered tools to
exercise. Run 8 owns budgets and owns this."*

Run 8 has the four tools and the two budgets that feed the arithmetic — a
serialized-byte ceiling per response and a bound on how many responses may be in
flight (ADR 0129). Those are exactly the inputs a memory floor needs.

## What was measured

ADR 0082's rule, obeyed literally: `ru_maxrss` is a **high-water mark**, so every
arm is a fresh interpreter and arm zero imports nothing. A control that moves
means the rig is measuring itself.

**The constant term** — one interpreter per layer, peak resident:

| layer | peak | over baseline |
|---|---|---|
| **CONTROL — nothing imported** | 12.1 MiB | **0.0** |
| `json`, `logging`, `asyncio`, `time` | 18.0 MiB | +5.9 |
| `jwt` and `cryptography` | 29.0 MiB | +16.9 |
| `mcp.types` | 54.3 MiB | +42.2 |
| `fastmcp` | 54.9 MiB | +42.8 |
| **the agent plane's nine modules** | **69.2 MiB** | **+57.1** |

**The protocol library is the cost, not the server.** `mcp.types` alone adds
25 MiB — more than PyJWT and `cryptography` together — and `fastmcp` on top of it
adds **0.6**. That is worth writing down because the intuition is backwards: the
framework looks like the heavy dependency and is not.

The comparable figure for the auth service in ADR 0082 was 60.9 MiB, for a
process that carries `psycopg`, a pool, `argon2` and FastAPI. The agent plane
carries none of those and costs **8 MiB more**.

**The variable term** — N reads held live at once, each a response at 90 % of
`MAX_SERIALIZED_BYTES` (0.87 MiB of raw upstream bytes), through the real path:
socket bytes, `json.loads`, `_within_budget`, `json.dumps`.

| arm | resident delta |
|---|---|
| **CONTROL — 0 reads** | **0.0 MiB** |
| 1 concurrent read | 1.8 MiB |
| 2 | 3.3 MiB |
| 5 | 8.8 MiB |
| 10 | 17.8 MiB |

Linear, at **≈1.8 MiB per concurrent read** — roughly twice the response's own
bytes, which is what holding the parsed rows and the serialized string at the
same time costs.

## Decision

**The floor is a function of the two budgets Run 8 set:**

    floor(share) = PROCESS_OVERHEAD_MB + share x PER_READ_MB
                 = 128 + share x 4

with `share` = `MCP_MAX_CONCURRENT_READS`. At the default share of 5 the floor is
**148 MiB**.

**Both constants are charged above what was measured**, in ADR 0082's direction
and for its reason — the direction that costs a redeploy is cheaper than the
direction that costs an OOM kill on a host with no swap.

| constant | measured | charged | ratio |
|---|---|---|---|
| process overhead | 69.2 MiB | 128 MiB | 1.85x |
| per concurrent read | 1.8 MiB | 4 MiB | 2.2x |

ADR 0082 charged 1.58x for the same quantity. This one is charged higher on
purpose: that measurement was of a process the deployment had been running for
two sessions, and **this one is of a process that has never started in a
container anywhere.** It is a profile of the interpreter in a virtualenv, not of
the container, and the difference is unmeasured.

**`MCP_MEMORY_LIMIT_MB` stays 384**, and what changes is what that number is: an
inherited constant becomes a **choice with a measured floor beneath it and stated
headroom** — 2.6x the floor at the default share.

**There is no manifest validator, and refusing to write one is the decision.**
ADR 0082's floor is enforced by `_validate_auth_memory`, because
`hash_concurrency` is a manifest field an operator can raise. The obvious move
was to mirror it. It was checked instead of assumed, and the check kills it:
`api.rest.pool_size` is bounded at **100** by the schema, so the largest share
any valid manifest can produce is 50 and the largest floor is **328 MiB** —
below the limit. **A validator here could not fail for any document the schema
admits.**

That is §6's defect pattern with the polarity reversed: not a value that looked
measured and was not, but a *guard* that would look enforced and enforce nothing.
This repository has enough of those (D277, D391).

**What replaces it is a test that can go red.** The relation is asserted against
the schema's own maximum, read from `schemas/project.schema.json` rather than
restated: raise that bound past 128 and the assertion fails, naming the choice —
raise the limit, or write the validator that has become possible.

## Alternatives rejected

**Lower the limit to the floor** (192 MiB, or 256 with headroom). Tempting: two
projects on a 3814 MiB host with no swap would give back 256–384 MiB, and it
would make the relation live enough to justify a validator. **Refused for now
because the measurement does not cover the container** — it is the interpreter in
a virtualenv, and no `mcp` container has started anywhere. Lowering a limit on
the strength of an off-container profile is the direction ADR 0082 named as the
expensive one. It becomes available the moment Run 9's host trip can profile a
running container, and this ADR is the arithmetic it should be re-checked
against.

**Make it a manifest field**, as `api.app.memory_limit_mb` is. ADR 0082 made that
field exist because operators tune `hash_concurrency` and the limit has to follow
them. Nothing here is tunable per project: the share is **derived** from
`api.rest.pool_size` (ADR 0129). A field would be a knob with no reason to turn
it — and a knob nobody turns is a knob nobody maintains, which is how a field
comes to accept a value the code stopped honouring.

**Derive the floor from the byte ceiling alone** — `share x MAX_SERIALIZED_BYTES`
= 5 MiB. It is the arithmetic that looks right and understates by 1.8x, because
the ceiling bounds the *serialized response* and the process also holds the raw
bytes and the parsed rows while it produces it. Measuring is what found that
factor; nothing about the ceiling implies it.

**Leave the number inherited and say so, again.** It is what Runs 4 through 7
did, honestly, with the flag in the right place. But the flag names Run 8, and a
provisional value carried forward once more is how a value that looked measured
and was not gets created — this time in slow motion, with everybody watching.

## Consequences

- **The last unmeasured number in the agent plane's budget set is measured.** The
  four bounds of ADR 0129 plus this one are now five numbers with a measurement
  or a stated derivation behind each.
- **`mcp.types` is the agent plane's largest dependency by resident cost**, and a
  future attempt to trim the image should start there rather than at `fastmcp`.
- The floor is expressed where the concurrency bound lives, so the two move
  together — the same reason ADR 0082's relation sits beside the profile.
- **The container-level figure is still unknown**, and it is the one a limit
  actually bounds. Run 9's host trip is the first time an `mcp` container exists;
  reading its resident set is one command and belongs in the operator guide.
- A validator becomes worth writing the moment either bound moves: the schema's
  `pool_size` maximum above 128, or the limit below 328. The test says which.
