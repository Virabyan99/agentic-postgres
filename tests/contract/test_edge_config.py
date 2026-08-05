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
    """Only web, websecure and the container-local ping exist."""
    assert set(static_config["entryPoints"]) == {"ping", "web", "websecure"}


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


def test_http_redirects_permanently_to_https(static_config: dict[str, Any]) -> None:
    redirection = static_config["entryPoints"]["web"]["http"]["redirections"]["entryPoint"]
    assert redirection["to"] == "websecure"
    assert redirection["scheme"] == "https"
    assert redirection["permanent"] is True


# ---------------------------------------------------------------------------
# Access logs
# ---------------------------------------------------------------------------


def test_query_parameters_are_dropped(static_config: dict[str, Any]) -> None:
    """The easiest place for a token to end up in a log.

    The setting is a claim; the live suite's random query-string sentinel is
    the measurement.
    """
    fields = static_config["accessLog"]["fields"]
    assert fields["queryParameters"]["defaultMode"] == "drop"


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


@pytest.fixture(scope="module")
def dynamic_config() -> dict[str, Any]:
    text = DYNAMIC.read_text(encoding="utf-8")
    # Empty is what edge.sh substitutes on staging.
    return yaml.safe_load(text.replace("__HSTS_BLOCK__", ""))


def test_tls_minimum_version_is_at_least_1_2(dynamic_config: dict[str, Any]) -> None:
    assert dynamic_config["tls"]["options"]["default"]["minVersion"] == "VersionTLS12"


def test_the_baseline_chain_exists_and_is_referenced_by_name(
    dynamic_config: dict[str, Any],
) -> None:
    """One name in a project label, so adding a middleware touches no project."""
    middlewares = dynamic_config["http"]["middlewares"]
    assert middlewares["apg-baseline"]["chain"]["middlewares"] == [
        "apg-security-headers",
        "apg-rate-limit",
    ]


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
