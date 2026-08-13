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

Version 4 is the same story a third time, and the most tempting one to get
wrong. It adds `database.access_profiles`, and two of a profile's five members
genuinely *are* derivable from a v3 document — the transport is fixed by the
profile's name, and the role is already sitting in `database.roles`. Deriving
them would work. It would also make this module a second authority on which
role serves which profile, and ADR 0002 allows one derivation path per name. So
the caller supplies the profiles and this module *validates* them: a profile
naming a role the document does not declare is refused, not corrected.

Version 5 is the first one that asks this module for nothing, and that is worth
saying rather than leaving to be noticed. Everything version 5 adds is on the
*deployed* branch -- published route statuses, an API observation block, public
token metadata, the cluster's instance UUID -- and this module migrates rendered
documents only. So the v4 -> v5 step takes no new argument, invents no field and
changes one integer. It is still a step, still chained, and still refuses a
document that is not a complete v4 rendered one, because the alternative is a
version bump that no code path exercises.

`migrate_rendered` migrates *to the current version*, chaining
v1 -> v2 -> v3 -> v4 -> v5 through the single-step functions rather than
jumping. A jump would mean the v1 -> v2 step stopped being exercised the moment
v3 existed, and the archived documents this module exists for are exactly the
ones that need the long path.
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

#: A v3 document has the same top-level keys as a v2 one. Version 3 added two
#: members *inside* `database`, so the outer shape did not move — which is why
#: this is an alias rather than a copy: writing the set out again would invite
#: the two to drift and say nothing when they did.
_V3_REQUIRED = _V2_REQUIRED

#: And a v4 rendered document has the same top-level keys again: version 4 added
#: a member inside `database`. Same aliasing, same reason.
_V4_REQUIRED = _V3_REQUIRED

#: A v5 rendered document, likewise. Version 5 added only deployed-branch fields
#: and version 6 adds one member inside `database.roles`, so the outer shape has
#: not moved since version 2.
_V5_REQUIRED = _V4_REQUIRED

#: The current output schema version. Everything else in this module is written
#: in terms of it so that adding v6 means adding one function and moving one
#: constant, not auditing a scattering of literals.
CURRENT_VERSION = 10

#: The three access profiles a v4 document carries (ADR 0041), and the transport
#: each one is fixed to. The schema states the same pairing with a `const`; this
#: is the migrator's copy, and ``test_profile_transports_agree_with_the_schema``
#: asserts the two match rather than trusting that they do.
ACCESS_PROFILE_TRANSPORTS: dict[str, str] = {
    "runtime_pooled": "pooled",
    "runtime_direct": "direct",
    "migration_direct": "direct",
}

#: Members of an access profile in a v4 document.
ACCESS_PROFILE_MEMBERS = frozenset(
    {"status", "available_from_session", "transport", "role", "password_secret_ref"}
)

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

#: The same shape ``naming`` validates a derived role against, and the same
#: shape the output schema's ``postgresIdentifier`` states. Copied rather than
#: imported for this module's standing reason -- it depends on nothing -- and
#: ``test_the_role_pattern_agrees_with_the_schema`` asserts the two agree.
_POSTGRES_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")

