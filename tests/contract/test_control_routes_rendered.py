"""The control facility, rendered: the mode, the route, the router and the
negated app rule (ADR 0251, D2043, D2045, D2059, D2075).

Everything here is rendered from one reader of the facility
(`config.control_enabled`). A project WITHOUT the facility -- alpha, beta and
both example fixtures -- must render exactly what it rendered before Session 37
apart from the route every project names: `AUTH_APP_MODE=auth`, no control
router, and an app rule byte-identical to the one copied below from
`runtime_override._app_labels` before this run edited it.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, config, naming, rendering, runtime_override

pytestmark = [pytest.mark.contract, pytest.mark.p0]

#: The app router's rule as `_app_labels` rendered it at 2538ac0 (1.14.0),
#: copied as a literal before the edit so a later change to the builder cannot
#: move both sides of this comparison at once.
APP_RULE_BEFORE = (
    "Host(`${PROJECT_DOMAIN:?required}`) && "
    "(Path(`${API_APP_PATH:?required}`) || PathPrefix(`${API_APP_PATH:?required}/`))"
)
#: The negation rig 37d measured: the boundary PAIR, because `!PathPrefix` of
#: the bare path also hid `/api/app/v1x`.
NEGATION = (
    " && !(Path(`${API_APP_PATH:?required}/v1`) || PathPrefix(`${API_APP_PATH:?required}/v1/`))"
)
CONTROL_RULE = (
    "Host(`${PROJECT_DOMAIN:?required}`) && "
    "(Path(`${CONTROL_ROUTE_PATH:?required}`) || PathPrefix(`${CONTROL_ROUTE_PATH:?required}/`))"
)

KEY = "control-prod"
NAMES = {
    "router_name": naming.health_router_name(KEY),
    "rest_router_name": naming.rest_router_name(KEY),
    "buffering_middleware_name": naming.api_buffering_middleware_name(KEY),
    "stripprefix_middleware_name": naming.api_stripprefix_middleware_name(KEY),
    "docs_router_name": naming.docs_router_name(KEY),
    "docs_auth_middleware_name": naming.docs_credential_middleware_name(KEY),
    "docs_stripprefix_middleware_name": naming.docs_stripprefix_middleware_name(KEY),
    "app_router_name": naming.app_router_name(KEY),
    "app_buffering_middleware_name": naming.app_buffering_middleware_name(KEY),
    "app_stripprefix_middleware_name": naming.app_stripprefix_middleware_name(KEY),
    "app_docs_router_name": naming.app_docs_router_name(KEY),
    "storage_router_name": naming.storage_router_name(KEY),
    "storage_buffering_middleware_name": naming.storage_buffering_middleware_name(KEY),
    "storage_stripprefix_middleware_name": naming.storage_stripprefix_middleware_name(KEY),
    "storage_cors_middleware_name": naming.storage_cors_middleware_name(KEY),
    "mcp_router_name": naming.mcp_router_name(KEY),
    "metrics_router_name": naming.metrics_router_name(KEY),
    "metrics_auth_middleware_name": naming.metrics_credential_middleware_name(KEY),
}
CONTROL_NAMES = {
    "control_router_name": naming.control_router_name(KEY),
    "control_stripprefix_middleware_name": naming.control_stripprefix_middleware_name(KEY),
}


def _auth_labels(**extra: Any) -> dict[str, str]:
    document = runtime_override.build_override(
        **NAMES, rest_enabled=True, https_entrypoint="websecure", rendered_directory="/r", **extra
    )
    return document["services"][runtime_override.AUTH_SERVICE]["labels"]


def _manifest(name: str, *, control: bool) -> dict[str, Any]:
    document = yaml.safe_load((REPO_ROOT / name).read_text(encoding="utf-8"))
    document = copy.deepcopy(document)
    if control:
        document["control"] = {"enabled": True}
    return document


def _identity(document: dict[str, Any]) -> naming.ProjectIdentity:
    return naming.derive(
        slug=document["project"]["slug"],
        environment=document["project"]["environment"],
        domain=document["project"]["domain"],
        api_base_path=document["api"]["public_base_path"],
        mcp_base_path=document["mcp"]["public_base_path"],
    )


def _compose_env(document: dict[str, Any]) -> dict[str, str]:
    raw = rendering.build_compose_env(
        _identity(document),
        config.database_budget(document["database"]),
        document["database"],
        document["api"],
        document.get("storage"),
        document.get("backup"),
        control=config.control_enabled(document),
    )
    return dict(line.split("=", 1) for line in raw.decode("utf-8").splitlines() if "=" in line)


def test_a_project_without_the_facility_renders_the_app_rule_it_had() -> None:
    """Off -- with or without the names passed -- the `auth` container carries no
    control router and the app rule byte-identical to 1.14.0's."""
    for extra in ({}, CONTROL_NAMES, {"control": False, **CONTROL_NAMES}):
        labels = _auth_labels(**extra)
        assert labels[f"traefik.http.routers.{NAMES['app_router_name']}.rule"] == APP_RULE_BEFORE
        # By the two derived names, not a substring: this key is `control-prod`,
        # so every label of the project contains "-control".
        assert not [
            key
            for key in labels
            if f".{CONTROL_NAMES['control_router_name']}." in key
            or f".{CONTROL_NAMES['control_stripprefix_middleware_name']}." in key
        ], extra


