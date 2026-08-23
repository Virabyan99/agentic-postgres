"""A WAL archiving failure is visible, Session 10 Run 7 (ADR 0150).

The numbers in this module were measured by rig 7 against the Run 4 derived
image, with each arm's control in the same invocation and the rig's own churn
under a control of its own:

    healthy baseline   archived_count  8 -> 12   failed_count 11 -> 11
    archiving broken   archived_count 12 -> 12   failed_count 11 -> 26
    repaired (control) archived_count 12 -> 21   failed_count 26 -> 26

Two of those columns are the whole decision. **`failed_count` is 26 on the
healthy cluster in the last row** -- the counter is cumulative and never resets,
and every project accrues failures in the window between its container starting
with `archive_mode=on` and step 6c creating its stanza. So the status compares
timestamps, and `failed_count > 0` is refused by a test rather than only by a
comment.

What is deliberately NOT here: the live signal. `REC-WAL-001` needs a deployment
and is Run 9's; this module covers the mapping, which has to be right for states
a healthy deployment never reaches.
"""

from __future__ import annotations

import ast
import json

import pytest
import yaml

from agentic_postgres import REPO_ROOT, backup_report

pytestmark = [pytest.mark.contract, pytest.mark.p0]


#: The three states rig 7 measured, as `pg_stat_archiver` reported them.
#:
#: Timestamps are the shape psql renders with `-qtA` -- which is what the
#: product parses, so the fixtures are in the product's input format rather than
#: in a tidier one nobody produces.
HEALTHY = {
    "archived_count": 12,
    "last_archived_time": "2026-08-23 18:40:12.114+00",
    "failed_count": 11,
    "last_failed_time": "2026-08-23 18:33:16.822996+00",
    "last_failed_wal": "000000010000000000000004",
}
BROKEN = {
    "archived_count": 12,
    "last_archived_time": "2026-08-23 18:40:12.114+00",
    "failed_count": 26,
    "last_failed_time": "2026-08-23 18:44:02.551+00",
    "last_failed_wal": "00000001000000000000000C",
}
REPAIRED = {
    "archived_count": 21,
    "last_archived_time": "2026-08-23 18:46:31.907+00",
    "failed_count": 26,
    "last_failed_time": "2026-08-23 18:44:02.551+00",
    "last_failed_wal": "00000001000000000000000C",
}
NEVER_ARCHIVED = {
    "archived_count": 0,
    "last_archived_time": None,
    "failed_count": 8,
    "last_failed_time": "2026-08-23 18:33:00.08093+00",
    "last_failed_wal": "000000010000000000000001",
}
NEVER_FAILED = {
    "archived_count": 4,
    "last_archived_time": "2026-08-23 18:33:08.174444+00",
    "failed_count": 0,
    "last_failed_time": None,
    "last_failed_wal": None,
}


# ---------------------------------------------------------------------------
# The predicate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "row", "failing"),
    [
        ("healthy baseline", HEALTHY, False),
        ("archiving broken", BROKEN, True),
        ("repaired -- the control", REPAIRED, False),
        ("never archived at all", NEVER_ARCHIVED, True),
        ("never failed at all", NEVER_FAILED, False),
    ],
)
def test_the_predicate_reads_each_measured_state(label: str, row: dict, failing: bool) -> None:
    """ADR 0150's table, against the rows rig 7 produced.

    `repaired` is the row that matters most: it carries a **higher**
    `failed_count` than the broken row and is nonetheless healthy, because what
    changed is which timestamp is newer.
    """
    assert backup_report.archiving_is_failing(row) is failing, label


