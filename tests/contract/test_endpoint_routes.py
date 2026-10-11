"""The customer's two doors, as the committed model and the override describe them
(Session 39, ADR 0268, ADR 0269).

Offline: what `compose.yaml` declares for `customer-pool` and `customer-direct`,
what `runtime_override.build_override` writes onto them, what the render puts in
`compose.env` for them, and when `project-runtime.sh` starts them. The poolers
running against a cluster are `test_customer_poolers.py`'s.

The property the whole file serves: **the public port reaches a customer
pooler and nothing else**. A TCP router on any other service -- above all on
`postgres` or the platform's `pgbouncer` -- would put a platform role one
password away from the internet, so it is asserted by walking every service the
override names, not by reading the two that should have one.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import (
    REPO_ROOT,
    compute_profiles,
    config,
    customer_credentials,
    host_config,
    naming,
    rendering,
    runtime_override,
)

pytestmark = [pytest.mark.contract, pytest.mark.security, pytest.mark.p0]

MODEL = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
POOL, DIRECT = naming.CUSTOMER_POOL_SERVICE, naming.CUSTOMER_DIRECT_SERVICE
RENDERED = "/var/lib/agentic-postgres/projects/alpha-dev/rendered"
USERLISTS = "/etc/agentic-postgres/projects/alpha-dev/customer-poolers"
POOL_ROUTER = naming.customer_pool_router_name("alpha-dev")
DIRECT_ROUTER = naming.customer_direct_router_name("alpha-dev")

NAMES = {
    "router_name": "apg-alpha-dev-health",
    "rest_router_name": "apg-alpha-dev-rest",
    "buffering_middleware_name": "apg-alpha-dev-rest-buffering",
    "stripprefix_middleware_name": "apg-alpha-dev-rest-strip",
    "docs_router_name": "apg-alpha-dev-docs",
    "docs_auth_middleware_name": "apg-alpha-dev-docs-auth",
    "docs_stripprefix_middleware_name": "apg-alpha-dev-docs-strip",
    "app_router_name": "apg-alpha-dev-app",
    "app_buffering_middleware_name": "apg-alpha-dev-app-buffering",
    "app_stripprefix_middleware_name": "apg-alpha-dev-app-strip",
    "app_docs_router_name": "apg-alpha-dev-app-docs",
    "storage_router_name": "apg-alpha-dev-storage",
    "storage_buffering_middleware_name": "apg-alpha-dev-storage-buffering",
    "storage_stripprefix_middleware_name": "apg-alpha-dev-storage-strip",
    "storage_cors_middleware_name": "apg-alpha-dev-storage-cors",
    "mcp_router_name": "apg-alpha-dev-mcp",
    "metrics_router_name": "apg-alpha-dev-metrics",
    "metrics_auth_middleware_name": "apg-alpha-dev-metrics-auth",
}


def override(*, public: bool) -> dict[str, Any]:
    return runtime_override.build_override(
        **NAMES,
        rest_enabled=True,
        https_entrypoint="websecure",
        rendered_directory=RENDERED,
        public_endpoints=public,
        customer_pool_router_name=POOL_ROUTER if public else "",
        customer_direct_router_name=DIRECT_ROUTER if public else "",
        customer_userlist_directory=USERLISTS if public else "",
    )


def expected_labels(router: str, host_key: str) -> dict[str, str]:
    """Written out whole, so a label added or loosened is a difference here."""
    tcp, service = f"traefik.tcp.routers.{router}", f"traefik.tcp.services.{router}"
    return {
        "traefik.enable": "true",
        f"{tcp}.entrypoints": "postgres",
        f"{tcp}.rule": f"HostSNI(`${{{host_key}:?required}}`)",
        f"{tcp}.tls.options": "postgres@file",
        f"{tcp}.tls.certresolver": "${ACME_RESOLVER_NAME:?required}",
        f"{tcp}.tls.domains[0].main": "${CUSTOMER_POOL_HOST:?required}",
        f"{tcp}.tls.domains[0].sans": "${CUSTOMER_DIRECT_HOST:?required}",
        f"{tcp}.service": router,
        f"{service}.loadbalancer.server.port": "6432",
    }


# ---------------------------------------------------------------------------
# The override
# ---------------------------------------------------------------------------


def test_each_door_carries_exactly_its_tcp_router_and_the_userlist_bind() -> None:
    services = override(public=True)["services"]
    assert services[POOL]["labels"] == expected_labels(POOL_ROUTER, "CUSTOMER_POOL_HOST")
    assert services[DIRECT]["labels"] == expected_labels(DIRECT_ROUTER, "CUSTOMER_DIRECT_HOST")
    for name in (POOL, DIRECT):
        assert services[name]["volumes"] == [f"{USERLISTS}:/run/apg/customer:ro"], name


def test_no_tcp_router_reaches_anything_but_a_customer_pooler() -> None:
    """Walked over every service the override names: a `traefik.tcp.` label on
    `postgres` or `pgbouncer` would publish a platform role's door."""
    services = override(public=True)["services"]
    carrying = sorted(
        name
        for name, service in services.items()
        if any(key.startswith("traefik.tcp.") for key in (service.get("labels") or {}))
    )
    assert carrying == sorted((POOL, DIRECT)), carrying
    # Control: the walk finds the HTTP routers it is not looking for, so an
    # empty answer above could not come from a reader that sees no labels.
    assert any(
        key.startswith("traefik.http.") for key in services[runtime_override.REST_SERVICE]["labels"]
    )


