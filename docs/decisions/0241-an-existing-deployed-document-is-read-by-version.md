# 0241 — An existing deployed document is read by version, never validated as if this release wrote it

- **Status:** Accepted
- **Date:** 2026-09-30
- **Session:** 34, Run 10a (D1848)
- **Affects:** `src/agentic_postgres/deployed_output.py`
  (`read_deployed_document`, `UnreadableVersion`, `READABLE_PREVIOUS_VERSION`),
  `src/agentic_postgres/capacity_probe.py` (deploy step 0's admission,
  `bin/admit.sh`, `doctor capacity`), `bin/fleet.py`,
  `src/agentic_postgres/dr_kit.py` (`export`, and `verify`'s current branch),
  `bin/project-retire.py`; `tests/contract/test_disaster_kit.py`.
- **Related:** ADR 0012 (a deployed document is an observation and is never
  migrated), ADR 0189 and D1122 (a kit's stored document is read by version),
  ADR 0195 (a reader reports what it could not determine), ADR 0221 (admission
  fails closed), D1141.

## Context

`outputs.schema.json` admits exactly one version, the current one. Four readers
validated a deployed document that ALREADY EXISTED on a host against it —
the writer's check, `validate_deployed_document`: deploy step 0's admission
(through `capacity_probe.read`), `fleet`, `dr-kit export` and `project-retire`.

Nothing exercised that until 1.12.0, the first release since admission shipped
(Session 31) to move the outputs version (18 → 19; the last move was Session
21). **Measured on the reference host on 2026-09-30, Sheet D1, before any
deploy:** `fleet` reported both projects' documents as *"does not validate
against the outputs schema"*, and `dr-kit export` refused them. Measured on the
workstation with beta's real version 18 document: `capacity_probe.read` counted
it unreadable and `decide` refused, so **alpha's release deploy would have
refused at step 0 on beta's document, and beta's on alpha's** — every order,
with no override. The same document with only the version 19 delta (`connectors:
{enabled: false}`) was read.

## Decision

1. **`deployed_output.read_deployed_document` is the one reader of a deployed
   document that already exists**, D1122's by-version rule for a kit made the
   rule for every reader. `validate_deployed_document` stays the check for the
   document a deploy is about to WRITE, and no module outside `deployed_output`
   calls it (a class guard, which also moves `dr-kit verify`'s current-version
   branch to the reader — the same check at that version).
2. **By version, three ways:** the current version validates against the full
   schema, unchanged; **the previous version** (the one the release before this
   one wrote) must be a `deployed` document with no sensitive key and no
   unfilled placeholder, and is returned **exactly as found**; any other
   version raises `UnreadableVersion`, which names the document's version and
   the two this release reads.
3. **Nothing is carried forward.** ADR 0012 stands: the reader adds no member
   and republishes nothing. Each consumer asks the document for what it needs
   and fails closed on a missing member as it already did —
   `capacity_reading.committed_from_documents` reports a document with no
   `database.budget.unreclaimable_mb` as unreadable, and `decide` refuses.
4. `capacity_probe` and `fleet` report an `UnreadableVersion` in its own words
   rather than as *does not validate* (ADR 0195): the first sends an operator to
   a newer checkout, the second to audit a document.

## Alternatives rejected

- **Lift the older document to the current version before validating.** It is
  a deployed-document migration: an observation republished under a version
  that never measured it. ADR 0012 and `test_a_deployed_document_is_not_migrated`
  refuse it, and the tree's `migrate_v18_to_v19` refuses the kind.
- **Edit the neighbour's document by hand before deploying.** A false record.
- **Accept every older version.** A document several versions behind may lack
  members its reader needs in shapes nobody has measured; the previous version
  is what an upgrade meets, and it is the one measured.
- **An admission override flag.** It would admit on a figure nobody read.

## Consequences

The first deploy of every future outputs bump reads its neighbours. A host with
a project TWO outputs versions behind still refuses a neighbour's deploy, and
says which version; that project is upgraded first. Proved by six tests in
`test_disaster_kit.py` and a nine-mutation battery, each mutation killed beside
a control it cannot reach.
