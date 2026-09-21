# 0228 — A workflow definition is a project artefact compiled against the lock and installed by the deploy, immutable per name and version

- **Status:** Accepted
- **Date:** 2026-09-21
- **Session:** 32, Run 1 (D1657, D1660)
- **Affects:** a new `schemas/workflow.schema.json`, new
  `src/agentic_postgres/workflow_definition.py` and `workflow_install.py`, a
  new `bin/workflow.sh` / `bin/workflow.py` (`init`, `validate`),
  `bin/deploy-project.py` (a new step 6d), `bin/dev.py`'s `up`, and two new
  files under `projects/example/workflows/`.
- **Related:** ADR 0198/0201 (a project's own migration set; the joined lock),
  ADR 0200 (the vocabulary is derived from the surface), ADR 0203 (`apg dev`
  is the database alone), ADR 0127 (the lock is the authority on every call),
  ADR 0182 (a dry run), ADR 0093 (a `bin/` command imports only
  `agentic_postgres` and `yaml`), D912, D1114.

## Context

A workflow needs something to execute. The question is what a definition *is*
and when it is bound: a file the loop reads at run time, a document submitted
with the run, or a reviewed artefact installed like a migration.

Two facts from the tree shape the answer.

**A capability is versioned; a tool is not.** `Tool.capabilities` is a tuple of
`CapabilityRef(name, version, lifecycle, risk)` (`mcp_lock.py:109,186`), and
`query_resource` is backed by **two** capabilities — `query_notes@1.0.0` and
`query_tasks@1.0.0`. So a step's referent must be the versioned thing, and the
compiler resolves it *to* the tool that serves it.

**The runtime reads its lock from a mounted file the deploy writes**
(`runtime_override.py:427-435`). Nothing today stores a definition at all.

## Decision

**A definition is YAML under `projects/<slug>/workflows/<name>.yaml`**,
validated against `schemas/workflow.schema.json` and compiled against the
project's lock — the release's joined with the project's (ADR 0201), resolved
by **calling the product's own join** rather than re-implementing it (D1114).

**A step names a capability `name@version`.** The compiler refuses, by name and
naming the step: an unknown capability; a version the lock does not carry; a
`lifecycle` other than `active`; a capability whose tool is `metadata`; a
capability with `requires_approval` (*approval steps arrive in Session 33*); an
argument the tool does not declare; a `{{steps.<name>.<field>}}` reference to a
later or unknown step; `retry.max` > 5; `backoff_seconds` > 300; a step
`timeout_seconds` below the tool's `timeout_ms`/1000 or above 600; a run
`timeout_seconds` above 3600.

The compiled body carries **`required_scopes`** (the union of the steps'),
**`lock_tools_sha256`** and **`source_sha256`** over the YAML bytes.

**Definitions are ROWS**, in `workflow_definition`, installed by the deploy at
a new **step 6d** — after the migrations, before the deferred services of step
6b — and by `apg dev up`, through `workflow_install_definition` as the
bootstrap superuser. The body is passed as a **psql variable**, never formatted
into the statement. A `(name, version)` is **immutable**: re-installing it with
a different `source_sha256` refuses the deploy at exit 5. A definition is
fixed forward by a new version, which is D912's rule applied to a definition.

**The loop does not compare `lock_tools_sha256` at run time.** It holds no
lock; the plane enforces the lock on every call. The digest is a record of what
`validate` compiled against, reported by `status` so a reader can tell whether
the lock has moved since.

**The trip's definitions** (D1657): `projects/example/workflows/
notes-roundtrip.yaml` is `create_note@1.0.0` → `query_notes@1.0.0` →
`create_note@1.0.0`, run on **beta**, whose deployed lock joins the release's
six tools with the project's two. `notes-retry.yaml` is the rehearsal arm: its
first step is `update_task_status@1.0.0` with an `p_expected_status` that
cannot match — a deterministic `write_conflict`, retryable, parked long enough
to kill the process under it. **Alpha is the control the other way**: it
installs no definitions, so `POST /workflows/runs` naming any definition
returns *no such definition*.

The example project's own `set_note_embedding@1.0.0` is
`requires_approval: true` (`projects/example/capabilities.yaml:58`) and is
therefore **refused at `validate`** until Session 33 — which is the refusal
being load-bearing rather than decorative.

## Consequences

* A developer who edits a definition must redeploy, under a new version. That
  is the migration-set discipline, applied to definitions, and it is the
  reason a parked run cannot resume against a definition that changed under
  it.
* `apg workflow install` as a separate verb is **not** built. If Session 33
  needs one for approval-gated definitions, it is priced then.
* `--render-only` never reaches step 6d, so the gate's four renders are
  unaffected.

## Alternatives rejected

* **A file the loop reads at run time.** Rejected: a run parked on a 45-second
  backoff could resume against a definition that changed while it waited, and
  nothing would record that it had.
* **A definition submitted with the run.** Rejected: an unreviewed artefact
  executed by a second principal is the stage's failure mode wearing a
  different hat.
* **A step naming a TOOL rather than a capability.** Rejected: a tool is not
  versioned, and `query_resource` is backed by two capabilities, so a
  tool-named step could not say which reviewed thing it meant.
