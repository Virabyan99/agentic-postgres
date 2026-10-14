"""A branch's record on the host: `branch.json` (Session 40, ADR 0271, D2450).

`bin/branch-runtime.sh` writes it, as root, under
`/etc/agentic-postgres/branches/<key>/<branch>/`; three readers read it --
`capacity_probe` (the branch's charge on the committed line, D2431), the
reconciler (`app.control_branches`, D2450) and `branch-runtime status`. It is
the branch's only state on the host: a branch has no deployed document, no
secret generation and no unit (ADR 0271).

**Three outcomes, never two** (ADR 0195). :func:`read` returns a
:class:`Record`, returns ``None`` when there is no record, and raises
:class:`UnreadableRecord` -- naming why -- when there is a file and it cannot be
read as one. A reader that folded the third into the second would charge an
unreadable branch nothing and report it as gone.

Written 0600 by an atomic rename in its own directory, so a reader sees the
previous record or the next, never half of one.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentic_postgres import naming

__all__ = [
    "BRANCH_ROOT",
    "RECORD_FILENAME",
    "SCHEMA_VERSION",
    "STATES",
    "Record",
    "UnreadableRecord",
    "branch_directory",
    "read",
    "record_path",
    "records",
    "write",
]

#: Where every branch's state lives. Beside `/etc/agentic-postgres/projects`,
#: never inside it: `capacity_probe` lists that directory as PROJECTS, and a
#: branch directory there would be read as a project whose document is missing.
BRANCH_ROOT = Path("/etc/agentic-postgres/branches")

RECORD_FILENAME = "branch.json"
SCHEMA_VERSION = 1

#: The states the runtime writes. `creating` is written BEFORE the restore, so a
#: crash leaves a record a reader can see (and charge, and a delete can clean
#: up) rather than a volume nobody records; `failed` is a create or reset that
#: stopped part way and left what `delete` removes. `deleting` is written before
#: the first removal. A deleted branch has no record at all: its directory is
#: removed last (D2438).
STATES: tuple[str, ...] = ("creating", "ready", "stopped", "failed", "deleting")

_MEMBERS: tuple[str, ...] = (
    "schema_version",
    "project_key",
    "branch",
    "state",
    "operation",
    "requested_point",
    "reached_point",
    "timeline",
    "parent_commit",
    "pool_host",
    "direct_host",
    "expires_at",
    "expires_for",
    "unreclaimable_mb",
    "created_at",
    "updated_at",
)


class UnreadableRecord(Exception):
    """A `branch.json` exists and cannot be read as a record. The message says why."""


@dataclass(frozen=True)
class Record:
    """One branch, as its runtime last wrote it.

    ``requested_point`` is None for a branch made at the end of the archive;
    ``reached_point`` and ``timeline`` are None until the recovery promoted.
    ``unreclaimable_mb`` is the charge admission summed when it admitted the
    branch -- `small`'s database budget, whatever the parent's profile (D2431).
    ``expires_for`` is the member whose operation set ``expires_at``; both or
    neither (ADR 0272).
    """

    project_key: str
    branch: str
    state: str
    operation: str
    requested_point: str | None
    reached_point: str | None
    timeline: int | None
    parent_commit: str | None
    pool_host: str
    direct_host: str
    expires_at: str | None
    expires_for: str | None
    unreclaimable_mb: int
    created_at: str
    updated_at: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        problem = _problem(asdict(self))
        if problem:
            raise ValueError(problem)

    def as_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"


def _problem(data: dict[str, Any]) -> str | None:
    """Why ``data`` is not a record, or None. Every member, every type."""
    if not isinstance(data, dict):
        return "the record is not a JSON object"
    missing = sorted(set(_MEMBERS) - set(data))
    extra = sorted(set(data) - set(_MEMBERS))
    if missing or extra:
        return f"the record's members differ: missing {missing}, unexpected {extra}"
    if data["schema_version"] != SCHEMA_VERSION:
        return f"schema_version {data['schema_version']!r}, this release reads {SCHEMA_VERSION}"
    try:
        naming.validate_branch_name(data["branch"])
    except (naming.NamingError, TypeError) as error:
        return str(error)
    if not isinstance(data["project_key"], str) or "_" in data["project_key"]:
        return f"not a project key: {data['project_key']!r}"
    if data["state"] not in STATES:
        return f"state {data['state']!r} is not one of {list(STATES)}"
    charge = data["unreclaimable_mb"]
    if not isinstance(charge, int) or isinstance(charge, bool) or charge <= 0:
        return f"unreclaimable_mb {charge!r} is not a positive integer"
    if (data["expires_at"] is None) != (data["expires_for"] is None):
        return "expires_at and expires_for are set together or not at all (ADR 0272)"
    timeline = data["timeline"]
    if timeline is not None and (not isinstance(timeline, int) or isinstance(timeline, bool)):
        return f"timeline {timeline!r} is not an integer"
    for member in ("operation", "pool_host", "direct_host", "created_at", "updated_at"):
        if not isinstance(data[member], str) or not data[member]:
            return f"{member} is not a non-empty string"
    for member in (
        "requested_point",
        "reached_point",
        "parent_commit",
        "expires_at",
        "expires_for",
    ):
        if data[member] is not None and not isinstance(data[member], str):
            return f"{member} is neither null nor a string"
    return None


def branch_directory(key: str, branch: str, *, root: Path = BRANCH_ROOT) -> Path:
    """`<root>/<key>/<branch>/`, the branch's whole state directory."""
    naming.validate_branch_name(branch)
    if not key or "/" in key or "_" in key or key.startswith("."):
        raise naming.NamingError(f"not a project key: {key!r}")
    return root / key / branch


