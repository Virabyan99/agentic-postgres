"""`FLEET-BACKUP-001` -- `backup.sh schedule`, offline.

Behavioural on `agentic_postgres.backup_schedule` for the refusals and the
fold, and on `bin/backup.py`'s verb with `systemctl` and the repository read
recorded rather than run: the two refusals arrive in order and before any
`enable`, `status` exits by the fold, and `enable` re-reads systemd rather
than trusting its exit code.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, backup_report, backup_schedule, fleet

pytestmark = [pytest.mark.contract, pytest.mark.p0]

KEY = "fixture-alpha-dev"
ENABLED = {"full": fleet.ENABLED, "incr": fleet.ENABLED}
ABSENT = {"full": fleet.ABSENT, "incr": fleet.ABSENT}
DISABLED = {"full": fleet.DISABLED, "incr": fleet.DISABLED}


# ---------------------------------------------------------------------------
# The decisions
# ---------------------------------------------------------------------------


def test_the_units_are_the_two_timer_instances() -> None:
    assert backup_schedule.units(KEY) == {
        "full": f"agentic-postgres-backup-full@{KEY}.timer",
        "incr": f"agentic-postgres-backup-incr@{KEY}.timer",
    }


def test_absent_units_are_refused_first_and_the_refusal_names_the_installer() -> None:
    """D944's state. The repository is not even consulted: the refusal for the
    absent unit names the repair, and `systemctl enable` on an instance of an
    uninstalled template would fail with a message about the template."""
    why = backup_schedule.enable_refusal(
        ABSENT,
        repository_status=backup_report.STATUS_READY,
        last_full_backup_at="2026-09-01T00:00:00Z",
    )
    assert why is not None and "provision-host.sh" in why and "full and incr" in why
    one = backup_schedule.enable_refusal(
        {"full": fleet.ABSENT, "incr": fleet.DISABLED},
        repository_status=backup_report.STATUS_READY,
        last_full_backup_at="2026-09-01T00:00:00Z",
    )
    assert one is not None and "the full timer" in one


def test_a_repository_without_a_full_backup_is_refused_and_the_refusal_names_the_command() -> None:
    for status, last in (
        (backup_report.STATUS_AWAITING_FIRST_BACKUP, None),
        (backup_report.STATUS_UNCONFIGURED, None),
        (backup_report.STATUS_FAILING, "2026-09-01T00:00:00Z"),
        (backup_report.STATUS_NOT_OBSERVED, None),
        (backup_report.STATUS_READY, None),
        (None, None),
    ):
        why = backup_schedule.enable_refusal(
            DISABLED, repository_status=status, last_full_backup_at=last
        )
        assert why is not None and "backup --type full" in why, (status, last)


def test_installed_units_and_a_full_backup_may_be_enabled() -> None:
    assert (
        backup_schedule.enable_refusal(
            DISABLED,
            repository_status=backup_report.STATUS_READY,
            last_full_backup_at="2026-09-01T00:00:00Z",
        )
        is None
    )


def test_an_unknown_timer_state_is_refused_rather_than_enabled_blind() -> None:
    why = backup_schedule.enable_refusal(
        {"full": fleet.UNKNOWN, "incr": fleet.DISABLED},
        repository_status=backup_report.STATUS_READY,
        last_full_backup_at="2026-09-01T00:00:00Z",
    )
    assert why is not None and "did not answer" in why


def test_the_status_document_folds_with_the_inventorys_rule() -> None:
    assert backup_schedule.status_document(KEY, ENABLED)["schedule"] == fleet.SCHEDULED
    assert backup_schedule.status_document(KEY, DISABLED)["schedule"] == fleet.UNSCHEDULED
    assert backup_schedule.status_document(KEY, ABSENT)["schedule"] == fleet.UNSCHEDULED
    mixed = {"full": fleet.ENABLED, "incr": fleet.UNKNOWN}
    assert backup_schedule.status_document(KEY, mixed)["schedule"] == fleet.UNKNOWN
    parsed = json.loads(backup_schedule.render_json(KEY, ABSENT))
    assert parsed["project_key"] == KEY and parsed["timers"] == ABSENT


def test_the_status_text_names_the_repair_for_each_unscheduled_state() -> None:
    assert "provision-host.sh" in backup_schedule.render_status(KEY, ABSENT)
    assert "schedule enable" in backup_schedule.render_status(KEY, DISABLED)
    assert "is scheduled" in backup_schedule.render_status(KEY, ENABLED)


# ---------------------------------------------------------------------------
# The verb, with systemd and the repository recorded
# ---------------------------------------------------------------------------


@pytest.fixture
def backup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("apg_backup", REPO_ROOT / "bin" / "backup.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "require_root", lambda: None)
    outputs = tmp_path / "outputs.json"
    outputs.write_text(
        json.dumps(
            {
                "project": {"key": KEY},
                "database": {"container": f"apg-{KEY}-postgres-1", "name": "x"},
                "backup": {"stanza": KEY, "enabled": True},
            }
        ),
        encoding="utf-8",
    )
    module.OUTPUTS_FOR_TEST = outputs
    return module


class Systemd:
    """A recorded systemd: `is-enabled` answers from a table the test controls,
    `enable --now` and `disable --now` are recorded and move the table."""

    def __init__(self, states: dict[str, str]) -> None:
        self.states = dict(states)
        self.calls: list[tuple[str, ...]] = []
        self.enable_moves_state = True

    def __call__(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        self.calls.append(arguments)
        unit = arguments[-1]
        kind = "full" if "backup-full@" in unit else "incr"
        if arguments[0] == "is-enabled":
            state = self.states[kind]
            answer = {
                fleet.ENABLED: ("enabled", 0),
                fleet.DISABLED: ("disabled", 1),
                fleet.ABSENT: ("not-found", 4),
            }[state]
            return subprocess.CompletedProcess(
                args=list(arguments), returncode=answer[1], stdout=answer[0] + "\n", stderr=""
            )
        if arguments[0] == "enable":
            if self.enable_moves_state:
                self.states[kind] = fleet.ENABLED
            return subprocess.CompletedProcess(
                args=list(arguments), returncode=0, stdout="", stderr=""
            )
        if arguments[0] == "disable":
            self.states[kind] = fleet.DISABLED
            return subprocess.CompletedProcess(
                args=list(arguments), returncode=0, stdout="", stderr=""
            )
        raise AssertionError(f"unexpected systemctl {arguments}")


def run_verb(backup: Any, *arguments: str) -> int:
    return backup.main(["--outputs", str(backup.OUTPUTS_FOR_TEST), "schedule", *arguments])


def stub_repository(
    backup: Any, monkeypatch: pytest.MonkeyPatch, *, status: str, last_full: str | None
) -> None:
    summary = {"status": status, "last_full_backup_at": last_full}
    monkeypatch.setattr(backup, "database_container", lambda document: f"apg-{KEY}-postgres-1")
    monkeypatch.setattr(backup, "read_repository", lambda container, stanza: summary)
    monkeypatch.setattr(backup, "read_archiver", lambda container, document: None)
    monkeypatch.setattr(
        backup.backup_report, "backup_state", lambda summary, archiver=None: dict(summary)
    )


def test_status_exits_zero_only_when_both_timers_are_enabled(
    backup: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(backup, "systemctl", Systemd(ENABLED))
    assert run_verb(backup, "status", "--json") == 0
    assert json.loads(capsys.readouterr().out)["schedule"] == fleet.SCHEDULED

    monkeypatch.setattr(
        backup, "systemctl", Systemd({"full": fleet.ENABLED, "incr": fleet.DISABLED})
    )
    assert run_verb(backup, "status") == backup.EXIT_REFUSED
    assert "unscheduled" in capsys.readouterr().out

    monkeypatch.setattr(backup, "systemctl", Systemd(ABSENT))
    assert run_verb(backup, "status") == backup.EXIT_REFUSED
    assert "provision-host.sh" in capsys.readouterr().out


def test_enable_refuses_absent_units_before_reading_the_repository(
    backup: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    systemd = Systemd(ABSENT)
    monkeypatch.setattr(backup, "systemctl", systemd)
    monkeypatch.setattr(
        backup, "read_repository", lambda *a: pytest.fail("the repository was read")
    )
    assert run_verb(backup, "enable") == backup.EXIT_PREREQUISITE
    assert "provision-host.sh" in capsys.readouterr().err
    assert not [c for c in systemd.calls if c[0] == "enable"], "an enable was issued"


def test_enable_refuses_a_repository_without_a_full_backup(
    backup: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    systemd = Systemd(DISABLED)
    monkeypatch.setattr(backup, "systemctl", systemd)
    stub_repository(
        backup, monkeypatch, status=backup_report.STATUS_AWAITING_FIRST_BACKUP, last_full=None
    )
    assert run_verb(backup, "enable") == backup.EXIT_REFUSED
    assert "backup --type full" in capsys.readouterr().err
    assert not [c for c in systemd.calls if c[0] == "enable"]


def test_enable_enables_both_and_re_reads_systemd(
    backup: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    systemd = Systemd(DISABLED)
    monkeypatch.setattr(backup, "systemctl", systemd)
    stub_repository(
        backup, monkeypatch, status=backup_report.STATUS_READY, last_full="2026-09-01T00:00:00Z"
    )
    assert run_verb(backup, "enable") == 0
    enables = [c for c in systemd.calls if c[0] == "enable"]
    assert [c[-1] for c in enables] == list(backup_schedule.units(KEY).values())
    assert all(c[1] == "--now" for c in enables)
    reads = [c for c in systemd.calls if c[0] == "is-enabled"]
    assert len(reads) == 4, "systemd was not re-read after the enable"
    out = capsys.readouterr().out
    assert "is scheduled" in out and "Persistent=true" in out
    # D973: the verb no longer promises an immediate run. Measured at the first
    # enable on the host: LastTriggerUSec empty, next elapse the next calendar
    # slot. A freshly enabled timer owes nothing.
    assert "fires now" not in out, "the verb still promises a run that does not happen (D973)"
    assert "next calendar slots" in out


def test_enable_that_systemd_did_not_honour_is_reported_not_trusted(
    backup: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The re-read is the point: `systemctl enable` can exit 0 and leave the
    unit disabled (a masked unit, a unit file with no [Install]), and a verb
    that trusted the exit code would report a schedule nothing runs."""
    systemd = Systemd(DISABLED)
    systemd.enable_moves_state = False
    monkeypatch.setattr(backup, "systemctl", systemd)
    stub_repository(
        backup, monkeypatch, status=backup_report.STATUS_READY, last_full="2026-09-01T00:00:00Z"
    )
    assert run_verb(backup, "enable") == backup.EXIT_STATE
    assert "does not report both enabled" in capsys.readouterr().err


def test_disable_disables_what_is_installed_and_skips_what_is_not(
    backup: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    systemd = Systemd({"full": fleet.ENABLED, "incr": fleet.ABSENT})
    monkeypatch.setattr(backup, "systemctl", systemd)
    assert run_verb(backup, "disable") == 0
    disables = [c for c in systemd.calls if c[0] == "disable"]
    assert [c[-1] for c in disables] == [backup_schedule.units(KEY)["full"]]
    assert "not installed" in capsys.readouterr().out


def test_the_wrapper_knows_the_verb() -> None:
    source = (REPO_ROOT / "bin" / "backup.sh").read_text(encoding="utf-8")
    assert "stanza-create | check | backup | info | expire | schedule)" in source
    assert "schedule status [--json]" in source
