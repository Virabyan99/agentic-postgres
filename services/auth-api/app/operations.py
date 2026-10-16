"""The control plane's operation types, and which of them it accepts (ADR 0254).

**A closed table.** Every type an `/api/v1` operation can ever carry, each
mapped to the Reality Ledger row of the concept it acts on (stage plan D1953,
D2054). A type outside this table does not exist; the control set's
`app.control_operations.type` CHECK lists exactly these keys, and a test holds
the two equal.

**`ACCEPTED_TYPES` follows the rows, and that is the decision.** A type is
accepted exactly when its ledger row is `available`, `beta` or `trial` (ADR
0254, ADR 0261). Session 38's Run 10 moved the six rows the executed types act
on to `trial`; its close returned them to `planned` (D2170). **Session 39's Run 9
moves them to `trial` again, with `direct_endpoint`** (`credential.rotate`'s
row), so the seven executed types were accepted on the commit its trip deployed
(1.17.0); **its close (Run 12) returned all seven rows to `planned`** --
`lifecycle_retrial_live` and `public_endpoints_live` failed on the tagged
evidence (D2415, D2416). **Session 40's Run 8 moved all eleven rows to `trial`;
its close (Run 11) read the tagged evidence**: `endpoints_reearned_live` passed,
so `direct_endpoint` is `beta` and `credential.rotate` stays accepted;
`lifecycle_reearned_live`, `branch_live` and `branch_host_live` failed (D2500,
D2501, D2504-D2506), so the six managed-project types and the four branch types
are refused until a later sitting re-earns them. This
image cannot read the ledger file -- it is not in the build context, and a
running service deciding what exists from a document would make a document its
authority -- so the set is written here and
`test_every_operation_type_names_a_ledger_row_and_is_accepted_iff_its_row_is_reachable`
requires it to equal what the ledger says: a row moved without this set
following, or a type added here while its row is `planned`, fails that guard.
That is the fake-complete guard ADR 0247 wrote, read in both directions.

**`EXECUTED_TYPES` are the six Session 38 builds and Session 39's
`credential.rotate`** (ADR 0256, ADR 0269): the types the control set's
`control_request_operation` records and the reconciler dispatches, each with
one branch of `ARGUMENT_SCHEMA_PATH` (D2154). A type may be accepted only if it
is executed; the converse waits on the ledger -- `credential.rotate` is
executed from Session 39's Run 6 and accepted only when `direct_endpoint`'s row
says so (Run 9).

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

#: The types the control set records and the reconciler executes (Session 38;
#: `credential.rotate` since Session 39, ADR 0269; the four branch types since
#: Session 40, ADR 0271 -- `restore.create` is `branch.create` with a point).
EXECUTED_TYPES: Final[frozenset[str]] = frozenset(
    {
        "project.create",
        "project.delete",
        "project.sleep",
        "project.wake",
        "project.resize",
        "project.export",
        "credential.rotate",
        "branch.create",
        "branch.reset",
        "branch.delete",
        "restore.create",
    }
)

#: Session 40's `BRANCHES_PER_PROJECT = 1` (D2430) is the plan's
#: `branches_total` since Session 41 (`app.plans`, ADR 0274): the number a
#: second `branch.create` or `restore.create` is refused `branch_limit_reached`
#: at, before any row exists.

#: A branch's `expires_at` lies between these, counted from the request (ADR
#: 0272): long enough to outlive the branch's own creation, short enough that a
#: forgotten branch's charge and certificate are bounded in time.
MIN_EXPIRY_SECONDS: Final = 15 * 60
MAX_EXPIRY_SECONDS: Final = 7 * 86400

#: How often the reconciler records each live managed project's backups
#: reading (ADR 0273); the API serves a reading older than twice this as
#: `could_not_determine`.
BACKUP_RECORD_SECONDS: Final = 900

#: The types the control mode accepts. Equal, by the guard, to the types whose
#: ledger row accepts: since Session 40's close, `credential.rotate` alone --
#: `direct_endpoint` is `beta` (endpoints_reearned_live passed); the six
#: managed-project rows and the branch rows are `planned` again (D2500, D2501,
#: D2504). Written out, never derived from `EXECUTED_TYPES` -- building a type
#: is not the decision to accept it.
ACCEPTED_TYPES: Final[frozenset[str]] = frozenset({"credential.rotate"})

#: Idle sleep acts through the type a person's sleep uses (ADR 0276), so it is
#: offered only while that type is accepted: the setting answers `not_available`
#: naming the concept's own row, and the reconciler asks the control set for an
#: idle sleep only then (D2548). `test_reality_ledger` holds the row reachable
#: exactly when the type is accepted.
IDLE_SLEEP_TYPE: Final = "project.sleep"
IDLE_SLEEP_ROW: Final = "idle_sleep"

#: The JSON Schema every operation's `{type, arguments}` validates against,
#: relative to the repository: read by the reconciler before dispatch, and
#: mirrored by `models.py`'s request models, which a test holds equal (D2154).
ARGUMENT_SCHEMA_PATH: Final = "schemas/operation-arguments.schema.json"

#: Every type may record these: the steps it ran (with their seconds), the step
#: it stopped at, a reason, and admission's refusal (D2152, D2160, D2171).
COMMON_RESULT_MEMBERS: Final[frozenset[str]] = frozenset({"reason", "refusal", "step", "steps"})

#: What a branch's creation, restore and reset record (ADR 0271).
BRANCH_RESULT: Final[frozenset[str]] = frozenset(
    {"branch", "direct_host", "pool_host", "reached_point", "target_time", "timeline"}
)

#: Type -> the members its `result` may carry. `app.control_result_members`
#: returns the same lists.
RESULT_MEMBERS: Final[dict[str, frozenset[str]]] = {
    "project.create": COMMON_RESULT_MEMBERS | {"profile", "project_key", "region"},
    "project.delete": COMMON_RESULT_MEMBERS,
    "project.sleep": COMMON_RESULT_MEMBERS,
    "project.wake": COMMON_RESULT_MEMBERS,
    # D2362, ADR 0270: the reading admission decided by, on both outcomes --
    # `{"requested_mb", "safe_available_mb"}` from the reconciler's `admit.sh --json`.
    "project.resize": COMMON_RESULT_MEMBERS | {"admission", "profile"},
    "project.export": COMMON_RESULT_MEMBERS | {"expires_at", "sha256", "size_bytes"},
    # ADR 0269: which role was rotated. Never the verifier, which the row's
    # arguments carry and no result repeats.
    "credential.rotate": COMMON_RESULT_MEMBERS | {"role"},
    # ADR 0271: the branch, its two names, the point asked for and the point
    # its recovery reached, and its timeline. Never a verifier.
    "branch.create": COMMON_RESULT_MEMBERS | BRANCH_RESULT,
    "restore.create": COMMON_RESULT_MEMBERS | BRANCH_RESULT,
    "branch.reset": COMMON_RESULT_MEMBERS | BRANCH_RESULT,
    "branch.delete": COMMON_RESULT_MEMBERS | {"branch"},
}


def is_accepted(operation_type: str) -> bool:
    """Whether the control mode accepts this type now. Unknown types are not."""
    return operation_type in OPERATION_TYPES and operation_type in ACCEPTED_TYPES
