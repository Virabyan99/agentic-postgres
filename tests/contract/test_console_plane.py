"""The console's plane: started on the control project only, routed by three paths, holding nothing.

Session 43 (ADR 0280): `CON-PLANE-001`. Two real manifests are rendered --
the control example and `project.example.yaml` -- and everything after reads
the rendered `compose.env` the way production does: `project-runtime.sh`'s own
`session_profiles` for the profile, and the deploy's own `_override_console`
and `_override_names` for the router. So the profile that starts the console
and the router that publishes it are proved to read one value.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, rendering, runtime_override

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

DEPLOY = REPO_ROOT / "bin" / "deploy-project.py"
RUNTIME = REPO_ROOT / "bin" / "project-runtime.sh"
CAPABILITIES = REPO_ROOT / "capabilities.example.yaml"
CONTROL = REPO_ROOT / "project.control.example.yaml"
PLAIN = REPO_ROOT / "project.example.yaml"

RULE = (
    "Host(`${PROJECT_DOMAIN:?required}`) && "
    "(Path(`/`) || Path(`/accept`) || PathPrefix(`/console/`))"
)


@pytest.fixture
def deploy() -> Any:
    spec = importlib.util.spec_from_file_location("_apg_deploy_console_under_test", DEPLOY)
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


def _profiles(rendered: Path, tmp_path: Path) -> list[str]:
    """`project-runtime.sh`'s own `session_profiles`, from a copy with `main` removed."""
    text = RUNTIME.read_text(encoding="utf-8")
    # The copy sources `bin/lib/` beside the real script, so its root is the repository's.
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
        rest_enabled=deploy._rest_enabled(compose_env),
        https_entrypoint="websecure",
        rendered_directory="/var/lib/agentic-postgres/rendered/x",
    )


def test_the_profile_is_added_only_for_the_control_project(sandbox: Path, tmp_path: Path) -> None:
    on = _profiles(_render(CONTROL), tmp_path)
    off = _profiles(_render(PLAIN), tmp_path)
    assert on.count("console") == 1 and on[on.index("console") - 1] == "--profile", on
    assert "console" not in off, off
    # The control: both still start their cumulative session profiles.
    assert "session43" in on and "session43" in off


def test_the_router_rule_is_the_three_paths(deploy: Any, sandbox: Path) -> None:
    on = _override(deploy, _render(CONTROL))
    off = _override(deploy, _render(PLAIN))
    assert runtime_override.CONSOLE_SERVICE not in off["services"]
    labels = on["services"][runtime_override.CONSOLE_SERVICE]["labels"]
    routers = {key.split(".")[3] for key in labels if key.startswith("traefik.http.routers.")}
    assert len(routers) == 1, routers
    router = routers.pop()
    assert router.endswith("-console")
    prefix = f"traefik.http.routers.{router}"
    assert labels[f"{prefix}.rule"] == RULE
    assert labels[f"{prefix}.middlewares"] == "${BASELINE_MIDDLEWARE_CHAIN:?required}"
    assert labels[f"{prefix}.entrypoints"] == "websecure"
    assert labels[f"traefik.http.services.{router}.loadbalancer.server.port"] == "8080"
    assert not [key for key in labels if ".middlewares." in key and "stripprefix" in key]


def test_the_console_holds_no_secret_and_no_mount(deploy: Any, sandbox: Path) -> None:
    model = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    console = model["services"]["console"]
    assert console["profiles"] == ["console"]
    assert set(console["environment"]) == {"APG_CONSOLE_PORT", "APG_CONSOLE_API_PATH"}
    # `.get`: an `APG_` subscript in a test body reads as an environment gate (D2381).
    api_path = console["environment"].get("APG_CONSOLE_API_PATH")
    assert api_path == "${CONTROL_ROUTE_PATH:?required}"
    for key in ("volumes", "secrets", "env_file", "ports", "depends_on"):
        assert key not in console, key
    assert console["networks"] == ["edge"]
    override = _override(deploy, _render(CONTROL))["services"][runtime_override.CONSOLE_SERVICE]
    assert set(override) == {"labels"}, "the override gives the console something besides a router"
