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

from agentic_postgres import REPO_ROOT, runtime_override
from agentic_postgres.naming import HEALTH_ROUTE_PATH

#: The Compose model, for the one test that checks a declared service name
#: against the services that actually exist.
MODEL = REPO_ROOT / "compose.yaml"

pytestmark = [pytest.mark.contract, pytest.mark.p0]

ROUTER = "apg-alpha-dev-health"
REST_ROUTER = "apg-alpha-dev-rest"
BUFFERING = "apg-alpha-dev-api-buffering"
RENDERED = "/var/lib/agentic-postgres/rendered/alpha-dev"

#: Every derived name the override renders into a label key. Collected here so a
#: new one cannot be added to the builder without every test that reads a label
#: key seeing it.
NAMES = {
    "router_name": ROUTER,
    "rest_router_name": REST_ROUTER,
    "buffering_middleware_name": BUFFERING,
}


@pytest.fixture
def labels() -> dict[str, str]:
    document = runtime_override.build_override(
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
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
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    document = yaml.safe_load(payload.decode("utf-8"))
    assert runtime_override.ROUTED_SERVICE in document["services"]


@pytest.mark.parametrize(
    "field",
    [
        "router_name",
        "rest_router_name",
        "buffering_middleware_name",
        "https_entrypoint",
        "rendered_directory",
    ],
)
def test_an_empty_input_is_refused(field: str) -> None:
    arguments = {
        **NAMES,
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
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    volumes = document["services"][runtime_override.MIGRATION_SERVICE]["volumes"]
    assert volumes == [f"{RENDERED}/migrations:{runtime_override.MIGRATIONS_MOUNT}:ro"]


def test_the_migration_mount_is_read_only() -> None:
    """A writable mount would let a migration rewrite the set that produced it."""
    document = runtime_override.build_override(
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    for volume in document["services"][runtime_override.MIGRATION_SERVICE]["volumes"]:
        assert volume.endswith(":ro"), volume


# ---------------------------------------------------------------------------
# The REST route (Session 5 Run 6)
# ---------------------------------------------------------------------------


@pytest.fixture
def rest_labels() -> dict[str, str]:
    document = runtime_override.build_override(
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    return document["services"][runtime_override.REST_SERVICE]["labels"]


def test_no_rest_label_key_contains_an_interpolation(rest_labels: dict[str, str]) -> None:
    """The same rule as the health router, and the same reason.

    Compose 2.24 renders `traefik.http.middlewares.${X}.buffering...` as a
    literal key, producing a middleware actually named `${X}` -- which the
    router's `middlewares` value, which *is* interpolated, never resolves to.
    """
    offenders = [key for key in rest_labels if "$" in key]
    assert not offenders, f"label keys must be fully rendered: {offenders}"


def test_the_boundary_is_an_exact_path_or_a_child_of_it(rest_labels: dict[str, str]) -> None:
    """Measured: `PathPrefix` is not segment-aware.

    A router ruled ``PathPrefix(`/api/rest`)`` answers `/api/restaurant` with
    200. The pair is what makes the boundary a segment boundary. This asserts
    the shape; `test_edge_behaviour.py` asserts the outcome against a running
    Traefik, including the control that the naive form really does over-match.
    """
    rule = rest_labels[f"traefik.http.routers.{REST_ROUTER}.rule"]
    assert "Path(`${API_REST_PATH:?required}`)" in rule
    assert "PathPrefix(`${API_REST_PATH:?required}/`)" in rule
    assert " || " in rule
    assert rule.count("PathPrefix") == 1, (
        "a second PathPrefix without a trailing slash re-opens the boundary"
    )


def test_the_rest_route_carries_the_baseline_chain_and_then_its_own_limit(
    rest_labels: dict[str, str],
) -> None:
    """Order is the order a request traverses them.

    The baseline is what puts `Cache-Control: no-store` on the 413 the buffering
    middleware itself generates.
    """
    attached = rest_labels[f"traefik.http.routers.{REST_ROUTER}.middlewares"]
    assert attached == f"${{BASELINE_MIDDLEWARE_CHAIN:?required}},{BUFFERING}"


def test_the_body_limits_stay_interpolated(rest_labels: dict[str, str]) -> None:
    """They are project-manifest values, so they come from `compose.env`.

    Rendering them here would put a manifest number in the root-owned file and
    give one limit two sources that can disagree.
    """
    prefix = f"traefik.http.middlewares.{BUFFERING}.buffering"
    assert rest_labels[f"{prefix}.maxrequestbodybytes"] == "${API_REQUEST_BODY_MAX_BYTES:?required}"
    assert rest_labels[f"{prefix}.memrequestbodybytes"] == (
        "${API_REQUEST_BODY_MEMORY_BYTES:?required}"
    )


def test_the_rest_router_and_service_names_agree(rest_labels: dict[str, str]) -> None:
    assert rest_labels[f"traefik.http.routers.{REST_ROUTER}.service"] == REST_ROUTER
    port = rest_labels[f"traefik.http.services.{REST_ROUTER}.loadbalancer.server.port"]
    assert port == str(runtime_override.REST_SERVICE_PORT)


def test_the_rest_route_is_not_attached_to_the_health_service() -> None:
    """Two routes, two services. A REST router pointing at the probe would
    answer 200 to every path under it and serve nothing of the API."""
    document = runtime_override.build_override(
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    probe = document["services"][runtime_override.ROUTED_SERVICE]["labels"]
    assert not [key for key in probe if REST_ROUTER in key]
    assert runtime_override.REST_SERVICE != runtime_override.ROUTED_SERVICE


def test_a_relative_rendered_directory_is_refused() -> None:
    """Compose resolves a relative bind against its project directory, which is
    the installed release -- not this project's rendered output."""
    with pytest.raises(ValueError):
        runtime_override.build_override(
            **NAMES, https_entrypoint="websecure", rendered_directory="rendered/alpha"
        )


# ---------------------------------------------------------------------------
# The deferred set is real, and the deploy defers exactly it (ADR 0063)
# ---------------------------------------------------------------------------


def test_deferred_services_are_real_services() -> None:
    """Every name in `POST_BOOTSTRAP_SERVICES` is a service `compose.yaml` defines.

    `project-runtime.sh` deliberately *skips* a deferred name it does not find,
    because the deploy passes the same list at every session and `postgrest` is
    simply not part of a session-4 deployment. Refusing there would break every
    deploy below the session that introduces the service.

    The cost of that permissiveness is that a typo defers nothing and silently
    starts the very service the caller was holding back — which is the deadlock
    ADR 0063 exists to prevent, arriving quietly. This is where that is caught:
    offline, in the gate, on every run.

    Goes red if: a service is renamed in `compose.yaml` and not here, or a name
    is misspelled here.
    """
    model = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    defined = set(model["services"])
    unknown = sorted(set(runtime_override.POST_BOOTSTRAP_SERVICES) - defined)
    assert not unknown, (
        f"{unknown} are deferred by the deploy and are not services in compose.yaml. "
        "project-runtime.sh skips a name it cannot find, so this would defer nothing"
    )


def test_the_deploy_defers_what_the_module_declares_and_resumes_after_bootstrapping() -> None:
    """ADR 0063's ordering, asserted on the deploy's source.

    Three properties, and the third is the one that matters: the `resume` must
    come **after** the bootstrap, or the roles are still NOLOGIN when the API
    plane starts and nothing has changed.

    Asserted on source text because the alternative is a live deploy, and the
    ordering is exactly what a live deploy cannot check cheaply — it either
    works or hangs for the healthcheck's full retry budget.

    Goes red if: the deploy grows its own list of deferred services rather than
    reading the declared one; `resume` moves above the bootstrap; or the
    deferral is dropped and step 5 goes back to starting everything.
    """
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")

    assert "runtime_override.POST_BOOTSTRAP_SERVICES" in source, (
        "the deploy no longer reads the declared deferred set; a second list is "
        "the one that goes stale when a service is added"
    )

    defer_at = source.index('"--defer"')
    bootstrap_at = source.index("postgres-bootstrap.sh")
    resume_at = source.index('"resume"')
    assert defer_at < bootstrap_at < resume_at, (
        "the deploy must defer, then bootstrap, then resume. Found the deferral at "
        f"{defer_at}, the bootstrap at {bootstrap_at}, the resume at {resume_at}"
    )
