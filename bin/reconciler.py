#!/usr/bin/env python3
"""The reconciler: the control plane's operations, executed on this host as root (ADR 0256).

Invoked by `bin/reconciler.sh` -- by the unit `agentic-postgres-reconciler.service`
(`run`) and by an operator (`once`, `status`, `install`).

**A customer's request reaches root only as a validated row of a closed type.**
The reconciler opens no socket and binds no port (D2151): it reaches the
control project's database the way `bin/control.sh` does -- `psql` as the
superuser through `container_exec.run`, calling functions the control set
grants to nobody -- and pulls one `pending` operation at a time. Each is
validated against `schemas/operation-arguments.schema.json` before anything
runs, and executed as argv LISTS of the existing `bin/` commands built by
`agentic_postgres.reconciler_dispatch` (D2154), with stdin `/dev/null` and
output to `/var/log/agentic-postgres/reconciler/<operation>-<step>.log` (0600).
A line this command prints names an operation, a step, an exit code, the key
and the profile -- never another argument's value.

**Never resume** (D2152). At start, before its first claim, every operation
still `running` was interrupted: it is finished `failed interrupted` naming its
last step, and an interrupted `project.create` quarantines its slot -- a
creation is not idempotent end to end (`auth-admin bootstrap` refuses a second
run), so running one twice is the failure.

**It acts for the operator who owns the checkout** (D2153): every child carries
`SUDO_UID`/`SUDO_GID` = the checkout's owner, so a deploy hands
`.generated/<key>` back as a `sudo` deploy does -- and git, run as root on that
operator's checkout, answers only with them (rig 38g: without, `dubious
ownership`, exit 128). A root-owned checkout is refused.

**It refuses to run on a moved checkout** (D2179): HEAD and the porcelain
status are read at start, and an operation is finished `failed
could_not_determine {"reason": "checkout moved"}` when HEAD differs or the tree
is dirty. A ship stops the unit first (D2178); `/run/agentic-postgres/reconciler.lock`
serialises a `once` beside the unit.

Verbs:
  run      recover, record the slots, then claim and handle one operation at a
           time, polling every 5 s (the unit's verb)
  once     recover, record the slots, handle at most one operation, exit
  status   `idle`, `working on <id> (<type>, step <step>)`, or `stopped (...)`
  install  the unit and its environment file, the log and export directories;
           daemon-reload; enable --now

Exit codes: 0 done; 2 invalid input; 3 a prerequisite is missing (root, a
checkout not owned by root, the host manifest, a control project, docker); 5
two control projects (D2168); 6 something could not be read, or the control
database stopped answering mid-operation (the unit restarts, and recovery
finishes that operation `interrupted`).
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml  # noqa: E402

from agentic_postgres import (  # noqa: E402
    CURRENT_SESSION,
    config,
    container_exec,
    control_registry,
    deployed_output,
    host_config,
    slot,
)
from agentic_postgres import reconciler_dispatch as dispatch  # noqa: E402
from agentic_postgres.config import ManifestError  # noqa: E402
from agentic_postgres.control_registry import OperatorError  # noqa: E402
from agentic_postgres.secret_generation import SECRET_ROOT as DEFAULT_SECRET_ROOT  # noqa: E402

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_REFUSED = 5
EXIT_UNKNOWN = 6

#: The roots this command reads and writes; module globals so a proof can move them.
STATE_ROOT = deployed_output.PROJECT_STATE_ROOT
SLOT_ROOT = slot.SLOT_ROOT
SECRET_ROOT = DEFAULT_SECRET_ROOT
LOG_ROOT = Path("/var/log/agentic-postgres/reconciler")
RUN_ROOT = Path("/run/agentic-postgres")
EXPORT_ROOT = Path("/var/lib/agentic-postgres/exports")
SYSTEMD_DIR = Path("/etc/systemd/system")
ENVIRONMENT_FILE = Path("/etc/agentic-postgres/reconciler.env")
#: The checkout's own host manifest: what admission and the deploy read (D2020).
HOST_MANIFEST = REPO_ROOT / "host.yaml"

UNIT = "agentic-postgres-reconciler.service"

#: How often an idle reconciler looks for work, and how often it re-records the
#: slot reading even when idle: the control mode refuses a reading older than
#: ten minutes (D2160), so an idle host must keep it fresh.
POLL_SECONDS = 5
RECORD_SECONDS = 120

#: An operation's bound, and each child's own (ADR 0256 §8). A child that
#: outlives its bound leaves its step's outcome unknown: `could_not_determine`.
OPERATION_SECONDS = 30 * 60
CHILD_SECONDS = {
    "admit.sh": 120,
    "deploy.sh": 900,
    "auth-admin.sh": 300,
    "database-ports.sh": 300,
    "systemctl": 60,
    "backup.sh": 1200,
    "project-runtime.sh": 300,
    "project-retire.sh": 900,
    "docker": 60,
}
DATABASE_SECONDS = 120
#: `pg_dump` of a slot's customer schemas, and its upload (D2164).
EXPORT_SECONDS = 900
#: The download URL's life: `app/export_upload.py`'s `EXPORT_URL_SECONDS`,
#: which a test holds equal (the URL's own `X-Amz-Expires` is what binds).
EXPORT_URL_SECONDS = 900

#: `admit.sh`'s refusal (ADR 0221): the host cannot take the candidate.
ADMISSION_REFUSED = 12

#: The deploy reaches through the release's own session (D2186): this
#: release's `CURRENT_SESSION`, never a typed number.
THROUGH_SESSION = CURRENT_SESSION

#: A checkout path written into the unit's environment file: no space, quote
#: or newline can reach systemd's parser through it.
_CHECKOUT_PATH = re.compile(r"/[A-Za-z0-9._/-]+")


class Refused(Exception):
    """The operation is finished `failed` with `code`; `members` join its result."""

    def __init__(self, code: str, members: dict[str, Any]) -> None:
        super().__init__(code)
        self.code = code
        self.members = members


class ControlError(Exception):
    """The control database refused a call, or did not answer it."""


def require_root() -> None:
    if os.geteuid() != 0:
        raise OperatorError(
            EXIT_PREREQUISITE,
            "must run as root: every command an operation runs is root's, and the control "
            "plane is reached through its database container as the superuser.",
        )


def checkout_owner(checkout: Path = REPO_ROOT) -> tuple[int, int]:
    """The uid and gid the children act for (D2153); a root-owned checkout is refused."""
    info = checkout.stat()
    if info.st_uid == 0:
        raise OperatorError(
            EXIT_PREREQUISITE,
            f"{checkout} is owned by root: the reconciler acts for the operator who owns the "
            "checkout (SUDO_UID, D2153) and a root checkout names nobody.",
        )
    return info.st_uid, info.st_gid


def child_environment(owner: tuple[int, int]) -> dict[str, str]:
    environment = dict(os.environ)
    environment["SUDO_UID"], environment["SUDO_GID"] = str(owner[0]), str(owner[1])
    return environment


def checkout_reading(owner: tuple[int, int], checkout: Path = REPO_ROOT) -> tuple[str, str]:
    """`(HEAD, porcelain status)` of the checkout. Read-only git, as its owner's
    proxy -- the reconciler never runs a git command that changes anything."""
    readings = []
    for argv in (["git", "rev-parse", "HEAD"], ["git", "status", "--porcelain"]):
        done = subprocess.run(
            argv,
            cwd=checkout,
            env=child_environment(owner),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if done.returncode != 0:
            raise OSError(f"{' '.join(argv)} exited {done.returncode}")
        readings.append(done.stdout.strip())
    return readings[0], readings[1]


#: The DNS reading for a slot (D2148) -- `slot.dns_reading`, named here so a
#: proof can replace it on this command alone.
dns_reading = slot.dns_reading


# ---------------------------------------------------------------------------
# The control database
# ---------------------------------------------------------------------------


class Control:
    """The control project's database, as its superuser (D2093)."""

    def __init__(self, container: str, database: str) -> None:
        self.container = container
        self.database = database

    def call(self, sql: str, **variables: str) -> str:
        return database_call(self.container, self.database, sql, variables)


