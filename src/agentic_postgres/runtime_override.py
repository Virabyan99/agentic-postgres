"""The router labels Compose cannot interpolate.

`compose.yaml` carries the identity labels and the network hint but neither
`traefik.enable` nor the router and service labels. A router label's *key*
contains the router name, and interpolation inside a label key is not portable
to `COMPOSE_MINIMUM_VERSION` (ADR 0013), so the keys are rendered here — once,
by the only component that holds a host manifest.

Values are deliberately *not* all rendered. `ACME_RESOLVER_NAME` and
`BASELINE_MIDDLEWARE_CHAIN` stay as interpolation references so that they keep
coming from the root-owned runtime env file rather than from the rendered
directory: an operator who can write a project's rendered output must not
thereby be able to change which resolver issues its certificate, or drop the
middleware chain from its routes.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from ipaddress import ip_address
from pathlib import Path
from typing import Any

import yaml

from agentic_postgres.naming import HEALTH_ROUTE_PATH

#: The two services Session 4 publishes on host loopback, and the ports they
#: listen on *inside* the container. The pooler's is the 6432 convention rather
#: than the image's own default of 5432, which Run 1 measured — a publication
#: written against the convention while the daemon listened on the default
#: would map a host port onto nothing.
POOLER_SERVICE = "pgbouncer"
POOLER_SERVICE_PORT = 6432
DATABASE_SERVICE = "postgres"
DATABASE_SERVICE_PORT = 5432

#: The Compose labels that select one project's database container.
#:
#: **`apg.project.key` is NOT among them, and that is the whole of D587.** That
#: label is a first-party one this model applies to six EDGE-FACING services --
#: `edge-probe`, `postgrest`, `docs`, `auth`, `storage`, `mcp` -- and not to
#: `postgres`, `pgbouncer` or `dbmate`. Run 6's `bin/backup.py` selected the
#: database container with it anyway, Run 8's drill copied that selector, and
#: **neither could ever match**: measured on the host, `apg.project.key=alpha-dev`
#: plus `service=postgres` returns 0 containers while the cluster is up and
#: healthy. It went unnoticed because step 6c had never run against a deployment.
#:
#: What is used instead is Compose's own pair, which Compose applies to every
#: container it creates. Measured in the same invocation: the same query with
#: `com.docker.compose.project` returns exactly 1.
#:
#: **This is not D293 returning.** D293 is about
#: `com.docker.compose.project.working_dir`, which is a PATH into a release
#: directory and changes with every release. `com.docker.compose.project` is the
#: project NAME, which `naming.compose_project_name` derives and `outputs.json`
#: publishes -- so the value handed in here comes from the deployed document and
#: is not re-derived (ADR 0002).
COMPOSE_PROJECT_LABEL = "com.docker.compose.project"
COMPOSE_SERVICE_LABEL = "com.docker.compose.service"


def database_container_filters(compose_project_name: str) -> tuple[str, ...]:
    """`docker ps --filter` values selecting one project's database container.

    ``compose_project_name`` is ``outputs.json``'s ``compose.project_name``. Read
    from the document rather than rebuilt from the key: the model deliberately
    does not pin `container_name:` (D55), and a second derivation here would be
    the copy that disagrees.
    """
    if not compose_project_name:
        raise ValueError("compose_project_name is required to select a container")
    return (
        f"label={COMPOSE_PROJECT_LABEL}={compose_project_name}",
        f"label={COMPOSE_SERVICE_LABEL}={DATABASE_SERVICE}",
    )


#: The service in `compose.yaml` that carries the public route.
ROUTED_SERVICE = "edge-probe"

#: Session 5's REST service, and the port it listens on inside its container.
#: 3000 is PostgREST's default `server-port`, which Run 4's `--dump-config`
#: printed; the Compose service does not override it.
REST_SERVICE = "postgrest"
REST_SERVICE_PORT = 3000

#: Session 6's auth service, and the port `uvicorn` binds inside its container.
#:
#: 8080 is not a default: `compose.yaml` sets `APG_LISTEN_PORT: "8080"` and
#: `app/settings.py` requires it. The two agree through
#: `test_the_compose_service_supplies_every_setting_the_service_requires`, and
#: this constant is the third reader -- Traefik needs the container port, and a
#: publication written against a number the process does not bind maps a router
#: onto nothing.
AUTH_SERVICE = "auth"
AUTH_SERVICE_PORT = 8080

#: Session 7's object-storage runtime, and the port it binds.
#:
#: The same image as `auth` in a second mode (ADR 0101), so the port is the same
#: number for the same reason: `compose.yaml` sets `APG_LISTEN_PORT` and the
#: settings module requires it. A separate Compose service rather than a second
#: surface of `auth`, because it authenticates as a different role, holds a
#: different credential, and takes its own share of the connection budget.
STORAGE_SERVICE = "storage"
STORAGE_SERVICE_PORT = 8080

#: Session 8's agent plane, and the port it binds.
#:
#: The same image again, in a third mode (ADR 0121), for the reason the second
#: one exists: a separate service directory could not import `LocalKeySet`, and
#: the fourth verifier acquiring a second key-set parser is how D381 happened to
#: the third. A separate Compose SERVICE, though, because it holds a different
#: set of credentials -- which is to say none at all. It authenticates as
#: nobody, carries no passfile, and forwards the caller's own token.
#:
#: That is why it is **deliberately absent from `POST_BOOTSTRAP_SERVICES`**
#: below, and the absence is the half worth reading: every other application
#: service is in that tuple because it logs in as a role the bootstrap plane
#: must activate first. This one has no role to activate (D410).
MCP_SERVICE = "mcp"
MCP_SERVICE_PORT = 8080

#: Services that cannot start until the bootstrap plane has activated the role
#: they authenticate as (ADR 0063).
#:
#: A property of the *service*, not of a session or a Compose profile. Eleven of
#: the thirteen roles are created NOLOGIN with a null password verifier and stay
#: that way until a session activates them (ADR 0046), and a service holding a
#: correct credential for one of those is refused with `password authentication
#: failed` -- the same message a wrong password gets, which is why the first
#: occurrence took a `pg_roles` query to diagnose rather than a log line.
#:
#: PostgREST is the first long-running service held to a healthcheck that
#: authenticates as a project role, which is why this constant did not exist
#: before. `dbmate` runs on demand after the bootstrap; PgBouncer's healthcheck
#: authenticates as its own admin user rather than as `app_runtime`.
#:
#: Deferring "the profile of the session being deployed" was the obvious
#: alternative and is wrong: a greenfield deploy through a later session would
#: bring this up in the first phase and deadlock exactly as before.
#:
#: `auth` joins the set in Run 10, when it is first started by a deploy. It
#: authenticates as `auth_service`, which migration 0011 creates NOLOGIN and the
#: bootstrap plane activates (D102), and its healthcheck opens a pool and runs a
#: statement -- so an `auth` started before step 6 does not merely fail to serve,
#: it fails its healthcheck and Compose restarts it five times against a role
#: that cannot log in. The message is `password authentication failed`, which is
#: what a *wrong* credential gets, and that is the diagnosis this constant
#: exists to keep nobody from having to make.
#:
#: `storage` joins in Session 7 Run 2, in the same commit as its Compose entry
#: rather than in the run that first starts it (D324). It authenticates as
#: `storage_service`, which is NOLOGIN until the bootstrap plane activates it,
#: so it fails in exactly the shape described above -- and adding a service to
#: `compose.yaml` while leaving this list alone is the mistake the paragraph
#: above exists to prevent, which makes "later" the wrong answer.
#: `mcp` does NOT join, in Session 8 Run 4, and this sentence is the record of
#: the decision rather than of an omission (D410). It holds no database
#: credential at all: `settings.load_mcp` refuses to start if handed one, so
#: there is no role for the bootstrap plane to activate and nothing for it to
#: wait on. Its zero share of ADR 0099's connection budget is the same fact
#: seen from the other side (D407). If a later session gives the agent plane a
#: database identity, this tuple is the first thing that has to move -- and the
#: reason it would have to is written here, where somebody adding one is
#: already standing.
POST_BOOTSTRAP_SERVICES: tuple[str, ...] = (REST_SERVICE, AUTH_SERVICE, STORAGE_SERVICE)

#: Services that cannot start until the deploy has WRITTEN the files they mount
#: (ADR 0133).
#:
#: **A different reason from the tuple above, and the distinction cost the agent
#: plane its first start anywhere** (D463). That one is about a database role the
#: bootstrap plane must activate; this one is about an artefact the deploy
#: produces after step 5. PostgREST needs both, so its membership above satisfied
#: this one by accident and nothing ever separated them. The agent plane needs
#: only this one -- it authenticates as no role (D410) -- so it was correctly
#: excluded above and lost the deferral it did need.
#:
#: What happens without it is not a clean failure: **Docker creates a bind-mount
#: source that does not exist as a DIRECTORY**, so the runtime opened a directory
#: where its key set should be and exited 1. `deploy-project.py` carried a
#: comment naming that exact trap, written for PostgREST.
#:
#: `mcp` mounts two files the deploy writes late: the rendered `jwks.json` it
#: verifies with (ADR 0113) and the compiled capability lock (ADR 0127). Both
#: exist by step 6b and neither exists at step 5.
POST_ARTIFACT_SERVICES: tuple[str, ...] = (MCP_SERVICE,)

#: What `--defer` actually receives: the union of the two reasons.
#:
#: **Computed, never typed.** A third list that had to agree with two others is
#: the shape this repository has paid for (D175, D264) -- and it would go stale
#: in exactly the way the two above did not.
DEFERRED_SERVICES: tuple[str, ...] = tuple(
    sorted(set(POST_BOOTSTRAP_SERVICES) | set(POST_ARTIFACT_SERVICES))
)

#: Session 5's documentation service, the port `serve.py` binds, and the
#: reviewed snapshot it serves.
#:
#: The host side of the mount is per-project and therefore lives here; the
#: container path is fixed, which is what lets `compose.yaml` name it in
#: `APG_DOCS_SNAPSHOT` while staying project-neutral.
DOCS_SERVICE = "docs"
DOCS_SERVICE_PORT = 8080
SNAPSHOT_FILENAME = "openapi.json"
SNAPSHOT_CONTAINER_PATH = "/app/snapshot/openapi.json"

#: Session 14's metrics collector (ADR 0164), its ports, and where its rendered
#: configuration is mounted.
#:
#: `OTEL_EXPORTER_PORT` is the one the edge router's service points at, and it
#: is the only one anything outside the project's networks can reach -- and only
#: through the route, which carries a credential. The two OTLP ports are how
#: this deployment's own services will push telemetry (Run 3); nothing publishes
#: them.
#:
#: **The port numbers are the collector's defaults for OTLP and the exporter's
#: conventional one**, written here rather than left implicit, because the
#: rendered config and the router's `loadbalancer.server.port` have to agree and
#: a default that moved in an upstream release would break them in different
#: places. One constant, two readers -- the rule ADR 0002 states for names,
#: applied to a number.
METRICS_SERVICE = "metrics"
OTEL_EXPORTER_PORT = 8889
OTEL_OTLP_GRPC_PORT = 4317
OTEL_OTLP_HTTP_PORT = 4318
OTEL_CONFIG_FILENAME = "otelcol.yaml"
OTEL_CONFIG_CONTAINER_PATH = "/etc/otelcol/config.yaml"

#: The collector's in-process memory ceiling and its burst allowance, in MiB.
#:
#: **Beneath the container limit, deliberately** (ADR 0165). The container limit
#: is what the collector sizes itself from and what the kernel enforces; this is
#: what makes the process refuse work at a threshold it chooses, rather than
#: grow into the limit and be killed by a kernel that picks its own victim on a
#: host with no swap. Measured under a 128 MiB cap the collector held 31.1 MB
#: anon, so 96 is a ceiling it has room beneath rather than a target it runs at.
OTEL_MEMORY_LIMIT_MIB = 96
OTEL_SPIKE_LIMIT_MIB = 24

#: What the container limit is set to, and the number ADR 0165 requires to
#: exist. Above `OTEL_MEMORY_LIMIT_MIB` so the in-process limiter is what binds
#: first: a process killed by its cgroup leaves no explanation, and one that
#: refuses work says so in its own log.
METRICS_MEMORY_LIMIT_MB = 128

#: The Compose key that carries the container path into `serve.py`. Named
#: here so the model and this module agree through one constant rather than
#: two spellings -- and so a test comparing them need not write the literal,
#: which `test_environment_gates.py` would read as an environment variable
#: the test consumes.
SNAPSHOT_ENV_KEY = "APG_DOCS_SNAPSHOT"

#: PostgreSQL's data directory inside the locked image, and the ONE place this
#: repository states it. Session 10, D514.
#:
#: The volume mounts one level ABOVE this, at `POSTGRES_VOLUME_TARGET`, which is
#: what the image declares as its VOLUME. D53 measured all three candidates: the
#: pre-18 `/var/lib/postgresql/data` makes the image refuse to start, mounting
#: at PGDATA itself works while silently leaving an anonymous volume on the
#: parent, and two of the three persist data -- so "the row survived" does not
#: distinguish them.
#:
#: Promoted out of a test constant because Session 10 gave it a second reader:
#: `pgbackrest.conf`'s `pg1-path`. A stanza created against the mount point
#: rather than PGDATA does not fail -- it makes the first restore wrong.
#: `tests/contract/test_image_contracts.py` asserts THIS constant against the
#: running image, so the value the renderer writes is the value that was
#: measured.
POSTGRES_PGDATA = "/var/lib/postgresql/18/docker"
POSTGRES_VOLUME_TARGET = "/var/lib/postgresql"

#: The rendered pgBackRest configuration, and where the archiver reads it.
#:
#: Host side per-project and therefore here, exactly like the JWKS below and for
#: the same reason: the path contains the rendered directory, which does not
#: exist in a checkout and cannot be a `compose.yaml` interpolation.
PGBACKREST_CONF_FILENAME = "pgbackrest.conf"
PGBACKREST_CONF_CONTAINER_PATH = "/etc/pgbackrest/pgbackrest.conf"

#: The rendered JWKS, and where PostgREST reads it.
#:
#: The host side is per-project and lives in this override; the container side is
#: fixed, which is what lets `compose.yaml` carry `PGRST_JWT_SECRET` while
#: staying project-neutral. `bin/render-jwks.py` writes the file (ADR 0051).
JWKS_FILENAME = "jwks.json"
JWKS_CONTAINER_PATH = "/etc/postgrest/jwks.json"

#: Where the SAME rendered file is mounted for the storage runtime (ADR 0113).
#:
#: One artefact, two verifiers, two container paths -- the path differs because
#: each image's convention does, and the file does not. Storage reads it with
#: `LocalKeySet.from_path`; PostgREST reads it through `PGRST_JWT_SECRET`. A
#: second *copy* for storage would be a second authority for one value (D264),
#: and deriving it again inside the image is what ADR 0002 exists to refuse.
#:
#: D381 is why this constant exists at all. Storage was declared the third
#: verifier in ADR 0098, D320, `compose.yaml` and `main.py`, and was given no
#: verification material of any kind -- so its first start on any host raised
#: `AttributeError: 'NoneType' object has no attribute 'jwks'` and exited 3.
STORAGE_JWKS_CONTAINER_PATH = "/etc/storage/jwks.json"

#: And where the SAME file is mounted for the agent plane (ADR 0113, ADR 0121).
#:
#: **One artefact, four verifiers, three container paths.** PostgREST reads it
#: through `PGRST_JWT_SECRET`; storage and MCP each read it with
#: `LocalKeySet.from_path`, at their own path, because each mode's convention
#: differs and the file does not. The auth service is the fourth reader of the
#: key set and is not a verifier of it -- it is the issuer, and derives its own
#: set from the private half it signs with (ADR 0098).
#:
#: The plan predicted this constant would be the moment to check that ADR 0088's
#: recreate list moved with it (D409). It was, and the answer was worse than
#: predicted: the list had never moved for STORAGE either. See ADR 0122.
MCP_JWKS_CONTAINER_PATH = "/etc/mcp/jwks.json"

#: The compiled capability lock, and where the agent plane reads it.
#:
#: Rendered per project by `bin/mcp-contract.sh lock` during the deploy, into the
#: same directory the key set is rendered into, and mounted read-only here. The
#: container path is fixed so `compose.yaml` can name it while staying
#: project-neutral (ADR 0127).
MCP_LOCK_FILENAME = "mcp-capability-lock.json"
MCP_LOCK_CONTAINER_PATH = "/etc/mcp/capability-lock.json"

#: Container paths a sensitive-named environment key may reference (ADR 0064).
#:
#: `PGRST_JWT_SECRET` is refused by ADR 0008's denylist -- it ends in `_secret`
#: -- and the name is PostgREST's, not ours. Its value is `@` followed by a path,
#: which is a *reference*, and the file it names is public verification material
#: written 0444. So the exemption is not "this variable is fine": it is "this
#: value is a reference, to a path declared here, and not to anything under
#: /run/secrets".
#:
#: Declared beside the mount deliberately. The path a service reads and the path
#: the security rule permits are then one string and cannot drift apart.
PUBLIC_REFERENCE_PATHS: frozenset[str] = frozenset({JWKS_CONTAINER_PATH})

#: `services/edge-probe/probe.py` LISTEN_PORT. Traefik needs the container port;
#: the probe publishes none, because only Traefik publishes a host port.
ROUTED_SERVICE_PORT = 8080

#: The second documentation surface's file inside the snapshot mount (D226).
#:
#: The directory is already mounted for `openapi.json`; this is a second file in
#: it, not a second mount and not a second container. One image, one CSP, one
#: credential.
APP_SNAPSHOT_FILENAME = "app-openapi.json"
APP_SNAPSHOT_CONTAINER_PATH = "/app/snapshot/app-openapi.json"

#: The Compose key that carries the second surface's container path into
#: `serve.py`, named here for the reason `SNAPSHOT_ENV_KEY` is.
APP_SNAPSHOT_ENV_KEY = "APG_DOCS_APP_SNAPSHOT"

#: The migration plane's service, and where its rendered set appears inside it.
#: The path is the one `compose.yaml` passes to `--migrations-dir`; the two
#: living in two files is exactly how dbmate ends up reporting "no migrations
#: found" against a directory that has five.
MIGRATION_SERVICE = "dbmate"
MIGRATIONS_MOUNT = "/migrations"

__all__ = [
    "APP_SNAPSHOT_CONTAINER_PATH",
    "APP_SNAPSHOT_ENV_KEY",
    "APP_SNAPSHOT_FILENAME",
    "AUTH_SERVICE",
    "AUTH_SERVICE_PORT",
    "DATABASE_SERVICE",
    "DATABASE_SERVICE_PORT",
    "DEFERRED_SERVICES",
    "JWKS_CONTAINER_PATH",
    "JWKS_FILENAME",
    "MCP_JWKS_CONTAINER_PATH",
    "MCP_LOCK_CONTAINER_PATH",
    "MCP_LOCK_FILENAME",
    "MCP_SERVICE",
    "MCP_SERVICE_PORT",
    "MIGRATIONS_MOUNT",
    "MIGRATION_SERVICE",
    "MOUNT_DIGEST_LABEL",
    "MOUNT_OVERRIDE_FILENAME",
    "POOLER_SERVICE",
    "POOLER_SERVICE_PORT",
    "POST_ARTIFACT_SERVICES",
    "POST_BOOTSTRAP_SERVICES",
    "PUBLIC_REFERENCE_PATHS",
    "REST_SERVICE",
    "REST_SERVICE_PORT",
    "ROUTED_SERVICE",
    "ROUTED_SERVICE_PORT",
    "STORAGE_CORS_METHODS",
    "STORAGE_JWKS_CONTAINER_PATH",
    "STORAGE_SERVICE",
    "STORAGE_SERVICE_PORT",
    "build_mount_override",
    "build_override",
    "is_loopback",
    "mount_sources",
    "mounted_digest",
    "mounted_paths_by_service",
    "override_service_names",
    "publication",
    "render_mount_override",
    "render_override",
]


def publication(*, address: str, port: int, container_port: int) -> dict[str, Any]:
    """Refused. Nothing is published (ADR 0044).

    This built a long-syntax `ports:` entry until Run 9, when the host proved
    that Docker installs no DNAT rule and no listener for a container on an
    `internal: true` network -- it accepts the request, records
    `HostConfig.PortBindings`, and does nothing. The transports are reached by
    an SSH forward to the container's own address on the host's bridge, so no
    host port exists to bind at all.

    Kept as a refusal rather than deleted. The signature is what a future reader
    reaches for when they want to publish a database port, and finding it raise
    with the reason is worth more than finding nothing and writing it again.
    """
    del address, port, container_port
    raise RuntimeError(
        "nothing is published (ADR 0044). A container on an internal network gets "
        "no DNAT rule and no listener, and the transports are reached through an "
        "SSH forward to the container's address on the host's own bridge. There is "
        "no host port, which is why there is no bind address to get wrong."
    )


def is_loopback(address: str) -> bool:
    """127.0.0.0/8 or ::1, and nothing else.

    Written as a real address comparison rather than a `startswith("127.")`,
    because `1270.0.0.1` starts with `127.` and `::1` does not.
    """
    try:
        return ip_address(address).is_loopback
    except ValueError:
        return False


def build_override(
    *,
    router_name: str,
    https_entrypoint: str,
    rendered_directory: str,
    rest_router_name: str,
    buffering_middleware_name: str,
    stripprefix_middleware_name: str,
    docs_router_name: str,
    docs_auth_middleware_name: str,
    docs_stripprefix_middleware_name: str,
    app_router_name: str,
    app_buffering_middleware_name: str,
    app_stripprefix_middleware_name: str,
    app_docs_router_name: str,
    storage_router_name: str,
    storage_buffering_middleware_name: str,
    storage_stripprefix_middleware_name: str,
    storage_cors_middleware_name: str,
    mcp_router_name: str,
    metrics_router_name: str,
    metrics_auth_middleware_name: str,
    publications: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the override document for one project's health route and migrations.

    Two deploy-time facts, in the file the deploy writes. The rendered
    directory's *path* is one of them: it is stable for the life of the
    deployment, unlike the secret generation, which is superseded on every
    start and therefore lives in the override `bin/project-runtime.sh` rewrites.
    Putting a per-start value in this file would leave dbmate reading whatever
    directory the last deploy happened to name.

    ``publications`` is the allocated pair, or ``None`` before one exists. It is
    optional because a project is deployed before it is published — the
    allocation key is the instance UUID the volume carries, and on a first
    deploy that UUID does not exist until the cluster has bootstrapped. So the
    first `up` publishes nothing and a later privileged render adds it, which is
    also what makes the publication re-runnable on its own.

    **This file is the only place a database publication may be written.** The
    committed model carries no `ports`, so a repository that could publish a
    database port would be one clone away from publishing one.
    """
    if not router_name:
        raise ValueError("router_name is required")
    if not rest_router_name:
        raise ValueError("rest_router_name is required")
    if not buffering_middleware_name:
        raise ValueError("buffering_middleware_name is required")
    if not stripprefix_middleware_name:
        raise ValueError("stripprefix_middleware_name is required")
    if not docs_router_name:
        raise ValueError("docs_router_name is required")
    if not docs_auth_middleware_name:
        raise ValueError("docs_auth_middleware_name is required")
    if not docs_stripprefix_middleware_name:
        raise ValueError("docs_stripprefix_middleware_name is required")
    if not app_router_name:
        raise ValueError("app_router_name is required")
    if not app_buffering_middleware_name:
        raise ValueError("app_buffering_middleware_name is required")
    if not app_stripprefix_middleware_name:
        raise ValueError("app_stripprefix_middleware_name is required")
    if not app_docs_router_name:
        raise ValueError("app_docs_router_name is required")
    if not storage_router_name:
        raise ValueError("storage_router_name is required")
    if not storage_buffering_middleware_name:
        raise ValueError("storage_buffering_middleware_name is required")
    if not storage_stripprefix_middleware_name:
        raise ValueError("storage_stripprefix_middleware_name is required")
    if not storage_cors_middleware_name:
        raise ValueError("storage_cors_middleware_name is required")
    if not metrics_router_name:
        raise ValueError("metrics_router_name is required")
    if not metrics_auth_middleware_name:
        raise ValueError("metrics_auth_middleware_name is required")
    if not https_entrypoint:
        raise ValueError("https_entrypoint is required")
    if not rendered_directory or not rendered_directory.startswith("/"):
        raise ValueError("rendered_directory must be an absolute path")

    router = f"traefik.http.routers.{router_name}"
    service = f"traefik.http.services.{router_name}"

    published: dict[str, Any] = {}
    if publications is not None:
        address = publications["address"]
        published = {
            POOLER_SERVICE: {
                "ports": [
                    publication(
                        address=address,
                        port=publications["pooled_port"],
                        container_port=POOLER_SERVICE_PORT,
                    )
                ]
            },
            DATABASE_SERVICE: {
                "ports": [
                    publication(
                        address=address,
                        port=publications["direct_port"],
                        container_port=DATABASE_SERVICE_PORT,
                    )
                ]
            },
        }

    return {
        "services": {
            **published,
            # Read-only, and the only thing dbmate is given besides its
            # credential. It runs one command against one schema; a writable
            # mount would let a migration rewrite the set that produced it.
            # The archiver's configuration. Read-only, and the cluster's only
            # mount besides its own data volume.
            #
            # Written by the render at step 4, which is BEFORE step 5 starts
            # this container -- so `postgres` is not in `POST_ARTIFACT_SERVICES`
            # and does not need to be. What makes that safe rather than lucky is
            # `require_mounts_exist(..., when="step 5")`, which refuses a
            # missing source instead of letting Docker create a DIRECTORY there
            # and the container open a directory where its config should be
            # (D463, ADR 0133).
            DATABASE_SERVICE: {
                "volumes": [
                    f"{rendered_directory}/{PGBACKREST_CONF_FILENAME}"
                    f":{PGBACKREST_CONF_CONTAINER_PATH}:ro"
                ]
            },
            MIGRATION_SERVICE: {
                "volumes": [f"{rendered_directory}/migrations:{MIGRATIONS_MOUNT}:ro"]
            },
            ROUTED_SERVICE: {
                "labels": {
                    "traefik.enable": "true",
                    f"{router}.rule": (
                        f"Host(`${{PROJECT_DOMAIN:?required}}`) && Path(`{HEALTH_ROUTE_PATH}`)"
                    ),
                    f"{router}.entrypoints": https_entrypoint,
                    f"{router}.tls.certresolver": "${ACME_RESOLVER_NAME:?required}",
                    f"{router}.middlewares": "${BASELINE_MIDDLEWARE_CHAIN:?required}",
                    f"{router}.service": router_name,
                    f"{service}.loadbalancer.server.port": str(ROUTED_SERVICE_PORT),
                }
            },
            REST_SERVICE: {
                "labels": _rest_labels(
                    https_entrypoint=https_entrypoint,
                    rest_router_name=rest_router_name,
                    buffering_middleware_name=buffering_middleware_name,
                    stripprefix_middleware_name=stripprefix_middleware_name,
                ),
                # The verification-only JWKS, derived from the bootstrap signing
                # key by `bin/render-jwks.py` at deploy time (ADR 0051).
                #
                # Here rather than in `compose.yaml` because the host side is a
                # per-project absolute path, and the model must stay
                # project-neutral: `bin/compose.sh` passes `--file` with no
                # `--project-directory`, so a relative source in the model would
                # resolve against the *release* and every project would mount one
                # file. The container side is fixed, which is why
                # `PGRST_JWT_SECRET` can live in the model.
                #
                # Read-only, and public: this is a modulus, an exponent, an
                # algorithm and a thumbprint. Nothing here can sign, which is the
                # property that lets a verifier hold it at all.
                "volumes": [f"{rendered_directory}/{JWKS_FILENAME}:{JWKS_CONTAINER_PATH}:ro"],
            },
            DOCS_SERVICE: {
                # Two routers onto one container (D226). The second surface is
                # a second file in the mount below and a second entry in
                # `serve.py`'s route table -- not a second image, a second CSP
                # or a second credential.
                "labels": {
                    **_docs_labels(
                        https_entrypoint=https_entrypoint,
                        docs_router_name=docs_router_name,
                        docs_auth_middleware_name=docs_auth_middleware_name,
                        docs_stripprefix_middleware_name=docs_stripprefix_middleware_name,
                    ),
                    **_app_docs_labels(
                        https_entrypoint=https_entrypoint,
                        app_docs_router_name=app_docs_router_name,
                        docs_auth_middleware_name=docs_auth_middleware_name,
                        docs_stripprefix_middleware_name=docs_stripprefix_middleware_name,
                    ),
                },
                # The two reviewed snapshots, read-only. The page serves these
                # bytes and nothing else; `contracts/postgrest-openapi.canonical
                # .json` and `contracts/app-openapi.canonical.json` are what a
                # human approved and the render copies them here.
                "volumes": [
                    f"{rendered_directory}/{SNAPSHOT_FILENAME}:{SNAPSHOT_CONTAINER_PATH}:ro",
                    f"{rendered_directory}/{APP_SNAPSHOT_FILENAME}"
                    f":{APP_SNAPSHOT_CONTAINER_PATH}:ro",
                ],
            },
            # Session 14's metrics collector (ADR 0164). One router onto it, and
            # the container it fronts holds no credential of any kind -- the
            # password guarding the route is a bcrypt hash in the edge's
            # dynamic document, and `secrets.required.yaml` declares it with a
            # root-plane consumer only. A compose consumer here would be a
            # container holding the password to its own front door, which is the
            # sentence `docs` already carries and the reason it is repeated.
            #
            # The config is mounted from the rendered directory rather than the
            # release, so what a deployment runs is pinned to what it rendered.
            # It is written at RENDER time, which is why this service is not in
            # `POST_ARTIFACT_SERVICES`: the file exists before any container
            # starts. Confusing that with `mcp`'s late-written artefacts is
            # D463, and the cost was the agent plane's first start anywhere.
            METRICS_SERVICE: {
                "labels": _metrics_labels(
                    https_entrypoint=https_entrypoint,
                    metrics_router_name=metrics_router_name,
                    metrics_auth_middleware_name=metrics_auth_middleware_name,
                ),
                "volumes": [
                    f"{rendered_directory}/{OTEL_CONFIG_FILENAME}:{OTEL_CONFIG_CONTAINER_PATH}:ro",
                ],
            },
            AUTH_SERVICE: {
                "labels": _app_labels(
                    https_entrypoint=https_entrypoint,
                    app_router_name=app_router_name,
                    app_buffering_middleware_name=app_buffering_middleware_name,
                    app_stripprefix_middleware_name=app_stripprefix_middleware_name,
                )
            },
            # Session 7 Run 7. A separate Compose service from `auth` rather than
            # a second router onto it (which is what `docs` does for its two
            # surfaces): storage authenticates as a different role, holds a
            # different credential and takes its own share of the connection
            # budget, so the two containers have to be separable.
            #
            # The entry is written unconditionally, exactly as the four above
            # are. Whether the container exists is `profiles: [session7]`'s
            # question, and an override naming a service Compose has not
            # selected is inert -- which is what has let this file describe the
            # `auth` service since Run 10 for deployments that never started it.
            STORAGE_SERVICE: {
                "labels": _storage_labels(
                    https_entrypoint=https_entrypoint,
                    storage_router_name=storage_router_name,
                    storage_buffering_middleware_name=storage_buffering_middleware_name,
                    storage_stripprefix_middleware_name=storage_stripprefix_middleware_name,
                    storage_cors_middleware_name=storage_cors_middleware_name,
                ),
                # The third verifier's key set (ADR 0113). The SAME per-project
                # file `postgrest` is given above, at a different container
                # path, read-only, and public by construction: a modulus, an
                # exponent, an algorithm and a thumbprint. Nothing here can
                # sign, which is the property that lets a verifier hold it.
                #
                # Here rather than in `compose.yaml` for the same reason the
                # REST mount is: the host side is a per-project absolute path
                # and the model must stay project-neutral.
                "volumes": [
                    f"{rendered_directory}/{JWKS_FILENAME}:{STORAGE_JWKS_CONTAINER_PATH}:ro"
                ],
            },
            # Session 8 Run 4. The agent plane, and the entry exists for exactly
            # one reason: **the fourth verifier's key set** (ADR 0113, ADR 0121).
            #
            # No labels. The router is Run 7's, for the reason `storage` gives
            # above -- a label set that published `/mcp` before anything
            # answered it would route to a container that 404s, and Traefik's
            # own 404 is indistinguishable from a routed one except by a 19-byte
            # body (D186, D187, D353).
            #
            # D381 is the whole of why this mount is written in the same run
            # that declares the verifier rather than in the run that publishes
            # it. Storage was named the third verifier in four places and handed
            # nothing to verify with, and the gap was invisible until a
            # container started somewhere real.
            MCP_SERVICE: {
                "labels": _mcp_labels(
                    https_entrypoint=https_entrypoint,
                    mcp_router_name=mcp_router_name,
                ),
                "volumes": [
                    f"{rendered_directory}/{JWKS_FILENAME}:{MCP_JWKS_CONTAINER_PATH}:ro",
                    # The compiled capability lock -- the whole of what this
                    # deployment's tools serve, and the roster they are
                    # enumerated from (ADR 0127).
                    f"{rendered_directory}/{MCP_LOCK_FILENAME}:{MCP_LOCK_CONTAINER_PATH}:ro",
                ],
            },
        }
    }


