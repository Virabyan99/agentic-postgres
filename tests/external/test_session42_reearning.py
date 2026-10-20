"""Session 42's customer proofs: the fourth re-earning, idle sleep, notifications, insights.

The claims `lifecycle_fourth_trial_live` (LIFE-LIVE-006), `idle_sleep_retrial_live`
(USE-LIVE-004), `notifications_retrial_live` (USE-LIVE-005) and `insights_live`
(INS-LIVE-001); D2581, D2569, ADR 0276-0279. Run from the workstation, never the
host, with no SSH, AFTER the lifecycle (Run 11 step 1): `s42-lifecycle.py` drove
a NEW slot, `slot6-prod`, through Sessions 38-41's eleven operations in a NEW
organisation; ran a known workload as `customer_app` and read the slot's
insights and monitoring after two usage passes; set its idle sleep to 15
minutes with its probes paused; read usage and notifications; deleted it and
had a second creation refused `capacity_exhausted`; and wrote
`APG_LIFECYCLE_RECORD_FILE` (0600) -- **and every probe sample to
`<record>.samples.jsonl` as it was taken**, the file's bytes, sha256 and lines
sealed into the record (D2581: Session 41 lost four windows held in memory).

**These proofs read that record, the samples file it seals, and ask the
deployment again** through the control project's `routes.control` as the probe
owner -- Session 38's fixtures and read-back (whose proofs, and Sessions 39-41's,
re-run against the same record). **None of these proofs has ever executed.**
"""

# ruff: noqa: F811 -- the imported names are pytest fixtures.

from __future__ import annotations

import ast
import hashlib
import json
import os
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

from agentic_postgres import naming, slot
from app import signals

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.external,
    pytest.mark.requires_environment(
        "APG_CONTROL_OUTPUTS", "APG_CONTROL_PROBE_FILE", "APG_LIFECYCLE_RECORD_FILE"
    ),
]

DECIDED = "decided by its admission reading"

#: Sessions 38-41's eleven, in creation order (D2442): the record keeps them alone
#: in `operations`; an export refused and resumed past is in `failed_exports`.
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

#: ADR 0276: the setting's minutes and the bound the instrument waited within.
IDLE_MINUTES = 15
IDLE_BOUND_SECONDS = IDLE_MINUTES * 60 + 2 * 300 + 120

#: The kinds a finished operation's notification takes (0008's template).
KIND_OF_ORIGIN = {"member": "operation_succeeded", "idle": "idle_sleep", "expiry": "branch_expired"}

#: D2569: the workload's statement as PostgreSQL normalises it, and its calls.
NORMALISED = ("pg_class", "relname = $1")
WORKLOAD_CALLS = 200


def instant(text: str) -> datetime:
    return datetime.fromisoformat(str(text).replace("Z", "+00:00"))


@pytest.fixture(scope="module")
def record42(record: dict[str, Any]) -> dict[str, Any]:
    """Session 42's record: a NEW slot's key -- never the kept `slot3-prod` -- in
    the lifecycle's OWN organisation, with its samples sealed (D2581)."""
    assert record["session"] in (42, 43), f"a Session {record['session']} record, not 42's or 43's"
    key = str(record.get("project_key"))
    assert slot.SLOT_KEY.fullmatch(key) and key != "slot3-prod", key
    assert record.get("organization_id") and record.get("probe_organization_id"), record
    assert record["organization_id"] != record["probe_organization_id"], (
        "the lifecycle ran in the probe's organisation, not one of its own"
    )
    assert isinstance(record.get("doors"), dict), "the record names no doors"
    assert isinstance(record.get("samples"), dict), "the record seals no samples file (D2581)"
    return record


