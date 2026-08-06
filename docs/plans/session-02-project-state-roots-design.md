# Session 2 — Project state roots and the runtime override

**Date:** 2026-08-06
**Status:** Approved, not yet implemented
**Decision record:** [ADR 0020](../decisions/0020-project-state-roots.md)
**Starting commit:** `7244cb9`

This design covers the step between "secrets are materialized" and "a project
container runs": making `./deploy.sh --through-session 2` work, and making the
systemd project path work, which are two different problems.

## 1. What is broken

Three defects, found by reading the code rather than the plan.

**The launcher and the script it invokes disagree on the state root.**
`libexec/agentic-postgres-project` reads from `/etc/agentic-postgres/projects/<key>/`;
`bin/project-runtime.sh`, `bin/compose.sh` and `src/agentic_postgres/deployed_output.py`
read from `/var/lib/agentic-postgres/projects/<key>/`.

**The launcher's three required files have no writer.** `deployment.json` is
written under no name — the deployed document is `outputs.json` — and the field
read from it, `installed_release_commit`, belongs to edge state; a deployed
document records `source_commit`. The launcher exits 4 at line 70 and has never
run.

**`assert_disjoint` compares one file with itself.** `project-runtime.sh` passes
the state directory as the Compose project directory, so `compose.sh` resolves
`<state>/compose.env` as both `project_env` (line 295) and `runtime_env` (line
316). Every key overlaps, exit 5, unconditionally.

The contract test written to catch the first two — `test_edge_state.py::test_every_state_file_a_launcher_requires_has_a_writer`
— finds one path when run against the tree, the one it was written for. Its scan
requires a `readonly` declaration ending in `.json`; the launcher composes paths
with `local` and interpolation, and two of its files are `.yaml`.

## 2. Layout

| Root | Rule | Contents |
|---|---|---|
| `/etc/agentic-postgres/projects/<key>/` | Operator-supplied, or records a decision. Not regenerable. | `manifest.yaml`, `secrets.required.yaml`, `bootstrap-state.json`, `outputs.json` (deployed), `compose.env` (host-derived) |
| `/var/lib/agentic-postgres/rendered/<key>/` | Tool-generated, regenerable from the manifests. | `compose.env` (rendered), `outputs.json` (rendered), `runtime-compose.override.yaml` |
| `/opt/agentic-postgres/releases/<commit>/` | Immutable code. Unchanged. | pristine copy of the tree |

`outputs.json` in both roots is deliberate; `output_migrations.require_kind`
already exists for that reason.

## 3. Changes

### 3.1 `src/agentic_postgres/deployed_output.py`

`PROJECT_STATE_ROOT` becomes `/etc/agentic-postgres/projects`. Add
`RENDERED_ROOT = Path("/var/lib/agentic-postgres/rendered")` and a
`rendered_path(project_key)` beside the existing `deployed_path`.

### 3.2 `bin/compose.sh`

`PROJECT_STATE_ROOT` (line 74) becomes `/etc/agentic-postgres/projects`. No
other change: the disjointness logic is correct and was being fed the same file
twice.

### 3.3 `bin/project-runtime.sh`

Split the single `state` into two resolved directories:

- `STATE_DIR=/etc/agentic-postgres/projects/<key>` — `manifest.yaml`,
  `secrets.required.yaml` for the `materialize-secrets.sh` call
- `RENDERED_DIR=/var/lib/agentic-postgres/rendered/<key>` — the Compose project
  directory passed to `compose.sh`

Both are validated the way `state_directory()` validates today: must exist, must
not be a symlink, exit 4 when absent. `status` (line 120) changes too — it
passes the state directory today and would fail for the same reason `up` does.

### 3.4 `bin/deploy-session-2.py`

Step 4 grows from writing one file to establishing both roots:

1. Create `/etc/.../projects/<key>/`, `0700 root:root`.
2. Copy the project manifest and the secret contract in, `0600 root:root`.
3. Write the host-derived `compose.env` there, `0600 root:root`.
4. Create `/var/lib/.../rendered/<key>/`, `0700 root:root`, and install
   `.generated/<key>/` into it.
5. Write `runtime-compose.override.yaml` into the rendered directory.

