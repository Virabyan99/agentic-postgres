"""The control plane's operation types, and which of them it accepts (ADR 0254).

**A closed table.** Every type an `/api/v1` operation can ever carry, each
mapped to the Reality Ledger row of the concept it acts on (stage plan D1953,
D2054). A type outside this table does not exist; the control set's
`app.control_operations.type` CHECK lists exactly these keys, and a test holds
the two equal.

**`ACCEPTED_TYPES` is empty until the rows move, and that is the decision.** A
type is accepted exactly when its ledger row is `available` or `beta` (and,
once Session 38's Run 10 adds the status, `trial`, ADR 0261); every row is
`planned` today, so nothing is accepted and every write route answers
`409 not_available` naming the row. This image cannot read the ledger file --
it is not in the build context, and a running service deciding what exists from
a document would make a document its authority -- so the set is written here
and `test_every_operation_type_names_a_ledger_row_and_none_is_accepted_while_planned`
requires it to equal what the ledger says: a row moved without this set
following, or a type added here while its row is `planned`, fails that guard.
That is the fake-complete guard ADR 0247 wrote, read in both directions.

**`EXECUTED_TYPES` are the six Session 38 builds** (ADR 0256): the types the
control set's `control_request_operation` records and the reconciler
dispatches, each with one branch of `ARGUMENT_SCHEMA_PATH` (D2154). A type may
be accepted only if it is executed; the converse waits on the ledger.

**`RESULT_MEMBERS`** (D2151): what a finished operation of each type may record
in its `result`. The control set's `app.control_result_members` returns the
same lists, and `control_finish_operation` refuses any other member, so the
reconciler cannot write -- and `GET /v1/operations/{id}` cannot return -- a
member nobody declared.

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

#: The types the control set records and the reconciler executes (Session 38).
EXECUTED_TYPES: Final[frozenset[str]] = frozenset(
    {
        "project.create",
        "project.delete",
        "project.sleep",
        "project.wake",
        "project.resize",
        "project.export",
    }
)

#: The types the control mode accepts. Equal, by the guard, to the types whose
#: ledger row accepts -- none until Run 10 moves the six rows to `trial` (D2170).
ACCEPTED_TYPES: Final[frozenset[str]] = frozenset()

#: The JSON Schema every operation's `{type, arguments}` validates against,
#: relative to the repository: read by the reconciler before dispatch, and
#: mirrored by `models.py`'s request models, which a test holds equal (D2154).
ARGUMENT_SCHEMA_PATH: Final = "schemas/operation-arguments.schema.json"

#: Every type may record these: the steps it ran (with their seconds), the step
#: it stopped at, a reason, and admission's refusal (D2152, D2160, D2171).
COMMON_RESULT_MEMBERS: Final[frozenset[str]] = frozenset({"reason", "refusal", "step", "steps"})

#: Type -> the members its `result` may carry. `app.control_result_members`
#: returns the same lists.
RESULT_MEMBERS: Final[dict[str, frozenset[str]]] = {
    "project.create": COMMON_RESULT_MEMBERS | {"profile", "project_key", "region"},
    "project.delete": COMMON_RESULT_MEMBERS,
    "project.sleep": COMMON_RESULT_MEMBERS,
    "project.wake": COMMON_RESULT_MEMBERS,
    "project.resize": COMMON_RESULT_MEMBERS | {"profile"},
    "project.export": COMMON_RESULT_MEMBERS | {"expires_at", "sha256", "size_bytes"},
}


def is_accepted(operation_type: str) -> bool:
    """Whether the control mode accepts this type now. Unknown types are not."""
    return operation_type in OPERATION_TYPES and operation_type in ACCEPTED_TYPES
