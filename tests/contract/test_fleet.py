"""`FLEET-INV-001` and `FLEET-INV-002` -- the fleet inventory, offline.

Behavioural on `agentic_postgres.fleet` for the composition, and on the
command for the two properties ADR 0185 makes a fleet inventory safe to have:
it prints every project under that project's own key, and it writes nothing.

The command is exercised against a fixture root holding one schema-valid
deployed document (built from the real rendered fixture, as
`test_deployed_output` builds it), one document that is not deployed, and one
directory with no document at all. The doctor runs for real underneath -- its
probes fail fast against a fixture domain and no containers -- so what is
measured is the whole pipeline the operator runs, minus a host.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, deployed_output, diagnosis, fleet

pytestmark = [pytest.mark.contract, pytest.mark.p0]

KEY = "fixture-alpha-dev"
COMMIT = "a" * 40
INSTANCE_UUID = "01927d3f-1a2b-7c4d-8e5f-6a7b8c9d0e1f"
NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
SENSITIVE = f"APG-SECRET-CANARY-{uuid.uuid4().hex}"


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rendered() -> dict[str, Any]:
    path = REPO_ROOT / ".generated" / KEY / "outputs.json"
    if not path.exists():
        pytest.skip("fixtures are not rendered in this working tree")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def deployed(rendered: dict[str, Any]) -> dict[str, Any]:
    """A schema-valid deployed document, built the way the deploy builds one."""
    return deployed_output.build_deployed_document(
        rendered=rendered,
        source_commit=COMMIT,
        health_status="ready",
        rest_status="unavailable",
        docs_status="unavailable",
        app_status="unavailable",
        app_docs_status="unavailable",
        storage_status="unavailable",
        mcp_status="unavailable",
        metrics_status="unavailable",
        api=deployed_output.API_NOT_PUBLISHED,
        jwt=deployed_output.JWT_NOT_PUBLISHED,
        mcp=deployed_output.MCP_NOT_PUBLISHED,
        deployed_through_session=3,
        host={
            "id": "apg-vps-01",
            "os_release": "26.04",
            "public_ipv4": "203.0.113.10",
            "public_ipv6": None,
        },
        edge={
            "stack_name": "apg-edge",
            "control_network": "apg-edge_control",
            "egress_network": "apg-edge_egress",
            "project_network_attached": True,
        },
        tls={
            "status": "issued",
            "acme_environment": "staging",
            "resolver": "letsencrypt-staging",
            "certificate_sha256": "c" * 64,
            "not_before": "2026-08-05T00:00:00Z",
            "not_after": "2026-11-03T00:00:00Z",
        },
        bootstrap={
            "status": "complete",
            "state_path": f"/etc/agentic-postgres/projects/{KEY}/bootstrap-state.json",
            "infisical_project_id": "5fffcd38-9af6-4f9d-bef9-c6eefc5e696f",
            "runtime_identity_id": "3302b5a4-7288-424f-bcd3-6cd158617827",
        },
        secrets={
            "status": "ready",
            "generation_id": "k7f2p9qd",
            "generation_manifest": (
                f"/var/lib/agentic-postgres/secrets/{KEY}/generations/k7f2p9qd/manifest.json"
            ),
            "required_names": ["session2_sentinel"],
            "fresh": True,
            "materialized_at": "2026-08-05T18:00:00Z",
        },
        runtime={
            "release_path": f"/opt/agentic-postgres/releases/{COMMIT}",
            "state_directory": f"/etc/agentic-postgres/projects/{KEY}",
            "compose_model_sha256": "d" * 64,
        },
        database_observed={
            "status": "observed",
            "server_version": "18.4",
            "extensions": {"vector": "0.8.6", "plpgsql": "1.0"},
            "memory": {"anon_mb": 62, "shmem_mb": 140, "file_mb": 410},
            "instance_uuid": INSTANCE_UUID,
        },
    )


def doctor_document(*checks: diagnosis.Check) -> dict[str, Any]:
    return diagnosis.document(checks, project_key=KEY, observed_at="2026-09-04T11:59:00Z")


HEALTHY = (
    diagnosis.containers(expected=10, running=tuple("abcdefghij"), unhealthy=()),
    diagnosis.migrations(applied=30, released=30),
    diagnosis.repository(status="ready", last_full_backup_at="2026-08-28T10:20:02Z"),
)


# ---------------------------------------------------------------------------
# The composition
# ---------------------------------------------------------------------------


def test_unit_state_is_the_measured_vocabulary() -> None:
    """D962, measured on the host: an instance of a template that is not
    installed answers `not-found` (exit 4); an instance nobody enabled answers
    `disabled` (exit 1); an enabled one `enabled` (exit 0). `absent` and
    `disabled` are kept apart because their repairs differ."""
    assert fleet.unit_state(4, "not-found\n") == fleet.ABSENT
    assert fleet.unit_state(1, "disabled\n") == fleet.DISABLED
    assert fleet.unit_state(0, "enabled\n") == fleet.ENABLED
    assert fleet.unit_state(None, "") == fleet.UNKNOWN, "a systemctl that could not run"
    assert fleet.unit_state(1, "") == fleet.UNKNOWN, "an answer this module does not know"


def test_a_project_is_scheduled_only_when_both_timers_are_enabled() -> None:
    both = {"full": fleet.ENABLED, "incr": fleet.ENABLED}
    assert fleet.schedule(both) == fleet.SCHEDULED
    assert fleet.schedule({"full": fleet.ENABLED, "incr": fleet.DISABLED}) == fleet.UNSCHEDULED
    assert fleet.schedule({"full": fleet.ABSENT, "incr": fleet.ABSENT}) == fleet.UNSCHEDULED
    assert fleet.schedule({"full": fleet.ENABLED, "incr": fleet.UNKNOWN}) == fleet.UNKNOWN
    assert fleet.schedule({}) == fleet.UNKNOWN


def test_the_timer_unit_is_the_templates_instance_name() -> None:
    """The template files are the authority for the name; this derives the
    instance from them once so Run 5's verb and the inventory agree."""
    for kind in fleet.TIMER_KINDS:
        template = REPO_ROOT / "systemd" / f"agentic-postgres-backup-{kind}@.timer"
        assert template.is_file(), f"{template} is not the template this derives from"
        assert fleet.timer_unit(kind, "k-dev") == f"agentic-postgres-backup-{kind}@k-dev.timer"
    with pytest.raises(ValueError):
        fleet.timer_unit("weekly", "k-dev")


