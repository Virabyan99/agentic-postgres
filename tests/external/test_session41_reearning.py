"""Session 41's customer proofs: the third re-earning, the plans, usage, idle sleep, notifications.

The claims `lifecycle_third_trial_live` (LIFE-LIVE-005), `plans_live`
(PLAN-LIVE-001), `usage_live` (USE-LIVE-001), `idle_sleep_live` (USE-LIVE-002)
and `notifications_live` (USE-LIVE-003); D2518, ADR 0274-0276. Run from the
workstation, never the host, with no SSH, AFTER the lifecycle (Run 11 step 1):
`s41-lifecycle.py` read both plans, asked Premium's interest twice, had the probe
organisation -- which holds `slot3-prod` -- refused `plan_limit_reached` while a
slot was ready, made a NEW organisation and drove a NEW slot, `slot5-prod`,
through Sessions 38-40's eleven operations in it; set the slot's idle sleep to 15
minutes with its probes paused and waited for the reconciler's own sleep; read
the slot's and the organisation's usage and the organisation's notifications;
deleted the slot and had a second creation refused `capacity_exhausted`; and
wrote `APG_LIFECYCLE_RECORD_FILE` (0600). Never a password, a token or a URL that
authorises anything.

**These proofs read that record and ask the deployment again**, through the
control project's `routes.control` as the probe owner -- the fixtures,
`Recorder` and the read-back are Session 38's module's (whose proofs, and
Sessions 39's and 40's, re-run against the same record: the eleven operations
are kept in `operations`, the idle sleep and its wake in `idle_operations`).
**None of these proofs has ever executed.**
"""

# ruff: noqa: F811 -- the imported names are pytest fixtures.

from __future__ import annotations

import ast
from collections import Counter
from datetime import datetime
from pathlib import Path
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

#: Sessions 38-40's eleven, in creation order (D2442): the record keeps them alone
#: in `operations`.
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

#: The intervals the slot's own probes read (D2444, D2500).
PROBED = ("sleep", "wake", "resize_standard", "resize_large")

#: ADR 0276: the setting's minutes, and the bound the instrument waited within --
#: the minutes, two sample intervals and two minutes for the reconciler.
IDLE_MINUTES = 15
IDLE_BOUND_SECONDS = IDLE_MINUTES * 60 + 2 * 300 + 120

#: The kinds a finished operation's notification takes (0008's template).
KIND_OF_ORIGIN = {"member": "operation_succeeded", "idle": "idle_sleep", "expiry": "branch_expired"}


def instant(text: str) -> datetime:
    return datetime.fromisoformat(str(text).replace("Z", "+00:00"))


@pytest.fixture(scope="module")
def record41(record: dict[str, Any]) -> dict[str, Any]:
    """Session 41's record, or Session 42's fourth re-earning (D2581): a NEW
    slot's key -- never the kept `slot3-prod` -- in the lifecycle's OWN
    organisation, not the probe's (step 1)."""
    assert record["session"] in (41, 42, 43, 44), (
        f"a Session {record['session']} record, not 41's, 42's, 43's or 44's"
    )
    key = str(record.get("project_key"))
    assert slot.SLOT_KEY.fullmatch(key) and key != "slot3-prod", key
    assert record.get("organization_id") and record.get("probe_organization_id"), record
    assert record["organization_id"] != record["probe_organization_id"], (
        "the lifecycle ran in the probe's organisation, not one of its own"
    )
    assert isinstance(record.get("doors"), dict), "the record names no doors"
    return record


def _operation(recorder: Recorder, endpoint: str, owner: str, operation: str) -> dict[str, Any]:
    status, row = recorder.json("GET", f"{endpoint}/operations/{operation}", None, owner)
    assert status == 200, (operation, status, row.get("error"))
    return row


# ---------------------------------------------------------------------------
# LIFE-LIVE-005
# ---------------------------------------------------------------------------


