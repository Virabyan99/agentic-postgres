"""Reading a repository's own report, Session 10 Run 6 (ADR 0149).

**The fixtures under `tests/fixtures/pgbackrest/` are real output**, captured
from rig 6 with `pgbackrest info --output=json` against the Run 4 derived image
at three points in a repository's life. They are not hand-written: a
hand-written fixture is a statement of what somebody expected the tool to say,
and half of this run's findings are places where that expectation was wrong.

What is deliberately NOT here: anything that needs a container. Whether
`stanza-create` really is idempotent and whether `check` really catches a broken
archiver were measured in rig 6 and are asserted on the host by `REC-WAL-001`.
This module covers the part that decides what the DOCUMENT says, which is pure
logic over a report -- and which has to be right for repository states a healthy
deployment never reaches.
"""

from __future__ import annotations

import ast
import json
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, backup_report

pytestmark = [pytest.mark.contract, pytest.mark.p0]

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "pgbackrest"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The finding that shaped the observer
# ---------------------------------------------------------------------------


def test_every_captured_report_came_from_a_process_that_exited_zero() -> None:
    """D548, and it is the reason nothing here reads an exit code.

    All three fixtures were produced by a `pgbackrest info` that exited **0** --
    including the one for a stanza that does not exist. That is D145's shape:
    `postgrest --ready` returned 0 while every request 404'd, and the proof that
    trusted it measured nothing.

    This test cannot re-run those processes, so what it asserts is the
    consequence: **the three reports are distinguishable only by `status.code`**.
    An observer built the obvious way -- run `info`, check it succeeded, report
    healthy -- would treat all three identically, and would report a healthy
    repository for a stanza that has never existed, on every project, forever.
    """
    codes = {
        name: _load(name)[0]["status"]["code"]
        for name in ("info-missing-stanza.json", "info-no-backups.json", "info-full-and-incr.json")
    }
    assert codes == {
        "info-missing-stanza.json": backup_report.REPOSITORY_MISSING_STANZA,
        "info-no-backups.json": backup_report.REPOSITORY_NO_BACKUPS,
        "info-full-and-incr.json": backup_report.REPOSITORY_OK,
    }, f"the captured reports no longer carry the measured codes: {codes}"

    assert len(set(codes.values())) == 3, (
        "two repository states report the same status.code, so the code cannot be what "
        "distinguishes them and the ladder in `backup_report.status_for` is reading the "
        "wrong field"
    )


def test_nothing_in_the_report_reader_looks_at_a_return_code() -> None:
    """The other half, asserted on what the module PRODUCES.

    A text scan for `returncode` would be D277's shape -- satisfied by a comment,
    and this module's docstring mentions exit codes repeatedly on purpose. So the
    syntax tree is read instead: no function in `backup_report` may reference a
    name or attribute that is a process's status.

    **What would have to break for this to go red:** somebody threads a
    `CompletedProcess` into the mapping and gates on `.returncode`, which is
    exactly the shortcut D548 makes tempting.
    """
    tree = ast.parse(
        (REPO_ROOT / "src" / "agentic_postgres" / "backup_report.py").read_text("utf-8")
    )
    offenders = [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in {"returncode", "stderr", "stdout"}
    ]
    assert not offenders, (
        f"`backup_report` reads {offenders} from a process. `pgbackrest info` exits 0 in "
        "every state including a stanza that does not exist (D548), so a process's "
        "status cannot distinguish a healthy repository from an absent one"
    )


# ---------------------------------------------------------------------------
# The ladder
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "stanza", "expected"),
    [
        ("info-missing-stanza.json", "nosuchstanza", backup_report.STATUS_FAILING),
        ("info-no-backups.json", "emptystanza", backup_report.STATUS_AWAITING_FIRST_BACKUP),
        ("info-full-and-incr.json", "rigstanza", backup_report.STATUS_READY),
    ],
)
def test_the_ladder_maps_each_measured_state(fixture: str, stanza: str, expected: str) -> None:
    """ADR 0149's table, against the reports that produced it."""
    summary = backup_report.summarise(_load(fixture), stanza)
    assert backup_report.status_for(summary) == expected


def test_an_unrecognised_status_code_is_not_success() -> None:
    """A control on the ladder's default, and the direction it defaults in.

    pgBackRest may add a code. Mapping an unknown to `ready` is how a new failure
    mode arrives as a green light, so the default is `failing` -- and this
    asserts the default rather than trusting the three branches above to be
    exhaustive forever.
    """
    assert backup_report.status_for({"status_code": 99}) == backup_report.STATUS_FAILING
    assert backup_report.status_for({"status_code": None}) == backup_report.STATUS_FAILING
    assert backup_report.status_for({}) == backup_report.STATUS_FAILING


