"""Strict manifest loading, schema validation, and semantic validation.

Runbook §3.2-§3.6. Three layers, applied in order, each rejecting what the
next one would otherwise have to trust:

1. **Parse** — a YAML loader that refuses ambiguity outright: duplicate keys,
   multiple documents, merge keys, non-string keys, unknown tags, oversized
   input. Default PyYAML silently keeps the last value for a duplicate key,
   which turns a typo into a silent configuration change.
2. **Schema** — JSON Schema Draft 2020-12 with ``additionalProperties: false``
   at every level and format checking actually enabled, not annotation-only.
3. **Semantics** — the cross-field and domain rules JSON Schema cannot state.

This module owns the constants named in the implementation plan's decision
log: ``MAX_MANIFEST_BYTES`` (D), ``RESERVED_BASE_PATHS`` and ``paths_overlap``
(B), ``SENSITIVE_KEY_DENYLIST``/``SAFE_KEY_ALLOWLIST`` (F). Numeric bounds are
deliberately *not* here — ``schemas/project.schema.json`` is their sole
authority (E) — but the cross-field *relations* between them are, because JSON
Schema cannot express them.
"""

from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from agentic_postgres import REPO_ROOT

# ---------------------------------------------------------------------------
# Constants owned by the decision log
# ---------------------------------------------------------------------------

#: Plan decision D. Applied to raw file size before the file is read, so an
#: oversized input never reaches the parser. The fixtures are ~1 KiB.
MAX_MANIFEST_BYTES = 65_536

#: Manifest schema versions this build understands.
SUPPORTED_SCHEMA_VERSIONS = frozenset({1})

#: Plan decision B. `/docs` is derived unconditionally by runbook §3.8, so it
#: is structurally reserved; `/.well-known` is ACME, needed from Session 2;
#: health and metrics paths are OPS-001 surface; the rest are conventional
#: edge-router paths that would silently shadow a project route.
#:
#: Root is deliberately absent. Under the segment-prefix relation every path
#: is below `/`, so including it would reject all input; `/` is rejected by an
#: explicit equality check in ``_validate_base_path`` instead.
#:
#: `/__apg` was added in Session 2 (ADR 0015). It is the prefix of the platform
#: health route ``naming.HEALTH_ROUTE_PATH``, which the shared edge plane is
#: verified through, and the `public_base_path` pattern permits it — so
#: reserving it is the only thing stopping a project manifest from shadowing
#: the route the Session 2 gate depends on.
RESERVED_BASE_PATHS: tuple[str, ...] = (
    "/__apg",
    "/docs",
    "/health",
    "/healthz",
    "/ready",
    "/metrics",
    "/.well-known",
    "/traefik",
    "/static",
    "/favicon.ico",
    "/robots.txt",
)

#: Plan decision F. Matched as a whole key or as a terminal `_`-delimited
#: token — never as a substring. `token` and `secret` are safe to list only
#: because of that rule: `token_ttl_seconds` and `password_secret_ref` end in
#: `_seconds` and `_ref`, so neither matches.
SENSITIVE_KEY_DENYLIST: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "passphrase",
        "secret",
        "private_key",
        "access_key",
        "secret_access_key",
        "client_secret",
        "api_token",
        "refresh_token",
        "access_token",
        "session_key",
        "signing_key",
        "credentials",
        "token",
    }
)

#: Consulted before the denylist. Under terminal-token matching none of these
#: actually collides, which is the desired property: the allowlist is a guard
#: with a test behind it, not a load-bearing set of exceptions.
SAFE_KEY_ALLOWLIST: frozenset[str] = frozenset(
    {
        "password_secret_ref",
        "token_ttl_seconds",
        "token_use",
        "secret_ref",
    }
)

#: Relations between bounded fields. JSON Schema cannot express a comparison
#: between two properties, so these live in code — but as data, so the
#: generated documentation reads them rather than restating them (decision E).
CROSS_FIELD_RELATIONS: tuple[str, ...] = (
    "`database.pool_size` must not exceed `database.max_client_connections`",
    "`mcp.max_result_rows` must not exceed `api.max_rows`",
    "`api.public_base_path` and `mcp.public_base_path` must not overlap segment-wise",
    "Neither base path may overlap a reserved route",
    "`database.pooled_public` must be false and `database.pooled_public_cidrs` empty; "
    "a public pooler is not a supported profile (ADR 0040)",
    "`database.query_wait_timeout_seconds` must be less than "
    "`database.idle_transaction_timeout_seconds`",
    "`database.shm_size_mb` must be at least `database.shared_buffers_mb`",
    "`database.memory_limit_mb` must exceed the derived unreclaimable budget",
    "The derived unreclaimable budget must not exceed the per-project memory guardrail",
    "`api.rest.request_body_max_bytes` must equal `api.rest.request_body_memory_bytes`",
    "`api.rest.pool_max_idle_seconds` must be less than `api.rest.pool_max_lifetime_seconds`",
    "`api.rest.pool_size` plus its reserved connections, `database.pool_size`, and the "
    "administration reserve must fit `database.max_connections`",
    "`api.rest.allowed_cors_origins` must contain the project's own HTTPS origin when the "
    "REST service is enabled",
    "`api.rest.statement_timeouts` may name only roles the platform derives",
    "The derived REST prefix and the PostgREST documentation prefix must not overlap "
    "segment-wise, and neither may overlap the MCP prefix",
)

