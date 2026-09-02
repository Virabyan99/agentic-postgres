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
import json
import os
import re
import secrets
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Any

from agentic_postgres import (
    REPO_ROOT,
    auth_limits,
    config,
    deployed_output,
    diagnosis,
    host_config,
    naming,
    runtime_override,
    scope_registry,
    secrets_contract,
    template_version,
)

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

#: The reviewed OpenAPI snapshot, and the name it is published under.
#:
#: Copied into the rendered directory rather than mounted from the release, so
#: that what a deployment serves is pinned to what it rendered rather than to
#: whatever the current release happens to hold.
CANONICAL_OPENAPI = REPO_ROOT / "contracts" / "postgrest-openapi.canonical.json"
SNAPSHOT_FILENAME = "openapi.json"

#: The application API's reviewed document, and the name it is published under
#: (D226, Run 10). A second file in the same directory -- one image, one CSP,
#: one credential, two documents.
#:
#: `bin/app-contract.py` captures it and names the same source path. That
#: command needs no host, because FastAPI generates the document from this
#: checkout rather than from a running server; the review step is the same, and
#: what is copied here is the approval rather than a fresh generation.
CANONICAL_APP_OPENAPI = REPO_ROOT / "contracts" / "app-openapi.canonical.json"
APP_SNAPSHOT_FILENAME = "app-openapi.json"

#: World-readable, because it is a **published document**: served to anyone who
#: can reach the page, a committed artefact a human reviewed, and read by a
#: container running as 65532 rather than as the owner of the rendered directory.
#: A `0600` copy would reach the mount and be unreadable, which `serve.py`
#: reports as 503: correct, and permanently.
#:
#: It was "the only rendered file that is" until Session 10 Run 11, and that
#: sentence is deleted rather than qualified -- `PGBACKREST_CONF_MODE` is the
#: second, and a stale "the only one" is how the next reader concludes there is
#: nothing else to check.
SNAPSHOT_MODE = 0o444

#: Session 14's metrics collector configuration, and the name it is published
#: under (ADR 0164).
#:
#: Rendered rather than mounted from the release, for `SNAPSHOT_FILENAME`'s
#: reason: what a deployment runs is pinned to what it rendered. Written at
#: render time rather than by the deploy, which is why the collector is **not**
#: in `POST_ARTIFACT_SERVICES` -- the file exists the moment the render is
#: published, before any container starts. `mcp` is deferred because its two
#: artefacts are written late, and confusing the two reasons is D463.
#:
#: **It holds no secret and cannot.** The credential guarding this surface is a
#: bcrypt hash in the edge's dynamic document (ADR 0086); nothing in this file
#: is sensitive, which is what lets it be world-readable at all.
OTEL_CONFIG_FILENAME = "otelcol.yaml"
OTEL_CONFIG_MODE = 0o444

#: The archiver's configuration, read by a container running as **999**.
#:
#: The third rendered artefact a container reads, after the migration set (uid
#: 65532) and the OpenAPI snapshots, and it was `0600` until a deploy proved it
#: (D588). pgBackRest refuses an unreadable config with
#: `[041]: unable to open file ... for read: [13] Permission denied` -- loudly,
#: which is the good news, and **from two places at once**: the deploy's step 6c,
#: and every `archive_command` the postmaster runs afterwards. Rig 9's arm K7
#: measured that exact code for a root-owned file under a container running as
#: 999, and nothing connected it to the rendered config because the rig supplied
#: its own.
#:
#: `0444` and not `0640 root:999`: the enclosing directory stays `0700`
#: root-owned on the host, so widening this does not make the file readable by
#: anyone who could not already traverse to it -- the argument
#: `MIGRATION_FILE_MODE` already makes. And **the file carries no credential by
#: construction**: `build_pgbackrest_conf` omits `repo1-s3-key`,
#: `repo1-s3-key-secret` and `repo1-cipher-pass`, and
#: `test_the_rendered_config_never_names_an_option_the_credential_files_set`
#: asserts it against the contract rather than against a list.
PGBACKREST_CONF_MODE = 0o444

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


#: The `statement_timeout` the platform insists on for the runtime role when the
#: manifest does not name one. It is not a second answer to the manifest's
#: question: the manifest says what a *project* wants, and this says what the
#: platform will not go without -- an application holding a server connection in
#: a long statement holds it out of the pool, which under transaction pooling is
#: the whole pool's problem rather than its own. A manifest entry for
#: `app_runtime` overrides it, and `bin/postgres-bootstrap.py` no longer carries
#: the literal it used to (ADR 0067).
DEFAULT_APP_RUNTIME_STATEMENT_TIMEOUT = "30s"


def resolve_api_connection_budget(project: dict[str, Any]) -> int:
    """What the REST service commits to, from `config` rather than from arithmetic here.

    One answer, computed in one place (ADR 0002 applied to a number). The
    manifest-side budget check reasons about this same figure, so a second sum
    written here would agree today and diverge on the day one of them changed --
    which is the only day it would matter.

    A project with no REST service still publishes one: the reservations are
    what a service *would* take, and a document whose value depended on whether
    a service happened to be enabled would make the bootstrap's division of the
    budget depend on it too.
    """
    rest = ((project.get("api") or {}).get("rest")) or {}
    return config.postgrest_connection_budget(rest)


def resolve_auth_connection_budget(project: dict[str, Any]) -> int:
    """What the auth service commits to, from `config` rather than arithmetic here.

    The same shape as :func:`resolve_api_connection_budget` and for the same
    reasons: one answer computed in one place, and published whether or not the
    service is enabled so that the bootstrap plane's division of the budget does
    not depend on a flag it does not read.
    """
    app = ((project.get("api") or {}).get("app")) or {}
    return config.auth_connection_budget(app)


def resolve_storage_connection_budget(project: dict[str, Any]) -> int:
    """What the storage service commits to, from `config` rather than arithmetic here.

    The same shape as the two functions above and for the same reasons: one
    answer computed in one place, and published whether or not the service is
    enabled so that the bootstrap plane's division of the budget does not depend
    on a flag it does not read.

    ADR 0099's fourth claimant. The division is exact -- it was exact at three,
    which is why adding one needed the ceiling raised rather than a number
    chosen.
    """
    storage = project.get("storage") or {}
    return config.storage_connection_budget(storage)


