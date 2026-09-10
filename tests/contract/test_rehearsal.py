"""`OPS-REHEARSE-001`..`008`, offline (ADR 0190, ADR 0193, Session 18 Run 4).

The plans `bin/rehearse.sh` builds for eight scenarios and what each refuses;
the command driven against a recorded runner with REAL files where the
scenario moves one (the port registry, the foreign lock), so that "reversed"
is a property of the filesystem after the run and not of a flag; the
registry refusal through every `database-ports.sh` verb, the deploy's reader
and provisioning's creator (`OPS-REHEARSE-006`); and the doctor's two new
readers, the injectable disk thresholds (`-007`) and the capability drift
check (`-008`). Nothing here needs root, Docker or a host.

The measured facts the plans rest on (rig 4, D1015) are asserted as the
shapes they decided: a SIGKILL to the process and never `docker kill`; a
DOCKER-USER rule selected by source subnet and destination, deleted by its
comment in the form `iptables -S` prints.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, diagnosis, naming, port_allocations, rehearsal

pytestmark = [pytest.mark.contract, pytest.mark.p0]

KEY = "fixture-alpha-dev"
COMPOSE = naming.compose_project_name(KEY)
RID = "202609061200beef"
INSTANCE_UUID = "01927d3f-1a2b-7c4d-8e5f-6a7b8c9d0e1f"
ENDPOINT = "s3.eu-central-003.backblazeb2.com"
ADDRESSES = ("203.0.113.7", "203.0.113.8")
SUBNET = "172.26.0.0/16"
LOCK_TEXT = json.dumps({"tools": ["a", "b"], "profile": "default"}, sort_keys=True) + "\n"
LOCK_SHA = hashlib.sha256(LOCK_TEXT.encode("utf-8")).hexdigest()
#: `iptables -S` as rig 4 printed it: normalised, `-m tcp` inserted, the
#: destination with its mask, the comment before the target.
LISTED_RULE = (
    "-A DOCKER-USER -s {subnet} -d {address}/32 -p tcp -m tcp --dport 443 "
    "-m comment --comment {comment} -j REJECT --reject-with tcp-reset"
)
FOREIGN_RULE = "-A DOCKER-USER -s 10.0.0.0/8 -m comment --comment apg-rehearsal-other -j RETURN"


def load_command(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"apg_{name}", REPO_ROOT / "bin" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def facts(**overrides: Any) -> rehearsal.Facts:
    base: dict[str, Any] = {
        "project_key": KEY,
        "rehearsal_id": RID,
        "outputs_path": f"/etc/agentic-postgres/projects/{KEY}/outputs.json",
        "doctor_argv": ("python", "bin/doctor.py", "--root", "/etc/agentic-postgres/projects"),
        "backup_sh": "bin/backup.sh",
        "database_ports_sh": "bin/database-ports.sh",
        "containers": {
            "edge-probe": f"{COMPOSE}-edge-probe-1",
            "postgres": f"{COMPOSE}-postgres-1",
            "pgbouncer": f"{COMPOSE}-pgbouncer-1",
        },
        "container_pids": {"edge-probe": 4242, "postgres": 4300, "pgbouncer": 4301},
        "restart_counts": {f"{COMPOSE}-edge-probe-1": 0, f"{COMPOSE}-postgres-1": 0},
        "health_url": "https://x.example.test/__apg/healthz",
        "mcp_url": "https://x.example.test/mcp",
        "stanza": KEY,
        "bucket": f"apg-{KEY}-backup",
        "mirror_enabled": True,
        "mirror_endpoint": ENDPOINT,
        "mirror_bucket": f"apg-{KEY}-backup-mirror",
        "mirror_addresses": ADDRESSES,
        "backup_subnet": SUBNET,
        "registry_path": "/etc/agentic-postgres/database-port-allocations.json",
        "registry_present": True,
        "registry_sha256": "ab" * 32,
        "instance_uuid": INSTANCE_UUID,
        "lock_path": f"/var/lib/agentic-postgres/rendered/{KEY}/mcp-capability-lock.json",
        "lock_present": True,
        "lock_recorded": True,
        "foreign_lock_path": f"/etc/agentic-postgres/projects/{KEY}/apg-rehearsal-{RID}-lock.json",
    }
    base.update(overrides)
    return rehearsal.Facts(**base)


def argvs(plan: rehearsal.Plan) -> list[tuple[str, ...]]:
    return [a.argv for a in (*plan.induce, *plan.reverse) if a.argv] + [
        o.argv for o in plan.observe if o.argv
    ]


# ---------------------------------------------------------------------------
# The plans
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", rehearsal.SCENARIOS)
def test_every_scenario_plans_three_phases_and_prints_every_command(scenario: str) -> None:
    plan = rehearsal.plan(scenario, facts())
    assert plan.scenario == scenario
    assert plan.induce and plan.observe and plan.reverse and plan.reader
    text = rehearsal.render_plan(plan, facts())
    for argv in argvs(plan):
        assert " ".join(argv) in text, f"{scenario}'s plan does not print {argv}"
    assert (plan.induced is False) == (scenario == "provider-loss")


def test_service_termination_signals_the_process_and_never_docker_kill() -> None:
    """Rig 4, D1015: `docker kill` is a manual stop no restart policy restarts
    (exit 137, restart count 0); a SIGKILL to the main process from the host's
    namespace is restarted within two seconds; `kill -9 1` from inside is
    ignored. The plan carries the first, says why, and keeps `docker start`
    as the fallback that is only run when the policy did not."""
    plan = rehearsal.plan("service-termination", facts())
    assert [a.argv for a in plan.induce] == [("kill", "-KILL", "4242")]
    assert not any(argv[:2] == ("docker", "kill") for argv in argvs(plan))
    assert "D1015" in plan.induce[0].what and "docker kill" in plan.induce[0].what
    fallback = [a for a in plan.reverse if a.kind == "run"]
    assert [a.argv for a in fallback] == [("docker", "start", f"{COMPOSE}-edge-probe-1")]
    assert fallback[0].conditional == "restarted"
    assert plan.bound_seconds == rehearsal.BOUNDS["service-termination"]


def test_the_terminated_service_is_the_one_whose_route_the_doctor_reads() -> None:
    """`edge-probe` serves the reserved health route (ADR 0015), the one route
    the doctor asserts 200 on. Killing PostgREST would leave every doctor
    check green, which is a rehearsal of nothing (ADR 0193)."""
    assert rehearsal.HEALTH_SERVICE == "edge-probe"
    with pytest.raises(rehearsal.RehearsalError, match="no running edge-probe"):
        rehearsal.plan("service-termination", facts(containers={"postgres": "x"}))
    with pytest.raises(rehearsal.RehearsalError, match="no main process"):
        rehearsal.plan("service-termination", facts(container_pids={}))


def test_wal_scenario_blocks_only_the_mirror_addresses_from_the_backup_subnet() -> None:
    """One REJECT per resolved address, selected by the backup network's
    subnet AND the address (rig 4 part 2: the control network still reached
    the destination), tagged with the rehearsal's comment; the archiver check
    is a control in both readings; refused for a project without a mirror,
    because the primary's path is never blocked (ADR 0188, ADR 0190)."""
    plan = rehearsal.plan("wal-archiving-failure", facts())
    rules = [a.argv for a in plan.induce]
    assert len(rules) == len(ADDRESSES)
    for address, argv in zip(ADDRESSES, rules, strict=True):
        assert argv[:3] == ("iptables", "-I", "DOCKER-USER")
        assert argv[argv.index("-s") + 1] == SUBNET
        assert argv[argv.index("-d") + 1] == address
        assert argv[argv.index("--dport") + 1] == "443"
        assert argv[argv.index("--comment") + 1] == rehearsal.rule_comment(RID)
        assert "REJECT" in argv
    controls = [o for o in plan.observe if o.control]
    assert len(controls) == 2 and all("archiver" in o.expect for o in controls)
    assert plan.reverse[0].argv == ("iptables", "-S", "DOCKER-USER")
    assert plan.reverse[1].argv[-1] == "mirror", "the next copy is part of the reversal"
    with pytest.raises(rehearsal.RehearsalError, match="primary's path is never blocked"):
        rehearsal.plan("wal-archiving-failure", facts(mirror_enabled=False))
    with pytest.raises(rehearsal.RehearsalError, match="no IPv4 address"):
        rehearsal.plan("wal-archiving-failure", facts(mirror_addresses=()))