def test_the_last_full_backup_comes_from_the_doctors_live_reading() -> None:
    """Never `backup_state.last_full_backup_at` off the document (D944): the
    doctor's repository probe read the repository now."""
    assert fleet.last_full_backup_at(doctor_document(*HEALTHY)) == "2026-08-28T10:20:02Z"
    unread = doctor_document(diagnosis.repository(status=None, last_full_backup_at=None))
    assert fleet.last_full_backup_at(unread) is None, "the module's null must not become a date"
    assert fleet.last_full_backup_at(None) is None


def test_age_in_days_is_whole_and_never_negative() -> None:
    assert fleet.age_days("2026-08-28T10:20:02Z", NOW) == 7
    assert fleet.age_days("2026-09-04T11:00:00Z", NOW) == 0
    assert fleet.age_days("2026-09-05T00:00:00Z", NOW) == 0, "a future backup is a clock problem"
    assert fleet.age_days(None, NOW) is None
    assert fleet.age_days("not a date", NOW) is None


def test_lifecycle_is_read_off_the_document_and_expiry_is_a_reading() -> None:
    """ADR 0186: a document without a lifecycle is permanent (a v14 document on
    a host not yet redeployed), and `expired` is true when an ephemeral
    project's `expires_at` is at or before now -- a reading, not a trigger."""
    permanent = {"kind": fleet.PERMANENT, "expires_at": None, "expired": False}
    assert fleet.lifecycle_of({}, NOW) == permanent
    assert fleet.lifecycle_of({"lifecycle": {"kind": "permanent"}}, NOW) == permanent

    live = {"lifecycle": {"kind": "ephemeral", "expires_at": "2026-09-04T13:00:00Z"}}
    assert fleet.lifecycle_of(live, NOW) == {
        "kind": fleet.EPHEMERAL,
        "expires_at": "2026-09-04T13:00:00Z",
        "expired": False,
    }
    at_noon = {"lifecycle": {"kind": "ephemeral", "expires_at": "2026-09-04T12:00:00Z"}}
    assert fleet.lifecycle_of(at_noon, NOW)["expired"] is True, "equal is expired"
    gone = {"lifecycle": {"kind": "ephemeral", "expires_at": "2026-09-01T00:00:00Z"}}
    assert fleet.lifecycle_of(gone, NOW)["expired"] is True


