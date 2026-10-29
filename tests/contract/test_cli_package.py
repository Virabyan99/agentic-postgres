"""The packaged CLI is `bin/cloud.py` with only its seam replaced, and it runs where Python does.

Session 43 (ADR 0284, D2666): `DX-PKG-001`. `bin/build-cli.py` is driven
as the operator and CI drive it; the staged tree is compared with its sources,
its imports walked, and the wheel installed into a clean pinned Python with no
network (`--network none`), where `apg --version` and every family's usage
are compared with what the tree's own `bin/cloud.py` prints -- the program
name read as `apg`, the exit code the tree's (D2684: `--help` is a usage error
in both, and the proof asserts the tree's behaviour, never a guessed one).
"""

from __future__ import annotations

import ast
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from tests.contract.test_image_contracts import LOCK, requires_docker

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

BUILD = REPO_ROOT / "bin" / "build-cli.py"
CLOUD = REPO_ROOT / "bin" / "cloud.py"
VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
#: The fourteen families the shims exec (`test_cli_contract` holds the shims).
FAMILIES = ("login", "logout", "context", "org", "project", "compute", "operation", "endpoint",
            "branch", "plan", "usage", "notifications", "insights", "monitoring")  # fmt: skip
SEAM = ("# packaging seam: begin\n", "# packaging seam: end\n")


