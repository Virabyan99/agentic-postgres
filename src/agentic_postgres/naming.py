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

#: The metrics surface, reserved in Session 1 and redeemed in Session 14.
#:
#: ADR 0005 reserved `/metrics` and called a reserved path *"a promise the
#: platform makes about a route it will one day own."* Thirteen sessions later
#: nothing owned it: the string appeared once outside the tests, in
#: `config.RESERVED_BASE_PATHS`. ADR 0164 makes this route its owner.
#:
#: **This is the one derivation of the path.** `config.RESERVED_BASE_PATHS`
#: holds the same characters because it is the *reservation* and this is the
#: *route* — the relationship `DOCS_ROOT_PATH` below already has with the same
#: tuple. `test_the_metrics_route_is_the_path_session_one_reserved` binds them,
#: so neither can move without the other, which is more than the documentation
#: root has ever had.
#:
#: **There is no root above this page**, unlike the documentation surface. The
#: collector's Prometheus exporter serves exactly this path and answers 404 on
#: `/` — measured against the image, not assumed — so nothing here needs a strip
#: prefix and ADR 0087's rewrite has no counterpart in this route.
METRICS_ROUTE_PATH = "/metrics"

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


def metrics_router_name(key: str) -> str:
    """The router and service name for one project's metrics surface (ADR 0164).

    Same construction as every other route's, for the reason `docs_router_name`
    gives: one name shared between `routers.<n>.service` and `services.<n>`, so
    the two cannot be mismatched.

    Derived per project rather than shared, because the surface is per project.
    A single host-scoped router would be the one place two projects' telemetry
    met, and ADR 0164 rejected that shape deliberately rather than by omission.
    """
    return traefik_name(f"apg-{key}-metrics", context="traefik_router_metrics")


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


def storage_router_name(key: str) -> str:
    """The router and service name for one project's object-storage surface.

    **The first NESTED route this project publishes**, and ADR 0108 is what that
    costs. `/api/app/storage` lies inside `/api/app`, so every request to it
    matches two routers, and Traefik's default priority was measured to be the
    rule string's **length** -- read back from its own API as `priority=84` for
    an 84-character rule and `priority=68` for a 68-character one.

    The storage rule is the application rule with `/storage` inserted into both
    matchers, so it is exactly sixteen characters longer for every project and
    every domain (both carry the same `Host()` clause, which cancels). The
    nested route wins by construction rather than by luck, which is why no
    explicit `priority` is set on any router.

    Measured with the control that makes it a finding rather than a
    reassurance: a router ruled ``PathPrefix(`/api/app/deep`)`` is *strictly
    more specific* than the application router and **loses to it**, because at
    50 characters it is shorter than the parent's 68. Concision changes routing.
    """
    return traefik_name(f"apg-{key}-storage", context="traefik_router_storage")


def mcp_router_name(key: str) -> str:
    """The router and service name for one project's agent plane.

    **A top-level route, and that is what makes it different from `storage`.**
    `/mcp` lies inside nothing, so no other rule in this deployment matches it
    and its precedence is uncontested -- derived from the rule's length like
    every other, and asserted by a test that interpolates every rule rather than
    by reasoning about them (ADR 0108, ADR 0128).

    The sibling problem is still real and is answered the same way. `PathPrefix`
    is a string prefix (D162), so `PathPrefix(`/mcp`)` alone would answer
    `/mcpx`; the two-matcher form does not. What differs from the storage route
    is where a sibling LANDS: `/api/app/storagex` is caught by the parent
    application router and gets the auth service's 404, while `/mcpx` matches
    nothing at all and gets **Traefik's own** 404 -- a 19-byte body with no
    `RouterName` (D186, D187, D353). The boundary proof reads which, never the
    status code.
    """
    return traefik_name(f"apg-{key}-mcp", context="traefik_router_mcp")


