# 0100 — The scope vocabulary has three classes, and they partition the union

Status: accepted
Date: 2026-08-15
Session: 7, Run 1
Settles: D310
Extends: [0079](0079-the-scope-vocabulary-has-two-closed-classes.md), [0006](0006-capability-scopes.md)
Affects: STO-OWN-001, AGT-SCOPE-001

## Context

Session 7 needs a scope for object storage. The runbook's §4.8 presents it as a
registry edit — "add exact scopes `storage:read` / `storage:write`" — and D310
recorded why it is not: ADR 0079 closed the vocabulary in **two classes**, each
closed by its own thing, and neither one has room for an object.

- The **data** class is one per (frozen-domain resource, verb) plus `meta:read`,
  closed by ADR 0003 and growing only when ADR 0003 is superseded.
- The **administrative** class is one per (platform identity resource, verb) over
  the auth service's own surface, closed by that surface.

An object is not a resource of the frozen example domain — ADR 0003 lists `notes`
and `tasks`, and mentions object storage only as an *optional attachment* to be
added once Session 7 exists. It is not part of the auth service's identity
surface either. So the vocabulary as it stands has nowhere to put it, which is
what makes this an ADR rather than an edit.

**What the two-class shape does to a third name was measured, not reasoned.** The
rig added `objects:read` and `objects:write` to the schema and ran
`tests/contract/test_scope_registry.py`, with the unmutated tree as the control
and a post-restore control to prove the snapshot list was complete. Both controls
exited 0.

| arm | result |
|---|---|
| **control** — unmutated | **exit 0** |
| **A** — the two names in `$defs/scope` only, held by nobody | `test_the_administrative_class_is_derived_not_listed` **fails** |
| **B** — arm A, plus `authenticated` holding them | A's failure, plus `test_an_administrative_scope_is_reachable_only_by_the_admin_role` **fails** |
| **post-restore control** | **exit 0** |

The mechanism is one line of `scope_registry`:

    def administrative_scopes() -> frozenset[str]:
        return approved_scopes() - agent_requestable_scopes()

**The complement is correct for exactly two classes and silently wrong for
three.** ADR 0079 derived the administrative class rather than listing it so that
the four names would be written once — a good reason, and it carries an unstated
premise: that everything in the union which is not requestable by an agent is
administrative. A third class makes that premise false, and the failure it
produces is not "storage is unclassified". It is **"storage is administrative"**,
asserted by derivation, with `authenticated` then appearing to hold an
administrative scope.

Arm B is what that looks like from the test suite, and it is worth being precise
about what saved it: `test_an_administrative_scope_is_reachable_only_by_the_admin_role`
went red because it enumerates holders, and `test_the_administrative_class_is_derived_not_listed`
went red because it compares against four literal names. Both would have been
*updated* by anyone implementing the runbook's instruction literally, because
both look like tests that need updating when a scope is added. **The
misclassification would have survived its own guard.**

## Decision

**Three classes, each named positively, and the union is asserted to be their
disjoint sum.**

- **`$defs/scope`** remains every approved name: the union, and the sole
  authority (ADR 0006).
- **`$defs/agent_scope`** remains the data class, and `required_scopes` binds to
  it. **It is not widened.**
- **`$defs/storage_scope`** is the new class: `objects:read`, `objects:write`.
- **`$defs/administrative_scope`** lists the four administrative names. **It is
  no longer derived**, and that is the part of ADR 0079 this ADR corrects.

`scope_registry` gains `storage_scopes()`, reads `administrative_scopes()` from
the schema instead of subtracting, and gains one thing ADR 0079 did not have:

**`assert_classes_partition_the_vocabulary()` — the three classes are pairwise
disjoint and their union is exactly `$defs/scope`.** This is the substance of
the ADR rather than bookkeeping, and it is why the complement had to go.

ADR 0079 derived the administrative class so its four names would be written
once, which was a good reason and is now paid for differently. **The relation
being checked is stronger than the one being given up.** "No name is written
twice" catches a typo; it cannot catch an *unclassified* name, because a
complement has no notion of one — every name it does not recognise is silently
a member. Checking the classes against the union exactly catches both, and it
catches them at the moment the registry is read, before any deployment could
carry it.

