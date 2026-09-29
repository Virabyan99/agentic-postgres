# 0237 — The inbound route verifies a signature over the delivery before it reads anything else, and every connector key is derived from one facility-gated secret

- **Status:** Accepted
- **Date:** 2026-09-29
- **Session:** 34, Run 1 (D1784, D1785, D1787, D1788, D1789, D1804; rig 34b)
- **Affects:** `secrets.required.yaml` (`connector_signing_key`),
  `src/agentic_postgres/secrets_contract.py` (`FACILITY_CONNECTORS`),
  `src/agentic_postgres/config.py` (`connectors_enabled`),
  `schemas/project.schema.json` (7), `schemas/outputs.schema.json` (19),
  `src/agentic_postgres/output_migrations.py`,
  `src/agentic_postgres/connector_keys.py`,
  `services/auth-api/app/connector_signature.py`,
  `services/auth-api/app/connector_body.py`,
  `services/auth-api/app/connector_routes.py`, `bin/connector.py key`.
- **Related:** ADR 0002 (derive an identity once), ADR 0162 (what a bump
  permits), ADR 0188 (a facility), ADR 0225 (a secret's value checked against
  its kind), ADR 0236 (the connector), ADR 0238 (the same scheme outbound).

## Context

The stage plan: *"an inbound request is signature-checked before any database
is touched"*; *"a signature over a shared secret, a replay window keyed on the
delivery id"*; and *"a worker that needs a new secret with no default is
`secret_required_added`, a major"*. Secrets are static per release; a new
`required: true` secret moves every rendered document's `required_names` and is
auto-classified major. An optional secret cannot reach a container. A
facility-gated secret is owed only by a project with the facility and is
required there by construction. There is no HMAC and no JSON-schema validator
in the auth image today, and `routes._body` parses before it validates.

**Rig 34b measured the scheme** from inside an auth image built from this
checkout with every build argument read from `versions.env` (`sha256:4a7a337e…`):
HMAC-SHA256 under a fixed 32-byte key over `1727600000.<uuid>.<body>` gave
`3c87822a…` from the image's Python, the workstation's Python and `openssl dgst
-sha256 -mac HMAC -macopt hexkey:…` alike; a one-byte change in the body gave
`0c80f3a0…` from all three.

## Decision

1. **One scheme, both directions**: headers `X-Apg-Delivery: <uuid>`,
   `X-Apg-Event: <name>@<version>` (outbound only), `X-Apg-Signature:
   t=<unix seconds>,v1=<64 lowercase hex>`; the signed bytes are
   `f"{t}.{delivery_id}.".encode("ascii") + body`; HMAC-SHA256 under the
   connector's derived key; compared with `hmac.compare_digest`; ±300 s.
2. **The route's order is fixed and proved**: (1) the name matches
   `^[a-z][a-z0-9-]{0,62}$`, else 404; (2) the key file is present, else 404;
   (3) the raw body is at most 16 KiB, else 413; (4) both headers parse, the
   timestamp is inside the window and the HMAC matches, else ONE fixed 401
   `{"error": "signature_invalid"}` for every cause; (5) only now
   `strict_json.parse_object`, else 400; (6) only now the database. A proof
   drives the route with a repository that raises on ANY call.
3. **No router, no route prefix, no deployed-document field for the route**:
   `POST /connectors/{name}` on the auth application, reached at
   `https://<domain>/api/app/connectors/<name>` through the existing prefix
   router; the edge's rate limit and body cap apply.
4. **One secret, facility-gated**: `connector_signing_key` (`provider_key
   APG_CONNECTOR_SIGNING_KEY`, `/auth`, generated `random_hex`, `facility:
   connectors`, one consumer — `auth`, `connector_signing_key`, 65532:65532,
   0400, raw — `redaction: full`, `rotate_by_replacement: true`).
5. **Each connector's key is DERIVED, never stored**:
   `hmac.new(bytes.fromhex(master), b"apg-connector-key-v1\x00" +
   name.encode("ascii"), hashlib.sha256).hexdigest()`, written twice —
   `src/agentic_postgres/connector_keys.py` and
   `services/auth-api/app/connector_signature.py` (ADR 0093 forbids `bin/`
   importing a service module) — and a proof holds the two together on fixed
   vectors.
6. **The facility is one fact with one reader**: project manifest schema 7
   adds `connectors: {enabled, endpoints}` (forbidden below 7);
   `config.connectors_enabled(document)` reads it from a manifest or a
   document; outputs schema 19 carries `connectors: {enabled}` on both
   branches, migrated from 18 with `false`. `endpoints` enters no document.
7. **An inbound body is a CLOSED SUBSET**: at most 16 members, each `string`
   (with `max_length`), `integer` (with bounds) or `boolean`, `required` or
   not, no nesting, no extras. The host validates the FILE with
   `schemas/connector.schema.json`; the service validates a BODY with its own
   small validator; a proof feeds both the same cases.
8. **The key reaches a sender through `sudo bin/connector.sh key --output
   FILE`** — a new 0600 root file, never stdout, the path derived from the
   active generation.

## Consequences

- A project that declares no connectors owes nothing new, so the release stays
  minor by declaration (`document_schema_migratable`).
- Rotating `APG_CONNECTOR_SIGNING_KEY` (a provider replacement and a redeploy)
  changes EVERY connector key of that project at once; operator guide §18 says
  so.
- One 401 for every cause tells a prober nothing; signing the delivery id stops
  a captured body being replayed under a fresh id inside the window.

## Alternatives rejected

- **A secret per connector in `secrets.required.yaml`** — secrets are static per
  release.
- **A required secret** — prices the release at major.
- **Keys in the database** — a plaintext credential in every backup, and a
  database read before the signature.
- **JSON Schema in the image** — an unpinned transitive dependency for a
  subset.
