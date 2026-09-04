# 0183 — A profile narrows the compiled contract and never widens it

- **Status:** accepted
- **Date:** 2026-09-04
- **Session:** 16, Run 8 (`AGT-PROFILE-001`, D867, D894, D929–D933)
- **Related:** **ADR 0179** (a capability narrows a budget and may never widen
  one — the same monotonicity, one level up), **ADR 0177** (a field arrives at
  the version that introduces it), ADR 0120 (a tool is one or more
  capabilities), ADR 0127 (the lock is the answer, read once at startup),
  ADR 0002 (one authority per value), D867, D894, D927 (a declared field with
  no reader is the trap this run walked into twice before it started).

## Context

Session 16's plan fixes the invariant before the run rather than leaving it to
the run (D867): **a profile may only narrow**, and the refusal is at compile
time. The row names the failure mode in advance — *"this is the feature most
likely to be built as a general override mechanism, because that is what
'profile' means everywhere else."* Here a profile is a monotone restriction of
the compiled contract, or the deployed lock stops being the answer to *what can
this agent do*, and every allowlist proof in Sessions 8 and 9 is written against
the lock.

### What project-local narrowing existed before this run

The plan says the only project-local narrowing is `enabled`, per capability.
**Measured, that is not quite right, and the difference is the interesting
part.** `enabled` lives in `capabilities.yaml`, which is one file per HOST: two
projects on one host compile the same canonical contract from it, so `enabled`
is host-local, not project-local. The project manifest, which IS per project,
carries two fields that read as exactly this feature:

```
mcp:
  max_result_rows: 100        # "Agent read row ceiling"
  max_response_bytes: 262144  # "Agent response size ceiling"
```

**Both are read by nothing** (D929). A grep over `bin/`, `src/` and
`services/` finds one consumer: the semantic check that `max_result_rows` does
not exceed `api.max_rows`. Neither reaches Compose, the rendered environment,
the lock or the runtime. They have been declared since Session 1 and have never
bounded anything — and `max_response_bytes` is permitted up to 10 MiB, ten
times `MAX_SERIALIZED_BYTES`, so a value that read as a ceiling could not have
been one even if something had read it. D816's rule (a declared field with no
reader is an unverified field) and D927's (off looks finished) in one block.

### What the runtime actually bounds from the lock

Seven things, read from the lock and nowhere else. This is the vocabulary a
profile has to be written in, because a profile that named anything else would
be narrowing a value the runtime does not consult:

| field | on | read at |
|---|---|---|
| `timeout_ms` | every tool | `mcp_tools` 348, 463, 597, 929 |
| `max_response_bytes` | read, write | `mcp_tools` 369, 488, 633 |
| `max_concurrent_calls` | read, write | `mcp_tools` 693 |
| `max_rows` | each resource of a read | `mcp_query` 300–304 |
| `max_affected_rows` | write | `mcp_tools` 606 |
| `supports_dry_run` | write | `mcp_tools` 585 |
| `requires_approval` | write | `mcp_tools` 573 |

## Decision

**A project manifest at `schema_version` 2 carries `mcp.profile`: a map from
tool name to the bounds that project narrows, in the seven fields above and no
others. The compiler applies it to the approved canonical contract when the
lock is compiled, refuses any entry that would widen, and the lock records the
profile it was compiled under so the runtime can verify the two agree.**

```
mcp:
  profile:
    query_resource:
      max_rows: 100              # ≤ every resource's compiled max_rows
      max_response_bytes: 262144 # ≤ the tool's compiled bound
    create_note:
      supports_dry_run: false    # a permission may be withdrawn, never granted
```

### The order, per field

"Narrower" has to be defined per field, and it is defined once, in
`capability_compiler.PROFILE_FIELDS`, beside the kinds each field applies to:

- a number narrows when it is **less than or equal to** the compiled value;
- `supports_dry_run` is a PERMISSION, so `false` is the narrow end — a profile
  may turn it off and may not turn it on;
- `requires_approval` is a RESTRICTION, so `true` is the narrow end — a profile
  may turn it on and may not turn it off.

That is the same polarity split ADR 0182 found in the compiler's own folds
(D925), and it is written here so that a reader of the profile does not have to
re-derive which boolean direction is the safe one.

**Equal is accepted.** A profile that restates the compiled bound narrows
nothing and widens nothing. Refusing it would make a profile break the day the
reviewed manifest tightens to meet it, which turns a safe change into a deploy
failure for no boundary gained.

### What is refused, and where

All of it in `apply_profile`, which is pure over its arguments and raises
`CompilerError` — a `CapabilityContractError`, so the CLI maps it to exit 5
rather than exit 2. Nothing here is a runtime denial:

- **a value that widens** — the message names the tool, the field, the profile's
  value and the compiled one;
- **a tool the contract does not compile** — a narrowing of nothing is D274's
  shape, a claim that lives only in a document;
- **a field the tool's kind does not carry** — `max_rows` on a write,
  `supports_dry_run` on a read, `max_response_bytes` on a metadata tool. A
  bound on nothing is what ADR 0179 forbids metadata capabilities, for the same
  reason;
- **a field the contract's version does not declare** — a v1 contract has no
  `max_response_bytes`, and a profile naming it would be *introducing* a bound
  rather than narrowing one. ADR 0177 says a field arrives at the version that
  introduces it; a profile cannot smuggle one in early;
- **`max_rows` above ANY resource of the tool** — `query_resource` has two, and
  they may disagree. A per-tool value is compared against each, because a clamp
  against the smaller would silently accept a value that widened it.

