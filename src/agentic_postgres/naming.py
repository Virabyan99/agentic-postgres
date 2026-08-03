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

# --------------------------------------------------------------------------
# Output validators (runbook §3.7 rule 4: context-specific validator + maximum)
# --------------------------------------------------------------------------

_POSTGRES_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
_R2_BUCKET = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
_COMPOSE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

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

    database_name: str
    roles: dict[str, str] = field(default_factory=dict)

    route_rest: str = ""
    route_app: str = ""
    route_mcp: str = ""
    route_docs: str = ""

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
        database_name=postgres_identifier(
            database_name if database_name else key_sql, context="postgres_database"
        ),
        roles=database_roles(key_sql),
        route_rest=f"https://{domain}{api_base_path}/rest",
        route_app=f"https://{domain}{api_base_path}/app",
        route_mcp=f"https://{domain}{mcp_base_path}",
        route_docs=f"https://{domain}/docs",
        jwt_issuer=f"https://{domain}{api_base_path}/app/auth",
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
