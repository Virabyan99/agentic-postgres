"""Session 39's customer proofs: a managed project's life re-trialed, with its doors.

The claim `lifecycle_retrial_live` (LIFE-LIVE-003, D2343). Run from the
workstation, never the host, AFTER the lifecycle (Run 11 step 1):
`s39-lifecycle.py` drove `slot2-prod` through `/v1` with the product's own
commands -- created, claimed, its two customer credentials set, both public
names reached and the app role rotated, slept (both names refused), woken,
resized twice, exported twice, deleted, and a second creation refused -- and
wrote `APG_LIFECYCLE_RECORD_FILE` (0600). Never a password, a token or a URL
that authorises anything.

**These proofs read that record and ask the deployment again**, through the
control project's `routes.control` as the probe owner -- the fixtures,
`Recorder` and the read-back are Session 38's module's (whose own six proofs
re-run against the same record, D2343). Every request goes to
`routes.control` (`_only`); the public names were reached by the instrument
through the product's `bin/endpoint.sh connect`, and are read here from its
record. **None of these six proofs has ever executed.**
"""

# ruff: noqa: F811 -- the imported names are pytest fixtures.

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from tests.external.test_session38_public_lifecycle import (  # noqa: F401 -- fixtures
    Recorder,
    _implied_status,
    _only,
    _read_back,
    control,
    endpoint,
    owner,
    probe,
    record,
    recorder,
)

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment(
        "APG_CONTROL_OUTPUTS", "APG_CONTROL_PROBE_FILE", "APG_LIFECYCLE_RECORD_FILE"
    ),
]

DECIDED = "decided by its admission reading"

#: What Session 39's lifecycle ran, in creation order (s39-lifecycle.py): the
#: creation, the two credentials and the app role's rotation, then Session 38's
#: seven.
LIFECYCLE = (
    ("project.create", "succeeded"),
    ("credential.rotate", "succeeded"),
    ("credential.rotate", "succeeded"),
    ("credential.rotate", "succeeded"),
    ("project.sleep", "succeeded"),
    ("project.wake", "succeeded"),
    ("project.resize", DECIDED),
    ("project.resize", DECIDED),
    ("project.export", "succeeded"),
    ("project.export", "succeeded"),
    ("project.delete", "succeeded"),
)
ROTATED = ("customer_app", "customer_admin", "customer_app")


@pytest.fixture(scope="module")
def record39(record: dict[str, Any]) -> dict[str, Any]:
    # D2442: Session 40's record has these members and these eleven operations
    # too, so 39's claim re-runs against the newest record, asserting all of it.
    assert record["session"] in (39, 40, 41, 42, 43, 44, 45, 46), (
        f"a Session {record['session']} record, not one of Sessions 39-46's"
    )
    assert isinstance(record.get("doors"), dict), "the record names no doors"
    return record


def test_every_accepted_type_ran_on_the_slot(
    recorder: Recorder, endpoint: str, owner: str, record39: dict[str, Any]
) -> None:
    """LIFE-LIVE-003: the eleven operations the record names read back through
    `/v1` in creation order, as the lifecycle ran -- every one of the seven
    accepted types on the slot, each `succeeded` but the resizes, which ended as
    their admission readings imply (ADR 0270) -- each on the record's project,
    agreeing with what the record kept; the three rotations name their roles
    and never a verifier; no read hands a download URL again."""
    rows = _read_back(recorder, endpoint, owner, record39)
    observed = [(row["type"], row["status"]) for row in rows]
    expected = [
        (kind, _implied_status(row) if status == DECIDED else status)
        for (kind, status), row in zip(LIFECYCLE, rows, strict=False)
    ]
    assert observed == expected and len(rows) == len(LIFECYCLE), observed
    kept = {operation["id"]: operation for operation in record39["operations"]}
    for row in rows:
        assert row["project_key"] == record39["project_key"], row
        assert (row["status"], row.get("error_code")) == (
            kept[row["id"]]["status"], kept[row["id"]]["error_code"],
        ), row["id"]  # fmt: skip
        assert "download_url" not in row, f"{row['id']} handed its URL again"
    rotations = [row for row in rows if row["type"] == "credential.rotate"]
    assert [(row.get("result") or {}).get("role") for row in rotations] == list(ROTATED)
    assert all("verifier" not in (row.get("result") or {}) for row in rotations)
    _only(recorder, endpoint)


def test_the_resizes_followed_the_admission_reading(
    recorder: Recorder, endpoint: str, owner: str, record39: dict[str, Any]
) -> None:
    """ADR 0270, D2362: each resize's outcome is what its OWN reading implies --
    the reading read back through `/v1` (`result.admission`), the instrument's
    judgement of it agreeing -- and the profile the customer read after the
    large one is the one that outcome left."""
    rows = [row for row in _read_back(recorder, endpoint, owner, record39)
            if row["type"] == "project.resize"]  # fmt: skip
    assert len(rows) == 2, rows
    for row, label in zip(rows, ("resize_standard", "resize_large"), strict=True):
        implied = _implied_status(row)
        assert row["status"] == implied, row
        judged = record39["observations"][f"{label}_admission"]
        assert judged["decided"] == judged["implied"], judged
        assert judged["implied"] == ("admitted" if implied == "succeeded" else "refused"), judged
    wanted = "large" if rows[1]["status"] == "succeeded" else "standard"
    assert record39["observations"]["profile_after_large_resize"] == wanted
    _only(recorder, endpoint)


