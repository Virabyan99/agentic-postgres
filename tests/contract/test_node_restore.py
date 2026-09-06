"""`REC-NODE-001`, offline (ADR 0189, ADR 0192, Session 18 Run 3).

The plan `bin/restore.sh` builds from the kit's two documents, this host's
contract and generation, and what it refuses before anything starts; the
argument vectors measured on the project's image (D1009, D1011, D1012); the
verdict; and the command driven against a recorded `docker` so that the
order -- refuse, build, create, restore, promote, observe, stop -- is a value
a test can hold. Nothing here starts a container or needs root.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, naming, node_restore, runtime_override
from agentic_postgres.secrets_contract import load_secret_contract

pytestmark = [pytest.mark.contract, pytest.mark.p0]

KEY = "fixture-alpha-dev"
MIRROR = {
    "enabled": True,
    "endpoint": "s3.eu-central-003.backblazeb2.com",
    "region": "eu-central-003",
    "bucket": f"apg-{KEY}-backup-mirror",
}
GENERATION = "k7f2p9qd"
#: The session the mirror pair is declared at (Run 5 bumps CURRENT_SESSION).
SESSION = 18
INSTANCE_UUID = "01927d3f-1a2b-7c4d-8e5f-6a7b8c9d0e1f"


def load_command(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"apg_{name}", REPO_ROOT / "bin" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return load_secret_contract(REPO_ROOT / "secrets.required.yaml")


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return yaml.safe_load((REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    """The kit's deployed document: the rendered fixture with the identity a
    deploy observed and a mirror the trip's manifest will declare."""
    path = REPO_ROOT / ".generated" / KEY / "outputs.json"
    if not path.exists():
        pytest.skip("fixtures are not rendered in this working tree")
    rendered = json.loads(path.read_text(encoding="utf-8"))
    rendered["backup"]["mirror"] = dict(MIRROR)
    rendered.setdefault("database", {})["observed"] = {"instance_uuid": INSTANCE_UUID}
    rendered["source_commit"] = "c" * 40
    return rendered


def plan_for(
    document: dict[str, Any], manifest: dict[str, Any], contract: dict[str, Any], **overrides: Any
) -> node_restore.RestorePlan:
    arguments: dict[str, Any] = {
        "document": document,
        "manifest": manifest,
        "contract": contract,
        "session": SESSION,
        "generation_id": GENERATION,
        "configuration_host_path": Path("/nonexistent/apg-restore-x/restore.conf"),
        "source": "mirror",
        "image": "apg-fixture-alpha-dev-postgres",
        "restore_id": "202609052000abcd",
    }
    arguments.update(overrides)
    return node_restore.build_plan(**arguments)


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------


def test_the_plan_restores_into_the_projects_own_volume_and_names_no_other(
    document: dict[str, Any], manifest: dict[str, Any], contract: dict[str, Any]
) -> None:
    plan = plan_for(document, manifest, contract)
    assert plan.volume == naming.postgres_volume_name(KEY) == f"apg-{KEY}-postgres"
    assert plan.data_mount.source == plan.volume
    assert plan.data_mount.target == runtime_override.POSTGRES_VOLUME_TARGET
    volumes = [m.source for m in plan.mounts() if m.kind == "volume"]
    assert volumes == [plan.volume]
    assert all(m.readonly for m in plan.inherited)
    node_restore.assert_own_volume(plan, node_restore.restore_arguments(plan, None))
    assert plan.expected_instance_uuid == INSTANCE_UUID
    assert plan.release == "c" * 40
    assert plan.restore_container != plan.instance_container


