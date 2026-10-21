"""Session 40's customer proofs: the managed project's life and doors re-earned.

The claims `lifecycle_reearned_live` (LIFE-LIVE-004) and
`endpoints_reearned_live` (EP-LIVE-004), D2415, D2442. Run from the
workstation, never the host, AFTER the lifecycle (Run 10 step 1):
`s40-lifecycle.py` drove a NEW slot, `slot4-prod`, through `/v1` with the
product's own commands -- created, claimed, its two customer credentials set,
both public names reached, the superuser and the slot's platform roles refused
at both doors, the app role rotated, slept (both names refused), woken, resized
twice, exported twice, deleted, and a second creation refused -- while it
probed the slot's own app route and pool name every 2 s (D2444), and wrote
`APG_LIFECYCLE_RECORD_FILE` (0600). Never a password, a token or a URL that
authorises anything.

**These proofs read that record and ask the deployment again**, through the
control project's `routes.control` as the probe owner -- the fixtures,
`Recorder` and the read-back are Session 38's module's, whose own proofs, and
Session 39's, re-run against the same record (D2442: the same eleven
operations, in the same order). Every request goes to `routes.control`
(`_only`). **None of these nine proofs has ever executed.**
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

from agentic_postgres import slot

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment(
        "APG_CONTROL_OUTPUTS", "APG_CONTROL_PROBE_FILE", "APG_LIFECYCLE_RECORD_FILE"
    ),
]

DECIDED = "decided by its admission reading"

#: What Session 40's lifecycle ran, in creation order (s40-lifecycle.py): Session
#: 39's eleven exactly (D2442).
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

#: The intervals D2444 reads, and the ones a customer is told a window about.
PROBED = ("sleep", "wake", "resize_standard", "resize_large")


@pytest.fixture(scope="module")
def record40(record: dict[str, Any]) -> dict[str, Any]:
    """Session 40's record, Session 41's third re-earning (D2518) or Session
    42's fourth (D2581): a NEW slot every time -- a slot's key, never the kept
    `slot3-prod`."""
    assert record["session"] in (40, 41, 42, 43, 44), (
        f"a Session {record['session']} record, not one of Sessions 40-44's"
    )
    key = str(record.get("project_key"))
    assert slot.SLOT_KEY.fullmatch(key) and key != "slot3-prod", key
    assert isinstance(record.get("doors"), dict), "the record names no doors"
    return record


# ---------------------------------------------------------------------------
# LIFE-LIVE-004
# ---------------------------------------------------------------------------


def test_every_accepted_type_ran_on_the_slot(
    recorder: Recorder, endpoint: str, owner: str, record40: dict[str, Any]
) -> None:
    """The eleven operations the record names read back through `/v1` in
    creation order, as the lifecycle ran -- each `succeeded` but the resizes,
    which ended as their admission readings imply (ADR 0270) -- each on the
    record's project and agreeing with what the record kept, each a member's
    (`origin`, D2480); the three rotations name their roles and never a
    verifier; no read hands a download URL again."""
    rows = _read_back(recorder, endpoint, owner, record40)
    observed = [(row["type"], row["status"]) for row in rows]
    expected = [
        (kind, _implied_status(row) if status == DECIDED else status)
        for (kind, status), row in zip(LIFECYCLE, rows, strict=False)
    ]
    assert observed == expected and len(rows) == len(LIFECYCLE), observed
    kept = {operation["id"]: operation for operation in record40["operations"]}
    for row in rows:
        assert row["project_key"] == record40["project_key"], row
        assert row.get("origin") == "member", row
        assert (row["status"], row.get("error_code")) == (
            kept[row["id"]]["status"], kept[row["id"]]["error_code"],
        ), row["id"]  # fmt: skip
        assert "download_url" not in row, f"{row['id']} handed its URL again"
    rotations = [row for row in rows if row["type"] == "credential.rotate"]
    assert [(row.get("result") or {}).get("role") for row in rotations] == list(ROTATED)
    assert all("verifier" not in (row.get("result") or {}) for row in rotations)
    _only(recorder, endpoint)


def test_the_resizes_followed_the_admission_reading(
    recorder: Recorder, endpoint: str, owner: str, record40: dict[str, Any]
) -> None:
    """ADR 0270: each resize's outcome is what its OWN reading implies -- the
    reading read back through `/v1`, the instrument's judgement agreeing -- and
    the profile the customer read after the large one is the one it left."""
    rows = [row for row in _read_back(recorder, endpoint, owner, record40)
            if row["type"] == "project.resize"]  # fmt: skip
    assert len(rows) == 2, rows
    for row, label in zip(rows, ("resize_standard", "resize_large"), strict=True):
        implied = _implied_status(row)
        assert row["status"] == implied, row
        judged = record40["observations"][f"{label}_admission"]
        assert judged["decided"] == judged["implied"], judged
        assert judged["implied"] == ("admitted" if implied == "succeeded" else "refused"), judged
    wanted = "large" if rows[1]["status"] == "succeeded" else "standard"
    assert record40["observations"]["profile_after_large_resize"] == wanted
    _only(recorder, endpoint)


def test_the_export_holds_the_three_customer_schemas(
    recorder: Recorder, endpoint: str, owner: str, record40: dict[str, Any]
) -> None:
    """D2333: the archive lists exactly `api`, `app` and `public` and names no
    `app_private`; its SHA-256 is one the operations recorded."""
    schemas = record40["observations"]["archive_schemas"]
    assert schemas == {"pg_restore": 0, "schemas": ["api", "app", "public"], "app_private": False}
    exported = record40["observations"]["export"]
    hashes = [(row.get("result") or {}).get("sha256")
              for row in _read_back(recorder, endpoint, owner, record40)
              if row["type"] == "project.export"]  # fmt: skip
    assert exported["sha256"] in hashes, (exported["sha256"], hashes)
    _only(recorder, endpoint)


def test_the_second_creation_was_refused_without_a_row(
    recorder: Recorder,
    endpoint: str,
    owner: str,
    probe: dict[str, Any],
    record40: dict[str, Any],
) -> None:
    """D2145, D2160: the lifecycle's second creation exited 5 on
    `capacity_exhausted` with the organisation's creations unchanged; asked again
    now, a creation is refused `capacity_exhausted` (`no_slot`) -- slot4 is
    consumed, slot3 allocated -- and the creations made during the record's own
    run are exactly the one it names."""
    second = record40["observations"]["second_create"]
    assert (second["exit"], second["no_slot"]) == (5, True), second
    assert second["creations_before"] == second["creations_after"], second
    # The organisation the lifecycle RAN in (D2550): the probe's for Session
    # 40's record, Session 41's own for its (the probe's answers
    # `plan_limit_reached`, ADR 0274).
    organization = record40["organization_id"]
    status, body = recorder.json("POST", f"{endpoint}/projects", {
        "organization": organization, "name": "Lifecycle s40 again", "profile": "small",
        "admin_username": "again.admin", "handoff_sha256": "0" * 64,
    }, owner)  # fmt: skip
    assert (status, body.get("error"), body.get("reason")) == (
        409, "capacity_exhausted", "no_slot",
    ), (status, body)  # fmt: skip
    status, listed = recorder.json(
        "GET", f"{endpoint}/operations?organization={organization}", None, owner
    )
    assert status == 200, status
    start, end = (datetime.fromisoformat(record40[k]) for k in ("started_at", "finished_at"))
    during = [row["id"] for row in listed["operations"] if row["type"] == "project.create"
              and start <= datetime.fromisoformat(row["created_at"]) <= end]  # fmt: skip
    recorded = [o["id"] for o in record40["operations"] if o["type"] == "project.create"]
    assert during == recorded and len(during) == 1, (during, recorded)
    _only(recorder, endpoint)


def test_the_slots_own_route_was_probed_through_each_resize(record40: dict[str, Any]) -> None:
    """D2444: the slot's own app route and its pool name were sampled every 2 s
    from the credentials through the deletion, and every one of sleep, wake and
    the two resizes was COVERED by both -- a sample before its start and one
    after its end, read when the probes stopped (D2482). The control that the
    probes can see an outage at all: during the sleep both of them failed."""
    observations = record40["observations"]
    probes = observations["probes"]
    for name in ("route", "pool"):
        assert probes[name]["samples"] >= 30, probes
    for label in PROBED:
        reading = observations[f"{label}_probe"]
        assert reading["interval_seconds"] > 0, (label, reading)
        for name in ("route", "pool"):
            assert reading[name]["covered"] is True, (label, name, reading)
            assert reading[name]["samples"] > 0, (label, name, reading)
    asleep = observations["sleep_probe"]
    assert asleep["route"]["failed"] > 0 and asleep["pool"]["failed"] > 0, asleep


# ---------------------------------------------------------------------------
# EP-LIVE-004
# ---------------------------------------------------------------------------


def test_the_slot_was_reached_through_both_names(
    recorder: Recorder, endpoint: str, owner: str, record40: dict[str, Any]
) -> None:
    """The CLI wrote both password files 0600 in a 0700 directory, and `endpoint
    connect` reached the pooled name as `customer_app` and the direct name as
    `customer_admin` -- the roles the doors recorded, every certificate verified.
    Asked now, the deleted slot has no doors: its connections are `not_found`."""
    observations = record40["observations"]
    credentials = observations["credentials"]
    assert credentials["modes"] == {"app": "0o600", "admin": "0o600"}, credentials
    assert credentials["directory_mode"] == "0o700", credentials
    doors = record40["doors"]
    reached = observations["connect"]
    assert (reached["app"]["exit"], reached["app"]["user"]) == (0, doors["pooled"]["user"])
    assert (reached["admin"]["exit"], reached["admin"]["user"]) == (0, doors["direct"]["user"])
    status, body = recorder.json(
        "GET", f"{endpoint}/projects/{record40['project_key']}/connections", None, owner
    )
    assert (status, body.get("error")) == (404, "not_found"), (status, body)
    _only(recorder, endpoint)


def test_a_rotation_refused_the_old_password(record40: dict[str, Any]) -> None:
    """EP-CRED-001 on the re-earning slot: after the app role's rotation its OLD
    password was refused at the pooled name and the new one admitted as the
    door's own role."""
    rotation = record40["observations"]["rotation"]
    assert rotation["old_exit"] != 0 and rotation["new_exit"] == 0, rotation
    assert rotation["new_user"] == record40["doors"]["pooled"]["user"], rotation


