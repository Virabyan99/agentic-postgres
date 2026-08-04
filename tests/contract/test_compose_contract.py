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
    """No image may bypass the lock by naming a repository inline.

    Session 2 added services that *build* rather than pull. A `FROM` line in a
    Dockerfile is a second, unlocked version declaration that
    `bin/lock-versions.sh` cannot see, so a built service must take its base
    image from the lock through a build argument instead — and this asserts one
    of the two forms is present, never neither.
    """
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    for name, service in document["services"].items():
        if "image" in service:
            image = service["image"]
            assert image.startswith("${") and image.endswith(":?required}"), (
                f"service {name} does not take its image from a locked variable: {image}"
            )
            continue

        base = service["build"]["args"]["BASE_IMAGE"]
        assert base.startswith("${") and base.endswith(":?required}"), (
            f"service {name} builds from an unlocked base image: {base}"
        )


def test_no_dockerfile_names_its_own_base_image() -> None:
    """The other half of the same rule, checked where it could be broken.

    A `FROM python:3.12-slim` would build successfully, pass every Compose
    assertion, and quietly reintroduce a floating tag into a public-facing
    image.
    """
    for dockerfile in sorted((REPO_ROOT / "services").rglob("Dockerfile")):
        froms = [
            line.strip()
            for line in dockerfile.read_text(encoding="utf-8").splitlines()
            if line.strip().upper().startswith("FROM ")
        ]
        assert froms, f"{dockerfile} has no FROM line"
        for line in froms:
            assert line == "FROM ${BASE_IMAGE}", (
                f"{dockerfile.relative_to(REPO_ROOT)} names its own base image: {line}"
            )


def test_no_project_service_publishes_a_host_port() -> None:
    """Only Traefik publishes a host port (runbook §9, SEC-NET-001).

    Asserted against the model source as well as the resolved model, because a
    `ports` entry added here would be reviewed once and then enforced only by a
    live test that needs a host.
    """
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    for name, service in document["services"].items():
        assert "ports" not in service, f"service {name} publishes a host port"


def test_built_services_run_as_a_fixed_non_root_user() -> None:
    """A root container makes `cap_drop: ALL` and `no-new-privileges` cosmetic."""
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    for name, service in document["services"].items():
        if "build" not in service:
            continue
        assert service["user"] == "65532:65532", f"service {name} does not run as nonroot"
        assert service["read_only"] is True, f"service {name} has a writable root filesystem"
        assert service["cap_drop"] == ["ALL"], f"service {name} retains capabilities"
        assert "no-new-privileges:true" in service["security_opt"], name


def test_the_edge_probe_is_inert_without_the_runtime_override() -> None:
    """`traefik.enable` is absent from the committed model, deliberately.

    The router labels are rendered into the root-owned runtime override, so this
    file on its own cannot expose anything. Exposure is an act of deployment
    rather than a property of a file in the repository (ADR 0013).
    """
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    labels = document["services"]["edge-probe"]["labels"]
    assert "traefik.enable" not in labels
    assert labels["apg.traefik.scope"] == "managed"
    assert not any(key.startswith("traefik.http.") for key in labels)


def test_the_unlabeled_probe_carries_no_discovery_label() -> None:
    """The control for DEP-EDGE-002 only controls if it is genuinely unlabeled."""
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    service = document["services"]["unlabeled-probe"]
    assert "labels" not in service, "the unlabeled probe has labels; it proves nothing"


def test_the_secret_check_service_declares_no_secret_source() -> None:
    """The generation path does not exist until materialization runs.

    A `file:` source in the committed model would either be a guess or a stable
    path -- and a stable path is exactly the shared, mutable location that
    immutable generations exist to avoid (ADR 0010).
    """
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    assert "secrets" not in document, "the committed model declares a secret source"
    assert "secrets" not in document["services"]["secret-check"]


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
    """Still exit 10 by default. Session 2 added a way through, not a hole.

    All eight parameters are unchanged from Session 1. What changed is the
    message: refusal is now conditional on ``--runtime`` rather than on the
    session, so asserting the old "Session 1 starts nothing" text would be
    asserting a sentence rather than a behaviour (ADR 0013).
    """
    result = compose(ALPHA, subcommand)
    assert result.returncode == 10, f"{subcommand} returned {result.returncode}"
    assert "requires --runtime with root" in result.stderr


