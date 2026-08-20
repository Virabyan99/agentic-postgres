# 0126 — The runtime dials the internal upstream; the lock names the public surface

Status: accepted
Date: 2026-08-20
Session: 8, Run 6
Affects: ADR 0002, ADR 0106, ADR 0125, D389, D436,
`src/agentic_postgres/capability_compiler.py`, `bin/mcp-contract.py`,
`services/auth-api/app/mcp_lock.py`, `compose.yaml`

## Context

Run 3 built the deployed lock and gave it an `upstream` member.
`capability_compiler.compile_lock` says what it is for:

> `upstream` is the ONE address the runtime may call — Run 6's fixed upstream.
> It is carried here rather than derived by the runtime for ADR 0002's reason.

Run 6 is the run that would consume it, and it cannot.

## What was measured

`bin/mcp-contract.sh lock` fills `upstream` from the deployed document's
`routes.rest`, and a rendered fixture shows what that is:

```
routes.rest      https://fixture-alpha-dev.test/api/rest
```

A **public** URL, on the project's own domain, behind Traefik and TLS.

The agent plane runs on the `internal` Compose network, which is declared
`internal: true` — *"no route off the host"*. `postgrest` and `mcp` are both
members of it. So the address the lock names is reached, if at all, by leaving
the host through public DNS and returning through the edge; and the address that
works is `http://postgrest:3000`, which Run 5 already dials for
`api.mcp_agent_context` and which was measured working against a live PostgREST.

**Two authorities for one question, disagreeing.** This is D389's shape: there,
outputs v11 put the storage bounds in the rendered document while the deployed
branch forbade them, and the runtime read the deployed one. Here a document
declares an address and the runtime cannot use it.

## Decision

**The runtime dials `APG_POSTGREST_URL`. The lock's `upstream` is the published
identity of the surface the capabilities were compiled against, and no code
dials it.**

1. `upstream` keeps its value — the public `routes.rest` — and its meaning is
   corrected in the compiler's docstring and in this ADR: it says *which API
   surface this contract describes*, which is what a reader of a deployed lock
   needs and what makes two projects' locks distinguishable.
2. The runtime's dial string is the one Run 5 established: an internal address,
   rendered by `rendering.py` from `POSTGREST_SERVICE_HOST` and
   `runtime_override.REST_SERVICE_PORT`, handed over finished (ADR 0002).
3. **A test asserts the runtime never reads `upstream`** — the field is loaded,
   carried and published, and no request is built from it. That is the only way
   the two meanings stay separate, because they are both correct-looking URLs.

## Alternatives rejected

**Change `lock` to emit the internal address.** It would make the docstring true
and put `http://postgrest:3000` into a deployed document whose every other
address is public and externally meaningful. `outputs.json` is the document two
operators and three planes read; a Docker service name in it is a value that is
true only from inside one network, which is precisely the confusion this ADR
exists to end.

**Have the runtime dial the public URL.** It makes an internal authorization
call depend on public DNS, a hairpin back through the host's own public IP, the
edge router, and a certificate — for a hop between two containers on the same
bridge. Every one of those is a new failure mode for the request that decides
whether a caller may proceed at all.

**Carry both in the lock.** Two addresses in a compiled artefact, one of which
must never be used, is the same trap with an extra step — and it would put an
internal address in the deployed document anyway.

## Consequences

- **The compiler's docstring changes and the field does not.** No schema bump
  and no recompilation: the bytes are identical, and what moved is a sentence
  about what they mean.
- The runtime holds two addresses with different jobs — one it dials, one it
  publishes — and the test that forbids dialling the second is what keeps them
  from collapsing into each other.
- A future session that wants the agent plane to reach a *different* project's
  API surface has the honest starting point: `upstream` already names it, and
  nothing about that is a dial string yet.
