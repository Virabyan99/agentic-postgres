"""The deployed document: what is running, observed rather than intended.

A rendered `outputs.json` says what the manifests describe. This says what the
host actually has — which release is installed, which certificate the edge
holds, which secret generation is mounted. The two share a schema file and
nothing else, and ADR 0012 makes the difference explicit: the deployed document
is a *published observation*, never the authority. Bootstrap state owns provider
ownership; this reports it.

Three properties follow from that.

**Every field is passed in, none is inferred.** This module does no discovery.
A function that both observes and assembles would be one that can quietly
substitute an assumption for a measurement — reporting `tls.status: issued`
because a resolver is configured rather than because a certificate exists. The
caller measures; this validates the shape and refuses what does not fit.

**A deployed document is never byte-compared.** ADR 0013 keeps `observed_at` out
of rendered output and the determinism test scoped to rendered documents; this
one carries timestamps precisely because it describes a moment.

**Nothing here may carry a secret.** The same secret-free assertion the rendered
path uses runs over this document too. A deployed document names paths, ids and
a certificate fingerprint — a public certificate is public, and its digest
reveals nothing a TLS handshake does not already hand out.
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

SCHEMA_VERSION = 2
PROJECT_STATE_ROOT = Path("/etc/agentic-postgres/projects")
RENDERED_ROOT = Path("/var/lib/agentic-postgres/rendered")

__all__ = [
    "PROJECT_STATE_ROOT",
    "RENDERED_ROOT",
    "SCHEMA_VERSION",
    "build_deployed_document",
    "deployed_path",
    "rendered_path",
    "validate_deployed_document",
    "write_deployed_document",
]


def deployed_path(project_key: str, *, root: Path = PROJECT_STATE_ROOT) -> Path:
    return root / project_key / "outputs.json"


def rendered_path(project_key: str, *, root: Path = RENDERED_ROOT) -> Path:
    """The installed rendered directory, not a file inside it.

    Callers need the directory: it is what `bin/compose.sh` is given as the
    Compose project directory. Returning `outputs.json` here would make the one
    caller that wants the directory derive it back out with `.parent`.
    """
    return root / project_key


def build_deployed_document(
    *,
    rendered: dict[str, Any],
    source_commit: str,
    host: dict[str, Any],
    edge: dict[str, Any],
    tls: dict[str, Any],
    bootstrap: dict[str, Any],
    secrets: dict[str, Any],
    runtime: dict[str, Any],
    health_status: str,
) -> dict[str, Any]:
    """Assemble a deployed document from a rendered one plus observed facts.

    The project identity, health-route URL, database block and template version
    are carried over from the rendered document rather than re-derived. Deriving
    them again would create a second path to the same answer, and the failure
    that produces is a deployed document describing a project the render never
    produced — the collision the isolation tests exist to catch, arriving from
    inside the tool instead of from a manifest.

    The health *status* is not carried over, and the schema is what makes that
    unavoidable: rendered documents report `planned`, deployed documents accept
    only `ready` or `unavailable`. A render-time claim and a measurement of a
    running route are different facts that happen to share a field name, and
    copying one into the other would publish "the health endpoint is fine"
    because a manifest once said it would be.
    """
    if rendered.get("document_kind") != "rendered":
        raise ManifestError(
            f"expected a rendered document to build from, got {rendered.get('document_kind')!r}"
        )

    document = {
        "schema_version": SCHEMA_VERSION,
        "document_kind": "deployed",
        "source_commit": source_commit,
        "project": {
            "slug": rendered["project"]["slug"],
            "environment": rendered["project"]["environment"],
            "key": rendered["project"]["key"],
            "domain": rendered["project"]["domain"],
        },
        "host": dict(host),
        "edge": dict(edge),
        "routes": {
            "health": {
                "status": health_status,
                "url": rendered["routes"]["health"]["url"],
            }
        },
        "tls": dict(tls),
        "bootstrap": dict(bootstrap),
        "secrets": dict(secrets),
        "runtime": dict(runtime),
        "database": rendered["database"],
        "template_version": rendered["template_version"],
        "observed_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    return validate_deployed_document(document)


def validate_deployed_document(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ManifestError("a deployed document must be a JSON object")

    config.validate_against_schema(document, "outputs.schema.json")

    if document.get("document_kind") != "deployed":
        raise ManifestError(
            f"expected document_kind 'deployed', got {document.get('document_kind')!r}"
        )

    # The schema constrains the fields it knows. This is the rule that has to
    # hold whatever the schema grows: a deployed document is written to disk on
    # a host and read by tests, and neither is a place for a secret.
    config.assert_no_sensitive_keys(document)

    _refuse_placeholders(document)
    return document


def _refuse_placeholders(document: dict[str, Any]) -> None:
    """Angle-bracket text is a template that escaped, not an observation.

    A deployed document is meant to record real values. `<commit>` passing
    schema validation because it is a string of the right shape is how a
    deployment reports success against a document nobody filled in.
    """

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")
        elif isinstance(node, str) and node.startswith("<") and node.endswith(">"):
            raise ManifestError(f"{path} is an unfilled placeholder: {node!r}")

    walk(document, "")


def write_deployed_document(document: dict[str, Any], path: Path) -> Path:
    """Write atomically at 0600 root.

    0600 rather than 0644: this names the bootstrap state path, the provider
    identity ids and the active secret generation. None of that is a secret, but
    together it is a map of where the secrets are, and there is no reason for an
    unprivileged process on the host to hold it.
    """
    validate_deployed_document(document)

    if path.is_symlink():
        raise ManifestError(f"{path} is a symlink, which is not accepted")

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"

    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".outputs.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise

    descriptor = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

    return path