def test_the_text_rendering_marks_an_expired_project(deployed: dict[str, Any]) -> None:
    ephemeral = json.loads(json.dumps(deployed))
    ephemeral["project"]["lifecycle"] = {"kind": "ephemeral", "expires_at": "2026-09-01T00:00:00Z"}
    r = fleet.row(
        KEY,
        ephemeral,
        doctor=None,
        doctor_problem="not run",
        timers={},
        denials=None,
        window_hours=24,
        now=NOW,
    )
    text = fleet.render_text((r,), observed_at="t", window_hours=24)
    header = text.split("\n\n")[1].splitlines()[0]
    assert "ephemeral until 2026-09-01T00:00:00Z EXPIRED" in header
    parsed = json.loads(fleet.render_json((r,), observed_at="t", window_hours=24))
    assert parsed["projects"][0]["lifecycle"]["expired"] is True


def test_a_row_is_composed_from_the_document_and_the_live_readings(
    deployed: dict[str, Any],
) -> None:
    r = fleet.row(
        KEY,
        deployed,
        doctor=doctor_document(*HEALTHY),
        doctor_problem=None,
        timers={"full": fleet.ABSENT, "incr": fleet.ABSENT},
        denials={"scope_not_held": 2, "budget_exceeded": 1},
        window_hours=24,
        now=NOW,
    )
    assert r.key == KEY
    assert r.domain == deployed["project"]["domain"]
    assert r.environment == deployed["project"]["environment"]
    assert r.source_commit == COMMIT
    assert r.deployed_through_session == 3
    assert r.template_version == deployed["template_version"]
    assert r.lifecycle == {"kind": fleet.PERMANENT, "expires_at": None, "expired": False}
    assert r.health["worst"] == diagnosis.OK
    assert r.health["counts"][diagnosis.OK] == 3
    assert r.health["checks"]["migrations"] == diagnosis.OK
    assert r.backups["state"] == fleet.UNSCHEDULED
    assert r.backups["last_full_backup_at"] == "2026-08-28T10:20:02Z"
    assert r.backups["age_days"] == 7
    assert r.denials == {
        "window_hours": 24,
        "total": 3,
        "by_reason": {"budget_exceeded": 1, "scope_not_held": 2},
    }
    assert r.problems == ()


def test_a_row_says_what_it_could_not_measure(deployed: dict[str, Any]) -> None:
    """Unknown is not a pass and it is not hidden: a doctor that did not run
    and a table that could not be read are each a problem on the row."""
    r = fleet.row(
        KEY,
        deployed,
        doctor=None,
        doctor_problem="the doctor exited 4",
        timers={},
        denials=None,
        window_hours=24,
        now=NOW,
    )
    assert r.health["worst"] == diagnosis.UNKNOWN
    assert r.health["reason"] == "the doctor exited 4"
    assert r.backups["state"] == fleet.UNKNOWN
    assert r.denials["total"] is None
    assert any("health not measured" in p for p in r.problems)
    assert any("denials not measured" in p for p in r.problems)


