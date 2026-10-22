"""A project's state, derived from its operation history alone (D2159, ADR 0256).

`control_states.project_state` is pure: these proofs hand it histories and read
the state. What matters most is the third outcome -- an operation that stopped
part way leaves `unknown`, never `ready` (ADR 0195) -- and that a failure which
ran nothing leaves the state it found.
"""

from __future__ import annotations

from typing import Any

import pytest

from app import control_states

pytestmark = [pytest.mark.contract, pytest.mark.p0]


def _op(kind: str, status: str, code: str | None = None) -> dict[str, Any]:
    return {"type": f"project.{kind}", "status": status, "error_code": code}


CREATED = _op("create", "succeeded")


@pytest.mark.parametrize(
    ("history", "state"),
    [
        ([_op("create", "running")], "creating"),
        ([CREATED], "ready"),
        ([CREATED, _op("sleep", "running")], "suspending"),
        ([CREATED, _op("sleep", "succeeded")], "sleeping"),
        ([CREATED, _op("sleep", "succeeded"), _op("wake", "running")], "starting"),
        ([CREATED, _op("sleep", "succeeded"), _op("wake", "succeeded")], "ready"),
        ([CREATED, _op("resize", "running")], "updating"),
        ([CREATED, _op("resize", "succeeded")], "ready"),
        ([CREATED, _op("export", "running")], "ready"),
        ([CREATED, _op("sleep", "succeeded"), _op("export", "running")], "sleeping"),
        ([CREATED, _op("export", "succeeded")], "ready"),
        ([CREATED, _op("delete", "running")], "deleting"),
        ([CREATED, _op("delete", "succeeded")], "deleted"),
    ],
)
def test_each_operation_moves_the_state_it_names(history: list[dict[str, Any]], state: str) -> None:
    assert control_states.project_state(history) == (state, control_states.RECONCILER)


@pytest.mark.parametrize("code", ["interrupted", "could_not_determine", "operation_failed"])
def test_an_interrupted_operation_leaves_the_state_unknown(code: str) -> None:
    """The third outcome is reported, never folded into `ready` (ADR 0195)."""
    for kind in ("create", "sleep", "wake", "resize", "export", "delete"):
        history = [CREATED, _op(kind, "failed", code)]
        assert control_states.project_state(history)[0] == "unknown", (kind, code)
    # Control: the same history with the operation succeeded is a known state.
    assert control_states.project_state([CREATED, _op("resize", "succeeded")])[0] == "ready"


@pytest.mark.parametrize("code", ["capacity_exhausted", "invalid_request"])
def test_a_failure_that_ran_nothing_leaves_the_state_before_it(code: str) -> None:
    asleep = [CREATED, _op("sleep", "succeeded")]
    assert control_states.project_state([*asleep, _op("resize", "failed", code)])[0] == "sleeping"
    assert control_states.project_state([CREATED, _op("resize", "failed", code)])[0] == "ready"


def test_pending_and_cancelled_leave_the_state_before_them() -> None:
    asleep = [CREATED, _op("sleep", "succeeded")]
    assert control_states.project_state([*asleep, _op("wake", "pending")])[0] == "sleeping"
    assert control_states.project_state([*asleep, _op("wake", "cancelled")])[0] == "sleeping"


def test_an_adopted_project_with_no_operation_is_operator_managed() -> None:
    assert control_states.project_state([]) == ("ready", control_states.OPERATOR)
    # Only operations that ran nothing: still the operator's.
    nothing = [_op("resize", "failed", "capacity_exhausted"), _op("sleep", "cancelled")]
    assert control_states.project_state(nothing) == ("ready", control_states.OPERATOR)


def test_a_history_it_cannot_read_is_unknown() -> None:
    for odd in (
        _op("sleep", "exploded"),
        _op("sleep", "failed", "no_such_code"),
        {"type": "project.teleport", "status": "succeeded", "error_code": None},
        {"type": "project.teleport", "status": "running", "error_code": None},
    ):
        assert control_states.project_state([CREATED, odd])[0] == "unknown", odd


def test_an_operation_on_a_branch_or_a_credential_leaves_the_state() -> None:
    """ADR 0287 (D2795): a branch, a restore to a branch or a rotation decides
    nothing about the project's own state, in any status -- before it, a
    succeeded `branch.create` read `unknown` and the SQL editor (which opens
    only a `ready` or `updating` project) refused the project. The state before
    it is kept, whichever it was."""
    slept = _op("sleep", "succeeded")
    outcomes = [("pending", None), ("running", None), ("succeeded", None),
                ("cancelled", None), ("failed", "interrupted"),
                ("failed", "operation_failed"), ("failed", "could_not_determine")]  # fmt: skip
    assert control_states.ELSEWHERE == {
        "branch.create",
        "branch.reset",
        "branch.delete",
        "restore.create",
        "credential.rotate",
    }
    for kind in sorted(control_states.ELSEWHERE):
        for status, code in outcomes:
            op = {"type": kind, "status": status, "error_code": code}
            assert control_states.project_state([CREATED, op]) == (
                "ready",
                control_states.RECONCILER,
            ), op
            assert control_states.project_state([CREATED, slept, op])[0] == "sleeping", op
    # Alone, it decides nothing: an adopted project with a branch is still the operator's.
    lone = {"type": "branch.create", "status": "succeeded", "error_code": None}
    assert control_states.project_state([lone]) == ("ready", control_states.OPERATOR)


def test_every_operation_type_is_decided_or_elsewhere() -> None:
    """The schema's closed type table (`0003-control-registry.sql`, D2054) is
    covered: every type the reconciler can record is in the succeeded table or
    in `ELSEWHERE` -- a type added later without a rule here reads `unknown`
    for every project it touches, which is how D2795 happened."""
    from app import operations

    covered = set(control_states.SUCCEEDED) | control_states.ELSEWHERE
    assert set(operations.OPERATION_TYPES) <= covered, set(operations.OPERATION_TYPES) - covered


def test_every_state_answered_is_in_the_closed_list() -> None:
    answered = set(control_states.RUNNING.values()) | set(control_states.SUCCEEDED.values())
    assert answered | {"unknown"} <= set(control_states.STATES)
    assert set(control_states.STATES) == answered | {"unknown"}
