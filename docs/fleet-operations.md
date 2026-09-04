# Fleet operations

Operating several projects on one host over time: seeing them, knowing which
are permanent, retiring one, and keeping the backup schedule on. Session 17,
ADRs 0185–0187.

Every command here runs as root at a terminal. None of them has a route, a
service, a credential or a reader (ADR 0185): the host's own files are read,
systemd and Docker are asked, and nothing is written except a retirement
record the operator asked for.

---

## 1. The inventory

```
sudo bin/fleet.sh                      # one block per deployed project
sudo bin/fleet.sh --json               # the same, as a document sorted by key
sudo bin/fleet.sh --window 168         # denials over the last week instead of 24 hours
```

One block per directory under `/etc/agentic-postgres/projects`, every line
under its project's key:

| Column | Where it comes from |
|---|---|
| identity, release, lifecycle | the deployed document — `project`, `source_commit`, `deployed_through_session`, `template_version`, `project.lifecycle` |
| health | `bin/doctor.py --json` run per project: the worst verdict, the counts, each check's verdict. **Live, never the document's status blocks** (ADR 0158) |
| backups | `systemctl is-enabled` on both timers, and the age of the last full backup **as the doctor's repository probe read it**. Never `backup_state.status`, which is a deploy-time snapshot (D700, D944) |
| denials | counts by `denial_reason` over the window, from `app_private.agent_audit` over the container socket. Counts, not a rate: the boundary that refused is the question (ADR 0178), and a refusal is not an alarm (D948) |

A project whose document cannot be read is a row saying so; the other rows
are still reported. A timer state is one of `enabled`, `disabled`, `absent`
(the unit file was never installed) or `unknown`, and a project is
`scheduled` only when both timers are enabled.

**It writes nothing.** No file under the state root, the runtime state, the
checkout or your home directory changes when it runs, and that is proved on
the host (`FLEET-INV-002`).

## 2. Lifecycle

A project manifest at schema version 3 declares:

```yaml
project:
  lifecycle:
    kind: permanent            # or ephemeral, with expires_at
    # expires_at: 2026-10-01T00:00:00Z   # RFC 3339 UTC, ephemeral only
```

A version 1 or 2 manifest says nothing and means `permanent`, which is what
every project deployed before the field existed was; neither host manifest
needs editing. The render refuses an ephemeral project born expired.

**Expiry is a fact you read, never a trigger** (ADR 0186). The inventory shows
an ephemeral project past its `expires_at` as `EXPIRED`; the retirement verb
refuses an unexpired one without `--before-expiry`. No unit, timer or cron
acts on the date, and a test asserts none names the verb.

## 3. Retiring a project

Plan first. The plan prints every name and every command and changes nothing:

```
sudo bin/project-retire.sh --host host.yaml --project <key> --confirm <key> \
     --record /root/retired-<key>.json --plan [--permanent | --before-expiry] [--destroy-data]
```

Then the same command without `--plan`, with `--operator-credential-file FILE`
when the project's bootstrap state exists (the provider destroy needs it to
revoke the runtime identity). The steps run in this order and no other:

1. **record** — the retirement record, written before anything changes. It is
   the file `--removed-project-file` hands the Session 12 removal proof.
2. **down** — `project-runtime.sh down`: detach the edge, stop the stack.
3. **disable-units** — the project's systemd instance and both timers, where enabled.
4. **release-ports** — the port allocation, under the volume's identity, **before**
   any volume is removed (ADR 0042).
5. **edge-files** — this project's files in the edge's dynamic directory.
6. **provider-destroy** — `bootstrap-providers.sh --destroy`: the runtime identity,
   **before** the state directory it reads from is removed.
7. **remove-directories** — the state, secrets and rendered directories.
8. **remove-volumes** — the postgres and store volumes, only with `--destroy-data`.
   Without it they are kept by name; a redeploy of the same key adopts them only
   if the identity matches (ADR 0030).

A step that fails stops the run and names itself; the steps after it do not run.

**What a retirement never touches** (ADR 0187): the backup repository, its
bucket, the cipher pass, the Infisical project's secrets, the DNS record, the
certificate. The record says where the backups still are. Deleting the bucket
and the Infisical project are console actions, taken afterwards and on purpose.

A permanent project needs `--permanent`; an unexpired ephemeral one needs
`--before-expiry`; an expired one needs neither, and a flag that does not apply
is refused. There is no `--force`. The record path must not exist.

## 4. The backup schedule

```
sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/<key>/outputs.json schedule status
sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/<key>/outputs.json schedule enable
sudo bin/backup.sh --outputs /etc/agentic-postgres/projects/<key>/outputs.json schedule disable
```

`status` exits 0 only when both timers are enabled. `enable` refuses while
either unit file is absent — installing units is `provision-host.sh --apply`'s
job and the refusal says so — and while the repository holds no full backup,
because the first one is yours to take by hand. It re-reads systemd afterwards
rather than trusting the enable's exit code. Both timers carry
`Persistent=true`, so a run the calendar already owed fires at enable.

**On the reference deployment no timer unit was installed until Session 17's
trip** (D944): the units were added in Session 10 after the host was
provisioned, nothing since re-ran the installer, and both deployed documents
said `ready` throughout. `FLEET-BACKUP-001` is the requirement that keeps that
from happening quietly again.

## 5. What is still an operator's

- Creating a project's two R2 buckets and tokens, its DNS record, and its
  Infisical bootstrap (`bootstrap-providers.sh --apply`) — and removing the
  buckets, the record and the Infisical project after a retirement.
- Installing the unit files: `provision-host.sh --check`, then `--apply`.
- Taking the first full backup of every project.
- Deciding, at a terminal, that a project is retired. Nothing here decides it.
