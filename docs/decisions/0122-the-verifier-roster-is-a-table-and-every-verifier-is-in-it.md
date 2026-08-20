# 0122 — The verifier roster is a table, and every verifier is in it

Status: accepted
Date: 2026-08-20
Session: 8, Run 4
Affects: ADR 0088, ADR 0098, ADR 0113, ADR 0121, D276, D300, D305, D320, D381,
D411, D416, D425, D426, D427, `bin/rotate-signing-key.py`,
`tests/contract/test_rotate_signing_key.py`, `docs/api-operations.md`

## Context

ADR 0088 is the rotation model, and its safety rests on one refusal:

> Promoting while any verifier still holds the previous key set means signing
> tokens that verifier will refuse, and the failure arrives at whoever holds one
> — as an authentication error with no cause visible from where it is seen.

`promote_rotation` therefore blocks until **every verifier** has recorded the
published digest. It takes the roster as an argument, `consumers: list[str]`, and
the caller supplies it. The caller is `bin/rotate-signing-key.py`:

```python
#: One today, and it is a list because promotion is blocked on *every* one of
#: them: a check written against a single name reads as though it could never
#: have been plural, and Session 9 adds agent-facing verifiers.
VERIFIERS: tuple[str, ...] = (runtime_override.REST_SERVICE,)
```

That comment was true when it was written, in Session 6. **Session 7 added a
third verifier and this line did not move.** ADR 0113's own Consequences
section says it did:

> **Storage joins the recreate list.** ADR 0088 already says every verifier must
> be **recreated, not restarted** … There are now three.

It was written down and not implemented — **D333's question for the sixth time,
and the first time the unimplemented half is an ADR's own stated consequence.**

Run 4 arrives to add a fourth verifier and finds three separate defects behind
the same constant.

## What was measured

Read from the code, and measured against the locked images on Docker 29.5.2 with
controls that discriminate.

**1. The roster names one of three verifiers.** `VERIFIERS` holds
`postgrest` alone. `storage` mounts the rendered `jwks.json`, requires
`APG_JWKS_FILE`, and loads it with `LocalKeySet.from_path` (ADR 0113) — and is
absent from the gate that blocks promotion. A rotation today promotes as soon as
PostgREST acknowledges, while the storage container still verifies against the
retired key set. **That is D276's symptom exactly**: 401 on every token, from one
surface, invisible until something asked both.

**2. The roster's tests cannot see the omission.** Every one of them iterates
`for verifier in command.VERIFIERS`, so they are derived entirely from the
constant. The only independent anchors are `REST_SERVICE in VERIFIERS` and
`AUTH_SERVICE not in VERIFIERS`, and neither mentions storage. **This is D300's
shape and D416's lesson arriving again**: a set derived entirely from the product
cannot refuse a bad edit to the product.

**3. `VERIFIER_JWKS_PATH` is one constant, and the verifiers read two paths.**
PostgREST reads `runtime_override.JWKS_CONTAINER_PATH`; storage reads
`STORAGE_JWKS_CONTAINER_PATH`, which is `/etc/storage/jwks.json`. The test
guarding it, `test_the_key_set_is_read_where_the_container_reads_it`, asserts
one constant equals one constant — **CLAUDE.md §6's "a test comparing two
constants is not testing the thing between them"**, passing while blind to the
second path.

**4. The read mechanism does not work in the image of the one verifier that is
listed.** `loaded_digest` runs `docker exec <container> cat <path>`. Measured:

| image | `--entrypoint cat` | `--entrypoint sh` | `docker cp` |
|---|---|---|---|
| locked PostgREST v14.16 | **exit 127**, *"executable file not found"* | **exit 127** | **exit 0** |
| CONTROL — locked `python:3.12-slim` | exit 0 | exit 0 | — |

The PostgREST image is distroless (D305, D411). **`acknowledge` cannot read the
digest of the only verifier in the roster**, so it raises `EXIT_STATE` and
promotion can never be unblocked. The control is what makes this a fact about
the image rather than about the probe.

That fourth finding is worth sitting with. `SEC-KEY-002`'s open item — *"the
rotation window, the only thing keeping two Session 5 claims red"* — has been
carried for three sessions, and the command it names cannot complete its second
phase against the verifier it knows about.

## Decision

**The roster is a table with one row per verifier, and the row carries
everything that differs between them.**

```python
VERIFIERS: tuple[Verifier, ...] = (
    Verifier(service=REST_SERVICE, jwks_path=JWKS_CONTAINER_PATH),
    Verifier(service=STORAGE_SERVICE, jwks_path=STORAGE_JWKS_CONTAINER_PATH),
    Verifier(service=MCP_SERVICE, jwks_path=MCP_JWKS_CONTAINER_PATH),
)
```

1. **Every service that reads a key set is a row.** Three today; the auth service
   is still not one, because it is the issuer and an acknowledgement from it
   would be the issuer agreeing with itself.
2. **The path comes from the row**, so a verifier configured with one path
   cannot be inspected at another. `VERIFIER_JWKS_PATH` is deleted rather than
   generalised — a single name for a per-verifier value is the defect.
3. **The digest is read with `docker cp`**, which works in a distroless image and
   in a hardened one alike. It reads the container's own filesystem, so it keeps
   the property `docker exec cat` was chosen for: a replaced file leaves the
   container bound to the previous inode, and the host's copy is not what the
   process is verifying against.
4. **The roster is checked against the product, not restated from it.** One test
   asserts that every Compose service given `APG_JWKS_FILE`, plus PostgREST,
   appears in the roster — derived, so it catches the *next* verifier — and a
   second names `storage` and `mcp` as literals with this ADR behind them, so a
   deletion is refused by something the product cannot move. Both are needed and
   D416 is why.

## Alternatives rejected

**Add `storage` and `mcp` to the tuple and change nothing else.** It would put
three verifiers behind a command that reads all of them at PostgREST's path with
a `cat` that does not exist in PostgREST's image. The roster would be right and
the command would fail on every row — a fix to the list that leaves the thing the
list feeds broken, which is the half-fix D333 keeps producing.

**Derive the roster from `compose.yaml` at runtime.** It removes the restatement
and with it the ability to refuse a bad edit: a product-derived set agrees with
whatever the product says, including a `compose.yaml` that quietly stopped
mounting a key set. D416 settled this shape — derive the sweep, keep one
independent anchor.

**Read the host's rendered file instead of the container's.** It is what the
`docker exec` was deliberately avoiding, and the case it avoids is the one that
matters: a verifier bound to a replaced inode reports the old digest, which is
precisely the state promotion must block on.

**Leave the rotation command to the session that runs a rotation.** Refused. The
fourth verifier is being added now, and adding it to a roster known to be missing
its third is how the roster ends up two short instead of one. The plan's Run 4
bullet says this list moves, and D409 predicted this is where it would be
checked.

## Consequences

- **Promotion is now blocked on three verifiers**, and a rotation is
  correspondingly slower to unblock. That is the cost ADR 0088 chose on purpose.
- **`SEC-KEY-002`'s readings go from three to four**, and D320's prediction —
  made in Session 7, due a second time in Session 8 — is now discharged in a
  place that cannot silently miss the fifth.
- **The rotation window's open item gains a measured cause.** Whether `docker cp`
  makes `acknowledge` complete end to end is a live-host claim and this session
  does not assert it; what is asserted offline is the command it builds. The
  window stays open, with a smaller and better-named unknown in it.
- The operator guide's rotation sequence names three containers to recreate
  rather than one.
