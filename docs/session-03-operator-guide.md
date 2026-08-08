# Session 3 operator guide

Deploying a project with its database, and proving it worked.

This assumes Session 2 is done: the host is provisioned, the edge is up, and the
provider bootstrap has run at least once. If not, start with the
[Session 2 operator guide](session-02-operator-guide.md).

Background: [the database](database.md) · [migrations](migrations.md) ·
[database security](database-security.md).

## 0. What changed for an operator

Three things, and each of them will stop you if you skip it.

**`--through-session 3` is required, and it is read rather than assumed.** The
deployed document now records `deployed_through_session`, and the systemd
launcher reads it back at boot to decide which secrets to materialize and which
Compose profiles to start. A project deployed through Session 2 and never
redeployed **cannot be restarted** by a Session 3 release: the launcher exits 4
naming the field rather than guessing.

**Session 3 declares two new provider secrets.** A project bootstrapped in an
earlier session does not have them, and the provider bootstrap now creates
whatever the contract declares rather than one hard-coded name.

**The launchers travel with the release.** They used to be installed only by
`bin/provision-host.sh`, so a launcher fixed in a release could sit on the host
unused indefinitely. A deploy now reinstalls them
([ADR 0037](decisions/0037-an-installed-launcher-resolves-a-release-and-nothing-else.md)).

## 1. Seed the provider secrets

Only needed for a project that has not been deployed through Session 3 before.
Check first — it writes nothing:

```bash
sudo bin/bootstrap-providers.sh --host host.yaml --project project.alpha.yaml --plan
```

Expect two proposed creations: `postgres_init_superuser_password` and
`migration_user_password`. Then:

```bash
sudo bin/bootstrap-providers.sh --host host.yaml --project project.alpha.yaml \
  --apply --operator-credential-file \
  /root/.config/agentic-postgres/bootstrap/infisical-control-plane-credential
```

That file is **two non-empty lines** — the organisation machine identity's client
ID, then its client secret. It is not the per-project runtime credential. It is
correct for it to be absent between sessions; recreate it when you need it and
remove it afterwards. Note that `nano` leaves a `.save` copy behind, which is a
second copy of an organisation-admin credential at whatever mode nano chose.

**An existing secret is adopted, never overwritten.** That matters most for
`postgres_init_superuser_password`: the image reads it only when the data
directory is empty, so a new value would change the file and not the cluster, and
materialization would then deliver a password that cannot open the database it is
for.

## 2. Materialize, then deploy

The ordering is operator-visible on purpose. Materialization can fail on its own
and be re-run on its own; a deploy that silently performed it would make its own
preconditions.

```bash
sudo bin/materialize-secrets.sh --project project.alpha.yaml \
  --requirements secrets.required.yaml --session 3

sudo ./deploy.sh --host host.yaml --project project.alpha.yaml \
  --capabilities capabilities.yaml --through-session 3
```

The deploy owns render → install → configuration → start → **bootstrap →
migrate → observe** → publish. On a new cluster expect ~40 bootstrap statements
and 5 migrations applied; on an existing one, 40 statements that converge and 0
migrations. It should end with:

```
  tls          issued (production)
  health       ready
  database     observed
```

## 3. Verify

```bash
sudo bin/postgres-bootstrap.sh --project project.alpha.yaml --runtime --check
sudo bin/migrate.sh --project project.alpha.yaml --runtime status
sudo bin/db.sh --project project.alpha.yaml --runtime status
sudo bin/db.sh --project project.alpha.yaml --runtime identity
```

The deploy already converged all of these, so they are verifications: `--check`
returns 0 with `violations none`, `status` reports 5 applied and 0 pending,
`db.sh status` names the server and its extensions.

To prove convergence rather than assume it, run `--apply` and `up` a second time
and compare: no role churn, no new migration, identical ledger checksums, and an
instance UUID **recovered** rather than regenerated.

## 4. The gate

```bash
sudo bin/session-03-check.sh --mode host --host host.yaml \
  --project-a-outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
  --project-b-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json \
  --sentinel-file "$(...)"
```

**`--project-b-outputs` is required.** `database_isolation` is a claim about two
clusters, and one project cannot be isolated from nothing.

**Derive the sentinel path from the active generation**, never type it. The
generation directory changes on every start, and a hard-coded path silently names
a superseded one — which plants a sentinel the scan then fails to find:

```bash
python3 -c "
import json
from pathlib import Path
root = Path('/var/lib/agentic-postgres/secrets/alpha-dev')
gen = json.loads((root / 'active-secret-generation.json').read_text())['generation_id']
print(root / 'generations' / gen / 'secret-check' / 'session2_sentinel')
"
```

Without it, the twelve secret-leakage proofs skip — and a skip is not a pass, so
the run reports `secret_leakage` unproved and exits 5 with every test green.
That is the evidence model working, not a bug.

There is no external mode. `SEC-NET-001`'s scan already covers 5432 and belongs
to Session 2; nothing new is visible from outside a cluster that publishes no
port.

## 5. Evidence

```bash
python bin/write-session-evidence.py --session 3 \
  --host-input evidence/session-03-host.json \
  --output evidence/session-03.json

jq -e '.tests.row_level_security=="passed" and .tests.database_isolation=="passed"' \
  evidence/session-03.json
```

One half, because there is one environment. The merge still runs: it is what
computes `status` and what refuses a document that is silent about a claim.

Session 3 records six claims, cumulatively — Session 2's `isolation` and
`secret_leakage` are still promises the product makes, so this gate proves them
too.

## 6. Restart and reboot

```bash
sudo systemctl restart agentic-postgres-project@alpha-dev.service
```

Both the container restart and the unit restart are asserted by the suite, so
running them by hand is only for confirming a specific worry. For a reboot, take
a snapshot first — the identity row, the ledger digest, the recorded session and
commit — reboot, **wait for both units to reach `active`**, and compare.

Two things that cost a run each when this was first done:

- a post-reboot check run at `up 0 min` reported ten failures that all said the
  host was still booting;
- comparing `app.notes` row counts for equality across a reboot fails, because
  the isolation suite inserts a row on every run. Compare identity and ledger for
  equality; compare rows for **never lost**.

## Traps

**A route that comes back after a restart is discovered, not announced.**
`systemctl start` returns when the containers are healthy and the edge is
attached; Traefik registers the router a moment later. Poll, do not ask once.

**`docker exec` without `-i` discards heredoc stdin and exits 0**, so a psql
block appears to run and does nothing.

**`pg_isready` succeeds against the image's temporary initialisation server**, so
`compose up --wait` can return mid-`initdb`. Anything that must talk to the real
cluster waits for two consecutive successful queries.

**Secret generations accumulate.** Nothing prunes them, and the deployed
document's `secrets.generation_id` records the generation the deploy *verified*,
which is not the one that is current after any restart
([ADR 0038](decisions/0038-the-deployed-document-records-the-generation-it-verified.md)).
Read the pointer for the live value.

**Never put a GitHub credential on the VPS.** Transport is `git bundle` + `scp`.

**Failed ACME validations are capped at 5/hour/hostname.** Never retry in a loop.
DNS records stay DNS-only / grey cloud.