def storage_stripprefix_middleware_name(key: str) -> str:
    """The storage route's strip-prefix middleware.

    Its own rather than the application route's, and the rig measured why
    sharing is not free: a router referencing a middleware defined by labels on
    **another container** resolves while that container runs and goes
    `status=disabled` when it stops, taking the borrowing route to Traefik's own
    404. `auth` and `storage` are separate containers with separate restarts, so
    a shared middleware would make either one's restart the other's outage.

    It strips `{api.public_base_path}/app/storage`, because the storage surface
    serves `/upload-intents` and `/objects/{id}` at its root.
    """
    return traefik_name(
        f"apg-{key}-storage-stripprefix", context="traefik_middleware_storage_strip"
    )


def storage_buffering_middleware_name(key: str) -> str:
    """The storage route's body-size middleware.

    The same bound as the application route's and for the same measured reason
    (`app_buffering_middleware_name`): the service refuses an oversized body
    *after* `request.body()` has read every byte of it, so the edge has to carry
    the limit one hop earlier. Storage runs the same `strict_json` in the same
    image, so the number is the same one -- and it reaches both labels from the
    same `compose.env` key, `AUTH_REQUEST_BODY_MAX_BYTES`, rather than from a
    second constant that would agree until somebody changed one of them.

    Its own name, not the application route's, for the lifetime reason above.
    """
    return traefik_name(
        f"apg-{key}-storage-buffering", context="traefik_middleware_storage_buffering"
    )


def storage_cors_middleware_name(key: str) -> str:
    """The storage route's CORS middleware (ADR 0109).

    A **container label**, not a file-provider document -- which is where D323
    predicted it, on the premise that the origin list is a root-owned value. It
    is not: it is `storage.allowed_cors_origins`, a manifest field, rendered
    into `compose.env` and published in `outputs.json`. ADR 0086's rule for the
    file provider is about where a *secret* may go, and this is not one.

    Per-project because Traefik's middleware namespace is host-wide, which for
    this middleware would mean one project's origin allowlist deciding
    another's -- the same collision `docs_credential_middleware_name` records
    for a password.

    **This middleware instructs a browser; it does not control access.**
    Measured: a request from an unlisted origin is forwarded to the service and
    answered normally, and only the `Access-Control-Allow-Origin` header is
    withheld. Every claim this project makes about who may reach the storage
    surface rests on the bearer token and the ownership filter.
    """
    return traefik_name(f"apg-{key}-storage-cors", context="traefik_middleware_storage_cors")


def docs_credential_middleware_name(key: str) -> str:
    """The per-project documentation credential middleware.

    Derived even though a project has only one, because Traefik's middleware
    namespace is host-wide: two projects whose middlewares collided would share
    one credential file, and the symptom would be that one project's
    documentation password opens the other's.
    """
    return traefik_name(f"apg-{key}-docs-auth", context="traefik_middleware_docs_auth")


def metrics_credential_middleware_name(key: str) -> str:
    """The per-project metrics credential middleware (ADR 0164).

    Derived for `docs_credential_middleware_name`'s reason and it is the same
    reason twice: Traefik's middleware namespace is host-wide, so two projects
    whose middleware names collided would share one credential, and the symptom
    would be that one project's metrics password opens the other's telemetry.

    **A separate middleware from the documentation one, not a reuse.** They are
    both basic-auth over a materialized secret and it is tempting to share, but
    a shared middleware is a shared credential: rotating the documentation
    password would silently rotate metrics access, and granting a monitoring
    system a scrape credential would hand it the documentation too. The two
    surfaces have different readers and different rotation lifetimes, so they
    get different credentials.
    """
    return traefik_name(f"apg-{key}-metrics-auth", context="traefik_middleware_metrics_auth")


def r2_bucket(value: str, *, context: str = "r2_bucket") -> str:
    """Truncate and validate ``value`` as an R2/S3 bucket name."""
    result = truncate(value, limit=R2_BUCKET_MAX, context=context, separator="-")
    if len(result) < 3:
        raise NamingError(f"R2 bucket name is shorter than 3 characters: {result!r}")
    return _validated(
        result, pattern=_R2_BUCKET, limit=R2_BUCKET_MAX, what=f"R2 bucket ({context})"
    )


