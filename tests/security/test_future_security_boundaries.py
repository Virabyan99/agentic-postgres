"""Security boundaries owned by later sessions.

Every test here is a genuine placeholder, not a skip. The ``future`` marker
makes it collectible and skipped; the body calls ``pytest.fail``. Removing the
marker therefore *activates* the test and exposes the unfinished
implementation, which is the signal the owning session needs. A body that
called ``pytest.skip()`` would stay green forever and prove nothing.

Requirement IDs here must match ``tests/acceptance-registry.yaml`` exactly;
``test_future_marker_policy.py`` enforces that in both directions.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.p0, pytest.mark.security]


def unimplemented(session: int, what: str) -> None:
    pytest.fail(f"Replace this placeholder with the Session {session} implementation: {what}")


# ---------------------------------------------------------------------------
# Session 3 — activated
#
# The seven Session 3 placeholders were replaced in Run 6 by real proofs in
# tests/security/test_session3_authorization.py. They are gone rather than kept
# beside their implementations: a placeholder next to a real test is a second,
# weaker claim about the same requirement, which is what
# test_no_requirement_is_claimed_by_two_placeholders exists to prevent.
#
#   SEC-RLS-001, SEC-VIEW-001, SEC-FUNC-001, SEC-DEFAULT-001, SEC-OWNER-001,
#   SEC-DB-001, SEC-DB-002  -> tests/security/test_session3_authorization.py
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Session 4 — activated in Run 8
#
#   SEC-DBX-001  -> tests/external/test_session4_public_transports.py
#   SEC-DBX-002, SEC-DBX-003 -> tests/deployment/test_session4_boundaries.py
#
# The last two live under tests/deployment/ and carry the `security` marker. The
# marker decides what runs and what the evidence records; the directory decides
# which conftest is in scope, and the fixtures that make them measurable are
# there. A second copy of "how a materialized credential is read" was not worth
# a directory convention.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Session 5 — the REST surface cannot widen the authorization model
# ---------------------------------------------------------------------------


@pytest.mark.future(session=5, requirement="SEC-ANON-001")
def test_anon_cannot_reach_protected_resources() -> None:
    unimplemented(5, "the anonymous role reads nothing it is not granted")


@pytest.mark.future(session=5, requirement="SEC-PRIV-001")
def test_api_roles_cannot_reach_the_private_schema() -> None:
    unimplemented(5, "app and app_private are unreachable through PostgREST")


# ---------------------------------------------------------------------------
# Session 6 — token validation
# ---------------------------------------------------------------------------


@pytest.mark.future(session=6, requirement="SEC-JWT-001")
def test_invalid_issuer_audience_algorithm_or_token_type_is_rejected() -> None:
    unimplemented(6, "the full negative-token matrix, including expiry and nbf")


@pytest.mark.future(session=6, requirement="SEC-KEY-001")
def test_verifying_services_do_not_hold_the_private_signing_key() -> None:
    unimplemented(6, "only the auth service can sign; verifiers hold public material")


@pytest.mark.future(session=6, requirement="SEC-CRED-001")
def test_raw_credentials_are_never_stored_or_logged() -> None:
    unimplemented(6, "passwords and agent secrets exist only as hashes")


# ---------------------------------------------------------------------------
# Session 9 — revocation and attribution
# ---------------------------------------------------------------------------


@pytest.mark.future(session=9, requirement="SEC-REV-001")
def test_revoked_token_is_denied_by_mcp_and_postgrest() -> None:
    unimplemented(9, "a token issued before revocation fails its next read and write")


@pytest.mark.future(session=9, requirement="SEC-PARAM-001")
def test_tool_parameters_cannot_override_identity_or_scope() -> None:
    unimplemented(9, "agent_id, role, and scope come from claims, never parameters")


@pytest.mark.future(session=8, requirement="SEC-INJ-001")
def test_injection_strings_remain_data() -> None:
    unimplemented(8, "a SQL payload in a filter value does not change query structure")


# ---------------------------------------------------------------------------
# Session 2 — activated
#
# SEC-NET-001 and SEC-SECRET-001 lived here as placeholders through Session 1.
# Session 2 replaced them with real proofs, so the placeholders are gone rather
# than retained alongside: a placeholder kept next to its implementation would
# be a second, weaker claim about the same requirement, and
# test_no_requirement_is_claimed_by_two_placeholders exists to prevent exactly
# that ambiguity.
#
#   SEC-NET-001     -> tests/external/test_session2_public_edge.py
#   SEC-SECRET-001  -> tests/security/test_session2_secret_model.py
#                      tests/security/test_session2_secrets.py
# ---------------------------------------------------------------------------
