# 0123 — The published protocol revision is the highest the runtime implements

Status: accepted
Date: 2026-08-20
Session: 8, Run 4
Affects: ADR 0121, D406, D413, D428, `schemas/outputs.schema.json`,
`src/agentic_postgres/deployed_output.py`, `services/auth-api/app/mcp_runtime.py`

## Context

Outputs v12 added `mcp.protocol_revision` in Run 1, and described it as:

> The MCP protocol revision the deployed runtime actually **negotiated**, read
> FROM the runtime and never from a document that hoped for one.

The second half of that sentence is the right instinct and D406 states it as a
rule. The first half names the wrong quantity, and Run 4 is the first run in a
position to notice, because it is the first one with a running server to ask.

## What was measured

A FastMCP 3.4.0 server, served over HTTP, handed a real `initialize` request.

| arm | client asked for | server answered |
|---|---|---|
| H1 | `2025-11-25` | `2025-11-25` |
| H2 — CONTROL | `2025-03-26` | **`2025-03-26`** |

H2 is the whole finding. **A negotiated revision is a fact about the client**,
not about the runtime: the same server answers whatever a caller asks for, as
long as it is a revision the server supports. A field filled from one handshake
would record the version of the *probe that measured it*, and would move when
the probe moved while the deployment did not.

What the framework itself reports, read from the locked version:

- `mcp.types.LATEST_PROTOCOL_VERSION` → `2025-11-25`
- `mcp.shared.version.SUPPORTED_PROTOCOL_VERSIONS` →
  `['2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25']`
- `mcp.types.DEFAULT_NEGOTIATED_VERSION` → `2025-03-26`, which is what a client
  that sends no version at all receives

Three plausible values, one field. `DEFAULT_NEGOTIATED_VERSION` is the trap: it
is the lowest thing a lazy caller gets, and it is two revisions behind what the
runtime can do.

Measured at the same time, and it belongs to a different field: with a bare
`TokenVerifier`, a 401 carries **no `WWW-Authenticate` header**. RFC 9728 and the
MCP authorization specification require one. So
`authorization_spec_conformant: false` now has a **measured** reason rather than
a prose one — which is D413's whole complaint about that field answered with an
observation.

## Decision

**`mcp.protocol_revision` is the highest revision the runtime implements, read
from the framework's own constant at startup.**

1. The runtime reads `LATEST_PROTOCOL_VERSION` from the installed framework and
   publishes it. It is never a literal in this repository, and never a value
   copied from a lock entry, a runbook or an ADR — including this one. The
   `2025-11-25` above is a record of what was measured, not a source.
2. The schema's description is corrected: *negotiated* becomes *implemented*,
   with the reason. The date-shaped pattern stays and still asserts nothing about
   which revisions exist.
3. `authorization_spec_conformant` is published `false`, and the measurement
   behind it is the missing `WWW-Authenticate` challenge rather than a sentence
   in a runbook.

## Alternatives rejected

**Publish the negotiated revision from a probe handshake.** Refused by H2: it
measures the probe. It is also the exact defect class this repository keeps
producing — a value that looked measured and was not, passing for as long as the
probe's request happened to coincide with the runtime's ceiling.

**Publish `DEFAULT_NEGOTIATED_VERSION`.** It is a real constant with a real
meaning, and it is the answer to a different question: what an unversioned client
gets. Published as *the* revision it would understate the deployment by two
revisions, and a reader deciding whether a client can connect would get the wrong
answer in the safe direction — which is still the wrong answer.

**Publish the whole supported list.** Honest, and a schema change (a v13 bump)
bought for information nothing consumes. The field's consumer is a reader asking
"what does this speak"; the ceiling answers it. If a consumer ever needs the
floor, that is the moment to widen the member, with the bump it costs.

## Consequences

- **The field cannot be filled by an observation probe**, so nothing in the
  deployment pipeline may fill it by asking the server. It comes from the runtime
  reporting its own framework's constant, alongside the tool count and the two
  checksums.
- **A framework bump moves this field**, which is correct and is the reason it is
  not written down anywhere a bump would miss. ADR 0121 pins the framework at a
  measured ceiling, so the two move together and deliberately.
- A test asserts the runtime does not carry a hard-coded revision string, because
  the failure mode here is a plausible constant that agrees with the framework
  right up until it does not.
