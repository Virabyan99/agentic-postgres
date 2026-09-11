# 0201 — A project owns a capability manifest and a compiled contract beside its surface, and the lock is the release's joined with the project's

- **Status:** accepted
- **Date:** 2026-09-11
- **Session:** 21, Run 1 (D1127, D1128, D1136, D1137, D1139)
- **Extends:** **ADR 0198** (a project owns a migration set, a reviewed surface
  and a snapshot under `projects/<slug>/`).
- **Amends:** **ADR 0183** §*what a profile cannot do* — where removing a tool
  lives, now that the runtime no longer refuses fewer than six (ADR 0200).
- **Related:** ADR 0050 (nothing exists in `api` the reviewed contract does
  not name), ADR 0118 (agent-only RPCs), ADR 0119/0120 (derived operation ids;
  a tool is one or more capabilities), ADR 0127 (the lock is the answer), ADR
  0155 (a deploy recreates a container whose mounted content changed), ADR
  0177 (a field arrives at its version), ADR 0184 (cases derived per frozen
  field), ADR 0200, D930, D933, D1029, D1111.

## Context

ADR 0200 lets a lock carry a tool for a tenant's relation. This ADR says where
a tenant declares one, what it may declare, and how the deployed lock is built
from two reviewed manifests.

### What the tree does, measured at `5a43f12`

**The manifest ADR 0183 points at is per host, and the deployed lock is not
compiled from it** (D1127). `bin/deploy-project.py:2151` runs `mcp-contract.sh
lock --outputs … --project …` with no `--capabilities`, so the lock is compiled
from the release's `capabilities.example.yaml`; the host's `capabilities.yaml`
reaches the render's `capabilities.enabled` list and `capabilities_sha256` and
nothing else (D930's two-digest item). Both host files are schema 1 — and
compiling a lock from a schema-1 manifest would produce a schema-1 contract
with no budgets (ADR 0177), which is why the deploy never did. So `enabled:
false` on a host has never reached a lock, and the *project* in D933 was a
host.

**The compiler resolves against the release surface alone** (D1128).
`bin/mcp-contract.py:79` loads `api_surface.load_surface()` and the release
snapshot; `surface_operations` reads `relations`, `rpcs` and `agent_rpcs`.
Session 20's `merged_surface` and `load_project_snapshot` exist and nothing in
the MCP path calls them. A project surface at api-surface schema 2 carries no
`agent_rpcs`, `agent_write_rpcs` or `forbidden_schemas` (`PLATFORM_ONLY_SECTIONS`).

**The deployed document's `mcp` block** carries `capability_contract_sha256`
and `capability_lock_sha256`; the isolation matrix names the lock digest and
the `mcp.` prefix; a project's contract is not in the document at all (D1136).

## Decision

### 1. Where a project's capabilities live

```
projects/<slug>/capabilities.yaml                          # capability schema 4
projects/<slug>/contracts/mcp-capabilities.canonical.json  # compiled, committed
projects/<slug>/contracts/evaluation-report.md             # rendered, committed
```

named by a new optional `mcp.capabilities: projects/<slug>` key in the project
manifest at **project schema 6**, forbidden below 6, the same `^projects/[a-z]
[a-z0-9-]{2,30}$` shape as `migrations.set` and usually the same directory.
The file is **tracked in the checkout**, for ADR 0198's reason: a release is
exactly its commit, and a tool an agent can call is code, not configuration. A
host-level `capabilities.yaml` keeps the role it has (D930 stays open and is
named as such).

### 2. What a project may declare, and what it may not

A project manifest declares **its own** capabilities — reads over its
relations, writes over its RPCs — compiled against the **merged** surface
(release + project) and the **project's** snapshot. It may also name release
capabilities to leave out of *this project's* lock:

```yaml
release:
  disabled: [create_note]
```

A name the release does not declare is refused; a metadata capability may not
be named (the runtime requires the pair, ADR 0200). This is where D933's first
thing closes, **per project, in the narrowing direction, at compile time**.

A project may **not** declare:

- a `kind: metadata` capability — the pair is the runtime's own;
- an operation in `agent_rpcs` — agent-only unpublished functions describe the
  whole database and stay platform-only, so a tenant tool always addresses a
  published object (ADR 0050 from the other direction; D1128);
- a read over an RPC with arguments — no shape (ADR 0200, D1129);
- a tool or capability name the release declares — refused at merge, exactly
  as `merged_surface` refuses a redeclared relation.

### 3. The lock

*Amended in Run 4 (D1147): the join is of the two MANIFESTS, not of two
compiled contracts.* As planned, `compile_lock` was to join two canonicals —
tools concatenated, the release's disabled ones removed. A disabled
capability behind a **grouped** tool (`query_notes` under `query_resource`)
cannot be removed from a compiled tool without recompiling it, so the join
happens one level up: `capability_manifest.joined_capabilities` takes the
release's manifest less the disabled entries plus the project's, and ONE
`compile_canonical` runs over that against the merged surface and the
project's snapshot, with contract id `<release>+<project>` (Session 20's shape
for the merged surface). `tools_sha256`, the profile (ADR 0183, unchanged) and
the vocabulary from the merged surface (ADR 0200) follow as `compile_lock`
always did. The project's OWN contract is still compiled alone, against the
same surface and snapshot, and that is the file the project commits.

