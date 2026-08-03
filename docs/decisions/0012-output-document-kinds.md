# 0012 — Two output document kinds under one versioned schema

- **Status:** Accepted
- **Date:** 2026-08-04
- **Session:** 2
- **Affects:** `CFG-004`, `CFG-005`, `DEP-EDGE-001`, `DEP-ISO-002`, `OPS-TLS-001`

Supersedes nothing. Extends plan decision **U** of the Session 1 implementation
plan, which reserved this exact question for the session that first needed it.

## Context

Session 1 froze two properties of `outputs.json` and tested both:

- it is **byte-identical** across renders with identical inputs (`CFG-004`);
- **no key** in it matches `/(_at|_time|timestamp)$/`.

Session 2 has to publish observed state — a certificate fingerprint, validity
timestamps, a provider project ID, a secret generation ID, whether the last
start used fresh secrets. Every one of those violates both properties.

Decision **U** anticipated this and set the precedent: *"If a later session
genuinely needs a deployment timestamp in rendered output, it goes in a field
the determinism test explicitly excludes, and it requires an ADR at that time."*

The literal reading — a growing allowlist of excluded field names inside one
document — is worse than the problem. Each new exclusion is a small, locally
reasonable edit, and after five of them nobody can say what the determinism test
still covers.

## Decision

**One versioned schema, two document kinds, discriminated by a required
`document_kind` const and separated by a `oneOf`.** `schema_version` is `2` on
both branches. `additionalProperties: false` is preserved at every level of
both.

| | `rendered` | `deployed` |
|---|---|---|
| Path | `.generated/{project_key}/outputs.json` | `/var/lib/agentic-postgres/projects/{project_key}/outputs.json` |
| Owner / mode | invoking user, `0600` | `root:root`, `0600` |
| Written by | `deploy.sh --render-only` | `deploy.sh --through-session N`, after convergence |
| Contains | planned names, routes, digests | observed host, TLS, provider IDs, generation |
| Timestamps | **none** | yes |
| Deterministic | **byte-identical** | no, and never asserted to be |

**The exclusion is by document kind, not by field name.** `rendered` stays
fully deterministic and fully timestamp-free, and Session 1's
`test_no_timestamp_reaches_rendered_output` is unchanged — it is scoped to
rendered documents, which is what it always examined. There is no field-name
allowlist to grow.

**Consumers declare which kind they accept.** `edge-network.sh`, the systemd
launchers and the external suite require `deployed`; the source contract tests
require `rendered`. The `oneOf` makes a rendered document fail validation as
deployed state rather than validating with absent fields, so "the wrong file was
passed" is a schema error rather than a `KeyError` three calls later.

**`inputs` gains a fifth digest, `secrets_contract_sha256`.** The rendered
document now carries `secrets.required_names`, derived from
`secrets.required.yaml`. The rule the block encodes is that it names *every*
file the render depends on; a value derived from an undigested file would let
two renders differ with nothing in the document explaining why.

**`output_migrations.py` migrates v1 → v2 `rendered` only, and never fabricates
a `deployed` document.** Nothing under `.generated/` is migrated in place: it is
gitignored, rewritten transactionally on every render, and the migration path
for a working tree is *re-render*. The migrator exists for archived or
third-party v1 documents and is tested against a committed v1 fixture.

**Absolute host paths live only on the deployed branch,** under `runtime`, with
anchored patterns. `project.generated_directory` keeps its
`^\.generated/[a-z0-9-]+$` pattern untouched on both branches.

Two deliberate departures from the runbook's Phase 3 fragments, recorded so they
are not mistaken for drift:

- the fragment replaces `secrets: {namespace}` with `secrets: {status,
  required_names}`. `namespace` is **kept** and the two new fields are added
  beside it — `secrets.namespace` is in `test_render_isolation.MUST_DIFFER` and
  in `evidence.ISOLATED_FIELDS`, so dropping it would silently remove a tested
  isolation field;
- the fragment puts `project_key` at the document root. Both branches keep
  `project.key` instead, so the two are structurally parallel and there is one
  place a project key lives.

## Consequences

Makes easy:

- Session 2 can publish everything it observes without touching Session 1's
  determinism contract, and `CFG-004` keeps meaning what it meant.
- Passing the wrong file to a tool is a validation failure with a message,
  which matters because the two files have the same basename.
- Later sessions add observed fields to `deployed` freely; that branch was
  never deterministic, so there is no invariant to erode.

Makes hard:

- Every consumer must state which kind it wants. Intended: it makes the
  distinction visible at each call site instead of implicit.
- The schema is roughly twice the size, and the `database` and endpoint
  definitions are shared through `$defs` to keep the duplication to the parts
  that genuinely differ.
- A v1 document no longer validates. Accepted: the only v1 documents are
  regenerated by any render, and the migrator covers anything archived.

Enforced by `tests/contract/test_output_schema.py` (rendered branch,
determinism, the five-digest set) and by the document-kind rejection tests that
land with `output_migrations.py`.

## Alternatives considered

**A field-name exclusion list inside one document.** Rejected: this is decision
**U**'s literal text and it is the option that decays. Five locally reasonable
edits later, nothing can state what the determinism test still covers.

**A separate `deployed-state.schema.json` with its own `schema_version`.**
Rejected, narrowly — it is a defensible design. Two version numbers that must
move together is a coupling with no mechanism enforcing it, and the two
documents genuinely share `project`, `database` and the endpoint definitions,
which would then need copying or an inter-schema `$ref`.

**Keep `outputs.json` v1 and add `deployment.json` for observed state.**
Rejected: `deployment.json` already exists for a different job — it is the
*authority* for provider ownership and convergence, mutable operational state.
The deployed document is a published *observation*, and merging the two would
make the file both the record and the report.

**Bump `schema_version` to 2 for rendered and 3 for deployed.** Rejected: they
are not successive versions of one thing. They are two kinds under one contract,
which is what `document_kind` says and what `oneOf` enforces.
