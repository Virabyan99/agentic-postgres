"""The operation types, read against the Reality Ledger (ADR 0254, D2054).

The table itself lives in the auth service's build context
(`services/auth-api/app/operations.py`) because the control mode refuses by it
and cannot import `src/` (ADR 0084); this module loads it and adds the half
only the repository can compute -- what the ledger says each type's row is.

`accepted(type, ledger)` is the ledger's answer; `ACCEPTED_TYPES` is the
service's. The guard in `tests/contract/test_reality_ledger.py` requires them
to agree for every type, which is how *a type is accepted iff its row is
`available`, `beta` or `trial`* stays true of the code that actually refuses
(`trial` since Session 38, ADR 0261).
"""

from __future__ import annotations

from typing import Any

from agentic_postgres import service_source

_operations = service_source.load("operations")

OPERATION_TYPES: dict[str, str] = _operations.OPERATION_TYPES
ACCEPTED_TYPES: frozenset[str] = _operations.ACCEPTED_TYPES
EXECUTED_TYPES: frozenset[str] = _operations.EXECUTED_TYPES
RESULT_MEMBERS: dict[str, frozenset[str]] = _operations.RESULT_MEMBERS
ARGUMENT_SCHEMA_PATH: str = _operations.ARGUMENT_SCHEMA_PATH

#: The ledger statuses under which a concept may be acted on (ADR 0247), with
#: `trial` -- reachable while its evidence is collected -- since ADR 0261.
ACCEPTING_STATUSES: frozenset[str] = frozenset({"available", "beta", "trial"})

__all__ = [
    "ACCEPTED_TYPES",
    "ACCEPTING_STATUSES",
    "ARGUMENT_SCHEMA_PATH",
    "EXECUTED_TYPES",
    "OPERATION_TYPES",
    "RESULT_MEMBERS",
    "accepted",
    "row_status",
]


def row_status(operation_type: str, ledger: dict[str, Any]) -> str | None:
    """The status of the ledger row `operation_type` acts on, or None when the
    type is unknown or its row is missing."""
    row_id = OPERATION_TYPES.get(operation_type)
    for row in ledger.get("rows", []):
        if row.get("id") == row_id:
            return row.get("status")
    return None


def accepted(operation_type: str, ledger: dict[str, Any]) -> bool:
    """Whether the ledger permits this type: its row is `available`, `beta` or `trial`."""
    return row_status(operation_type, ledger) in ACCEPTING_STATUSES