def storage_bucket_name(key: str, override: str | None = None) -> str:
    """The R2 bucket for a project, whether or not storage is enabled.

    Split out of :func:`derive` in Session 7 Run 2 so there is still exactly one
    derivation (ADR 0002) with two readers. ``derive`` publishes ``None`` in the
    identity when storage is disabled -- a rendered document must not name a
    bucket for a service that is off -- but ``compose.env`` has to carry a value
    for every variable regardless, because Compose's ``${VAR:?required}``
    refuses an *empty* value as well as an unset one (D178, ADR 0062) and a
    project with storage off would otherwise not render at all.

    So the two readers want different things from one derivation, which is
    precisely the case that produces a second copy if the derivation is not
    named. D330 is the near miss: the manifest's ``bucket`` and ``prefix`` were
    predicted to be a second live derivation and turned out to be overrides of
    this one, and the prediction was only settled by reading the deriver.

    **The derived name carries the ``apg-`` namespace every other derived
    identifier here carries** (D339, ADR 0105). Traefik routers and middlewares
    are ``apg-<key>-…`` and database roles are ``apg_<key>_…``; the bucket was
    the sole exception, and a bucket's collision domain is the whole Cloudflare
    account. Read from a real account rather than reasoned about: one already
    held six unrelated buckets named ``items``, ``photos``, ``pictures`` and
    the like, and a bare ``alpha-dev`` sits in exactly that namespace.

    **An explicit ``override`` is used verbatim and is NOT namespaced.** The
    override exists so an operator can point at a bucket named by a convention
    that is not ours, and prefixing it would defeat the only reason it is there.
    A collision on an overridden name is then the operator's to resolve, which
    is what an override means -- and the bootstrap still refuses to adopt a
    bucket it did not create, so the failure is a stop rather than a silent
    reuse.
    """
    return r2_bucket(override if override else f"apg-{key}")


def storage_object_prefix(key: str, override: str | None = None) -> str:
    """The object-key prefix for a project. See :func:`storage_bucket_name`.

    The per-object suffix is not here: ADR 0102 puts it in
    ``services/auth-api/app/object_keys.py``, composed with this prefix in
    exactly one function, because the build context cannot reach ``src/``.
    """
    return override if override else f"objects/{key}/"


def backup_bucket_name(key: str, override: str | None = None) -> str:
    """The R2 bucket holding a project's pgBackRest repository.

    **A different bucket from :func:`storage_bucket_name`, and that is the
    decision rather than a filing choice** (ADR 0145). R2 scopes an API token
    to buckets far more cleanly than to key prefixes, so "the storage service
    cannot reach the backup repository" becomes a token scope a ``HeadBucket``
    can be measured against, instead of a policy sentence nothing executes.

    ADR 0105 is *applied* here, not restated: the derived name carries the
    ``apg-`` namespace every other derived identifier carries, and an explicit
    override is used **verbatim and unprefixed**, because an override exists so
    an operator can point at a bucket named by a convention that is not ours.

    The ``-backup`` suffix cannot collapse onto this project's own storage
    bucket even when the key is long enough to truncate: :func:`truncate`
    fingerprints the *untruncated* value together with ``context``, and both
    differ here. That is asserted rather than assumed, because
    ``evidence.ISOLATED_FIELDS`` compares identities *between* projects and
    would never see a collision *within* one.
    """
    return r2_bucket(override if override else f"apg-{key}-backup", context="r2_bucket_backup")


def compose_project_name(key: str) -> str:
    """The Compose project name, and the ONE place it is derived.

    Split out of :func:`derive` for :func:`backup_network_name`'s reason -- one
    derivation, more than one reader -- and the second reader is what forced it
    (D592): `runtime_override.database_container_filters` selects a project's
    database container by `com.docker.compose.project`, and it is called with
    **both** document kinds.

    The RENDERED document publishes this as `compose.project_name`. The DEPLOYED
    document does not publish it at all -- it carries `project`, `host`, `routes`,
    `database` and the rest, and `compose` is not among them. So a selector that
    read the published value worked from a render and raised from a deployment,
    which is what `bin/backup.sh --outputs /etc/...` hands it.

    Calling this is not a second derivation under ADR 0002: it *is* the
    authority, and `derive` calls it too. What ADR 0002 forbids is
    re-implementing `f"apg-{key}"` somewhere else, which is exactly what this
    exists to stop.
    """
    return compose_name(f"apg-{key}", context="compose_project")


