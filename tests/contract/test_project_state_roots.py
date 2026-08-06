"""The two roots a project's files live in, and the fact that they differ.

`bin/project-runtime.sh` passed one directory to `bin/compose.sh` as the Compose
project directory *and* let `bin/compose.sh` derive its runtime env file from the
same key. Both resolved to `<dir>/compose.env`, so `assert_disjoint` compared a
file with itself, every key overlapped, and the runtime path could only exit 5.

The test that matters here is the last one: the two roots must not share a
prefix. Everything else is a detail of where each file lives.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT, deployed_output

pytestmark = [pytest.mark.contract, pytest.mark.p0]

FIXTURE_COMPOSE_ENV = REPO_ROOT / ".generated" / "fixture-alpha-dev" / "compose.env"
requires_rendered_fixture = pytest.mark.skipif(
    not FIXTURE_COMPOSE_ENV.is_file(), reason="render the fixtures first: ./deploy.sh"
)


def _sourced_definitions(script: Path) -> str:
    """Everything in a `bin/*.sh` script except its trailing `main "$@"` call.

    Every launcher in this repository ends with an unconditional `main "$@"`,
    so sourcing the file outright would execute it. Slicing that one call off
    leaves every real function and constant defined and callable, which is
    what lets a test exercise the actual parser/reader instead of a
    restatement of it in source-text regex.
    """
    text = script.read_text(encoding="utf-8")
    return text[: text.rindex('main "$@"')]


def _run_harness(body: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    harness = tmp_path / "harness.sh"
    harness.write_text(body, encoding="utf-8")
    return subprocess.run(["bash", str(harness)], capture_output=True, text=True, check=False)


def test_configuration_lives_under_etc() -> None:
    assert str(deployed_output.PROJECT_STATE_ROOT) == "/etc/agentic-postgres/projects"


def test_generated_output_lives_under_var_lib() -> None:
    assert str(deployed_output.RENDERED_ROOT) == "/var/lib/agentic-postgres/rendered"


def test_the_deployed_document_is_outputs_json_under_the_state_root() -> None:
    assert (
        str(deployed_output.deployed_path("alpha-dev"))
        == "/etc/agentic-postgres/projects/alpha-dev/outputs.json"
    )


def test_rendered_path_is_a_directory_under_the_rendered_root() -> None:
    assert (
        str(deployed_output.rendered_path("alpha-dev"))
        == "/var/lib/agentic-postgres/rendered/alpha-dev"
    )


def test_the_two_roots_do_not_share_a_prefix() -> None:
    """The self-comparison regression.

    If either root is a prefix of the other, `bin/compose.sh` can once again be
    handed the same `compose.env` as both its project env file and its runtime
    env file, and `assert_disjoint` will compare it with itself.
    """
    state = str(deployed_output.PROJECT_STATE_ROOT)
    rendered = str(deployed_output.RENDERED_ROOT)
    assert not state.startswith(rendered)
    assert not rendered.startswith(state)


def test_compose_sh_reads_the_state_root_from_etc(code_only) -> None:
    source = code_only((REPO_ROOT / "bin" / "compose.sh").read_text(encoding="utf-8"))
    assert 'readonly PROJECT_STATE_ROOT="/etc/agentic-postgres/projects"' in source


def test_project_runtime_resolves_two_distinct_directories(code_only) -> None:
    source = code_only((REPO_ROOT / "bin" / "project-runtime.sh").read_text(encoding="utf-8"))
    assert 'readonly PROJECT_STATE_ROOT="/etc/agentic-postgres/projects"' in source
    assert 'readonly PROJECT_RENDERED_ROOT="/var/lib/agentic-postgres/rendered"' in source


def test_the_launcher_reads_the_document_the_deploy_writes(code_only) -> None:
    """`deployment.json` was never written under any name, and
    `installed_release_commit` belongs to edge state."""
    source = code_only(
        (REPO_ROOT / "libexec" / "agentic-postgres-project").read_text(encoding="utf-8")
    )
    assert "deployment.json" not in source
    assert "installed_release_commit" not in source
    assert "outputs.json" in source
    assert ".source_commit" in source


# ---------------------------------------------------------------------------
# Regression: three writer/reader pairs the ADR 0020 review found unchecked
# ---------------------------------------------------------------------------


@requires_rendered_fixture
def test_edge_network_reads_the_deployed_root_and_a_key_the_fixture_carries(
    tmp_path: Path,
) -> None:
    """`bin/edge-network.sh` must read the same root the deploy writes the
    rendered directory to, and the key it greps out of `compose.env` must
    actually be a key a rendered `compose.env` carries.

    Both halves are exercised for real: the constant is read back from the
    sourced script rather than re-typed here, and the grep runs against the
    real fixture at `.generated/fixture-alpha-dev/compose.env` rather than a
    literal `EDGE_NETWORK_NAME=...` copied into the test.
    """
    body = _sourced_definitions(REPO_ROOT / "bin" / "edge-network.sh")

    root_result = _run_harness(body + '\nprintf %s "${PROJECT_RENDERED_ROOT}"\n', tmp_path)
    assert root_result.returncode == 0, root_result.stderr
    assert root_result.stdout == str(deployed_output.RENDERED_ROOT), (
        "bin/edge-network.sh reads a root the deploy does not write the rendered directory to"
    )

    # project_edge_network() takes its root from PROJECT_RENDERED_ROOT, which is
    # not writable here without root (it lives under /var/lib). Redirecting it
    # at the real .generated tree for this one invocation lets the real
    # function's grep/cut run against the real fixture, rather than asserting
    # that some EDGE_NETWORK_NAME string merely appears somewhere in the file.
    redirected = body.replace(
        'readonly PROJECT_RENDERED_ROOT="/var/lib/agentic-postgres/rendered"',
        f"PROJECT_RENDERED_ROOT={shlex.quote(str(REPO_ROOT / '.generated'))}",
    )
    assert redirected != body, "could not redirect PROJECT_RENDERED_ROOT for the test"
    key_result = _run_harness(redirected + "\nproject_edge_network fixture-alpha-dev\n", tmp_path)
    assert key_result.returncode == 0, key_result.stderr

    expected = next(
        line.partition("=")[2]
        for line in FIXTURE_COMPOSE_ENV.read_text(encoding="utf-8").splitlines()
        if line.startswith("EDGE_NETWORK_NAME=")
    )
    assert key_result.stdout == expected


@requires_rendered_fixture
def test_compose_sh_looks_for_the_override_where_the_deploy_writes_it(
    tmp_path: Path, code_only
) -> None:
    """`bin/compose.sh` resolves `OVERRIDE_PATH` relative to its own
    project-directory argument. `bin/deploy-session-2.py` must therefore write
    `runtime-compose.override.yaml` into the same directory it installs the
    rendered output into, or compose.sh's `[ -f "${OVERRIDE_PATH}" ]` check
    looks in a directory nothing ever wrote it to.

    The compose.sh half is exercised for real: `configure_project_scope` is
    the actual function, run against the real fixture directory. The
    deploy-session-2.py half stays source-text (it requires root and a
    provisioned host to run for real, same as
    test_deploy_establishes_roots.py), but is read with `code_only` so a
    comment cannot satisfy it.
    """
    project_dir = FIXTURE_COMPOSE_ENV.parent
    body = _sourced_definitions(REPO_ROOT / "bin" / "compose.sh")
    # ROOT_DIR is normally derived from the script's own on-disk location; the
    # harness lives in a temp directory, so it is pointed at the real repo
    # here rather than left to resolve against the temp file's location.
    # Nothing under test depends on ROOT_DIR -- OVERRIDE_PATH is derived from
    # PROJECT_DIR -- but configure_project_scope also checks PROJECT_MODEL
    # (ROOT_DIR/compose.yaml) exists, which requires ROOT_DIR to be real.
    body = body.replace(
        'ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"',
        f"ROOT_DIR={shlex.quote(str(REPO_ROOT))}",
    )
    harness = body + (
        f"\nparse_arguments {shlex.quote(str(project_dir))} config"
        "\nconfigure_project_scope"
        '\nprintf %s "${OVERRIDE_PATH}"\n'
    )
    result = _run_harness(harness, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == str(project_dir / "runtime-compose.override.yaml")

    deploy_source = code_only(
        (REPO_ROOT / "bin" / "deploy-session-2.py").read_text(encoding="utf-8")
    )
    assert 'staging / "runtime-compose.override.yaml"' in deploy_source, (
        "bin/deploy-session-2.py no longer writes the override into the staged "
        "rendered directory before the atomic move"
    )
    assert "deployed_output.rendered_path(key)" in deploy_source, (
        "bin/deploy-session-2.py no longer installs the rendered directory at "
        "deployed_output.rendered_path(key)"
    )


def test_state_directory_pattern_accepts_the_path_the_deploy_passes() -> None:
    """`schemas/outputs.schema.json`'s `runtime.state_directory` pattern must
    accept the path `bin/deploy-session-2.py` actually passes:
    `PROJECT_STATE_ROOT/<key>`. Built from the real
    `deployed_output.PROJECT_STATE_ROOT` constant and matched against the
    pattern read out of the schema file, so neither side restates the other
    as a literal (the schema pattern failed exactly this way once already,
    at deploy step 6, after the containers were already up -- ADR 0020).
    """
    schema = json.loads((REPO_ROOT / "schemas" / "outputs.schema.json").read_text(encoding="utf-8"))
    pattern = schema["$defs"]["deployedDocument"]["properties"]["runtime"]["properties"][
        "state_directory"
    ]["pattern"]

    path = f"{deployed_output.PROJECT_STATE_ROOT}/alpha-dev"
    assert re.fullmatch(pattern, path), f"{path!r} does not match {pattern!r}"
