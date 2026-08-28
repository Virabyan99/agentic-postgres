"""``future`` and "the host is not here" must never become the same thing.

Session 2 introduces tests that cannot run in a checkout. There are two ways to
express that and only one of them is honest.

``future`` means *nobody has written this*. Its entire value is that removing
the marker activates a failing placeholder, which is how a later session learns
what it owes. If it were also used for "the environment is absent", then on the
host — where the environment is present — the marker would be removed, and the
suite would have lost its only way to say a test is unwritten.

``requires_environment`` means *this is written and the host is elsewhere*. Its
condition is a named variable and nothing else, so a test that is skipped
everywhere is a typo rather than a policy.

This module holds that line: statically, so a new module cannot opt out by
omission, and dynamically, so the gate is proved to both skip and admit.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

TESTS_ROOT = REPO_ROOT / "tests"

#: Markers that assert a test needs an execution environment a checkout lacks.
ENVIRONMENT_MARKERS = ("live_host", "external")


def marker_names(decorator: ast.expr) -> str | None:
    """Return the marker name for ``@pytest.mark.x`` or ``@pytest.mark.x(...)``."""
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def marker_arguments(node: ast.expr) -> list[str]:
    """String arguments of a ``requires_environment(...)`` marker."""
    if not isinstance(node, ast.Call):
        return []
    return [
        arg.value
        for arg in node.args
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
    ]


def module_markers(tree: ast.Module) -> list[ast.expr]:
    """Entries of a module-level ``pytestmark`` list, if present."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets
        ):
            if isinstance(node.value, ast.List):
                return list(node.value.elts)
    return []


