"""PostgREST and FastAPI contract, owned by Sessions 5 and 6."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.p0, pytest.mark.integration]


def unimplemented(session: int, what: str) -> None:
    pytest.fail(f"Replace this placeholder with the Session {session} implementation: {what}")


# ---------------------------------------------------------------------------
# Session 5 — activated in Run 8
#
#   API-SCHEMA-001, API-REST-001, API-RPC-001, API-ERR-001, API-LIMIT-001
#       -> tests/deployment/test_session5_rest_surface.py
#   API-CONTRACT-001, API-CACHE-001
#       -> tests/deployment/test_session5_api_contract.py
#
# The seven placeholders that were here are gone rather than kept beside their
# implementations: a placeholder next to a real test is a second, weaker claim
# about the same requirement, which is what
# test_no_requirement_is_claimed_by_two_placeholders exists to prevent.
#
# They land under tests/deployment/ rather than here because the fixtures that
# make them measurable -- a minted token, a call to the published route, a
# statement against the cluster -- are in that directory's conftest. The marker
# decides what runs and what the evidence records; the directory decides which
# conftest is in scope. That is D111's shape, one session on.
# ---------------------------------------------------------------------------


@pytest.mark.future(session=6, requirement="API-AUTH-001")
def test_login_and_identity_endpoints_behave() -> None:
    unimplemented(6, "login issues a short-lived token and /auth/me reflects it")


@pytest.mark.future(session=6, requirement="API-ADMIN-001")
def test_admin_endpoints_require_explicit_admin_scope() -> None:
    unimplemented(6, "a role name alone is insufficient for admin operations")
