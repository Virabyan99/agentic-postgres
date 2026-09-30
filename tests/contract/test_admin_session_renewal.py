"""The live suite's administrator session renews its token (D1854).

`tests/deployment/conftest.py`'s `admin_session` is opened once per run, and
the deployment issues 900-second tokens. Session 34's second 1.12.0 sweep
reached a proof 933 seconds after the session opened, and project A refused
its own administrator's expired token -- correctly. `AdminSession.token` now
logs in again inside a margin of the deadline. The live half cannot be run
here; this is the offline half, over the class itself with a stub renewal.
"""

# The token literals below are stub values a fake renewal returns, not secrets.
# ruff: noqa: S105, S106

from __future__ import annotations

import importlib.util
import sys
import time
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

MODULE_NAME = "apg_deployment_conftest"


def load_deployment_conftest() -> Any:
    if MODULE_NAME in sys.modules:
        return sys.modules[MODULE_NAME]
    spec = importlib.util.spec_from_file_location(
        MODULE_NAME, REPO_ROOT / "tests" / "deployment" / "conftest.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # A dataclass resolves its annotations through sys.modules[cls.__module__].
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def session(module: Any, *, expires_in: int, renew: Any) -> Any:
    return module.AdminSession(
        username="administrator",
        issued_token="first",
        expires_at=int(time.time()) + expires_in,
        user_id="u-1",
        role="project_admin",
        scopes=("admin_users:read",),
        renew=renew,
    )


def test_a_token_near_its_deadline_is_renewed_and_one_far_from_it_is_not() -> None:
    module = load_deployment_conftest()
    margin = module.ADMIN_TOKEN_RENEW_MARGIN_SECONDS
    calls: list[int] = []

    def renew() -> tuple[str, int]:
        calls.append(1)
        return f"renewed-{len(calls)}", int(time.time()) + 900

    fresh = session(module, expires_in=900, renew=renew)
    assert fresh.token == "first" and fresh.token == "first"
    assert calls == [] and fresh.renewals == 0

    # Inside the margin: renewed once, and the renewed token then holds.
    near = session(module, expires_in=margin - 1, renew=renew)
    assert near.token == "renewed-1"
    assert near.token == "renewed-1"
    assert near.renewals == 1 and len(calls) == 1

    # Past the deadline -- the 933-second case -- the same.
    expired = session(module, expires_in=-33, renew=renew)
    assert expired.token == "renewed-2"
    assert expired.renewals == 1


def test_the_token_never_appears_in_the_sessions_repr() -> None:
    """A failing proof prints its fixtures; the sweep's log printed this one."""
    module = load_deployment_conftest()
    shown = repr(session(module, expires_in=900, renew=None))
    assert "first" not in shown
    assert "administrator" in shown