def record_path(key: str, branch: str, *, root: Path = BRANCH_ROOT) -> Path:
    return branch_directory(key, branch, root=root) / RECORD_FILENAME


def read(path: Path) -> Record | None:
    """The record at ``path``; None when there is none; :class:`UnreadableRecord`
    when there is a file that is not one (ADR 0195)."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as error:
        raise UnreadableRecord(f"{path} could not be read: {error.strerror}") from None
    try:
        data = json.loads(text)
    except ValueError:
        raise UnreadableRecord(f"{path} is not valid JSON") from None
    problem = _problem(data)
    if problem:
        raise UnreadableRecord(f"{path}: {problem}")
    data.pop("schema_version")
    return Record(**data)


def records(root: Path = BRANCH_ROOT) -> tuple[dict[str, Record], dict[str, str]]:
    """Every branch under ``root``: ``({stem-name: record}, {stem-name: why})``.

    Keyed `<key>_<branch>`. **An absent root is no branches**; a root that
    exists and cannot be listed, or a project directory that cannot, is one
    entry in the second mapping -- never an empty first one. A branch directory
    with no `branch.json` is unreadable too: the runtime writes the record
    before it creates anything, so a directory without one is a state no
    release writes.
    """
    found: dict[str, Record] = {}
    unreadable: dict[str, str] = {}
    try:
        projects = sorted(path for path in root.iterdir() if path.is_dir())
    except FileNotFoundError:
        return found, unreadable
    except OSError as error:
        return found, {f"<{root}>": f"the branch root could not be listed: {error.strerror}"}
    for project in projects:
        try:
            branches = sorted(path for path in project.iterdir() if path.is_dir())
        except OSError as error:
            unreadable[f"{project.name}_*"] = f"{project} could not be listed: {error.strerror}"
            continue
        for directory in branches:
            name = f"{project.name}_{directory.name}"
            try:
                record = read(directory / RECORD_FILENAME)
            except UnreadableRecord as error:
                unreadable[name] = str(error)
                continue
            if record is None:
                unreadable[name] = f"{directory} holds no {RECORD_FILENAME}"
                continue
            if (record.project_key, record.branch) != (project.name, directory.name):
                unreadable[name] = (
                    f"{directory / RECORD_FILENAME} names {record.project_key}_{record.branch}"
                )
                continue
            found[name] = record
    return found, unreadable


def write(path: Path, record: Record) -> None:
    """Write ``record`` to ``path`` atomically, 0600, its directory 0700."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".branch-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(record.as_json())
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
