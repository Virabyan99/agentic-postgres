# The secret store

Every project's secrets — role passwords, signing keys, the storage and backup
key pairs and the backup cipher pass — live in **Infisical, self-hosted on a
host of its own** (ADR 0262): `https://secrets.agenticpostgresql.com`. This page
is how that host is built, reached, backed up, restored, upgraded and lost. Its
files are `infra/secret-store/`; nothing of the product's release runs there.

**If this host and its backup are both lost, every project's backups are
unreadable** (ADR 0188): the cipher pass exists nowhere else. The backup, the
operator's copies of two keys, and a rehearsed restore are the whole defence.

---

## 1. What runs, and who reaches it

| Service | Image | Reaches / reached by |
|---|---|---|
| `backend` | Infisical (pinned by digest) | publishes `127.0.0.1:8080` only |
| `db` | PostgreSQL 16 | the `store` network only; volume `pg_data` |
| `redis` | Redis 7.4 | the `store` network only; regenerable |
| `edge` | Caddy, **host network** | ports 80 and 443, under ufw |

Docker-published ports bypass ufw, so the only published port is on loopback
and the edge runs on the host network, where ufw applies (D2250):

| Port | From |
|---|---|
| 22/tcp | anywhere, key-only (`PasswordAuthentication no`) |
| 80/tcp | anywhere: Let's Encrypt's HTTP-01 challenge and a redirect |
| 443/tcp | the hosts that read secrets only — today `15.204.231.45` |

The console is reached through SSH: `ssh -L 8443:127.0.0.1:443
op@15.204.66.146` with `127.0.0.1 secrets.agenticpostgresql.com` in the
workstation's hosts file, then `https://secrets.agenticpostgresql.com:8443`.

## 2. The keys, and where they live

| Value | Where on the host | Also kept by the operator |
|---|---|---|
| `ENCRYPTION_KEY` (`openssl rand -hex 16`) | `/etc/secret-store/infisical.env` | password manager + one offline copy |
| `AUTH_SECRET` (`openssl rand -base64 32`) | `/etc/secret-store/infisical.env` | password manager + one offline copy |
| database password (`openssl rand -hex 24`) | `db.env` and inside `infisical.env`'s `DB_CONNECTION_URI` | password manager |
| B2 key restricted to `apg-secret-store-backup` | `/etc/secret-store/backup.env` | the B2 console can issue another |
| the backup's `age` **identity** | **nowhere on the host** | password manager + one offline copy |
| the backup's `age` recipient (public) | `/etc/secret-store/backup.age.pub` | — |

The three env files are root, 0600, each written at the operator's terminal from
its `*.env.example`. Each container reads one: the backend `infisical.env`, the
database `db.env`, the backup's rclone `backup.env`. **None of these values is
ever pasted into a conversation, a ticket or a kit** (ADR 0189).

## 3. Building the host

The order is the migration plan's Sheets E1, D1 and I1
(`docs/plans/session-38-migration-plan.md`):

1. The `op` account and the operator's key; the image's default `ubuntu`
   account locked; `PasswordAuthentication no` (D2245).
2. A **grey-cloud** A record `secrets.agenticpostgresql.com` → the host, no AAAA.
3. Docker from Docker's apt repository (the lines `bin/provision-host.sh` writes),
   `age` and `ufw` from Ubuntu's; ufw as §1.
4. `infra/secret-store/` copied to `/home/op/secret-store/`; the env files
   written (§2); then:
   ```bash
   cd /home/op/secret-store && sudo docker compose -p secret-store up -d
   curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/api/status   # 200
   ```
   The first start runs the store's migrations: about two minutes.
5. In the console: the administrator (the first account), an organisation, and
   the **control-plane machine identity** with the organisation's Admin role,
   Universal Auth and one client secret. Its client id and secret are the
   *operator credential* `bootstrap-providers.sh` reads
   (`docs/provider-bootstrap.md`), kept in the password manager and placed on a
   host only for a sheet, then shredded.

## 4. The backup

```bash
sudo install -m 0755 /home/op/secret-store/backup.sh /usr/local/sbin/secret-store-backup
sudo install -m 0644 /home/op/secret-store/secret-store-backup.service /home/op/secret-store/secret-store-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start secret-store-backup.service      # the first pass, read before the timer
sudo systemctl enable --now secret-store-backup.timer  # nightly, 05:15 UTC, catches up after downtime
```

A pass dumps the store's database inside its container, encrypts it to the
recipient on the way out, keeps the newest fourteen under
`/var/backups/secret-store/`, copies the new one to B2 and reads its size back.
Its last line names the object and its size; any failure exits 1 and the unit
fails. `journalctl -u secret-store-backup` is the record.

## 5. A restore

On the workstation, with the `age` identity: download the newest
`infisical-<utc>.dump.age` from the bucket, `age -d -i <identity> -o
store.dump <object>`, copy `store.dump` to the target host. Then a compose
project with the SAME `ENCRYPTION_KEY` (a restored database is unreadable
without it):

```bash
sudo docker compose -p secret-store up -d db
sudo docker compose -p secret-store exec -T db pg_restore -U infisical -d infisical --clean --if-exists < store.dump
sudo docker compose -p secret-store up -d
```

`shred -u` the plain dump on both machines afterwards. A **rehearsal** uses the
project name `secret-store-drill`, starts no edge and is removed with `down -v`.

## 6. Upgrading

1. A backup pass (§4), read.
2. A commit moving the image's tag and digest in `infra/secret-store/compose.yaml`
   (the newest tag at least two weeks old), reviewed; the files shipped.
3. `sudo docker compose -p secret-store up -d`, then the backend's log until it
   reports its migrations, then `/api/status`.

## 7. If something goes wrong

| Symptom | Cause | Do |
|---|---|---|
| `/api/status` never answers after `up` | the first start's migrations, or a wrong `DB_CONNECTION_URI` | `docker compose -p secret-store logs backend`; the password in `infisical.env` must equal `db.env`'s |
| A host's `materialize-secrets` fails with a TLS error | the certificate, or 443 not admitted for that host | `curl -v https://secrets.agenticpostgresql.com/api/status` from that host; `sudo ufw status` here |
| The backup unit failed | B2 key, bucket, or a full disk | `journalctl -u secret-store-backup`; the encrypted file is kept locally either way |
| The host is gone | — | a new host by §3, then §5 with the operator's key and identity, before anything else |