def override_service_names(payload: bytes) -> tuple[str, ...]:
    """Every service the rendered override names.

    Here rather than in the caller for the reason `mount_sources` is: this
    module owns the document's shape, and a `bin/` command that reached into it
    would be a second place that knows the top-level key.
    """
    document = yaml.safe_load(payload.decode("utf-8")) or {}
    return tuple(sorted(document.get("services") or {}))


def mount_sources(payload: bytes, services: Iterable[str]) -> tuple[str, ...]:
    """The host paths `services` bind-mount, read out of the built override.

    **Takes the rendered bytes, not a parsed document.** The deploy holds the
    payload it is about to write, and parsing it here keeps the document's shape
    -- including its top-level key -- knowledge this module has and `bin/` does
    not (D464).

    **Derived, not declared** (ADR 0133). A hand-maintained inventory of mounts
    is precisely the thing that goes stale when a mount is added, which is the
    defect this function exists because of -- so it parses the document the
    deploy is about to write rather than repeating it.

    The `source:destination:mode` form is Compose's short syntax, which is what
    `build_override` emits. Only the source half is returned, and only for the
    named services: at step 5 the deferred services' artefacts do not exist yet
    and asking about them would refuse a correct deploy.
    """
    document = yaml.safe_load(payload.decode("utf-8")) or {}
    wanted = set(services)
    found: dict[str, None] = {}
    for name, service in (document.get("services") or {}).items():
        if name not in wanted:
            continue
        for volume in service.get("volumes") or ():
            # A named volume has no `/` in its source and is not a bind mount;
            # Docker creates one on demand and it is not this check's business.
            source = volume.split(":", 1)[0]
            if source.startswith("/"):
                found[source] = None
    return tuple(sorted(found))


