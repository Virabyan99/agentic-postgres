"""Transactional rendering of generated project outputs.

Runbook §4.1. The ordering is the contract: validate everything, stage into a
private directory, validate the staged result, and only then publish. A render
that fails validation must never be able to replace a render that passed,
because otherwise the recovery path from a bad manifest is "restore from
memory".

Publication is a **directory swap**, not a sequence of per-file renames (plan
decision J). Three independent ``os.replace`` calls leave two windows in which
the published directory holds a mixed set, and no way back once the second
succeeds and the third fails. Renaming the whole directory aside, renaming the
new one into place, and renaming the old one back on failure is a real
rollback. Every file additionally records the same input hashes, so a torn set
is still detectable if the process dies between the two renames.
"""

from __future__ import annotations

import fcntl
import os
import re
import secrets
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Any

from agentic_postgres import REPO_ROOT, config, naming, secrets_contract, template_version

#: The session whose planned surface a render describes. Rendering is a
#: planning operation, so this bounds which declared secrets appear in
#: ``secrets.required_names`` — not which are materialized, which is a
#: deployment concern and lives in the ``deployed`` document.
RENDER_SESSION = 2

#: The declared grant surface. A repository-level file, like ``versions.env``:
#: it is not per-project, and it is digested into ``inputs`` so the render
#: cannot depend on it invisibly.
SECRET_CONTRACT_PATH = REPO_ROOT / "secrets.required.yaml"

#: Owner-only. Runbook §4.2 and §9 check 5 make this a tested contract, not a
#: nicety: rendered output names every role and authority in the project.
FILE_MODE = 0o600
DIRECTORY_MODE = 0o700

GENERATED_ROOT = REPO_ROOT / ".generated"
STAGING_ROOT = GENERATED_ROOT / ".staging"
LOCK_ROOT = GENERATED_ROOT / ".locks"

#: A value permitted under a ``*_secret_ref`` key: a namespace path, never a
#: credential. Session 1 emits only ``null``.
_SECRET_REFERENCE = re.compile(r"^[a-z0-9][a-z0-9/_-]{2,127}$")

#: `scheme://user:password@host` — a credential-bearing URL.
_CREDENTIAL_URL = re.compile(r"[a-z][a-z0-9+.-]*://[^/@\s]*:[^/@\s]*@")

#: Presigned-URL signatures, which must never reach a rendered file or a log.
_PRESIGNED = re.compile(r"(X-Amz-Signature|X-Amz-Credential|[?&]Signature=)", re.IGNORECASE)


class RenderError(RuntimeError):
    """Rendering could not complete. The previous valid render is untouched."""


# ---------------------------------------------------------------------------
# Input digests
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise RenderError(f"required input is missing: {path}")
    return sha256(path.read_bytes()).hexdigest()


def input_digests(project_path: Path, capabilities_path: Path) -> dict[str, str]:
    """Digest every input that determines the render.

    All five are recorded in each generated file so that an incomplete set is
    detectable (runbook §4.1).

    ``secrets_contract_sha256`` joined the set in Session 2, when
    ``secrets.required_names`` started reaching rendered output. The rule is
    that this block names *every* file the render depends on: a value derived
    from an undigested file would make two renders differ with no visible
    reason, which is the precise failure the digest block exists to expose.
    """
    return {
        "project_sha256": sha256_file(project_path),
        "capabilities_sha256": sha256_file(capabilities_path),
        "secrets_contract_sha256": sha256_file(SECRET_CONTRACT_PATH),
        "versions_lock_sha256": sha256_file(REPO_ROOT / "versions.env"),
        "source_specification_sha256": sha256_file(REPO_ROOT / "docs" / "source-specification.md"),
    }


# ---------------------------------------------------------------------------
# Document construction
# ---------------------------------------------------------------------------


