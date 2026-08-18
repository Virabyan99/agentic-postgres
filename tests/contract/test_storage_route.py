"""The published storage route: its precedence, its strip, and its CORS policy.

**`/api/app/storage` is the first route this project publishes INSIDE another
one.** Every route before it was a sibling — `/api/rest`, `/api/app`,
`/docs/rest`, `/docs/app` — so no request has ever matched two routers and no
ordering has ever mattered. Every request to this surface matches the
application router as well, and if that one wins, `POST
/api/app/storage/upload-intents` reaches the auth service as
`/storage/upload-intents` and FastAPI answers 404. At the edge that is
indistinguishable from a missing route, a missing container, and Traefik's own
404 (D186, D187).

**What was measured, against the locked Traefik and read back from its own API
rather than inferred from a response** (ADR 0108):

* the default priority is the rule string's **length**, exactly — `priority=68`
  for a 68-character rule and `priority=84` for an 84-character one;
* priority is length and **not specificity**, with the control that makes it a
  finding: a router ruled ``PathPrefix(`/api/app/deep`)`` is strictly more
  specific than the application router and **loses to it**, at 50 characters
  against 68;
* a sibling of a nested path is **not a 404** — `/api/app/storagex` is caught by
  the parent router and reaches the auth service — so a boundary proof here
  cannot assert a status code.

And for the CORS half (ADR 0109), with controls:

* a comma-separated origin list in one label parses into a list;
* an **empty** list parses to `None`, leaves the middleware enabled, and permits
  nothing — which is what makes attaching it unconditionally safe;
* an **unlisted origin is not refused**: the request is forwarded to the service
  and answered normally, with only `Access-Control-Allow-Origin` withheld. The
  middleware instructs a browser; it does not control access.

Nothing here reaches a network. These tests assert the rendered labels and the
rendered `compose.env`, which is where a mistake would live.
"""

from __future__ import annotations

import re

import pytest
import yaml
from tests.contract.test_runtime_override import NAMES, RENDERED

from agentic_postgres import REPO_ROOT, config, naming, rendering, runtime_override

pytestmark = [pytest.mark.contract, pytest.mark.p0]

MODEL = REPO_ROOT / "compose.yaml"


@pytest.fixture
def override() -> dict:
    return runtime_override.build_override(
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
    )


@pytest.fixture
def storage_labels(override: dict) -> dict[str, str]:
    return override["services"][runtime_override.STORAGE_SERVICE]["labels"]


@pytest.fixture
def app_labels(override: dict) -> dict[str, str]:
    return override["services"][runtime_override.AUTH_SERVICE]["labels"]


def _rule(labels: dict[str, str]) -> str:
    matched = [value for key, value in labels.items() if key.endswith(".rule")]
    assert len(matched) == 1, f"expected exactly one router rule, found {len(matched)}"
    return matched[0]


def _interpolate(rule: str, values: dict[str, str]) -> str:
    """Substitute `${NAME:?required}` / `${NAME?required}` the way Compose does.

    **The interpolation is the whole point of doing this.** The raw label values
    hold `${API_APP_PATH:?required}` and `${API_STORAGE_PATH:?required}`, which
    differ by four characters because one variable name is longer than the
    other. A length comparison over the RAW strings would pass, and would be
    measuring the spelling of two variable names rather than the two paths — a
    tautology of exactly D173's shape, in the test written to prevent one.
    """

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        assert name in values, f"{name} is referenced by a label and not rendered"
        return values[name]

    return re.sub(r"\$\{([A-Z0-9_]+)(?::?\?[^}]*)?\}", replace, rule)


