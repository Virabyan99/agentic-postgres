"""`bin/branch-runtime.py` and `infra/branch/compose.yaml`, without a daemon
(Session 40, ADR 0271, D2426, D2427, D2431, D2438, D2439).

The runtime's phases are module-level functions, so these proofs drive
`create` with each phase replaced by a recorder and read the ORDER it ran them
in -- the property ADR 0271 states as an ordering: the record before anything
is created, the re-key before either door. Admission is driven through the
product's own `capacity_probe.read` and `decide`; `delete` through a recording
`docker`. `test_branch_runtime_on_a_cluster.py` runs the same phases on a real
cluster.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import (
    REPO_ROOT,
    branch_plan,
    branch_record,
    host_config,
    naming,
    restore_drill,
    runtime_override,
    secrets_contract,
)

pytestmark = [pytest.mark.contract, pytest.mark.security, pytest.mark.p0]

KEY = "slot3-prod"
DOMAIN = "slot3.agenticpostgresql.com"
HOST = REPO_ROOT / "host.example.yaml"
COMPOSE = REPO_ROOT / "infra" / "branch" / "compose.yaml"
IMAGE_TAG = f"apg-{KEY}-postgres:latest"
PLATFORM_DIGEST = "sha256:" + "9" * 64
VERIFIERS = {
    "customer_app": "SCRAM-SHA-256$4096:" + "A" * 22 + "==$" + "B" * 43 + "=:" + "C" * 43 + "=",
    "customer_admin": "SCRAM-SHA-256$4096:" + "D" * 22 + "==$" + "E" * 43 + "=:" + "F" * 43 + "=",
}


def _runtime() -> Any:
    spec = importlib.util.spec_from_file_location(
        "apg_branch_runtime", REPO_ROOT / "bin" / "branch-runtime.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inspect() -> dict[str, Any]:
    contract = secrets_contract.load_secret_contract(REPO_ROOT / "secrets.required.yaml")
    mounts = [
        {"Type": "volume", "Name": naming.postgres_volume_name(KEY),
         "Destination": runtime_override.POSTGRES_VOLUME_TARGET, "RW": True},
    ] + [
        {"Type": "bind", "Source": f"/var/lib/agentic-postgres/secrets/{KEY}/{p.rsplit('/')[-1]}",
         "Destination": p, "RW": False}
        for p in restore_drill.required_container_paths(contract)
    ]  # fmt: skip
    # A real container's own record of its image (D2513): the tag it was made
    # from and the platform manifest of the content it runs.
    descriptor = {"digest": PLATFORM_DIGEST, "platform": {"os": "linux", "architecture": "amd64"}}
    return {"Name": f"/apg-{KEY}-postgres-1", "Image": "sha256:" + "8" * 64, "Mounts": mounts,
            "Config": {"Env": [], "Image": IMAGE_TAG}, "State": {"Running": True},
            "ImageManifestDescriptor": descriptor}  # fmt: skip


def _document() -> dict[str, Any]:
    return {
        "source_commit": "b0249ce5667610a45746c6cec89c3eb38457ed70",
        "project": {"key": KEY, "domain": DOMAIN},
        "backup": {"enabled": True, "stanza": KEY},
        "database": {
            "name": "slot3_prod",
            "container": f"apg-{KEY}-postgres-1",
            "roles": naming.database_roles("slot3_prod"),
            "public": {"enabled": True},
        },
    }


def _plan(runtime: Any, target: str | None = None) -> branch_plan.BranchPlan:
    return runtime.build_plan(_document(), _inspect(), "dev", target)


def _arguments(**extra: Any) -> argparse.Namespace:
    values = {
        "parent_outputs": Path("/unused/outputs.json"),
        "branch": "dev",
        "verifiers_stdin": True,
        "target_time": None,
        "operation": "0a7b6f5e-0000-4000-8000-000000000040",
        "host": HOST,
        "expires_at": None,
        "expires_for": None,
    }
    values.update(extra)
    return argparse.Namespace(**values)


@pytest.fixture
def recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, list[str]]:
    """The runtime with every phase that touches a daemon replaced by a recorder."""
    runtime = _runtime()
    calls: list[str] = []
    monkeypatch.setattr(runtime, "BRANCH_ROOT", tmp_path / "branches")
    monkeypatch.setattr(runtime, "require_root", lambda: None)
    monkeypatch.setattr(runtime, "read_verifiers", lambda: dict(VERIFIERS))
    monkeypatch.setattr(runtime, "load_document", lambda path: _document())
    monkeypatch.setattr(runtime, "load_host", lambda path: {"edge": {"acme_resolver_name": "le"}})
    monkeypatch.setattr(runtime, "inspect_running", lambda container, what: _inspect())
    # Resolving the parent's image reads the daemon (D2497); its three answers are
    # test_runnable_image.py's. Here it answers "the container's own id".
    monkeypatch.setattr(
        runtime.restore_drill,
        "runnable_image",
        lambda inspect, docker: (calls.append("image"), inspect["Image"])[1],
    )
    monkeypatch.setattr(runtime, "check_dns", lambda plan, host: calls.append("dns"))
    window = (datetime(2026, 10, 12, 10, 39, tzinfo=UTC), datetime(2026, 10, 14, 8, 0, tzinfo=UTC))
    monkeypatch.setattr(
        runtime, "read_window", lambda document: (calls.append("window"), window)[1]
    )
    monkeypatch.setattr(runtime, "admit", lambda plan, host: calls.append("admit"))
    original_record = runtime.record

    def record(plan: Any, *, state: str, **values: Any) -> Any:
        calls.append(f"record:{state}")
        return original_record(plan, state=state, **values)

    monkeypatch.setattr(runtime, "record", record)
    for step in ("create_volume", "restore", "persist", "write_userlists", "open_doors"):
        monkeypatch.setattr(runtime, step, lambda plan, _s=step: calls.append(_s))
    monkeypatch.setattr(
        runtime,
        "recover",
        lambda plan: (calls.append("recover"), ("2026-10-14 08:04:58+00", 2, 3.0))[1],
    )
    monkeypatch.setattr(
        runtime, "write_compose_state", lambda plan, **_: calls.append("write_compose_state")
    )
    monkeypatch.setattr(runtime, "rekey", lambda plan, verifiers: calls.append("rekey"))
    monkeypatch.setattr(runtime, "attach", lambda names: calls.append("attach"))
    monkeypatch.setattr(
        runtime,
        "pin_image",
        lambda directory, current: (calls.append("pin_image"), "sha256:" + "6" * 64)[1],
    )
    monkeypatch.setattr(
        runtime, "await_door", lambda hosts: (calls.append("door"), ("ready", None))[1]
    )
    return runtime, calls


def test_the_poolers_start_after_the_rekey(recorded: tuple[Any, list[str]]) -> None:
    """`create`'s order: the readings and the admission before anything exists,
    the record `creating` BEFORE the volume, then restore, recovery, the
    persistent postgres, the RE-KEY, the userlists, the doors and the edge --
    and only then `ready`, with the point the recovery reached.

    Goes red if: the re-key moves after the doors (a door would answer the
    parent's password), the record moves after the restore (a crash would leave
    a volume no reader charges), or admission moves after anything is created."""
    runtime, calls = recorded
    assert runtime.command_create(_arguments()) == 0
    assert calls == [
        "image", "dns", "window", "admit", "record:creating", "create_volume", "restore", "recover",
        "write_compose_state", "pin_image", "persist", "rekey", "write_userlists", "open_doors",
        "attach", "door", "record:ready",
    ], calls  # fmt: skip
    assert calls.index("rekey") < calls.index("open_doors") < calls.index("attach")
    # D2515: `ready` only after the door; D2513: the image pinned before the
    # persistent phase's compose up, from the identity the record carries.
    assert calls.index("door") < calls.index("record:ready")
    assert calls.index("pin_image") < calls.index("persist")
    record = branch_record.read(branch_record.record_path(KEY, "dev", root=runtime.BRANCH_ROOT))
    assert record is not None and record.state == "ready"
    # D2483: psql's spelling of the reached point is written RFC 3339.
    assert (record.reached_point, record.timeline) == ("2026-10-14T08:04:58+00:00", 2)
    assert record.parent_commit == "b0249ce5667610a45746c6cec89c3eb38457ed70"
    assert record.unreclaimable_mb == 192
    assert (record.pool_host, record.direct_host) == (f"dev.pool.{DOMAIN}", f"dev.direct.{DOMAIN}")
    assert (record.image_tag, record.image_digest, record.image_platform) == (
        IMAGE_TAG, PLATFORM_DIGEST, "linux/amd64",
    )  # fmt: skip
    assert (record.door, record.reason) == ("ready", None)


def test_a_failure_after_the_record_leaves_it_failed(
    recorded: tuple[Any, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A phase that fails after the record exists leaves `failed` -- a record
    `delete` reads and cleans up after -- and the doors are never opened."""
    runtime, calls = recorded

    def broken(plan: Any) -> None:
        raise runtime.OperatorError(runtime.EXIT_UNKNOWN, "the branch's postgres did not start")

    monkeypatch.setattr(runtime, "persist", broken)
    with pytest.raises(runtime.OperatorError):
        runtime.command_create(_arguments())
    assert "open_doors" not in calls and "rekey" not in calls
    assert calls[-1] == "record:failed", calls
    record = branch_record.read(branch_record.record_path(KEY, "dev", root=runtime.BRANCH_ROOT))
    assert record is not None and record.state == "failed"
    # D2514: the failure's own line is recorded, so a reader can say why.
    assert record.reason == "the branch's postgres did not start", record.reason