@pytest.fixture(scope="module")
def samples(record42: dict[str, Any]) -> list[dict[str, Any]]:
    """The samples file the record seals, read whole: the path the record names,
    else the record file's own sibling; its bytes and sha256 EQUAL to the seal --
    a file shortened, extended or rewritten since the stop is a failure."""
    sealed = record42["samples"]
    path = Path(str(sealed.get("file")))
    if not path.is_file():
        recorded = os.environ.get("APG_LIFECYCLE_RECORD_FILE", "")
        path = Path(recorded).with_suffix(".samples.jsonl")
    assert path.is_file(), f"no samples file at {sealed.get('file')} or beside the record"
    raw = path.read_bytes()
    assert (len(raw), hashlib.sha256(raw).hexdigest()) == (sealed["bytes"], sealed["sha256"]), (
        "the samples file is not the one the record sealed"
    )
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    assert len(rows) == sealed["lines"], (len(rows), sealed["lines"])
    return rows


def _operation(recorder: Recorder, endpoint: str, owner: str, operation: str) -> dict[str, Any]:
    status, row = recorder.json("GET", f"{endpoint}/operations/{operation}", None, owner)
    assert status == 200, (operation, status, row.get("error"))
    return row


# ---------------------------------------------------------------------------
# LIFE-LIVE-006
# ---------------------------------------------------------------------------


def test_every_accepted_type_ran_on_the_slot(
    recorder: Recorder, endpoint: str, owner: str, record42: dict[str, Any]
) -> None:
    """The eleven operations the record keeps read back through `/v1` in
    creation order -- each `succeeded` but the resizes, which ended as their
    admission readings imply (ADR 0270) -- each on the record's project, a
    member's, agreeing with what the record kept; no read hands a download URL
    again."""
    rows = _read_back(recorder, endpoint, owner, record42)
    observed = [(row["type"], row["status"]) for row in rows]
    expected = [
        (kind, _implied_status(row) if status == DECIDED else status)
        for (kind, status), row in zip(LIFECYCLE, rows, strict=False)
    ]
    assert observed == expected and len(rows) == len(LIFECYCLE), observed
    kept = {operation["id"]: operation for operation in record42["operations"]}
    for row in rows:
        assert row["project_key"] == record42["project_key"], row
        assert row.get("origin") == "member", row
        assert row["organization_id"] == record42["organization_id"], row
        assert (row["status"], row.get("error_code")) == (
            kept[row["id"]]["status"], kept[row["id"]]["error_code"],
        ), row["id"]  # fmt: skip
        assert "download_url" not in row, f"{row['id']} handed its URL again"
    _only(recorder, endpoint)


def test_the_resizes_followed_the_admission_reading(
    recorder: Recorder, endpoint: str, owner: str, record42: dict[str, Any]
) -> None:
    """ADR 0270: each resize's outcome is what its OWN reading implies, read
    back through `/v1`, the instrument's judgement agreeing; the profile read
    after the large one is the one it left."""
    rows = [row for row in _read_back(recorder, endpoint, owner, record42)
            if row["type"] == "project.resize"]  # fmt: skip
    assert len(rows) == 2, rows
    for row, label in zip(rows, ("resize_standard", "resize_large"), strict=True):
        implied = _implied_status(row)
        assert row["status"] == implied, row
        judged = record42["observations"][f"{label}_admission"]
        assert judged["decided"] == judged["implied"], judged
        assert judged["implied"] == ("admitted" if implied == "succeeded" else "refused"), judged
    wanted = "large" if rows[1]["status"] == "succeeded" else "standard"
    assert record42["observations"]["profile_after_large_resize"] == wanted
    _only(recorder, endpoint)


def test_the_export_holds_the_three_customer_schemas(
    recorder: Recorder, endpoint: str, owner: str, record42: dict[str, Any]
) -> None:
    """D2333: the archive lists exactly `api`, `app` and `public` and names no
    `app_private`; its SHA-256 is one the operations recorded; the second read
    of the finished export handed no URL."""
    schemas = record42["observations"]["archive_schemas"]
    assert schemas == {"pg_restore": 0, "schemas": ["api", "app", "public"], "app_private": False}
    exported = record42["observations"]["export"]
    assert exported["mode"] == "0o600" and exported["second_read_handed_a_url"] is False, exported
    hashes = [(row.get("result") or {}).get("sha256")
              for row in _read_back(recorder, endpoint, owner, record42)
              if row["type"] == "project.export"]  # fmt: skip
    assert exported["sha256"] in hashes, (exported["sha256"], hashes)
    _only(recorder, endpoint)


