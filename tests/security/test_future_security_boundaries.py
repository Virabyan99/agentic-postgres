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
# Session 3 — the database is the authorization source of truth
# ---------------------------------------------------------------------------


@pytest.mark.future(session=3, requirement="SEC-RLS-001")
def test_user_a_cannot_access_user_b_rows() -> None:
    unimplemented(3, "User A reads and mutates only its own notes and tasks")


@pytest.mark.future(session=3, requirement="SEC-VIEW-001")
def test_security_invoker_view_preserves_rls() -> None:
    unimplemented(3, "an api-schema view does not bypass the underlying row policy")


@pytest.mark.future(session=3, requirement="SEC-FUNC-001")
def test_api_role_cannot_execute_ungranted_functions() -> None:
    unimplemented(3, "execution is denied for every function not explicitly granted")


@pytest.mark.future(session=3, requirement="SEC-DEFAULT-001")
def test_newly_created_function_is_not_executable_by_public() -> None:
    unimplemented(3, "default EXECUTE on new functions is revoked from PUBLIC")


@pytest.mark.future(session=3, requirement="SEC-OWNER-001")
def test_object_owner_is_a_non_login_role() -> None:
    unimplemented(3, "no service connects as the object owner")


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
# Session 2 — network boundary
# ---------------------------------------------------------------------------


@pytest.mark.future(session=2, requirement="SEC-NET-001")
def test_public_routes_cannot_reach_direct_postgresql() -> None:
    unimplemented(2, "only Traefik is public, and it does not route to 5432")


@pytest.mark.future(session=2, requirement="SEC-SECRET-001")
def test_secret_values_do_not_appear_in_images_logs_or_compose_output() -> None:
    unimplemented(2, "repository, image, Compose, and log scans find no secret value")