def build_outputs(
    project: dict[str, Any],
    capabilities: dict[str, Any],
    identity: naming.ProjectIdentity,
    digests: dict[str, str],
) -> dict[str, Any]:
    """Assemble ``outputs.json``.

    Note what is deliberately absent: any timestamp (plan decision U), and any
    endpoint metadata that does not exist yet. Session 1 has no tunnel host, no
    bound port, and no provisioned credential, so the endpoint fields are null
    with an explicit ``unavailable`` status rather than a placeholder string
    that would eventually be pasted into a connection dialog.
    """
    storage_enabled = bool(project.get("storage", {}).get("enabled", False))
    backup_enabled = bool(project.get("backup", {}).get("enabled", False))

    unavailable_endpoint = {
        "status": "unavailable",
        "available_from_session": 4,
        "host": None,
        "port": None,
        "url": None,
        "password_secret_ref": None,
    }

    # Three profiles over two transports (ADR 0041). `transport` and `role` are
    # written from the first render because both are derivations this function
    # already holds -- the transport is fixed by the profile's name, the role
    # comes from `naming`. `password_secret_ref` stays null until a secret by
    # that name has actually been declared, and `status` stays `unavailable`
    # until a role has been activated and a transport published. Writing a
    # secret reference here now would name something that does not exist, which
    # is the failure this repository keeps producing in other clothes.
    access_profiles = {
        "runtime_pooled": {
            "status": "unavailable",
            "available_from_session": 4,
            "transport": "pooled",
            "role": identity.roles["app_runtime"],
            "password_secret_ref": None,
        },
        "runtime_direct": {
            "status": "unavailable",
            "available_from_session": 4,
            "transport": "direct",
            "role": identity.roles["app_runtime"],
            "password_secret_ref": None,
        },
        "migration_direct": {
            "status": "unavailable",
            "available_from_session": 4,
            "transport": "direct",
            "role": identity.roles["migration_user"],
            "password_secret_ref": None,
        },
    }

    required_secret_names = sorted(
        secret["name"]
        for secret in secrets_contract.active_secrets(
            secrets_contract.load_secret_contract(SECRET_CONTRACT_PATH), RENDER_SESSION
        )
    )

    return {
        "schema_version": 4,
        "document_kind": "rendered",
        "inputs": dict(digests),
        "project": {
            "slug": identity.slug,
            "environment": identity.environment,
            "key": identity.key,
            "domain": identity.domain,
            "generated_directory": identity.generated_directory,
        },
        "compose": {
            "project_name": identity.compose_project_name,
            "networks": {
                "edge": identity.edge_network,
                "internal": identity.internal_network,
            },
            "volumes": {"postgres": identity.postgres_volume},
        },
        "database": {
            "name": identity.database_name,
            "container": identity.postgres_container,
            "roles": dict(identity.roles),
            # Resolved against the schema's defaults and totalled in one place
            # (config.database_budget). No `observed` member: a rendered
            # document has measured nothing, and on this branch the schema
            # makes the field unrepresentable rather than merely null.
            "budget": config.database_budget(project["database"]),
            "pooled": dict(unavailable_endpoint),
            "direct": dict(unavailable_endpoint),
            "access_profiles": {name: dict(profile) for name, profile in access_profiles.items()},
        },
        "routes": {
            "rest": identity.route_rest,
            "app": identity.route_app,
            "mcp": identity.route_mcp,
            "docs": identity.route_docs,
            # `planned`, unconditionally. A rendered document describes what a
            # deployment would create; nothing has been observed when it is
            # written, and a readiness claim in a planning document is a lie
            # that automation would believe.
            "health": {"status": "planned", "url": identity.route_health},
        },
        "jwt": {"issuer": identity.jwt_issuer, "audience": identity.jwt_audience},
        "secrets": {
            "namespace": identity.secrets_namespace,
            "status": "planned",
            # Names only. No generation ID, no path, no value: none of those
            # exist until materialization, and inventing them here is exactly
            # the placeholder-shaped output §4.5 forbids.
            "required_names": required_secret_names,
        },
        "storage": {
            "enabled": storage_enabled,
            "bucket": identity.storage_bucket,
            "prefix": identity.storage_prefix,
        },
        "backup": {
            "enabled": backup_enabled,
            "stanza": identity.backup_stanza,
            "repository_prefix": identity.backup_repository_prefix,
        },
        "capabilities": {
            "enabled": sorted(
                entry["name"] for entry in capabilities.get("capabilities", []) if entry["enabled"]
            )
        },
        "template_version": template_version(),
    }


