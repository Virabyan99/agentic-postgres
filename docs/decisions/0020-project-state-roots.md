# 0020 — Configuration in /etc, generated output in /var/lib

- **Status:** Accepted
- **Date:** 2026-08-06
- **Session:** 2
- **Affects:** `libexec/agentic-postgres-project`, `bin/project-runtime.sh`, `bin/compose.sh`, `bin/deploy-session-2.py`, `src/agentic_postgres/deployed_output.py`, `test_every_state_file_a_launcher_requires_has_a_writer`, `test_the_recorded_paths_match_the_schema_patterns`

## Context

A project had two state roots, and nothing reconciled them.

`libexec/agentic-postgres-project` — the launcher `agentic-postgres-project@.service`
invokes — read `deployment.json`, `manifest.yaml` and `secrets.required.yaml`
from `/etc/agentic-postgres/projects/<key>/`. The script it execs,
`bin/project-runtime.sh`, read the same two manifests from
`/var/lib/agentic-postgres/projects/<key>/`. `bin/compose.sh` and
`src/agentic_postgres/deployed_output.py` agreed with the second.
`bootstrap_state` wrote to the first, and on the live host
`/etc/agentic-postgres/projects/alpha-dev/bootstrap-state.json` already existed.

None of the three files the launcher requires had a writer. `deployment.json`
was never written under any name: `deployed_output.deployed_path()` produces
`outputs.json`. The field the launcher reads out of it,
`installed_release_commit`, appears only in `edge-state.schema.json`; a deployed
document records `source_commit`. The launcher therefore exits 4 before it
reaches `project-runtime.sh`, and had never been executed once.

`tests/contract/test_edge_state.py::test_every_state_file_a_launcher_requires_has_a_writer`
exists to catch exactly this. It did not, because its scan matches
`^readonly \w+="(/(?:etc|var)/[^"]+\.json)"`. Run directly against the tree it
returns a single path:

```
scan finds: ['/etc/agentic-postgres/edge-state.json']
```

The launcher composes its paths at the use site
(`local deployment="${STATE_ROOT}/${project_key}/deployment.json"`) rather than
declaring them as `readonly` literals, and two of the three files end in
`.yaml`. The test generalised in its prose and not in its code.

A second defect sat underneath. `project-runtime.sh` passed the state directory
to `compose.sh` as the Compose project directory, so `compose.sh` resolved
`<state>/compose.env` as both the project env file and the runtime env file and
called `assert_disjoint` on one path twice. Every key overlaps with itself, so
the runtime path could only ever exit 5.

## Decision

Two roots, each with one rule.

`/etc/agentic-postgres/projects/<key>/` holds what an operator supplied or what
records a decision: `manifest.yaml`, `secrets.required.yaml`,
`bootstrap-state.json`, the deployed `outputs.json`, and the host-derived
`compose.env`. It is not regenerable and it survives.

`/var/lib/agentic-postgres/rendered/<key>/` holds what the tool generated and
can regenerate from those manifests: the rendered `compose.env`, the rendered
`outputs.json`, and `runtime-compose.override.yaml`.

`/opt/agentic-postgres/releases/<commit>/` is unchanged and stays a pristine
copy of the tree, so the ownership and immutability checks the launchers apply
keep meaning what they say.

`outputs.json` appears in both roots. That is deliberate and predates this ADR:
`output_migrations.require_kind` exists because the two document kinds share a
basename.

The launcher is corrected to read `outputs.json` and `.source_commit`. Its
`STATE_ROOT` was already right and does not move.

`compose.sh` keeps its logic unchanged. Because the Compose project directory is
now the rendered directory, its two env files are finally two different files and
`assert_disjoint` compares real content.

`runtime-compose.override.yaml` is written by `bin/deploy-session-2.py`, which is
the only component holding a host manifest. `--render-only` keeps working with
no host and no root, unchanged and without special-casing.

## Consequences

The generalised writer scan is a strengthened contract test, which the
non-negotiable constraints permit only with an ADR. This is that ADR. The scan
resolves `${VAR}` against `readonly` assignments in the same launcher, matches
`local` as well as `readonly`, and accepts `.yaml` and `.env` alongside `.json`.

`PROJECT_STATE_ROOT` moves in three modules that currently agree with each
other. They agree on a value the launcher never used, so the agreement was
between consumers, not with the system.

`test_the_recorded_paths_match_the_schema_patterns` pins `deployed_path` to a
path literal, so relocating the root breaks it mechanically. The literal is
updated to `/etc/agentic-postgres/projects/<key>/outputs.json` and the
assertion keeps its meaning: it still pins the built path against the schema
pattern. That is a consequence of the decision above rather than a separate
one, which is why it is recorded here instead of in its own ADR.

The systemd project path has never run. Correcting the launcher is necessary but
proves nothing on its own: `systemctl start agentic-postgres-project@<key>` is
part of the acceptance for this change, on the host, and not a deferred item.

## Alternatives considered

**Make `/var/lib` canonical and move `bootstrap-state.json` to it.** Three
modules already say `/var/lib`, so this touches less code. Rejected: it requires
migrating live, converged bootstrap state on the host — the one thing in Session
2 that is proven and idempotent — to satisfy a majority among files that had
never been executed together.

**Render into the installed release.** Binds rendered output to the code that
produced it. Rejected: the release stops being a pristine copy, which is what
`stat -c '%U'` and the symlink refusals in both launchers depend on.