def test_both_routes_were_probed_through_every_window(
    record42: dict[str, Any], samples: list[dict[str, Any]]
) -> None:
    """D2581, read from the SAMPLES FILE the record seals, not from the
    instrument's summary: the slot's app route AND its pooled name were sampled
    through each of sleep, wake and the two resizes -- a sample of each class
    before the interval's start and one after its end, samples inside it -- and
    the instrument's own reading of each window agrees with the file's count.
    The control that the probes see an outage at all: inside the sleep both
    classes failed. And the pool was sampled after the idle step: its thread
    lived through the pause (D2500)."""
    by_class = {name: [s for s in samples if s["class"] == name] for name in ("route", "pool")}
    for name, rows in by_class.items():
        assert len(rows) >= 30, (name, len(rows))
    intervals = {kept["label"]: kept for kept in record42["probe_intervals"]}
    assert set(PROBED) <= set(intervals), sorted(intervals)
    for label in PROBED:
        start = instant(intervals[label]["started_at"]).timestamp()
        end = instant(intervals[label]["finished_at"]).timestamp()
        reading = record42["observations"][f"{label}_probe"]
        for name, rows in by_class.items():
            inside = [s for s in rows if start <= s["t"] <= end + 60]
            assert rows[0]["t"] <= start and rows[-1]["t"] >= end, (label, name, "not covered")
            assert inside, (label, name, "no sample inside")
            assert reading[name]["samples"] == len(inside), (
                label,
                name,
                reading[name],
                len(inside),
            )
            assert reading[name]["covered"] is True, (label, name, reading)
    start = instant(intervals["sleep"]["started_at"]).timestamp()
    end = instant(intervals["sleep"]["finished_at"]).timestamp()
    for name, rows in by_class.items():
        assert any(not s["ok"] for s in rows if start <= s["t"] <= end + 60), (name, "no outage")
    resumed = instant(record42["observations"]["idle"]["resumed_at"]).timestamp()
    assert any(s["t"] > resumed for s in by_class["pool"]), "no pool sample after the idle step"


def test_the_second_creation_after_the_deletion_was_refused_by_capacity(
    recorder: Recorder, endpoint: str, owner: str, record42: dict[str, Any]
) -> None:
    """ADR 0274 sentence 4: the lifecycle's OWN organisation, within its plan
    once the slot was deleted, asked for a second project and was refused
    `capacity_exhausted` (`no_slot`) with its creations unchanged; asked again
    now, the same answer, and the creations made in the record's window are
    exactly the one it names."""
    second = record42["observations"]["second_create"]
    assert (second["exit"], second["no_slot"]) == (5, True), second
    assert second["creations_before"] == second["creations_after"], second
    organization = record42["organization_id"]
    status, body = recorder.json("POST", f"{endpoint}/projects", {
        "organization": organization, "name": "Lifecycle s42 again", "profile": "small",
        "admin_username": "again.admin", "handoff_sha256": "0" * 64,
    }, owner)  # fmt: skip
    assert (status, body.get("error"), body.get("reason")) == (
        409, "capacity_exhausted", "no_slot",
    ), (status, body)  # fmt: skip
    status, listed = recorder.json(
        "GET", f"{endpoint}/operations?organization={organization}", None, owner
    )
    assert status == 200, status
    start = instant(record42.get("window_started_at") or record42["started_at"])
    end = instant(record42["finished_at"])
    during = [row["id"] for row in listed["operations"] if row["type"] == "project.create"
              and start <= instant(row["created_at"]) <= end]  # fmt: skip
    recorded = [o["id"] for o in record42["operations"] if o["type"] == "project.create"]
    assert during == recorded and len(during) == 1, (during, recorded)
    _only(recorder, endpoint)


# ---------------------------------------------------------------------------
# USE-LIVE-004
# ---------------------------------------------------------------------------