#: The label whose value is a digest of what a service bind-mounts.
#:
#: **This exists so that Compose can see a change it structurally cannot see
#: otherwise** (D591). `install_rendered` ends in `os.replace(staging,
#: destination)` -- a new directory with new inodes -- and `project-runtime up`
#: runs `up -d --build --wait` with no `--force-recreate`. Compose's config hash
#: covers the service *definition*, and a bind mount's source path is the
#: identical string on every deploy, so nothing looks changed and the running
#: container keeps its open file handle on a **deleted inode**.
#:
#: Measured on the host: the installed `pgbackrest.conf` was `-r--r--r--` dated
#: 06:14 while the running container saw `-rw------- 0 root root` dated 05:36 --
#: link count 0, from a container created before two consecutive correct fixes,
#: neither of which could reach it. Three deploys went to that one defect.
#:
#: Compose hashes labels into the config hash, so a service whose mounted bytes
#: changed gets recreated and one whose bytes did not does not. That is the
#: difference between this and `--force-recreate`, which restarts the world on
#: every deploy including the services nothing touched.
MOUNT_DIGEST_LABEL = "apg.mounted.sha256"

#: Written beside the runtime and secret overrides, and regenerated immediately
#: before `up` for the same reason the secret override is: it must describe the
#: files as they are at the moment the containers are created, which is after
#: the deploy has written the late artefacts (`jwks.json`, the snapshots) and
#: after a reboot has changed nothing at all.
MOUNT_OVERRIDE_FILENAME = "mounts-compose.override.yaml"