def test_the_export_holds_the_three_customer_schemas(
    recorder: Recorder, endpoint: str, owner: str, record39: dict[str, Any]
) -> None:
    """D2333, ADR 0259 amended: the archive lists exactly `api`, `app` and
    `public` -- the customer's own tables live in `public` since Session 39 --
    and names no `app_private`; its SHA-256 is one the operations recorded."""
    schemas = record39["observations"]["archive_schemas"]
    assert schemas == {"pg_restore": 0, "schemas": ["api", "app", "public"], "app_private": False}
    exported = record39["observations"]["export"]
    hashes = [(row.get("result") or {}).get("sha256")
              for row in _read_back(recorder, endpoint, owner, record39)
              if row["type"] == "project.export"]  # fmt: skip
    assert exported["sha256"] in hashes, (exported["sha256"], hashes)
    _only(recorder, endpoint)


def test_the_slot_was_reached_through_both_names(
    recorder: Recorder, endpoint: str, owner: str, record39: dict[str, Any]
) -> None:
    """EP-CRED-001's live half on the re-trial slot: the CLI wrote both password
    files 0600 in a 0700 directory; `endpoint connect` reached the pooled name
    as `customer_app` and the direct name as `customer_admin` -- the roles the
    doors recorded; after the app role's rotation its OLD password was refused
    and the new one admitted. Asked now, the deleted slot has no doors: its
    connections are the one `not_found`."""
    observations = record39["observations"]
    credentials = observations["credentials"]
    assert credentials["modes"] == {"app": "0o600", "admin": "0o600"}, credentials
    assert credentials["directory_mode"] == "0o700", credentials
    doors = record39["doors"]
    reached = observations["connect"]
    assert (reached["app"]["exit"], reached["app"]["user"]) == (0, doors["pooled"]["user"])
    assert (reached["admin"]["exit"], reached["admin"]["user"]) == (0, doors["direct"]["user"])
    rotation = observations["rotation"]
    assert rotation["old_exit"] != 0 and rotation["new_exit"] == 0, rotation
    assert rotation["new_user"] == doors["pooled"]["user"], rotation
    status, body = recorder.json(
        "GET", f"{endpoint}/projects/{record39['project_key']}/connections", None, owner
    )
    assert (status, body.get("error")) == (404, "not_found"), (status, body)
    _only(recorder, endpoint)


def test_a_sleeping_slot_refused_both_names(record39: dict[str, Any]) -> None:
    """D2336: while the project slept every sample of its address was the
    edge's 404 and BOTH public names refused the login (psql's exit, never 0) --
    its poolers stopped, so the edge had no route for either name."""
    observations = record39["observations"]
    asleep = observations["asleep_samples"]
    assert set(asleep) == {"404"} and asleep["404"] >= 30, asleep
    refused = observations["asleep_connect"]
    assert set(refused) == {"app", "admin"} and all(code != 0 for code in refused.values()), refused


def test_the_second_creation_was_refused_without_a_row(
    recorder: Recorder,
    endpoint: str,
    owner: str,
    probe: dict[str, Any],
    record39: dict[str, Any],
) -> None:
    """D2145, D2160: the lifecycle's second creation exited 5 on
    `capacity_exhausted` with the organisation's creations unchanged; asked again
    now, a creation is refused `capacity_exhausted` (`no_slot`) -- slot2 is
    consumed, slot3 allocated -- and the organisation's creations made during the
    record's own run are exactly the one it names."""
    second = record39["observations"]["second_create"]
    assert (second["exit"], second["no_slot"]) == (5, True), second
    assert second["creations_before"] == second["creations_after"], second
    # The organisation the lifecycle RAN in (D2550): the probe's for Sessions
    # 39-40's records, Session 41's own for its (the probe's answers
    # `plan_limit_reached`, ADR 0274).
    organization = record39["organization_id"]
    status, body = recorder.json("POST", f"{endpoint}/projects", {
        "organization": organization, "name": "Lifecycle s39 again", "profile": "small",
        "admin_username": "again.admin", "handoff_sha256": "0" * 64,
    }, owner)  # fmt: skip
    assert (status, body.get("error"), body.get("reason")) == (
        409, "capacity_exhausted", "no_slot",
    ), (status, body)  # fmt: skip
    status, listed = recorder.json(
        "GET", f"{endpoint}/operations?organization={organization}", None, owner
    )
    assert status == 200, status
    start, end = (datetime.fromisoformat(record39[k]) for k in ("started_at", "finished_at"))
    during = [row["id"] for row in listed["operations"] if row["type"] == "project.create"
              and start <= datetime.fromisoformat(row["created_at"]) <= end]  # fmt: skip
    recorded = [o["id"] for o in record39["operations"] if o["type"] == "project.create"]
    assert during == recorded and len(during) == 1, (during, recorded)
    _only(recorder, endpoint)