def test_a_mirror_restore_mounts_the_mirror_pair_and_never_the_primarys_key(
    document: dict[str, Any], manifest: dict[str, Any], contract: dict[str, Any]
) -> None:
    """The primary account's credential is absent from the argument vector, not
    merely overridden (D1009 makes either sufficient; absence is the stronger)."""
    plan = plan_for(document, manifest, contract, source="mirror")
    targets = sorted(m.target for m in plan.inherited)
    assert targets == [
        "/etc/pgbackrest/conf.d/30-repo1-cipher-pass.conf",
        node_restore.CONFIG_CONTAINER_PATH,
        "/run/secrets/mirror-s3-access-key-id",
        "/run/secrets/mirror-s3-secret-access-key",
    ]
    sources = [m.source for m in plan.inherited]
    assert all(f"/{KEY}/generations/{GENERATION}/postgres/" in s for s in sources[1:]), sources
    assert not any("repo1-s3-key" in s for s in sources), "the primary's key is mounted"
    assert f"repo1-s3-endpoint={MIRROR['endpoint']}" in plan.configuration
    assert f"repo1-s3-bucket={MIRROR['bucket']}" in plan.configuration
    assert f"repo1-s3-region={MIRROR['region']}" in plan.configuration
    assert "repo1-s3-key" not in plan.configuration and "cipher-pass=" not in plan.configuration
    assert f"[{plan.stanza}]" in plan.configuration


def test_a_primary_restore_mounts_the_archivers_three_includes(
    document: dict[str, Any], manifest: dict[str, Any], contract: dict[str, Any]
) -> None:
    plan = plan_for(document, manifest, contract, source="primary")
    targets = sorted(m.target for m in plan.inherited)
    assert targets == [
        "/etc/pgbackrest/conf.d/10-repo1-s3-key.conf",
        "/etc/pgbackrest/conf.d/20-repo1-s3-key-secret.conf",
        "/etc/pgbackrest/conf.d/30-repo1-cipher-pass.conf",
        node_restore.CONFIG_CONTAINER_PATH,
    ]
    assert "repo1-s3-region=auto" in plan.configuration
    assert f"repo1-s3-bucket={document['backup']['bucket']}" in plan.configuration
    assert ".r2.cloudflarestorage.com" in plan.configuration


def test_the_refusals_come_before_anything_starts(
    document: dict[str, Any], manifest: dict[str, Any], contract: dict[str, Any]
) -> None:
    other_key = copy.deepcopy(manifest)
    other_key["project"]["slug"] = "someone-else"
    with pytest.raises(node_restore.RestoreRefusal, match="another's document"):
        plan_for(document, other_key, contract)
    other_stanza = copy.deepcopy(manifest)
    other_stanza["backup"]["stanza"] = "not-this-one"
    with pytest.raises(node_restore.RestoreRefusal, match="stanza"):
        plan_for(document, other_stanza, contract)
    unmirrored = copy.deepcopy(document)
    unmirrored["backup"]["mirror"] = {
        "enabled": False,
        "endpoint": None,
        "bucket": None,
        "region": None,
    }
    with pytest.raises(node_restore.RestoreRefusal, match="no mirror"):
        plan_for(unmirrored, manifest, contract, source="mirror")
    plan_for(unmirrored, manifest, contract, source="primary")  # the primary still restores
    disabled = copy.deepcopy(document)
    disabled["backup"]["enabled"] = False
    with pytest.raises(node_restore.RestoreError, match="nothing to restore"):
        plan_for(disabled, manifest, contract)
    with pytest.raises(node_restore.RestoreError, match="--from"):
        plan_for(document, manifest, contract, source="secondary")


def test_assert_own_volume_refuses_a_foreign_volume_a_writable_mount_and_delta(
    document: dict[str, Any], manifest: dict[str, Any], contract: dict[str, Any]
) -> None:
    from agentic_postgres.restore_drill import Mount

    plan = plan_for(document, manifest, contract)
    argv = node_restore.restore_arguments(plan, None)
    node_restore.assert_own_volume(plan, argv)  # the subject arm

    foreign = node_restore.RestorePlan(
        **{**plan.__dict__, "volume": "apg-someone-else-dev-postgres"}
    )
    with pytest.raises(node_restore.RestoreRefusal, match="not this project"):
        node_restore.assert_own_volume(
            node_restore.RestorePlan(
                **{
                    **plan.__dict__,
                    "inherited": (
                        *plan.inherited,
                        Mount(source=foreign.volume, target="/other", readonly=True, kind="volume"),
                    ),
                }
            ),
            argv,
        )
    writable = node_restore.RestorePlan(
        **{
            **plan.__dict__,
            "inherited": tuple(
                Mount(source=m.source, target=m.target, readonly=False, kind=m.kind)
                for m in plan.inherited
            ),
        }
    )
    with pytest.raises(node_restore.RestoreRefusal, match="writable"):
        node_restore.assert_own_volume(writable, argv)
    with pytest.raises(node_restore.RestoreRefusal, match="--delta"):
        node_restore.assert_own_volume(plan, (*argv, "--delta"))


