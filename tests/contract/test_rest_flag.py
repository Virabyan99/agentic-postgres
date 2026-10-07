"""`api.rest.enabled` has a reader (Session 38, D2137, D2144, D2172; ADR 0251 item 6).

Until 1.16.0 the flag's only reader was a validator: `build_override` emitted
PostgREST's router whatever the manifest said, and control-prod -- whose manifest
sets `api.rest.enabled: false` -- served `/api/rest/` through the edge. The flag
now reaches the two places that act on it, from ONE value in the rendered
`compose.env` (`API_REST_ENABLED`): the runtime override's labels and the
deploy's observation of the served document. The deployed document refuses a
`ready` REST route beside the flag off.

What these proofs do NOT reach: that Traefik really answers 404 for the withheld
router. That is measured on control-prod's 1.16.0 deploy (Sheet R2c).
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, deployed_output, rendering, runtime_override
from agentic_postgres.config import ManifestError

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

DEPLOY = REPO_ROOT / "bin" / "deploy-project.py"
CAPABILITIES = REPO_ROOT / "capabilities.example.yaml"


@pytest.fixture
def deploy() -> Any:
    """`bin/deploy-project.py` imported by path -- `bin/` is not a package."""
    spec = importlib.util.spec_from_file_location("_apg_deploy_rest_flag_under_test", DEPLOY)
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


def _override_from_render(deploy: Any, manifest: Path) -> tuple[bool, dict[str, Any]]:
    """Render a real manifest, then build the override the way the deploy does:
    every name AND the flag read from the rendered compose.env by the deploy's
    own readers."""
    directory = rendering.render_project(manifest, CAPABILITIES, validate_compose=False)
    compose_env = directory / "compose.env"
    enabled = deploy._rest_enabled(compose_env)
    document = runtime_override.build_override(
        **deploy._override_names(compose_env),
        **deploy._override_control(compose_env),
        rest_enabled=enabled,
        https_entrypoint="websecure",
        rendered_directory="/var/lib/agentic-postgres/rendered/x",
    )
    return enabled, document


def _rest_routers(document: dict[str, Any]) -> list[str]:
    labels = document["services"][runtime_override.REST_SERVICE].get("labels", {})
    return [key for key in labels if key.startswith("traefik.")]


def test_a_disabled_rest_service_has_no_router(deploy: Any, sandbox: Path) -> None:
    """The control example (`api.rest.enabled: false`) renders `API_REST_ENABLED=false`
    and its override gives PostgREST no `traefik.*` label; the container keeps its
    JWKS mount (ADR 0062: the service is unconditional, only the route moves).

    Control, in the same test: the alpha example (`api.rest.enabled: true`) renders
    `true` and its override carries the router.
    """
    disabled, off = _override_from_render(deploy, REPO_ROOT / "project.control.example.yaml")
    assert disabled is False
    assert _rest_routers(off) == [], "a project that does not publish REST got a router"
    assert off["services"][runtime_override.REST_SERVICE]["volumes"], (
        "the PostgREST container lost its JWKS mount -- only the route may move"
    )

    enabled, on = _override_from_render(deploy, REPO_ROOT / "project.example.yaml")
    assert enabled is True
    routers = _rest_routers(on)
    assert "traefik.enable" in routers
    assert any(key.endswith(".rule") for key in routers), routers


def test_the_deploy_records_rest_unpublished_without_reading_it(
    deploy: Any, tmp_path: Path
) -> None:
    """With the flag off the deploy does not call `observe_served_document` at all,
    so no 90-second observation window is spent on a route nothing answers, and
    `rest_status` / `api` stay `unavailable` / `API_NOT_PUBLISHED`.

    Structural, because `main()` is a whole deploy: the call is parsed and must sit
    in the `else` of an `if not rest_enabled:` -- and `observe_api` with it, since
    without a served document there is nothing for it to read. The reader itself is
    exercised directly, including its refusal of a value it does not understand.
    """
    tree = ast.parse(DEPLOY.read_text(encoding="utf-8"))
    guarded: dict[str, bool] = {"observe_served_document": False, "observe_api": False}

    def calls_in(nodes: list[ast.stmt]) -> set[str]:
        found = set()
        for node in nodes:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
                    found.add(inner.func.id)
        return found

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.UnaryOp)
            and isinstance(node.test.op, ast.Not)
            and isinstance(node.test.operand, ast.Name)
            and node.test.operand.id == "rest_enabled"
        ):
            in_else = calls_in(node.orelse)
            in_body = calls_in(node.body)
            for name in guarded:
                if name in in_else and name not in in_body:
                    guarded[name] = True
    assert guarded == {"observe_served_document": True, "observe_api": True}, guarded

    unguarded = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "observe_served_document"
    ]
    # One call site, and it is the guarded one (a lambda inside the else).
    assert len(unguarded) == 1, f"observe_served_document is called {len(unguarded)} times"

    env = tmp_path / "compose.env"
    env.write_text("API_REST_ENABLED=false\n", encoding="utf-8")
    assert deploy._rest_enabled(env) is False
    env.write_text("API_REST_ENABLED=true\n", encoding="utf-8")
    assert deploy._rest_enabled(env) is True
    env.write_text("API_REST_ENABLED=yes\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        deploy._rest_enabled(env)


def test_a_ready_rest_route_with_the_flag_off_is_refused() -> None:
    """The document cannot record a REST route answering for a project whose
    manifest withholds it. Control: the same `ready` with the flag on builds."""
    path = REPO_ROOT / ".generated" / "fixture-alpha-dev" / "outputs.json"
    if not path.exists():
        pytest.skip("fixtures are not rendered in this working tree")
    rendered = json.loads(path.read_text(encoding="utf-8"))

    from tests.contract.test_deployed_output import build

    with pytest.raises(ManifestError, match=r"api\.rest\.enabled: false"):
        build(rendered, rest_status="ready", rest_enabled=False)

    document = build(rendered, rest_status="ready", rest_enabled=True)
    assert document["routes"]["rest"]["status"] == "ready"
    assert build(rendered, rest_status="unavailable", rest_enabled=False)["api"] == (
        deployed_output.API_NOT_PUBLISHED
    )