def test_the_idle_slot_was_put_to_sleep_by_the_reconciler(
    recorder: Recorder, endpoint: str, owner: str, record42: dict[str, Any]
) -> None:
    """ADR 0276: with the minutes set to 15 and the slot's probes stopped, the
    reconciler asked and the control set inserted ONE `project.sleep` with
    `origin = idle` -- never sent by the instrument -- on behalf of the member who
    set the minutes, no sooner than the window allows and within the bound; it
    succeeded, and the slot was then woken by a member. Read back now."""
    idle = record42["observations"]["idle"]
    assert idle["minutes"] == IDLE_MINUTES and idle["bound_seconds"] == IDLE_BOUND_SECONDS, idle
    assert "its backups stop" in idle["note"], idle["note"]
    requested = idle["requested"]
    seconds = requested["seconds_from_setting"]
    assert IDLE_MINUTES * 60 - 60 <= seconds <= IDLE_BOUND_SECONDS, seconds
    members = {o["requested_by"] for o in record42["operations"]}
    assert len(members) == 1, members
    kinds = [(o["type"], o["origin"]) for o in record42["idle_operations"]]
    assert kinds == [("project.sleep", "idle"), ("project.wake", "member")], kinds
    read = _operation(recorder, endpoint, owner, requested["operation"])
    assert (read["type"], read["origin"], read["status"]) == (
        "project.sleep", "idle", "succeeded",
    ), read  # fmt: skip
    assert read["requested_by"] in members and read["project_key"] == record42["project_key"], read
    assert requested["operation"] not in {o["id"] for o in record42["operations"]}
    _only(recorder, endpoint)


def test_the_idle_sleep_closed_both_doors(record42: dict[str, Any]) -> None:
    """D2336 under an idle sleep: while the slot slept by idleness every sample
    of its address was the edge's 404 and BOTH public names refused the login."""
    observations = record42["observations"]
    asleep = observations["idle"]["asleep_samples"]
    assert set(asleep) == {"404"} and asleep["404"] >= 30, asleep
    refused = observations["idle_asleep_connect"]
    assert set(refused) == {"app", "admin"} and all(code != 0 for code in refused.values()), refused


# ---------------------------------------------------------------------------
# USE-LIVE-005
# ---------------------------------------------------------------------------


def _expected_notifications(record42: dict[str, Any]) -> Counter:
    """D2581: EVERY operation the record names -- the eleven, the idle sleep and
    its wake, and any export refused and resumed past -- by its outcome."""
    expected: Counter = Counter()
    for listed in ("operations", "idle_operations", "failed_exports"):
        for row in record42.get(listed) or []:
            kind = KIND_OF_ORIGIN.get(row.get("origin") or "member", "operation_succeeded")
            if row["status"] == "failed":
                kind = "operation_failed"
            expected[(kind, f"{row['type']} on {record42['project_key']} {row['status']}")] += 1
    return expected