**No clamping anywhere.** The runtime already takes `min(lock, global)` for a
lock it did not compile (ADR 0179), and that leniency is right there because a
lock is an input. A profile is an operator's declaration, and a declaration that
is silently corrected is one the operator does not know was wrong.

### Where "compile time" is

Two places, and the deploy cannot skip the second:

- `bin/mcp-contract.sh check --project FILE` applies the project's profile to
  the approved contract in a checkout, with no host and no root, and exits 5 on
  a widening. This is the sentence the plan wrote.
- `bin/mcp-contract.sh lock --outputs FILE --project FILE` compiles the deployed
  lock, and **`--project` is required**, not optional. An optional flag the
  deploy forgot to pass would compile a lock ignoring the profile and report
  success — D927's shape, one step later. The deploy passes it.

### What the lock records, and what the runtime does with it

The lock gains a top-level `profile` — the profile as declared, absent when the
project manifest is at version 1 rather than present and empty (D600) — and
`compiled_from` gains `project_manifest_sha256`. `canonical_sha256` **stays the
digest of the approved contract the profile was applied to**: `mcp_tools`
records it as `contract_hash` on every audit row and the deployed document
publishes it as `capability_contract_sha256`, and both name the reviewed
contract, which is what a reader wants to match against the committed file.
The profile block is the whole difference between that contract and the tools
the lock carries.

`mcp_lock.load_lock` reads the block and **refuses a lock whose tools disagree
with its own profile** — every profiled field must equal the tool's value,
because the compiler set them equal. A field with no reader is unverified
(D816), and this is the reader: a lock that says it was narrowed and was not
came from something other than this repository's compiler.

### What a profile cannot do

Stated so the next reader does not build it as an exception:

- **Remove a tool.** The runtime refuses a lock with fewer than six (ADR 0127),
  and that is the enumerated-not-discovered property. A project that must not
  expose a write disables it in the capability manifest, where the compiler
  compiles it out entirely — and today that lock would not start either, which
  is recorded as D933 rather than repaired here.
- **Narrow `columns`, `filters` or `order_by`.** The reviewed manifest's own
  comment explains why its column list is the reviewed view's list and not a
  narrower one: *a second list maintained here would be a second authority
  over one surface.* A third list in the project manifest is the same
  objection. If a project needs a narrower projection it is a narrower
  capability in the reviewed manifest, reviewed once.
- **Touch a per-capability declaration.** The lock's `capabilities[]` entries
  record what the reviewed manifest declared for each capability; the tool-level
  fields are what the runtime obeys. A profile moves the second and leaves the
  first as the record of what was declared.

## Alternatives rejected

**A general override with a ceiling.** The alternative D867 predicts. It reads
as flexibility and is a second authority over what a deployment permits; the
frozen column allowlist and every Session 8 and 9 proof are written against the
lock being the one answer.

**Clamp rather than refuse — `min(profile, compiled)`.** It is what the runtime
does with a foreign lock and it is wrong for an operator's declaration: a value
that was silently narrowed is a value the operator believes applies and does
not. The two inert fields this run replaces are what a bound nobody reads looks
like after fifteen sessions.

**Keep `mcp.max_result_rows` and `mcp.max_response_bytes` beside the profile.**
Three project-local bounds in one block, two of them read by nothing, is worse
than the state before this run: a reader would assume all three apply. At
version 2 they are forbidden and the profile is the only project-local bound; at
version 1 they stay as they were, because `project.alpha.yaml` lives only on
the host. Their VALUES migrate into the example profiles, where they get a
reader for the first time.

**Give the two fields a project-wide reader instead.** A project-wide ceiling
can only be a clamp — 100 rows against `run_report`'s compiled bound of 1 is a
widening as a comparison and a no-op as a `min` — which is the semantics
rejected above, and mixing a clamped project-wide bound with a refused per-tool
one in a single run is how "profile" drifts into "override".

**Put the profile in `capabilities.yaml`.** It is per host, so two projects on
one host would share it, and "project-local" would mean nothing. D894 already
placed it in the project manifest for this reason.

**A separate profile file.** A fourth gitignored operator input for a block
that belongs beside `mcp.public_base_path`. The project manifest already carries
the `mcp` block and its own schema version.

## Consequences

- `project.schema.json` accepts `{1, 2}`, and `SUPPORTED_PROJECT_SCHEMA_VERSIONS`
  with it. **A version 1 manifest still loads and compiles the lock it always
  did** — byte-identical, no `profile` key — because both host manifests are
  version 1 and no commit can edit them (D894's budget, ADR 0177's rule).
- Both example project manifests move to version 2 and narrow something real,
  and differently from each other, because an aggregate reached only with
  inputs that agree tells nothing (D884, D927).
- `config.bounds_table` walks `patternProperties`, so the profile entry's bounds
  reach the generated table in `docs/product-contract.md`. A walk that stopped
  at `properties` would have generated a table missing seven fields that still
  looked complete — the failure ADR 0007 names, arriving through the generator
  for the second time (D932).
- The lock's `compiled_from` has four digests for every project from now on.
  `test_the_lock_carries_the_digests_of_everything_it_was_compiled_from` asserts
  the compiler's own three; the fourth is the CLI's and is asserted there.
- **Nothing on the host changes until an operator moves `project.alpha.yaml`
  to version 2.** Whether a `--migrate-manifest` helper ships is the open
  decision Run 4 recorded, and this run adds a second manifest to it.