@pytest.mark.parametrize("subcommand", ["up", "restart", "exec"])
def test_runtime_mode_requires_root(subcommand: str) -> None:
    """Docker access is root-equivalent, so --runtime is not a flag you just add.

    The privilege check runs before the allowlist check deliberately: what an
    unprivileged caller may do is the same question regardless of which
    subcommand they asked for.
    """
    result = compose(ALPHA, "--runtime", subcommand)
    assert result.returncode == 3, f"{subcommand} returned {result.returncode}"
    assert "requires root" in result.stderr


def test_the_runtime_allowlist_excludes_container_entry_verbs() -> None:
    """`exec`, `attach`, `run` and `cp` reach inside a running container.

    Nothing in Session 2's documented path needs them, so --runtime does not
    grant them even to root. Asserted against the script's allowlist because
    proving it at runtime would need a root test process.
    """
    text = COMPOSE_SH.read_text(encoding="utf-8")
    allowed = re.search(r'RUNTIME_ALLOWED="([^"]*)"', text)
    assert allowed is not None
    permitted = set(allowed.group(1).split())
    assert permitted == {"up", "down", "restart", "build", "ps", "config", "logs"}
    assert not permitted & {"exec", "attach", "run", "cp", "start", "create"}


def test_the_forbidden_list_is_unchanged_from_session_one() -> None:
    """The default refusal is the inherited contract; only the escape is new."""
    text = COMPOSE_SH.read_text(encoding="utf-8")
    forbidden = re.search(r'FORBIDDEN="([^"]*)"', text)
    assert forbidden is not None
    assert forbidden.group(1).split() == [
        "up",
        "run",
        "start",
        "create",
        "restart",
        "exec",
        "attach",
        "cp",
    ]


# ---------------------------------------------------------------------------
# The shared edge plane
# ---------------------------------------------------------------------------


def edge(*args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        [str(COMPOSE_SH), "--edge", "--host", str(REPO_ROOT / "host.example.yaml"), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **(env or {})},
    )


def test_edge_model_renders_from_the_host_manifest() -> None:
    """`--edge config` must work offline: CI has no root-owned edge state."""
    result = edge("config")
    assert result.returncode == 0, result.stderr
    document = yaml.safe_load(result.stdout)
    assert document["name"] == "apg-edge"
    assert set(document["services"]) == {"traefik", "docker-socket-proxy"}