def _compose_env(project: str = "project.example.yaml") -> dict[str, str]:
    """The rendered `compose.env` for one example manifest, as a mapping."""
    manifest = config.load_project_manifest(REPO_ROOT / project)
    identity = naming.derive(
        slug=manifest["project"]["slug"],
        environment=manifest["project"]["environment"],
        domain=manifest["project"]["domain"],
        api_base_path=manifest["api"]["public_base_path"],
        mcp_base_path=manifest["mcp"]["public_base_path"],
        storage_enabled=bool((manifest.get("storage") or {}).get("enabled")),
        storage_bucket=(manifest.get("storage") or {}).get("bucket"),
        storage_prefix=(manifest.get("storage") or {}).get("prefix"),
    )
    database = manifest["database"]
    raw = rendering.build_compose_env(
        identity,
        config.database_budget(database),
        database,
        api=manifest.get("api"),
        storage={**config.STORAGE_DEFAULTS, **(manifest.get("storage") or {})},
    )
    values: dict[str, str] = {}
    for line in raw.decode("utf-8").splitlines():
        if line and not line.startswith("#"):
            name, _, value = line.partition("=")
            values[name] = value
    return values


# ---------------------------------------------------------------------------
# ADR 0108 — the nested route has to outrank the one it sits inside
# ---------------------------------------------------------------------------


def test_the_storage_rule_is_longer_than_the_application_rule_it_sits_inside(
    storage_labels, app_labels
) -> None:
    """The measured invariant, on the rules Traefik actually sees.

    Traefik's default priority is the rule string's length, so the nested route
    wins **because** its rule is longer. The storage rule is the application
    rule with `/storage` inserted into both matchers, which makes it exactly
    sixteen characters longer for every project and every domain — both carry
    the same `Host()` clause, so the domain cancels.

    Goes red if: the storage rule is rewritten as a single `PathPrefix` (which
    would make it *shorter* than the parent's and route nothing), if the strip
    or the boundary construction changes, or if the application route moves
    deeper.
    """
    values = _compose_env()
    application = _interpolate(_rule(app_labels), values)
    storage = _interpolate(_rule(storage_labels), values)

    assert len(storage) > len(application), (
        f"the storage rule is {len(storage)} characters and the application rule it "
        f"sits inside is {len(application)}. Traefik's default priority IS the rule "
        "length (measured), so the application router would win every request to "
        "the storage surface and the auth service would answer 404"
    )
    assert len(storage) - len(application) == 2 * len(naming.STORAGE_PATH_SUFFIX), (
        "the difference is not the suffix inserted into both matchers; the two "
        "rules are no longer the same construction and the margin is accidental"
    )


def test_the_storage_rule_uses_the_two_matcher_segment_boundary(storage_labels) -> None:
    """`PathPrefix` is a string prefix, and here it also decides precedence.

    The pair — the exact path, and anything strictly beneath it — is what gives
    a segment boundary (D162). For this route it is load-bearing a second time:
    it is what makes the rule long enough to outrank the application router.

    Goes red if: either matcher is dropped, or the boundary is written as a bare
    prefix.
    """
    rule = _rule(storage_labels)
    path = "${API_STORAGE_PATH:?required}"
    assert f"Path(`{path}`)" in rule
    assert f"PathPrefix(`{path}/`)" in rule
    assert f"PathPrefix(`{path}`)" not in rule.replace(f"PathPrefix(`{path}/`)", ""), (
        "the rule carries a bare PathPrefix on the storage path, which matches "
        "/api/app/storagex as well"
    )


def test_no_router_sets_an_explicit_priority(override) -> None:
    """ADR 0108 decided the ordering is derived, so nothing may pin it.

    An explicit priority on one router would need one on every router it has to
    beat, and the number a router has to beat depends on the project's domain
    length. A single pinned priority is a second authority for an ordering the
    rule already determines.

    Goes red if: anything adds a `.priority` label — which would be a decision
    this ADR made the other way.
    """
    for name, definition in override["services"].items():
        for key in definition.get("labels", {}):
            assert not key.endswith(".priority"), (
                f"{name} pins a router priority; ADR 0108 derives the ordering from "
                "the rule and a pinned number is a second authority for it"
            )