def test_iptables_delete_arguments_select_exactly_the_tagged_rules() -> None:
    """The listing form is the one `iptables -S` printed in rig 4, and the
    deletion is `-D CHAIN <spec>` over that same spec. A foreign rule whose
    comment merely shares the prefix is left alone: equality, not containment."""
    comment = rehearsal.rule_comment(RID)
    listing = "\n".join(
        [
            "-N DOCKER-USER",
            FOREIGN_RULE,
            LISTED_RULE.format(subnet=SUBNET, address=ADDRESSES[0], comment=comment),
            LISTED_RULE.format(subnet=SUBNET, address=ADDRESSES[1], comment=comment),
            "-A DOCKER-USER -j RETURN",
        ]
    )
    deletions = rehearsal.iptables_delete_arguments(listing, comment)
    assert len(deletions) == 2
    for address, argv in zip(ADDRESSES, deletions, strict=True):
        assert argv[:3] == ("iptables", "-D", "DOCKER-USER")
        assert f"{address}/32" in argv and comment in argv
        assert "-A" not in argv
    assert rehearsal.iptables_delete_arguments(listing, "apg-rehearsal-") == ()
    assert rehearsal.iptables_delete_arguments("", comment) == ()


def test_registry_loss_moves_aside_in_the_same_directory_and_refuses_when_absent() -> None:
    plan = rehearsal.plan("registry-loss", facts())
    induce = plan.induce[0]
    assert induce.kind == "rename"
    assert Path(induce.target).parent == Path(induce.source).parent, "a rename across filesystems"
    assert induce.target.endswith(rehearsal.rule_comment(RID))
    back = plan.reverse[0]
    assert (back.kind, back.source, back.target) == ("rename", induce.target, induce.source)
    verbs = [o.argv[1] for o in plan.observe]
    assert verbs == ["show", "release"]
    assert "--plan" in plan.observe[1].argv, "release must never write during a rehearsal"
    with pytest.raises(rehearsal.RehearsalError, match="nothing to lose"):
        rehearsal.plan("registry-loss", facts(registry_present=False))


def test_disk_threshold_injects_the_doctor_and_changes_nothing() -> None:
    plan = rehearsal.plan("disk-threshold", facts())
    assert all(a.kind == "none" for a in (*plan.induce, *plan.reverse))
    assert "no disk is filled" in plan.induce[0].what
    flags = [o.argv for o in plan.observe if "--disk-warn-copies" in o.argv]
    assert len(flags) == 2
    problem = [o for o in plan.observe if "--disk-problem-copies" in o.argv]
    assert len(problem) == 1 and problem[0].expect == "problem"
    assert [o.control for o in plan.observe] == [True, False, False]


def test_capability_drift_writes_beside_the_document_and_never_over_the_lock() -> None:
    plan = rehearsal.plan("capability-drift", facts())
    write = plan.induce[0]
    assert write.kind == "write" and write.target == facts().foreign_lock_path
    assert write.target != facts().lock_path
    assert plan.reverse[0].kind == "remove" and plan.reverse[0].target == write.target
    foreign = [o for o in plan.observe if "--lock-file" in o.argv]
    assert len(foreign) == 1 and foreign[0].argv[-1] == write.target
    control = [o for o in plan.observe if o.control]
    assert len(control) == 1 and "--lock-file" not in control[0].argv
    with pytest.raises(rehearsal.RehearsalError, match="no deployed lock"):
        rehearsal.plan("capability-drift", facts(lock_recorded=False))
    with pytest.raises(rehearsal.RehearsalError, match="no deployed lock"):
        rehearsal.plan("capability-drift", facts(lock_present=False))


def test_a_foreign_lock_is_the_deployed_lock_plus_one_member() -> None:
    foreign = rehearsal.foreign_lock(LOCK_TEXT, RID)
    assert json.loads(foreign) == {**json.loads(LOCK_TEXT), "rehearsal": RID}
    assert hashlib.sha256(foreign.encode()).hexdigest() != LOCK_SHA
    with pytest.raises(rehearsal.RehearsalError):
        rehearsal.foreign_lock("[]", RID)


def test_backup_credential_failure_changes_nothing_and_carries_its_control() -> None:
    """The wrong credential lives in one exec's environment (D1009: the
    environment overrides the mounted include) and nowhere else; the control
    is the same check with no override, and it names no credential at all."""
    plan = rehearsal.plan("backup-credential-failure", facts())
    assert all(a.kind == "none" for a in (*plan.induce, *plan.reverse))
    wrong, control = plan.observe
    throwaway = rehearsal.throwaway_credential(RID)
    assert "not-a-credential" in throwaway
    assert f"PGBACKREST_REPO1_S3_KEY={throwaway}" in wrong.argv
    assert f"PGBACKREST_REPO1_S3_KEY_SECRET={throwaway}" in wrong.argv
    assert wrong.argv[-3:] == ("pgbackrest", f"--stanza={KEY}", "check")
    assert control.control and "-e" not in control.argv
    assert control.argv[-3:] == wrong.argv[-3:]
    assert f"apg-{KEY}-backup" in wrong.expect, "the reading names the repository"


