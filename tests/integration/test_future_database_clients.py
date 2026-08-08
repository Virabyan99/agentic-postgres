"""Database endpoint and client compatibility, owned by Session 4."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.p0, pytest.mark.integration]


def unimplemented(session: int, what: str) -> None:
    pytest.fail(f"Replace this placeholder with the Session {session} implementation: {what}")


@pytest.mark.future(session=4, requirement="DBX-001")
def test_prisma_migrate_uses_the_direct_url() -> None:
    unimplemented(4, "migrations run against the direct endpoint, not the pooler")


@pytest.mark.future(session=4, requirement="DBX-002")
def test_prisma_client_uses_the_pooled_url() -> None:
    unimplemented(4, "application CRUD works through PgBouncer transaction pooling")


@pytest.mark.future(session=4, requirement="DBX-003")
def test_psql_works_on_both_endpoints() -> None:
    unimplemented(4, "psql connects directly and through the pooler")


@pytest.mark.future(session=4, requirement="DBX-004")
def test_node_and_python_clients_work_through_the_pooler() -> None:
    unimplemented(4, "node pg and a Python driver both round-trip a query")


@pytest.mark.future(session=4, requirement="DBX-005")
def test_direct_postgresql_is_not_publicly_reachable() -> None:
    unimplemented(4, "the direct endpoint is reachable only through the tunnel")


# ---------------------------------------------------------------------------
# Pool behaviour (Session 4 Run 1; implemented in Run 8)
#
# What the locked pooler does was measured in Run 1 and recorded in
# tests/contract/test_image_contracts.py, not here: a named prepared statement
# is unusable after the backend changes when max_prepared_statements is 0, and
# usable when it is not. These three prove the *deployed* pooler behaves that
# way, which is a different claim from the image being capable of it.
# ---------------------------------------------------------------------------


@pytest.mark.future(session=4, requirement="DBX-POOL-001")
def test_the_pooler_runs_in_transaction_mode_with_bounded_limits() -> None:
    unimplemented(4, "pool mode, limits and prepared-statement tracking read from the pooler")


@pytest.mark.future(session=4, requirement="DBX-POOL-002")
def test_client_concurrency_stays_inside_the_server_budget() -> None:
    unimplemented(4, "more clients than the budget complete, and the budget is never exceeded")


@pytest.mark.future(session=4, requirement="DBX-POOL-003")
def test_a_named_prepared_statement_survives_a_backend_change() -> None:
    unimplemented(4, "the statement is reused after an observed backend change, not an assumed one")