def test_every_accepted_type_ran_on_the_slot(
    recorder: Recorder, endpoint: str, owner: str, record41: dict[str, Any]
) -> None:
    """The eleven operations the record keeps read back through `/v1` in
    creation order -- each `succeeded` but the resizes, which ended as their
    admission readings imply (ADR 0270) -- each on the record's project, a
    member's, agreeing with what the record kept; no read hands a download URL
    again."""
    rows = _read_back(recorder, endpoint, owner, record41)
    observed = [(row["type"], row["status"]) for row in rows]
    expected = [
        (kind, _implied_status(row) if status == DECIDED else status)
        for (kind, status), row in zip(LIFECYCLE, rows, strict=False)
    ]
    assert observed == expected and len(rows) == len(LIFECYCLE), observed
    kept = {operation["id"]: operation for operation in record41["operations"]}
    for row in rows:
        assert row["project_key"] == record41["project_key"], row
        assert row.get("origin") == "member", row
        assert row["organization_id"] == record41["organization_id"], row
        assert (row["status"], row.get("error_code")) == (
            kept[row["id"]]["status"], kept[row["id"]]["error_code"],
        ), row["id"]  # fmt: skip
        assert "download_url" not in row, f"{row['id']} handed its URL again"
    _only(recorder, endpoint)


def test_the_resizes_followed_the_admission_reading(
    recorder: Recorder, endpoint: str, owner: str, record41: dict[str, Any]
) -> None:
    """ADR 0270: each resize's outcome is what its OWN reading implies, read
    back through `/v1`, the instrument's judgement agreeing; the profile read
    after the large one is the one it left."""
    rows = [row for row in _read_back(recorder, endpoint, owner, record41)
            if row["type"] == "project.resize"]  # fmt: skip
    assert len(rows) == 2, rows
    for row, label in zip(rows, ("resize_standard", "resize_large"), strict=True):
        implied = _implied_status(row)
        assert row["status"] == implied, row
        judged = record41["observations"][f"{label}_admission"]
        assert judged["decided"] == judged["implied"], judged
        assert judged["implied"] == ("admitted" if implied == "succeeded" else "refused"), judged
    wanted = "large" if rows[1]["status"] == "succeeded" else "standard"
    assert record41["observations"]["profile_after_large_resize"] == wanted
    _only(recorder, endpoint)


def test_the_export_holds_the_three_customer_schemas(
    recorder: Recorder, endpoint: str, owner: str, record41: dict[str, Any]
) -> None:
    """D2333: the archive lists exactly `api`, `app` and `public` and names no
    `app_private`; its SHA-256 is one the operations recorded; the second read
    of the finished export handed no URL."""
    schemas = record41["observations"]["archive_schemas"]
    assert schemas == {"pg_restore": 0, "schemas": ["api", "app", "public"], "app_private": False}
    exported = record41["observations"]["export"]
    assert exported["mode"] == "0o600" and exported["second_read_handed_a_url"] is False, exported
    hashes = [(row.get("result") or {}).get("sha256")
              for row in _read_back(recorder, endpoint, owner, record41)
              if row["type"] == "project.export"]  # fmt: skip
    assert exported["sha256"] in hashes, (exported["sha256"], hashes)
    _only(recorder, endpoint)


def test_both_routes_were_probed_through_every_window(record41: dict[str, Any]) -> None:
    """D2444, D2500: the slot's own app route AND its pooled name were sampled
    every 2 s from the credentials through the deletion -- the pool's thread
    surviving any sample that could not be taken -- and each of sleep, wake and
    the two resizes was COVERED by both, a sample before its start and one
    after its end. The control that the probes see an outage at all: during the
    sleep both failed."""
    observations = record41["observations"]
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
    # The pool was sampled AFTER the idle step's pause too: the thread lived on.
    trace = probes["pool"]["trace"]
    resumed = instant(observations["idle"]["resumed_at"]).timestamp()
    first = instant(probes["pool"]["first"]).timestamp()
    assert any(first + sample[0] > resumed for sample in trace), (
        "no pool sample after the idle step"
    )