def test_without_the_facility_the_override_names_neither_pooler() -> None:
    services = override(public=False)["services"]
    assert POOL not in services and DIRECT not in services
    assert not any(
        key.startswith("traefik.tcp.")
        for service in services.values()
        for key in (service.get("labels") or {})
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"customer_pool_router_name": ""}, "router_name"),
        ({"customer_direct_router_name": ""}, "router_name"),
        ({"customer_userlist_directory": "relative/dir"}, "absolute"),
        ({"customer_userlist_directory": ""}, "absolute"),
    ],
)
def test_an_enabled_override_refuses_a_missing_name_or_a_relative_directory(
    change: dict[str, str], message: str
) -> None:
    arguments = {
        **NAMES,
        "rest_enabled": True,
        "https_entrypoint": "websecure",
        "rendered_directory": RENDERED,
        "public_endpoints": True,
        "customer_pool_router_name": POOL_ROUTER,
        "customer_direct_router_name": DIRECT_ROUTER,
        "customer_userlist_directory": USERLISTS,
        **change,
    }
    with pytest.raises(ValueError, match=message):
        runtime_override.build_override(**arguments)


def test_the_entrypoint_and_the_tls_option_are_the_edges_own() -> None:
    """The router names an entrypoint `infra/edge/traefik.yaml` defines and a TLS
    option `dynamic/baseline.yaml` defines -- read from those files, so a rename
    on either side is a failure here and not a router Traefik drops. The
    dynamic file is a template; it is read through the edge render's own
    substitution, as `test_edge_config` reads it."""
    from tests.contract.test_edge_config import _render_dynamic

    static = yaml.safe_load((REPO_ROOT / "infra/edge/traefik.yaml").read_text("utf-8"))
    dynamic = yaml.safe_load(_render_dynamic("production"))
    assert host_config.EDGE_POSTGRES_ENTRYPOINT in static["entryPoints"]
    option, _, provider = runtime_override.CUSTOMER_TLS_OPTION.partition("@")
    assert provider == "file"
    assert option in dynamic["tls"]["options"]


def test_the_userlist_directory_is_derived_once() -> None:
    assert customer_credentials.userlist_directory("alpha-dev") == Path(USERLISTS)


# ---------------------------------------------------------------------------
# The committed model
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "mode"), [(POOL, "transaction"), (DIRECT, "session")])
def test_the_model_declares_each_door_customer_only(name: str, mode: str) -> None:
    service = MODEL["services"][name]
    assert service["profiles"] == ["public-endpoints"]
    assert service["image"] == "${PGBOUNCER_IMAGE:?required}"
    assert service["user"] == "70:70"
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert set(service["networks"]) == {"internal", "edge"}
    # No secret of any kind: the userlist is a verifier from pg_authid, through
    # the override's bind, and there is no admin user to hold a password for.
    assert "secrets" not in service
    assert "ports" not in service
    assert "volumes" not in service
    environment = service["environment"]
    assert environment["APG_POOL_MODE"] == mode
    upper = name.upper().replace("-", "_")
    assert environment["APG_POOL_CONNECTIONS"] == f"${{{upper}_CONNECTIONS:?required}}"
    assert environment["APG_AUTH_FILE"] == (
        f"{runtime_override.CUSTOMER_USERLIST_MOUNT}/{runtime_override.CUSTOMER_USERLISTS[name]}"
    )
    script = service["entrypoint"][2]
    for line in (
        '"auth_type = scram-sha-256"',
        '"auth_file = $$APG_AUTH_FILE"',
        '"pool_mode = $$APG_POOL_MODE"',
        '"default_pool_size = $$APG_POOL_CONNECTIONS"',
        '"max_db_connections = $$APG_POOL_CONNECTIONS"',
        '"max_prepared_statements = 100"',
        '"track_extra_parameters = search_path"',
        '"ignore_startup_parameters = extra_float_digits"',
        '"unix_socket_dir = /tmp"',
    ):
        assert line in script, (name, line)
    assert "admin_users" not in script and "/run/secrets" not in script
    # The reset is unconditional only on the transaction door (D116).
    assert ('"server_reset_query_always = 1"' in script) is (mode == "transaction")
    labels = service["labels"]
    assert labels["apg.traefik.scope"] == "managed"
    assert labels["traefik.docker.network"] == "${EDGE_NETWORK_NAME:?required}"
    assert not any(key.startswith("traefik.tcp.") for key in labels)