def test_an_unreadable_project_is_a_row_not_an_exception() -> None:
    r = fleet.invalid_row("broken-dev", "the deployed document is not valid JSON")
    assert r.key == "broken-dev"
    assert r.domain is None
    assert r.health["worst"] == diagnosis.UNKNOWN
    assert r.problems == ("the deployed document is not valid JSON",)
    text = fleet.render_text((r,), observed_at="t", window_hours=24)
    assert "broken-dev  (the deployed document is not valid JSON)" in text


def test_every_value_is_printed_under_its_own_key(deployed: dict[str, Any]) -> None:
    """Two projects on one screen is the first place a value could land under
    the wrong project. Each line of the text carries the key it belongs to,
    and the JSON groups by key -- asserted by looking for A's domain inside
    B's block and not finding it."""
    other = json.loads(json.dumps(deployed))
    other["project"] = {**other["project"], "key": "zeta-dev", "domain": "zeta.example.test"}
    rows = (
        fleet.row(
            KEY,
            deployed,
            doctor=doctor_document(*HEALTHY),
            doctor_problem=None,
            timers={"full": fleet.ENABLED, "incr": fleet.ENABLED},
            denials={"scope_not_held": 1},
            window_hours=24,
            now=NOW,
        ),
        fleet.row(
            "zeta-dev",
            other,
            doctor=None,
            doctor_problem="not run",
            timers={"full": fleet.ABSENT, "incr": fleet.ABSENT},
            denials=None,
            window_hours=24,
            now=NOW,
        ),
    )
    text = fleet.render_text(rows, observed_at="t", window_hours=24)
    blocks = text.split("\n\n")
    assert len(blocks) == 3, text
    alpha_block = next(b for b in blocks if b.startswith(KEY))
    zeta_block = next(b for b in blocks if b.startswith("zeta-dev"))
    assert deployed["project"]["domain"] in alpha_block
    assert deployed["project"]["domain"] not in zeta_block
    assert "zeta.example.test" not in alpha_block
    for line in alpha_block.splitlines():
        assert line.lstrip().startswith(KEY), f"a line without its key: {line!r}"
    for line in zeta_block.splitlines():
        assert line.lstrip().startswith("zeta-dev"), f"a line without its key: {line!r}"

    parsed = json.loads(fleet.render_json(rows, observed_at="t", window_hours=24))
    assert [p["key"] for p in parsed["projects"]] == [KEY, "zeta-dev"]
    assert parsed["projects"][1]["domain"] == "zeta.example.test"
    assert parsed["projects"][0]["domain"] == deployed["project"]["domain"]


def test_render_json_is_deterministic_and_round_trips(deployed: dict[str, Any]) -> None:
    r = fleet.row(
        KEY,
        deployed,
        doctor=doctor_document(*HEALTHY),
        doctor_problem=None,
        timers={"full": fleet.ENABLED, "incr": fleet.ENABLED},
        denials={},
        window_hours=6,
        now=NOW,
    )
    first = fleet.render_json((r,), observed_at="t", window_hours=6)
    assert first == fleet.render_json((r,), observed_at="t", window_hours=6)
    parsed = json.loads(first)
    assert parsed["window_hours"] == 6
    assert parsed["projects"][0]["denials"]["total"] == 0
    assert list(parsed) == sorted(parsed)


