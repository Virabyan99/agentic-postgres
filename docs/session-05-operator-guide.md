# Session 5 operator guide

Publishing a REST surface and a documentation page over the edge, proving what
they refuse, and proving what a stranger cannot reach.

This assumes Session 4 is done: the project is deployed with its cluster, pooler
and both transports. If not, start with the
[Session 4 operator guide](session-04-operator-guide.md).

Background: [the API surface](api-surface.md) ·
[API operations](api-operations.md) ·
[database security](database-security.md).

## 0. What changed for an operator

**`--through-session 5` starts two more services.** A REST plane and a
documentation page. The launcher reads `deployed_through_session` from the
deployed document, so a project deployed through Session 4 and never redeployed
comes back as a Session 4 project — with neither route, and every signal below
them green.

**Ten migrations.** 0010 makes the pre-request hook carry each role's
`statement_timeout` into its request, which is what makes the manifest's declared
timeouts bind at all.

**One new provider secret**: `docs_basic_auth_password`. It has a **root-plane
consumer only** — no container holds it. The credential lives in Traefik's file
provider, written by the deploy.

**`app_runtime`'s connection limit drops.** It used to hold everything the server
had; it now holds what is left after the API's share (ADR 0070). On the example
manifest that is 42 → 29. This is the first Session 5 redeploy that tightens a
live limit rather than only moving documents.

**The gate is `bin/session-05-check.sh`**, three modes, and external mode is not
optional here: Session 5 is the first session whose public surface carries
authorization, so what a stranger can reach is a measurement rather than an
inference.

## 1. Deploy

Both projects, because the isolation proofs need two:

```bash
cd ~/agentic-postgres
git fetch /tmp/apg-session5.bundle main && git checkout -B main FETCH_HEAD
git log --oneline -1        # confirm the sha you just fetched

sudo ./deploy.sh --host host.yaml --project project.alpha.yaml \
     --capabilities capabilities.yaml --through-session 5
sudo ./deploy.sh --host host.yaml --project project.beta.yaml \
     --capabilities capabilities.yaml --through-session 5
```

**Read step 3's `release <sha>` line and confirm it is the sha you fetched.** A
skipped fetch has already produced one deploy of the previous commit.

What step 7 must print:

```
  tls          issued (production)
  health       ready
  docs         ready
  database     observed
```

`docs ready` means the route **refused** — 401 with a Basic challenge. It is the
only outcome that records as ready, and a 200 there is worse than an unpublished
route.

## 2. The first deploy cannot publish `api.status: ready`

That is not a fault. `api.status` requires three checksums, one of which is the
reviewed OpenAPI snapshot — and the snapshot is captured *from* a running
deployment. So:

```bash
sudo bin/api.sh contract --update --project-outputs /etc/.../outputs.json
git diff contracts/postgrest-openapi.canonical.json     # review it
git add -A && git commit
```

Redeploy at the approved commit. The second deploy is what publishes.

## 3. Verify by hand

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://<domain>/api/rest          # 200
curl -s -o /dev/null -w '%{http_code}\n' https://<domain>/api/rest/notes    # 401
curl -s -D - -o /dev/null https://<domain>/docs/rest | head -1              # 401
```

A 404 anywhere here is ambiguous. **Read the access log before diagnosing it** —
Traefik's own 404 and a routed one are identical from outside.

## 4. The gate, host mode

```bash
sudo bin/session-05-check.sh --mode host --host host.yaml \
  --project-a-outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
  --project-b-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json
```

It writes `evidence/session-05-host.json` and hands the evidence directory back
to you — the gate runs under `sudo`, and root-owned evidence is evidence the
person who has to commit it cannot read.

## 5. The gate, external mode

**From a different network.** A scan run on the host measures its own routing
table.

```bash
bin/session-05-check.sh --mode external \
  --public-ipv4 <address> --ssh-destination op@<address> \
  --project-a-outputs ./alpha-outputs.json
```

Copy the deployed documents down first; the gate takes deployed documents, not
manifests, because a manifest describes what was asked for.

## 6. Evidence

Both halves, then the merge. The writer refuses a session document that is silent
about a claim, so neither half alone is the document:

```bash
python bin/write-session-evidence.py --session 5 \
  --host-input evidence/session-05-host.json \
  --external-input evidence/session-05-external.json \
  --output evidence/session-05.json
```

## 7. The maintenance window

Restarts, rotations and the reboot proof are in
[API operations](api-operations.md) and [pool operations](pool-operations.md),
which is where they belong. The flags that admit their proofs —
`--after-reboot`, `--rotated-from-file`,
`--rotated-authenticator-from-file`, `--rotated-docs-from-file`,
`--rotated-jwt-from-file` — are declarations that something happened, and each is
written so that a **false declaration fails rather than passes**.

Rotate one credential per window. Write the pre-rotation value to a file before
you rotate; you cannot recover it afterwards, and a proof you cannot admit is a
proof that skips.

## Traps

**A restart does not pick up a code change.** The installed launcher runs the
release the deployed document records. Redeploy.

**`sudo` rewrites `.git/index` as root.** The deploy hands it back; if a run dies
before that, `sudo chown op:op .git/index` before fetching again — the transport
is a bundle and a fetch, so a broken `git` breaks the only way to deliver the fix.

**A deployed document at an older schema version stops validating.** Every
outputs version bump costs a redeploy of every project, which is the price ADR
0053 accepted.

**`docker exec` without `-i` discards heredoc stdin and exits 0**, so a psql block
appears to run and does nothing.

**A skip is not a pass.** If a rotation proof skipped, no rotation was measured —
whatever else the run reported.