def test_an_existing_branch_or_a_doorless_parent_is_refused_before_anything(
    recorded: tuple[Any, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """One live branch is the control plane's rule (D2430); on the host a
    branch that exists is refused before any reading, and so is a parent with
    no public endpoints (a branch would have no door)."""
    runtime, calls = recorded
    assert runtime.command_create(_arguments()) == 0
    calls.clear()
    with pytest.raises(runtime.OperatorError) as exists:
        runtime.command_create(_arguments())
    assert exists.value.code == runtime.EXIT_REFUSED and "already exists" in str(exists.value)
    assert calls == []
    doorless = _document()
    doorless["database"]["public"] = {"enabled": False}
    with pytest.raises(runtime.OperatorError, match="no public endpoints"):
        runtime.refuse(doorless, "qa")


def test_a_point_outside_the_window_is_refused_before_anything_persists() -> None:
    """D2457/D2456: the window is the oldest backup's STOP to the last
    archived time; a point before or after it is exit 7, and a point inside
    passes (the control)."""
    runtime = _runtime()
    window = (datetime(2026, 10, 12, 10, 39, tzinfo=UTC), datetime(2026, 10, 14, 8, 0, tzinfo=UTC))
    runtime.check_window("2026-10-13 12:00:00.000000+00:00", window)
    runtime.check_window(None, window)
    for outside in ("2026-10-12 10:38:59.000000+00:00", "2026-10-14 08:00:01.000000+00:00"):
        with pytest.raises(runtime.OperatorError) as refused:
            runtime.check_window(outside, window)
        assert refused.value.code == runtime.EXIT_UNSAFE
        assert "outside this project's restore window" in str(refused.value)


def _write_branches(root: Path, count: int) -> None:
    for index in range(count):
        name = f"br{index}"
        branch_record.write(
            branch_record.record_path(KEY, name, root=root),
            branch_record.Record(
                project_key=KEY, branch=name, state="ready", operation="x",
                requested_point=None, reached_point=None, timeline=2, parent_commit=None,
                pool_host=f"{name}.pool.{DOMAIN}", direct_host=f"{name}.direct.{DOMAIN}",
                expires_at=None, expires_for=None, unreclaimable_mb=192,
                created_at="2026-10-14T08:00:00Z", updated_at="2026-10-14T08:00:00Z",
                image_tag=IMAGE_TAG, image_digest=PLATFORM_DIGEST, image_platform="linux/amd64",
            ),
        )  # fmt: skip


def test_a_branch_that_does_not_fit_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Admission through the product's own `capacity_probe.read` and `decide`
    (D2431): with enough recorded branches to fill the example host's declared
    memory, a new branch is refused exit 12 and the committed line names them;
    with none, the same branch is admitted (the control).

    Goes red if: admission stops counting branches, or a refusal is not 12."""
    runtime = _runtime()
    declared = host_config.declared_capacity(host_config.load_host_manifest(HOST))
    assert declared is not None
    monkeypatch.setattr(runtime, "PROJECT_ROOT", tmp_path / "projects")
    monkeypatch.setattr(runtime, "BRANCH_ROOT", tmp_path / "branches")
    (tmp_path / "projects").mkdir()

    def runner(*command: str, timeout: int = 60) -> subprocess.CompletedProcess | None:
        if command[:2] == ("docker", "info"):
            return subprocess.CompletedProcess(command, 0, f"{tmp_path}\n", "")
        return None  # the ceilings: a report line, never an input to the rule

    monkeypatch.setattr(runtime, "_runner", runner)
    # Only memory decides here: the disk is measured as 100 GiB free.
    hundred = shutil._ntuple_diskusage(100 * 1024**3, 0, 100 * 1024**3)
    monkeypatch.setattr(runtime.capacity_probe, "disk_usage_near", lambda path: (hundred, path))
    plan = _plan(runtime)
    runtime.admit(plan, HOST)
    _write_branches(tmp_path / "branches", declared.memory_mb // 192 + 1)
    with pytest.raises(runtime.OperatorError) as refused:
        runtime.admit(plan, HOST)
    assert refused.value.code == runtime.EXIT_ADMISSION
    assert "(branch) 192" in capsys.readouterr().out


class _Docker:
    """A recording `docker`: inspect answers "exists" for the branch's own names."""

    def __init__(self, existing: set[str]) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.existing = existing

    def __call__(self, *arguments: str, timeout: float = 60) -> subprocess.CompletedProcess:
        self.calls.append(arguments)
        found = arguments[-1] in self.existing
        code = (
            0
            if (
                arguments[0] not in ("inspect", "volume")
                or found
                or arguments[:2] == ("volume", "rm")
            )
            else 1
        )
        if arguments[:2] == ("volume", "inspect"):
            code = 0 if found else 1
        return subprocess.CompletedProcess(arguments, code, "", "")


def test_delete_touches_only_derived_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`delete` names exactly what `branch_names` derives -- five containers, two
    networks, one volume -- and removes the branch's state directory; never the
    parent's volume or any other name. Deleting what does not exist is exit 0.

    Goes red if: delete removes a name it did not derive (the parent's volume
    above all), or leaves the state directory behind."""
    runtime = _runtime()
    names = naming.branch_names(KEY, "dev")
    monkeypatch.setattr(runtime, "BRANCH_ROOT", tmp_path / "branches")
    monkeypatch.setattr(runtime, "require_root", lambda: None)
    detached: list[str] = []
    monkeypatch.setattr(runtime, "detach", lambda n: detached.append(n.edge_network))
    _write_branches(tmp_path / "branches", 0)
    path = branch_record.record_path(KEY, "dev", root=tmp_path / "branches")
    branch_record.write(
        path,
        branch_record.Record(
            project_key=KEY, branch="dev", state="ready", operation="x", requested_point=None,
            reached_point=None, timeline=2, parent_commit=None, pool_host="p", direct_host="d",
            expires_at=None, expires_for=None, unreclaimable_mb=192,
            created_at="2026-10-14T08:00:00Z", updated_at="2026-10-14T08:00:00Z",
        ),
    )  # fmt: skip
    recorder = _Docker({names.volume, names.postgres_container})
    monkeypatch.setattr(runtime, "docker", recorder)
    arguments = argparse.Namespace(parent_key=KEY, branch="dev")
    assert runtime.command_delete(arguments) == 0
    allowed = set(names.all_resources())
    named = {call[-1] for call in recorder.calls}
    assert named <= allowed, sorted(named - allowed)
    assert naming.postgres_volume_name(KEY) not in {
        part for call in recorder.calls for part in call
    }
    removed = {
        call[-1]
        for call in recorder.calls
        if call[0] in ("rm", "network") or call[:2] == ("volume", "rm")
    }
    assert removed == allowed, sorted(allowed - removed)
    assert detached == [names.edge_network]
    assert not path.parent.exists() and not path.parent.parent.exists()

    recorder.existing.clear()
    recorder.calls.clear()
    assert runtime.command_delete(arguments) == 0
    assert all(call[0] in ("inspect", "volume") for call in recorder.calls), recorder.calls


def test_start_all_records_a_branch_that_did_not_come_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D2439: the reconciler's start brings every recorded branch back; one that
    does not come back is recorded `stopped` and the verb exits 6 -- never a
    loop, never `ready`."""
    runtime = _runtime()
    monkeypatch.setattr(runtime, "BRANCH_ROOT", tmp_path / "branches")
    monkeypatch.setattr(runtime, "require_root", lambda: None)
    _write_branches(tmp_path / "branches", 2)
    attached: list[str] = []
    monkeypatch.setattr(runtime, "attach", lambda names: attached.append(names.branch))
    # The image's resolution is test_branch_start.py's; here every start finds it.
    monkeypatch.setattr(runtime, "pin_image", lambda directory, current: "sha256:" + "6" * 64)
    monkeypatch.setattr(runtime, "await_door", lambda hosts: ("ready", None))

    def docker(*arguments: str, timeout: float = 60) -> subprocess.CompletedProcess:
        failing = "apg-slot3-prod_br1" in arguments
        return subprocess.CompletedProcess(
            arguments, 1 if failing else 0, "", "boom" if failing else ""
        )

    monkeypatch.setattr(runtime, "docker", docker)
    assert runtime.command_start(argparse.Namespace(all=True)) == runtime.EXIT_UNKNOWN
    states = {
        name: branch_record.read(
            branch_record.record_path(KEY, name, root=tmp_path / "branches")
        ).state
        for name in ("br0", "br1")
    }
    assert states == {"br0": "ready", "br1": "stopped"}, states
    assert attached == ["br0"]


# ---------------------------------------------------------------------------
# The compose file
# ---------------------------------------------------------------------------


def _compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _substitute(value: Any, environment: dict[str, str]) -> Any:
    if isinstance(value, str):
        return re.sub(
            r"\$\{([A-Z0-9_]+)(?::\?required)?\}", lambda m: environment[m.group(1)], value
        )
    if isinstance(value, list):
        return [_substitute(item, environment) for item in value]
    if isinstance(value, dict):
        return {key: _substitute(item, environment) for key, item in value.items()}
    return value


def test_the_compose_file_cannot_reach_the_repository() -> None:
    """D2426 on the file the runtime runs: three services, no `ports:` anywhere,
    no backup network, the database on its own `internal` network with one
    mount -- the branch volume, external -- and the command `branch_plan`
    asserts, setting for setting, once the env file is substituted. Every
    service is bounded (mem, pids, cpus); the edge network carries the label
    `edge-network.sh` reconciles by (D2464).

    Goes red if: a port is published, the database gains a mount or a network,
    or its command stops being `persistent_command()`."""
    model = _compose()
    text = COMPOSE.read_text(encoding="utf-8")
    assert set(model["services"]) == {"postgres", "customer-pool", "customer-direct"}
    assert not re.search(r"^\s*ports\s*:", text, re.MULTILINE)
    assert all("ports" not in service for service in model["services"].values())
    assert "backup" not in model["networks"]
    postgres = model["services"]["postgres"]
    assert postgres["networks"] == ["internal"]
    assert postgres["volumes"] == ["postgres-data:/var/lib/postgresql"]
    assert model["volumes"]["postgres-data"]["external"] is True
    assert model["networks"]["internal"]["internal"] is True
    assert model["networks"]["edge"]["labels"] == {"apg.branch.edge": "true"}
    for name, service in model["services"].items():
        for bound in ("mem_limit", "pids_limit", "cpus"):
            assert bound in service, (name, bound)
    plan = _plan(_runtime())
    environment = branch_plan.compose_environment(plan, pgbouncer_image="sha256:" + "7" * 64,
                                                  acme_resolver_name="le")  # fmt: skip
    assert tuple(_substitute(postgres["command"], environment)) == branch_plan.persistent_command()
    interpolated = set(re.findall(r"\$\{([A-Z0-9_]+)", text))
    override = yaml.safe_dump(branch_plan.compose_override(plan, userlist_directory="/x"))
    interpolated |= set(re.findall(r"\$\{([A-Z0-9_]+)", override))
    assert interpolated <= set(environment), sorted(interpolated - set(environment))
    assert environment["BRANCH_POSTGRES_MEMORY_LIMIT"] == "512m"
    assert (
        environment["CUSTOMER_POOL_CONNECTIONS"]
        == environment["CUSTOMER_DIRECT_CONNECTIONS"]
        == "2"
    )


def test_the_doors_are_the_projects_doors() -> None:
    """Each branch pooler equals the project's (`compose.yaml`) except what makes
    it the branch's: its labels, its image (the parent's running one), its
    cluster host and claimant, and no profile or platform. The override's labels
    are the project's own builder with the branch's router names (D2462)."""
    project = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))["services"]
    branch = _compose()["services"]
    for service in ("customer-pool", "customer-direct"):
        mine, theirs = dict(branch[service]), dict(project[service])
        for member in ("labels", "image", "profiles", "platform"):
            mine.pop(member, None)
            theirs.pop(member, None)
        mine_env, theirs_env = mine.pop("environment"), theirs.pop("environment")
        assert mine == theirs, service
        for key in ("APG_CLUSTER_HOST", "APG_POOL_CONNECTIONS", "APG_DATABASE_NAME"):
            mine_env.pop(key)
            theirs_env.pop(key)
        assert mine_env == theirs_env, service
        assert branch[service]["labels"]["apg.traefik.scope"] == "managed"
    override = branch_plan.compose_override(
        _plan(_runtime()), userlist_directory="/state/customer-poolers"
    )
    pool = override["services"]["customer-pool"]
    assert "traefik.tcp.routers.apg-slot3-prod_dev-customer-pool.rule" in pool["labels"]
    assert pool["volumes"] == ["/state/customer-poolers:/run/apg/customer:ro"]


def test_the_verifiers_never_reach_an_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    """`--verifiers-stdin` reads JSON from stdin; anything else is exit 2 and
    nothing of it is echoed. No verb takes a verifier as an argument."""
    runtime = _runtime()
    import io
    import sys

    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(VERIFIERS)))
    assert runtime.read_verifiers() == VERIFIERS
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"customer_app": "x"}'))
    with pytest.raises(runtime.OperatorError) as refused:
        runtime.read_verifiers()
    assert refused.value.code == runtime.EXIT_INPUT and '"x"' not in str(refused.value)
    flags = {
        action.option_strings[0]
        for sub in runtime.build_parser()._subparsers._group_actions[0].choices.values()
        for action in sub._actions
        if action.option_strings
    }
    assert not {flag for flag in flags if "verifier" in flag and flag != "--verifiers-stdin"}
    assert not {flag for flag in flags if "password" in flag}
