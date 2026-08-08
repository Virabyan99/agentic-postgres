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
    project-directory argument. `bin/deploy-project.py` must therefore write
    `runtime-compose.override.yaml` into the same directory it installs the
    rendered output into, or compose.sh's `[ -f "${OVERRIDE_PATH}" ]` check
    looks in a directory nothing ever wrote it to.

    The compose.sh half is exercised for real: `configure_project_scope` is
    the actual function, run against the real fixture directory. The
    deploy-project.py half stays source-text (it requires root and a
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

    deploy_source = code_only((REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8"))
    assert 'staging / "runtime-compose.override.yaml"' in deploy_source, (
        "bin/deploy-project.py no longer writes the override into the staged "
        "rendered directory before the atomic move"
    )
    assert "deployed_output.rendered_path(key)" in deploy_source, (
        "bin/deploy-project.py no longer installs the rendered directory at "
        "deployed_output.rendered_path(key)"
    )


def test_state_directory_pattern_accepts_the_path_the_deploy_passes() -> None:
    """`schemas/outputs.schema.json`'s `runtime.state_directory` pattern must
    accept the path `bin/deploy-project.py` actually passes:
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


# ---------------------------------------------------------------------------
# OVERRIDE_REQUIRED: a project-scope --runtime up/restart with no
# runtime-compose.override.yaml is refused, and down/ps/logs and --edge are
# not caught by the same check.
# ---------------------------------------------------------------------------

COMPOSE_SH = REPO_ROOT / "bin" / "compose.sh"
ALPHA = FIXTURE_COMPOSE_ENV.parent
HOST_MANIFEST = REPO_ROOT / "host.example.yaml"

#: Substring unique to OVERRIDE_REQUIRED's own die() message. `main()`'s
#: privilege check ("--runtime requires root") also exits 3, so the two must
#: be told apart by message, never by exit code alone (see
#: `_override_check_result` below for why a real `main()` call cannot do
#: this as a non-root test process).
OVERRIDE_MESSAGE = "is unroutable without it"


def _compose_definitions_at_real_root() -> str:
    """`_sourced_definitions(COMPOSE_SH)` with ROOT_DIR pointed at the real
    repository, exactly as
    `test_compose_sh_looks_for_the_override_where_the_deploy_writes_it` does
    it: the harness runs from a tmp_path, so ROOT_DIR must not resolve
    against that instead.
    """
    body = _sourced_definitions(COMPOSE_SH)
    patched = body.replace(
        'ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"',
        f"ROOT_DIR={shlex.quote(str(REPO_ROOT))}",
    )
    assert patched != body, "could not redirect ROOT_DIR for the test"
    return patched


def _extract_override_check(compose_source: str) -> str:
    """The literal OVERRIDE_REQUIRED conditional out of `main()`, unmodified.

    The tests below run this directly instead of calling `main()`: `main()`
    checks "--runtime requires root" first, unconditionally, before it ever
    looks at OVERRIDE_REQUIRED -- and these tests run as non-root, so a real
    `main()` call would only ever observe "requires root", for every
    subcommand and every scope, regardless of what OVERRIDE_REQUIRED
    contains. A test that asserted exit 3 against that call would pass
    whether or not the constant were correct, emptied, or inverted, which is
    worse than no test.

    Slicing the real conditional out of the current file -- not retyping its
    condition or its die() message -- keeps this tied to the actual code: if
    the guard, the constant, or the message changes, the slice changes with
    it; if the anchor below stops matching at all, `.index` raises loudly
    instead of silently testing stale text.
    """
    start_marker = 'if [ "${EDGE}" -eq 0 ] && in_list "${subcommand}" "${OVERRIDE_REQUIRED}"; then'
    start = compose_source.index(start_marker)
    end_marker = "\n    fi\n"
    end = compose_source.index(end_marker, start) + len(end_marker)
    return compose_source[start:end]


def _override_check_result(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Resolve EDGE/subcommand/OVERRIDE_PATH/PROJECT_KEY for `args` exactly as
    `main()` would -- via the real `parse_arguments` and the real scope
    configurator -- then run the real OVERRIDE_REQUIRED conditional against
    what they resolved to.
    """
    override_check = _extract_override_check(COMPOSE_SH.read_text(encoding="utf-8"))
    quoted_args = " ".join(shlex.quote(a) for a in args)
    harness = _compose_definitions_at_real_root() + (
        f"\nparse_arguments {quoted_args}"
        '\nPROJECT_KEY=""'
        '\nENV_FILE_ARGS=(--env-file "${LOCK_ENV}")'
        '\nif [ "${EDGE}" -eq 1 ]; then configure_edge_scope; else configure_project_scope; fi'
        '\nsubcommand="$(first_subcommand)"'
        f"\n{override_check}\n"
    )
    return _run_harness(harness, tmp_path)


@requires_rendered_fixture
def test_runtime_up_without_an_override_is_refused_by_the_override_check(
    tmp_path: Path,
) -> None:
    """The regression this test exists for: OVERRIDE_REQUIRED could be
    emptied, inverted, or have its die() deleted, and
    `bin/session-01-check.sh` would stay green (a reviewer confirmed the
    behaviour but no test pinned it).

    ALPHA has no runtime-compose.override.yaml, which is the case under
    test. Asserted on the message, not just the exit code -- exit 3 alone is
    shared with `main()`'s privilege gate.
    """
    result = _override_check_result(tmp_path, str(ALPHA), "--runtime", "up")
    assert result.returncode == 3, result.stderr
    assert OVERRIDE_MESSAGE in result.stderr
    assert str(ALPHA / "runtime-compose.override.yaml") in result.stderr


@requires_rendered_fixture
@pytest.mark.parametrize("subcommand", ["down", "ps", "logs"])
def test_runtime_x_is_not_refused_for_a_missing_override(subcommand: str, tmp_path: Path) -> None:
    """down/ps/logs must stay usable without an override -- a partially
    installed or older-release project must still be inspectable and
    tearable-down. If OVERRIDE_REQUIRED ever grew to include one of these,
    this would start dying with the exact message the `up` test above
    expects, at the same exit code (3) -- which is why both tests assert on
    the message rather than the bare exit code.
    """
    result = _override_check_result(tmp_path, str(ALPHA), "--runtime", subcommand)
    assert result.returncode == 0, result.stderr
    assert OVERRIDE_MESSAGE not in result.stderr


@requires_rendered_fixture
def test_edge_scope_is_unaffected_by_the_override_check(tmp_path: Path) -> None:
    """The edge plane has no override file at all; OVERRIDE_PATH is never set
    for it. Uses `up`, which *is* in OVERRIDE_REQUIRED, so this exercises the
    `EDGE -eq 0` guard itself rather than merely picking a subcommand the
    check would ignore anyway.
    """
    result = _override_check_result(
        tmp_path, "--edge", "--host", str(HOST_MANIFEST), "--runtime", "up"
    )
    assert result.returncode == 0, result.stderr
    assert OVERRIDE_MESSAGE not in result.stderr
