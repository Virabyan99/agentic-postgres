"""The doctor's two READINGS (Session 31, NODE-READ-001, ADR 0221).

A reading is not a check. The twelve checks answer *is this deployment well*
and are allowed four verdicts; a reading answers *what is true of this node*
and is allowed two -- `OK` with the numbers, or `UNKNOWN` naming the figure it
could not read.

**The missing third and fourth verdicts are the subject of this module.** A
`WARN` at some percentage of memory used, or a `PROBLEM` at some disk
threshold, would be a number nobody has measured, invented inside the one
command that runs as root on production, and capable of failing a host that
works. That is exactly what `agent record` was corrected for in Session 30
(D1441, ADR 0213), and the correction is load-bearing here rather than
stylistic.

`usage`'s proofs land in Run 4, which is what builds it. What this module
asserts about `usage` today is that the verb is REFUSED rather than answered
-- a reading that returned `OK` having measured nothing would be the defect
this session exists to close, wearing the session's own uniform.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, capacity_probe, capacity_reading, diagnosis
from agentic_postgres.host_config import Declared

pytestmark = [pytest.mark.contract, pytest.mark.p0]

DOCTOR_PY = REPO_ROOT / "bin" / "doctor.py"
DOCTOR_SH = REPO_ROOT / "bin" / "doctor.sh"

DECLARED = Declared(memory_mb=3814, reserve_memory_mb=2214, disk_gb=38, reserve_disk_gb=8)


@pytest.fixture(scope="module")
def doctor() -> Any:
    """`bin/doctor.py` imported by path -- `bin/` is not a package."""
    spec = importlib.util.spec_from_file_location("_apg_doctor_under_test", DOCTOR_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reading(**overrides: object) -> capacity_reading.Reading:
    base: dict[str, object] = {
        "declared": DECLARED,
        "mem_total": capacity_reading.Figure.measured(3814),
        "mem_available": capacity_reading.Figure.measured(2182),
        "swap_total": capacity_reading.Figure.measured(0),
        "docker_root_free_gb": capacity_reading.Figure.measured(22),
        "docker_root_total_gb": capacity_reading.Figure.measured(37),
        "committed": {"alpha-dev": 304, "beta-dev": 304},
        "unreadable": {},
        "ceilings": {"alpha-dev": 2240, "beta-dev": 2240},
        "unbounded": (),
    }
    base.update(overrides)
    return capacity_reading.Reading(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Two verdicts, never four
# ---------------------------------------------------------------------------


def test_the_capacity_report_has_two_verdicts_only() -> None:
    """Every check, in both directions, is OK or UNKNOWN.

    Asserted over a healthy reading AND over one where every figure failed, so
    a report that simply never produced a verdict at all could not pass.
    """
    permitted = {diagnosis.OK, diagnosis.UNKNOWN}

    healthy = diagnosis.capacity_report(reading())
    assert healthy, "the report produced no checks, so this test measures nothing"
    assert {check.verdict for check in healthy} <= permitted

    why = "nothing could be read"
    blind = diagnosis.capacity_report(
        reading(
            declared=None,
            mem_total=capacity_reading.Figure.unknown(why),
            mem_available=capacity_reading.Figure.unknown(why),
            swap_total=capacity_reading.Figure.unknown(why),
            docker_root_free_gb=capacity_reading.Figure.unknown(why),
            docker_root_total_gb=capacity_reading.Figure.unknown(why),
            committed={},
            unreadable={"alpha-dev": "the deployed document could not be read"},
            ceilings={},
        )
    )
    assert {check.verdict for check in blind} <= permitted
    assert diagnosis.UNKNOWN in {check.verdict for check in blind}, (
        "the control: a reading that measured nothing must say so"
    )


def test_the_capacity_report_names_neither_warn_nor_problem() -> None:
    """A scan of the function's own source, not of its output.

    The verdict test above can only see the branches a fixture reaches. This
    reads the code, so a `WARN` behind a condition no test happens to trigger
    is still caught -- which is the shape D1441 arrived in: a threshold
    somebody added that nothing exercised.
    """
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(diagnosis.capacity_report)))
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    # The docstring is removed before the scan, and that is not a convenience.
    # It is the paragraph explaining WHY this function has no WARN, and a scan
    # that failed on it would be repaired by deleting the explanation --
    # leaving a guard that passes and a decision nobody can find the reason
    # for. `ast.unparse` drops comments too, for the same reason: a comment
    # cannot emit a verdict.
    if isinstance(function.body[0], ast.Expr) and isinstance(function.body[0].value, ast.Constant):
        function.body = function.body[1:]
    code = ast.unparse(function)

    assert "WARN" not in code, "a capacity reading may not warn (ADR 0221, D1441)"
    assert "PROBLEM" not in code, "a capacity reading may not report a problem"
    # The control: this scan can see the verdicts that ARE there, so it would
    # have seen a third one.
    assert "UNKNOWN" in code and "OK" in code, "the scan is reading the wrong thing"


def test_an_unreadable_figure_is_unknown_and_names_itself() -> None:
    """The reason travels with the figure, all the way to the operator."""
    report = diagnosis.capacity_report(
        reading(
            docker_root_free_gb=capacity_reading.Figure.unknown("`docker info` said nothing"),
            docker_root_total_gb=capacity_reading.Figure.unknown("`docker info` said nothing"),
        )
    )
    disk = next(check for check in report if check.name == "disk")
    assert disk.verdict == diagnosis.UNKNOWN
    assert "docker_root_free_gb" in disk.detail
    assert "docker info" in disk.detail

    memory = next(check for check in report if check.name == "memory")
    assert memory.verdict == diagnosis.OK, "only the figure that failed may be unknown"


def test_an_undeclared_capacity_is_unknown_rather_than_a_default() -> None:
    """A schema 2 host has declared nothing, and the report says so.

    Not zero, and not a number measured off the host and presented as a
    declaration -- that substitution is the exact fold ADR 0195 forbids.
    """
    report = diagnosis.capacity_report(reading(declared=None))
    declared = next(check for check in report if check.name == "declared")
    assert declared.verdict == diagnosis.UNKNOWN
    assert "schema 2" in declared.detail


def test_a_project_whose_claim_is_unreadable_makes_the_total_not_a_total() -> None:
    """The committed sum is either complete or it is not a sum."""
    report = diagnosis.capacity_report(
        reading(committed={"alpha-dev": 304}, unreadable={"beta-dev": "permission denied"})
    )
    committed = next(check for check in report if check.name == "committed")
    assert committed.verdict == diagnosis.UNKNOWN
    assert "beta-dev" in committed.detail


def test_the_ceilings_are_reported_as_ceilings() -> None:
    """The single most misleading number on this host, labelled (D767).

    The six caps sum to 2240 MiB per project against 3814 MiB of RAM. An
    operator who read that as a reservation would conclude the host is
    catastrophically oversubscribed; what it means is that a cap is a ceiling.
    """
    report = diagnosis.capacity_report(reading())
    ceilings = next(check for check in report if check.name == "ceilings")
    assert ceilings.verdict == diagnosis.OK
    assert "ceiling" in ceilings.detail.lower()
    assert "D767" in ceilings.detail


def test_the_ceilings_line_says_by_compose_project() -> None:
    """The keys changed meaning, so the line has to say which question it answers.

    Session 32 regrouped the reading from `apg.project.key` to Compose's own
    project label (D1636, ADR 0221), which is what puts the database's 768 MiB
    back in the sum. An operator comparing this figure against Session 31's
    sheet -- where it read 2,944 MiB and the true sum was 4,480 -- must be able
    to tell the two readings apart from the line itself.
    """
    report = diagnosis.capacity_report(reading())
    ceilings = next(check for check in report if check.name == "ceilings")
    assert "by compose project" in ceilings.detail, ceilings.detail
    assert "D767" in ceilings.detail, "the ceilings-are-not-reservations warning was lost"


def test_the_evidence_is_only_values_this_program_produced() -> None:
    """ADR 0159: no third party's bytes reach a report.

    Every evidence value is a number this process computed or a word from its
    own vocabulary -- never a line of `docker info`'s output, and never a path
    under the secret root.
    """
    report = diagnosis.capacity_report(reading())
    for check in report:
        for name, value in check.evidence:
            assert "/" not in value or value == "null", (
                f"{check.name}.{name} carries something path-shaped: {value!r}"
            )


# ---------------------------------------------------------------------------
# The verb, and what it does not disturb
# ---------------------------------------------------------------------------


def run_doctor_py(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(DOCTOR_PY), *argv],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_doctor_sh_maps_the_capacity_word_to_the_reading() -> None:
    """The shell turns a verb into `--reading`, and nothing else does.

    Read out of the script rather than executed, because executing it needs
    root. The execution half is the trip's (`admission_live`).
    """
    source = DOCTOR_SH.read_text(encoding="utf-8")
    assert "capacity|usage) reading=" in source.replace('"$1"', "$1").replace("  ", " ") or (
        "capacity|usage)" in source
    ), "the verb arm is gone, so nothing maps a verb to a reading"
    assert "--reading" in source
    assert 'argv=("${ROOT_DIR}/bin/doctor.py" --reading "${verb}")' in source


def test_the_capacity_verb_documents_itself_and_needs_no_root_to_say_so() -> None:
    """DX-002 one level down (D1395): `--help` is a read.

    A verb that demanded root to print its own usage is the failure seven
    verbs in three commands had before Session 24 found it.
    """
    result = subprocess.run(
        ["bash", str(DOCTOR_SH), "capacity", "--help"],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "capacity" in result.stdout
    assert "--host" in result.stdout


def test_doctor_with_no_verb_runs_the_twelve_checks_unchanged(tmp_path: Path) -> None:
    """The regression that would be quietest.

    `bin/fleet.py` and `rehearsal._doctor` both invoke `doctor.py --project KEY
    --json` and neither knows a verb exists. If adding `--reading` had made
    `--project` conditional in a way that broke the bare form, the fleet
    inventory and every rehearsal would fail somewhere else entirely.

    Run without root, so it gets as far as the document and stops -- which is
    enough to prove the argument parsing still reaches the twelve checks
    rather than a usage error.
    """
    result = run_doctor_py(
        "--project", "no-such-project", "--root", str(tmp_path / "apg-nonexistent-root")
    )
    assert result.returncode != 2, (
        f"the bare form now fails as bad INPUT, which is the regression: {result.stderr}"
    )


def test_the_capacity_reading_refuses_without_a_host_manifest() -> None:
    """It cannot report a declaration without the file that declares it."""
    result = run_doctor_py("--reading", "capacity")
    assert result.returncode == 2
    assert "--host" in result.stderr


def test_host_without_a_reading_is_refused_rather_than_ignored() -> None:
    """A flag that silently does nothing is how an operator comes to believe
    they asked for something they did not."""
    result = run_doctor_py("--host", "host.example.yaml", "--project", "alpha-dev")
    assert result.returncode == 2
    assert "--host" in result.stderr


def test_the_usage_verb_needs_a_project_and_then_reads_its_document() -> None:
    """Run 2 asserted this verb REFUSED; Run 4 built it, so the proof moves.

    With no `--project` it is bad input (2). With one, it goes looking for
    that project's deployed document and reports the state it found -- 4 when
    the document is not there, which on this workstation is the honest answer
    and on the host is root's to read (D1606). What it must never do is
    return `OK` having measured nothing.
    """
    without = run_doctor_py("--reading", "usage")
    assert without.returncode == 2
    assert "--project" in without.stderr

    with_project = run_doctor_py(
        "--reading", "usage", "--project", "no-such-project", "--root", "/nonexistent-root"
    )
    assert with_project.returncode == 4, with_project.stderr
    assert with_project.stdout.strip() == "", (
        "a usage reading printed a report for a project it never found"
    )


def test_the_probe_reads_meminfo_directly_rather_than_through_a_container(
    tmp_path: Path,
) -> None:
    """A figure read inside a cgroup answers a different question.

    `mem_limit` is what a container may use; this reading is about what the
    machine HAS. The probe takes a path so the substitution is visible here.

    It lives in `capacity_probe` rather than in the doctor because `admit` and
    the deploy's step 0 need the same reading and a `bin/` command may not
    import another (ADR 0093). One probe, three runners.
    """
    parsed = capacity_probe.read_meminfo(Path("/proc/meminfo"))
    assert parsed is None or set(parsed) == {"MemTotal", "MemAvailable", "SwapTotal"}

    assert capacity_probe.read_meminfo(tmp_path / "apg-no-such-meminfo") is None


def test_the_three_commands_share_one_probe_and_one_parser() -> None:
    """§7 question 5, asserted rather than trusted.

    `doctor capacity`, `admit` and the deploy all decide from the same reading.
    If each spelled its own, a repair that reached one would be invisible in
    the others until a deploy admitted something the doctor had refused.
    """
    import re

    readers = {
        "bin/doctor.py": "capacity_probe.read",
        "bin/admit.py": "capacity_probe.read",
        "bin/deploy-project.py": "capacity_probe.read",
    }
    missing = []
    for relative, call in readers.items():
        path = REPO_ROOT / relative
        if not path.is_file():
            missing.append(f"{relative} does not exist")
            continue
        if call not in path.read_text(encoding="utf-8"):
            missing.append(f"{relative} does not call {call}")
    assert not missing, missing

    # The control: none of the three re-implements the parse. `parse_meminfo`
    # is the library's, and a second `MemAvailable` split in `bin/` would be
    # the copy that drifts.
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in sorted((REPO_ROOT / "bin").glob("*.py"))
        if re.search(r"MemAvailable|/proc/meminfo", path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"these parse meminfo themselves instead of using the library: {offenders}"
    )


def test_an_unlistable_project_root_is_undetermined_rather_than_empty(
    doctor: Any, tmp_path: Path
) -> None:
    """Found by running the reading, and it is the sharpest case in the module.

    With a root it cannot list, an earlier version reported `committed 0 MiB
    across 0 projects` with verdict `ok` -- and `decide` would then have
    handed a candidate the entire declared budget on the strength of a
    directory it failed to open. The claims of projects this command cannot
    see are not zero.
    """
    missing = tmp_path / "not-a-root"
    result = doctor.probe_capacity(REPO_ROOT / "host.example.yaml", missing, exclude=None)

    assert result.committed == {}
    assert result.unreadable, "an unlistable root reported an empty, confident sum"

    decision = capacity_reading.decide(
        result,
        candidate_key="gamma-dev",
        candidate_unreclaimable_mb=1,
        candidate_is_deployed=False,
    )
    assert decision.outcome == "refused", "a decision on an unread root must fail closed"


# ---------------------------------------------------------------------------
# The disk figure, and the path it was actually read from
# ---------------------------------------------------------------------------


def test_the_disk_figure_is_measured_from_the_nearest_readable_ancestor(
    tmp_path: Path,
) -> None:
    """A rule nothing can satisfy is not a rule.

    `decide` fails closed on an undetermined disk figure, which is right --
    and the figure was being read with a bare `disk_usage(docker_root)`.
    `/var/lib/docker` **does not exist** under Docker Desktop (the daemon
    reports a path inside its own VM) and is 0710 root on a CI runner, so that
    read fails unprivileged in both places and every admission would have been
    refused for a reason that has nothing to do with capacity. It would have
    been found on the host, during a trip.

    Measuring the same filesystem from an ancestor answers the same question;
    substituting a number would not. So the path is returned with the figure.
    """
    deep = tmp_path / "a" / "b" / "c" / "does-not-exist"
    usage, measured_at = capacity_probe.disk_usage_near(str(deep))

    assert usage is not None, "nothing on the way up could be stat'd"
    assert measured_at, "the figure came back without saying where it was measured"
    assert Path(measured_at).exists()
    assert str(tmp_path) in measured_at or measured_at == "/"
    assert usage.total > 0


def test_a_readable_docker_root_is_measured_at_itself(tmp_path: Path) -> None:
    """The control.

    Without it, a walk that ALWAYS climbed to `/` would pass the test above
    while never once measuring the path it was asked about.
    """
    usage, measured_at = capacity_probe.disk_usage_near(str(tmp_path))
    assert usage is not None
    assert measured_at == str(tmp_path), (
        f"a readable path was measured at {measured_at!r} instead of itself"
    )


def test_the_measured_path_is_printed_when_a_decision_is_taken() -> None:
    """An operator must be able to see which disk was measured.

    If the Docker root were its own mount, an ancestor describes a different
    filesystem -- and then the honest thing is a visible path rather than a
    plausible number (ADR 0195).
    """
    from agentic_postgres.host_config import Declared

    declared = Declared(memory_mb=3814, reserve_memory_mb=2214, disk_gb=38, reserve_disk_gb=8)
    measured = capacity_reading.Reading(
        declared=declared,
        mem_total=capacity_reading.Figure.measured(3814),
        mem_available=capacity_reading.Figure.measured(2182),
        swap_total=capacity_reading.Figure.measured(0),
        docker_root_free_gb=capacity_reading.Figure.measured(22),
        docker_root_total_gb=capacity_reading.Figure.measured(37),
        committed={"alpha-dev": 304},
        unreadable={},
        ceilings={},
        unbounded=(),
        docker_root_measured_at="/var/lib",
    )
    decision = capacity_reading.decide(
        measured,
        candidate_key="gamma-dev",
        candidate_unreclaimable_mb=304,
        candidate_is_deployed=False,
    )
    rendered = capacity_reading.render_decision(decision)
    assert "disk measured at" in rendered
    assert "/var/lib" in rendered


def test_the_reading_also_names_the_filesystem_it_measured() -> None:
    """**The decision said where; the reading did not.** (Run 6.)

    `decide` prints `disk measured at <path>` because the probe walks up from
    the Docker data root to the nearest point it can stat (D1611) and an
    ancestor can be a different mount from the one the daemon writes to.
    `capacity_report` reported the same two figures -- free and total GiB --
    and said nothing about their subject, so `apg doctor capacity` handed an
    operator a number they had no way to check against `df`.

    Found by writing `test_capacity_agrees_with_free_and_df_on_this_host`,
    whose control has to point `df` at the path the reading actually used: the
    alternative is hardcoding `/var/lib/docker` in the proof, which is the
    assumption D1611 took OUT of the product.

    Goes red if the evidence loses the member, and the arm below goes red if
    it is invented when nothing could be stat'd -- an empty path reported as a
    path would be worse than no path at all.
    """
    from agentic_postgres.host_config import Declared

    declared = Declared(memory_mb=3814, reserve_memory_mb=2214, disk_gb=38, reserve_disk_gb=8)

    def reading_at(measured_at: str) -> capacity_reading.Reading:
        return capacity_reading.Reading(
            declared=declared,
            mem_total=capacity_reading.Figure.measured(3814),
            mem_available=capacity_reading.Figure.measured(2182),
            swap_total=capacity_reading.Figure.measured(0),
            docker_root_free_gb=capacity_reading.Figure.measured(22),
            docker_root_total_gb=capacity_reading.Figure.measured(37),
            committed={"alpha-dev": 304},
            unreadable={},
            ceilings={},
            unbounded=(),
            docker_root_measured_at=measured_at,
        )

    disk = {check.name: check for check in diagnosis.capacity_report(reading_at("/var/lib"))}[
        "disk"
    ]
    evidence = dict(disk.evidence)
    assert evidence.get("measured_at") == "/var/lib", (
        "the disk check does not say which filesystem produced its figures, so "
        f"nothing can check them against df: {evidence}"
    )

    # And when nothing on the way up could be stat'd there is no path to name.
    # A path invented here would be the fold ADR 0195 forbids, reported as a
    # fact an operator would go and check.
    nowhere = {check.name: check for check in diagnosis.capacity_report(reading_at(""))}["disk"]
    assert "measured_at" not in dict(nowhere.evidence), (
        f"a path was reported for a reading that measured nothing: {dict(nowhere.evidence)}"
    )


# ---------------------------------------------------------------------------
# Session 31 Run 4 -- the usage reading (NODE-USAGE-001)
# ---------------------------------------------------------------------------


def figures(**overrides: object) -> capacity_reading.UsageFigures:
    base: dict[str, object] = {
        name: capacity_reading.Figure.measured(1) for name in capacity_reading.USAGE_FIGURE_UNITS
    }
    base.update(overrides)
    return capacity_reading.UsageFigures(**base)  # type: ignore[arg-type]


def test_the_usage_report_has_two_verdicts_only() -> None:
    """OK with the numbers, or UNKNOWN naming the figure. Never four."""
    permitted = {diagnosis.OK, diagnosis.UNKNOWN}

    healthy = diagnosis.usage_report(figures(), units=capacity_reading.USAGE_FIGURE_UNITS)
    assert healthy, "the report produced no checks"
    assert {check.verdict for check in healthy} == {diagnosis.OK}

    why = "nothing answered"
    blind = diagnosis.usage_report(
        figures(
            **{
                name: capacity_reading.Figure.unknown(why)
                for name in capacity_reading.USAGE_FIGURE_UNITS
            }
        ),
        units=capacity_reading.USAGE_FIGURE_UNITS,
    )
    assert {check.verdict for check in blind} <= permitted
    assert {check.verdict for check in blind} == {diagnosis.UNKNOWN}


def test_no_usage_figure_carries_a_threshold() -> None:
    """A scan of the code, not of the output (D1441).

    No size or count here has a measured value at which this deployment is
    unwell, and `doctor` runs as root on production.
    """
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(diagnosis.usage_report)))
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    if isinstance(function.body[0], ast.Expr) and isinstance(function.body[0].value, ast.Constant):
        function.body = function.body[1:]
    code = ast.unparse(function)

    assert "WARN" not in code
    assert "PROBLEM" not in code
    assert "UNKNOWN" in code and "OK" in code, "the scan is reading the wrong thing"


def test_half_a_group_is_not_a_group() -> None:
    """A group with one unreadable figure is UNKNOWN, and names it.

    Two of three sizes is not a size. Reporting the two that came back as a
    healthy line would be the fold ADR 0195 forbids, and it is the shape an
    operator would never notice.
    """
    report = diagnosis.usage_report(
        figures(wal_kb=capacity_reading.Figure.unknown("du printed nothing")),
        units=capacity_reading.USAGE_FIGURE_UNITS,
    )
    database = next(check for check in report if check.name == "database")
    assert database.verdict == diagnosis.UNKNOWN
    assert "wal_kb" in database.detail
    assert "du printed nothing" in database.detail

    others = [check for check in report if check.name != "database"]
    assert {check.verdict for check in others} == {diagnosis.OK}, (
        "one unreadable figure took down a group it does not belong to"
    )


def test_storage_objects_is_not_a_usage_figure() -> None:
    """D1601, asserted rather than left as an absence.

    The object listing is reachable only through the credential the storage
    container alone holds, and a second holder of that credential is this
    stage's declared failure mode. A member reported `unknown` forever would
    be a field with no reader (D816), so it is absent by decision.
    """
    assert "storage_objects" not in capacity_reading.USAGE_FIGURE_UNITS
    assert not hasattr(capacity_reading.UsageFigures, "storage_objects")


def test_every_usage_figure_has_a_unit() -> None:
    """A number whose unit lives only in its name is a number to guess about."""
    assert set(capacity_reading.USAGE_FIGURE_UNITS) == set(figures().as_mapping())
    assert all(unit for unit in capacity_reading.USAGE_FIGURE_UNITS.values())


def test_doctor_sh_maps_the_usage_word_to_the_reading() -> None:
    source = DOCTOR_SH.read_text(encoding="utf-8")
    assert "capacity|usage)" in source
    assert "usage --project" in source


def test_the_store_query_sums_across_instances(doctor: Any) -> None:
    """`sum(...)`, because `instance` is a fresh UUID per process (D1609).

    The exporter promotes the SDK's `service.instance.id` onto every series,
    so each restart of the mcp container mints a new one. Reading a single
    series would undercount silently after any restart -- D553's shape in a
    new disguise.
    """
    for query in doctor.STORE_QUERIES.values():
        assert query.startswith("sum("), query
    assert set(doctor.STORE_QUERIES) == {"requests_total", "tool_calls_total"}
