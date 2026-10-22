"""A project's state, derived from its operation history alone (D2159, ADR 0256).

**One pure function, one record.** The control plane owns its operation
history and nothing else about a project: it holds no credential to the node
(ADR 0246), so it cannot read a doctor, a container or a deployed document.
`project_state` reads the history and answers with one of `STATES`; it never
invents a reading it did not take.

The rules, for the LATEST operation that decides:

* running -- `project.create` `creating`; `project.sleep` `suspending`;
  `project.wake` `starting`; `project.resize` `updating`; `project.delete`
  `deleting`; `project.export` leaves the state as it was, because an export
  does not interrupt the project;
* succeeded -- create, wake, resize and export `ready`; sleep `sleeping`;
  delete `deleted`;
* failed `capacity_exhausted` or `invalid_request`, and cancelled -- nothing
  ran, so the state is the one before it;
* failed `interrupted`, `could_not_determine` or `operation_failed` --
  `unknown`: the operation stopped part way and what it left is not known
  (ADR 0195's third outcome, never folded into `ready`);
* pending -- not started, so the state before it;
* any status of `branch.create`, `branch.reset`, `branch.delete`,
  `restore.create` or `credential.rotate` -- the state before it: these act on
  a branch (its own record, `/branches`) or on a credential, never on the
  project's own compute, so they decide nothing about it (ADR 0287, D2795 --
  read as `unknown` before, the SQL editor refused every project that had
  ever had a branch or a rotation).

A project with no deciding operation -- one the operator adopted (alpha, beta,
the control project) -- is `ready`, and `managed_by` says the operator manages
it: `ready (operator-managed)`, kept as two members so a client switching on
`state` never meets a word with a parenthesis in it.

`degraded` and the doctor's readings are not built (Session 42's support
bundle reads the doctor).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Final

#: Every state this function can answer.
STATES: Final[tuple[str, ...]] = (
    "creating",
    "ready",
    "suspending",
    "sleeping",
    "starting",
    "updating",
    "deleting",
    "deleted",
    "unknown",
)

#: The state a RUNNING operation of each type puts its project in. An export
#: is absent: it does not interrupt the project.
RUNNING: Final[dict[str, str]] = {
    "project.create": "creating",
    "project.sleep": "suspending",
    "project.wake": "starting",
    "project.resize": "updating",
    "project.delete": "deleting",
}

#: The state a SUCCEEDED operation of each type leaves.
SUCCEEDED: Final[dict[str, str]] = {
    "project.create": "ready",
    "project.wake": "ready",
    "project.resize": "ready",
    "project.export": "ready",
    "project.sleep": "sleeping",
    "project.delete": "deleted",
}

#: Failures that ran nothing: the state is the one before the operation.
NOTHING_RAN: Final[frozenset[str]] = frozenset({"capacity_exhausted", "invalid_request"})

#: Failures that may have left the project part way: the third outcome.
UNKNOWN_AFTER: Final[frozenset[str]] = frozenset(
    {"interrupted", "could_not_determine", "operation_failed"}
)

#: Operations that act on a branch or a credential, never on the project's own
#: compute: whatever their status they leave the project's state as it was
#: (ADR 0287). A type in neither this set nor the tables above stays `unknown`.
ELSEWHERE: Final[frozenset[str]] = frozenset(
    {"branch.create", "branch.reset", "branch.delete", "restore.create", "credential.rotate"}
)

#: Who manages a project: the operator (adopted, no operation) or the
#: reconciler (at least one operation decided its state).
OPERATOR: Final = "operator"
RECONCILER: Final = "reconciler"


def project_state(history: Iterable[Mapping[str, Any]]) -> tuple[str, str]:
    """`(state, managed_by)` for a project's operations, OLDEST FIRST.

    Each operation is a mapping with `type`, `status` and `error_code`. A
    history this module cannot read -- an unknown status, a failure with an
    unknown code, a type outside the table -- answers `unknown` rather than
    guessing.
    """
    state: str | None = None
    for operation in history:
        decided = _after(operation)
        if decided is _UNCHANGED:
            continue
        state = decided
    if state is None:
        return "ready", OPERATOR
    return state, RECONCILER


class _Unchanged:
    """The marker for an operation that leaves the state as it was."""


_UNCHANGED: Final = _Unchanged()


def _after(operation: Mapping[str, Any]) -> str | _Unchanged:
    kind, status = operation.get("type"), operation.get("status")
    code = operation.get("error_code")
    if kind in ELSEWHERE:
        return _UNCHANGED
    if status == "running":
        if kind == "project.export":
            return _UNCHANGED
        return RUNNING.get(str(kind), "unknown")
    if status == "succeeded":
        return SUCCEEDED.get(str(kind), "unknown")
    if status in ("pending", "cancelled"):
        return _UNCHANGED
    if status == "failed":
        if code in NOTHING_RAN:
            return _UNCHANGED
        return "unknown"
    return "unknown"
