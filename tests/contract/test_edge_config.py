"""Traefik static and dynamic configuration templates (Session 2, Phase 10).

These are templates, not the rendered files: `bin/edge.sh` substitutes the
placeholders into root-owned state under `/var/lib/agentic-postgres/edge/`. So
the assertions here are about what the template can and cannot become.

The two that matter most are negative. `api.insecure` must be false and no
dashboard router may exist, because an exposed Traefik API is a full read of
every route on the host. And `caServer` must point at the ACME *staging*
directory, because a template that shipped production issuance would make
"iterate until the route works" cost real rate limit.
"""

from __future__ import annotations

import functools
import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, host_config

pytestmark = [pytest.mark.contract, pytest.mark.p0]

STATIC = REPO_ROOT / "infra" / "edge" / "traefik.yaml"
DYNAMIC = REPO_ROOT / "infra" / "edge" / "dynamic" / "baseline.yaml"

#: Placeholders edge.sh substitutes. Any other `__NAME__` token is a typo that
#: would ship to the host verbatim.
STATIC_PLACEHOLDERS = {"__ACME_EMAIL__", "__ACME_RESOLVER_NAME__"}
DYNAMIC_PLACEHOLDERS = {"__HSTS_BLOCK__"}


@pytest.fixture(scope="module")
def static_config() -> dict[str, Any]:
    """Parse the template with placeholders replaced by valid stand-ins."""
    text = STATIC.read_text(encoding="utf-8")
    text = text.replace("__ACME_RESOLVER_NAME__", "letsencrypt")
    text = text.replace("__ACME_EMAIL__", "platform@example.com")
    return yaml.safe_load(text)


def placeholders_in(text: str) -> set[str]:
    import re

    return set(re.findall(r"__[A-Z0-9_]+__", text))


# ---------------------------------------------------------------------------
# Templates substitute exactly what edge.sh substitutes
# ---------------------------------------------------------------------------


def test_static_template_declares_only_known_placeholders() -> None:
    assert placeholders_in(STATIC.read_text(encoding="utf-8")) == STATIC_PLACEHOLDERS


def test_dynamic_template_declares_only_known_placeholders() -> None:
    assert placeholders_in(DYNAMIC.read_text(encoding="utf-8")) == DYNAMIC_PLACEHOLDERS


def test_static_template_parses_once_substituted(static_config: dict[str, Any]) -> None:
    assert static_config["providers"]["docker"]["watch"] is True


# ---------------------------------------------------------------------------
# Administration surface
# ---------------------------------------------------------------------------


def test_the_api_is_not_insecure_and_the_dashboard_is_off(
    static_config: dict[str, Any],
) -> None:
    """An exposed Traefik API is a full read of every route on the host."""
    assert static_config["api"]["insecure"] is False
    assert static_config["api"]["dashboard"] is False


def test_no_dashboard_entry_point_is_published(static_config: dict[str, Any]) -> None:
    """Only web, websecure and two container-local entry points exist.

    **Widened to a measured set, and made stricter in the same edit** (ADR 0167,
    which authorises the metrics entry point). `apgmetrics` joined `ping` in
    Session 14 Run 4. The set stays an exact equality rather than becoming a
    subset check: widening an allowlist to a measured set is permitted here,
    loosening it to a containment test is not.

    The second half is new, and it is what the test's NAME always claimed. The
    assertion above is about which entry points *exist*, which is a different
    property: `ping` has existed since Session 2 and has never been published.
    What matters is that nothing beyond 80 and 443 reaches the host — and that
    is a fact about `compose.yaml`'s `ports`, not about this document. **A test
    can check a string its target cannot contain** (D374); this one was reading
    the wrong file for the thing it was named after, and passed for thirteen
    sessions because no entry point had ever been added.
    """
    assert set(static_config["entryPoints"]) == {"apgmetrics", "ping", "web", "websecure"}

    model = yaml.safe_load((REPO_ROOT / "infra" / "edge" / "compose.yaml").read_text("utf-8"))
    published = model["services"]["traefik"]["ports"]
    assert published == ["80:8080", "443:8443"]

    # Derived from the entry points rather than from a list of the safe ones,
    # so a future entry point is covered by this without anybody remembering to.
    local = {
        name: spec["address"]
        for name, spec in static_config["entryPoints"].items()
        if name not in {"web", "websecure"}
    }
    assert local, "no container-local entry point; this half would be measuring nothing"
    for name, address in local.items():
        port = address.lstrip(":")
        assert not any(mapping.endswith(f":{port}") for mapping in published), (
            f"entry point {name} on {address} is published to the host"
        )


