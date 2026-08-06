"""The two roots a project's files live in, and the fact that they differ.

`bin/project-runtime.sh` passed one directory to `bin/compose.sh` as the Compose
project directory *and* let `bin/compose.sh` derive its runtime env file from the
same key. Both resolved to `<dir>/compose.env`, so `assert_disjoint` compared a
file with itself, every key overlapped, and the runtime path could only exit 5.

The test that matters here is the last one: the two roots must not share a
prefix. Everything else is a detail of where each file lives.
"""

from __future__ import annotations

import pytest

from agentic_postgres import REPO_ROOT, deployed_output

pytestmark = [pytest.mark.contract, pytest.mark.p0]


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
