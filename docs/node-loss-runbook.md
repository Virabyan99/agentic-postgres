# The node-loss runbook

The host is gone, or is being treated as gone. What you are holding is the
disaster kit (ADR 0189), the control-plane credential, and access to the
providers. What you are building is a replacement host that runs the project
again from the mirror of its backups (ADR 0188), with the same identity, under
a new address.

**Derived by diff from the Session 11 and 17 operator guides** (D693): the
steps that are theirs are named and not retyped here. Two facts shape the
order, both measured on the project's own image (D1008, D1012):

- **The restore comes before the first deploy.** A first `up` on an empty
  volume runs `initdb`, and the deploy's step 6c would then create a stanza
  for a cluster with a different system identifier than the one the
  repository holds. `restore.sh` fills the volume first; `deploy.sh` then
  starts a cluster that already exists and skips `initdb`.
- **A volume that holds a cluster is never written to**, on any host.
  `restore.sh` refuses `PG_VERSION` under the data directory and refuses a
  volume any container mounts. On the production host it therefore does
  nothing, by construction.

Two terms. The **kit** is `dr-kit.sh export`'s output: the host and
capability manifests and, per project, the manifest, `bootstrap-state.json`,
the deployed document and `secrets.txt`. The **rehearsal** is this runbook
performed while production still runs, under a drill domain, on a host that
is retired afterwards; §6 says what a rehearsal must not do.

---

## 0. Before the day: what must already be true

