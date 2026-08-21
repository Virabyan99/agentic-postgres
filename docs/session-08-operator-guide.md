# Session 8 operator guide — the agent plane

Read this once before the host trip, then work through §4 in order and **stop at
the first thing that surprises you**.

Session 7's guide is the parent of this one and its corrections are carried
forward (D378, D379, D383, D384). What is different is what Session 8 needs from
you, and the short answer is: **much less than Session 7 did.**

---

## 0. What Session 8 adds, and what it needs from you

Session 8 builds the **agent plane**: a fourth container, a third `APP_MODE` of
the application image, serving four read-only MCP tools at one published path.

**There is no provider step.** No Cloudflare, no bucket, no API token, no new
Infisical folder, no operator-supplied secret of any kind. Everything the agent
plane needs is derived by the renderer or already materialized — the rendered
public key set, the compiled capability lock, the internal upstream address, and
a memory limit. **It holds no database credential and no signing material**
(D407, ADR 0121), so there is nothing for you to create and nothing for you to
keep safe.

**What it does need from you is four things**, and three of them are ordinary:

| | What | Why it needs a human |
|---|---|---|
| 1 | Transport the release to the host | `git bundle` + `scp`; no GitHub credential goes on the VPS |
| 2 | **Sync the host venv** | `fastmcp` is new this session. Without it nothing imports (D384, D297) |
| 3 | Apply migration **0018** | Forward-only, as `migration_user`, never as a superuser (D285) |
| 4 | **Deploy twice** | D326's two-stage convergence. §3 is the whole explanation |

Everything else is a gate run.

---

## 1. What is irreversible, and what is merely disruptive

Four things this session does cannot be undone by re-running a command. Three of
them already happened in the repository; only the last is yours.

**Already done, in the tree you are about to transport:**

- `CURRENT_SESSION` moved to **8** (Run 6, D439). This **arms the `session8`
  Compose profile**, so the next deploy of *any* project at
  `--through-session 8` starts an MCP container. It is designed to fail closed
  without its inputs rather than start without them, and §4 step 2 is what
  supplies them.
- `agent_reader` is activated in the bootstrap plane (ADR 0116). Granting the
  authenticator membership in a role widens what a token may name.
- Migration **0018** is frozen in the lock.

**Yours, and the one to think about:**

- **Publishing the capability lock.** The deployed lock is what the runtime
  obeys. A lock built from an unreviewed OpenAPI capture is a capability surface
  nobody approved, which is the whole failure mode `capabilities.yaml` exists to
  prevent. The deploy compiles it from the committed contract; you are not asked
  to hand one over, and **the gate refuses a `--capability-lock` flag** for
  exactly this reason.

