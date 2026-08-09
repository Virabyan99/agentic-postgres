"""Pytest configuration for the acceptance harness.

The ``future`` marker lifecycle (runbook §4.6, §8.3) is the important part.
A placeholder for a later session must be *collectible* and *skipped*, but must
fail if it is ever executed. That is why the skip is added here at collection
time rather than by ``pytest.skip()`` inside the test body: removing the marker
then activates the test and exposes the unfinished implementation, which is
exactly the signal a later session needs.
"""

from __future__ import annotations

import ast
import os

import pytest

from agentic_postgres import CURRENT_SESSION, REPO_ROOT

TESTS_ROOT = REPO_ROOT / "tests"


def acceptance_session() -> int:
    """Gate session for registry policy checks.

    Defaults to the repository's ``CURRENT_SESSION`` so a bare ``pytest`` run
    enforces the same policy as ``bin/session-01-check.sh`` instead of silently
    skipping it (plan decision P).
    """
    raw = os.environ.get("APG_ACCEPTANCE_SESSION")
    if raw is None:
        return CURRENT_SESSION
    try:
        return int(raw)
    except ValueError as exc:
        raise pytest.UsageError(f"APG_ACCEPTANCE_SESSION must be an integer, got {raw!r}") from exc


def _marker_arguments(decorator: ast.expr) -> dict[str, ast.expr] | None:
    """Return the kwargs of a ``@pytest.mark.future(...)`` decorator, if any."""
    if not isinstance(decorator, ast.Call):
        return None
    target = decorator.func
    if not isinstance(target, ast.Attribute) or target.attr != "future":
        return None
    return {kw.arg: kw.value for kw in decorator.keywords if kw.arg}