def test_the_argument_vectors_are_the_measured_ones(
    document: dict[str, Any], manifest: dict[str, Any], contract: dict[str, Any]
) -> None:
    """D1011: a plain restore for --latest; --target-action only with --type.
    D1010: the configuration and include path on the command line, which is
    what pgBackRest writes into restore_command for the recovering instance."""
    plan = plan_for(document, manifest, contract)
    latest = node_restore.restore_arguments(plan, None)
    assert latest == (
        f"--config={node_restore.CONFIG_CONTAINER_PATH}",
        f"--config-include-path={node_restore.INCLUDE_CONTAINER_DIR}",
        f"--stanza={plan.stanza}",
        "--log-level-console=info",
        "restore",
    )
    assert not any(a.startswith("--target") or a.startswith("--type") for a in latest)
    timed = node_restore.restore_arguments(plan, "2026-09-05 12:00:00+00")
    assert timed[-3:] == (
        "--type=time",
        "--target=2026-09-05 12:00:00+00",
        "--target-action=promote",
    )
    assert "--delta" not in latest and "--delta" not in timed
    assert node_restore.instance_arguments() == ("postgres", "-c", "archive_mode=off")


def test_the_wrapper_exports_exactly_the_mirror_pair_from_the_mounted_files() -> None:
    """The values enter pgBackRest's environment inside the container (D1009)
    and nowhere else; the script names the two files and the two variables
    and execs what it was given."""
    script = node_restore.wrapper_script()
    assert script.startswith("set -eu;") and script.endswith('exec "$@"')
    for file, variable in zip(
        node_restore.MIRROR_KEY_FILES,
        ("PGBACKREST_REPO1_S3_KEY", "PGBACKREST_REPO1_S3_KEY_SECRET"),
        strict=True,
    ):
        assert f'{variable}="$(cat /run/secrets/{file})"' in script
    assert script.count("PGBACKREST_") == 4, "a variable beyond the pair is exported"
    assert "echo" not in script and "cipher" not in script


def test_pg_version_is_looked_for_where_pgdata_sits_inside_the_volume() -> None:
    """D1012: the probe reads `<PGDATA relative to the mount>/PG_VERSION`,
    derived from the runtime override's two constants."""
    assert node_restore.pg_version_relative_path() == "18/docker/PG_VERSION"
    assert runtime_override.POSTGRES_PGDATA.startswith(runtime_override.POSTGRES_VOLUME_TARGET)


def test_the_verdict_needs_recovery_a_new_timeline_the_identity_and_a_ledger() -> None:
    good = {
        "achieved_lsn": "0/5000028",
        "timeline_id": 2,
        "instance_uuid": INSTANCE_UUID,
        "schema_migration_count": 30,
    }
    assert node_restore.restore_verdict(observed=good, expected_instance_uuid=INSTANCE_UUID) == {
        "passed": True,
        "reasons": [],
    }
    for change, phrase in (
        ({"achieved_lsn": None}, "did not recover"),
        ({"timeline_id": 1}, "timeline 1"),
        ({"instance_uuid": "00000000-0000-4000-8000-000000000000"}, "not the kit's"),
        ({"schema_migration_count": 0}, "no migration ledger"),
    ):
        verdict = node_restore.restore_verdict(
            observed={**good, **change}, expected_instance_uuid=INSTANCE_UUID
        )
        assert not verdict["passed"] and any(phrase in r for r in verdict["reasons"]), change
    # A kit that recorded no identity cannot be checked against one; the other
    # three conditions still hold.
    assert node_restore.restore_verdict(observed=good, expected_instance_uuid=None)["passed"]
    # No achieved timestamp is NOT a failure here: a restore to the latest point
    # right after a full backup can replay no committed transaction.
    assert node_restore.restore_verdict(
        observed={**good, "achieved_recovery_point": None}, expected_instance_uuid=INSTANCE_UUID
    )["passed"]