def test_provider_loss_is_recorded_not_induced() -> None:
    plan = rehearsal.plan("provider-loss", facts())
    assert plan.induced is False
    assert not argvs(plan)
    assert "D976" in plan.observe[0].expect
    assert rehearsal.verdict("provider-loss", {}) == (
        "recorded",
        "provider loss is recorded, not induced (D976)",
    )


@pytest.mark.parametrize(
    ("scenario", "healthy", "broken", "why"),
    [
        (
            "service-termination",
            {
                "restarted": True,
                "route_status_after": 200,
                "doctor_after": {"containers": "ok", "route health": "ok"},
                "seconds_to_ready": 3.0,
                "gap_reported": True,
            },
            {"restarted": False},
            "did not come back",
        ),
        (
            "database-restart",
            {
                "doctor_after": {"containers": "ok", "database": "ok", "route health": "ok"},
                "dependents_restarted": [],
                "agent_route_status": 401,
            },
            {
                "doctor_after": {"containers": "ok", "database": "ok", "route health": "ok"},
                "dependents_restarted": ["x-auth-1"],
            },
            "dependents restarted",
        ),
        (
            "backup-credential-failure",
            {"wrong_credential_exit": 41, "deployed_credential_exit": 0},
            {"wrong_credential_exit": 0, "deployed_credential_exit": 0},
            "authenticates to nothing",
        ),
        (
            "wal-archiving-failure",
            {
                "blocked_copy_exit": 1,
                "archiver_before": "ok",
                "archiver_under_block": "ok",
                "copy_after_reversal_exit": 0,
            },
            {
                "blocked_copy_exit": 1,
                "archiver_before": "ok",
                "archiver_under_block": "problem",
                "copy_after_reversal_exit": 0,
            },
            "control failed",
        ),
        (
            "registry-loss",
            {
                "show_exit": 4,
                "registry_present_after_show": False,
                "release_exit": 4,
                "registry_present_after_release": False,
            },
            {
                "show_exit": 4,
                "registry_present_after_show": True,
                "release_exit": 4,
                "registry_present_after_release": False,
            },
            "recreated",
        ),
        (
            "disk-threshold",
            {"disk_warn": "warn", "disk_problem": "problem"},
            {"disk_warn": "ok", "disk_problem": "problem"},
            "warn injected",
        ),
        (
            "capability-drift",
            {"drift_foreign": "problem", "drift_deployed": "ok"},
            {"drift_foreign": "ok", "drift_deployed": "ok"},
            "not problem",
        ),
    ],
)
def test_a_reader_that_read_nothing_is_unread_never_read(
    scenario: str, healthy: dict[str, Any], broken: dict[str, Any], why: str
) -> None:
    """ADR 0190: a reader that reads nothing is a finding, not a passed
    rehearsal. Every scenario's verdict has a reading whose absence or wrong
    value turns it unread, and says which."""
    outcome, _ = rehearsal.verdict(scenario, healthy)
    assert outcome == "read"
    outcome, reason = rehearsal.verdict(scenario, broken)
    assert outcome == "unread" and why in reason
    assert rehearsal.verdict(scenario, {})[0] == "unread", "empty readings read nothing"


def test_the_check_names_the_module_reads_are_the_doctors_own() -> None:
    """A misspelled check name reads None and reports the reader unread -- the
    guarded failure, and this makes sure the guard never fires for a typo."""
    produced = {
        diagnosis.containers(expected=1, running=("a",), unhealthy=()).name,
        diagnosis.route(name="health", url="u", status=200, expected=200).name,
        diagnosis.database(reachable=True, pooler_reachable=True).name,
        diagnosis.archiver(failing=False, last_archived_time="t").name,
        diagnosis.mirror(enabled=False, status=None, last_copied_at=None, age_days=None).name,
        diagnosis.disk_headroom(cluster_kb=1, available_kb=9, mount="/m").name,
        diagnosis.capability_drift(recorded=False, present=False, matches=None).name,
    }
    assert set(rehearsal.DEPLOYED_DOCTOR_CHECKS.values()) == produced
    document = diagnosis.render_json(
        (diagnosis.disk_headroom(cluster_kb=1, available_kb=1, mount="/m"),),
        project_key=KEY,
        observed_at="2026-09-06T00:00:00Z",
    )
    assert rehearsal.doctor_check(document, "disk headroom") == "warn"
    assert rehearsal.doctor_check(document, "no such check") is None
    assert rehearsal.doctor_check("not json", "disk headroom") is None
    assert rehearsal.inspect_state("true 1\n") == (True, 1)
    assert rehearsal.inspect_state("garbage") == (None, None)


# ---------------------------------------------------------------------------
# The command, against a recorded runner and real files
# ---------------------------------------------------------------------------


def deployed_document(*, mirror: bool = True, lock_sha: str | None = LOCK_SHA) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": 16,
        "document_kind": "deployed",
        "project": {"key": KEY, "domain": "x.example.test"},
        "routes": {
            "health": {"status": "ready", "url": "https://x.example.test/__apg/healthz"},
            "mcp": {"status": "ready", "url": "https://x.example.test/mcp"},
        },
        "database": {
            "container": f"{COMPOSE}-postgres-1",
            "name": "apg_fixture_alpha_dev",
            "observed": {"instance_uuid": INSTANCE_UUID, "status": "observed"},
        },
        "backup": {
            "enabled": True,
            "stanza": KEY,
            "bucket": f"apg-{KEY}-backup",
            "repository_prefix": f"pgbackrest/{KEY}/",
            "retain_full": 2,
        },
        "mcp": {"status": "ready", "capability_lock_sha256": lock_sha},
    }
    if mirror:
        document["backup"]["mirror"] = {
            "enabled": True,
            "endpoint": ENDPOINT,
            "region": "eu-central-003",
            "bucket": f"apg-{KEY}-backup-mirror",
        }
    return document


def empty_registry_text() -> str:
    return json.dumps(port_allocations.empty_registry(), indent=2, sort_keys=True) + "\n"


