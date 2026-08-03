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