def test_the_storage_strip_removes_the_storage_path_and_not_the_application_path(
    storage_labels, app_labels
) -> None:
    """Two routers onto two containers, stripping two different prefixes.

    The storage surface routes `/upload-intents` and `/objects/{id}` at its
    root. Stripping the application path would deliver `/storage/upload-intents`
    and the service would answer 404 — which at the edge reads as a missing
    route and is not one (D187).

    Goes red if: the two routes are given one strip middleware, or the storage
    strip is pointed at the application path.
    """
    strips = {
        key: value for key, value in storage_labels.items() if key.endswith(".stripprefix.prefixes")
    }
    assert list(strips.values()) == ["${API_STORAGE_PATH:?required}"], strips

    application_strips = {key for key in app_labels if key.endswith(".stripprefix.prefixes")}
    storage_strips = set(strips)
    assert not (application_strips & storage_strips), (
        "the two routes share a strip-prefix middleware; one middleware cannot "
        "remove two different prefixes"
    )


def test_the_storage_middlewares_are_defined_on_the_storage_container(
    storage_labels, app_labels
) -> None:
    """A middleware defined on another container is withdrawn with it.

    Measured: a router referencing a middleware defined by labels on a different
    container resolves while that container runs, and goes `status=disabled`
    with `middleware "…" does not exist` when it stops — taking the borrowing
    route to Traefik's own 404. `auth` and `storage` are separate containers with
    separate restarts, so a borrowed middleware would make either one's restart
    the other's outage.

    Every middleware the storage router names must therefore be *defined* by a
    label on the storage container. The baseline chain is the exception and is
    excluded by name: it is the edge's own, defined once in the shared file
    provider, and it is already a dependency of every route on this host.

    **The converse is asserted too, and the battery is why.** Dropping a
    middleware from the chain while leaving its definition in place left the
    first version of this test green — a defined-but-unattached CORS middleware
    is a policy that exists, parses, and is applied to nothing. Traefik reports
    it `enabled` either way.

    Goes red if: the storage router names `apg-<key>-app-buffering` or any other
    middleware it does not define; or defines one it does not name.
    """
    chain = next(value for key, value in storage_labels.items() if key.endswith(".middlewares"))
    named = [entry for entry in chain.split(",") if not entry.startswith("${")]
    defined = {
        key.split(".")[3] for key in storage_labels if key.startswith("traefik.http.middlewares.")
    }
    assert named, "the storage router names no middleware of its own"
    for entry in named:
        assert entry in defined, (
            f"the storage router names {entry!r} and does not define it. If it is "
            "defined on another container, that container's restart takes this "
            "route down with it"
        )
    assert defined == set(named), (
        f"the storage router defines {sorted(defined - set(named))} and does not "
        "attach it. A middleware nothing references is a policy applied to no "
        "request, and Traefik calls it `enabled` regardless"
    )
    assert not (
        defined
        & {key.split(".")[3] for key in app_labels if key.startswith("traefik.http.middlewares.")}
    ), "the two routes define a middleware under the same name"


def test_the_two_routes_share_one_body_bound(storage_labels, app_labels) -> None:
    """One number from `strict_json.MAX_BODY_BYTES`, reaching both routes.

    Both modes run the same parser in the same image (ADR 0101), and the service
    refuses an oversized body only *after* `request.body()` has read every byte
    of it — so the edge is the only thing that bounds what either process
    allocates. A `STORAGE_REQUEST_BODY_MAX_BYTES` would be a second constant that
    agreed with the first until somebody changed one, which is D264's cost.

    Goes red if: the storage route grows its own limit variable.
    """

    def limits(labels: dict[str, str]) -> set[str]:
        return {value for key, value in labels.items() if ".buffering." in key}

    assert limits(storage_labels) == {"${AUTH_REQUEST_BODY_MAX_BYTES:?required}"}
    assert limits(storage_labels) <= limits(app_labels)