def registered_variables() -> tuple[str, ...]:
    """Read ``ENVIRONMENT_VARIABLES`` out of the conftest source with ast.

    Parsed rather than imported, for the same reason the conftest parses
    markers rather than importing test modules: ``tests/`` is not a package, so
    importing it means putting a directory on ``sys.path`` to make one name
    resolve.
    """
    tree = ast.parse((TESTS_ROOT / "conftest.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "ENVIRONMENT_VARIABLES"
            for target in node.targets
        ):
            continue
        assert isinstance(node.value, ast.Tuple), "ENVIRONMENT_VARIABLES must stay a literal tuple"
        return tuple(
            element.value
            for element in node.value.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        )
    raise AssertionError("ENVIRONMENT_VARIABLES is absent from tests/conftest.py")


ENVIRONMENT_VARIABLES = registered_variables()


def all_test_modules() -> list[Path]:
    """Named to avoid the ``test_`` prefix, which pytest would collect."""
    return sorted(TESTS_ROOT.rglob("test_*.py"))


def gated_functions() -> list[tuple[str, set[str], set[str]]]:
    """``(node_id, marker names, requires_environment variables)`` per test.

    Module-level ``pytestmark`` and per-function decorators are merged, because
    pytest merges them and a check that looked at only one would be satisfied
    by moving a marker.
    """
    collected: list[tuple[str, set[str], set[str]]] = []

    for path in all_test_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module_level = module_markers(tree)
        module_names = {name for entry in module_level if (name := marker_names(entry))}
        module_variables = {
            variable
            for entry in module_level
            if marker_names(entry) == "requires_environment"
            for variable in marker_arguments(entry)
        }

        for node in tree.body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue

            names = set(module_names)
            variables = set(module_variables)
            for decorator in node.decorator_list:
                name = marker_names(decorator)
                if name:
                    names.add(name)
                if name == "requires_environment":
                    variables.update(marker_arguments(decorator))

            relative = path.relative_to(REPO_ROOT).as_posix()
            collected.append((f"{relative}::{node.name}", names, variables))

    return collected


# ---------------------------------------------------------------------------
# The static rule
# ---------------------------------------------------------------------------


def test_every_environment_dependent_test_names_its_variables() -> None:
    offenders = [
        node_id
        for node_id, names, variables in gated_functions()
        if names & set(ENVIRONMENT_MARKERS) and not variables
    ]
    assert not offenders, (
        f"tests marked {ENVIRONMENT_MARKERS} with no requires_environment gate: {offenders}. "
        "Without one they run in a checkout and fail for the wrong reason."
    )


#: Fixtures that read a deployment out of the environment, and the variable each
#: one needs. Requesting the fixture without declaring the variable produces a
#: collection-time KeyError instead of a skip.
FIXTURE_REQUIREMENTS = {
    "project_a": "APG_PROJECT_A_OUTPUTS",
    "project_b": "APG_PROJECT_B_OUTPUTS",
}


def consumed_variables() -> list[tuple[str, set[str]]]:
    """What each test actually needs, read from its parameters and its body."""
    needs: list[tuple[str, set[str]]] = []

    for path in all_test_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue

            required = {
                FIXTURE_REQUIREMENTS[argument.arg]
                for argument in node.args.args
                if argument.arg in FIXTURE_REQUIREMENTS
            }
            # os.environ["APG_..."] anywhere in the body counts too: reading it
            # directly is the same dependency as taking the fixture.
            for descendant in ast.walk(node):
                if (
                    isinstance(descendant, ast.Subscript)
                    and isinstance(descendant.slice, ast.Constant)
                    and isinstance(descendant.slice.value, str)
                    and descendant.slice.value.startswith("APG_")
                ):
                    required.add(descendant.slice.value)

            if required:
                relative = path.relative_to(REPO_ROOT).as_posix()
                needs.append((f"{relative}::{node.name}", required))

    return needs


def test_every_test_declares_the_environment_it_consumes() -> None:
    """Carrying *a* gate is not the same as carrying the *right* gate.

    ``test_every_environment_dependent_test_names_its_variables`` only checks
    that a live_host test declares something. Five tests in
    ``tests/deployment/test_session2_host.py`` declared ``APG_LIVE_HOST`` and
    then took the ``project_a`` fixture, so on a host with no project deployed
    they raised ``KeyError: 'APG_PROJECT_A_OUTPUTS'`` at fixture setup instead of
    skipping. That is the failure this file exists to prevent, and it passed the
    existing check comfortably.
    """
    declared = {node_id: variables for node_id, _, variables in gated_functions()}

    offenders = [
        (node_id, sorted(required - declared.get(node_id, set())))
        for node_id, required in consumed_variables()
        if required - declared.get(node_id, set())
    ]
    assert not offenders, (
        "tests that consume an environment they do not declare: "
        f"{offenders}. Without the declaration they error instead of skipping."
    )


def test_the_consumption_scan_finds_something() -> None:
    """A scan over an empty set proves nothing and passes forever."""
    assert consumed_variables(), "no test consumes a deployment fixture; the scan is stale"


def test_every_gate_names_a_registered_variable() -> None:
    """A typo here produces a test that silently never runs anywhere."""
    offenders = [
        (node_id, sorted(variables - set(ENVIRONMENT_VARIABLES)))
        for node_id, _, variables in gated_functions()
        if variables - set(ENVIRONMENT_VARIABLES)
    ]
    assert not offenders, f"gates naming unregistered variables: {offenders}"


def test_no_environment_dependent_test_is_also_future() -> None:
    """The two meanings may not be applied to the same test."""
    offenders = [
        node_id
        for node_id, names, _ in gated_functions()
        if "future" in names and names & set(ENVIRONMENT_MARKERS)
    ]
    assert not offenders, f"tests claiming both 'unwritten' and 'environment absent': {offenders}"


def test_no_future_placeholder_names_an_environment_variable() -> None:
    offenders = [
        node_id
        for node_id, names, variables in gated_functions()
        if "future" in names and variables
    ]
    assert not offenders, f"future placeholders gated on an environment variable: {offenders}"


def test_every_registered_variable_is_used() -> None:
    """An unused entry is either a deleted test or a gate that never fired."""
    used = {variable for _, _, variables in gated_functions() for variable in variables}
    unused = sorted(set(ENVIRONMENT_VARIABLES) - used)
    assert not unused, f"ENVIRONMENT_VARIABLES lists variables no test gates on: {unused}"


def test_the_session_two_environments_are_all_represented() -> None:
    """All three execution environments exist, so none was quietly dropped."""
    markers = {name for _, names, _ in gated_functions() for name in names}
    for marker in ENVIRONMENT_MARKERS:
        assert marker in markers, f"no test is marked {marker}"


# ---------------------------------------------------------------------------
# The gate actually gates
# ---------------------------------------------------------------------------


def run_generated(
    tmp_path: Path, body: str, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run a throwaway test beside a copy of the real conftest.

    The copy matters: without it pytest never loads the hook under test and
    every assertion below would pass for the wrong reason. This mirrors
    ``test_future_marker_policy.write_test`` for the same reason.
    """
    import shutil

    shutil.copy(TESTS_ROOT / "conftest.py", tmp_path / "conftest.py")
    path = tmp_path / "test_generated_gate.py"
    path.write_text(textwrap.dedent(body), encoding="utf-8")

    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src"), **environment},
    )


GATED_TEST = """
    import pytest

    pytestmark = [
        pytest.mark.live_host,
        pytest.mark.requires_environment("APG_LIVE_HOST"),
    ]

    def test_gated() -> None:
        assert False, "this body must run only when the environment is present"
"""


def test_an_absent_variable_skips(tmp_path: Path) -> None:
    result = run_generated(tmp_path, GATED_TEST, {"APG_LIVE_HOST": ""})
    assert result.returncode == 0, result.stdout
    assert "1 skipped" in result.stdout


def test_a_present_variable_admits_the_test(tmp_path: Path) -> None:
    """Guard the guard: a gate that skips unconditionally proves nothing.

    The generated body fails on purpose, so admission is observable — a gate
    that never admits would report a skip here and pass silently.
    """
    result = run_generated(tmp_path, GATED_TEST, {"APG_LIVE_HOST": "1"})
    assert result.returncode != 0, result.stdout
    assert "1 failed" in result.stdout
    assert "this body must run only when the environment is present" in result.stdout


def test_an_unregistered_variable_aborts_collection(tmp_path: Path) -> None:
    result = run_generated(
        tmp_path,
        """
        import pytest

        @pytest.mark.live_host
        @pytest.mark.requires_environment("APG_TYPOED_VARIABLE")
        def test_gated() -> None:
            pass
        """,
        {},
    )
    assert result.returncode != 0
    assert "Invalid requires_environment marker" in result.stdout + result.stderr


def test_a_gate_with_no_variable_aborts_collection(tmp_path: Path) -> None:
    result = run_generated(
        tmp_path,
        """
        import pytest

        @pytest.mark.live_host
        @pytest.mark.requires_environment()
        def test_gated() -> None:
            pass
        """,
        {},
    )
    assert result.returncode != 0
    assert "Invalid requires_environment marker" in result.stdout + result.stderr


def test_the_markers_are_declared() -> None:
    """``--strict-markers`` turns an undeclared marker into an error, not a typo."""
    text = (REPO_ROOT / "pytest.ini").read_text(encoding="utf-8")
    for marker in ENVIRONMENT_MARKERS:
        assert f"\n    {marker}:" in text, f"marker {marker} is not declared"
    assert "requires_environment(*names):" in text


def test_every_operator_supplied_gate_can_be_supplied_by_a_session_gate() -> None:
    """D687. A variable no gate can pass is a proof that can only ever skip.

    `APG_REDEPLOY_BEFORE_FILE` was read by a Session 11 fixture and exported by
    nothing. Both `DEP-002` proofs skipped, and `deployment_convergence` -- one
    of Session 11's own four claims -- came back unproved from the gate written
    in the same session to record it. **Question 5**: a claim was added, and the
    gate, which is a reader of the claim set, did not get the flag.

    A skip is not a pass, so nothing went green that should not have. What went
    wrong is quieter and worse: the run reported everything it could measure and
    the missing measurement looked like an operator choice.

    The roster is the declaration of *"this is supplied by an operator"*. This
    asserts each entry is reachable from at least one `bin/session-*-check.sh`,
    which is the only way an operator can supply one.
    """
    exported: set[str] = set()
    for path in sorted((REPO_ROOT / "bin").glob("session-*-check.sh")):
        for match in re.finditer(r"export\s+(APG_[A-Z0-9_]+)", path.read_text(encoding="utf-8")):
            exported.add(match.group(1))

    # The control. A scan matching no exports would report every name orphaned
    # and read as a catastrophe rather than as a broken scan (D374).
    assert "APG_LIVE_HOST" in exported, (
        "no gate appears to export APG_LIVE_HOST, which every host gate sets. The scan "
        "is not reading the gates, so its verdict below is about nothing"
    )

    unsuppliable = sorted(set(ENVIRONMENT_VARIABLES) - exported)
    assert not unsuppliable, (
        f"these are declared as operator-supplied and no session gate exports them, so "
        f"every proof gated on one can only skip: {unsuppliable}"
    )