def test_ping_is_on_its_own_entry_point(static_config: dict[str, Any]) -> None:
    """`traefik healthcheck` reaches it in-container, so no shell is needed.

    That is what lets the container run read-only with every capability dropped.
    """
    assert static_config["ping"]["entryPoint"] == "ping"
    assert static_config["entryPoints"]["ping"]["address"] == ":8082"


# ---------------------------------------------------------------------------
# Discovery is doubly constrained
# ---------------------------------------------------------------------------


def test_discovery_requires_both_opt_in_and_the_project_label(
    static_config: dict[str, Any],
) -> None:
    """Two independent conditions, not one.

    `exposedByDefault: false` means a container must ask. The constraint means
    asking is not enough. A stray `traefik.enable=true` on some unrelated
    container on this host therefore still routes nothing.
    """
    docker = static_config["providers"]["docker"]
    assert docker["exposedByDefault"] is False
    assert docker["constraints"] == "Label(`apg.traefik.scope`,`managed`)"


def test_the_docker_endpoint_is_the_socket_proxy(static_config: dict[str, Any]) -> None:
    endpoint = static_config["providers"]["docker"]["endpoint"]
    assert endpoint == "tcp://docker-socket-proxy:2375"
    assert "docker.sock" not in endpoint


# ---------------------------------------------------------------------------
# ACME
# ---------------------------------------------------------------------------


def test_the_template_ships_staging_acme(static_config: dict[str, Any]) -> None:
    """Iteration must not cost production rate limit.

    Promotion rewrites caServer and storage from root-owned edge state. It is
    never reached by editing this file, and host.schema.json pins
    `initial_acme_environment` to the constant "staging" so the manifest cannot
    request otherwise either.
    """
    acme = static_config["certificatesResolvers"]["letsencrypt"]["acme"]
    assert "acme-staging-v02" in acme["caServer"]
    assert acme["storage"] == "/var/lib/traefik/acme/staging.json"
    assert acme["httpChallenge"]["entryPoint"] == "web"


def test_staging_and_production_use_separate_state_files() -> None:
    """Separate files are what make promotion reversible."""
    text = STATIC.read_text(encoding="utf-8")
    assert "staging.json" in text
    assert "production.json" not in text, "the staging template names production state"


def test_the_redirect_names_the_published_port_not_the_container_port(
    static_config: dict[str, Any],
) -> None:
    """Traefik redirects to the target entryPoint's own address by default.

    The container ports are unprivileged on purpose -- 8080 and 8443, so no
    capability is needed to bind them -- and Docker publishes them as 80 and
    443. Left to default, every HTTP visitor is sent to https://host:8443/,
    which is not published and never answers.

    Invisible from the host, where websecure really is :8443. It was found by
    following the redirect from another network, and it is the reason the
    external suite exists.
    """
    redirection = static_config["entryPoints"]["web"]["http"]["redirections"]["entryPoint"]
    assert redirection["to"] == ":443", (
        "the redirect names an entry point, so Traefik sends clients to its container port"
    )
    assert "port" not in redirection, (
        "there is no `port` field in a Traefik redirection; it refuses to start with one"
    )

    published = {"80": "8080", "443": "8443"}
    model = yaml.safe_load((REPO_ROOT / "infra" / "edge" / "compose.yaml").read_text("utf-8"))
    ports = dict(entry.split(":") for entry in model["services"]["traefik"]["ports"])
    assert ports == published, f"the published ports moved; the redirect port must follow: {ports}"


