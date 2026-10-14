"""A branch's whole life on this host: create, reset, delete, start, status (ADR 0271).

Invoked by `sudo bin/branch-runtime.sh` -- by the reconciler for an operation
(Run 5), by an operator to read (`status`) -- and never by a customer. A branch
is its own Compose project of three services (`infra/branch/compose.yaml`),
restored from its parent's repository and re-keyed before either door exists.
It holds no secret of its own, has no systemd unit and publishes no port.

`create` runs, in this order, and the order is the property
(`test_branch_runtime.py::test_the_poolers_start_after_the_rekey`):

    refuse     the parent must be a project with public endpoints, running
               (a sleeping parent is refused: wake it first, D2438), and the
               branch must not exist
    dns        both branch names resolve to this host, no AAAA (D2428)
    window     a --target-time inside the parent's recorded restore window:
               its oldest backup's STOP, the archiver's last archived time
               (D2457, D2456); outside it, exit 7 before anything persists
    plan       `branch_plan.build` + `assert_branch_safe` (exit 7, D2426)
    admit      `small`'s 192 MiB against what the node has committed (exit 12)
    record     `branch.json` `creating`, BEFORE anything is created
    restore    pgBackRest into the branch's own volume (read-only repository)
    recover    a recovery instance, archiving off, until it promotes; removed
    persist    the branch's `postgres`: no repository, its own network
    rekey      every platform role NOLOGIN, the branch's verifiers (D2427)
    userlists  read back from the branch's own `pg_authid` (D2460)
    doors      the two customer poolers
    attach     the edge proxy joins the branch's edge network
    ready      `branch.json` `ready`, with the point reached and the timeline

Exit codes:
  0  done; or every branch's state determined
  2  invalid input
  3  a prerequisite is missing: root, a file, the parent's document or container
  5  refused: the branch exists or does not, the parent cannot have one now,
     a name does not resolve here, or pgBackRest or Docker refused
  6  could not determine: a reading failed, a branch did not come back
  7  refused as unsafe or outside the window; nothing was started for it
  12 admission: the branch does not fit on this node
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml  # noqa: E402

from agentic_postgres import (  # noqa: E402
    backup_report,
    branch_plan,
    branch_record,
    branch_rekey,
    capacity_probe,
    capacity_reading,
    container_exec,
    customer_credentials,
    deployed_output,
    host_config,
    naming,
    restore_drill,
    runtime_override,
    secrets_contract,
    slot,
)

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_REFUSED = 5
EXIT_UNKNOWN = 6
EXIT_UNSAFE = 7
EXIT_ADMISSION = 12

BRANCH_ROOT = branch_record.BRANCH_ROOT
PROJECT_ROOT = deployed_output.PROJECT_STATE_ROOT
DEFAULT_HOST = Path("/etc/agentic-postgres/host.yaml")
COMPOSE_FILE = REPO_ROOT / "infra" / "branch" / "compose.yaml"
EDGE_NETWORK_SH = REPO_ROOT / "bin" / "edge-network.sh"
SECRET_CONTRACT = REPO_ROOT / "secrets.required.yaml"

POSTGRES_UID = "999"
POOLER_GID: int | None = customer_credentials.POOLER_GID
QUICK_SECONDS = 60
COMPOSE_SECONDS = 300
RESTORE_SECONDS = 7200
PROMOTION_SECONDS = 900

#: PostgreSQL's words when recovery ran out of WAL before the target (rig 40a).
_TARGET_NOT_REACHED = "recovery ended before configured recovery target was reached"
_LAST_TRANSACTION = re.compile(r"last completed transaction was at log time (\S+ \S+)")
_VERIFIER_TEXT = re.compile(r"SCRAM-SHA-256\$\S+")


class OperatorError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def say(message: str) -> None:
    print(f"branch-runtime: {message}", flush=True)


def require_root() -> None:
    if os.geteuid() != 0:
        raise OperatorError(
            EXIT_PREREQUISITE,
            "must run as root: a branch's volume, containers and state directory are root's.",
        )


def docker(*arguments: str, timeout: float = QUICK_SECONDS) -> subprocess.CompletedProcess:
    """One `docker` command, stdin closed, output captured."""
    return subprocess.run(
        ["docker", *arguments],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _tail(text: str, lines: int = 6) -> str:
    kept = [line for line in (text or "").strip().splitlines() if line.strip()]
    return _VERIFIER_TEXT.sub("SCRAM-SHA-256$<redacted>", " | ".join(kept[-lines:]))


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Reading the parent
# ---------------------------------------------------------------------------


def load_document(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise OperatorError(EXIT_PREREQUISITE, f"no deployed document at {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise OperatorError(EXIT_PREREQUISITE, f"{path} could not be read: {error}") from None
    if not isinstance(document, dict) or not (document.get("project") or {}).get("key"):
        raise OperatorError(EXIT_PREREQUISITE, f"{path} names no project key")
    return document


def load_host(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise OperatorError(EXIT_PREREQUISITE, f"host manifest not found: {path}")
    try:
        return host_config.load_host_manifest(path)
    except (OSError, ValueError) as error:
        raise OperatorError(EXIT_INPUT, f"the host manifest is refused: {error}") from None


def inspect_running(container: str, what: str) -> dict[str, Any]:
    """`docker inspect` of a container that must be RUNNING (D2438: a sleeping
    parent's containers are stopped, and a restore through one was never measured)."""
    done = docker("inspect", container)
    if done.returncode != 0:
        raise OperatorError(
            EXIT_REFUSED, f"{what} {container} does not exist: is the project deployed here?"
        )
    try:
        inspect = json.loads(done.stdout)[0]
    except (ValueError, IndexError):
        raise OperatorError(EXIT_UNKNOWN, f"docker inspect {container} was not readable") from None
    if not (inspect.get("State") or {}).get("Running"):
        raise OperatorError(
            EXIT_REFUSED,
            f"{what} {container} is not running: the project sleeps or is stopped. "
            "Wake the project first; a branch is restored through its running database.",
        )
    return inspect


def refuse(document: dict[str, Any], branch: str) -> None:
    """The parent can have this branch now, or the reason it cannot."""
    key = str(document["project"]["key"])
    public = (document.get("database") or {}).get("public") or {}
    if not public.get("enabled"):
        raise OperatorError(
            EXIT_REFUSED, f"{key} has no public endpoints, so a branch of it would have no door"
        )
    path = branch_record.record_path(key, branch, root=BRANCH_ROOT)
    if path.parent.exists():
        raise OperatorError(
            EXIT_REFUSED,
            f"{key}_{branch} already exists ({path.parent}); reset it or delete it first",
        )


def check_dns(plan: branch_plan.BranchPlan, host: dict[str, Any]) -> None:
    expected = (host.get("host") or {}).get("expected_public_ipv4")
    for name in plan.hosts:
        resolves, why = slot.dns_reading(name, expected)
        if resolves is None:
            raise OperatorError(EXIT_UNKNOWN, f"could not read {name}: {why}")
        if not resolves:
            raise OperatorError(
                EXIT_REFUSED,
                f"this project's branch names do not resolve to this server ({why}): create "
                "the two wildcard records (operator guide §22)",
            )
    say(f"dns: {plan.hosts[0]} and {plan.hosts[1]} resolve here")


def read_window(document: dict[str, Any]) -> tuple[datetime, datetime]:
    """`(earliest, latest)` from the parent's own readings, or exit 6 (ADR 0273)."""
    database = document.get("database") or {}
    container, name = str(database.get("container") or ""), str(database.get("name") or "")
    stanza = str((document.get("backup") or {}).get("stanza") or "")
    info = container_exec.run(
        container, "pgbackrest", f"--stanza={stanza}", "--output=json", "info",
        user=POSTGRES_UID, timeout=QUICK_SECONDS,
    )  # fmt: skip
    archiver = container_exec.run(
        container, "psql", "-U", "postgres", "-d", name, "-X", "-qtA",
        "-F", backup_report.ARCHIVER_SEPARATOR, "-c", backup_report.ARCHIVER_QUERY,
        timeout=QUICK_SECONDS,
    )  # fmt: skip
    if info.returncode != 0 or archiver.returncode != 0:
        raise OperatorError(
            EXIT_UNKNOWN,
            "the parent's restore window could not be read: "
            + _tail(info.stderr if info.returncode else archiver.stderr, 2),
        )
    try:
        summary = backup_report.summarise(json.loads(info.stdout), stanza)
    except ValueError as error:
        raise OperatorError(EXIT_UNKNOWN, f"pgbackrest info was not readable: {error}") from None
    parsed = backup_report.parse_archiver(archiver.stdout)
    # The oldest stop PLUS ONE SECOND: pgBackRest refuses a target inside the
    # recorded stop's own second (D2465, measured by the cluster proof).
    earliest = backup_report.earliest_point(summary.get("oldest_backup_stop"))
    latest = restore_drill.instant((parsed or {}).get("last_archived_time"))
    if earliest is None or latest is None:
        raise OperatorError(
            EXIT_UNKNOWN,
            "the parent's restore window could not be determined: "
            f"oldest backup stop {summary.get('oldest_backup_stop')!r}, "
            f"last archived {(parsed or {}).get('last_archived_time')!r}",
        )
    return earliest, latest


def check_window(target: str | None, window: tuple[datetime, datetime]) -> None:
    if target is None:
        say("window: no point given; the branch is restored to the end of the archive")
        return
    instant = restore_drill.instant(target)
    earliest, latest = window
    if instant is None or not (earliest <= instant <= latest):
        raise OperatorError(
            EXIT_UNSAFE,
            f"the point {target} is outside this project's restore window "
            f"({earliest.isoformat()} ... {latest.isoformat()})",
        )
    say(f"window: {target} is inside {earliest.isoformat()} ... {latest.isoformat()}")


def build_plan(
    document: dict[str, Any], inspect: dict[str, Any], branch: str, target: str | None
) -> branch_plan.BranchPlan:
    try:
        plan = branch_plan.build(
            document=document,
            inspect=inspect,
            contract=secrets_contract.load_secret_contract(SECRET_CONTRACT),
            branch=branch,
            target_time=target,
        )
        branch_plan.assert_branch_safe(plan)
    except branch_plan.BranchSafetyError as error:
        raise OperatorError(EXIT_UNSAFE, str(error)) from None
    except restore_drill.DrillError as error:
        raise OperatorError(EXIT_REFUSED, str(error)) from None
    return plan


def _runner(*command: str, timeout: int = QUICK_SECONDS) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            list(command),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def admit(plan: branch_plan.BranchPlan, host_path: Path) -> None:
    reading, _ = capacity_probe.read(
        host_path, PROJECT_ROOT, runner=_runner, branch_root=BRANCH_ROOT
    )
    decision = capacity_reading.decide(
        reading,
        candidate_key=f"{plan.names.stem.removeprefix('apg-')} (branch)",
        candidate_unreclaimable_mb=branch_plan.BRANCH_UNRECLAIMABLE_MB,
        candidate_is_deployed=False,
    )
    for name, value in decision.lines:
        print(f"  {name:<16} {value}")
    if decision.outcome != "admitted":
        raise OperatorError(EXIT_ADMISSION, f"the branch does not fit: {decision.reason}")


# ---------------------------------------------------------------------------
# The three phases
# ---------------------------------------------------------------------------


def _run_arguments(phase: branch_plan.Phase, *, detached: bool) -> list[str]:
    arguments = ["run", "--name", phase.container, "-u", f"{POSTGRES_UID}:{POSTGRES_UID}"]
    arguments += ["-d"] if detached else ["--rm"]
    for mount in phase.mounts:
        arguments += ["--mount", mount.as_mount_argument()]
    for name, value in sorted(phase.environment.items()):
        arguments += ["--env", f"{name}={value}"]
    if phase.network:
        arguments += ["--network", phase.network]
    return arguments


def create_volume(plan: branch_plan.BranchPlan) -> None:
    if docker("volume", "inspect", plan.names.volume).returncode == 0:
        raise OperatorError(
            EXIT_REFUSED,
            f"the branch volume {plan.names.volume} already exists: a leftover this command "
            "did not record; `delete` removes it",
        )
    done = docker(
        "volume", "create",
        "--label", f"apg.branch.project={plan.project_key}",
        "--label", f"apg.branch.name={plan.branch}",
        plan.names.volume,
    )  # fmt: skip
    if done.returncode != 0:
        raise OperatorError(
            EXIT_REFUSED, f"the branch volume was not created: {_tail(done.stderr)}"
        )


def restore(plan: branch_plan.BranchPlan) -> float:
    started = time.monotonic()
    phase = plan.restore
    done = docker(
        *_run_arguments(phase, detached=False),
        "--entrypoint", str(phase.entrypoint), phase.image, *phase.argv,
        timeout=RESTORE_SECONDS,
    )  # fmt: skip
    seconds = time.monotonic() - started
    if done.returncode == restore_drill.RESTORE_EXIT_NO_BACKUP_SET:
        raise OperatorError(
            EXIT_UNSAFE,
            f"the point {plan.target} is before this project's oldest backup: "
            + _tail(done.stdout + done.stderr, 2),
        )
    if done.returncode != 0:
        raise OperatorError(
            EXIT_REFUSED,
            f"pgBackRest refused the restore (exit {done.returncode}): "
            + restore_drill.failure_detail(done.stdout, done.stderr),
        )
    say(f"restore: {seconds:.1f} s into {plan.names.volume}")
    return seconds


def _query(container: str, database: str, sql: str) -> tuple[int, str]:
    done = container_exec.run(
        container, "psql", "-U", "postgres", "-d", database, "-X", "-qtA", "-c", sql,
        timeout=QUICK_SECONDS,
    )  # fmt: skip
    return done.returncode, done.stdout.strip()


def recover(plan: branch_plan.BranchPlan) -> tuple[str | None, int | None, float]:
    """`(reached point, timeline, seconds)`; the recovery container removed in every case."""
    phase = plan.recovery
    name = phase.container
    started = docker(*_run_arguments(phase, detached=True), phase.image, *phase.argv)
    if started.returncode != 0:
        raise OperatorError(
            EXIT_REFUSED, f"the recovery instance did not start: {_tail(started.stderr)}"
        )
    began = time.monotonic()
    try:
        while time.monotonic() - began < PROMOTION_SECONDS:
            running = docker("inspect", "-f", "{{.State.Running}}", name).stdout.strip()
            if running != "true":
                logs = docker("logs", "--tail", "40", name)
                text = (logs.stdout or "") + (logs.stderr or "")
                if _TARGET_NOT_REACHED in text:
                    last = _LAST_TRANSACTION.search(text)
                    raise OperatorError(
                        EXIT_UNSAFE,
                        "the newest change in this project's archive is at "
                        f"{last.group(1) if last else 'an instant the log did not name'}; "
                        f"the point {plan.target} is after it",
                    )
                raise OperatorError(
                    EXIT_UNKNOWN, f"the recovery instance exited before it promoted: {_tail(text)}"
                )
            code, answer = _query(name, plan.database, "SELECT pg_is_in_recovery()")
            if code == 0 and answer == "f":
                break
            time.sleep(2)
        else:
            raise OperatorError(
                EXIT_UNKNOWN, f"the recovery instance did not promote within {PROMOTION_SECONDS} s"
            )
        seconds = time.monotonic() - began
        _query(name, plan.database, "CHECKPOINT")
        _, reached = _query(name, plan.database, "SELECT pg_last_xact_replay_timestamp()")
        _, timeline = _query(name, plan.database, "SELECT timeline_id FROM pg_control_checkpoint()")
        point = reached or "no transaction"
        say(f"recover: promoted in {seconds:.1f} s, reached {point}, timeline {timeline}")
        return (reached or None), (int(timeline) if timeline.isdigit() else None), seconds
    finally:
        docker("stop", "-t", "60", name, timeout=120)
        docker("rm", "-f", name)


def write_compose_state(
    plan: branch_plan.BranchPlan, *, pgbouncer_image: str, acme_resolver_name: str
) -> None:
    """The env file and the override, 0600 in the branch's 0700 directory."""
    directory = branch_record.branch_directory(plan.project_key, plan.branch, root=BRANCH_ROOT)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    environment = branch_plan.compose_environment(
        plan, pgbouncer_image=pgbouncer_image, acme_resolver_name=acme_resolver_name
    )
    override = branch_plan.compose_override(
        plan, userlist_directory=str(directory / runtime_override.CUSTOMER_USERLIST_DIRNAME)
    )
    _write_private(directory / "branch.env", "".join(f"{k}={v}\n" for k, v in environment.items()))
    _write_private(directory / "compose.override.yaml", yaml.safe_dump(override, sort_keys=True))


def _write_private(path: Path, text: str) -> None:
    staging = path.with_name(f".{path.name}.new")
    staging.unlink(missing_ok=True)
    descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, text.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(staging, path)


def compose(plan: branch_plan.BranchPlan, *arguments: str) -> subprocess.CompletedProcess:
    directory = branch_record.branch_directory(plan.project_key, plan.branch, root=BRANCH_ROOT)
    return docker(
        "compose", "-p", plan.names.compose_project,
        "--env-file", str(directory / "branch.env"),
        "-f", str(COMPOSE_FILE), "-f", str(directory / "compose.override.yaml"),
        *arguments,
        timeout=COMPOSE_SECONDS,
    )  # fmt: skip


def persist(plan: branch_plan.BranchPlan) -> None:
    done = compose(plan, "up", "-d", "--wait", "postgres")
    if done.returncode != 0:
        raise OperatorError(
            EXIT_UNKNOWN, f"the branch's postgres did not start: {_tail(done.stderr)}"
        )
    say(f"persist: {plan.names.postgres_container} up, no repository, archiving off")


def rekey(plan: branch_plan.BranchPlan, verifiers: dict[str, str]) -> None:
    """The re-key, then the restore settings reset (D2427, D2459)."""
    try:
        text = branch_rekey.psql_input(plan.roles, verifiers)
    except branch_rekey.RekeyError as error:
        raise OperatorError(EXIT_INPUT, str(error)) from None
    psql = (
        "psql",
        "-U",
        "postgres",
        "-d",
        plan.database,
        "-X",
        "-qtA",
        "-v",
        "ON_ERROR_STOP=1",
        "-f",
        "-",
    )
    done = container_exec.run(plan.names.postgres_container, *psql, input=text, timeout=120)
    if done.returncode != 0:
        errors = [line for line in done.stderr.splitlines() if "ERROR" in line or "FATAL" in line]
        raise OperatorError(
            EXIT_UNKNOWN, f"the re-key did not commit: {_tail(chr(10).join(errors))}"
        )
    reset = container_exec.run(
        plan.names.postgres_container,
        *psql,
        input="\n".join(branch_rekey.reset_statements()),
        timeout=60,
    )
    if reset.returncode != 0:
        raise OperatorError(
            EXIT_UNKNOWN, f"the restore settings were not reset: {_tail(reset.stderr)}"
        )
    say("rekey: every platform role NOLOGIN, the branch's own verifiers set, sessions revoked")


def write_userlists(plan: branch_plan.BranchPlan) -> None:
    """Each door's userlist, from the branch's own `pg_authid` (D2460)."""
    roles = {
        naming.CUSTOMER_POOL_SERVICE: plan.roles["customer_app"],
        naming.CUSTOMER_DIRECT_SERVICE: plan.roles["customer_admin"],
    }
    done = container_exec.run(
        plan.names.postgres_container,
        "psql", "-U", "postgres", "-d", plan.database, "-X", "-qtA", "-v", "ON_ERROR_STOP=1",
        "-v", f"pool_role={roles[naming.CUSTOMER_POOL_SERVICE]}",
        "-v", f"direct_role={roles[naming.CUSTOMER_DIRECT_SERVICE]}",
        "-f", "-",
        input=customer_credentials.VERIFIER_QUERY,
        timeout=QUICK_SECONDS,
    )  # fmt: skip
    if done.returncode != 0:
        raise OperatorError(
            EXIT_UNKNOWN, f"the branch's verifiers were not readable: {_tail(done.stderr)}"
        )
    try:
        verifiers = customer_credentials.parse_verifiers(done.stdout, tuple(roles.values()))
    except customer_credentials.CredentialError as error:
        raise OperatorError(EXIT_UNKNOWN, str(error)) from None
    if any(value is None for value in verifiers.values()):
        raise OperatorError(EXIT_UNKNOWN, "a customer role has no verifier after the re-key")
    directory = (
        branch_record.branch_directory(plan.project_key, plan.branch, root=BRANCH_ROOT)
        / runtime_override.CUSTOMER_USERLIST_DIRNAME
    )
    customer_credentials.ensure_directory(directory, gid=POOLER_GID)
    for service, role in roles.items():
        customer_credentials.write_userlist(
            directory,
            runtime_override.CUSTOMER_USERLISTS[service],
            customer_credentials.userlist(role, verifiers[role]),
            gid=POOLER_GID,
        )
    say("userlists: one role per door, read from the branch's own catalog")


def open_doors(plan: branch_plan.BranchPlan) -> None:
    done = compose(
        plan, "up", "-d", "--wait", naming.CUSTOMER_POOL_SERVICE, naming.CUSTOMER_DIRECT_SERVICE
    )
    if done.returncode != 0:
        raise OperatorError(EXIT_UNKNOWN, f"the branch's doors did not start: {_tail(done.stderr)}")
    say(f"doors: {plan.hosts[0]} and {plan.hosts[1]}")


def attach(names: naming.BranchNames) -> None:
    done = subprocess.run(
        [str(EDGE_NETWORK_SH), "attach-network", names.edge_network],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=QUICK_SECONDS,
        check=False,
    )
    if done.returncode != 0:
        raise OperatorError(EXIT_UNKNOWN, f"the edge did not attach: {_tail(done.stderr)}")
    say(f"attach: the edge joined {names.edge_network}")


def detach(names: naming.BranchNames) -> None:
    subprocess.run(
        [str(EDGE_NETWORK_SH), "detach-network", names.edge_network],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=QUICK_SECONDS,
        check=False,
    )


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def record(plan: branch_plan.BranchPlan, *, state: str, **values: Any) -> branch_record.Record:
    path = branch_record.record_path(plan.project_key, plan.branch, root=BRANCH_ROOT)
    previous = _read(path)
    base: dict[str, Any] = (
        {member: getattr(previous, member) for member in previous.__dataclass_fields__}
        if previous is not None
        else {
            "project_key": plan.project_key,
            "branch": plan.branch,
            "operation": values.get("operation", "unknown"),
            "requested_point": plan.target,
            "reached_point": None,
            "timeline": None,
            "parent_commit": None,
            "pool_host": plan.hosts[0],
            "direct_host": plan.hosts[1],
            "expires_at": None,
            "expires_for": None,
            "unreclaimable_mb": branch_plan.BRANCH_UNRECLAIMABLE_MB,
            "created_at": now(),
        }
    )
    base.pop("schema_version", None)
    base.update(values)
    base.update(state=state, updated_at=now())
    written = branch_record.Record(**base)
    branch_record.write(path, written)
    return written


def _read(path: Path) -> branch_record.Record | None:
    try:
        return branch_record.read(path)
    except branch_record.UnreadableRecord:
        return None


# ---------------------------------------------------------------------------
# Verbs
# ---------------------------------------------------------------------------


def read_verifiers() -> dict[str, str]:
    """`{"customer_app": <verifier>, "customer_admin": <verifier>}` on stdin --
    the reconciler's pipe. Never an argument, never echoed."""
    try:
        verifiers = json.loads(sys.stdin.read())
    except ValueError:
        raise OperatorError(EXIT_INPUT, "--verifiers-stdin: stdin is not a JSON object") from None
    if not isinstance(verifiers, dict) or set(verifiers) != set(branch_rekey.CUSTOMER_ROLES):
        raise OperatorError(
            EXIT_INPUT,
            f"--verifiers-stdin: expected exactly {list(branch_rekey.CUSTOMER_ROLES)}",
        )
    return verifiers


def _build_life(
    plan: branch_plan.BranchPlan, verifiers: dict[str, str], *, pgbouncer_image: str, resolver: str
) -> tuple[str | None, int | None]:
    """restore -> recover -> persist -> rekey -> userlists -> doors -> attach."""
    restore(plan)
    reached, timeline, _ = recover(plan)
    write_compose_state(plan, pgbouncer_image=pgbouncer_image, acme_resolver_name=resolver)
    persist(plan)
    rekey(plan, verifiers)
    write_userlists(plan)
    open_doors(plan)
    attach(plan.names)
    return reached, timeline


def command_create(arguments: argparse.Namespace) -> int:
    require_root()
    verifiers = read_verifiers()
    if (arguments.expires_at is None) != (arguments.expires_for is None):
        raise OperatorError(EXIT_INPUT, "--expires-at and --expires-for go together (ADR 0272)")
    document = load_document(arguments.parent_outputs)
    host = load_host(arguments.host)
    refuse(document, arguments.branch)
    inspect = inspect_running(str(document["database"]["container"]), "the parent's database")
    pooler = inspect_running(
        naming.customer_pooler_containers(str(document["project"]["key"]))[0], "the parent's pooler"
    )
    plan = build_plan(document, inspect, arguments.branch, arguments.target_time)
    check_dns(plan, host)
    check_window(plan.target, read_window(document))
    admit(plan, arguments.host)
    record(
        plan,
        state="creating",
        operation=arguments.operation,
        parent_commit=document.get("source_commit"),
        expires_at=arguments.expires_at,
        expires_for=arguments.expires_for,
    )
    try:
        create_volume(plan)
        reached, timeline = _build_life(
            plan, verifiers, pgbouncer_image=str(pooler.get("Image") or ""),
            resolver=str(host["edge"]["acme_resolver_name"]),
        )  # fmt: skip
    except BaseException:
        record(plan, state="failed")
        raise
    record(plan, state="ready", reached_point=reached, timeline=timeline)
    say(f"{plan.names.stem.removeprefix('apg-')}: ready at {reached}, timeline {timeline}")
    return EXIT_OK


def _remove_runtime(names: naming.BranchNames) -> None:
    """Every container of the branch, then its networks: derived names only (D2438)."""
    detach(names)
    for container in (
        names.pool_container,
        names.direct_container,
        names.postgres_container,
        names.recovery_container,
        names.restore_container,
    ):
        docker("rm", "-f", container, timeout=120)
    for network in (names.edge_network, names.internal_network):
        docker("network", "rm", network)


def command_reset(arguments: argparse.Namespace) -> int:
    require_root()
    verifiers = read_verifiers()
    document = load_document(arguments.parent_outputs)
    host = load_host(arguments.host)
    key = str(document["project"]["key"])
    path = branch_record.record_path(key, arguments.branch, root=BRANCH_ROOT)
    try:
        current = branch_record.read(path)
    except branch_record.UnreadableRecord as error:
        raise OperatorError(EXIT_UNKNOWN, str(error)) from None
    if current is None or current.state not in ("ready", "stopped", "failed"):
        raise OperatorError(
            EXIT_REFUSED,
            f"{key}_{arguments.branch} cannot be reset: "
            + ("it does not exist" if current is None else f"it is {current.state}"),
        )
    inspect = inspect_running(str(document["database"]["container"]), "the parent's database")
    pooler = inspect_running(naming.customer_pooler_containers(key)[0], "the parent's pooler")
    plan = build_plan(document, inspect, arguments.branch, arguments.target_time)
    check_window(plan.target, read_window(document))
    record(
        plan,
        state="creating",
        operation=arguments.operation,
        requested_point=plan.target,
        reached_point=None,
        timeline=None,
        parent_commit=document.get("source_commit"),
    )
    try:
        _remove_runtime(plan.names)
        docker("volume", "rm", plan.names.volume, timeout=120)
        create_volume(plan)
        reached, timeline = _build_life(
            plan, verifiers, pgbouncer_image=str(pooler.get("Image") or ""),
            resolver=str(host["edge"]["acme_resolver_name"]),
        )  # fmt: skip
    except BaseException:
        record(plan, state="failed")
        raise
    record(plan, state="ready", reached_point=reached, timeline=timeline)
    say(f"{plan.names.stem.removeprefix('apg-')}: reset to {reached}, timeline {timeline}")
    return EXIT_OK


def command_delete(arguments: argparse.Namespace) -> int:
    require_root()
    try:
        names = naming.branch_names(arguments.parent_key, arguments.branch)
        directory = branch_record.branch_directory(
            arguments.parent_key, arguments.branch, root=BRANCH_ROOT
        )
    except naming.NamingError as error:
        raise OperatorError(EXIT_INPUT, str(error)) from None
    existed = directory.exists()
    existed |= docker("volume", "inspect", names.volume).returncode == 0
    for container in (names.postgres_container, names.pool_container, names.direct_container):
        existed |= docker("inspect", container).returncode == 0
    if not existed:
        say(f"nothing of {names.stem.removeprefix('apg-')} exists")
        return EXIT_OK
    path = directory / branch_record.RECORD_FILENAME
    current = _read(path)
    if current is not None:
        branch_record.write(
            path,
            branch_record.Record(
                **{
                    **{m: getattr(current, m) for m in current.__dataclass_fields__},
                    "state": "deleting",
                    "updated_at": now(),
                }
            ),
        )
    _remove_runtime(names)
    gone = docker("volume", "rm", names.volume, timeout=120)
    if gone.returncode != 0 and docker("volume", "inspect", names.volume).returncode == 0:
        raise OperatorError(
            EXIT_UNKNOWN, f"the branch volume was not removed: {_tail(gone.stderr)}"
        )
    if directory.exists():
        shutil.rmtree(directory)
    parent_directory = directory.parent
    if parent_directory.exists() and not any(parent_directory.iterdir()):
        parent_directory.rmdir()
    say(
        f"{names.stem.removeprefix('apg-')}: deleted -- its containers, networks, volume and record"
    )
    return EXIT_OK


def _plan_from_record(current: branch_record.Record) -> naming.BranchNames:
    return naming.branch_names(current.project_key, current.branch)


def command_start(arguments: argparse.Namespace) -> int:
    """Bring every recorded branch back -- after a reboot, by the reconciler (D2439)."""
    require_root()
    found, unreadable = branch_record.records(BRANCH_ROOT)
    failed = 0
    for name, why in sorted(unreadable.items()):
        print(f"  {name}: could not be read: {why}")
        failed += 1
    for name, current in sorted(found.items()):
        if current.state not in ("ready", "stopped"):
            print(f"  {name}: {current.state}; not started")
            continue
        names = _plan_from_record(current)
        directory = branch_record.branch_directory(
            current.project_key, current.branch, root=BRANCH_ROOT
        )
        done = docker(
            "compose", "-p", names.compose_project,
            "--env-file", str(directory / "branch.env"),
            "-f", str(COMPOSE_FILE), "-f", str(directory / "compose.override.yaml"),
            "up", "-d", "--wait",
            timeout=COMPOSE_SECONDS,
        )  # fmt: skip
        try:
            if done.returncode != 0:
                raise OperatorError(EXIT_UNKNOWN, _tail(done.stderr))
            attach(names)
        except OperatorError as error:
            branch_record.write(
                directory / branch_record.RECORD_FILENAME,
                branch_record.Record(
                    **{
                        **{m: getattr(current, m) for m in current.__dataclass_fields__},
                        "state": "stopped",
                        "updated_at": now(),
                    }
                ),
            )
            print(f"  {name}: did not come back: {error}")
            failed += 1
            continue
        if current.state != "ready":
            branch_record.write(
                directory / branch_record.RECORD_FILENAME,
                branch_record.Record(
                    **{
                        **{m: getattr(current, m) for m in current.__dataclass_fields__},
                        "state": "ready",
                        "updated_at": now(),
                    }
                ),
            )
        print(f"  {name}: started")
    return EXIT_UNKNOWN if failed else EXIT_OK


def command_status(arguments: argparse.Namespace) -> int:
    require_root()
    found, unreadable = branch_record.records(BRANCH_ROOT)
    rows: list[dict[str, Any]] = []
    for name, current in sorted(found.items()):
        names = _plan_from_record(current)
        listed = docker(
            "ps", "-a", "--filter", f"label=com.docker.compose.project={names.compose_project}",
            "--format", "{{.Names}} {{.State}}",
        )  # fmt: skip
        containers = (
            dict(line.split(" ", 1) for line in listed.stdout.splitlines() if " " in line)
            if listed.returncode == 0
            else None
        )
        rows.append({"branch": name, "state": current.state, "reached_point": current.reached_point,
                     "timeline": current.timeline, "pool_host": current.pool_host,
                     "direct_host": current.direct_host, "expires_at": current.expires_at,
                     "containers": containers})  # fmt: skip
    for name, why in sorted(unreadable.items()):
        rows.append({"branch": name, "state": "undetermined", "why": why})
    if arguments.json:
        print(json.dumps({"branches": rows}, indent=2, sort_keys=True))
    else:
        if not rows:
            print("branch-runtime: no branches on this host")
        for row in rows:
            detail = row.get("why") or (
                f"reached {row['reached_point']}, timeline {row['timeline']}, "
                f"containers {row['containers'] if row['containers'] is not None else 'unreadable'}"
            )
            print(f"  {row['branch']}: {row['state']} -- {detail}")
    return EXIT_UNKNOWN if unreadable else EXIT_OK


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


def _target_time(value: str) -> str:
    try:
        return restore_drill.pgbackrest_target(value)
    except restore_drill.DrillError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def _branch(value: str) -> str:
    try:
        return naming.validate_branch_name(value)
    except naming.NamingError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="branch-runtime", description=__doc__.split("\n", 1)[0])
    verbs = parser.add_subparsers(dest="verb", required=True)

    for verb in ("create", "reset"):
        command = verbs.add_parser(verb)
        command.add_argument("--parent-outputs", type=Path, required=True)
        command.add_argument("--branch", type=_branch, required=True)
        command.add_argument("--verifiers-stdin", action="store_true", required=True)
        command.add_argument("--target-time", type=_target_time, default=None)
        command.add_argument("--operation", required=True)
        command.add_argument("--host", type=Path, default=DEFAULT_HOST)
        if verb == "create":
            command.add_argument("--expires-at", default=None)
            command.add_argument("--expires-for", default=None)

    delete = verbs.add_parser("delete")
    delete.add_argument("--parent-key", required=True)
    delete.add_argument("--branch", type=_branch, required=True)

    start = verbs.add_parser("start")
    start.add_argument("--all", action="store_true", required=True)

    status = verbs.add_parser("status")
    status.add_argument("--json", action="store_true")
    return parser


COMMANDS = {
    "create": command_create,
    "reset": command_reset,
    "delete": command_delete,
    "start": command_start,
    "status": command_status,
}


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        return COMMANDS[arguments.verb](arguments)
    except OperatorError as error:
        print(f"branch-runtime: {error}", file=sys.stderr)
        return error.code


if __name__ == "__main__":
    sys.exit(main())
