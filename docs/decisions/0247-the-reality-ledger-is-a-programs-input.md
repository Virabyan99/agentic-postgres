# 0247 — The Reality Ledger is a program's input

- **Status:** Accepted; amended by ADR 0254 (Session 37): a row's STATUS moves
  in the run whose evidence makes it true, its TEXT with the build; and the
  guard's operations half is written
- **Date:** 2026-10-03
- **Session:** 36, Run 1 (D1979, D2000)
- **Affects:** `LEDGER-001` (registered by Run 8). `docs/reality-ledger.yaml`,
  `schemas/reality-ledger.schema.json`, `src/agentic_postgres/reality_ledger.py`,
  `bin/render-reality-ledger.py`, the generated `docs/reality-ledger.md`,
  `tests/contract/test_reality_ledger.py`, `bin/session-01-check.sh` step 6 —
  all written by Session 36's Run 5.
- **Related:** ADR 0246 (the hosted boundary), ADR 0195 (a report may not
  substitute an answer for not knowing), ADR 0202 (an offline claim is
  declared), `capacity.ENVELOPE` (measured windows), `docs/scope-closure.md`,
  the Stage 5 specification's §6, §50–§52, §59 and Appendix A.

## Context

The class Stage 5 is most exposed to is *a surface that claims what the node
does not do* (the stage plan's §9). A hosted console will show a customer
buttons, statuses and numbers; each is a sentence about the product, and
the product is one node with one operator. The specification asks for a
*"Reality Ledger"* — every concept `available`, `beta` or `planned`, never one
that *"looks active but does nothing"* — and a list of words a release may not
use unless evidenced.

Nothing in the tree is that today. `docs/scope-closure.md` says what each
session closed; `product-contract.md` §2 says *"none of the elasticity"*;
`capacity.ENVELOPE` holds measured windows. All three are documents a person
reads. **No document is read by a program to decide what a surface may say**,
and a ledger only a person reads is one that drifts the first week nobody
reads it — the same reason the requirement table, the bounds and the envelope
are generated with a `--check` (ADR 0195's habit: a report that can be stale
says so, or is regenerated).

## Decision

**The Ledger is `docs/reality-ledger.yaml`, validated by
`schemas/reality-ledger.schema.json`, rendered to `docs/reality-ledger.md` by
`bin/render-reality-ledger.py --write|--check`, and guarded by
`tests/contract/test_reality_ledger.py` from its first commit.**

**Each row** (one per product concept) carries:

| Field | Meaning |
|---|---|
| `id` | a stable snake_case name |
| `concept` | the concept as a customer would name it |
| `status` | `available` \| `beta` \| `planned` \| `not_metered` \| `not_offered` |
| `customer_text` | the sentence a customer reads about it |
| `today` | what the appliance does now, for its operator |
| `today_evidence` | the claim (in `evidence_claims.CLAIMS`) or `capacity.ENVELOPE` subject that proves `today`, or `null` when nothing does |
| `evidence` | for an `available` or `beta` row: the claims or envelope subjects that prove the customer-facing status; empty for every other status |
| `stage5_reality` | what Stage 5 builds of it, or why it does not |
| `eventual` | what a fuller product would do — never promised |
| `controls` | the console controls and `/api/v1` operation types that act on it; `[]` until a session builds one |
| `since_session` | the session the row's current status was set in |
| `target_session` | the Stage 5 session that builds it, or `null` |

`not_offered` is a status the specification did not list and this ADR adds:
a concept cut by decision (the SQL editor, in-place restore for a customer,
branch promotion, support grants, autoscaling, high availability, multi-region,
an SLA, billing) is not `planned` — nothing will build it — and saying
`planned` would be a promise.

**The guard, in the halves that have a subject today** (D2000):

1. the file validates against the schema;
2. every `available` or `beta` row's `evidence` is non-empty and every entry
   resolves — a claim `passed` in the newest `evidence/session-*.json`, or a
   `capacity.ENVELOPE` subject; every `today_evidence` that is not `null`
   resolves the same way. **The evidence documents are gitignored** (runbook
   §6.1), so this is read in two halves (D2021, corrected in place in Run 5):
   *every checkout*, CI's included, checks that each name is a claim in
   `evidence_claims.CLAIMS` or an envelope subject; *a checkout holding an
   evidence document* — the workstation and the host, where the session gates
   run — also checks that each claim passed in the newest one, and a checkout
   without one skips that half and says so;
3. every `planned`, `not_metered` and `not_offered` row has `controls: []` —
   the fake-complete guard: nothing a customer can press acts on a thing that
   is not there;
4. no row's `customer_text` uses a word of the specification's §59 list
   (`production-ready`, `enterprise-grade`, `highly available`,
   `fault tolerant`, `multi-region`, `serverless`, `autoscaling`,
   `zero downtime`), case-insensitively;
5. `docs/reality-ledger.md` is the renderer's current output.

**The halves without a subject land later, and the test says so.** *"Every
console control and every `/api/v1` operation type maps to a row"* has no
console and no operation type to read until Sessions 37 and 42. The test
asserts the two sets it will read are **empty today** — no
`src/agentic_postgres/operations.py`, no `services/console/` — so the day
either appears, the assertion fails loudly and names the session that must
write the real guard. A guard over a set that does not exist passes
vacuously; one that names its empty set cannot.

**A row moves in the run that builds the thing**, not at a session's close:
the run that makes a concept reachable sets its status, its `evidence` and its
`controls` in the same commit, and the guard reads them at that commit.

**Session 36 writes today's truth**: every customer-facing concept `planned`
(no customer exists), the cut ones `not_offered`, egress `not_metered`; the
substrate a customer would rely on (PostgreSQL 18.4, isolation, backups,
agents, workflows, connectors, the audit) `planned` for a customer with a
`today_evidence` claim that passed at Session 35.

## Alternatives rejected

**A Markdown page only.** Rejected: the page is what a person reads, and the
point is that a program reads the source. The page is generated from the YAML
with `--check`, the shape every other derived document here takes.

**Guard the forbidden words over every `docs/` page.** Rejected for now:
`product-contract.md` §5 and the stage plans use *autoscaling*, *multi-region*
and *failover* as negations (*"Autoscaling … stays out"*). A word guard that
cannot read a negation would force the non-goals to be reworded around the
guard. The guard reads `customer_text` — the only text written *for* a
customer today — and Session 42 extends it to the console's served strings and
the API's, which are the next texts written for one.

**Use the stage plan's four statuses.** Rejected: a cut concept marked
`planned` is a promise (above).

## Consequences

**Makes easy:** a console (Session 42) renders a concept's status from one
reader; a reviewer asks of any new button *which row, and is its status
`available`?*; the release language is checked, not remembered.

**Makes hard:** every run that builds a customer-facing thing edits the Ledger
in the same commit, and an `available` row cannot be written until a claim
that proves it has passed on a sweep — so a feature is `beta` or `planned`
until the evidence exists, even when the code is done. That is the intent.

**Enforced by:** `tests/contract/test_reality_ledger.py` (Run 5) and
`bin/render-reality-ledger.py --check` in `bin/session-01-check.sh` step 6.