def mounted_paths_by_service(payload: bytes) -> dict[str, tuple[str, ...]]:
    """Every bind-mount source, per service, out of the rendered override.

    Derived from the document rather than declared (ADR 0133), for the reason
    :func:`mount_sources` gives: a hand-maintained inventory of mounts is
    exactly the thing that goes stale when a mount is added, and a stale
    inventory here means a service whose content changed is silently not
    recreated -- which is the defect this is for.
    """
    document = yaml.safe_load(payload.decode("utf-8")) or {}
    found: dict[str, tuple[str, ...]] = {}
    for name, service in sorted((document.get("services") or {}).items()):
        sources = sorted(
            volume.split(":", 1)[0]
            for volume in (service.get("volumes") or ())
            # A named volume has no leading `/` and is not a bind mount. Its
            # content is not something a deploy replaces underneath a container.
            if volume.split(":", 1)[0].startswith("/")
        )
        if sources:
            found[name] = tuple(sources)
    return found


def mounted_digest(sources: Iterable[str]) -> str:
    """A digest of the CONTENT at `sources`, stable across identical bytes.

    A file contributes its path and its bytes; a directory contributes every
    file under it, sorted. **Path as well as bytes**, so that moving a mount to
    a different destination with identical content still counts as a change --
    the container would have to be recreated for that too.

    A source that does not exist contributes its path and a marker rather than
    raising: at step 5 the deferred services' artefacts do not exist yet
    (`mount_sources` makes the same allowance), and a digest that refused to be
    computed would turn a correct deploy into a failure. Its **absence is part
    of the digest**, so the artefact appearing later changes the value and the
    container is recreated then.
    """
    digest = hashlib.sha256()
    for source in sorted(sources):
        path = Path(source)
        digest.update(source.encode("utf-8"))
        digest.update(b"\0")
        if path.is_dir():
            for child in sorted(p for p in path.rglob("*") if p.is_file()):
                digest.update(str(child.relative_to(path)).encode("utf-8"))
                digest.update(b"\0")
                digest.update(child.read_bytes())
        elif path.is_file():
            digest.update(path.read_bytes())
        else:
            digest.update(b"<absent>")
        digest.update(b"\0")
    return digest.hexdigest()