def test_a_sleeping_slot_refused_both_names(record40: dict[str, Any]) -> None:
    """D2336: while the project slept every sample of its address was the
    edge's 404 and BOTH public names refused the login."""
    observations = record40["observations"]
    asleep = observations["asleep_samples"]
    assert set(asleep) == {"404"} and asleep["404"] >= 30, asleep
    refused = observations["asleep_connect"]
    assert set(refused) == {"app", "admin"} and all(code != 0 for code in refused.values()), refused


def test_no_platform_role_passed_either_door(record40: dict[str, Any]) -> None:
    """ADR 0269 item 3: the superuser and the slot's three platform roles --
    derived by the instrument with the product's `naming`, never typed -- were
    each refused at BOTH names with the door's own password, so a refusal is the
    door's userlist and not a wrong password alone; the door's own role, with
    the same file, was admitted (the instrument stops otherwise)."""
    platform = record40["observations"]["platform_roles"]
    assert platform["roles"] == 4, platform
    for door in ("pooled", "direct"):
        exits = platform["exits"][door]
        strangers = {user: code for user, code in exits.items() if user.startswith("platform:")}
        assert len(strangers) == 4 and all(code != 0 for code in strangers.values()), (door, exits)
        assert exits[record40["doors"][door]["user"]] == 0, (door, exits)
