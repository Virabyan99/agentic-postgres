"""What a generation of secret files contains, described without its contents.

Every immutable generation under
``/var/lib/agentic-postgres/secrets/<key>/generations/<id>/`` carries a
``manifest.json`` saying which declared secrets it materialized, for which
consumer, at which filename, owned by which uid. The deployed ``outputs.json``
points at this file by path, so a deployment that claims secrets are ready can
be checked against a record of what was actually written.

It was required by the output schema and produced by nothing.

**Placement, never content.** No secret value goes in here, and no digest of one
either. A digest would turn this file into a verification oracle for a value it
exists to keep unreadable — anyone who could guess a value could confirm it —
and §16 already refuses digests as an isolation substitute. That a consumer got
its own secret is proved by the mount list plus a successful read by that
consumer, not by a hash a third party can compare.

**Written into the staging directory, before the rename.** The manifest is part
of the generation, not an annotation added afterwards; a generation that became
active without one would be a directory nothing could describe.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_postgres import config
from agentic_postgres.config import ManifestError

SCHEMA_VERSION = 1
SECRET_ROOT = Path("/var/lib/agentic-postgres/secrets")

__all__ = [
    "SCHEMA_VERSION",
    "SECRET_ROOT",
    "build_manifest",
    "manifest_path",
    "validate_manifest",
    "write_manifest",
]


def manifest_path(project_key: str, generation: str, *, root: Path = SECRET_ROOT) -> Path:
    """The path the deployed document records. Its shape is in the schema."""
    return root / project_key / "generations" / generation / "manifest.json"


def _entry(consumer: dict[str, Any]) -> dict[str, Any]:
    """One consumer, as the manifest records it.

    The plane travels with it (ADR 0054). A manifest that recorded a root-plane
    file as though a service held it would describe a grant surface that does
    not exist -- and this file is what an operator reads to answer "who has
    this", so a wrong answer here is worse than none.
    """
    entry = {
        "plane": consumer["plane"],
        "target_file": consumer["target_file"],
        "uid": int(consumer["uid"]),
        "gid": int(consumer["gid"]),
        "mode": consumer["mode"],
        # Placement includes shape. A file written in pgpass format is not the
        # provider's value, and an operator reading this manifest to answer
        # "what is in that file" would otherwise be told the wrong thing.
        "format": consumer["format"],
    }
    if consumer["plane"] != "root":
        entry["service"] = consumer["service"]
    return entry


def build_manifest(
    *,
    project_key: str,
    generation_id: str,
    secrets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Describe what a generation holds, from the secret contract entries.

    Only the fields that say where a file went. ``provider_key`` and
    ``provider_path`` are deliberately dropped: where a value came from is
    bootstrap state's business, and copying the provider layout into a file that
    sits beside the values widens what reading one directory tells an attacker.
    """
    entries = [
        {
            "name": secret["name"],
            "consumers": [_entry(consumer) for consumer in secret["consumers"]],
        }
        for secret in secrets
    ]

    document = {
        "schema_version": SCHEMA_VERSION,
        "generation_id": generation_id,
        "project_key": project_key,
        "materialized_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "secrets": entries,
    }
    return validate_manifest(document)


def validate_manifest(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ManifestError("secret generation manifest must be a JSON object")

    config.validate_against_schema(document, "secret-generation.schema.json")

    # The schema constrains every key it knows about. This is the rule it cannot
    # express: nothing anywhere in the document may be a secret-bearing key.
    # assert_no_sensitive_keys walks the whole structure, so a future field
    # called `password_digest` is refused here rather than in review.
    config.assert_no_sensitive_keys(document)
    return document


def write_manifest(document: dict[str, Any], path: Path) -> Path:
    """Write the manifest into a generation directory, root-owned and read-only.

    No atomic rename here, and that is not an oversight: this is written into
    the staging directory *before* the generation is renamed into place, so the
    whole directory appears at once or not at all. Renaming a file into a
    directory that is itself about to be renamed would add a second failure
    window for no benefit.
    """
    validate_manifest(document)

    if path.is_symlink():
        raise ManifestError(f"{path} is a symlink, which is not accepted")

    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")
    os.chmod(path, 0o400)
    os.chown(path, 0, 0)

    with path.open("rb") as stream:
        os.fsync(stream.fileno())

    return path
