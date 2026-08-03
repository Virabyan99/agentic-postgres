"""Object storage ownership, owned by Session 7."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.p0, pytest.mark.integration]


def unimplemented(session: int, what: str) -> None:
    pytest.fail(f"Replace this placeholder with the Session {session} implementation: {what}")


@pytest.mark.future(session=7, requirement="STO-OWN-001")
def test_cross_user_object_download_is_denied() -> None:
    unimplemented(7, "User A cannot obtain a download URL for User B's object")


@pytest.mark.future(session=7, requirement="STO-KEY-001")
def test_client_supplied_object_keys_are_rejected() -> None:
    unimplemented(7, "keys are generated server-side and are not guessable")


@pytest.mark.future(session=7, requirement="STO-URL-001")
def test_presigned_urls_never_reach_logs_or_the_audit_table() -> None:
    unimplemented(7, "a presigned URL appears in the response and nowhere else")


@pytest.mark.future(session=7, requirement="STO-COMPLETE-001")
def test_abandoned_upload_intents_are_not_downloadable() -> None:
    unimplemented(7, "only objects verified against R2 reach the available state")