Keeping the complement and adding a hand-written list of administrative names to
check it against was the first attempt and was discarded: it writes the four
names twice anyway, and leaves in place the arithmetic that made the
misclassification possible. Removing a failure mode is worth more than guarding
it.

**The names are `objects:read` and `objects:write`.** Two segments and a
(resource, verb) pair, like every other scope, and split by verb for ADR 0049's
reason: a token can hold read without write, which is what makes a ceiling
enumerable rather than asserted. `storage:*` was the runbook's spelling and names
a **surface** rather than a resource — the ground on which ADR 0049 refused
`openapi:read` and ADR 0079 declined to fit the administrative class into the
enum's stated rule.

**The ceiling gains the two names for `authenticated` and `project_admin`, and
for nobody else.** Not `agent_reader`, not `agent_writer`, not
`api_documentation`, not `anon`. Storage is human-only in Session 7, and the
place that is enforced is the `$ref` — `required_scopes` binds to `agent_scope`,
so a capability manifest cannot request an object scope no matter what a role's
ceiling says.

## Alternatives

**Extend the data class: add the two names to `$defs/scope` and
`$defs/agent_scope` both.** The cheapest edit, and it keeps the complement
correct with no new machinery. Rejected: `agent_scope` *is* the data class by
ADR 0079's definition, so widening it to keep the arithmetic tidy widens what a
tool manifest may request — which is D220's proposal and D244's refusal, arriving
by a different route. §8 of the Session 7 plan states the opposite invariant
("an agent token cannot use storage; `agent_scope` unwidened"), and this would
quietly trade a security boundary for one fewer function.

**Supersede ADR 0003 to make objects a resource of the frozen domain.** Coherent,
and it would make the data class the honest home. Rejected for now on cost: ADR
0003 is the fixture every ownership proof in the project runs against, and
superseding it requires matching updates to the capability plan and to
`SEC-RLS-001`, `SEC-VIEW-001`, `AGT-READ-001` and `AGT-WRITE-001`. ADR 0003
already anticipates the *attachment* — an optional object on a note or a task —
and that is the change which belongs in that ADR when Session 8 or later needs
it. A standalone object workflow is not it.

**Keep two classes and simply add the names to the administrative class.** It is
what the complement does anyway, so it would be honest about the code's actual
behaviour. Rejected: it makes `administrative` mean "everything an agent may not
request", which is not what ADR 0079 says it means and not what
`test_an_administrative_scope_is_reachable_only_by_the_admin_role` asserts. The
class would then contain a scope every ordinary user holds, and the word would
have stopped carrying information.

**Add the third class and leave the complement alone.** Rejected on the
measurement: that is arm A, and arm A is the state where the vocabulary is wrong
and one test says so for a reason nobody would connect to the cause.

## Consequences

- `schemas/capabilities.schema.json` gains `$defs/storage_scope`,
  `$defs/administrative_scope` and two names in `$defs/scope`.
  **`$defs/agent_scope` is byte-identical**, which is the security property this
  ADR is most responsible for and the easiest one to lose by accident.
- `scope_registry.administrative_scopes()` becomes a schema read.
  `assert_classes_partition_the_vocabulary()` is called wherever the registry is
  read.
- `test_the_administrative_class_is_derived_not_listed` is **replaced by a
  stricter test**, which is the only ground CLAUDE.md §5 admits for changing a
  passing one: the class is no longer derived, so a test asserting that it is
  cannot be kept. What replaces it asserts the partition, which is what the old
  test was reaching for through the one relation available to it.
- **A fourth class fails loudly.** Whoever adds one gets a message naming the
  classes and the unclassified name, instead of a silent membership in whichever
  class is currently derived. That is the whole return on this ADR, and it is
  paid for by one function.
- `services/auth-api/app/scopes.py` grants the pair to `authenticated` and
  `project_admin`. The role still never implies the scope: what a subject holds
  comes from a server-side record, which is `API-ADMIN-001`'s distinction and
  applies unchanged to storage.
- ADR 0003 is **not** superseded, and object storage remains outside the frozen
  domain. Anything that later attaches an object to a note or a task is that
  ADR's to decide.