def test_a_nonzero_failure_count_does_not_mean_failing() -> None:
    """D553, and it is the finding that chose the predicate.

    The healthy cluster rig 7 measured carried `failed_count = 26`. **Every
    project accrues failures before its stanza exists** -- the window between the
    container starting with `archive_mode=on` and step 6c running
    `stanza-create` is a window in which every archive attempt fails. A
    `failed_count > 0` status would report every project as failing, permanently,
    from its first deploy.

    Asserted as a property of the product rather than as a note: the two rows
    below differ in `failed_count` in the direction that would fool a counter and
    agree in the direction that matters.
    """
    assert REPAIRED["failed_count"] > HEALTHY["failed_count"], (
        "the fixtures no longer make the point: the healthy-after-repair row must carry "
        "MORE cumulative failures than the earlier healthy one"
    )
    assert not backup_report.archiving_is_failing(REPAIRED)
    assert not backup_report.archiving_is_failing(HEALTHY)


def test_a_frozen_archived_count_is_not_the_signal_either() -> None:
    """`archived_count` catches up after a repair, so it cannot be the status.

    Measured: 12 -> 12 while broken, then 12 -> 21 across the repair. A reader
    sampling it twice around a repair sees a healthy-looking increase, and one
    sampling a quiet cluster sees no increase at all. Both readings are wrong in
    opposite directions, which is why the predicate uses neither.
    """
    assert BROKEN["archived_count"] == HEALTHY["archived_count"], (
        "the broken fixture no longer shows a frozen archived_count"
    )
    assert backup_report.archiving_is_failing(BROKEN)
    assert REPAIRED["archived_count"] > BROKEN["archived_count"]
    assert not backup_report.archiving_is_failing(REPAIRED)


