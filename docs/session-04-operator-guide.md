# Session 4 operator guide

Giving a deployed project two database transports, proving they work for real
clients, and proving they are not reachable from anywhere else.

This assumes Session 3 is done: the project is deployed with its cluster, roles
and migrations. If not, start with the
[Session 3 operator guide](session-03-operator-guide.md).

Background: [database connections](database-connections.md) ·
[client compatibility](client-compatibility.md) ·
[pool operations](pool-operations.md).

## 0. What changed for an operator

**`--through-session 4` deploys a pooler.** The launcher reads
`deployed_through_session` from the deployed document, so a project deployed
through Session 3 and never redeployed comes back as a Session 3 project — with
no pooler, and every signal above the transport green.

**Two new provider secrets.** `app_runtime_password` and
`pgbouncer_admin_password`. A project bootstrapped in an earlier session does not
have them.

**The gate has three modes again.** Session 3 had two; Session 4 restores the
external one, and it is the only place a boundary can be measured from outside
and the only place `bin/connect.sh` can be exercised as what it is.

**Nothing is published**, which is the opposite of what this session set out to
do. See [database connections](database-connections.md#nothing-is-published) and
[ADR 0044](decisions/0044-there-is-no-publication.md). The practical consequence:
a developer needs SSH to reach a database, always.

## 1. Seed the provider secrets

Only for a project that has not been deployed through Session 4 before. Check
first — it writes nothing:

```bash
sudo bin/bootstrap-providers.sh --host host.yaml --project project.alpha.yaml --plan
```

Expect two proposed creations. Then `--apply` with the operator credential file,
exactly as in Session 3. **An existing secret is adopted, never overwritten.**

## 2. Materialize, then deploy

```bash
sudo bin/materialize-secrets.sh --project project.alpha.yaml \
  --requirements secrets.required.yaml --session 4

sudo ./deploy.sh --host host.yaml --project project.alpha.yaml \
  --capabilities capabilities.yaml --through-session 4
```

Session 4 materializes **seven files per project**: the pooler's two, dbmate's
one, and the four client fixtures' copies of the application credential. That
number is the price of per-consumer isolation and it is what a rotation has to
reach.

That count is Session 4's, and later sessions add to it. Do not carry it
forward: `bin/materialize-secrets.sh --plan --session N` prints every file it
would write and totals them, contacts no provider and writes nothing, and is the
authority for what a rotation has to reach at any session (D108).

The deploy allocates two ports, verifies both container endpoints, promotes the
allocation from `reserved` to `active`, and only then writes transports into the
deployed document. A project whose allocation is still `reserved` reports every
transport `unavailable`, which is the correct answer: the endpoint checks never
passed.

## 3. Verify by hand

```bash
sudo bin/database-ports.sh show
sudo bin/db.sh --project project.alpha.yaml --runtime status
```

Then the four client fixtures, which is what `DBX-001`–`DBX-004` are proved by.
Running them by hand is for confirming a specific worry; the host gate runs them
all.

## 4. The gate, first half

```bash
sudo bin/session-04-check.sh --mode host --host host.yaml \
  --project-a-outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
  --project-b-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json \
  --sentinel-file "$(…)"
```

**`--project-b-outputs` is required.** `transport_isolation` is a claim about two
projects, and one project cannot be isolated from nothing.

**Derive the sentinel path from the active generation**, never type it — the
generation directory changes on every start, and a hard-coded path silently names
a superseded one. The snippet is in the
[Session 3 guide](session-03-operator-guide.md#4-the-gate); change the consumer
directory to suit the secret you are planting.

This run restarts the pooler, the cluster and one project unit. That is
deliberate and non-destructive: each restarts one thing and asserts it came back,
so a failure to restore cannot pass silently. Expect it to take minutes.

## 5. The gate, second half

**From a machine that is not the deployment host.** A scan run on the host
traverses loopback and the host's own routing table, so it reports "closed" for
ports the world can reach and "open" for ports only the host can. Neither answer
is about the public boundary.

```bash
bin/session-04-check.sh --mode external \
  --public-ipv4 203.0.113.10 \
  --project-a-outputs ./alpha-dev-outputs.json \
  --project-b-outputs ./beta-dev-outputs.json \
  --ssh-destination operator@host.example
```

**`--ssh-destination` is required.** `DX-DB-001` and `DX-DB-002` are about a
developer's helper and a privileged broker reached over SSH; without a
destination both skip, and a skip is not a pass.

Copy the deployed documents off the host to run this. `--project-b-outputs` is
optional here and no external test reads it — it is passed so the merge can tell
that both halves describe the same deployment rather than two different ones.

The scan asserts **443 is open** from the same place, in the same run. Without
that control, a scan from a network that cannot route to the host at all would
report every port closed and pass while measuring nothing.

## 6. Evidence

Session 4 has two halves and **cannot be written from one**:

```bash
python bin/write-session-evidence.py --session 4 \
  --host-input evidence/session-04-host.json \
  --external-input evidence/session-04-external.json \
  --output evidence/session-04.json

jq -e '.tests.pooled_transport=="passed" and .tests.direct_transport=="passed" \
   and .tests.transport_boundary=="passed" and .tests.connection_tooling=="passed" \
   and .tests.transport_isolation=="passed"' evidence/session-04.json
```

Session 4 records **eleven claims**, cumulatively: Session 2's two, Session 3's
four, and Session 4's five. Sessions 2 and 3 do not stop making their promises
because the product grew a pooler.

If you run only the host half, the writer refuses and names the claims that are
measured from outside. That is the guard working
([ADR 0045](decisions/0045-a-claim-is-shaped-by-where-it-can-be-measured.md)), not
a bug.

## 7. Restart, reboot, rotation

All three are in [pool operations](pool-operations.md), which is where they
belong: they are things you do to a running system rather than steps in a
deployment. The two flags that admit their proofs are `--after-reboot` and
`--rotated-from-file`, and each is a declaration that something happened —
written so that a false declaration fails rather than passes.

## Traps

**A restart does not pick up a code change.** The installed launcher runs the
release the deployed document records (ADR 0037). Redeploy.

**`docker exec` without `-i` discards heredoc stdin and exits 0**, so a psql block
appears to run and does nothing.

**`pg_isready` succeeds against the image's temporary initialisation server**, so
`compose up --wait` can return mid-`initdb`. Anything that must talk to the real
cluster waits for two consecutive successful queries.

**Loopback is trusted inside the cluster's own container.** The image's
`pg_hba.conf` carries `host all all 127.0.0.1/32 trust` above its `scram-sha-256`
line, so a credential test run with `psql -h 127.0.0.1` inside the postgres
container succeeds with *any* password. Only a connection arriving from another
address reaches the line that checks one.

**Secret generations accumulate.** Nothing prunes them, and the deployed
document's `secrets.generation_id` records the generation the deploy *verified*,
which is not the one that is current after any restart (ADR 0038). Read the
pointer for the live value — and keep the previous generation until the rotation
proof has run against it.

**Never put a GitHub credential on the VPS.** Transport is `git bundle` + `scp`.

**Failed ACME validations are capped at 5/hour/hostname.** Never retry in a loop.
DNS records stay DNS-only / grey cloud.
