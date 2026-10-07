# 0259 — Sleep is `compose stop`, wake is `compose start`, and an export is a 900-second URL

- **Status:** Accepted
- **Date:** 2026-10-07
- **Session:** 38, Run 1 (D2155, D2164, D2182; rig rows D2190, D2192)
- **Affects:** `bin/project-runtime.sh stop|start` (Run 5), the reconciler's
  sleep, wake and export handlers (Run 7),
  `services/auth-api/app/export_upload.py` (new, Run 7),
  `services/auth-api/app/storage_client.py` (`presign_get`'s expiry and one
  new operation, Run 7), the control set's `0004` (`result_secret`,
  `control_take_result_secret`, Run 4). Requirements `LIFE-SLEEP-001`,
  `LIFE-EXPORT-001`, `LIFE-LIVE-001`, `LIFE-LIVE-002`.
- **Related:** ADR 0085 (routes stay on labels), ADR 0124 (the storage
  transport guard), ADR 0187 (backups are kept), ADR 0246 (the control plane
  holds nothing that opens a project's data plane), ADR 0256.

## Context

**Sleep.** `project-runtime.sh` has `up`, `down`, `status` and `resume`; the
unit's stop path is `down` (containers removed) and its start path
materializes every secret from Infisical first, with no last-known-good
fallback. The backup timers' services `BindsTo=` the project unit, so a timer
firing on a sleeping project would start it.

Rig 38b measured `compose stop`/`start` under the pinned Postgres, PostgREST
and Traefik images, a label router on Traefik's Docker provider, sampling the
route every 0.1 s (WSL Docker Compose v5.1.3):

- `stop` returned in 0.71 s; the route went 200 → one 502 → one timeout →
  Traefik's own **`404 page not found`, 19 bytes**, for as long as it slept;
  container ids kept, state `exited`.
- `start` returned in 2.16 s (it honours `depends_on: service_healthy`); the
  first 200 came **4.64 s** after it began, because **Traefik routes a
  container only once its healthcheck reads healthy** — so a project's wake is
  bounded below by its PostgREST healthcheck (interval 10 s, start period 20 s
  in `compose.yaml`), not by `start` returning; ids unchanged, `StartedAt`
  moved.
- Control: `up -d --force-recreate` moved the ids; `stop` then `up -d --wait`
  did not (an unchanged definition is not recreated), and the route read just
  after `--wait` returned was still 404 — `--wait` returning is not the route
  being served.
- Compose v5.1.3's `start` offers `--wait`/`--wait-timeout`; the plan assumed it
  did not (D2192). The host's Compose, v5.4.0, offers both too (Sheet E0).

**Export.** Presigning exists only inside the storage service, with the
project's own `/storage` credential. Rig 38e read, offline: `R2Adapter.presign_get(key)`
takes no expiry and signs the project's `download_url_ttl_seconds` (300 by
default, 60–3600 allowed); the adapter's four operations include no upload of
bytes. Rig 38d: `pg_dump -Fc -n app -n api --no-owner --no-privileges` of a
cluster with the release set lists no `app_private` entry (45,391 bytes,
schema only — the release seeds no rows); the control without `-n` lists it
(318,442 bytes). No release policy on `app` references `app_private`;
`app.note_embeddings` needs `vector` in `extensions` at the restore target.

## Decision

1. **`project-runtime.sh stop`** = `edge-network.sh detach`, then `compose
   stop` — containers and volumes kept. **`start`** = `compose start --wait
   --wait-timeout 120` (the host's Compose is v5.4.0 and lists both flags
   under `start`, read on Sheet E0 — D2192), then `edge-network.sh attach`. **Neither materializes,
   renders a secret override, renders digests, builds or recreates** — wake
   must not depend on the provider's rate limit (D2139) or on a secret that
   moved while the project slept.
2. **`project.sleep`** = `backup.sh … schedule disable`, `systemctl disable
   agentic-postgres-project@KEY` (no `--now`: the unit stays active),
   `project-runtime.sh stop`. **`project.wake`** = `start`, `systemctl
   enable`, `schedule enable`. A reboot while asleep keeps it asleep (the unit
   is disabled) — unproved, §10.
3. **No fallback body.** A caller of a sleeping project gets the edge's
   `404 page not found`; `/v1/projects/{key}` says `sleeping`. **A sleeping
   project's archiver is stopped, so its last restore point is its sleep
   time**, and nothing in 38 reads its doctor (D2182); the Ledger says both.
4. **Export in three steps, no credential leaving its container.** (a)
   `pg_dump -U postgres -Fc -n app -n api --no-owner --no-privileges` through
   `container_exec.run` into `/var/lib/agentic-postgres/exports/<operation>.dump`
   (root, 0600, directory 0700); (b) the file streamed into the project's
   storage container to `python -m app.export_upload --key
   exports/<operation>.dump`, which stores it with the container's own adapter
   and prints ONE line, a presigned GET **valid 900 s**; (c) the local file
   removed.
5. **The adapter gains exactly what export needs** (D2190): `presign_get(key,
   *, expires_in=None)` — the export passes 900, and a value above 900 is
   refused — and one fifth operation, `put_object(key, body)`, first-write-only
   (`IfNoneMatch: "*"`, `presign_put`'s rule). Still no list operation; ADR
   0124's transport allowlist is not widened.
6. **The URL crosses the control database once.** It is the operation's
   `result_secret`; `GET /v1/operations/{id}` returns it ONCE to the
   requesting member and erases it in the same transaction
   (`control_take_result_secret`); it is never in a list answer or a log line.

## Alternatives rejected

- **Sleep as `down`, wake as `up`.** Removes containers and re-reads every
  secret from Infisical on wake; a timer or a provider limit decides whether a
  customer's project comes back.
- **A "sleeping" fallback page.** A FILE-provider route resolving a shared
  Compose name served one project to another's router (ADR 0085); routes stay
  on labels, and the edge's own 404 is what a stopped router produces.
- **Exporting through the project's storage API as its administrator.** No
  object-ownership path exists for the control plane; priced at Session 40.
- **A long-lived or listed URL.** A presigned URL is a bearer credential to
  the object (D358); 900 s and one read bound it.

## Consequences

- The export URL is the one credential-shaped value that crosses the control
  plane; it sits in the control database's WAL and backup until it expires.
- `process-max` 1 (D593) is now a customer's export time as well as a restore
  time.
- The wake window a customer sees is the first 200 after `start`, read on the
  host in Run 12 (D2171); this rig's 4.6 s used a 1 s healthcheck.