#: The strict duration grammar, restated here for the same reason the identifier
#: pattern is: this module depends on nothing, and a test asserts it agrees with
#: the schema's `statementTimeouts` pattern. Digits and a unit, no space, no
#: compound, no leading zero -- PostgreSQL reads a bare integer as milliseconds
#: and `0` as *disabled*, so a looser grammar admits a document that turns a
#: timeout off while looking like it set one.
_STATEMENT_TIMEOUT = re.compile(r"^[1-9][0-9]{0,4}(ms|s)$")

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
    access_profiles: dict[str, dict[str, Any]],
    documentation_role: str,
    statement_timeouts: dict[str, str],
    api_connection_budget: int,
    app_docs_url: str,
    auth_connection_budget: int,
) -> dict[str, Any]:
    """Migrate a ``rendered`` document of any earlier version to the current one.

    Chains the single-step functions rather than jumping, so a v1 document
    still exercises the v1 -> v2 step that a direct v1 -> v6 path would have
    quietly retired.

    Every argument is required for the same reason: each is a value the input
    document predates, and none of them is derivable from it. Defaulting any
    one would put an invented value in a document that automation reads as
    authoritative. A v4 input needs none of them, and still passes them: the
    entry point migrates *to the current version* from wherever it starts, and a
    signature that changed shape with the input would make the caller decide
    which arguments its archived document deserves.
    """
    version = detect_version(document)
    if version == CURRENT_VERSION:
        raise MigrationError(
            f"document is already version {CURRENT_VERSION}; migration would be a no-op"
        )
    if version not in {1, 2, 3, 4, 5, 6, 7, 8, 9}:
        raise MigrationError(f"only versions 1 through 9 can be migrated, got {version}")

    if version == 1:
        document = migrate_v1_to_v2(document, secrets_contract_sha256=secrets_contract_sha256)
    if detect_version(document) == 2:
        document = migrate_v2_to_v3(
            document,
            database_budget=database_budget,
            database_container=database_container,
        )
    if detect_version(document) == 3:
        document = migrate_v3_to_v4(document, access_profiles=access_profiles)
    if detect_version(document) == 4:
        document = migrate_v4_to_v5(document)

    if detect_version(document) == 5:
        document = migrate_v5_to_v6(document, documentation_role=documentation_role)

    if detect_version(document) == 6:
        document = migrate_v6_to_v7(document, statement_timeouts=statement_timeouts)

    if detect_version(document) == 7:
        document = migrate_v7_to_v8(document, api_connection_budget=api_connection_budget)

    if detect_version(document) == 8:
        document = migrate_v8_to_v9(document, app_docs_url=app_docs_url)

    return migrate_v9_to_v10(document, auth_connection_budget=auth_connection_budget)


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