#: The exact key set of a generated ``compose.env`` (plan decision M, extended
#: by ADR 0013). Every entry is derived from the project manifest alone.
#:
#: The boundary this set encodes: a value that comes from ``host.yaml`` may not
#: be here. ``host.yaml`` is not one of the digested render inputs, so a
#: host-derived value in a rendered file would make the render depend on which
#: machine produced it and break the determinism contract. Those values live in
#: the root-owned ``/var/lib/agentic-postgres/projects/{key}/compose.env``,
#: passed as a third ``--env-file`` in ``--runtime`` mode only.
COMPOSE_ENV_KEYS: tuple[str, ...] = (
    "COMPOSE_PROJECT_NAME",
    "EDGE_NETWORK_NAME",
    "INTERNAL_NETWORK_NAME",
    "POSTGRES_VOLUME_NAME",
    "PROJECT_KEY",
    "PROJECT_ENVIRONMENT",
    "PROJECT_DOMAIN",
    "HEALTH_ROUTER_NAME",
    # Session 3. Every one is project-derived, so this is the right file for
    # them: the image references they are used beside come from versions.env,
    # and the three env files must stay disjoint (ADR 0013).
    #
    # Emitted with their units already attached -- `128MB`, `768m` -- rather
    # than as bare integers. compose.yaml then interpolates a finished value
    # instead of concatenating a suffix onto one, which it cannot do anyway,
    # and the unit a number is in stops being something a reader has to infer
    # from the variable's name.
    "POSTGRES_DATABASE_NAME",
    "POSTGRES_SHARED_BUFFERS",
    "POSTGRES_MAX_CONNECTIONS",
    "POSTGRES_WORK_MEM",
    "POSTGRES_MAINTENANCE_WORK_MEM",
    "POSTGRES_MEMORY_LIMIT",
    "POSTGRES_SHM_SIZE",
    "MIGRATIONS_TABLE",
    # The one role name that reaches a container. dbmate's connection URL is
    # assembled inside the migration container from this, the database name and
    # a password file; the alternative -- storing a whole URL as the secret --
    # would put a derived role name inside an operator-entered value, where
    # nothing checks it against `naming.ROLE_SUFFIXES` (D60).
    "MIGRATION_ROLE_NAME",
    # Session 4. All project-derived, so this is still the right file: the
    # allocated host port is NOT here, because it comes from host state and a
    # host-derived value in a rendered file would break the determinism
    # contract. It goes in the root-owned runtime env file instead.
    "POSTGRES_SERVICE_HOST",
    "APP_RUNTIME_ROLE_NAME",
    "PGBOUNCER_LISTEN_PORT",
    "PGBOUNCER_ADMIN_USER",
    "PGBOUNCER_POOL_MODE",
    "PGBOUNCER_POOL_SIZE",
    "PGBOUNCER_MAX_CLIENT_CONN",
    "PGBOUNCER_MAX_PREPARED_STATEMENTS",
    "PGBOUNCER_QUERY_WAIT_TIMEOUT",
    "PGBOUNCER_IDLE_TRANSACTION_TIMEOUT",
    "PGBOUNCER_SERVER_LIFETIME",
)

#: The pooler's port on its own project network. 6432 is the PgBouncer
#: convention; the locked image's own default is 5432, measured in Run 1, which
#: is why this is written down rather than left to the image.
PGBOUNCER_LISTEN_PORT = 6432

#: Transaction pooling is the only mode Session 4 supports, and this constant is
#: why it cannot be configured away. A manifest field would let a failing client
#: test be fixed by selecting session pooling, which the plan forbids in so many
#: words; the consequences of transaction mode are documented instead.
PGBOUNCER_POOL_MODE = "transaction"

#: The pooler's admin identity. Not a database role: PgBouncer's admin console
#: is a virtual database the daemon answers itself.
PGBOUNCER_ADMIN_USER = "pgbouncer_admin"

#: The Compose service name the cluster is reachable under on its own project
#: network. A constant rather than a derived name because it is the *service*
#: name inside one project's Compose model, which is scoped by the project
#: already; deriving it would make two projects' models differ for no reason.
POSTGRES_SERVICE_HOST = "postgres"

