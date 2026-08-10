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
import shlex
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


# ---------------------------------------------------------------------------
# The Session 3 cluster is project-internal (DBX-PG-002, offline half)
# ---------------------------------------------------------------------------


def test_postgres_joins_only_the_internal_network() -> None:
    """The boundary is the network, not a bind address.

    `internal: true` on that network means no route off the host at all. This
    is the claim SEC-NET-001's external scan of 5432 measures from Session 3
    on -- until now it found the port closed because nothing was listening,
    which is a different fact wearing the same green tick.
    """
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    assert document["services"]["postgres"]["networks"] == ["internal"]
    assert document["networks"]["internal"]["internal"] is True


def test_postgres_carries_no_traefik_label_of_any_kind() -> None:
    """Not `traefik.enable`, not a router, not even the network hint.

    Checked over every key rather than against a list of known-dangerous ones:
    the edge-probe carries `traefik.docker.network` legitimately, so a test
    that only looked for `traefik.enable` would let a router label through.
    """
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    labels = document["services"]["postgres"].get("labels", {}) or {}
    offenders = [key for key in labels if "traefik" in str(key).lower()]
    assert not offenders, f"postgres carries Traefik labels: {offenders}"


def test_the_migration_service_is_also_project_internal() -> None:
    """dbmate reaches the cluster over the project network and nothing else."""
    document = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    dbmate = document["services"]["dbmate"]
    assert dbmate["networks"] == ["internal"]
    assert "ports" not in dbmate
    labels = dbmate.get("labels", {}) or {}
    assert not [key for key in labels if "traefik" in str(key).lower()]


def test_no_database_credential_appears_in_the_model_or_the_env() -> None:
    """The credential reaches dbmate by value only inside the container.

    The model does contain the *shape* of a connection URL, and from Run 7 it
    has to: the entrypoint assembles one from three interpolated identifiers and
    a password it reads out of a mounted file, because a stored URL would embed
    three derived names in an operator-entered value (ADR 0034).

    So the assertion is about the userinfo, not about the substring. Every
    `postgres://` in the model must be followed by variable references all the
    way to the `@`: a literal anywhere in there is a credential in the model,
    which is the thing being forbidden. `postgresql://` and `PGPASSWORD` stay
    banned outright -- nothing here has a use for either.

    Session 5 added the second URL and made the check understand Compose's own
    syntax. `${VAR:?required}` contains a colon, so splitting the userinfo on
    colons used to produce `?required}` and read it as a literal password. That
    is a parser fault, not a finding: the references are expanded away first,
    and what is asserted about the remainder is *stricter* than before -- every
    part must now be either a variable reference or empty, where it previously
    only had to start with `$`.
    """
    text = MODEL.read_text(encoding="utf-8")
    for marker in ("postgresql://", "PGPASSWORD"):
        assert marker not in text, f"compose.yaml contains {marker}"

    urls = re.findall(r"postgres://([^@\s]*)@", text)
    assert urls, "the model no longer assembles a connection URL; this test is measuring nothing"
    for userinfo in urls:
        # `${VAR}`, `${VAR:?required}` and the `$$VAR` a shell entrypoint sees.
        # Replaced by a marker rather than deleted, so that `${A}:${B}` still
        # shows two parts and an empty one cannot hide a dropped literal.
        expanded = re.sub(r"\$\{[^}]*\}|\$\$[A-Za-z_][A-Za-z0-9_]*", "$", userinfo)
        for part in expanded.split(":"):
            assert part == "$", (
                f"compose.yaml has a literal in a connection URL's userinfo: {part!r} "
                f"(from {userinfo!r})"
            )

    for directory in (ALPHA, ALPINE):
        env = (directory / "compose.env").read_text(encoding="utf-8")
        for marker in ("postgresql://", "postgres://", "PASSWORD", "PGPASSWORD"):
            assert marker not in env, f"{directory.name}/compose.env contains {marker}"