def _build_module() -> Any:
    spec = importlib.util.spec_from_file_location("_apg_build_cli_under_test", BUILD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _outside_seam(text: str) -> str:
    head, rest = text.split(SEAM[0])
    return head + rest.split(SEAM[1])[1]


@pytest.fixture
def staged(tmp_path: Path) -> Path:
    out = tmp_path / "stage"
    _build_module().stage(out)
    return out


def test_the_stage_differs_only_in_the_seam(staged: Path) -> None:
    package = staged / "src" / "apg_cli"
    source = CLOUD.read_text(encoding="utf-8")
    cli = (package / "cli.py").read_text(encoding="utf-8")
    assert _outside_seam(cli) == _outside_seam(source)
    assert cli != source, "the seam was not replaced"
    for module in ("control_client.py", "scram.py"):
        original = REPO_ROOT / "src" / "agentic_postgres" / module
        assert (package / module).read_bytes() == original.read_bytes(), module
    assert (staged / "LICENSE").read_bytes() == (REPO_ROOT / "LICENSE").read_bytes()
    assert sorted(path.name for path in package.iterdir()) == [
        "__init__.py", "__main__.py", "cli.py", "control_client.py", "scram.py",
    ]  # fmt: skip


def test_the_package_imports_only_stdlib(staged: Path) -> None:
    """Every import in the staged package is the standard library or the
    package itself -- `plans`, `service_source` and `agentic_postgres` cannot
    travel in a wheel."""
    found: set[str] = set()
    for module in (staged / "src" / "apg_cli").glob("*.py"):
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                found.add(node.module.split(".")[0])
    allowed = set(sys.stdlib_module_names) | {"apg_cli", "__future__"}
    foreign = sorted(found - allowed)
    assert not foreign, foreign
    assert "apg_cli" in found


def test_the_version_is_the_release(staged: Path) -> None:
    init = (staged / "src" / "apg_cli" / "__init__.py").read_text(encoding="utf-8")
    assert f'__version__ = "{VERSION}"' in init
    pyproject = (staged / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{VERSION}"' in pyproject
    assert 'name = "agentic-postgres-cli"' in pyproject
    assert 'requires-python = ">=3.11"' in pyproject
    assert 'apg = "apg_cli.cli:main"' in pyproject


def test_the_package_names_the_sites_own_addresses(staged: Path) -> None:
    """ADR 0299, D2962's rule: the README's API endpoint, its documentation
    link and the Homepage are `site_build`'s own constants -- the build cannot
    import `site_build` (the publish job's Python has no `yaml`), so the typed
    copies are held equal to it here, and the domain moves in both together
    or this fails. Every `https://` the two files name is one of these or the
    repository."""
    from agentic_postgres import site_build

    readme = (staged / "README.md").read_text(encoding="utf-8")
    pyproject = (staged / "pyproject.toml").read_text(encoding="utf-8")
    assert f"--endpoint {site_build.CONTROL_ENDPOINT} " in readme
    assert f"{site_build.SITE_URL}/docs/cli/" in readme
    assert f'Homepage = "{site_build.SITE_URL}/"' in pyproject
    named = {url.rstrip(".,") for url in re.findall(r"https://[^\s\"'`]+", readme + pyproject)}
    allowed = {
        site_build.CONTROL_ENDPOINT,
        f"{site_build.SITE_URL}/docs/cli/",
        f"{site_build.SITE_URL}/",
        "https://github.com/Virabyan99/agentic-postgres",
    }
    assert named <= allowed, sorted(named - allowed)


def test_an_out_inside_the_repository_is_refused(tmp_path: Path) -> None:
    for out in (REPO_ROOT / "dist-x", REPO_ROOT):
        done = subprocess.run([sys.executable, str(BUILD), "--out", str(out)],
                              capture_output=True, text=True, check=False)  # fmt: skip
        assert done.returncode == 2 and "inside the repository" in done.stderr, done.stderr
        assert not (REPO_ROOT / "dist-x").exists()
    full = tmp_path / "full"
    full.mkdir()
    (full / "x").write_text("x", encoding="utf-8")
    done = subprocess.run([sys.executable, str(BUILD), "--out", str(full)],
                          capture_output=True, text=True, check=False)  # fmt: skip
    assert done.returncode == 2 and "not an empty directory" in done.stderr, done.stderr


def _tree_usage(family: str) -> tuple[int, str]:
    done = subprocess.run([sys.executable, str(CLOUD), family, "--help"],
                          capture_output=True, text=True, check=False)  # fmt: skip
    return done.returncode, (done.stdout + done.stderr).replace("cloud.py", "apg")


@requires_docker
@pytest.mark.skipif(shutil.which("uv") is None, reason="uv builds the wheel and is not on PATH")
def test_the_wheel_runs_every_family(tmp_path: Path) -> None:
    out = tmp_path / "cli"
    built = subprocess.run([sys.executable, str(BUILD), "--out", str(out)],
                           capture_output=True, text=True, check=False, timeout=600)  # fmt: skip
    assert built.returncode == 0, built.stderr
    wheels = sorted((out / "dist").glob("*.whl"))
    assert [wheel.name for wheel in wheels] == [f"agentic_postgres_cli-{VERSION}-py3-none-any.whl"]
    results = tmp_path / "results"
    results.mkdir()
    # A script file, never an inline loop through two shells (CLAUDE.md §1).
    script = tmp_path / "run.sh"
    script.write_text(
        "set -u\n"
        "pip install --quiet --disable-pip-version-check --root-user-action=ignore --no-index "
        "/dist/*.whl || exit 90\n"
        "apg --version > /results/version 2>&1; echo $? > /results/version.rc\n"
        f"for family in {' '.join(FAMILIES)}; do\n"
        '  apg "$family" --help > "/results/$family" 2>&1; echo $? > "/results/$family.rc"\n'
        "done\n",
        encoding="utf-8",
    )
    done = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "-v", f"{out / 'dist'}:/dist:ro",
         "-v", f"{results}:/results", "-v", f"{script}:/run.sh:ro",
         LOCK["PYTHON_RUNTIME_IMAGE"], "sh", "/run.sh"],
        capture_output=True, text=True, check=False, timeout=600,
    )  # fmt: skip
    assert done.returncode == 0, done.stdout + done.stderr
    assert (results / "version").read_text(encoding="utf-8") == f"apg {VERSION}\n"
    assert (results / "version.rc").read_text(encoding="utf-8").strip() == "0"
    for family in FAMILIES:
        # The tree's own answer is the expectation: a family with verbs prints
        # its usage, `logout` (no verbs) the top level's -- exit 2 either way.
        code, usage = _tree_usage(family)
        assert usage.startswith("usage: apg ") and "cloud.py" not in usage, (family, usage)
        # Whitespace collapsed: argparse indents a wrapped line by the
        # program name's length, which is the one thing the seam changes.
        printed = (results / family).read_text(encoding="utf-8")
        assert printed.split() == usage.split(), family
        assert (results / f"{family}.rc").read_text(encoding="utf-8").strip() == str(code), family