**`sudo` needs a TTY**, so anything privileged that mutates is run by a human at
a terminal, never piped over `ssh`. Read-only diagnosis is not — but note
**D380**: `apg-diag`'s service allowlist is `postgres pgbouncer postgrest docs
edge-probe dbmate`. It has no `auth`, no `storage` and **no `mcp`**, so a
read-only question about the agent plane's logs still sends you to a terminal.
Widening it is an ADR-shaped decision nobody has taken.

---

## 2. What must NOT be attempted this session

**Do not activate `mcp_audit_service`.** The role exists, unactivated, since
Session 3. Activating it puts an audit identity in production **before the record
it writes has been designed**, and Session 9 owns that with its own fail-closed
contract. What exists today is telemetry — one structured log record per tool
call — and it is deliberately durable nowhere (D412, ADR 0130).

**Do not activate `agent_writer`.** Session 8 is reads. The role is derived and
granted nothing; Session 9 owns writes, and it owns them together with the audit
record a write requires.

**Do not run the signing-key rotation during this trip unless you mean to.**
There are **four** verifiers now — PostgREST, auth, storage and the agent plane
(ADR 0113, ADR 0122) — and after any phase that changes the published key set,
**every one of them is recreated, not restarted** (ADR 0088). The agent plane
reads the same rendered `jwks.json` the others do. If you do run it, the gate's
`--rotated-jwt-from-file` flag is what admits the proofs.

---

## 3. Deploy twice, and why that is not a workaround

`routes.mcp` is published with an **observed** status, not a declared one: the
deploy asks the edge whether the route is being served and writes down the
answer. The deploy that *first* starts an MCP container observes it **before
Traefik has attached the router**, so it correctly publishes:

```json
"mcp": { "status": "unavailable", "url": null }
```

That is D326's two-stage convergence and it is the system working. The redeploy
observes a route that is now attached and publishes `ready`.

**Two consequences you need before the gate:**

1. `bin/session-08-check.sh --mode host` **refuses** a document whose
   `routes.mcp` is not `ready`, before it runs anything. The message says
   `DEPLOY AGAIN`. That refusal replaces forty proofs failing on a connection
   error.
2. **Outputs moves v11 → v12 on this trip.** Both hosts currently carry v11;
   this tree renders v12. `evidence.py` refuses a deployed document that is not
   the current version, so **the redeploy is a prerequisite of the gate rather
   than a consequence of it.** Storage went through the identical step in
   Session 7; this is the normal cost of a version bump and it is written here
   so it is not discovered at step 6.

---

## 3.1 What has already been done for you

Steps 0, 1, 2 and 5 are **complete**. They need no `sudo`, so they were run over
SSH as `op` rather than waiting for a terminal:

| Step | State |
|---|---|
| 1. Transport | Host is at **`42db9e4`**, clean tree, on `main` |
| 2. Venv sync | **fastmcp 3.4.0**, protocol `2025-11-25` — imports confirmed |
| 0. Re-render | **All four** projects at **v12** (D462) |
| 5. Offline gates | `session-01-check` **PASSED** (3474 passed, 143 skipped, 0 identity collisions); `session-08-check --mode offline` **PASSED** |

**What is left is steps 3, 4 and 6 — every one of them `sudo`.** Plus one
`install` so the external half can read the deployed documents. §4 gives them in
order; nothing else in this guide needs a human.

---

## 4. The Run 9 host sequence, in order

Everything Session 8 built is written and **the agent plane has never started
anywhere**. Session 6's first host trip found nine defects; Session 7's found
eight product defects and ten process rows, every one invisible to a green
offline suite. **Expect this trip to find things.** That is what it is for.

**0. Re-render — ON THE HOST, after transport, and ALL FOUR projects (D383,
D462).**

```bash
./deploy.sh --project project.example.yaml        --capabilities capabilities.example.yaml --render-only
./deploy.sh --project project.second.example.yaml --capabilities capabilities.example.yaml --render-only
./deploy.sh --project project.alpha.yaml          --capabilities capabilities.yaml         --render-only
./deploy.sh --project project.beta.yaml           --capabilities capabilities.yaml         --render-only
```

`.generated/*` is gitignored, so rendered output is **not in the transport
bundle**: every machine keeps its own, and the host's was last written by
whatever release it ran before. Session 7's Run 10 followed the older wording —
"re-render before leaving the workstation" — and the host gate refused at exit 6
naming both fixtures at v10 against code rendering v11. The gate was doing its
job.

> **The last two lines are D462, and they were learned by leaving them out.**
> With only the fixtures re-rendered, `bin/session-01-check.sh` exited **5** at
> its evidence step: *"these projects were rendered by an older release:
> alpha-dev (v11), beta-dev (v11)"*. That step compares **every** rendered
> project, and the host carries `alpha-dev` and `beta-dev` from real deploys —
> which the example manifests do not touch. `rendered_fixtures.py` reported
> `current` throughout, correctly: it only knows about the two example keys.

Neither root nor a running project is needed; `--render-only` runs in a bare
checkout and touches nothing in `/etc`, `/var/lib` or any container. Run it
**after** step 1.

**1. Transport.**

```bash
# workstation
git bundle create /tmp/apg.bundle main
scp -i ~/.ssh/agentic_postgres_ed25519 /tmp/apg.bundle op@62.238.99.122:/tmp/

# host, as op
cd ~/op/agentic-postgres
git fetch /tmp/apg.bundle main && git checkout -B main FETCH_HEAD
git log --oneline -1
```

**Read the sha and confirm it is the one you bundled.** Not a fast-forward
merge — `checkout -B` — and a skipped fetch has already produced one deploy of
the previous commit.

**2. Sync the host venv. This session it is not optional.**

```bash
uv pip sync requirements-dev.txt
python -c "import fastmcp, mcp; print(fastmcp.__version__, mcp.types.LATEST_PROTOCOL_VERSION)"
```

`fastmcp` is new in Session 8, pinned at **3.4.0** — a measured ceiling, because
3.4.1 cannot share a process with this repository's FastAPI (ADR 0121). D384 and
D297 are the same finding twice: the lock file is checked, the *installed
distributions* are not, so a host that skipped this reports import errors that
read like defects.

**3. Apply migration 0018, as `migration_user`.**

```bash
sudo bin/migrate.sh --project project.alpha.yaml status   # read-only, look first
sudo bin/migrate.sh --project project.alpha.yaml up
sudo bin/migrate.sh --project project.beta.yaml  up
```

**`--project`, naming the manifest — not `--outputs`.** This page said
`--outputs` until the flag was read off `--help`; there is no such flag and the
command would have failed at the first thing an operator typed with root.
`--runtime` is the flag that reads the installed rendered document.

`status` first: it lists applied and pending migrations and reads only. You want
to see **0018 pending and nothing else**.

Never as a superuser: one bypasses the ownership check that made migrations 0012
and 0013 fail on a real cluster (D285). 0018 adds the agent read plane — the
pre-request hook's fifth definition, `api.mcp_agent_context()` and
`api.owner_activity_report()`, granted to `agent_reader` alone. **No RLS policy
moves** (ADR 0117).

> **Nothing else has to be re-run first.** `--through-session` expects a
> provisioned host and does not bring up the edge, bootstrap providers or
> materialize secrets — and Session 8 needs none of them: the `mcp` service
> declares **no `secrets:` block**, so there is no new generation to materialize.
> The key set it reads is the rendered `jwks.json` the other three verifiers
> already read (ADR 0113).

**4. Deploy — twice, both projects.**

```bash
sudo ./deploy.sh --project project.alpha.yaml --capabilities capabilities.yaml \
     --host host.yaml --through-session 8
```

Then read `routes.mcp` in the deployed document. It will say `unavailable`; that
is §3. **Run the same command again**, then confirm:

```bash
sudo python3 -c "
import json
d = json.load(open('/etc/agentic-postgres/projects/alpha-dev/outputs.json'))
print(d['schema_version'], d['routes']['mcp'], d['mcp'])"
```

You want `12`, a `ready` route with a URL, and an `mcp` block carrying a
`protocol_revision`. Repeat for beta.

**5. The offline gate, on the host.** Neither needs root.

```bash
bin/session-01-check.sh
bin/session-08-check.sh --mode offline
```

> **`op` cannot reach the Docker daemon**, and both gates handle it rather than
> failing. `docker compose config` is client-side, so every model still
> resolves; what is *not* determined is step 7's second half — whether a project
> container is running — and `session-01-check` says so in as many words rather
> than passing quietly (ADR 0018). It is proved by
> `sudo bin/session-02-check.sh --mode host`.

**6. The host gate.** At a terminal, as a human, with the flags in the command —
`--help` prints it with the sentinel path derived rather than typed:

```bash
sudo bin/session-08-check.sh --mode host --host host.yaml \
     --project-a-outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
     --project-b-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json \
     --admin-password-file /root/alpha-dev-administrator \
     --sentinel-file "$(...)"
```

**7. The external gate, from somewhere that is not the host.** The assistant can
run this: it needs no TTY and no root, given fresh deployed documents (one
`sudo install -o op …` from you) and an ephemeral `ssh-agent`.

```bash
bin/session-08-check.sh --mode external --public-ipv4 62.238.99.122 \
     --project-a-outputs ./alpha-dev-outputs.json \
     --project-b-outputs ./beta-dev-outputs.json \
     --ssh-destination apg-agent@62.238.99.122
```

**This mode is only meaningful off-host.** The agent plane's health routes answer
**200 on the container's own socket** and are private by the *absence* of a
Traefik router — so a scan run on the host would report them reachable and
conclude the boundary is broken when it is working.

**8. Merge the evidence.**

```bash
python bin/write-session-evidence.py --session 8 \
  --host-input evidence/session-08-host.json \
  --external-input evidence/session-08-external.json \
  --output evidence/session-08.json
```

Both halves must describe the **same release** or the merge refuses — it did
once, and was right to. `evidence/*` is gitignored by design; regenerating it is
how you get it back.

---

## 5. What the evidence will say, and what it will not

Session 8 adds **eight claims** (ADR 0132): seven measured on the host and one —
`public_agent_boundary` — measured only from off-host, which is what makes the
external mode load-bearing rather than ceremonial.

**Every one of them reports `not_run` until this trip.** No MCP container has
started anywhere, so no proof of any of them has ever executed. A claim that has
never been measured must not be mistaken for one that passed.

**Two claims will still be red, and they are Session 5's**: `api_authorization`
and `bootstrap_identity`, blocked on the rotation window. Session 8 does not
close them and must not appear to. If you hold the window during this trip, it
closes them; if you do not, Session 8's evidence carries them red for the same
stated reason Session 7's did.

**`AGT-DRIFT-001` is a P0 requirement with a passing test and no claim**, and
that is deliberate. Its guarantee — adding an API operation exposes no capability
without a `capabilities.yaml` change — is a property of the compiler and is
complete in a checkout, so under ADR 0045 it is not a claim.

---

## 6. If something goes wrong

**The MCP container will not start.** It is designed to fail closed. Look at
`settings.load_mcp`'s refusals first: it exits rather than starting if handed a
signing key or any `APG_DATABASE_*`, and it refuses a lock it cannot parse or
whose `schema_version` it does not know. A container that starts without its key
set would refuse every request with `no key with kid` — which is D381 exactly,
and why the start is ordered settings, then key material, then lock.

**`routes.mcp` stays `unavailable` after two deploys.** Read the edge access log
before anything else. Traefik's own 404 and a routed 404 are identical from
outside; Traefik's carries no `RouterName` and a 19-byte body. And note **D387**:
the REST document observation does not retry, so a slow edge attach can publish
`unavailable` for a route that serves — it was hit twice in one trip.

**The gate refuses before running anything.** That is the design. Three
refusals have specific meanings:

- *rendered fixtures are absent/stale* → step 0, on the host.
- *routes.mcp is not ready* → §3, deploy again.
- *routes.mcp is not a published-route object* → the deployment predates outputs
  v12. Redeploy.

**A proof fails that has never run before.** Expect this. Record it as a
divergence row with all six columns rather than fixing it silently — and ask
§6's fourth question of it: when this defect class was fixed before, which side
got the fix, the product or the proof?
