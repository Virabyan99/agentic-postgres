# Session 2 operator guide

The ordered path from a fresh Ubuntu host to two isolated projects on trusted
certificates, and how to find out whether it worked.

Every command here verifies or acts. None of them does both: a gate that
deployed the system it measures could not be re-run to confirm a fix, and its
result would depend on whether it was the first run.

## Inputs you supply

Four files, none of them tracked, all of them gitignored explicitly because
`bin/session-01-check.sh` fails on any untracked file and also runs on this
host:

| File | From | Contains |
|---|---|---|
| `host.yaml` | `host.example.yaml` | The real host, DNS and provider coordinates. **No secret.** |
| `capabilities.yaml` | `capabilities.example.yaml` | Agent capability grants |
| `project.alpha.yaml` | `project.example.yaml` | Project A |
| `project.beta.yaml` | `project.second.example.yaml` | Project B |

The control-plane credential is a **separate root-owned file**, passed to
bootstrap by path and never named in a manifest.

DNS: `A` records for each project hostname, **DNS-only / grey cloud**. A proxied
record breaks HTTP-01 validation. Publish `AAAA` only when IPv6 ingress
genuinely works — see [host baseline](host-baseline.md).

## The order

Each step assumes the previous one succeeded. Nothing here makes its own
preconditions: `deploy.sh --through-session 2` expects the host to be ready, the
edge to be up, providers bootstrapped and secrets materialized. A deploy that
silently performed those would leave nobody able to say which half failed.

### 1. Host baseline

Three `--apply` passes with two rollback timers. Full procedure in
[host baseline](host-baseline.md) — read it before running anything, because
step 2 and step 3 can lock you out.

```bash
sudo bin/provision-host.sh --host host.yaml --check      # default; changes nothing
sudo bin/provision-host.sh --host host.yaml --apply
```

Verify the baseline before deploying anything:

```bash
sudo bin/session-02-check.sh --mode host --host host.yaml --baseline-only
```

`--baseline-only` writes no evidence, deliberately. Every project test skips for
want of `APG_PROJECT_A_OUTPUTS`, and a verdict from a run where they never
executed would assert something nobody measured.

### 2. Edge plane

```bash
sudo bin/edge.sh --host host.yaml up
bin/edge.sh --host host.yaml status        # redacted; readable without root
```

The edge starts on **staging** ACME certificates. Production is never selected
from source; it is reached only by the promotion in step 6.

### 3. Provider bootstrap, per project

```bash
bin/bootstrap-providers.sh --host host.yaml --project project.alpha.yaml --plan
sudo bin/bootstrap-providers.sh --host host.yaml --project project.alpha.yaml \
     --apply --operator-credential-file /root/.config/agentic-postgres/infisical.json
```

Run `--plan` again afterwards. It must report no changes.

### 4. Materialize secrets, per project

```bash
sudo bin/materialize-secrets.sh --project project.alpha.yaml \
     --requirements secrets.required.yaml --session 2
```

### 5. Deploy, per project

```bash
sudo ./deploy.sh --host host.yaml --project project.alpha.yaml \
     --capabilities capabilities.yaml --through-session 2

curl --fail https://alpha-db.<domain>/__apg/healthz
```

Repeat steps 3–5 for project B **while still on staging certificates.**

### 6. Promote to production certificates

Once — for the host, not per project — and only after every configured hostname
has answered on a staging certificate.

```bash
sudo bin/edge.sh --host host.yaml promote-acme --to production --confirm <host.id>
```

Deploying project B *before* the promotion is a deliberate reordering of the
plan's Run 7 (divergence D33). `staging_certificate_exists` can only see the
first project's hostname, so promoting first would make B's first-ever
certificate request a **production** one against a route that had never issued
anything.

> **Rate limits.** Let's Encrypt production allows 50 issuances per registered
> domain per week and 5 duplicate certificates per week; failed validations are
> capped at **5 per hour per hostname**. The way people exhaust these is deleting
> state and re-requesting in a loop. **Never retry in a loop.** If the limit is
> reached, stop, do not delete `production.json`, and finish the session on
> staging with the deviation recorded.