def test_a_repository_reporting_ok_with_a_failed_backup_is_failing() -> None:
    """`error` is per backup, and `ok` overall does not clear it."""
    summary = backup_report.summarise(_load("info-full-and-incr.json"), "rigstanza")
    assert backup_report.status_for(summary) == backup_report.STATUS_READY, (
        "the control is not green, so the arm below would prove nothing"
    )
    summary["backup_errors"] = ["20260823-174442F"]
    assert backup_report.status_for(summary) == backup_report.STATUS_FAILING


def test_ok_with_no_full_backup_is_failing_because_the_chain_has_no_base() -> None:
    """An incremental cannot be restored without the full it references."""
    summary = backup_report.summarise(_load("info-full-and-incr.json"), "rigstanza")
    summary["last_full_backup_label"] = None
    assert backup_report.status_for(summary) == backup_report.STATUS_FAILING


# ---------------------------------------------------------------------------
# What the summary carries
# ---------------------------------------------------------------------------


def test_the_newest_full_backup_is_reported_not_the_first_one_listed() -> None:
    """Read from the ordering key rather than from the report's order.

    **This test needed TWO full backups and the battery is why.** Its first
    version used the full-plus-incremental fixture, where there is exactly one
    full -- so `fulls[0]` and `max(fulls, key=stop)` are the same object and the
    mutation that replaced one with the other survived. A test that cannot
    distinguish the two things it is named after is not testing either.

    `info-two-fulls.json` is a real capture with the newest full **last**, which
    is the arrangement that makes the distinction observable at all.
    """
    document = _load("info-two-fulls.json")
    backups = document[0]["backup"]
    fulls = [b for b in backups if b["type"] == "full"]
    assert len(fulls) == 2, "the fixture no longer carries two full backups"

    newest = max(fulls, key=lambda b: b["timestamp"]["stop"])
    oldest = min(fulls, key=lambda b: b["timestamp"]["stop"])
    assert fulls[0] is oldest, (
        "the fixture's newest full is FIRST in the report, so taking the first entry "
        "would accidentally be correct and this test would prove nothing"
    )

    summary = backup_report.summarise(document, "rigstanza")
    assert summary["last_full_backup_label"] == newest["label"], (
        f"reported {summary['last_full_backup_label']!r}, expected the newest full "
        f"{newest['label']!r} rather than the first listed {oldest['label']!r}"
    )

    # And the answer must not move when the report's order does.
    document[0]["backup"] = list(reversed(backups))
    assert (
        backup_report.summarise(document, "rigstanza")["last_full_backup_label"] == newest["label"]
    ), "reversing the report changed the answer, so the list's order is being trusted"


def test_the_latest_recoverable_time_is_the_newest_backup_of_any_type() -> None:
    """D550: a proven FLOOR, and the floor is the newest backup, not the newest full.

    `pgbackrest info` has no latest-recoverable-time field at all -- it carries
    per-backup epochs and WAL segment names, and a segment name has no time in
    or beside it. So this publishes the latest instant the deployment can PROVE
    is recoverable, and an incremental extends that floor.
    """
    document = _load("info-full-and-incr.json")
    summary = backup_report.summarise(document, "rigstanza")

    stops = [b["timestamp"]["stop"] for b in document[0]["backup"]]
    assert summary["latest_recoverable_time"] == backup_report._timestamp(max(stops))
    assert summary["last_full_backup_at"] != summary["latest_recoverable_time"], (
        "the floor equals the newest FULL backup's time, so an incremental is not "
        "extending it -- which is the whole reason the two are separate fields"
    )


def test_a_timestamp_matches_the_documents_own_pattern() -> None:
    """The schema's `timestamp` is `...THH:MM:SSZ`, and pgBackRest reports epochs.

    Asserted against the schema's pattern rather than against a format string
    written here, so the two cannot drift apart with both looking right.
    """
    import re

    schema = json.loads((REPO_ROOT / "schemas" / "outputs.schema.json").read_text("utf-8"))
    pattern = schema["$defs"]["timestamp"]["pattern"]

    summary = backup_report.summarise(_load("info-full-and-incr.json"), "rigstanza")
    for field in ("last_full_backup_at", "latest_recoverable_time"):
        value = summary[field]
        assert value and re.match(pattern, value), f"{field}={value!r} does not match {pattern}"


def test_a_report_about_another_stanza_is_refused() -> None:
    """`info` answers for the stanza it was ASKED about, even a nonexistent one.

    So a report with no entry for the stanza means the report is about something
    else entirely -- a different project's repository, or a `--stanza` that never
    reached the command. Publishing that project's backup times under this
    project's key is the failure this refusal prevents.
    """
    with pytest.raises(ValueError, match="does not include"):
        backup_report.summarise(_load("info-full-and-incr.json"), "some-other-project")


