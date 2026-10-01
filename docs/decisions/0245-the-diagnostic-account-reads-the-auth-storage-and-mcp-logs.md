# 0245 — The diagnostic account reads the auth, storage and MCP logs, and its redaction knows a JSON key

- **Status:** Accepted
- **Date:** 2026-09-30
- **Session:** 35, Run 1 (D380, D1879)
- **Affects:** `bin/apg-diag.sh` (`SERVICES`, `redact()`),
  `tests/contract/test_diagnostic_surface.py`, the host's installed copy
  `/usr/local/bin/apg-diag` (re-installed on Session 35's trip, Sheet F4b),
  `infra/host/apg-agent.sudoers` (unchanged).
- **Related:** ADR 0071 (the read-only diagnostic account), ADR 0237 (the
  inbound route logs a refusal and writes nothing), D380, D1528.

## Context

`apg-diag` is what the unprivileged `apg-agent` account runs through one
sudoers rule (ADR 0071). Its log verb accepts a closed list of services,
`postgres pgbouncer postgrest docs edge-probe dbmate`, fixed since Session 7;
`auth`, `storage` and `mcp` were left out because widening what the account
sees was judged *"an ADR's shape rather than a one-line allowlist edit"*
(D380). Nothing pins the list.

Since 1.12.0 that gap has a consequence: a refused inbound connector request is
recorded ONLY in the auth service's log — deliberately, because a refusal that
wrote a row would be a write an unauthenticated caller could cause (ADR 0237).
The one account meant for diagnosis cannot read the one record of a refusal.

The redaction `apg-diag` applies (`(password|secret|token|pgpass)([=: ]+)…`)
was written for PostgreSQL's and PostgREST's text logs. The three services
log JSON, where a key is quoted — `"token": "…"` — so the closing quote sits
between the key and the colon and the existing rule does not match.

## Decision

1. `SERVICES` becomes exactly `postgres pgbouncer postgrest docs edge-probe
   dbmate auth storage mcp`, and a proof pins it EXACTLY.
2. `redact()` gains one rule beside its three: a JSON-quoted key named
   `password`, `secret`, `token`, `pgpass`, `authorization` or `api_key`
   (case-insensitive) has its quoted value replaced by `"<redacted>"`. The
   proof feeds lines in the three services' real log shapes, read from
   `services/auth-api/app/`'s logging, through it.
3. The 200-line cap stays. The sudoers rule does not change; the installed
   copy is re-installed on the trip (`sudo install -o root -g root -m 0755
   bin/apg-diag.sh /usr/local/bin/apg-diag`) and read as `apg-agent`.

## Alternatives rejected

- **A connector-only log reader.** A second diagnostic surface with its own
  rule, for one service's lines.
- **Structured-log parsing.** `apg-diag` is a shell reader and stays one; a
  parser is a program the account would run as root.

## Consequences

- The diagnostic account now reads three more services' logs, each still
  capped and redacted. The services already log no credential by design; the
  redaction is the belt, and it now fits the format they log in.
- `apg-diag`'s standing account still has no lifetime (D1528).
