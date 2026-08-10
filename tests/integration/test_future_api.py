"""PostgREST and FastAPI contract, owned by Sessions 5 and 6."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.p0, pytest.mark.integration]


def unimplemented(session: int, what: str) -> None:
    pytest.fail(f"Replace this placeholder with the Session {session} implementation: {what}")


@pytest.mark.future(session=5, requirement="API-SCHEMA-001")
def test_only_the_api_schema_is_exposed() -> None:
    unimplemented(5, "exposed resources match the committed allowlist snapshot")


@pytest.mark.future(session=5, requirement="API-CACHE-001")
def test_api_migration_reloads_the_schema_cache_and_updates_openapi() -> None:
    unimplemented(5, "a DDL change appears in OpenAPI after the reload")


@pytest.mark.future(session=5, requirement="API-LIMIT-001")
def test_row_limits_and_timeouts_are_enforced_server_side() -> None:
    unimplemented(5, "a client cannot raise the row ceiling by asking")


@pytest.mark.future(session=5, requirement="API-REST-001")
def test_http_reads_reproduce_the_database_row_level_result() -> None:
    unimplemented(5, "one claim, two transports, the same rows: HTTP agrees with psql")


@pytest.mark.future(session=5, requirement="API-RPC-001")
def test_writes_are_exactly_the_named_rpcs() -> None:
    unimplemented(5, "generic view writes fail, and an RPC changes at most one row")


@pytest.mark.future(session=5, requirement="API-ERR-001")
def test_the_public_error_contract_discloses_nothing_internal() -> None:
    unimplemented(5, "no SQL, role, schema path or foreign row reaches a public response")


@pytest.mark.future(session=5, requirement="API-CONTRACT-001")
def test_the_live_openapi_matches_the_reviewed_contract() -> None:
    unimplemented(5, "the normalized live document equals the committed snapshot")


@pytest.mark.future(session=6, requirement="API-AUTH-001")
def test_login_and_identity_endpoints_behave() -> None:
    unimplemented(6, "login issues a short-lived token and /auth/me reflects it")


@pytest.mark.future(session=6, requirement="API-ADMIN-001")
def test_admin_endpoints_require_explicit_admin_scope() -> None:
    unimplemented(6, "a role name alone is insufficient for admin operations")