def test_the_evidence_document_is_the_drills_shape_with_source_and_identity(
    document: dict[str, Any], manifest: dict[str, Any], contract: dict[str, Any]
) -> None:
    plan = plan_for(document, manifest, contract)
    evidence = node_restore.evidence_document(
        plan=plan,
        restore_id="202609052000abcd",
        requested_target=None,
        observed={
            "achieved_recovery_point": "2026-09-05 12:00:00+00",
            "achieved_lsn": "0/5000028",
            "timeline_id": 2,
            "instance_uuid": INSTANCE_UUID,
            "schema_migration_count": 30,
            "schema_version": "20260904000000",
        },
        repository={"latest_recoverable_time": "2026-09-05T11:00:00Z"},
        backup_set={"label": "20260905-030000F", "type": "full"},
        timings={"restore_seconds": 151.2, "recovery_seconds": 9.1, "rto_seconds": 161.0},
    )
    assert evidence["kind"] == "node_restore" and evidence["source"] == "mirror"
    assert evidence["identity"] == {
        "expected_instance_uuid": INSTANCE_UUID,
        "observed_instance_uuid": INSTANCE_UUID,
    }
    assert evidence["restore"]["volume"] == plan.volume
    assert evidence["recovery"]["achieved_is_at_or_after_floor"] is True
    assert evidence["verdict"]["passed"] is True
    text = json.dumps(evidence)
    assert "cipher" not in text and "secret" not in text.lower().replace("secrets/", "")


# ---------------------------------------------------------------------------
# The command, against a recorded docker
# ---------------------------------------------------------------------------


class Docker:
    """Records every `docker` argv and answers from a small state: whether the
    volume exists, whether it holds PG_VERSION, who mounts it, and what the
    restore and the queries say."""

    def __init__(self, *, exists: bool = False, holds_cluster: bool = False, mounted_by: str = ""):
        self.exists = exists
        self.holds_cluster = holds_cluster
        self.mounted_by = mounted_by
        self.calls: list[list[str]] = []
        self.restore_exit = 0
        self.recovery = ["t", "f"]

    def __call__(self, *arguments: str, timeout: int = 0) -> subprocess.CompletedProcess:
        argv = list(arguments)
        self.calls.append(argv)
        ok = lambda out="": subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")  # noqa: E731
        if argv[:2] == ["ps", "-a"]:
            return ok(self.mounted_by + "\n")
        if argv[:2] == ["volume", "inspect"]:
            return (
                ok() if self.exists else subprocess.CompletedProcess(argv, 1, "", "no such volume")
            )
        if argv[:2] == ["volume", "create"]:
            self.exists = True
            return ok()
        if argv[:2] == ["network", "inspect"]:
            return subprocess.CompletedProcess(argv, 1, "", "no such network")
        if argv[0] == "run" and "chown" in argv:
            return ok()
        if argv[0] == "run" and "test -e /probe/18/docker/PG_VERSION" in argv:
            return subprocess.CompletedProcess(argv, 0 if self.holds_cluster else 1, "", "")
        if argv[0] == "run" and "info" in argv and "--output=json" in argv:
            return ok(
                json.dumps(
                    [
                        {
                            "name": KEY,
                            "status": {"code": 0, "message": "ok"},
                            "backup": [
                                {
                                    "label": "20260905-030000F",
                                    "type": "full",
                                    "timestamp": {"start": 1757041200, "stop": 1757041260},
                                }
                            ],
                            "archive": [{"max": "000000010000000000000005"}],
                        }
                    ]
                )
            )
        if argv[0] == "run" and "restore" in argv:
            self.holds_cluster = self.restore_exit == 0
            return subprocess.CompletedProcess(
                argv,
                self.restore_exit,
                "P00   INFO: repo1: restore backup set 20260905-030000F\n"
                "P00   INFO: restore command end: completed successfully (151000ms)\n",
                "",
            )
        if argv[0] == "run" and "-d" in argv:
            return ok("container-id\n")
        if argv[:1] == ["inspect"] and "-f" in argv:
            return ok("true\n")
        if argv[:1] == ["inspect"]:
            return ok("[]")
        if argv[:2] == ["exec", "-i"]:
            sql = argv[-1]
            answers = {
                "SELECT pg_is_in_recovery()": self.recovery.pop(0)
                if len(self.recovery) > 1
                else "f",
                "SELECT pg_last_xact_replay_timestamp()": "2026-09-05 03:01:00+00",
                "SELECT pg_last_wal_replay_lsn()": "0/5000028",
                "SELECT timeline_id FROM pg_control_checkpoint()": "2",
                "SELECT instance_uuid FROM app_private.project_identity": INSTANCE_UUID,
                "SELECT count(*) FROM app_private.schema_migrations": "30",
            }
            for prefix, answer in answers.items():
                if sql.startswith(prefix):
                    return ok(answer + "\n")
            return ok("20260904000000\n")
        if argv[0] in {"stop", "rm", "logs"}:
            return ok()
        raise AssertionError(f"unexpected docker {argv}")


