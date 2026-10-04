# 0253 — Management API keys, the `/v1` contract and the CLI's state

- **Status:** Accepted
- **Date:** 2026-10-04
- **Session:** 37, Run 1 (D2052, D2057, D2066)
- **Affects:** `KEY-MINT-001`, `KEY-USE-001`, `CTL-API-001`, `CTL-CLI-001`
  (registered by Run 9). The control mode's key routes,
  `projects/control/migrations/` (`control_keys`),
  `contracts/control-openapi.canonical.json`, `bin/app-contract.py` and
  `bin/app-contract.sh` (`--snapshot app|control`), `bin/login.sh`,
  `bin/logout.sh`, `bin/context.sh`, `bin/org.sh`, `bin/project.sh`.
- **Related:** ADR 0251 (the control plane), ADR 0252 (accounts and roles),
  ADR 0093 (a `bin/` command imports only `agentic_postgres` and `yaml`;
  `app-contract.py` is its one checkout-only exception), ADR 0218 (no product
  child reads the terminal), `one_time_tokens.py` (*"unsalted and deterministic
  on purpose"*), `profile.py` (the frozen Argon2id profile and
  `HASH_CONCURRENCY`), `docs/threat-model.md` hosted items 2 and 10,
  `docs/plans/stage-5-plan.md` D1952.

## Context

D1952 asks for management API keys `apg_` + 32 random bytes, Argon2id-hashed
like an agent secret, shown once, scoped from a closed vocabulary, owned by a
member and revoked with them; `/api/v1` frozen as a fifth contract with a
`--check`; and the CLI as a client of `/api/v1` with a context file.

An agent secret is Argon2id-verified once per 900-second token exchange. A
management key is presented on every request. Rig 37c measured both checks on
the workstation (12th Gen Intel Core i3-1215U), 20 verifications of a
43-character secret each:

| Check | Median | p95 | Memory |
|---|---|---|---|
| Argon2id at `profile.FROZEN` (64 MiB, t=3, p=1) | **229.8 ms** | 245.4 ms | peak RSS 20.9 → 85.1 MiB |
| SHA-256 + `hmac.compare_digest` (the control) | **0.8 µs** | 29 µs | — |

The service runs at most `HASH_CONCURRENCY = 2` Argon2id computations at once,
so a per-request Argon2id check would cap the whole control plane at two
key-authenticated requests in flight, each allocating 64 MiB and taking about a
quarter of a second — a denial of service the product would hand itself. The
tree already stores 256-bit random tokens as unsalted SHA-256, on purpose
(`one_time_tokens.py`): a slow hash buys nothing against a secret nobody can
guess.

## Decision

1. **A key is `apg_<key_id>_<secret>`** (D2052): `key_id` 16 lowercase hex
   (8 random bytes, the lookup), `secret` `secrets.token_urlsafe(32)` (43
   characters, 256 bits). `app.control_keys` stores `key_id`, the secret's
   SHA-256 hex, the owning member, the organisation, `scopes text[]`,
   `created_at`, `last_used_at`, `revoked_at`. The check is a SHA-256 and
   `hmac.compare_digest` — **never Argon2id** — and the key is shown once, in
   the `201` body, with `Cache-Control: no-store`.
2. **The vocabulary is exactly the scopes a Session 37 route checks**:
   `organizations:read`, `members:read`, `projects:read`, `operations:read`.
   Each later session adds its own with its route (`projects:write` in 38, …).
   A key's scopes are a subset of the vocabulary and of what its minter's role
   grants at minting.
3. **Effective scopes are computed on every request**: the key's scopes ∩ what
   its owner's CURRENT role grants. A revoked key, and a key whose owner left the
   organisation, get `401 authentication_failed` on the next request; nothing
   is cached.
4. **A key mints nothing.** Keys, invitations, factors and role changes are
   human-session routes; a key gets `403 human_session_required` there, so a
   leaked key cannot mint its successor, and *a key's scopes never exceed its
   minter's* holds across time, not only at minting.
5. **The contract** (D2057). `bin/app-contract.sh` writes and checks TWO
   snapshots: `contracts/app-openapi.canonical.json` (unchanged: `auth` and
   `storage`) and `contracts/control-openapi.canonical.json`
   (`create_app("control").openapi()`, the `/v1` paths only, titled *Agentic
   Postgres management API*). `--update` gains `--snapshot app|control`
   (default `app`, so every existing caller is unchanged); `--check` checks
   both. **No new command**: ADR 0093's checkout-only allowlist keeps its one
   entry, and the gate already calls `--check`.
6. **The CLI's state** (D2066) is `${XDG_CONFIG_HOME:-$HOME/.config}/apg/`,
   created 0700 and refused if it is a symlink, another owner's, or wider. It
   holds `context.json` (0600: `endpoint`, `organization`, `project`, and
   EITHER `key_file` — the PATH of a 0600 key file, never the key — OR
   `session: true`) and, for a password login only, `session.json` (0600: the
   refresh token and its expiry; the access token is never written). Writes are
   `O_WRONLY|O_CREAT|O_TRUNC|O_NOFOLLOW` to a temporary name, then
   `os.replace`. **A secret enters only through a 0600 file whose mode is
   checked** (`--password-file`, `--key-file`, `--invitation-file`) **or a
   TTY** (`getpass`); the TOTP code through `--totp-code-stdin` or a TTY.
   **https only**, except `http://127.0.0.1` and `http://localhost` for tests.
   `apg logout` revokes the session server-side (`DELETE /v1/sessions/current`)
   and removes `session.json`; a key context is forgotten, never revoked (`apg
   org key-revoke` revokes).

## Alternatives rejected

- **Argon2id per request** — measured above; it turns the control plane's
  concurrency into the hasher's.
- **Argon2id at minting and a cached verification.** A cache is a second
  revocation path that can disagree with the first; property 3 forbids it.
- **`bin/control-contract.sh` as a second checkout-only command.** It would
  widen ADR 0093's allowlist for a job the existing command does.
- **The key itself in `context.json`.** Two copies of a secret; the person's own
  file is the one copy.
- **A `--token` or `--api-key` flag.** A secret in argv is visible to every
  process on the machine, and `test_cli_contract.py` refuses such a flag in any
  `--help`.

## Consequences

- A database dump reveals key digests, not keys; a 256-bit secret is not
  recoverable from its SHA-256.
- A refresh token sits on the person's disk, 0600, revocable — the standard CLI
  trade; it is not a database credential and opens no project.
- Every later session that adds a `/v1` route adds its scope to the vocabulary
  and regenerates the control snapshot in the same commit.