class Recorded:
    """Every argv the command runs, answered from a small state: whether the
    health service was killed and whether the policy brings it back, which
    tagged rules stand in DOCKER-USER, and the files the verbs would read."""

    def __init__(self, *, restart_on_kill: bool = True) -> None:
        self.calls: list[list[str]] = []
        self.restart_on_kill = restart_on_kill
        self.killed = False
        self.started = False
        self.doctor_calls_since_kill = 0
        self.rules: list[str] = []
        self.copies: list[int] = []

    @property
    def back(self) -> bool:
        return not self.killed or (self.killed and self.restart_on_kill) or self.started

    def __call__(self, *arguments: str, timeout: int = 0) -> subprocess.CompletedProcess:
        argv = list(arguments)
        self.calls.append(argv)

        def answer(out: str = "", code: int = 0) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(argv, code, stdout=out, stderr="")

        if argv[:2] == ["docker", "ps"]:
            if "Label" in argv[-1]:
                return answer(
                    f"edge-probe\t{COMPOSE}-edge-probe-1\npostgres\t{COMPOSE}-postgres-1\n"
                    f"pgbouncer\t{COMPOSE}-pgbouncer-1\n"
                )
            return answer(f"{COMPOSE}-edge-probe-1\n{COMPOSE}-postgres-1\n{COMPOSE}-pgbouncer-1\n")
        if argv[:2] == ["docker", "inspect"]:
            template, name = argv[3], argv[4]
            edge = "edge-probe" in name
            restarts = 1 if (edge and self.killed and self.restart_on_kill) else 0
            if "Pid" in template:
                return answer(f"4242 {restarts}\n")
            running = self.back if edge else True
            return answer(f"{'true' if running else 'false'} {restarts}\n")
        if argv[:3] == ["docker", "network", "inspect"]:
            return answer(f"{SUBNET}\n")
        if argv[0] == "kill":
            self.killed = True
            return answer()
        if argv[:2] == ["docker", "start"]:
            self.started = True
            return answer()
        if argv[:2] == ["docker", "restart"]:
            return answer()
        if argv[:2] == ["docker", "exec"]:
            return answer(code=41 if "-e" in argv else 0)
        if argv[0] == "iptables":
            return self.iptables(argv, answer)
        if argv[0].endswith("backup.sh") and argv[-1] == "mirror":
            code = 1 if self.rules else 0
            self.copies.append(code)
            return answer(code=code)
        if argv[0].endswith("database-ports.sh"):
            registry = Path(argv[argv.index("--registry") + 1])
            return answer(code=0 if registry.is_file() else 4)
        if argv[0] == "curl":
            if "-X" in argv:
                return answer("401")
            return answer("200" if self.back else "503")
        if len(argv) > 1 and argv[1].endswith("doctor.py"):
            return answer(self.doctor(argv))
        raise AssertionError(f"unexpected command {argv}")

    def iptables(self, argv: list[str], answer: Any) -> subprocess.CompletedProcess:
        if argv[1] == "-I":
            self.rules.append(
                LISTED_RULE.format(
                    subnet=argv[argv.index("-s") + 1],
                    address=argv[argv.index("-d") + 1],
                    comment=argv[argv.index("--comment") + 1],
                )
            )
            return answer()
        if argv[1] == "-S":
            return answer("\n".join(["-N DOCKER-USER", FOREIGN_RULE, *self.rules]) + "\n")
        if argv[1] == "-D":
            spec = "-A " + " ".join(argv[2:])
            if spec not in self.rules:
                return answer(code=1)
            self.rules.remove(spec)
            return answer()
        raise AssertionError(f"unexpected iptables {argv}")

    def doctor(self, argv: list[str]) -> str:
        gap = self.killed and self.doctor_calls_since_kill == 0 and not self.started
        if self.killed:
            self.doctor_calls_since_kill += 1
        if (
            "--disk-problem-copies" in argv
            and float(argv[argv.index("--disk-problem-copies") + 1]) > 1e6
        ):
            disk = "problem"
        elif (
            "--disk-warn-copies" in argv and float(argv[argv.index("--disk-warn-copies") + 1]) > 1e6
        ):
            disk = "warn"
        else:
            disk = "ok"
        drift = "ok"
        if "--lock-file" in argv:
            text = Path(argv[argv.index("--lock-file") + 1]).read_text(encoding="utf-8")
            drift = "problem" if '"rehearsal"' in text else "ok"
        checks = tuple(
            diagnosis.Check(name=name, verdict=verdict, detail="", evidence=(("k", "v"),))
            for name, verdict in (
                ("containers", "problem" if gap else "ok"),
                ("route health", "problem" if gap else "ok"),
                ("database", "ok"),
                ("wal archiver", "ok"),
                ("backup mirror", "ok"),
                ("disk headroom", disk),
                ("capability drift", drift),
            )
        )
        return diagnosis.render_json(checks, project_key=KEY, observed_at="2026-09-06T00:00:00Z")


