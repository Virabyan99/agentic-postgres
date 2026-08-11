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

from ipaddress import ip_address
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

#: The service in `compose.yaml` that carries the public route.
ROUTED_SERVICE = "edge-probe"

#: Session 5's REST service, and the port it listens on inside its container.
#: 3000 is PostgREST's default `server-port`, which Run 4's `--dump-config`
#: printed; the Compose service does not override it.
REST_SERVICE = "postgrest"
REST_SERVICE_PORT = 3000

#: `services/edge-probe/probe.py` LISTEN_PORT. Traefik needs the container port;
#: the probe publishes none, because only Traefik publishes a host port.
ROUTED_SERVICE_PORT = 8080

#: The migration plane's service, and where its rendered set appears inside it.
#: The path is the one `compose.yaml` passes to `--migrations-dir`; the two
#: living in two files is exactly how dbmate ends up reporting "no migrations
#: found" against a directory that has five.
MIGRATION_SERVICE = "dbmate"
MIGRATIONS_MOUNT = "/migrations"

__all__ = [
    "DATABASE_SERVICE",
    "DATABASE_SERVICE_PORT",
    "MIGRATIONS_MOUNT",
    "MIGRATION_SERVICE",
    "POOLER_SERVICE",
    "POOLER_SERVICE_PORT",
    "REST_SERVICE",
    "REST_SERVICE_PORT",
    "ROUTED_SERVICE",
    "ROUTED_SERVICE_PORT",
    "build_override",
    "is_loopback",
    "publication",
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
                )
            },
        }
    }


def _rest_labels(
    *, https_entrypoint: str, rest_router_name: str, buffering_middleware_name: str
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
    path = "${API_REST_PATH:?required}"
    return {
        "traefik.enable": "true",
        f"{router}.rule": (
            f"Host(`${{PROJECT_DOMAIN:?required}}`) && (Path(`{path}`) || PathPrefix(`{path}/`))"
        ),
        f"{router}.entrypoints": https_entrypoint,
        f"{router}.tls.certresolver": "${ACME_RESOLVER_NAME:?required}",
        # The baseline chain first, then the body-size limit. Order is the order
        # a request traverses them, and the baseline is what puts
        # `Cache-Control: no-store` on the 413 the buffering middleware itself
        # generates -- measured, and the reason the response policy lives in the
        # chain rather than beside the upstream.
        f"{router}.middlewares": (
            f"${{BASELINE_MIDDLEWARE_CHAIN:?required}},{buffering_middleware_name}"
        ),
        f"{router}.service": rest_router_name,
        f"{service}.loadbalancer.server.port": str(REST_SERVICE_PORT),
        f"{buffering}.buffering.maxrequestbodybytes": "${API_REQUEST_BODY_MAX_BYTES:?required}",
        f"{buffering}.buffering.memrequestbodybytes": "${API_REQUEST_BODY_MEMORY_BYTES:?required}",
    }


def render_override(
    *,
    router_name: str,
    https_entrypoint: str,
    rendered_directory: str,
    rest_router_name: str,
    buffering_middleware_name: str,
    publications: dict[str, Any] | None = None,
) -> bytes:
    """Serialize the override deterministically, with a header saying what it is."""
    document = build_override(
        router_name=router_name,
        https_entrypoint=https_entrypoint,
        rendered_directory=rendered_directory,
        rest_router_name=rest_router_name,
        buffering_middleware_name=buffering_middleware_name,
        publications=publications,
    )
    header = (
        "# Generated from host.yaml and the rendered compose.env by ./deploy.sh.\n"
        "# Do not edit; do not shell-source. Router label keys are rendered\n"
        "# because Compose cannot interpolate inside a label key (ADR 0013).\n"
    )
    body = yaml.safe_dump(document, sort_keys=True, default_flow_style=False, width=10_000)
    return (header + body).encode("utf-8")
