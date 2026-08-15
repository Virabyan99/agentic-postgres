"""Deterministic, context-aware derivation of project-scoped identities.

Runbook §3.7 and §3.8. This module is load-bearing: everything else consumes
it, and nothing else may re-derive a name independently.

It takes primitives rather than a parsed manifest, so it is testable before
``config.py`` exists and cannot grow a hidden dependency on validation order.

Three properties matter more than anything else here, and each has a direct
test in ``tests/contract/test_naming.py``:

1. Every derived PostgreSQL role is independently derived, so no suffix can
   push a role past 63 bytes (rule 9).
2. Truncation is a pure function of ``(context, untruncated value)`` — never
   of Python's randomized ``hash()`` (rule 8).
3. Canonical JSON is byte-stable across processes and runs (rules 10, 11).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

# --------------------------------------------------------------------------
# Limits
# --------------------------------------------------------------------------

#: PostgreSQL truncates identifiers at NAMEDATALEN-1 bytes (runbook §3.7 r5).
POSTGRES_IDENTIFIER_MAX = 63

#: R2/S3 bucket names are 3-63 characters (runbook §3.4, §3.7 r6).
R2_BUCKET_MAX = 63

#: Docker imposes no comparably tight ceiling, but runbook §3.7 rule 4 requires
#: every derived value to have a maximum. 63 is chosen deliberately (plan
#: decision W): it makes every identity in the system truncate at one boundary
#: rather than several, and at the largest input the schema permits — a 31
#: character slug plus a 16 character environment — the longest Compose name is
#: 61 bytes, so this ceiling never actually fires. It is a guard, not a
#: constraint.
COMPOSE_NAME_MAX = 63

#: Number of hexadecimal characters retained from the fingerprint (rule 7).
FINGERPRINT_LENGTH = 10

#: The platform health route, identical for every project. Session 2's edge
#: probe answers here, and the Session 2 gate proves HTTPS through it.
#:
#: The prefix is `/__apg` rather than `/health` on purpose: `/health` is a path
#: an application may reasonably want for itself, and this one cannot be given
#: up. `config.RESERVED_BASE_PATHS` reserves `/__apg` so a project manifest
#: cannot claim it and shadow the route the edge plane is verified through.
HEALTH_ROUTE_PATH = "/__apg/healthz"

#: The documentation root, reserved since Session 1 and published by nobody.
#:
#: `config.RESERVED_BASE_PATHS` keeps a manifest from claiming it, and Session 11
#: is expected to own an index here. **No route names it** — that is ADR 0061:
#: a published route names the page, and a status attached to a root nothing
#: serves is a record that claims to exist and points at nothing.
DOCS_ROOT_PATH = "/docs"

#: Where the REST documentation page is served, under that root.
#:
#: The one derivation of this path (ADR 0002). Run 6 measured the edge's
#: behaviour here against the locked Traefik -- 401 without a credential, 200
#: with it, `Authorization` stripped before the upstream -- and `config` reads
#: this rather than holding a second literal, which is what it did until ADR 0061.
DOCS_PAGE_PATH = f"{DOCS_ROOT_PATH}/rest"

#: Where the application API's documentation page is served, under the same
#: root (D226).
#:
#: A second *surface* of `services/docs/`, not a second service: one image,
#: one CSP, one credential, one mounted snapshot directory holding a second
#: file (ADR 0069). Derived here for the reason `DOCS_PAGE_PATH` is -- ADR
#: 0061 made this module the one authority for a documentation path after
#: `config` held a copy described as kept in step with it, and the copy was
#: the one that had drifted (D177).
DOCS_APP_PAGE_PATH = f"{DOCS_ROOT_PATH}/app"

#: Suffix appended to a project's `api.public_base_path` for the REST surface.
#:
#: Here for the same reason and by the same amendment: `config` held a copy
#: described as "kept in step with `naming.derive`'s `route_rest`", which is the
#: shape ADR 0061 is about with the failure not yet drawn.
REST_PATH_SUFFIX = "/rest"

#: Suffix appended to a project's `api.public_base_path` for the application
#: API surface -- the auth service (Session 6).
#:
#: It was an inline f-string in `derive` until Run 10 needed the path as well as
#: the URL. Both are built from this one constant for the reason ADR 0061 gives:
#: the URL a person is given and the rule a router matches on must move
#: together, and `jwt_issuer` is built from the same expression again.
APP_PATH_SUFFIX = "/app"

#: Suffix appended to the application API's path for the object-storage surface
#: (Session 7). It sits UNDER `APP_PATH_SUFFIX` rather than beside it, because
#: storage is a second surface of the application API and shares its issuer and
#: audience -- so the published path is `/api/app/storage`.
#:
#: One constant, and both the URL and the path are built from it, for ADR 0061's
#: reason: the URL a person is given and the rule a router matches on must move
#: together. The router's rule is NOT a bare `PathPrefix` on this string --
#: `PathPrefix(/api/rest)` matches `/api/restaurant` because it is a string
#: prefix and not a path prefix (D162), and the storage router uses the
#: construction Session 5 arrived at for that.
STORAGE_PATH_SUFFIX = "/storage"

# --------------------------------------------------------------------------
# Output validators (runbook §3.7 rule 4: context-specific validator + maximum)
# --------------------------------------------------------------------------

_POSTGRES_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
_R2_BUCKET = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
_COMPOSE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

#: Traefik router and service names. Hyphens only, no underscores and no dots.
#:
#: A dot is the reason this pattern is tighter than ``_COMPOSE_NAME``: the name
#: is embedded in a *label key* (``traefik.http.routers.<name>.rule``), which
#: Traefik parses by splitting on dots. A name containing one would silently
#: produce a router nobody asked for, under a name nobody chose.
_TRAEFIK_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")

#: Every project-scoped PostgreSQL role. Order is stable because it reaches
#: rendered output; ``object_owner`` is the non-login owner of runbook §3.8.
ROLE_SUFFIXES: tuple[str, ...] = (
    "anon",
    "authenticated",
    "agent_reader",
    "agent_writer",
    "project_admin",
    "postgrest_authenticator",
    "auth_service",
    "mcp_audit_service",
    "storage_service",
    "migration_user",
    "backup_user",
    "app_runtime",
    "object_owner",
    # Session 5, Run 7. The role the OpenAPI capture and the documentation page
    # read the published surface as -- the fourteenth entry D151 anticipated:
    # "the day the documentation role exists, it becomes namable [in
    # statement_timeouts] with no schema change and no test change."
    #
    # Appended rather than placed beside the other request roles because this
    # tuple's order reaches rendered output, and inserting into the middle would
    # move twelve names that nothing about this change touches.
    "api_documentation",
)


class NamingError(ValueError):
    """A derived identity could not be produced, or failed its validator."""


# --------------------------------------------------------------------------
# Truncation
# --------------------------------------------------------------------------


def fingerprint(context: str, value: str) -> str:
    """Return the first 10 hex characters of ``SHA-256("{context}:{value}")``.

    SHA-256 rather than ``hash()``: the built-in is randomized per process by
    ``PYTHONHASHSEED`` and would make rendered output differ between runs
    (runbook §3.7 rule 8).
    """
    payload = f"{context}:{value}".encode()
    return sha256(payload).hexdigest()[:FINGERPRINT_LENGTH]


def truncate(value: str, *, limit: int, context: str, separator: str) -> str:
    """Shorten ``value`` to ``limit`` characters, preserving distinguishability.

    When truncation is required, the result keeps room for ``separator`` plus a
    10 character fingerprint of the *untruncated* value, so two inputs sharing
    a long prefix cannot collapse to the same name (runbook §3.7 rule 7).

    Inputs are lowercase ASCII by the time they reach this module, which is why
    character and byte truncation are equivalent (rule 3). That equivalence is
    asserted rather than assumed — a non-ASCII value would silently break the
    63-*byte* guarantee if it were allowed through.
    """
    if not value.isascii():
        raise NamingError(f"non-ASCII value cannot be length-checked in bytes: {value!r}")
    if len(separator) != 1:
        raise NamingError(f"separator must be one character, got {separator!r}")

    if len(value) <= limit:
        return value

    keep = limit - FINGERPRINT_LENGTH - len(separator)
    if keep < 1:
        raise NamingError(
            f"limit {limit} is too small to truncate with a "
            f"{FINGERPRINT_LENGTH}-character fingerprint"
        )

    return f"{value[:keep]}{separator}{fingerprint(context, value)}"


def _validated(value: str, *, pattern: re.Pattern[str], limit: int, what: str) -> str:
    if len(value) > limit:
        raise NamingError(f"{what} exceeds {limit} characters: {value!r} ({len(value)})")
    if not pattern.match(value):
        raise NamingError(f"{what} is not a valid identifier: {value!r}")
    return value


# --------------------------------------------------------------------------
# Context-specific derivations
# --------------------------------------------------------------------------


def postgres_identifier(value: str, *, context: str) -> str:
    """Truncate and validate ``value`` as an unquoted PostgreSQL identifier."""
    result = truncate(value, limit=POSTGRES_IDENTIFIER_MAX, context=context, separator="_")
    return _validated(
        result,
        pattern=_POSTGRES_IDENTIFIER,
        limit=POSTGRES_IDENTIFIER_MAX,
        what=f"PostgreSQL identifier ({context})",
    )


def compose_name(value: str, *, context: str) -> str:
    """Truncate and validate ``value`` as a Docker Compose resource name."""
    result = truncate(value, limit=COMPOSE_NAME_MAX, context=context, separator="-")
    return _validated(
        result,
        pattern=_COMPOSE_NAME,
        limit=COMPOSE_NAME_MAX,
        what=f"Compose name ({context})",
    )


def traefik_name(value: str, *, context: str) -> str:
    """Truncate and validate ``value`` as a Traefik router or service name.

    Truncated at the same 63 boundary as every other identity (decision W), so
    a long project key produces a distinguishable router name rather than a
    Compose validation failure at deploy time.
    """
    result = truncate(value, limit=COMPOSE_NAME_MAX, context=context, separator="-")
    return _validated(
        result,
        pattern=_TRAEFIK_NAME,
        limit=COMPOSE_NAME_MAX,
        what=f"Traefik name ({context})",
    )


def health_router_name(key: str) -> str:
    """The router and service name for one project's health route.

    Router and service share the name deliberately: Traefik keys them in
    separate namespaces, and one name per route is one fewer thing that can be
    mismatched between the ``routers.<n>.service`` and ``services.<n>`` labels.
    """
    return traefik_name(f"apg-{key}-health", context="traefik_router_health")


def rest_router_name(key: str) -> str:
    """The router and service name for one project's REST route.

    Same construction as the health router and for the same reason: one name
    per route, shared between `routers.<n>.service` and `services.<n>`.
    """
    return traefik_name(f"apg-{key}-rest", context="traefik_router_rest")


def api_buffering_middleware_name(key: str) -> str:
    """The per-project body-size middleware.

    Per-project because the limits are: `api.rest.request_body_max_bytes` is a
    manifest value, and a middleware in the shared baseline file could only
    carry one number for every project on the host. The name is derived so two
    projects cannot define the same middleware and have whichever loaded last
    decide what both of them enforce.
    """
    return traefik_name(f"apg-{key}-api-buffering", context="traefik_middleware_buffering")


def api_stripprefix_middleware_name(key: str) -> str:
    """The per-project middleware that removes the published prefix.

    The REST route is published at `{api.public_base_path}/rest` and PostgREST
    serves its document at `/` and its objects at `/notes`, `/rpc/create_note`.
    Without this the router matches, forwards the path unchanged, and PostgREST
    answers 404 for a path it has never heard of -- which reads at the edge as a
    missing route and is not one (D187).

    Per-project for the same reason the buffering middleware is: the prefix is a
    manifest value, so one middleware in the shared baseline could only carry one
    project's path.

    Measured against the locked Traefik v3.7 before this existed, with a control:
    `/api/rest` arrives as **`/`** rather than as an empty path, `/api/rest/` as
    `/`, and `/api/rest/notes` as `/notes`.
    """
    return traefik_name(f"apg-{key}-api-stripprefix", context="traefik_middleware_stripprefix")


def docs_stripprefix_middleware_name(key: str) -> str:
    """The strip-prefix middleware **both** documentation routers use.

    Its own, not the REST API route's: a middleware name is host-wide in
    Traefik, so two routes sharing one strip the same prefix from both -- and
    `/api/rest` is not `/docs`.

    Shared between the two *documentation* routers for exactly that reason
    read forwards. Since ADR 0087 both strip the documentation **root** rather
    than their own page path, so the container receives `/rest`, `/rest/`,
    `/app` and `/app/` and can tell the two surfaces apart. It could not before:
    `/docs/rest` and `/docs/rest/` both arrived as `/`, and the missing
    distinction is what made the page fail to render when its URL was typed
    without a trailing slash -- measured, `/docs/standalone.js` 404.
    """
    return traefik_name(f"apg-{key}-docs-strip", context="traefik_middleware_docs_strip")


def docs_router_name(key: str) -> str:
    """The router and service name for one project's documentation page.

    Same construction as the health and REST routers, and for the same reason:
    one name per route, shared between `routers.<n>.service` and `services.<n>`
    so the two cannot be mismatched.
    """
    return traefik_name(f"apg-{key}-docs", context="traefik_router_docs")


def app_router_name(key: str) -> str:
    """The router and service name for one project's application API route.

    Session 6 Run 10, and the same construction as every route before it: one
    name shared between `routers.<n>.service` and `services.<n>`.

    It stays a *container label* rather than moving into the file provider, and
    ADR 0085 is the measured reason: a file-provider service can address a
    backend only by DNS, and the Compose service name is shared by every project
    on the host -- measured, it resolves to whichever project the edge attached
    to first, ten times out of ten, with the other unreachable by that name.
    """
    return traefik_name(f"apg-{key}-app", context="traefik_router_app")


def app_stripprefix_middleware_name(key: str) -> str:
    """The application route's strip-prefix middleware.

    Its own, for the reason `docs_stripprefix_middleware_name` is its own: a
    middleware name is host-wide, and the three prefixes differ. This strips
    `{api.public_base_path}/app`, because the auth service serves `/auth/login`
    and `/admin/users` at its root and would answer 404 for the published path.
    """
    return traefik_name(f"apg-{key}-app-stripprefix", context="traefik_middleware_app_strip")


def app_buffering_middleware_name(key: str) -> str:
    """The application route's body-size middleware.

    Not a duplicate of the REST route's, and not decoration. The auth service
    bounds a request body at `strict_json.MAX_BODY_BYTES` -- **after**
    `request.body()` has read all of it. Measured with a control: a 108-byte
    body is read as 108 bytes and an 8 MiB body is read in full and then refused
    for exceeding 16 KiB. The service's bound protects its parser; this protects
    the process, and it is the only thing that does.
    """
    return traefik_name(f"apg-{key}-app-buffering", context="traefik_middleware_app_buffering")


def app_docs_router_name(key: str) -> str:
    """The router and service name for the application documentation page.

    A second router onto the *same* container as `docs_router_name` (D226): one
    image, one CSP, one credential, one mounted snapshot directory holding a
    second file. Two routers rather than one because the two surfaces publish
    two paths and strip two different prefixes.
    """
    return traefik_name(f"apg-{key}-app-docs", context="traefik_router_app_docs")


def docs_credential_middleware_name(key: str) -> str:
    """The per-project documentation credential middleware.

    Derived even though a project has only one, because Traefik's middleware
    namespace is host-wide: two projects whose middlewares collided would share
    one credential file, and the symptom would be that one project's
    documentation password opens the other's.
    """
    return traefik_name(f"apg-{key}-docs-auth", context="traefik_middleware_docs_auth")


def r2_bucket(value: str, *, context: str = "r2_bucket") -> str:
    """Truncate and validate ``value`` as an R2/S3 bucket name."""
    result = truncate(value, limit=R2_BUCKET_MAX, context=context, separator="-")
    if len(result) < 3:
        raise NamingError(f"R2 bucket name is shorter than 3 characters: {result!r}")
    return _validated(
        result, pattern=_R2_BUCKET, limit=R2_BUCKET_MAX, what=f"R2 bucket ({context})"
    )


def project_key(slug: str, environment: str) -> str:
    """``{slug}-{environment}`` (runbook §3.7 rule 1)."""
    return f"{slug}-{environment}"


def sql_key(key: str) -> str:
    """``project_key`` with hyphens replaced by underscores (rule 2)."""
    return key.replace("-", "_")


def database_role(key_sql: str, role_suffix: str) -> str:
    """Derive one complete role name independently (runbook §3.7 rule 9).

    Each role is built and truncated from its own full string. A shared
    truncated prefix with per-role suffixes appended would let a long suffix
    push the total past 63 bytes, which is the failure this rule exists to
    prevent.
    """
    return postgres_identifier(f"apg_{key_sql}_{role_suffix}", context="postgres_role")


def database_roles(key_sql: str) -> dict[str, str]:
    """Derive every role in :data:`ROLE_SUFFIXES`, independently."""
    roles = {suffix: database_role(key_sql, suffix) for suffix in ROLE_SUFFIXES}

    distinct = set(roles.values())
    if len(distinct) != len(roles):
        # Unreachable for schema-valid input; a 40-bit fingerprint makes it
        # vanishingly unlikely. Fail loudly rather than emit a duplicate role.
        raise NamingError(f"role name collision for sql_key {key_sql!r}")
    return roles


# --------------------------------------------------------------------------
# The full derived identity set (runbook §3.8)
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProjectIdentity:
    """Every project-scoped identity derivable without a running system."""

    slug: str
    environment: str
    domain: str
    key: str
    sql_key: str

    compose_project_name: str
    edge_network: str
    internal_network: str
    postgres_volume: str
    #: The name Compose gives the PostgreSQL container: `<project>-<service>-1`.
    #:
    #: This is a *prediction* of Compose's own naming, and it is deliberately
    #: not enforced with `container_name:`. The model forbids that key
    #: (`test_model_does_not_use_container_name`) because it is not
    #: project-scoped, and Session 3 is not an ADR-backed reason to weaken a
    #: passing contract test -- so the identity is recorded here and *checked
    #: against reality* on the host instead. `DEP-ISO-003` compares this string
    #: to the container actually running in Run 8; until then it is unverified,
    #: and it is written down in one place so that the live test compares
    #: against the rendered document rather than against a second f-string.
    #:
    #: It carries no isolation weight of its own: it is a function of
    #: `compose_project_name`, which is already in MUST_DIFFER, so two projects
    #: cannot collide here without colliding there first. See D55.
    postgres_container: str

    database_name: str
    roles: dict[str, str] = field(default_factory=dict)

    route_rest: str = ""
    route_app: str = ""
    route_mcp: str = ""
    route_docs: str = ""
    #: Session 2's public health probe. Under the platform-reserved `/__apg`
    #: prefix rather than `/health`, because `/health` is a path an application
    #: may legitimately want and this one is not negotiable: it is the route the
    #: edge plane proves itself with. `/__apg` is reserved in
    #: ``config.RESERVED_BASE_PATHS`` so a manifest cannot claim it.
    route_health: str = ""
    #: Traefik router and service name for the health route. Project-derived,
    #: so it reaches `compose.env`; the host-derived label values (resolver,
    #: middleware chain) do not, because `host.yaml` is not a digested render
    #: input (ADR 0009).
    health_router: str = ""
    #: The REST surface's *path*, without the scheme and host. `route_rest` is
    #: the URL a person is given; this is what a router rule matches on, and the
    #: two are derived from one expression so a change to the base path cannot
    #: move the published URL without moving the rule.
    route_rest_path: str = ""
    #: Traefik router and service name for the REST route, and the two
    #: per-project middlewares. All three are project-derived and reach
    #: `compose.env`; a middleware name is host-wide in Traefik, so deriving it
    #: is what stops two projects from sharing one.
    rest_router: str = ""
    #: The documentation page's *path*, and its router. Split from `route_docs`
    #: for the reason `route_rest_path` is split from `route_rest`: one is the
    #: URL a person is given and the other is what a rule matches on, and D177
    #: is what happens when the two are derived twice and drift.
    route_docs_path: str = ""
    #: The application documentation page's URL and path. Separate members
    #: from `route_docs`/`route_docs_path` rather than a computed suffix,
    #: because a caller that built one from the other would be the second
    #: derivation ADR 0061 exists to prevent.
    route_app_docs: str = ""
    route_app_docs_path: str = ""
    docs_router: str = ""
    docs_stripprefix_middleware: str = ""
    api_buffering_middleware: str = ""
    api_stripprefix_middleware: str = ""
    docs_credential_middleware: str = ""
    #: The application API's *path*, split from `route_app` for the reason
    #: `route_rest_path` is split from `route_rest`: one is the URL a person is
    #: given and the other is what a router rule matches on, and D177 is what
    #: happens when the two are derived twice and drift.
    route_app_path: str = ""
    #: Session 7's object-storage surface, under the application API. Both
    #: members derived from one expression for ADR 0061's reason, and the URL is
    #: published whether or not storage is enabled -- a rendered document names
    #: what a deployment would create, and whether the provider answers is the
    #: deployed branch's `routes.storage` status (D326).
    route_storage: str = ""
    route_storage_path: str = ""
    #: Session 6 Run 10's routers and middlewares. Project-derived, so all five
    #: reach `compose.env`; a middleware name is host-wide in Traefik, which is
    #: what makes deriving them the thing that stops two projects sharing one.
    app_router: str = ""
    app_stripprefix_middleware: str = ""
    app_buffering_middleware: str = ""
    app_docs_router: str = ""

    jwt_issuer: str = ""
    jwt_audience: str = ""
    secrets_namespace: str = ""

    storage_bucket: str | None = None
    storage_prefix: str | None = None
    backup_stanza: str | None = None
    backup_repository_prefix: str | None = None

    generated_directory: str = ""


def derive(
    *,
    slug: str,
    environment: str,
    domain: str,
    api_base_path: str,
    mcp_base_path: str,
    database_name: str | None = None,
    storage_enabled: bool = True,
    storage_bucket: str | None = None,
    storage_prefix: str | None = None,
    backup_enabled: bool = True,
    backup_stanza: str | None = None,
    backup_repository_prefix: str | None = None,
) -> ProjectIdentity:
    """Derive the complete identity set from validated manifest primitives.

    Callers pass already-validated values. This function enforces the *output*
    contract — context limits and validators — not the input contract, which
    belongs to ``config.py``.
    """
    key = project_key(slug, environment)
    key_sql = sql_key(key)

    return ProjectIdentity(
        slug=slug,
        environment=environment,
        domain=domain,
        key=key,
        sql_key=key_sql,
        compose_project_name=compose_name(f"apg-{key}", context="compose_project"),
        edge_network=compose_name(f"apg-{key}-edge", context="compose_network_edge"),
        internal_network=compose_name(f"apg-{key}-internal", context="compose_network_internal"),
        postgres_volume=compose_name(f"apg-{key}-postgres", context="compose_volume_postgres"),
        postgres_container=compose_name(
            f"apg-{key}-postgres-1", context="compose_container_postgres"
        ),
        database_name=postgres_identifier(
            database_name if database_name else key_sql, context="postgres_database"
        ),
        roles=database_roles(key_sql),
        route_rest=f"https://{domain}{api_base_path}{REST_PATH_SUFFIX}",
        route_rest_path=f"{api_base_path}{REST_PATH_SUFFIX}",
        route_app=f"https://{domain}{api_base_path}{APP_PATH_SUFFIX}",
        route_app_path=f"{api_base_path}{APP_PATH_SUFFIX}",
        route_storage=(f"https://{domain}{api_base_path}{APP_PATH_SUFFIX}{STORAGE_PATH_SUFFIX}"),
        route_storage_path=f"{api_base_path}{APP_PATH_SUFFIX}{STORAGE_PATH_SUFFIX}",
        route_mcp=f"https://{domain}{mcp_base_path}",
        # The page, not the root above it (ADR 0061).
        route_docs=f"https://{domain}{DOCS_PAGE_PATH}",
        route_docs_path=DOCS_PAGE_PATH,
        route_app_docs=f"https://{domain}{DOCS_APP_PAGE_PATH}",
        route_app_docs_path=DOCS_APP_PAGE_PATH,
        route_health=f"https://{domain}{HEALTH_ROUTE_PATH}",
        health_router=health_router_name(key),
        rest_router=rest_router_name(key),
        docs_router=docs_router_name(key),
        docs_stripprefix_middleware=docs_stripprefix_middleware_name(key),
        api_buffering_middleware=api_buffering_middleware_name(key),
        api_stripprefix_middleware=api_stripprefix_middleware_name(key),
        docs_credential_middleware=docs_credential_middleware_name(key),
        app_router=app_router_name(key),
        app_stripprefix_middleware=app_stripprefix_middleware_name(key),
        app_buffering_middleware=app_buffering_middleware_name(key),
        app_docs_router=app_docs_router_name(key),
        jwt_issuer=f"https://{domain}{api_base_path}{APP_PATH_SUFFIX}/auth",
        jwt_audience=f"urn:agentic-postgres:{slug}:{environment}",
        secrets_namespace=f"agentic-postgres/{key}",
        storage_bucket=(
            r2_bucket(storage_bucket if storage_bucket else key) if storage_enabled else None
        ),
        storage_prefix=(
            (storage_prefix if storage_prefix else f"objects/{key}/") if storage_enabled else None
        ),
        backup_stanza=((backup_stanza if backup_stanza else key) if backup_enabled else None),
        backup_repository_prefix=(
            (backup_repository_prefix if backup_repository_prefix else f"pgbackrest/{key}/")
            if backup_enabled
            else None
        ),
        generated_directory=f".generated/{key}",
    )


# --------------------------------------------------------------------------
# Canonical serialization (runbook §3.7 rules 10 and 11)
# --------------------------------------------------------------------------


def canonical_json(data: Any) -> bytes:
    """Serialize to canonical bytes: sorted keys, UTF-8, LF, trailing newline.

    Determinism here is what makes ``outputs.json`` byte-identical across
    renders with identical inputs. ``sort_keys`` removes dict insertion order
    from the output, and there is deliberately no timestamp anywhere in the
    document (plan decision U).
    """
    text = json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=False,
        indent=2,
        separators=(",", ": "),
    )
    return (text + "\n").encode("utf-8")