@pytest.fixture
def restore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, document: dict[str, Any]) -> Any:
    module = load_command("restore")
    monkeypatch.setattr(module, "require_root", lambda: None)
    monkeypatch.setattr(module, "build_image", lambda rendered: "apg-fixture-alpha-dev-postgres")
    monkeypatch.setattr(
        module,
        "time",
        type(
            "T", (), {"monotonic": staticmethod(lambda: 0.0), "sleep": staticmethod(lambda s: None)}
        ),
    )
    (tmp_path / "rendered").mkdir()
    (tmp_path / "rendered" / "compose.env").write_text("x=1\n")
    secret_root = tmp_path / "secrets"
    (secret_root / KEY).mkdir(parents=True)
    (secret_root / KEY / "active-secret-generation.json").write_text(
        json.dumps({"generation_id": GENERATION}), encoding="utf-8"
    )
    outputs = tmp_path / "outputs.json"
    outputs.write_text(json.dumps(document), encoding="utf-8")
    module.ARGV = [
        "--outputs",
        str(outputs),
        "--project",
        str(REPO_ROOT / "project.example.yaml"),
        "--rendered-dir",
        str(tmp_path / "rendered"),
        "--secret-root",
        str(secret_root),
        "--evidence-dir",
        str(tmp_path / "evidence"),
        "--session",
        "18",
    ]
    module.TMP = tmp_path
    return module


