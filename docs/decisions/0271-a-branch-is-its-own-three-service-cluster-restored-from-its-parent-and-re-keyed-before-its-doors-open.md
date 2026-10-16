# 0271 — A branch is its own three-service cluster, restored from its parent and re-keyed before its doors open

- **Status:** Accepted; amended by Session 41 (the image resolved at start, the door, the reason, the budget; D2513-D2516, D2537)
- **Date:** 2026-10-14
- **Session:** 40, Run 1 (`docs/plans/session-40-implementation-plan.md`,
  D2422–D2432, D2434, D2436–D2441, D2449–D2451, and Run 1's rows D2454–D2460;
  the operator's answers of 2026-10-14)
- **Affects:** `src/agentic_postgres/naming.py` (`branch_names`,
  `branch_endpoint_hosts`), `src/agentic_postgres/branch_plan.py` (new),
  `src/agentic_postgres/restore_drill.py` (`assert_disposable` checks
  `archive_mode`, D2447), `src/agentic_postgres/capacity_probe.py` (branches on
  the committed line) — Run 2; `infra/branch/compose.yaml` and
  `bin/branch-runtime.sh|py` (new) — Run 3; the control set's `0006`,
  `services/auth-api/app/operations.py`, `control_routes.py`,
  `control_roles.py`, `errors.py`, `schemas/operation-arguments.schema.json` —
  Run 4; `bin/reconciler.py`, `src/agentic_postgres/reconciler_dispatch.py` —
  Run 5; `bin/branch.sh`, `bin/cloud.py` — Run 6. Requirements `BR-NAME-001`,
  `BR-PLAN-001`, `BR-REKEY-001`, `BR-CTL-001`, `BR-DISPATCH-001`,
  `BR-CAP-001`, `BR-CLI-001`, `BR-LIVE-001`, `BR-LIVE-002`.
- **Related:** ADR 0002 (derive an identity once), ADR 0151 (the drill,
  disposable by construction — whose argv the restore reuses), ADR 0192
  (D1010: pgBackRest writes `--config` into `restore_command`), ADR 0195 (three
  outcomes), ADR 0221/0222 (admission), ADR 0256 (the reconciler), ADR 0265 (a
  project returns at boot by its unit), ADR 0268 (the edge's 5432, one
  certificate per name pair), ADR 0269 (customer roles by verifier: *"Session
  40's re-key must rotate both customer roles before a branch's names open"*),
  ADR 0272 (a branch's expiry), ADR 0273 (the backups surface).

## Context

The stage plan's D1961 calls a branch *"a child deployment of its project …
restored from the parent's repository at a target time … re-keyed before its
endpoint opens"*. Read against the tree (D2422), a branch cannot be a deploy:

- A restored volume carries the parent's `app_private.project_identity`, and
  `bin/postgres-bootstrap.py` exits **11** for a volume whose identity names
  another key (`:953-997`). That guard is right and stays.
- A deploy needs the key's own active secret generation, materialized from the
  key's own Infisical project (`naming.py:1293`), which only a
  provider-administering credential creates (D1953).
- Compose profiles are cumulative by session (`project-runtime.sh:107-117`):
  no facility drops auth, REST, MCP, docs or the collector from a deployed
  project, and none of them has a job in a copy whose promise is *a Postgres
  database at a point in time*.

The drill (ADR 0151) already restores a project's repository into a volume of
its own, through the parent's own mounts read-only, and tears it down. A
branch is that restore made to live — with the two properties the stage plan's
§8 states: *a branch starts re-keyed and cannot write its parent's repository*.

## Measured

Rig 40a (2026-10-14, `~/s40/run1/rig40/rig40a.py`, attempt 3; attempts 1–2
kept): the project's own image (`services/postgres`, built from `versions.env`'s
three arguments: PostgreSQL 18.4, pgBackRest 2.59.1), a parent bootstrapped by
`build_statements` and the release's 43 migrations, the customer roles given
verifiers by `agentic_postgres.scram`, archiving to a **POSIX** repository —
the product's own rendered `pgbackrest.conf` with exactly its four `repo1-s3-*`
lines dropped and `repo1-type=posix` — one full backup (32.2 MB), two marked
rows 3 s apart.

- **(a) A restore to T1** (`--type=time --target-action=promote`) through a
  one-shot container mounting the repository and both configuration paths
  **read-only**, then a recovery container (`archive_mode=off`, the same
  read-only mounts): restore 11.1 s, promoted 3.1 s; **row 1 present, row 2
  absent**; reached `pg_last_xact_replay_timestamp()` = row 1's commit.
- **(b) `--type=default`**: restore 12.1 s, promoted 3.2 s; **both rows**;
  reached = row 2's commit.
- **(a0) The ISO `T` form of the same instant is refused** before anything is
  written: `ERROR: [029]: automatic backup set selection cannot be performed
  with provided time '2026-10-14T08:04:56.104356+00:00'`, *"time format must be
  YYYY-MM-DD HH:MM:SS with optional msec and optional timezone"*, exit 29
  (D2454). Attempt 1 lost every time case to it.
- **(c2) A target after the last commit but inside the archived WAL**, and
  **(c) one an hour ahead**: pgBackRest exits 0; the recovery instance logs
  *"last completed transaction was at log time <row 2's commit>"* then `FATAL:
  recovery ended before configured recovery target was reached` and the
  container exits 1 within 3 s (D2456).
- **(d) A target before the full backup**: `ERROR: [075]: unable to find backup
  set with stop time less than '…'`, exit 75, 1.1 s — the bound is the oldest
  set's **stop** time, not its start (D2457).
- **(e) The persistent phase** on (a)'s volume — no repository mount, no
  configuration mount, only an `internal` network, `-c archive_mode=off -c
  archive_command=/bin/false`, `small`'s settings and `--memory 512m --cpus 1.0`:
  started, not in recovery, `SHOW archive_command` = `(disabled)`,
  `pg_stat_archiver` 0/0 after a write and a WAL switch; no `recovery.signal`;
  `postgresql.auto.conf` still holds pgBackRest's `restore_command`,
  `recovery_target_time` and `recovery_target_action` — inert without a signal
  file (D2459).
- **The repository** (file count and newest mtime, read through a read-only
  mount with the parent stopped): **1,423 files, unchanged** across (a0)–(e).
  **Control (e')**: the same promoted copy started WITH the repository mounted
  read-write, on the backup network, `archive_mode=on` → after one write and a
  switch, **1,424**: `…/18-1/0000000200000000/000000020000000000000009-….gz`, a
  timeline-2 segment pushed into the parent's archive. That file is what a
  mis-built branch does to its parent; its absence is the property.
- **(f) The re-key** (19 statements, one transaction, as `postgres` over the
  local socket, 0.31 s). BEFORE, from a peer container on the branch's
  network: the parent's `customer_app`, `migration_user` and superuser passwords
  **accepted**; a wrong password refused (SCRAM decides). AFTER: the parent's
  `customer_app` password **refused** (`password authentication failed`),
  `migration_user` and the superuser over TCP **refused**, both customer roles
  with the branch's own verifiers **accepted**; `docker exec … psql -U
  postgres` still works; `UPDATE 2` live refresh families revoked and `UPDATE 1`
  unexpired agent credential expired (the already-expired one untouched); LOGIN
  roles after: the two customer roles at limit 2, and `postgres`.
  `revoked_reason = 'branch'` is refused: `invalid input value for enum
  app_private.refresh_revocation` (D2455). The parent's `pg_hba.conf`, copied
  into the branch, is the image's initdb: `local` and `127.0.0.1`/`::1`
  **trust**, then `host all all all scram-sha-256` — so a login over loopback
  INSIDE the container succeeds with any password (attempt 2 read that as a
  failed re-key; it is D2458), and every network peer meets SCRAM.
- **(g)** Parent before and after: timeline 1, the same `system_identifier`
  and `instance_uuid`, both rows. Branch: **timeline 2, the parent's
  `system_identifier` and `instance_uuid`** (ADR 0151's residual).
- **Rig 40c** (the branch's three containers through the product's own pooler
  entrypoint, read-only, uid 70, `--memory 64m --pids-limit 64`; userlists read
  back from `pg_authid` — a second, differently salted verifier fails every
  login through SCRAM passthrough, D2460): idle `postgres` 21.0 MiB / pids 9,
  poolers 1.2 MiB each; **20 pooled clients, all answered** (`default_pool_size`
  2): 24.2 MiB / 11, pool 1.6 MiB; after, 28.1 MiB / 13. The direct door admitted
  the branch's administrator and refused the parent's password (`SASL
  authentication failed`).
- **Rig 40b** (Pebble + challtestsrv at Session 39's digests, which the registry
  still serves; Traefik 3.7): two label TCP routers `dev.pool.a.test` /
  `dev.direct.a.test` with `tls.domains[0]` and `tls.certresolver` → **one
  order**, one certificate naming both (serial `181af6883ca83c77`); both
  containers removed and created again with the same labels → **orders still 1,
  the served serial equal** — the stored certificate is reused; **control**:
  `qa.pool` / `qa.direct` → order 2, a new serial. Let's Encrypt's published
  limits, read 2026-10-14 (page *last updated August 5, 2026*): **5 certificates
  per exact set of identifiers per 7 days** (refill one per 34 h), **50 per
  registered domain per 7 days** (one per 202 min), 300 new orders per account
  per 3 h.

## Decision

1. **A branch is its own compose project, not a deploy** (D2422):
   `infra/branch/compose.yaml`, exactly three services — `postgres` (the
   parent's running image, by id), `customer-pool` and `customer-direct`
   (`${PGBOUNCER_IMAGE}`, the product's pooler entrypoint) — on two networks of
   its own (`edge`; `internal`, `internal: true`). It holds **no secret of its
   own**, has **no systemd unit**, publishes **no port**, and runs no auth,
   REST, storage, MCP, docs, metrics or backup. A root command,
   `bin/branch-runtime.sh` (`create|reset|delete|start|status`), runs it and
   records it in `/etc/agentic-postgres/branches/<key>/<branch>/branch.json`.
   The identity sentinel is **kept**: a product bootstrap aimed at a branch
   volume still exits 11.
2. **Names** (D2423): `naming.branch_names(key, branch)` derives every name
   from the stem **`apg-<key>_<branch>`** — a project key never holds `_`, so a
   branch stem can equal no project's and no drill's (`apg-<key>-restore-<id>`).
   A branch name is `^[a-z][a-z0-9]{1,11}$`; `main` is refused (it is the
   project).
3. **Three phases** (D2424), built and asserted by `branch_plan`:
   **restore** — `restore_drill.restore_arguments`'s argv and the drill's
   inherited mounts, read-only, into the branch's own volume; **recovery** — a
   `…-recovery` container with the same read-only mounts on the parent's backup
   network, `postgres -c archive_mode=off`, until `pg_is_in_recovery()` is
   false, then removed; **persistent** — the branch's `postgres` from the same
   volume with **no repository mount, no path into the parent's secret
   generation, no backup network, `archive_mode=off`,
   `archive_command=/bin/false`**. **`branch_plan.assert_branch_safe`** refuses,
   exit 7 before anything starts: the branch volume equal to or mounted by the
   parent; any writable inherited mount; `--delta`; a recovery command without
   `archive_mode=off`; a persistent service with any of the four forbidden
   members (D2426). The re-key step also `ALTER SYSTEM RESET`s
   `restore_command`, `recovery_target_time` and `recovery_target_action`, so
   the branch's configuration names nothing of the parent's repository (D2459;
   measured by Run 3's cluster test).
4. **The point** (D2425, D2454, D2456, D2457): no target restores to the end of
   the archive (`--type=default`) and records the point reached
   (`pg_last_xact_replay_timestamp()`); `restore.create` requires one
   (`--type=time --target-action=promote`). An RFC 3339 instant from the API is
   rendered **`YYYY-MM-DD HH:MM:SS.ffffff+00:00`** before it reaches pgBackRest
   — never the `T` form. The recorded window (ADR 0273) is checked first; then
   `[075]` maps to exit 7 *"the point is before this project's oldest backup
   (<stop time>)"*, and the recovery's `recovery ended before configured
   recovery target was reached` to exit 7 *"the newest change in this
   project's archive is at <last completed transaction>; your point is after
   it"*, the volume removed. A live parent commits at least every 5 s (the
   workflow heartbeat, `POLL_SECONDS`), so that refusal is met only at the
   archive's last seconds.
5. **The re-key runs before any door exists** (D2427, D2455, D2458), one
   transaction through `container_exec.run` as `postgres` on the local socket:
   every role of `naming.database_roles(key)` but the two customer roles
   `NOLOGIN PASSWORD NULL`; the superuser `PASSWORD NULL` (the image's
   `pg_hba.conf` trusts the local socket and loopback INSIDE the container,
   which no network peer reaches; every peer meets SCRAM); `customer_app` /
   `customer_admin` `LOGIN CONNECTION LIMIT` small's 2/2 `PASSWORD` the
   branch's own verifiers, from the operation's arguments, on stdin; every live
   refresh family revoked with **`revoked_reason = 'administrative'`** (an
   existing value; no released migration, D912); every unexpired agent
   credential expired. Only then do the two poolers start — with userlists
   **read back from `pg_authid`** by the same reader `customer-credentials.py`
   uses (D2460) — and the edge attach. User password hashes are not touched: no
   auth service reads them in a branch and no customer grant reaches them.
6. **Hostnames** (D2428): `<branch>.pool.<domain>` and
   `<branch>.direct.<domain>` (`naming.branch_endpoint_hosts`, 253-character
   refusal), reached through two grey wildcard records per slot the operator
   creates once; `create` reads both with `slot.dns_reading` before admission
   and refuses exit 5 otherwise.
7. **Certificates** (D2429): one per name pair, by the branch poolers' labels
   exactly as a project's. A returning pair reuses the stored certificate
   (rig 40b), so `reset` and a re-created branch of the same name issue nothing;
   a NEW name costs one of the registered domain's 50 per week, shared by every
   project on the zone. With one branch per project, that is the arithmetic:
   a slot that created a new branch name every day would spend 7 of 50 a week.
   Certificates for deleted branches stay in `acme.json` (Session 41 inherits
   it).
8. **One live branch per project** (D2430): `BRANCHES_PER_PROJECT = 1`;
   `409 branch_limit_reached` from the route AND from the control database
   before an operation row exists. `OPERATION_ERROR_CODES` gains exactly that
   code. A capacity refusal stays `capacity_exhausted` from the branch's own
   admission (D2431).
9. **The charge** (D2431): every branch runs `small`'s database settings
   whatever its parent's profile and is charged `small`'s **192 MiB**
   (`shared_buffers 64 + maintenance_work_mem 32 + 2 × max_connections 48`) —
   the budget it could grow to, not the ~21–28 MiB rig 40c read resident;
   `capacity_probe.read` adds every readable `branch.json` to `committed` and
   names it; an unreadable one makes the reading `unreadable`.
10. **The parent's guards** (D2438): `branch.create|reset` and `restore.create`
    refuse a sleeping parent; `project.delete` is refused while the project has
    a recorded branch; `branch-runtime delete` removes exactly the names
    `branch_names` derives and the branch's state directory.
11. **Boot** (D2439): the reconciler's `start()` runs `branch-runtime.sh start
    --all`; a branch that does not come back is recorded `stopped`, never
    retried in a loop.
12. **What is not built**: no test-restore operation (a branch at a point IS a
    tested restore, D2432); one class, no promotion, no in-place restore
    (D2440, `not_offered`); a branch is **not backed up** (D2441);
    `restore.create` is `branch.create` with `target_time` required (D2434); no
    new key scope — branch and backups reads are `projects:read`, and **no key
    reaches a branch write** (corrected in Run 4, D2468: each carries the
    branch's own credentials, so a key that could create one could open a full
    copy of the data — the export case and ADR 0269's credential case at once);
    the writes are a person's, member and above, `branch.delete` admin
    (D2436); credentials are set at create and reset
    only, never by `credential.rotate` (D2449); the customer's nouns are `apg
    branch` and `apg project backups`, the operator's `backup.sh` and
    `restore.sh` keep their meaning (D2437); every branch route resolves the
    project through the reader the project route uses, so a foreign and a
    missing branch answer one `404` (D2451); the branch's point and state live
    in `app.control_branches`, recorded by the reconciler, `undetermined` when
    `branch.json` cannot be read (D2450).

## Alternatives rejected

- **A branch as a deploy of a new key**: needs its own Infisical project and a
  provider credential per branch, a bootstrap that refuses the parent's
  identity, and every service a project runs. It would make a copy as heavy as
  a project and its secrets as many.
- **Keeping the repository mounted in the persistent phase "read-only"**: the
  recovery needs it; a living copy does not, and a read-only repository with
  `archive_mode=on` is one flag away from rig 40a's control.
- **Re-keying through the poolers' first connection, or after the edge
  attaches**: the property is an ordering, and only "before the poolers exist"
  is one a test can read.
- **A per-branch DNS record**: every branch would wait on the operator.

## Consequences

- A branch shares its parent's `system_identifier` and identity row; any
  reader that tells clusters apart uses the timeline or `branch.json`.
- A branch lives on one disk and is not backed up; deleting it, or losing the
  server, loses what was written to it. `branch.reset` is the way back to a
  point.
- The parent's user password hashes are copied into every branch, reachable by
  no customer grant and read by no service there.
- A branch's creation time is a restore of the parent's whole repository chain
  with `process-max` 1 (D593) — Sheet E0's drill of `slot3-prod` is the
  baseline (D2452).
- `restore-test.py --help`'s *"ISO 8601 with an offset"* misleads (D2454): Run 2
  corrects the text and makes the drill render the space form too.

## Amendment (Session 41, Runs 1 and 3, D2513-D2516, D2537, D2542)

Four repairs of what Session 40's trip found (D2495, D2503, D2504).

1. **The image is resolved at every start, never pinned as an id** (D2513).
   `branch.json` (schema 2) records the parent's image TAG (`Config.Image`),
   the platform manifest digest the branch was made with
   (`ImageManifestDescriptor.digest`) and that manifest's platform
   (`os/architecture`, never typed), read from the parent's raw inspect by
   `restore_drill.image_identity`. Every start -- `start`, `start --all`, and
   the persistent phase of `create` and `reset` -- resolves the image through
   `restore_drill.image_for(tag, digest, platform)` and rewrites `branch.env`
   before `compose up`: the tag's current index id iff its `--platform`
   manifest digest equals the recorded one; otherwise
   **refused with a reason** (*"the parent's image changed since this branch was
   made; reset the branch"*) and the record `stopped` with it; an unreadable
   manifest is said (ADR 0195). It needs the parent's tag, not the parent's
   running container. **Rig 41c** (2026-10-16, Docker 29.5.2, containerd store,
   the real `services/postgres/Dockerfile`): a rebuild of unchanged content
   moved the index id (`d677c532…` -> `82700cbc…`), the old id stopped
   resolving, and the platform digest stayed `sha256:2794179a…`; `image_for`
   chose the new index and `docker run` of it started. **Control:** a rebuild
   with `RUN true` appended changed the platform digest (`sha256:7cbc07f1…`)
   and was refused with the reason. **A version 1 record** (1.18.0's, which
   pinned the id) is still read -- capacity charges it, the reconciler lists it
   -- and a start refuses it, *"this branch was made before 1.19.0 and records
   no image identity; reset it"*; a reset records the identity afresh.
2. **The child's output is kept and the reason recorded** (D2514). The
   reconciler runs `branch-runtime.sh start --all` through the 0600 step-log
   path its operations use and logs the child's last line; `branch.json` gains
   `reason` (the last failure's one line, cleared on `ready`), recorded into
   `app.control_branches.reason` by the control set's `0008` (Run 4) and served
   on the branch's route. `apg-diag containers` lists each branch's containers
   by the Compose project its `branch.env` names, checked before use.
3. **`ready` waits for the door** (D2515, D2537). After `attach`,
   `branch-runtime` opens PostgreSQL's `SSLRequest` to the edge on
   `127.0.0.1:5432` for each branch name, expects `S`, then TLS with SNI = the
   name and ALPN `postgresql`, verifying the chain against the system store and
   the name, every 5 s for up to `DOOR_SECONDS = 180`. Both verified -> `ready`,
   `door: "ready"`. **Rig 41b** (2026-10-16, Pebble, Traefik v3.7 with the
   edge's `sniStrict` `postgres` options): both names verified **3.0 s** after
   their containers were created; **before** the certificate was issued the
   edge did NOT serve a default certificate -- with `sniStrict` it closed the
   handshake (`UNEXPECTED_EOF_WHILE_READING`), exactly as it does for a name
   with no router (the control, which never verified in 60 s); a check against
   the wrong root read `unable to get local issuer certificate`. So **after the
   `S`, an EOF in the handshake and a verification failure both mean the door is
   not open yet** -> at the bound, `ready` with `door: "pending"` and the
   reason (*"the door's certificate is not issued yet"*); **`door: "unknown"`
   only when the check could not run** -- no connection, no `S`, or a TLS
   failure of any other kind. 180 s is 60 times the rig's 3.0 s and well above
   the trip's 4.5 s (D2503); it stays. **On the host** (D2542), the
   interpreter the runtime runs (uv CPython 3.12.13, OpenSSL 3.5.7) found the
   system store through `capath=/etc/ssl/certs`, verified both of `slot3-prod`'s
   names, and read the no-router name's EOF as `ssl.SSLEOFError` -- `pending`.
   The check is `agentic_postgres.branch_door`.
4. **A larger budget for the three branch types** (D2516):
   `OPERATION_SECONDS_BY_TYPE = {branch.create, restore.create, branch.reset:
   3600}` (every other type keeps 1,800), `CHILD_SECONDS["branch-runtime.sh"] =
   3300`, `PROMOTION_SECONDS = 2400`, and the customer CLI's `--wait` default
   3,900 s (it was 2,400, below the new bound); the guard holds promotion <
   child < each type's operation bound < the CLI's wait. Not taken: a forced incremental before a branch (it touches
   the parent's repository) and a bucket move (a provider act).
