"""Structural migration of `outputs.json` version 1 to version 2 (ADR 0012).

Two things this module deliberately cannot do, both of them the point:

**It never fabricates a `deployed` document.** A deployed document is a published
*observation* — a certificate fingerprint, a provider identifier, a generation
ID, a readiness claim. None of that is derivable from a v1 document, and a
migrator that emitted plausible defaults would produce a file that automation
would believe.

**It is not how `.generated/` is upgraded.** That directory is gitignored and
rewritten transactionally by every render, so the migration path for a working
tree is simply *re-render*. This module exists for a v1 document that was
archived, exported, or handed to a third party — the cases where re-rendering is
not available because the inputs are gone.

The `secrets_contract_sha256` problem is why this returns a document the caller
must complete rather than a finished one. Version 2 requires that digest, and it
is a digest of a file that did not exist when a v1 document was written. Guessing
it would be worse than useless: the whole purpose of the `inputs` block is that
its values are real, and `test_input_digests_are_real_and_correct` exists to say
so. So the migrator requires the caller to supply it, and refuses without it.
"""

from __future__ import annotations

import re
from typing import Any

#: What a v1 document could legitimately contain. Anything else means the input
#: is not a v1 `outputs.json` and migrating it would be guessing.
_V1_REQUIRED = frozenset(
    {
        "schema_version",
        "inputs",
        "project",
        "compose",
        "database",
        "routes",
        "jwt",
        "secrets",
        "storage",
        "backup",
        "capabilities",
        "template_version",
    }
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_HOSTNAME = re.compile(r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$")

#: Kept in step with ``naming.HEALTH_ROUTE_PATH``. Imported rather than copied
#: would create an import cycle for no benefit; ``test_output_migrations.py``
#: asserts the two agree.
HEALTH_ROUTE_PATH = "/__apg/healthz"


class MigrationError(ValueError):
    """The input is not a migratable version 1 document."""


def detect_version(document: dict[str, Any]) -> int:
    version = document.get("schema_version")
    if not isinstance(version, int):
        raise MigrationError(f"schema_version is missing or not an integer: {version!r}")
    return version


def document_kind(document: dict[str, Any]) -> str:
    """Return the document kind, treating an unversioned v1 document as rendered.

    Every consumer that accepts only one kind calls :func:`require_kind` instead.
    This exists for tools that need to *report* what they were handed.
    """
    if detect_version(document) == 1:
        return "rendered"
    kind = document.get("document_kind")
    if kind not in {"rendered", "deployed"}:
        raise MigrationError(f"document_kind is missing or unknown: {kind!r}")
    return kind


def require_kind(document: dict[str, Any], expected: str) -> dict[str, Any]:
    """Refuse a document of the wrong kind, loudly and early.

    The two documents share a basename, so the realistic mistake is passing the
    wrong path. Without this the failure surfaces as a ``KeyError`` on a field
    the other kind does not have, several calls away from the mistake.
    """
    if expected not in {"rendered", "deployed"}:
        raise MigrationError(f"unknown expected kind: {expected!r}")
    actual = document_kind(document)
    if actual != expected:
        raise MigrationError(
            f"expected a {expected!r} outputs document, got {actual!r}. "
            "Rendered output lives under .generated/{project_key}/; deployed state lives "
            "under /var/lib/agentic-postgres/projects/{project_key}/."
        )
    return document


def migrate_rendered(document: dict[str, Any], *, secrets_contract_sha256: str) -> dict[str, Any]:
    """Return a version 2 ``rendered`` document derived from a version 1 one.

    ``secrets_contract_sha256`` is required rather than defaulted because it is a
    digest of a file the v1 document predates. The caller knows which contract
    the migrated document should claim; this module does not, and inventing a
    value would put a false digest in the one block whose whole purpose is that
    its values are real.
    """
    version = detect_version(document)
    if version == 2:
        raise MigrationError("document is already version 2; migration would be a no-op")
    if version != 1:
        raise MigrationError(f"only version 1 can be migrated, got {version}")

    missing = _V1_REQUIRED - set(document)
    if missing:
        raise MigrationError(f"not a complete version 1 document; missing {sorted(missing)}")
    unexpected = set(document) - _V1_REQUIRED
    if unexpected:
        raise MigrationError(
            f"document carries fields no version 1 document has: {sorted(unexpected)}"
        )

    if not _SHA256.match(secrets_contract_sha256):
        raise MigrationError(
            f"secrets_contract_sha256 must be 64 lowercase hex characters, "
            f"got {secrets_contract_sha256!r}"
        )

    domain = document["project"].get("domain", "")
    if not isinstance(domain, str) or not _HOSTNAME.match(domain):
        raise MigrationError(f"project.domain is not a usable hostname: {domain!r}")

    migrated = {key: _copy(value) for key, value in document.items()}
    migrated["schema_version"] = 2
    migrated["document_kind"] = "rendered"
    migrated["inputs"]["secrets_contract_sha256"] = secrets_contract_sha256

    # The health route is derived, not carried: it is a pure function of the
    # domain, so a v1 document already determines it.
    migrated["routes"]["health"] = {
        "status": "planned",
        "url": f"https://{domain}{HEALTH_ROUTE_PATH}",
    }

    # `namespace` is preserved. The runbook's Phase 3 fragment replaces the
    # secrets block wholesale, which would drop a field that
    # test_render_isolation.MUST_DIFFER and evidence.ISOLATED_FIELDS both
    # depend on (ADR 0012).
    migrated["secrets"]["status"] = "planned"
    # Empty, not guessed. A v1 document was written before any secret was
    # declared, so the honest migration says "none declared" rather than
    # asserting the current contract applied retroactively.
    migrated["secrets"].setdefault("required_names", [])

    return migrated


def _copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy(item) for item in value]
    return value


__all__ = [
    "HEALTH_ROUTE_PATH",
    "MigrationError",
    "detect_version",
    "document_kind",
    "migrate_rendered",
    "require_kind",
]
