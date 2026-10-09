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

**A secret that moved between stores carries its age** (ADR 0263, D2242).
`bootstrap-providers --rehome` writes every value at the new store, so the new
store's `updatedAt` is the move -- beta's never-rotated trio would read as
fresh, the reassuring direction of a wrong premise. The rehome writes
`secret-ages-carried.json` beside the project's state with the SOURCE store's
times, and `judge` reads them while the value is still the one the move wrote:
**version 1 at the new store** (measured on the self-hosted store, 2026-10-09:
13 values created by the bootstrap, all version 1, `createdAt` = `updatedAt`).
A value replaced since the move has a later version and its own provider time
is the truth; a version the provider did not report is the third outcome
(D2276).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from agentic_postgres.infisical_client import SecretTimes

OK = "ok"
OVERDUE = "overdue"
UNKNOWN = "unknown"

#: Where an answer came from: the provider that holds the value now, or the
#: store it was copied from (ADR 0263).
PROVIDER = "provider"
CARRIED = "carried"

#: The file `bootstrap-providers --rehome` writes beside `bootstrap-state.json`,
#: and its kind. A list of entries rather than a mapping by name: a secret's
#: name ends in `_password` or `_signing_key`, which the sensitive-key guard
#: refuses as a KEY (`config.assert_no_sensitive_keys`), and the file passes it.
CARRIED_AGES = "secret-ages-carried.json"
CARRIED_KIND = "secret_ages_carried"

#: The provider's clock and this host's may disagree by a little; an update
#: time further in the future than this is not an age.
CLOCK_TOLERANCE = timedelta(minutes=5)


class CarriedAgesError(ValueError):
    """The carried file is not one `--rehome` wrote. The message names why."""


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
    #: `provider` or `carried` once a time was read; None when none was.
    source: str | None = None


def declared(secrets: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """The secrets that declare an age, in contract order."""
    return [secret for secret in secrets if "max_age_days" in secret]


def rendered_time(value: Any) -> str | None:
    """A provider time re-rendered by this program, or None (ADR 0159).

    What the carried file holds: the source store's string never travels, only
    what `datetime` made of it -- so a value that is not a zoned timestamp is
    recorded as absent rather than copied.
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.isoformat()


def carried_document(
    *,
    project_key: str,
    rehomed_at: str,
    source_api_url: str,
    source_project_id: str,
    times: dict[str, SecretTimes],
    previous: dict[str, SecretTimes] | None = None,
) -> dict[str, Any]:
    """The carried file's content: per secret name, the SOURCE store's times.

    A second move keeps the first one's answer (`previous`): the store the
    value came from the second time had itself only the first move's date.
    """
    entries = []
    for name in sorted(times):
        chosen = (previous or {}).get(name) or times[name]
        entries.append(
            {
                "name": name,
                "created_at": rendered_time(chosen.created_at),
                "updated_at": rendered_time(chosen.updated_at),
                "version": chosen.version
                if isinstance(chosen.version, int) and not isinstance(chosen.version, bool)
                else None,
            }
        )
    return {
        "kind": CARRIED_KIND,
        "schema_version": 1,
        "project_key": project_key,
        "rehomed_at": rehomed_at,
        "source": {"api_url": source_api_url, "project_id": source_project_id},
        "entries": entries,
    }


def parse_carried(document: Any, *, project_key: str) -> dict[str, SecretTimes]:
    """Validate a carried file and return its times by secret name.

    Raises `CarriedAgesError` naming what is wrong; a caller reports it as the
    third outcome rather than reading no file (ADR 0195).
    """
    from agentic_postgres.config import ManifestError, assert_no_sensitive_keys

    if not isinstance(document, dict) or document.get("kind") != CARRIED_KIND:
        raise CarriedAgesError(f"{CARRIED_AGES} is not a {CARRIED_KIND} document")
    if document.get("schema_version") != 1:
        raise CarriedAgesError(f"{CARRIED_AGES} has an unknown schema_version")
    if document.get("project_key") != project_key:
        raise CarriedAgesError(
            f"{CARRIED_AGES} records {document.get('project_key')!r}, not {project_key!r}"
        )
    try:
        assert_no_sensitive_keys(document)
    except ManifestError as problem:
        raise CarriedAgesError(str(problem)) from None
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise CarriedAgesError(f"{CARRIED_AGES} has no entries list")
    times: dict[str, SecretTimes] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise CarriedAgesError(f"{CARRIED_AGES} has an entry with no name")
        if set(entry) != {"name", "created_at", "updated_at", "version"}:
            raise CarriedAgesError(f"{CARRIED_AGES}: {entry['name']} has unexpected members")
        if entry["name"] in times:
            raise CarriedAgesError(f"{CARRIED_AGES} names {entry['name']} twice")
        version = entry["version"]
        times[entry["name"]] = SecretTimes(
            version=version if isinstance(version, int) and not isinstance(version, bool) else None,
            created_at=rendered_time(entry["created_at"]),
            updated_at=rendered_time(entry["updated_at"]),
        )
    return times


def load_carried(path: Path, *, project_key: str) -> dict[str, SecretTimes] | None:
    """The carried times, None when the file is absent; raises when it is not readable.

    "Cannot look" is not "absent" (ADR 0195): a directory this user may not
    enter raises from `exists()` itself, and that is reported, never read as a
    project that never moved.
    """
    try:
        if not path.exists():
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as problem:
        raise CarriedAgesError(f"{path} could not be read: {problem}") from None
    return parse_carried(document, project_key=project_key)


def judge(
    name: str,
    max_age_days: int,
    times: SecretTimes,
    *,
    now: datetime,
    carried: SecretTimes | None = None,
) -> Age:
    """One secret's outcome from what the provider said about it.

    With `carried` (the secret moved stores, ADR 0263): the provider's own
    times while its version is 1 -- the value the move wrote -- are the move's,
    so the carried ones answer; a later version is a replacement since the move
    and the provider answers; no version is the third outcome, because which
    of the two is the age cannot be told (D2276).
    """
    source = PROVIDER
    if carried is not None:
        if times.version is None:
            return Age(
                name,
                max_age_days,
                UNKNOWN,
                "the secret moved stores and the provider returned no version, so whether "
                "it was replaced since the move cannot be told",
            )
        if times.version == 1:
            times = carried
            source = CARRIED
    whose = "the provider's" if source == PROVIDER else "the carried"
    if times.updated_at is None:
        return Age(name, max_age_days, UNKNOWN, f"{whose} record holds no update time")
    try:
        updated = datetime.fromisoformat(times.updated_at)
    except ValueError:
        return Age(name, max_age_days, UNKNOWN, f"{whose} update time is not a timestamp")
    if updated.tzinfo is None:
        return Age(name, max_age_days, UNKNOWN, f"{whose} update time has no timezone")
    if updated > now + CLOCK_TOLERANCE:
        return Age(
            name,
            max_age_days,
            UNKNOWN,
            f"{whose} update time is in the future",
            updated_at=updated.isoformat(),
            version=times.version,
            source=source,
        )
    age_days = max(0, (now - updated).days)
    outcome = OVERDUE if age_days > max_age_days else OK
    if source == PROVIDER:
        reason = f"{age_days} days since the provider's last update, declared {max_age_days}"
    else:
        reason = (
            f"{age_days} days since the last update before the secret store moved "
            f"(carried), declared {max_age_days}"
        )
    return Age(
        name,
        max_age_days,
        outcome,
        reason,
        updated_at=updated.isoformat(),
        age_days=age_days,
        version=times.version,
        source=source,
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
