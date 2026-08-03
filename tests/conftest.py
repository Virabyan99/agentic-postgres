"""Pytest configuration for the acceptance harness.

The ``future`` marker lifecycle (runbook §4.6, §8.3) is the important part.
A placeholder for a later session must be *collectible* and *skipped*, but
must fail if it is ever executed. That is why the skip is added here at
collection time rather than by ``pytest.skip()`` inside the test body:
removing the marker then activates the test and exposes the unfinished
implementation, which is exactly the signal a later session needs.
"""

from __future__ import annotations

import os

import pytest

from agentic_postgres import CURRENT_SESSION


def acceptance_session() -> int:
    """Gate session for registry policy checks.

    Defaults to the repository's ``CURRENT_SESSION`` so a bare ``pytest`` run
    enforces the same policy as ``bin/session-01-check.sh`` instead of
    silently skipping it (plan decision P).
    """
    raw = os.environ.get("APG_ACCEPTANCE_SESSION")
    if raw is None:
        return CURRENT_SESSION
    try:
        return int(raw)
    except ValueError as exc:
        raise pytest.UsageError(f"APG_ACCEPTANCE_SESSION must be an integer, got {raw!r}") from exc


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