def test_the_second_creation_after_the_deletion_was_refused_by_capacity(
    recorder: Recorder, endpoint: str, owner: str, record41: dict[str, Any]
) -> None:
    """ADR 0274 sentence 4: the lifecycle's OWN organisation -- within its plan
    once the slot was deleted, a deleted project held against nothing -- asked
    for a second project and was refused `capacity_exhausted` (`no_slot`), the
    capacity reader's, with its creations unchanged; asked again now, the same
    answer, and the creations made in the record's window are exactly the one
    it names."""
    second = record41["observations"]["second_create"]
    assert (second["exit"], second["no_slot"]) == (5, True), second
    assert second["creations_before"] == second["creations_after"], second
    organization = record41["organization_id"]
    status, body = recorder.json("POST", f"{endpoint}/projects", {
        "organization": organization, "name": "Lifecycle s41 again", "profile": "small",
        "admin_username": "again.admin", "handoff_sha256": "0" * 64,
    }, owner)  # fmt: skip
    assert (status, body.get("error"), body.get("reason")) == (
        409, "capacity_exhausted", "no_slot",
    ), (status, body)  # fmt: skip
    status, listed = recorder.json(
        "GET", f"{endpoint}/operations?organization={organization}", None, owner
    )
    assert status == 200, status
    start = instant(record41.get("window_started_at") or record41["started_at"])
    end = instant(record41["finished_at"])
    during = [row["id"] for row in listed["operations"] if row["type"] == "project.create"
              and start <= instant(row["created_at"]) <= end]  # fmt: skip
    recorded = [o["id"] for o in record41["operations"] if o["type"] == "project.create"]
    assert during == recorded and len(during) == 1, (during, recorded)
    _only(recorder, endpoint)


# ---------------------------------------------------------------------------
# PLAN-LIVE-001
# ---------------------------------------------------------------------------


def test_the_plans_were_read(recorder: Recorder, endpoint: str, owner: str,
                             record41: dict[str, Any]) -> None:  # fmt: skip
    """ADR 0274: both plans were read through `bin/plan.sh list` -- Free
    `active`, Premium `unavailable_during_beta` -- with Free's enforced
    entitlements (one project, one branch) enforced and its shown ones not; asked
    now, `/v1/plans` serves the same two."""
    plans = {p["plan"]: p for p in record41["observations"]["plans"]["plans"]}
    assert (plans["free"]["status"], plans["premium"]["status"]) == (
        "active", "unavailable_during_beta",
    ), plans  # fmt: skip
    free = plans["free"]["entitlements"]
    assert free["projects_active"] == {"value": 1, "enforced": True}, free
    assert free["branches_total"] == {"value": 1, "enforced": True}, free
    assert (
        free["storage_gb"]["enforced"] is False and free["agent_calls_per_day"]["enforced"] is False
    )
    status, served = recorder.json("GET", f"{endpoint}/plans", None, owner)
    assert status == 200, status
    assert [(p["plan"], p["status"]) for p in served["plans"]] == [
        ("free", "active"), ("premium", "unavailable_during_beta"),
    ], served  # fmt: skip
    _only(recorder, endpoint)


def test_the_second_project_was_refused_by_the_plan_while_a_slot_was_ready(
    recorder: Recorder, endpoint: str, owner: str, record41: dict[str, Any]
) -> None:
    """ADR 0274, D2521: the probe organisation -- holding `slot3-prod` against
    Free's one -- asked for a second project and was refused
    `plan_limit_reached`, the entitlement's reader, NOT `capacity_exhausted`,
    with its creations and the CLI's handoff files unchanged; a slot WAS ready:
    the very next creation, in the lifecycle's organisation, was accepted and
    succeeded into `slot5-prod` after it. Asked again now, the plan refuses."""
    refusal = record41["observations"]["plan_refusal"]
    assert refusal["organization"] == record41["probe_organization_id"], refusal
    assert (refusal["exit"], refusal["plan_limit_reached"], refusal["capacity_exhausted"]) == (
        5, True, False,
    ), refusal  # fmt: skip
    assert refusal["creations_before"] == refusal["creations_after"], refusal
    assert refusal["handoffs_before"] == refusal["handoffs_after"], refusal
    (create,) = [o for o in record41["operations"] if o["type"] == "project.create"]
    read = _operation(recorder, endpoint, owner, create["id"])
    assert read["status"] == "succeeded" and read["project_key"] == record41["project_key"], read
    assert instant(refusal["at"]) <= instant(read["created_at"]), (
        refusal["at"],
        read["created_at"],
    )
    status, body = recorder.json("POST", f"{endpoint}/projects", {
        "organization": record41["probe_organization_id"], "name": "Plan s41 again",
        "profile": "small", "admin_username": "again.admin", "handoff_sha256": "0" * 64,
    }, owner)  # fmt: skip
    assert (status, body.get("error")) == (409, "plan_limit_reached"), (status, body)
    _only(recorder, endpoint)


