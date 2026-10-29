"""Each operation type's steps and typical time, read from the auth service's build context
(ADR 0296, ADR 0084).

The table lives in `services/auth-api/app/operation_steps.py` because the control
mode serves it with every operation and cannot import `src/`; this module
re-exports it for the repository's readers -- the test that holds it equal to the
reconciler's steps and to the envelope first.
"""

from __future__ import annotations

from agentic_postgres import service_source

_operation_steps = service_source.load("operation_steps")

BOUND_SECONDS: int = _operation_steps.BOUND_SECONDS
BOUND_SECONDS_BY_TYPE: dict[str, int] = _operation_steps.BOUND_SECONDS_BY_TYPE
STEPS = _operation_steps.STEPS
STEP_SECONDS = _operation_steps.STEP_SECONDS
STEP_SOURCE: str = _operation_steps.STEP_SOURCE
TYPICAL = _operation_steps.TYPICAL
expected = _operation_steps.expected

__all__ = [
    "BOUND_SECONDS",
    "BOUND_SECONDS_BY_TYPE",
    "STEPS",
    "STEP_SECONDS",
    "STEP_SOURCE",
    "TYPICAL",
    "expected",
]
