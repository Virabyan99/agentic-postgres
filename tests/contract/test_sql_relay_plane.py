"""The SQL relay's plane: the control project only, routed by its own host, holding nothing.

Session 44 (ADR 0286): `SQL-PLANE-001`. Two real manifests are rendered -- the
control example and `project.example.yaml` -- and everything after reads the
rendered `compose.env` the way production does: `project-runtime.sh`'s own
`session_profiles` for the profile, and the deploy's own `_override_sql_relay`
and `_override_names` for the router (`test_console_plane.py`'s shape). So the
profile that starts the relay and the router that publishes it are proved to
read one value, and every name the relay is given is proved to be derived.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, host_config, naming, rendering, runtime_override

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

DEPLOY = REPO_ROOT / "bin" / "deploy-project.py"
RUNTIME = REPO_ROOT / "bin" / "project-runtime.sh"
CAPABILITIES = REPO_ROOT / "capabilities.example.yaml"
CONTROL = REPO_ROOT / "project.control.example.yaml"
PLAIN = REPO_ROOT / "project.example.yaml"
RELAY_KEYS = (
    "APG_SQL_RELAY",
    "APG_SQL_RELAY_HOST",
    "APG_SQL_RELAY_ZONE",
    "APG_SQL_RELAY_UPSTREAM",
    "APG_CONSOLE_SQL_RELAY_ORIGIN",
    "SQL_RELAY_ROUTER_NAME",
    "SQL_RELAY_MEMORY_LIMIT",
    "SQL_RELAY_PIDS_LIMIT",
    "SQL_RELAY_CPUS",
)


@pytest.fixture
def deploy() -> Any:
    spec = importlib.util.spec_from_file_location("_apg_deploy_sql_relay_under_test", DEPLOY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    generated = tmp_path / "generated"
    monkeypatch.setattr(rendering, "GENERATED_ROOT", generated)
    monkeypatch.setattr(rendering, "STAGING_ROOT", generated / ".staging")
    monkeypatch.setattr(rendering, "LOCK_ROOT", generated / ".locks")
    return generated


def _render(manifest: Path) -> Path:
    return rendering.render_project(manifest, CAPABILITIES, validate_compose=False)


def _values(rendered: Path) -> dict[str, str]:
    values = {}
    for line in (rendered / "compose.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            name, _, value = line.partition("=")
            values[name] = value
    return values


def _profiles(rendered: Path, tmp_path: Path) -> list[str]:
    """`project-runtime.sh`'s own `session_profiles`, from a copy with `main` removed."""
    text = RUNTIME.read_text(encoding="utf-8")
    for old, new in (
        ('ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"',
         f'ROOT_DIR="{REPO_ROOT}"'),
        ('\nmain "$@"\n', "\n"),
    ):  # fmt: skip
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    copy = tmp_path / "project-runtime.sh"
    copy.write_text(text, encoding="utf-8")
    done = subprocess.run(
        ["bash", "-c", f'. "{copy}"; session_profiles 43 "{rendered}"'],
        capture_output=True, text=True, check=False, timeout=30,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    return done.stdout.split()


def _override(deploy: Any, rendered: Path) -> dict[str, Any]:
    compose_env = rendered / "compose.env"
    return runtime_override.build_override(
        **deploy._override_names(compose_env),
        **deploy._override_control(compose_env),
        **deploy._override_console(compose_env),
        **deploy._override_sql_relay(compose_env),
        rest_enabled=deploy._rest_enabled(compose_env),
        https_entrypoint="websecure",
        rendered_directory="/var/lib/agentic-postgres/rendered/x",
    )


def test_the_profile_is_added_only_for_the_control_project(sandbox: Path, tmp_path: Path) -> None:
    on = _profiles(_render(CONTROL), tmp_path)
    off = _profiles(_render(PLAIN), tmp_path)
    assert on.count("sql-relay") == 1 and on[on.index("sql-relay") - 1] == "--profile", on
    assert "sql-relay" not in off, off
    # The control: the console's profile follows the same switch's twin.
    assert "console" in on and "console" not in off


def test_the_router_rule_is_the_relay_host_alone(deploy: Any, sandbox: Path) -> None:
    on = _override(deploy, _render(CONTROL))
    off = _override(deploy, _render(PLAIN))
    assert runtime_override.SQL_RELAY_SERVICE not in off["services"]
    labels = on["services"][runtime_override.SQL_RELAY_SERVICE]["labels"]
    routers = {key.split(".")[3] for key in labels if key.startswith("traefik.http.routers.")}
    assert len(routers) == 1, routers
    router = routers.pop()
    assert router.endswith("-sql-relay")
    prefix = f"traefik.http.routers.{router}"
    assert labels[f"{prefix}.rule"] == "Host(`${APG_SQL_RELAY_HOST:?required}`)"
    assert labels[f"{prefix}.middlewares"] == "${BASELINE_MIDDLEWARE_CHAIN:?required}"
    assert labels[f"{prefix}.entrypoints"] == "websecure"
    assert labels[f"{prefix}.tls.certresolver"] == "${ACME_RESOLVER_NAME:?required}"
    assert labels[f"traefik.http.services.{router}.loadbalancer.server.port"] == "8080"
    assert not [key for key in labels if ".middlewares." in key], "the relay defines a middleware"
    # A relay with no router name is refused, as the console's rule is.
    names = deploy._override_names(_render(CONTROL) / "compose.env")
    with pytest.raises(ValueError, match="sql_relay_router_name"):
        runtime_override.build_override(
            **names, sql_relay=True, sql_relay_router_name="", rest_enabled=True,
            https_entrypoint="websecure", rendered_directory="/x",
        )  # fmt: skip


def test_the_relay_holds_no_secret_and_no_mount(deploy: Any, sandbox: Path) -> None:
    model = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    relay = model["services"]["sql-relay"]
    assert relay["profiles"] == ["sql-relay"]
    assert relay["build"] == {
        "context": "./services/sql-relay",
        "args": {
            "PYTHON_BASE_IMAGE": "${PYTHON_RUNTIME_IMAGE:?required}",
            "WEBSOCKETS_VERSION": "${WEBSOCKETS_VERSION:?required}",
        },
    }
    # `.get`: an `APG_` subscript in a test body reads as an environment gate (D2381).
    environment = relay["environment"]
    assert set(environment) == {
        "APG_SQL_RELAY_PORT",
        "APG_SQL_RELAY_ALLOWED_ORIGIN",
        "APG_SQL_RELAY_ZONE",
        "APG_SQL_RELAY_UPSTREAM",
    }
    assert environment.get("APG_SQL_RELAY_PORT") == "8080"
    assert environment.get("APG_SQL_RELAY_ALLOWED_ORIGIN") == "${APG_CONSOLE_ORIGIN?required}"
    assert environment.get("APG_SQL_RELAY_ZONE") == "${APG_SQL_RELAY_ZONE?required}"
    assert environment.get("APG_SQL_RELAY_UPSTREAM") == "${APG_SQL_RELAY_UPSTREAM?required}"
    for key in ("volumes", "secrets", "env_file", "ports", "depends_on", "expose", "extra_hosts"):
        assert key not in relay, key
    assert relay["networks"] == ["edge"]
    assert relay["read_only"] is True and relay["user"] == "65532:65532"
    assert relay["cap_drop"] == ["ALL"] and relay["security_opt"] == ["no-new-privileges:true"]
    override = _override(deploy, _render(CONTROL))["services"][runtime_override.SQL_RELAY_SERVICE]
    assert set(override) == {"labels"}, "the override gives the relay something besides a router"


def test_the_names_are_derived(sandbox: Path) -> None:
    """Every value the relay and the console's policy read is the render's,
    from `naming` and `host_config` -- never typed -- and EMPTY off the control
    project, where `compose.yaml` allows it (`?required` without the colon)."""
    on, off = _values(_render(CONTROL)), _values(_render(PLAIN))
    assert set(RELAY_KEYS) <= set(rendering.COMPOSE_ENV_KEYS)
    domain = yaml.safe_load(CONTROL.read_text(encoding="utf-8"))["project"]["domain"]
    zone = naming.sql_relay_zone(domain)
    host = naming.sql_relay_host(domain)
    assert host == f"sql.{zone}" and domain.endswith(f".{zone}")
    # `.get`, never a subscript (D2381).
    assert on.get("APG_SQL_RELAY") == "1" and off.get("APG_SQL_RELAY") == "0"
    assert on.get("APG_SQL_RELAY_HOST") == host
    assert on.get("APG_SQL_RELAY_ZONE") == zone
    assert (
        on.get("APG_SQL_RELAY_UPSTREAM")
        == (f"{host_config.EDGE_PROXY_ALIAS}:{host_config.EDGE_POSTGRES_PORT}")
        == "apg-edge-proxy:8432"
    )
    assert on.get("APG_CONSOLE_SQL_RELAY_ORIGIN") == f"wss://{host}"
    for key in ("APG_SQL_RELAY_HOST", "APG_SQL_RELAY_ZONE", "APG_SQL_RELAY_UPSTREAM",
                "APG_CONSOLE_SQL_RELAY_ORIGIN"):  # fmt: skip
        assert off.get(key) == "", key
    # Derived for every project, as the console's router name is.
    for values in (on, off):
        expected = naming.sql_relay_router_name(values["PROJECT_KEY"])
        assert values["SQL_RELAY_ROUTER_NAME"] == expected
        assert expected == f"apg-{values['PROJECT_KEY']}-sql-relay"
    assert on["SQL_RELAY_MEMORY_LIMIT"] == "192m" and on["SQL_RELAY_CPUS"] == "0.5"
    # The deployed zone (control.agenticpostgresql.com) and the refusals.
    assert naming.sql_relay_host("control.agenticpostgresql.com") == "sql.agenticpostgresql.com"
    assert naming.sql_relay_origin("sql.agenticpostgresql.com") == "wss://sql.agenticpostgresql.com"
    for bad in ("control.com", "localhost", "control..com"):
        with pytest.raises(naming.NamingError):
            naming.sql_relay_zone(bad)
    for bad in ("", "sql.example.com/x", "sql.example.com:443"):
        with pytest.raises(naming.NamingError):
            naming.sql_relay_origin(bad)


def test_the_upstream_follows_the_edges_constants(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The upstream is DERIVED, not typed: move the edge's alias and its
    Postgres entrypoint's port and the render moves with them. (A typed value
    equal to today's derived one is invisible to any reading of the output;
    this is the reading that can see it.)"""
    monkeypatch.setattr(host_config, "EDGE_PROXY_ALIAS", "apg-edge-elsewhere")
    monkeypatch.setattr(host_config, "EDGE_POSTGRES_PORT", 9432)
    moved = _values(_render(CONTROL))
    assert moved.get("APG_SQL_RELAY_UPSTREAM") == "apg-edge-elsewhere:9432"