Step 5 is unchanged in shape — it still calls `project-runtime.sh`. Step 6's
deployed document goes to the `/etc` state directory via the updated
`deployed_path`.

Installation is copy-to-temp-then-`os.replace` on the directory, so a failed
deploy never leaves a half-written rendered directory that the next boot would
treat as complete.

### 3.5 `runtime-compose.override.yaml`

Written by the deploy because it is the only component holding a host manifest;
`--render-only` therefore keeps working with no host and no root, unchanged.

It carries what `compose.yaml` deliberately omits (see the comment at
`compose.yaml:52-61`): `traefik.enable`, the router labels whose *keys* contain
the router name, and the service port. Keys are fully rendered rather than
interpolated, because `traefik.http.routers.${X}.rule` is not portable to
`COMPOSE_MINIMUM_VERSION=2.24.0`.

Inputs are all present already: `HEALTH_ROUTER_NAME` is emitted into the
rendered `compose.env` by `rendering.py:239`, `HEALTH_ROUTE_PATH` is
`/__apg/healthz`, and the resolver name comes from `host.yaml`'s
`edge.acme_resolver_name`.

### 3.6 `libexec/agentic-postgres-project`

Reads `outputs.json`, not `deployment.json`. Resolves the release from
`.source_commit`, not `.installed_release_commit`. `STATE_ROOT` is already
correct and does not move. Every existing validation — key pattern, hex commit,
length, symlink refusal, root ownership — is kept as is.

## 4. Error handling

New paths inherit the checks the launchers already apply: symlinks refused,
root ownership required, `0700` directories and `0600` files. The override and
the deployed document are written tempfile-then-`os.replace`, matching
`write_deployed_document`. The deploy fails closed when `.generated/<key>/` is
absent rather than installing an empty directory.

## 5. Testing

**Contract, offline.**

- Generalize `test_every_state_file_a_launcher_requires_has_a_writer`: resolve
  `${VAR}` against `readonly` assignments in the same launcher, match `local` as
  well as `readonly`, accept `.yaml` and `.env` alongside `.json`. It must find
  every file all four launchers open, and each must have a writer. This is a
  strengthening and is authorized by ADR 0020.
- A test that the rendered root and the state root are different prefixes, so
  the self-comparison cannot return.
- Offline unit tests for the override builder: rendered keys, no interpolation
  left in any label key.

**On the host, and not deferred.**

- `sudo ./deploy.sh --host host.yaml --project project.alpha.yaml --capabilities capabilities.yaml --through-session 2`
- `sudo systemctl start agentic-postgres-project@alpha-dev` — the launcher path
  has never executed; correcting it proves nothing until it runs.
- `curl -k --fail https://alpha-db.agenticpostgresql.com/__apg/healthz`
- External, from another network, per the lesson that host-local checks missed
  the redirect-port defect.

**Gate.** `bin/session-01-check.sh` exits 0 on a clean tree at the end of every
commit, as always.

## 6. Sequencing

Small commits, each ending green, transported to the host and verified there:

1. ADR 0020 and this design.
2. The generalized writer scan, plus the launcher correction it names. Roots
   moved: `deployed_output.py`, `compose.sh`, `project-runtime.sh`.
3. Deploy writes both roots; override generator.
4. Host run, then Run 7.

Within step 2 the scan is written and observed failing — naming
`deployment.json`, `manifest.yaml` and `secrets.required.yaml` as orphans —
before any fix is written. That observation is the point: the scan is the thing
that would have caught this class, and writing it afterwards would prove only
that it agrees with the fix. The observation happens mid-run against
`bin/smoke-test.sh`; the commit boundary lands after the fix, so
`bin/session-01-check.sh` is green on a clean tree at every commit, as required.

## 7. Divergences from the session-02 plan

The plan is a source of tasks, not of code; where it disagrees with the tree,
the tree wins.

| Plan says | Tree says | Followed |
|---|---|---|
| `schemas/deployment-state.schema.json` exists (Run 1) | No such file; deployed state is `outputs.json` under `outputs.schema.json` with `document_kind: "deployed"` | Tree |
| Router-key rendering is "D12" | The code cites ADR 0013 (`compose.yaml:56-58`) | Tree — cite ADR 0013 |
| Project state lives at one root | Two roots, contradictory | Resolved by ADR 0020 |