There is no `--to staging`. Staging is where the edge starts, and going back is
a re-render, not a command.

### 7. Verify

Three environments, three commands, because they cannot be one. A port scan run
on the host traverses loopback and the host's own routing table, so it can
report "closed" for a port the world can reach.

```bash
# In CI or a checkout: contracts, schemas, models. No host, no network.
bin/session-02-check.sh --mode offline

# On the host, as root.
sudo bin/session-02-check.sh --mode host --host host.yaml \
  --project-a-outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
  --project-b-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json \
  --sentinel-file "$(derive from active-secret-generation.json)"

# From a network that is NOT the host.
bin/session-02-check.sh --mode external --public-ipv4 <address> \
  --project-a-outputs <copy of A's deployed document> \
  --project-b-outputs <copy of B's deployed document>
```

Derive the sentinel path from the **active** generation rather than typing it.
The generation directory changes on every materialize, and a hard-coded path
silently points at a superseded one:

```bash
python3 -c "
import json
from pathlib import Path
root = Path('/var/lib/agentic-postgres/secrets/alpha-dev')
gen = json.loads((root / 'active-secret-generation.json').read_text())['generation_id']
print(root / 'generations' / gen / 'secret-check' / 'session2_sentinel')
"
```

The deployed documents are `0600 root`. Copy them to the external machine
deliberately; they carry no secret (`assert_output_is_secret_free` applies to
both document kinds), but they do name the deployment.

### 8. Merge the evidence

```bash
python bin/write-session-evidence.py --session 2 \
  --host-input evidence/session-02-host.json \
  --external-input evidence/session-02-external.json \
  --output evidence/session-02.json

jq -e '.tests.secret_leakage=="passed" and .tests.isolation=="passed"' evidence/session-02.json
```

The merge is not a union. It **fails when the halves disagree** about the source
commit, the project keys, the routes or the certificate fingerprint — that
disagreement means the external run measured a host that had already moved on.
Both halves must therefore be given the same `--project-*-outputs`.

`tests` is keyed by **claim**, not by suite name. Each claim's verdict comes
from the JUnit results of every node ID the acceptance registry lists for its
requirements; a proof that was skipped, or absent from the artifact, is not a
pass ([ADR 0025](decisions/0025-evidence-names-the-claim-not-the-suite.md)).

`-k` writes no evidence in any mode. It selects a subset, and a subset cannot
support a claim about the whole.

### 9. Close

```bash
python bin/render-acceptance-matrix.py --check
git status --porcelain          # must be empty
bin/session-01-check.sh         # must exit 0, on the host too
```

## Day-two operations

```bash
sudo systemctl restart agentic-postgres-project@alpha-dev.service
sudo bin/edge.sh --host host.yaml reconcile      # re-attach every project
bin/edge.sh --host host.yaml status
sudo bin/docker-firewall.sh status
```

`bin/project-runtime.sh` and `bin/edge-network.sh` are invoked by the units and
are not normally run by hand. Always use `bin/compose.sh`, never `docker compose`
directly: inherited shell variables win over `--env-file`, which would silently
point a command at the wrong project or bypass a locked digest.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `2` | Invalid operator input or manifest |
| `3` | Missing prerequisite, or not root |
| `4` | Missing runtime state — the project was never deployed here |
| `5` | Contract, lock, collision, or generated-output validation failure |
| `6` | A host or gate check failed |
| `7` | The provider rejected an operation, or state disagrees with it |
| `8` | A secret could not be fetched or written |
| `9` | The edge could not be brought to the requested state |
| `10` | Capability intentionally unavailable in the current session |

## See also

- [Host baseline](host-baseline.md)
- [Provider bootstrap](provider-bootstrap.md)
- [Project isolation](project-isolation.md)
- [Secret handling](secret-handling.md)
- [Session 2 implementation plan](plans/session-02-implementation-plan.md) — the
  divergence table and the decision log