def postgres_volume_name(key: str) -> str:
    """The live cluster's data volume, and the ONE place it is derived.

    The third name split out of :func:`derive` for one reason -- more than one
    reader -- after :func:`backup_network_name` and :func:`compose_project_name`.

    It is the name `bin/restore-test.sh` must never touch, and it used to be
    read from `compose.volumes.postgres`. **Only the RENDERED document publishes
    a `compose` block**; the DEPLOYED document -- what
    `/etc/agentic-postgres/projects/<key>/outputs.json` holds, and what an
    operator passes to `--outputs` -- does not. So the drill refused every real
    invocation with "the deployed document names no postgres volume" while
    passing against a render (D598).

    That is D592 a second time, in the same command, one field along: the repair
    there was applied to `compose.project_name` because that was the field that
    failed, and not to every field read out of the same absent block. Calling
    this is not a second derivation under ADR 0002 -- it IS the authority, and
    `derive` calls it too.
    """
    return compose_name(f"apg-{key}-postgres", context="compose_volume_postgres")


def backup_network_name(key: str) -> str:
    """The egress network the cluster reaches its backup repository over.

    Split out of :func:`derive` for :func:`storage_bucket_name`'s reason -- one
    derivation, more than one reader. ``derive`` is one; the rendered Compose
    model is another (Run 4); and ``output_migrations`` is a third, which is the
    reader that forces the split: a migrator computing ``f"apg-{key}-backup"``
    inline would be a second derivation of a name ADR 0002 allows one of, and it
    is the copy nobody re-reads when this one changes.

    No override. ``storage.bucket`` takes one because a bucket is a third
    party's namespace that an operator may already have populated; a Docker
    network is created by this project, on this host, every deploy.
    """
    return compose_name(f"apg-{key}-backup", context="compose_network_backup")


#: A drill identifier: lowercase letters and digits, and nothing else.
#:
#: Validated rather than trusted because it is the ONE component of a derived
#: name that does not come from the project identity. It reaches this function
#: from `bin/restore-test.py`, which generates it -- but a name assembled from an
#: unvalidated component is a name whose shape depends on its caller, and the
#: whole point of this module is that no name does.
_DRILL_ID = re.compile(r"\A[0-9a-z]{4,24}\Z")


@dataclass(frozen=True)
class RestoreDrillNames:
    """The resources one restore rehearsal owns, and nothing else.

    Returned as a set rather than by three functions because they are created
    and destroyed together: a caller that could derive one without the others is
    a caller that can tear down half a drill.
    """

    volume: str
    container: str
    restore_container: str


def restore_drill_names(key: str, drill_id: str) -> RestoreDrillNames:
    """The disposable resources for one restore rehearsal (ADR 0151).

    **The three stems differ, and that is what keeps the names apart -- not the
    contexts.** Run 8's mutation battery is why this paragraph says so: arm Q7
    changed the volume's context to ``compose_volume_postgres``, the live
    volume's own, and **nothing went red**. It could not: :func:`truncate`
    fingerprints ``(context, value)``, and these values already differ from
    ``apg-<key>-postgres`` and from each other, so the fingerprints differ
    whatever the contexts are. The first draft of ADR 0151 claimed the contexts
    were load-bearing here; they are not, and a survivor said so (D493's
    category, reached honestly).

    A context is still given to each, because every derivation in this module
    names one and because the guarantee it *does* buy is real: two derivations
    that ever shared a stem would still not collapse. It is a convention with a
    latent purpose rather than the reason these three are distinct.

    ``-pg`` and ``-pgbackrest`` are therefore not cosmetic. Without them the
    volume and the instance container would be the **same string** for any key
    short enough to escape truncation and *different* strings for any key long
    enough to hit it -- an identity that is sometimes equal and sometimes not,
    which is the kind of thing a test then passes for the wrong reason (D374).

    ``drill_id`` is part of the name so that a leftover from a crashed drill is a
    **different resource** from the next drill's, rather than something the next
    drill adopts. Measured (rig 8, arm J): ``docker volume create`` on a name
    that already exists exits **0** and keeps the original volume, so "reuse one
    volume per project" and "silently restore into whatever a crashed drill left
    behind" are the same code path.

    Two containers, because the restore and the instance are two things:
    pgBackRest writes PGDATA in a one-shot container that exits, and the image's
    own entrypoint then starts a cluster on it. That is what makes the drill
    instance come up by the route production uses rather than by a route invented
    for the drill (ADR 0065/0066).
    """
    if not _DRILL_ID.match(drill_id):
        raise NamingError(
            f"drill id is not a valid identifier: {drill_id!r} "
            "(4-24 characters, lowercase letters and digits)"
        )
    stem = f"apg-{key}-restore-{drill_id}"
    return RestoreDrillNames(
        volume=compose_name(stem, context="compose_volume_restore_drill"),
        container=compose_name(f"{stem}-pg", context="compose_container_restore_drill"),
        restore_container=compose_name(
            f"{stem}-pgbackrest", context="compose_container_restore_drill_pgbackrest"
        ),
    )