def test_the_command_refuses_a_volume_that_holds_a_cluster_before_the_restore(
    restore: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    docker = Docker(exists=True, holds_cluster=True)
    monkeypatch.setattr(restore, "docker", docker)
    assert restore.main([*restore.ARGV, "--from", "mirror", "--latest"]) == 7
    assert "already holds a cluster" in capsys.readouterr().err
    assert not any("restore" in c for c in docker.calls if c[0] == "run" and "info" not in c)
    assert not any(c[:2] == ["volume", "create"] for c in docker.calls)


def test_the_command_refuses_a_volume_a_container_mounts(
    restore: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    docker = Docker(exists=True, mounted_by=f"apg-{KEY}-postgres-1")
    monkeypatch.setattr(restore, "docker", docker)
    assert restore.main([*restore.ARGV, "--from", "mirror", "--latest"]) == 7
    assert "mounted by" in capsys.readouterr().err
    assert [c[0] for c in docker.calls] == ["ps"], "something ran after the refusal"


def test_a_mirror_restore_runs_in_order_and_leaves_the_volume_holding_the_cluster(
    restore: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    docker = Docker()
    monkeypatch.setattr(restore, "docker", docker)
    assert restore.main([*restore.ARGV, "--from", "mirror", "--latest"]) == 0, capsys.readouterr()
    kinds = [
        c[0]
        if c[0] != "run"
        else (
            "run:"
            + (
                "restore"
                if "restore" in c
                else "info"
                if "info" in c
                else "probe"
                if "test -e" in " ".join(c)
                else "chown"
                if "chown" in c
                else "instance"
            )
        )
        for c in docker.calls
    ]
    assert (
        kinds.index("volume")
        < kinds.index("run:info")
        < kinds.index("run:restore")
        < kinds.index("run:instance")
    )
    assert "run:probe" not in kinds, "an absent volume was probed for a cluster"
    restore_call = next(c for c in docker.calls if c[0] == "run" and "restore" in c)
    # The wrapper carries the pair into the container's environment; the
    # host-side argv holds paths and the script, never a value or an `--env`.
    assert "--entrypoint" in restore_call and "sh" in restore_call
    assert "--env" not in restore_call and "-e" not in restore_call
    assert node_restore.wrapper_script() in restore_call
    mounts = [a for a in restore_call if a.startswith("type=")]
    assert f"type=volume,source=apg-{KEY}-postgres,target=/var/lib/postgresql" in mounts
    assert all("readonly" in m for m in mounts if m.startswith("type=bind")), mounts
    assert not any("volume" in m and f"apg-{KEY}-postgres" not in m for m in mounts)
    assert "--delta" not in restore_call
    # The instance ran with archiving off, was queried, and was stopped; the
    # volume was never removed.
    instance = next(c for c in docker.calls if c[0] == "run" and "-d" in c)
    assert instance[-3:] == ["postgres", "-c", "archive_mode=off"]
    assert any(c[0] == "stop" for c in docker.calls)
    assert not any(c[:2] == ["volume", "rm"] for c in docker.calls)
    evidence = list((restore.TMP / "evidence").glob(f"restore-{KEY}-*.json"))
    assert len(evidence) == 1
    record = json.loads(evidence[0].read_text(encoding="utf-8"))
    assert record["kind"] == "node_restore" and record["verdict"]["passed"] is True
    assert record["identity"]["observed_instance_uuid"] == INSTANCE_UUID
    assert record["backup_set"] == {"label": "20260905-030000F", "type": "full"}
    assert record["timing"]["pgbackrest_reported_ms"] == 151000
    assert oct(evidence[0].stat().st_mode & 0o777) == "0o600"
    assert "verified" in capsys.readouterr().out


def test_a_primary_restore_runs_pgbackrest_straight_with_its_includes(
    restore: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    docker = Docker()
    monkeypatch.setattr(restore, "docker", docker)
    assert restore.main([*restore.ARGV, "--from", "primary", "--latest"]) == 0
    restore_call = next(c for c in docker.calls if c[0] == "run" and "restore" in c)
    assert restore_call[restore_call.index("--entrypoint") + 1] == "pgbackrest"
    assert node_restore.wrapper_script() not in restore_call
    assert any("10-repo1-s3-key.conf" in a for a in restore_call)


def test_a_refused_restore_writes_no_evidence_and_stops_its_containers(
    restore: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    docker = Docker()
    docker.restore_exit = 40
    monkeypatch.setattr(restore, "docker", docker)
    assert restore.main([*restore.ARGV, "--from", "mirror", "--latest"]) == 7
    assert "populated" in capsys.readouterr().err
    assert (
        not list((restore.TMP / "evidence").glob("*.json"))
        if (restore.TMP / "evidence").exists()
        else True
    )
    assert not any(c[0] == "run" and "-d" in c for c in docker.calls), "the instance was started"


def test_plan_prints_reads_the_volume_and_starts_nothing(
    restore: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR 0194: the plan reads what the run would refuse and writes nothing --
    a `docker ps` and a volume inspect against an absent volume, no create, no
    build, no restore, no instance."""
    docker = Docker(exists=False)
    monkeypatch.setattr(restore, "docker", docker)
    assert restore.main([*restore.ARGV, "--from", "mirror", "--latest", "--plan"]) == 0
    assert [c[:2] for c in docker.calls] == [["ps", "-a"], ["volume", "inspect"]]
    out = capsys.readouterr().out
    assert f"apg-{KEY}-postgres" in out and "--plan; nothing was started" in out


@pytest.mark.parametrize(
    ("docker", "reason"),
    [
        (Docker(exists=True, holds_cluster=True), "holds a cluster"),
        (
            Docker(exists=True, holds_cluster=False, mounted_by=f"apg-{KEY}-postgres-1"),
            "is mounted by",
        ),
    ],
)
def test_plan_refuses_what_the_run_refuses_with_exit_7(
    restore: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    docker: Docker,
    reason: str,
) -> None:
    """D1031: the first host gate ran `--plan` against the production cluster's
    volume and it exited 0. Both refusals now come before the plan returns,
    read through a probe and a `docker ps`, and nothing is created or built."""
    monkeypatch.setattr(restore, "docker", docker)
    assert restore.main([*restore.ARGV, "--from", "mirror", "--latest", "--plan"]) == 7
    assert reason in capsys.readouterr().err
    assert not any(c[:2] == ["volume", "create"] for c in docker.calls)
    assert not any(c[0] == "run" and "restore" in c for c in docker.calls)
    assert not any(c[0] == "run" and "-d" in c for c in docker.calls)


def test_the_command_needs_a_materialized_generation_first(
    restore: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (restore.TMP / "secrets" / KEY / "active-secret-generation.json").unlink()
    monkeypatch.setattr(restore, "docker", Docker())
    assert restore.main([*restore.ARGV, "--from", "mirror", "--latest"]) == 3
    assert "materialize-secrets.sh first" in capsys.readouterr().err


def test_the_wrapper_never_removes_a_volume_and_the_runbook_orders_it_before_the_deploy() -> None:
    source = (REPO_ROOT / "bin" / "restore.sh").read_text(encoding="utf-8")
    assert "volume rm" not in source and "volume prune" not in source
    assert "instance_container | restore_container" in source
    assert "never the volume" in source.lower() or "NEVER the volume" in source


# The listing Compose 5.5.1 printed on the replacement host with `--profile "*"`
# (2026-09-06, D1027): every profile's images, the built ones untagged, the
# pulled ones by digest. Without a profile it printed nothing at all.
MEASURED_LISTING = """apg-alpha-dev-client-prisma
docker.io/otel/opentelemetry-collector-contrib:0.159.0@sha256:1f2c54a30e713fac6b3ae77a1ec84010c2007e29ced8ec666214fc2f6739c1cc
apg-alpha-dev-auth
apg-alpha-dev-postgres
apg-alpha-dev-docs
docker.io/postgrest/postgrest:v14.16@sha256:bea1c76a856fa39d1e542d25911cf95d02fe2bf971992d033044ff209f1504b8
apg-alpha-dev-backup-mirror
apg-alpha-dev-edge-probe
"""


@pytest.mark.parametrize(
    ("listing", "expected"),
    [
        (MEASURED_LISTING, "apg-alpha-dev-postgres"),
        (
            MEASURED_LISTING.replace("apg-alpha-dev-postgres\n", "apg-alpha-dev-postgres:latest\n"),
            "apg-alpha-dev-postgres",
        ),
        ("", None),
        ("name: apg-alpha-dev\nservices: {}\n", None),
    ],
)
def test_the_image_is_named_from_every_profile_and_a_silent_listing_is_refused(
    listing: str, expected: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D1027. The first live restore built the image and then could not name
    it: the model's services all sit behind profiles, and a `config --images`
    with none selected prints nothing. The listing now selects every profile
    and the name is read with or without a tag; an empty listing is the
    refusal that stopped the trip, kept as a refusal."""
    module = load_command("restore")
    calls: list[list[str]] = []

    def run(argv: list[str], **_: Any) -> subprocess.CompletedProcess:
        calls.append(argv)
        if "build" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout=listing, stderr="")

    monkeypatch.setattr(module.subprocess, "run", run)
    if expected is None:
        with pytest.raises(module.OperatorError, match="could not name the postgres image"):
            module.build_image(Path("/nonexistent/rendered"))
    else:
        assert module.build_image(Path("/nonexistent/rendered")) == expected
    assert calls[0][-3:] == ["--runtime", "build", "postgres"]
    assert calls[1][-5:] == ["--runtime", "--profile", "*", "config", "--images"]