def migrate_v3_to_v4(
    document: dict[str, Any], *, access_profiles: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Return a version 4 ``rendered`` document derived from a version 3 one.

    Version 4 adds `database.access_profiles` (ADR 0041). Two of a profile's
    five members *are* derivable from a v3 document — `transport` is fixed by
    the profile's name and `role` is already in `database.roles` — and the
    module still does not derive them. It validates them instead: the caller
    supplies profiles, and a profile naming a role the document does not declare
    is refused rather than accepted or corrected.

    That is the difference that matters. Deriving would make this module a
    second authority on which role serves which profile, and ADR 0002 allows one
    derivation path per name. Validating makes it a check on somebody else's
    answer, which is the only job it can do without becoming the thing it is
    checking.

    A v3 document knows no bound port and no provisioned credential, so every
    profile it gains must be `unavailable` with a null secret reference. A
    migrator that accepted an `available` profile would be inventing a
    deployment.
    """
    version = detect_version(document)
    if version == 4:
        raise MigrationError("document is already version 4; migration would be a no-op")
    if version != 3:
        raise MigrationError(f"only version 3 can be migrated to 4, got {version}")

    require_kind(document, "rendered")

    missing = _V3_REQUIRED - set(document)
    if missing:
        raise MigrationError(f"not a complete version 3 document; missing {sorted(missing)}")
    unexpected = set(document) - _V3_REQUIRED
    if unexpected:
        raise MigrationError(
            f"document carries fields no version 3 rendered document has: {sorted(unexpected)}"
        )

    declared_roles = document["database"].get("roles")
    if not isinstance(declared_roles, dict):
        raise MigrationError("database.roles is missing; this is not a version 3 document")

    supplied = set(access_profiles)
    if supplied != set(ACCESS_PROFILE_TRANSPORTS):
        raise MigrationError(
            f"access_profiles must have exactly {sorted(ACCESS_PROFILE_TRANSPORTS)}, "
            f"got {sorted(supplied)}"
        )

    for name, profile in access_profiles.items():
        if not isinstance(profile, dict):
            raise MigrationError(f"access profile {name!r} is not an object")
        members = set(profile)
        if members != set(ACCESS_PROFILE_MEMBERS):
            raise MigrationError(
                f"access profile {name!r} must have exactly "
                f"{sorted(ACCESS_PROFILE_MEMBERS)}, got {sorted(members)}"
            )
        if profile["transport"] != ACCESS_PROFILE_TRANSPORTS[name]:
            raise MigrationError(
                f"access profile {name!r} names transport {profile['transport']!r}; "
                f"that profile is the {ACCESS_PROFILE_TRANSPORTS[name]!r} transport"
            )
        if profile["role"] not in set(declared_roles.values()):
            raise MigrationError(
                f"access profile {name!r} names role {profile['role']!r}, which this "
                "document does not declare in database.roles"
            )
        if profile["status"] != "unavailable" or profile["password_secret_ref"] is not None:
            raise MigrationError(
                f"access profile {name!r} claims to be provisioned. A version 3 document "
                "records no bound port and no credential, so migrating one cannot produce "
                "an available profile; that is a deployment, not a migration"
            )

    migrated = {key: _copy(value) for key, value in document.items()}
    migrated["schema_version"] = 4
    migrated["database"]["access_profiles"] = {
        name: _copy(profile) for name, profile in access_profiles.items()
    }

    return migrated


def migrate_v4_to_v5(document: dict[str, Any]) -> dict[str, Any]:
    """Return a version 5 ``rendered`` document derived from a version 4 one.

    The step that adds nothing, and the reason it exists anyway.

    Version 5's additions are all on the deployed branch (ADR 0053): the
    published route statuses, the `api` observation block, the public token
    metadata and `database.observed.instance_uuid`. A rendered document has none
    of those and must not grow them -- `routes.rest` and `routes.docs` are bare
    URLs here and stay bare, because a status is a claim about a running service
    and this branch describes a plan.

    So this changes one integer. What it does not do is skip: an unmigrated v4
    document does not validate against the current schema, and a chain that
    jumped from 3 straight to 5 would leave the v3 -> v4 step unexercised for
    every archived document that starts below it. It also still refuses -- a
    deployed document, an incomplete one, or one carrying fields no v4 rendered
    document has -- so a caller cannot use the cheap step as a way past the
    checks the expensive ones make.
    """
    version = detect_version(document)
    if version == 5:
        raise MigrationError("document is already version 5; migration would be a no-op")
    if version != 4:
        raise MigrationError(f"only version 4 can be migrated to 5, got {version}")

    require_kind(document, "rendered")

    missing = _V4_REQUIRED - set(document)
    if missing:
        raise MigrationError(f"not a complete version 4 document; missing {sorted(missing)}")
    unexpected = set(document) - _V4_REQUIRED
    if unexpected:
        raise MigrationError(
            f"document carries fields no version 4 rendered document has: {sorted(unexpected)}"
        )

    if "access_profiles" not in document.get("database", {}):
        raise MigrationError(
            "database.access_profiles is missing; this is not a version 4 document"
        )

    migrated = {key: _copy(value) for key, value in document.items()}
    migrated["schema_version"] = 5
    return migrated


def migrate_v5_to_v6(document: dict[str, Any], *, documentation_role: str) -> dict[str, Any]:
    """Return a version 6 ``rendered`` document derived from a version 5 one.

    Version 6 adds `database.roles.api_documentation` (D158). Unlike version 5,
    which asked this module for nothing, this one changes the *rendered* branch:
    `databaseRoles` is required with `additionalProperties: false` on both, so a
    v5 document does not validate against version 6 and cannot be made to
    without the name.

    ``documentation_role`` is required rather than derived, and that is the same
    call `database_container` got in v2 -> v3. The name *is* derivable — it is
    ``naming.database_role(key_sql, "api_documentation")`` — and deriving it here
    would make this module a second authority on a derived identity, which ADR
    0002 allows exactly one of. So the caller derives it and this module
    validates the shape: an empty string, or one already sitting in
    `database.roles` under another key, is refused rather than accepted.
    """
    version = detect_version(document)
    if version == 6:
        raise MigrationError("document is already version 6; migration would be a no-op")
    if version != 5:
        raise MigrationError(f"only version 5 can be migrated to 6, got {version}")

    require_kind(document, "rendered")

    missing = _V5_REQUIRED - set(document)
    if missing:
        raise MigrationError(f"not a complete version 5 document; missing {sorted(missing)}")
    unexpected = set(document) - _V5_REQUIRED
    if unexpected:
        raise MigrationError(
            f"document carries fields no version 5 rendered document has: {sorted(unexpected)}"
        )

    roles = document.get("database", {}).get("roles")
    if not isinstance(roles, dict) or "object_owner" not in roles:
        raise MigrationError("database.roles is missing or incomplete; this is not a v5 document")
    if "api_documentation" in roles:
        raise MigrationError(
            "database.roles already names api_documentation; this is not a version 5 document"
        )

    if not _POSTGRES_IDENTIFIER.match(documentation_role):
        raise MigrationError(
            f"documentation_role is not a bare lowercase SQL identifier: {documentation_role!r}"
        )

    # The refusal that matters. Every role in this document is distinct by
    # construction -- `naming.database_roles` raises on a collision -- so a
    # duplicate here means the caller passed the wrong role, and accepting it
    # would produce a document in which two names claim one identity and every
    # grant written from it reaches the wrong one.
    collision = {name for name, value in roles.items() if value == documentation_role}
    if collision:
        raise MigrationError(
            f"documentation_role {documentation_role!r} is already this document's "
            f"{sorted(collision)}. Two role keys naming one role is a document in which "
            "a grant cannot be attributed to the role it was written for"
        )

    migrated = {key: _copy(value) for key, value in document.items()}
    migrated["database"]["roles"]["api_documentation"] = documentation_role
    migrated["schema_version"] = 6
    return migrated


def migrate_v6_to_v7(
    document: dict[str, Any], *, statement_timeouts: dict[str, str]
) -> dict[str, Any]:
    """Return a version 7 ``rendered`` document derived from a version 6 one.

    Version 7 adds ``database.statement_timeouts``: the manifest's per-role
    ``statement_timeout``, resolved from role *suffix* to derived role *name*.
    Before it, the manifest declared these, `config` validated them, and the
    render dropped them -- so the bootstrap plane, which reads only this
    document, never saw one and no request role was ever bounded (ADR 0067,
    D197).

    ``statement_timeouts`` is required rather than derived, for the reason
    ``documentation_role`` was in v5 -> v6: the *values* come from a manifest
    this document does not carry, and the *names* come from
    ``naming.database_roles``, of which ADR 0002 allows exactly one authority.
    So the caller resolves and this validates -- that every key is a role the
    document already names, and that every value is the strict duration grammar
    the schema admits. A timeout on a role this document does not know is
    refused rather than written, because that is precisely the setting that
    applies to nothing and says so nowhere.
    """
    version = detect_version(document)
    if version == 7:
        raise MigrationError("document is already version 7; migration would be a no-op")
    if version != 6:
        raise MigrationError(f"only version 6 can be migrated to 7, got {version}")

    require_kind(document, "rendered")

    roles = document.get("database", {}).get("roles")
    if not isinstance(roles, dict) or "app_runtime" not in roles:
        raise MigrationError("database.roles is missing or incomplete; this is not a v6 document")
    if "statement_timeouts" in document.get("database", {}):
        raise MigrationError(
            "database already carries statement_timeouts; this is not a version 6 document"
        )

    known = set(roles.values())
    for role, value in statement_timeouts.items():
        if role not in known:
            raise MigrationError(
                f"statement_timeouts names {role!r}, which this document's database.roles "
                "does not. A timeout on a role the document does not know is applied to "
                "nothing and reports nothing"
            )
        if not _STATEMENT_TIMEOUT.match(value):
            raise MigrationError(
                f"statement_timeouts[{role!r}] is {value!r}, which is not a strict "
                "duration. PostgreSQL reads a bare integer as milliseconds and 0 as "
                "disabled, so a looser grammar would let a document disable a timeout "
                "while looking like it set one"
            )

    migrated = {key: _copy(value) for key, value in document.items()}
    migrated["database"]["statement_timeouts"] = dict(sorted(statement_timeouts.items()))
    migrated["schema_version"] = 7
    return migrated


def migrate_v7_to_v8(document: dict[str, Any], *, api_connection_budget: int) -> dict[str, Any]:
    """Return a version 8 ``rendered`` document derived from a version 7 one.

    Version 8 adds ``database.api_connection_budget``: how many cluster
    connections the REST service commits to. Before it, the bootstrap plane --
    which reads only this document -- could not see the declared pool at all, so
    it gave the application role everything the server had and left the API
    unbounded, because bounding one without the other produces two limits that
    sum past what the server will hand out (D161, ADR 0070).

    Required rather than derived, for the reason every argument here is: the
    figure comes from a manifest this document does not carry, and
    ``config.postgrest_connection_budget`` is its one authority. This validates
    what it is handed -- a positive integer, and one that leaves room for the
    administration reserve beside it -- and computes nothing.
    """
    version = detect_version(document)
    if version == 8:
        raise MigrationError("document is already version 8; migration would be a no-op")
    if version != 7:
        raise MigrationError(f"only version 7 can be migrated to 8, got {version}")

    require_kind(document, "rendered")

    if "api_connection_budget" in document.get("database", {}):
        raise MigrationError(
            "database already carries api_connection_budget; this is not a version 7 document"
        )

    if isinstance(api_connection_budget, bool) or not isinstance(api_connection_budget, int):
        raise MigrationError(
            f"api_connection_budget must be an integer, got {api_connection_budget!r}"
        )
    if api_connection_budget < 1:
        raise MigrationError(
            f"api_connection_budget is {api_connection_budget}; a service that commits no "
            "connection cannot serve a request, and 0 is how PostgreSQL spells "
            "'reject every login' rather than 'unlimited'"
        )

    # The budget the document already carries is what the manifest asked the
    # server for. A commitment that does not fit inside it was never going to
    # be applicable, and refusing here is cheaper than discovering it on a host.
    maximum = int(document["database"]["budget"]["max_connections"])
    if api_connection_budget >= maximum:
        raise MigrationError(
            f"api_connection_budget ({api_connection_budget}) leaves nothing of "
            f"max_connections ({maximum}) for the application or for administration"
        )

    migrated = {key: _copy(value) for key, value in document.items()}
    migrated["database"]["api_connection_budget"] = api_connection_budget
    migrated["schema_version"] = 8
    return migrated


def migrate_v8_to_v9(document: dict[str, Any], *, app_docs_url: str) -> dict[str, Any]:
    """Return a version 9 ``rendered`` document derived from a version 8 one.

    Version 9 adds ``routes.app_docs``: the URL of the application API's
    documentation page, a second surface of the same documentation service
    (D226, ADR 0069) rather than a second service.

    Everything else version 9 adds is on the **deployed** branch -- ``routes.app``
    and ``routes.app_docs`` as status-carrying routes, and
    ``jwt.verifier_acknowledgements`` -- so it is not this function's business.
    That is the same division the v5 step drew, and the reason this step looks
    small: a rendered document describes what would be created, and a status is
    an observation.

    ``app_docs_url`` is supplied rather than derived, for the reason every
    argument in this module is supplied: ``naming.derive`` is the one authority
    for a route (ADR 0002, ADR 0061), and a migrator that computed the URL would
    be a second one -- which is exactly the pair D177 watched drift, where the
    copy carrying a comment saying it was kept in step was the copy that had.

    Not added here: ``routes.app``. The rendered branch has carried it since
    Session 1, which is measured rather than assumed -- ``naming.derive`` builds
    ``route_app`` and ``jwt_issuer`` from it. A step that added it would be
    refusing every document it was given.
    """
    version = detect_version(document)
    if version == 9:
        raise MigrationError("document is already version 9; migration would be a no-op")
    if version != 8:
        raise MigrationError(f"only version 8 can be migrated to 9, got {version}")

    require_kind(document, "rendered")

    routes = document.get("routes", {})
    if "app_docs" in routes:
        raise MigrationError("routes already carries app_docs; this is not a version 8 document")
    if "app" not in routes:
        raise MigrationError(
            "routes carries no app; the rendered branch has derived it since Session 1, so "
            "this document was not written by this project's renderer"
        )

    if not isinstance(app_docs_url, str) or not app_docs_url.startswith("https://"):
        raise MigrationError(f"app_docs_url must be an https URL, got {app_docs_url!r}")
    if app_docs_url in (routes.get("docs"), routes.get("app")):
        raise MigrationError(
            f"app_docs_url {app_docs_url!r} is the URL of another route. Two routes at one "
            "address is a router that answers for whichever was attached last"
        )

    migrated = {key: _copy(value) for key, value in document.items()}
    migrated["routes"]["app_docs"] = app_docs_url
    migrated["schema_version"] = 9
    return migrated


def migrate_v9_to_v10(document: dict[str, Any], *, auth_connection_budget: int) -> dict[str, Any]:
    """Return a version 10 ``rendered`` document derived from a version 9 one.

    Version 10 adds ``database.auth_connection_budget``: how many cluster
    connections the auth service commits to. It exists because the bootstrap
    plane reads only this document (D102, ADR 0067), and a claimant it cannot see
    is one it cannot divide the budget between -- which is ADR 0070's whole
    subject.

    Required rather than derived, for the reason every argument in this module
    is: the figure comes from a manifest this document does not carry, and
    ``config.auth_connection_budget`` is its one authority. This validates what
    it is handed and computes nothing.

    The validation is the v8 step's, applied to a third claimant: a positive
    integer, and one that still leaves the application something. A budget where
    the two services between them take everything is a document that renders and
    a deploy that fails, and it fails in the bootstrap plane where the error
    reads as a cluster problem.
    """
    version = detect_version(document)
    if version == 10:
        raise MigrationError("document is already version 10; migration would be a no-op")
    if version != 9:
        raise MigrationError(f"only version 9 can be migrated to 10, got {version}")

    require_kind(document, "rendered")

    database = document.get("database", {})
    if "auth_connection_budget" in database:
        raise MigrationError(
            "database already carries auth_connection_budget; this is not a version 9 document"
        )
    if "api_connection_budget" not in database:
        raise MigrationError(
            "database carries no api_connection_budget, so this document predates version 8 "
            "and cannot be a version 9 one"
        )

    if isinstance(auth_connection_budget, bool) or not isinstance(auth_connection_budget, int):
        raise MigrationError(
            f"auth_connection_budget must be an integer, got {auth_connection_budget!r}"
        )
    if auth_connection_budget < 1:
        raise MigrationError(
            f"auth_connection_budget is {auth_connection_budget}; a service that commits no "
            "connection cannot answer a request, and 0 is how PostgreSQL spells 'reject "
            "every login' rather than 'unlimited'"
        )

    maximum = int(database["budget"]["max_connections"])
    api = int(database["api_connection_budget"])
    if api + auth_connection_budget >= maximum:
        raise MigrationError(
            f"the two services commit {api} + {auth_connection_budget} of "
            f"max_connections ({maximum}), leaving nothing for the application or for "
            "administration"
        )

    migrated = {key: _copy(value) for key, value in document.items()}
    migrated["database"]["auth_connection_budget"] = auth_connection_budget
    migrated["schema_version"] = 10
    return migrated


def _copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy(item) for item in value]
    return value


__all__ = [
    "ACCESS_PROFILE_MEMBERS",
    "ACCESS_PROFILE_TRANSPORTS",
    "BUDGET_MEMBERS",
    "CURRENT_VERSION",
    "HEALTH_ROUTE_PATH",
    "MigrationError",
    "detect_version",
    "document_kind",
    "migrate_rendered",
    "migrate_v1_to_v2",
    "migrate_v2_to_v3",
    "migrate_v3_to_v4",
    "migrate_v4_to_v5",
    "migrate_v5_to_v6",
    "migrate_v6_to_v7",
    "migrate_v7_to_v8",
    "migrate_v8_to_v9",
    "migrate_v9_to_v10",
    "require_kind",
]
