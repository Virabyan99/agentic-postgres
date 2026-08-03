"""Validation-only Compose model and its controlled wrapper (runbook §7).

The central test here is ``test_inherited_variable_cannot_override_*``. Compose
gives shell environment variables *higher* interpolation precedence than
``--env-file`` values, so without the wrapper a stray ``COMPOSE_PROJECT_NAME``
would silently point a command at the wrong project and the model would still
render successfully.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

COMPOSE_SH = REPO_ROOT / "bin" / "compose.sh"
MODEL = REPO_ROOT / "compose.yaml"
ALPHA = REPO_ROOT / ".generated" / "fixture-alpha-dev"
ALPINE = REPO_ROOT / ".generated" / "fixture-alpine-dev"

pytestmark.append(
    pytest.mark.skipif(not ALPHA.is_dir(), reason="render the fixtures first: ./deploy.sh")
)


def compose(project_dir: Path, *args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        [str(COMPOSE_SH), str(project_dir), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **(env or {})},
    )


def rendered(project_dir: Path) -> dict[str, Any]:
    result = compose(project_dir, "--profile", "contract", "config")
    assert result.returncode == 0, result.stderr
    return yaml.safe_load(result.stdout)


def outputs(project_dir: Path) -> dict[str, Any]:
    return json.loads((project_dir / "outputs.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The model source
# ---------------------------------------------------------------------------


def test_every_interpolation_is_required() -> None:
    """`${VAR:?required}` fails loudly; a bare `${VAR}` renders empty.

    An empty resource name would collapse two projects onto one network.
    """
    text = MODEL.read_text(encoding="utf-8")
    for reference in re.findall(r"\$\{[^}]+\}", text):
        assert reference.endswith(":?required}"), f"{reference} is not a required interpolation"


def test_model_hardcodes_no_identity() -> None:
    text = MODEL.read_text(encoding="utf-8")
    for forbidden in ("fixture-alpha", "fixture-alpine", "apg-fixture"):
        assert forbidden not in text, f"compose.yaml hard-codes {forbidden}"


def test_model_does_not_use_container_name() -> None:
    """`container_name` is not project-scoped and would collide across projects.

    Checked structurally rather than by grepping the file: the model's own
    comment explains why the key is forbidden, and a text search would match
    that explanation.
    """
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    for name, service in document["services"].items():
        assert "container_name" not in service, f"service {name} sets container_name"


def test_model_references_only_locked_image_variables() -> None:
    """No image may bypass the lock by naming a repository inline."""
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    for name, service in document["services"].items():
        image = service["image"]
        assert image.startswith("${") and image.endswith(":?required}"), (
            f"service {name} does not take its image from a locked variable: {image}"
        )


def test_probe_is_profile_gated() -> None:
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    assert document["services"]["contract-probe"]["profiles"] == ["contract"]
    assert document["services"]["contract-probe"]["restart"] == "no"


def test_internal_network_is_internal() -> None:
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    assert document["networks"]["internal"]["internal"] is True


# ---------------------------------------------------------------------------
# Rendered names match outputs.json exactly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("project_dir", [ALPHA, ALPINE], ids=lambda p: p.name)
def test_model_renders(project_dir: Path) -> None:
    assert rendered(project_dir)["name"]


@pytest.mark.parametrize("project_dir", [ALPHA, ALPINE], ids=lambda p: p.name)
def test_rendered_resource_names_match_outputs(project_dir: Path) -> None:
    """Runbook §12: the names Docker would create must equal the ones we published."""
    model = rendered(project_dir)
    declared = outputs(project_dir)["compose"]

    assert model["name"] == declared["project_name"]
    assert model["networks"]["edge"]["name"] == declared["networks"]["edge"]
    assert model["networks"]["internal"]["name"] == declared["networks"]["internal"]
    assert model["volumes"]["postgres-data"]["name"] == declared["volumes"]["postgres"]


def test_rendered_image_carries_the_locked_digest() -> None:
    image = rendered(ALPHA)["services"]["contract-probe"]["image"]
    assert "@sha256:" in image
    locked = next(
        line.split("=", 1)[1]
        for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines()
        if line.startswith("PYTHON_RUNTIME_IMAGE=")
    )
    assert image == locked


def test_two_projects_render_disjoint_resource_names() -> None:
    alpha, alpine = rendered(ALPHA), rendered(ALPINE)
    assert alpha["name"] != alpine["name"]
    assert alpha["networks"]["edge"]["name"] != alpine["networks"]["edge"]["name"]
    assert alpha["networks"]["internal"]["name"] != alpine["networks"]["internal"]["name"]
    assert alpha["volumes"]["postgres-data"]["name"] != alpine["volumes"]["postgres-data"]["name"]


# ---------------------------------------------------------------------------
# The override defence (runbook §7.2, §9 check 14)
# ---------------------------------------------------------------------------


def test_inherited_project_name_cannot_override_the_generated_one() -> None:
    result = compose(
        ALPHA, "--profile", "contract", "config", env={"COMPOSE_PROJECT_NAME": "hijacked"}
    )
    assert result.returncode == 0, result.stderr
    assert "hijacked" not in result.stdout
    assert yaml.safe_load(result.stdout)["name"] == outputs(ALPHA)["compose"]["project_name"]


def test_inherited_image_cannot_override_the_locked_digest() -> None:
    result = compose(
        ALPHA,
        "--profile",
        "contract",
        "config",
        env={"PYTHON_RUNTIME_IMAGE": "docker.io/library/evil:latest"},
    )
    assert result.returncode == 0, result.stderr
    assert "evil:latest" not in result.stdout
    assert "@sha256:" in yaml.safe_load(result.stdout)["services"]["contract-probe"]["image"]


def test_inherited_network_name_cannot_override() -> None:
    result = compose(
        ALPHA, "--profile", "contract", "config", env={"EDGE_NETWORK_NAME": "hijacked-edge"}
    )
    assert result.returncode == 0, result.stderr
    assert "hijacked-edge" not in result.stdout


def test_wrapper_uses_an_allowlist_not_a_denylist() -> None:
    """`env -u` cannot be proven complete; `env -i` plus a list can.

    Comments are stripped first: the wrapper documents why it rejects the
    denylist approach, and that explanation names the thing being rejected.
    """
    code = "\n".join(
        line
        for line in COMPOSE_SH.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("#")
    )
    assert "env -i" in code
    assert "env -u" not in code


def test_wrapper_never_shell_sources_an_env_file() -> None:
    text = COMPOSE_SH.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert not re.match(r"^(\.|source)\s+.*env", stripped), f"sources an env file: {line}"


# ---------------------------------------------------------------------------
# Session 1 starts nothing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subcommand", ["up", "run", "start", "create", "restart", "exec", "attach", "cp"]
)
def test_container_starting_subcommands_are_refused(subcommand: str) -> None:
    result = compose(ALPHA, subcommand)
    assert result.returncode == 10, f"{subcommand} returned {result.returncode}"
    assert "Session 1 starts nothing" in result.stderr


@pytest.mark.parametrize("project_dir", [ALPHA, ALPINE], ids=lambda p: p.name)
def test_no_container_is_running(project_dir: Path) -> None:
    result = compose(project_dir, "ps", "--quiet")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", f"containers exist: {result.stdout}"


def test_config_does_not_require_the_daemon() -> None:
    """`config` is rendered client-side; only daemon subcommands probe it."""
    text = COMPOSE_SH.read_text(encoding="utf-8")
    needs_daemon = re.search(r'NEEDS_DAEMON="([^"]*)"', text)
    assert needs_daemon is not None
    assert "config" not in needs_daemon.group(1).split()


# ---------------------------------------------------------------------------
# Wrapper input handling
# ---------------------------------------------------------------------------


def test_env_files_are_disjoint() -> None:
    def keys(path: Path) -> set[str]:
        return {
            line.split("=", 1)[0]
            for line in path.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and "=" in line
        }

    overlap = keys(REPO_ROOT / "versions.env") & keys(ALPHA / "compose.env")
    assert not overlap, f"overlapping variables: {sorted(overlap)}"


def test_missing_project_directory_is_rejected(tmp_path: Path) -> None:
    result = compose(tmp_path / "absent")
    assert result.returncode == 2


def test_directory_without_compose_env_is_rejected(tmp_path: Path) -> None:
    result = compose(tmp_path)
    assert result.returncode == 2
    assert "compose.env" in result.stderr


def test_help_is_available() -> None:
    result = subprocess.run(
        [str(COMPOSE_SH), "--help"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert "generated-project-dir" in result.stdout