def test_http_redirects_permanently_to_https(static_config: dict[str, Any]) -> None:
    """Scheme and permanence only.

    The target used to be asserted here as the entry point name `websecure`,
    which is what sent visitors to the container port. The target is now the
    subject of the test below, which carries the reasoning.
    """
    redirection = static_config["entryPoints"]["web"]["http"]["redirections"]["entryPoint"]
    assert redirection["scheme"] == "https"
    assert redirection["permanent"] is True


# ---------------------------------------------------------------------------
# Access logs
# ---------------------------------------------------------------------------


def test_the_request_path_is_dropped_so_query_strings_cannot_be_logged(
    static_config: dict[str, Any],
) -> None:
    """ADR 0019. This asserted a key that does not exist.

    `accessLog.fields.queryParameters` was invented in a threat-model table and
    read as a control that was in place. Traefik v3.5 rejects it outright --
    "field not found, node: queryParameters" -- and refuses to start, which is
    how the edge plane failed on a real host. The test passed throughout,
    because it read the template rather than the binary.

    RequestPath carries the query string, so dropping it is the only way to keep
    query strings out of the log.
    """
    fields = static_config["accessLog"]["fields"]
    assert fields["names"]["RequestPath"] == "drop"
    assert "queryParameters" not in fields, (
        "queryParameters is not a Traefik field; the locked image refuses to start with it"
    )


def test_headers_are_dropped_by_default_and_kept_by_name(
    static_config: dict[str, Any],
) -> None:
    """Authorization and Cookie are dropped by absence, not by a denylist.

    A denylist has to be kept complete; an allowlist of two is complete by
    construction.
    """
    headers = static_config["accessLog"]["fields"]["headers"]
    assert headers["defaultMode"] == "drop"
    assert set(headers["names"]) == {"X-Request-ID", "User-Agent"}
    assert all(value == "keep" for value in headers["names"].values())


def test_logs_are_structured(static_config: dict[str, Any]) -> None:
    assert static_config["log"]["format"] == "json"
    assert static_config["accessLog"]["format"] == "json"


# ---------------------------------------------------------------------------
# Baseline dynamic policy
# ---------------------------------------------------------------------------


def _render_dynamic(acme_environment: str) -> str:
    """Through the real substitution, not a hand-written stand-in.

    This fixture used to be ``text.replace("__HSTS_BLOCK__", "")`` -- the
    staging substitution, transcribed. Transcribing it meant the production
    substitution was never rendered by any test, and the production one was the
    broken one: it also replaced the placeholder inside the file's own header
    comment, whose second and third lines then escaped the ``#`` into top-level
    YAML. The file stopped parsing, Traefik's file provider discarded every
    baseline middleware with it, and both hostnames served 404 behind valid
    certificates.
    """
    return _render_config()._substitute_hsts(DYNAMIC.read_text(encoding="utf-8"), acme_environment)