# ---------------------------------------------------------------------------
# ADR 0109 — the CORS middleware
# ---------------------------------------------------------------------------


def test_the_cors_middleware_is_a_label_on_the_storage_container(storage_labels) -> None:
    """Not a file-provider document, which is where D323 predicted it.

    The origin list is `storage.allowed_cors_origins` — a manifest field,
    rendered into `compose.env` and published in `outputs.json`. ADR 0086's rule
    for the file provider is about where a *secret* may go, and this is not one.
    A label has exactly the router's lifetime; a second artifact does not.

    Goes red if: the CORS keys leave this label set.
    """
    keys = [key for key in storage_labels if ".headers.accesscontrol" in key]
    assert keys, "the storage router defines no CORS middleware"
    assert all(key.startswith("traefik.http.middlewares.") for key in keys)


def test_the_cors_middleware_advertises_the_methods_the_router_serves() -> None:
    """The advertised methods are the surface's, not a list written twice.

    `OPTIONS` is here because the middleware answers the preflight itself —
    measured, with the control: attached, the `OPTIONS` never reached the
    backend; removed, it did. The other three are what the four endpoints
    declare.

    Goes red if: a fifth endpoint is added with a method this list does not
    carry, or a method is advertised that no endpoint serves.
    """
    from app import storage_routes

    served = {
        method
        for route in storage_routes.router.routes
        for method in getattr(route, "methods", set())
        if method != "HEAD"
    }
    advertised = set(runtime_override.STORAGE_CORS_METHODS)

    assert served <= advertised, (
        f"the storage surface serves {sorted(served - advertised)} and the CORS "
        "middleware does not advertise it; a browser will not send the request"
    )
    assert advertised - served == {"OPTIONS"}, (
        f"the CORS middleware advertises {sorted(advertised - served - {'OPTIONS'})}, "
        "which no endpoint serves. OPTIONS is the one legitimate extra -- the "
        "middleware answers the preflight itself"
    )


def test_the_origin_list_reaches_the_label_as_one_compose_value(storage_labels) -> None:
    """One list, rendered once, referenced rather than restated.

    Measured: Traefik parses a comma-separated label value into a list, read
    back from its own API as `['https://a.example', 'https://b.example']`.

    Goes red if: the origins are written into the override, which would put a
    manifest value in a file the deploy renders from the host manifest.
    """
    value = next(
        value
        for key, value in storage_labels.items()
        if key.endswith(".headers.accesscontrolalloworiginlist")
    )
    assert value == "${STORAGE_CORS_ALLOWED_ORIGINS?required}", value


def test_the_origin_list_reference_admits_an_empty_value(storage_labels) -> None:
    """`?required`, not `:?required`, and it is the only one in the file.

    The colon form refuses an EMPTY value as firmly as an unset one (D178,
    measured), and an empty origin list is a legitimate configuration: a project
    that enables storage and permits no browser origin. Measured on the locked
    Traefik — an empty list parses to `None`, the middleware stays enabled, and
    it permits nothing, which is why it can be attached unconditionally.

    Goes red if: somebody "fixes" the missing colon, which would make every
    project without a browser origin fail to render.
    """
    origins = next(
        value
        for key, value in storage_labels.items()
        if key.endswith(".headers.accesscontrolalloworiginlist")
    )
    assert ":?" not in origins, (
        "the origin list is referenced with the colon form, which refuses an empty "
        "value -- and an empty origin list is a project that permits no browser"
    )
    assert "?" in origins, (
        "the origin list is referenced with no failure clause at all, so a missing "
        "key would render as permissively-shaped nothing rather than refusing"
    )

    others = [
        value
        for key, value in storage_labels.items()
        if "${" in value
        and key
        != next(
            key for key in storage_labels if key.endswith(".headers.accesscontrolalloworiginlist")
        )
    ]
    for value in others:
        for reference in re.findall(r"\$\{[A-Z0-9_]+[^}]*\}", value):
            assert ":?" in reference, (
                f"{reference} admits an empty value and is not the origin list; only "
                "the origin list has a meaningful empty case"
            )


def test_the_compose_value_is_the_list_the_document_publishes() -> None:
    """One origin list, two renderings, and a test that ties them together.

    D323's requirement in one assertion: the edge middleware and the bucket's
    own CORS policy are two renderings of `storage.allowed_cors_origins`, so the
    value handed to Traefik has to be the value the document publishes. A second
    list is what D177 cost when two derivations of one path disagreed.

    The alpha fixture declares **two** origins, out of order, so the join and
    the sort are both measurable — with one entry everywhere, `",".join(...)`
    and `origins[0]` are the same function (D332).

    Goes red if: either side stops sorting, or the join changes separator, or
    the two are rendered from different fields.
    """
    manifest = config.load_project_manifest(REPO_ROOT / "project.example.yaml")
    declared = manifest["storage"]["allowed_cors_origins"]
    assert len(declared) > 1, (
        "the alpha fixture declares one origin or none; a single-element list "
        "cannot tell a join from an index (D332)"
    )
    assert declared != sorted(declared), (
        "the alpha fixture declares its origins already sorted, so nothing here "
        "can tell a renderer that sorts from one that does not"
    )

    values = _compose_env()
    assert values["STORAGE_CORS_ALLOWED_ORIGINS"] == ",".join(sorted(declared))

    identity = naming.derive(
        slug=manifest["project"]["slug"],
        environment=manifest["project"]["environment"],
        domain=manifest["project"]["domain"],
        api_base_path=manifest["api"]["public_base_path"],
        mcp_base_path=manifest["mcp"]["public_base_path"],
    )
    outputs = rendering.build_outputs(
        manifest,
        config.load_capabilities_manifest(REPO_ROOT / "capabilities.example.yaml"),
        identity,
        {},
    )
    assert outputs["storage"]["allowed_cors_origins"] == sorted(declared)
    assert (
        values["STORAGE_CORS_ALLOWED_ORIGINS"].split(",")
        == outputs["storage"]["allowed_cors_origins"]
    )


def test_two_projects_render_two_origin_lists() -> None:
    """The renderer reads the manifest rather than a constant.

    Held at this level as well as in the fixtures, so a later edit to either
    example cannot quietly remove the only coverage (D332).

    Goes red if: the origin list is hard-coded, or read from the wrong project.
    """
    alpha = _compose_env("project.example.yaml")["STORAGE_CORS_ALLOWED_ORIGINS"]
    alpine = _compose_env("project.second.example.yaml")["STORAGE_CORS_ALLOWED_ORIGINS"]
    assert alpha and alpine and alpha != alpine


# ---------------------------------------------------------------------------
# The container the route points at
# ---------------------------------------------------------------------------


def test_the_router_names_the_port_the_container_binds(storage_labels) -> None:
    """A publication written against a number the process does not bind.

    `compose.yaml` sets `APG_LISTEN_PORT` and `settings.py` requires it; Traefik
    needs the *container* port, and a router pointed at the wrong number maps
    onto nothing and answers 502.

    **The comparison is against the RENDERED LABEL, and the battery is why.**
    The first version compared `compose.yaml`'s `APG_LISTEN_PORT` against
    `runtime_override.STORAGE_SERVICE_PORT` — two constants, neither of which is
    what the router publishes. Pointing the label at `REST_SERVICE_PORT` left it
    green: the two constants still agreed, and the thing under test was never
    read. D173's tautology, in a test written to prevent a routing defect.

    The two constants happen to hold the same number (8080), which is what makes
    the mistake invisible to a reader as well: a label naming
    `AUTH_SERVICE_PORT` would be wrong for the same reason and would render
    identically today.

    Goes red if: the storage router's service port stops being the port the
    storage container binds — including when the wrong constant is named.
    """
    # The variable's NAME from `settings.SHARED_VARIABLES` rather than written
    # here. One authority for it, and it also keeps `test_environment_gates`
    # from reading this as an environment the test itself consumes -- which it
    # did, and the fix was the code rather than the scanner (D351's shape).
    from app import settings

    key = next(name for name in settings.SHARED_VARIABLES if name.endswith("LISTEN_PORT"))
    model = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    declared = model["services"][runtime_override.STORAGE_SERVICE]["environment"][key]

    published = {
        value for key, value in storage_labels.items() if key.endswith(".loadbalancer.server.port")
    }
    assert published == {str(int(declared))}, (
        f"the storage router publishes port {published} and the container binds "
        f"{declared}. Traefik would forward to a port nothing is listening on"
    )


