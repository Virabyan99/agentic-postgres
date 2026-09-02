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
import sys
from pathlib import Path

import pytest
import yaml

from agentic_postgres import REPO_ROOT, naming, runtime_override, secrets_contract
from agentic_postgres.naming import HEALTH_ROUTE_PATH

#: The Compose model, for the one test that checks a declared service name
#: against the services that actually exist.
MODEL = REPO_ROOT / "compose.yaml"

pytestmark = [pytest.mark.contract, pytest.mark.p0]

ROUTER = "apg-alpha-dev-health"
REST_ROUTER = "apg-alpha-dev-rest"
BUFFERING = "apg-alpha-dev-api-buffering"
STRIPPREFIX = "apg-alpha-dev-api-stripprefix"
DOCS_ROUTER = "apg-alpha-dev-docs"
DOCS_AUTH = "apg-alpha-dev-docs-auth"
DOCS_STRIPPREFIX = "apg-alpha-dev-docs-strip"
APP_ROUTER = "apg-alpha-dev-app"
APP_BUFFERING = "apg-alpha-dev-app-buffering"
APP_STRIPPREFIX = "apg-alpha-dev-app-stripprefix"
APP_DOCS_ROUTER = "apg-alpha-dev-app-docs"
STORAGE_ROUTER = "apg-alpha-dev-storage"
STORAGE_BUFFERING = "apg-alpha-dev-storage-buffering"
STORAGE_STRIPPREFIX = "apg-alpha-dev-storage-stripprefix"
STORAGE_CORS = "apg-alpha-dev-storage-cors"
MCP_ROUTER = "apg-alpha-dev-mcp"
METRICS_ROUTER = "apg-alpha-dev-metrics"
METRICS_AUTH = "apg-alpha-dev-metrics-auth"
RENDERED = "/var/lib/agentic-postgres/rendered/alpha-dev"