#: Where dbmate records applied versions. A constant rather than a manifest
#: field: the ledger's location is part of the migration contract, and a
#: project that could choose it could point two projects at one table.
MIGRATIONS_TABLE = "app_private.schema_migrations"


def build_compose_env(
    identity: naming.ProjectIdentity, budget: dict[str, int], database: dict[str, Any]
) -> bytes:
    """Exactly :data:`COMPOSE_ENV_KEYS`, in that order, and nothing else.

    Anything from ``versions.env`` belongs to ``versions.env``, and anything
    from ``host.yaml`` belongs to the root-owned runtime env file: all three
    must define disjoint namespaces so ``bin/compose.sh`` can prove none of
    them silently overrides another regardless of ``--env-file`` ordering.

    ``budget`` is passed in already resolved, from ``config.database_budget``.
    Resolving it here would be a second place that decides what a manifest
    without a `shared_buffers_mb` means, and the two would agree until one of
    them was changed.

    ``database`` is the manifest's ``database`` block, and it is required rather
    than optional. The pool settings that have schema defaults are resolved
    against ``config.POOL_DEFAULTS``; ``pool_size`` and ``max_client_connections``
    have none, because the schema makes them required — so they are read
    directly and a manifest missing one raises here rather than rendering an
    invented number that would look measured.
    """
    settings: dict[str, int] = {
        key: int(database.get(key, default)) for key, default in config.POOL_DEFAULTS.items()
    }
    settings["pool_size"] = int(database["pool_size"])
    settings["max_client_connections"] = int(database["max_client_connections"])

    values = {
        "COMPOSE_PROJECT_NAME": identity.compose_project_name,
        "EDGE_NETWORK_NAME": identity.edge_network,
        "INTERNAL_NETWORK_NAME": identity.internal_network,
        "POSTGRES_VOLUME_NAME": identity.postgres_volume,
        "PROJECT_KEY": identity.key,
        "PROJECT_ENVIRONMENT": identity.environment,
        "PROJECT_DOMAIN": identity.domain,
        "HEALTH_ROUTER_NAME": identity.health_router,
        "POSTGRES_DATABASE_NAME": identity.database_name,
        "POSTGRES_SHARED_BUFFERS": f"{budget['shared_buffers_mb']}MB",
        "POSTGRES_MAX_CONNECTIONS": str(budget["max_connections"]),
        "POSTGRES_WORK_MEM": f"{budget['work_mem_mb']}MB",
        "POSTGRES_MAINTENANCE_WORK_MEM": f"{budget['maintenance_work_mem_mb']}MB",
        # Lowercase `m` is Docker's byte suffix; uppercase `MB` is
        # PostgreSQL's. They are different spellings on purpose, because they
        # are read by different parsers, and a value that satisfied both would
        # be a coincidence rather than a fact.
        "POSTGRES_MEMORY_LIMIT": f"{budget['memory_limit_mb']}m",
        "POSTGRES_SHM_SIZE": f"{budget['shm_size_mb']}m",
        "MIGRATIONS_TABLE": MIGRATIONS_TABLE,
        "MIGRATION_ROLE_NAME": identity.roles["migration_user"],
        "POSTGRES_SERVICE_HOST": POSTGRES_SERVICE_HOST,
        "APP_RUNTIME_ROLE_NAME": identity.roles["app_runtime"],
        "PGBOUNCER_LISTEN_PORT": str(PGBOUNCER_LISTEN_PORT),
        "PGBOUNCER_ADMIN_USER": PGBOUNCER_ADMIN_USER,
        "PGBOUNCER_POOL_MODE": PGBOUNCER_POOL_MODE,
        "PGBOUNCER_POOL_SIZE": str(settings["pool_size"]),
        "PGBOUNCER_MAX_CLIENT_CONN": str(settings["max_client_connections"]),
        "PGBOUNCER_MAX_PREPARED_STATEMENTS": str(settings["max_prepared_statements"]),
        # Seconds, with the unit in the name rather than in a suffix: PgBouncer
        # reads a bare integer as seconds and would take `20s` as a parse error.
        "PGBOUNCER_QUERY_WAIT_TIMEOUT": str(settings["query_wait_timeout_seconds"]),
        "PGBOUNCER_IDLE_TRANSACTION_TIMEOUT": str(settings["idle_transaction_timeout_seconds"]),
        "PGBOUNCER_SERVER_LIFETIME": str(settings["server_lifetime_seconds"]),
    }
    lines = [
        "# Generated. Do not edit; do not shell-source.",
        "# Consumed only by bin/compose.sh via --env-file.",
        *(f"{key}={values[key]}" for key in COMPOSE_ENV_KEYS),
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_summary(outputs: dict[str, Any]) -> bytes:
    """Human-readable summary, derived purely from ``outputs.json``.

    Deterministic by construction (plan decision L): no timestamp, no host
    name, no absolute path. The same determinism test that covers outputs.json
    covers this file.
    """
    project = outputs["project"]
    database = outputs["database"]

    lines = [
        f"Project        {project['key']}",
        f"Domain         {project['domain']}",
        f"Compose        {outputs['compose']['project_name']}",
        f"Database       {database['name']}",
        f"Roles          {len(database['roles'])} derived",
        "",
        "Routes",
        f"  rest         {outputs['routes']['rest']}",
        f"  app          {outputs['routes']['app']}",
        f"  mcp          {outputs['routes']['mcp']}",
        f"  docs         {outputs['routes']['docs']}",
        f"  health       {outputs['routes']['health']['url']} "
        f"({outputs['routes']['health']['status']})",
        "",
        "Authority",
        f"  jwt issuer   {outputs['jwt']['issuer']}",
        f"  jwt audience {outputs['jwt']['audience']}",
        f"  secrets ns   {outputs['secrets']['namespace']}",
        "",
        "Endpoints",
        f"  pooled       {database['pooled']['status']} "
        f"(session {database['pooled']['available_from_session']})",
        f"  direct       {database['direct']['status']} "
        f"(session {database['direct']['available_from_session']})",
        "",
        f"Storage        {'enabled' if outputs['storage']['enabled'] else 'disabled'}"
        + (f"  bucket={outputs['storage']['bucket']}" if outputs["storage"]["enabled"] else ""),
        f"Backup         {'enabled' if outputs['backup']['enabled'] else 'disabled'}"
        + (f"  stanza={outputs['backup']['stanza']}" if outputs["backup"]["enabled"] else ""),
        f"Capabilities   {len(outputs['capabilities']['enabled'])} enabled",
        f"Secrets        {len(outputs['secrets']['required_names'])} declared, "
        f"{outputs['secrets']['status']}",
        "",
        "No service was started. Session 1 renders configuration only.",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Output security policy (runbook §4.4)
# ---------------------------------------------------------------------------


def assert_output_is_secret_free(document: Any, *, path: str = "") -> None:
    """Reject credentials in rendered output, at any depth."""
    if isinstance(document, dict):
        for key, value in document.items():
            where = f"{path}.{key}" if path else str(key)

            if isinstance(key, str) and key.endswith("_secret_ref"):
                if value is not None and not (
                    isinstance(value, str) and _SECRET_REFERENCE.match(value)
                ):
                    raise RenderError(
                        f"{where} must be null or a validated reference string, got {value!r}"
                    )
            elif isinstance(key, str) and config.is_sensitive_key(key):
                raise RenderError(f"rendered output contains a secret-bearing key: {where}")

            assert_output_is_secret_free(value, path=where)

    elif isinstance(document, list):
        for index, value in enumerate(document):
            assert_output_is_secret_free(value, path=f"{path}[{index}]")

    elif isinstance(document, str):
        if _CREDENTIAL_URL.search(document):
            raise RenderError(f"{path} contains a credential-bearing URL")
        if _PRESIGNED.search(document):
            raise RenderError(f"{path} contains a presigned URL signature")


# ---------------------------------------------------------------------------
# Filesystem transaction
# ---------------------------------------------------------------------------


def refuse_symlink(path: Path) -> None:
    """Runbook §4.1 step 3 and §9 check 6.

    A symlinked target would let a render write through the repository into an
    arbitrary location, and would silently break the owner-only mode contract.
    """
    if path.is_symlink():
        raise RenderError(f"refusing to render through a symlink: {path}")


@contextmanager
def project_lock(project_key: str) -> Iterator[None]:
    """Exclusive, non-blocking per-project lock (plan decision I)."""
    LOCK_ROOT.mkdir(parents=True, exist_ok=True)
    lock_path = LOCK_ROOT / f"{project_key}.lock"
    handle = os.open(lock_path, os.O_CREAT | os.O_RDWR, FILE_MODE)
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RenderError(
                f"another render holds the lock for {project_key}; refusing to interleave"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        os.close(handle)


def write_private(path: Path, payload: bytes) -> None:
    """Create a new file with owner-only mode and flush it to disk."""
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
    with os.fdopen(handle, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    # O_CREAT honours the umask, so set the mode explicitly rather than
    # assuming the process umask is 0o077.
    os.chmod(path, FILE_MODE)


def publish(staging: Path, target: Path) -> None:
    """Swap the staged directory into place, with rollback (plan decision J)."""
    refuse_symlink(target)

    backup: Path | None = None
    if target.exists():
        backup = STAGING_ROOT / f"{target.name}.backup.{secrets.token_hex(6)}"
        os.replace(target, backup)

    try:
        os.replace(staging, target)
    except OSError as exc:
        if backup is not None:
            os.replace(backup, target)
        raise RenderError(f"failed to publish {target}: {exc}") from exc

    if backup is not None:
        shutil.rmtree(backup, ignore_errors=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


#: The rendered migration set is the one generated artifact a *container* reads,
#: and it is read by a service that runs as uid 65532. Everything else under
#: `.generated/<key>/` is 0600 because it is read only by root or by the
#: operator who rendered it; a 0600 file bind-mounted into a non-root container
#: is a migration run that fails with "permission denied" from inside dbmate,
#: which is a long way from where the mode was set.
#:
#: The enclosing directory stays 0700 root-owned on the host, so widening these
#: two modes does not make the SQL readable by anyone who could not already
#: traverse to it. And the SQL carries no secret: it is templates plus derived
#: identifiers, and `assert_output_is_secret_free` has already run over the
#: document every one of those identifiers comes from.
MIGRATION_FILE_MODE = 0o644
MIGRATION_DIRECTORY_MODE = 0o755

#: What the rendered set records about itself, beside the SQL.
MIGRATION_MANIFEST_NAME = "rendered-manifest.json"


def write_rendered_migrations(directory: Path, document: dict[str, Any]) -> Path:
    """Render this project's migration set into `<directory>/migrations/`.

    A rendered payload, not a template: ADR 0028 makes the *rendered* text the
    immutable unit, and this is where it becomes a file. The digest recorded
    beside each one is the digest of exactly these bytes, so `migrate.sh` can
    refuse a file edited after it was rendered without re-rendering it to find
    out.
    """
    from agentic_postgres import migrations

    manifest = migrations.load_manifest()
    target = directory / "migrations"
    target.mkdir(mode=MIGRATION_DIRECTORY_MODE)

    entries = []
    for entry in manifest["migrations"]:
        payload = migrations.render_migration(entry, manifest, document)
        # dbmate orders by filename and parses `<version>_<name>.sql`. The name
        # is built from the manifest's own two fields rather than from the
        # template's filename: the template path is an input this repository
        # controls, and the applied version is a value the ledger keeps forever.
        filename = f"{entry['version']}_{entry['name']}.sql"
        path = target / filename
        path.write_text(payload, encoding="utf-8")
        path.chmod(MIGRATION_FILE_MODE)
        entries.append(
            {
                "version": entry["version"],
                "name": entry["name"],
                "file": filename,
                "sha256": migrations.digest(payload),
            }
        )

    manifest_path = target / MIGRATION_MANIFEST_NAME
    manifest_path.write_text(
        naming.canonical_json(
            {
                "project_key": document["project"]["key"],
                "migrations_table": MIGRATIONS_TABLE,
                "migrations": entries,
            }
        ).decode("utf-8"),
        encoding="utf-8",
    )
    manifest_path.chmod(MIGRATION_FILE_MODE)
    return target


def render_project(
    project_path: Path,
    capabilities_path: Path,
    *,
    validate_compose: bool = True,
) -> Path:
    """Validate, stage, verify, and publish one project. Returns the directory.

    ``validate_compose`` is honoured from Run 4 onward, when ``bin/compose.sh``
    and the Compose model exist. It is the single deliberate seam between runs
    and is closed, not left open: with no model present the step is skipped and
    said so, rather than silently reporting success.
    """
    project = config.load_project_manifest(project_path)
    capabilities = config.load_capabilities_manifest(capabilities_path)

    identity = naming.derive(
        slug=project["project"]["slug"],
        environment=project["project"]["environment"],
        domain=project["project"]["domain"],
        api_base_path=project["api"]["public_base_path"],
        mcp_base_path=project["mcp"]["public_base_path"],
        database_name=project["database"].get("name"),
        storage_enabled=bool(project.get("storage", {}).get("enabled", False)),
        storage_bucket=project.get("storage", {}).get("bucket"),
        storage_prefix=project.get("storage", {}).get("prefix"),
        backup_enabled=bool(project.get("backup", {}).get("enabled", False)),
        backup_stanza=project.get("backup", {}).get("stanza"),
        backup_repository_prefix=project.get("backup", {}).get("repository_prefix"),
    )

    digests = input_digests(project_path, capabilities_path)
    outputs = build_outputs(project, capabilities, identity, digests)

    refuse_symlink(GENERATED_ROOT)
    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
    STAGING_ROOT.mkdir(parents=True, exist_ok=True)

    target = GENERATED_ROOT / identity.key

    with project_lock(identity.key):
        staging = STAGING_ROOT / f"{identity.key}.{os.getpid()}.{secrets.token_hex(8)}"
        staging.mkdir(mode=DIRECTORY_MODE)

        try:
            write_private(staging / "outputs.json", naming.canonical_json(outputs))
            write_private(
                staging / "compose.env",
                build_compose_env(identity, outputs["database"]["budget"], project["database"]),
            )
            write_private(staging / "rendered-summary.txt", build_summary(outputs))

            staged = staging / "outputs.json"
            document = _reread(staged)
            config.validate_against_schema(document, "outputs.schema.json")
            assert_output_is_secret_free(document)

            for name in ("outputs.json", "compose.env", "rendered-summary.txt"):
                refuse_symlink(staging / name)

            # From the validated document that was just written, not from the
            # in-memory object and not from `identity`. The migration renderer
            # reads every identifier out of outputs.json precisely so that the
            # SQL and the Compose model cannot be derived from two different
            # readings of the same manifest (ADR 0002, ADR 0028).
            write_rendered_migrations(staging, document)

            if validate_compose:
                _validate_staged_compose(staging)

            publish(staging, target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    return target


def _reread(path: Path) -> dict[str, Any]:
    """Validate the bytes that were written, not the object in memory."""
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _validate_staged_compose(staging: Path) -> None:
    """Runbook §4.1 step 6: the staged model must render before it is published.

    Validating the *staged* directory rather than the published one is the
    whole point: a model that fails to interpolate must never reach
    ``.generated/{project_key}``.
    """
    wrapper = REPO_ROOT / "bin" / "compose.sh"
    model = REPO_ROOT / "compose.yaml"
    if not wrapper.is_file() or not model.is_file():
        raise RenderError(
            f"the Compose model is missing ({wrapper.name}, {model.name}); "
            "cannot validate the staged render"
        )

    import subprocess

    # S603 is suppressed deliberately, and narrowly. src/ is not in the
    # shell-out ignore list in pyproject.toml because library code generally
    # should not spawn processes; this is the one place runbook §4.1 step 6
    # requires it. Both arguments are repository-relative paths this module
    # constructed itself, never operator input.
    result = subprocess.run(  # noqa: S603
        [str(wrapper), str(staging), "--profile", "contract", "config"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RenderError(
            f"staged Compose model failed validation (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )
