# 0065 — A version is not a configuration, and a measured set records both

Status: accepted
Date: 2026-08-12
Session: 5, Run 9
Amends: [0050](0050-the-reviewed-api-surface.md)
Affects: API-CONTRACT-001

## Context

`openapi_normalize.KNOWN_TOP_LEVEL` is an exact set, not a floor, and says so:

> Every top-level key the locked PostgREST emits, measured. […] A PostgREST
> upgrade is *expected* to fail here, and the repair is to re-measure and
> re-approve, not to widen the set.

The first capture from a real deployment refused the document:

```
api-contract: the document carries top-level ['security', 'securityDefinitions'],
which this normalizer has never seen. A PostgREST upgrade is expected to fail
here…
```

There was no upgrade. The version is the digest the lock names, unchanged since
Run 4. The set was measured against a throwaway rig running that same image
under a **different configuration** — one that did not set
`openapi-security-active`.

Measured on the locked image (`postgrest:v14.16@sha256:bea1c76a…`), three arms,
JWT secret held constant across all three so it cannot be the explanation:

| `PGRST_OPENAPI_SECURITY_ACTIVE` | top-level keys |
|---|---|
| `true` (what `compose.yaml:585` sets) | the eleven, **plus** `security`, `securityDefinitions` |
| unset | the eleven |
| `false` | the eleven — byte-identical to unset |

A prior rig ruled the JWT secret out directly: with and without
`PGRST_JWT_SECRET`, and `openapi-security-active` unset in both, the two
documents carried the same eleven keys and neither carried `security`.

The emitted content is fixed:

```json
"security": [{"JWT": []}],
"securityDefinitions": {
  "JWT": {
    "type": "apiKey", "in": "header", "name": "Authorization",
    "description": "Add the token prepending \"Bearer \" (without quotes) to it"
  }
}
```

`PGRST_OPENAPI_SECURITY_ACTIVE: "true"` was set in Run 4 and is asserted by
`test_postgrest_service.py:169`. That test checks the *setting*. Nothing ever
measured what the setting does to the document, and it is the only `PGRST_*`
entry in its block carrying no comment while every neighbour carries a measured
justification.

## Decision

**The measured set records a version *and* a configuration, and the two keys are
required rather than tolerated.**

Three changes to `openapi_normalize`:

1. `security` and `securityDefinitions` join `KNOWN_TOP_LEVEL`.
2. Both join a new `REQUIRED_SECURITY_TOP_LEVEL`, so their **absence** is a
   refusal. A capture taken from a deployment with `openapi-security-active` off
   would otherwise normalize cleanly into a snapshot describing an API that
   announces no authentication at all — the same class of failure
   `REQUIRED_SCHEMES` exists to catch, where a capture without the proxy URI
   carries `["http"]`.
3. `security` is asserted equal to `REQUIRED_SECURITY = ({"JWT": []},)` in code.
   `securityDefinitions` is **not** asserted; it is carried into the snapshot as
   content.

The split between (3)'s two halves is the module's existing one. `security` is
the *requirement* — every operation is behind the `JWT` scheme — and a document
that drops it, or names a different scheme, is a different security posture
arriving as a diff a reviewer can approve with a glance. `securityDefinitions`
is the *description* of how to send the credential: a header name and an English
sentence. Description belongs in the snapshot, which is what the snapshot is
for, and a PostgREST that reworded it should produce a reviewable diff rather
than a refusal.

The docstring on `KNOWN_TOP_LEVEL` is corrected. "A PostgREST upgrade is
expected to fail here" was true and incomplete: a configuration change to the
*same* version is expected to fail here too, and that is what happened.

## Alternatives

**Widen the set and carry both keys through as ordinary content.** Simplest, and
rejected: it makes the two keys optional in practice. A deployment that lost
`openapi-security-active` would publish a document announcing no authentication
and the normalizer would have no opinion, which is the shape ADR 0050 was
written against.

**Turn `openapi-security-active` off so the document matches the normalizer.**
Rejected, and worth stating because it is the cheapest fix on the table: it
resolves a conflict by making the product worse. The keys are how a generated
client, a documentation page and a human reading the document learn that a
bearer token is required. Removing them to satisfy a set measured against a rig
is the normalizer dictating the product's contract.

**Assert the `securityDefinitions` content in code as well.** Rejected as
over-fitting. The `description` string is prose from an upstream project; pinning
it in source turns a routine upstream wording change into a normalizer refusal
with no reviewable artifact, where the snapshot already gives one.

## Consequences

- The first snapshot approved under this ADR carries `security` and
  `securityDefinitions`. Every project's capture carries them identically —
  they are neither project-specific nor sentinel-substituted.
- A deployment with `openapi-security-active` off can no longer produce an
  approved snapshot. That is intended.
- The rule this generalizes is in the divergence table as D188: **a set measured
  against a rig records the rig's configuration, not the product's.** Every
  constant in this module derived from a throwaway rig is suspect until it has
  seen a capture from a deployment, and this is the first one that has.