| Held where | What | Made by |
|---|---|---|
| Off the host | The kit, verified | `sudo bin/dr-kit.sh export …` then `bin/dr-kit.sh verify DIR`, after every deploy that changed a manifest or a bootstrap |
| With the operator | The Infisical control-plane credential (`docs/provider-bootstrap.md`) | Infisical's console |
| At the second provider | The mirror bucket, holding the last copy (`backup_state.mirror` and the doctor's `backup mirror` check say when) | The nightly `agentic-postgres-backup-mirror@<key>.timer` |
| In the project's Infisical project | Every value `secrets.txt` names -- the cipher pass above all, and the mirror's key pair | The bootstrap and the operator (`/backup`) |
| A DNS zone you can edit | The record for the project's domain | Cloudflare's console |

A kit exported before the last manifest change restores the project as it
was then. `bin/dr-kit.sh verify DIR` tells you the export date and release;
`projects/<key>/outputs.json` inside it carries the `instance_uuid` the
restore is verified against and the `source_commit` the replacement should
run.

---

## 1. The replacement host, by the documented path

The Session 2 and 11 guides' host sequence, unchanged: the operator user, the
release transported by bundle and checked out under `~op/agentic-postgres` at
the kit's `source_commit`, `provision-host.sh --apply` (which installs the
backup units, the mirror's included), the edge plane up. Nothing here differs
from a fresh host, and that is the point: `fresh_host` is closed by a NEW
project deployed on this host by that path (D987), not by the restore.

The kit's `host.yaml` is the host manifest to use, edited for the new host's
own facts (`host.id`, addresses, the SSH block). **Its `infisical` block stays
exactly as it is**: adoption compares this host's provider inputs against the
recorded ones and refuses a difference.

---

## 2. Adopt the project's provider identity, by id

```bash
bin/dr-kit.sh verify /path/to/kit
sudo bin/bootstrap-providers.sh --host host.yaml --project /path/to/kit/projects/<key>/project.yaml \
     --adopt --state /path/to/kit/projects/<key>/bootstrap-state.json \
     --operator-credential-file /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
```

`--adopt` reads the recorded Infisical project id, asks the provider for that
project and nothing else, mints a fresh runtime identity against it, grants
it read, and writes this host's credential files and state. It refuses a host
that already records the project, a recorded id the provider does not have
(HTTP 404 -- **nothing here searches by name**, ADR 0189), a project in
another organisation, and provider inputs that differ from the recorded
ones. The lost host's identity is named and not revoked: revoke it in the
console once that host is known to be gone.

Then converge, which adopts the existing secret values into this host's
record without writing any:

```bash
sudo bin/bootstrap-providers.sh --host host.yaml --project <manifest> --apply \
     --operator-credential-file …
```

Every line it prints as *already present at the provider; not overwritten* is
a value `secrets.txt` named. A line it would *create* is a value the lost
host never had, which is a finding, not a step.

Shred the control-plane credential from the host when this section is done.

---

## 3. Materialize, and render

The manifest deployed here is the kit's, with two edits for a rehearsal (§6)
and none for a real loss:

- `backup.mirror` **stays as it is** -- it names the bucket the restore reads.
- `backup.bucket` names the **new** primary bucket this host will archive to
  (a new account after a real loss; a rehearsal bucket during one), with its
  credential pair in Infisical under `/backup`. The old primary is gone or is
  production's; neither is this host's to write.

```bash
sudo bin/materialize-secrets.sh --project <manifest> --requirements secrets.required.yaml --session <N>
./deploy.sh --project <manifest> --capabilities capabilities.yaml --render-only
```

The render needs no host and no root, and `deploy.sh` refuses `--render-only`
beside `--through-session` (D1025); the kit's `capabilities.yaml` is the
capability manifest to render with.

Materialization fetches the mirror's pair and the cipher pass; the render
writes `.generated/<key>/` with the compose model the restore builds the
image from. No container starts.

---

## 4. Restore, then deploy

```bash
sudo bin/restore.sh --outputs /path/to/kit/projects/<key>/outputs.json --project <manifest> \
     --rendered-dir .generated/<key> --from mirror --latest --plan
sudo bin/restore.sh --outputs /path/to/kit/projects/<key>/outputs.json --project <manifest> \
     --rendered-dir .generated/<key> --from mirror --latest
```

`--plan` prints the volume, the stanza, the generation and every mount and
starts nothing. The real run: refuses a volume a container mounts or that
holds a cluster; builds the postgres image through `bin/compose.sh`; creates
the project's volume; reads the mirror's report (`no backup set` here means
the cipher pass is not the one the objects were written under, D999);
restores through the project's own image with the mirror's key pair in the
container's environment and the primary's credential never mounted; starts
the cluster once with archiving off; waits for it to promote; reads its
`instance_uuid` and migration ledger; stops it; writes
`evidence/restore-<key>-<id>.json`. Its last line names the timeline and the
identity. `--target-time` in place of `--latest` stops recovery at an instant.

Then the deploy, unredirected (D972):

```bash
sudo ./deploy.sh --host host.yaml --project <manifest> --through-session <N>
```

The cluster starts on the restored volume without `initdb`; the bootstrap
reconciles every role's password to this host's generation; migrations
report applied; step 6c creates the stanza in the **new** primary bucket and
`check` proves archiving into it. `sudo bin/doctor.sh --project <key>` then
reads `ready` on every route.

Verification, `REC-NODE-002`'s: the deployed document's `instance_uuid`
equals the kit's `outputs.json`'s; a row count of a table the last copied
backup set held matches what production's own count said at that instant;
`bin/backup.sh --outputs <outputs.json> info` on the replacement reports the
new stanza.

---

## 5. The cutover, last

The DNS record for the project's domain is moved to the replacement's
address in Cloudflare's console, grey-cloud, as the Session 2 guide made it.
It is the last step because it is the one that cannot be rehearsed without
taking production's name, and the one that turns a replacement into the
deployment. ACME on the replacement has already issued for the drill domain;
the production domain's certificate is issued on first request after the
record moves -- **never retried in a loop** (5 per hour per hostname).

---

## 6. A rehearsal is not a loss

While production still runs, three rules keep the rehearsal from touching it:

- **The restored copy runs under a drill domain** (`alpha-dr-db.…`), never
  the project's. The DNS cutover is rehearsed as a plan and never performed.
- **The restored copy is not deployed while production runs.** A rehearsal
  ends at `restore.sh`: the volume holds the promoted cluster, the record
  proves it, and nothing starts. It cannot archive to a bucket of its own,
  because adoption binds the replacement to production's Infisical project
  AND environment (the provider-inputs digest covers the environment slug,
  D1028), so the only backup credential it can materialize is production's.
  A rehearsal that must deploy the copy names its own
  `backup.repository_prefix` in production's bucket, never enables a timer,
  and accepts that its storage bucket and signing key are production's for
  the day; that was measured as too much coupling for a disposable host
  (2026-09-06) and is not the rehearsed path.
- **`backup.sh schedule enable` is never run on the replacement.** Its mirror
  timer would copy the rehearsal's bucket to the mirror bucket with
  `--remove`, deleting production's own copy there. The timers stay
  disabled; the retirement disables what a deploy enabled.

At the end, `project-retire.sh --record …` on the replacement, and the host
destroyed. The records are the trip's evidence.

---

## 7. If something goes wrong

| Symptom | Cause | Do |
|---|---|---|
| `--adopt` exits 7, *does not exist* | The recorded project id is not at the provider, or the credential cannot see it | Check the kit's export date; the project may have been deleted after it. Do not create one by name. |
| `--adopt` exits 7, *provider inputs differ* | The host manifest's `infisical` block or the project's slug/environment was edited | Use the kit's values as they are |
| `restore.sh` exits 7, *already holds a cluster* | A deploy or `up` ran before the restore | Remove the project's volume deliberately (`docker volume rm`, by its printed name) and restore again; nothing else on the host references it yet |
| `restore.sh` exits 5, *no backup set to restore* | The cipher pass in this host's generation is not the one the mirror's objects were written under, or the mirror is empty | `secrets.txt` names the pass; compare the provider's value with what production materializes. An empty mirror is a mirror that never copied: `backup_state.mirror` in the kit's document says so |
| The instance exits before promoting | Recovery could not reach a segment: the mirror's last copy predates WAL the backup set needs | Restore `--target-time` at the last copied set's stop time (the document's `latest_recoverable_time`) |
| The deploy's 6c `check` fails | The new primary bucket's credential or bucket name | The Session 10 guide's repository section; the restore is intact and the deploy re-runs |