def test_the_poolers_wait_for_the_bootstrap() -> None:
    """They log in upstream as roles the bootstrap makes LOGIN (ADR 0063)."""
    assert {POOL, DIRECT} <= set(runtime_override.POST_BOOTSTRAP_SERVICES)
    assert {POOL, DIRECT} <= set(runtime_override.DEFERRED_SERVICES)


def test_the_deploy_writes_the_userlists_after_6b_and_before_6c() -> None:
    """6f follows the start of the poolers it signals and the bootstrap whose
    verifiers it reads; read from the deploy's own source order."""
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    order = [source.index(f'step("{label}') for label in ("6. ", "6b. ", "6f. ", "6c. ")]
    assert order == sorted(order), order
    assert '"customer-credentials.sh"' in source


# ---------------------------------------------------------------------------
# The render and the runtime's profile
# ---------------------------------------------------------------------------


def compose_env(*, public: bool, profile: str = "standard") -> dict[str, str]:
    identity = naming.derive(
        slug="alpha",
        environment="dev",
        domain="alpha.example.com",
        api_base_path="/api",
        mcp_base_path="/mcp",
        storage_enabled=False,
    )
    database = {
        "max_client_connections": 100,
        "pool_size": 20,
        "public_endpoints": {"enabled": public},
    }
    raw = rendering.build_compose_env(
        identity, config.database_budget(database), database, compute_profile=profile
    )
    return dict(line.split("=", 1) for line in raw.decode("utf-8").splitlines() if "=" in line)


@pytest.mark.parametrize("profile", sorted(compute_profiles.CUSTOMER_CONNECTIONS))
def test_the_render_names_the_doors_and_their_claimants(profile: str) -> None:
    env = compose_env(public=True, profile=profile)
    claim = compute_profiles.CUSTOMER_CONNECTIONS[profile]
    assert env["APG_PUBLIC_ENDPOINTS"] == "1"
    assert env["CUSTOMER_POOL_CONNECTIONS"] == str(claim["pool"])
    assert env["CUSTOMER_DIRECT_CONNECTIONS"] == str(claim["direct"])
    assert env["CUSTOMER_POOL_HOST"] == "pool.alpha.example.com"
    assert env["CUSTOMER_DIRECT_HOST"] == "direct.alpha.example.com"
    assert env["CUSTOMER_POOL_ROUTER_NAME"] == naming.customer_pool_router_name("alpha-dev")
    assert env["CUSTOMER_DIRECT_ROUTER_NAME"] == naming.customer_direct_router_name("alpha-dev")
    assert env["CUSTOMER_POOL_MEMORY_LIMIT"] == "64m"
    assert env["CUSTOMER_POOL_PIDS_LIMIT"] == "64"


def test_off_the_render_says_so() -> None:
    assert compose_env(public=False)["APG_PUBLIC_ENDPOINTS"] == "0"


def _session_profiles(tmp_path: Path, env_line: str | None) -> list[str]:
    """`project-runtime.sh`'s own `session_profiles`, extracted and executed."""
    (tmp_path / "compose.env").unlink(missing_ok=True)
    if env_line is not None:
        (tmp_path / "compose.env").write_text(f"A=1\n{env_line}\nB=2\n", encoding="utf-8")
    script = REPO_ROOT / "bin" / "project-runtime.sh"
    program = (
        f'eval "$(sed -n \'/^session_profiles() {{/,/^}}/p\' "{script}")"; '
        f'session_profiles 4 "{tmp_path}"'
    )
    done = subprocess.run(
        ["bash", "-c", program],
        capture_output=True,
        text=True,
        check=True,
        stdin=subprocess.DEVNULL,
    )
    return done.stdout.split()


def test_the_runtime_adds_the_profile_exactly_when_the_render_says_one(tmp_path: Path) -> None:
    on = _session_profiles(tmp_path, "APG_PUBLIC_ENDPOINTS=1")
    assert on[-2:] == ["--profile", "public-endpoints"]
    # The session profiles are untouched -- the control that the function ran.
    assert on[:6] == ["--profile", "session2", "--profile", "session3", "--profile", "session4"]
    for line in ("APG_PUBLIC_ENDPOINTS=0", "APG_PUBLIC_ENDPOINTS=10", None):
        assert "public-endpoints" not in _session_profiles(tmp_path, line), line


def test_every_call_site_hands_the_function_its_rendered_directory() -> None:
    text = (REPO_ROOT / "bin" / "project-runtime.sh").read_text(encoding="utf-8")
    assert text.count('session_profiles "${THROUGH_SESSION}"') == 5
    assert text.count('session_profiles "${THROUGH_SESSION}" "${rendered}"') == 5
