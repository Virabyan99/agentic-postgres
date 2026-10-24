"""A project's state, read from the auth service's build context (ADR 0293, ADR 0084).

The rule lives in `services/auth-api/app/control_states.py` because the control
mode answers every project's state and cannot import `src/`; this module
re-exports it so `control.sh status` derives each state with the service's own
function (D704) -- one derivation, read by the API and the operator alike.
"""

from __future__ import annotations

from agentic_postgres import service_source

_control_states = service_source.load("control_states")

OPERATOR: str = _control_states.OPERATOR
RECONCILER: str = _control_states.RECONCILER
STATES: tuple[str, ...] = _control_states.STATES
project_state = _control_states.project_state

__all__ = ["OPERATOR", "RECONCILER", "STATES", "project_state"]
