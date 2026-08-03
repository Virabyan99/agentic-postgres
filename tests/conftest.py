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


@pytest.fixture(scope="session")
def future_markers() -> dict[str, tuple[int, str]]:
    """Every ``future`` marker in the suite, keyed by node ID."""
    return future_markers_in_source()


@pytest.fixture(scope="session")
def gate_session() -> int:
    return acceptance_session()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        marker = item.get_closest_marker("future")
        if marker is None:
            continue

        session = marker.kwargs.get("session")
        requirement = marker.kwargs.get("requirement")
        if not isinstance(session, int) or not isinstance(requirement, str):
            raise pytest.UsageError(
                f"Invalid future marker on {item.nodeid}: "
                f"expected session=<int> and requirement=<str>, "
                f"got session={session!r}, requirement={requirement!r}"
            )

        item.add_marker(pytest.mark.skip(reason=f"Future Session {session}: {requirement}"))


def pytest_report_header(config: pytest.Config) -> str:
    del config
    return f"acceptance gate session: {acceptance_session()}"
