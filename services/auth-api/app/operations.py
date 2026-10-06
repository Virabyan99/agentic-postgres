"""The control plane's operation types, and which of them it accepts (ADR 0254).

**A closed table.** Every type an `/api/v1` operation can ever carry, each
mapped to the Reality Ledger row of the concept it acts on (stage plan D1953,
D2054). A type outside this table does not exist; the control set's
`app.control_operations.type` CHECK lists exactly these keys, and a test holds
the two equal.

**`ACCEPTED_TYPES` is empty in Session 37, and that is the decision.** A type
is accepted exactly when its ledger row is `available` or `beta`; every row is
`planned` today, so nothing is accepted and `POST /v1/projects` answers
`409 not_available` naming the row. This image cannot read the ledger file --
it is not in the build context, and a running service deciding what exists from
a document would make a document its authority -- so the set is written here
and `test_every_operation_type_names_a_ledger_row_and_none_is_accepted_while_planned`
requires it to equal what the ledger says: a row moved to `beta` without this
set following, or a type added here while its row is `planned`, fails that
guard. That is the fake-complete guard ADR 0247 wrote, read in both directions.

`src/agentic_postgres/operations.py` reaches this module through
`service_source.load` (ADR 0084); **standard library only**, for that reason.
"""

from __future__ import annotations

from typing import Final

#: Type -> the Reality Ledger row of the concept it acts on.
OPERATION_TYPES: Final[dict[str, str]] = {
    "project.create": "projects_self_service",
    "project.delete": "project_deletion",
    "project.sleep": "sleep",
    "project.wake": "sleep",
    "project.resize": "compute_profiles",
    "project.export": "export",
    "branch.create": "branches",
    "branch.reset": "branches",
    "branch.delete": "branches",
    "restore.create": "restore_to_branch",
    "credential.rotate": "direct_endpoint",
}

#: The types the control mode accepts. Equal, by the guard, to the types whose
#: ledger row is `available` or `beta` -- none in Session 37.
ACCEPTED_TYPES: Final[frozenset[str]] = frozenset()


def is_accepted(operation_type: str) -> bool:
    """Whether the control mode accepts this type now. Unknown types are not."""
    return operation_type in OPERATION_TYPES and operation_type in ACCEPTED_TYPES
