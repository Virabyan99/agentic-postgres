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
from ipaddress import ip_network
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
RESERVED_BASE_PATHS: tuple[str, ...] = (
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
    "`database.pooled_public_cidrs` must be non-empty when `database.pooled_public` is true, "
    "and may not contain a default route",
)

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
    """
    rows: list[dict[str, Any]] = []

    def walk(node: Any, pointer: str) -> None:
        if not isinstance(node, dict):
            return
        for key, value in node.get("properties", {}).items():
            child = f"{pointer}.{key}" if pointer else key
            if isinstance(value, dict) and ("minimum" in value or "maximum" in value):
                rows.append(
                    {
                        "field": child,
                        "minimum": value.get("minimum"),
                        "maximum": value.get("maximum"),
                        "description": value.get("description", ""),
                    }
                )
            walk(value, child)

    walk(load_schema(schema_name), "")
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
    _validate_storage(document.get("storage", {}))
    _validate_backup(document.get("backup", {}))


def _validate_pooled_public(database: dict[str, Any]) -> None:
    cidrs = database.get("pooled_public_cidrs") or []
    if not database.get("pooled_public"):
        if cidrs:
            raise ManifestError(
                "database.pooled_public_cidrs must be empty when pooled_public is false"
            )
        return

    if not cidrs:
        raise ManifestError(
            "database.pooled_public is true, so pooled_public_cidrs must be non-empty; "
            "exposing the pooler to an unstated audience is not a default"
        )

    for entry in cidrs:
        try:
            network = ip_network(entry, strict=True)
        except ValueError as exc:
            raise ManifestError(f"invalid CIDR in pooled_public_cidrs: {entry!r} ({exc})") from exc
        if network.prefixlen == 0:
            raise ManifestError(
                f"pooled_public_cidrs may not contain a default route: {entry!r}; "
                "an allowlist that allows everything is not an allowlist"
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