def database_call(container: str, database: str, sql: str, variables: dict[str, str]) -> str:
    """One `psql` as the superuser, every value set on stdin (D2154); stdout,
    or ControlError carrying psql's last line."""
    try:
        done = container_exec.run(
            container,
            "psql", "-U", "postgres", "-d", database, "-X", "-qtA", "-v", "ON_ERROR_STOP=1",
            "-f", "-",
            input=dispatch.psql_input(sql, variables),
            timeout=DATABASE_SECONDS,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ControlError(f"{database} did not answer ({type(error).__name__})") from error
    if done.returncode != 0:
        lines = (done.stderr or "").strip().splitlines()
        raise ControlError(lines[-1] if lines else f"psql exited {done.returncode}")
    return done.stdout.strip()


def control_target() -> Control:
    """The one deployed control project (D2168): two is exit 5, and the unit retries."""
    control = control_registry.find_control(
        control_registry.read_all(root=STATE_ROOT), decision=True
    )
    return Control(*control_registry.target(control.document or {}))


def load_host() -> dict[str, Any]:
    if not HOST_MANIFEST.is_file():
        raise OperatorError(EXIT_PREREQUISITE, f"host manifest not found: {HOST_MANIFEST}")
    try:
        return host_config.load_host_manifest(HOST_MANIFEST)
    except (OSError, ValueError) as problem:
        raise OperatorError(EXIT_INPUT, f"the host manifest is refused: {problem}") from problem


def say(line: str) -> None:
    """One journal line: an operation, a step, an exit code, a key, a profile."""
    print(f"reconciler: {line}", flush=True)


def _write_private(path: Path, text: str, *, exclusive: bool = False) -> None:
    """`text` at `path`, 0600, durable; with `exclusive`, never over an existing file."""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, text.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_private(path: Path, data: bytes) -> None:
    """`data` at `path` by a 0600 temporary renamed over it."""
    handle = tempfile.NamedTemporaryFile(dir=path.parent, delete=False, prefix=f".{path.name}.")
    candidate = Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(candidate, 0o600)
        os.replace(candidate, path)
    except BaseException:
        candidate.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# One operation
# ---------------------------------------------------------------------------


class Operation:
    """A claimed row, and what its handler may do: steps, children, databases."""

    def __init__(self, reconciler: Reconciler, row: dict[str, Any]) -> None:
        self.reconciler = reconciler
        self.id = str(uuid.UUID(str(row["id"])))
        self.type = str(row["type"])
        self.arguments = row.get("arguments")
        self.organization_id = str(row["organization_id"])
        self.project_key: str | None = row.get("project_key")
        self.steps: list[dict[str, Any]] = []
        self.current: str | None = None
        self.deadline = time.monotonic() + OPERATION_SECONDS
        #: The slot a creation took, and the manifest bytes it was prepared with.
        self.allocated: str | None = None
        self.original_manifest: bytes | None = None
        #: An export's download URL (D2164): finished into `result_secret`,
        #: never into `result`, never printed, never logged.
        self.secret: str | None = None

    @contextlib.contextmanager
    def step(self, name: str) -> Iterator[None]:
        progress = dict(dispatch.STEPS[self.type])[name]
        self.current = name
        self.advance(progress)
        self.reconciler.state(self, name)
        say(f"{self.id} {self.type} step {name}")
        started = time.monotonic()
        try:
            yield
        finally:
            self.steps.append({"step": name, "seconds": round(time.monotonic() - started, 1)})

    def advance(self, progress: int | None = None, *, project_key: str | None = None) -> None:
        if progress is None:
            progress = dict(dispatch.STEPS[self.type])[self.current or ""]
        self.reconciler.control.call(
            dispatch.PROGRESS_SQL,
            id=self.id,
            step=self.current or "",
            progress=str(progress),
            project_key=project_key or "",
        )
        if project_key:
            self.project_key = project_key

    def remaining(self, bound: float) -> float:
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise Refused("could_not_determine", {"reason": "the operation's 30 minutes ran out"})
        return min(bound, left)

    def child(
        self,
        argv: list[str],
        *,
        capture: bool = False,
        pass_fds: tuple[int, ...] = (),
    ) -> subprocess.CompletedProcess:
        """One command: stdin `/dev/null`, acting for the checkout's owner,
        output appended to this step's 0600 log -- and, with `capture`, also
        returned (admission's verdict is read from it)."""
        name = Path(argv[0]).name
        timeout = self.remaining(CHILD_SECONDS[name])
        log = self.reconciler.log_path(self.id, self.current or "operation")
        descriptor = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                handle.write(f"== {datetime.now(UTC).isoformat(timespec='seconds')} {name}\n")
                handle.flush()
                options: dict[str, Any] = {
                    "cwd": REPO_ROOT,
                    "env": child_environment(self.reconciler.owner),
                    "stdin": subprocess.DEVNULL,
                    "timeout": timeout,
                    "check": False,
                    "text": True,
                    "pass_fds": pass_fds,
                }
                if capture:
                    done = subprocess.run(argv, capture_output=True, **options)
                    handle.write((done.stdout or "") + (done.stderr or ""))
                else:
                    done = subprocess.run(argv, stdout=handle, stderr=subprocess.STDOUT, **options)
                handle.write(f"== exit {done.returncode}\n")
        except subprocess.TimeoutExpired as error:
            say(f"{self.id} step {self.current} {name} outlived its bound")
            raise Refused(
                "could_not_determine",
                {"reason": f"{name} did not finish within {int(timeout)} s"},
            ) from error
        say(f"{self.id} step {self.current} {name} exit {done.returncode}")
        return done

    def require(self, done: subprocess.CompletedProcess, what: str) -> None:
        if done.returncode != 0:
            raise Refused("operation_failed", {"reason": f"{what} exited {done.returncode}"})

    def project_value(self, document: dict[str, Any], sql: str, **variables: str) -> str:
        """One value from the PROJECT's database, as its superuser, or Refused."""
        database = document.get("database") or {}
        try:
            answer = database_call(
                str(database["container"]), str(database["name"]), sql, variables
            )
        except (KeyError, ControlError) as error:
            raise Refused(
                "could_not_determine", {"reason": "the project's database did not answer"}
            ) from error
        lines = [line for line in answer.splitlines() if line.strip()]
        if len(lines) != 1:
            raise Refused(
                "could_not_determine",
                {"reason": "the project's database answered in a shape nobody asked for"},
            )
        return lines[0].strip()


# ---------------------------------------------------------------------------
# project.create (D2173)
# ---------------------------------------------------------------------------


def _slot_manifest(key: str) -> Path:
    return slot.slot_directory(key, root=SLOT_ROOT) / slot.MANIFEST


def _deployed(key: str) -> dict[str, Any]:
    path = deployed_output.deployed_path(key, root=STATE_ROOT)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return deployed_output.read_deployed_document(raw)
    except (OSError, ValueError) as error:
        raise Refused(
            "could_not_determine", {"reason": "the deployed document could not be read"}
        ) from error


def allocate(operation: Operation, profile: str) -> str:
    """A `ready` slot: its marker written (the operation's id), its manifest
    re-written with the requested profile and loaded by the product."""
    rows = slot.observe(
        operation.reconciler.host,
        dns=dns_reading,
        slot_root=SLOT_ROOT,
        state_root=STATE_ROOT,
        secret_root=SECRET_ROOT,
    )
    ready = [row["key"] for row in rows if row["state"] == "ready"]
    if not ready:
        raise Refused("capacity_exhausted", {"reason": "no_slot"})
    key = ready[0]
    marker = slot.slot_directory(key, root=SLOT_ROOT) / slot.ALLOCATED
    try:
        _write_private(marker, operation.id + "\n", exclusive=True)
    except FileExistsError as error:
        raise Refused("capacity_exhausted", {"reason": "no_slot"}) from error
    operation.allocated = key
    manifest = _slot_manifest(key)
    original = manifest.read_bytes()
    operation.original_manifest = original
    _replace_private(manifest, _with_profile(original, key, operation.id, profile))
    try:
        config.load_project_manifest(manifest)
    except ManifestError as error:
        release(operation)
        raise Refused(
            "could_not_determine", {"reason": "the slot's manifest was refused by the loader"}
        ) from error
    operation.advance(project_key=key)
    say(f"{operation.id} took slot {key} at profile {profile}")
    return key


def _with_profile(original: bytes, key: str, operation_id: str, profile: str) -> bytes:
    """A slot manifest's bytes with `compute.profile` set; nothing else moves."""
    document = yaml.safe_load(original)
    document["compute"] = {"profile": dispatch.profile_name(profile)}
    return (
        f"# Slot {key}, re-written by the reconciler for operation {operation_id} "
        f"(ADR 0256): compute {profile}.\n" + yaml.safe_dump(document, sort_keys=False)
    ).encode("utf-8")


def release(operation: Operation) -> None:
    """The slot back to `ready`: its prepared manifest restored, its marker removed.
    Only before anything was rendered or deployed (D2160)."""
    if operation.allocated is None:
        return
    directory = slot.slot_directory(operation.allocated, root=SLOT_ROOT)
    if operation.original_manifest is not None:
        _replace_private(directory / slot.MANIFEST, operation.original_manifest)
    (directory / slot.ALLOCATED).unlink(missing_ok=True)
    say(f"{operation.id} returned slot {operation.allocated}")
    operation.allocated = None


def administrator(operation: Operation, key: str, username: str, handoff_sha256: str) -> None:
    """The first administrator and the handoff by hash (ADR 0260, D2163).

    The password is random, written to a pipe the child inherits, and held by
    nothing afterwards -- the member chooses theirs by presenting the token
    whose hash opens the reset."""
    outputs = deployed_output.deployed_path(key, root=STATE_ROOT)
    read_end, write_end = os.pipe()
    try:
        try:
            os.write(write_end, (secrets.token_urlsafe(32) + "\n").encode("ascii"))
        finally:
            os.close(write_end)
        done = operation.child(
            dispatch.bootstrap_argv(REPO_ROOT, outputs, username, read_end),
            pass_fds=(read_end,),
        )
    finally:
        os.close(read_end)
    operation.require(done, "auth-admin bootstrap")
    document = _deployed(key)
    user = operation.project_value(document, dispatch.ADMIN_ID_SQL, username=username)
    reset = operation.project_value(
        document, dispatch.OPEN_HANDOFF_SQL, user=str(uuid.UUID(user)), hash=handoff_sha256
    )
    uuid.UUID(reset)


def ports(operation: Operation, key: str, manifest: Path) -> None:
    """The port reservation, then `verify` with an argv BUILT from the volume's
    identity read from the database -- never the line the render printed."""
    operation.require(
        operation.child(dispatch.runtime_render_argv(REPO_ROOT, manifest)), "the runtime render"
    )
    instance = operation.project_value(_deployed(key), dispatch.INSTANCE_UUID_SQL)
    try:
        argv = dispatch.verify_argv(REPO_ROOT, instance)
    except ValueError as error:
        raise Refused(
            "could_not_determine", {"reason": "the volume's identity is not a uuid"}
        ) from error
    operation.require(operation.child(argv), "database-ports verify")


def refresh_registry(operation: Operation, key: str, display_name: str) -> str | None:
    """The project's registry row from its deployed document (D2167); the
    display name is written here and nowhere else."""
    document = _deployed(key)
    fields, reason = control_registry.document_fields(key, document)
    if fields is None:
        raise Refused("could_not_determine", {"reason": reason})
    region = (document.get("region") or {}).get("id")
    profile = (document.get("compute") or {}).get("profile") or ""
    app = (document.get("routes") or {}).get("app")
    app_route = app.get("url") if isinstance(app, dict) else None
    operation.reconciler.control.call(
        dispatch.ADOPT_SQL,
        key=key,
        organization=operation.organization_id,
        **fields,
        region=region or "",
        profile=profile,
        slot=key,
        app_route=app_route or "",
        display_name=display_name,
    )
    return region


def create(operation: Operation) -> dict[str, Any]:
    arguments = operation.arguments
    profile = arguments["profile"]
    with operation.step("allocate"):
        key = allocate(operation, profile)
    manifest = _slot_manifest(key)
    outputs = deployed_output.deployed_path(key, root=STATE_ROOT)

    with operation.step("admit"):
        # Before anything is rendered or deployed: a refusal leaves nothing (D2160).
        done = operation.child(dispatch.admit_argv(REPO_ROOT, manifest), capture=True)
        if done.returncode != 0:
            release(operation)
            if done.returncode == ADMISSION_REFUSED:
                raise Refused(
                    "capacity_exhausted",
                    {"reason": "admission", "refusal": admission_reason(done.stdout)},
                )
            raise Refused("operation_failed", {"reason": f"admission exited {done.returncode}"})
    deploy = dispatch.deploy_argv(REPO_ROOT, manifest, through_session=THROUGH_SESSION)
    with operation.step("deploy-1"):
        operation.require(operation.child(deploy), "the first deploy")
    with operation.step("admin"):
        administrator(operation, key, arguments["admin_username"], arguments["handoff_sha256"])
    with operation.step("ports"):
        ports(operation, key, manifest)
    with operation.step("deploy-2"):
        operation.require(operation.child(deploy), "the second deploy")
    with operation.step("unit"):
        operation.require(operation.child(dispatch.enable_argv(key)), "systemctl enable")
    with operation.step("backup"):
        for verb in dispatch.BACKUP_SEQUENCE:
            operation.require(
                operation.child(dispatch.backup_argv(REPO_ROOT, outputs, verb)),
                "backup " + " ".join(verb),
            )
    with operation.step("registry"):
        region = refresh_registry(operation, key, arguments["name"])
    return {"project_key": key, "profile": profile, "region": region}


def admission_reason(stdout: str) -> str:
    """Admission's own sentence for its refusal, from `--json`; a fixed one if
    the verdict could not be read."""
    try:
        reason = json.loads(stdout).get("reason")
    except (ValueError, AttributeError):
        reason = None
    return reason if isinstance(reason, str) and reason else "admission refused (exit 12)"


# ---------------------------------------------------------------------------
# The other five types (Run 7): sleep, wake, resize, export, delete
# ---------------------------------------------------------------------------


def slot_project(operation: Operation) -> tuple[str, dict[str, Any]]:
    """The operation's project, which must be a DECLARED slot with a deployed
    document. Alpha, beta and the control project are operator-managed: a
    request naming one is refused before anything runs -- the reconciler never
    stops, resizes, exports or retires a project it did not create."""
    key = operation.project_key or ""
    declared = {entry.key for entry in host_config.declared_slots(operation.reconciler.host)}
    if key not in declared:
        raise Refused(
            "invalid_request",
            {"reason": "the reconciler acts on slot projects only; this one is operator-managed"},
        )
    return key, _deployed(key)


def require_running(operation: Operation, document: dict[str, Any]) -> None:
    """The database container runs, or Refused: a sleeping project is woken
    first (`invalid_request`, its state unchanged); no answer is the third
    outcome (`could_not_determine`)."""
    container = str((document.get("database") or {}).get("container", ""))
    done = operation.child(dispatch.running_argv(container), capture=True)
    answer = (done.stdout or "").strip()
    if done.returncode == 0 and answer == "true":
        return
    if done.returncode == 0 and answer == "false":
        raise Refused("invalid_request", {"reason": "the project is sleeping; wake it first"})
    raise Refused(
        "could_not_determine",
        {"reason": "whether the project's database runs could not be read"},
    )


def _through(document: dict[str, Any]) -> int:
    """The session the project was deployed through: its unit's, its runtime's."""
    session = document.get("deployed_through_session")
    if not isinstance(session, int) or isinstance(session, bool):
        raise Refused("could_not_determine", {"reason": "the deployed document names no session"})
    return session


def sleep(operation: Operation) -> dict[str, Any]:
    """D2155: the timers disabled (a timer firing would start the project), the
    boot unit disabled, the containers stopped and kept."""
    key, document = slot_project(operation)
    outputs = deployed_output.deployed_path(key, root=STATE_ROOT)
    session = _through(document)
    with operation.step("schedule"):
        operation.require(
            operation.child(dispatch.backup_argv(REPO_ROOT, outputs, ("schedule", "disable"))),
            "backup schedule disable",
        )
    with operation.step("unit"):
        operation.require(operation.child(dispatch.disable_argv(key)), "systemctl disable")
    with operation.step("stop"):
        operation.require(
            operation.child(dispatch.runtime_argv(REPO_ROOT, key, session, "stop")),
            "project-runtime stop",
        )
    return {}


def wake(operation: Operation) -> dict[str, Any]:
    """The same containers started (nothing materialized, D2155), the boot unit
    enabled, the timers enabled."""
    key, document = slot_project(operation)
    outputs = deployed_output.deployed_path(key, root=STATE_ROOT)
    session = _through(document)
    with operation.step("start"):
        operation.require(
            operation.child(dispatch.runtime_argv(REPO_ROOT, key, session, "start")),
            "project-runtime start",
        )
    with operation.step("unit"):
        operation.require(operation.child(dispatch.enable_argv(key)), "systemctl enable")
    with operation.step("schedule"):
        operation.require(
            operation.child(dispatch.backup_argv(REPO_ROOT, outputs, ("schedule", "enable"))),
            "backup schedule enable",
        )
    return {}


def resize(operation: Operation) -> dict[str, Any]:
    """Admission on a CANDIDATE manifest -- the slot's own with the new profile,
    beside it -- before anything changes (D2160): a refusal is
    `capacity_exhausted {admission}` with the manifest untouched and nothing
    rendered. Admitted, the candidate replaces the manifest, one deploy, the
    registry row refreshed."""
    key, document = slot_project(operation)
    profile = operation.arguments["profile"]
    manifest = _slot_manifest(key)
    with operation.step("admit"):
        require_running(operation, document)
        candidate = manifest.with_name(f".candidate.{operation.id}.yaml")
        _write_private(
            candidate,
            _with_profile(manifest.read_bytes(), key, operation.id, profile).decode("utf-8"),
            exclusive=True,
        )
        try:
            try:
                config.load_project_manifest(candidate)
            except ManifestError as error:
                raise Refused(
                    "could_not_determine",
                    {"reason": "the resized manifest was refused by the loader"},
                ) from error
            done = operation.child(dispatch.admit_argv(REPO_ROOT, candidate), capture=True)
            if done.returncode == ADMISSION_REFUSED:
                raise Refused(
                    "capacity_exhausted",
                    {"reason": "admission", "refusal": admission_reason(done.stdout)},
                )
            if done.returncode != 0:
                raise Refused("operation_failed", {"reason": f"admission exited {done.returncode}"})
            os.replace(candidate, manifest)
        finally:
            candidate.unlink(missing_ok=True)
    with operation.step("deploy"):
        operation.require(
            operation.child(
                dispatch.deploy_argv(REPO_ROOT, manifest, through_session=THROUGH_SESSION)
            ),
            "the deploy",
        )
    with operation.step("registry"):
        refresh_registry(operation, key, "")
    return {"profile": profile}


def export(operation: Operation) -> dict[str, Any]:
    """D2164: `pg_dump` of the customer's schemas to a root 0600 file, streamed
    into the project's storage container, which writes it to its own bucket and
    prints one presigned GET valid 900 s; the local file removed whatever
    happened. The URL is the operation's secret, never its result."""
    key, document = slot_project(operation)
    database = document.get("database") or {}
    archive = EXPORT_ROOT / f"{operation.id}.dump"
    try:
        with operation.step("dump"):
            require_running(operation, document)
            done = container_exec.run(
                str(database.get("container", "")),
                *dispatch.dump_argv(str(database.get("name", ""))),
                timeout=operation.remaining(EXPORT_SECONDS),
                text=False,
            )
            if done.returncode != 0 or not done.stdout:
                raise Refused("operation_failed", {"reason": f"pg_dump exited {done.returncode}"})
            EXPORT_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(EXPORT_ROOT, 0o700)
            descriptor = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(descriptor, done.stdout)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            say(f"{operation.id} step dump: {len(done.stdout)} bytes")
        with operation.step("upload"):
            found = operation.child(dispatch.storage_container_argv(key), capture=True)
            names = (found.stdout or "").split()
            if found.returncode != 0 or len(names) != 1:
                raise Refused(
                    "could_not_determine",
                    {"reason": "the project's storage container could not be found"},
                )
            body = archive.read_bytes()
            uploaded = container_exec.run(
                names[0],
                "python", "-m", "app.export_upload", "--operation", operation.id,
                input=body,
                timeout=operation.remaining(EXPORT_SECONDS),
                text=False,
            )  # fmt: skip
            if uploaded.returncode != 0:
                raise Refused(
                    "operation_failed", {"reason": f"the upload exited {uploaded.returncode}"}
                )
            lines = uploaded.stdout.decode("utf-8", "replace").strip().splitlines()
            if len(lines) != 1 or not lines[0].startswith("https://") or " " in lines[0]:
                raise Refused(
                    "could_not_determine",
                    {"reason": "the upload answered in a shape nobody asked for"},
                )
            operation.secret = lines[0]
            expires = datetime.now(UTC) + timedelta(seconds=EXPORT_URL_SECONDS)
            say(f"{operation.id} step upload: uploaded; the URL is the operation's secret")
    finally:
        archive.unlink(missing_ok=True)
    return {
        "sha256": hashlib.sha256(body).hexdigest(),
        "size_bytes": len(body),
        "expires_at": expires.isoformat(timespec="seconds"),
    }


def delete(operation: Operation) -> dict[str, Any]:
    """D2158: the retirement -- data destroyed, the provider deferred to the
    operator's `slot.sh revoke` -- then the tombstone no command removes, then
    the registry row marked deleted (D2167)."""
    key, _document = slot_project(operation)
    directory = slot.slot_directory(key, root=SLOT_ROOT)
    with operation.step("retire"):
        operation.require(
            operation.child(dispatch.retire_argv(REPO_ROOT, key, directory / "retirement.json")),
            "project-retire",
        )
    with operation.step("tombstone"):
        with contextlib.suppress(FileExistsError):
            _write_private(directory / slot.CONSUMED, operation.id + "\n", exclusive=True)
    with operation.step("registry"):
        operation.reconciler.control.call(dispatch.MARK_DELETED_SQL, key=key)
    return {}


#: The closed table's executing half: one handler per type of `dispatch.STEPS`.
HANDLERS: dict[str, Callable[[Operation], dict[str, Any]]] = {
    "project.create": create,
    "project.sleep": sleep,
    "project.wake": wake,
    "project.resize": resize,
    "project.export": export,
    "project.delete": delete,
}


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


class Reconciler:
    def __init__(
        self,
        control: Control,
        host: dict[str, Any],
        owner: tuple[int, int],
        baseline: tuple[str, str],
    ) -> None:
        self.control = control
        self.host = host
        self.owner = owner
        self.baseline = baseline
        self.worker = f"{socket.gethostname()}:{os.getpid()}"

    # -- files ----------------------------------------------------------------

    def log_path(self, operation_id: str, step: str) -> Path:
        LOG_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(LOG_ROOT, 0o700)
        return LOG_ROOT / f"{operation_id}-{step}.log"

    def state(self, operation: Operation | None, step: str | None = None) -> None:
        """What `status` reads: the operation being worked on, or nothing."""
        path = RUN_ROOT / "reconciler.state.json"
        if operation is None:
            path.unlink(missing_ok=True)
            return
        RUN_ROOT.mkdir(parents=True, exist_ok=True)
        payload = {"operation": operation.id, "type": operation.type, "step": step}
        handle = tempfile.NamedTemporaryFile(
            "w", dir=RUN_ROOT, delete=False, prefix=".reconciler.state."
        )
        with handle:
            json.dump(payload, handle)
        os.chmod(handle.name, 0o644)
        os.replace(handle.name, path)

    @contextlib.contextmanager
    def lock(self) -> Iterator[bool]:
        """`/run/agentic-postgres/reconciler.lock`, held for one operation (D2178)."""
        RUN_ROOT.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(RUN_ROOT / "reconciler.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            yield True
        finally:
            os.close(descriptor)

    # -- the control plane ----------------------------------------------------

    def finish(
        self,
        operation_id: str,
        status: str,
        code: str | None,
        result: dict,
        secret: str | None = None,
    ) -> None:
        self.control.call(
            dispatch.FINISH_SQL,
            id=operation_id,
            status=status,
            error_code=code or "",
            result=json.dumps(result, sort_keys=True),
            secret=secret or "",
        )
        say(f"{operation_id} {status}" + (f" {code}" if code else ""))

    def record_slots(self) -> None:
        """The slot reading the control mode refuses creations by (D2160). A
        failure is reported and the reading goes stale -- which the control
        mode reads as no slot, failing closed."""
        try:
            rows = slot.observe(
                self.host,
                dns=dns_reading,
                slot_root=SLOT_ROOT,
                state_root=STATE_ROOT,
                secret_root=SECRET_ROOT,
            )
            payload = [{k: row[k] for k in ("key", "state", "region_id")} for row in rows]
            self.control.call(dispatch.RECORD_SLOTS_SQL, slots=json.dumps(payload))
        except (OSError, ValueError, ControlError) as error:
            say(f"the slot reading was not recorded: {error}")
            return
        say("slots " + (", ".join(f"{r['key']} {r['state']}" for r in rows) or "none declared"))

    def recover(self) -> int:
        """D2152: every operation still running was interrupted. Finished failed,
        never resumed; an interrupted creation quarantines its slot."""
        rows = json.loads(self.control.call(dispatch.INTERRUPTED_SQL) or "[]")
        for row in rows:
            self.finish(str(row["id"]), "failed", "interrupted", {"step": row.get("step")})
            if row.get("type") == "project.create":
                self.quarantine(str(row["id"]), row.get("project_key"))
        return len(rows)

    def quarantine(self, operation_id: str, project_key: str | None) -> None:
        """The slot whose `allocated` marker names this operation -- or, failing
        that, the row's key -- marked `quarantined` for the operator."""
        taken = None
        for entry in host_config.declared_slots(self.host):
            marker = slot.slot_directory(entry.key, root=SLOT_ROOT) / slot.ALLOCATED
            with contextlib.suppress(OSError):
                if marker.read_text(encoding="utf-8").strip() == operation_id:
                    taken = entry.key
        if taken is None and project_key and slot.SLOT_KEY.fullmatch(project_key):
            taken = project_key
        if taken is None:
            say(f"{operation_id} was interrupted before it took a slot")
            return
        with contextlib.suppress(FileExistsError):
            _write_private(
                slot.slot_directory(taken, root=SLOT_ROOT) / slot.QUARANTINED,
                operation_id + "\n",
                exclusive=True,
            )
        say(f"{operation_id} was interrupted: slot {taken} quarantined (D2152)")

    def claim(self) -> dict[str, Any] | None:
        answer = self.control.call(dispatch.CLAIM_SQL, worker=self.worker)
        return json.loads(answer) if answer else None

    # -- one operation --------------------------------------------------------

    def cycle(self) -> bool:
        """At most one operation, under the host-wide lock. True when one ran."""
        with self.lock() as held:
            if not held:
                return False
            row = self.claim()
            if row is None:
                return False
            try:
                self.handle(Operation(self, row))
            finally:
                self.state(None)
            self.record_slots()
            return True

    def handle(self, operation: Operation) -> None:
        try:
            moved = checkout_reading(self.owner) != (self.baseline[0], "")
        except (OSError, subprocess.TimeoutExpired):
            moved = True
        if moved:
            self.finish(operation.id, "failed", "could_not_determine", {"reason": "checkout moved"})
            return
        handler = HANDLERS.get(operation.type)
        if handler is None:
            self.finish(
                operation.id,
                "failed",
                "invalid_request",
                {"reason": f"this release does not execute {operation.type}"},
            )
            return
        problem = dispatch.invalid(operation.type, operation.arguments)
        if problem is not None:
            self.finish(operation.id, "failed", "invalid_request", {"reason": problem})
            return
        code: str | None = None
        try:
            members = handler(operation)
        except Refused as refusal:
            members, code = dict(refusal.members), refusal.code
        except ControlError:
            # A refusal mid-step (the database answered no). If it stopped
            # answering instead, the finish below raises too, the unit
            # restarts, and recovery finishes this operation `interrupted`.
            members = {"reason": "the control database refused a call"}
            code = "could_not_determine"
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            members = {"reason": f"{type(error).__name__} during the step"}
            code = "could_not_determine"
        if code is not None and operation.current is not None:
            members["step"] = operation.current
        members["steps"] = operation.steps
        self.finish(
            operation.id,
            "failed" if code else "succeeded",
            code,
            dispatch.result(operation.type, members),
            operation.secret if code is None else None,
        )


# ---------------------------------------------------------------------------
# The verbs
# ---------------------------------------------------------------------------


def start() -> Reconciler:
    require_root()
    owner = checkout_owner()
    host = load_host()
    control = control_target()
    try:
        head, porcelain = checkout_reading(owner)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OperatorError(EXIT_UNKNOWN, f"the checkout could not be read: {error}") from error
    if porcelain:
        say("the checkout is dirty: every operation will be refused until it is clean (D2179)")
    reconciler = Reconciler(control, host, owner, (head, porcelain))
    reconciler.state(None)
    say(f"control project {control.container}; checkout {head[:12]}; worker {reconciler.worker}")
    try:
        recovered = reconciler.recover()
    except ControlError as error:
        raise OperatorError(EXIT_UNKNOWN, f"the control database: {error}") from error
    if recovered:
        say(f"{recovered} interrupted operation(s) finished failed (D2152)")
    reconciler.record_slots()
    return reconciler


def run(*, once: bool) -> int:
    reconciler = start()
    recorded = time.monotonic()
    while True:
        try:
            worked = reconciler.cycle()
        except ControlError as error:
            # Mid-operation, the row stays `running` and the restart's recovery
            # finishes it `interrupted`; idle, the claim simply failed.
            raise OperatorError(EXIT_UNKNOWN, f"the control database: {error}") from error
        if once:
            return EXIT_OK
        if time.monotonic() - recorded >= RECORD_SECONDS:
            reconciler.record_slots()
            recorded = time.monotonic()
        if not worked:
            time.sleep(POLL_SECONDS)


def systemctl(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", *argv],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def status() -> int:
    """`idle`, `working on …`, or `stopped (…)`; exit 6 when it could not be read."""
    try:
        active = systemctl("is-active", UNIT).stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"reconciler: could not determine ({type(error).__name__})")
        return EXIT_UNKNOWN
    if active != "active":
        last = systemctl("show", "-p", "ExecMainStatus", "--value", UNIT).stdout.strip()
        print(
            f"stopped ({active or 'unknown'}; last exit {last or 'unknown'}) -- "
            f"journalctl -u {UNIT} says why"
        )
        return EXIT_OK
    try:
        state = json.loads((RUN_ROOT / "reconciler.state.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        print("idle")
        return EXIT_OK
    except (OSError, ValueError):
        state = None
    if not isinstance(state, dict) or not all(k in state for k in ("operation", "type", "step")):
        print("reconciler: could not determine: the state file is unreadable")
        return EXIT_UNKNOWN
    print(f"working on {state['operation']} ({state['type']}, step {state['step']})")
    return EXIT_OK


def install() -> int:
    """The unit, verbatim; its environment file naming this checkout; the log
    and export directories; then daemon-reload and enable --now."""
    require_root()
    checkout_owner()
    if not _CHECKOUT_PATH.fullmatch(str(REPO_ROOT)):
        raise OperatorError(
            EXIT_INPUT, f"the checkout path {REPO_ROOT} cannot be written into a unit's environment"
        )
    source = REPO_ROOT / "systemd" / UNIT
    shutil.copyfile(source, SYSTEMD_DIR / UNIT)
    os.chmod(SYSTEMD_DIR / UNIT, 0o644)
    ENVIRONMENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENVIRONMENT_FILE.write_text(f"APG_CHECKOUT={REPO_ROOT}\n", encoding="utf-8")
    os.chmod(ENVIRONMENT_FILE, 0o644)
    for directory in (LOG_ROOT, EXPORT_ROOT):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
    for argv in (("daemon-reload",), ("enable", "--now", UNIT)):
        done = systemctl(*argv)
        if done.returncode != 0:
            raise OperatorError(
                EXIT_UNKNOWN, f"systemctl {' '.join(argv)} exited {done.returncode}"
            )
    print(f"reconciler: installed {SYSTEMD_DIR / UNIT} for {REPO_ROOT}; enabled and started")
    return EXIT_OK


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="reconciler.sh", add_help=False)
    verbs = top.add_subparsers(dest="verb", required=True)
    for verb in ("run", "once", "status", "install"):
        verbs.add_parser(verb, add_help=False)
    return top


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = parser().parse_args(argv)
    except SystemExit:
        return EXIT_INPUT
    try:
        if arguments.verb in ("run", "once"):
            return run(once=arguments.verb == "once")
        if arguments.verb == "status":
            return status()
        return install()
    except OperatorError as error:
        print(f"reconciler: {error}", file=sys.stderr)
        return error.code


if __name__ == "__main__":
    raise SystemExit(main())