def build_mount_override(payload: bytes) -> dict[str, Any]:
    """One label per service that bind-mounts anything, keyed by its content."""
    services = {
        name: {"labels": {MOUNT_DIGEST_LABEL: mounted_digest(sources)}}
        for name, sources in mounted_paths_by_service(payload).items()
    }
    return {"services": services}


def render_mount_override(payload: bytes) -> bytes:
    """The document Compose reads, with the reason it exists at the top."""
    header = (
        "# Generated by bin/project-runtime.sh from the runtime override.\n"
        "# Do not edit; do not shell-source. It is rewritten before every start,\n"
        "# because it must describe the mounted files as they are at that moment.\n"
        "#\n"
        "# Each label is a digest of what that service bind-mounts. Compose hashes\n"
        "# labels into its config hash, so a service whose mounted CONTENT changed\n"
        "# is recreated and one whose content did not is left alone (D591).\n"
    )
    body = yaml.safe_dump(build_mount_override(payload), sort_keys=True, default_flow_style=False)
    return (header + body).encode("utf-8")


def _docs_labels(
    *,
    https_entrypoint: str,
    docs_router_name: str,
    docs_auth_middleware_name: str,
    docs_stripprefix_middleware_name: str,
) -> dict[str, str]:
    """The documentation router: the same three lessons the REST router carries.

    **The rule is two matchers** (ADR 0059, D162). `PathPrefix` is not
    segment-aware, so a router ruled ``PathPrefix(`/docs/rest`)`` answers
    ``/docs/restaurant``. The pair gives a segment boundary: the exact path, and
    anything strictly beneath it.

    **The path comes from the document** (ADR 0061, D177). ``DOCS_PAGE_PATH`` is
    written into `compose.env` from ``identity.route_docs_path``, which is the
    same expression ``route_docs`` is built from -- so the published URL and the
    rule this matches on cannot drift. They did once, `/docs` against
    `/docs/rest`, and the copy carrying a comment saying it was kept in step was
    the one that had not drifted.

    **The documentation ROOT is stripped, not the page path** (ADR 0087, D187).
    Without any strip, `serve.py` would receive `/docs/rest/standalone.js` and
    answer 404 -- which at the edge reads as a missing route and is not one.
    Stripping the whole page path was the first design and it removed one bit
    too many: `/docs/rest` and `/docs/rest/` both arrived as `/`, so the process
    could not tell them apart and could not redirect the first to the second.
    Measured -- a browser given `/docs/rest` resolves the page's own
    `<script src="standalone.js">` to `/docs/standalone.js`, which **404s**,
    with `/docs/rest/standalone.js` as the control at 200.

    Stripping the root leaves `/rest`, `/rest/`, `/app` and `/app/`, which is
    what lets one container serve two surfaces and answer the slash-less form
    with a relative redirect.

    **This middleware is shared with the application documentation router**,
    which is now possible because the two strip the same thing.

    The credential middleware is referenced ``@file`` because it is defined by
    Traefik's *file* provider, not by these labels. The reason is now a rule
    rather than a limitation: since ADR 0086 the middleware carries the bcrypt
    hash **inline**, and a label carrying it would put a credential into Compose
    interpolation, which is one of the five places CLAUDE.md forbids a secret
    value to reach. (It would also need every `$` doubled, and a hash that
    survived interpolation half-escaped is a 401 on a correct password -- D165's
    failure through a new door.)

    A cross-provider reference without the ``@file`` suffix resolves to nothing,
    and a router whose middleware does not resolve serves the page **without
    asking for the password**.

    The other two middlewares stay here as labels, and ADR 0085 is why: moving
    them to the file provider was measured to change nothing, because the
    *router* is a label and is withdrawn with the container whatever its
    middlewares are doing.
    """
    router = f"traefik.http.routers.{docs_router_name}"
    service = f"traefik.http.services.{docs_router_name}"
    stripprefix = f"traefik.http.middlewares.{docs_stripprefix_middleware_name}"
    path = "${DOCS_PAGE_PATH:?required}"
    return {
        "traefik.enable": "true",
        f"{router}.rule": (
            f"Host(`${{PROJECT_DOMAIN:?required}}`) && (Path(`{path}`) || PathPrefix(`{path}/`))"
        ),
        f"{router}.entrypoints": https_entrypoint,
        f"{router}.tls.certresolver": "${ACME_RESOLVER_NAME:?required}",
        # Baseline, then the credential, then the strip. The credential is
        # before the strip because a refusal must not depend on the rewrite
        # having happened, and after the baseline so a 401 carries the same
        # response policy every other answer does.
        f"{router}.middlewares": (
            f"${{BASELINE_MIDDLEWARE_CHAIN:?required}},"
            f"{docs_auth_middleware_name}@file,{docs_stripprefix_middleware_name}"
        ),
        f"{router}.service": docs_router_name,
        f"{service}.loadbalancer.server.port": str(DOCS_SERVICE_PORT),
        # The ROOT, not `path`. ADR 0087, and the docstring above says why.
        f"{stripprefix}.stripprefix.prefixes": "${DOCS_ROOT_PATH:?required}",
    }


