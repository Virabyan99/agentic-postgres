"""Carry a rendered outputs document to the current version (D1105, D1134).

**The class this removes.** Eleven test sites chained the outputs migrator by
hand -- `migrate_v13_to_v14(...)`, then `_v14_to_v15`, `_v15_to_v16`,
`_v16_to_v17` -- and every version bump edited all of them, each instance found
by CI at the end of a run (D965, D1105, and a comment in `test_backup_plane`
that recorded the trap and was walked into anyway). A grep for the previous
step's name finds the line; a grep for the CONCEPT finds nothing.

So the concept gets a name. `carry_to_current` applies every step from the
document's version up to `CURRENT_VERSION`, and a new version adds one entry
to `STEPS` here and nothing anywhere else.

**From version 13 only, deliberately.** The steps below 13 take fixture
parameters a document does not carry (a budget, a container, access
profiles, a documentation role, connection budgets, storage settings, backup
names) and each test that starts lower derives them from its own document in
its own way; a helper that accepted eighteen keyword arguments would be
`migrate_rendered` with a second signature. From 13 upward the only parameter
is the metrics URL, and every caller passes it.

Not a test module: no `test_` prefix, no fixtures, importable by name from a
sibling because pytest's prepend import mode puts this directory on the path.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentic_postgres import output_migrations

__all__ = ["FIRST_CARRIED_VERSION", "STEPS", "carry_to_current"]

#: The lowest version this helper starts from. Below it, a step needs a
#: fixture parameter the document cannot supply.
FIRST_CARRIED_VERSION = 13


def _steps(metrics_url: str) -> dict[int, Callable[[dict[str, Any]], dict[str, Any]]]:
    """Version -> the step that leaves it. One entry per released step."""
    return {
        13: lambda d: output_migrations.migrate_v13_to_v14(d, metrics_url=metrics_url),
        14: output_migrations.migrate_v14_to_v15,
        15: output_migrations.migrate_v15_to_v16,
        16: output_migrations.migrate_v16_to_v17,
    }


#: The versions this helper knows how to leave. Asserted against
#: `CURRENT_VERSION` by `test_output_migrations`, so a new version that was
#: not added here fails ONE test by name rather than eleven by accident.
STEPS: tuple[int, ...] = tuple(range(FIRST_CARRIED_VERSION, output_migrations.CURRENT_VERSION))


def carry_to_current(document: dict[str, Any], *, metrics_url: str) -> dict[str, Any]:
    """Every step from the document's version to the current one, in order.

    Raises rather than guessing for a document below `FIRST_CARRIED_VERSION`,
    and returns the document unchanged only when it is already current --
    which the single-step functions refuse, so a caller cannot tell "carried"
    from "was current" by the exception it did not get, and asks the version.
    """
    steps = _steps(metrics_url)
    version = output_migrations.detect_version(document)
    if version < FIRST_CARRIED_VERSION:
        raise ValueError(
            f"carry_to_current starts at version {FIRST_CARRIED_VERSION}; a version "
            f"{version} document needs the earlier steps' fixture parameters, which the "
            "test that built it derives itself"
        )
    while version < output_migrations.CURRENT_VERSION:
        step = steps.get(version)
        if step is None:
            raise ValueError(
                f"no step leaves version {version}; add it to outputs_chain.STEPS beside "
                "the migrator that introduced the next version"
            )
        document = step(document)
        version = output_migrations.detect_version(document)
    return document