# ---------------------------------------------------------------------------
# The published block
# ---------------------------------------------------------------------------


def test_the_block_validates_against_the_deployed_schema() -> None:
    """Built, then validated by the schema rather than by a list written here."""
    summary = backup_report.summarise(_load("info-full-and-incr.json"), "rigstanza")
    state = backup_report.backup_state(summary)

    schema = json.loads((REPO_ROOT / "schemas" / "outputs.schema.json").read_text("utf-8"))
    definition = schema["$defs"]["backupState"]
    assert set(state) == set(definition["required"]), (
        f"the block carries {sorted(state)}, the schema requires {sorted(definition['required'])}"
    )
    assert state["status"] in definition["properties"]["status"]["enum"]


def test_the_wal_counters_are_null_because_run_6_did_not_read_the_archiver() -> None:
    """Honest rather than zero, and the distinction is this project's oldest one.

    `wal_archived_count` and `wal_failed_count` come from `pg_stat_archiver`,
    which is Run 7's subject. A zero here would be indistinguishable from a real
    measurement that happened to be zero -- `NOT_OBSERVED`'s whole discipline --
    and it would sit beside a `ready` status, which is where it would be read as
    "nothing has failed".
    """
    summary = backup_report.summarise(_load("info-full-and-incr.json"), "rigstanza")
    state = backup_report.backup_state(summary)
    assert state["status"] == backup_report.STATUS_READY
    assert state["wal_archived_count"] is None
    assert state["wal_failed_count"] is None


def test_awaiting_first_backup_publishes_a_stanza_and_no_backup() -> None:
    """The state every project is in after its first Session 10 deploy."""
    summary = backup_report.summarise(_load("info-no-backups.json"), "emptystanza")
    state = backup_report.backup_state(summary)

    assert state["status"] == backup_report.STATUS_AWAITING_FIRST_BACKUP
    assert state["stanza_created"] is True
    assert state["last_full_backup_label"] is None
    assert state["latest_recoverable_time"] is None, (
        "a repository with no backup published a recoverable time, which is a claim that "
        "something can be restored from a repository that holds nothing"
    )


def test_a_missing_stanza_does_not_claim_to_be_created() -> None:
    summary = backup_report.summarise(_load("info-missing-stanza.json"), "nosuchstanza")
    state = backup_report.backup_state(summary)
    assert state["status"] == backup_report.STATUS_FAILING
    assert state["stanza_created"] is False


# ---------------------------------------------------------------------------
# The command, and what it refuses to take
# ---------------------------------------------------------------------------


def _backup_command_source() -> str:
    return (REPO_ROOT / "bin" / "backup.py").read_text(encoding="utf-8")


def test_no_verb_takes_a_stanza_a_bucket_or_a_retention_count() -> None:
    """ADR 0002 and D495, asserted on the parser rather than on the prose.

    Every one of those four is decided once and published -- the stanza and the
    bucket in `outputs.json`, the prefix with them, and `retain_full` in the
    rendered `pgbackrest.conf`. A flag here would be a second statement of the
    value, and the second statement is the one that wins while the first is the
    one people read.

    The sharpest of the four is the stanza: a command pointed at a stanza the
    archiver is not writing to succeeds at every step and backs up nothing.
    """
    tree = ast.parse(_backup_command_source())
    flags = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    forbidden = {
        flag
        for flag in flags
        if any(
            word in flag
            for word in ("stanza", "bucket", "prefix", "retention", "retain", "cipher", "key")
        )
    }
    assert not forbidden, (
        f"bin/backup.py accepts {sorted(forbidden)}. Each of those is decided once and "
        "published; a flag here is a second authority over it (ADR 0002, D495)"
    )
    assert flags == {"--outputs", "--type", "--json"}, (
        f"the command's flags are {sorted(flags)}; anything beyond --outputs, --type and "
        "--json is a value this command should be reading rather than being told"
    )


def test_the_expire_verb_states_no_retention() -> None:
    """Measured (rig 6): `expire` applies `repo1-retention-full` from the config.

    So the flag is not merely undesirable, it is unnecessary -- which is the
    order those two facts have to be established in. D463 and D495 are both
    cases where a value was restated because nobody checked whether it had to be.

    **Asserted on the ARGUMENT VECTOR, not on the function's string literals.**
    The first version of this scanned every constant in `verb_expire` and went
    red on the word "retention" inside the message it prints afterwards -- which
    is a report of what happened, not an instruction to pgBackRest. A scan that
    cannot tell a command-line flag from a sentence is the shape that produced
    D464's false positive.
    """
    tree = ast.parse(_backup_command_source())
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "verb_expire"
    )
    calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "pgbackrest"
    ]
    assert len(calls) == 1, f"verb_expire makes {len(calls)} pgbackrest calls, expected one"

    # `pgbackrest(container, stanza, *arguments)` -- everything after the first
    # two positionals is the command line pgBackRest actually receives.
    passed = [
        argument.value
        for argument in calls[0].args[2:]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
    ]
    assert passed == ["expire"], (
        f"verb_expire runs pgbackrest with {passed}. Retention is `repo1-retention-full` "
        "in the rendered config and pgBackRest was MEASURED applying it from there with "
        "nothing on the command line, so a flag here is a second statement of one value"
    )