def _metrics_labels(
    *,
    https_entrypoint: str,
    metrics_router_name: str,
    metrics_auth_middleware_name: str,
) -> dict[str, str]:
    """The metrics route (ADR 0164), and the two things it does NOT have.

    **No strip prefix.** Every other routed surface here rewrites the path
    before the upstream sees it, because the upstream serves at a root the edge
    does not publish. The collector's exporter serves `/metrics` and answers 404
    on `/` -- measured against the locked digest, and asserted by
    `test_the_metrics_exporter_serves_one_parameterless_path`. So the path the
    edge matches is the path the upstream wants, and ADR 0087's rewrite has no
    counterpart. A strip added here by analogy with `docs` would deliver `/` and
    turn the whole surface into a 404.

    **No buffering middleware.** The API and application routes bound a request
    BODY because callers send them; a scrape is a GET with no body, so a
    buffering middleware would be a control over something that does not occur.
    Rate limiting still applies -- it arrives in the baseline chain.

    The rule is the exact path and nothing below it. `PathPrefix` alone would
    match `/metricsomething`, which is D162 (`PathPrefix(/api/rest)` matching
    `/api/restaurant`) at a new route; and unlike the documentation surface
    there is no subtree to admit, so this is `Path` alone rather than the
    path-or-prefix pair the other routers use.

    The credential middleware is referenced ``@file`` for
    ``docs_credential_middleware_name``'s reason, unchanged and load-bearing:
    since ADR 0086 the middleware carries the bcrypt hash inline, a label
    carrying it would put a credential into Compose interpolation, and **a
    cross-provider reference without the suffix resolves to nothing -- which
    serves the surface without asking for the password.**
    """
    router = f"traefik.http.routers.{metrics_router_name}"
    service = f"traefik.http.services.{metrics_router_name}"
    return {
        "traefik.enable": "true",
        # `Path`, not `PathPrefix`: one path exactly, and nothing beneath it.
        f"{router}.rule": (
            "Host(`${PROJECT_DOMAIN:?required}`) && Path(`${METRICS_PATH:?required}`)"
        ),
        f"{router}.entrypoints": https_entrypoint,
        f"{router}.tls.certresolver": "${ACME_RESOLVER_NAME:?required}",
        # Baseline first, then the credential. Same order as the documentation
        # route and for the same reason: a 401 carries the response policy every
        # other answer does, and the refusal does not depend on anything the
        # baseline chain has not already done.
        f"{router}.middlewares": (
            f"${{BASELINE_MIDDLEWARE_CHAIN:?required}},{metrics_auth_middleware_name}@file"
        ),
        f"{router}.service": metrics_router_name,
        f"{service}.loadbalancer.server.port": str(OTEL_EXPORTER_PORT),
    }


def _app_docs_labels(
    *,
    https_entrypoint: str,
    app_docs_router_name: str,
    docs_auth_middleware_name: str,
    docs_stripprefix_middleware_name: str,
) -> dict[str, str]:
    """The application documentation router: the same container, a second path.

    **The same credential middleware and the same strip**, referenced by the
    same names the REST documentation router uses. That is D226's decision
    working: one page's worth of infrastructure serving two documents, so an
    operator holds one password and the edge carries one rewrite.

    Sharing the strip is what ADR 0087 bought. Both routers remove the
    documentation *root*, so the container receives `/rest`, `/rest/`, `/app`
    and `/app/` -- four paths it can tell apart. Both removing their own page
    path would have delivered `/` for either surface, which is the state the
    REST route was already in, and it is why that page did not render when its
    URL was typed without a trailing slash.

    The rule still matches the published page path, with the segment-boundary
    pair, because `PathPrefix` is not segment-aware (D162).
    """
    router = f"traefik.http.routers.{app_docs_router_name}"
    service = f"traefik.http.services.{app_docs_router_name}"
    path = "${APP_DOCS_PAGE_PATH:?required}"
    return {
        "traefik.enable": "true",
        f"{router}.rule": (
            f"Host(`${{PROJECT_DOMAIN:?required}}`) && (Path(`{path}`) || PathPrefix(`{path}/`))"
        ),
        f"{router}.entrypoints": https_entrypoint,
        f"{router}.tls.certresolver": "${ACME_RESOLVER_NAME:?required}",
        # Baseline, credential, strip -- the same order and the same reasons the
        # REST documentation router uses.
        f"{router}.middlewares": (
            f"${{BASELINE_MIDDLEWARE_CHAIN:?required}},"
            f"{docs_auth_middleware_name}@file,{docs_stripprefix_middleware_name}"
        ),
        f"{router}.service": app_docs_router_name,
        f"{service}.loadbalancer.server.port": str(DOCS_SERVICE_PORT),
        # No `stripprefix.prefixes` here. The middleware is defined once, by
        # `_docs_labels`, on this same container -- a second definition under
        # the same name would be one of two answers to what gets removed.
    }


def _app_labels(
    *,
    https_entrypoint: str,
    app_router_name: str,
    app_buffering_middleware_name: str,
    app_stripprefix_middleware_name: str,
) -> dict[str, str]:
    """The application API router: the auth service, published (Run 10).

    **The boundary rule, re-measured for this route.** ``PathPrefix`` is a
    string prefix, so the pair is what gives a segment boundary. Measured
    against the locked Traefik with a control: `/api/app` and `/api/app/x`
    serve, while `/api/application`, `/api/app-extra`, `/api/app2` and `/api`
    all answer 404. The runbook named `/api/application` as the trap and this
    repository had already fallen into it once (D162).

    **The buffering middleware is the process's only body bound.** The service
    refuses a body over `strict_json.MAX_BODY_BYTES`, and it refuses it *after*
    `await request.body()` has read every byte -- measured, an 8 MiB body read
    in full and then rejected against a 16 KiB limit, a factor of 512. So the
    edge carries the same number one hop earlier, and it carries it from the
    same declaration (`auth_limits.py`, ADR 0084) rather than from a second
    constant that would agree until somebody changed one of them.

    **The strip is the published path.** The service routes `/auth/login` and
    `/admin/users` at its root; without the strip it receives `/api/app/auth/
    login` and FastAPI answers 404, which at the edge reads as a missing route
    and is not one (D187).

    The router lives here, on the container, rather than in the file provider --
    ADR 0085, measured: a file-provider service can name its backend only by
    DNS, and the Compose service name resolves to whichever project the edge
    attached to first.
    """
    router = f"traefik.http.routers.{app_router_name}"
    service = f"traefik.http.services.{app_router_name}"
    buffering = f"traefik.http.middlewares.{app_buffering_middleware_name}"
    stripprefix = f"traefik.http.middlewares.{app_stripprefix_middleware_name}"
    path = "${API_APP_PATH:?required}"
    return {
        "traefik.enable": "true",
        f"{router}.rule": (
            f"Host(`${{PROJECT_DOMAIN:?required}}`) && (Path(`{path}`) || PathPrefix(`{path}/`))"
        ),
        f"{router}.entrypoints": https_entrypoint,
        f"{router}.tls.certresolver": "${ACME_RESOLVER_NAME:?required}",
        f"{router}.middlewares": (
            f"${{BASELINE_MIDDLEWARE_CHAIN:?required}},"
            f"{app_buffering_middleware_name},{app_stripprefix_middleware_name}"
        ),
        f"{router}.service": app_router_name,
        f"{service}.loadbalancer.server.port": str(AUTH_SERVICE_PORT),
        # One number, from `strict_json.MAX_BODY_BYTES`, reaching the label as a
        # value through `compose.env` -- which is ADR 0013's split doing what it
        # is for: the middleware's NAME is in a key and is rendered, the limit is
        # a value and is interpolated.
        f"{buffering}.buffering.maxrequestbodybytes": "${AUTH_REQUEST_BODY_MAX_BYTES:?required}",
        f"{buffering}.buffering.memrequestbodybytes": "${AUTH_REQUEST_BODY_MAX_BYTES:?required}",
        f"{stripprefix}.stripprefix.prefixes": path,
    }


