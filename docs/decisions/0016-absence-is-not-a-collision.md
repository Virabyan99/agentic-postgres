# 0016 — Two projects that both lack a facility do not collide

- **Status:** Accepted
- **Date:** 2026-08-04
- **Session:** 2
- **Affects:** CFG-012

## Context

`evidence.collision_count` compares two rendered projects field by field over
`ISOLATED_FIELDS` and counts every pair that matches. `project_scoped_collision_count`
must be `0` or `bin/write-session-evidence.py` exits `5` and the gate fails at
step 8.

Four of those fields — `storage.bucket`, `storage.prefix`, `backup.stanza`,
`backup.repository_prefix` — are `null` when the project disables storage or
backup. Session 2 deploys exactly such projects: object storage lands in Session
7 and backups in Session 10, so a Session 2 project manifest turns both off.

Two projects with storage disabled therefore render `null == null` four times
and score four collisions each pass, and the gate reports `status: "failed"` for
two projects that share nothing whatsoever. The comparison is asking "are these
values equal" when the question is "do these projects share a resource".

This is a Session 1 defect. It was invisible only because both Session 1
fixtures enable storage and backup, so no `null` ever reached the comparison.

## Decision

A pair where **both** values are `null` is not a collision and is not counted.
A pair where both values are equal and non-null still is, as before, and a pair
where one is `null` and the other is not was never equal and remains uncounted.

The reasoning is that `null` here means "this project has no bucket", and two
projects that both have no bucket are not sharing one. Identity collision is a
claim about a shared resource; absence is not a resource.

The role comparison below it is unchanged. Role names are never `null` —
`naming.derive` produces all thirteen unconditionally — so the same reasoning
does not apply and no exemption is granted there.

## Consequences

`collision_count` can no longer be satisfied by rendering two projects with
everything switched off. That is the failure mode this decision creates, and it
is why the change ships with a guard: `test_two_projects_sharing_a_bucket_still_collide`
asserts that two projects with the *same non-null* bucket still score a
collision. Without it, "ignore null pairs" and "ignore this field" would be
indistinguishable from the test suite's point of view.

The comparison remains over parsed semantic fields, never a duplicate-string
search, which is the property runbook §8 actually requires.

Enforced by:

- `tests/contract/test_evidence_collisions.py::test_two_storage_disabled_projects_do_not_collide`
- `tests/contract/test_evidence_collisions.py::test_two_projects_sharing_a_bucket_still_collide`
- `tests/contract/test_evidence_collisions.py::test_a_shared_role_name_is_still_a_collision`
- `tests/contract/test_render_isolation.py::test_collision_count_is_zero`

## Alternatives considered

**Drop the four nullable fields from `ISOLATED_FIELDS`.** Removes the check
entirely for Sessions 7 and 10, when those fields become the ones most worth
comparing. The problem is the comparison of absent values, not the fields.

**Require Session 2 projects to enable storage and backup.** Deploys two
provider integrations to make a counter behave, in a session whose scope is host
and ingress. The evidence would be honest and the system would be wrong.

**Treat it as a bug fix and skip the ADR.** The change reduces what counts as a
failure in a P0 requirement's evidence. That is exactly the category the ADR
rule exists for, regardless of how obviously correct the reduction looks.