def test_the_command_runs_pgbackrest_as_the_postmasters_uid() -> None:
    """999, and not root (D515).

    Root inside the container reads the credential files fine and then writes
    repository state owned by root, which the postmaster cannot read afterwards
    -- a failure that appears one archive-push later, somewhere else.
    """
    import importlib.util

    specification = importlib.util.spec_from_file_location(
        "apg_backup_command", REPO_ROOT / "bin" / "backup.py"
    )
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)

    assert module.POSTGRES_UID == "999"
    # And it is the uid the secret contract materializes the backup files to,
    # rather than a literal that happens to match today.
    contract = yaml.safe_load((REPO_ROOT / "secrets.required.yaml").read_text("utf-8"))
    consumers = [
        consumer
        for secret in contract["secrets"]
        for consumer in (secret.get("consumers") or [])
        if secret["name"].startswith(("backup_", "pgbackrest_"))
    ]
    assert consumers, "no backup secrets declare a consumer"
    assert {str(consumer["uid"]) for consumer in consumers} == {module.POSTGRES_UID}, (
        "the uid pgBackRest runs as is not the uid its credential files are owned by; a "
        "0400 file owned 999 read by another uid is a repository authentication failure "
        "nobody debugs by re-reading an ownership table (D515)"
    )


# ---------------------------------------------------------------------------
# Step 6c
# ---------------------------------------------------------------------------


def _deploy_tree() -> ast.Module:
    return ast.parse((REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8"))


def test_a_failed_check_fails_the_deploy() -> None:
    """The whole point of step 6c, asserted on control flow rather than on text.

    A text scan for "fail" would be D277's shape -- satisfied by a comment, and
    the comments around step 6c say the word repeatedly. So the syntax tree is
    read: the branch guarded by the check's non-zero return must CALL `fail`.

    **What would have to break for this to go red:** somebody turns the check
    into a warning. That is the specific edit this run exists to prevent, because
    a deploy that converged over a broken archiver is the failure this session
    was commissioned for -- and D534 measured that it is invisible from outside,
    `pg_isready` answering *accepting connections* while `pg_wal` fills.
    """
    branches = [
        node
        for node in ast.walk(_deploy_tree())
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Attribute)
        and node.test.left.attr == "returncode"
        and isinstance(node.test.left.value, ast.Name)
        and node.test.left.value.id == "checked"
    ]
    assert len(branches) == 1, (
        f"expected exactly one branch on the check's return code, found {len(branches)}"
    )
    called = {
        node.func.id
        for node in ast.walk(branches[0])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "fail" in called, (
        "a failing `pgbackrest check` does not fail the deploy. It is the only command in "
        "this system that tests archiving end to end -- it forces a WAL switch and "
        "confirms the segment arrived -- so downgrading it to a warning means a release "
        "converges over a cluster that cannot archive"
    )


def test_the_stanza_is_created_without_probing_first() -> None:
    """Measured idempotent (rig 6), so the probe is unnecessary.

    A probe-then-create buys nothing and adds a window in which the answer can
    change. Asserted by requiring that nothing reads the repository BEFORE
    `stanza-create` in the same step: `read_backup_repository` must be called
    after it, not before.
    """
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    step = source.split("6c. Create the backup stanza", 1)[1].split('step("7.', 1)[0]
    assert step.index("stanza-create") < step.index("read_backup_repository"), (
        "the repository is read before the stanza is created, which is a probe -- and "
        "`stanza-create` was measured idempotent precisely so no probe is needed"
    )


def test_the_deploy_reads_the_rendered_document_not_the_deployed_one() -> None:
    """D465, one step up, and the same trap.

    The deployed document at this point in the run is the PREVIOUS deploy's,
    because step 7 writes the new one long after. `backup` is one shared `$def`
    (ADR 0146) so the two branches agree in SHAPE -- which is exactly why 0146
    chose a shared definition over a copy per branch -- but the previous
    deploy's document can still name a stanza this release has changed.
    """
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    step = source.split("6c. Create the backup stanza", 1)[1].split('step("7.', 1)[0]
    assert "deployed_path" not in step, (
        "step 6c reads the deployed document, which at this point is the PREVIOUS deploy's (D465)"
    )
    assert "rendered_path" in step