#: The methods the CORS middleware advertises, and the one authority for them.
#:
#: `OPTIONS` is here because the browser's preflight uses it and the middleware
#: answers it -- measured: with the middleware attached the `OPTIONS` never
#: reached the backend, and with it removed (the control) it did. The other
#: three are the storage surface's own, and
#: `test_the_cors_middleware_advertises_the_methods_the_router_serves` compares
#: this tuple against what `storage_routes.router` declares, so a fifth endpoint
#: cannot be added without this list being answered.
STORAGE_CORS_METHODS: tuple[str, ...] = ("DELETE", "GET", "OPTIONS", "POST")


def _storage_labels(
    *,
    https_entrypoint: str,
    storage_router_name: str,
    storage_buffering_middleware_name: str,
    storage_stripprefix_middleware_name: str,
    storage_cors_middleware_name: str,
) -> dict[str, str]:
    """The object-storage router: the first route nested inside another one.

    **The two-matcher rule is load-bearing twice over here.** It is the segment
    boundary every route since D162 has used -- ``PathPrefix`` is a string
    prefix, so ``PathPrefix(`/api/app/storage`)`` alone would answer
    ``/api/app/storagex``. And it is what makes this router *win*.

    ADR 0108, measured against the locked Traefik and read back from its own
    API: **the default priority is the rule string's length**, exactly
    (`priority=68` for a 68-character rule, `priority=84` for an 84-character
    one). Every request to this surface also matches the application router one
    segment above, and this rule is the application's with `/storage` inserted
    into both matchers -- exactly sixteen characters longer, for every project
    and every domain, because both carry the same `Host()` clause.

    The trap, with the control that proves it is one: a router ruled
    ``PathPrefix(`/api/app/deep`)`` is strictly *more specific* than the
    application router and **loses to it**, at 50 characters against 68. Writing
    this rule the concise way would produce a storage service that is never
    reached, with no error anywhere and a 404 from the auth service as the only
    symptom -- which at the edge is indistinguishable from a missing route
    (D186, D187).

    **A sibling here is not a 404**, and that is the second difference from
    every route before it. `/api/app/storagex` is caught by the *parent* router
    and reaches the auth service, which answers 404. So the boundary is a claim
    about which service answered, never about a status code; the host proof
    reads `RouterName` from the access log.

    **The strip is the published storage path**, not the application path. The
    service routes `/upload-intents` and `/objects/{id}` at its root, and this
    router's middleware chain is its own -- borrowing the application router's
    strip was measured to couple the two containers' lifetimes: a router whose
    middleware is defined by labels on another container goes `status=disabled`
    when that container stops, and answers Traefik's own 404.

    **The buffering middleware carries the same number as the application
    route's**, from the same `compose.env` key, because both modes run the same
    `strict_json` in the same image (ADR 0101) and the service refuses an
    oversized body only after reading every byte of it.

    **The CORS middleware is a label** (ADR 0109), not a file-provider document
    as D323 predicted -- the origin list is a manifest field published in
    `outputs.json`, not a root-owned value, and the file provider's rule
    (ADR 0086) is about where a *secret* may go. It is attached unconditionally,
    including when the list is empty, because an empty list was measured to
    permit nothing rather than everything.

    **It instructs a browser and does not control access.** Measured: a request
    from an unlisted origin is forwarded to the service and answered normally,
    with only the `Access-Control-Allow-Origin` header withheld. What refuses a
    caller here is the bearer token and the ownership filter.
    """
    router = f"traefik.http.routers.{storage_router_name}"
    service = f"traefik.http.services.{storage_router_name}"
    buffering = f"traefik.http.middlewares.{storage_buffering_middleware_name}"
    stripprefix = f"traefik.http.middlewares.{storage_stripprefix_middleware_name}"
    cors = f"traefik.http.middlewares.{storage_cors_middleware_name}"
    path = "${API_STORAGE_PATH:?required}"
    return {
        "traefik.enable": "true",
        f"{router}.rule": (
            f"Host(`${{PROJECT_DOMAIN:?required}}`) && (Path(`{path}`) || PathPrefix(`{path}/`))"
        ),
        f"{router}.entrypoints": https_entrypoint,
        f"{router}.tls.certresolver": "${ACME_RESOLVER_NAME:?required}",
        # Baseline, CORS, buffering, strip. CORS is before the buffering
        # middleware because it answers the preflight itself and a preflight has
        # no body to bound; it is after the baseline so the preflight it
        # generates carries the same response policy every other answer does --
        # which is the measured reason the REST route puts its 413 there.
        f"{router}.middlewares": (
            f"${{BASELINE_MIDDLEWARE_CHAIN:?required}},"
            f"{storage_cors_middleware_name},"
            f"{storage_buffering_middleware_name},{storage_stripprefix_middleware_name}"
        ),
        f"{router}.service": storage_router_name,
        f"{service}.loadbalancer.server.port": str(STORAGE_SERVICE_PORT),
        # `AUTH_REQUEST_BODY_MAX_BYTES`, deliberately: one number from
        # `strict_json.MAX_BODY_BYTES` through `auth_limits` (ADR 0084), reaching
        # both routes. A `STORAGE_REQUEST_BODY_MAX_BYTES` would be a second
        # constant that agreed with the first until somebody changed one, which
        # is D264's cost paid a second time.
        f"{buffering}.buffering.maxrequestbodybytes": "${AUTH_REQUEST_BODY_MAX_BYTES:?required}",
        f"{buffering}.buffering.memrequestbodybytes": "${AUTH_REQUEST_BODY_MAX_BYTES:?required}",
        f"{stripprefix}.stripprefix.prefixes": path,
        # `?required` rather than `:?required`, and it is the only key in this
        # module written that way. The colon form refuses an EMPTY value as
        # firmly as an unset one (D178), and an empty origin list is a
        # legitimate configuration -- a project that enables storage and permits
        # no browser origin. Measured: an empty list parses to `None` and the
        # middleware stays enabled and permits nothing.
        f"{cors}.headers.accesscontrolalloworiginlist": "${STORAGE_CORS_ALLOWED_ORIGINS?required}",
        f"{cors}.headers.accesscontrolallowmethods": ",".join(STORAGE_CORS_METHODS),
        # `Authorization` because every storage request carries a bearer token,
        # and `Content-Type` because the two POST bodies are JSON. Nothing else:
        # a header not listed here is one a browser will not send.
        f"{cors}.headers.accesscontrolallowheaders": "Authorization,Content-Type",
        f"{cors}.headers.accesscontrolmaxage": "600",
        # Measured to appear on real responses and NOT on the preflight
        # responses, which is Traefik's behaviour and not something this setting
        # changes. Recorded in ADR 0109; nothing between a browser and this edge
        # caches, and a cache placed there would need the preflight to vary.
        f"{cors}.headers.addvaryheader": "true",
    }