#: The jurisdictions Cloudflare documents for R2, and the only values
#: `storage.jurisdiction` admits.
#:
#: READ FROM VENDOR DOCUMENTATION, NOT MEASURED, and recorded as such because
#: this repository's defect pattern is a value that looked measured and was not.
#: Run 5 measured `default` -- the probe bucket reports `jurisdiction: default`
#: and every arm of the rig dialled its endpoint. The other two are names in a
#: list that nothing here has ever dialled (ADR 0106).
R2_JURISDICTIONS: tuple[str, ...] = ("default", "eu", "fedramp")

#: A Cloudflare account id as it appears in the endpoint hostname.
_R2_ACCOUNT_ID = re.compile(r"\A[0-9a-f]{32}\Z")


def storage_endpoint_url(account_id: str, jurisdiction: str = "default") -> str:
    """The S3 endpoint for one Cloudflare account, derived in exactly one place.

    Measured in Run 5 against a real account rather than read from the S3
    documentation: ``https://<ACCOUNT_ID>.r2.cloudflarestorage.com``, with a
    jurisdictional bucket reachable only through its own host. The account id is
    32 lowercase hex characters.

    **This is the only assembly site** (ADR 0002, ADR 0106). The container is
    handed the finished URL as ``STORAGE_ENDPOINT`` rather than the two
    fragments and a format string, because a second assembly inside the image
    would be a second authority for a value the deploy already knows -- which is
    what two derivations of the documentation route cost in Session 5 (D177),
    where the copy whose comment said it was "kept in step" was the one that had
    drifted.

    The account id is validated here rather than trusted from the manifest: a
    malformed one produces a hostname that resolves to nothing, and a DNS
    failure at the first presign is a much worse place to learn about a typo
    than validation is.
    """
    if not _R2_ACCOUNT_ID.match(account_id):
        raise NamingError(f"R2 account id must be 32 lowercase hex characters: {account_id!r}")
    if jurisdiction not in R2_JURISDICTIONS:
        raise NamingError(
            f"unknown R2 jurisdiction {jurisdiction!r}; expected one of {R2_JURISDICTIONS}"
        )
    label = "" if jurisdiction == "default" else f"{jurisdiction}."
    return f"https://{account_id}.{label}r2.cloudflarestorage.com"


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
    #: The egress network the cluster reaches its backup repository over.
    #:
    #: Derived unconditionally, like every other network name, and attached to
    #: no service until Run 4 -- `storage_bucket` spent six sessions in exactly
    #: this state. `internal` is `internal: true` and has no route off the host
    #: (measured, D516), so `archive-push` cannot reach R2 from where the
    #: postmaster runs it; `edge` would work and is refused, because it is where
    #: Traefik's public side lives and the database has never been on it.
    backup_network: str
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
    #: The published path alone, for the router rule and for the boundary
    #: proof. Carried beside the URL because a label needs the path and a
    #: document reader needs the address, and slicing one out of the other at
    #: a call site is a second derivation of a value this module owns.
    route_mcp_path: str = ""
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
    #: Session 14's metrics surface (ADR 0164). URL and path carried as separate
    #: members for the reason `route_rest`/`route_rest_path` are: one is the
    #: address a reader is given, the other is what a router rule matches on,
    #: and D177 is what happened when the two were derived twice.
    #:
    #: There is no `metrics_stripprefix_middleware` beside these, and its
    #: absence is a decision rather than an omission: the collector's exporter
    #: serves `/metrics` and 404s on `/`, so the path the edge matches is the
    #: path the upstream wants and there is nothing to rewrite.
    route_metrics: str = ""
    route_metrics_path: str = ""
    metrics_router: str = ""
    metrics_credential_middleware: str = ""
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
    #: Session 7 Run 7's router and its three middlewares. Derived for every
    #: project whether or not storage is enabled, for the reason `route_storage`
    #: is: a rendered document names what a deployment would create, and the
    #: `storage` Compose service is held behind `profiles: [session7]` anyway.
    #:
    #: The strip and the buffering middleware are storage's own rather than
    #: shared with `app`'s, because a middleware defined by labels on another
    #: container is withdrawn with that container and disables the borrowing
    #: router (measured). The CORS middleware is a label rather than a
    #: file-provider document (ADR 0109).
    storage_router: str = ""
    mcp_router: str = ""
    storage_stripprefix_middleware: str = ""
    storage_buffering_middleware: str = ""
    storage_cors_middleware: str = ""

    jwt_issuer: str = ""
    jwt_audience: str = ""
    secrets_namespace: str = ""

    storage_bucket: str | None = None
    storage_prefix: str | None = None
    backup_stanza: str | None = None
    backup_repository_prefix: str | None = None
    #: The repository's bucket. `None` when backups are disabled, for the reason
    #: the stanza is: a rendered document must not name a repository for a
    #: facility that is off.
    backup_bucket: str | None = None

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
    backup_bucket: str | None = None,
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
        compose_project_name=compose_project_name(key),
        edge_network=compose_name(f"apg-{key}-edge", context="compose_network_edge"),
        internal_network=compose_name(f"apg-{key}-internal", context="compose_network_internal"),
        backup_network=backup_network_name(key),
        postgres_volume=postgres_volume_name(key),
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
        route_mcp_path=mcp_base_path,
        # The page, not the root above it (ADR 0061).
        route_docs=f"https://{domain}{DOCS_PAGE_PATH}",
        route_docs_path=DOCS_PAGE_PATH,
        route_app_docs=f"https://{domain}{DOCS_APP_PAGE_PATH}",
        route_app_docs_path=DOCS_APP_PAGE_PATH,
        # Reserved in Session 1, redeemed in Session 14 (ADR 0164). The path is
        # the whole route -- no root above it, nothing stripped below it.
        route_metrics=f"https://{domain}{METRICS_ROUTE_PATH}",
        route_metrics_path=METRICS_ROUTE_PATH,
        metrics_router=metrics_router_name(key),
        metrics_credential_middleware=metrics_credential_middleware_name(key),
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
        storage_router=storage_router_name(key),
        mcp_router=mcp_router_name(key),
        storage_stripprefix_middleware=storage_stripprefix_middleware_name(key),
        storage_buffering_middleware=storage_buffering_middleware_name(key),
        storage_cors_middleware=storage_cors_middleware_name(key),
        jwt_issuer=f"https://{domain}{api_base_path}{APP_PATH_SUFFIX}/auth",
        jwt_audience=f"urn:agentic-postgres:{slug}:{environment}",
        secrets_namespace=f"agentic-postgres/{key}",
        storage_bucket=(storage_bucket_name(key, storage_bucket) if storage_enabled else None),
        storage_prefix=(storage_object_prefix(key, storage_prefix) if storage_enabled else None),
        backup_stanza=((backup_stanza if backup_stanza else key) if backup_enabled else None),
        backup_repository_prefix=(
            (backup_repository_prefix if backup_repository_prefix else f"pgbackrest/{key}/")
            if backup_enabled
            else None
        ),
        backup_bucket=(backup_bucket_name(key, backup_bucket) if backup_enabled else None),
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
