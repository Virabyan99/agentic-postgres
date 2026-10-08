# 0262 — The secret store is self-hosted Infisical on its own host

- **Status:** Accepted
- **Date:** 2026-10-09
- **Session:** 38, migration Run M1 (`docs/plans/session-38-migration-plan.md`;
  D2223, D2239, D2250, D2258, D2261)
- **Affects:** `infra/secret-store/` (new), `tests/contract/test_secret_store_files.py`
  (new, `REC-STORE-001`, registered in Run M3), `docs/secret-store.md` (new),
  `bin/session-01-check.sh` and `bin/session-38-check.sh` (shellcheck reaches the
  store's script), every host's `host.yaml` `infisical` block (from Run M4).
- **Related:** ADR 0010 (secrets are files in immutable generations), ADR 0110
  (no command creates a bucket), ADR 0188 (the mirror does not survive the loss
  of the Infisical project), ADR 0189 (the kit names every secret and holds
  none), ADR 0255 (the 429 budget), ADR 0257 (one identity per project).

## Context

Every project's every secret — role passwords, signing keys, the R2 and B2
key pairs and the pgBackRest cipher pass — lives in one Infisical project per
deployed project (`secrets.required.yaml`). Until now that was Infisical Cloud's
free plan: four machine identities, all four in use (D2146), 120 secret
operations a minute (D2139). Session 38's slot needs a fifth identity, and every
later slot one more (ADR 0257). Infisical prices its paid plan per identity —
about $120 a month for this deployment — which the operator declined on
2026-10-08 (D2223).

Infisical's core is MIT-licensed. An unlicensed self-hosted instance sets no
identity, member or project limit (`getDefaultOnPremFeatures`: `identityLimit:
null`, read 2026-10-08), keeps machine identities and Universal Auth, and
enforces no API rate limit by default. What it withholds — audit-log retention,
custom roles, SSO, secret rotation, dynamic secrets — the product uses none of.

## Decision

1. **The secret store is Infisical, self-hosted, on a host of its own**
   (`15.204.66.146`, OVH US-West; 2 vCPU, 3,814 MiB, 38 GB, Ubuntu 26.04), at
   `https://secrets.agenticpostgresql.com`. It runs nothing of the release and
   the release runs nothing of it.
2. **Its files are `infra/secret-store/`**: the backend, PostgreSQL 16 and Redis
   7.4 in one compose project with every image a tag pinned by digest (the
   newest tag at least two weeks old on the day it is chosen); Caddy as the
   edge. An upgrade moves a digest in a reviewed commit, after a backup.
3. **Who reaches it is decided by ufw, not by Docker** (D2250). Caddy runs on the
   host network; the backend publishes `127.0.0.1:8080` only; the database and
   Redis publish nothing. ufw admits 22 (key-only) and 80 (the HTTP-01 challenge
   and a redirect) from anywhere, and 443 only from the hosts that read secrets.
   The operator reaches the console through SSH.
4. **Its keys are the operator's.** `ENCRYPTION_KEY` and `AUTH_SECRET` are
   generated on the store host at the operator's terminal into
   `/etc/secret-store/infisical.env` (root, 0600) and copied to the operator's
   password manager and one offline copy before the stack first starts. They
   never enter a kit (ADR 0189), a repository file, a record or a conversation
   (D2239). Each container reads one env file: the backend
   `infisical.env`, the database `db.env`.
5. **It is backed up nightly and the backup is unreadable on the host that
   wrote it** (D2258). `pg_dump --format=custom` inside the database container
   is piped straight into `age --recipient`; the host holds only the recipient,
   the operator holds the identity. Fourteen copies stay on the host; each new
   one goes to the B2 bucket `apg-secret-store-backup` under a key restricted
   to that bucket, and its size is read back.
6. **Its restore is rehearsed before any project depends on it**, and again
   before the first project's secrets move: a backup decrypted on the
   workstation and restored into a throwaway compose project on the same host,
   then read.

## Consequences

- **ADR 0188's sentence now names a host.** Losing this host without its backup
  and its `ENCRYPTION_KEY` loses every project's cipher pass, and with it every
  backup. The backup, the key's two copies and the rehearsed restore are the
  whole defence; a second instance is not built (an open item).
- The identity limit and the per-minute ceiling stop shaping the product's
  plans: D2146 is void (D2255). ADR 0255's 429 budget stays, unused.
- One more host to patch: `unattended-upgrades` and the pinned digests are its
  maintenance, written in `docs/secret-store.md`.
- A project's provider project moves to this store by value, on the host that
  runs it (ADR 0263), before any host move.

## Measured (Run M1's rig, 2026-10-09, the committed compose file on the workstation)

The backend answered `/api/status` 200 after 130 s on its first start
(migrations included) and settled at 766 MiB resident (cap 1,536), PostgreSQL
133 MiB (768), Redis 5 MiB (256). `caddy validate` accepted the Caddyfile. A
`pg_dump | age` pass wrote 4.3 MB beginning `age-encryption.org/v1`; decrypted
with the identity and restored into a second database, it read the same 764
tables.
