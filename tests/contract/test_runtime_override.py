"""Router label keys are rendered; the values that matter are not.

A router label's *key* contains the router name, and interpolation inside a
label key is not portable to the Compose version floor (ADR 0013), so the key is
rendered here. The resolver and the middleware chain stay as interpolation
references on purpose: they come from the root-owned runtime env file, and an
operator who can write a project's rendered output must not thereby be able to
change which resolver issues its certificate or drop the middleware chain.
"""

from __future__ import annotations

import ast
import re

import pytest
import yaml

from agentic_postgres import REPO_ROOT, naming, runtime_override
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


# ---------------------------------------------------------------------------
# The verification JWKS (ADR 0051, Run 9)
# ---------------------------------------------------------------------------

RENDER_JWKS = REPO_ROOT / "bin" / "render-jwks.py"


def test_the_derivation_never_reads_private_material() -> None:
    """`-noout` does not mean "public only", and this is where that is held.

    Measured against OpenSSL 3.5.5, with a control confirming the search finds
    private parameters when they are present: `openssl rsa -in <private> -noout
    -text` prints `privateExponent`, `prime1`, `prime2` and the coefficient.
    `-noout` suppresses the re-encoded key, not the dump. So the obvious way to
    read a modulus and an exponent pulls the whole private key into a captured
    stdout, where a traceback or a log can carry it.

    The spelling is asserted, not the intention: the command that reads key
    *description* must be `-pubin`, and the only invocation given the private
    key's path must be the `-pubout` that derives the public half.

    Goes red if: a `-text` or `-modulus` invocation is pointed back at the
    private key path, which is the change that would make this file leak.
    """
    source = RENDER_JWKS.read_text(encoding="utf-8")
    tree = ast.parse(source)

    invocations: list[list[str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.List):
            continue
        literals = [
            element.value
            for element in node.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        ]
        if literals[:1] == ["openssl"]:
            invocations.append(literals)

    assert invocations, "no openssl invocation found; this test is reading the wrong shape"

    for command in invocations:
        reads_key_file = any(part == "-in" for part in command)
        describes = any(part in ("-text", "-modulus") for part in command)
        if describes:
            assert "-pubin" in command, (
                f"{command} reads a key description without -pubin. Against a private "
                "key, -text prints privateExponent and the primes"
            )
            assert not reads_key_file, (
                f"{command} names a key file and describes it; the public half must "
                "arrive on stdin so no private parameter is ever in this process"
            )
        elif reads_key_file:
            assert "-pubout" in command, (
                f"{command} opens the private key for something other than deriving its public half"
            )


def test_the_jwks_is_public_material_and_stored_as_such() -> None:
    """0444, and the reason is not convenience.

    A 0400 file would imply a confidentiality this content does not have -- a
    modulus, an exponent, an algorithm and a thumbprint -- and the next reader
    would have to work out whether the mode meant something. The private key it
    is derived from stays 0400 root, which is the property `SEC-BOOT-001`
    asserts.

    Goes red if: the mode is tightened, which would be a claim, or loosened to
    writable, which would let a container's own uid replace the key set it
    verifies against.
    """
    module = _load_render_jwks()
    assert module.JWKS_MODE == 0o444


def test_the_mount_and_the_model_name_the_same_file() -> None:
    """Two halves of one path, in two files that cannot see each other.

    The host side is per-project and lives in the runtime override; the
    container side is fixed and lives in `compose.yaml`, which is what lets the
    model stay project-neutral. Nothing but this test compares them, and a
    mismatch is a service reading a path nothing wrote -- which Docker answers
    by creating a *directory* at the mount source, so the symptom is a key set
    that will not parse rather than a missing file.

    Goes red if: either side is renamed alone.
    """
    module = _load_render_jwks()
    assert module.JWKS_FILENAME == runtime_override.JWKS_FILENAME

    model = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    secret = model["services"][runtime_override.REST_SERVICE]["environment"]["PGRST_JWT_SECRET"]
    assert secret == f"@{runtime_override.JWKS_CONTAINER_PATH}", (
        f"compose.yaml reads {secret!r} and the override mounts at "
        f"{runtime_override.JWKS_CONTAINER_PATH!r}"
    )

    override = runtime_override.build_override(
        router_name="r",
        https_entrypoint="websecure",
        rendered_directory="/var/lib/agentic-postgres/rendered/example-dev",
        rest_router_name="rest",
        buffering_middleware_name="buffer",
    )
    mounts = override["services"][runtime_override.REST_SERVICE]["volumes"]
    assert mounts == [
        f"/var/lib/agentic-postgres/rendered/example-dev/{runtime_override.JWKS_FILENAME}"
        f":{runtime_override.JWKS_CONTAINER_PATH}:ro"
    ], mounts


def _load_render_jwks():
    import importlib.util

    specification = importlib.util.spec_from_file_location("apg_render_jwks", RENDER_JWKS)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# A router on an invisible container is not a route (D186)
# ---------------------------------------------------------------------------

EDGE_STATIC = REPO_ROOT / "infra" / "edge" / "traefik.yaml"


def test_every_routed_service_carries_the_label_the_edge_filters_on() -> None:
    """Router labels on a container Traefik ignores create no route.

    `infra/edge/traefik.yaml` sets a provider constraint, so a container without
    the matching label is not merely unrouted — it is **invisible**. The router
    labels this module writes are then attached to something the proxy never
    looks at, no router is created, and the edge answers 404 for the published
    URL. That is what the first live capture got, from a PostgREST that was
    serving the document correctly to its own network the whole time.

    The two halves live in different files and neither can see the other: the
    router labels are rendered here, the identity labels are in `compose.yaml`,
    and the constraint is in the edge's static configuration. This is the only
    place all three meet.

    **The label and its value are read from the constraint**, not written here.
    A test carrying its own copy of `managed` would keep passing after the edge
    started filtering on something else.

    Goes red if: a service gains a router in the override without the scope
    label; or the constraint changes and the labels do not follow.
    """
    constraint = yaml.safe_load(EDGE_STATIC.read_text(encoding="utf-8"))
    expression = constraint["providers"]["docker"]["constraints"]
    matched = re.fullmatch(r"Label\(`([^`]+)`,\s*`([^`]+)`\)", expression.strip())
    assert matched, f"the edge constraint is not a simple Label() match: {expression!r}"
    label, value = matched.group(1), matched.group(2)

    override = runtime_override.build_override(
        router_name="health",
        https_entrypoint="websecure",
        rendered_directory="/var/lib/agentic-postgres/rendered/example-dev",
        rest_router_name="rest",
        buffering_middleware_name="buffer",
    )
    model = yaml.safe_load(MODEL.read_text(encoding="utf-8"))

    routed = [
        name
        for name, definition in override["services"].items()
        if any(key.startswith("traefik.http.routers.") for key in definition.get("labels", {}))
    ]
    assert routed, "no service in the override carries a router; this test found nothing"

    for name in routed:
        labels = model["services"][name].get("labels") or {}
        assert labels.get(label) == value, (
            f"{name} is given a router by the override and does not carry "
            f"{label}={value} in compose.yaml. The edge filters on that label, so the "
            "router is attached to a container it never sees"
        )
        # One network needs no hint; two leave Traefik no way to choose, and the
        # one it must not choose is the internal network the proxy cannot reach.
        if len(model["services"][name].get("networks") or []) > 1:
            assert "traefik.docker.network" in labels, (
                f"{name} is on multiple networks and names none of them for Traefik"
            )


def test_the_published_document_describes_the_published_address() -> None:
    """`openapi-server-proxy-uri`, or the document names the container's own bind.

    Measured on the deployed service before this was set: the generated document
    carried `"host": "0.0.0.0:3000"` and `"basePath": "/"` — a private address,
    published to every consumer of the API.

    `openapi_normalize` compares both fields against the published address and
    refuses a document that disagrees, so the snapshot capture fails rather than
    approving one that names the wrong host. Run 7's committed fixture was
    captured *with* this set, against a configuration the product did not yet
    produce, which is why nothing offline noticed.

    Goes red if: the proxy URI is dropped, or stops being built from the same
    two values `naming.derive` builds `route_rest` from.
    """
    model = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    environment = model["services"][runtime_override.REST_SERVICE]["environment"]

    proxy = environment.get("PGRST_OPENAPI_SERVER_PROXY_URI")
    assert proxy, (
        "PGRST_OPENAPI_SERVER_PROXY_URI is unset, so the document describes "
        "0.0.0.0:3000 and the capture refuses it"
    )
    assert proxy == "https://${PROJECT_DOMAIN:?required}${API_REST_PATH:?required}", proxy

    # And the two interpolations compose to the route the identity derives, so
    # the document's address and the router's address are one derivation.
    identity = naming.derive(
        slug="fixture-alpha",
        environment="dev",
        domain="fixture-alpha-dev.test",
        api_base_path="/api",
        mcp_base_path="/mcp",
    )
    assert f"https://{identity.domain}{identity.route_rest_path}" == identity.route_rest
