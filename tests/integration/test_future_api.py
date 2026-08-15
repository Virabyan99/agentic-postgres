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


# ---------------------------------------------------------------------------
# Session 6 — activated in Run 11
#
#   API-AUTH-001, API-AUTH-002 -> tests/deployment/test_session6_identity.py
#   API-ADMIN-001              -> tests/deployment/test_session6_admin.py
#
# API-AUTH-002's contract half stays in tests/contract/test_auth_strict_json.py
# and test_auth_tokens.py, which Run 7 wrote. It is registered against the
# requirement rather than duplicated here: the strict parser's refusals need no
# deployment, and the one property that does -- that an oversized body is
# refused by the EDGE rather than read in full by the service (D273) -- is the
# live half and lives with the other deployment proofs.
#
# Both placeholders are gone rather than kept beside their implementations.
# ---------------------------------------------------------------------------