def test_every_finished_operation_was_notified_by_its_outcome(
    recorder: Recorder, endpoint: str, owner: str, record42: dict[str, Any]
) -> None:
    """ADR 0275, D2581: every finished operation the record names has exactly
    ONE notification, its kind the outcome's -- a failed one `operation_failed`,
    the idle sleep `idle_sleep` naming its cause -- its sentence the operation's
    type, project and status; the refused creations, which wrote no operation,
    wrote none. Listed after the deletion, and asked again now."""
    expected = _expected_notifications(record42)
    key = record42["project_key"]
    for listing in (record42["observations"]["notifications_after_delete"], None):
        if listing is None:
            status, served = recorder.json(
                "GET", f"{endpoint}/organizations/{record42['organization_id']}/notifications"
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
    (idle,) = [n for n in record42["observations"]["notifications_after_delete"]
               if n["kind"] == "idle_sleep"]  # fmt: skip
    assert "idle" in idle["text"] and "backups" in idle["text"], idle
    _only(recorder, endpoint)


def test_no_notification_carries_a_secret(record42: dict[str, Any]) -> None:
    """ADR 0275: a notification is a fixed template -- never a result member, a
    URL or a caller value: no sentence holds an address, an export's hash or
    size, an operation's id, a door's host or the insights canary."""
    observations = record42["observations"]
    doors = record42["doors"]
    forbidden = {observations["export"]["sha256"], str(observations["export"]["size_bytes"]),
                 doors["pooled"]["host"], doors["direct"]["host"],
                 observations["insights"]["canary"]}  # fmt: skip
    forbidden |= {o["id"] for listed in ("operations", "idle_operations", "failed_exports")
                  for o in record42.get(listed) or []}  # fmt: skip
    for notification in observations["notifications_after_delete"]:
        text = notification["text"]
        assert "://" not in text and "http" not in text.lower(), text
        assert not [value for value in forbidden if value and value in text], text


# ---------------------------------------------------------------------------
# INS-LIVE-001
# ---------------------------------------------------------------------------


def test_the_workload_is_in_the_insights_without_its_literal(record42: dict[str, Any]) -> None:
    """ADR 0278, D2569: after one call, a usage pass, 200 calls and a second
    pass, `insights show` held the workload's statement NORMALISED -- its
    literal a `$1` -- with exactly the 200 calls the window can see (the first
    call entered with the statement's first sample, which counts nothing), as
    the slot's `customer_app` role -- the DATABASE role the extension records
    (`rolname`), derived by `naming.database_roles`, never the suffix (D2645,
    as `test_insights_reading` reads it); the canary's literal appears nowhere
    in the insights or the monitoring documents; the document carries no
    advising member."""
    insight = record42["observations"]["insights"]
    assert [w["calls"] for w in insight["workload"]] == [1, WORKLOAD_CALLS], insight["workload"]
    assert all(w["exit"] == 0 for w in insight["workload"]), insight["workload"]
    passes = insight["passes"]
    assert len(passes) == 2 and instant(passes[0]["sampled_at"]) < instant(passes[1]["sampled_at"])
    served = insight["insights"]
    assert served["exit"] == 0 and served["document"]["status"] == "read", served
    found = [s for s in served["document"]["statements"]
             if all(part in s["query"] for part in NORMALISED)]  # fmt: skip
    assert len(found) == 1, found
    roles = naming.database_roles(naming.sql_key(record42["project_key"]))
    expected = (WORKLOAD_CALLS, roles["customer_app"])
    assert (found[0]["calls"], found[0]["role"]) == expected, found[0]
    canary = insight["canary"]
    assert canary.startswith("APG-INSIGHT-CANARY-"), canary
    assert canary not in json.dumps(served) and canary not in json.dumps(insight["monitoring"])
    for advice in ("finding", "recommendation", "confidence", "severity"):
        assert advice not in json.dumps(served["document"]).lower(), advice


def test_usage_read_db_time(record42: dict[str, Any]) -> None:
    """ADR 0278: the slot's usage, read after the workload, carries DB time as
    an increase over the window -- read, not unread, and above zero."""
    document = record42["observations"]["usage"]["project"]["document"]
    assert document["status"] == "read", document["status"]
    db_time = document["db_time"]
    assert db_time is not None and db_time["increase_ms"] > 0, db_time


def test_monitoring_named_each_source(record42: dict[str, Any]) -> None:
    """ADR 0279: `monitoring show` served every signal of the release's list,
    in its order, each with the table and column it is read from, each a value
    with when it was read or `unread` with the reason -- and the insight
    sample's time among them was read."""
    monitoring = record42["observations"]["insights"]["monitoring"]
    assert monitoring["exit"] == 0, monitoring
    shown = monitoring["document"]["signals"]
    assert [(s["name"], s["source"]) for s in shown] == [
        (s.name, s.source) for s in signals.SIGNALS
    ], shown  # fmt: skip
    for signal in shown:
        assert (signal["value"] is not None and signal["observed_at"]) or signal.get("unread"), (
            signal
        )
    (sampled,) = [s for s in shown if s["name"] == "insights_sampled_at"]
    assert sampled["value"] is not None, sampled


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