class FakeTime:
    """A clock that advances ten seconds per reading and never sleeps, so a
    bound is reached in a handful of polls rather than in minutes."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        self.now += 10.0
        return self.now

    def sleep(self, seconds: float) -> None:
        return None


@pytest.fixture
def rehearse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    module = load_command("rehearse")
    monkeypatch.setattr(module, "require_root", lambda: None)
    monkeypatch.setattr(module, "resolve", lambda hostname: ADDRESSES)
    monkeypatch.setattr(module, "new_rehearsal_id", lambda: RID)
    monkeypatch.setattr(module, "time", FakeTime())

    state_root = tmp_path / "etc" / "projects"
    (state_root / KEY).mkdir(parents=True)
    outputs = state_root / KEY / "outputs.json"
    outputs.write_text(json.dumps(deployed_document()), encoding="utf-8")
    rendered = tmp_path / "rendered"
    (rendered / KEY).mkdir(parents=True)
    (rendered / KEY / "mcp-capability-lock.json").write_text(LOCK_TEXT, encoding="utf-8")
    registry = tmp_path / "etc" / "database-port-allocations.json"
    registry.write_text(empty_registry_text(), encoding="utf-8")

    module.PATHS = {
        "outputs": outputs,
        "state_root": state_root,
        "state_file": tmp_path / "etc" / rehearsal.STATE_FILENAME,
        "lock": rendered / KEY / "mcp-capability-lock.json",
        "foreign": state_root / KEY / f"{rehearsal.rule_comment(RID)}-capability-lock.json",
        "registry": registry,
        "aside": registry.with_name(f"{registry.name}.{rehearsal.rule_comment(RID)}"),
        "evidence": tmp_path / "evidence",
    }
    module.ARGV = [
        "--outputs",
        str(outputs),
        "--state-root",
        str(state_root),
        "--rendered-root",
        str(rendered),
        "--registry",
        str(registry),
        "--evidence-dir",
        str(tmp_path / "evidence"),
    ]
    return module


def drive(
    module: Any, monkeypatch: pytest.MonkeyPatch, *arguments: str, runner: Recorded | None = None
) -> tuple[int, Recorded]:
    runner = runner or Recorded()
    monkeypatch.setattr(module, "run", runner)
    return module.main([*arguments, *module.ARGV]), runner


def evidence(module: Any, scenario: str) -> dict[str, Any]:
    path = module.PATHS["evidence"] / f"rehearsal-{KEY}-{scenario}-{RID}.json"
    return json.loads(path.read_text(encoding="utf-8"))


MUTATING = {"kill", "iptables"}


def mutating_calls(runner: Recorded) -> list[list[str]]:
    return [
        argv
        for argv in runner.calls
        if argv[0] in MUTATING
        or argv[:2] in (["docker", "restart"], ["docker", "start"], ["docker", "exec"])
        or (len(argv) > 1 and argv[1].endswith("doctor.py"))
        or argv[0].endswith("backup.sh")
        or argv[0].endswith("database-ports.sh")
        or argv[0] == "curl"
    ]


@pytest.mark.parametrize("scenario", rehearsal.SCENARIOS)
def test_plan_reads_the_facts_and_runs_writes_and_moves_nothing(
    rehearse: Any,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`OPS-REHEARSE-001`'s second half. The fact-gathering reads (`docker ps`,
    `inspect`, `network inspect`) are the only subprocesses; nothing is
    killed, no rule is inserted, no verb or doctor is run, and the filesystem
    is what it was: registry in place, no foreign lock, no evidence, no
    in-progress file."""
    before = rehearse.PATHS["registry"].read_bytes()
    code, runner = drive(rehearse, monkeypatch, scenario, "--plan")
    assert code == 0
    assert mutating_calls(runner) == []
    assert rehearse.PATHS["registry"].read_bytes() == before
    assert not rehearse.PATHS["aside"].exists()
    assert not rehearse.PATHS["foreign"].exists()
    assert not rehearse.PATHS["state_file"].exists()
    assert not rehearse.PATHS["evidence"].exists()
    out = capsys.readouterr().out
    assert "plan only: nothing was run" in out and scenario in out


