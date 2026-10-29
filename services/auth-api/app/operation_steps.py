"""Each operation type's steps in the customer's words, and how long they take (ADR 0296).

The control mode serves `expected` with every operation it reads: the type's
steps in order, a plain label each, and the time it typically takes -- a number
read from `capacity.ENVELOPE`, never a promise. The console shows *"usually
about N minutes"* from it and holds no copy of its own.

The step names are the reconciler's (`reconciler_dispatch.STEPS`) and the bounds
its own (`bin/reconciler.py`'s `OPERATION_SECONDS`, `OPERATION_SECONDS_BY_TYPE`);
`tests/contract/test_operation_steps.py` holds all three equal, and each typical
number to the measurement it cites.

Standard library only: `src/agentic_postgres/operation_steps.py` loads this
module through `service_source.load` (ADR 0084).
"""

from __future__ import annotations

from typing import Any, Final

#: Type -> its steps in the reconciler's order, each `(step, label)`.
STEPS: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    "project.create": (
        ("allocate", "Reserving a server slot"),
        ("admit", "Checking there is room on the server"),
        ("deploy-1", "Starting the database"),
        ("admin", "Creating your administrator"),
        ("ports", "Opening the two connection doors"),
        ("deploy-2", "Starting the API and storage"),
        ("unit", "Making it start again after a reboot"),
        ("backup", "Taking the first full backup"),
        ("registry", "Recording the project"),
    ),
    "project.sleep": (
        ("schedule", "Pausing its scheduled jobs"),
        ("unit", "Stopping it from starting after a reboot"),
        ("stop", "Stopping the project"),
    ),
    "project.wake": (
        ("start", "Starting the project"),
        ("unit", "Making it start again after a reboot"),
        ("schedule", "Resuming its scheduled jobs"),
    ),
    "project.resize": (
        ("admit", "Checking there is room for the new size"),
        ("deploy", "Restarting at the new size"),
        ("registry", "Recording the new size"),
    ),
    "project.export": (
        ("dump", "Writing a full dump of the database"),
        ("upload", "Uploading it for download"),
    ),
    "project.delete": (
        ("retire", "Stopping and removing the project"),
        ("tombstone", "Recording the deletion"),
        ("registry", "Freeing its slot"),
    ),
    "credential.rotate": (
        ("check", "Checking the door"),
        ("alter", "Setting the new password"),
        ("sync", "Updating the door's poolers"),
    ),
    "branch.create": (
        ("check", "Checking the project"),
        ("runtime", "Restoring the branch and opening its doors"),
        ("record", "Recording the branch"),
    ),
    "restore.create": (
        ("check", "Checking the project"),
        ("runtime", "Restoring to your point in time and opening its doors"),
        ("record", "Recording the branch"),
    ),
    "branch.reset": (
        ("check", "Checking the branch"),
        ("runtime", "Restoring the branch again"),
        ("record", "Recording the branch"),
    ),
    "branch.delete": (
        ("check", "Checking the branch"),
        ("runtime", "Removing the branch"),
        ("record", "Recording the deletion"),
    ),
}

#: Type -> (low, high) seconds as measured end to end, and where: the subject of
#: a `capacity.ENVELOPE` measurement and the words in its value that hold the
#: number(s). A test reads both back.
_LIFECYCLE: Final = "The lifecycle's other operations at 1.20.0"
_BRANCHES: Final = "A branch's operations on slot3-prod at 1.20.0"
TYPICAL: Final[dict[str, tuple[float, float, tuple[tuple[str, str], ...]]]] = {
    "project.create": (1375.9, 1708.4, (
        ("Provisioning a managed project at 1.20.0", "1,375.9 s"),
        ("The seventh re-earning: slot9-prod's lifecycle at 1.23.0", "create 1,708.4 s"),
    )),
    "project.sleep": (19.6, 19.6, ((_LIFECYCLE, "sleep 19.6 s"),)),
    "project.wake": (20.1, 20.1, ((_LIFECYCLE, "wake 20.1 s"),)),
    "project.resize": (58.8, 59.4, (
        (_LIFECYCLE, "small -> standard 59.4 s"),
        (_LIFECYCLE, "standard -> large 58.8 s"),
    )),
    "project.export": (1.9, 9.2, ((_LIFECYCLE, "export 1.9 / 9.2 s"),)),
    "project.delete": (16.4, 16.4, ((_LIFECYCLE, "delete 16.4 s"),)),
    "credential.rotate": (1.7, 5.1, ((_LIFECYCLE, "x3 1.7, 5.1, 4.4 s"),)),
    "branch.create": (571.5, 571.5, ((_BRANCHES, "(tmp) 571.5 s"),)),
    "restore.create": (486.9, 486.9, ((_BRANCHES, "(dev) 486.9 s"),)),
    "branch.reset": (474.5, 474.5, ((_BRANCHES, "branch.reset 474.5 s"),)),
    "branch.delete": (4.5, 7.8, (
        (_BRANCHES, "branch.delete 7.8 s"),
        (_BRANCHES, "and 4.5 s (dev)"),
    )),
}  # fmt: skip

#: `project.create`'s only per-step measurement (slot6-prod, 1.20.0), each read
#: back from that record's value as `"<step> <seconds>"`.
STEP_SECONDS: Final[dict[str, dict[str, float]]] = {
    "project.create": {
        "allocate": 1.0, "admit": 0.8, "deploy-1": 63.8, "admin": 1.4, "ports": 1.4,
        "deploy-2": 41.2, "unit": 0.9, "backup": 1259.1, "registry": 0.2,
    },
}  # fmt: skip
STEP_SOURCE: Final = "Provisioning a managed project at 1.20.0"

#: The reconciler's bound on one operation, and the three branch types' own.
BOUND_SECONDS: Final = 30 * 60
BOUND_SECONDS_BY_TYPE: Final[dict[str, int]] = {
    "branch.create": 3600,
    "restore.create": 3600,
    "branch.reset": 3600,
}


def expected(operation_type: str) -> dict[str, Any] | None:
    """What an operation of this type is expected to do, or None for a type
    this module does not know -- the reader serves `null` then, never a guess."""
    steps = STEPS.get(operation_type)
    if steps is None:
        return None
    low, high, _ = TYPICAL[operation_type]
    per_step = STEP_SECONDS.get(operation_type, {})
    return {
        "steps": [
            {"step": step, "label": label, "typical_seconds": per_step.get(step)}
            for step, label in steps
        ],
        "typical_seconds": {"low": low, "high": high},
        "bound_seconds": BOUND_SECONDS_BY_TYPE.get(operation_type, BOUND_SECONDS),
    }
