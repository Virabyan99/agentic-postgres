#!/usr/bin/env python3
"""Restore a project's stanza into its OWN volume on a replacement host (ADR 0189, 0192).

Invoked only by `bin/restore.sh`, which has already checked root and set the
trap that removes what this command's state file names. Kept as its own
program for `doctor.py`'s reason.

**On the production host this is never run** (plan §4): the project's volume
holds a cluster there, and the first refusal below is exactly that. On a
replacement host the order is adopt, materialize, THIS, deploy (D1008):

  1. Reads the kit's deployed document and the manifest deployed here, the
     contract, and this host's active secret generation; builds the plan
     (`node_restore.build_plan`) and refuses a manifest naming another key or
     stanza, or a mirror the document does not have.
  2. Refuses, before anything starts, a volume that a container mounts or
     that holds `PG_VERSION` (D1012); asserts every mount names this project's
     volume and no other (`REC-NODE-001`).
  3. Builds the project's postgres image through `bin/compose.sh` from the
     rendered directory, creates the volume owned by the postmaster's uid,
     and reads the repository's own report.
  4. Restores through the same image; for `--from mirror` the mirror's key
     pair reaches pgBackRest through the container's own environment
     (D1009), the primary's includes never mounted.
  5. Starts the restored cluster with archiving OFF, waits for it to promote,
     reads its identity, stops it, and writes `evidence/restore-<key>-<id>.json`.
     The volume is left holding the promoted cluster for `deploy.sh` to start.

Exit codes (runbook section 2 convention):
  0  the restore ran and verified
  2  invalid operator input
  3  missing local prerequisite, or not root
  5  the deployment or the repository refused the operation
  6  the restore ran and its answer is "no" -- it did not verify
  7  the plan was refused as unsafe; nothing was started
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import (  # noqa: E402
    CURRENT_SESSION,
    access_broker,
    backup_report,
    config,
    database_observation,
    node_restore,
    restore_drill,
)
from agentic_postgres.secrets_contract import SECRET_ROOT, load_secret_contract  # noqa: E402

EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_STATE = 5
EXIT_REFUSED = 6
EXIT_UNSAFE = 7

POSTGRES_UID = "999"
PROMOTION_TIMEOUT_SECONDS = 900
RESTORE_TIMEOUT_SECONDS = 7200
QUICK_TIMEOUT_SECONDS = 120
BUILD_TIMEOUT_SECONDS = 1800

_REPORTED_MS = re.compile(r"restore command end: completed successfully \((?P<ms>\d+)ms\)")


class OperatorError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def require_root() -> None:
    if os.geteuid() != 0:
        raise OperatorError(
            EXIT_PREREQUISITE,
            "must run as root: the secret generation is root-owned and the restore reaches "
            "Docker over the local socket.",
        )


def docker(*arguments: str, timeout: int = QUICK_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )


def load_json(path: Path, what: str) -> dict[str, Any]:
    if not path.is_file():
        raise OperatorError(EXIT_INPUT, f"{what} not found: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise OperatorError(EXIT_INPUT, f"{path} is not readable as JSON: {error}") from error
    if not isinstance(document, dict):
        raise OperatorError(EXIT_INPUT, f"{path} is not a document")
    return document


def new_restore_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H%M") + secrets.token_hex(2)


# ---------------------------------------------------------------------------
# Refusals that need the daemon
# ---------------------------------------------------------------------------


def containers_mounting(volume: str) -> list[str]:
    result = docker("ps", "-a", "--filter", f"volume={volume}", "--format", "{{.Names}}")
    if result.returncode != 0:
        raise OperatorError(EXIT_STATE, f"docker ps failed: {result.stderr.strip()[:300]}")
    return [line for line in result.stdout.split() if line]


def volume_exists(volume: str) -> bool:
    return docker("volume", "inspect", volume).returncode == 0


def probe_image() -> str:
    """The pinned runtime image from versions.env, for a plan's read of the
    volume: a plan builds nothing (ADR 0194), and this image is the one every
    host already holds for the probes the model runs."""
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "PYTHON_RUNTIME_IMAGE" and value.strip():
            return value.strip()
    raise OperatorError(EXIT_PREREQUISITE, "PYTHON_RUNTIME_IMAGE is absent from versions.env")


def volume_holds_a_cluster(volume: str, image: str) -> bool:
    """`PG_VERSION` under PGDATA inside the volume (D1012): present means a
    cluster, whatever else is there. Read through the project's own image,
    never by a bind on the host, because the volume's host path is Docker's."""
    relative = node_restore.pg_version_relative_path()
    result = docker(
        "run",
        "--rm",
        "--mount",
        f"type=volume,source={volume},target=/probe,readonly",
        "--entrypoint",
        "sh",
        image,
        "-c",
        f"test -e /probe/{relative}",
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise OperatorError(EXIT_STATE, f"could not probe {volume}: {result.stderr.strip()[:300]}")


# ---------------------------------------------------------------------------
# The image, the volume, the repository
# ---------------------------------------------------------------------------


def build_image(rendered: Path) -> str:
    """The project's postgres image, built by the model that deploys it and
    named by it: one build site (ADR 0144), reached through `bin/compose.sh`."""
    compose = str(REPO_ROOT / "bin" / "compose.sh")
    build = subprocess.run(
        [compose, str(rendered), "--runtime", "build", "postgres"],
        capture_output=True,
        text=True,
        check=False,
        timeout=BUILD_TIMEOUT_SECONDS,
        stdin=subprocess.DEVNULL,
    )
    if build.returncode != 0:
        raise OperatorError(
            EXIT_STATE, f"the postgres image did not build: {build.stderr.strip()[-600:]}"
        )
    # Every service in the model sits behind a profile, and Compose lists the
    # images of the selected profiles and no other: without one, `config
    # --images` printed nothing and the first live restore named no image
    # (D1027, measured on Compose 5.5.1 on the replacement, 2026-09-06). `*`
    # selects every profile; the filter below picks the one built postgres,
    # with or without a tag.
    images = subprocess.run(
        [compose, str(rendered), "--runtime", "--profile", "*", "config", "--images"],
        capture_output=True,
        text=True,
        check=False,
        timeout=QUICK_TIMEOUT_SECONDS,
        stdin=subprocess.DEVNULL,
    )
    names = [line.strip().split(":", 1)[0] for line in images.stdout.splitlines() if line.strip()]
    postgres = [name for name in names if name.endswith("-postgres")]
    if images.returncode != 0 or len(postgres) != 1:
        raise OperatorError(
            EXIT_STATE,
            f"could not name the postgres image from the model (found {postgres}); "
            "nothing was started",
        )
    return postgres[0]


def create_volume(volume: str, image: str) -> None:
    result = docker("volume", "create", volume)
    if result.returncode != 0:
        raise OperatorError(EXIT_STATE, f"could not create {volume}: {result.stderr.strip()[:300]}")
    # Owned by the postmaster's uid, as the image's entrypoint would have done
    # on a first start: the restore runs as 999 and writes there.
    chown = docker(
        "run",
        "--rm",
        "--mount",
        f"type=volume,source={volume},target=/v",
        "--entrypoint",
        "chown",
        image,
        f"{POSTGRES_UID}:{POSTGRES_UID}",
        "/v",
    )
    if chown.returncode != 0:
        raise OperatorError(EXIT_STATE, f"could not chown {volume}: {chown.stderr.strip()[:300]}")


def run_arguments(plan: node_restore.RestorePlan, name: str, *, detached: bool) -> list[str]:
    arguments = ["run", "--name", name, "-u", f"{POSTGRES_UID}:{POSTGRES_UID}"]
    arguments += ["-d"] if detached else ["--rm"]
    for mount in plan.mounts():
        arguments += ["--mount", mount.as_mount_argument()]
    if plan.network and docker("network", "inspect", plan.network).returncode == 0:
        arguments += ["--network", plan.network]
    return arguments


def command_for(plan: node_restore.RestorePlan, executable: str, *arguments: str) -> list[str]:
    """The image and what runs in it. A mirror restore runs through the wrapper
    that puts the mirror's pair into the process environment (D1009); a
    primary restore runs the executable straight, its includes mounted."""
    if plan.source == "mirror":
        return [
            "--entrypoint",
            "sh",
            plan.image,
            "-c",
            node_restore.wrapper_script(),
            "sh",
            executable,
            *arguments,
        ]
    if executable == "pgbackrest":
        return ["--entrypoint", "pgbackrest", plan.image, *arguments]
    return [plan.image, executable, *arguments]


def read_repository(plan: node_restore.RestorePlan) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """`pgbackrest info` against the SOURCE, through the restore container's
    own configuration -- the state is in a field, never the exit code (D548)."""
    command = run_arguments(plan, f"{plan.restore_container}-info", detached=False)
    command += command_for(
        plan,
        "pgbackrest",
        f"--config={node_restore.CONFIG_CONTAINER_PATH}",
        f"--config-include-path={node_restore.INCLUDE_CONTAINER_DIR}",
        f"--stanza={plan.stanza}",
        "info",
        "--output=json",
    )
    result = docker(*command, timeout=QUICK_TIMEOUT_SECONDS * 5)
    if not result.stdout.strip():
        raise OperatorError(
            EXIT_STATE,
            f"pgbackrest info produced no output (exit {result.returncode}): "
            f"{result.stderr.strip()[:400]}",
        )
    try:
        document = json.loads(result.stdout)
        summary = backup_report.summarise(document, plan.stanza)
    except ValueError as error:
        raise OperatorError(EXIT_STATE, f"pgbackrest info could not be read: {error}") from error
    if summary.get("status_code") != backup_report.REPOSITORY_OK:
        raise OperatorError(
            EXIT_STATE,
            f"the {plan.source} repository reports {backup_report.status_for(summary)} for "
            f"stanza {plan.stanza}: no backup set to restore. If the objects are there, "
            "the cipher pass is not the one they were written under (D999).",
        )
    entries = [entry for entry in document if entry.get("name") == plan.stanza]
    return summary, list(entries[0].get("backup") or [])


# ---------------------------------------------------------------------------
# The restore and the instance
# ---------------------------------------------------------------------------


def run_restore(
    plan: node_restore.RestorePlan, arguments: tuple[str, ...]
) -> tuple[subprocess.CompletedProcess, float]:
    command = run_arguments(plan, plan.restore_container, detached=False)
    command += command_for(plan, "pgbackrest", *arguments)
    started = time.monotonic()
    result = docker(*command, timeout=RESTORE_TIMEOUT_SECONDS)
    return result, time.monotonic() - started


def start_instance(plan: node_restore.RestorePlan) -> None:
    command = run_arguments(plan, plan.instance_container, detached=True)
    command += command_for(plan, *node_restore.instance_arguments())
    result = docker(*command)
    if result.returncode != 0:
        raise OperatorError(
            EXIT_STATE, f"the instance did not start: {result.stderr.strip()[:400]}"
        )


def query(plan: node_restore.RestorePlan, sql: str) -> tuple[int, str]:
    result = docker(
        "exec",
        "-i",
        plan.instance_container,
        "psql",
        "-U",
        "postgres",
        "-d",
        plan.database,
        "-X",
        "-qtA",
        "-c",
        sql,
    )
    return result.returncode, result.stdout.strip()


def wait_for_promotion(plan: node_restore.RestorePlan) -> float:
    started = time.monotonic()
    deadline = started + PROMOTION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        running = docker("inspect", "-f", "{{.State.Running}}", plan.instance_container)
        if running.stdout.strip() != "true":
            logs = docker("logs", "--tail", "40", plan.instance_container)
            raise OperatorError(
                EXIT_REFUSED,
                "the restored instance exited before it promoted; the restore wrote a data "
                "directory and recovery failed. Its last words:\n"
                + (logs.stdout or "")
                + (logs.stderr or ""),
            )
        code, answer = query(plan, "SELECT pg_is_in_recovery()")
        if code == 0 and answer == "f":
            return time.monotonic() - started
        time.sleep(2)
    logs = docker("logs", "--tail", "40", plan.instance_container)
    raise OperatorError(
        EXIT_REFUSED,
        f"the restored instance did not promote within {PROMOTION_TIMEOUT_SECONDS}s:\n"
        + (logs.stdout or "")
        + (logs.stderr or ""),
    )


def observe_instance(plan: node_restore.RestorePlan) -> dict[str, Any]:
    reads = {
        "requested_target": "SELECT current_setting('recovery_target_time', true)",
        "achieved_recovery_point": "SELECT pg_last_xact_replay_timestamp()",
        "achieved_lsn": "SELECT pg_last_wal_replay_lsn()",
        "timeline_id": "SELECT timeline_id FROM pg_control_checkpoint()",
        # The newest RELEASE version, which is what "how far is this cluster
        # migrated" means for the platform; a project set's versions are its
        # own and are counted below (ADR 0206).
        "schema_version": "SELECT coalesce(max(version), '') FROM app_private.schema_migrations",
        # Every set, so the record a restore leaves describes the whole cluster
        # rather than the release's half of it (ADR 0206).
        "schema_migration_count": (
            "SELECT (SELECT count(*) FROM app_private.schema_migrations)"
            " + (SELECT count(*) FROM app_private.project_schema_migrations)"
        ),
        "instance_uuid": "SELECT instance_uuid FROM app_private.project_identity",
    }
    observed: dict[str, Any] = {}
    for name, sql in reads.items():
        code, answer = query(plan, sql)
        observed[name] = None if code != 0 or answer == "" else answer
    for name in ("timeline_id", "schema_migration_count"):
        if observed[name] is not None:
            observed[name] = int(observed[name])
    if observed["instance_uuid"] is not None:
        try:
            observed["instance_uuid"] = database_observation.parse_instance_uuid(
                observed["instance_uuid"]
            )
        except ValueError:
            observed["instance_uuid"] = None
    return observed


def stop_instance(plan: node_restore.RestorePlan) -> list[str]:
    """Stop and remove the instance container; the volume stays. What could
    not be removed is reported, never searched for by pattern."""
    problems: list[str] = []
    for name in (plan.instance_container, plan.restore_container):
        if docker("inspect", name).returncode != 0:
            continue
        docker("stop", "-t", "30", name, timeout=60)
        if docker("rm", name).returncode != 0:
            problems.append(f"container {name} could not be removed")
    return problems


def write_state_file(path: Path, plan: node_restore.RestorePlan) -> None:
    """What the shell trap may stop: the two containers. NEVER the volume --
    the whole command exists to leave it holding the restored cluster."""
    lines = [
        f"instance_container={plan.instance_container}",
        f"restore_container={plan.restore_container}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="restore", description=__doc__, add_help=True)
    parser.add_argument("--outputs", type=Path, required=True, help="the kit's deployed document")
    parser.add_argument("--project", type=Path, required=True, help="the manifest deployed here")
    parser.add_argument("--rendered-dir", type=Path, required=True, help="the rendered directory")
    parser.add_argument("--from", dest="source", choices=node_restore.SOURCES, required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--latest", action="store_true")
    target.add_argument("--target-time", metavar="ISO8601")
    parser.add_argument("--session", type=int, default=CURRENT_SESSION)
    parser.add_argument("--evidence-dir", type=Path, default=REPO_ROOT / "evidence")
    parser.add_argument("--secret-root", type=Path, default=Path(SECRET_ROOT))
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--plan", action="store_true", help="print the plan; start nothing")
    return parser


def restore(arguments: argparse.Namespace) -> int:
    document = load_json(arguments.outputs, "deployed document")
    try:
        manifest = config.load_project_manifest(arguments.project, expiry=False)
    except (OSError, ValueError) as error:
        raise OperatorError(EXIT_INPUT, f"the manifest did not load: {error}") from error
    contract = load_secret_contract(REPO_ROOT / "secrets.required.yaml")
    key = str((document.get("project") or {}).get("key") or "")
    if not (arguments.rendered_dir / "compose.env").is_file():
        raise OperatorError(
            EXIT_INPUT, f"{arguments.rendered_dir} holds no rendered project (no compose.env)"
        )
    try:
        generation = access_broker.active_generation(key, secret_root=arguments.secret_root)
    except Exception as error:  # the reader's message names the pointer
        raise OperatorError(
            EXIT_PREREQUISITE,
            f"no active secret generation for {key} on this host ({error}); run "
            "bin/materialize-secrets.sh first -- the restore reads its credential from it.",
        ) from error

    restore_id = new_restore_id()
    staging = Path(tempfile.mkdtemp(prefix=f"apg-restore-{restore_id}-"))
    # World-readable directory: the container reads the configuration as uid
    # 999, and the file carries no credential (build_pgbackrest_conf omits
    # every one by construction).
    os.chmod(staging, 0o755)  # noqa: S103
    configuration_path = staging / "restore.conf"
    try:
        plan = node_restore.build_plan(
            document=document,
            manifest=manifest,
            contract=contract,
            session=arguments.session,
            generation_id=generation,
            configuration_host_path=configuration_path,
            source=arguments.source,
            image="(built below)",
            restore_id=restore_id,
        )
    except node_restore.RestoreRefusal as error:
        raise OperatorError(EXIT_UNSAFE, str(error)) from error
    except node_restore.RestoreError as error:
        raise OperatorError(EXIT_STATE, str(error)) from error
    restore_argv = node_restore.restore_arguments(plan, arguments.target_time)
    try:
        node_restore.assert_own_volume(plan, restore_argv)
    except node_restore.RestoreRefusal as error:
        raise OperatorError(EXIT_UNSAFE, str(error)) from error

    print(f"restore: {restore_id} for {plan.project_key} from the {plan.source} repository")
    print(f"  volume     {plan.volume}  (this project's own; must hold no cluster)")
    print(f"  stanza     {plan.stanza}")
    print(f"  generation {plan.generation_id}")
    print(f"  target     {arguments.target_time or 'latest'}")
    for mount in plan.inherited:
        print(f"  mount      {mount.target}  (read-only)")
    # Both refusals before the plan returns (ADR 0194): a plan that printed
    # "would restore into" the production cluster's volume exited 0 on the
    # first host gate of Session 18 (D1031). The mounted check is a `docker
    # ps`; the cluster check reads one file through the pinned runtime
    # image, so the plan builds nothing.
    mounted_by = containers_mounting(plan.volume)
    if mounted_by:
        raise OperatorError(
            EXIT_UNSAFE,
            f"{plan.volume} is mounted by {mounted_by}; a restore into a volume a container "
            "holds is refused. On a production host that is the running cluster.",
        )
    if arguments.plan:
        if volume_exists(plan.volume) and volume_holds_a_cluster(plan.volume, probe_image()):
            raise OperatorError(
                EXIT_UNSAFE,
                f"{plan.volume} already holds a cluster (PG_VERSION is present, D1012); the "
                "run would refuse it and so does the plan (ADR 0194).",
            )
        print("restore: --plan; nothing was started.")
        return 0

    image = build_image(arguments.rendered_dir)
    plan = node_restore.RestorePlan(**{**plan.__dict__, "image": image})
    if volume_exists(plan.volume):
        if volume_holds_a_cluster(plan.volume, image):
            raise OperatorError(
                EXIT_UNSAFE,
                f"{plan.volume} already holds a cluster (PG_VERSION is present, D1012). A "
                "restore never overwrites one, on any host. If this is a replacement host "
                "whose first `up` ran before the restore, remove the project's volume "
                "deliberately and restore again.",
            )
    else:
        create_volume(plan.volume, image)

    configuration_path.write_text(plan.configuration, encoding="utf-8")
    os.chmod(configuration_path, 0o444)
    if arguments.state_file:
        write_state_file(arguments.state_file, plan)

    summary, backups = read_repository(plan)
    rto_started = time.monotonic()
    problems: list[str] = []
    try:
        result, restore_seconds = run_restore(plan, restore_argv)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()[:600]
            if result.returncode == restore_drill.RESTORE_EXIT_POPULATED_DIRECTORY:
                raise OperatorError(
                    EXIT_UNSAFE,
                    f"pgBackRest refused a populated data directory (exit {result.returncode}); "
                    f"the volume was not empty.\n{detail}",
                )
            raise OperatorError(
                EXIT_REFUSED, f"the restore failed (pgBackRest exit {result.returncode}).\n{detail}"
            )
        label = restore_drill.parse_backup_set(result.stdout + result.stderr)
        backup_type = restore_drill.backup_set_type(backups, label)
        reported = _REPORTED_MS.search(result.stdout + result.stderr)

        start_instance(plan)
        recovery_seconds = wait_for_promotion(plan)
        rto_seconds = time.monotonic() - rto_started
        observed = observe_instance(plan)
        evidence = node_restore.evidence_document(
            plan=plan,
            restore_id=restore_id,
            requested_target=arguments.target_time,
            observed=observed,
            repository=summary,
            backup_set={"label": label, "type": backup_type},
            timings={
                "restore_seconds": restore_seconds,
                "recovery_seconds": recovery_seconds,
                "rto_seconds": rto_seconds,
                "pgbackrest_reported_ms": int(reported.group("ms")) if reported else None,
            },
        )
    finally:
        problems = stop_instance(plan)
        if arguments.state_file:
            Path(arguments.state_file).unlink(missing_ok=True)
        configuration_path.unlink(missing_ok=True)
        staging.rmdir()

    arguments.evidence_dir.mkdir(parents=True, exist_ok=True)
    path = arguments.evidence_dir / f"restore-{plan.project_key}-{restore_id}.json"
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    print(f"restore: evidence written to {path}")
    for problem in problems:
        print(f"restore: CLEANUP -- {problem}", file=sys.stderr)

    verdict = evidence["verdict"]
    if not verdict["passed"]:
        for reason in verdict["reasons"]:
            print(f"restore: {reason}", file=sys.stderr)
        return EXIT_REFUSED
    print(
        f"restore: verified. {plan.volume} holds the promoted cluster (timeline "
        f"{evidence['recovery']['timeline_id']}, instance {observed.get('instance_uuid')}); "
        "deploy the project now -- the cluster starts on it without initdb."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        require_root()
        return int(restore(arguments))
    except OperatorError as error:
        print(f"restore: {error}", file=sys.stderr)
        return error.code
    except subprocess.TimeoutExpired as error:
        print(f"restore: docker did not answer within {error.timeout}s.", file=sys.stderr)
        return EXIT_STATE


if __name__ == "__main__":
    raise SystemExit(main())
