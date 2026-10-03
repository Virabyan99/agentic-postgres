"""A secret's age: the provider's update time, read, never acted on (ADR 0250).

`OPS-ROTATE-001`. A secret in `secrets.required.yaml` may declare
`max_age_days`; `doctor secrets --project KEY` reads the provider's
`updatedAt` for each such secret and this module judges it -- `ok`, `overdue`
or `unknown`. Nothing here rotates anything, and nothing reads a value: the
input is `infisical_client.SecretTimes`, which carries none.

What `updatedAt` means was measured before this was written (D2022): on both
projects, the four secrets with known rotations read `version` = 1 + their
rotation count and `updatedAt` = the last rotation's date, and the 37 never
rotated read `version` 1 with `updatedAt` equal to `createdAt`. Whether an edit
that is NOT a value replacement (a comment, a tag) also moves it was not
measured; ADR 0250 says what that would mean for a reading.

Pure: the I/O is `bin/doctor.py`'s. Every outcome carries its reason, and an
`unknown` is reported, never folded into `ok` (ADR 0195).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from agentic_postgres.infisical_client import SecretTimes

OK = "ok"
OVERDUE = "overdue"
UNKNOWN = "unknown"

#: The provider's clock and this host's may disagree by a little; an update
#: time further in the future than this is not an age.
CLOCK_TOLERANCE = timedelta(minutes=5)


@dataclass(frozen=True)
class Age:
    name: str
    max_age_days: int
    outcome: str
    reason: str
    #: Re-rendered from the parsed time, never the provider's own string: the
    #: doctor's evidence holds only values this program produced (ADR 0159).
    updated_at: str | None = None
    age_days: int | None = None
    version: int | None = None


def declared(secrets: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """The secrets that declare an age, in contract order."""
    return [secret for secret in secrets if "max_age_days" in secret]


def judge(name: str, max_age_days: int, times: SecretTimes, *, now: datetime) -> Age:
    """One secret's outcome from what the provider said about it."""
    if times.updated_at is None:
        return Age(name, max_age_days, UNKNOWN, "the provider returned no update time")
    try:
        updated = datetime.fromisoformat(times.updated_at)
    except ValueError:
        return Age(name, max_age_days, UNKNOWN, "the provider's update time is not a timestamp")
    if updated.tzinfo is None:
        return Age(name, max_age_days, UNKNOWN, "the provider's update time has no timezone")
    if updated > now + CLOCK_TOLERANCE:
        return Age(
            name,
            max_age_days,
            UNKNOWN,
            "the provider's update time is in the future",
            updated_at=updated.isoformat(),
            version=times.version,
        )
    age_days = max(0, (now - updated).days)
    outcome = OVERDUE if age_days > max_age_days else OK
    reason = f"{age_days} days since the provider's last update, declared {max_age_days}"
    return Age(
        name,
        max_age_days,
        outcome,
        reason,
        updated_at=updated.isoformat(),
        age_days=age_days,
        version=times.version,
    )


def unreadable(name: str, max_age_days: int, status: int | None) -> Age:
    """A read that failed. A 404 is the one status that means *absent*."""
    if status == 404:
        reason = "the provider holds no such secret (HTTP 404)"
    elif status is None:
        reason = "the provider could not be reached"
    else:
        reason = f"the provider answered HTTP {status}"
    return Age(name, max_age_days, UNKNOWN, reason)
