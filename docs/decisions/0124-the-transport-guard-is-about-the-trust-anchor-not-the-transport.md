# 0124 — The transport guard is about the trust anchor, not the transport

Status: accepted
Date: 2026-08-20
Session: 8, Run 5
Affects: ADR 0113, ADR 0121, D274, D277, D429, D431,
`tests/contract/test_auth_service_shape.py`,
`services/auth-api/app/mcp_upstream.py`

## Context

`test_the_service_never_constructs_a_network_jwks_client` has stood since
Session 6. Its docstring states the property exactly right:

> `PyJWKClient` takes a URI and fetches. This service must not hold one. A
> verifier that can fetch its keys is a verifier whose trust anchor is whatever
> answered the request — and the rotation design depends on knowing exactly
> which key material each verifier holds at each moment.

Its implementation is a different thing: an AST scan over every `.py` file under
`services/auth-api/`, refusing five names — `PyJWKClient`, `urllib`, `httpx`,
`requests`, `aiohttp`, `socket`.

Run 4 met it from one side and deferred (**D429**): a container liveness probe
needs `urllib`, and weakening a P0 guard to fit a healthcheck was the wrong
trade, so the probe was dropped and the healthcheck left to Run 7.

**Run 5 cannot defer.** The agent plane's whole job this run is to forward the
caller's token to `api.mcp_agent_context` over HTTP. There is no version of that
which does not construct an HTTP client.

## What was measured

Read from the repository, and the result is not what the test's name implies.

**The service tree already makes network calls, and the guard does not see
them.** `services/auth-api/app/storage_client.py` calls `head_object` and
`delete_object` — real round trips to R2 — through **boto3**, which is not one of
the five names. The guard has been passing for a whole session over a module
whose entire purpose is talking to a third party over the network.

So the guard is:

- **too wide** — it refuses a PostgREST call that has nothing to do with key
  material, and it refused a loopback liveness probe in Run 4; and
- **too narrow** — it admits boto3 today, and would admit `http.client`,
  `pycurl`, `aiohttp`'s successor, or any client whose module is spelled
  differently tomorrow.

**This is D277's shape.** There, an AST scan asking whether a function was
*mentioned* was satisfied by dead code. Here, a scan asking whether a transport
is *named* is satisfied by importing a different one. In both cases a
filesystem fact stands in for a logic test — CLAUDE.md §6's pattern, produced
by a test written to enforce §6.

Also read, and it is the reason the replacement can be precise: the service
obtains key material in exactly two places, both of them already
single-authority. `AuthService` is **handed** its `key_set` (ADR 0113), and the
only constructors are `LocalKeySet.load` and `LocalKeySet.from_path`.

## Decision

**The guard keeps its subject and gains an implementation that matches it. It is
replaced by three checks, all stricter than the one they replace.**

1. **`PyJWKClient` is banned outright, everywhere under the service tree.** That
   name *is* the network JWKS client, and nothing here may hold one. Unchanged
   in force, narrowed to the thing the docstring is about.
2. **A key set may not be built from anything but a local file or the signing
   key.** Asserted directly: the arguments to `LocalKeySet.load` and
   `LocalKeySet.from_path` are traced, and every construction resolves to a path
   read or to the issuer's own key. This is the property the old test *claimed*
   to enforce and never did — it inferred it from the absence of a transport.
3. **Every transport is declared, per module, in an allowlist with a reason** —
   and the allowlist covers **boto3 as well**, which the old guard did not. Two
   modules declare one today:

   | module | transport | why |
   |---|---|---|
   | `storage_client.py` | `boto3` | the R2 adapter; presigning and object lifecycle (ADR 0093) |
   | `mcp_upstream.py` | `urllib` | the agent plane's PostgREST call, with the caller's own token (ADR 0125) |

   Any other module naming any transport fails, and a *new* transport in a
   declared module fails too. Adding a row is a reviewed act, which is what the
   old blanket ban was reaching for.

## Alternatives rejected

**Add `mcp_upstream.py` to an exception list and change nothing else.** This is
the weakening CLAUDE.md §5 forbids, and it would leave the boto3 hole open —
buying Run 5's exemption with the guard's remaining credibility.

**Give the agent plane its own image so the guard does not apply.** It would put
the exemption in the filesystem instead of in a list, and ADR 0121 refused a
second image for a stronger reason: a second image cannot import `LocalKeySet`,
and the fourth verifier acquiring a second key-set parser is how D381 happened
to the third.

**Reach PostgREST through boto3 or some already-admitted library.** Satisfying
the letter of a guard by choosing an oddly-shaped client is the purest form of
the defect this ADR is about.

**Drop the transport list entirely and keep only checks 1 and 2.** Tempting,
because those two are the real property. Refused: the list is what makes a new
network dependency *visible* in review, and Run 5 is itself the proof that one
arrives without anybody planning it. The cost of a row is one sentence.

## Consequences

- **The guard now fails for a case it previously passed** — a transport in an
  undeclared module, including boto3 — so this is a net tightening, and a test
  asserts exactly that by constructing both a passing and a failing source.
- The allowlist is a **review surface**. Two rows today; a third is a
  conversation, not a diff nobody reads.
- **D429's healthcheck is unblocked but not taken here.** Run 7 still owns the
  agent plane's health surface, and a probe module would now be a third row with
  a third reason. That is Run 7's decision to make, with this ADR available.
- The old test's docstring survives almost intact, because it was never the part
  that was wrong.