def test_nothing_from_the_documents_sensitive_blocks_reaches_either_rendering(
    deployed: dict[str, Any],
) -> None:
    """The deployed document is 0600 root because it is a map of where the
    secrets are. The inventory reads its identity and release blocks and
    nothing else -- asserted by poisoning every other block and scanning."""
    poisoned = json.loads(json.dumps(deployed))
    for block in (
        "bootstrap",
        "secrets",
        "jwt",
        "backup",
        "backup_state",
        "tls",
        "mcp",
        "api",
        "storage",
    ):
        poisoned[block] = {"planted": SENSITIVE, "status": SENSITIVE}
    r = fleet.row(
        KEY,
        poisoned,
        doctor=doctor_document(*HEALTHY),
        doctor_problem=None,
        timers={"full": fleet.ENABLED, "incr": fleet.ENABLED},
        denials={"scope_not_held": 1},
        window_hours=24,
        now=NOW,
    )
    assert SENSITIVE not in fleet.render_text((r,), observed_at="t", window_hours=24)
    assert SENSITIVE not in fleet.render_json((r,), observed_at="t", window_hours=24)


def test_the_sensitive_scan_would_catch_a_leaky_row(deployed: dict[str, Any]) -> None:
    """The control (D374): a row that carried a poisoned value is caught by the
    same scan, spelled the same way."""
    r = fleet.invalid_row(KEY, f"reason quoting {SENSITIVE}")
    assert SENSITIVE in fleet.render_text((r,), observed_at="t", window_hours=24)


# ---------------------------------------------------------------------------
# The command, against a fixture root
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fleet_command() -> Any:
    spec = importlib.util.spec_from_file_location("apg_fleet", REPO_ROOT / "bin" / "fleet.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fixture_root(tmp_path: Path, deployed: dict[str, Any], rendered: dict[str, Any]) -> Path:
    """Three project directories: one valid, one holding a RENDERED document
    (which is not a deployed one), one empty."""
    root = tmp_path / "projects"
    (root / KEY).mkdir(parents=True)
    (root / KEY / "outputs.json").write_text(json.dumps(deployed), encoding="utf-8")
    (root / "broken-dev").mkdir()
    (root / "broken-dev" / "outputs.json").write_text(json.dumps(rendered), encoding="utf-8")
    (root / "empty-dev").mkdir()
    return root


def _snapshot(paths: list[Path]) -> dict[str, tuple[int, int]]:
    """mtime_ns and size of every file under each path, skipping the caches a
    Python process is allowed to touch and the repository's own history."""
    seen: dict[str, tuple[int, int]] = {}
    skip = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv", ".mypy_cache"}
    for base in paths:
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in skip]
            for name in filenames:
                path = Path(dirpath) / name
                try:
                    stat = path.stat()
                except OSError:
                    continue
                seen[str(path)] = (stat.st_mtime_ns, stat.st_size)
    return seen


def run_fleet(*arguments: str, home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "bin" / "fleet.py"), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        env={**os.environ, "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=600,
    )


def test_the_command_reports_every_project_directory_and_nothing_else(
    fixture_root: Path, tmp_path: Path, deployed: dict[str, Any]
) -> None:
    """`FLEET-INV-001`'s offline half: three directories in, three rows out,
    each under its own key, the valid one carrying its document's identity and
    a health verdict the doctor produced, the other two saying why not."""
    result = run_fleet("--root", str(fixture_root), "--json", home=tmp_path / "home")
    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    by_key = {p["key"]: p for p in parsed["projects"]}
    assert set(by_key) == {KEY, "broken-dev", "empty-dev"}

    valid = by_key[KEY]
    assert valid["domain"] == deployed["project"]["domain"]
    assert valid["source_commit"] == COMMIT
    # The doctor ran: its probes could not reach a fixture domain or a
    # container, so what comes back is verdicts it produced, not an absence.
    assert valid["health"]["checks"], f"the doctor produced no checks: {valid['health']}"
    assert "containers" in valid["health"]["checks"]
    assert valid["health"]["worst"] in {diagnosis.PROBLEM, diagnosis.UNKNOWN}
    assert valid["backups"]["timers"]["full"] in {fleet.ABSENT, fleet.DISABLED, fleet.UNKNOWN}

    assert by_key["broken-dev"]["problems"] == [
        "the deployed document does not validate against the outputs schema"
    ]
    assert by_key["empty-dev"]["problems"] == [
        "no deployed document: the directory exists and outputs.json does not"
    ]