def resolve_statement_timeouts(project: dict[str, Any], roles: dict[str, str]) -> dict[str, str]:
    """Resolve the manifest's suffix-keyed timeouts to derived role names.

    The manifest keys `api.rest.statement_timeouts` by role *suffix* -- `anon`,
    `authenticated` -- because that is what an operator can reasonably write.
    Every consumer needs the derived name, and there is exactly one authority
    for that mapping (ADR 0002), so it is resolved here and written into the
    document. The bootstrap plane then applies a name it was handed rather than
    deriving one, which is the difference between one authority and two.

    Before version 7 this function did not exist and neither did the field: the
    manifest's timeouts were validated by `config._validate_statement_timeouts`
    and then dropped, so no request role ever received one and a 30-second
    statement ran to completion under a manifest that said 5s (D197).
    """
    declared = ((project.get("api") or {}).get("rest") or {}).get("statement_timeouts") or {}

    resolved = {
        roles["app_runtime"]: DEFAULT_APP_RUNTIME_STATEMENT_TIMEOUT,
    }
    for suffix, value in declared.items():
        # `config._validate_statement_timeouts` has already refused any suffix
        # the platform does not derive, so this lookup cannot fail on a valid
        # manifest -- and if it ever could, failing here is right: a timeout
        # written for a role nothing created is the thing that schema's own
        # description warns about.
        resolved[roles[suffix]] = value
    return dict(sorted(resolved.items()))


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
    storage_settings = {**config.STORAGE_DEFAULTS, **(project.get("storage") or {})}
    storage_enabled = bool(storage_settings["enabled"])
    backup_settings = {**config.BACKUP_DEFAULTS, **(project.get("backup") or {})}
    backup_enabled = bool(backup_settings["enabled"])

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
        # Version 5 added nothing to this branch (ADR 0053): `routes.rest`,
        # `routes.docs`, `jwt.issuer` and `jwt.audience` have been here since
        # Session 1 and remain the single derivation of those values. What moved
        # was the deployed branch, which now records a status and an observation
        # against them.
        #
        # Version 6 does reach this branch, and needs no line here: it adds
        # `database.roles.api_documentation` (D158), and `database.roles` is
        # written from `naming.database_roles`, which derives every entry of
        # `ROLE_SUFFIXES`. Appending the role there is the whole change, which is
        # what single-authority derivation is for -- a second list here would be
        # the place the two could disagree.
        # Read, not restated. This was the literal `10`, and a literal here is a
        # second authority for a number `deployed_output` already owns -- caught
        # only because `test_the_rendered_fixture_is_current` compares the two,
        # which is a test doing the work an import does for free. Session 7's
        # bump to 11 is the fourth time this literal has had to be found by
        # hand.
        "schema_version": deployed_output.SCHEMA_VERSION,
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
                # Version 13, and named here a run before anything attaches to
                # it -- Run 4 puts it in the model. The rendered branch names
                # what a deployment WOULD create, and `storage_bucket` sat in
                # exactly this state from Session 1 to Session 7.
                "backup": identity.backup_network,
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
            # Version 7. Resolved to derived role names here so the bootstrap
            # plane -- the only plane that may ALTER ROLE (D102) -- applies a
            # name it was given rather than deriving one (ADR 0067).
            "statement_timeouts": resolve_statement_timeouts(project, dict(identity.roles)),
            "api_connection_budget": resolve_api_connection_budget(project),
            # Version 10. The auth service's own commitment, charged whether or
            # not the service is enabled, for the reason the line above is.
            "auth_connection_budget": resolve_auth_connection_budget(project),
            # Version 11. The fourth claimant (ADR 0099), charged on the same
            # terms as the two above.
            "storage_connection_budget": resolve_storage_connection_budget(project),
            # Version 11, and it is not a claimant -- it is what the bootstrap
            # plane checks the application's REMAINDER against (D327). Two
            # arithmetics exist over this budget and until ADR 0099 nothing
            # compared them; this is the field that lets the plane which knows
            # the live numbers do the comparison.
            "pooler_pool_size": int(project["database"]["pool_size"]),
        },
        "routes": {
            "rest": identity.route_rest,
            "app": identity.route_app,
            "mcp": identity.route_mcp,
            "docs": identity.route_docs,
            "app_docs": identity.route_app_docs,
            # `planned`, unconditionally. A rendered document describes what a
            # deployment would create; nothing has been observed when it is
            # written, and a readiness claim in a planning document is a lie
            # that automation would believe.
            "health": {"status": "planned", "url": identity.route_health},
            # Version 11. Named whether or not storage is enabled, like every
            # other route here: a rendered document describes what a deployment
            # would create, and the readiness claim lives on the deployed
            # branch (D326).
            "storage": identity.route_storage,
            # Version 14. The surface ADR 0005 reserved in Session 1 and nothing
            # owned for thirteen sessions (D760). A bare URL like every route
            # added since version 5 -- the readiness claim lives on the deployed
            # branch, where something can observe it.
            "metrics": identity.route_metrics,
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
            # Version 11. Resolved against the defaults here rather than at the
            # runtime, for the reason the budget above is resolved here: the
            # document is the one thing every plane reads (ADR 0002), and a
            # service applying its own default would be a second authority for a
            # bound the deploy was checked against.
            **{
                key: storage_settings[key]
                for key in (
                    "upload_url_ttl_seconds",
                    "download_url_ttl_seconds",
                    "max_upload_bytes",
                )
            },
            "allowed_cors_origins": sorted(storage_settings["allowed_cors_origins"]),
        },
        "backup": {
            "enabled": backup_enabled,
            "stanza": identity.backup_stanza,
            "repository_prefix": identity.backup_repository_prefix,
            # Version 13. The bucket is `naming`'s, like the stanza beside it;
            # `retain_full` is the manifest's, resolved against the defaults
            # HERE for the reason the storage bounds above are resolved here --
            # this document is the one thing every plane reads (ADR 0002), and
            # a `pgbackrest.conf` renderer applying its own default would be a
            # second authority for a retention the deploy was checked against.
            #
            # `retain_full` is published whether or not backups are enabled,
            # unlike the three identities: it is a bound rather than a name, and
            # nulling it would make "the default is two chains" a fact readable
            # only from source. The identities go null because a rendered
            # document must not name a repository for a facility that is off.
            "bucket": identity.backup_bucket,
            "retain_full": int(backup_settings["retain_full"]),
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
    # Session 10 (ADR 0147). Rendered for every project, enabled or not: the
    # network is declared in `compose.yaml` unconditionally, and Compose refuses
    # an empty interpolation as firmly as an unset one (D178, ADR 0062).
    "BACKUP_NETWORK_NAME",
    "POSTGRES_VOLUME_NAME",
    "STORE_VOLUME_NAME",
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
    # Session 10's four (ADR 0144). Rendered for every project whether or not
    # backups are enabled, because `compose.yaml` interpolates all four
    # unconditionally -- a disabled project renders `archive_mode=off` and an
    # archive command that cannot run, rather than an empty value Compose
    # refuses (D178).
    "POSTGRES_ARCHIVE_MODE",
    "POSTGRES_ARCHIVE_COMMAND",
    "POSTGRES_ARCHIVE_TIMEOUT",
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
    # Session 4 Run 7. The client compatibility fixtures reach the pooler by its
    # Compose service name, the same way the cluster is reached by `postgres`.
    "PGBOUNCER_SERVICE_HOST",
    # Two identities the fixtures assert row isolation between. Constants rather
    # than values generated per run: a fixture that invented its identities could
    # pass by comparing two empty result sets, and a failure would not be
    # reproducible from the evidence. They are UUIDs and nothing else -- no
    # credential, no claim to authenticity. ADR 0029 is explicit that a claim is
    # asserted rather than verified in Session 4.
    "APG_FIXTURE_USER_A",
    "APG_FIXTURE_USER_B",
    "APG_DISPOSABLE_SCHEMA",
    # Session 5. The REST service is configured entirely from its environment,
    # because its image has no shell to read a config file into (ADR 0056) --
    # so every one of these is a value Compose interpolates straight into
    # `PGRST_*`. All project-derived, all non-secret: the credential is a file
    # named by `?passfile=` inside a conninfo built from three of them.
    #
    # `POSTGREST_CORS_ORIGINS` is the one that is not an identifier. It is a
    # comma-joined list of exact HTTPS origins, validated in `config` before it
    # reaches here, and it is here rather than in the runtime env file because
    # it comes from the project manifest -- a host-derived value in a rendered
    # file would break the determinism contract (ADR 0013).
    "POSTGREST_AUTHENTICATOR_ROLE",
    "ANON_ROLE_NAME",
    "POSTGREST_EXPOSED_SCHEMA",
    "POSTGREST_MAX_ROWS",
    "POSTGREST_POOL_SIZE",
    "POSTGREST_POOL_ACQUISITION_TIMEOUT",
    "POSTGREST_POOL_MAX_IDLE",
    "POSTGREST_POOL_MAX_LIFETIME",
    "POSTGREST_CORS_ORIGINS",
    "JWT_AUDIENCE",
    # Session 5 Run 6. The edge's half of the same configuration.
    #
    # PostgREST provides no general body-size control, so the limit is enforced
    # one hop earlier by a Traefik buffering middleware -- which means these two
    # numbers are read by a *label value* in the runtime override rather than by
    # any container's environment. They are here for the same reason as the
    # rest: they come from the project manifest. Interpolation is what keeps a
    # middleware's name (a label *key*, and therefore rendered) apart from its
    # limits (values, and therefore not).
    "API_REQUEST_BODY_MAX_BYTES",
    "API_REQUEST_BODY_MEMORY_BYTES",
    # The path a router rule matches on, derived beside the URL it publishes so
    # that moving the base path cannot move one without moving the other.
    "API_REST_PATH",
    "DOCS_PAGE_PATH",
    "DOCS_ROUTER_NAME",
    "DOCS_STRIPPREFIX_MIDDLEWARE_NAME",
    "REST_ROUTER_NAME",
    "API_BUFFERING_MIDDLEWARE_NAME",
    "API_STRIPPREFIX_MIDDLEWARE_NAME",
    "DOCS_CREDENTIAL_MIDDLEWARE_NAME",
    # Session 6, Run 7. Every one is project-derived or manifest-declared, so
    # this is the right file for them. The auth service's CREDENTIAL is not
    # here and never will be: it is a mounted file libpq reads through the
    # conninfo's `passfile=`, which is what keeps it out of the environment,
    # the argument vector and `docker inspect` (D60).
    "JWT_ISSUER",
    "AUTH_SERVICE_ROLE_NAME",
    "AUTH_POOL_SIZE",
    "AUTH_MEMORY_LIMIT",
    # Session 6, Run 8. The suffix -> derived-name map for every role a TOKEN
    # may name. The service needs it because `naming.py` is the single authority
    # for derivation (ADR 0002) and is not in the image; emitting it here means
    # the container is handed names rather than deriving its own, which is the
    # same rule ADR 0067 applies to the bootstrap plane.
    "AUTH_ROLE_NAMES",
    # Session 6, Run 10. The application API's route and the second
    # documentation surface, in the same two shapes everything above uses: a
    # *path* a router rule matches on, and a *name* that `runtime_override.py`
    # renders into a label key because Compose cannot interpolate inside one
    # (ADR 0013).
    "API_APP_PATH",
    "APP_ROUTER_NAME",
    "APP_BUFFERING_MIDDLEWARE_NAME",
    "APP_STRIPPREFIX_MIDDLEWARE_NAME",
    "APP_DOCS_PAGE_PATH",
    "APP_DOCS_ROUTER_NAME",
    # The documentation ROOT, which is what the application documentation
    # router strips -- not its page path. `_app_docs_labels` says why: two
    # surfaces on one container cannot both arrive at `/`.
    "DOCS_ROOT_PATH",
    # The auth service's body bound, read from `strict_json.MAX_BODY_BYTES`
    # rather than declared here (ADR 0084). It reaches a Traefik buffering
    # middleware's label *value*, exactly as the REST route's limits do, and it
    # is the only thing that bounds what the process allocates: the service's
    # own check runs after `request.body()` has already read everything.
    "AUTH_REQUEST_BODY_MAX_BYTES",
    # Session 7, Run 2. The storage runtime's configuration, in the same two
    # shapes everything above uses: values the container reads, and identifiers
    # `naming.py` derives and hands over rather than letting the image derive
    # its own (ADR 0002, ADR 0067).
    #
    # The R2 credential is NOT here and never will be. Both halves are mounted
    # files whose container paths `compose.yaml` names, which is what keeps a
    # third party's credential out of the environment, the argument vector and
    # `docker inspect` -- the rule D60 states for every database password here.
    "STORAGE_SERVICE_ROLE_NAME",
    "STORAGE_POOL_SIZE",
    "STORAGE_MEMORY_LIMIT",
    "STORAGE_BUCKET",
    "STORAGE_PREFIX",
    "STORAGE_ENDPOINT",
    "STORAGE_UPLOAD_URL_TTL_SECONDS",
    "STORAGE_DOWNLOAD_URL_TTL_SECONDS",
    "STORAGE_MAX_UPLOAD_BYTES",
    # Session 8, Runs 4 and 5. The agent plane's two rendered values, and the
    # length of this list is worth noticing against the nine above it: no role
    # name, no pool size, no credential path. It holds none of those things
    # (ADR 0121, D407).
    #
    # `MCP_POSTGREST_URL` is an *address*, not a credential -- the request it is
    # used for carries the caller's own token (ADR 0125). It is derived here
    # rather than assembled in the image, which is ADR 0002's rule and the same
    # one ADR 0106 states for the storage endpoint.
    "MCP_MEMORY_LIMIT",
    "MCP_POSTGREST_URL",
    # Session 8, Run 8. How many upstream reads the agent plane may have in
    # flight (ADR 0129). **Derived from PostgREST's pool**, because that is
    # what it protects: the agent plane holds no database credential and no
    # share of ADR 0099's budget (D407), but each read it makes occupies one
    # of PostgREST's connections while it runs, and that pool is shared with
    # human callers.
    "MCP_MAX_CONCURRENT_READS",
    # Session 8, Run 7. The published route (ADR 0128). A TOP-LEVEL path,
    # unlike every other application route: nothing else in this deployment
    # matches it, so its precedence is uncontested rather than won by
    # construction. What it shares with the others is the two-matcher form,
    # because `PathPrefix` is a string prefix and `/mcp` would otherwise
    # answer `/mcpx` (D162, D408).
    "API_MCP_PATH",
    "MCP_ROUTER_NAME",
    # Session 14 (ADR 0164). Both were computed by `compose_env`'s values
    # dict from Run 2 and named in the deploy's OVERRIDE_NAME_KEYS, and
    # neither was here -- so both were dropped on the way out, because this
    # list is what `compose_env` iterates. It surfaced as a step-4 refusal
    # on the host, which is `_env_value` doing its job at the latest
    # possible moment; `test_every_name_the_deploy_reads_is_a_name_the_render_emits`
    # is the same finding in a checkout.
    "METRICS_ROUTER_NAME",
    "METRICS_CREDENTIAL_MIDDLEWARE_NAME",
    # Interpolated by COMPOSE, not read by the deploy -- it is the
    # `Path()` matcher in the metrics router's rule, and a router label's
    # VALUE is interpolated where its key is rendered (ADR 0013). So the
    # round-1 guard over the deploy's own reads cannot see it, and did
    # not: this surfaced as `METRICS_PATH is missing a value` from
    # `compose config`, one step later than the pair above.
    "METRICS_PATH",
    # Session 7, Run 7. The published route, in the same two shapes the
    # application route uses one line-block above: a *path* a router rule
    # matches on, and three *names* `runtime_override.py` renders into label
    # keys because Compose cannot interpolate inside one (ADR 0013).
    #
    # `API_STORAGE_PATH` is the application path plus `/storage`, and the
    # relationship is load-bearing rather than cosmetic: the storage rule is the
    # application rule with that suffix inserted into both matchers, which makes
    # it exactly sixteen characters longer and therefore higher-priority
    # (ADR 0108 -- Traefik's default priority was measured to be the rule
    # string's length).
    "API_STORAGE_PATH",
    "STORAGE_ROUTER_NAME",
    "STORAGE_BUFFERING_MIDDLEWARE_NAME",
    "STORAGE_STRIPPREFIX_MIDDLEWARE_NAME",
    "STORAGE_CORS_MIDDLEWARE_NAME",
    # The origin allowlist, as one comma-separated value (ADR 0109). Measured:
    # Traefik parses a comma-separated label into a list, read back from its own
    # API as `['https://a.example', 'https://b.example']`.
    #
    # It is a VALUE and not a name, so it stays an interpolation reference and
    # never reaches `runtime_override.py` -- and it is the same sorted list the
    # rendered document publishes under `storage.allowed_cors_origins`, because
    # one origin list with two renderings is the whole point of D323.
    "STORAGE_CORS_ALLOWED_ORIGINS",
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

#: Session 8, Run 4; **measured in Run 8** (ADR 0131, D456).
#:
#: The agent plane's memory ceiling, in MiB. It was the application API's figure,
#: inherited and flagged as unmeasured for four runs. It is now a **choice with a
#: floor under it**, and the floor is a function of the two budgets ADR 0129 set:
#:
#:     floor(share) = 128 + share x 4   -- mcp_budgets.memory_floor_mb
#:                  = 148 MiB at the default share of 5
#:
#: Measured with ADR 0082's rig -- one fresh interpreter per arm, because
#: `ru_maxrss` is a high-water mark, and a control that imports nothing. The
#: fully loaded runtime is **69.2 MiB** resident and one concurrent read at the
#: byte ceiling costs **1.8 MiB** on top, linear to ten. Both are charged high,
#: 128 and 4, because this profiles the *interpreter* and **no `mcp` container
#: has started anywhere yet**.
#:
#: 384 is 2.6x the floor at the default share, and it stays: lowering a limit on
#: the strength of an off-container profile is the direction that costs an OOM
#: kill rather than a redeploy, on a host with no swap. **Run 9's host trip is
#: where the container's own figure comes from.**
MCP_MEMORY_LIMIT_MB = 384

#: The pooler's admin identity. Not a database role: PgBouncer's admin console
#: is a virtual database the daemon answers itself.
PGBOUNCER_ADMIN_USER = "pgbouncer_admin"

#: The Compose service name the cluster is reachable under on its own project
#: network. A constant rather than a derived name because it is the *service*
#: name inside one project's Compose model, which is scoped by the project
#: already; deriving it would make two projects' models differ for no reason.
POSTGRES_SERVICE_HOST = "postgres"

#: The pooler's Compose service name, for the same reason and on the same terms.
PGBOUNCER_SERVICE_HOST = "pgbouncer"

#: The one schema PostgREST exposes. A constant, not a manifest field: `db-schemas`
#: is the boundary that decides what a request can name at all, and a project
#: that could widen it from its own manifest could name `app` (ADR 0052).
POSTGREST_EXPOSED_SCHEMA = "api"

#: The Compose service name, as the edge and the internal network see it.
POSTGREST_SERVICE_HOST = "postgrest"

#: The two identities the client fixtures prove row isolation between.
#:
#: Fixed, and version 5 UUIDs of nothing in particular -- they are opaque and
#: only have to be two distinct valid UUIDs. Fixed rather than generated so that
#: a run's evidence names the same identities every time and a failure can be
#: reproduced from it; and because a fixture that generated its own could
#: satisfy "A cannot see B's rows" by comparing two empty result sets. The
#: fixtures also assert that each user sees *some* of its own rows, which is the
#: half that stops that.
FIXTURE_USER_A = "3f6c2a10-5d84-4f1e-9b7c-0a2d61e8c401"
FIXTURE_USER_B = "8b41d9e2-7c05-4a63-8f19-2d5e70a3b902"

#: The schema Prisma Migrate creates and drops in the live project database
#: (plan §4.4).
#:
#: A derived constant, not a value chosen per run, and that is a divergence from
#: §4.4 rather than an oversight (D109). Every interpolation in `compose.yaml`
#: must be `:?required`, and every value in `compose.env` must be project-derived
#: or the rendered output stops being deterministic — so a randomly chosen name
#: cannot reach the model at all. What §4.4 actually buys is kept: the name is
#: recorded in root-owned state before the drop, the drop targets only the
#: recorded name, and the fixture refuses any of the protected schemas by name.
#:
#: `apg_` prefixed and unmistakable, so an operator who finds it in a database
#: knows what created it.
PRISMA_FIXTURE_SCHEMA = "apg_client_fixture"

#: Session 5's transient acceptance object, in `api` (plan §4.4).
#:
#: The timeout and reload proofs need something the released schema does not
#: have: a function slow enough to exceed a role's `statement_timeout`, and one
#: DDL change PostgREST has not already cached. Both are the same object, created
#: and dropped inside one fixture.
#:
#: In `api` because that is the only schema PostgREST exposes, so an object
#: anywhere else could not be reached over HTTP and would prove nothing about
#: the plane under test. Which is also what makes the name load-bearing: for as
#: long as it exists it is on the published surface, and `API-SCHEMA-001` and
#: `API-CONTRACT-001` both assert it is gone afterwards.
#:
#: A constant for D109's reason, restated one session on: a name chosen per run
#: cannot be asserted absent by a test that does not know it. `apg_` prefixed and
#: unmistakable, like the schema above, so an operator who finds one in a
#: database knows what created it and that nothing released did.
ACCEPTANCE_PROBE_FUNCTION = "apg_acceptance_probe"

#: Where dbmate records applied versions. A constant rather than a manifest
#: field: the ledger's location is part of the migration contract, and a
#: project that could choose it could point two projects at one table.
MIGRATIONS_TABLE = "app_private.schema_migrations"


def build_pgbackrest_conf(
    identity: naming.ProjectIdentity, outputs: dict[str, Any], endpoint: str
) -> bytes:
    """The repository configuration, rendered from the document nothing else reads.

    **Every value here comes out of `outputs`**, not out of the manifest and not
    re-derived from the key. That is ADR 0002 in the place it matters most: the
    stanza, the bucket, the prefix and the retention are already decided and
    published, and a second derivation here would be the copy that disagrees.

    **What is NOT here is a credential.** `repo1-s3-key`, `repo1-s3-key-secret`
    and `repo1-cipher-pass` are absent by construction -- pgBackRest reads each
    of them from the environment when the config omits it, and the runtime
    override supplies them from the mounted files. A secret in a rendered file
    is a secret in the rendered directory, and `secrets.required.yaml` exists so
    that values live in per-consumer generations instead (ADR 0010, D60).

    ``endpoint`` arrives FINISHED, derived once by `naming.storage_endpoint_url`
    from `backup.account_id`. It is not in `outputs`: the storage endpoint is
    not either, for the same reason -- it reaches its container through
    `compose.env` and this one reaches its container through this file, and
    neither is a fact a document reader needs. What matters is that there is one
    assembly site and it is not here (ADR 0106).

    `pg1-path` is PGDATA and never the volume's mount point (D53, D514). Two of
    the three plausible paths persist data, so "the row survived" does not
    distinguish them -- but a stanza created against the wrong one would make
    the first restore wrong rather than failing.

    A disabled project still gets a file, with the stanza section omitted. The
    mount is unconditional, and Docker turns a missing source into a directory
    (D463).
    """
    backup = outputs["backup"]
    lines = [
        "# GENERATED by bin/render-config.py. Do not edit by hand.",
        "#",
        "# Credentials are deliberately absent. Each is a one-option fragment",
        "# mounted per consumer under /etc/pgbackrest/conf.d, which pgBackRest",
        "# reads after this file -- so nothing here may name those options.",
        "[global]",
    ]
    if not backup["enabled"]:
        lines += [
            "# Backups are disabled for this project. The file exists because the",
            "# mount does; nothing reads past this line.",
            "",
        ]
        return "\n".join(lines).encode("utf-8")

    lines += [
        "repo1-type=s3",
        f"repo1-s3-bucket={backup['bucket']}",
        f"repo1-path=/{backup['repository_prefix'].rstrip('/')}",
        f"repo1-s3-endpoint={endpoint.removeprefix('https://')}",
        # R2 is not AWS and has no regions, but the S3 protocol requires the
        # field and pgBackRest requires it too. `auto` is what R2's own
        # documentation uses for S3-compatible clients.
        "repo1-s3-region=auto",
        # ADR 0107 froze `path` for the storage service against a MEASURED
        # botocore fallback. That measurement does not transfer -- pgBackRest is
        # not botocore -- but the decision to freeze one style does, and path is
        # the style R2 documents for S3-compatible clients. Written explicitly
        # rather than left to a default, so an upstream default change is a
        # visible diff instead of a working deployment that stops working.
        "repo1-s3-uri-style=path",
        "repo1-cipher-type=aes-256-cbc",
        f"repo1-retention-full={backup['retain_full']}",
        # Created in the image, owned 999:999, because the container runs as the
        # postmaster and cannot create directories under /var.
        "log-path=/var/log/pgbackrest",
        "spool-path=/var/spool/pgbackrest",
        "log-level-console=warn",
        "log-level-file=info",
        "",
        f"[{backup['stanza']}]",
        f"pg1-path={runtime_override.POSTGRES_PGDATA}",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


#: A domain, for the one label whose value is not a Traefik name.
#:
#: Deliberately narrow: it is interpolated into a regex, and a hostname is the
#: first identity here that legitimately contains a `.`.
_DOMAIN_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def _scrape_keep_regex(router_names: tuple[str, ...], domain: str) -> str:
    """The `keep` regex admitting only this project's series.

    Three branches over `[router, service, cn]`, because Prometheus concatenates
    the source labels with `;` and chains rules with AND. `router` ours, or
    `service` ours, or the certificate's `cn` ours -- and a series carrying none
    of them (Traefik's own Go and process metrics, its config counters, and every
    ENTRYPOINT family, which is shared by every project on the host) matches no
    branch and is dropped.

    **`cn` is Run 5's addition and it is question 5 arriving one run later.**
    Run 4 wrote this filter from the labels it had, which were `router` and
    `service`. `traefik_tls_certs_not_after` carries neither -- it is labelled
    `cn`, `sans` and `serial` -- so the two-branch form dropped the certificate
    series entirely, and the certificate alert would have been a rule over a
    series this project's own surface refused to publish. **The rule would have
    stayed quiet for ever, which is what a healthy deployment looks like.**

    `(@[a-z]+)?` admits Traefik's provider suffix without naming one. The
    routers are docker-label-derived today and read `…@docker`; the measurement
    behind this rule ran against `…@file`. Pinning either would make this rule
    silently keep nothing the day a route moved providers -- and keeping
    nothing looks exactly like a route nobody used.

    **The `cn` branch is an equality, and a certificate covering more than one
    domain is a case this does not serve.** If a project's domain appeared only
    in `sans`, its certificate would carry another project's `cn` and be
    dropped. That is the safe direction -- a missed alert rather than another
    project's expiry on this surface -- and the rule states that an absent
    certificate series is `unknown` rather than `fine`, so the gap is visible
    where it matters.
    """
    # An identity is interpolated into a regex here, so the charset is asserted
    # rather than trusted. `_TRAEFIK_NAME` is `^[a-z0-9][a-z0-9-]*$` and holds
    # no metacharacter, but this function would still be the place a future
    # identity with a `.` in it became a wildcard.
    for name in router_names:
        if not naming.TRAEFIK_NAME_PATTERN.match(name):
            raise ValueError(
                f"router name {name!r} is not a Traefik name and may not be "
                "interpolated into the scrape filter"
            )
    # The domain is the exception: a hostname's dots are legitimate, so this one
    # is ESCAPED rather than refused. Asserted first all the same -- escaping an
    # unvalidated value would quietly accept whatever it was handed.
    if not _DOMAIN_LABEL.match(domain):
        raise ValueError(
            f"domain {domain!r} is not a hostname and may not be interpolated "
            "into the scrape filter"
        )

    alternation = "|".join(router_names)
    ours = f"({alternation})(@[a-z]+)?"
    cn = re.escape(domain)
    return f"{ours};.*;.*|.*;{ours};.*|.*;.*;{cn}"


def build_otel_config(router_names: tuple[str, ...], domain: str) -> bytes:
    """The metrics collector's configuration (ADR 0164, ADR 0167).

    **It took no project until Run 4, and now it does.** The reversal is the
    scrape filter and nothing else: the OTLP endpoints and the exporter's
    address are still identical in every deployment, but a collector that
    scrapes the SHARED edge is reading a surface that describes every project on
    the host, and what it may keep off that surface is per project by
    definition. The route in front of the collector is still where the
    authorisation lives; this is where the *attribution* does.

    Two receivers now, and they answer different questions:

      * **`otlp`** -- what this project's own processes report about themselves.
        Run 3's transport, carrying Run 4's metric set.
      * **`prometheus`** -- what the shared edge observed about this project's
        routes. The edge is the only place a request's status and duration are
        seen by something other than the service being asked, which is why this
        is worth a scrape at all rather than more instrumentation.

    **The scrape target holds no credential.** Traefik's exposition endpoint is
    unauthenticated on an entrypoint reachable only from the project edge
    networks the proxy is attached to, exactly as `ping` already is. And the
    direction is the one that already existed: Traefik has reached this
    collector since Run 2, because the route points at it.

    Still true, and still the second half of ADR 0164:

      * **no exporter to anywhere off the host.** The `prometheus` exporter
        serves an endpoint and initiates no connection. The database container's
        egress is this deployment's one named residual (ADR 0147) and Session 14
        does not add a second. A scrape inside the edge network is not egress.

    The exporter's endpoint is `0.0.0.0` inside the container, which is the
    container's own network namespace and not the host's -- the port reaches the
    edge network and nothing publishes it. The route in front of it is what
    decides who may read it, and that decision is a middleware, not a bind
    address.
    """
    keep = _scrape_keep_regex(router_names, domain)
    lines = [
        "# GENERATED by agentic_postgres.rendering. Do not edit by hand.",
        "#",
        "# The metrics collector's pipeline (ADR 0164, ADR 0167). It receives",
        "# OTLP from this project's own processes, scrapes the shared edge for",
        "# what the edge observed about this project's routes, and serves",
        "# Prometheus exposition at /metrics. It exports nowhere and holds no",
        "# credential.",
        "",
        "receivers:",
        "  otlp:",
        "    protocols:",
        "      grpc:",
        f"        endpoint: 0.0.0.0:{runtime_override.OTEL_OTLP_GRPC_PORT}",
        "      http:",
        f"        endpoint: 0.0.0.0:{runtime_override.OTEL_OTLP_HTTP_PORT}",
        "  prometheus:",
        "    config:",
        "      scrape_configs:",
        "        - job_name: edge",
        f"          scrape_interval: {runtime_override.OTEL_EDGE_SCRAPE_INTERVAL_SECONDS}s",
        "          static_configs:",
        "            - targets:",
        f'                - "{host_config.EDGE_PROXY_ALIAS}:{host_config.EDGE_METRICS_PORT}"',
        "          metric_relabel_configs:",
        "            # An ENUMERATION of this project's routers, not a prefix.",
        "            # A project key permits hyphens, so `alpha` and `alpha-two`",
        "            # are both lawful on one shared edge and `apg-alpha-.*`",
        "            # matches both -- measured, at twenty of another project's",
        "            # series admitted onto this one's surface. The prefix form",
        "            # is kept as that proof's control because it must still",
        "            # leak (ADR 0167).",
        "            #",
        "            # `up` and the `scrape_*` series are NOT filterable here:",
        "            # the receiver synthesises them after metric_relabel_configs",
        "            # runs, measured. That matters, because they are the only",
        "            # thing that distinguishes a route nobody used from an edge",
        "            # nobody could reach -- and both are an absent series.",
        "            - source_labels: [router, service, cn]",
        # SINGLE-quoted, and this is not a style choice. A regex is not a YAML
        # string: the domain branch is `re.escape`d, so it carries `\.` and
        # `\-`, and a double-quoted YAML scalar processes backslash escapes --
        # `\-` is not one, and the collector refuses the whole document with
        # "found unknown escape character" and exits before it serves anything.
        # A single-quoted scalar performs no escape processing at all, which is
        # what a regex needs. Measured: the double-quoted form would not start.
        f"              regex: '{keep}'",
        "              action: keep",
        "",
        "processors:",
        "  # A hard stop inside the process, beneath the container limit ADR",
        "  # 0165 requires. The container limit is what the collector SIZES",
        "  # itself from; this is what makes it refuse work rather than grow",
        "  # into the limit and be killed by a kernel that picks its own victim.",
        "  memory_limiter:",
        "    check_interval: 1s",
        f"    limit_mib: {runtime_override.OTEL_MEMORY_LIMIT_MIB}",
        f"    spike_limit_mib: {runtime_override.OTEL_SPIKE_LIMIT_MIB}",
        "  batch:",
        "    timeout: 5s",
        "",
        "exporters:",
        "  prometheus:",
        f"    endpoint: 0.0.0.0:{runtime_override.OTEL_EXPORTER_PORT}",
        "    # Explicit, because the default is five minutes and five minutes is",
        "    # how long a dead emitter's last value goes on reading as current.",
        "    # Measured: with the emitter stopped, the default pipeline still",
        "    # served its gauge at t+40s; a collector configured this way dropped",
        "    # it between t+5s and t+10s, so the two are distinguishable and this",
        "    # is a setting rather than a hope.",
        "    #",
        "    # It bounds a SILENCE, not a rate. An OTLP series is refreshed every",
        "    # export interval whether or not anything happened -- a cumulative",
        "    # counter re-exports the same number -- so a series only stops being",
        "    # refreshed when the process emitting it has stopped. That is what",
        "    # this is allowed to notice, and the several missed intervals of",
        "    # slack are so it notices a dead process and not a slow one.",
        f"    metric_expiration: {runtime_override.OTEL_METRIC_EXPIRATION_SECONDS}s",
        "",
        "service:",
        "  telemetry:",
        "    logs:",
        "      # The collector's own logs reach the same place every other",
        "      # container's do. `warn` because an info-level collector narrates",
        "      # every pipeline start, and a log nobody reads is a log that",
        "      # hides the one line that mattered.",
        "      level: warn",
        "  pipelines:",
        "    metrics:",
        "      receivers: [otlp, prometheus]",
        "      processors: [memory_limiter, batch]",
        "      exporters: [prometheus]",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def build_prometheus_config() -> bytes:
    """The store's configuration (ADR 0168).

    **It takes no project, and unlike `build_otel_config` it stays that way.**
    The store scrapes exactly one target -- this project's own collector, on the
    project's own network, under a name Compose gives it -- and every value here
    is identical in every deployment. The per-project attribution was already
    done upstream, by the collector's `metric_relabel_configs`: what reaches this
    store is this project's series and nothing else, so there is nothing left
    here to filter and no identity to derive.

    **The store is a consumer of the collector's exposition, exactly as ADR 0164
    §3 describes** -- which is what keeps it holding no edge credential. It
    scrapes over the project's own network and carries no router label, so it is
    reachable from nothing outside the deployment and is routed nowhere.

    `evaluation_interval` is deliberately equal to `scrape_interval`. Evaluating
    faster than the data arrives re-evaluates identical samples and moves a
    `for:` clock against no new evidence; evaluating slower delays every alert by
    the difference for no benefit.
    """
    lines = [
        "# GENERATED by agentic_postgres.rendering. Do not edit by hand.",
        "#",
        "# The metrics store (ADR 0168). It scrapes this project's collector and",
        "# evaluates this project's alert rules. It is routed nowhere, holds no",
        "# credential, and initiates no connection off the host.",
        "",
        "global:",
        f"  scrape_interval: {runtime_override.STORE_SCRAPE_INTERVAL_SECONDS}s",
        f"  evaluation_interval: {runtime_override.STORE_SCRAPE_INTERVAL_SECONDS}s",
        "",
        "rule_files:",
        f"  - {runtime_override.STORE_RULES_CONTAINER_PATH}",
        "",
        "scrape_configs:",
        "  - job_name: collector",
        "    # The collector is a CARRIER, not an origin: most of what it serves",
        "    # was scraped from the proxy or pushed by the agent plane, and each",
        "    # of those already carries its own `job` and `instance`.",
        "    #",
        "    # The default (`false`) renames every conflicting label to",
        "    # `exported_job` / `exported_instance` and stamps `job=collector` on",
        '    # top. Measured, and it is not cosmetic: it made `up{job="collector"}`',
        "    # match TWO series -- the store's own scrape of the collector, and",
        "    # the collector's forwarded scrape of the proxy -- so one rule fired",
        "    # for two different failures and named the wrong one. **The store",
        "    # cannot reach the collector** and **the collector cannot reach the",
        "    # proxy** are different sentences with different remedies.",
        "    #",
        "    # With this on, the forwarded series keep `job: edge` and the agent",
        "    # plane's keep `job: apg-mcp`, so each hop has its own `up` and each",
        "    # gets its own rule.",
        "    honor_labels: true",
        "    static_configs:",
        "      - targets:",
        f'          - "{runtime_override.METRICS_SERVICE}:{runtime_override.OTEL_EXPORTER_PORT}"',
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def build_alert_rules() -> bytes:
    """This project's alert rules (ADR 0168), `OPS-ALERT-001`.

    **Every threshold is read from the decision that owns it**, which is ADR
    0167's rule applied inside a rule file. `diagnosis.TLS_WARN_DAYS` has owned
    "how many days before a certificate deadline matters" since Session 11, and
    a rule file spelling `21` would be a second authority on it -- one that
    could not be found by anybody grepping for the constant.

    **Every rule states what it means by an ABSENT series** (D769), because a
    rule over a series that does not exist evaluates to nothing and reports
    healthy for ever. Three things produce an absent series here and they are not
    the same event: nothing has happened yet, the emitter has stopped, and the
    series was never published at all.

    **What is NOT here is most of the plan's list**, and it is a decision rather
    than an omission: Run 4 did not build backup, WAL, disk, pooler or
    connection metrics, each for a reason recorded there. **A rule over a series
    no deployment publishes is silent in exactly the way a healthy deployment
    is**, so writing one would produce a rule set that looks complete and
    measures a third of what it names. `OPS-ALERT-001` reports the classes that
    have a series, and the plan says which do not.
    """
    lines = [
        "# GENERATED by agentic_postgres.rendering. Do not edit by hand.",
        "#",
        "# `OPS-ALERT-001` (ADR 0168). Every threshold is read from the decision",
        "# that owns it, and every rule states what an absent series means.",
        "#",
        "# Nothing here pages anybody. There is no Alertmanager in this",
        "# deployment and no receiver configured: a rule with no measured",
        "# false-positive rate is not a rule anybody should be woken by, and",
        "# routing one to a human is a later decision (plan section 4.4).",
        "",
        "groups:",
        "  - name: apg",
        f"    interval: {runtime_override.STORE_SCRAPE_INTERVAL_SECONDS}s",
        "    rules:",
        "",
        "      # HOP 1: the store cannot reach this project's collector.",
        "      #",
        "      # Two hops carry this project's metrics -- store to collector, and",
        "      # collector to proxy -- and they fail for different reasons with",
        "      # different remedies. They are separate rules because a single",
        "      # `up` rule was MEASURED to conflate them: without honor_labels",
        "      # the forwarded `up` is restamped `job=collector` too, so one rule",
        "      # matched both series and named whichever it happened to catch.",
        "      #",
        "      # ABSENT SERIES: cannot happen while the store has this target",
        "      # configured -- `up` is synthesised on every scrape, success or",
        "      # failure. Its disappearance is a third failure, below.",
        "      - alert: ApgCollectorUnreachable",
        '        expr: up{job="collector"} == 0',
        f"        for: {runtime_override.ALERT_FOR_SECONDS}s",
        "        labels:",
        "          severity: warning",
        "        annotations:",
        "          summary: >-",
        "            The metrics store cannot scrape this project's collector.",
        "            Nothing is being recorded. The deployment itself may be",
        "            entirely healthy -- this is a failure of the observation,",
        "            not of the thing observed.",
        "",
        "      # HOP 2: the collector cannot reach the shared proxy.",
        "      #",
        "      # This one IS about the deployment: the proxy is the edge every",
        "      # project's ingress passes through. It is forwarded through the",
        "      # collector rather than measured here, which is why it needs",
        "      # honor_labels to keep its own `job` (ADR 0168).",
        "      #",
        "      # ABSENT SERIES: means the collector is not scraping at all, which",
        "      # hop 1 reports. If both are quiet and no route series exist, read",
        "      # hop 1's rule first.",
        "      - alert: ApgEdgeUnreachable",
        '        expr: up{job="edge"} == 0',
        f"        for: {runtime_override.ALERT_FOR_SECONDS}s",
        "        labels:",
        "          severity: warning",
        "        annotations:",
        "          summary: >-",
        "            This project's collector cannot scrape the shared edge",
        "            proxy. Route metrics stop; ingress may still be working.",
        "",
        "      # The scrape configuration is gone, or the store is not evaluating.",
        "      #",
        "      # A SEPARATE rule again, because the measurement said so: with a",
        "      # configured target stopped, `up` becomes **0, not absent**, so",
        "      # `absent()` did NOT fire and the comparison did. Assuming one",
        "      # rule covers both is the assumption this run had backwards.",
        "      #",
        "      # ABSENT SERIES: that IS the condition. This is the only rule here",
        "      # that fires on absence rather than in spite of it, and it is the",
        "      # one that catches every other rule being quiet for the wrong",
        "      # reason.",
        "      - alert: ApgStoreScrapeMissing",
        '        expr: absent(up{job="collector"})',
        f"        for: {runtime_override.ALERT_FOR_SECONDS}s",
        "        labels:",
        "          severity: warning",
        "        annotations:",
        "          summary: >-",
        "            The store has no scrape target for this project's collector.",
        "            Nothing is being recorded and every other rule here is quiet",
        "            for the wrong reason.",
        "",
        "      # A certificate deadline that renewal should already have met.",
        "      #",
        "      # The threshold is `diagnosis.TLS_WARN_DAYS`, rendered rather than",
        "      # spelled, because that constant already owns this question: 21",
        '      # days, chosen so the rule means "renewal should have happened and',
        '      # did not" rather than "renewal is due".',
        "      #",
        "      # ABSENT SERIES: means UNKNOWN, not fine. Traefik publishes this",
        "      # family only once a certificate is loaded (measured, with a",
        "      # control that had none), so before first issuance there is nothing",
        "      # to compare and this rule is silent. A deployment whose",
        "      # certificate never arrives is not reported here -- the route",
        "      # answering at all is what reports that.",
        "      - alert: ApgCertificateExpiringSoon",
        "        expr: >-",
        "          (traefik_tls_certs_not_after - time()) / 86400",
        f"          < {diagnosis.TLS_WARN_DAYS}",
        f"        for: {runtime_override.ALERT_FOR_SECONDS}s",
        "        labels:",
        "          severity: warning",
        "        annotations:",
        "          summary: >-",
        "            A certificate for this project expires in under",
        f"            {diagnosis.TLS_WARN_DAYS} days. Let's Encrypt renews at 30",
        "            days remaining, so renewal should already have happened.",
        "",
        "      # This project's own routes are answering 5xx.",
        "      #",
        "      # A RATIO rather than a count, because a count makes a busy",
        "      # deployment noisier than a quiet one at the same health. The",
        "      # denominator is this project's routers only -- the filter upstream",
        "      # already guarantees that, and it is why this rule needs no",
        "      # project label of its own.",
        "      #",
        "      # ABSENT SERIES: means no request has crossed this route since the",
        "      # exporter started. Traefik publishes a router family only after a",
        "      # request has crossed it (D769), so a quiet deployment has no",
        "      # series here and this rule is silent -- correctly. It reports",
        '      # "requests are failing", never "requests are absent".',
        "      - alert: ApgRouteErrorRateHigh",
        "        expr: >-",
        "          sum by (router) (",
        '            rate(traefik_router_requests_total{code=~"5.."}'
        f"[{runtime_override.ALERT_RATE_WINDOW_SECONDS}s])",
        "          )",
        "          /",
        "          sum by (router) (",
        "            rate(traefik_router_requests_total"
        f"[{runtime_override.ALERT_RATE_WINDOW_SECONDS}s])",
        "          )",
        f"          > {runtime_override.ALERT_ERROR_RATIO}",
        f"        for: {runtime_override.ALERT_FOR_SECONDS}s",
        "        labels:",
        "          severity: warning",
        "        annotations:",
        "          summary: >-",
        "            More than",
        f"            {int(runtime_override.ALERT_ERROR_RATIO * 100)}% of requests to this"
        " route are",
        "            answering 5xx.",
        "",
        "      # The agent plane is failing calls it did not classify.",
        "      #",
        "      # `failed` and not `refused`: a refusal is the boundary working",
        "      # (ADR 0139/0140), and alerting on one would page somebody because",
        "      # an agent asked for something it may not have. `failed` is an",
        "      # exception the tool path did not classify, which is the shape a",
        "      # defect takes here.",
        "      #",
        "      # ABSENT SERIES: means no tool call has failed since the process",
        "      # started -- the counter is created on first use, so a healthy",
        '      # deployment has no `outcome="failed"` series at all rather than a',
        "      # zero. That is the correct silence, and it is the reason this rule",
        "      # asks about a RATE rather than a total: a total that has never",
        "      # existed and a total that stopped growing are the same reading.",
        "      - alert: ApgAgentPlaneFailing",
        "        expr: >-",
        '          rate(agent_tool_calls_total{outcome="failed"}'
        f"[{runtime_override.ALERT_RATE_WINDOW_SECONDS}s]) > 0",
        f"        for: {runtime_override.ALERT_FOR_SECONDS}s",
        "        labels:",
        "          severity: warning",
        "        annotations:",
        "          summary: >-",
        "            Agent tool calls are failing with unclassified exceptions.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _archive_settings(identity: naming.ProjectIdentity, *, backup_enabled: bool) -> dict[str, str]:
    """The three archiving variables, for an enabled project and a disabled one.

    A disabled project renders `off` and a command that cannot succeed, rather
    than an empty string: Compose refuses an empty interpolation exactly as it
    refuses an unset one (D178, ADR 0062), so every project has to carry a
    value. With `archive_mode=off` the postmaster never runs the command, so
    `/bin/false` is a value that is both honest and unreachable.

    The stanza reaches the command line here and nowhere else. It is `naming`'s
    (ADR 0002), and the container assembles nothing -- the same rule ADR 0106
    states for the storage endpoint, applied to a command instead of a URL.
    """
    if not backup_enabled:
        return {
            "POSTGRES_ARCHIVE_MODE": "off",
            "POSTGRES_ARCHIVE_COMMAND": "/bin/false",
            "POSTGRES_ARCHIVE_TIMEOUT": f"{config.ARCHIVE_TIMEOUT_SECONDS}s",
        }
    return {
        "POSTGRES_ARCHIVE_MODE": "on",
        "POSTGRES_ARCHIVE_COMMAND": (
            f"pgbackrest --stanza={identity.backup_stanza} archive-push %p"
        ),
        "POSTGRES_ARCHIVE_TIMEOUT": f"{config.ARCHIVE_TIMEOUT_SECONDS}s",
    }


def build_compose_env(
    identity: naming.ProjectIdentity,
    budget: dict[str, int],
    database: dict[str, Any],
    api: dict[str, Any] | None = None,
    storage: dict[str, Any] | None = None,
    backup: dict[str, Any] | None = None,
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

    # Session 5. `api.rest` is optional (D150), so a manifest without it renders
    # the defaults -- which include `enabled: false` and an empty CORS list. The
    # keys are emitted either way: a service whose environment depended on
    # whether a manifest section existed would be two services wearing one name,
    # and `compose config` would resolve differently depending on which project
    # produced the file.
    api = api or {}
    rest = {**config.API_REST_DEFAULTS, **(api.get("rest") or {})}
    # Defaults merged in for the same reason `rest` merges them: a project that
    # declares no `api.app` section still has to render, and every variable
    # compose.yaml marks `:?required` must therefore have a value (D150, D178).
    app_service = {**config.API_APP_DEFAULTS, **(api.get("app") or {})}
    # Session 7, and merged for the reason `rest` and `app_service` are: the
    # `storage:` section is optional, every key compose.yaml marks `:?required`
    # must have a value whether or not a project declares one, and Compose
    # refuses an EMPTY value as well as an unset one (D178, ADR 0062).
    storage_settings = {**config.STORAGE_DEFAULTS, **(storage or {})}
    backup_settings = {**config.BACKUP_DEFAULTS, **(backup or {})}
    backup_enabled = bool(backup_settings["enabled"])

    values = {
        "COMPOSE_PROJECT_NAME": identity.compose_project_name,
        "EDGE_NETWORK_NAME": identity.edge_network,
        "INTERNAL_NETWORK_NAME": identity.internal_network,
        "BACKUP_NETWORK_NAME": identity.backup_network,
        "POSTGRES_VOLUME_NAME": identity.postgres_volume,
        "STORE_VOLUME_NAME": identity.store_volume,
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
        # Session 10's archiving four (ADR 0144).
        #
        # A project with backups disabled renders `off` and an archive command
        # that refuses rather than an empty string: Compose treats an empty
        # interpolation exactly as it treats an unset one (D178), so the
        # variables must carry a value for every project. `/bin/false` is the
        # honest command for a cluster with nowhere to archive to -- and with
        # `archive_mode=off` the postmaster never runs it.
        #
        # The stanza is interpolated here and nowhere else. `naming` derives it;
        # the image never assembles one (ADR 0002, ADR 0106's rule applied to a
        # command line instead of a URL).
        **_archive_settings(identity, backup_enabled=backup_enabled),
        "MIGRATIONS_TABLE": MIGRATIONS_TABLE,
        "MIGRATION_ROLE_NAME": identity.roles["migration_user"],
        "POSTGRES_SERVICE_HOST": POSTGRES_SERVICE_HOST,
        "PGBOUNCER_SERVICE_HOST": PGBOUNCER_SERVICE_HOST,
        "APG_FIXTURE_USER_A": FIXTURE_USER_A,
        "APG_FIXTURE_USER_B": FIXTURE_USER_B,
        "APG_DISPOSABLE_SCHEMA": PRISMA_FIXTURE_SCHEMA,
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
        "POSTGREST_AUTHENTICATOR_ROLE": identity.roles["postgrest_authenticator"],
        "ANON_ROLE_NAME": identity.roles["anon"],
        "POSTGREST_EXPOSED_SCHEMA": POSTGREST_EXPOSED_SCHEMA,
        # `api.max_rows` is the sole row-limit authority and is required by the
        # schema, so it is read directly rather than defaulted.
        "POSTGREST_MAX_ROWS": str(int(api["max_rows"])) if api else "0",
        "POSTGREST_POOL_SIZE": str(rest["pool_size"]),
        "POSTGREST_POOL_ACQUISITION_TIMEOUT": str(rest["pool_acquisition_timeout_seconds"]),
        "POSTGREST_POOL_MAX_IDLE": str(rest["pool_max_idle_seconds"]),
        "POSTGREST_POOL_MAX_LIFETIME": str(rest["pool_max_lifetime_seconds"]),
        # Comma-joined, which is what PostgREST parses. An empty list renders an
        # empty string -- no cross-origin browser request is permitted -- rather
        # than being omitted, because a project with no REST service still has
        # to render (D150).
        #
        # Emitting it is necessary and was not sufficient, which is D178. This
        # comment used to end "because an unset variable is a required
        # interpolation that fails", and that is true and beside the point:
        # Compose's `${VAR:?err}` refuses an **empty** value as well as an unset
        # one, so the model refused this render too and the first live deploy
        # failed at step 1. The model now spells this one `${VAR?err}`; the
        # reason lives beside it in `compose.yaml`, and
        # `test_no_required_interpolation_names_a_value_that_renders_empty`
        # compares the variables that render empty against the ones the model
        # marks strict.
        "POSTGREST_CORS_ORIGINS": ",".join(rest["allowed_cors_origins"]),
        "JWT_AUDIENCE": identity.jwt_audience,
        "API_REQUEST_BODY_MAX_BYTES": str(rest["request_body_max_bytes"]),
        # Equal to the maximum for P0, so nothing is ever written to disk on the
        # way through. `memRequestBodyBytes` below the maximum makes Traefik
        # spill the remainder to a temporary file, which puts a request body --
        # the one place a caller's data is in the clear at the edge -- onto the
        # filesystem of a container that has no business holding it.
        "API_REQUEST_BODY_MEMORY_BYTES": str(rest["request_body_memory_bytes"]),
        "API_REST_PATH": identity.route_rest_path,
        "DOCS_PAGE_PATH": identity.route_docs_path,
        "DOCS_ROUTER_NAME": identity.docs_router,
        "DOCS_STRIPPREFIX_MIDDLEWARE_NAME": identity.docs_stripprefix_middleware,
        "REST_ROUTER_NAME": identity.rest_router,
        "API_BUFFERING_MIDDLEWARE_NAME": identity.api_buffering_middleware,
        "API_STRIPPREFIX_MIDDLEWARE_NAME": identity.api_stripprefix_middleware,
        "DOCS_CREDENTIAL_MIDDLEWARE_NAME": identity.docs_credential_middleware,
        # Session 14's metrics surface (ADR 0164). All three from `identity`,
        # so the URL the deployed document publishes and the rule the router
        # matches on are one expression evaluated once (ADR 0061, D177).
        "METRICS_PATH": identity.route_metrics_path,
        "METRICS_ROUTER_NAME": identity.metrics_router,
        "METRICS_CREDENTIAL_MIDDLEWARE_NAME": identity.metrics_credential_middleware,
        # Session 6, Run 10. Every one from `identity`, so the URL the deployed
        # document publishes and the rule the router matches on are the same
        # expression evaluated once (ADR 0061, D177).
        "API_APP_PATH": identity.route_app_path,
        "APP_ROUTER_NAME": identity.app_router,
        "APP_BUFFERING_MIDDLEWARE_NAME": identity.app_buffering_middleware,
        "APP_STRIPPREFIX_MIDDLEWARE_NAME": identity.app_stripprefix_middleware,
        "APP_DOCS_PAGE_PATH": identity.route_app_docs_path,
        "APP_DOCS_ROUTER_NAME": identity.app_docs_router,
        "DOCS_ROOT_PATH": naming.DOCS_ROOT_PATH,
        # From `services/auth-api/app/strict_json.py`, through `auth_limits`
        # (ADR 0084). Not a number declared here: the edge and the service
        # enforce the same bound for two different reasons, and two constants
        # would agree exactly until somebody changed one.
        "AUTH_REQUEST_BODY_MAX_BYTES": str(auth_limits.MAX_BODY_BYTES),
        # The issuer, from the same `identity` the audience above comes from.
        # There is no second derivation here and there must not be: a token
        # this service signs and a token PostgREST verifies have to agree on
        # both strings, and the only way to guarantee that is for both to read
        # one authority (ADR 0002).
        "JWT_ISSUER": identity.jwt_issuer,
        "AUTH_SERVICE_ROLE_NAME": identity.roles["auth_service"],
        "AUTH_POOL_SIZE": str(app_service.get("pool_size", config.API_APP_DEFAULTS["pool_size"])),
        # Lowercase `m`, Docker's byte suffix, matching POSTGRES_MEMORY_LIMIT.
        # The unit is attached here rather than in compose.yaml, which cannot
        # concatenate a suffix onto an interpolated value anyway.
        "AUTH_MEMORY_LIMIT": "{}m".format(
            app_service.get("memory_limit_mb", config.API_APP_DEFAULTS["memory_limit_mb"])
        ),
        # Compact JSON with sorted keys, so the value is byte-stable across
        # renders -- `test_render_is_byte_identical_across_processes` compares
        # the whole file and a dict's iteration order would fail it.
        #
        # Only the roles a token may name. The service identities -- the
        # authenticator, the migration user, this service's own role -- are
        # deliberately absent: `scope_registry` refuses to answer for them
        # because "a command that offers the option invites somebody to find
        # out", and a map that listed them would be that offer.
        "AUTH_ROLE_NAMES": json.dumps(
            {
                suffix: identity.roles[suffix]
                for suffix in sorted(scope_registry.ROLE_SCOPES)
                if suffix in identity.roles
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
        # Session 7, Run 2.
        #
        # `storage_service` is read from `identity.roles`, which has carried it
        # since Session 3 -- the role has existed as a NOLOGIN stub all along
        # and Session 7 activates it rather than creating it (D307).
        "STORAGE_SERVICE_ROLE_NAME": identity.roles["storage_service"],
        "STORAGE_POOL_SIZE": str(storage_settings["pool_size"]),
        # Lowercase `m`, Docker's byte suffix, as POSTGRES_MEMORY_LIMIT and
        # AUTH_MEMORY_LIMIT are. The number is provisional and `config` says so.
        "STORAGE_MEMORY_LIMIT": "{}m".format(storage_settings["memory_limit_mb"]),
        # Session 8, Run 4. A CONSTANT rather than a manifest field, which is a
        # smaller promise than `STORAGE_MEMORY_LIMIT` above and deliberately so.
        #
        # The number is `MCP_MEMORY_LIMIT_MB` and it is **inherited, not
        # measured** -- said here for the reason `config` says it of storage's
        # 384: this repository's defect pattern is a value that looked measured
        # and was not. ADR 0082 is the shape the measurement has to take, and it
        # cannot be taken until Run 6 has four tools to profile. **Run 8 owns
        # budgets** and owns this one.
        #
        # Not a manifest field yet, because a manifest field is a published
        # contract with an outputs member and a schema bump behind it, and
        # committing to one before the shape of the agent plane's budget is
        # known would be the wrong half of the promise. When Run 8 measures it,
        # promoting it is a small change; un-publishing a manifest field is not.
        "MCP_MEMORY_LIMIT": f"{MCP_MEMORY_LIMIT_MB}m",
        # Session 8, Run 5. The agent plane's upstream (ADR 0125).
        #
        # The Compose service name and container port, which is how every
        # service on the `internal` network addresses another -- the same two
        # constants `runtime_override` uses to point a Traefik router at this
        # backend, so a change to either moves both readers together rather than
        # leaving one pointing at nothing.
        #
        # **`http`, and inside the internal network only.** There is no TLS on
        # this hop and that is the deployment's shape rather than an oversight:
        # `internal: true` means the network has no route off the host, the two
        # containers are the only members that matter, and terminating TLS
        # between them would need a certificate authority this project does not
        # have and a rotation nobody would run. What travels on it is the
        # caller's own token, which is already a bearer credential over a link
        # the edge terminated TLS for.
        # Half the REST pool, floor one (ADR 0129). A manifest that shrinks
        # the pool shrinks the agent plane's share with it, which is ADR
        # 0070's rule -- a division rather than independent grants -- applied
        # one level out. **The RATIO is a choice and is flagged as one**;
        # what is measured is that the two numbers must move together, and
        # deriving is what makes that true rather than a coincidence two
        # constants maintain until somebody edits one (D264).
        "MCP_MAX_CONCURRENT_READS": str(max(1, int(rest["pool_size"]) // 2)),
        "API_MCP_PATH": identity.route_mcp_path,
        "MCP_ROUTER_NAME": identity.mcp_router,
        "MCP_POSTGREST_URL": (
            f"http://{POSTGREST_SERVICE_HOST}:{runtime_override.REST_SERVICE_PORT}"
        ),
        # Through `naming`, and unconditionally -- not from `identity`, whose
        # storage fields are None when the service is disabled because a
        # rendered document must not name a bucket for a service that is off.
        # Compose refuses an empty value as firmly as an unset one (D178), so a
        # project with storage disabled would not render at all. One derivation,
        # two readers, which is what `storage_bucket_name` exists for.
        "STORAGE_BUCKET": naming.storage_bucket_name(identity.key, storage_settings.get("bucket")),
        "STORAGE_PREFIX": naming.storage_object_prefix(
            identity.key, storage_settings.get("prefix")
        ),
        # The endpoint, derived once (ADR 0106) and handed over finished rather
        # than as two fragments the image would have to reassemble.
        #
        # When storage is disabled there is no account id, and Compose refuses
        # an empty value as firmly as an unset one (D178) -- the same problem
        # STORAGE_BUCKET has three lines above, answered the same way. The
        # placeholder is a reserved-TLD host that resolves to nothing anywhere,
        # so a service that somehow dialled it fails to connect rather than
        # reaching something real. Nothing dials it: the consumer is on the
        # `session7` profile and `project-runtime.sh` does not start it.
        "STORAGE_ENDPOINT": (
            naming.storage_endpoint_url(
                storage_settings["account_id"],
                storage_settings.get("jurisdiction", "default"),
            )
            if storage_settings.get("account_id")
            else "https://storage.disabled.invalid"
        ),
        "STORAGE_UPLOAD_URL_TTL_SECONDS": str(storage_settings["upload_url_ttl_seconds"]),
        "STORAGE_DOWNLOAD_URL_TTL_SECONDS": str(storage_settings["download_url_ttl_seconds"]),
        "STORAGE_MAX_UPLOAD_BYTES": str(storage_settings["max_upload_bytes"]),
        # Session 7, Run 7. From `identity`, so the URL the deployed document
        # publishes and the rule the router matches on are one expression
        # evaluated once (ADR 0061, D177) -- and so the sixteen-character
        # relationship ADR 0108 rests on holds by construction.
        "API_STORAGE_PATH": identity.route_storage_path,
        "STORAGE_ROUTER_NAME": identity.storage_router,
        "STORAGE_BUFFERING_MIDDLEWARE_NAME": identity.storage_buffering_middleware,
        "STORAGE_STRIPPREFIX_MIDDLEWARE_NAME": identity.storage_stripprefix_middleware,
        "STORAGE_CORS_MIDDLEWARE_NAME": identity.storage_cors_middleware,
        # The same sorted list the rendered document publishes, comma-joined --
        # measured to parse into a list by the locked Traefik, read back from
        # its own API rather than inferred from a response header.
        #
        # **It is legitimately EMPTY**, for any project that enables storage and
        # names no browser origins, and an empty list was measured to permit
        # nothing rather than everything. That is why the label references it as
        # `${STORAGE_CORS_ALLOWED_ORIGINS?required}` and not with the `:?` form
        # every other key here uses: the colon form refuses an empty value as
        # firmly as an unset one (D178), and this is the one key whose empty
        # case is meaningful. `POSTGREST_CORS_ORIGINS` has carried the same
        # distinction since Session 5.
        "STORAGE_CORS_ALLOWED_ORIGINS": ",".join(sorted(storage_settings["allowed_cors_origins"])),
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


def write_readable(path: Path, mode: int, payload: bytes) -> None:
    """Create a new file at an explicit mode and flush it to disk.

    `write_private`'s sibling, for the rendered artefacts a **container** reads.
    The mode is a required argument rather than a default: the whole class of
    defect this exists for is a file whose mode nobody stated (D588).
    """
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(handle, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(path, mode)


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
        backup_bucket=project.get("backup", {}).get("bucket"),
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
                build_compose_env(
                    identity,
                    outputs["database"]["budget"],
                    project["database"],
                    project["api"],
                    project.get("storage"),
                    project.get("backup"),
                ),
            )
            # The archiver's configuration, rendered beside `compose.env` and
            # mounted by `runtime_override`. Written for every project: a
            # disabled one still renders a file, because a mount whose source
            # does not exist makes Docker create a DIRECTORY there and the
            # container opens a directory where its config should be (D463).
            backup_block = {**config.BACKUP_DEFAULTS, **(project.get("backup") or {})}
            write_readable(
                staging / runtime_override.PGBACKREST_CONF_FILENAME,
                PGBACKREST_CONF_MODE,
                build_pgbackrest_conf(
                    identity,
                    outputs,
                    # Derived once, here, by the function storage already uses
                    # (ADR 0002, ADR 0106). Empty for a disabled project, whose
                    # rendered file stops before it would be read.
                    naming.storage_endpoint_url(
                        backup_block["account_id"], backup_block["jurisdiction"]
                    )
                    if backup_block["enabled"]
                    else "",
                ),
            )
            # The metrics collector's pipeline (ADR 0164), on the same terms as
            # the archiver's config above and for the same measured reason: a
            # mount whose source does not exist makes Docker create a DIRECTORY
            # there, and the collector then opens a directory where its config
            # should be (D463). Written for every project, including one whose
            # deploy will never start the container -- an override naming a
            # service Compose has not selected is inert, and a conditional write
            # turns "this session is not deployed yet" into "this container will
            # not start" the moment it is.
            write_readable(
                staging / OTEL_CONFIG_FILENAME,
                OTEL_CONFIG_MODE,
                # The routers this project owns, enumerated by `naming` rather
                # than assembled here from the identity's fields. `identity`
                # holds the same eight names, and reading them off it would be
                # a second place that knows what the set is -- which is the
                # thing that goes stale when a ninth route is added (ADR 0002).
                # The domain joined in Run 5: the certificate series is labelled
                # by `cn` and carries no router or service, so the two-branch
                # filter dropped it (ADR 0168).
                build_otel_config(naming.project_router_names(identity.key), identity.domain),
            )
            # The store's configuration and its rules, on the same terms as the
            # collector's config above: written for EVERY project, including one
            # whose deploy will never start the container. A mount whose source
            # does not exist makes Docker create a directory there (D463), and a
            # conditional write turns "this session is not deployed yet" into
            # "this container will not start" the moment it is.
            #
            # Two files rather than one because only the rules change when a
            # threshold moves, and a deploy recreates a container whose mounted
            # content changed (ADR 0155).
            write_readable(
                staging / runtime_override.STORE_CONFIG_FILENAME,
                OTEL_CONFIG_MODE,
                build_prometheus_config(),
            )
            write_readable(
                staging / runtime_override.STORE_RULES_FILENAME,
                OTEL_CONFIG_MODE,
                build_alert_rules(),
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

            # The reviewed surface, copied verbatim. Not generated, not
            # normalized here, not re-derived: `bin/api-contract.py` captures and
            # a human approves, and this is a copy of that approval (ADR 0069).
            # A render that produced its own document would be a second
            # authority on what the API looks like.
            snapshot = staging / SNAPSHOT_FILENAME
            snapshot.write_bytes(CANONICAL_OPENAPI.read_bytes())
            os.chmod(snapshot, SNAPSHOT_MODE)
            refuse_symlink(snapshot)

            # The second surface's document, on identical terms (D226). It is
            # copied whether or not `api.app` is enabled, and that is the same
            # decision `openapi.json` embodies: the runtime override mounts both
            # unconditionally, and Docker answers a mount source that does not
            # exist by creating a **directory** there -- so a conditional copy
            # turns "this project has no application API" into "this
            # documentation container will not start".
            app_snapshot = staging / APP_SNAPSHOT_FILENAME
            app_snapshot.write_bytes(CANONICAL_APP_OPENAPI.read_bytes())
            os.chmod(app_snapshot, SNAPSHOT_MODE)
            refuse_symlink(app_snapshot)

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
