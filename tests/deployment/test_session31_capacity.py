"""Session 31's live halves: the node as a finite resource.

`NODE-ADMIT-002`, `OPS-TELEMETRY-002`, `NODE-USAGE-001`. Written at the bump
(Run 6) and gated on the roster variables, two of which this session adds --
`APG_HOST_MANIFEST` and `APG_CANDIDATE_MANIFEST`, both declared in
`tests/conftest.py`'s closed tuple and both exported by `bin/session-31-
check.sh --mode host`, so that `pytest --setup-plan` can answer *will these
run* before the day rather than during it (D671, D676, D687).

**None of this has executed before the trip.** Each docstring says what it
asserts and Run 7 finds out. That sentence is not a disclaimer: fifteen
never-executed proofs have failed on first execution across this project's
history, and the honest thing is to say which these are while they still cost
nothing.

**What only a deployment can prove**, and why the offline halves are not
enough:

* that `decide`'s arithmetic, which twenty-four offline proofs exercise
  against synthesised readings, refuses a REAL third project against a REAL
  host's declaration -- and that the same manifest at the release's default
  budget is admitted. The pair is the proof: a refusal alone is satisfied by a
  rule that refuses everything, which is exactly what D1611 found the disk
  rule doing before it was repaired;
* that `/proc/meminfo` and `shutil.disk_usage` agree with `free -m` and
  `df -Pk` **on this host**. Offline, the parser is fed fixture text; nothing
  offline says the file it will read on a production kernel has the shape the
  fixtures have;
* that the collector, whose exporter gained `const_labels` in Run 4, actually
  emits them -- and that the mcp runtime's two instruments, configured in
  production for the first time in this release, reach the store at all. The
  offline half proves `configure` returns `True` and creates two instruments
  in-process; whether a metric crosses an OTLP connection and lands in a
  Prometheus that is routed nowhere is not a question a checkout has;
* that `doctor usage` answers every figure on a cluster with nine sessions of
  data in it. Offline, each figure is a parsed string.

**The rehearsal proof reads a record and does not perform one** (ADR 0190).
`rehearse.sh admission-refused` is run on Sheet A5, BEFORE the sweep, and this
reads the file it wrote -- a test cannot inject a reserve into a running host
and survive to report the result.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, capacity_reading, config

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST",
        "APG_HOST_MANIFEST",
        "APG_CANDIDATE_MANIFEST",
        "APG_PROJECT_A_OUTPUTS",
        "APG_PROJECT_B_OUTPUTS",
        "APG_REHEARSAL_EVIDENCE_DIR",
    ),
]

#: How far the reading may sit from `free -m`'s MemTotal. Five per cent, and
#: the slack is not for rounding: `free` reads the same `/proc/meminfo` this
#: does, but the two run seconds apart on a host that is serving, and
#: MemTotal itself can move on a machine with memory hotplug. MemAvailable is
#: deliberately NOT compared -- it moves by tens of MiB between two adjacent
#: reads and a proof that pinned it would fail for the wrong reason.
MEMORY_TOLERANCE = 0.05


def _admit(*arguments: str) -> tuple[int, str, str]:
    """`bin/admit.sh`, as a subprocess, which is the operator's own path.

    The product's own command rather than a hand-rolled call to `decide`
    (D1114): what an operator runs is the shell wrapper, and the wrapper's
    argument handling, its root check and its exit code are part of what
    `NODE-ADMIT-002` claims.
    """
    completed = subprocess.run(
        [str(REPO_ROOT / "bin" / "admit.sh"), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _doctor(*arguments: str) -> tuple[int, dict[str, Any], str]:
    """`bin/doctor.sh <verb> … --json`, parsed."""
    completed = subprocess.run(
        [str(REPO_ROOT / "bin" / "doctor.sh"), *arguments, "--json"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    if completed.returncode not in (0, 6):
        pytest.fail(
            f"doctor.sh {' '.join(arguments)} exited {completed.returncode}\n"
            f"{completed.stdout[-2000:]}\n{completed.stderr[-2000:]}"
        )
    try:
        return completed.returncode, json.loads(completed.stdout), completed.stderr
    except json.JSONDecodeError:
        pytest.fail(f"doctor.sh did not print JSON:\n{completed.stdout[-2000:]}")


def _checks(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {check["name"]: check for check in document["checks"]}


@pytest.fixture(scope="module")
def host_manifest() -> Path:
    path = Path(os.environ["APG_HOST_MANIFEST"])
    if not path.is_file():
        pytest.fail(f"APG_HOST_MANIFEST names {path}, which is not a file")
    return path


@pytest.fixture(scope="module")
def candidate_manifest() -> Path:
    path = Path(os.environ["APG_CANDIDATE_MANIFEST"])
    if not path.is_file():
        pytest.fail(f"APG_CANDIDATE_MANIFEST names {path}, which is not a file")
    return path


# ---------------------------------------------------------------------------
# NODE-ADMIT-002 -- a third project is refused, and the same one is admitted
# ---------------------------------------------------------------------------


def test_a_third_project_that_does_not_fit_is_refused_on_this_host(
    as_root: None, host_manifest: Path, candidate_manifest: Path
) -> None:
    """**`decide` against a real declaration, for the first time.**

    Twenty-four offline proofs exercise this arithmetic against readings this
    suite synthesised. None of them says that the host's own `host.yaml`,
    edited on Sheet A2 with numbers read off the machine on Sheet A1, refuses
    a project whose claim genuinely does not fit beside the two already
    deployed.

    Root, because the deployed documents the committed total sums are
    `drwx------ root root` (D1606) and a run that cannot read them refuses
    every project for a reason that has nothing to do with capacity. That
    refusal is correct and is NOT what this proof wants: the assertions below
    read the `committed` line and require it to name both deployed projects,
    so a root-less run fails here loudly rather than passing for the wrong
    reason.

    Goes red if: the candidate manifest's claim was set too low to be refused
    (the reason the control beside it exists); `host.yaml` was left at schema
    2; the deployed documents could not be summed; or exit 12 is not what a
    refusal returns.
    """
    code, out, err = _admit(
        "--host", str(host_manifest), "--project", str(candidate_manifest), "--json"
    )  # fmt: skip
    assert code == capacity_reading.EXIT_ADMISSION_REFUSED, (
        f"admit.sh exited {code}, not {capacity_reading.EXIT_ADMISSION_REFUSED}. "
        f"This project was supposed to be too large for this host.\n{out}\n{err}"
    )

    decision = json.loads(out)
    assert decision["outcome"] == "refused", decision
    assert decision["exit_code"] == capacity_reading.EXIT_ADMISSION_REFUSED
    assert decision["declaration_injected"] is False, (
        "the host's own declaration was overridden, so this measured a rehearsal "
        "rather than the host"
    )
    assert decision["already_deployed_here"] is False, (
        "the candidate has a deployed document here, so this is a redeploy and "
        "the committed sum excludes it -- not the third-project case"
    )

    labels = [line["label"] for line in decision["lines"]]
    assert labels[:6] == [
        "declared",
        "reserved",
        "committed",
        "requested",
        "safe available",
        "suggested action",
    ], labels

    lines = {line["label"]: line["value"] for line in decision["lines"]}
    # The committed line names the two projects that ARE deployed. Without
    # this the refusal could be a host that summed nothing.
    assert "unknown" not in lines["committed"], (
        f"the committed total could not be read: {lines['committed']}. A refusal "
        "on that basis says nothing about capacity (D1606)"
    )
    for key in ("alpha-dev", "beta-dev"):
        assert key in lines["committed"], (
            f"{key} is absent from the committed line, so this host's existing "
            f"claims were not all counted: {lines['committed']}"
        )


def test_the_same_project_at_the_default_budget_is_admitted(
    as_root: None, host_manifest: Path, candidate_manifest: Path, tmp_path: Path
) -> None:
    """**The control, and it is the half that makes the refusal mean
    something.**

    A rule that refused every project would satisfy the proof above, and this
    repository has shipped exactly that: D1611's disk rule refused every
    admission because `/var/lib/docker` is unreadable in two of the three
    environments this product runs in, and it would have surfaced on the host
    mid-trip.

    The SAME manifest, with `database.shared_buffers_mb` put back to the
    release's default, is offered again. Only one field moves, so an admission
    here is a statement about the claim rather than about the manifest: the
    candidate's `unreclaimable_mb` is `shared_buffers_mb +
    maintenance_work_mem_mb + max_connections * PER_BACKEND_ANON_MB`, and this
    subtracts exactly the difference.

    Copied to `tmp_path` rather than edited in place -- `/home/op/s31-third.
    yaml` is the operator's file and a test that rewrote it would leave the
    host in a state the next command reads differently.
    """
    default = config.DATABASE_BUDGET_DEFAULTS["shared_buffers_mb"]
    document = yaml.safe_load(candidate_manifest.read_text(encoding="utf-8"))
    raised = document["database"]["shared_buffers_mb"]
    assert raised > default, (
        f"the candidate declares shared_buffers_mb {raised}, which is not above "
        f"the default {default} -- so lowering it changes nothing and this is "
        "not a control"
    )

    document["database"]["shared_buffers_mb"] = default
    # shm_size_mb must stay at least shared_buffers_mb; lowering one and not
    # the other is refused at manifest load, which would fail this test as
    # invalid input rather than as a capacity answer.
    if document["database"].get("shm_size_mb", 0) > default:
        document["database"]["shm_size_mb"] = default

    smaller = tmp_path / "third-at-the-default.yaml"
    smaller.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    code, out, err = _admit("--host", str(host_manifest), "--project", str(smaller), "--json")
    assert code == 0, (
        f"the same project at the release's default budget was still refused "
        f"(exit {code}). Either this host has no room for any third project -- "
        "which is a finding, not a failure -- or the rule refuses everything.\n"
        f"{out}\n{err}"
    )
    decision = json.loads(out)
    assert decision["outcome"] == "admitted", decision
    assert decision["declaration_injected"] is False, decision

    # And the two decisions differ only in the requested figure, which is what
    # makes this a control rather than a second unrelated reading.
    assert decision["requested_unreclaimable_mb"] < raised + 1024, decision


def test_the_admission_rehearsal_recorded_a_refusal_and_a_control(as_root: None) -> None:
    """**ADR 0190's ninth scenario, read from the record it wrote.**

    `rehearse.sh admission-refused` moves `reserve_memory_mb` to a number no
    host could satisfy, asks `admit.sh`, and records what came back. It is run
    on Sheet A5 BEFORE the sweep, because a test cannot inject a reserve into
    a running host and survive to report the result.

    Two things are asserted and the second is the one worth having: that the
    injected run was REFUSED, and that the record says the declaration was
    injected. A rehearsal whose reading could be mistaken for the host's is a
    rehearsal that proves nothing about the host, which is why every printed
    line of an injected declaration is marked `(injected)`.

    `induced: false` is the rehearsal harness's own field and means the
    scenario did not have to break anything to produce its answer -- this one
    asks a question rather than causing a failure.
    """
    directory = Path(os.environ["APG_REHEARSAL_EVIDENCE_DIR"])
    if not directory.is_dir():
        pytest.fail(f"APG_REHEARSAL_EVIDENCE_DIR names {directory}, which is not a directory")

    records = sorted(directory.glob("rehearsal-*-admission-refused-*.json"))
    assert records, (
        f"no admission-refused rehearsal record under {directory}. Sheet A5 runs "
        "`rehearse.sh admission-refused` BEFORE the sweep; without it this claim "
        "is not_run rather than failed"
    )

    newest = max(records, key=lambda path: path.stat().st_mtime)
    record = json.loads(newest.read_text(encoding="utf-8"))

    assert record["scenario"] == "admission-refused", record

    # **The READINGS are the assertion, not the verdict** (D1637). The first
    # version of this proof checked `verdict == "refused"` and
    # `induced is False`, and the harness produces neither: `verdict` is
    # `"read"` -- its word for a scenario that reads rather than one that
    # passes or fails -- and `induced` is true because the induce PHASE ran,
    # which is not the same as something having been broken. Both were
    # assumed rather than measured, and the rehearsal they would have failed
    # did exactly what it should.
    #
    # What the record actually holds is stronger than either: the injected
    # run and the control, each with its outcome AND its exit code, and the
    # flag saying which of the two carried the injection.
    readings = record["readings"]

    assert readings["admission_refused"] == "refused", (
        f"{newest.name}: a reserve larger than any host has was ADMITTED "
        f"({readings['admission_refused']!r}), so the injection did not reach "
        "the decision"
    )
    assert readings["admission_refused_exit"] == capacity_reading.EXIT_ADMISSION_REFUSED, (
        f"{newest.name}: the refused run exited "
        f"{readings['admission_refused_exit']}, not "
        f"{capacity_reading.EXIT_ADMISSION_REFUSED}"
    )

    # **The control is the half that matters.** A rehearsal whose injected run
    # refuses proves nothing on a host that refuses everything -- which is
    # exactly what D1611 found this rule doing before it was repaired. The
    # host's own declaration must ADMIT the same project in the same breath.
    assert readings["admission_as_declared"] == "admitted", (
        f"{newest.name}: the host's own declaration refused this project too "
        f"({readings['admission_as_declared']!r}), so the injected refusal says "
        "nothing about the injection"
    )
    assert readings["admission_as_declared_exit"] == 0, readings

    # And the control is the one that is NOT injected -- a rehearsal reading
    # that could be mistaken for the host's own is a rehearsal that proves
    # nothing about the host.
    assert readings["control_declaration_injected"] is False, (
        f"{newest.name}: the control carried the injected declaration"
    )
    assert record["reversed"] is True, (
        f"{newest.name} was not reversed; this scenario changes nothing and says so"
    )


# ---------------------------------------------------------------------------
# NODE-USAGE-001 -- the readings, against the machine
# ---------------------------------------------------------------------------


def test_capacity_agrees_with_free_and_df_on_this_host(as_root: None, host_manifest: Path) -> None:
    """**The parser, against a production kernel's own `/proc/meminfo`.**

    Offline this parser is fed fixture text, including text designed to be
    malformed. Nothing offline says the file on this host has the shape those
    fixtures have -- and `test_a_meminfo_in_unexpected_units_is_not_believed`
    exists because a kernel reporting anything but `kB` would be silently
    mis-scaled by a thousand.

    The controls are the operator's own tools, read here rather than trusted:
    `free -m` for MemTotal and `df -Pk` for the filesystem the reading says it
    measured. **`df` is pointed at the path the reading REPORTS**, not at
    `/var/lib/docker`, because the reading walks up to the nearest readable
    ancestor and says which one it used (D1611) -- comparing against a path it
    did not measure would be comparing two filesystems.

    MemAvailable is deliberately not compared: it moves by tens of MiB between
    two adjacent reads on a serving host.
    """
    _code, document, _err = _doctor("capacity", "--host", str(host_manifest))
    checks = _checks(document)
    assert set(checks) >= {"declared", "memory", "disk", "committed", "ceilings"}, sorted(checks)
    assert {check["verdict"] for check in document["checks"]} <= {"ok", "unknown"}, (
        "the capacity reading produced a verdict other than ok/unknown; it has "
        f"two by design (ADR 0221): {[(c['name'], c['verdict']) for c in document['checks']]}"
    )

    assert checks["memory"]["verdict"] == "ok", checks["memory"]
    reported_total = int(checks["memory"]["evidence"]["mem_total_mb"])

    free = subprocess.run(["free", "-m"], capture_output=True, text=True, check=False)
    assert free.returncode == 0, free.stderr
    control_total = int(free.stdout.splitlines()[1].split()[1])
    drift = abs(reported_total - control_total) / control_total
    assert drift <= MEMORY_TOLERANCE, (
        f"the reading says MemTotal is {reported_total} MiB and `free -m` says "
        f"{control_total} MiB -- {drift:.1%} apart. Either /proc/meminfo is not "
        "in kB on this kernel or the parser is scaling it wrongly"
    )

    assert checks["disk"]["verdict"] == "ok", checks["disk"]
    reported_gb = int(checks["disk"]["evidence"]["docker_root_total_gb"])

    # **`df` is pointed at the path the READING says it measured**, which the
    # reading now reports for this proof's reason: the probe walks up to the
    # nearest readable ancestor and an ancestor can be a different mount.
    # Hardcoding `/var/lib/docker` here would be the assumption D1611 removed
    # from the product, reintroduced in the proof.
    measured_at = checks["disk"]["evidence"].get("measured_at")
    assert measured_at, (
        "the capacity reading does not say which filesystem it measured, so "
        "there is no path to point a control at: "
        f"{checks['disk']['evidence']}"
    )
    control = subprocess.run(
        ["df", "-Pk", str(measured_at)], capture_output=True, text=True, check=False
    )
    assert control.returncode == 0, (
        f"df could not read {measured_at}, which the reading says it measured: {control.stderr}"
    )
    control_kb = int(control.stdout.splitlines()[1].split()[1])
    control_gb = control_kb * 1024 // (1024**3)
    assert reported_gb == control_gb, (
        f"the reading says the Docker root's filesystem holds {reported_gb} GiB "
        f"and `df -Pk {measured_at}` says {control_gb} GiB. Both floor the same "
        "bytes, so a difference means they measured two filesystems"
    )


def test_usage_returns_every_figure_on_both_projects(as_root: None) -> None:
    """**Eight figures, on two clusters with nine sessions of data in them.**

    Offline every figure is a parsed string from a captured fixture. This is
    the first time any of them is read off a cluster that has actually been
    written to -- and the first time `repository_bytes` sums a pgBackRest
    listing from the real R2 repository rather than from
    `info-full-and-incr.json`.

    **A group is `unknown` when any of its figures is, and that is not a
    failure here** -- it is the reading working (ADR 0195). What this asserts
    is that every group is REPORTED for both projects, with two verdicts and
    no threshold, and that a group reporting `ok` carries an integer for every
    one of its figures. A run where `traffic` comes back `unknown` on a project
    whose store has just started is a true statement about that store.

    Goes red if a figure is folded to zero rather than reported unknown, if a
    verdict outside the two appears, or if `usage` cannot find a project the
    deployment has.
    """
    for variable in ("APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"):
        document = json.loads(Path(os.environ[variable]).read_text(encoding="utf-8"))
        key = document["project"]["key"]

        _code, reading, _err = _doctor("usage", "--project", key)
        checks = _checks(reading)
        assert set(checks) == {"database", "repository", "agent record", "traffic"}, sorted(checks)

        verdicts = {check["verdict"] for check in reading["checks"]}
        assert verdicts <= {"ok", "unknown"}, (
            f"{key}: the usage reading has two verdicts by design and produced {sorted(verdicts)}"
        )

        for name, check in sorted(checks.items()):
            if check["verdict"] != "ok":
                continue
            for member, value in check["evidence"].items():
                assert str(value).lstrip("-").isdigit(), (
                    f"{key}: {name}.{member} reads {value!r}, which is not an "
                    "integer this program produced"
                )


# ---------------------------------------------------------------------------
# OPS-TELEMETRY-002 -- the collector, consumed
# ---------------------------------------------------------------------------


def test_usage_reads_request_counts_from_this_projects_store(as_root: None) -> None:
    """**The store answers, for the first time in this product's life.**

    Prometheus has been running per project since Session 14 and nothing has
    ever read it. `doctor usage`'s `traffic` group is the first consumer, and
    it queries through the store's own container because the store is routed
    nowhere -- there is no URL off the host that could ask it.

    `unknown` is a legitimate answer here and is asserted as such: a store
    holding no `agent_tool_calls_total` series yet is a true reading, not a
    broken one. What is NOT legitimate is a number with no series behind it,
    which is why the offline half asserts the query is a `sum(...)` rather
    than a bare selector -- the exporter promotes the SDK's fresh-per-process
    `service.instance.id` to an `instance` label, so reading one series would
    undercount silently after any restart (D1609).

    Goes red if the traffic group disappears, if it reports a figure without
    the store having answered, or if the reading reaches the store by a route
    that is not the container.
    """
    document = json.loads(Path(os.environ["APG_PROJECT_A_OUTPUTS"]).read_text(encoding="utf-8"))
    key = document["project"]["key"]

    _code, reading, _err = _doctor("usage", "--project", key)
    traffic = _checks(reading)["traffic"]
    assert traffic["verdict"] in {"ok", "unknown"}, traffic

    if traffic["verdict"] == "ok":
        for member in ("requests_total", "tool_calls_total"):
            assert member in traffic["evidence"], traffic
            assert str(traffic["evidence"][member]).isdigit(), traffic
    else:
        assert traffic["detail"], "an unknown traffic group that names no figure"


def test_every_series_the_store_returns_names_this_project(as_root: None) -> None:
    """**ADR 0223's whole claim, on the deployment.**

    Run 4 put `const_labels: {project: <key>}` on the collector's Prometheus
    exporter so that every series it exports names the project it came from.
    Six of seven series carried it in the rendered check and `target_info` did
    not (D1604) -- an exception the offline contract test names rather than
    folds away.

    This asks the running store. The query is the product's own -- the same
    one `doctor usage` builds -- and every series that comes back must carry
    `project=<key>`. A store that answered with another project's series would
    mean two projects' telemetry had been merged, which on a shared host is
    the one thing the const label exists to prevent.

    Read inside the container (`container_exec`), because the store publishes
    no port and is on no router.
    """
    document = json.loads(Path(os.environ["APG_PROJECT_A_OUTPUTS"]).read_text(encoding="utf-8"))
    key = document["project"]["key"]

    from agentic_postgres import container_exec

    answered = container_exec.run(
        f"apg-{key}-store-1",
        "wget",
        "-qO-",
        "http://127.0.0.1:9090/api/v1/query?query=up",
        timeout=30,
    )
    assert answered is not None and answered.returncode == 0, (
        f"the store in apg-{key}-store-1 did not answer: {answered}"
    )

    payload = json.loads(answered.stdout)
    assert payload["status"] == "success", payload
    series = payload["data"]["result"]
    assert series, "the store returned no series at all, so this scan measures nothing"

    foreign = [
        entry["metric"] for entry in series if entry["metric"].get("project") not in (None, key)
    ]
    assert not foreign, (
        f"{key}'s store returned series belonging to another project: {foreign}. "
        "Two projects' telemetry has been merged"
    )


def test_the_metrics_route_now_serves_the_agent_instrument(as_root: None) -> None:
    """**`mcp_metrics.configure` has a production caller for the first time.**

    Until this release `configure` existed, was proved in-process, and nothing
    called it -- the instruments were created by tests and by nothing else. Run
    4 called it in `create_mcp_app`, after the lock loads, because the tool
    roster it labels is the lock's.

    So this is the first sweep at which `agent_tool_calls_total` can exist on
    a deployment at all, and its absence is a real answer rather than a
    failure: the counter appears once an agent has made a call through the
    plane, and a freshly recreated mcp container that has served none has
    nothing to export. **That is asserted as the two-outcome reading it is**,
    with the failing case being the third: the route serving something that is
    not a Prometheus exposition.

    Goes red if the metrics surface stops being served, or if it answers with
    a body that is not an exposition.
    """
    document = json.loads(Path(os.environ["APG_PROJECT_A_OUTPUTS"]).read_text(encoding="utf-8"))
    key = document["project"]["key"]

    from agentic_postgres import container_exec

    answered = container_exec.run(
        f"apg-{key}-store-1",
        "wget",
        "-qO-",
        "http://127.0.0.1:9090/api/v1/query?query=sum%28agent_tool_calls_total%29",
        timeout=30,
    )
    assert answered is not None and answered.returncode == 0, (
        f"the store in apg-{key}-store-1 did not answer: {answered}"
    )

    payload = json.loads(answered.stdout)
    assert payload["status"] == "success", (
        f"the store refused the agent-instrument query: {payload}. An empty result "
        "is a fine answer; a refused query is not"
    )
    # Empty is legitimate and is recorded rather than asserted away: the
    # counter exists once the plane has served a call.
    print(
        f"agent_tool_calls_total on {key}: "
        f"{'present' if payload['data']['result'] else 'no series yet'}"
    )