def test_the_control_plane_renders_the_control_router_and_hides_the_second_address() -> None:
    labels = _auth_labels(control=True, **CONTROL_NAMES)
    app = f"traefik.http.routers.{NAMES['app_router_name']}"
    router = f"traefik.http.routers.{CONTROL_NAMES['control_router_name']}"
    service = f"traefik.http.services.{CONTROL_NAMES['control_router_name']}"
    strip = f"traefik.http.middlewares.{CONTROL_NAMES['control_stripprefix_middleware_name']}"

    assert labels[f"{app}.rule"] == APP_RULE_BEFORE + NEGATION
    assert labels[f"{router}.rule"] == CONTROL_RULE
    assert labels[f"{router}.entrypoints"] == "websecure"
    assert labels[f"{router}.tls.certresolver"] == "${ACME_RESOLVER_NAME:?required}"
    assert labels[f"{router}.middlewares"] == (
        "${BASELINE_MIDDLEWARE_CHAIN:?required},"
        f"{NAMES['app_buffering_middleware_name']},"
        f"{CONTROL_NAMES['control_stripprefix_middleware_name']}"
    )
    assert labels[f"{router}.service"] == CONTROL_NAMES["control_router_name"]
    assert labels[f"{service}.loadbalancer.server.port"] == str(runtime_override.AUTH_SERVICE_PORT)
    assert labels[f"{strip}.stripprefix.prefixes"] == "${API_CONTROL_PATH:?required}"
    assert not [key for key in labels if "$" in key], "a label key must be fully rendered"


def test_the_control_plane_needs_both_of_its_names() -> None:
    for missing in CONTROL_NAMES:
        partial = {name: value for name, value in CONTROL_NAMES.items() if name != missing}
        with pytest.raises(ValueError, match="control"):
            _auth_labels(control=True, **partial)


def test_the_mode_is_control_only_where_the_facility_is_on() -> None:
    """Every project renders the five keys (compose.yaml interpolates them with
    `:?`); only the control plane renders `AUTH_APP_MODE=control`."""
    for name in ("project.example.yaml", "project.second.example.yaml"):
        values = _compose_env(_manifest(name, control=False))
        assert values["AUTH_APP_MODE"] == "auth", name
    on = _manifest("project.second.example.yaml", control=True)
    values = _compose_env(on)
    identity = _identity(on)
    assert values["AUTH_APP_MODE"] == "control"
    assert values["API_CONTROL_PATH"] == on["api"]["public_base_path"] == "/api"
    assert values["CONTROL_ROUTE_PATH"] == "/api/v1" == identity.route_control_path
    assert values["CONTROL_ROUTER_NAME"] == identity.control_router
    assert values["CONTROL_STRIPPREFIX_MIDDLEWARE_NAME"] == identity.control_stripprefix_middleware
    for key in (
        "AUTH_APP_MODE",
        "API_CONTROL_PATH",
        "CONTROL_ROUTE_PATH",
        "CONTROL_ROUTER_NAME",
        "CONTROL_STRIPPREFIX_MIDDLEWARE_NAME",
    ):
        assert key in rendering.COMPOSE_ENV_KEYS, key


def test_every_project_names_the_route_and_records_the_facility() -> None:
    """`routes.control` is named for every project, derived beside `routes.app`
    (D326), and the document records the facility so a reader finds the control
    project from documents alone (D2068)."""
    capabilities = config.load_capabilities_manifest(REPO_ROOT / "capabilities.example.yaml")
    for control in (False, True):
        document = _manifest("project.second.example.yaml", control=control)
        identity = _identity(document)
        outputs = rendering.build_outputs(document, capabilities, identity, {})
        assert outputs["routes"]["control"] == "https://fixture-alpine-dev.test/api/v1"
        assert outputs["routes"]["control"] == identity.route_control
        assert outputs["control"] == {"enabled": control}


def test_the_compose_model_interpolates_the_mode() -> None:
    model = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    environment = model["services"]["auth"]["environment"]
    assert environment["APP_MODE"] == "${AUTH_APP_MODE:?required}"
    # The two other modes stay literals: only `auth`'s container can be the
    # control plane (ADR 0251).
    assert model["services"]["storage"]["environment"]["APP_MODE"] == "storage"
    assert model["services"]["mcp"]["environment"]["APP_MODE"] == "mcp"