def test_interest_was_recorded_once(
    recorder: Recorder, endpoint: str, owner: str, record41: dict[str, Any]
) -> None:
    """ADR 0274: *Notify me* for Premium, asked twice, recorded once -- the
    second answer `recorded: false`; asked now, the probe organisation's plan
    names Premium among the plans it asked about, and it is still on Free."""
    interest = record41["observations"]["interest"]
    assert interest["recorded"][1] is False and "premium" in interest["interest"], interest
    status, plan = recorder.json(
        "GET", f"{endpoint}/organizations/{record41['probe_organization_id']}/plan", None, owner
    )
    assert status == 200, status
    assert (plan["plan"], plan["interest"]) == ("free", ["premium"]), plan
    _only(recorder, endpoint)


# ---------------------------------------------------------------------------
# USE-LIVE-001
# ---------------------------------------------------------------------------


def test_the_slots_usage_was_read(record41: dict[str, Any]) -> None:
    """ADR 0275: while the slot lived its usage was READ -- samples recorded,
    no more than expected; its database's size read; its requests answered
    below 400 counted (they rose while it was used); and every figure either
    read or counted as not read in so many samples, never a silent zero."""
    usage = record41["observations"]["usage"]["project"]
    assert usage["exit"] == 0, usage
    document = usage["document"]
    assert document["status"] == "read" and document["project_key"] == record41["project_key"]
    samples = document["samples"]
    assert 0 < samples["present"] <= samples["expected"] + 1, samples
    figures = document["figures"]
    assert figures["database_bytes"]["latest"] is not None, figures
    for name, figure in figures.items():
        assert figure["latest"] is not None or figure["unread_samples"] > 0, (name, figure)
    assert document["requests"] is not None and document["requests"]["increase"] > 0, document


def test_the_organizations_usage_holds_the_slot(record41: dict[str, Any]) -> None:
    """The organisation's usage lists the slot -- and only the slot: the
    lifecycle's organisation held no other project."""
    usage = record41["observations"]["usage"]["organization"]
    assert usage["exit"] == 0, usage
    keys = [p["project_key"] for p in usage["document"]["projects"]]
    assert keys == [record41["project_key"]], keys


# ---------------------------------------------------------------------------
# USE-LIVE-002
# ---------------------------------------------------------------------------


def test_the_idle_slot_was_put_to_sleep_by_the_reconciler(
    recorder: Recorder, endpoint: str, owner: str, record41: dict[str, Any]
) -> None:
    """ADR 0276: with the minutes set to 15 and the slot's probes stopped, the
    reconciler asked and the control set inserted ONE `project.sleep` with
    `origin = idle` -- never sent by the instrument -- on behalf of the member who
    set the minutes (the requester of every member operation), no sooner than
    the window allows and within the bound; it succeeded, and the slot was then
    woken by a member. Read back through `/v1` now. The setting's answer said
    what sleeping does to the backups (D2534)."""
    idle = record41["observations"]["idle"]
    assert idle["minutes"] == IDLE_MINUTES and idle["bound_seconds"] == IDLE_BOUND_SECONDS, idle
    assert "its backups stop" in idle["note"], idle["note"]
    requested = idle["requested"]
    seconds = requested["seconds_from_setting"]
    assert IDLE_MINUTES * 60 - 60 <= seconds <= IDLE_BOUND_SECONDS, seconds
    members = {o["requested_by"] for o in record41["operations"]}
    assert len(members) == 1, members
    kinds = [(o["type"], o["origin"]) for o in record41["idle_operations"]]
    assert kinds == [("project.sleep", "idle"), ("project.wake", "member")], kinds
    read = _operation(recorder, endpoint, owner, requested["operation"])
    assert (read["type"], read["origin"], read["status"]) == (
        "project.sleep", "idle", "succeeded",
    ), read  # fmt: skip
    assert read["requested_by"] in members and read["project_key"] == record41["project_key"], read
    assert requested["operation"] not in {o["id"] for o in record41["operations"]}
    _only(recorder, endpoint)