def test_edge_scope_requires_a_host_manifest() -> None:
    result = subprocess.run(
        [str(COMPOSE_SH), "--edge", "config"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 2
    assert "--host" in result.stderr


def test_edge_mode_refuses_volume_removal() -> None:
    """A deleted production ACME file turns a failed renewal into a rate limit.

    The state is a bind mount, so `down -v` cannot actually reach it. Refusing
    the flag removes the question rather than relying on that remaining true.
    """
    for flag in ("-v", "--volumes"):
        result = edge("down", flag)
        assert result.returncode == 2, flag
        assert "ACME state" in result.stderr


def test_inherited_edge_stack_name_cannot_override() -> None:
    result = edge("config", env={"EDGE_STACK_NAME": "hijacked"})
    assert result.returncode == 0, result.stderr
    assert "hijacked" not in result.stdout


def test_only_traefik_publishes_host_ports() -> None:
    """Runbook §9 and SEC-NET-001, asserted against the resolved edge model."""
    document = yaml.safe_load(edge("config").stdout)
    assert "ports" not in document["services"]["docker-socket-proxy"]
    published = {p["published"] for p in document["services"]["traefik"]["ports"]}
    assert published == {"80", "443"}


def test_traefik_has_no_direct_docker_socket_mount() -> None:
    """DEP-EDGE-003. The whole reason the socket proxy exists."""
    document = yaml.safe_load(edge("config").stdout)
    for mount in document["services"]["traefik"].get("volumes", []):
        assert "docker.sock" not in mount["source"], "Traefik mounts the Docker socket directly"


def test_the_socket_proxy_denies_every_unneeded_api_section() -> None:
    """`POST: 0` is the important one: it is what keeps read access read-only."""
    document = yaml.safe_load(edge("config").stdout)
    environment = document["services"]["docker-socket-proxy"]["environment"]

    assert {k for k, v in environment.items() if v == "1"} == {
        "CONTAINERS",
        "EVENTS",
        "NETWORKS",
        "PING",
        "VERSION",
    }
    for denied in ("POST", "EXEC", "BUILD", "IMAGES", "VOLUMES", "SECRETS", "SWARM", "INFO"):
        assert environment[denied] == "0", f"{denied} is not explicitly disabled"


def test_the_socket_proxy_is_not_privileged_and_is_unpublished() -> None:
    document = yaml.safe_load(edge("config").stdout)
    proxy = document["services"]["docker-socket-proxy"]
    assert proxy.get("privileged") is not True
    assert "ports" not in proxy
    assert proxy["cap_drop"] == ["ALL"]
    assert proxy["read_only"] is True
    assert proxy["networks"] == {"control": None}


def test_the_control_network_is_internal() -> None:
    """The proxy is unreachable from any project network because of this."""
    document = yaml.safe_load(edge("config").stdout)
    assert document["networks"]["control"]["internal"] is True


def test_the_edge_declares_no_named_volume() -> None:
    """ACME state is a bind mount so `docker volume prune` cannot reach it."""
    document = yaml.safe_load(edge("config").stdout)
    assert "volumes" not in document or not document["volumes"]


#: What ``bin/compose.sh`` prints when a daemon subcommand cannot reach Docker.
#: Matched on the message rather than the exit code, because exit 3 covers
#: several unrelated prerequisites and only this one is a question the calling
#: account is not permitted to ask.
DAEMON_UNREACHABLE = "the Docker daemon is unreachable"


@pytest.mark.parametrize("project_dir", [ALPHA, ALPINE], ids=lambda p: p.name)
def test_no_container_is_running(project_dir: Path) -> None:
    """ADR 0018: failing to reach the daemon is not the same answer as "none".

    The operator account on the deployment host is deliberately not in the
    ``docker`` group — membership is root-equivalent — so on that host this
    question cannot be asked at all. Reporting the refusal as a failure makes it
    indistinguishable from a fixture container actually running.

    The claim is not dropped there. ``bin/session-02-check.sh --mode host`` runs
    as root and enumerates every running container directly.
    """
    result = compose(project_dir, "ps", "--quiet")

    if result.returncode != 0 and DAEMON_UNREACHABLE in result.stderr:
        pytest.skip(
            "the Docker daemon is unreachable from this account, so whether a fixture "
            "container is running cannot be determined here; proved on the host by "
            "session-02-check.sh --mode host, which runs as root (ADR 0018)"
        )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", f"containers exist: {result.stdout}"


def test_a_running_container_would_still_fail() -> None:
    """Guard the guard: the skip must not grow into "skip if compose fails".

    Asserted against the test's own source, because producing a genuinely
    running container inside the contract suite is the one thing this suite
    exists to forbid.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    body = source.split("def test_no_container_is_running", 1)[1].split("\ndef ", 1)[0]

    assert "DAEMON_UNREACHABLE in result.stderr" in body, (
        "the skip is not conditioned on the daemon being unreachable"
    )
    assert 'assert result.stdout.strip() == ""' in body, (
        "the running-container assertion was removed rather than gated"
    )
    # Requiring a non-zero exit too: without it, a compose that succeeded and
    # printed container ids while mentioning the daemon would be skipped.
    assert "result.returncode != 0 and" in body


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
