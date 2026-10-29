"""The steps and times the control mode serves with an operation (CTL-STEPS-001; ADR 0296).

`operation_steps` is one table read by the service and the console alike. Its
step names must be the reconciler's, its bounds the reconciler's, and every
typical number the measurement it cites -- so a renamed step, a moved bound or
an edited number is red here, not a sentence on a customer's screen.
"""

from __future__ import annotations

import ast

import pytest

from agentic_postgres import REPO_ROOT, capacity, operation_steps, operations
from agentic_postgres import reconciler_dispatch as dispatch

pytestmark = [pytest.mark.contract, pytest.mark.p0]


def _reconciler_constant(name: str) -> object:
    """A module-level literal of `bin/reconciler.py`, read without importing it."""
    tree = ast.parse((REPO_ROOT / "bin" / "reconciler.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            value = node.value
            # `30 * 60`: one product of two literals, folded here.
            if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Mult):
                left, right = ast.literal_eval(value.left), ast.literal_eval(value.right)
                return left * right
            return ast.literal_eval(value)
    raise AssertionError(f"bin/reconciler.py defines no {name}")


def _measurement(subject: str) -> capacity.Measurement:
    found = [m for m in capacity.ENVELOPE if m.subject.startswith(subject)]
    assert len(found) == 1, (subject, [m.subject for m in found])
    return found[0]


def test_every_type_has_the_reconcilers_steps_in_its_order() -> None:
    assert set(operation_steps.STEPS) == set(dispatch.STEPS) == set(operations.EXECUTED_TYPES)
    for kind, steps in operation_steps.STEPS.items():
        assert [s for s, _ in steps] == [s for s, _ in dispatch.STEPS[kind]], kind


def test_every_label_is_a_plain_sentence_fragment() -> None:
    for kind, steps in operation_steps.STEPS.items():
        for step, label in steps:
            assert label and label[0].isupper() and not label.endswith("."), (kind, step)
            assert label.lower() != step and len(label.split()) >= 2, f"{kind}: {label!r}"


def test_the_bounds_are_the_reconcilers() -> None:
    assert operation_steps.BOUND_SECONDS == _reconciler_constant("OPERATION_SECONDS") == 1800
    assert operation_steps.BOUND_SECONDS_BY_TYPE == _reconciler_constant(
        "OPERATION_SECONDS_BY_TYPE"
    )


def test_every_typical_time_is_the_measurement_it_cites() -> None:
    assert set(operation_steps.TYPICAL) == set(operation_steps.STEPS)
    for kind, (low, high, sources) in operation_steps.TYPICAL.items():
        assert 0 < low <= high, kind
        cited = []
        for subject, words in sources:
            value = _measurement(subject).value
            assert words in value, (kind, words, subject)
            cited.append(words)
        text = " ".join(cited)
        for number in {low, high}:
            assert f"{number:,}" in text, f"{kind}: {number} is not in the words it cites"


def test_creations_per_step_seconds_are_slot6s() -> None:
    value = _measurement(operation_steps.STEP_SOURCE).value
    per_step = operation_steps.STEP_SECONDS["project.create"]
    assert list(per_step) == [s for s, _ in operation_steps.STEPS["project.create"]]
    for step, seconds in per_step.items():
        assert f"{step} {seconds:,}" in value, step


def test_expected_serves_steps_times_and_the_bound() -> None:
    create = operation_steps.expected("project.create")
    assert create is not None
    assert [s["step"] for s in create["steps"]][-2:] == ["backup", "registry"]
    assert create["steps"][7] == {
        "step": "backup", "label": "Taking the first full backup", "typical_seconds": 1259.1
    }  # fmt: skip
    assert create["typical_seconds"] == {"low": 1375.9, "high": 1708.4}
    assert create["bound_seconds"] == 1800
    reset = operation_steps.expected("branch.reset")
    assert reset is not None and reset["bound_seconds"] == 3600
    assert all(s["typical_seconds"] is None for s in reset["steps"])
    # Control: a type the module does not know is answered None, never a guess.
    assert operation_steps.expected("project.teleport") is None