# ---------------------------------------------------------------------------
# The Session 3 memory budget (D52, plan §3.3)
# ---------------------------------------------------------------------------

#: Defaults for the manifest's database budget. Duplicated from
#: `schemas/project.schema.json` because JSON Schema `default` annotates, it does
#: not populate — a validator will happily accept a document without these keys
#: and hand it back unchanged. ADR 0007 keeps the *bounds* in the schema and this
#: is not a bound; `test_budget_defaults_match_the_schema` asserts the two
#: agree, so the duplication cannot drift silently.
DATABASE_BUDGET_DEFAULTS: dict[str, int] = {
    "shared_buffers_mb": 128,
    "max_connections": 50,
    "work_mem_mb": 4,
    "maintenance_work_mem_mb": 64,
    "memory_limit_mb": 768,
    "shm_size_mb": 256,
}

#: Defaults for the manifest's pool settings, duplicated from
#: `schemas/project.schema.json` for the same reason as the budget defaults
#: above: JSON Schema `default` annotates, it does not populate.
#: `test_pool_defaults_match_the_schema` asserts the two agree.
POOL_DEFAULTS: dict[str, int] = {
    "max_prepared_statements": 100,
    "query_wait_timeout_seconds": 20,
    "idle_transaction_timeout_seconds": 60,
    "server_lifetime_seconds": 3600,
}

#: Anonymous memory charged per backend, in MiB. Measured, not reasoned: two
#: clusters at the defaults held 62 MiB of anonymous memory across 49 backends,
#: which is ~1.3 MiB each. Charged at 2 so the guardrail is conservative in the
#: direction that costs a redeploy rather than an OOM kill.
#:
#: `work_mem` deliberately does not appear here. The obvious formula charges
#: `max_connections * work_mem`, which at the defaults would be 200 MiB per
#: cluster of memory that measurement says is never allocated: `work_mem` is a
#: per-sort-node ceiling, taken on demand and released, not a per-backend
#: reservation. Charging it would make the guardrail refuse configurations that
#: fit comfortably, and a guardrail that cries wolf gets raised.
PER_BACKEND_ANON_MB = 2

# ---------------------------------------------------------------------------
# The Session 5 REST service (plan §5 Run 2)
# ---------------------------------------------------------------------------

#: Defaults for `api.rest`, duplicated from `schemas/project.schema.json` for the
#: same reason as the budget and pool defaults above: JSON Schema `default`
#: annotates, it does not populate. `test_rest_defaults_match_the_schema` asserts
#: the two agree.
#:
#: `enabled` is `false`, and that is the load-bearing default. A project manifest
#: written before Session 5 declares no REST service, and the honest render for
#: one is a project that publishes no REST route -- not a project that quietly
#: acquires a public API because a schema had a default.
API_REST_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "request_body_max_bytes": 1048576,
    "request_body_memory_bytes": 1048576,
    "pool_size": 10,
    "pool_acquisition_timeout_seconds": 5,
    "pool_max_idle_seconds": 30,
    "pool_max_lifetime_seconds": 1800,
    "anonymous_access": "deny_data",
    # Empty, so a service that names no origins permits no cross-origin browser
    # request. Combined with the rule that an enabled service must name its own
    # origin, the only way to reach this default is to declare no REST service.
    "allowed_cors_origins": [],
}

#: What PostgREST takes out of the cluster's connection budget beyond its pool.
#:
#: One for the `LISTEN` connection the schema cache needs -- it is held for the
#: process's life and is not drawn from the pool -- and two for startup and
#: recovery, because a pool that is being re-established while the old
#: connections are still closing is briefly over its own size. Measured as a
#: reservation rather than reasoned from documentation: what matters is that the
#: number is charged at all, since the failure it prevents is a cluster refusing
#: connections to the pooler because the API took the last of them.
POSTGREST_RESERVED_CONNECTIONS = 3

#: Held back for migrations, backups, a direct developer session and PostgreSQL's
#: own `superuser_reserved_connections`. If this is exhausted, the operation that
#: cannot get a connection is the one that would have fixed the problem.
ADMINISTRATION_RESERVED_CONNECTIONS = 5

