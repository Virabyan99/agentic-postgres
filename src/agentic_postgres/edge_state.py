"""The record that decides what systemd executes as root.

`/etc/agentic-postgres/edge-state.json` names the installed release the
launchers under `/usr/local/libexec/agentic-postgres` resolve before they run
anything. It exists so that a working tree — mid-edit, dirty, or checked out to
some other commit — can never become what a root unit runs after a reboot
(§4.2).

It was read by three consumers and written by nothing. `libexec/…/firewall` and
`libexec/…/edge` both open with a check for this file and exit 3 without it, and
`agentic-postgres-docker-firewall.service` was enabled on a provisioned host
having never once executed. The DOCKER-USER policy was present only because
`--apply` had run the reconciler out of the checkout by hand; nothing would have
reinstated it after a reboot, and the edge unit `Requires=` the firewall unit,
so ingress would have failed too.

Two rules follow from what this file decides.

**The commit is validated before it is used as a path component.** The launchers
already re-check it in shell, and that redundancy is deliberate: a value that
selects a directory to execute as root should be refused by everything that
touches it, not by whichever layer happens to be last.

**The write is atomic.** A launcher reading this file concurrently with a
rewrite must see the old record or the new one, never a truncated one — a
partial read is a missing commit, and a missing commit stops ingress.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_postgres import config
from agentic_postgres.config import ManifestError
from agentic_postgres.installed_release import validate_commit

STATE_PATH = Path("/etc/agentic-postgres/edge-state.json")

SCHEMA_VERSION = 1

__all__ = [
    "SCHEMA_VERSION",
    "STATE_PATH",
    "build_state",
    "load_state",
    "validate_state",
    "write_state",
]


def build_state(*, installed_release_commit: str, host_manifest_sha256: str) -> dict[str, Any]:
    """Assemble a record, validating it before anyone can act on it."""
    document = {
        "schema_version": SCHEMA_VERSION,
        "installed_release_commit": validate_commit(installed_release_commit),
        "host_manifest_sha256": host_manifest_sha256,
        "updated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    return validate_state(document)


def validate_state(document: Any) -> dict[str, Any]:
    """Schema, then the semantic check the schema cannot express."""
    if not isinstance(document, dict):
        raise ManifestError("edge state must be a JSON object")

    config.validate_against_schema(document, "edge-state.schema.json")

    # The pattern in the schema already accepts only 40 lowercase hex
    # characters. Running it through validate_commit as well is not redundancy
    # for its own sake: this is the value that selects a directory to execute as
    # root, and every layer that handles it refuses a bad one.
    validate_commit(document["installed_release_commit"])
    return document


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if path.is_symlink():
        raise ManifestError(f"{path} is a symlink, which is not accepted")
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ManifestError(f"no edge state at {path}") from error
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ManifestError(f"{path} is not valid JSON: {error}") from error
    return validate_state(document)


def write_state(document: dict[str, Any], path: Path = STATE_PATH) -> Path:
    """Write atomically, 0644 root, never through a symlink.

    0644 rather than 0600: the file names a commit and a digest, no secret, and
    an operator diagnosing a failed unit should be able to read what the unit
    resolved without becoming root to do it. What matters is that it is not
    writable by anyone but root, since writing it chooses what root executes.
    """
    validate_state(document)

    if path.is_symlink():
        raise ManifestError(f"{path} is a symlink, which is not accepted")

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"

    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".edge-state.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise

    # The rename is only durable once the directory entry is. Without this a
    # power loss between replace and flush leaves the launchers with no state
    # file at all, which is the exact condition this module exists to remove.
    descriptor = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

    return path