def test_service_termination_kills_the_process_reads_the_restart_and_the_gap(
    rehearse: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, runner = drive(rehearse, monkeypatch, "service-termination")
    assert code == 0
    assert ["kill", "-KILL", "4242"] in runner.calls
    assert not any(argv[:2] == ["docker", "kill"] for argv in runner.calls)
    assert not any(argv[:2] == ["docker", "start"] for argv in runner.calls), (
        "the policy restarted it"
    )
    record = evidence(rehearse, "service-termination")
    assert record["verdict"] == "read" and record["reversed"] is True
    assert record["readings"]["restarted"] is True
    assert record["readings"]["restart_count_after"] == 1
    assert record["readings"]["gap_reported"] is True
    assert record["readings"]["route_status_after"] == 200
    assert record["readings"]["doctor_after"] == {"containers": "ok", "route health": "ok"}
    assert not rehearse.PATHS["state_file"].exists()


def test_a_service_the_policy_does_not_restart_is_started_by_the_fallback_and_reported_unread(
    rehearse: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bound passes with the container down; the conditional `docker start`
    runs; the reversal verifies (it is running) and the rehearsal is UNREAD
    (exit 6): the reader did not see what it exists to see, and that is a
    finding, not a pass (ADR 0190)."""
    code, runner = drive(
        rehearse, monkeypatch, "service-termination", runner=Recorded(restart_on_kill=False)
    )
    assert code == 6
    assert ["docker", "start", f"{COMPOSE}-edge-probe-1"] in runner.calls
    record = evidence(rehearse, "service-termination")
    assert record["verdict"] == "unread" and "did not come back" in record["why"]
    assert record["reversed"] is True
    assert not rehearse.PATHS["state_file"].exists(), "reversed, so nothing is in progress"


def test_database_restart_reads_reconnection_dependents_and_the_agent_boundary(
    rehearse: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, runner = drive(rehearse, monkeypatch, "database-restart")
    assert code == 0
    assert ["docker", "restart", "-t", "30", f"{COMPOSE}-postgres-1"] in runner.calls
    record = evidence(rehearse, "database-restart")
    readings = record["readings"]
    assert readings["doctor_after"] == {"containers": "ok", "database": "ok", "route health": "ok"}
    assert readings["dependents_restarted"] == []
    assert readings["agent_route_status"] == 401
    assert record["verdict"] == "read"


def test_backup_credential_failure_runs_the_wrong_check_and_the_control(
    rehearse: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, runner = drive(rehearse, monkeypatch, "backup-credential-failure")
    assert code == 0
    checks = [argv for argv in runner.calls if argv[:2] == ["docker", "exec"]]
    assert len(checks) == 2
    assert "-e" in checks[0] and "-e" not in checks[1]
    assert checks[0][-1] == "check" and checks[1][-1] == "check"
    record = evidence(rehearse, "backup-credential-failure")
    assert record["readings"]["wrong_credential_exit"] == 41
    assert record["readings"]["deployed_credential_exit"] == 0
    assert record["readings"]["repository"] == {"stanza": KEY, "bucket": f"apg-{KEY}-backup"}
    assert "6c" in record["readings"]["a_deploy_would"]
    assert record["verdict"] == "read"
    assert not rehearse.PATHS["state_file"].exists()


def test_wal_scenario_inserts_the_rules_reads_the_failed_copy_and_deletes_by_comment(
    rehearse: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The copy fails only while the rules stand, the reversal deletes exactly
    the tagged rules (the foreign one stays), and the copy after the reversal
    completes. The runner answers the copy from the rule table, so a reversal
    that ran after the second copy, or not at all, is read as a failed copy."""
    code, runner = drive(rehearse, monkeypatch, "wal-archiving-failure")
    assert code == 0, evidence(rehearse, "wal-archiving-failure")["why"]
    inserted = [argv for argv in runner.calls if argv[:2] == ["iptables", "-I"]]
    assert [argv[argv.index("-d") + 1] for argv in inserted] == list(ADDRESSES)
    deleted = [argv for argv in runner.calls if argv[:2] == ["iptables", "-D"]]
    assert len(deleted) == 2 and all(rehearsal.rule_comment(RID) in argv for argv in deleted)
    assert not any("apg-rehearsal-other" in argv for argv in deleted)
    assert runner.rules == [] and runner.copies == [1, 0]
    record = evidence(rehearse, "wal-archiving-failure")
    readings = record["readings"]
    assert readings["blocked_copy_exit"] == 1 and readings["copy_after_reversal_exit"] == 0
    assert readings["archiver_before"] == "ok" and readings["archiver_under_block"] == "ok"
    assert readings["rules_remaining"] == 0
    assert readings["blocked_addresses"] == list(ADDRESSES)
    assert record["verification"]["no tagged rule remains"] is True
    assert record["verdict"] == "read" and record["reversed"] is True


def test_wal_scenario_is_refused_for_a_project_without_a_mirror(
    rehearse: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rehearse.PATHS["outputs"].write_text(
        json.dumps(deployed_document(mirror=False)), encoding="utf-8"
    )
    code, runner = drive(rehearse, monkeypatch, "wal-archiving-failure")
    assert code == 5
    assert "never blocked" in capsys.readouterr().err
    assert not any(argv[0] == "iptables" for argv in runner.calls)
    assert not rehearse.PATHS["state_file"].exists()


def test_registry_loss_moves_the_file_reads_two_refusals_and_restores_the_bytes(
    rehearse: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The registry is a real file. The runner's `database-ports.sh` answers
    4 exactly when the file is absent, so the readings prove the rename
    happened; the verification proves the bytes came back."""
    before = rehearse.PATHS["registry"].read_bytes()
    code, runner = drive(rehearse, monkeypatch, "registry-loss")
    assert code == 0
    assert rehearse.PATHS["registry"].read_bytes() == before
    assert not rehearse.PATHS["aside"].exists()
    verbs = [argv[1] for argv in runner.calls if argv[0].endswith("database-ports.sh")]
    assert verbs == ["show", "release", "show"], "two refusals under the loss, one read after"
    record = evidence(rehearse, "registry-loss")
    readings = record["readings"]
    assert readings["show_exit"] == 4 and readings["release_exit"] == 4
    assert readings["registry_present_after_show"] is False
    assert readings["registry_present_after_release"] is False
    assert record["verification"]["registry present with its original bytes"] is True
    assert record["verdict"] == "read" and record["reversed"] is True
    assert not rehearse.PATHS["state_file"].exists()


def test_registry_loss_is_refused_when_there_is_no_registry_to_lose(
    rehearse: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rehearse.PATHS["registry"].unlink()
    code, _ = drive(rehearse, monkeypatch, "registry-loss")
    assert code == 5
    assert "nothing to lose" in capsys.readouterr().err
    assert not rehearse.PATHS["registry"].exists(), "the refusal created nothing"


def test_disk_threshold_reads_warn_and_problem_from_the_injected_flags(
    rehearse: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, runner = drive(rehearse, monkeypatch, "disk-threshold")
    assert code == 0
    doctors = [argv for argv in runner.calls if argv[1].endswith("doctor.py")]
    assert len(doctors) == 3
    assert "--disk-warn-copies" not in doctors[0]
    assert "--disk-warn-copies" in doctors[1] and "--disk-problem-copies" not in doctors[1]
    assert "--disk-problem-copies" in doctors[2]
    record = evidence(rehearse, "disk-threshold")
    assert record["readings"]["disk_default"] == "ok"
    assert record["readings"]["disk_warn"] == "warn"
    assert record["readings"]["disk_problem"] == "problem"
    assert record["verdict"] == "read"
    assert not rehearse.PATHS["state_file"].exists()


def test_capability_drift_writes_the_foreign_lock_beside_the_document_and_removes_it(
    rehearse: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The doctor in the runner reads the file `--lock-file` names, so the
    `problem` reading proves the foreign lock was written where the plan said
    and held what `foreign_lock` produces; the deployed lock is byte-identical
    after and the foreign one is gone."""
    lock_before = rehearse.PATHS["lock"].read_bytes()
    code, runner = drive(rehearse, monkeypatch, "capability-drift")
    assert code == 0
    doctors = [argv for argv in runner.calls if argv[1].endswith("doctor.py")]
    assert len(doctors) == 2 and "--lock-file" in doctors[0] and "--lock-file" not in doctors[1]
    assert doctors[0][-1] == str(rehearse.PATHS["foreign"])
    assert rehearse.PATHS["lock"].read_bytes() == lock_before
    assert not rehearse.PATHS["foreign"].exists()
    record = evidence(rehearse, "capability-drift")
    assert record["readings"] == {"drift_foreign": "problem", "drift_deployed": "ok"}
    assert record["verdict"] == "read" and record["reversed"] is True


def test_provider_loss_runs_nothing_and_records_the_measurement(
    rehearse: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, runner = drive(rehearse, monkeypatch, "provider-loss")
    assert code == 0
    assert mutating_calls(runner) == []
    record = evidence(rehearse, "provider-loss")
    assert record["induced"] is False and record["verdict"] == "recorded"
    assert "D976" in record["readings"]["record"]
    assert not rehearse.PATHS["state_file"].exists()


def test_a_second_scenario_is_refused_while_one_is_unreversed(
    rehearse: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rehearse.PATHS["state_file"].write_text(
        json.dumps(
            {"scenario": "registry-loss", "project_key": KEY, "rehearsal_id": "old", "reverse": []}
        ),
        encoding="utf-8",
    )
    code, runner = drive(rehearse, monkeypatch, "service-termination")
    assert code == 5
    err = capsys.readouterr().err
    assert "un-reversed" in err and "registry-loss" in err and "rehearse.sh reverse" in err
    assert mutating_calls(runner) == []
    assert rehearse.PATHS["state_file"].exists(), "the refusal keeps the record"


def test_an_observation_that_raises_is_still_reversed_and_reported_unread(
    rehearse: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Induce, then the observer blows up: the registry must come back, the
    in-progress file must go, and the evidence must say what happened."""
    before = rehearse.PATHS["registry"].read_bytes()

    def explode(plan: Any, facts: Any) -> dict[str, Any]:
        raise RuntimeError("the observer broke")

    monkeypatch.setattr(rehearse, "observe", explode)
    code, _ = drive(rehearse, monkeypatch, "registry-loss")
    assert code == 6
    assert rehearse.PATHS["registry"].read_bytes() == before
    assert not rehearse.PATHS["aside"].exists()
    assert not rehearse.PATHS["state_file"].exists()
    record = evidence(rehearse, "registry-loss")
    assert record["reversed"] is True and record["verdict"] == "unread"
    assert "RuntimeError: the observer broke" in record["readings"]["error"]


def test_reverse_replays_the_reversal_an_interrupted_rehearsal_recorded(
    rehearse: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, aside = rehearse.PATHS["registry"], rehearse.PATHS["aside"]
    original = registry.read_bytes()
    registry.rename(aside)
    rehearse.PATHS["state_file"].write_text(
        json.dumps(
            {
                "scenario": "registry-loss",
                "project_key": KEY,
                "rehearsal_id": RID,
                "registry_sha256": hashlib.sha256(original).hexdigest(),
                "reverse": [
                    {
                        "what": "back",
                        "kind": "rename",
                        "source": str(aside),
                        "target": str(registry),
                        "argv": [],
                    },
                    {
                        "what": "show",
                        "kind": "run",
                        "argv": ["bin/database-ports.sh", "show", "--registry", str(registry)],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    runner = Recorded()
    monkeypatch.setattr(rehearse, "run", runner)
    assert rehearse.main(["reverse", "--state-root", str(rehearse.PATHS["state_root"])]) == 0
    assert registry.read_bytes() == original and not aside.exists()
    assert not rehearse.PATHS["state_file"].exists()
    assert rehearse.main(["reverse", "--state-root", str(rehearse.PATHS["state_root"])]) == 0


def test_the_evidence_carries_the_plan_every_reading_and_the_verification(
    rehearse: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    drive(rehearse, monkeypatch, "disk-threshold")
    record = evidence(rehearse, "disk-threshold")
    assert set(record) >= {
        "document_kind",
        "scenario",
        "project_key",
        "rehearsal_id",
        "started_at",
        "finished_at",
        "induced",
        "reader",
        "bound_seconds",
        "plan",
        "readings",
        "reversed",
        "verification",
        "verdict",
        "why",
    }
    assert record["document_kind"] == "rehearsal"
    assert "--disk-warn-copies" in record["plan"]


# ---------------------------------------------------------------------------
# OPS-REHEARSE-006: an absent registry is refused by every reader, created by one
# ---------------------------------------------------------------------------


@pytest.fixture
def ports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    module = load_command("database-ports")
    monkeypatch.setattr(module, "LOCK_PATH", tmp_path / "lock")
    return module


def test_every_port_verb_refuses_an_absent_registry_with_exit_4_and_recreates_nothing(
    ports: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Until Session 18 an absent file loaded as an empty registry and the next
    `allocate` wrote a fresh one -- a loss read as a clean slate. Every verb
    now refuses, and the path is still absent afterwards.

    **The refusal an unprivileged caller gets is the LOCK's, and admitting that
    is not a weakening** (Session 20 Run 7). The writing verbs take `HostLock`
    on `/run/lock/agentic-postgres-database-ports.lock` before they read the
    registry. On this workstation and in CI that file does not exist, the caller
    creates it, and the registry check is reached: exit 4. On the production
    host a root run left the file `root:root 0644` on 2026-09-06, so `op` cannot
    open it and the same verb exits 3 -- *"Allocation writes host state and
    needs root"* -- before the registry is ever consulted. Measured on both.

    Both are correct product behaviour and neither is this test's subject. What
    IS its subject holds either way and is asserted in both branches: the verb
    REFUSES, and **it recreates nothing**. That last clause is the whole of what
    Session 18 repaired, and a run stopped at the lock could not have recreated
    a registry it never opened.

    Exposed by running the Session 1 gate as `op` on the host -- the one
    environment where the lock file is somebody else's. No `--lock-file` flag
    was added to make this hermetic: the lock is what makes probe-and-write
    atomic, and a caller able to redirect it could run two allocations that do
    not see each other.
    """
    missing = tmp_path / "etc" / "database-port-allocations.json"
    host = str(REPO_ROOT / "host.example.yaml")
    common = ["--registry", str(missing), "--instance-uuid", INSTANCE_UUID]
    verbs = {
        "show": ["show", "--registry", str(missing)],
        "release": ["release", *common, "--project-key", KEY, "--plan"],
        "allocate": ["allocate", "--host", host, *common, "--project-key", KEY, "--plan"],
        "verify": ["verify", "--host", host, *common, "--plan"],
    }
    reached_the_registry = 0
    for verb, argv in verbs.items():
        code = ports.main(argv)
        err = capsys.readouterr().err

        assert code in (3, 4), f"{verb} exited {code}; 4 is an absent registry, 3 is the lock"
        if code == 4:
            assert str(missing) in err and "not an empty one" in err, verb
            reached_the_registry += 1
        else:
            assert "needs root" in err, (
                f"{verb} exited 3 for a reason other than the host lock: {err!r}"
            )

        # The subject, asserted in both branches.
        assert not missing.exists(), f"{verb} recreated the registry"
        assert not missing.parent.exists() or not any(missing.parent.iterdir()), verb

    # Anti-vacuity. `show` takes no lock, so at least one verb reaches the
    # registry check in every environment. A run where all four stopped at the
    # lock would have asserted only that a lock refusal writes nothing, which is
    # not what this test is for.
    assert reached_the_registry >= 1, (
        "no verb reached the registry check, so this asserted nothing about an absent registry"
    )


def test_a_present_registry_still_loads_and_the_message_is_the_modules(
    ports: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control for the refusal, and the one spelling of its message."""
    present = tmp_path / "database-port-allocations.json"
    present.write_text(empty_registry_text(), encoding="utf-8")
    assert ports.main(["show", "--registry", str(present)]) == 0
    assert "no allocations" in capsys.readouterr().out
    with pytest.raises(port_allocations.RegistryMissing) as raised:
        ports.load_registry(tmp_path / "absent.json")
    assert str(raised.value) == port_allocations.missing_registry_message(tmp_path / "absent.json")
    assert issubclass(port_allocations.RegistryMissing, port_allocations.AllocationError)


def test_the_deploy_names_the_loss_instead_of_publishing_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`_live_allocation` returned None for an absent registry and the deploy
    published the transports `unavailable` -- the loss read as "nothing
    allocated yet". It refuses by name now, and the control reads a present
    registry as before."""
    deploy = load_command("deploy-project")
    missing = tmp_path / "absent" / "database-port-allocations.json"
    monkeypatch.setattr(port_allocations, "REGISTRY_PATH", str(missing))
    with pytest.raises(SystemExit) as refused:
        deploy._live_allocation(KEY, INSTANCE_UUID)
    assert refused.value.code == 5
    assert str(missing) in capsys.readouterr().err
    assert not missing.exists()

    present = tmp_path / "database-port-allocations.json"
    registry = port_allocations.empty_registry()
    registry["allocations"].append(
        {
            "instance_uuid": INSTANCE_UUID,
            "project_key": KEY,
            "pooled_port": 15432,
            "direct_port": 15433,
            "state": "active",
            "reserved_at": "2026-09-06T00:00:00Z",
            "activated_at": "2026-09-06T00:00:05Z",
            "released_at": None,
        }
    )
    present.write_text(json.dumps(registry), encoding="utf-8")
    monkeypatch.setattr(port_allocations, "REGISTRY_PATH", str(present))
    assert deploy._live_allocation(KEY, INSTANCE_UUID)["pooled_port"] == 15432


def test_provisioning_creates_the_initial_registry_once_and_names_the_same_path() -> None:
    """The initial registry is provisioning's (ADR 0190): `--check` reports its
    absence, `--apply` creates it after the sudoers rule and before the units,
    from `port_allocations.empty_registry`, and never rewrites a present one.
    The script spells the path itself because it runs before the release is
    installed; this is where the two spellings are held together."""
    source = (REPO_ROOT / "bin" / "provision-host.sh").read_text(encoding="utf-8")
    assert 'PORT_REGISTRY="${ETC}/database-port-allocations.json"' in source
    assert 'ETC="/etc/agentic-postgres"' in source
    assert port_allocations.REGISTRY_PATH == "/etc/agentic-postgres/database-port-allocations.json"
    assert "== port registry ==" in source.split("check_baseline()")[1].split("apply_baseline()")[0]
    creator = source.split("install_port_registry() {")[1].split("\n}\n")[0]
    assert 'if [ -f "${PORT_REGISTRY}" ]' in creator and "left as it is" in creator
    assert "port_allocations.empty_registry()" in creator
    assert 'install -m 0644 -o root -g root "${staged}" "${PORT_REGISTRY}"' in creator
    apply = source.split("apply_baseline() {")[1]
    assert (
        apply.index("install_database_access_sudoers")
        < apply.index("install_port_registry")
        < apply.index("install_units")
    )


# ---------------------------------------------------------------------------
# OPS-REHEARSE-007 and -008: the doctor's two rehearsed readers
# ---------------------------------------------------------------------------


def test_disk_thresholds_are_injectable_and_the_evidence_carries_the_ones_used() -> None:
    deployed = diagnosis.disk_headroom(cluster_kb=1000, available_kb=5000, mount="/pg")
    assert deployed.verdict == diagnosis.OK
    warned = diagnosis.disk_headroom(
        cluster_kb=1000, available_kb=5000, mount="/pg", warn_copies=10.0
    )
    assert warned.verdict == diagnosis.WARN
    assert ("warn_below_copies", "10.0") in warned.evidence
    broken = diagnosis.disk_headroom(
        cluster_kb=1000, available_kb=5000, mount="/pg", warn_copies=20.0, problem_copies=10.0
    )
    assert broken.verdict == diagnosis.PROBLEM
    assert ("problem_below_copies", "10.0") in broken.evidence
    assert ("warn_below_copies", str(diagnosis.DISK_WARN_COPIES)) in deployed.evidence


@pytest.mark.parametrize(("warn", "problem"), [(1.0, 2.0), (2.0, 2.0), (2.0, 0.0), (0.5, -1.0)])
def test_an_impossible_threshold_pair_is_refused_before_anything_is_read(
    warn: float, problem: float, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(ValueError, match="0 < problem"):
        diagnosis.disk_thresholds(warn_copies=warn, problem_copies=problem)
    doctor = load_command("doctor")
    code = doctor.main(
        [
            "--project",
            KEY,
            "--root",
            "/nonexistent",
            "--json",
            "--disk-warn-copies",
            str(warn),
            "--disk-problem-copies",
            str(problem),
        ]
    )
    assert code == 2, "refused as input, before the document that does not exist is looked for"
    assert "0 < problem" in capsys.readouterr().err


def test_capability_drift_classifies_every_state() -> None:
    drift = diagnosis.capability_drift
    assert drift(recorded=False, present=False, matches=None).verdict == diagnosis.OK
    assert drift(recorded=False, present=True, matches=None).verdict == diagnosis.WARN
    assert drift(recorded=True, present=None, matches=None).verdict == diagnosis.UNKNOWN
    assert drift(recorded=True, present=False, matches=None).verdict == diagnosis.PROBLEM
    assert drift(recorded=True, present=True, matches=True).verdict == diagnosis.OK
    check = drift(recorded=True, present=True, matches=False)
    assert check.verdict == diagnosis.PROBLEM and check.name == "capability drift"
    assert ("matches", "False") in check.evidence


def test_the_drift_probe_compares_digests_itself_and_hands_the_check_only_booleans(
    tmp_path: Path,
) -> None:
    """The `mcp` block is one the doctor never echoes (ADR 0159): the recorded
    digest reaches neither the detail nor the evidence, in any state."""
    doctor = load_command("doctor")
    lock = tmp_path / "mcp-capability-lock.json"
    lock.write_text(LOCK_TEXT, encoding="utf-8")
    foreign = tmp_path / "foreign.json"
    foreign.write_text(rehearsal.foreign_lock(LOCK_TEXT, RID), encoding="utf-8")
    document = deployed_document(lock_sha=LOCK_SHA)

    same = doctor.probe_capability_drift(document, lock_file=lock)
    assert same.verdict == diagnosis.OK
    drifted = doctor.probe_capability_drift(document, lock_file=foreign)
    assert drifted.verdict == diagnosis.PROBLEM
    absent = doctor.probe_capability_drift(document, lock_file=tmp_path / "none.json")
    assert absent.verdict == diagnosis.PROBLEM
    unrecorded = doctor.probe_capability_drift(deployed_document(lock_sha=None), lock_file=lock)
    assert unrecorded.verdict == diagnosis.WARN
    for check in (same, drifted, absent, unrecorded):
        assert LOCK_SHA not in check.detail
        assert LOCK_SHA not in json.dumps(check.evidence)
        assert all(value in {"True", "False", "null"} for _, value in check.evidence)


def test_the_doctor_wrapper_forwards_the_injections_to_deployed_mode_only() -> None:
    source = (REPO_ROOT / "bin" / "doctor.sh").read_text(encoding="utf-8")
    assert "--disk-warn-copies|--disk-problem-copies|--lock-file)" in source
    assert 'INJECTIONS+=("$1" "$2")' in source
    deployed = source.split("deployed_mode() {")[1].split("\n}\n")[0]
    assert deployed.count('${INJECTIONS[@]+"${INJECTIONS[@]}"}') == 3, "every exec forwards them"
    assert "is a deployed-mode injection; it needs --project" in source
