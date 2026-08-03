"""Backup and recovery, owned by Session 10.

Recovery is a feature only when restore has been demonstrated. These
placeholders exist so that claim cannot be made on prose alone.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.p0, pytest.mark.recovery]


def unimplemented(session: int, what: str) -> None:
    pytest.fail(f"Replace this placeholder with the Session {session} implementation: {what}")


@pytest.mark.future(session=10, requirement="REC-PITR-001")
def test_timestamp_targeted_restore_succeeds() -> None:
    unimplemented(10, "restore to a point between T1 and T2 into a disposable volume")


@pytest.mark.future(session=10, requirement="REC-SAFE-001")
def test_restore_never_touches_the_active_volume() -> None:
    unimplemented(10, "the live data directory is not mounted, overwritten, or mutated")


@pytest.mark.future(session=10, requirement="REC-SMOKE-001")
def test_restored_instance_passes_schema_and_rls_smoke_checks() -> None:
    unimplemented(10, "the restored database answers a protected read and a write RPC")


@pytest.mark.future(session=10, requirement="REC-EVID-001")
def test_restore_evidence_records_the_required_fields() -> None:
    unimplemented(10, "backup set, requested and achieved recovery point, RTO, schema version")


@pytest.mark.future(session=10, requirement="REC-WAL-001")
def test_wal_archiving_failure_is_visible() -> None:
    unimplemented(10, "a broken archive command produces a non-zero operational signal")
