"""The PostgreSQL cluster and the migration plane, owned by Session 3.

Marked ``database`` rather than ``contract`` even though these live under
tests/contract/, for the same reason ``test_future_deployment.py`` is marked
``deployment``: the Session 1 gate runs ``-m "contract and not future"``, and
once these are activated they need a container runtime or a live cluster. The
marker, not the directory, decides what runs.

Their real implementations arrive across Runs 3 to 6 and land in
``tests/contract/test_image_contracts.py``, the migration contract tests, and
``tests/security/test_session3_*.py``. See
``docs/plans/session-03-implementation-plan.md`` §2.2.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.p0, pytest.mark.database]


def unimplemented(session: int, what: str) -> None:
    pytest.fail(f"Replace this placeholder with the Session {session} implementation: {what}")


# ---------------------------------------------------------------------------
# The cluster itself
# ---------------------------------------------------------------------------


@pytest.mark.future(session=3, requirement="DBX-PG-001")
def test_locked_postgres_image_provides_pgvector_at_the_locked_version() -> None:
    unimplemented(3, "the locked digest runs PostgreSQL 18 with pgvector in extensions")


@pytest.mark.future(session=3, requirement="DBX-PG-002")
def test_postgres_is_unreachable_from_outside_the_project_network() -> None:
    unimplemented(3, "no published port, no edge network, and no Traefik label on postgres")


@pytest.mark.future(session=3, requirement="DBX-PG-003")
def test_a_volume_belonging_to_another_project_is_refused() -> None:
    unimplemented(3, "an identity mismatch against an existing volume exits 11 and adopts nothing")


# ---------------------------------------------------------------------------
# The migration plane
# ---------------------------------------------------------------------------


@pytest.mark.future(session=3, requirement="DBX-MIG-001")
def test_bootstrap_and_migration_authority_are_distinct() -> None:
    unimplemented(3, "the membership option columns show SET without INHERIT or ADMIN")


@pytest.mark.future(session=3, requirement="DBX-MIG-002")
def test_rendered_migrations_are_deterministic_and_match_their_source() -> None:
    unimplemented(3, "two renders of one input agree byte for byte and match the released lock")


@pytest.mark.future(session=3, requirement="DBX-MIG-003")
def test_an_applied_migration_cannot_be_edited_removed_or_reordered() -> None:
    unimplemented(3, "the five-way preflight refuses an edited, absent, or renumbered migration")