def test_the_command_writes_nothing(fixture_root: Path, tmp_path: Path) -> None:
    """`FLEET-INV-002`. The fixture root, a home directory, and the checkout
    are byte-for-byte where they were, by mtime and size, after both
    renderings ran. An inventory that cached would fail here first."""
    home = tmp_path / "home"
    home.mkdir()
    watched = [fixture_root, home, REPO_ROOT]
    before = _snapshot(watched)
    for arguments in (("--root", str(fixture_root)), ("--root", str(fixture_root), "--json")):
        result = run_fleet(*arguments, home=home)
        assert result.returncode == 0, result.stderr
    after = _snapshot(watched)
    changed = sorted(set(before) ^ set(after)) + sorted(
        p for p in before if p in after and before[p] != after[p]
    )
    assert not changed, f"the inventory changed these files: {changed}"


def test_nothing_in_the_release_reads_the_inventory() -> None:
    """`FLEET-INV-002`'s other half, and ADR 0185's fourth property: no service,
    unit, route, deploy step or other command names the inventory. It is the
    end of a chain, never a link in one.

    The COMMAND, not the module: `backup.py` imports `fleet` for the timer
    vocabulary it shares with the inventory, which is one classifier rather
    than one reader, so the scan is for `bin/fleet`, `fleet.sh` and `fleet.py`.
    And the CODE, not the prose (D968): a gate's header telling an operator to
    run the inventory is not a reader of it.
    """
    mention = re.compile(r"bin/fleet\b|fleet\.(sh|py)\b")

    def code_of(path: Path) -> str:
        lines: list[str] = []
        in_usage = False
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "<<'USAGE'" in line:
                in_usage = True
                continue
            if in_usage:
                if line.strip() == "USAGE":
                    in_usage = False
                continue
            if line.lstrip().startswith("#"):
                continue
            lines.append(line)
        return "\n".join(lines)

    offenders: list[str] = []
    for directory, patterns in (
        ("systemd", ("*",)),
        ("libexec", ("*",)),
        ("services", ("**/*.py", "**/*.yaml", "**/*.toml")),
        ("bin", ("*.sh", "*.py")),
        (".", ("compose.yaml", "deploy.sh")),
    ):
        for pattern in patterns:
            for path in sorted((REPO_ROOT / directory).glob(pattern)):
                if not path.is_file() or path.stem == "fleet":
                    continue
                if mention.search(code_of(path)):
                    offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"these name the inventory, and only an operator may: {offenders}"
    assert list((REPO_ROOT / "systemd").iterdir()), "the scan saw no units"


def test_the_write_scan_would_notice_a_write(tmp_path: Path) -> None:
    """The control: the snapshot sees a file appear."""
    before = _snapshot([tmp_path])
    (tmp_path / "written").write_text("x", encoding="utf-8")
    after = _snapshot([tmp_path])
    assert set(after) - set(before) == {str(tmp_path / "written")}


def test_the_command_refuses_a_bad_window_and_a_missing_root(tmp_path: Path) -> None:
    home = tmp_path / "home"
    assert run_fleet("--root", str(tmp_path), "--window", "0", home=home).returncode == 2
    assert run_fleet("--root", str(tmp_path / "absent"), home=home).returncode == 4


def test_the_denial_statement_takes_only_the_validated_window(fleet_command: Any) -> None:
    """No caller text reaches the statement: the only formatted value is an
    integer this program bounded, and the reason column is coalesced so rows
    from before the taxonomy count rather than vanish (D940)."""
    statement = fleet_command.DENIALS_SQL.format(hours=24)
    assert "make_interval(hours => 24)" in statement
    assert "coalesce(denial_reason::text, 'unclassified')" in statement
    assert "outcome = 'refused'" in statement
    assert statement.count("{") == 0
