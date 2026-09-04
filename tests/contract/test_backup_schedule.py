"""The four backup units, and the glob that installs them (D522, Session 10 Run 9).

D522 is a small row with a large shape: `provision-host.sh install_units` globbed
`systemd/*.service` only, so **a `.timer` placed in `systemd/` was installed by
nothing**. A schedule that is written and not installed is the same defect class
as a bound that is validated and not applied (D519), one layer up — and both
fail by looking finished.

So the assertions here are in both directions. The units exist and say what they
should; and the installer's glob would actually pick them up. The second half is
the one that was missing, and a test that only read the unit files would have
passed against the exact defect this row records.
"""

from __future__ import annotations

import configparser
import re

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SYSTEMD = REPO_ROOT / "systemd"
INSTALLER = (REPO_ROOT / "bin" / "provision-host.sh").read_text(encoding="utf-8")
LAUNCHER = (REPO_ROOT / "libexec" / "project-launcher").read_text(encoding="utf-8")

BACKUP_UNITS = (
    "agentic-postgres-backup-full@.service",
    "agentic-postgres-backup-full@.timer",
    "agentic-postgres-backup-incr@.service",
    "agentic-postgres-backup-incr@.timer",
)


def _install_units_glob() -> str:
    """The glob inside `install_units`, not the first `for origin in` in the file.

    `provision-host.sh` has more than one such loop -- an earlier one installs
    `libexec/agentic-postgres-*` -- so a search over the whole file reads the
    wrong one and reports that `install_units` globs no units at all. Found by
    this module's own first run, which is what naming your subject precisely
    is for.
    """
    body = INSTALLER.split("install_units() {", 1)
    assert len(body) == 2, "install_units() could not be found; this reads nothing"
    match = re.search(r"for origin in ([^\n]*?); do", body[1])
    assert match, "install_units has no glob loop; this test reads nothing"
    return match.group(1)


def read_unit(name: str) -> configparser.ConfigParser:
    """Parsed as the ini it is, not grepped.

    A `grep` for `OnCalendar` passes against a line inside a comment, and every
    unit in this repository is heavily commented.
    """
    # `interpolation=None`: systemd uses `%i` for the instance name and
    # configparser reads `%` as its own interpolation syntax, which turns
    # every `Unit=...@%i.service` into a mangled value or a parse error.
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    # systemd option names are case-sensitive; configparser lowercases by default.
    parser.optionxform = str  # type: ignore[method-assign]
    parser.read_string((SYSTEMD / name).read_text(encoding="utf-8"))
    return parser


@pytest.mark.parametrize("name", BACKUP_UNITS)
def test_the_unit_exists_and_parses(name: str) -> None:
    assert (SYSTEMD / name).is_file(), f"{name} is missing"
    read_unit(name)


def test_install_units_globs_timers_as_well_as_services() -> None:
    """The half of D522 that a unit-file test cannot see.

    Read off the installer's own glob rather than by running it: `install_units`
    writes into /etc/systemd/system and calls `systemctl daemon-reload`, neither
    of which belongs in a contract test. What can be read is whether the loop it
    iterates would ever reach a `.timer`.
    """
    globs = _install_units_glob()
    assert "systemd/*.service" in globs, globs
    assert "systemd/*.timer" in globs, (
        "install_units does not glob *.timer, so every timer in systemd/ is "
        f"installed by nothing -- which is D522 exactly. The loop reads: {globs}"
    )


def test_no_unit_in_the_directory_is_left_uninstallable() -> None:
    """The general form, so a fifth unit type cannot arrive unnoticed.

    The previous test names the two suffixes; this one asserts that the suffixes
    the glob covers are *all* the suffixes present. A `.socket` or `.path` added
    later would fail here rather than being silently skipped at provisioning
    time, which is how the timers got here.
    """
    covered = set(re.findall(r"systemd/\*(\.[a-z]+)", _install_units_glob()))
    present = {path.suffix for path in SYSTEMD.iterdir() if path.is_file()}
    assert present <= covered, (
        f"systemd/ holds {sorted(present - covered)} which install_units' glob does "
        "not cover, so those files are installed by nothing"
    )


def _check_units_glob() -> str:
    """The glob inside `--check`'s unit section, found by its own heading.

    The check function is long and its unit loop sits after the launcher and
    sudoers loops, so the search is anchored on the `== launchers and units ==`
    heading and the first `for origin in` after it. The install function has
    its own heading of the same text, so the FIRST heading is the check's only
    because `check_baseline` precedes `install_units` in the file; the
    assertion on ordering below keeps that from becoming a silent assumption.
    """
    first, _, rest = INSTALLER.partition("== launchers and units ==")
    assert rest, "the check's unit heading could not be found; this reads nothing"
    assert "install_units() {" not in first, "install_units precedes the check; the anchor moved"
    match = re.search(r"for origin in ([^\n]*?); do", rest)
    assert match, "the check has no glob loop over the units; this reads nothing"
    return match.group(1)


def test_the_check_reads_the_same_glob_the_installer_writes() -> None:
    """D970. `--check` listed three units by name and reported the baseline met
    on a host missing all four backup units: D522 widened the installer's glob
    and the checker kept a definition of its own. One source for both readers.
    The control is that the two globs come from two different functions --
    the anchors are distinct -- so this cannot pass by reading the installer
    twice."""
    installer = _install_units_glob()
    check = _check_units_glob()
    assert installer == check, (
        f"the installer globs {installer} and the check reads {check}; a unit the "
        "installer would write is one the check cannot miss only if they agree (D970)"
    )
    assert "systemd/*.timer" in check, "the check would not notice a missing timer (D944)"
    # Control: the two loops are different loops, not one text read twice.
    install_body = INSTALLER.split("install_units() {", 1)[1]
    assert 'bad "unit ' not in install_body, "the installer reports deviations; anchors crossed"
    assert (
        "install -m 0644" in install_body
        and "install -m 0644"
        not in (INSTALLER.partition("== launchers and units ==")[2].split("printf", 1)[0])
    )