def _deploy_module():
    """`bin/deploy-project.py`, imported for its pure observers.

    Importing it runs no deploy: everything at module scope is constants and
    function definitions, and `main()` is behind the usual guard. The same
    loader `test_deployed_output.py` uses.
    """
    import importlib.util

    source = REPO_ROOT / "bin" / "deploy-project.py"
    specification = importlib.util.spec_from_file_location("apg_deploy_storage_route", source)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_an_uncredentialed_project_publishes_no_storage_route(capsys) -> None:
    """D326's gate, and it refuses before it probes.

    A storage container without an R2 credential starts, serves, and answers
    every request with the 404 its provider errors collapse to
    (`storage_routes._guard`) — which is indistinguishable from an object that
    is not yours. So a route that answered a *refusal* would look correct for
    the wrong reason, which is the false green this repository keeps producing.

    The observer takes the credential as a parameter rather than reading it, so
    this decision is testable with no host, no generation and no network — the
    shape D341 extracted `activated_login_roles` into for exactly this reason.

    Goes red if: the gate is dropped, or inverted, or the observer probes first
    and decides afterwards.
    """
    module = _deploy_module()

    assert module.observe_storage(
        "https://alpha.example.com/api/app/storage", credentialed=False
    ) == ("unavailable")
    printed = capsys.readouterr().out
    assert "R2 credential" in printed and "D326" in printed, (
        "the refusal says nothing about why; an operator reading this has to "
        "guess which of the two gates fired"
    )


def test_the_credential_gate_names_both_halves_of_the_r2_secret() -> None:
    """Both halves, by the names `secrets.required.yaml` gives them.

    An access key id without its secret is not a credential, and the generation
    can carry one without the other: they are two entries in the contract with
    two provider paths. Naming only one would publish a route for a container
    that cannot sign a URL.

    Goes red if: a name here drifts from the contract, or one half is dropped.
    """
    from agentic_postgres import secrets_contract

    module = _deploy_module()
    contract = secrets_contract.load_secret_contract(REPO_ROOT / "secrets.required.yaml")
    declared = {entry["name"] for entry in contract["secrets"]}
    for name in module.STORAGE_CREDENTIAL_NAMES:
        assert name in declared, f"{name} is not a secret this repository declares"
    assert set(module.STORAGE_CREDENTIAL_NAMES) == {
        name for name in declared if name.startswith("r2_")
    }, "the gate does not name every R2 secret the contract declares"


def test_the_storage_service_is_held_back_until_the_bootstrap_has_run() -> None:
    """D324: it authenticates as a bootstrap-activated role.

    `storage_service` is NOLOGIN until the bootstrap plane activates it, so a
    container started before that step fails its healthcheck against `password
    authentication failed` — the message a *wrong* credential gets, which is the
    diagnosis this list exists to keep nobody from having to make.

    Goes red if: the service is dropped from `POST_BOOTSTRAP_SERVICES` while
    still carrying a database credential.
    """
    assert runtime_override.STORAGE_SERVICE in runtime_override.POST_BOOTSTRAP_SERVICES