def test_the_predicate_names_no_counter_at_all() -> None:
    """The other half, on what the code PRODUCES rather than on its text.

    A grep for `failed_count` would be D277's shape -- this module and the
    function's own docstring discuss the counter at length, deliberately. So the
    syntax tree is read: `archiving_is_failing` may not subscript a count.

    **What would have to break for this to go red:** somebody "simplifies" the
    predicate to `failed_count > 0`, which is the shortcut D553 exists to refuse
    and which reads as more obvious than what is there.
    """
    tree = ast.parse(
        (REPO_ROOT / "src" / "agentic_postgres" / "backup_report.py").read_text("utf-8")
    )
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "archiving_is_failing"
    )
    keys = {
        node.slice.value
        for node in ast.walk(function)
        if isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)
    }
    constants = {
        node.args[0].value
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    read = keys | constants
    assert "failed_count" not in read and "archived_count" not in read, (
        f"`archiving_is_failing` reads {sorted(read)}. A counter cannot answer a "
        "point-in-time question: it is cumulative, never resets, and stood at 26 on the "
        "healthy cluster rig 7 measured (D553)"
    )
    assert {"last_failed_time", "last_archived_time"} <= read, (
        f"the predicate reads {sorted(read)}; it must compare the two timestamps"
    )


# ---------------------------------------------------------------------------
# Parsing what psql actually prints
# ---------------------------------------------------------------------------


def test_the_archiver_row_is_parsed_from_the_shape_psql_prints() -> None:
    """`-qtA -F'|'`, which is how the deploy already reads this cluster."""
    raw = "12|2026-08-23 18:40:12.114+00|26|2026-08-23 18:44:02.551+00|00000001000000000000000C\n"
    parsed = backup_report.parse_archiver(raw)
    assert parsed == {
        "archived_count": 12,
        "last_archived_time": "2026-08-23 18:40:12.114+00",
        "failed_count": 26,
        "last_failed_time": "2026-08-23 18:44:02.551+00",
        "last_failed_wal": "00000001000000000000000C",
    }


def test_an_empty_timestamp_becomes_none_rather_than_an_empty_string() -> None:
    """A cluster that has never failed prints empty, and empty is not a time.

    `coalesce(..., '')` in the query is what makes the column positions stable;
    turning it back into None here is what keeps "never" distinguishable from
    "at the epoch".

    **Both timestamps, and the battery is why.** The first version asserted only
    the failed one, so mutating `last_archived_time`'s `or None` survived -- and
    it survived for an uncomfortable reason: an empty string still compares
    greater-than against nothing, so the predicate happened to return the right
    answer for the wrong reason. A field that is only accidentally correct is one
    line of refactoring from being wrong.
    """
    never_failed = backup_report.parse_archiver("4|2026-08-23 18:33:08.174444+00|0||\n")
    assert never_failed is not None
    assert never_failed["last_failed_time"] is None
    assert never_failed["last_failed_wal"] is None
    assert not backup_report.archiving_is_failing(never_failed)

    # The other empty field, which is what a cluster that has NEVER archived
    # prints -- every project, in the window before step 6c creates its stanza.
    never_archived = backup_report.parse_archiver(
        "0||8|2026-08-23 18:33:00.08093+00|000000010000000000000001\n"
    )
    assert never_archived is not None
    assert never_archived["last_archived_time"] is None, (
        "an empty archived timestamp survived as a string. `archiving_is_failing` tests "
        "it with `is None`, so a '' would fall through to a string comparison and be "
        "right only by accident"
    )
    assert never_archived["archived_count"] == 0
    assert backup_report.archiving_is_failing(never_archived)


@pytest.mark.parametrize("raw", ["", "\n", "   \n", "not|enough", "a|b|c|d|e"])
def test_an_unreadable_row_is_none_rather_than_zeros(raw: str) -> None:
    """None, never a dict of zeros.

    A cluster that could not be asked and a cluster reporting zero failures are
    different facts, and publishing the second for the first is the substitution
    `NOT_OBSERVED` exists to refuse. Zeros would read as "archiving has never
    failed", which is the most reassuring possible wrong answer.
    """
    assert backup_report.parse_archiver(raw) is None


# ---------------------------------------------------------------------------
# What the document publishes
# ---------------------------------------------------------------------------


def _summary(status_code: int = 0, label: str | None = "20260823-174442F") -> dict:
    return {
        "status_code": status_code,
        "stanza_created": True,
        "backup_count": 1,
        "last_full_backup_label": label,
        "last_full_backup_at": "2026-08-23T18:33:08Z",
        "latest_recoverable_time": "2026-08-23T18:33:08Z",
        "backup_errors": [],
    }


def test_a_broken_archiver_turns_a_ready_repository_into_failing() -> None:
    """The two sources fail independently, so the status needs both.

    A repository full of good backups can sit behind an archiver that stopped an
    hour ago, and `pgbackrest info` reports `ok` for exactly that cluster.
    """
    ready = backup_report.backup_state(_summary(), HEALTHY)
    assert ready["status"] == backup_report.STATUS_READY, "the control is not ready"

    failing = backup_report.backup_state(_summary(), BROKEN)
    assert failing["status"] == backup_report.STATUS_FAILING
    assert failing["last_full_backup_label"] == ready["last_full_backup_label"], (
        "the backup facts changed with the archiver; only the status should have"
    )


def test_a_healthy_archiver_cannot_promote_a_repository_with_no_backup() -> None:
    """The archiver may only make the status worse.

    A stanza with no backup is `awaiting_first_backup` however well WAL is
    flowing, because there is still nothing to restore. Without this the
    archiver's verdict would be an override rather than a second condition.
    """
    state = backup_report.backup_state(
        _summary(status_code=backup_report.REPOSITORY_NO_BACKUPS, label=None), NEVER_FAILED
    )
    assert state["status"] == backup_report.STATUS_AWAITING_FIRST_BACKUP


def test_the_counters_are_published_as_measured() -> None:
    """Cumulative and unreset, including the pre-stanza failures.

    They are the diagnostic that justifies the status rather than the status
    itself. Resetting them would discard the evidence and would make the deploy
    a writer of the statistics it reads.
    """
    state = backup_report.backup_state(_summary(), REPAIRED)
    assert state["wal_archived_count"] == REPAIRED["archived_count"]
    assert state["wal_failed_count"] == REPAIRED["failed_count"]
    assert state["wal_failed_count"] > 0
    assert state["status"] == backup_report.STATUS_READY, (
        "a non-zero failed count made the status failing; the counter is cumulative and "
        "26 is what a healthy cluster carries (D553)"
    )


def test_an_unread_archiver_leaves_both_counters_null() -> None:
    """Run 6's behaviour, preserved for every deployment that reads nothing.

    Null rather than zero, and the status falls back to the repository's own
    verdict rather than to a failure nobody observed.
    """
    state = backup_report.backup_state(_summary(), None)
    assert state["wal_archived_count"] is None
    assert state["wal_failed_count"] is None
    assert state["status"] == backup_report.STATUS_READY


def test_the_published_block_still_matches_the_schema_with_counters_present() -> None:
    schema = json.loads((REPO_ROOT / "schemas" / "outputs.schema.json").read_text("utf-8"))
    definition = schema["$defs"]["backupState"]
    state = backup_report.backup_state(_summary(), BROKEN)

    assert set(state) == set(definition["required"])
    assert state["status"] in definition["properties"]["status"]["enum"]
    for field in ("wal_archived_count", "wal_failed_count"):
        assert isinstance(state[field], int) and state[field] >= 0


# ---------------------------------------------------------------------------
# The healthcheck decision
# ---------------------------------------------------------------------------


def test_the_postgres_healthcheck_does_not_read_the_archiver() -> None:
    """ADR 0150, and the plan predicted the opposite -- so this is the record.

    Measured (rig 7 arm H): with the predicate as the healthcheck,
    `compose up --wait` **exits 1** with "container … is unhealthy" while the
    database answers queries; the control, the same broken archiver behind
    `pg_isready`, exits 0.

    **Three services gate on `postgres: condition: service_healthy`.** An
    archiving predicate there means a backup problem stops the pooler, the auth
    service and storage from starting -- on a cluster that is serving -- and it
    blocks the deploy that would carry the repair.

    **What would have to break for this to go red:** somebody moves the signal
    into the healthcheck because the plan's Run 7 entry says "the healthcheck
    goes unhealthy". It said that before the cost was measured.
    """
    # Parsed rather than string-split. The first version of this sliced the file
    # on "\n  postgres:" and produced an EMPTY block, which asserted nothing
    # while looking thorough -- a test measuring a substring it had failed to
    # extract. Compose's own structure is the thing being asserted about, so it
    # is the thing to read.
    compose = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    postgres = compose["services"]["postgres"]

    healthcheck = postgres.get("healthcheck")
    assert healthcheck, "the postgres service has no healthcheck at all"
    test = " ".join(str(part) for part in healthcheck.get("test", []))

    assert "pg_stat_archiver" not in test, (
        f"the postgres healthcheck is {test!r} and reads pg_stat_archiver. Three services "
        "gate on this health, so a broken archiver would stop the application from "
        "starting -- on a cluster that is serving -- and would block the deploy carrying "
        "the fix (ADR 0150, rig 7 arm H)"
    )
    assert "pg_isready" in test, (
        f"the postgres healthcheck is {test!r}; ADR 0150 keeps pg_isready there "
        "deliberately, and a change needs its own decision"
    )

    # And the gating this decision turns on is real rather than remembered.
    gated = sorted(
        name
        for name, service in compose["services"].items()
        if (service.get("depends_on") or {}).get("postgres", {}).get("condition")
        == "service_healthy"
    )
    assert len(gated) >= 3, (
        f"only {gated} gate on postgres being healthy. ADR 0150 rests on that gating "
        "being what turns a backup problem into an availability one; if it has shrunk to "
        "nothing, the decision deserves re-reading rather than silent inheritance"
    )


def test_the_deploy_reads_the_archiver_beside_the_repository_not_later() -> None:
    """One instant, two reads.

    Two reads minutes apart could publish a `ready` repository beside counters
    taken after something broke -- a document internally inconsistent about one
    system. Asserted on order within step 6c rather than on the presence of a
    call.
    """
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    step = source.split("6c. Create the backup stanza", 1)[1].split('step("7.', 1)[0]
    assert "read_backup_repository" in step and "read_archiver" in step, (
        "step 6c no longer reads both sources; the archiver and the repository fail "
        "independently, so a status from one alone is about half the system"
    )