def future_markers_in_source() -> dict[str, tuple[int, str]]:
    """Map ``path::test_name`` to ``(session, requirement)`` for every marker.

    Read with ``ast`` rather than by importing or by regex: importing would
    execute module-level code, and a regex would silently miss a marker written
    across two lines.
    """
    found: dict[str, tuple[int, str]] = {}

    for path in sorted(TESTS_ROOT.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                arguments = _marker_arguments(decorator)
                if arguments is None:
                    continue
                session = arguments.get("session")
                requirement = arguments.get("requirement")
                if not isinstance(session, ast.Constant) or not isinstance(
                    requirement, ast.Constant
                ):
                    continue
                relative = path.relative_to(REPO_ROOT).as_posix()
                found[f"{relative}::{node.name}"] = (session.value, requirement.value)

    return found


#: Environment variables that name the three execution environments of Session
#: 2. A test gated on one of these is written and complete; it is the *host*
#: that is absent. The tuple is closed so that a typo in a gate reads as an
#: error rather than as a test that quietly never runs anywhere.
ENVIRONMENT_VARIABLES = (
    # The edge plane comes up before any project is deployed, so "the edge is
    # running" and "a project exists" are genuinely different states. A test
    # that needs Traefik must not have to claim it needs a project's outputs.
    "APG_EDGE_DEPLOYED",
    "APG_LIVE_HOST",
    "APG_PROJECT_A_OUTPUTS",
    "APG_PROJECT_B_OUTPUTS",
    # No APG_PUBLIC_HOST_*: the hostname is read from the deployed document
    # rather than supplied alongside it. Two sources for one fact is how a run
    # ends up measuring one project's certificate against another's route.
    "APG_PUBLIC_IPV4",
    "APG_PUBLIC_IPV6",
    "APG_SECRET_SENTINEL_FILE",
)


@pytest.fixture(scope="session")
def future_markers() -> dict[str, tuple[int, str]]:
    """Every ``future`` marker in the suite, keyed by node ID."""
    return future_markers_in_source()


@pytest.fixture(scope="session")
def gate_session() -> int:
    return acceptance_session()


def apply_future_marker(item: pytest.Item) -> None:
    marker = item.get_closest_marker("future")
    if marker is None:
        return

    session = marker.kwargs.get("session")
    requirement = marker.kwargs.get("requirement")
    if not isinstance(session, int) or not isinstance(requirement, str):
        raise pytest.UsageError(
            f"Invalid future marker on {item.nodeid}: "
            f"expected session=<int> and requirement=<str>, "
            f"got session={session!r}, requirement={requirement!r}"
        )

    item.add_marker(pytest.mark.skip(reason=f"Future Session {session}: {requirement}"))


def apply_environment_gate(item: pytest.Item) -> None:
    """Skip because the environment is absent — never because a test is unwritten.

    Session 2 introduces tests that cannot run in a checkout: they measure a
    provisioned host or a public route. Those must not use ``future``.
    ``future`` means *nobody has written this*, and its entire value is that
    removing it activates a failing placeholder. Reused for "the host is not
    here" it would be removed on the host, and would then have no way left to
    say that work is unfinished.

    The two are therefore kept apart by construction. Environment absence is
    this marker, whose condition is a named variable and nothing else;
    ``tests/contract/test_environment_gates.py`` asserts that every
    ``live_host`` and ``external`` test carries one.
    """
    marker = item.get_closest_marker("requires_environment")
    if marker is None:
        return

    names = marker.args
    if not names or not all(isinstance(name, str) for name in names):
        raise pytest.UsageError(
            f"Invalid requires_environment marker on {item.nodeid}: "
            f"expected one or more variable names, got {names!r}"
        )

    unknown = [name for name in names if name not in ENVIRONMENT_VARIABLES]
    if unknown:
        raise pytest.UsageError(
            f"Invalid requires_environment marker on {item.nodeid}: "
            f"{unknown} are not in tests/conftest.py ENVIRONMENT_VARIABLES. "
            "A typo here would produce a test that silently never runs."
        )

    absent = [name for name in names if not os.environ.get(name)]
    if absent:
        item.add_marker(pytest.mark.skip(reason=f"environment absent: {', '.join(absent)}"))


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        apply_future_marker(item)
        apply_environment_gate(item)


def pytest_report_header(config: pytest.Config) -> str:
    del config
    return f"acceptance gate session: {acceptance_session()}"


@pytest.fixture(scope="session")
def code_only():
    """Strip whole-line comments from a source string.

    Ordering assertions over source text keep matching the prose that explains
    the ordering, which by construction sits above the code and therefore always
    comes first. That has produced a false failure four separate times in this
    repository: a comment reading "before install_units" made
    ``body.index("install_units")`` point at the explanation rather than the
    call.

    The same shape breaks *absence* assertions too, and Session 4 Run 7 hit it
    six times in one module: a fixture whose comment explains why it refuses
    ``?pgbouncer=true`` fails a scan for ``pgbouncer=true``, and the only way to
    make that scan pass without this is to delete the explanation.

    Three comment syntaxes, because this repository writes three: ``#`` for
    shell, Python and YAML, ``//`` for the JavaScript client fixtures, and
    ``--`` for SQL. Extended here rather than copied into a second helper, which
    is the thing the next paragraph says this fixture exists to prevent.

    **A SQL comment is ``--`` followed by whitespace or nothing**, and the
    distinction is not pedantry: a bare ``--`` prefix also matches a shell
    continuation line beginning with a long option. Stripping those removed
    ``--edge-static`` from ``edge.sh``'s ``do_up`` and turned a passing ordering
    assertion into a false failure the moment this was widened. The boundary is
    where the failure put it.

    A fixture rather than a copied two-line helper, so the next test that scans
    source text inherits the fix instead of rediscovering the bug.
    """

    def is_comment(line: str) -> bool:
        stripped = line.lstrip()
        if stripped.startswith(("#", "//")):
            return True
        return stripped == "--" or stripped.startswith("-- ")

    def strip(text: str) -> str:
        return "\n".join(line for line in text.splitlines() if not is_comment(line))

    return strip
