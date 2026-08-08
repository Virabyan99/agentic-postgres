"""Router label keys are rendered; the values that matter are not.

A router label's *key* contains the router name, and interpolation inside a
label key is not portable to the Compose version floor (ADR 0013), so the key is
rendered here. The resolver and the middleware chain stay as interpolation
references on purpose: they come from the root-owned runtime env file, and an
operator who can write a project's rendered output must not thereby be able to
change which resolver issues its certificate or drop the middleware chain.
"""

from __future__ import annotations

import pytest
import yaml

from agentic_postgres import runtime_override
from agentic_postgres.naming import HEALTH_ROUTE_PATH

pytestmark = [pytest.mark.contract, pytest.mark.p0]

ROUTER = "apg-alpha-dev-health"
RENDERED = "/var/lib/agentic-postgres/rendered/alpha-dev"


@pytest.fixture
def labels() -> dict[str, str]:
    document = runtime_override.build_override(
        router_name=ROUTER, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    return document["services"][runtime_override.ROUTED_SERVICE]["labels"]


def test_no_label_key_contains_an_interpolation(labels: dict[str, str]) -> None:
    """The defect this file exists to prevent. Compose 2.24 renders
    `traefik.http.routers.${X}.rule` as a literal key."""
    offenders = [key for key in labels if "$" in key]
    assert not offenders, f"label keys must be fully rendered: {offenders}"


def test_the_router_name_is_in_the_keys(labels: dict[str, str]) -> None:
    assert f"traefik.http.routers.{ROUTER}.rule" in labels
    assert f"traefik.http.services.{ROUTER}.loadbalancer.server.port" in labels


def test_traefik_is_enabled_here_and_not_in_the_committed_model(
    labels: dict[str, str],
) -> None:
    """Exposure is a deliberate act of deployment, not a property of a file in
    the repository."""
    assert labels["traefik.enable"] == "true"


def test_the_resolver_and_middlewares_stay_interpolated(labels: dict[str, str]) -> None:
    assert labels[f"traefik.http.routers.{ROUTER}.tls.certresolver"] == (
        "${ACME_RESOLVER_NAME:?required}"
    )
    assert labels[f"traefik.http.routers.{ROUTER}.middlewares"] == (
        "${BASELINE_MIDDLEWARE_CHAIN:?required}"
    )


def test_the_rule_matches_the_reserved_health_path(labels: dict[str, str]) -> None:
    rule = labels[f"traefik.http.routers.{ROUTER}.rule"]
    assert "${PROJECT_DOMAIN:?required}" in rule
    assert HEALTH_ROUTE_PATH in rule


def test_the_router_and_service_names_agree(labels: dict[str, str]) -> None:
    """Mismatched `routers.<n>.service` and `services.<n>` labels produce a
    router that resolves to nothing."""
    assert labels[f"traefik.http.routers.{ROUTER}.service"] == ROUTER


def test_the_rendered_document_is_parseable_yaml() -> None:
    payload = runtime_override.render_override(
        router_name=ROUTER, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    document = yaml.safe_load(payload.decode("utf-8"))
    assert runtime_override.ROUTED_SERVICE in document["services"]


@pytest.mark.parametrize("field", ["router_name", "https_entrypoint", "rendered_directory"])
def test_an_empty_input_is_refused(field: str) -> None:
    arguments = {
        "router_name": ROUTER,
        "https_entrypoint": "websecure",
        "rendered_directory": RENDERED,
    }
    arguments[field] = ""
    with pytest.raises(ValueError):
        runtime_override.build_override(**arguments)


# ---------------------------------------------------------------------------
# The migration mount (D60). The rendered set is the one generated artifact a
# container reads, and dbmate is handed a directory rather than a file list --
# so the *path* is what decides which migrations run.
# ---------------------------------------------------------------------------


def test_the_migration_service_is_given_the_projects_own_rendered_set() -> None:
    document = runtime_override.build_override(
        router_name=ROUTER, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    volumes = document["services"][runtime_override.MIGRATION_SERVICE]["volumes"]
    assert volumes == [f"{RENDERED}/migrations:{runtime_override.MIGRATIONS_MOUNT}:ro"]


def test_the_migration_mount_is_read_only() -> None:
    """A writable mount would let a migration rewrite the set that produced it."""
    document = runtime_override.build_override(
        router_name=ROUTER, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    for volume in document["services"][runtime_override.MIGRATION_SERVICE]["volumes"]:
        assert volume.endswith(":ro"), volume


def test_a_relative_rendered_directory_is_refused() -> None:
    """Compose resolves a relative bind against its project directory, which is
    the installed release -- not this project's rendered output."""
    with pytest.raises(ValueError):
        runtime_override.build_override(
            router_name=ROUTER, https_entrypoint="websecure", rendered_directory="rendered/alpha"
        )