#: Every derived name the override renders into a label key. Collected here so a
#: new one cannot be added to the builder without every test that reads a label
#: key seeing it.
NAMES = {
    "router_name": ROUTER,
    "rest_router_name": REST_ROUTER,
    "buffering_middleware_name": BUFFERING,
    "stripprefix_middleware_name": STRIPPREFIX,
    "docs_router_name": DOCS_ROUTER,
    "docs_auth_middleware_name": DOCS_AUTH,
    "docs_stripprefix_middleware_name": DOCS_STRIPPREFIX,
    "app_router_name": APP_ROUTER,
    "app_buffering_middleware_name": APP_BUFFERING,
    "app_stripprefix_middleware_name": APP_STRIPPREFIX,
    "app_docs_router_name": APP_DOCS_ROUTER,
    "storage_router_name": STORAGE_ROUTER,
    "storage_buffering_middleware_name": STORAGE_BUFFERING,
    "storage_stripprefix_middleware_name": STORAGE_STRIPPREFIX,
    "storage_cors_middleware_name": STORAGE_CORS,
    "mcp_router_name": MCP_ROUTER,
    "metrics_router_name": METRICS_ROUTER,
    "metrics_auth_middleware_name": METRICS_AUTH,
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
        "stripprefix_middleware_name",
        "docs_router_name",
        "docs_auth_middleware_name",
        "docs_stripprefix_middleware_name",
        "app_router_name",
        "app_buffering_middleware_name",
        "app_stripprefix_middleware_name",
        "app_docs_router_name",
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

    The strip is **last**, and that is not arbitrary: everything above it matches
    and reports on the *published* path, and the upstream is the only thing that
    wants the path without its prefix.
    """
    attached = rest_labels[f"traefik.http.routers.{REST_ROUTER}.middlewares"]
    assert attached == f"${{BASELINE_MIDDLEWARE_CHAIN:?required}},{BUFFERING},{STRIPPREFIX}"


def test_the_published_prefix_is_removed_before_the_upstream_sees_it(
    rest_labels: dict[str, str],
) -> None:
    """D187, and the reason the route 404'd from a service that was serving.

    The router publishes ``{api.public_base_path}/rest``; PostgREST serves its
    document at ``/`` and its objects at ``/notes`` and ``/rpc/create_note``.
    Without this middleware the router matches, forwards the published path
    unchanged, and PostgREST answers 404 for a path it has never heard of --
    which at the edge is indistinguishable from a missing route, and is not one.
    Measured on the deployed service: ``/`` answered 200 with 2412 bytes and
    ``/api/rest`` answered 404 with 96, matching Traefik's own logged
    ``DownstreamContentSize`` for the failing request exactly.

    The prefix stripped is the **same interpolation the rule matches on**, so a
    project whose base path changes cannot end up with a router that matches one
    path and strips another.

    Goes red if: the middleware is dropped, or its prefix stops being the value
    the rule uses.
    """
    prefixes = rest_labels[f"traefik.http.middlewares.{STRIPPREFIX}.stripprefix.prefixes"]
    rule = rest_labels[f"traefik.http.routers.{REST_ROUTER}.rule"]
    assert prefixes == "${API_REST_PATH:?required}"
    assert f"Path(`{prefixes}`)" in rule, (
        "the router matches one path and the middleware strips another"
    )


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

    **Replaced by a stricter version in Run 10, and ADR 0133 authorises it.**
    This asserted `POST_BOOTSTRAP_SERVICES` by name, which was true and too
    narrow: that tuple means *"authenticates as a role the bootstrap must
    activate"*, and the deploy was also using it to mean *"must not start before
    the files it mounts are written"*. The agent plane needs the second and not
    the first, so it was correctly absent and started too early — and its first
    start anywhere exited 1 on a key set Docker had turned into a directory
    (D463). The deploy now defers the **union**, and this test refuses the
    single-reason spelling as well as the second-list one.
    """
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")

    assert "runtime_override.DEFERRED_SERVICES" in source, (
        "the deploy no longer reads the declared deferred set; a second list is "
        "the one that goes stale when a service is added"
    )
    assert 'deferred = ",".join(runtime_override.POST_BOOTSTRAP_SERVICES)' not in source, (
        "the deploy defers only the bootstrap reason again; that is D463, and the "
        "service it silently starts too early is the one with no database role"
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
        **NAMES,
        https_entrypoint="websecure",
        rendered_directory="/var/lib/agentic-postgres/rendered/example-dev",
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


def _load_dev_token():
    import importlib.util

    source = REPO_ROOT / "bin" / "dev-token.py"
    specification = importlib.util.spec_from_file_location("apg_dev_token", source)
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
        **NAMES,
        https_entrypoint="websecure",
        rendered_directory="/var/lib/agentic-postgres/rendered/example-dev",
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


# ---------------------------------------------------------------------------
# The documentation router (ADR 0069, ADR 0061, ADR 0059, D162, D177, D187)
# ---------------------------------------------------------------------------


@pytest.fixture
def docs_labels() -> dict[str, str]:
    document = runtime_override.build_override(
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    return document["services"][runtime_override.DOCS_SERVICE]["labels"]


def test_the_docs_boundary_is_an_exact_path_or_a_child_of_it(docs_labels: dict[str, str]) -> None:
    """`PathPrefix` alone is not segment-aware (D162).

    Measured against the locked Traefik on the REST route, and the same matcher
    behaves the same way here: ``PathPrefix(`/docs/rest`)`` answers
    ``/docs/restaurant``. The pair is the exact path, and anything strictly
    beneath it.
    """
    rule = docs_labels[f"traefik.http.routers.{DOCS_ROUTER}.rule"]
    path = "${DOCS_PAGE_PATH:?required}"
    assert f"Path(`{path}`) || PathPrefix(`{path}/`)" in rule
    assert f"PathPrefix(`{path}`)" not in rule.replace(f"PathPrefix(`{path}/`)", "")


def test_the_docs_rule_takes_its_path_from_the_document(docs_labels: dict[str, str]) -> None:
    """ADR 0061, and the defect it settled.

    The page's path was derived twice and the two disagreed -- `/docs` in
    `outputs.json`, `/docs/rest` everywhere it was measured -- so a check would
    have answered 404 rather than 401 (D177). A literal here would be that
    second derivation, back again.
    """
    rule = docs_labels[f"traefik.http.routers.{DOCS_ROUTER}.rule"]
    assert "${DOCS_PAGE_PATH:?required}" in rule
    assert "/docs" not in rule, "the rule carries a literal path rather than the derived one"


def test_the_docs_credential_middleware_is_referenced_across_providers(
    docs_labels: dict[str, str],
) -> None:
    """`@file`, because the middleware is defined by Traefik's file provider.

    A `usersFile` names a path inside the Traefik container and a label cannot
    carry one, so `edge_credentials.py` writes the middleware into the dynamic
    directory instead. A cross-provider reference without the suffix resolves to
    nothing -- and **a router whose middleware does not resolve serves the page
    without asking for the password**, which is the failure that looks like
    success.
    """
    chain = docs_labels[f"traefik.http.routers.{DOCS_ROUTER}.middlewares"]
    assert f"{DOCS_AUTH}@file" in chain, f"the credential middleware is not resolvable: {chain}"


def test_the_credential_is_demanded_before_the_prefix_is_stripped(
    docs_labels: dict[str, str],
) -> None:
    """Order is the order a request traverses them.

    The refusal must not depend on the rewrite having happened, and it must come
    after the baseline so a 401 carries the same response policy every other
    answer does.
    """
    chain = docs_labels[f"traefik.http.routers.{DOCS_ROUTER}.middlewares"]
    parts = chain.split(",")
    assert parts[0] == "${BASELINE_MIDDLEWARE_CHAIN:?required}"
    assert parts.index(f"{DOCS_AUTH}@file") < parts.index(DOCS_STRIPPREFIX)


def test_the_docs_root_is_stripped_and_the_page_segment_is_not(
    docs_labels: dict[str, str],
) -> None:
    """The ROOT, not the page path, and ADR 0087 is why.

    Without any strip `serve.py` receives `/docs/rest/standalone.js` and answers
    404 -- which at the edge reads as a missing route and is not one (D187).
    Stripping the whole page path removed one bit too many: `/docs/rest` and
    `/docs/rest/` both arrived as `/`, so the process could not tell them apart
    and could not redirect the first to the second. Measured -- a browser given
    `/docs/rest` asks for `/docs/standalone.js`, which 404s.

    This replaces `test_the_docs_prefix_is_stripped`, which asserted the strip
    equalled `${DOCS_PAGE_PATH}`. That was true throughout the defect.
    """
    rule = docs_labels[f"traefik.http.routers.{DOCS_ROUTER}.rule"]
    stripped = docs_labels[f"traefik.http.middlewares.{DOCS_STRIPPREFIX}.stripprefix.prefixes"]
    assert stripped == "${DOCS_ROOT_PATH:?required}"
    assert stripped != "${DOCS_PAGE_PATH:?required}", (
        "the whole page path is stripped again, so the container cannot tell the "
        "slash-less form from the slash form and the page will not render"
    )
    # The rule still matches the page, which is what makes the root safe to
    # strip: nothing but this surface's own paths reaches the middleware.
    assert "${DOCS_PAGE_PATH:?required}" in rule


def test_both_documentation_routers_share_one_strip(docs_labels: dict[str, str]) -> None:
    """One middleware, because they now remove the same thing (ADR 0087).

    A second middleware under a second name would be a second answer to what
    gets removed, and Traefik's middleware namespace is host-wide -- so two
    definitions of one rewrite is the shape that ends with whichever loaded last
    deciding for both.
    """
    chain = docs_labels[f"traefik.http.routers.{APP_DOCS_ROUTER}.middlewares"]
    assert chain.endswith(DOCS_STRIPPREFIX)
    defined = [
        key
        for key in docs_labels
        if key.startswith("traefik.http.middlewares.") and key.endswith(".stripprefix.prefixes")
    ]
    assert defined == [f"traefik.http.middlewares.{DOCS_STRIPPREFIX}.stripprefix.prefixes"], (
        f"the documentation container defines {defined}; there is one rewrite here"
    )


def test_the_docs_router_and_service_names_agree(docs_labels: dict[str, str]) -> None:
    assert docs_labels[f"traefik.http.routers.{DOCS_ROUTER}.service"] == DOCS_ROUTER
    assert docs_labels[f"traefik.http.services.{DOCS_ROUTER}.loadbalancer.server.port"] == str(
        runtime_override.DOCS_SERVICE_PORT
    )


def test_no_docs_label_key_contains_an_interpolation(docs_labels: dict[str, str]) -> None:
    """ADR 0013: Compose cannot interpolate inside a label key."""
    offenders = [key for key in docs_labels if "$" in key]
    assert not offenders, f"label keys must be fully rendered: {offenders}"


def test_the_snapshot_mount_and_the_model_name_the_same_file() -> None:
    """Two halves of one path, in two files that cannot see each other.

    The host side is per-project and lives in this override; the container side
    is what `compose.yaml` puts in `APG_DOCS_SNAPSHOT`. A mismatch is a service
    reading a path nothing wrote -- and Docker answers that by creating a
    *directory* at the mount source, so the symptom is a document that will not
    parse rather than a missing file.
    """
    document = runtime_override.build_override(
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    mounts = document["services"][runtime_override.DOCS_SERVICE]["volumes"]
    assert mounts == [
        f"{RENDERED}/{runtime_override.SNAPSHOT_FILENAME}:"
        f"{runtime_override.SNAPSHOT_CONTAINER_PATH}:ro",
        f"{RENDERED}/{runtime_override.APP_SNAPSHOT_FILENAME}:"
        f"{runtime_override.APP_SNAPSHOT_CONTAINER_PATH}:ro",
    ]

    model = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    environment = model["services"][runtime_override.DOCS_SERVICE]["environment"]
    declared = environment[runtime_override.SNAPSHOT_ENV_KEY]
    assert declared == runtime_override.SNAPSHOT_CONTAINER_PATH, (
        f"compose.yaml reads {declared!r} and the override mounts at "
        f"{runtime_override.SNAPSHOT_CONTAINER_PATH!r}"
    )
    # The second surface (D226), held to the same rule. Two files in one mounted
    # directory, and the model and the override have to name each of them
    # identically for the same reason: Docker creates a *directory* at a mount
    # source that does not exist, so a mismatch is a document that will not
    # parse rather than a file that is missing.
    declared_app = environment[runtime_override.APP_SNAPSHOT_ENV_KEY]
    assert declared_app == runtime_override.APP_SNAPSHOT_CONTAINER_PATH, (
        f"compose.yaml reads {declared_app!r} and the override mounts at "
        f"{runtime_override.APP_SNAPSHOT_CONTAINER_PATH!r}"
    )
    assert declared_app != declared, "both surfaces would serve the same document"


def test_the_snapshot_mount_is_read_only() -> None:
    """The page serves a reviewed document; it has no business rewriting one."""
    document = runtime_override.build_override(
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    for mount in document["services"][runtime_override.DOCS_SERVICE]["volumes"]:
        assert mount.endswith(":ro"), mount


# ---------------------------------------------------------------------------
# The application API route (Run 10)
# ---------------------------------------------------------------------------


@pytest.fixture
def app_labels() -> dict[str, str]:
    document = runtime_override.build_override(
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    return document["services"][runtime_override.AUTH_SERVICE]["labels"]


def test_no_app_label_key_contains_an_interpolation(app_labels: dict[str, str]) -> None:
    """The same rule as every router before it, and the same reason: Compose
    renders a label KEY literally, producing a middleware actually named
    `${X}` that the router's interpolated `middlewares` value never resolves to.
    """
    offenders = [key for key in app_labels if "$" in key]
    assert not offenders, f"label keys must be fully rendered: {offenders}"


def test_the_app_boundary_is_an_exact_path_or_a_child_of_it(app_labels: dict[str, str]) -> None:
    """Measured against the locked Traefik for THIS route, not inherited.

    `PathPrefix` is a string prefix, so a router ruled ``PathPrefix(`/api/app`)``
    answers `/api/application` -- which the runbook named as the trap and which
    this repository has fallen into once (D162). Re-measured with the pair in
    place: `/api/app` and `/api/app/x` serve, while `/api/application`,
    `/api/app-extra`, `/api/app2` and `/api` all answer 404.
    """
    rule = app_labels[f"traefik.http.routers.{APP_ROUTER}.rule"]
    assert "Path(`${API_APP_PATH:?required}`)" in rule
    assert "PathPrefix(`${API_APP_PATH:?required}/`)" in rule
    without_pair = rule.replace("PathPrefix(`${API_APP_PATH:?required}/`)", "")
    assert "PathPrefix(`${API_APP_PATH:?required}`)" not in without_pair, (
        "a bare PathPrefix would answer /api/application"
    )


def test_the_app_prefix_is_stripped_before_the_service_sees_it(
    app_labels: dict[str, str],
) -> None:
    """The service routes `/auth/login` at its root. Without the strip it
    receives `/api/app/auth/login` and FastAPI answers 404 -- which at the edge
    reads as a missing route and is not one (D187)."""
    stripped = app_labels[f"traefik.http.middlewares.{APP_STRIPPREFIX}.stripprefix.prefixes"]
    assert stripped == "${API_APP_PATH:?required}"


def test_the_app_route_carries_a_body_limit(app_labels: dict[str, str]) -> None:
    """The process's only body bound (D273).

    The service refuses a body over `strict_json.MAX_BODY_BYTES` **after**
    `request.body()` has read all of it -- measured, an 8 MiB body read in full
    and then rejected against a 16 KiB limit, a factor of 512. So this
    middleware is what bounds what the process allocates, and both settings
    carry the same interpolation so nothing spills to disk on the way through.
    """
    for setting in ("maxrequestbodybytes", "memrequestbodybytes"):
        key = f"traefik.http.middlewares.{APP_BUFFERING}.buffering.{setting}"
        assert app_labels[key] == "${AUTH_REQUEST_BODY_MAX_BYTES:?required}"


def test_the_edge_bound_is_the_service_bound() -> None:
    """One number, read from the service's own module (ADR 0084).

    Written as a comparison across the boundary rather than against a literal: a
    test asserting `16384 == 16384` is D260's third mutation, which computed its
    expectation from the constant under test and could not fail.
    """
    from agentic_postgres import auth_limits, service_source

    assert auth_limits.MAX_BODY_BYTES == service_source.load("strict_json").MAX_BODY_BYTES


def test_the_body_bound_reaches_the_rendered_environment() -> None:
    """A middleware interpolating a variable nothing emits does not render at
    all -- D178, which reached a live deploy."""
    from agentic_postgres import rendering

    assert "AUTH_REQUEST_BODY_MAX_BYTES" in rendering.COMPOSE_ENV_KEYS


def test_the_app_router_and_service_names_agree(app_labels: dict[str, str]) -> None:
    assert app_labels[f"traefik.http.routers.{APP_ROUTER}.service"] == APP_ROUTER
    assert f"traefik.http.services.{APP_ROUTER}.loadbalancer.server.port" in app_labels


def test_the_app_route_carries_the_baseline_chain_first(app_labels: dict[str, str]) -> None:
    """The baseline puts the response policy on answers the edge generates
    itself -- including the 413 the buffering middleware produces."""
    chain = app_labels[f"traefik.http.routers.{APP_ROUTER}.middlewares"]
    assert chain.startswith("${BASELINE_MIDDLEWARE_CHAIN:?required},")
    assert chain.endswith(f"{APP_BUFFERING},{APP_STRIPPREFIX}")


def test_the_application_documentation_router_shares_the_credential(
    docs_labels: dict[str, str],
) -> None:
    """One password for two surfaces (D226). A second credential middleware
    would be a second password an operator has to hold for one page's worth of
    infrastructure."""
    chain = docs_labels[f"traefik.http.routers.{APP_DOCS_ROUTER}.middlewares"]
    assert f"{DOCS_AUTH}@file" in chain, "the application documentation route is not protected"


# ---------------------------------------------------------------------------
# The key set, and every live issuer in it (Run 10, D276)
# ---------------------------------------------------------------------------


def _write_key(path: Path) -> None:
    """A real 2048-bit RSA key, because `build` shells out to openssl."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    path.parent.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def test_the_key_set_carries_every_live_issuers_key(tmp_path, monkeypatch) -> None:
    """D276, measured by building a key set rather than by reading the builder.

    `secrets.required.yaml` declares `auth_jwt_signing_key` with the sentence
    "the JWKS every verifier reads is derived from it", and until Run 10 nothing
    derived it: the only other reference in the repository was `compose.yaml`'s
    `APG_SIGNING_KEY_FILE`. The auth service signed with a key PostgREST had
    never been given, and a token signed by a key outside the published set is
    **401** -- measured, with a published key at 200 as the control.

    **This is the third version of this test.** The first asserted that `build`'s
    source named `auth_key_path`, and the mutation battery found it green with
    the `keys.append` deleted -- the mutated builder still computed the path and
    discarded it. A test that a function is mentioned is not a test that a key is
    published.

    **The second asserted the set carried BOTH issuers, and ADR 0170 replaces it
    with this stricter one.** Two independently published signing keys are two
    keys whose compromise is total, and the second stopped having a signer when
    `dev-token` moved to the issuer's own key (D821). The subject is unchanged --
    D276, the auth key must be published or every token it signs is refused --
    but the assertion is now that it is published *and is the only one*, which
    the previous version would have passed with the retired key still in the set.
    """
    module = _load_render_jwks()
    generation = tmp_path / "probe-dev" / "generations" / "gen"
    monkeypatch.setattr(module, "SECRET_ROOT", tmp_path)

    _write_key(generation / module.AUTH_SERVICE / module.AUTH_SIGNING_KEY_FILE)

    document, keys = module.build("probe-dev", "gen")
    assert len(keys) == 1, "the retired issuer's key is still being published"
    assert [key["kid"] for key in document["keys"]] == [key["kid"] for key in keys]

    # The auth service's key leads, and now leads alone: it is the issuer from
    # Session 6 onward, and `observe_jwt` reads `active_kid` off the head.
    auth_jwk = module._jwk_from(generation / module.AUTH_SERVICE / module.AUTH_SIGNING_KEY_FILE)
    assert keys[0]["kid"] == auth_jwk["kid"], "the auth service's key is not the active one"


def test_a_generation_that_still_holds_the_retired_key_still_publishes_it(
    tmp_path, monkeypatch
) -> None:
    """The retirement is a GUARD, not a deletion (ADR 0170).

    A generation materialized before Run 1 still carries
    `bootstrap_jwt_signing_key.pem` on disk, and until a retiring deploy replaces
    that generation the key is still there. Publishing a set without it while it
    is still present would refuse tokens minted with it that are still inside
    their 930 s lifetime -- so the builder reports what is there rather than
    enforcing what ought to be.

    **This is the control on the test above.** Without it, a builder that deleted
    the bootstrap append outright -- rather than guarding it -- would satisfy
    every other assertion in this module.
    """
    module = _load_render_jwks()
    generation = tmp_path / "probe-dev" / "generations" / "gen"
    monkeypatch.setattr(module, "SECRET_ROOT", tmp_path)

    _write_key(generation / module.AUTH_SERVICE / module.AUTH_SIGNING_KEY_FILE)
    _write_key(generation / secrets_contract.ROOT_PLANE_DIRECTORY / module.SIGNING_KEY_FILE)

    _, keys = module.build("probe-dev", "gen")
    bootstrap = module._jwk_from(
        generation / secrets_contract.ROOT_PLANE_DIRECTORY / module.SIGNING_KEY_FILE
    )
    auth = module._jwk_from(generation / module.AUTH_SERVICE / module.AUTH_SIGNING_KEY_FILE)
    assert len(keys) == 2, "a bootstrap key still on disk was dropped from the set"
    assert bootstrap["kid"] in {key["kid"] for key in keys}

    # And the auth key still LEADS. `observe_jwt` takes `active_kid = kids[0]`,
    # so an order that put the retiring key first would publish a document
    # naming it as the active one during the whole transition.
    assert keys[0]["kid"] == auth["kid"], "the retiring key leads the set"


def test_a_set_with_no_keys_is_refused_where_the_cause_is_visible(tmp_path, monkeypatch) -> None:
    """Guarding the last unconditional append made an empty set REACHABLE.

    `build_jwks` already refuses one -- "a key set with no keys verifies
    nothing" -- and stays the backstop. `build` refuses first because its message
    names the *cause* rather than the symptom: a generation carrying neither key
    is a project deployed before Session 6 whose bootstrap key has been retired,
    and the repair is a redeploy, not an inspection of the published set.
    ADR 0170.
    """
    module = _load_render_jwks()
    monkeypatch.setattr(module, "SECRET_ROOT", tmp_path)
    (tmp_path / "probe-dev" / "generations" / "gen").mkdir(parents=True)

    with pytest.raises(Exception, match="no key would be published"):
        module.build("probe-dev", "gen")


def test_a_prepared_key_joins_the_published_set(tmp_path, monkeypatch) -> None:
    """Prepare's whole observable effect -- and D683, which is why Run 1 exists.

    **This test could not have passed before ADR 0170.** The set was permanently
    full at `MAX_VERIFICATION_KEYS`: the auth key plus the bootstrap issuer's,
    appended unconditionally, so a prepared key was the third and `build_jwks`
    refused the render. That is D683, and it is what kept the signing key
    unrotatable for nine sessions.

    Its base is now the AUTH key rather than the bootstrap key, which is the same
    change: the auth service is the issuer, and a rotation prepares a successor
    to *its* key.
    """
    module = _load_render_jwks()
    generation = tmp_path / "probe-dev" / "generations" / "gen"
    monkeypatch.setattr(module, "SECRET_ROOT", tmp_path)

    _write_key(generation / module.AUTH_SERVICE / module.AUTH_SIGNING_KEY_FILE)

    _, before = module.build("probe-dev", "gen")
    assert len(before) == 1

    _write_key(generation / secrets_contract.ROOT_PLANE_DIRECTORY / module.PREPARED_KEY_FILE)
    _, after = module.build("probe-dev", "gen")
    assert len(after) == 2, "a rotation still cannot be prepared; D683 is not closed"
    assert after[0]["kid"] == before[0]["kid"], "preparing a rotation moved the leading key"


def test_every_key_a_minter_signs_with_is_a_key_the_renderer_publishes(
    tmp_path, monkeypatch
) -> None:
    """The guard over D821's CLASS, not over the instance that caused it.

    `bin/dev-token.py` signed with the bootstrap issuer's key for nine sessions,
    which is why the key could not be retired: the deploy mints one on every run
    through `observe_served_document`, and a token signed outside the published
    set is 401. That instance is fixed by pointing it at the auth key.

    **The instance is not the defect.** The defect is that two files decided
    independently which key was live -- one signing, one publishing -- with
    nothing comparing them, which is D486's shape and the reason this asserts a
    relation rather than a filename. It goes red if a minter is repointed at a
    key the renderer does not publish: the prepared key, whose private half must
    reach no signer, or a retired one.

    Measured through both modules rather than by reading either.
    """
    jwks = _load_render_jwks()
    dev_token = _load_dev_token()
    generation = tmp_path / "probe-dev" / "generations" / "gen"
    monkeypatch.setattr(jwks, "SECRET_ROOT", tmp_path)
    monkeypatch.setattr(dev_token, "SECRET_ROOT", tmp_path)

    _write_key(generation / jwks.AUTH_SERVICE / jwks.AUTH_SIGNING_KEY_FILE)

    document, _ = jwks.build("probe-dev", "gen")
    published = {key["kid"] for key in document["keys"]}

    deployed = {"project": {"key": "probe-dev"}, "secrets": {"generation_id": "gen"}}
    signing = dev_token.signing_key_path("probe-dev", deployed)
    assert dev_token.key_id(signing) in published, (
        f"dev-token signs with {signing.name}, whose kid is not in the published set "
        f"{sorted(published)}. Every token it mints would be refused by every verifier."
    )


def test_a_third_key_is_refused_rather_than_published(tmp_path, monkeypatch) -> None:
    """The ceiling, still reached through the builder -- and it matters that it is.

    **The first draft of ADR 0170 said this became unreachable**, on the grounds
    that only the auth key and a prepared key remain publishable. The rig's
    control arm measured otherwise: a generation that still holds the bootstrap
    key beside those two offers three, and that is exactly the state this change
    passes through -- an operator preparing a rotation before the retiring deploy
    has run.

    So the ceiling is not vacuous, not lowered, and its proof is not deleted
    because its last violation was removed. That is the shape this repository's
    §7 defect takes.
    """
    module = _load_render_jwks()
    generation = tmp_path / "probe-dev" / "generations" / "gen"
    monkeypatch.setattr(module, "SECRET_ROOT", tmp_path)

    root = generation / secrets_contract.ROOT_PLANE_DIRECTORY
    _write_key(root / module.SIGNING_KEY_FILE)
    _write_key(root / module.PREPARED_KEY_FILE)
    _write_key(generation / module.AUTH_SERVICE / module.AUTH_SIGNING_KEY_FILE)

    with pytest.raises(Exception, match="above the ceiling"):
        module.build("probe-dev", "gen")


def test_the_auth_key_is_read_from_the_services_own_plane() -> None:
    """A compose-plane consumer, in the service's directory.

    `secrets.required.yaml` gives it `plane: compose, service: auth`, and the
    generation layout puts a compose consumer's file under the service's name.
    A reader looking in `_root/` would find nothing and publish a set without
    it, which is D276 again with the derivation present and pointed elsewhere.
    """
    module = _load_render_jwks()
    path = module.auth_key_path("probe-dev", "gen")
    assert path.name == module.AUTH_SIGNING_KEY_FILE
    assert path.parent.name == module.AUTH_SERVICE
    assert path.parent.name != secrets_contract.ROOT_PLANE_DIRECTORY


def test_the_prepared_key_is_read_from_the_root_plane_where_no_service_holds_it() -> None:
    """The safety property of the whole cutover, as a path.

    Between prepare and promote the incoming key's PUBLIC half is published so
    every verifier can acknowledge it, and its private half must reach no
    running process -- a key a signer could reach is a key it could sign with
    before the verifiers agreed to accept it, which is the gap the
    acknowledgement step exists to close.
    """
    module = _load_render_jwks()
    path = module.prepared_key_path("probe-dev", "gen")
    assert path.parent.name == secrets_contract.ROOT_PLANE_DIRECTORY


def test_the_declared_key_files_are_the_ones_the_secret_contract_writes() -> None:
    """Three filenames in two files, and nothing else compares them.

    A renderer looking for `auth_jwt_signing_key.pem` while the contract
    materialized `auth_signing_key.pem` would publish a set missing that key and
    say nothing -- the file is optional by construction, because a project
    deployed through session 5 has none.
    """
    module = _load_render_jwks()
    contract = secrets_contract.load_secret_contract(REPO_ROOT / "secrets.required.yaml")
    targets = {
        consumer["target_file"]
        for secret in contract["secrets"]
        for consumer in secret["consumers"]
    }
    for declared in (
        module.SIGNING_KEY_FILE,
        module.AUTH_SIGNING_KEY_FILE,
        module.PREPARED_KEY_FILE,
    ):
        assert declared in targets, f"{declared} is not a file secrets.required.yaml writes"


# ---------------------------------------------------------------------------
# ADR 0133 -- a service is deferred for two reasons, and they are separate
# ---------------------------------------------------------------------------


def test_the_two_deferral_reasons_are_separate_constants() -> None:
    """**D463.** One name carrying two ideas is what cost the agent plane its
    first start anywhere.

    `POST_BOOTSTRAP_SERVICES` means *"authenticates as a role the bootstrap must
    activate"*. The deploy also used it to mean *"must not start before the
    files it mounts are written"*. PostgREST needs both, so membership satisfied
    the second by accident; the agent plane needs only the second, was correctly
    excluded for a reason about the first, and lost the second with it.

    Asserted as a **disjointness that is allowed to be non-empty**: a service may
    legitimately be in both. What may not happen is the two collapsing into one
    tuple again.
    """
    assert runtime_override.MCP_SERVICE in runtime_override.POST_ARTIFACT_SERVICES
    assert runtime_override.MCP_SERVICE not in runtime_override.POST_BOOTSTRAP_SERVICES, (
        "D410 still holds: the agent plane authenticates as no role"
    )
    assert runtime_override.POST_ARTIFACT_SERVICES != runtime_override.POST_BOOTSTRAP_SERVICES


def test_the_deferred_set_is_the_union_and_is_computed() -> None:
    """A third list that had to agree with two others would go stale (D175, D264).

    The CONTROL is the second assertion: a union that merely *contained* both
    would be satisfied by a hand-typed superset, which is the thing being
    refused. It has to equal the union exactly.
    """
    union = set(runtime_override.POST_BOOTSTRAP_SERVICES) | set(
        runtime_override.POST_ARTIFACT_SERVICES
    )
    assert set(runtime_override.DEFERRED_SERVICES) == union
    assert runtime_override.DEFERRED_SERVICES == tuple(sorted(union)), (
        "the deferred set is not derived from the two reasons; a typed copy drifts"
    )


def test_the_deploy_defers_the_union_rather_than_one_reason() -> None:
    """The caller, which is the half D463 was actually about.

    Both constants can be perfectly correct while the deploy reads only one of
    them -- and that is exactly what happened. §6's question 5: when a decision
    is implemented, which of its callers got it?
    """
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    assert "runtime_override.DEFERRED_SERVICES" in source
    assert 'deferred = ",".join(runtime_override.POST_BOOTSTRAP_SERVICES)' not in source, (
        "the deploy still defers only the bootstrap reason"
    )


def test_the_agent_planes_mounts_are_written_after_the_step_that_starts_it() -> None:
    """Why the agent plane needs the second reason, as an ordering fact.

    Read out of the deploy's own line order rather than asserted as a comment:
    the service is started by step 5, and both files it mounts are written after
    it. If a future change moved either write earlier, this test should be the
    thing that says the deferral is no longer needed.
    """
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    # The CALL, not the first mention. Both names appear in commentary above the
    # step that runs them, and a scan that cannot tell an instruction from a
    # description of one reports documentation as a defect.
    starts = source.index('step("5. Start the data plane')
    jwks = source.index('str(release / "bin" / "render-jwks.py")')
    lock = source.index('str(release / "bin" / "mcp-contract.sh")')

    assert starts < jwks, "the key set is written before the start; the deferral may be stale"
    assert starts < lock, "the lock is written before the start; the deferral may be stale"


# ---------------------------------------------------------------------------
# ADR 0133 -- the mount pre-flight
# ---------------------------------------------------------------------------


def test_the_deploy_calls_the_pre_flight_before_BOTH_starts() -> None:
    """The wiring, which the function's own test cannot see (D454's family).

    There are two starts and therefore two checks: step 5 starts everything not
    deferred, step 6b starts the rest. A guard wired into one of them leaves the
    other exactly as exposed as it was — and the phase that was missing its
    guard would be the one that starts the agent plane.

    Asserted on source ORDER rather than by running a deploy, because the
    property is "before", and each call is placed by hand where a human could
    put it in the wrong place.
    """
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")

    calls = [
        index
        for index in range(len(source))
        if source.startswith("    require_mounts_exist(", index)
    ]
    assert len(calls) == 2, (
        f"the deploy calls require_mounts_exist {len(calls)} times; there are two "
        "starts, so a guard on one of them leaves the other as exposed as before"
    )

    step_five = source.index('step("5. Start the data plane')
    up_at = source.index('"up",', step_five)
    step_six_b = source.index('step("6b. Start the deferred services')

    assert step_five < calls[0] < up_at, (
        "the step 5 pre-flight does not sit between the step and the `up` it guards"
    )
    assert calls[1] < step_six_b, "the step 6b pre-flight runs after the services start"


def test_mount_sources_are_read_out_of_the_override_rather_than_restated() -> None:
    """Derived, so a mount added later is covered without anyone editing a list.

    A hand-maintained inventory is precisely what goes stale when a mount is
    added — which is the defect this function exists because of.
    """
    payload = yaml.safe_dump(
        {
            "services": {
                "mcp": {
                    "volumes": [
                        "/var/lib/x/jwks.json:/etc/mcp/jwks.json:ro",
                        "/var/lib/x/mcp-capability-lock.json:/etc/mcp/capability-lock.json:ro",
                    ]
                },
                "postgrest": {"volumes": ["/var/lib/x/jwks.json:/etc/postgrest/jwks.json:ro"]},
                "postgres": {"volumes": ["pgdata:/var/lib/postgresql/data"]},
            }
        }
    ).encode("utf-8")

    assert runtime_override.mount_sources(payload, ["mcp"]) == (
        "/var/lib/x/jwks.json",
        "/var/lib/x/mcp-capability-lock.json",
    )
    # Only the named services. At step 5 the deferred services' artefacts do not
    # exist yet, and asking about them would refuse a correct deploy.
    assert runtime_override.mount_sources(payload, ["postgrest"]) == ("/var/lib/x/jwks.json",)
    # A NAMED VOLUME is not a bind mount: Docker creates one on demand and it is
    # not this check's business. Without this arm the pre-flight would refuse
    # every deploy on `pgdata`.
    assert runtime_override.mount_sources(payload, ["postgres"]) == ()


def test_the_deploy_proves_its_mounts_before_each_start(tmp_path: Path) -> None:
    """**The guard D463 says the class needs**, exercised rather than grepped.

    The ordering fix makes this instance impossible; it does not make the class
    impossible. The next service to mount a file the deploy writes late fails the
    same way, at the same silent seam.

    Three arms, and the third is the CONTROL: a present file must not be refused,
    or the guard would refuse every correct deploy and would be removed by the
    first person it inconvenienced.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_deploy_project_mounts", REPO_ROOT / "bin" / "deploy-project.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    def payload(source: str) -> bytes:
        return (
            f"services:\n  probe:\n    volumes:\n      - {source}:/etc/probe/thing.json:ro\n"
        ).encode()

    absent = tmp_path / "absent.json"
    with pytest.raises(SystemExit) as missing:
        module.require_mounts_exist(payload(str(absent)), ["probe"], when="test")
    assert missing.value.code == module.EXIT_VALIDATION

    a_directory = tmp_path / "adirectory.json"
    a_directory.mkdir()
    with pytest.raises(SystemExit) as directory:
        module.require_mounts_exist(payload(str(a_directory)), ["probe"], when="test")
    assert directory.value.code == module.EXIT_VALIDATION

    # THE CONTROL. Without it, both arms above are satisfied by a guard that
    # refuses unconditionally.
    present = tmp_path / "present.json"
    present.write_text("{}", encoding="utf-8")
    module.require_mounts_exist(payload(str(present)), ["probe"], when="test")


# ---------------------------------------------------------------------------
# Session 14's metrics route (ADR 0164)
# ---------------------------------------------------------------------------


@pytest.fixture
def metrics_labels() -> dict[str, str]:
    document = runtime_override.build_override(
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    return document["services"][runtime_override.METRICS_SERVICE]["labels"]


def test_the_metrics_rule_matches_one_path_and_not_its_neighbours(
    metrics_labels: dict[str, str],
) -> None:
    """`Path`, not `PathPrefix`, and D162 is why.

    `PathPrefix(/api/rest)` matches `/api/restaurant` -- Traefik's prefix is a
    STRING prefix, not a segment-aware one, and this repository has already paid
    for believing otherwise. Every other route here answers that with the
    two-matcher form, admitting the exact path and the subtree beneath it.

    This route has no subtree: the collector's exporter serves `/metrics` and
    404s on everything else, measured against the locked digest. So the answer
    here is `Path` alone, and a `PathPrefix` appearing in this rule would widen
    the surface to every path that merely starts with the same characters.
    """
    rule = metrics_labels[f"traefik.http.routers.{METRICS_ROUTER}.rule"]
    assert "Path(`${METRICS_PATH:?required}`)" in rule
    assert "PathPrefix" not in rule, (
        "the metrics rule uses PathPrefix, which is a string prefix in Traefik "
        "and would match /metricsanything (D162)"
    )


def test_the_metrics_credential_is_referenced_across_providers(
    metrics_labels: dict[str, str],
) -> None:
    """`@file`, and without it the surface serves without asking for a password.

    The middleware is defined by Traefik's FILE provider because it carries the
    bcrypt hash inline (ADR 0086), and a cross-provider reference without the
    suffix resolves to nothing. Traefik does not fail a router whose middleware
    is missing -- it serves it. So the omission is not a broken route, it is an
    OPEN one, which is the failure mode this assertion exists for.
    """
    attached = metrics_labels[f"traefik.http.routers.{METRICS_ROUTER}.middlewares"]
    assert f"{METRICS_AUTH}@file" in attached, (
        "the metrics credential middleware is not referenced @file. A "
        "cross-provider reference without the suffix resolves to nothing, and a "
        "router whose middleware does not resolve serves the surface without "
        "asking for the password"
    )


def test_the_metrics_route_attaches_the_baseline_before_the_credential(
    metrics_labels: dict[str, str],
) -> None:
    """Order, for the documentation route's reason: a 401 is still a response.

    The baseline chain carries the response policy every other answer gets, so
    attaching the credential first would make a refusal the one reply that
    leaves without it.
    """
    attached = metrics_labels[f"traefik.http.routers.{METRICS_ROUTER}.middlewares"]
    parts = attached.split(",")
    assert parts[0] == "${BASELINE_MIDDLEWARE_CHAIN:?required}"
    assert parts[1] == f"{METRICS_AUTH}@file"


def test_the_metrics_route_has_no_strip_prefix(metrics_labels: dict[str, str]) -> None:
    """The absence is the decision, and adding one by analogy would 404 the surface.

    Every other routed surface here rewrites the path before its upstream sees
    it. This one must not: the exporter serves `/metrics` itself, so a strip
    would deliver `/` -- which the same image answers 404 (measured in
    `test_image_contracts`). A reader who added a strip for symmetry would take
    the whole surface away and the label would look right.
    """
    stripprefixes = [key for key in metrics_labels if ".stripprefix." in key]
    assert stripprefixes == [], (
        f"the metrics route grew {stripprefixes}. The exporter serves /metrics and "
        "404s on /, so a strip delivers a path it does not serve"
    )


def test_the_metrics_service_points_at_the_exporter_port(
    metrics_labels: dict[str, str],
) -> None:
    """One constant, two readers -- the router's backend and the rendered config.

    `OTEL_EXPORTER_PORT` is written into the collector's own configuration and
    into this label. If the two disagreed the router would answer 502 with a
    healthy collector behind it, and neither file would look wrong on its own.
    """
    port = metrics_labels[f"traefik.http.services.{METRICS_ROUTER}.loadbalancer.server.port"]
    assert port == str(runtime_override.OTEL_EXPORTER_PORT)


def test_the_metrics_container_mounts_its_rendered_config(tmp_path: Path) -> None:
    """From the rendered directory, not the release (ADR 0164).

    What a deployment runs is pinned to what it rendered. A release-relative
    source would make every project on the host mount one file, and a rollback
    would change the running pipeline without changing the release that is
    supposedly deployed.
    """
    document = runtime_override.build_override(
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    volumes = document["services"][runtime_override.METRICS_SERVICE]["volumes"]
    assert volumes == [
        f"{RENDERED}/{runtime_override.OTEL_CONFIG_FILENAME}"
        f":{runtime_override.OTEL_CONFIG_CONTAINER_PATH}:ro"
    ]


def test_the_metrics_collector_is_not_deferred() -> None:
    """It mounts a RENDER-time artefact, so deferring it would be wrong.

    `POST_ARTIFACT_SERVICES` exists for services whose mounts the deploy writes
    late; `mcp` is there because its key set and capability lock do not exist at
    step 5. The collector's config is written when the render is published, so
    it is present before any container starts.

    The two reasons look alike and are not, and D463 is the record of what
    conflating them cost: `mcp` was excluded from the bootstrap tuple correctly
    and thereby lost the deferral it did need. This asserts the other direction.
    """
    assert runtime_override.METRICS_SERVICE not in runtime_override.POST_ARTIFACT_SERVICES
    assert runtime_override.METRICS_SERVICE not in runtime_override.DEFERRED_SERVICES
