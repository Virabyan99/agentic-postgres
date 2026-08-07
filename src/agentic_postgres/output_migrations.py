"""Structural migration of `outputs.json` across schema versions (ADR 0012, 0027).

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

Version 3 has the same problem in a second place, and it is answered the same
way. A v2 document predates `database.budget` and `database.container`: the
budget lives in `project.yaml`, and the container name is derived by `naming`,
which this module deliberately does not import — the copy of
``HEALTH_ROUTE_PATH`` below exists for that reason, with a test asserting the
two agree. So `migrate_rendered` requires the caller to supply both, and
refuses without them. It never derives a name and never invents a number.

`migrate_rendered` migrates *to the current version*, chaining v1 -> v2 -> v3
through the single-step functions rather than jumping. A jump would mean the
v1 -> v2 step stopped being exercised the moment v3 existed, and the archived
documents this module exists for are exactly the ones that need the long path.
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

#: What a v2 document contains. A v2 document is a v1 document plus
#: `document_kind`, and the rendered branch is the only kind this module
#: handles, so the deployed-only keys are absent by construction.
_V2_REQUIRED = _V1_REQUIRED | {"document_kind"}

#: The current output schema version. Everything else in this module is written
#: in terms of it so that adding v4 means adding one function and moving one
#: constant, not auditing a scattering of literals.
CURRENT_VERSION = 3

#: Members of `database.budget` in a v3 document. Kept in step with
#: ``config.database_budget``; imported rather than copied would pull the whole
#: manifest layer into a module whose entire value is that it depends on
#: nothing, so ``test_budget_members_agree_with_config`` asserts the two match.
BUDGET_MEMBERS = frozenset(
    {
        "shared_buffers_mb",
        "max_connections",
        "work_mem_mb",
        "maintenance_work_mem_mb",
        "memory_limit_mb",
        "shm_size_mb",
        "unreclaimable_mb",
    }
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_HOSTNAME = re.compile(r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$")
_COMPOSE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

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


def migrate_rendered(
    document: dict[str, Any],
    *,
    secrets_contract_sha256: str,
    database_budget: dict[str, int],
    database_container: str,
) -> dict[str, Any]:
    """Migrate a version 1 or 2 ``rendered`` document to the current version.

    Chains the single-step functions rather than jumping, so a v1 document
    still exercises the v1 -> v2 step that a direct v1 -> v3 path would have
    quietly retired.

    Every argument is required for the same reason: each is a value the input
    document predates, and none of them is derivable from it. Defaulting any
    one would put an invented value in a document that automation reads as
    authoritative.
    """
    version = detect_version(document)
    if version == CURRENT_VERSION:
        raise MigrationError(
            f"document is already version {CURRENT_VERSION}; migration would be a no-op"
        )
    if version not in {1, 2}:
        raise MigrationError(f"only versions 1 and 2 can be migrated, got {version}")

    if version == 1:
        document = migrate_v1_to_v2(document, secrets_contract_sha256=secrets_contract_sha256)

    return migrate_v2_to_v3(
        document,
        database_budget=database_budget,
        database_container=database_container,
    )


def migrate_v1_to_v2(document: dict[str, Any], *, secrets_contract_sha256: str) -> dict[str, Any]:
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


def migrate_v2_to_v3(
    document: dict[str, Any],
    *,
    database_budget: dict[str, int],
    database_container: str,
) -> dict[str, Any]:
    """Return a version 3 ``rendered`` document derived from a version 2 one.

    Version 3 adds two members to `database`, and this module can derive
    neither. `budget` comes from `project.yaml`, which a migrator handed an
    archived output document does not have. `container` is a derived identity,
    and ADR 0002 allows exactly one derivation path for a name — which lives in
    ``naming``, not here. So both are supplied by the caller and validated for
    shape, never guessed.

    No `observed` block is added. The rendered branch has none, and this
    function migrates rendered documents only; a v2 *deployed* document is
    refused above by :func:`require_kind`.
    """
    version = detect_version(document)
    if version == 3:
        raise MigrationError("document is already version 3; migration would be a no-op")
    if version != 2:
        raise MigrationError(f"only version 2 can be migrated to 3, got {version}")

    require_kind(document, "rendered")

    missing = _V2_REQUIRED - set(document)
    if missing:
        raise MigrationError(f"not a complete version 2 document; missing {sorted(missing)}")
    unexpected = set(document) - _V2_REQUIRED
    if unexpected:
        raise MigrationError(
            f"document carries fields no version 2 rendered document has: {sorted(unexpected)}"
        )

    supplied = set(database_budget)
    if supplied != set(BUDGET_MEMBERS):
        raise MigrationError(
            f"database_budget must have exactly {sorted(BUDGET_MEMBERS)}, got {sorted(supplied)}"
        )
    non_integer = sorted(
        key
        for key, value in database_budget.items()
        if not isinstance(value, int) or isinstance(value, bool) or value < 1
    )
    if non_integer:
        raise MigrationError(f"database_budget members must be positive integers: {non_integer}")

    if not isinstance(database_container, str) or not _COMPOSE_NAME.match(database_container):
        raise MigrationError(
            f"database_container is not a usable Compose name: {database_container!r}"
        )

    migrated = {key: _copy(value) for key, value in document.items()}
    migrated["schema_version"] = 3
    migrated["database"]["container"] = database_container
    migrated["database"]["budget"] = dict(database_budget)

    return migrated


def _copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy(item) for item in value]
    return value


__all__ = [
    "BUDGET_MEMBERS",
    "CURRENT_VERSION",
    "HEALTH_ROUTE_PATH",
    "MigrationError",
    "detect_version",
    "document_kind",
    "migrate_rendered",
    "migrate_v1_to_v2",
    "migrate_v2_to_v3",
    "require_kind",
]