#: The documentation page's prefix, and the REST surface's suffix.
#:
#: **Read from `naming`, not restated here** (ADR 0061). Both were literals in
#: this file, the second one carrying a comment saying it was "kept in step
#: with `naming.derive`" — and the first one was not: `naming` derived
#: `routes.docs` as the `/docs` *root* while this said `/docs/rest`, so the
#: document every consumer reads a route from pointed one segment above the only
#: path Run 6 ever measured. `bin/docs.sh check` would have reported 404 rather
#: than 401, in the middle of Run 9's maintenance window.
#:
#: The manifest layer still must not import a URL to compare prefixes, which is
#: why these are paths and why the names stay. `naming` imports nothing from
#: this module, so the import is one-way.
from agentic_postgres.naming import (  # noqa: E402 — placed with the constants it defines
    DOCS_PAGE_PATH as DOCS_REST_PATH,
)
from agentic_postgres.naming import (  # noqa: E402
    REST_PATH_SUFFIX as REST_PATH_SUFFIX,
)


def postgrest_connection_budget(rest: dict[str, Any]) -> int:
    """How many cluster connections the REST service commits to.

    Its pool plus the reservations above. One function so there is one answer,
    which is ADR 0002's rule applied to a number instead of a name -- and so the
    figure a deployed document publishes is the figure the manifest was checked
    against, rather than a second sum that agrees today.
    """
    size = int(rest.get("pool_size", API_REST_DEFAULTS["pool_size"]))
    return size + POSTGREST_RESERVED_CONNECTIONS


#: What one host may commit to PostgreSQL clusters, in MiB, across every project
#: deployed on it. The host is 3814 MiB with no swap and roughly 681 MiB already
#: held by Traefik, the socket proxy and the project containers. This leaves
#: well over a gigabyte unspoken for, deliberately: with no swap the OOM killer
#: is the only backstop, and it does not choose politely — it can take Traefik,
#: which drops every project's ingress at once.
HOST_MEMORY_GUARDRAIL_MB = 1600


def unreclaimable_mb(budget: dict[str, int]) -> int:
    """What the host must actually find for this cluster, in MiB.

    Page cache is excluded because it is reclaimable, and on a no-swap box that
    is the only distinction that matters: the kernel will evict cache under
    pressure and will kill a process rather than evict shared memory. A figure
    that summed everything the container touches would be larger, more
    impressive, and useless for deciding whether a second cluster fits.
    """
    return (
        budget["shared_buffers_mb"]
        + budget["maintenance_work_mem_mb"]
        + budget["max_connections"] * PER_BACKEND_ANON_MB
    )


def database_budget(database: dict[str, Any]) -> dict[str, int]:
    """Resolve the manifest's budget against the defaults, and derive the total.

    Returns a new mapping; the manifest is not mutated. The derived member is
    computed here rather than at every call site so there is one answer to
    "how much does this cluster cost", which is the whole point of ADR 0002
    applied to a number instead of a name.
    """
    resolved = {
        key: int(database.get(key, default)) for key, default in DATABASE_BUDGET_DEFAULTS.items()
    }
    resolved["unreclaimable_mb"] = unreclaimable_mb(resolved)
    return resolved


#: Plan decision X. pgBackRest stanza names: lowercase alphanumeric plus `-`
#: and `_`, starting alphanumeric, at most 63 characters. No whitespace and no
#: path separator, so a stanza can never escape its repository prefix.
_BACKUP_STANZA = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")

_SLUG = re.compile(r"^[a-z][a-z0-9-]{2,30}$")
_ENVIRONMENT = re.compile(r"^[a-z][a-z0-9-]{1,15}$")
_POSTGRES_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
_R2_BUCKET = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
_DNS_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

_SCHEMA_DIR = REPO_ROOT / "schemas"


class ManifestError(ValueError):
    """A manifest is unparseable, schema-invalid, or semantically invalid."""


class CapabilityContractError(ManifestError):
    """A capability claims a backing API contract that cannot be verified.

    Distinct from :class:`ManifestError` because the CLI maps it to exit 5
    (contract failure) rather than exit 2 (invalid operator input): the
    manifest is well formed, it just asserts something untrue.
    """


# ---------------------------------------------------------------------------
# Layer 1 — strict parsing
# ---------------------------------------------------------------------------


class StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses every ambiguity runbook §3.2 lists."""


def _construct_strict_mapping(loader: StrictLoader, node: yaml.MappingNode) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for key_node, value_node in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            raise ManifestError(
                f"YAML merge keys are not allowed (line {key_node.start_mark.line + 1}): "
                "a merged mapping hides where a value came from"
            )
        if key_node.tag != "tag:yaml.org,2002:str":
            raise ManifestError(
                f"mapping keys must be strings, got {key_node.tag!r} "
                f"at line {key_node.start_mark.line + 1}"
            )

        key = loader.construct_object(key_node, deep=True)
        if key in mapping:
            raise ManifestError(
                f"duplicate mapping key {key!r} at line {key_node.start_mark.line + 1}: "
                "the default YAML behaviour of keeping the last value would make "
                "this a silent configuration change"
            )
        mapping[key] = loader.construct_object(value_node, deep=True)
    return mapping


StrictLoader.add_constructor("tag:yaml.org,2002:map", _construct_strict_mapping)


def load_manifest(path: Path) -> dict[str, Any]:
    """Parse one YAML manifest strictly. Raises :class:`ManifestError`."""
    if not path.is_file():
        raise ManifestError(f"manifest is not a file: {path}")
    if path.is_symlink():
        raise ManifestError(f"manifest is a symlink, which is not accepted: {path}")

    size = path.stat().st_size
    if size > MAX_MANIFEST_BYTES:
        raise ManifestError(
            f"manifest is {size} bytes, above the {MAX_MANIFEST_BYTES} byte limit: {path}"
        )

    text = path.read_text(encoding="utf-8")

    try:
        documents = list(yaml.load_all(text, Loader=StrictLoader))
    except ManifestError:
        raise
    except yaml.YAMLError as exc:
        raise ManifestError(f"{path}: {exc}") from exc

    if len(documents) != 1:
        raise ManifestError(f"{path}: expected exactly one YAML document, found {len(documents)}")
    document = documents[0]
    if not isinstance(document, dict):
        raise ManifestError(f"{path}: top level must be a mapping, got {type(document).__name__}")
    return document


# ---------------------------------------------------------------------------
# Secret-key defense (plan decision F)
# ---------------------------------------------------------------------------


def is_sensitive_key(key: str) -> bool:
    """Whole-key or terminal-token match against the denylist. Never substring."""
    lowered = key.lower()
    if lowered in SAFE_KEY_ALLOWLIST:
        return False
    if lowered in SENSITIVE_KEY_DENYLIST:
        return True
    return any(lowered.endswith(f"_{denied}") for denied in SENSITIVE_KEY_DENYLIST)


def assert_no_sensitive_keys(document: Any, *, path: str = "") -> None:
    """Recursively reject secret-bearing keys at any depth (runbook §3.6)."""
    if isinstance(document, dict):
        for key, value in document.items():
            where = f"{path}.{key}" if path else str(key)
            if isinstance(key, str) and is_sensitive_key(key):
                raise ManifestError(
                    f"manifest key {where!r} looks like secret material; "
                    "manifests are non-secret by contract"
                )
            assert_no_sensitive_keys(value, path=where)
    elif isinstance(document, list):
        for index, value in enumerate(document):
            assert_no_sensitive_keys(value, path=f"{path}[{index}]")


# ---------------------------------------------------------------------------
# Layer 2 — JSON Schema
# ---------------------------------------------------------------------------


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((_SCHEMA_DIR / name).read_text(encoding="utf-8"))


def validate_against_schema(document: dict[str, Any], schema_name: str) -> None:
    """Validate with format checking genuinely enabled (runbook §3.3)."""
    validator = Draft202012Validator(
        load_schema(schema_name),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    errors = sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path))
    if errors:
        rendered = "; ".join(
            f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors
        )
        raise ManifestError(f"{schema_name}: {rendered}")


def bounds_table(schema_name: str = "project.schema.json") -> list[dict[str, Any]]:
    """Extract every numeric bound from the schema (plan decision E).

    The schema is the sole authority. This exists so documentation can be
    generated from it rather than restating it.

    Local ``$ref``s are followed, and that is not a refinement. Session 5 put
    the REST service in ``$defs`` and referenced it from ``api.rest``; a walk
    that stopped at the reference would have generated a bounds table missing
    eight fields, and the table would still have looked complete -- which is the
    failure mode ADR 0007 exists to prevent, arriving through the generator
    rather than through the schema.
    """
    schema = load_schema(schema_name)
    rows: list[dict[str, Any]] = []

    def resolve(
        node: dict[str, Any], seen: frozenset[str]
    ) -> tuple[dict[str, Any], frozenset[str]]:
        reference = node.get("$ref")
        if not isinstance(reference, str) or not reference.startswith("#/$defs/"):
            return node, seen
        name = reference.removeprefix("#/$defs/")
        if name in seen:
            # A self-referential definition would otherwise walk forever. There
            # is none today; refusing to follow one twice is cheaper than
            # discovering there is by hanging the documentation build.
            return {}, seen
        return schema.get("$defs", {}).get(name, {}), seen | {name}

    def walk(node: dict[str, Any], pointer: str, seen: frozenset[str]) -> None:
        for key, value in node.get("properties", {}).items():
            child = f"{pointer}.{key}" if pointer else key
            if not isinstance(value, dict):
                continue
            resolved, child_seen = resolve(value, seen)
            if "minimum" in resolved or "maximum" in resolved:
                rows.append(
                    {
                        "field": child,
                        "minimum": resolved.get("minimum"),
                        "maximum": resolved.get("maximum"),
                        "description": resolved.get("description", ""),
                    }
                )
            walk(resolved, child, child_seen)

    walk(schema, "", frozenset())
    return sorted(rows, key=lambda row: row["field"])


# ---------------------------------------------------------------------------
# Route paths (plan decision B)
# ---------------------------------------------------------------------------


def path_segments(base_path: str) -> tuple[str, ...]:
    return tuple(segment for segment in base_path.split("/") if segment)


def paths_overlap(left: str, right: str) -> bool:
    """True when one path's segment tuple is a prefix of the other's.

    Segment-wise, so `/api` and `/apiv2` do not overlap. A naive
    ``str.startswith`` would wrongly reject that pair, and would also miss
    that `/api` and `/api/v1` genuinely conflict.
    """
    a, b = path_segments(left), path_segments(right)
    if not a or not b:
        # Root has no segments, so it is a prefix of everything. That is
        # mathematically true and operationally useless, so callers comparing
        # against reserved routes must handle root separately.
        return False
    shortest = min(len(a), len(b))
    return a[:shortest] == b[:shortest]


def _validate_base_path(value: str, *, field: str) -> None:
    if not value.isascii():
        raise ManifestError(f"{field} must be ASCII: {value!r}")
    if not value.startswith("/"):
        raise ManifestError(f"{field} must begin with '/': {value!r}")
    if value == "/":
        raise ManifestError(f"{field} must not be '/'")
    if value.endswith("/"):
        raise ManifestError(f"{field} must not end with '/': {value!r}")
    if "//" in value:
        raise ManifestError(f"{field} must not contain '//': {value!r}")
    for segment in path_segments(value):
        if segment in (".", ".."):
            raise ManifestError(f"{field} must not contain '.' or '..' segments: {value!r}")

    for reserved in RESERVED_BASE_PATHS:
        if paths_overlap(value, reserved):
            raise ManifestError(f"{field} {value!r} collides with the reserved route {reserved!r}")


def _validate_domain(value: str) -> None:
    if not value.isascii():
        raise ManifestError(f"domain must be ASCII or punycode: {value!r}")
    if value != value.lower():
        raise ManifestError(f"domain must be lowercase: {value!r}")
    if "://" in value or ":" in value:
        raise ManifestError(f"domain must not contain a scheme or port: {value!r}")
    if "/" in value:
        raise ManifestError(f"domain must not contain a path: {value!r}")
    if "*" in value:
        raise ManifestError(f"domain must not be a wildcard: {value!r}")
    if value.endswith("."):
        raise ManifestError(f"domain must not have a trailing dot: {value!r}")
    if len(value) > 253:
        raise ManifestError(f"domain exceeds 253 characters: {value!r}")

    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise ManifestError(f"domain must be a name, not an IP literal: {value!r}")

    labels = value.split(".")
    if len(labels) < 2:
        raise ManifestError(f"domain must have at least two labels: {value!r}")
    for label in labels:
        if not 1 <= len(label) <= 63:
            raise ManifestError(f"domain label must be 1-63 characters: {label!r}")
        if not _DNS_LABEL.match(label):
            raise ManifestError(f"invalid domain label: {label!r}")


def _validate_prefix(value: str, *, field: str) -> None:
    if value.startswith("/"):
        raise ManifestError(f"{field} must be relative: {value!r}")
    if not value.endswith("/"):
        raise ManifestError(f"{field} must end with '/': {value!r}")
    if ".." in Path(value).parts:
        raise ManifestError(f"{field} must not contain a '..' segment: {value!r}")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ManifestError(f"{field} must not contain control characters: {value!r}")


# ---------------------------------------------------------------------------
# Layer 3 — semantic validation
# ---------------------------------------------------------------------------


def validate_project_semantics(document: dict[str, Any]) -> None:
    """Apply every rule of runbook §3.4 that JSON Schema cannot express."""
    version = document.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ManifestError(
            f"unsupported schema_version {version!r}; "
            f"supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )

    project = document["project"]
    if not _SLUG.match(project["slug"]):
        raise ManifestError(f"invalid project.slug: {project['slug']!r}")
    if not _ENVIRONMENT.match(project["environment"]):
        raise ManifestError(f"invalid project.environment: {project['environment']!r}")
    _validate_domain(project["domain"])

    api = document["api"]
    mcp = document["mcp"]
    _validate_base_path(api["public_base_path"], field="api.public_base_path")
    _validate_base_path(mcp["public_base_path"], field="mcp.public_base_path")

    if paths_overlap(api["public_base_path"], mcp["public_base_path"]):
        raise ManifestError(
            f"api.public_base_path {api['public_base_path']!r} and "
            f"mcp.public_base_path {mcp['public_base_path']!r} overlap ambiguously; "
            "one route tree is a prefix of the other"
        )

    database = document["database"]
    if database["pool_size"] > database["max_client_connections"]:
        raise ManifestError(
            f"database.pool_size ({database['pool_size']}) must not exceed "
            f"database.max_client_connections ({database['max_client_connections']})"
        )
    if mcp["max_result_rows"] > api["max_rows"]:
        raise ManifestError(
            f"mcp.max_result_rows ({mcp['max_result_rows']}) must not exceed "
            f"api.max_rows ({api['max_rows']})"
        )

    name = database.get("name")
    if name is not None:
        if not _POSTGRES_IDENTIFIER.match(name):
            raise ManifestError(f"database.name is not a bare lowercase identifier: {name!r}")
        if len(name.encode("utf-8")) > 63:
            raise ManifestError(f"database.name exceeds 63 bytes: {name!r}")

    _validate_pooled_public(database)
    _validate_pool(database)
    _validate_memory_budget(database)
    _validate_rest_service(api, database=database, domain=project["domain"])
    _validate_route_boundaries(api, mcp)
    _validate_storage(document.get("storage", {}))
    _validate_backup(document.get("backup", {}))


def _validate_memory_budget(database: dict[str, Any]) -> None:
    """The three relations JSON Schema cannot express (D52, plan §3.3).

    All three refuse at render time, with no host involved, which is the only
    point at which refusing is cheap: the alternative is an operator finding out
    from a killed container which, with no swap, may not even be this one.
    """
    budget = database_budget(database)
    required = budget["unreclaimable_mb"]

    if budget["shm_size_mb"] < budget["shared_buffers_mb"]:
        raise ManifestError(
            f"database.shm_size_mb ({budget['shm_size_mb']}) is below "
            f"database.shared_buffers_mb ({budget['shared_buffers_mb']}); "
            "PostgreSQL's dynamic shared memory lands in /dev/shm, and a parallel "
            "query that cannot allocate there fails at run time, not at start"
        )

    if budget["memory_limit_mb"] <= required:
        raise ManifestError(
            f"database.memory_limit_mb ({budget['memory_limit_mb']}) does not exceed the "
            f"unreclaimable budget ({required} MiB). A container limit caps page cache "
            "as well as anonymous memory, so a limit set at the budget leaves the cluster "
            "in permanent cache reclaim: it will run, and it will never report why it is slow"
        )

    if required > HOST_MEMORY_GUARDRAIL_MB:
        raise ManifestError(
            f"the derived unreclaimable budget ({required} MiB) exceeds the per-host "
            f"guardrail ({HOST_MEMORY_GUARDRAIL_MB} MiB). Reduce shared_buffers_mb, "
            "maintenance_work_mem_mb or max_connections; do not raise the guardrail to "
            "match a manifest, because the host has no swap and nothing below it to give"
        )


#: The refusal `pooled_public: true` gets. A constant because it is a contract:
#: an operator reads it, a test matches it, and the operator guide quotes it.
#: An error message that drifts is an error message somebody has to re-learn.
UNSUPPORTED_PUBLIC_POOL = (
    "database.pooled_public is not a supported profile (ADR 0040). The pooler is "
    "reachable on a host-loopback publication and through a verified tunnel, and "
    "on no other path. There is no allowlist that makes a public bind supported, "
    "so this is refused rather than narrowed. Use bin/connect.sh."
)


def _validate_pooled_public(database: dict[str, Any]) -> None:
    """Fail closed on the one configuration Session 4 removed.

    Through Session 3 this accepted `pooled_public: true` with a non-empty CIDR
    allowlist and validated the CIDRs. ADR 0040 draws the boundary at loopback
    instead, and an allowlisted public bind is on the wrong side of it. Note
    which direction that moved: everything this function used to accept, it now
    refuses, and it accepts nothing it did not accept before.

    The CIDR parsing is gone with the configuration it validated. Keeping it
    would leave code that carefully checks the shape of a value nothing may set.
    """
    cidrs = database.get("pooled_public_cidrs") or []

    if database.get("pooled_public"):
        raise ManifestError(UNSUPPORTED_PUBLIC_POOL)

    if cidrs:
        raise ManifestError(
            "database.pooled_public_cidrs must be empty: no non-loopback source "
            "reaches the pooler directly (ADR 0040)"
        )


def _validate_pool(database: dict[str, Any]) -> None:
    """The pool relations JSON Schema cannot express.

    `max_prepared_statements` has its floor in the schema, where ADR 0007 says a
    bound belongs. What is here is the relation the schema cannot state: the
    queue timeout must be shorter than the idle-transaction timeout, because a
    client that waits longer for a connection than a stuck transaction is
    allowed to hold one turns a bounded failure into an unbounded one.
    """
    query_wait = database.get(
        "query_wait_timeout_seconds", POOL_DEFAULTS["query_wait_timeout_seconds"]
    )
    idle_transaction = database.get(
        "idle_transaction_timeout_seconds", POOL_DEFAULTS["idle_transaction_timeout_seconds"]
    )

    if query_wait >= idle_transaction:
        raise ManifestError(
            f"database.query_wait_timeout_seconds ({query_wait}) must be less than "
            f"database.idle_transaction_timeout_seconds ({idle_transaction}). A client "
            "that is allowed to wait for a server connection longer than a stuck "
            "transaction is allowed to hold one will queue behind it rather than fail, "
            "and a queue with no error at the end of it is a hang"
        )


def _validate_rest_service(api: dict[str, Any], *, database: dict[str, Any], domain: str) -> None:
    """The `api.rest` relations JSON Schema cannot express (Session 5, Run 2).

    Bounds are in the schema, where ADR 0007 says a bound belongs. What is here
    is every rule that compares two fields, and one that compares a field against
    a derivation.

    An absent section is not an error and not a default-filled service: it is a
    project that does not serve REST. Everything below is skipped for it, which
    is why the first check is the one that returns.
    """
    rest = api.get("rest")
    if rest is None:
        return

    resolved = {**API_REST_DEFAULTS, **rest}

    if not resolved["enabled"]:
        # A disabled service still has its numbers checked. A manifest that
        # carries an unusable configuration behind `enabled: false` is a
        # manifest that fails on the day somebody flips one boolean, which is
        # the worst possible day to find out.
        _validate_rest_numbers(resolved)
        return

    _validate_rest_numbers(resolved)

    budget = postgrest_connection_budget(resolved)
    committed = budget + database["pool_size"] + ADMINISTRATION_RESERVED_CONNECTIONS
    ceiling = int(database.get("max_connections", DATABASE_BUDGET_DEFAULTS["max_connections"]))
    if committed > ceiling:
        raise ManifestError(
            f"the connection budget does not fit: api.rest.pool_size "
            f"({resolved['pool_size']}) plus {POSTGREST_RESERVED_CONNECTIONS} reserved, "
            f"database.pool_size ({database['pool_size']}), and "
            f"{ADMINISTRATION_RESERVED_CONNECTIONS} held for administration come to "
            f"{committed}, above database.max_connections ({ceiling}). The connection "
            "that cannot be opened is the pooler's or the migration's, and neither "
            "reports the reason as a capacity problem"
        )

    origin = f"https://{domain}"
    if origin not in resolved.get("allowed_cors_origins", []):
        raise ManifestError(
            f"api.rest.allowed_cors_origins does not contain {origin!r}. The "
            "documentation page this session publishes issues its requests from the "
            "project's own origin, so a list that omits it disables the page it was "
            "written for and reports it as a browser error"
        )

    _validate_statement_timeouts(resolved.get("statement_timeouts", {}))


def _validate_rest_numbers(rest: dict[str, Any]) -> None:
    """The two comparisons between REST fields, checked enabled or not."""
    if rest["request_body_max_bytes"] != rest["request_body_memory_bytes"]:
        raise ManifestError(
            f"api.rest.request_body_max_bytes ({rest['request_body_max_bytes']}) must "
            f"equal api.rest.request_body_memory_bytes "
            f"({rest['request_body_memory_bytes']}). A memory limit below the accepted "
            "size is how a request body reaches the proxy's disk, where nothing is "
            "auditing it and nothing is deleting it on a schedule"
        )

    if rest["pool_max_idle_seconds"] >= rest["pool_max_lifetime_seconds"]:
        raise ManifestError(
            f"api.rest.pool_max_idle_seconds ({rest['pool_max_idle_seconds']}) must be "
            f"less than api.rest.pool_max_lifetime_seconds "
            f"({rest['pool_max_lifetime_seconds']}). An idle timeout at or above the "
            "lifetime never fires, so the setting reads as configured and does nothing"
        )


#: Bounds on a parsed statement timeout, in milliseconds. Below the floor a
#: legitimate query fails and the repair is to raise the timeout, which is how a
#: timeout becomes decorative; above the ceiling a single statement can hold a
#: connection out of a bounded pool for longer than the pool tolerates.
STATEMENT_TIMEOUT_MS = (100, 60_000)


def _validate_statement_timeouts(timeouts: dict[str, Any]) -> None:
    """Bounded durations, on roles that exist.

    The second half is the one worth having. A timeout set on a role nothing
    derives is applied to nothing, reports nothing, and reads in the manifest
    exactly like one that works -- so the role names are checked against
    ``naming.ROLE_SUFFIXES`` rather than against a list written here, which would
    keep agreeing with itself after the roles changed.
    """
    from agentic_postgres import naming

    unknown = sorted(set(timeouts) - set(naming.ROLE_SUFFIXES))
    if unknown:
        raise ManifestError(
            f"api.rest.statement_timeouts names {unknown}, which the platform does not "
            f"derive. Known roles: {sorted(naming.ROLE_SUFFIXES)}. A timeout on a role "
            "that does not exist is applied to nothing and says so nowhere"
        )

    floor, ceiling = STATEMENT_TIMEOUT_MS
    for role, value in timeouts.items():
        milliseconds = int(value[:-2]) if value.endswith("ms") else int(value[:-1]) * 1000
        if not floor <= milliseconds <= ceiling:
            raise ManifestError(
                f"api.rest.statement_timeouts.{role} is {value!r} ({milliseconds} ms), "
                f"outside {floor}-{ceiling} ms"
            )


def _validate_route_boundaries(api: dict[str, Any], mcp: dict[str, Any]) -> None:
    """The three published prefixes, proved pairwise distinct (ADR 0005).

    Session 5 publishes two more routes under prefixes it does not choose: the
    REST surface at ``{api.public_base_path}/rest`` and its documentation at
    ``/docs/rest``. Both are derived, so neither can be got wrong by a manifest
    directly -- which is exactly why this is checked rather than assumed. The
    manifest chooses ``api.public_base_path`` and ``mcp.public_base_path``, and a
    pair such as ``/api`` and ``/api/rest`` would make one route's tree a prefix
    of another's without either field looking wrong on its own.

    ``/docs`` is already reserved and ``paths_overlap`` already refuses a base
    path that collides with a reserved route, so the docs prefix cannot collide
    with a manifest's choice today. It is compared anyway: the reserved list is a
    tuple somebody can edit, and this states the consequence of editing it.
    """
    rest_prefix = f"{api['public_base_path']}{REST_PATH_SUFFIX}"
    pairs = (
        ("the REST prefix", rest_prefix, "the MCP prefix", mcp["public_base_path"]),
        ("the REST prefix", rest_prefix, "the documentation prefix", DOCS_REST_PATH),
        (
            "the documentation prefix",
            DOCS_REST_PATH,
            "the MCP prefix",
            mcp["public_base_path"],
        ),
    )
    for left_name, left, right_name, right in pairs:
        if paths_overlap(left, right):
            raise ManifestError(
                f"{left_name} {left!r} and {right_name} {right!r} overlap segment-wise; "
                "one route tree is a prefix of the other, and the edge would answer "
                "whichever router matched first"
            )


def _validate_storage(storage: dict[str, Any]) -> None:
    enabled = storage.get("enabled", False)
    bucket = storage.get("bucket")
    prefix = storage.get("prefix")

    if not enabled:
        if bucket is not None or prefix is not None:
            raise ManifestError(
                "storage is disabled, so storage.bucket and storage.prefix must be absent or null"
            )
        return

    if bucket is not None:
        if not 3 <= len(bucket) <= 63:
            raise ManifestError(f"storage.bucket must be 3-63 characters: {bucket!r}")
        if not _R2_BUCKET.match(bucket):
            raise ManifestError(f"invalid R2 bucket name: {bucket!r}")
    if prefix is not None:
        _validate_prefix(prefix, field="storage.prefix")


def _validate_backup(backup: dict[str, Any]) -> None:
    enabled = backup.get("enabled", False)
    stanza = backup.get("stanza")
    repository_prefix = backup.get("repository_prefix")

    if not enabled:
        if stanza is not None or repository_prefix is not None:
            raise ManifestError(
                "backup is disabled, so backup.stanza and backup.repository_prefix "
                "must be absent or null"
            )
        return

    if stanza is not None and not _BACKUP_STANZA.match(stanza):
        raise ManifestError(
            f"invalid backup.stanza: {stanza!r}; expected lowercase alphanumeric "
            "with '-' or '_', starting alphanumeric, at most 63 characters"
        )
    if repository_prefix is not None:
        _validate_prefix(repository_prefix, field="backup.repository_prefix")


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def load_project_manifest(path: Path) -> dict[str, Any]:
    """Parse, schema-check, secret-check, and semantically validate a project."""
    document = load_manifest(path)
    assert_no_sensitive_keys(document)
    validate_against_schema(document, "project.schema.json")
    validate_project_semantics(document)
    return document


def load_capabilities_manifest(path: Path) -> dict[str, Any]:
    """Parse and validate a capability manifest (runbook §5)."""
    document = load_manifest(path)
    assert_no_sensitive_keys(document)
    validate_against_schema(document, "capabilities.schema.json")

    version = document.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ManifestError(f"unsupported schema_version {version!r}")

    capabilities = document.get("capabilities") or []
    names = [entry["name"] for entry in capabilities]
    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        raise ManifestError(f"duplicate capability names: {sorted(duplicates)}")

    for entry in capabilities:
        if entry.get("enabled"):
            raise CapabilityContractError(
                f"capability {entry['name']!r} is enabled, but no live API contract "
                "exists to validate it against in this session"
            )

    return document
