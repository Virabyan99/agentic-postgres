"""Finding this host's control project, and reading a project's registry pointers.

Moved out of `bin/control.py` in Session 38 (D2168, ADR 0256) so the two root
commands that reach the control plane -- `bin/control.sh` and
`bin/reconciler.sh` -- share ONE rule for which deployed project is the control
project, rather than two copies that could disagree about it (ADR 0093: a
`bin/` command imports only `agentic_postgres` and `yaml`).

**The control project is found, never named**: the one deployed document under
the state root whose `control.enabled` is true (outputs 20, D2068). A version
19 document predates the facility and so does not enable it. Two enabling
documents is exit 5 -- for `control.sh` and for the reconciler at its start,
whose unit then retries every 30 s. A document that cannot be read might be the
control project: a DECISION refuses (exit 6) rather than act on a search it
could not finish; a report says what it could not read (ADR 0195).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NamedTuple

from agentic_postgres import deployed_output

__all__ = [
    "CONTROL_SINCE_VERSION",
    "EXIT_PREREQUISITE",
    "EXIT_REFUSED",
    "EXIT_UNKNOWN",
    "FIELDS",
    "OperatorError",
    "Reading",
    "document_fields",
    "enables_control",
    "find_control",
    "read_all",
    "read_one",
    "target",
]

EXIT_PREREQUISITE = 3
EXIT_REFUSED = 5
EXIT_UNKNOWN = 6

#: The outputs version that first records the facility. An older document was
#: written by a release that had no control plane, so it enables none.
CONTROL_SINCE_VERSION = 20

#: What a registry row copies from a deployed document, in the order printed.
#: The first three are `project.*` members, the last two top-level members.
FIELDS = ("slug", "environment", "domain", "template_version", "source_commit")


class OperatorError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


class Reading(NamedTuple):
    """One directory under the state root: its document, or why there is none."""

    key: str
    document: dict[str, Any] | None
    reason: str | None = None
    missing: bool = False


def read_one(key: str, *, root: Path) -> Reading:
    path = deployed_output.deployed_path(key, root=root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Reading(key, None, "no deployed document", missing=True)
    except OSError:
        return Reading(key, None, "the deployed document could not be read")
    except ValueError:
        return Reading(key, None, "the deployed document is not valid JSON")
    try:
        return Reading(key, deployed_output.read_deployed_document(raw))
    except ValueError as error:
        return Reading(key, None, str(error))


def read_all(*, root: Path) -> list[Reading]:
    """Every directory under the state root, sorted -- a directory is a project the
    deploy established, and one without a document is reported, never skipped."""
    try:
        keys = sorted(path.name for path in root.iterdir() if path.is_dir())
    except FileNotFoundError as error:
        raise OperatorError(
            EXIT_PREREQUISITE,
            f"no deployed project enables the control facility ({root} does not exist)",
        ) from error
    except OSError as error:
        raise OperatorError(EXIT_UNKNOWN, f"{root} could not be listed: {error}") from error
    return [read_one(key, root=root) for key in keys]


def enables_control(document: dict[str, Any]) -> bool | None:
    """True or false from the document; None when it says something unreadable."""
    control = document.get("control")
    if control is None and document.get("schema_version", 0) < CONTROL_SINCE_VERSION:
        return False
    if not isinstance(control, dict) or not isinstance(control.get("enabled"), bool):
        return None
    return control["enabled"]


def find_control(readings: list[Reading], *, decision: bool) -> Reading:
    """The one reading whose document enables the facility, or an OperatorError."""
    enabling = [r for r in readings if r.document is not None and enables_control(r.document)]
    unread = [f"{r.key}: {r.reason}" for r in readings if r.document is None and not r.missing] + [
        f"{r.key}: the document's control member is not readable"
        for r in readings
        if r.document is not None and enables_control(r.document) is None
    ]
    if len(enabling) > 1:
        raise OperatorError(
            EXIT_REFUSED,
            "two deployed projects enable the control facility: "
            + ", ".join(r.key for r in enabling),
        )
    if unread and (decision or not enabling):
        raise OperatorError(
            EXIT_UNKNOWN,
            "which deployed project enables the control facility could not be determined; "
            + "; ".join(unread),
        )
    if not enabling:
        raise OperatorError(EXIT_PREREQUISITE, "no deployed project enables the control facility")
    return enabling[0]


def target(document: dict[str, Any]) -> tuple[str, str]:
    """The control project's database container and database, from its document."""
    database = document.get("database") or {}
    container, name = database.get("container"), database.get("name")
    if not container or not name:
        raise OperatorError(
            EXIT_PREREQUISITE, "the control project's deployed document names no database container"
        )
    return str(container), str(name)


def document_fields(key: str, document: dict[str, Any]) -> tuple[dict[str, str] | None, str | None]:
    """The five pointers, or the reason they cannot be read from this document."""
    project = document.get("project")
    if not isinstance(project, dict):
        return None, "the document names no project"
    if project.get("key") != key:
        return None, f"the document under {key}/ names project {project.get('key')!r}"
    values = {
        "slug": project.get("slug"),
        "environment": project.get("environment"),
        "domain": project.get("domain"),
        "template_version": document.get("template_version"),
        "source_commit": document.get("source_commit"),
    }
    absent = [name for name in FIELDS if not isinstance(values[name], str) or not values[name]]
    if absent:
        return None, "the document carries no " + ", ".join(absent)
    return {name: str(values[name]) for name in FIELDS}, None