def test_the_idle_sleep_closed_both_doors(record41: dict[str, Any]) -> None:
    """D2336 under an idle sleep: while the slot slept by idleness every sample
    of its address was the edge's 404 and BOTH public names refused the login."""
    observations = record41["observations"]
    asleep = observations["idle"]["asleep_samples"]
    assert set(asleep) == {"404"} and asleep["404"] >= 30, asleep
    refused = observations["idle_asleep_connect"]
    assert set(refused) == {"app", "admin"} and all(code != 0 for code in refused.values()), refused


# ---------------------------------------------------------------------------
# USE-LIVE-003
# ---------------------------------------------------------------------------


def _expected_notifications(record41: dict[str, Any]) -> Counter:
    expected: Counter = Counter()
    for row in [*record41["operations"], *record41["idle_operations"]]:
        origin = row.get("origin") or "member"
        kind = KIND_OF_ORIGIN.get(origin, "operation_succeeded")
        if row["status"] == "failed":
            kind = "operation_failed"
        expected[(kind, f"{row['type']} on {record41['project_key']} {row['status']}")] += 1
    return expected


def test_every_finished_operation_was_notified(
    recorder: Recorder, endpoint: str, owner: str, record41: dict[str, Any]
) -> None:
    """ADR 0275: every finished operation of the slot -- the eleven and the idle
    sleep and its wake -- has exactly ONE notification, its kind the outcome's
    (the idle sleep's `idle_sleep`, naming its cause), its sentence the
    operation's type, project and status; the refused creations, which wrote no
    operation, wrote none. Listed after the deletion, and asked again now."""
    expected = _expected_notifications(record41)
    key = record41["project_key"]
    for listing in (record41["observations"]["notifications_after_delete"], None):
        if listing is None:
            status, served = recorder.json(
                "GET", f"{endpoint}/organizations/{record41['organization_id']}/notifications"
                "?limit=200", None, owner,
            )  # fmt: skip
            assert status == 200, status
            listing = served["notifications"]
        found: Counter = Counter()
        for notification in listing:
            if notification["project"] != key or notification["kind"] == "limit_approaching":
                continue
            prefix = " ".join(notification["text"].split(" ")[:4])
            found[(notification["kind"], prefix)] += 1
        assert found == expected, (found, expected)
    (idle,) = [n for n in record41["observations"]["notifications_after_delete"]
               if n["kind"] == "idle_sleep"]  # fmt: skip
    assert "idle" in idle["text"] and "backups" in idle["text"], idle
    _only(recorder, endpoint)


def test_no_notification_carries_a_secret(record41: dict[str, Any]) -> None:
    """ADR 0275: a notification is a fixed template -- never a result member, a
    URL or a caller value. No sentence of the lifecycle organisation's holds an
    address, an export's hash or size, an operation's id, or a door's host."""
    observations = record41["observations"]
    doors = record41["doors"]
    forbidden = {observations["export"]["sha256"], str(observations["export"]["size_bytes"]),
                 doors["pooled"]["host"], doors["direct"]["host"]}  # fmt: skip
    forbidden |= {o["id"] for o in [*record41["operations"], *record41["idle_operations"]]}
    for notification in observations["notifications_after_delete"]:
        text = notification["text"]
        assert "://" not in text and "http" not in text.lower(), text
        assert not [value for value in forbidden if value and value in text], text


def test_this_module_uses_no_ssh() -> None:
    """D2174's rule for a customer proof: nothing here reaches the host by any
    path but `routes.control`. Read from this file's own text and syntax: no SSH
    library, no `ssh` argv, no destination -- and no process door at all."""
    text = Path(__file__).read_text(encoding="utf-8")
    # Each needle split so this list never spells what it forbids (D2398).
    for needle in ("para" + "miko", '"s' + 'sh"', "ss" + "h_destination", "ss" + "h-agent"):
        assert needle not in text, needle
    tree = ast.parse(text)
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}  # fmt: skip
    assert "subprocess" not in imported, imported