@functools.cache
def _render_config() -> Any:
    """``bin/render-config.py``, imported by path because it is not a module."""
    path = REPO_ROOT / "bin" / "render-config.py"
    spec = importlib.util.spec_from_file_location("render_config_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def dynamic_config() -> dict[str, Any]:
    return yaml.safe_load(_render_dynamic("staging"))


@pytest.mark.parametrize("acme_environment", ["staging", "production"])
def test_the_whole_edge_render_produces_files_traefik_can_load(
    tmp_path: Path, acme_environment: str
) -> None:
    """End to end, because this path had never been run offline at all.

    ``render-config.py --edge-static`` is invoked only by ``bin/edge.sh``, on a
    host, as root. Nothing in the gate reached it, so a defect in it could be
    found only by promoting a real deployment -- which is how the production
    substitution defect was found, and it cost a live outage to find it.
    """
    exit_code = _render_config().edge_static(
        REPO_ROOT / "host.example.yaml", tmp_path, acme_environment
    )
    assert exit_code == 0, "the edge render refused its own templates"

    static = yaml.safe_load((tmp_path / "traefik.yaml").read_text(encoding="utf-8"))
    dynamic = yaml.safe_load((tmp_path / "dynamic" / "baseline.yaml").read_text(encoding="utf-8"))

    assert set(dynamic["http"]["middlewares"]) == {
        "apg-security-headers",
        "apg-response-policy",
        "apg-rate-limit",
        "apg-baseline",
    }
    # And every one of them is in the chain. A middleware defined here and left
    # out of `apg-baseline` is attached to nothing, and it reads in this file
    # exactly like one that applies to every route.
    assert set(dynamic["http"]["middlewares"]["apg-baseline"]["chain"]["middlewares"]) == (
        set(dynamic["http"]["middlewares"]) - {"apg-baseline"}
    )

    resolver = next(iter(static["certificatesResolvers"].values()))["acme"]
    expected = "production.json" if acme_environment == "production" else "staging.json"
    assert resolver["storage"].endswith(expected), resolver["storage"]
    assert ("acme-staging-v02" in resolver["caServer"]) == (acme_environment == "staging"), (
        resolver["caServer"]
    )


def test_a_placeholder_reaching_a_value_is_refused_and_one_in_a_comment_is_not() -> None:
    """The distinction a raw-text scan cannot make.

    Scanning rendered text for ``__NAME__`` treated ``baseline.yaml``'s own
    documentation of its placeholder as an unsubstituted placeholder, and
    refused to render at all. Scanning the parse tells an inert comment from a
    live value without anyone writing a YAML comment stripper.
    """
    render_problem = _render_config().render_problem

    assert render_problem("t.yaml", "http:\n  x: __ACME_EMAIL__\n") == (
        "t.yaml: unsubstituted ['__ACME_EMAIL__']"
    )
    assert render_problem("t.yaml", "# documented: __ACME_EMAIL__\nhttp:\n  x: 1\n") is None
    assert "not valid YAML" in (render_problem("t.yaml", "a:\n  b: 1\n c: 2\n") or "")


@pytest.mark.parametrize("acme_environment", ["staging", "production"])
def test_the_rendered_dynamic_config_parses_in_both_environments(acme_environment: str) -> None:
    """The assertion whose absence cost a live outage.

    A file Traefik cannot parse is not refused, it is discarded, and the only
    symptom is that the middlewares it defined stop existing.
    """
    parsed = yaml.safe_load(_render_dynamic(acme_environment))

    assert set(parsed) == {"tls", "http"}, (
        f"the {acme_environment} render has top-level keys it should not: {sorted(parsed)}"
    )
    assert set(parsed["http"]["middlewares"]) == {
        "apg-security-headers",
        "apg-response-policy",
        "apg-rate-limit",
        "apg-baseline",
    }, f"the {acme_environment} render lost a baseline middleware"


def test_promotion_adds_hsts_and_staging_does_not() -> None:
    """Both directions, because either alone passes for the wrong reason."""
    staging = yaml.safe_load(_render_dynamic("staging"))["http"]["middlewares"]
    production = yaml.safe_load(_render_dynamic("production"))["http"]["middlewares"]

    assert "stsSeconds" not in staging["apg-security-headers"]["headers"]
    assert production["apg-security-headers"]["headers"]["stsSeconds"] == 31_536_000


def test_documenting_the_placeholder_cannot_inject_configuration() -> None:
    """Guard the guard.

    The header comment naming ``__HSTS_BLOCK__`` is what broke this, and it is
    worth keeping -- an undocumented placeholder is worse. What must hold is
    that documenting one cannot inject anything. Asserting the comment is still
    present keeps the regression reachable: without it a later edit could
    delete the comment, and the substitution would look correct again for a
    reason unrelated to the fix.
    """
    assert "#   __HSTS_BLOCK__" in DYNAMIC.read_text(encoding="utf-8"), (
        "the placeholder is no longer documented in a comment"
    )

    rendered = _render_dynamic("production")
    documentation = [line for line in rendered.splitlines() if "empty on staging" in line]
    assert len(documentation) == 1, documentation
    assert documentation[0].lstrip().startswith("#"), (
        f"the substitution escaped the comment: {documentation[0]!r}"
    )


def test_tls_minimum_version_is_at_least_1_2(dynamic_config: dict[str, Any]) -> None:
    assert dynamic_config["tls"]["options"]["default"]["minVersion"] == "VersionTLS12"


def test_the_baseline_chain_exists_and_is_referenced_by_name(
    dynamic_config: dict[str, Any],
) -> None:
    """One name in a project label, so adding a middleware touches no project.

    The name of this test asserted a property that was FALSE for eight sessions
    (D772): project labels enumerated two middlewares and referenced this chain
    nowhere. What the body checks is the chain's contents, which was true
    throughout. The gap between the two is the whole defect, and
    `test_every_middleware_baseline_defines_is_attached_to_project_routes`
    below is what closes it.
    """
    middlewares = dynamic_config["http"]["middlewares"]
    assert middlewares["apg-baseline"]["chain"]["middlewares"] == [
        "apg-security-headers",
        "apg-response-policy",
        "apg-rate-limit",
    ]


def test_every_middleware_baseline_defines_is_attached_to_project_routes(
    dynamic_config: dict[str, Any],
) -> None:
    """The guard D772 needed and did not have.

    Two tests already assert things about `apg-baseline`: that it contains the
    three middlewares, and that every middleware the file defines is a member of
    it. **Both were green throughout the eight sessions in which
    `apg-response-policy` was attached to no route at all**, because neither
    looks at what a project router actually references. They read the file
    against itself.

    This one starts from `host_config.BASELINE_MIDDLEWARE_CHAIN` -- the value
    every router label interpolates -- and resolves it against the file. That is
    the only direction that can see a middleware the platform defines and never
    attaches, which in this file reads exactly like one that applies everywhere.
    """
    middlewares = dynamic_config["http"]["middlewares"]

    def resolve(reference: str) -> set[str]:
        """Expand one router reference into the middlewares it actually runs."""
        bare = reference.split("@", 1)[0]
        if bare not in middlewares:
            raise AssertionError(
                f"every project route attaches {reference!r} and "
                f"infra/edge/dynamic/baseline.yaml defines no such middleware"
            )
        definition = middlewares[bare]
        if "chain" not in definition:
            return {bare}
        reached = {bare}
        for member in definition["chain"]["middlewares"]:
            reached |= resolve(member)
        return reached

    attached: set[str] = set()
    for reference in host_config.BASELINE_MIDDLEWARE_CHAIN.split(","):
        attached |= resolve(reference.strip())

    unattached = sorted(set(middlewares) - attached)
    assert not unattached, (
        f"{unattached} are defined in infra/edge/dynamic/baseline.yaml and reach no "
        "project route. A middleware defined and never attached reads in that file "
        "exactly like one that applies to everything -- which is how "
        "apg-response-policy spent eight sessions not setting Cache-Control on a "
        "REST surface whose every row is selected per caller (D772)"
    )


def test_hsts_is_absent_from_the_staging_form() -> None:
    """Sending HSTS under a staging certificate is not reversible.

    Every browser that saw the header refuses the site for max-age seconds, and
    there is no way to un-teach them.
    """
    text = DYNAMIC.read_text(encoding="utf-8")
    assert "stsSeconds" not in text
    assert "__HSTS_BLOCK__" in text, "there is no seam for promotion to add HSTS"


def test_the_rate_limit_is_documented_as_operational_not_authorization() -> None:
    """Session 2 has no authenticated surface; treating this as one is an error.

    Asserted on the comment because the distinction is the point: the config
    itself cannot express 'this is not an authorization control'.
    """
    text = DYNAMIC.read_text(encoding="utf-8")
    assert "never an authorization claim" in text


def test_edge_state_paths_agree_with_the_host_module() -> None:
    """The bind-mount sources in the edge model come from one constant."""
    assert host_config.EDGE_STATE_DIR == "/var/lib/agentic-postgres/edge"
    model = (REPO_ROOT / "infra" / "edge" / "compose.yaml").read_text(encoding="utf-8")
    assert "${EDGE_STATE_DIR:?required}/traefik.yaml" in model
    assert "${EDGE_STATE_DIR:?required}/dynamic" in model
    assert "${EDGE_STATE_DIR:?required}/acme" in model


# ---------------------------------------------------------------------------
# The socket proxy runs read-only, and had to be made able to
# ---------------------------------------------------------------------------


def edge_model_text() -> str:
    return (REPO_ROOT / "infra" / "edge" / "compose.yaml").read_text(encoding="utf-8")


def test_the_socket_proxy_stays_read_only() -> None:
    """The control that keeps a compromised proxy from rewriting its allowlist.

    The image's entrypoint renders its HAProxy config back into
    /usr/local/etc/haproxy, which read_only forbids: the container exited 1 and
    Traefik, which depends on it being healthy, never started. Dropping
    read_only was the obvious fix and the wrong one -- the allowlist is the only
    thing between a read-only Docker API and a writable one, and it lives in
    that config file.
    """
    model = yaml.safe_load(edge_model_text())
    proxy = model["services"]["docker-socket-proxy"]
    assert proxy["read_only"] is True
    assert "ALL" in proxy["cap_drop"]
    assert "no-new-privileges:true" in proxy["security_opt"]


def test_the_rendered_config_is_written_to_a_tmpfs() -> None:
    """A read-only container needs somewhere writable, and only somewhere.

    /tmp is already declared as tmpfs, so the rendered config lands nowhere that
    survives a restart and nowhere the image ships anything else.
    """
    model = yaml.safe_load(edge_model_text())
    proxy = model["services"]["docker-socket-proxy"]
    command = "\n".join(proxy["command"])

    # S108 flags these literals as insecure temp paths. They are neither: this
    # is a path *inside a read-only container*, on a tmpfs the same file
    # declares, asserted rather than created.
    rendered = "/tmp/haproxy.cfg"  # noqa: S108
    assert rendered in command
    assert f"-f {rendered}" in command, "haproxy is not pointed at the rendered copy"

    writable = {mount.split(":")[0] for mount in proxy["tmpfs"]}
    assert "/tmp" in writable  # noqa: S108


def test_the_config_directory_is_not_masked() -> None:
    """A tmpfs over /usr/local/etc/haproxy was the other tempting fix.

    It would hide the template the render reads and the errors/ pages the
    config references, so the container would start and then serve nothing.
    """
    model = yaml.safe_load(edge_model_text())
    proxy = model["services"]["docker-socket-proxy"]
    for mount in proxy["tmpfs"]:
        assert not mount.startswith("/usr/local/etc/haproxy"), (
            "a tmpfs here masks haproxy.cfg.template and errors/"
        )
    assert "haproxy.cfg.template" in "\n".join(proxy["command"]), (
        "the render no longer reads the image's own template"
    )


# ---------------------------------------------------------------------------
# Every bind source must be produced before Compose sees it
# ---------------------------------------------------------------------------


def test_edge_up_renders_the_static_configuration_before_compose(code_only) -> None:
    """Compose creates a missing bind source as a directory.

    `do_up` created the state directory and the ACME store and then started
    Compose, having never rendered traefik.yaml. Compose invented a directory at
    that path and Traefik restarted forever on "read /etc/traefik/traefik.yaml:
    is a directory" -- a template with no renderer, which is the same shape as
    the edge-state.json that had three readers and no writer.
    """
    body = code_only((REPO_ROOT / "bin" / "edge.sh").read_text(encoding="utf-8"))
    up = body.split("do_up()", 1)[1].split("\n}", 1)[0]
    assert "--edge-static" in up, "edge.sh up starts Compose without rendering the config"
    assert up.index("--edge-static") < up.index("compose --runtime up")


def test_promotion_re_renders_the_static_configuration(code_only) -> None:
    """It claimed to and did not.

    `--edge-env` writes compose.env only, so promotion moved the ACME store on
    disk while leaving Traefik pointed at the staging directory -- production
    certificates would never have been requested.
    """
    body = code_only((REPO_ROOT / "bin" / "edge.sh").read_text(encoding="utf-8"))
    promote = body.split("do_promote()", 1)[1].split("\n}", 1)[0]
    assert "--edge-static" in promote
    assert "--acme-environment production" in promote


def test_every_edge_bind_source_is_produced_by_the_up_path(code_only) -> None:
    """The general rule, not just the file that broke.

    Anything the Compose model bind-mounts out of EDGE_STATE_DIR has to be
    created before `up` runs, or Compose fills the gap with a directory and the
    failure lands inside a container.
    """
    model = yaml.safe_load((REPO_ROOT / "infra" / "edge" / "compose.yaml").read_text("utf-8"))
    sources = {
        volume["source"].replace("${EDGE_STATE_DIR:?required}/", "")
        for service in model["services"].values()
        for volume in service.get("volumes", [])
        if "${EDGE_STATE_DIR" in volume.get("source", "")
    }
    assert sources, "no edge bind mounts found; this scan is measuring nothing"

    up = code_only((REPO_ROOT / "bin" / "edge.sh").read_text(encoding="utf-8"))
    up = up.split("do_up()", 1)[1].split("\n}", 1)[0]
    renderer = (REPO_ROOT / "bin" / "render-config.py").read_text(encoding="utf-8")

    for source in sorted(sources):
        produced = source in up or source in renderer
        assert produced, (
            f"the edge model mounts {source} but nothing in do_up or render-config creates it; "
            "Compose will create a directory there"
        )


def test_edge_up_reports_why_it_failed(code_only) -> None:
    """A failure that only names the symptom sends an operator to docker logs.

    Every failure of `edge.sh up` in this session was diagnosed by hand: the
    reason was on the host the whole time and the command chose not to say it.
    """
    body = code_only((REPO_ROOT / "bin" / "edge.sh").read_text(encoding="utf-8"))
    up = body.split("do_up()", 1)[1].split("\n}", 1)[0]
    assert "docker logs" in up, "up dies without printing why"
    assert up.index("docker logs") < up.index("did not become healthy"), (
        "the diagnosis is printed after the script has already exited"
    )


def test_status_never_reports_an_absence_it_did_not_measure(code_only) -> None:
    """**D666**, found by running `status` exactly as the guide tells an operator.

    It was `compose ps 2>/dev/null || printf 'containers (not running)'`. Every
    failure became that one sentence — and the commonest failure is precisely
    the documented invocation: `bin/edge.sh status` **without root**, where the
    caller cannot reach the Docker socket. Measured on a fresh host in Session 11
    Run 8: two containers Up and healthy, and this command reported them not
    running. An operator who believes it restarts an edge that is serving.

    D145 and D548 are the same defect in two third parties five sessions apart —
    the state was in a field and never in the exit code. ADR 0157's
    `undetermined` and ADR 0158's `unknown` are this repository's answer to it,
    and this command predates both.

    The assertion is on the **wording**, because the wording is what an operator
    acts on: a failed read may not claim the containers are absent.
    """
    body = code_only((REPO_ROOT / "bin" / "edge.sh").read_text(encoding="utf-8"))
    status = body.split("do_status()", 1)[1].split("\n}", 1)[0]

    assert "compose ps" in status, "status no longer lists containers at all"
    assert "(not running)" not in status, (
        "status still says 'not running' on a failed read. `compose ps` fails for "
        "permission, for a missing daemon and for a malformed project, and only "
        "one of those means nothing is running (D666)"
    )
    assert "could not be read" in status, (
        "status does not distinguish 'nobody could look' from 'nothing is there'"
    )