def test_the_timers_are_installed_but_not_enabled() -> None:
    """The rule the edge and project units already follow, and its stated reason.

    Nothing can back up until a bucket exists, a token has been issued out of
    band and the first full backup has been taken by hand. A timer enabled before
    that fails on every boot, and *a unit that fails on every boot until the
    operator is ready trains an operator to ignore it.*
    """
    enabled = re.findall(r"systemctl enable ([^\s>]+)", INSTALLER)
    for name in BACKUP_UNITS:
        assert name not in enabled, (
            f"{name} is enabled at provisioning time, before any repository exists"
        )
    assert "agentic-postgres-docker-firewall.service" in enabled, (
        "no unit is enabled at all, so this test would pass against an installer "
        "that had stopped enabling anything"
    )


@pytest.mark.parametrize(
    ("timer", "service"),
    [
        ("agentic-postgres-backup-full@.timer", "agentic-postgres-backup-full@%i.service"),
        ("agentic-postgres-backup-incr@.timer", "agentic-postgres-backup-incr@%i.service"),
    ],
)
def test_each_timer_names_its_own_service_and_a_schedule(timer: str, service: str) -> None:
    """A timer whose `Unit=` names the wrong service is a schedule for something else."""
    parsed = read_unit(timer)
    assert parsed["Timer"]["Unit"] == service
    assert parsed["Timer"]["OnCalendar"].strip(), f"{timer} has no schedule"
    assert parsed["Timer"]["Persistent"] == "true", (
        f"{timer} is not Persistent, so a backup missed while the host was down is "
        "a backup that never happens"
    )
    assert parsed["Timer"]["RandomizedDelaySec"], (
        f"{timer} has no jitter, so two projects on one host start in the same "
        "second, on the same disk, over the same uplink"
    )
    assert parsed["Install"]["WantedBy"] == "timers.target"


def test_the_two_schedules_do_not_start_at_the_same_time() -> None:
    """An incremental starting during a full is two commands against one stanza.

    `backup_user` holds `CONNECTION LIMIT 2` (ADR 0148), of which the deploy's
    step 6c may already be using one — measured: a lone pgBackRest command holds
    1 and an overlapping pair holds 2 (D544). The gap is chosen rather than
    measured and the timer says so; what this asserts is only that there is one.
    """
    full = read_unit("agentic-postgres-backup-full@.timer")["Timer"]["OnCalendar"]
    incr = read_unit("agentic-postgres-backup-incr@.timer")["Timer"]["OnCalendar"]
    assert full != incr, "the full and incremental timers fire at the same moment"
    assert full.split()[-1] != incr.split()[-1], (
        f"the two timers name the same time of day ({full!r} vs {incr!r}); the full "
        "runs weekly and the incremental daily, so they would collide every week"
    )


@pytest.mark.parametrize(
    ("service", "action"),
    [
        ("agentic-postgres-backup-full@.service", "backup-full"),
        ("agentic-postgres-backup-incr@.service", "backup-incr"),
    ],
)
def test_each_service_reaches_the_release_through_the_trampoline(service: str, action: str) -> None:
    """The same seam `materialize`, `up` and `attach` travel (ADR 0037).

    The unit names the stable root-owned trampoline and an action; the trampoline
    validates `%i` against the project-key pattern and hands over to the
    *release's* launcher. A unit invoking `bin/backup.sh` directly would be a
    host-side file naming a path inside a release it may never have seen, which
    is D72 — a copy on the host still holding a literal three runs after it was
    fixed in the repository.
    """
    parsed = read_unit(service)
    start = parsed["Service"]["ExecStart"]
    assert start == f"/usr/local/libexec/agentic-postgres/project %i {action}", start
    # And the release's launcher actually knows the action, in both places it
    # has to: the validation case and the dispatch case.
    assert f"{action}" in LAUNCHER, f"the release launcher has no {action} action"
    assert re.search(r"backup-full\|backup-incr\)", LAUNCHER), (
        "the launcher's action validation does not admit the backup actions, so "
        "every timer firing would exit 2 with 'unknown action'"
    )


def test_the_scheduled_backup_checks_before_it_backs_up() -> None:
    """`check` is the only thing here that tests the archiver end to end.

    A timer that took a backup without it would keep writing to a repository the
    cluster had stopped archiving to — and `check` needs two privileges the
    backup itself does not (D541), so a run that backs up and fails its check is
    a real shape rather than a contradiction. It is the half that is supposed to
    notice.
    """
    dispatch = LAUNCHER.split("backup-full|backup-incr)")[-1].split(";;")[0]
    assert "check" in dispatch, "the scheduled backup does not run `check` first"
    assert dispatch.index("check") < dispatch.index("backup --type"), (
        "the scheduled action backs up before it checks, so a broken archiver is "
        "discovered after the repository has been written to"
    )
    # Retention is applied from the rendered config and is not restated on any
    # command line (D495, ADR 0149). A `--retention` here would be one value
    # stated twice, and the second statement would win.
    assert "retention" not in dispatch.lower(), (
        "the scheduled backup names a retention count, which the rendered config already sets"
    )
