# 0177 — A capability declares a version, a lifecycle and a risk, and each has a reader

- **Status:** accepted
- **Date:** 2026-09-03
- **Session:** 16, Run 2 (`AGT-CAPVER-001`, `AGT-RISK-001`, D866, D879–D882)
- **Related:** **D816** (a declared field with no reader is an unverified field —
  nineteen rotation flags, three read), **D866** (the "one schema bump" is seven
  fields whose required-ness differs by kind), ADR 0120 (a tool may be backed by
  more than one capability; `metadata` reaches nothing and is *forbidden* the
  fields describing a backing), ADR 0129 (four budgets, independent by
  decision), ADR 0002 (one identity, one derivation), **D267** (a value that
  looks measured and was not), ADR 0119 (the operation id is derived).

## Context

`capabilities.schema.json` v1 carries sixteen properties and enforces
required-ness **per kind**, in three `if/then` branches: a `read` additionally
requires `resource`, `columns`, `max_rows`; a `write` requires
`max_affected_rows`, `idempotent`; and a `metadata` capability is *forbidden*
six of them by a `not/anyOf`. The object is `additionalProperties: false`, so a
new field is refused everywhere until the schema names it.

Session 16 adds three: a per-capability semantic version, a lifecycle state, and
a risk classification. §2 of the session plan fixes what each must do, and two of
those readers do not exist yet:

- `AGT-CAPVER-001` — *"the version reaches the audit row"*
- `AGT-RISK-001` — *"a high-risk capability's denial and its audit record differ
  observably from a low-risk one's"*

`app_private.agent_audit` gains `capability_version`, `contract_hash` and
`denial_reason` in **migration 0027, which is Run 3**. So D816's rule — a field
arrives with its reader in the same run — collides with the plan's own run order,
and the collision is real rather than a wording problem.

**The tempting escape is worse than the problem.** Risk could select a behaviour
today by narrowing `max_affected_rows` or `timeout_ms` for a high-risk
capability. That would make risk a **second authority** over two of ADR 0129's
four budgets, which are independent *by decision*, and it is exactly the shape
that ADR's own warning names.

## Decision

**Three fields, three readers, and one of the three readers is deliberately not
a behaviour yet.**

### `version` — a semantic version, read by the lock and the catalog

`"pattern": "^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)$"`. Required at
schema version 2, for every kind. The compiler carries it into the canonical
contract and the deployed lock, and `docs/mcp-tool-catalog.md` publishes it.

It reaches the audit row in Run 3, and `AGT-CAPVER-001` is proved there.

### `lifecycle` — `active | deprecated | retired`, read by the compiler

**A `retired` capability may not be `enabled: true`, and the compiler refuses
it.** This is not a new decision: `compile_canonical` already drops disabled
capabilities entirely, with the reason written beside it — *"a runtime that
received them would have to be trusted to ignore them, and the lock is meant to
be the thing that cannot be argued with."* Retirement is that rule reached by a
declaration instead of by a boolean, so the enforcement is the lock's **absence**
rather than a runtime check that could be forgotten.

`deprecated` compiles in and stays callable. The state travels into the lock and
the catalog, so an operator reading either can see what is on its way out. A
lifecycle that refused a deprecated call would make the word mean *retired*, and
then one of the two states would be unreachable.

### `risk` — `low | moderate | high`, read as a consistency rule

Validated, not behavioural, and this is the part to be honest about:

- a `metadata` capability must be `low` — it reaches no backend, holds no
  credential and answers from the lock, so any other value would describe a
  hazard that does not exist;
- a `write` may not be `low` — it changes rows.

That is a reader: it refuses manifests. It is **not** the behaviour
`AGT-RISK-001` requires, and that requirement is proved in Run 3 when the denial
taxonomy and the audit columns exist. Recorded rather than glossed, because a
plan that reports a requirement closed on a validation rule would be claiming a
behaviour nobody built.

### Compatibility: v1 still loads, and v2 is where the fields live

`schema_version` accepts `1` and `2`. At **v1 the three fields are forbidden**;
at **v2 all three are required**. Both halves matter: forbidding them at v1 keeps
a v1 manifest from carrying fields nothing reads at that version, and requiring
them at v2 keeps v2 from being a version in which they are optional and therefore
absent.

`capabilities.yaml` is a gitignored operator input that exists **only on the
host**. A schema that refused v1 outright would make the next deploy fail on a
file no commit can fix, in a session that has not been to the host yet. Accepting
both makes the manifest's move a deliberate edit at a moment the operator picks.
`capabilities.example.yaml` moves to v2 in this run, so the tree exercises the
new branch rather than describing it.

### `SUPPORTED_SCHEMA_VERSIONS` is split in two

One frozenset governed **both** the project manifest and the capability
manifest. Adding `2` for capabilities would have made
`validate_project_semantics` accept a project manifest declaring v2 — which
`project.schema.json`'s `enum: [1]` then refuses, so the two authorities would
disagree about the same document. ADR 0002. There are now two constants, each
named for the document it governs, and each is checked against its own schema's
enum by a contract test.

## Alternatives rejected

**Pull migration 0027 into Run 2 so all three fields get real readers now.**
Coherent, and it was offered. It roughly doubles the run and carries an
irreversible artifact — a released migration is fix-forward — into the run whose
job is deciding what the columns should hold. The denial taxonomy that
`denial_reason` records does not exist until Run 3, so the column set would be
designed before its vocabulary.

**Drop `risk` from Run 2 and add it in Run 3.** The strictest reading of D816,
and it costs a second schema bump or a delayed one. `schema_version` 1 → 2 was
meant to land once, and a manifest format that moves twice in one session is a
worse thing to hand an operator than a field whose behaviour arrives a run later.

**Let risk narrow a budget.** Rejected above: a second authority over ADR 0129's
independent budgets.

**Make `lifecycle` optional, defaulting to `active`.** A default is a value
nobody chose, and this schema has no defaults on a capability for that reason.
An operator who has not thought about a capability's lifecycle should be made to.

## Consequences

- A v1 manifest still loads, so the host is not broken by a commit. The host's
  `capabilities.yaml` moves to v2 when its operator moves it, and until then it
  declares none of the three fields — which is why they are forbidden at v1
  rather than merely unrequired.
- `AGT-CAPVER-001` and `AGT-RISK-001` are **not** closed by this run. Run 3
  closes them, and the session plan says so in §5 rather than in a footnote.
- The compiled contract's own `schema_version` moves to 2 with the tool shape,
  and the committed canonical snapshot is regenerated. That digest reaches the
  deployed document, so the next deploy carries a new capability contract hash.
- Two schema-version constants exist where there was one. A third manifest kind
  gaining a version will now find the pattern rather than the shared frozenset.