def test_the_postgres_memory_limit_exceeds_the_declared_budget() -> None:
    """The measured failure, asserted on the rendered pair rather than the rule.

    `config` refuses a manifest whose limit is at the budget. This checks the
    other end -- that what actually reaches Compose still satisfies it, so a
    future renderer that emitted the budget into POSTGRES_MEMORY_LIMIT would
    fail here rather than on a host, where it looks like a slow cluster.
    """
    for directory in (ALPHA, ALPINE):
        budget = outputs(directory)["database"]["budget"]
        assert budget["memory_limit_mb"] > budget["unreclaimable_mb"], directory.name
        assert budget["shm_size_mb"] >= budget["shared_buffers_mb"], directory.name


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
    "subcommand",
    ["up", "run", "start", "create", "restart", "exec", "attach", "cp", "watch", "scale"],
)
def test_container_starting_subcommands_are_refused(subcommand: str) -> None:
    """Still exit 10 by default. Session 2 added a way through, not a hole.

    The first eight parameters are unchanged from Session 1; what changed
    there is the message: refusal is now conditional on ``--runtime`` rather
    than on the session, so asserting the old "Session 1 starts nothing" text
    would be asserting a sentence rather than a behaviour (ADR 0013).
    ``watch`` and ``scale`` were added after an audit against the currently
    installed Compose found both start containers from a subcommand that was
    not refused (ADR 0022).
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


# ---------------------------------------------------------------------------
# ADR 0021 -- a flag's value must not be mistaken for the subcommand
# ---------------------------------------------------------------------------


def _first_subcommand(*args: str, tmp_path: Path) -> str:
    """Call the real ``first_subcommand`` out of bin/compose.sh.

    Sources every definition in the script except its trailing `main "$@"`
    call, so this exercises the actual parser rather than a description of
    it. ``COMPOSE_ARGS`` is set to ``args`` before calling the function.
    """
    text = COMPOSE_SH.read_text(encoding="utf-8")
    body = text[: text.rindex('main "$@"')]
    quoted = " ".join(shlex.quote(a) for a in args)
    harness = tmp_path / "first_subcommand.sh"
    harness.write_text(body + f"\nCOMPOSE_ARGS=({quoted})\nfirst_subcommand\n", encoding="utf-8")
    result = subprocess.run(["bash", str(harness)], capture_output=True, text=True, check=True)
    return result.stdout


def test_a_flag_with_a_value_cannot_smuggle_a_container_start() -> None:
    """A value-taking flag ahead of the subcommand must not defeat FORBIDDEN.

    Before ADR 0021, ``first_subcommand`` returned the flag's value
    (``session2``) instead of ``up``. ``session2`` is not in FORBIDDEN, so the
    refusal that is supposed to fire for every container-starting subcommand,
    unconditionally, by default, silently did not -- and the real
    ``docker compose ... up`` that followed still received the unexamined
    ``up`` in COMPOSE_ARGS.
    """
    result = compose(ALPHA, "--profile", "session2", "up")
    assert result.returncode == 10, result.stderr
    assert "requires --runtime with root" in result.stderr


@pytest.mark.parametrize("subcommand", ["up", "restart"])
def test_runtime_call_with_a_flag_value_still_reaches_the_privilege_gate(
    subcommand: str,
) -> None:
    """The exact shape ``bin/project-runtime.sh`` uses
    (``--runtime --profile session2 <subcommand>``), run unprivileged.

    This alone does not distinguish a correct resolution from the ADR 0021
    bug: the privilege check in ``main()`` runs before the allowlist check
    regardless of which subcommand was resolved, by design
    (``test_runtime_mode_requires_root``). What it proves is that the parser
    change does not disturb that ordering, or raise before reaching it.
    ``test_first_subcommand_skips_a_flags_value``, below, is the test that
    actually pins the resolution.
    """
    result = compose(ALPHA, "--runtime", "--profile", "session2", subcommand)
    assert result.returncode == 3, f"{subcommand} returned {result.returncode}: {result.stderr}"
    assert "requires root" in result.stderr


def test_first_subcommand_skips_a_flags_value(tmp_path: Path) -> None:
    """The direct regression test for ADR 0021.

    Calls the real ``first_subcommand``, not a reimplementation of it, and
    proves it returns the subcommand rather than the value of a flag written
    ahead of it -- for both call shapes this repository actually uses
    (``--profile session2 up``/``down`` in bin/project-runtime.sh, and
    ``--profile contract config`` in bin/deploy-project.py's
    ``_model_digest``) and for the ``--flag=value`` form, which needs no
    entry in ``SUBCOMMAND_VALUE_FLAGS`` because it consumes nothing further.
    """
    up_args = ("--profile", "session2", "up", "-d", "--wait")
    assert _first_subcommand(*up_args, tmp_path=tmp_path) == "up"
    assert _first_subcommand("--profile", "session2", "down", tmp_path=tmp_path) == "down"
    assert _first_subcommand("--profile", "contract", "config", tmp_path=tmp_path) == "config"
    assert _first_subcommand("--profile=contract", "config", tmp_path=tmp_path) == "config"


def test_the_runtime_allowlist_excludes_container_entry_verbs() -> None:
    """`exec`, `attach`, `cp`, `watch` and `scale` all reach inside a container.

    --runtime does not grant them even to root. `run` was among them until
    Session 3, when the migration plane needed a one-shot container and said so
    in an ADR, which is the process the old comment on this list asked for
    (ADR 0034). It is the only addition, and it arrives with two refusals that
    the rest of the allowlist does not need -- asserted below, because `run`
    without them is a way to execute anything as root inside a project's
    network with its secrets mounted.

    Asserted against the script's allowlist because proving it at runtime would
    need a root test process.
    """
    text = COMPOSE_SH.read_text(encoding="utf-8")
    allowed = re.search(r'RUNTIME_ALLOWED="([^"]*)"', text)
    assert allowed is not None
    permitted = set(allowed.group(1).split())
    assert permitted == {"up", "down", "restart", "build", "ps", "config", "logs", "run"}
    assert not permitted & {"exec", "attach", "cp", "start", "create", "watch", "scale"}

    refused = re.search(r'RUN_FORBIDDEN_FLAGS="([^"]*)"', text)
    assert refused is not None, "run is permitted with no flag refusals at all"
    flags = set(refused.group(1).split())
    assert {"--entrypoint", "-e", "--env", "--volume", "-v", "--user", "-u"} <= flags


@pytest.mark.parametrize(
    "flag",
    [("--entrypoint", "sh"), ("-e", "APG_X=1"), ("--env", "APG_X=1"), ("-v", "/etc:/etc")],
    ids=["entrypoint", "short-env", "long-env", "volume"],
)
def test_run_refuses_the_flags_that_would_replace_the_reviewed_model(flag: tuple[str, ...]) -> None:
    """Declared and enforced are different things.

    The list above says which flags are refused; this runs the command. Both,
    because a list is only a comment until something reads it, and this one
    guards the difference between "start the service the model declares" and
    "start anything, as root, on that network".

    Unprivileged on purpose: the refusal is checked before the --runtime gate,
    so it does not depend on who asked.
    """
    result = compose(ALPHA, "--profile", "migration", "run", *flag, "dbmate")
    assert result.returncode == 10, result.stderr
    assert flag[0] in result.stderr


def test_run_with_an_equals_form_flag_is_refused_too() -> None:
    """`--entrypoint=sh` is the same request as `--entrypoint sh`."""
    result = compose(ALPHA, "--profile", "migration", "run", "--entrypoint=sh", "dbmate")
    assert result.returncode == 10, result.stderr


def test_the_forbidden_list_is_pinned_to_the_audited_compose_surface() -> None:
    """The default refusal covers every container-starting Compose subcommand
    an audit has actually checked for -- not just Session 1's original eight.

    Formerly ``test_the_forbidden_list_is_unchanged_from_session_one``: that
    name and its "only the escape is new" docstring stopped being true once
    ``watch`` and ``scale`` were added. Both create or start containers and
    were reachable with no ``--runtime`` and no root before this (ADR 0022) --
    the list had drifted behind the Compose surface it was meant to cover,
    which is a way this test's old formulation (diffing the file against its
    own past self) could never have caught. This asserts the audited list is
    what ships; it does not claim the audit is complete against any future
    Compose release.
    """
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
        "watch",
        "scale",
    ]


def _compose_definitions_at_real_root() -> str:
    """`bin/compose.sh`'s real definitions, minus the trailing `main "$@"`
    call, with ROOT_DIR pointed at the real repository.

    Same shape as the helper of the same name in
    ``tests/contract/test_project_state_roots.py``, used there for the same
    reason: the harness runs from a tmp_path, so ROOT_DIR must not resolve
    against that instead.
    """
    text = COMPOSE_SH.read_text(encoding="utf-8")
    body = text[: text.rindex('main "$@"')]
    patched = body.replace(
        'ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"',
        f"ROOT_DIR={shlex.quote(str(REPO_ROOT))}",
    )
    assert patched != body, "could not redirect ROOT_DIR for the test"
    return patched


def _extract_runtime_allowed_check(compose_source: str) -> str:
    """The literal RUNTIME_ALLOWED conditional out of `main()`, unmodified.

    Run directly instead of through `main()`, for the same reason
    ``tests/contract/test_project_state_roots.py`` runs OVERRIDE_REQUIRED's
    conditional directly rather than calling `main()`: the privilege check
    (``--runtime requires root``, exit 3) runs first, unconditionally, before
    RUNTIME_ALLOWED is ever consulted. As a non-root test process, a real
    ``bin/compose.sh --runtime watch`` or ``--runtime scale`` call can only
    ever exit 3 with "requires root" -- never exit 10 with the allowlist
    message -- regardless of whether RUNTIME_ALLOWED excludes them. A test
    against the real subprocess could not even be made to pass while
    asserting the allowlist's own exit code, let alone distinguish a correct
    exclusion from a regression.

    Slicing the real conditional out of the current file -- not retyping its
    condition or its die() message -- keeps this tied to the actual code: if
    the condition or the message changes, the slice changes with it; if the
    anchor below stops matching, ``.index`` raises instead of silently
    testing stale text.
    """
    start_marker = 'if ! in_list "${subcommand}" "${RUNTIME_ALLOWED}"; then'
    start = compose_source.index(start_marker)
    end_marker = "\n    fi\n"
    end = compose_source.index(end_marker, start) + len(end_marker)
    return compose_source[start:end]


def _runtime_allowed_result(tmp_path: Path, subcommand: str) -> subprocess.CompletedProcess[str]:
    """Resolve `subcommand` for a project-scope `--runtime <subcommand>` call
    exactly as `main()` would -- via the real `parse_arguments` and
    `configure_project_scope` -- then run the real RUNTIME_ALLOWED
    conditional against what it resolved to.
    """
    runtime_check = _extract_runtime_allowed_check(COMPOSE_SH.read_text(encoding="utf-8"))
    harness = _compose_definitions_at_real_root() + (
        f"\nparse_arguments {shlex.quote(str(ALPHA))} --runtime {shlex.quote(subcommand)}"
        '\nENV_FILE_ARGS=(--env-file "${LOCK_ENV}")'
        '\nPROJECT_KEY=""'
        "\nconfigure_project_scope"
        '\nsubcommand="$(first_subcommand)"'
        f"\n{runtime_check}\n"
    )
    harness_path = tmp_path / "harness.sh"
    harness_path.write_text(harness, encoding="utf-8")
    return subprocess.run(["bash", str(harness_path)], capture_output=True, text=True, check=False)


@pytest.mark.parametrize("subcommand", ["watch", "scale"])
def test_watch_and_scale_are_refused_with_runtime_even_as_root(
    subcommand: str, tmp_path: Path
) -> None:
    """`--runtime` does not grant `watch` or `scale` even to root -- neither
    is in RUNTIME_ALLOWED (ADR 0022), so both hit the same allowlist refusal
    `exec`, `attach`, `run` and `cp` already get.

    Asserted on the message rather than the exit code alone: exit 10 here is
    the allowlist's own die(), distinct from the privilege gate's exit 3 --
    but see `_extract_runtime_allowed_check` for why this cannot be proven
    by calling `bin/compose.sh` itself as a non-root test process.
    """
    result = _runtime_allowed_result(tmp_path, subcommand)
    assert result.returncode == 10, result.stderr
    assert "not permitted in --runtime mode" in result.stderr
    assert f"'{subcommand}'" in result.stderr


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
