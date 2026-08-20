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
# Session 5 — activated in Run 8
#
#   SEC-ANON-001, SEC-PRIV-001, SEC-ROLE-001, SEC-DOCS-001
#       -> tests/deployment/test_session5_api_authorization.py
#   SEC-BOOT-001
#       -> tests/deployment/test_session5_bootstrap_identity.py
#   SEC-API-001
#       -> tests/external/test_session5_public_api.py
#
# The first five carry the `security` marker under tests/deployment/, which is
# D111's shape one session on: the marker decides what runs and what the
# evidence records, the directory decides which conftest is in scope, and the
# fixtures that make them measurable -- minting a token, calling the published
# route, reaching the cluster -- are there. A second copy of the one piece of
# plumbing that handles a credential was not worth a directory convention.
#
# SEC-API-001 moved to tests/external/, which is what the comment that used to
# sit here said would have to happen: it is measured from a network that is not
# the deployment host, and a requirement whose proofs straddle two environments
# breaks every claim containing it because `claim_mode` reads the union across a
# claim's requirements (ADR 0045). Measured before the move, with both controls:
# a claim over one requirement holding a host node ID and an external one is
# refused, and the same construction with both on the host resolves.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Session 6 — token validation
#
# SEC-JWT-001 and SEC-KEY-001 stay Session 6's. Session 5 issues bootstrap
# tokens and validates them, and a Session 5 requirement for either would give
# two IDs one meaning -- the call D47 made when it dropped API-DB-001 against
# SEC-VIEW-001. Session 5's negative matrix is proved under SEC-ROLE-001 and
# SEC-ANON-001; the key separation of the *temporary* issuer is SEC-BOOT-001,
# which Session 6 was expected to retire rather than inherit (ADR 0051) -- and
# did not: ADR 0088 built the cutover and Session 6 deliberately does not run it.
# ---------------------------------------------------------------------------


# Activated in Run 11:
#
#   SEC-JWT-001, SEC-KEY-001, SEC-KEY-002
#       -> tests/deployment/test_session6_tokens.py, plus the contract halves in
#          tests/contract/test_auth_tokens.py, test_jwt_claims.py, test_jwt_keys.py
#   SEC-CRED-001  -> tests/deployment/test_session6_credentials.py
#   SEC-CRED-002  -> tests/contract/test_auth_hashing.py
#   SEC-BOOT-002  -> tests/deployment/test_session6_admin.py
#   SEC-REV-002   -> tests/deployment/test_session6_identity.py
#
# The three placeholders are gone rather than kept beside their implementations,
# as every activated session before this one has done.
#
# Two of the new IDs are not the ones §2 of the plan named, and the reason is
# mechanical rather than editorial (ADR 0089). `SEC-BOOT-001` already means that
# the temporary bootstrap ISSUER holds the only private key, which is a
# different guarantee from Session 6's "the first administrator is created
# locally and exactly once"; `SEC-REV-001` is Session 9's and is about denial
# through MCP. Reusing the second would have been silent -- `claim_session` is
# the max of a claim's requirements' sessions, so the claim would have resolved
# to Session 9 and disappeared from Session 6's own gate with no error.
#
# SEC-BOOT-001 stays Session 5's and stays where it is: Session 6 does NOT
# retire the bootstrap issuer, because ADR 0088's cutover is built and
# deliberately unexercised. Its expiry clause is re-keyed rather than fired
# (ADR 0090).


# ---------------------------------------------------------------------------
# Session 9 — revocation and attribution
#
# SEC-REV-001 stays here and stays Session 9's. Session 6's non-resurrection
# property is SEC-REV-002, and the two are not the same guarantee: this one is
# about a revoked token failing its next read and write through MCP *and*
# PostgREST, and Session 6 ships no MCP.
# ---------------------------------------------------------------------------


@pytest.mark.future(session=9, requirement="SEC-REV-001")
def test_revoked_token_is_denied_by_mcp_and_postgrest() -> None:
    unimplemented(9, "a token issued before revocation fails its next read and write")


@pytest.mark.future(session=9, requirement="SEC-PARAM-001")
def test_tool_parameters_cannot_override_identity_or_scope() -> None:
    unimplemented(9, "agent_id, role, and scope come from claims, never parameters")


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