def _mcp_labels(*, https_entrypoint: str, mcp_router_name: str) -> dict[str, str]:
    """The agent plane's router: one published path, and nothing stripped.

    **No `stripprefix`, and that is measured rather than economical.** The
    application serves the MCP endpoint at `/mcp` on its own root -- read back
    from the route table FastMCP builds -- so the published path and the served
    path are the same string. A strip would forward `/` to a service that
    answers 404 there.

    **The two-matcher rule, for D162's reason.** `PathPrefix` is a string prefix,
    so `PathPrefix(`/mcp`)` alone answers `/mcpx`. The `Path()` half is what
    serves the endpoint itself, and the `PathPrefix(`/mcp/`)` half is what keeps
    a sub-path inside the surface without letting a sibling in.

    **A sibling lands somewhere different here than it does under `storage`.**
    `/api/app/storagex` is caught by the PARENT application router and gets the
    auth service's 404. `/mcp` is top-level, so `/mcpx` matches no router at all
    and gets **Traefik's own** 404 -- a 19-byte body carrying no `RouterName`
    (D186, D187, D353). The boundary proof reads which service answered.

    **No CORS middleware and no buffering.** No CORS because this is not a
    browser API and ADR 0128 refuses any request carrying an `Origin` at the
    runtime; attaching one would advertise a cross-origin flow that is
    deliberately impossible (ADR 0109). No buffering because the agent plane
    reads and the bodies are JSON-RPC envelopes, not uploads -- and the response
    ceiling it does need is a serialized-byte budget the runtime enforces after
    the read, which a request-body limit cannot express.

    **Health is absent from this label set on purpose** (ADR 0128). The
    container serves `/health/live` and `/health/ready` at its root and no router
    publishes them, so they are private by the absence of a route rather than by
    a guard. The public health answer stays `__apg/healthz` (D231).
    """
    router = f"traefik.http.routers.{mcp_router_name}"
    service = f"traefik.http.services.{mcp_router_name}"
    path = "${API_MCP_PATH:?required}"
    return {
        "traefik.enable": "true",
        f"{router}.rule": (
            f"Host(`${{PROJECT_DOMAIN:?required}}`) && (Path(`{path}`) || PathPrefix(`{path}/`))"
        ),
        f"{router}.entrypoints": https_entrypoint,
        f"{router}.tls.certresolver": "${ACME_RESOLVER_NAME:?required}",
        # The baseline chain alone: response headers and the platform's own
        # policy. No strip, no CORS, no buffering -- each absent for a reason
        # written in the docstring above rather than by omission.
        f"{router}.middlewares": "${BASELINE_MIDDLEWARE_CHAIN:?required}",
        f"{router}.service": mcp_router_name,
        f"{service}.loadbalancer.server.port": str(MCP_SERVICE_PORT),
    }


def _rest_labels(
    *,
    https_entrypoint: str,
    rest_router_name: str,
    buffering_middleware_name: str,
    stripprefix_middleware_name: str,
) -> dict[str, str]:
    """The REST router, its body-size middleware, and the boundary rule.

    **The rule is two matchers, and that is the measurement.** `PathPrefix` is
    not segment-aware: measured against the locked Traefik, a router ruled
    ``PathPrefix(`/api/rest`)`` answers ``/api/restaurant`` and
    ``/api/rest-extra`` with 200. A prefix boundary written the obvious way
    captures every sibling path that happens to share a spelling, and the
    symptom is a route serving a surface nobody attached it to.

    ``Path(`/api/rest`) || PathPrefix(`/api/rest/`)`` is the pair that gives a
    segment boundary: the exact path, and anything strictly beneath it.
    Re-measured, ``/api/restaurant``, ``/api/rest-extra`` and ``/api/rest2`` all
    return 404 while ``/api/rest``, ``/api/rest/`` and ``/api/rest/notes``
    return 200.

    The middleware's name is rendered into the label *key* and its two limits
    are left as interpolation references, which is ADR 0013's rule doing exactly
    what it is for. A name in a key is rendered because Compose 2.24 does not
    interpolate inside a key and would produce a middleware literally called
    `${API_BUFFERING_MIDDLEWARE_NAME}`; the numbers are values, so they come
    from `compose.env` and stay out of this file.
    """
    router = f"traefik.http.routers.{rest_router_name}"
    service = f"traefik.http.services.{rest_router_name}"
    buffering = f"traefik.http.middlewares.{buffering_middleware_name}"
    stripprefix = f"traefik.http.middlewares.{stripprefix_middleware_name}"
    path = "${API_REST_PATH:?required}"
    return {
        "traefik.enable": "true",
        f"{router}.rule": (
            f"Host(`${{PROJECT_DOMAIN:?required}}`) && (Path(`{path}`) || PathPrefix(`{path}/`))"
        ),
        f"{router}.entrypoints": https_entrypoint,
        f"{router}.tls.certresolver": "${ACME_RESOLVER_NAME:?required}",
        # The baseline chain first, then the body-size limit, then the prefix
        # strip. Order is the order a request traverses them: the baseline is
        # what puts `Cache-Control: no-store` on the 413 the buffering middleware
        # itself generates -- measured, and the reason the response policy lives
        # in the chain rather than beside the upstream -- and the strip is last
        # because everything above it matches on the published path.
        f"{router}.middlewares": (
            f"${{BASELINE_MIDDLEWARE_CHAIN:?required}},"
            f"{buffering_middleware_name},{stripprefix_middleware_name}"
        ),
        f"{router}.service": rest_router_name,
        f"{service}.loadbalancer.server.port": str(REST_SERVICE_PORT),
        f"{buffering}.buffering.maxrequestbodybytes": "${API_REQUEST_BODY_MAX_BYTES:?required}",
        f"{buffering}.buffering.memrequestbodybytes": "${API_REQUEST_BODY_MEMORY_BYTES:?required}",
        # Without this the router matches, forwards the published path unchanged,
        # and PostgREST -- which serves its document at `/` and its objects at
        # `/notes` -- answers 404 for a path it has never heard of. At the edge
        # that reads as a missing route and is not one (D187).
        #
        # Measured against the locked Traefik v3.7, with a control: `/api/rest`
        # arrives as `/` rather than as an empty path, `/api/rest/` as `/`, and
        # `/api/rest/notes` as `/notes`.
        f"{stripprefix}.stripprefix.prefixes": path,
    }


def render_override(
    *,
    router_name: str,
    https_entrypoint: str,
    rendered_directory: str,
    rest_router_name: str,
    buffering_middleware_name: str,
    stripprefix_middleware_name: str,
    docs_router_name: str,
    docs_auth_middleware_name: str,
    docs_stripprefix_middleware_name: str,
    app_router_name: str,
    app_buffering_middleware_name: str,
    app_stripprefix_middleware_name: str,
    app_docs_router_name: str,
    storage_router_name: str,
    storage_buffering_middleware_name: str,
    storage_stripprefix_middleware_name: str,
    storage_cors_middleware_name: str,
    mcp_router_name: str,
    metrics_router_name: str,
    metrics_auth_middleware_name: str,
    publications: dict[str, Any] | None = None,
) -> bytes:
    """Serialize the override deterministically, with a header saying what it is."""
    document = build_override(
        router_name=router_name,
        https_entrypoint=https_entrypoint,
        rendered_directory=rendered_directory,
        rest_router_name=rest_router_name,
        buffering_middleware_name=buffering_middleware_name,
        stripprefix_middleware_name=stripprefix_middleware_name,
        docs_router_name=docs_router_name,
        docs_auth_middleware_name=docs_auth_middleware_name,
        docs_stripprefix_middleware_name=docs_stripprefix_middleware_name,
        app_router_name=app_router_name,
        app_buffering_middleware_name=app_buffering_middleware_name,
        app_stripprefix_middleware_name=app_stripprefix_middleware_name,
        app_docs_router_name=app_docs_router_name,
        storage_router_name=storage_router_name,
        storage_buffering_middleware_name=storage_buffering_middleware_name,
        storage_stripprefix_middleware_name=storage_stripprefix_middleware_name,
        storage_cors_middleware_name=storage_cors_middleware_name,
        mcp_router_name=mcp_router_name,
        metrics_router_name=metrics_router_name,
        metrics_auth_middleware_name=metrics_auth_middleware_name,
        publications=publications,
    )
    header = (
        "# Generated from host.yaml and the rendered compose.env by ./deploy.sh.\n"
        "# Do not edit; do not shell-source. Router label keys are rendered\n"
        "# because Compose cannot interpolate inside a label key (ADR 0013).\n"
    )
    body = yaml.safe_dump(document, sort_keys=True, default_flow_style=False, width=10_000)
    return (header + body).encode("utf-8")
