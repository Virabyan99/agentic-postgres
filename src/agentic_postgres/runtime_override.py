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

from typing import Any

import yaml

from agentic_postgres.naming import HEALTH_ROUTE_PATH

#: The service in `compose.yaml` that carries the public route.
ROUTED_SERVICE = "edge-probe"

#: `services/edge-probe/probe.py` LISTEN_PORT. Traefik needs the container port;
#: the probe publishes none, because only Traefik publishes a host port.
ROUTED_SERVICE_PORT = 8080

__all__ = [
    "ROUTED_SERVICE",
    "ROUTED_SERVICE_PORT",
    "build_override",
    "render_override",
]


def build_override(*, router_name: str, https_entrypoint: str) -> dict[str, Any]:
    """Build the override document for one project's health route."""
    if not router_name:
        raise ValueError("router_name is required")
    if not https_entrypoint:
        raise ValueError("https_entrypoint is required")

    router = f"traefik.http.routers.{router_name}"
    service = f"traefik.http.services.{router_name}"

    return {
        "services": {
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
            }
        }
    }


def render_override(*, router_name: str, https_entrypoint: str) -> bytes:
    """Serialize the override deterministically, with a header saying what it is."""
    document = build_override(router_name=router_name, https_entrypoint=https_entrypoint)
    header = (
        "# Generated from host.yaml and the rendered compose.env by ./deploy.sh.\n"
        "# Do not edit; do not shell-source. Router label keys are rendered\n"
        "# because Compose cannot interpolate inside a label key (ADR 0013).\n"
    )
    body = yaml.safe_dump(document, sort_keys=True, default_flow_style=False, width=10_000)
    return (header + body).encode("utf-8")