A lock is compiled from approved parts only: `lock` first proves the
release's committed contract and the project's are each what their manifests
compile to, and refuses (exit 5) when either is not. `mcp-contract.sh check
--project FILE` compiles the project's contract and compares it byte for byte
with the committed one, then applies the profile to the JOINT contract;
`compile --project` streams the project's; `lock` reads `mcp.capabilities`
from the manifest it is already given, so the deploy's call at
`deploy-project.py:2151` does not change shape.

A project's capabilities presuppose its reviewed surface: the contract id
derives from the surface's, the merged surface is what the scopes are
approved against, and the project's snapshot is what the operations are
checked against — so `mcp.capabilities` without `migrations.set` is refused at
load, and a set without its surface or snapshot is refused with the command
that writes each.

`canonical_sha256` in the lock digests the canonical the lock was compiled
from — the joint one for a project that declares capabilities — and the
deployed document's `capability_contract_sha256` keeps its name and records
that. **Outputs v18** adds `capabilities.project` on the rendered branch and
`mcp.project_capabilities` on the deployed one, each `null | {root,
contract_sha256, tool_count, capability_count}`, where `contract_sha256`
digests the project's COMMITTED contract (the bytes `check --project`
compares); the deployed member is null beside `status: unavailable` like every
other member of the block. The migrator adds `null` and touches nothing else;
the isolation matrix's `mcp.` prefix and the doctor's `mcp` sensitive block
already cover the new leaf (checked, not assumed — D1111), with a project
without capabilities rendering the explicit null as the control.

### 4. A profile still cannot remove a tool

ADR 0183's sentence was true for the wrong reason — *"the runtime refuses a
lock with fewer than six"* — and stays true for the right one: a profile
narrows *values* on tools that exist, in a vocabulary of seven bounds the
runtime reads, and the roster is a *set*, decided one level up in the project's
capability manifest where the compiler compiles a tool out entirely. Keeping
the two levels apart is what keeps `apply_profile`'s seven-field vocabulary the
whole of what a profile can say (D1139).

### 5. The scaffold

`bin/agent.sh init --project FILE --operation NAME [--kind read|write]` streams
**one capability entry** to stdout, derived from the merged surface's
operations table — the same table the compiler resolves against, which is
why a scaffold cannot express what the compiler cannot emit — and writes no
file (D1137):

- a relation → a read with `tool: query_resource`, the view's column list, no
  filters, no ordering, `max_rows` 100, `risk: low`;
- an RPC → a write with the reviewed argument list in PostgreSQL order,
  `supports_dry_run: true`, `requires_approval: true`, `idempotent: false`,
  every argument redacted, `risk: moderate`;
- scopes derived (`<relation>:read`, or the write scope of the relation the
  reviewer names — a write's scope is a review decision the scaffold states
  as a placeholder to edit, never guesses);
- `version 1.0.0`, `lifecycle active`, budgets at the conservative end of every
  bound a profile could narrow (ADR 0183's polarity, D925).

`validate` is `mcp-contract.sh check --project`, `test` is
`render-evaluation-report.py --project --check`, `dry-run` is the runtime's
(ADR 0182); the usage names them rather than wrapping them (D707).

The example project's own `capabilities.yaml` is what the scaffold emits for
`note_embeddings` and `set_note_embedding`, byte for byte, and a test keeps it
so.

## Alternatives

**The host's `capabilities.yaml` as the per-project lever.** It is per host,
schema 1 on both production projects, and compiling a lock from it would
downgrade the lock's shape (D1127). Rejected.

**Tool removal in the profile** (`mcp.profile.<tool>.enabled: false`). The
profile's vocabulary is seven bounds on tools that exist; making it also decide
the set is what ADR 0183 was written to prevent, and it would need project
schema 6 anyway. Rejected (D1139).

**A project's capabilities beside its manifest on the host.** ADR 0198
rejected the same for SQL: a release is its commit, and a tool an agent can
call is at least as much code as a view. Rejected.

**One canonical contract per deployment, compiled from a merged manifest.** It
would make the release's committed contract vary per project and
`mcp-contract.sh check` a comparison against a document that depends on which
project is asked about. Rejected; two canonicals, one join.

**Admitting `agent_rpcs` in a project surface.** An unpublished function
reachable by an agent and named by no served document; ADR 0050's case.
Rejected.

## Consequences

- Project schema 6 (`mcp.capabilities`); capability schema 4's project form
  (`release.disabled`, no metadata kind); `load_project_capabilities`,
  `merged_capabilities`, `project_capabilities_path`, `project_contract_path`.
- `bin/mcp-contract.py`: `check`, `compile` and `lock` read `--project`'s
  `mcp.capabilities`; `bin/agent.sh` / `bin/agent.py` with `init`.
- Outputs v18 with the migrator, the matrix classification and the doctor's
  map; `carry_to_current` in the tests first (D1134), so the bump is one edit.
- `bin/render-evaluation-report.py --project FILE`; the harness derives cases
  for the merged contract; a project's written cases, if any, at
  `projects/<slug>/evaluation-cases.yaml`.
- `projects/example/capabilities.yaml` and its contract, committed in Run 5;
  `project.example.yaml` at schema 6 naming it; `project.second.example.yaml`
  at 6 without.
- README §*Giving an agent your tables*; `docs/mcp-tool-catalog.md`'s
  per-project sentence; `docs/capability-plan.md` marked historical.
- D930 stays open: two fields named `capabilities_sha256` still digest two
  files, and the host's manifest still reaches only the render.
