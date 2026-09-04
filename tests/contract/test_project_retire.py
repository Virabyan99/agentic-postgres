"""`FLEET-RETIRE-001`, `FLEET-RETIRE-002`, `FLEET-EXPIRE-001` -- retirement, offline.

Behavioural on `agentic_postgres.retirement` for what a retirement names and
refuses, and on the command for the two properties ADR 0187 makes it safe to
have: the plan mutates nothing, and the real run performs its steps in
`STEP_ORDER` -- the record first, the port release before any volume, the
provider destroy before the state directory -- against a fixture root with the
subprocess layer recorded rather than run.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, deployed_output, fleet, naming, retirement

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

KEY = "fixture-alpha-dev"
OTHER = "fixture-alpine-dev"
COMMIT = "a" * 40
INSTANCE_UUID = "01927d3f-1a2b-7c4d-8e5f-6a7b8c9d0e1f"
NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
HOST = REPO_ROOT / "host.example.yaml"


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rendered() -> dict[str, Any]:
    path = REPO_ROOT / ".generated" / KEY / "outputs.json"
    if not path.exists():
        pytest.skip("fixtures are not rendered in this working tree")
    return json.loads(path.read_text(encoding="utf-8"))


def build(rendered: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """A schema-valid deployed document, as `test_fleet` builds one."""
    arguments: dict[str, Any] = {
        "rendered": rendered,
        "source_commit": COMMIT,
        "health_status": "ready",
        "rest_status": "unavailable",
        "docs_status": "unavailable",
        "app_status": "unavailable",
        "app_docs_status": "unavailable",
        "storage_status": "unavailable",
        "mcp_status": "unavailable",
        "metrics_status": "unavailable",
        "api": deployed_output.API_NOT_PUBLISHED,
        "jwt": deployed_output.JWT_NOT_PUBLISHED,
        "mcp": deployed_output.MCP_NOT_PUBLISHED,
        "deployed_through_session": 16,
        "host": {
            "id": "apg-vps-01",
            "os_release": "26.04",
            "public_ipv4": "203.0.113.10",
            "public_ipv6": None,
        },
        "edge": {
            "stack_name": "apg-edge",
            "control_network": "apg-edge_control",
            "egress_network": "apg-edge_egress",
            "project_network_attached": True,
        },
        "tls": {
            "status": "issued",
            "acme_environment": "staging",
            "resolver": "letsencrypt-staging",
            "certificate_sha256": "c" * 64,
            "not_before": "2026-08-05T00:00:00Z",
            "not_after": "2026-11-03T00:00:00Z",
        },
        "bootstrap": {
            "status": "complete",
            "state_path": f"/etc/agentic-postgres/projects/{KEY}/bootstrap-state.json",
            "infisical_project_id": "5fffcd38-9af6-4f9d-bef9-c6eefc5e696f",
            "runtime_identity_id": "3302b5a4-7288-424f-bcd3-6cd158617827",
        },
        "secrets": {
            "status": "ready",
            "generation_id": "k7f2p9qd",
            "generation_manifest": (
                f"/var/lib/agentic-postgres/secrets/{KEY}/generations/k7f2p9qd/manifest.json"
            ),
            "required_names": ["session2_sentinel"],
            "fresh": True,
            "materialized_at": "2026-08-05T18:00:00Z",
        },
        "runtime": {
            "release_path": f"/opt/agentic-postgres/releases/{COMMIT}",
            "state_directory": f"/etc/agentic-postgres/projects/{KEY}",
            "compose_model_sha256": "d" * 64,
        },
        "database_observed": {
            "status": "observed",
            "server_version": "18.4",
            "extensions": {"vector": "0.8.6", "plpgsql": "1.0"},
            "memory": {"anon_mb": 62, "shmem_mb": 140, "file_mb": 410},
            "instance_uuid": INSTANCE_UUID,
        },
    }
    arguments.update(overrides)
    return deployed_output.build_deployed_document(**arguments)


@pytest.fixture(scope="module")
def deployed(rendered: dict[str, Any]) -> dict[str, Any]:
    return build(rendered)


def with_lifecycle(document: dict[str, Any], lifecycle: dict[str, str]) -> dict[str, Any]:
    changed = json.loads(json.dumps(document))
    changed["project"]["lifecycle"] = lifecycle
    return changed


ROOTS = {
    "state_root": Path("/etc/agentic-postgres/projects"),
    "secret_root": Path("/var/lib/agentic-postgres/secrets"),
    "rendered_root": Path("/var/lib/agentic-postgres/rendered"),
    "edge_dynamic_dir": Path("/var/lib/agentic-postgres/edge/dynamic"),
}


# ---------------------------------------------------------------------------
# What a retirement names, and where each name comes from
# ---------------------------------------------------------------------------


def test_every_resource_is_derived_from_the_key_or_read_off_its_document(
    deployed: dict[str, Any],
) -> None:
    r = retirement.resources_of(KEY, deployed, **ROOTS)
    assert r.compose_project == naming.compose_project_name(KEY)
    assert r.postgres_volume == naming.postgres_volume_name(KEY)
    assert r.store_volume == naming.store_volume_name(KEY)
    assert r.backup_network == naming.backup_network_name(KEY)
    assert r.edge_network == deployed["edge"]["project_edge_network"]
    assert r.internal_network == deployed["edge"]["project_internal_network"]
    assert r.unit == f"agentic-postgres-project@{KEY}.service"
    assert r.timers == tuple(fleet.timer_unit(k, KEY) for k in fleet.TIMER_KINDS)
    assert r.state_directory == ROOTS["state_root"] / KEY
    assert r.secrets_directory == ROOTS["secret_root"] / KEY
    assert r.rendered_directory == ROOTS["rendered_root"] / KEY
    assert r.installed_manifest == ROOTS["state_root"] / KEY / "manifest.yaml"
    assert r.edge_files[0] == ROOTS["edge_dynamic_dir"] / f"project-{KEY}.yaml"
    assert r.instance_uuid == INSTANCE_UUID
    assert r.deployed_through_session == 16
    assert r.backup_bucket == deployed["backup"]["bucket"]
    assert r.backup_stanza == deployed["backup"]["stanza"]
    assert r.infisical_project_id == deployed["bootstrap"]["infisical_project_id"]

    # Scoped by derivation: every name carries this key and none carries the
    # other fixture's, which shares a twelve-character prefix with it.
    for name in (
        r.compose_project,
        r.postgres_volume,
        r.store_volume,
        r.backup_network,
        r.edge_network,
        r.internal_network,
        r.unit,
        *r.timers,
        *(
            str(p)
            for p in (r.state_directory, r.secrets_directory, r.rendered_directory, *r.edge_files)
        ),
    ):
        assert KEY in name, name
        assert OTHER not in name, name


def test_a_document_naming_another_project_is_refused(deployed: dict[str, Any]) -> None:
    """A document under one key naming another is the one thing a retirement
    must never act on: every derived name would be for the wrong project."""
    with pytest.raises(ValueError, match="names project"):
        retirement.resources_of(OTHER, deployed, **ROOTS)
    with pytest.raises(ValueError, match="not a project key"):
        retirement.resources_of("../etc", deployed, **ROOTS)


def test_the_key_pattern_agrees_with_the_schema_and_the_runtime() -> None:
    schema = json.loads((REPO_ROOT / "schemas" / "outputs.schema.json").read_text("utf-8"))
    assert retirement.PROJECT_KEY.pattern == schema["$defs"]["projectKey"]["pattern"]
    runtime = (REPO_ROOT / "bin" / "project-runtime.sh").read_text(encoding="utf-8")
    assert f"PROJECT_KEY_PATTERN='{retirement.PROJECT_KEY.pattern}'" in runtime


# ---------------------------------------------------------------------------
# The refusals (ADR 0186): read, never acted on
# ---------------------------------------------------------------------------


def test_a_permanent_project_needs_the_flag_and_an_ephemeral_one_its_expiry() -> None:
    permanent = {"kind": "permanent"}
    assert "pass --permanent" in retirement.refusal(
        permanent, permanent=False, before_expiry=False, now=NOW
    )
    assert retirement.refusal(permanent, permanent=True, before_expiry=False, now=NOW) is None
    assert "does not apply" in retirement.refusal(
        permanent, permanent=True, before_expiry=True, now=NOW
    )

    live = {"kind": "ephemeral", "expires_at": "2026-09-04T13:00:00Z"}
    assert "pass --before-expiry" in retirement.refusal(
        live, permanent=False, before_expiry=False, now=NOW
    )
    assert retirement.refusal(live, permanent=False, before_expiry=True, now=NOW) is None
    assert "does not apply" in retirement.refusal(
        live, permanent=True, before_expiry=False, now=NOW
    )

    gone = {"kind": "ephemeral", "expires_at": "2026-09-04T12:00:00Z"}
    assert retirement.refusal(gone, permanent=False, before_expiry=False, now=NOW) is None, (
        "equal is expired"
    )
    assert "does not apply" in retirement.refusal(
        gone, permanent=False, before_expiry=True, now=NOW
    )


# ---------------------------------------------------------------------------
# The order is a contract (D956)
# ---------------------------------------------------------------------------


def test_the_steps_come_in_the_only_order_they_may_run(deployed: dict[str, Any]) -> None:
    r = retirement.resources_of(KEY, deployed, **ROOTS)
    plan = retirement.steps(
        r, host_manifest=HOST, root_dir=REPO_ROOT, destroy_data=True, operator_credential_file=None
    )
    names = [step.name for step in plan]
    assert tuple(names) == retirement.STEP_ORDER
    assert names.index("record") == 0
    assert names.index("release-ports") < names.index("remove-volumes")
    assert names.index("provider-destroy") < names.index("remove-directories")
    assert names.index("down") < names.index("disable-units")

    by_name = {step.name: step for step in plan}
    assert by_name["release-ports"].commands[0][-1] == INSTANCE_UUID
    assert "--confirm" in by_name["provider-destroy"].commands[0]
    assert by_name["provider-destroy"].commands[0][-1] == KEY
    assert str(r.installed_manifest) in by_name["provider-destroy"].commands[0]
    assert [c[-1] for c in by_name["remove-volumes"].commands] == [
        r.postgres_volume,
        r.store_volume,
    ]
    assert by_name["remove-directories"].paths == (
        r.state_directory,
        r.secrets_directory,
        r.rendered_directory,
    )

    kept = retirement.steps(
        r, host_manifest=HOST, root_dir=REPO_ROOT, destroy_data=False, operator_credential_file=None
    )
    assert kept[-1].commands == (), "without --destroy-data no volume command exists at all"
    assert "keep volumes" in kept[-1].what


def test_nothing_off_the_host_is_a_step(deployed: dict[str, Any], tmp_path: Path) -> None:
    """`FLEET-RETIRE-002`: no command names the bucket, the stanza or a
    secret; the record names them as what still holds the backups."""
    r = retirement.resources_of(KEY, deployed, **ROOTS)
    plan = retirement.steps(
        r, host_manifest=HOST, root_dir=REPO_ROOT, destroy_data=True, operator_credential_file=None
    )
    arguments = [argument for step in plan for c in step.commands for argument in c]
    # The bucket by exact argument. The stanza is not asserted: `naming`
    # derives it AS the project key, so every `--project-key` would match it.
    assert r.backup_bucket not in arguments
    joined = " ".join(arguments)
    assert "pgbackrest" not in joined
    assert "stanza-delete" not in joined
    assert "backup.sh" not in joined
    for step in plan:
        for path in step.paths:
            assert KEY in str(path)

    document = retirement.record(
        r, captured_at=NOW, destroy_data=True, record_path=tmp_path / "record.json"
    )
    assert document["project_key"] == KEY
    assert document["captured_at"] == "2026-09-04T12:00:00Z"
    assert r.backup_bucket in document["backups_still_held"]
    assert r.backup_stanza in document["backups_still_held"]
    assert "console" in document["backups_still_held"]
    assert document["resources"]["port_allocation_instance_uuid"] == INSTANCE_UUID
    assert document["resources"]["volumes"] == [r.postgres_volume, r.store_volume]


# ---------------------------------------------------------------------------
# The command, against a fixture root
# ---------------------------------------------------------------------------


@pytest.fixture
def command() -> Any:
    spec = importlib.util.spec_from_file_location(
        "apg_retire", REPO_ROOT / "bin" / "project-retire.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def host_layout(
    tmp_path: Path, deployed: dict[str, Any], monkeypatch: pytest.MonkeyPatch, command: Any
) -> dict[str, Path]:
    """A host's worth of directories for one project, under tmp, and the
    command pointed at them: the state root by flag (as the inventory is), the
    secrets, rendered and edge roots by the module constants a test may set."""
    state = tmp_path / "projects"
    secrets = tmp_path / "secrets"
    rendered = tmp_path / "rendered"
    edge = tmp_path / "edge" / "dynamic"
    for root in (
        state / KEY,
        secrets / KEY / "generations" / "g1",
        rendered / KEY,
        edge,
        state / OTHER,
    ):
        root.mkdir(parents=True)
    (state / KEY / "outputs.json").write_text(json.dumps(deployed), encoding="utf-8")
    (state / KEY / "manifest.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    (state / OTHER / "outputs.json").write_text("{}", encoding="utf-8")
    (secrets / KEY / "generations" / "g1" / "manifest.json").write_text("{}", encoding="utf-8")
    (rendered / KEY / "outputs.json").write_text("{}", encoding="utf-8")
    (edge / f"project-{KEY}.yaml").write_text("http: {}\n", encoding="utf-8")
    (edge / f"project-{OTHER}.yaml").write_text("http: {}\n", encoding="utf-8")
    monkeypatch.setattr(command, "SECRET_ROOT", secrets)
    monkeypatch.setattr(command, "EDGE_DYNAMIC_DIR", edge)
    monkeypatch.setattr(command.deployed_output, "RENDERED_ROOT", rendered)
    return {"state": state, "secrets": secrets, "rendered": rendered, "edge": edge}


def _snapshot(base: Path) -> dict[str, tuple[int, int]]:
    seen: dict[str, tuple[int, int]] = {}
    for dirpath, _, filenames in os.walk(base):
        for name in filenames:
            path = Path(dirpath) / name
            stat = path.stat()
            seen[str(path)] = (stat.st_mtime_ns, stat.st_size)
    return seen


def run_command(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "bin" / "project-retire.py"), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=120,
    )


def test_the_plan_names_every_resource_and_mutates_nothing(
    host_layout: dict[str, Path], tmp_path: Path
) -> None:
    """`FLEET-RETIRE-001`'s `--plan` half, as a subprocess: no record written,
    nothing under the fixture host changed, and every derived name printed."""
    record = tmp_path / "record.json"
    before = _snapshot(tmp_path)
    result = run_command(
        "--host",
        str(HOST),
        "--project",
        KEY,
        "--confirm",
        KEY,
        "--record",
        str(record),
        "--plan",
        "--permanent",
        "--destroy-data",
        "--root",
        str(host_layout["state"]),
    )
    assert result.returncode == 0, result.stderr
    assert _snapshot(tmp_path) == before, "the plan changed a file"
    assert not record.exists()
    out = result.stdout
    for expected in (
        naming.compose_project_name(KEY),
        naming.postgres_volume_name(KEY),
        naming.store_volume_name(KEY),
        f"agentic-postgres-project@{KEY}.service",
        fleet.timer_unit("full", KEY),
        INSTANCE_UUID,
        "project-runtime.sh",
        "bootstrap-providers.sh",
        "database-ports.sh",
        "plan only, nothing changes",
        "never touched",
    ):
        assert expected in out, f"the plan does not name {expected!r}:\n{out}"
    assert OTHER not in out, "the plan names the other project"


def test_the_command_refuses_before_reading_anything(
    host_layout: dict[str, Path], tmp_path: Path
) -> None:
    record = tmp_path / "record.json"
    base = (
        "--host",
        str(HOST),
        "--project",
        KEY,
        "--record",
        str(record),
        "--root",
        str(host_layout["state"]),
    )

    missing = run_command(*base, "--plan")
    assert missing.returncode == 2 and "--confirm" in missing.stderr

    # The refusal's OWN sentence, not the "Nothing was changed" every refusal
    # ends with: a battery arm that dropped the comparison survived on that
    # shared tail, because the next refusal (--permanent) carries it too.
    wrong = run_command(*base, "--confirm", OTHER, "--plan")
    assert wrong.returncode == 2
    assert f"--confirm said {OTHER!r} but this project is {KEY!r}" in wrong.stderr

    permanent = run_command(*base, "--confirm", KEY, "--plan")
    assert permanent.returncode == 2 and "--permanent" in permanent.stderr

    traversal = run_command(
        "--host",
        str(HOST),
        "--project",
        "../etc",
        "--confirm",
        "../etc",
        "--record",
        str(record),
        "--plan",
    )
    assert traversal.returncode == 2 and "not a valid project key" in traversal.stderr

    never = run_command(
        "--host",
        str(HOST),
        "--project",
        "never-deployed-dev",
        "--confirm",
        "never-deployed-dev",
        "--record",
        str(record),
        "--plan",
        "--root",
        str(host_layout["state"]),
    )
    assert never.returncode == 4

    assert not record.exists()


def test_an_unexpired_ephemeral_project_is_refused_without_the_flag(
    host_layout: dict[str, Path], deployed: dict[str, Any], tmp_path: Path
) -> None:
    state = host_layout["state"]
    live = with_lifecycle(deployed, {"kind": "ephemeral", "expires_at": "2999-01-01T00:00:00Z"})
    (state / KEY / "outputs.json").write_text(json.dumps(live), encoding="utf-8")
    base = (
        "--host",
        str(HOST),
        "--project",
        KEY,
        "--confirm",
        KEY,
        "--record",
        str(tmp_path / "r.json"),
        "--root",
        str(state),
        "--plan",
    )
    refused = run_command(*base)
    assert refused.returncode == 2 and "--before-expiry" in refused.stderr
    assert run_command(*base, "--before-expiry").returncode == 0

    gone = with_lifecycle(deployed, {"kind": "ephemeral", "expires_at": "2000-01-01T00:00:00Z"})
    (state / KEY / "outputs.json").write_text(json.dumps(gone), encoding="utf-8")
    assert run_command(*base).returncode == 0, "an expired project needs no flag"
    assert run_command(*base, "--before-expiry").returncode == 2, (
        "a flag that does not apply is refused"
    )


def test_a_real_run_performs_the_steps_in_order_and_writes_the_record_first(
    host_layout: dict[str, Path], command: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The order, measured (D956): every subprocess recorded and every removal
    observed, with the record's mtime before the first command."""
    calls: list[tuple[str, ...]] = []
    record = tmp_path / "record.json"
    record_seen_before: list[bool] = []

    def fake_run(*argv: str, timeout: int = 0) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        record_seen_before.append(record.exists())
        stdout = "enabled\n" if argv[:2] == ("systemctl", "is-enabled") else ""
        return subprocess.CompletedProcess(args=list(argv), returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(command, "run", fake_run)
    credential = tmp_path / "token"
    credential.write_text("x", encoding="utf-8")
    code = command.main(
        [
            "--host",
            str(HOST),
            "--project",
            KEY,
            "--confirm",
            KEY,
            "--record",
            str(record),
            "--permanent",
            "--destroy-data",
            "--operator-credential-file",
            str(credential),
            "--root",
            str(host_layout["state"]),
        ]
    )
    assert code == 0
    assert all(record_seen_before), "a command ran before the record was written"
    assert oct(record.stat().st_mode & 0o777) == "0o600"
    written = json.loads(record.read_text(encoding="utf-8"))
    assert written["project_key"] == KEY and written["destroy_data"] is True

    programs = [
        Path(c[0]).name if c[0] not in ("systemctl", "docker") else " ".join(c[:2]) for c in calls
    ]
    first = {name: programs.index(name) for name in set(programs)}
    assert first["project-runtime.sh"] < first["systemctl is-enabled"]
    assert first["systemctl is-enabled"] < first["database-ports.sh"]
    assert first["database-ports.sh"] < first["bootstrap-providers.sh"]
    assert first["bootstrap-providers.sh"] < first["docker volume"]
    down = next(c for c in calls if c[0].endswith("project-runtime.sh"))
    assert down[-1] == "down" and "--through-session" in down and "16" in down
    release = next(c for c in calls if c[0].endswith("database-ports.sh"))
    assert release[1] == "release" and release[-1] == INSTANCE_UUID
    destroy = next(c for c in calls if c[0].endswith("bootstrap-providers.sh"))
    assert "--destroy" in destroy and destroy[destroy.index("--confirm") + 1] == KEY
    volumes = [c[-1] for c in calls if c[:3] == ("docker", "volume", "rm")]
    assert volumes == [naming.postgres_volume_name(KEY), naming.store_volume_name(KEY)]

    # The other project's directories and edge file are exactly where they were.
    assert not (host_layout["state"] / KEY).exists()
    assert not (host_layout["secrets"] / KEY).exists()
    assert not (host_layout["rendered"] / KEY).exists()
    assert not (host_layout["edge"] / f"project-{KEY}.yaml").exists()
    assert (host_layout["state"] / OTHER / "outputs.json").exists()
    assert (host_layout["edge"] / f"project-{OTHER}.yaml").exists()


def test_a_failed_step_stops_the_run_and_names_itself(
    host_layout: dict[str, Path],
    command: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def failing_release(*argv: str, timeout: int = 0) -> subprocess.CompletedProcess[str]:
        code = 4 if argv[0].endswith("database-ports.sh") else 0
        stdout = "enabled\n" if argv[:2] == ("systemctl", "is-enabled") else ""
        return subprocess.CompletedProcess(
            args=list(argv), returncode=code, stdout=stdout, stderr=""
        )

    monkeypatch.setattr(command, "run", failing_release)
    record = tmp_path / "record.json"
    code = command.main(
        [
            "--host",
            str(HOST),
            "--project",
            KEY,
            "--confirm",
            KEY,
            "--record",
            str(record),
            "--permanent",
            "--destroy-data",
            "--root",
            str(host_layout["state"]),
        ]
    )
    captured = capsys.readouterr()
    assert code == 6
    assert "release-ports" in captured.err and "did not run" in captured.err
    assert record.exists(), "the record was written before the failing step"
    assert (host_layout["state"] / KEY).exists(), "a later step ran after the failure"
    assert (host_layout["edge"] / f"project-{KEY}.yaml").exists()


def test_a_record_is_never_overwritten(
    host_layout: dict[str, Path], command: Any, tmp_path: Path
) -> None:
    record = tmp_path / "record.json"
    record.write_text("{}", encoding="utf-8")
    code = command.main(
        [
            "--host",
            str(HOST),
            "--project",
            KEY,
            "--confirm",
            KEY,
            "--record",
            str(record),
            "--permanent",
            "--root",
            str(host_layout["state"]),
        ]
    )
    assert code == 2
    assert record.read_text(encoding="utf-8") == "{}"


# ---------------------------------------------------------------------------
# Nothing in the release acts on expiry (FLEET-EXPIRE-001)
# ---------------------------------------------------------------------------


def code_of(path: Path) -> str:
    """A file's code: comment lines and the usage heredoc removed (D968).

    The scan below is about what a file DOES. The first form read prose too,
    and the Session 17 gate's header -- which tells the operator to run the
    verb and pass its record -- was reported as a unit acting on expiry. The
    same distinction `test_root_script_policy.code_of` draws, for the same
    reason: a comment explaining why a script does not do something must not
    fail the test asserting it does not.
    """
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


def test_the_code_stripper_keeps_code_and_drops_prose(tmp_path: Path) -> None:
    """The control for `code_of`: a mention in a comment or the usage block is
    dropped, a mention in a command line is kept."""
    script = tmp_path / "x.sh"
    script.write_text(
        "#!/usr/bin/env bash\n# run bin/project-retire.sh first\nusage() {\n  cat <<'USAGE'\n"
        "  bin/project-retire.sh --plan\nUSAGE\n}\nexec bin/other.sh\n",
        encoding="utf-8",
    )
    assert "project-retire" not in code_of(script)
    assert "exec bin/other.sh" in code_of(script)
    script.write_text("exec bin/project-retire.sh --confirm x\n", encoding="utf-8")
    assert "project-retire" in code_of(script)


def test_no_unit_timer_or_command_names_the_retirement_verb() -> None:
    """Expiry is a fact an operator reads (ADR 0186). The only files that name
    the verb IN CODE are the verb itself; prose that tells an operator to run
    it is not a unit acting on expiry (D968)."""
    mention = re.compile(r"project-retire")
    offenders: list[str] = []
    for directory, patterns in (
        ("systemd", ("*",)),
        ("libexec", ("*",)),
        ("bin", ("*.sh", "*.py")),
        (".", ("compose.yaml", "deploy.sh")),
    ):
        for pattern in patterns:
            for path in sorted((REPO_ROOT / directory).glob(pattern)):
                if not path.is_file() or path.stem in {"project-retire"}:
                    continue
                if mention.search(code_of(path)):
                    offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"these name the retirement verb, and only a human may: {offenders}"
    assert (REPO_ROOT / "systemd").is_dir() and list((REPO_ROOT / "systemd").iterdir()), (
        "the scan saw no units"
    )


def test_volume_removal_lives_in_exactly_two_commands() -> None:
    """`test_neither_command_can_remove_a_volume` says volume removal exists in
    one place, the drill. ADR 0187 makes it two, and this is the list."""
    found = sorted(
        str(path.relative_to(REPO_ROOT))
        for path in (REPO_ROOT / "bin").glob("*")
        if path.is_file() and "volume rm" in path.read_text(encoding="utf-8", errors="replace")
    )
    assert found == ["bin/restore-test.py", "bin/restore-test.sh"], found
    module = (REPO_ROOT / "src" / "agentic_postgres" / "retirement.py").read_text(encoding="utf-8")
    assert '("docker", "volume", "rm", name)' in module, "the retirement's volume removal moved"
    assert '"rm", "-f"' not in module, "a forced removal cannot tell removed from never there"
    command = (REPO_ROOT / "bin" / "project-retire.py").read_text(encoding="utf-8")
    assert '"--force"' not in command, "a --force is typed reflexively; a matching name is not"
